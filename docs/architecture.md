# MANDATE — Architecture

## System boundaries

```
mandate/
  backend/
    app/
      core/         pure infrastructure: RNG, money type, error types — no game rules
      simulation/    pure game engine: state, decisions, phases, resolver, invariants — NO I/O
      api/           FastAPI routes (Phase 4+) — thin, delegates to simulation + services
      db/            SQLAlchemy models, session management (Phase 4+)
      models/        ORM row models (Phase 4+, distinct from simulation/state.py domain models)
      schemas/       Pydantic request/response DTOs for the API (Phase 4+)
      services/      orchestration: load state → call simulation → persist (Phase 4+)
      content/       loaders/validators for data-driven content (policies, events, scenarios)
      saves.py       disk I/O for save files: atomic writes/reads — outside core/simulation
      cli.py         headless entry point: create games, resolve turns, inspect history
    migrations/      Alembic (Phase 4+)
    tests/
  frontend/
    src/{App.tsx,main.tsx,styles/}   verified shell (Phase 0/1); gameplay screens start Phase 5
  data/
    scenarios/       validated scenario YAML (content, not code)
    events/          (Phase 8+)
    map/             (Phase 6+)
  docs/
  scripts/
  docker-compose.yml (Phase 4+: Postgres for local dev)
```

The load-bearing boundary is **`app/simulation` has zero dependencies on FastAPI, SQLAlchemy, or
any I/O**. It is a library: construct a `GameState`, submit a `DecisionSet`, call `resolve_turn`,
get back a new `GameState` and a `TurnReport`. Everything else in the backend (API routes, DB
persistence, the CLI) is a caller of that library, not part of it. This is what makes the engine
independently testable and keeps turn-resolution logic in one place instead of leaking into
request handlers.

`app/core` sits below `simulation`: infrastructure primitives (deterministic RNG, the `Money` type
alias, canonical JSON/hashing, shared error types) that carry no game-specific rules and that
`simulation` depends on. `app/saves.py` sits on the *other* side of the boundary from `simulation`:
it is the one module allowed to touch the filesystem (`tempfile`, `os`) for save I/O, and it is
deliberately a sibling of `app/core`/`app/simulation`, not inside either — see "History, hash
chaining, and immutability" below for why atomic file writes don't belong inside the pure engine.

## Deterministic simulation

