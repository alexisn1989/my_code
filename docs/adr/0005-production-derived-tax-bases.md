# ADR 0005: Production-derived tax bases and the Phase 2B2 ruleset bump

- Status: accepted
- Date: 2026-08-02

## Context

Phase 2A resolved government accounting against fixed, scenario-authored tax bases — changing a
tax rate never moved the base it applied to. Phase 2B1 added sector production, deliberately
isolated from finance in both directions. Phase 2B2 connects them, but only one way: sector
production now determines the tax bases that revenue is computed against.

```
sector production -> transparent tax-base derivation -> existing tax rates
    -> existing revenue calculation -> existing spending/interest/cash/debt reconciliation
```

Tax rates and spending still must not affect production or the bases derived from it — that
direction stays isolated, unchanged from Phase 2B1. `accounting.py` itself is not modified: the
only change is *where* `compute_tax_revenue`'s `TaxBaseState` argument comes from.

This ADR also records four corrections (R1–R4) made during an independent review of the initial
design, before implementation — each is a real gap the review caught, not a stylistic preference.

## Decisions

### R1 — Three internally-valid reports are not enough; the whole chain is cross-validated

`ProductionReport`, `TaxBaseDerivationReport`, and `FinanceReport` each self-validate their own
internals (mirroring the Phase 2A/2B1 pattern), but each was checked independently — nothing
proved `ProductionReport.actual_output` for a given sector was actually the value
`TaxBaseDerivationReport` used as its input, or that `TaxBaseDerivationReport.derived_tax_bases`
was actually what `FinanceReport.tax_bases` recorded as applied. Three internally-correct reports
could still describe three different calculations that happened to each validate in isolation.

