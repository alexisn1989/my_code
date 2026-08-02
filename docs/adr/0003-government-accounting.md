# ADR 0003: Government accounting and the Phase 2A ruleset bump

- Status: accepted
- Date: 2026-08-02

## Context

Phase 1 gave a deterministic, hash-chained turn resolver where 14 of 15 resolution phases were
honest no-ops. Phase 2A implements the first real gameplay chain: the player changes tax rates
and spending, revenue/spending/interest resolve, treasury and debt update, the outcome reconciles
exactly, and history records it. Full formulas live in `docs/economy_methodology.md`; this ADR
covers the design decisions and their tradeoffs.

## Decisions

### `RULESET_VERSION` moves from scenario content to an engine constant

Phase 1's `ScenarioDefinition.ruleset_version` was a YAML field, copied verbatim into
`GameState.ruleset_version`. That conflates two different things: which simulation *rules* a game
runs under (an engine property) versus which *content* it uses (a scenario property). Left as-is,
a hand-written scenario could declare `ruleset_version: 0.2.0` while providing none of the finance
data 0.2.0's rules require, and the engine would accept it. `RULESET_VERSION = "0.2.0"` is now a
constant in `app.simulation.state`, stamped onto every game by `simulation.scenario._to_game_state`;
scenarios declare `content_version` only. `ScenarioDefinition` uses `extra="forbid"`, so an old
scenario file that still has a `ruleset_version:` key fails to parse rather than being silently
accepted with a value nobody checks.

**Consequence**: this is a breaking format change for scenario YAML. `tiny_valid.yaml` and the new
`deficit_demo.yaml` both omit `ruleset_version`; a Phase-1-era scenario file with that key would
now fail to load. No such file exists outside this repository's own fixtures.

### Phase-1 saves are rejected, not migrated

`SUPPORTED_RULESET_VERSIONS` moved from `{"0.1.0"}` to `{RULESET_VERSION}` (`{"0.2.0"}`). A save
created under Phase 1 records only a bare `GameState` history with no budget decisions and no
finance state — there is no data a migration could construct 2A's accounting fields from. Rejected
outright with the existing `UnsupportedRulesetVersionError`, naming both the found and supported
versions, per the same policy `docs/adr/0002-snapshot-history-and-versioning.md` already
established for the Phase-0-to-Phase-1 save-format change.

**Consequence for testing**: once `RULESET_VERSION` is bumped, no code path can produce a genuine
Phase-1-era save anymore — every new game stamps `0.2.0`. `tests/fixtures/phase1_save_ruleset_0.1.0.json`
was generated with unmodified Phase-1 code and committed *before* this bump landed, specifically so
`tests/test_compatibility.py` has something real to reject. This is the only chance to produce such
a fixture; regenerating it later would require reverting the bump first.

### Accounting resolves for the player country only

`CountryState.finance: GovernmentFinanceState | None` is optional. The player country is required
to have it — enforced in `simulation.invariants.check_invariants` (a new `player_finance_required`
violation, checked pre- and post-resolution like every other invariant) rather than a bespoke
exception type, so a missing player budget inherits the resolver's existing guarantees for free:
no accounting attempted, no history entry appended, no output file written. AI countries may omit
`finance` freely — they have no decision-making of their own yet, so budget data for them would be
static numbers with nothing to consume them until AI countries exist as a real system.

**Alternative considered**: requiring finance on every country now, to avoid an "if you add AI
decisions later, remember to add finance data" trap. Rejected — it would force every future test
and scenario fixture to author full budget data for countries nothing yet reads, for a
Phase-6-shaped concern this phase has no way to validate is even the right shape.

### `FinanceReport` is self-validating, independent of the code that builds it