Every `GameState` stores an integer `seed`. Any code that needs randomness during turn resolution
must request a `random.Random` instance from `core.rng.derive_rng(seed, turn, stream)`, which seeds
from a hash of `(seed, turn, stream_name)`. `stream_name` namespaces independent random draws (e.g.
`"events"` vs. `"combat"`) so that adding a new consumer of randomness in one system cannot shift
the sequence another system draws — a common source of "deterministic but fragile" bugs. Simulation
code must never read `random` module global state or wall-clock time directly; this is enforced by
an AST-based test (`tests/test_no_forbidden_imports.py`) that inspects every module under
`app/core` and `app/simulation` and fails if it imports `random` (only `app/core/rng.py` may) or
`time`/`datetime` `.now()`-style calls. The one exemption is imports inside `if TYPE_CHECKING:`
blocks: those never execute at runtime (doubly so under this codebase's universal `from __future__
import annotations`), so they cannot introduce non-determinism — this is what lets
`simulation/phases.py` annotate a method as returning `random.Random` without actually importing
`random`. `app/saves.py` is deliberately *outside* both scanned packages: its `tempfile`/`os` usage
is real, necessary non-determinism (unique temp filenames, filesystem timing), but it lives at the
I/O boundary, never inside a function that computes game state — see "History, hash chaining, and
immutability" below.

Determinism is verified by resolving the same scenario + seed + decisions twice, independently, and
comparing **canonical JSON** serializations of the resulting state and report byte-for-byte:
sorted object keys, fixed separators, no timestamps, no UUID4 values, no unordered-set
serialization, no environment-dependent fields (hostnames, PIDs, cwd). `core/canonical_json.py`
provides the single serialization path used by tests, save files, and (later) API responses, so
"deterministic" is actually machine-checked rather than asserted by eye.

## Turn resolution

`resolve_turn(state: GameState, decisions: DecisionSet) -> TurnResolution` is a pure function:

1. **Validate first, on the untouched input.** `validate_decision_set(state, decisions)` checks the
   decision set's `expected_turn`/`state_version` against `state.turn`/`state.version` and runs
   `check_invariants(state)` on the input. Any failure raises `TurnResolutionError` and returns
   before anything is copied — the caller's `state` object is provably untouched (checked with a
   pre/post equality assertion in tests, not just "we didn't call any mutators").
2. **Copy.** Only after validation passes, deep-copy `state` into a working copy.
3. **Run phases in the fixed order** from `simulation/phases.py::PHASE_ORDER`, mutating the copy.
   The 15-phase order from the product spec (§7) is encoded as data — a tuple of `(phase_id,
   handler)` — so the order is declared once, tested once (`test_resolver.py` asserts the exact
   sequence of phase IDs that ran), and cannot silently drift.
4. **Re-validate.** `check_invariants` runs again on the result. A violation discards the working
   copy and raises — the original `state` argument is still the untouched pre-turn state, giving
   the same "fully commits or leaves state unchanged" guarantee the database transaction will give
   at Phase 4, but provable in-process without a database.
5. **Return** `TurnResolution(state=new_state, report=TurnReport(...))`.

As of Phase 2C1, five of the fifteen phases implement real logic: decision validation, sector
production (see below — now also performing labor allocation and resource extraction first),
government accounting (three phases — see below, one of which also performs tax-base derivation),
and report generation. The remaining named phases (trade, prices,
diplomacy, combat, group welfare, institutional updates, unrest, elections, narrative events) are
still registered in `PHASE_ORDER` as explicit no-ops — each
phase handler exists and runs, but does nothing yet and records that fact in
`TurnReport.dev.phase_statuses: dict[str, Literal["implemented", "not_implemented"]]`, structured
metadata for developers/tests. It is **not** surfaced as repetitive entries in the player-facing
part of the report — the brief's "no placeholder feature claims" rule (§5.7) means absent behavior
is marked in dev metadata, not narrated to a hypothetical player as if it were content.
`test_resolver.py::test_only_the_accounting_and_report_phases_are_implemented_so_far` tracks this
boundary explicitly and is meant to be updated, not weakened, as more phases gain real logic.

### Sector production phase (Phase 2B1, labor allocation added in Phase 2B3, resource extraction added in Phase 2C1, extraction-sector output derivation replaced in Phase 2C2)

`resolve_production_and_trade` — the fixed §7 phase slot this fills; only production (plus, as of
Phase 2B3, the labor allocation that feeds it, and as of Phase 2C1, the resource extraction
sub-allocated from that same labor) is implemented, trade (imports/exports, cross-country flows)
is explicitly out of scope this phase — reads the player's `EconomyState` (required;
`simulation.invariants` enforces this the same way it requires player `finance`) and, at the very
start of the phase, derives this turn's labor allocation via the pure
`simulation/labor_allocation.py` engine (population, `effective_labor_force_share_bps`, and each
sector's capacity/productivity — see "Phase 2B3 labor allocation" below), assembling the
self-validating `LaborMarketReport` into `PhaseContext.labor_market_report`. Immediately after
that, it derives this turn's resource extraction via the pure `simulation/resource_extraction.py`
engine, sub-allocating the extraction sector's just-allocated workers across the eight resource
deposits (see "Phase 2C1 resource extraction" below), assembling the self-validating
`ResourceExtractionReport` into `PhaseContext.resources_report` — and, in that same step, writing
each deposit's closing stock back into the working `economy.resource_deposits`. It then computes
each sector's output via the pure `simulation/production_accounting.py` engine — labor-limited
output (using that sector's just-allocated workers, not a stored field), actual output (capped at
capacity), capacity-utilization bps, and constraint classification — **except for the EXTRACTION
sector**: as of Phase 2C2, that one row never calls `compute_sector_output` at all; its
`actual_output` is the physical-extraction bridge total computed in the same step as the resource
report (see "Phase 2C2 physical-extraction-derived output" below), and its
`capacity_utilization_bps`/`constraint` are derived from the potential-output total, never from
`quarterly_capacity_output`. The other ten sectors are byte-for-byte unaffected. Every row —
extraction included — still assembles into the same self-validating `ProductionReport` at
`PhaseContext.production_report` — no `FinanceScratch`-style intermediate workspace for any of the
three reports, since none of them span multiple phases the way accounting does. This phase runs
*before* the three accounting phases in `PHASE_ORDER` (unchanged — no reordering); it is written to
never read or write `ctx.finance`/`ctx.finance_report`/treasury/debt itself. As of Phase 2B2, the
revenue phase immediately after it *does* read `ctx.production_report` (see below) — that one,
one-directional read is deliberate and actively tested (`tests/test_phase_isolation.py`), not an
accidental crossing; nothing else reaches across the shared `PhaseContext` in either direction.
Full formulas: `docs/economy_methodology.md`. Design rationale:
`docs/adr/0004-sector-production-fixed-prices.md`,
`docs/adr/0006-labor-allocation-at-fixed-prices.md`,
`docs/adr/0007-resource-endowments-and-extraction.md`,
`docs/adr/0008-physical-extraction-derived-sector-output.md`.

### Phase 2B3 labor allocation

No new `PHASE_ORDER` slot: allocation runs at the *start* of `resolve_production_and_trade`,
immediately before per-sector output — same phase, same turn, so same-turn linkage (a population
or labor-force-share change affects production the turn it applies) is structural.
`SectorState.employed_workers` (Phase 2B1/2B2) is removed entirely; employment is now purely
derived and turn-local, stored only on `PhaseContext.labor_market_report` and copied onto
`TurnReport.labor_market` by `resolver.py`, alongside `production`, `tax_base_derivation`,
`finance`, and (as of Phase 2C1) `resources`. `TurnReport`'s cross-report validators extend from
three reports to four: `LaborMarketReport.allocated_workers` must match
`ProductionReport.employed_workers` per `SectorCategory` (matched by category identity, never
tuple position), and `labor_market`/`production`/`tax_base_derivation`/`finance` must be all
present or all absent. See `docs/economy_methodology.md` and
`docs/adr/0006-labor-allocation-at-fixed-prices.md` for the full formulas, the largest-remainder
allocation algorithm and its tie-breaking rule, and the calibration approach.

### Phase 2C1 resource extraction

No new `PHASE_ORDER` slot: extraction runs immediately after labor allocation, at the start of
`resolve_production_and_trade`, before per-sector production — same phase, same turn. The
extraction **sector's** just-allocated workers (`LaborMarketReport.sectors[EXTRACTION]
.allocated_workers`) are the budget, sub-allocated across the eight resource deposits by the
shared `simulation/integer_allocation.py` core (see below). Unlike every other helper in this
phase, resource extraction is **not** pure with respect to `ctx.state`: after computing each
deposit's closing stock, it writes that value straight back into
`economy.resource_deposits`, matched by `ResourceCategory` identity — never tuple position, and
never any field but `remaining_stock`. This is a deliberate, narrow exception to the phase's
otherwise-unchanged "never mutates state" contract; `resolve_production_and_trade` still never
reads or writes `ctx.finance`/`ctx.finance_report`/treasury/debt, and resource extraction itself
never touches anything but `resource_deposits`. Safe because the resolver's single deep copy and
its post-phase invariant re-check are unaffected by *which* phase performed a mutation — an
invariant violation later in the same `resolve_turn` call still discards the entire working copy.

`SectorState`'s labor supply and `EconomyState.resource_deposits`'s physical endowments were
originally fully isolated from production/tax bases/revenue (conservation-only boundary, D8) —
**this isolation boundary was deliberately reversed in Phase 2C2** (below); resource endowments
now determine the extraction sector's `RealOutput` directly. `TurnReport.resources:
ResourceExtractionReport | None` is a fifth report, copied onto `TurnReport` by `resolver.py`; the
completeness rule extends from four reports to five, and a cross-report validator checks
`labor_market.sectors[EXTRACTION].allocated_workers == resources.extraction_sector_workers`.

The shared largest-remainder allocation core (used by both labor and resources) lives in
`simulation/integer_allocation.py`, extracted verbatim from the pre-Phase-2C1 labor algorithm
since it had no labor-specific content. It is **order-sensitive by contract**, not
permutation-independent: `labor_allocation.allocate_workers` keeps its existing canonical-tuple
signature byte-for-byte unchanged, while `resource_extraction.allocate_extraction_workers` (the
one caller needing permutation independence) accepts a category-keyed mapping and canonicalizes to
`tuple(ResourceCategory)` order *before* calling the core. See `docs/economy_methodology.md` and
`docs/adr/0007-resource-endowments-and-extraction.md` for the full formulas, the
regeneration/ceiling/conservation identities, the status-classification tie-break, and the
calibration approach.

### Phase 2C2 physical-extraction-derived output

Still no new `PHASE_ORDER` slot, and `resource_extraction.py` (formulas, conservation,
regeneration) stays completely unmodified. In the same step that builds
`ResourceExtractionReport`, a new pure module (`simulation/resource_output.py`) converts each
deposit's extracted quantity — and, separately, its stock/capacity-bounded *potential* quantity —
into fixed-base-year `RealOutput` via a single named bridge function
(`core/quantity.extracted_resource_to_real_output`, mirroring
`base_year_real_output_to_money`'s shape: exact integer multiplication, no division). The
per-category coefficients live in the new `EconomyState.resource_output_coefficients` field.
Both totals — `extraction_sector_real_output`/`extraction_sector_potential_output` — are stored on
`ResourceExtractionReport`.

Immediately after, the sector-production loop's EXTRACTION branch (see above) reads those two
totals directly: `actual_output` is the real total (no capacity cap — `quarterly_capacity_output`
is not read); `capacity_utilization_bps` is `floor(real * 10_000 / potential)`, or `0` if
`potential == 0`; `constraint` comes from a shared classifier
(`report.classify_extraction_constraint`) also called by `TurnReport`'s cross-validator — the one
case in this codebase where a report-level check and its construction site deliberately share
code, because the classification itself has no freedom given `(potential, actual)` — what needs
independent re-derivation is whether those two inputs themselves are correct, which two *other*
new `TurnReport` cross-validators already establish. `actual_output > potential_output` is
rejected by validation at three independent layers, never assigned a business status, since
`resource_extraction.py`'s own `min()`-bounded extraction formula makes it provably unreachable via
any legitimate code path. See `docs/economy_methodology.md` and
`docs/adr/0008-physical-extraction-derived-sector-output.md` for the full formulas, the
no-clamp-needed proof, and the calibration approach.

### Phase 3A legitimacy and political capital

Still no new `PHASE_ORDER` slot: the political phase implements the existing slot 10,
`update_group_welfare_approval_trust_radicalization`, which runs after every economic phase (3-5)
so `ctx.production_report`/`ctx.labor_market_report` already exist and are self-validated. Sharing
that slot's name is a scheduling convenience, not a concept merger — legitimacy is never called
"approval" anywhere in the codebase, and nothing in this phase reads or writes
`PopulationGroupState.approval`.

The handler captures `OpeningPoliticalSnapshot` (`phases.py`, mirroring `OpeningFinanceSnapshot`) —
the player's constitution, authored order support, legitimacy, political capital and economic
baseline, by value, before any mutation — then calls the pure `simulation/legitimacy.py` functions
with two numbers read from the already-validated reports (`total_gross_output`,
`unemployment_rate_bps`) against the snapshot's baseline. `simulation/legitimacy.py` accepts no
constitutional type anywhere in its public signatures: government form cannot reach the legitimacy
formula, a guarantee `mypy` enforces at every call site, not merely a tested convention.
`constitutional_order_support_bps` is scenario-authored and static in Phase 3A — nothing here moves
it. The handler writes the resolved legitimacy, political capital and a fresh
`EconomicBaselineState` (this turn's own observations) back into `player.politics`, and builds
`PoliticalReport` from the snapshot plus those results — `PoliticalReport` never holds, and cannot
reach, a `GameState`.

`resolver.py` copies the political report onto `TurnReport.political`, then calls
`simulation/reconciliation.py`'s `reconcile_political_report(opening_state, closing_state, report)`
— a plain function, not a `TurnReport` validator, because `TurnReport` has no state reference at
all (the same structural limit a late Phase 2C2 deviation ran into). `resolve_turn` already holds
both the caller's untouched input state and the mutated working copy in one scope, which is what
lets this function exist without giving `TurnReport` itself any new capability. A nonempty result
raises `TurnResolutionError` before `TurnResolution` is returned, discarding the working copy
exactly like an invariant violation. `validate_history` calls the same function per history entry,
threading the previous entry's parsed state forward — see "Performance boundary" below for the
measured cost. See `docs/economy_methodology.md` for every formula and
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md` for the R1-R8
independent-review corrections applied before implementation.

### Government accounting phases (Phase 2A, extended in Phase 2B2)

`apply_legal_and_administrative_changes` captures a frozen `OpeningFinanceSnapshot`
(`phases.py`) — opening cash/debt, the previous tax policy and spending plan, by value, before
anything is mutated — then applies the turn's `BudgetDecision` (if any) to the player's active tax
policy and spending plan. `resolve_government_revenue_and_expenditure` first derives this turn's
tax bases from `ctx.production_report` via the pure `simulation/tax_base_derivation.py` engine
(reading each sector's `actual_output` from the production report, never re-deriving it — see
"Phase 2B2 tax-base derivation" below), then computes revenue, total spending, and quarterly
interest via the pure `simulation/accounting.py` engine using those derived bases.
`update_prices_inflation_employment_debt_reserves` resolves cash and debt for the quarter and
writes the result into the player's treasury (the phase name is the full §7 resolution-order
label; only the debt/reserves portion of it is implemented). `generate_turn_report` assembles the
self-validating `FinanceReport` from the accumulated `FinanceScratch` (a plain per-turn workspace
threaded through `PhaseContext.finance` — now also carrying `applied_tax_bases`, the derived bases
— no global state). Full formulas: `docs/economy_methodology.md`. Design rationale:
`docs/adr/0003-government-accounting.md`, `docs/adr/0005-production-derived-tax-bases.md`.

