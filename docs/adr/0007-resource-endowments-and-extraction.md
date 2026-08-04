# ADR 0007: Resource endowments and extraction at fixed prices

- Status: accepted
- Date: 2026-08-03

## Context

Phases 2A–2B3 built a closed chain in which every input is derived, not authored:

```
population -> labor force -> sector allocation -> production -> tax bases -> revenue -> cash/debt
```

Each phase deleted one hand-authored number (2B2 removed `GovernmentFinanceState.tax_bases`; 2B3
removed `SectorState.employed_workers`). What the economy still lacked was **physical stuff**:
there is an `extraction` sector producing abstract "real output," but nothing is extracted,
nothing depletes, and no country can be resource-rich or import-dependent.

Phase 2C1 adds the shallow **base-game resource layer** — not the future Resources and Energy
expansion. It is deliberately a *conservation foundation*:

```
resource endowments -> regeneration -> extraction-sector labor sub-allocation -> extraction
    -> depletion -> (nothing further this phase)
```

Reserves deplete exactly, timber regenerates deterministically, extraction is bounded by
stock/capacity/labor/productivity, and all of it is explainable and hash-protected. It does
**not** connect physical extraction to production, prices, trade, or politics —
`docs/roadmap.md`'s deferred Phase 2C1 entry recorded exactly this shape before implementation
began.

This ADR also records nine corrections (R1–R9) made across two independent review rounds before
and during implementation, plus one structural recommendation — real gaps the reviews caught, not
stylistic preferences. Round 2 (R7–R9) is purely additive: it does not revise R1–R6, and
explicitly re-approved phase-3 depletion (R2), the report's regeneration fields (R1),
reject-not-normalize ordering (R3), the neutral allocator module, the "unassigned" naming (R6),
physical/money isolation, and the Phase 2C2 follow-up.

## Decisions

### Eight resources, canonical order, reject-not-normalize (R3)

`ResourceCategory` (`simulation.state`) is a `StrEnum` with 8 members in canonical declaration
order — `TIMBER, IRON_ORE, COAL, CRUDE_OIL, NATURAL_GAS, URANIUM, COPPER, CRITICAL_MINERALS` —
matching the ticket's list. **Every resource-facing canonical-order validator (state and report)
REJECTS reordered input rather than silently normalizing it** — a deliberate divergence from the
four existing sector-order validators (`EconomyState.sectors`, `LaborMarketReport.sectors`,
`ProductionReport.sectors`, `TaxBaseDerivationReport.sectors`), which all normalize on reorder.
Deterministic canonical serialization should be a property **proven of valid input**, not a
repair silently applied to invalid input — a rule not applied retroactively to the four existing
validators, which keep their established normalize-on-reorder behavior unchanged.

### A new physical-quantity type family, with no bridge to `Money` or `RealOutput`

