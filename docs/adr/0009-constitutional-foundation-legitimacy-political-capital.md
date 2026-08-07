# ADR 0009: Constitutional foundation, legitimacy and political capital

- Status: accepted
- Date: 2026-08-07

## Context

Phases 2A–2C2 built a fully derived economic chain ending in physical resource extraction driving
production, tax bases, revenue and treasury. Every number in that chain is derived, reconciled and
hash-protected. What the game still lacked was an economy with **no politics attached to it**: a
reserve could deplete, output could collapse by 10%, and nothing about the player's hold on power
changed, because there was no representation of how authority is organised, how accepted it is, or
what governing costs.

Phase 3A adds the smallest deterministic political foundation later phases can build parties,
legislatures, elections, coups and repression onto **without rebuilding the state model**. It stops
well short of political gameplay: no removal from power, no elections, no factions, no repression.
It establishes the nouns (constitution, legitimacy, political capital), the one-way
economic→political linkage, and the report/invariant/history scaffolding those later phases need.

`docs/roadmap.md`'s Phase 3 entry previously bundled political capital, legislative/faction
bargaining and government-survival mechanics into one oversized item. This ADR's companion roadmap
change splits it: **3A** (this ADR) is the constitutional and metric foundation; **3B** is
political-capital expenditure and legislative/faction bargaining; **3C** is government survival
(elections, coups, removal).

**The governing principle:** the engine models *whether a constitutional order is internally
coherent* and *how accepted it currently is* (authored, then moved by economics). It never encodes
an opinion about which forms of government deserve acceptance.

## Decisions

### Legitimacy is form-blind by construction, not by convention (R1)

An early draft derived a legitimacy *anchor* from constitutional form — parliamentary democracy
around 8,100, monarchy around 3,100 — an engine-level moral hierarchy. That anchor table is
**deleted outright, not rebalanced**. `simulation/legitimacy.py` is a pure module whose public
functions take only integers and dataclasses of integers; **no function in it accepts a
`ConstitutionState`, an `ExecutiveSystem`, or any other constitutional type.** This is a
compile-time, `mypy`-checked guarantee, stronger than any test: government form cannot influence
legitimacy because the type signature makes it unreachable.

In its place, `PoliticalState.constitutional_order_support_bps` is **scenario-authored** —
chosen the same way `remaining_stock` or a tax rate is chosen, never derived from
`ConstitutionState`'s axes. Legitimacy drifts toward this authored value by a fixed,
form-independent rate (`DRIFT_RATE_BPS = 1,000`, 10% of the gap per turn), identically for every
government form. A monarchy authored at 8,500 and a democracy authored at 8,500 receive exactly
the same drift; a monarchy at 2,000 and a democracy at 2,000 likewise agree. `test_legitimacy_
neutrality.py` proves this with five authored orders spanning accepted/illegitimate monarchy and
accepted/unpopular democracy, all following the same economic shock, and pins their agreement
turn by turn.

### The neutrality claim is a six-field numeric projection, never byte identity (R4)

Two countries with different constitutions necessarily have different `ConstitutionState`s,
`constitution_digest`s, `state_json`, `PoliticalReport`s, `TurnReport`s and `entry_hash`es —
claiming otherwise would be false. What is proven identical, exactly, is six explicitly enumerated
fields per turn:

```
order_support_contribution_bps, performance_contribution_bps, total_legitimacy_change_bps,
closing_legitimacy_bps, political_capital_regeneration, closing_political_capital
```

`test_legitimacy_neutrality.py` asserts both halves live at once: the six fields agree, *and* the
two constitutions' digests genuinely differ — so the comparison cannot silently degenerate into
comparing nothing. Same-input determinism (two independent runs of the *same* scenario with the
*same* decisions producing byte-identical `state_json`/`report_json`/`entry_hash`) is a distinct
property, already covered by `test_determinism.py`'s existing whole-state/whole-report canonical-
JSON comparisons now that `politics`/`political` are ordinary fields.

### Performance signals carry genuinely unbounded intermediates (R5)

`output_change_bps` is not scale-bounded: a baseline of 1 rising to 3 is +20,000 bps, and larger
rebounds go further; a complete collapse is exactly −10,000 bps (the one point where the negative
direction happens to fit the ±10,000 legitimacy scale). Typing every political bps field
`StrictSignedLegitimacyBps` (±10,000) would reject arithmetically correct values. `core/politics.py`
therefore introduces two signed aliases: `StrictSignedBps` (unbounded, for raw rates and their
uncapped intermediates — `output_change_bps`, `output_contribution_bps`) and
`StrictSignedLegitimacyBps` (±10,000, for quantities a formula provably keeps in scale —
`unemployment_change_bps`, the two `_contribution_bps` fields, and `total_legitimacy_change_bps`,
each independently re-derived and capped by a report validator, which is a stronger guarantee than
a type bound because a validator can distinguish a correctly-capped value from an uncapped one).