### Phase 2B2 tax-base derivation

No new `PHASE_ORDER` slot: derivation runs at the *start* of the existing
`resolve_government_revenue_and_expenditure` phase, since production (phase 3) already precedes
revenue (phase 4) — same-turn linkage is structural, not incidental. `GovernmentFinanceState
.tax_bases` (Phase 2A) is removed; tax bases are now purely derived and turn-local, stored only on
`PhaseContext.tax_base_derivation_report` and copied onto `TurnReport.tax_base_derivation` by
`resolver.py`, alongside `production` and `finance`. Three internally-valid reports are not enough
to prove the chain is consistent, so `TurnReport` adds its own cross-report validators: production's
`actual_output` must match derivation's input per `SectorCategory` (matched by category identity,
never tuple position), derivation's `derived_tax_bases` must exactly equal
`FinanceReport.tax_bases`, and `production`/`tax_base_derivation`/`finance` must be all present or
all absent — a partial combination is rejected as a broken audit chain. See
`docs/economy_methodology.md` and `docs/adr/0005-production-derived-tax-bases.md` for the full
formulas, the real-to-nominal unit bridge, and the calibration approach.

Accounting resolves for the **player country only** — `CountryState.finance` is optional, and
`simulation.invariants` requires it just for the player (AI countries may omit it; see the ADR).
Sector production (and, as of Phase 2B3, labor allocation) follows the identical pattern:
`CountryState.economy` is optional, `player_economy_required` requires it just for the player, and
`LaborMarketReport`/`ProductionReport`/`TaxBaseDerivationReport` are all player-only, mirroring
`FinanceReport`'s scope exactly.

