# ADR 0008: Physical extraction drives extraction-sector output

- Status: accepted
- Date: 2026-08-06

## Context

Phase 2C1 landed a physically-conserved resource layer that is **economically inert by design**
(ADR 0007, D8): the extraction sector produces abstract `RealOutput` from `allocated_workers *
output_per_worker`, exactly like every other sector, while the same workers separately produce
tonnes and barrels that feed nothing. ADR 0007 records this plainly as limitation 2 — "two
descriptions of the same labor, not two connected activities" — and names the fix as its own
follow-up ticket, deliberately not attempted in the same phase because it moves tax bases and
revenue and needs its own calibration pass.

Phase 2C2 is that follow-up. It **replaces** (never adds to) the extraction sector's `RealOutput`
derivation with one computed from that turn's physical extraction:

```
population -> effective labor force -> sector labor allocation -> resource extraction
    -> extraction-sector RealOutput -> other-sector production -> production-derived tax bases
    -> tax revenue -> spending/interest -> treasury and debt
```

After this phase, depleting a reserve costs real revenue. That is the entire economic point.

This ADR also records the corrections made across three independent review rounds (R1–R10)
before implementation began, and the one deliberate, documented deviation from the approved plan
discovered during implementation (the invariant-code count — see "Known limitations" below).

## Decisions

### Replace, not add — the extraction sector stops calling `compute_sector_output`

The generic per-sector loop in `resolve_production_and_trade` (`phases.py`) special-cases exactly
one sector: for `SectorCategory.EXTRACTION`, it no longer calls `production_accounting.
compute_sector_output` at all. `production_accounting.py` itself — the pure, sector-agnostic
formula module — is **completely unmodified**; the extraction row simply stops being one of its
callers. The other ten sectors are unaffected, byte-for-byte, by anything in this phase.

### A named, non-lossy bridge — multiplication only, no rounding

`core/quantity.py` gains `StrictRealOutputPerResourceUnit` (`Annotated[int, Field(strict=True,
gt=0)]`) and `extracted_resource_to_real_output(*, extracted, real_output_per_unit) -> RealOutput`
— a real function, mirroring `base_year_real_output_to_money`'s established shape: explicit type
rejection (bool, non-int, negative `extracted`, non-positive coefficient), exact integer
multiplication, **no division anywhere**. The same function converts both the actual extracted
quantity and the potential (stock/capacity-bounded) quantity — one bridge, two call sites, per
category.

### Coefficients are scenario-authored state, strictly positive, canonical order rejected