`core/quantity.py` gains `ResourceQuantity` (plain-`int` alias), `StrictResourceQuantity`
(`ge=0`), and `StrictResourceQuantityPerWorker` (`gt=0`, so "no extraction" is expressed only via
zero allocated workers or zero remaining stock, never by also allowing productivity to be zero —
mirroring `StrictRealOutputPerWorker`'s reasoning). **No conversion function to `Money` or
`RealOutput` is added.** Distinct concepts get distinct aliases so a field's annotation alone
states what it holds — the repo's own established rule. The deliberate *absence* of a
`resource_to_*` function is what makes "resources feed nothing yet" structurally true, not merely
documented. Each category's physical unit (cubic metres, tonnes, barrels, thousand cubic metres)
is a fixed property of the category (`RESOURCE_UNITS`), not authored per-deposit state — the same
"no redundant, driftable value" reasoning that removed `tax_bases` and `employed_workers` in
earlier phases. Heterogeneous resource quantities are never summed together (no `total_extraction`
field anywhere) — only worker counts and per-status counts are aggregated.

### `EconomyState.resource_deposits`, grouped with the sectors whose labor works it

`EconomyState.resource_deposits: tuple[ResourceDepositState, ...]` covers all 8 categories exactly
once, canonical order (rejected, not normalized, per R3 above), zero-stock/zero-capacity entries
legal — a resource-poor country still declares every category, just at zero, the same
no-ambiguous-missing-vs-zero reasoning `sectors` already follows. Grouped on `EconomyState` rather
than `CountryState` directly because deposits are worked by the same extraction sector's labor
this economy already allocates.

### The extraction sector's allocated workers are the resource labor budget

The extraction **sector's** `allocated_workers` (from `LaborMarketReport`, already validated) is
sub-allocated across the 8 deposits — reusing the single national labor supply, inventing no
second pool. Because it *subdivides* an already-allocated number, every existing Phase 2B3 labor
figure is unchanged. Unused workers surface explicitly as `unassigned_resource_workers`.

### The neutral allocation core is order-sensitive; permutation independence lives in the wrapper (R7)

The Phase 2B3 largest-remainder algorithm was structurally generic — it never named
`SectorCategory`, only ever read weights and a budget, with canonical order a documented but
unvalidated caller contract. It moved verbatim into a new, category-agnostic
`simulation/integer_allocation.py` rather than staying inside `labor_allocation.py`, since
resource extraction should not import a generic algorithm out of a labor-specific module.

An initial draft of this decision said the core "breaks ties by caller-supplied order" while
separately expecting reordered resource input to produce identical results — a real contradiction
an independent review caught: carrying category identity alongside each weight does **not**, by
itself, make positional tie-breaking permutation-independent. Bound as follows:

- The core (`largest_remainder_allocation`) accepts **ordered** `(category, weight)` pairs,
  preserves that order in its output, and resolves every remainder tie by caller-supplied
  position. It is honestly **order-sensitive by contract**, not permutation-independent — pinned
  by a dedicated test showing reordering *can* change which tied category wins a leftover unit.
- `labor_allocation.allocate_workers` keeps its existing `tuple[tuple[SectorCategory, int], ...]`
  signature and canonical order **byte-for-byte unchanged** — its callers already pass canonical
  order, exactly as before this refactor, so its behavior is provably identical to the
  pre-refactor algorithm (a dedicated regression test proves the wrapper's output matches the core
  called directly, for arbitrary inputs).
- `resource_extraction.allocate_extraction_workers` — the one caller that genuinely needs
  permutation independence — accepts a `Mapping[ResourceCategory, int]` (whose iteration order is
  not a contract worth depending on), verifies it covers all eight categories exactly once, and
  builds the `(category, weight)` pairs in `tuple(ResourceCategory)` order **before** calling the
  order-sensitive core. Mapping insertion order therefore provably cannot reach the tie-break.

State/report **tuples** are a different surface entirely and still reject noncanonical order (R3)
— this split does not relax that rule anywhere.

### Formulas: regeneration before extraction, three-way-min extraction, exact conservation

```
regenerated = 0                                                    [nonrenewable]
            = max(0, min(regeneration_per_turn,
                         stock_ceiling - remaining_stock))         [renewable]
available   = remaining_stock + regenerated
required_workers = 0                                       [min(available, capacity) == 0]
                  = ceil(min(available, capacity) / output_per_worker)   [otherwise]
extracted   = min(available, extraction_capacity_per_turn,
                  allocated_workers * output_per_worker)
closing     = available - extracted
```

Regeneration happens *before* extraction — growth accrues over the quarter and is harvestable
within it; `available` is the single quantity every downstream bound is expressed against.
Conservation (`remaining_stock + regenerated == extracted + closing_stock`) holds **by
construction**: `closing_stock` is *defined* as `available − extracted`, and `extracted ≤
available` because `available` is one of the three terms of the `min`.

### Status classification: the stock/capacity tie resolves to STOCK_CONSTRAINED (R8)

```
if extraction_capacity_per_turn == 0:            INACTIVE
elif available == 0:                             DEPLETED
elif extracted == available:                      STOCK_CONSTRAINED
elif extracted == extraction_capacity_per_turn:   CAPACITY_CONSTRAINED
else:                                              LABOR_CONSTRAINED
```

Checked top-down, mirroring `SectorConstraint`. Stock exhaustion is checked **before** the
stock/capacity tie case: a deposit whose `available` stock exactly equals its
`extraction_capacity_per_turn` reports `STOCK_CONSTRAINED`, not `CAPACITY_CONSTRAINED` — the
stock, not the capacity, determined the outcome that turn, even though the two bounds happened to
coincide. An independent review caught a first-draft calibration that folded this exact case into
"39 turns capacity-bound, then steady state," silently skipping the boundary turn itself; the
corrected `deficit_demo.yaml` timber trajectory (§ calibration below) makes this a distinct,
separately-tested regime.

### Extraction and its depletion are one domain operation, performed together in phase 3 (R2)

```
phase 3  resolve_production_and_trade
           +- labor allocation                     (existing, unchanged)
           +- resource extraction                   [NEW]
           |     1. compute every deposit's formulas (pure)
           |     2. write each deposit's closing_stock into the working
           |        economy.resource_deposits, by ResourceCategory identity —
           |        never tuple position — the ONLY state mutation this phase performs
           +- sector production                     (existing, unchanged)
phase 5  update_prices_inflation_employment_debt_reserves
           +- treasury cash/debt only (existing, unchanged) — needs NO resource code
```

The original design placed depletion in phase 5 (mirroring where treasury "closing" mutations
already lived). An independent review rejected this as splitting one domain operation —
extraction and its resulting depletion — across two unrelated phases. Depletion now happens in
the **same step** that computes the extraction report, inside phase 3, immediately after labor
allocation and before aggregate production. No `PHASE_ORDER` change.

This is a **deliberate, narrow, explicitly-tested exception** to phase 3's prior "never mutates
`state`" contract, not a silent erosion of it: the exception is limited to
`economy.resource_deposits` — phase 3 still never touches `finance`/`treasury`, and phase 5 needs
no resource-related code at all after this change. Transactional safety is unaffected: the
resolver's single deep copy and its post-phase invariant re-check are unaffected by *which* phase
performed a mutation — an invariant violation later in the same `resolve_turn` call still discards
the entire working copy. A dedicated test proves phase 3's mutation is scoped to
`resource_deposits` alone (nothing else in state changes when only resource endowments differ),
and that report-stated closing stocks match the returned state's stocks exactly, every turn.

### Self-validating reports, with genuine self-validation of regeneration (R1)

`ResourceDepositReport` mirrors the established self-validation pattern (one
`@model_validator(mode="after")` per equation) but an independent review caught that, as first
drafted, it could not actually re-derive `regenerated` from its own stored fields — it had nowhere
to read `regeneration_per_turn`/`stock_ceiling` from. Both fields are now carried on the report
row specifically so `_regenerated_matches_formula` can recompute the clamp formula independently,
on both fresh construction and `model_validate_json` history loading — not trust the phase that
built it. A second validator enforces the renewability rule at the report level (nonrenewable ⇒
regeneration/ceiling both zero/`None`; renewable ⇒ ceiling present and `available_stock` within
it), mirroring `ResourceDepositState`'s own construction-time rule.

`TurnReport` gains a fifth report (`resources: ResourceExtractionReport | None`) and a new
pairwise cross-report validator: `LaborMarketReport.sectors[EXTRACTION].allocated_workers` must
equal `ResourceExtractionReport.extraction_sector_workers` exactly. The existing
all-present-or-all-absent completeness rule extends from four reports to five — all 30 proper
nonempty partial combinations are rejected.

### Integration boundary: conservation-only, extraction is economically inert (D8)

Production, tax bases, revenue, and treasury stay **byte-identical** regardless of resource
endowments. The alternative — deriving some of the extraction sector's `RealOutput` from physical
extraction — would **double-count**: the extraction sector already produces `RealOutput` from
those same workers, so adding physical-derived output on top counts the same labor twice. Making
that connection non-duplicative requires *replacing* the sector's output derivation entirely, a
materially larger change with real calibration consequences, recorded as the first follow-up
(Phase 2C2) rather than attempted here.

### No player decision this phase

A choice between extraction targets is not gameplay while extraction has no economic, political,
or strategic consequence yet (D8). Adding a decision now would be a UI surface with no effect
behind it — exactly the kind of half-built feature the product spec's "no placeholder feature
claims" rule (§5.7) forbids.

### `unassigned_resource_workers`, not "idle" (R6)

Workers the labor market allocated to the extraction sector but that no modeled deposit consumed
are still counted as **employed** by `LaborMarketReport` — calling them "idle" would imply a
contradiction with that report. Named `unassigned_resource_workers` and documented explicitly as
support/surveying/transport/other aggregate extraction-sector activity not assigned to a modeled
deposit, never double-counted against `LaborMarketReport.unemployed_workers`.

## R4/R8 — Calibration: the corrected three-regime timber trajectory

An initial calibration pass preserved every Phase 2B3 figure correctly but produced an inaccurate
narrative: "timber holds steady" (false — it declines under capacity-bound extraction) and "39
turns capacity-bound, then steady state" (incomplete — it skips the boundary turn itself). Both
were corrected rather than the fixtures recalibrated, per explicit review guidance.

`deficit_demo.yaml`'s timber (opening 200,000; capacity 10,000; output-per-worker 25; regeneration
5,000/turn; ceiling 250,000), counted by completed resolutions:

- **Resolutions 1–39**: `CAPACITY_CONSTRAINED`, declining `10,000 − 5,000 = 5,000` net per
  resolution; closing stock reaches exactly 5,000 at resolution 39.
- **Resolution 40** (the boundary, its own distinct case): opening 5,000 + regeneration 5,000 =
  available 10,000, which **ties** capacity exactly; extracted 10,000, closing **0**. Because the
  status precedence checks `extracted == available` before `extracted == capacity`, this
  classifies **`STOCK_CONSTRAINED`**, not `CAPACITY_CONSTRAINED`, even though extraction is still
  the full 10,000.
- **Resolutions 41+**: the true steady state — extracts exactly the regenerated 5,000/turn
  forever, closing 0, `STOCK_CONSTRAINED` (never `DEPLETED`, since `available` is never exactly
  zero while regeneration is active).

Verified numerically (a small forward simulation) before being written into the scenario header,
the economy-methodology doc, and every test that exercises it. `tiny_valid.yaml`'s own timber
declines under an identical capacity-bound calibration but never reaches its own boundary within
any tested horizon (its own crossover sits around resolution 250) — the three-regime dynamic is
`deficit_demo`'s alone to exercise, mirroring the existing precedent of using one scenario for
abundance and the other for a scarcity/edge-case dynamic.