## History, hash chaining, and immutability

`resolve_turn` has no notion of "the game so far" — it stays a pure function of one state and one
decision set. `app/simulation/history.py` adds that notion in a layer *above* the resolver rather
than inside it, because the two concerns are genuinely separate (correctly computing one
transition vs. durably and verifiably remembering the sequence that produced the current state) and
keeping them apart meant the resolver's existing test suite needed zero changes.

**Representation, not just a `frozen=True` flag, is what makes history immutable.** A frozen
wrapper around a mutable `GameState` does not make the `GameState` immutable — a caller can still
reach through it. `HistoryEntry` instead stores `state_json`/`decisions_json`/`report_json` as
canonical JSON **strings** plus plain `str`/`int`/`None` fields; there is no mutable object
anywhere inside a `HistoryEntry` or `GameSave` to reach. `.state()`/`.decisions()`/`.report()` and
`GameSave.current_state()` each parse a **fresh** model on every call, so two calls return two
independent objects and mutating either cannot touch what's stored
(`tests/test_history.py::test_mutating_retrieved_*`). `current_state` is derived from the final
entry rather than cached as a second mutable copy — "current state matches the final entry" holds
by construction, with nothing to independently drift.

**The hash chain protects the complete path to a state, not just the state.** Every entry's
`entry_hash` is a BLAKE2b-256 digest (`core.canonical_json.canonical_digest`) over the canonical
JSON of `{turn, previous_entry_hash, decisions, report, state, ruleset_version, content_version}`
— the submitted decisions and resulting report are covered, not only the resulting numbers.
Changing any of those seven fields on any entry breaks that entry's hash and every
`previous_entry_hash` link after it. A **chain-link check alone cannot catch tail truncation**
(deleting the last N entries leaves a shorter chain that is still internally consistent), so
`GameSave` also carries `entry_count` and `head_entry_hash`, each updated by exactly one
increment/replacement per successful `advance_game` call and untouched on failure.