`trunc_div_toward_zero` — the single rounding step used by every signed political formula — now
**requires `denominator > 0` and raises otherwise**, rather than silently returning 0. The one
legitimate zero-denominator case (a zero previous-turn output baseline) is handled explicitly by
the caller, `assess_economic_performance`, which tests `baseline_output == 0` *before* dividing and
returns `output_change_bps = 0` directly — stating the precondition where it is decided, not
absorbing it silently in the helper. Truncation is toward zero, not Python's floor-toward-negative-
infinity `//`: political deltas are the codebase's first genuinely signed quantities, and flooring
would give a systematic pessimism bias (a −1.39% change flooring to −139 bps while a symmetric
+1.39% gain rounds to +138). `deficit_demo` turn 41's `-138` (not floor's `-139`) is pinned by both
`test_legitimacy.py` and, end to end through the real resolver, `test_political_economy_linkage.py`.

### The baseline is a turn-scoped observation record with a four-stage lifecycle (R2)

`EconomicBaselineState` (`source_turn`, `total_gross_output`, `unemployment_rate_bps`) is written
by the political phase from that same turn's own already-validated economic reports, never
scenario-authored, and read the following turn as the opening baseline. Four stages: **read** the
prior closing baseline as this turn's opening (may be `None`), **assess** performance against it,
**write** this turn's observations as the new closing baseline, **report** everything into
`PoliticalReport`. The first resolved turn always has `opening_economic_baseline is None` and
therefore exactly zero performance contribution — a zero-output baseline is never fabricated,
since `None` and `total_gross_output == 0` are different states.

`OpeningPoliticalSnapshot` (a frozen dataclass mirroring the pre-existing `OpeningFinanceSnapshot`)
is captured, by value, at the start of the phase handler, before any mutation — so the report's
"opening" values cannot be retroactively changed by the same handler's later writes, and
`PoliticalReport` never needs, and never gets, a `GameState` reference.

### Reconciliation against state is a resolver-level function, not a `TurnReport` validator (R2/R3/R7)