## R5/R9 — Test-surface corrections

- **R5**: `test_resolver.py` proves no mutation and no appended history but cannot prove "no
  output file" or "no stray temp file" — that is a CLI-level, filesystem-level property.
  `test_cli.py` already had a matching failure test
  (`test_invalid_decisions_file_produces_no_output_and_leaves_input_untouched`); it gained the one
  missing assertion (no stray `write_save_atomic` temp file) rather than a new,
  resource-specific test being invented — the property is general-purpose and protects any future
  failure path for free.
- **R9(a)**: one resolution produces historical **turn 1** — turn 0 is the genesis snapshot and
  carries no report. Manual verification steps and documentation were corrected to say
  `history --turn 1`, not `--turn 0`, after resolving once.
- **R9(b)**: the resolver-level "invalid input" test is named for what it actually proves — **no
  mutation and no appended history** — not "no output file," which was never true of a test that
  never touches the filesystem in the first place. File-output guarantees belong exclusively to
  the CLI-level test (R5).

## Consequences

- `SectorState.employed_workers` stays gone (unaffected by this phase); `EconomyState` gains
  `resource_deposits` as a new required tuple.
- `production_accounting`/`labor_allocation` are unmodified in their own arithmetic;
  `labor_allocation.allocate_workers`'s body becomes a thin delegation to the new
  `integer_allocation` core, byte-identical to its pre-refactor behavior.
- `phases.py`'s `resolve_production_and_trade` gains a resource-extraction step with the one
  documented state-mutation exception (R2); `PhaseContext` gains a `resources_report` field.
  `resolver.py` gains one kwarg copying it onto `TurnReport`.
- `invariants.py` gains six defense-in-depth codes mirroring the existing sector/coefficient
  backstops: `duplicate_resource_category`, `missing_resource_category`,
  `noncanonical_resource_order` (now even more purely unreachable than its sector counterpart,
  since the constructor itself already rejects reordering — R3), `resource_regeneration_on_
  nonrenewable`, `renewable_missing_stock_ceiling`, `resource_stock_exceeds_ceiling`. No invariant
  constrains depletion rate or reserve life — that is scenario calibration, and a future war or
  crisis must be free to exhaust a reserve.
- `RULESET_VERSION` bumps again: `0.5.0 -> 0.6.0`. `EconomyState`'s reachable shape changes (a new
  required `resource_deposits` field), so — the same "nothing to migrate from" reasoning as every
  prior bump — old-ruleset saves are rejected outright.
  `backend/tests/fixtures/phase2b3_save_ruleset_0.5.0.json` was generated with unmodified
  Phase-2B3 code and committed *before* this bump landed, mirroring exactly how every prior
  phase's fixture was frozen before its own bump. `SAVE_FORMAT_VERSION` is unchanged; only the
  ruleset/content-governed inner schema changed.
- **Known limitations, all documented rather than hidden**: extraction is economically inert by
  design (D8); the extraction sector's `RealOutput` and physical tonnage remain two descriptions
  of the same labor, not two connected activities, until Phase 2C2 replaces (not adds to) the
  sector's output derivation; endowments are country-level only until Phase 6's map exists;
  `extraction_capacity_per_turn` is a reduced-form placeholder conflating infrastructure,
  technology, and accessibility, the same deliberate simplification shape as
  `effective_labor_force_share_bps` and `effective_consumption_base_share_bps`; there is no upper
  bound on quantity magnitudes at the type level (an authoring typo in magnitude is not caught
  here, carried forward from Phase 2B1); and phase 3 mutating state at all (R2) is a **first**
  exception to an informal pattern, not now a general precedent — any future phase wanting to
  mutate state ahead of phase 5 must earn that exception with equally explicit justification and
  equally scoped tests.