**Two independent checks catch two different kinds of tampering.** `validate_history` checks both
(1) whether a stored payload's *parsed value* still matches its recomputed hash, and (2) whether
the *stored string itself* is still exactly its own canonical form
(`canonical_dumps(json.loads(s)) == s`). Editing a number breaks (1). Adding whitespace or
reordering keys inside a stored JSON string breaks (2) but not (1), since `json.loads` ignores
formatting — so (2) exists specifically to catch a class of tampering the hash chain alone would
miss. Neither check ever repairs what it finds; malformed stored data is reported as a problem, not
silently renormalized. Full details and the exact hash payload are in
`docs/adr/0002-snapshot-history-and-versioning.md`.

**What this is not.** The chain, `entry_count`, and `head_entry_hash` are unkeyed hashes over a
public algorithm — anyone editing a save file can recompute all of them. This is deterministic
*corruption and unsophisticated-tampering detection*, not anti-cheat security, and is never
described otherwise.

**Atomic writes use a unique temp file, not a deterministic one.** `app.saves.write_save_atomic`
creates a unique temp file in the destination's own directory (`tempfile.NamedTemporaryFile`),
writes and `fsync`s it, closes it, then `os.replace`s the destination, cleaning up on any failure.
Filesystem naming has no bearing on game-state determinism — it's not part of any canonical
payload, hash, or history — so there was nothing to gain by making it predictable, and a fixed name
would let concurrent writes to the same destination collide. Best-effort directory `fsync` after
the replace persists the rename itself where the platform supports it (skipped, not failed, on
platforms without a directory file descriptor to sync, e.g. Windows).