`TurnReport` gains three additional `@model_validator(mode="after")` checks: (a) per
`SectorCategory` — matched by **category identity**, never tuple position, since both reports
independently normalize their own sector ordering and nothing guarantees they'd stay
positionally aligned under a future refactor — `ProductionReport.actual_output` must equal
`TaxBaseDerivationReport`'s input for that same category; (b)
`TaxBaseDerivationReport.derived_tax_bases` must exactly equal `FinanceReport.tax_bases`; (c)
`production`, `tax_base_derivation`, and `finance` must be all present or all absent — a partial
combination (e.g. production ran but derivation silently didn't) is rejected outright rather than
accepted as whatever subset happens to exist. Tests independently corrupt each of the four
combinations (production-vs-derivation both directions, derivation-vs-finance both directions)
and every missing-report combination, proving each fails on fresh construction *and*
`model_validate_json` — independently of history's hash-tampering detection, which catches a
different failure mode (bytes changed after the fact) than this (the reports were never
consistent with each other in the first place).

### R2 — The unit bridge is a named function, not an implicit `int` pass-through

Production is real (fixed-base-year) output; tax bases are nominal `Money`. Both are plain `int`
type aliases at runtime, so without an explicit boundary, nothing would visibly mark the single
most important unit conversion in the economy simulation — a future contributor could pass a real
output figure directly into a `Money`-typed field and nothing would complain.
`app.core.quantity.base_year_real_output_to_money(value: RealOutput) -> Money` is that boundary:
currently an identity conversion at `BASE_YEAR_PRICE_INDEX_BPS = 10_000` (i.e. 1.0, expressed as
exact integer basis points rather than a runtime float, so there is no floating-point price
index anywhere in the engine), called at exactly one point — national tax-base construction in
`tax_base_derivation.aggregate_tax_base_contributions`. It rejects negative and non-integer
(including `bool`) input directly, since it is a plain function rather than a Pydantic field.
This function, not the constant alone, is what a later price-level/inflation system replaces;
every call site stays the same when that happens.

### R3 — `modeled_value_added`, not `sector_value_added`

The original design used `sector_value_added = actual_output * value_added_share_bps`. That name
implies national-accounts value added, which this is not — no intermediate-consumption
accounting exists, so there is no basis for claiming a real value-added measure. Renamed to
`modeled_value_added` everywhere (code, reports, CLI output, tests, docs) to make clear it is an
internal decomposition proxy whose only job is to prevent gross-output double counting *within
this derivation* — not a claim about GDP, official value added, or economic growth.
`labor_income + operating_surplus == modeled_value_added` still holds exactly (`operating_surplus`
is computed by subtraction, not a second floored share, specifically so this identity never has a
rounding gap to explain).

### R4 — `effective_consumption_base_share_bps`, not "the tax system's reach"

The country-level consumption coefficient converts modeled value added into a consumption tax
base in one step. In reality that conversion depends on household final-demand composition,
government-vs-private consumption split, exports and other non-domestic demand, and tax
exemptions/fiscal coverage — none of which Phase 2B2 models separately. Calling it simply "the tax
system's reach" (as an earlier draft did) overclaims what a single reduced-form coefficient can
represent. Renamed to `effective_consumption_base_share_bps` and documented, in both code and
`docs/economy_methodology.md`, as a deliberate reduced-form placeholder that temporarily combines
economic composition and taxable coverage. Splitting it into a structural final-demand-exposure
coefficient and a separate tax-coverage coefficient is recorded as a later economy task, not
attempted here — Phase 2B2 does not add a final-demand or trade model.

### Per-sector structural shares stay on `SectorState`; fiscal coefficients move to a new model

`value_added_share_bps`/`labor_income_share_bps` are added to `SectorState` (per-sector) because
they are genuinely structural — how much of a sector's gross output survives as modeled value
added, and how much of that is labor income, differs by industry. The three fiscal-reach
coefficients (`personal_taxable_share_bps`, `corporate_taxable_share_bps`,
`effective_consumption_base_share_bps`) become a new `TaxBaseCoefficients` model, country-level,
because they describe how much of the economy the tax system reaches — a property of fiscal
policy, not of any one sector. This is a deliberate split, not an arbitrary one: putting all five
coefficients per-sector would mean 55 authored numbers per scenario, mostly duplicated; putting
all five at country level would make every sector's tax-base composition identical, losing the
actual point of per-sector decomposition.

### `GovernmentFinanceState.tax_bases` is removed; bases become purely derived

Tax bases are no longer authored state — they are computed fresh every turn from
`ctx.production_report` and `tax_base_coefficients`, and recorded only in
`TaxBaseDerivationReport`/`FinanceReport`, never written back into `GameState`. This was a
deliberate rejection of the alternative (keep `tax_bases` in state, overwritten each turn): that
alternative stores a derived value where it can drift from its own derivation, and forces
defining what "opening" vs. "closing" tax bases would even mean for a value with no
turn-to-turn carry-over. There is only **applied** — the bases this turn's production produced,
used by this turn's revenue calculation, nothing more.

### Derivation runs at the start of the revenue phase, reading `ctx.production_report`

No new `PHASE_ORDER` slot and no reordering: `resolve_production_and_trade` (phase 3) already
runs before `resolve_government_revenue_and_expenditure` (phase 4), so same-turn linkage is
structural, not incidental — derivation simply reads what production already computed this same
`resolve_turn` call. No scratch workspace beyond the existing `FinanceScratch` (which gains one
field, `applied_tax_bases`): derivation is a single-phase computation with no need to span
multiple phases the way finance's opening-snapshot-then-apply shape does.

### Sum-of-parts, not a national recompute

National tax bases are defined as the **sum of per-sector contributions**, not a value recomputed
from national aggregate value added. `sum(floor(xi * r)) <= floor(sum(xi) * r)` in general — the
gap can be up to `n - 1` — so summing per-sector floors is the only definition under which every
reported national figure is exactly the sum of the rows shown beneath it, matching how
`ProductionReport`'s totals already work. A test with hand-picked values proves the two approaches
genuinely diverge, so this is a real design decision with an observable effect, not an arbitrary
implementation detail.

### Calibration: re-author production, not budgets

At a base-year price index of 1.0, the original Phase 2B1 scenario production figures were
roughly three orders of magnitude too small to reproduce the existing Phase 2A tax bases (total
gross output ~1.77M vs. an authored personal-income base of 4B). Rather than accept collapsed
revenue or rescale budgets/treasury to match the smaller bases (which would invalidate every
documented Phase 2A hand-checked figure, including `deficit_demo.yaml`'s worked example), both
scenarios' sector outputs are re-authored — scaling `quarterly_capacity_output`/
`output_per_worker` only, never `employed_workers` (which would risk breaching
`sector_employment_exceeds_population`) — so derived bases reproduce the original authored bases
**exactly**. Verified by direct computation before writing the YAML, then re-verified by resolving
turn 0 through the real engine and comparing byte-for-byte: `tiny_valid.yaml` reproduces
personal=4,000,000,000 / corporate=2,000,000,000 / consumption=3,000,000,000 exactly;
`deficit_demo.yaml` reproduces personal=1,000,000,000 / corporate=500,000,000 /
consumption=800,000,000 exactly, and every downstream revenue/interest/borrowing/reconciliation
figure in both fixtures is therefore unchanged from Phase 2A.

### `RULESET_VERSION` bumps again; a pre-bump fixture was frozen first

`0.3.0 -> 0.4.0`. `CountryState`'s reachable finance shape changes in both directions: a new
required `tax_base_coefficients` field (and each `SectorState` gains two new required share
fields), and the removal of the previously-required `tax_bases` field. An older save has no
coefficient data to backfill and no way to derive it retroactively, so — the same "nothing to
migrate from" reasoning as every prior bump — old-ruleset saves are rejected outright.
`backend/tests/fixtures/phase2b1_save_ruleset_0.3.0.json` was generated with unmodified Phase-2B1
code and committed *before* this bump landed, mirroring exactly how the Phase-1 and Phase-2A
fixtures were frozen before their respective bumps. `SAVE_FORMAT_VERSION` is unchanged; only the
ruleset/content-governed inner schema changed.

## Consequences

- `tests/conftest.make_finance`'s `personal_income`/`corporate_profit`/`taxable_consumption`
  parameters are removed (there is nothing to author directly anymore) and replaced with
  `personal_taxable_share_bps`/`corporate_taxable_share_bps`/
  `effective_consumption_base_share_bps`. `tests/conftest.make_economy` gains
  `value_added_share_bps`/`labor_income_share_bps` parameters and its default output magnitude
  was raised (from 1,000/100/2 to 25,000,000/25,000,000/1 per sector) specifically so the
  factory's "comfortably sustainable" default-budget claim — needed for the 100-turn soak to stay
  a meaningful timing signal — remains true once tax bases are derived rather than authored
  directly; the previous tiny magnitudes would have floored to near-zero bases.
- `tests/test_phase_isolation.py::test_finance_report_is_byte_identical_across_wildly_
  different_economies` (Phase 2B1) asserted the literal opposite of Phase 2B2's design and is
  replaced, not silently deleted, by
  `test_different_economies_produce_different_tax_bases_and_revenue` plus a companion test
  proving the *other* direction (tax rate and spending changes still do not affect production or
  derived bases). Notably, the old test was still technically passing against the new code before
  this fix — its four fixture economies all happened to floor to zero modeled value added at
  their tiny magnitudes, so it was vacuously true for the wrong reason. Left as-is, it would have
  silently stopped testing anything real.
- Two new invariant codes, `tax_base_coefficient_out_of_range` and
  `sector_tax_base_share_out_of_range`, mirror `noncanonical_sector_order`'s role from Phase 2B1:
  `StrictBps` already rejects an out-of-range value at every legitimate construction/assignment
  path, so these are defense-in-depth against a fully bypassed construction
  (`model_construct`/`model_copy(update=...)`), not a claim that the gap is reachable through
  ordinary Pydantic-validated code today.