`EconomyState.resource_output_coefficients: tuple[ResourceOutputCoefficient, ...]` — one
`{category, real_output_per_unit}` pair per `ResourceCategory`, all 8 required exactly once,
canonical order **rejected, not normalized** (following the resource-deposit precedent from ADR
0007 R3, not the four sector-order validators' normalize-on-reorder precedent).
`real_output_per_unit` is strictly positive (`gt=0`) — zero is deliberately never a legal
coefficient, keeping "extraction happened but yielded nothing" (impossible by type) cleanly
distinct from "nothing was extracted" (the only legal zero-contribution path). Persisted inside
`EconomyState`, the same container path as `resource_deposits`; part of `state_json` in every
`HistoryEntry`, hash-protected by the same BLAKE2b chain as everything else in state; validated
on every construction path (fresh build, save import, history replay) and independently
re-checked every `resolve_turn` call by `check_invariants`.

An engine-wide constant was rejected: arithmetic proves it is the only design where both
`tiny_valid.yaml` and `deficit_demo.yaml` preserve their turn-1 output exactly with honest round
integers — `tiny_valid` needs `timber = 1,000`; `deficit_demo` needs `timber = 10,000`. A single
constant would force a correction term into one fixture or the other.

### Potential output, not nominal capacity — the source of both the utilization formula and the no-clamp proof

Per deposit, alongside the actual extracted quantity, the bridge also converts
`potential_quantity = min(available_stock, extraction_capacity_per_turn)` — the same two terms
`resource_extraction.py`'s own extraction formula already computes, read from
`DepositExtractionResult`, requiring no change to that module at all. Summed and converted, this
gives `extraction_sector_potential_output`, which is what `capacity_utilization_bps` and
`constraint` are computed against for the extraction row — **never** `quarterly_capacity_output`,
the legacy sector-level field every other sector still uses.

This one substitution is what eliminates the need for a saturating clamp. Per deposit,
`extracted_i = min(available_i, capacity_i, allocated_i * output_per_worker_i)` is a `min` over
the same two terms as `potential_quantity_i = min(available_i, capacity_i)` plus one more term, so
`extracted_i <= potential_quantity_i` unconditionally — dropping a `min` term can only keep or
raise the result. Multiplying by a positive coefficient and summing preserves the inequality:
`extraction_sector_real_output <= extraction_sector_potential_output` always, by construction. The
ratio therefore never needs clamping to satisfy `StrictBps`'s `[0, 10_000]` bound — it is exact and
lossless, exactly as it already was for every other sector. When
`extraction_sector_potential_output == 0`, `capacity_utilization_bps := 0` by defined convention
— never a `ZeroDivisionError` — and the same proof shows `potential == 0` forces `actual == 0` too,
so "0% utilization of zero possible extraction" is the only coherent reading; there is no
reachable state this convention could be hiding a real problem behind.

### `SectorProductionConstraint` — a dedicated `PHYSICAL_RESOURCE_CONSTRAINED` member, and `actual > potential` is rejected, never classified

`report.py` gains `SectorOutputBasis` (`STANDARD` | `RESOURCE_EXTRACTION`, forced entirely by
category identity — never authored) and `SectorProductionConstraint`, a report.py-local superset
of `production_accounting.SectorConstraint`'s four members plus `PHYSICAL_RESOURCE_CONSTRAINED`.
Defined here rather than added to the engine's own `SectorConstraint` for the same reason
`SectorOutputBasis` is: `production_accounting.py` never produces this value and must stay
untouched. The four shared members keep identical string values, so a STANDARD row's canonical
JSON is byte-for-byte unaffected by the type swap — pinned by a dedicated parity test.

A dedicated member was chosen over reusing `CAPACITY_CONSTRAINED` for the resource-bound case:
reuse would overload one label with two meanings distinguished only by which basis produced it —
`CAPACITY_CONSTRAINED` for a STANDARD row means "nominal per-sector capacity was the limiting
factor"; for the extraction row it would have to mean "the aggregate physical resource ceiling was
the limiting factor," a related but genuinely different claim. A dedicated member removes the
ambiguity at the type level.

`classify_extraction_constraint(*, potential_output, actual_output)` is a genuine, total 3-way
classification over the *valid* input space:

```
potential_output == 0                              -> INACTIVE           (implies actual == 0)
potential_output >  0, actual_output <  potential   -> LABOR_CONSTRAINED  (includes zero
                                                          employment — the 2B1 precedent: a
                                                          resource existing but unstaffed is a
                                                          labor fact, not an inactivity fact)
potential_output >  0, actual_output == potential   -> PHYSICAL_RESOURCE_CONSTRAINED
                                                          (deterministic tie semantics: this is
                                                          the outcome whether labor was scarce-
                                                          but-exactly-sufficient or merely
                                                          abundant with the resource itself the
                                                          true ceiling)
```

**`actual_output > potential_output` is rejected by a `raise`, at the top of the function, before
any classification is attempted — not a classifiable, if unreachable, fourth branch.** This state
is invalid, not merely unreachable, and the function refuses to assign it any business status even
under a bypassed construction. Three independent layers back this: the row-level
`ResourceDepositReport._real_output_contribution_does_not_exceed_potential`, the aggregate-level
`ResourceExtractionReport._extraction_sector_real_output_does_not_exceed_potential`, and this
classifier's own `raise` — defense-in-depth, not a single point of failure.

This one classification function is called from both `phases.py` (to construct the row) and
`TurnReport`'s cross-validator (to authoritatively check it) — the one deliberate exception to
this codebase's usual "independently re-derive, don't share code" self-validation philosophy. The
classification itself has no freedom given `(potential, actual)`; re-deriving it a second time
would only re-prove the same deterministic function agrees with itself. What genuinely needs
independent re-derivation — whether `potential`/`actual` themselves agree with
`ResourceExtractionReport`'s stored totals — is exactly what the other two `TurnReport`
cross-validators already do.

### `ProductionReport` validation design: row self-consistency plus authoritative `TurnReport` cross-checks

`SectorProductionReport` gains `output_basis`. Its four existing validators now branch on it:

- `_labor_limited_output_matches_formula`/`_actual_output_matches_formula`: the STANDARD branch is
  byte-for-byte the pre-2C2 formula; the RESOURCE_EXTRACTION branch is a definitional
  self-consistency check only (`labor_limited_output == actual_output`), since the row cannot
  independently re-derive the physical bridge total from its own fields alone — the inputs live in
  a sibling report (`ResourceExtractionReport`).
- `_capacity_utilization_bps_matches_formula`/`_constraint_matches_classification_rule`: the
  STANDARD branch is unchanged; the RESOURCE_EXTRACTION branch performs **no row-level check at
  all** — `quarterly_capacity_output` is read nowhere in this branch, not even as a denominator.

No field on `SectorProductionReport` becomes `Optional` for either basis — the fallback the
original ticket allowed for ("if this cannot fit the existing model without misleading semantics,
use `None`") was assessed and found unnecessary; the row-self-check/`TurnReport`-cross-check split
already established for `actual_output` extends cleanly to the two remaining fields.
`TurnReport` gains three new cross-validators, all matching the extraction row by category
identity, never tuple position: `resources.extraction_sector_real_output ==
production.sectors[EXTRACTION].actual_output`; the potential-based utilization formula; and
`classify_extraction_constraint`. These are the *authoritative* checks for fields the extraction
row cannot self-validate in isolation — they fire on every construction and `model_validate_json`
history-replay path, exactly like every other `TurnReport` cross-check. `TurnReport` stays at five
reports; the all-present-or-all-absent completeness rule (30 rejected proper nonempty subsets) is
unchanged.

### Legacy fields are completely inert for the extraction row — no exception

`SectorState.quarterly_capacity_output`/`.output_per_worker` are retained, unmodified, on every
sector including EXTRACTION, but are **read nowhere** in the RESOURCE_EXTRACTION derivation path
— not for output, not for utilization, not for classification. A scenario author can set either
to any value with zero effect on anything the extraction row reports. (Both fields are still read
by `labor_allocation.py`, untouched by this phase, to compute the sector's labor *demand* — a
real, expected, unrelated effect on `employed_workers`, which the inertness tests deliberately
hold fixed to isolate the derivation-formula claim from it.) `employed_workers` itself is **not**
legacy — it reports true extraction-sector employment every turn, cross-validated against
`LaborMarketReport`, simply no longer an *input* to any derived output field on this row.

### Accounting identity: extraction is counted exactly once

`ProductionReport._total_gross_output_matches_sum` — unmodified since before this phase — sums
`sectors[*].actual_output` unconditionally, and the extraction row's `actual_output` is now the
physical bridge total rather than the old capacity-derived figure. No other code path adds the
extraction total anywhere else. The identity is exercised end to end through the real resolver
(the eight `real_output_contribution`s sum to `extraction_sector_real_output`, which equals the
extraction row's `actual_output`, which appears in `total_gross_output` exactly once, alongside
the other ten sectors' untouched contributions) and defended structurally by a `model_construct`
test proving an inflated total is rejected.

### Content-version policy: lockstep bump, corrected justification

`RULESET_VERSION` bumps `0.6.0 -> 0.7.0`, `SUPPORTED_CONTENT_VERSIONS -> {"0.7.0"}`,
`SAVE_FORMAT_VERSION` unchanged — the same lockstep every prior phase has used. The trigger is
schema-shape compatibility, not content-value uniqueness: `resource_output_coefficients` is a new
required `EconomyState` field, so old scenario YAML literally cannot construct a valid
`EconomyState` without it, exactly like every prior phase's schema-shape change (2B1's per-sector
shares, 2B2's `TaxBaseCoefficients`, 2B3's labor-supply fields, 2C1's `resource_deposits`).

**`ruleset_version` identifies compatible simulation behavior and model shape** — which formulas,
phase order, and state/report schema `resolve_turn` implements; this is what gates whether the
engine can run a save at all. **`content_version` identifies the compatible content-package/schema
version** — which shape of authored data a scenario or save must conform to; it is a
schema-compatibility marker, not a fingerprint of any scenario's actual parameter values.
`tiny_valid.yaml` and `deficit_demo.yaml` share `content_version = "0.7.0"` while holding
deliberately different `resource_output_coefficients` — exactly like every other piece of
scenario-authored data they already disagree on today. An independent, finer-grained
content-version axis to distinguish "different authored values under one schema" was considered
and rejected: that has always been the job of *which scenario file you load*, not a version
number, and no prior phase — including ones touching data at least as consequential as tax
coefficients or resource endowments — has ever needed one.

The frozen compatibility fixture, `backend/tests/fixtures/phase2c1_save_ruleset_0.6.0.json`, was
generated with the genuinely unmodified 0.6.0 engine and committed *before* any model or constant
change landed, mirroring every prior phase's fixture-freeze-before-bump discipline. No test in
this suite asserts equality of any save, state, report, or hash across the ruleset boundary —
only specific enumerated numeric fields, and only for the exact turn ranges the calibration
tables below state.

## Calibration

Both fixtures are calibrated so every deposit is capacity- or stock-bound throughout their tested
horizons — neither committed fixture ever reaches `LABOR_CONSTRAINED` for the extraction row (a
known, documented limitation below).

`tiny_valid.yaml` — Σ = 2,000,000,000, held for the full 100-turn tested horizon (every deposit
capacity-bound; the shortest-lived, `critical_minerals`, lasts exactly 100 turns):

| Resource | `real_output_per_unit` | contribution/turn |
|---|---|---|
| timber | 1,000 | 100,000,000 |
| iron_ore | 1,500 | 300,000,000 |
| coal | 1,000 | 300,000,000 |
| crude_oil | 1,200 | 600,000,000 |
| natural_gas | 1,000 | 400,000,000 |
| uranium | 100,000 | 50,000,000 |
| copper | 1,000 | 150,000,000 |
| critical_minerals | 5,000 | 100,000,000 |
| **total** | | **2,000,000,000** |

`deficit_demo.yaml` — Σ = 500,000,000 at turn 1, then a two-step decline as endowments deplete:

| Turns | timber | iron_ore | extraction output | driver |
|---|---|---|---|---|
| 1–25 | 10,000 | 20,000 | 500,000,000 | both deposits producing |
| 26–40 | 10,000 | 0 (depleted) | 100,000,000 | iron_ore exhausted after turn 25 |
| 41–100 | 5,000 | 0 | 50,000,000 | timber's renewable steady state |

Both boundaries (turn 26, turn 41) are pinned by dedicated tests, not merely spot-checked
somewhere in range; the plateau (turns 26–40) and the steady state (turns 41–100) are each pinned
across their full range, extending the existing 100-turn soak rather than adding a new one.

## Known limitations

- **Neither committed fixture ever exercises `LABOR_CONSTRAINED` for the extraction row** — both
  stay capacity/stock-bound throughout. The classification logic's `LABOR_CONSTRAINED` branch is
  still fully specified and tested (a synthetic zero-employment fixture exercises it directly),
  but real, multi-turn, organically-labor-constrained coverage from either scenario is a gap worth
  a follow-up fixture if a future phase needs it exercised end to end.
- **`classify_extraction_constraint`'s rejection of `actual > potential` depends on an invariant
  that lives entirely in `resource_extraction.py`'s unmodified 2C1 formula.** If a future phase
  changes that formula's `min()` structure, this guarantee could silently stop holding without
  this phase's own code changing at all. Mitigated by the three independent layers described
  above, plus the state-level `resource_output_coefficient_out_of_range` invariant — but the
  underlying assumption is worth re-verifying explicitly if `resource_extraction.py` ever changes.
- **Only 4 of the plan's originally-proposed 14 new invariant codes were implemented** — a
  deliberate, reasoned deviation discovered during implementation, not an oversight. The plan's
  §9 table specified 10 additional codes checking report-vs-formula correctness (e.g. "a
  contribution ≠ `extracted * coefficient`", "the extraction sector's `actual_output` ≠ the
  bridge total"). `check_invariants(state: GameState)` takes only a `GameState`, never a
  `TurnReport` — and `resolver.py` calls it *before* the working copy's `TurnReport` is even
  constructed, by design, so an invariant violation can discard the working copy before any
  report is ever built from it. This means `check_invariants` structurally cannot check
  report-vs-formula mismatches without a materially larger, riskier redesign (passing an unbuilt
  report into invariants, or moving invariant checking after report construction, which would
  break the "discard the whole working copy on violation" safety property). No prior phase has
  added a report-vs-formula invariant code either — that has always been report.py's job via
  Pydantic self-validation. The 4 codes implemented
  (`missing_resource_output_coefficient`/`duplicate_resource_output_coefficient`/
  `noncanonical_resource_output_coefficient_order`/`resource_output_coefficient_out_of_range`) are
  the genuinely state-structural ones, mirroring the existing `resource_deposits` structural
  checks exactly. The other 10 checks' *intent* is fully covered — more thoroughly, in fact — by
  the 7 new `report.py` row/aggregate self-validators plus the 3 new `TurnReport` cross-validators,
  which run on every construction/history-replay/CLI-inspection path, not merely at
  `resolve_turn`'s two invariant checkpoints.
- Carried forward from ADR 0007, unaffected by this phase: no prices, inflation, trade, imports,
  stockpiles, discoveries, ownership, royalties, environmental effects, or province-level
  geography; `extraction_capacity_per_turn` stays a reduced-form placeholder; no upper bound on
  quantity magnitudes at the type level.

## Consequences

- `production_accounting.py`, `resource_extraction.py`, `labor_allocation.py`,
  `integer_allocation.py`, `accounting.py`, `tax_base_derivation.py`, `history.py`,
  `core/canonical_json.py`, and `resolver.py` are all **unmodified** by this phase.
- `core/quantity.py` gains `StrictRealOutputPerResourceUnit` and
  `extracted_resource_to_real_output`; `simulation/state.py` gains `ResourceOutputCoefficient` and
  the `resource_output_coefficients` field; a new pure `simulation/resource_output.py` module
  computes per-category contributions and sector aggregates; `simulation/report.py` gains
  `SectorOutputBasis`, `SectorProductionConstraint`, `classify_extraction_constraint`, 5 new
  fields across `ResourceDepositReport`/`ResourceExtractionReport`, and 3 new `TurnReport`
  cross-validators; `simulation/phases.py`'s extraction branch replaces `compute_sector_output`
  for the EXTRACTION row; `simulation/invariants.py` gains 4 new codes (see "Known limitations").
- `RULESET_VERSION` bumps again: `0.6.0 -> 0.7.0`.
  `backend/tests/fixtures/phase2c1_save_ruleset_0.6.0.json` was generated with unmodified
  Phase-2C1 code and committed *before* this bump landed.
- 567 -> 660 backend tests: the physical-to-output bridge's exactness and no-rounding property
  (including a Hypothesis property test proving `actual <= potential` for arbitrary valid
  inputs), `output_basis` structural design, the no-clamp-needed proof, R9's reject-not-classify
  behavior and its 2B1-consistency/deterministic-tie-semantics corollaries, the direct accounting
  identity, legacy-field inertness (extended from two-of-three to all three derived fields),
  the reversed resource-endowment isolation boundary (rewritten, not deleted, from ADR 0007),
  the exact turn-26/turn-41 calibration boundaries and their soak extensions, tamper detection
  extended to the new state/report fields, and frozen-fixture compatibility rejection.