**Performance boundary.** `advance_game` runs `validate_history` (a full O(n) re-verification of
every entry's hash and chain link) before every single turn, so N sequential turns cost O(n²)
total. Phase 3A (§9.4 of its plan) extended this per-entry pass to also parse `report_json` into a
`TurnReport` and re-run `reconcile_political_report` against the neighbouring entry's state — a
genuinely new cost, not a free addition, deliberately measured before and after landing rather than
assumed. Using isolated git worktrees at the commit immediately before and immediately after this
change (one discarded warm-up run plus three measured runs each, median taken), all three 100-turn
soaks moved from a ~4.2-4.8s/100-turns (~42-48ms/turn) median to a ~6.3-7.1s/100-turns
(~63-71ms/turn) median — a ~1.48-1.50x ratio, safely under the ~2x stop threshold the plan set in
advance. Measured at n=100 (`tests/test_soak.py`) on the current `HEAD`, later commits (invariants,
CLI, additional tests) push this further: ~7.8-8.6s total, ~76-86ms/turn. This build favors
correctness over optimization — validation strength is not weakened to make this faster. If a
later phase's soak testing shows this matters at realistic game lengths, the options are
incremental tail-only validation (trust everything before the last known-good entry) or a trusted
in-memory session wrapper that validates once on load; neither is implemented without a measured
reason to.

## Money and bounded values

`Money` is declared as `Money: TypeAlias = int` in `core/money.py` (Python 3.11 target — no PEP 695
`type` statement). One unit = 1/100 of the in-fiction currency. All treasury, debt, revenue, and
expenditure fields use `Money`; arithmetic is plain integer arithmetic, so ledgers either reconcile
exactly or fail a test — no binary-float drift. `PopulationGroupState`/`InstitutionState`'s
approval/loyalty/trust fields (0–100 scale, Phase 0 scaffolding, read by no formula yet) are
`float` with a shared `clamp01_100` helper; they don't need to balance to zero the way money does,
only to stay in range, which `check_invariants` enforces.

Government-accounting fields (Phase 2A) use `StrictMoney`/`StrictSignedMoney`/`StrictBps` —
`Annotated[int, Field(strict=True, ...)]` aliases in `core/money.py`. Pydantic's `strict=True` on
an `int` field rejects whole-number floats (`10.0`), numeric strings (`"10"`), booleans (despite
`bool` being an `int` subclass in plain Python), NaN, and ±infinity — verified empirically rather
than assumed, and pinned by `tests/test_money.py`. Rate fields (`StrictBps`) are additionally
bounded to `[0, 10_000]` (0%–100%).

Phase 3A's political metrics (`core/politics.py`) follow the same strict-integer-bps convention,
**not** the float `approval`/`loyalty` convention — `legitimacy_bps` is a validated
`StrictLegitimacyBps`, never a `clamp01_100`-managed float. Two further aliases handle signed
deltas: `StrictSignedLegitimacyBps` (bounded to `[-10_000, 10_000]`, for quantities a formula
provably keeps in scale) and `StrictSignedBps` (genuinely unbounded, for raw rate changes like
`output_change_bps` that can exceed the legitimacy scale — a baseline of 1 rising to 3 is +20,000
bps). `trunc_div_toward_zero`, the one rounding step every signed political formula uses, requires
a positive denominator and raises otherwise, rather than silently treating a zero denominator as 0.

## Persistence: file-based now, database at Phase 4

Two storage shapes, kept deliberately separate — one built now, one designed for later:

- **Immutable snapshot history, built now, as files.** A `GameSave` (`simulation/history.py`) *is*
  the "new row per turn, never overwritten" model from the product spec (§5.4), just backed by a
  JSON file instead of a database table. `save_format.dump_save_json`/`load_save_json` are the pure
  (de)serialization; `app/saves.py` is the atomic disk I/O. `cli.py new` creates a save with one
  genesis entry; `cli.py resolve` appends N entries via `advance_game` and writes atomically,
  refusing to overwrite its input; `cli.py history` retrieves any past entry without mutating
  anything; `cli.py inspect` reports version/turn/entry-count/integrity status without requiring the
  save to be valid to inspect it.
- **Relational identity tables** (`games`, `countries`, `leaders`, …), for things queried by ID,
  joined, or listed (e.g. "list my saves" across many games at once) — genuinely deferred to Phase
  4, since nothing about listing/querying many games is needed to play one game end to end. At
  Phase 4, a `GameSave`'s entries become rows in a `game_snapshots` table (one immutable row per
  turn, same content, same hash chain) instead of array elements in a JSON file; the
  `history`/`save_format` modules do not need to change shape to make that move; the entries stay
  in this file-based form for local development and headless tooling regardless.