Every reconciliation equation and cross-total is re-derived by a `@model_validator(mode="after")`
on `FinanceReport` itself, run on *every* construction path — a fresh build in `phases.py`,
`model_validate` parsing a report back out of hash-protected history JSON, a loaded save, or CLI
`history` inspection. This is deliberately a second, independent code path from
`simulation.accounting` (which `phases.py` uses to *compute* the numbers in the first place): a bug
in one is likely to be caught by the other, and a hand-edited or corrupted report can never claim
`reconciliation_status == "reconciled"` when the numbers don't actually add up — that property is a
derived `@property`, not a stored field that construction could get out of sync with.

**Cost**: recomputing `compute_tax_revenue`/`compute_quarterly_interest` on every parse (including
every time a historical report is read back out of a save) is real, measured, accepted overhead —
see "Performance boundary" in `docs/architecture.md`, which already accepted the analogous cost for
full history revalidation on every `advance_game` call.

### Report entries use `reason_id` + `params`, never prose

A `TurnReportEntry`/`FinanceReport` created during turn resolution is stored inside
`simulation.history`'s hash-protected chain. Whatever text was baked in at that moment can never be
re-rendered or translated later without invalidating `entry_hash` — so no text is baked in.
`reason_id: str` + `params: dict[str, str | int]` describe *what happened*; `app.cli.REASON_RENDERERS`
renders that into English at display time, entirely outside history. This also directly satisfies
the product spec's localization requirement (§28, "use localization keys for user-facing strings
from the beginning") for free, rather than needing a later retrofit.

`render_entry` never raises: an unmapped `reason_id` or a renderer that can't parse its `params`
produces a visibly-labeled fallback string. `tests/test_reason_renderers.py` proves every
`reason_id` the engine can actually emit has a registered renderer — both by direct catalog
comparison and by running real resolver output (four different decision shapes) through it and
checking none hit the fallback.

### Opening state is captured by value, not by reference

`OpeningFinanceSnapshot` (`app.simulation.phases`) is a frozen dataclass capturing opening cash,
opening debt, the annual interest rate, tax bases, and the previous tax policy/spending plan,
before `apply_legal_and_administrative_changes` mutates anything. Its Pydantic-model-typed fields
are captured via `.model_copy()`, not a bare reference — `TaxPolicyState`/`SpendingPlanState` use
`validate_assignment=True`, which permits in-place field mutation (`obj.field = x`) on a live
instance. A bare reference would mean a *future* phase handler that mutates the working policy in
place (rather than replacing it wholesale, as the current handlers do) would silently corrupt what
that turn's report calls "opening," despite the outer snapshot being frozen. This was a real bug in
an earlier draft of this phase's code, found by writing the required opening-snapshot immutability
tests with an in-place mutation rather than only the reassignment case (which was already safe
either way) — see `tests/test_phases.py` and the commit that fixed it.

### `BudgetDecision` is not (yet) a discriminated union

It is the only decision kind Phase 2A defines. `DecisionSet.decisions: tuple[BudgetDecision, ...]`
is a plain homogeneous tuple rather than `Annotated[BudgetDecision | ..., Field(discriminator=...)]`
— a `Union` of one member is not a union. "At most one budget decision per `DecisionSet`" is a
`@model_validator` checking `len(self.decisions) <= 1`. When a second decision kind is introduced
(Phase 3+), that is the point to introduce real discriminated-union machinery — not before.

## Consequences

- Every backend test that constructs a player country via `tests/conftest.make_country` now gets a
  `GovernmentFinanceState` by default (`with_finance=True`), so the new invariant doesn't silently
  break unrelated Phase 1 coverage; tests that specifically want an AI-shaped country without
  finance pass `with_finance=False` explicitly.
- `tests/conftest.make_finance`'s default spending was scaled down to be genuinely
  sustainable (revenue exceeds spending + interest unconditionally, not just non-negative by
  construction) — needed for the 100-turn soak test to stay meaningful rather than dominated by an
  ever-growing deficit figure.
- Two scenario fixtures now exist for two different purposes: `tiny_valid.yaml` (sustainable,
  used broadly including the soak test) and `deficit_demo.yaml` (deliberately runs a deficit large
  enough to borrow, with every resulting figure hand-checked against the resolver and documented in
  its own header comment).