`TurnReport` is constructed from reports alone and has no `GameState` reference — the same
structural limit that produced a late Phase 2C2 deviation, caught here before implementation began.
`resolve_turn` already holds, in one scope, the caller's untouched input `state` and the mutated
`working` copy; `simulation/reconciliation.py`'s `reconcile_political_report(*, opening_state,
closing_state, report)` is a separate pure function taking both, called immediately after
`TurnReport(...)` is built and before `TurnResolution` is returned. A nonempty result raises
`TurnResolutionError` and discards the working copy, exactly like an invariant violation.

Eleven check groups, not a fixed comparison count (two groups compare an *optional* baseline, so a
headline number would mislead): opening/closing legitimacy and political capital against state (4
checks); the opening and closing economic baseline against state, each either both `None` or all
three fields equal (2 checks); **each of the nine `ConstitutionSummary` fields against both opening
and closing `ConstitutionState`, independently** (18 checks) — a digest alone is not a substitute,
since the report's summary fields and its digest are stored independently and could disagree with
each other; the digest against `constitution_digest()` of both states (2 checks); authored
`constitutional_order_support_bps` against both states (2 checks); and `political_capital_capacity`
against both states (2 checks). Every field within every group is independently corruptible and
independently rejected (`test_reconciliation.py`), proving that constitution, authored support and
capacity are genuinely static in Phase 3A as a runtime property, not merely a claim.

Finance reconciliation (`FinanceReport.closing_cash` vs `TreasuryState.cash_on_hand`) is a real
pre-existing gap, unrelated to this phase's approved signals (unemployment, gross output), and is
explicitly out of scope — recorded as follow-up ticket FIN-1, not bundled in as a "free" addition.

### History replay re-runs report validation and reconciliation, not just the hash chain (R2, §9.4)

`validate_history` already built a full `GameState` per entry and ran `check_invariants` on it, but
never parsed `report_json`. Phase 3A extends `_validate_entry_payload` so each non-genesis entry
also (1) parses `report_json` via `TurnReport.model_validate_json` — automatically re-running all
ten `PoliticalReport` self-validators and all `TurnReport` cross-validators — and (2) calls
`reconcile_political_report` with the previous entry's parsed state as `opening_state` and this
entry's as `closing_state`, threaded forward through the existing loop with no additional state
parse. This is what makes a **consistently re-hashed** tamper detectable: editing `legitimacy_bps`
and recomputing `entry_hash` to match produces a chain that passes every hash check but still fails
reconciliation (`test_history.py`'s T-R7 tests) — a strictly stronger guarantee than the
traditional stale-hash tamper detection every earlier phase relied on alone (also independently
covered, for political fields specifically, by the traditional-tamper tests added alongside T-R7).

This is the one change in the phase with a measurable performance cost: `validate_history` is
already O(n²) by design (`docs/architecture.md`'s "correctness over performance" boundary), and
adding a `TurnReport` parse per entry multiplies that constant. Measured immediately before and
after this commit, all three 100-turn soaks stayed at roughly 1.5-1.6x their pre-change duration —
safely within the plan's ~2× stop threshold; no fallback (splitting `validate_history` into a
cheap chain check plus an explicit deep pass) was needed.

### `MONARCHICAL` becomes a fourth `ExecutiveSystem`, resolving an incoherent pairing (R8)

An early draft represented monarchy as `PRESIDENTIAL + HEREDITARY`, which is incoherent: a
presidential system's defining feature is a separately-originated executive answerable to an
electorate, and a hereditary office is neither. `ExecutiveSystem` gains `MONARCHICAL`, and the
combination rules (C1–C9) grow two members to make the distinction real: **C6**
(`hereditary_requires_monarchical_system`) — `HEREDITARY` implies `MONARCHICAL`; **C7**
(`monarchical_requires_hereditary_or_appointed`) — `MONARCHICAL` implies selection is `HEREDITARY`
or `APPOINTED` (elective monarchies stay representable). **C3**
(`presidential_forbids_legislative_selection`) is narrowed to reject only `LEGISLATIVE_SELECTION`
under `PRESIDENTIAL` — its inheritance half is now C6's exclusive responsibility, which is what
makes C6 reachable as a first violation at all (C1/C2 already catch `PARLIAMENTARY + HEREDITARY`,
C4 catches `SEMI_PRESIDENTIAL + HEREDITARY`, leaving `PRESIDENTIAL + HEREDITARY` as the only
combination for C6 to own).

`executive_election_interval_turns` is renamed `national_election_interval_turns`: a parliamentary
national election selects a *legislature*, which then selects the executive — the electorate never
votes for the executive directly — so the old name was wrong for exactly the case it needed to
describe. **C9** (`national_election_requires_something_elected`) is rewritten to require a
legislature *or* direct election, correctly admitting the parliamentary case the old executive-only
rule wrongly rejected.

The full configuration space is enumerated and checked computationally: 10,368 total
configurations (2,592 axis combinations × term-limit presence × election-interval presence), of
which 2,862 are valid and 7,506 rejected, with every one of C1–C9 independently reachable as a
first violation.

### Twelve state-structural invariant codes, and no others (§10)

`check_invariants(state: GameState)` takes only a `GameState`, so it can only decide what is
computable from state alone. `_check_politics` adds twelve codes mirroring `_check_economy`'s
shape: `player_politics_required`; `non_player_politics_not_supported` (see below);
`invalid_constitutional_combination`; range checks for `constitutional_order_support_bps`,
`legitimacy_bps`, `political_capital` (non-negative), `political_capital_capacity` (positive) and
`political_capital > capacity`; and three baseline-lifecycle codes tied to `state.turn`
(`economic_baseline_present_at_genesis`, `economic_baseline_missing_after_genesis`,
`economic_baseline_turn_mismatch`) plus one range check on the baseline's own unemployment field.

Deliberately **not** created: any code re-deriving a report formula (owned by `PoliticalReport`'s
ten self-validators, which run on every construction/replay/CLI path, not merely at `resolve_turn`'s
checkpoints) or comparing two states (owned by `reconcile_political_report`). `test_invariants.py`
pins this boundary with a static source-scan guard (T-V2) asserting none of those code families'
names ever appear in `invariants.py`.

**Non-player politics is rejected outright** (`non_player_politics_not_supported`), resolving an
ambiguity rather than leaving inert authored data lying around: only the player has an
`EconomyState`, hence only the player has the observations legitimacy is computed from, and a
non-player `PoliticalState` would be data the engine silently never updates. AI-country politics is
deferred to a follow-up ticket (POL-4), gated on AI countries first gaining economies.

### Phase wiring reuses slot 10, adding no sixteenth `PHASE_ORDER` slot (§8)

Four consecutive phases (2B2, 2B3, 2C1, 2C2) added real logic without adding a `PHASE_ORDER` slot;
Phase 3A follows the same convention, implementing the existing slot 10,
`update_group_welfare_approval_trust_radicalization`. The slot's name mentions "approval," and this
ADR insists legitimacy ≠ approval — sharing a resolution *slot* is a scheduling convenience, not a
concept merger. Every artefact produced is named `legitimacy`, never `approval`; nothing in this
phase reads or writes `PopulationGroupState.approval`. The handler is pure (no `ctx.rng()` calls —
drift and performance response are modeled relationships, not lotteries), mutates only the working
copy's `politics`, and cannot reach `economy`/`finance`/`treasury` by construction — proven by
`test_phase_isolation.py`'s T-I1/T-I2/T-I3 tests in both directions.

### Political capital regenerates on legitimacy alone; nothing spends it yet (§7)

`regeneration = 200 + trunc_div_toward_zero(legitimacy_bps * 300, 10_000)`, ranging 200 (zero
legitimacy) to 500 (full legitimacy) — a legitimate monarchy and a legitimate democracy at the same
`legitimacy_bps` regenerate identically, since the formula never sees government form. Closing
capital is `min(capacity, opening + regeneration - spent)`; `spent` is always 0 in Phase 3A
(pinned by `test_political_phase.py`'s T-P5) because passing laws needs a legislature with members,
negotiating factions needs factions, and reforms need a reform system — none of which exist yet.
The report already carries `political_capital_spent` so the reconciliation identity shipped here is
the one Phase 3B will use unchanged.

### Versioning: lockstep bump, schema-shape trigger (§11)

`RULESET_VERSION` `0.7.0 → 0.8.0`, `SUPPORTED_CONTENT_VERSIONS → {"0.8.0"}`, `SAVE_FORMAT_VERSION`
unchanged at 1 — the same lockstep every prior phase used. The trigger is schema shape:
`CountryState.politics` becomes required for the player, so old scenario YAML cannot construct a
valid player country without it. `backend/tests/fixtures/phase2c2_save_ruleset_0.7.0.json` was
generated with the genuinely unmodified 0.7.0 CLI and committed before any model or constant change
landed, mirroring the established fixture-freeze-before-bump discipline. No fabricated migration: an
older save has no constitution, no authored order support, no legitimacy and no political capital,
and none is invented — the save is simply rejected by `UnsupportedRulesetVersionError` before any
entry payload is parsed.

## Calibration

`tiny_valid.yaml` — parliamentary/legislative-selection/bicameral/unitary, strong judicial review,
`constitutional_order_support_bps = 8,000`, opening `legitimacy_bps = 7,000`, political capital
500/1,000. Flat economy (zero performance every turn) means legitimacy moves by order-support drift
alone: 7,000 → 7,100 (turn 1) → … → 7,991 (turn 100), monotone, never overshooting. Political
capital clamps to its 1,000 capacity from turn 2 onward, exercising the capacity clamp naturally
for the whole soak.

`deficit_demo.yaml` — presidential/direct-election/unicameral/unitary, weak judicial review,
`constitutional_order_support_bps = 6,500`, opening `legitimacy_bps = 6,000`, political capital
300/800. Reuses the same iron-ore/timber depletion shocks 2C2 already calibrated: turn 26
(iron-ore exhaustion) drops output 10%, giving `output_change_bps = -1,000`,
`performance_contribution_bps = -250`, closing legitimacy `6,459 → 6,213`; turn 41 (timber's
renewable steady state) is the truncation case, `output_change_bps = -138` (not floor's `-139`),
closing legitimacy `6,431 → 6,403`. Both boundaries are pinned exactly by
`test_political_economy_linkage.py`, reproducing depletion's legitimacy cost with no new economic
engineering and no invented effect — the existing extraction→production chain is the entire
mechanism.

## Known limitations

- **The five sensitivity constants** (`OUTPUT_SENSITIVITY_BPS`, `UNEMPLOYMENT_SENSITIVITY_BPS`,
  the two per-turn caps, `DRIFT_RATE_BPS`) are authored calibration, not derived from first
  principles. None is per-form — the R1 defect is structurally gone, not rebalanced — but 3B/3C may
  revise the magnitudes.
- **`constitutional_order_support_bps` is authored and static in Phase 3A.** A scenario author can
  correlate it with government form; that is their prerogative and does not compromise the engine's
  neutrality. Nothing in this phase moves it — 3B/3C amendments and coups will.
- **Neither committed fixture moves unemployment** (both flat at 1000 bps); that channel has only
  synthetic unit-test coverage (`test_legitimacy.py`). Recorded as follow-up ticket POL-3, mirroring
  2C2's own never-`LABOR_CONSTRAINED` gap.
- **`PopulationGroupState`/`InstitutionState` keep float `approval`/`trust`/`loyalty` fields**
  (Phase 0 scaffolding, read by no formula anywhere). Phase 3A neither extends nor converts this
  convention — out of scope, tracked as follow-up ticket POL-2 (migrate to strict integer bps,
  alongside deleting the now-corrected `core/money.py:clamp01_100` once truly unused code removal
  is in scope).
- **Political capital regenerates but nothing spends it in Phase 3A**, so it pins to capacity on
  both fixtures. Correct for this phase; spending arrives in 3B.
- **`TerritorialOrganization` is mechanically inert** — R1 removed its only effect (the deleted
  anchor table). Retained for save-schema stability and the constitution digest; stated plainly
  rather than disguised as a live mechanic.
- **`FinanceReport.closing_cash` vs `TreasuryState.cash_on_hand` remains unreconciled** — a
  pre-existing gap (dating to Phase 2A) unrelated to this phase's political scope. Recorded as
  follow-up ticket FIN-1.
- **AI-country politics is out of scope** — Phase 3A rejects non-player politics outright
  (`non_player_politics_not_supported`) rather than storing data the engine never updates. Recorded
  as follow-up ticket POL-4, blocked on AI countries first gaining economies.

## Consequences

- New modules: `core/politics.py` (metric aliases, `trunc_div_toward_zero`);
  `simulation/constitution.py` (axes, `ConstitutionState`, C1–C9, `constitution_digest`);
  `simulation/legitimacy.py` (pure performance/legitimacy/political-capital formulas);
  `simulation/reconciliation.py` (`reconcile_political_report`).
- `simulation/state.py` gains `PoliticalState`, `EconomicBaselineState`, `CountryState.politics`;
  `RULESET_VERSION` bumps `0.7.0 → 0.8.0`.
- `simulation/report.py` gains `ConstitutionSummary`, `EconomicBaselineReport`, `PoliticalReport`
  (ten self-validators) and `TurnReport.political` (three cross-validators); the all-present-or-
  all-absent completeness rule extends from five reports (30 rejected subsets) to six (62 rejected
  subsets).
- `simulation/phases.py` gains `OpeningPoliticalSnapshot` and implements slot 10's handler; no
  `PHASE_ORDER` change.
- `simulation/resolver.py` calls `reconcile_political_report` immediately after `TurnReport(...)`
  construction.
- `simulation/history.py`'s `validate_history` parses each entry's report and reconciles it against
  the neighbouring entry's state.
- `simulation/invariants.py` gains twelve new codes via `_check_politics`.
- Both scenario fixtures gain a `politics:` block on their player country only.
- `app/cli.py` gains legitimacy/political-capital renderers, an `inspect --politics` block, and a
  `history` political block on both display code paths (`resolve` and `history`).
- `production_accounting.py`, `resource_extraction.py`, `resource_output.py`, `labor_allocation.py`,
  `integer_allocation.py`, `accounting.py`, `tax_base_derivation.py`, `core/canonical_json.py`, and
  `core/quantity.py` are all **unmodified** by this phase.
- `RULESET_VERSION` bumps again: `0.7.0 → 0.8.0`.
  `backend/tests/fixtures/phase2c2_save_ruleset_0.7.0.json` was generated with unmodified
  Phase-2C2 code and committed *before* this bump landed.
- 827 → 944 backend tests: constitutional validity (C1–C9, full 10,368-configuration coverage),
  legitimacy/political-capital unit and Hypothesis-property tests, the form/support-independence
  matrix, the baseline lifecycle end to end, report self-validation and cross-checks (including the
  62-subset completeness rule), reconciliation (every field in every check group independently
  corruptible), history-replay revalidation (both consistently-rehashed and traditional stale-hash
  tampers), phase-isolation in both directions, resolver atomicity for stale decisions and invalid
  political state, the resource-depletion shock reproduced exactly through the real resolver, soak
  bounds and trajectories, a static guard against report-formula codes leaking into invariants, and
  CLI display coverage.