## Content and versioning

Scenarios are YAML. Parsing/validation is pure and lives in `app/simulation/scenario.py` (text in,
`GameState` out, no disk access); reading the file from `data/scenarios/` is the one line of I/O in
`app/content/scenarios.py`, which is otherwise where Phase 2+ content loaders (policies, events)
will live once those systems exist to validate against. Every `GameState` carries `ruleset_version`
and `content_version` strings (semver-ish, hand-bumped).

**`ruleset_version` is an engine constant, not scenario-authored.** `RULESET_VERSION` lives in
`simulation/state.py` and is stamped onto every game by `scenario._to_game_state` — a scenario file
declares `content_version` only. This changed in Phase 2A: Phase 1 let scenarios declare their own
`ruleset_version`, which meant content could claim compatibility with rules it had no data for. See
`docs/adr/0003-government-accounting.md`. `content_version` stays scenario-authored so that a
balance change to policy/event/scenario data does not retroactively alter already-resolved turns
loaded from an older snapshot.

A third, independent version — `save_format_version` (`simulation/save_format.py`) — covers the
shape of the save *file* itself, separate from both `ruleset_version` and `content_version`.
`save_format.check_compatibility` checks all three independently and raises a distinct exception
naming exactly which one is unsupported, rather than one generic "incompatible save" error. See
`docs/adr/0002-snapshot-history-and-versioning.md` for the compatibility policy and why the Phase-0
save format is rejected outright rather than migrated.

## Why not more, yet

FastAPI, SQLAlchemy, and Alembic are intentionally not exercised yet. The brief's phase discipline
(§38, §39) treats "playable and understandable game loop" and "deterministic, correct simulation"
as higher priority than API surface or UI, and explicitly warns against generating a large amount
of unverified code in one pass. `app/api`, `app/db`, `app/models`, `app/schemas`, `app/services`
are documented here as the target shape (git does not track empty directories, so they are not
created on disk until Phase 4 gives them contents).

The frontend toolchain *is* now installed and verified (`npm ci`, `tsc --noEmit`, `vite build`,
`vitest run` all pass in CI) — see `README.md` for the commands — but it remains a placeholder
shell with one render smoke test. No gameplay screens, API calls, routing, or state management are
implemented; those start at Phase 5 once there is a backend API for them to talk to. Building them
sooner would mean building UI against a save-file CLI it will never talk to in production.

Future domain model classes from the product spec (§8) that have no behavior yet — full
`GovernmentState`, `MilitaryState`, `DiplomaticRelationState`, party/election models, and so on —
are added in the phase that gives them behavior (see `docs/roadmap.md`), not stubbed out empty now.
An empty placeholder model is worse than no model: it looks like progress, has no tests worth
writing against it, and has to be redesigned anyway once its actual behavior is known.
