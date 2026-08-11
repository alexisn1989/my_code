# MANDATE — Economy Methodology (Phase 2A + 2B1 + 2B2 + 2B3 + 2C1 + 2C2 + 3A)

Scope of this document: the government-finance slice implemented in Phase 2A (tax revenue,
spending, quarterly debt interest, deficit financing), the sector-production slice implemented in
Phase 2B1 (aggregate sector capacity, labor productivity, employment, deterministic quarterly
output at fixed base-year prices), the production-derived tax-base slice implemented in
Phase 2B2 (deriving Phase 2A's tax bases from Phase 2B1's production, replacing the fixed
scenario-authored bases), the labor-allocation slice implemented in Phase 2B3 (deriving
Phase 2B1's employment from population and sector labor demand, replacing the fixed
scenario-authored `employed_workers`), the resource-extraction slice implemented in Phase 2C1
(deterministic extraction and depletion of eight physical natural resources, sub-allocated from
Phase 2B3's extraction-sector labor, entirely isolated from production/tax/revenue this phase),
the physical-extraction-drives-output slice implemented in Phase 2C2 (replacing the extraction
sector's abstract output derivation with one computed from that turn's physical extraction), and
the constitutional-foundation/legitimacy/political-capital slice implemented in Phase 3A (the
first political layer, driven one-way by this economy's own output and unemployment signals,
never by government form). Nothing else in §13 of the product spec (prices, inflation, wages,
central banking, exchange rates) is implemented yet; see "Explicitly not yet simulated" below.

## Units and conventions

- **Money**: integer minor units, 1/100 of the in-fiction "denar" (`app.core.money.Money`). Never
  a float, anywhere in accounting state or arithmetic.
- **Rates**: integer basis points (bps). `10,000 bps = 100%`. `app.core.money.BPS_DENOMINATOR`.
- **Strict validation**: every money and bps field (`StrictMoney`, `StrictSignedMoney`,
  `StrictBps` in `app.core.money`) uses Pydantic `strict=True`, which — verified empirically,
  see `tests/test_money.py` — rejects whole-number floats (`10.0`), numeric strings (`"10"`),
  booleans (despite `bool` being an `int` subclass in plain Python), NaN, and ±infinity. Only a
  genuine `int` is accepted.
- **Rounding policy**: floor division throughout, applied once per quantity. `apply_bps(amount,
  rate_bps) = amount * rate_bps // 10_000`.

## Formulas

Per tax category (personal income, corporate, consumption):

```
gross_tax     = floor(tax_base * rate_bps / 10_000)
collected_tax = floor(gross_tax * compliance_rate_bps / 10_000)
```

```
total_revenue          = personal_income_tax + corporate_tax + consumption_tax
total_program_spending = health + education + welfare + infrastructure
                        + defense + security + administration
quarterly_interest     = floor(opening_debt * annual_rate_bps / 40_000)
pre_financing_balance  = total_revenue - total_program_spending - quarterly_interest   [signed]
cash_before_financing  = opening_cash + pre_financing_balance                          [signed]
new_borrowing          = max(0, -cash_before_financing)
closing_cash           = max(0, cash_before_financing)
closing_debt           = opening_debt + new_borrowing
```

### Quarterly interest: one division, not two

`quarterly_interest = floor(opening_debt * annual_rate_bps / 40_000)` computes a quarter's
interest from an *annual* bps rate in a single floor division (`40_000 = 4 quarters × 10,000
bps/unit`). This is **mathematically identical**, not merely "close enough," to the two-step form
`floor(floor(opening_debt * annual_rate_bps / 10_000) / 4)` — floor division is associative for
nonnegative integers (`floor(floor(a/b)/c) == floor(a/(b·c))`), verified for representative cases
and a 200,000-trial random search in `tests/test_money.py`. The single-step form is used because
it is one operation, not because it avoids a rounding discrepancy — there isn't one. (An earlier
draft of this document claimed the two forms differ; that claim was wrong and was caught by the
test that was supposed to demonstrate it, before it shipped.)

Interest accrues on **opening** debt only — debt newly issued this quarter via `new_borrowing` is
interest-free until the following quarter.

### Deficit financing

A deficit first consumes available cash; only once cash would go negative does the remaining
shortfall become new borrowing. `new_borrowing` and `closing_cash` are the two halves of
`max(0, x)` / `max(0, -x)` applied to the same signed `cash_before_financing`, so exactly one of
them is nonzero (or both are zero at an exact break-even). A surplus is retained as cash; **debt is
never automatically repaid**, even by a large surplus — that stays a scenario-authored/future
player decision, not modeled in Phase 2A.

## Reconciliation (must hold exactly, in integer minor units, for every input)

```
opening_cash + total_revenue + new_borrowing
    == closing_cash + total_program_spending + quarterly_interest

closing_public_debt == opening_public_debt + new_borrowing
```

Both hold **by construction** given the formulas above (short proof: split on the sign of
`cash_before_financing`; both branches reduce to an identity — see `app/simulation/accounting.py`'s
module docstring). `FinanceReport` re-derives and checks both equations independently on every
construction — see "Self-validation" below — rather than trusting that whatever computed the
report got the formulas right.

## Self-validation

`FinanceReport` (`app.simulation.report`) is not a passive data container. A
`@model_validator(mode="after")` runs on **every** construction path — a fresh build during turn
resolution, `model_validate` parsing a report back out of hash-protected history JSON, loading a
save, or CLI `history` inspection — and independently re-derives:

- each revenue category from `tax_bases`/`active_tax_policy` (not just that they sum to the total)
- spending categories summing to `total_program_spending`
- `quarterly_interest_expense` from `opening_debt`/`annual_debt_interest_rate_bps`
- `pre_financing_balance` from revenue/spending/interest
- `new_borrowing`/`closing_cash` from `opening_cash`/`pre_financing_balance`
- `closing_debt` from `opening_debt`/`new_borrowing`
- the aggregate cash-flow equation (redundant given the checks above — see the validator's own
  docstring for why it can never be the *first* check to fail, and how it's tested directly anyway)
- every `budget_changes` entry against the `previous_*`/`active_*` policy snapshots it claims to
  summarize, including its `unchanged`/`increased`/`decreased` label

`reconciliation_status` is a `@property`, not a stored field: it can only ever read `"reconciled"`,
because construction raises `ValidationError` before an unreconciled report could exist. Each
equation has its own validator with a specific, actionable message — a corrupted `closing_debt`
does not report the same error as a corrupted `quarterly_interest_expense`. See
`tests/test_finance_report.py` for one test per equation.

## Opening snapshot

The player's complete financial position — opening cash, opening debt, the annual interest rate,
tax bases, and the *previous* tax policy and spending plan — is captured into a frozen
`OpeningFinanceSnapshot` (`app.simulation.phases`) before the turn's `BudgetDecision` (if any) is
applied to anything.

**(Phase 3B1) A `BudgetDecision` is now a *proposal*, not an instruction.** The snapshot is still
captured exactly as described here, but whether the proposed tax policy and spending plan are ever
committed to state depends on the legislative vote resolved one slot earlier — see "Legislative
gating of the budget" at the end of this document. On a failed vote the opening policy is preserved
byte-for-byte and every figure below is computed against it, so the whole economic chain that
follows is the *unchanged* budget's chain, not the proposed one's. Every nested Pydantic sub-model is captured via `.model_copy()`, not a bare
reference: `TaxPolicyState`/`SpendingPlanState` allow in-place field mutation
(`obj.field = x`, since they use `validate_assignment=True`), so a bare reference would let a
future phase handler that mutates the *working* policy in place — rather than replacing it
wholesale, as the current handlers do — silently corrupt what the turn's report calls "opening."
`tests/test_phases.py` proves this with a direct in-place mutation, not just by reassigning the
parent object (a subtler and less forgiving test than the reassignment case, which would have
passed either way).

## Player-only accounting

Government accounting resolves for the **player country only** in Phase 2A. `CountryState.finance`
is optional; the player country is required to have it (enforced pre-resolution — a missing player
budget produces no accounting, no history entry, and no output file), while AI countries may omit
it freely. AI budget decisions arrive with AI country behavior in a later phase.

## Version compatibility

`RULESET_VERSION` (`app.simulation.state`) is an **engine constant**, stamped onto every new game —
not authored in scenario YAML, which would let content declare which rules it runs under. Bumped
to `0.2.0` for this phase. Phase-1 saves (`ruleset_version="0.1.0"`, no government accounting) are
rejected outright: they record only a bare state, never the budget decisions or finance state a
migration would need, so there is nothing to migrate *from*. `content_version` stays
scenario-authored and separate — see `docs/adr/0002-snapshot-history-and-versioning.md` for why the
three version concepts (save-format, ruleset, content) are kept apart, and
`docs/adr/0003-government-accounting.md` for this phase's specific version-bump decision.

## Explicitly not yet simulated (Phase 2A)

Changing a tax rate does **not** move the tax base it applies to — `TaxBaseState` is fixed,
scenario-authored data for the whole of Phase 2A.

---

# Phase 2B1: Sector Production at Fixed Prices

Aggregate economic sectors with capacity, labor productivity, employment, and deterministic
quarterly output at fixed base-year prices. This is the production foundation later phases will use
to derive tax bases from real economic activity — it does **not** yet do that derivation, and it
does not let taxes, spending, prices, inflation, confidence, or population approval affect sector
behavior in either direction. See "Interaction with Phase 2A accounting" below for the isolation
guarantee and "Explicitly not yet simulated" for the full deferred list.

## Sector categories

Eleven fixed categories (`app.simulation.state.SectorCategory`), in a declared canonical order that
is itself part of the ruleset (reordering the enum is a ruleset-affecting change, not cosmetic,
since it changes canonical JSON and `entry_hash`): agriculture, extraction, manufacturing,
construction, energy, transportation, consumer services, finance and professional services,
technology, defense industry, public services.

A player country's `EconomyState` must contain **exactly one `SectorState` per category, all
eleven present** — a zero-capacity sector is a legitimate ("inactive") input, but an absent one
introduces a second, ambiguous "missing vs. zero" concept and is rejected instead.

## Units — real output vs. worker counts vs. money, kept distinct

- `employed_workers`: a nonnegative worker headcount (`app.core.quantity.StrictWorkerCount`).
- `output_per_worker`: fixed-base-year output minor units produced per worker per quarter,
  **strictly positive** (`StrictRealOutputPerWorker`, `gt=0`) — "no output" is expressed only via
  `employed_workers == 0`, not by also allowing `output_per_worker == 0`, so there is exactly one
  way to model an idle sector, not two redundant ones.
- `quarterly_capacity_output`, `labor_limited_output`, `actual_output`, `total_gross_output`:
  fixed-base-year output minor units (`StrictRealOutput`).

These are **real production measures, never spendable money** — a `StrictRealOutput` value cannot
be taxed, spent, or added to cash/debt, and nothing in Phase 2B1 performs such a conversion. Worker
counts and output amounts get distinct type aliases (not one generic "quantity" type) precisely so
a field's annotation alone states what kind of number it holds; see `app/core/quantity.py`.

## Formulas (integer, no floats, no randomness)

```
labor_limited_output    = employed_workers * output_per_worker
actual_output            = min(quarterly_capacity_output, labor_limited_output)
capacity_utilization_bps = floor(actual_output * 10_000 / quarterly_capacity_output)   [capacity > 0]
                          = 0                                                           [capacity == 0]
```

Floor division (not rounding) is used for the same reason `apply_bps` floors elsewhere in this
document: it guarantees `capacity_utilization_bps == 10_000` **if and only if**
`actual_output == quarterly_capacity_output` exactly — rounding could report "100% utilized" for a
sector genuinely short of full capacity by a rounding margin, inside a hash-protected,
self-validating report where every derived number must be exactly recomputable.

## Constraint classification

```
if quarterly_capacity_output == 0:                        INACTIVE
elif labor_limited_output <  quarterly_capacity_output:    LABOR_CONSTRAINED
elif labor_limited_output >  quarterly_capacity_output:    CAPACITY_CONSTRAINED
else:                                                      EXACTLY_BALANCED
```

Capacity is checked **first**. This resolves two edge cases explicitly rather than leaving them to
fall out of the formula incidentally:

- `quarterly_capacity_output == 0 and employed_workers == 0` is `INACTIVE`, not the trivial
  `labor_limited_output (0) == quarterly_capacity_output (0)` reading of "exactly balanced" — a
  sector with no capacity at all has not achieved full utilization of anything.
- `quarterly_capacity_output > 0 and employed_workers == 0` is `LABOR_CONSTRAINED`, **not**
  `INACTIVE` — capacity exists and is simply unstaffed, a materially different fact from "this
  sector has no capacity." Zero output and zero utilization are still correct in this case; only the
  classification label differs from the zero-capacity case.

## Employment boundary — deliberately static this phase (superseded by Phase 2B3)

As originally shipped, `employed_workers` was fixed scenario/decision input, guarded only by
`sector_employment_exceeds_population` (`sum(employed_workers) > population`). **Phase 2B3
removes `employed_workers` entirely** and derives employment every turn from population and
sector labor demand instead — see "Phase 2B3: Labor Allocation and Unemployment at Fixed Prices"
below. What stays true from this section: Phase 2B1 itself still does not implement wage
formation, hiring/layoffs, worker movement, population-group occupations, immigration, strikes,
or tax-driven employment changes — Phase 2B3 adds *how many workers a sector gets*, not any of
those dynamics.

## Report design and self-validation

`ProductionReport`/`SectorProductionReport` (`app.simulation.report`) mirror `FinanceReport`'s
self-validation pattern exactly: a `@model_validator(mode="after")` on every construction path
(fresh build, `model_validate` from history JSON, loaded save, CLI inspection) independently
re-derives `labor_limited_output`, `actual_output`, `capacity_utilization_bps`, and `constraint`
from each sector's own stored inputs, plus `total_employment`/`total_gross_output` from the sum of
the sectors — no trusted boolean, no stored value that could disagree with its own formula.

`sectors` must cover all eleven categories exactly once, in canonical declaration order — enforced
(and, absent duplicates/missing categories, silently normalized) by the same validator, so two
logically-identical reports authored/serialized in different sector order produce byte-identical
canonical JSON and `entry_hash`.

**`ProductionReport` is player-country-only** this phase, exactly mirroring `FinanceReport`'s
scope — AI countries may have `economy=None` and get no production report.

Per-turn `TurnReportEntry` production entries stay concise: a `production_summary` entry (total
employment, total gross output, sector counts per classification) plus a `sector_inactive` entry
for each zero-capacity sector. The complete per-sector figures live exclusively in
`ProductionReport` — they are **not** duplicated as one `TurnReportEntry` per sector per turn.

## `EconomyState`'s structural invariant is checked twice, not once

`SectorState` is deliberately kept **mutable** (no `frozen=True`) — a later economy phase is
expected to make `employed_workers` adjustable. Because of that, `EconomyState`'s own
`@model_validator` (which enforces "all eleven categories, exactly once, canonical order," and
normalizes order when there's no duplicate/missing) only runs at construction time: a later
`sector.category = ...` assignment on an already-built `EconomyState` mutates a *child* object's own
field, which does not re-trigger the *parent* `EconomyState`'s validator. `simulation.invariants`
re-checks the same completeness/uniqueness/ordering rule independently, every turn (before and
after phase execution, like every other invariant), specifically to catch this gap — see
`tests/test_invariants.py`'s nested-mutation regression tests. A plain reassignment of the whole
`sectors` tuple *does* re-trigger the parent validator (pydantic's `validate_assignment=True`
reruns "after" validators even for an already-constructed nested instance) and would silently
re-normalize order back to canonical — only a genuinely bypassed construction
(`model_construct`/`model_copy(update=...)`) can produce a noncanonical-order economy to test
against.

## Phase integration

`resolve_production_and_trade` — an existing, previously no-op slot in the fixed 15-phase
`PHASE_ORDER` — now implements sector production. **Trade (imports/exports, cross-country flows) is
fully out of scope for Phase 2B1** despite the phase's name; that name is the fixed product-spec
phase slot this fills, not a claim about what's implemented. `PhaseContext` gains one field,
`production_report: ProductionReport | None`, set directly by the phase (no `FinanceScratch`-style
intermediate workspace — production reads only current-turn `state...economy` and never spans
multiple phases, unlike finance's opening-snapshot-then-apply shape). `PHASE_ORDER` itself is
unchanged — no reordering.

## Interaction with Phase 2A accounting — full isolation, both directions (superseded by Phase 2B2)

As originally shipped, Phase 2B1 kept production and finance fully isolated in both directions:
production read only `economy`, never `finance`/`treasury`; finance read only its own opening
snapshot and the decision, never `production_report`/`economy`. **Phase 2B2 deliberately breaks
this symmetry** — see "Phase 2B2: Production-Derived Tax Bases" below for the one-directional
relationship that replaces it. What stays true from this section: spending still does not change
sector capacity, infrastructure spending still does not improve production, defense spending still
does not improve defense-industry output, and there is no "higher taxes → lower output" rule (that
connection, if it ever exists, is later work). What changed: sector output **does** now change tax
revenue, through derived tax bases — that is the entire purpose of Phase 2B2.

## Terminology — this is not GDP

Sector output is described as "gross sector output at fixed base-year prices," "production
capacity," "labor-limited output," and "capacity utilization" — **never** GDP, value added, real
GDP, inflation, or economic growth. No value-added accounting exists yet, so summing sector output
(`total_gross_output`) can include intermediate production (e.g. steel counted once as
manufacturing output and again inside a vehicle that consumes it) and must not be read as GDP.

## Version compatibility (Phase 2B1)

`RULESET_VERSION` bumps again, `0.2.0 -> 0.3.0` (`app.simulation.state`), and `content_version`
bumps alongside it. `CountryState.economy` becomes a new **required** field for the player country;
a Phase-2A save has no sector data and none is invented or backfilled — the same "no migration path
because there's no data to migrate from" policy the Phase 1 → 2A bump already established. A
Phase-2A-ruleset save fixture (`backend/tests/fixtures/phase2a_save_ruleset_0.2.0.json`) was frozen
**before** this bump landed — the only way to produce a genuine one, mirroring the Phase-1 fixture.
`SAVE_FORMAT_VERSION` is unchanged; only the ruleset/content-governed inner schema changed.

---

# Phase 2B2: Production-Derived Tax Bases

Phase 2A's tax bases (`personal_income`, `corporate_profit`, `taxable_consumption`) are no longer
fixed, scenario-authored numbers. They are derived every turn from that turn's own sector
production. This is the one connection deliberately left out of Phase 2B1:

```
sector production -> transparent tax-base derivation -> existing tax rates
    -> existing revenue calculation -> existing spending/interest/cash/debt reconciliation
```

The connection is **one-directional**. Tax rates and spending still do not affect production or
the bases derived from it — only production affects bases, and bases affect revenue. `accounting.py`
itself is unmodified: `compute_tax_revenue` still takes a `TaxBaseState`, it just now receives one
that was computed this turn instead of read from state.

## The unit bridge — real output to nominal money, exactly once

Production is fixed-base-year **real** output; tax bases are nominal `Money`. There is no
price-level or inflation model yet, so the conversion is an explicit, temporary bridge: a fixed
base-year price index of 1.0, expressed as exact integer basis points —
`app.core.quantity.BASE_YEAR_PRICE_INDEX_BPS = 10_000` — never a runtime float. The conversion
itself is a named function, `base_year_real_output_to_money(value: RealOutput) -> Money`, not an
implicit `int` pass-through: `RealOutput` and `Money` are both plain `int` aliases at runtime, so
without a real function marking the crossing, nothing would visibly distinguish a real-output
figure from spendable currency at the one place they actually meet. It rejects negative and
non-integer (including `bool`) input, and is called at **exactly one point** — national tax-base
construction in `tax_base_derivation.aggregate_tax_base_contributions`. Every value upstream of
that call (`actual_output`, `modeled_value_added`, `labor_income`, `operating_surplus`, and the
three per-sector contributions) is real; everything at and after that call is nominal `Money`. This
is deliberately temporary: when a real price-level system exists, this function's body changes and
every call site stays the same.

## Formulas (integer, all floored, no randomness)

Per sector, using that sector's `actual_output` from `ProductionReport` (never re-derived from
`SectorState` — see "Same-turn linkage" below):

```
modeled_value_added = floor(actual_output       * value_added_share_bps / 10_000)
labor_income         = floor(modeled_value_added * labor_income_share_bps / 10_000)
operating_surplus    = modeled_value_added - labor_income          # exact, no rounding

personal_contribution    = floor(labor_income        * personal_taxable_share_bps           / 10_000)
corporate_contribution   = floor(operating_surplus   * corporate_taxable_share_bps          / 10_000)
consumption_contribution = floor(modeled_value_added * effective_consumption_base_share_bps / 10_000)
```

`operating_surplus` is computed by subtraction, not a second floored share, specifically so
`labor_income + operating_surplus == modeled_value_added` holds exactly for every input.

**National tax bases are the sum of per-sector contributions**, converted to `Money` via
`base_year_real_output_to_money` — not a value recomputed from national aggregates.
`sum(floor(xi * r)) <= floor(sum(xi) * r)` in general (the gap can be up to `n - 1`), so summing
per-sector floors is the only definition under which every national figure shown in
`TaxBaseDerivationReport` is exactly the sum of the rows beneath it — the same reasoning
`ProductionReport`'s totals already use. `tests/test_tax_base_derivation.py` includes a hand-picked
case proving the two approaches genuinely diverge.

## Terminology: `modeled_value_added` is a proxy, not GDP

`actual_output * an authored share` is named `modeled_value_added`, not "value added" or "sector
value added" — there is no intermediate-consumption accounting behind it, so it cannot honestly
claim to be a national-accounts value-added measure. Its only job is preventing gross-output double
counting *within this derivation*. It is never called GDP, real GDP, or economic growth, and the
sum of per-sector `actual_output` (`ProductionReport.total_gross_output`) still is not GDP either —
see the "Terminology" section above.

`effective_consumption_base_share_bps` is a deliberately reduced-form, country-level coefficient.
It currently combines four things that would, in a fuller model, be separate: household
final-demand composition, the government-vs-private consumption split, exports and other
non-domestic demand, and tax exemptions/fiscal coverage. Calling it simply "the tax system's reach"
would overclaim what one coefficient can represent. Splitting it into a structural final-demand
coefficient and a separate tax-coverage coefficient is recorded as later work, not attempted here —
Phase 2B2 does not add a final-demand or trade model.

## Authored inputs vs. derived outputs

Two new authored inputs, kept structurally separate by what they describe:

- **Per-sector, structural** (`SectorState`): `value_added_share_bps`, `labor_income_share_bps` —
  genuinely differ by industry (extraction vs. professional services), so they live per sector.
- **Country-level, fiscal** (`GovernmentFinanceState.tax_base_coefficients`, a new
  `TaxBaseCoefficients` model): `personal_taxable_share_bps`, `corporate_taxable_share_bps`,
  `effective_consumption_base_share_bps` — describe how much of the economy the tax system
  reaches, a property of fiscal policy rather than any one sector.

`GovernmentFinanceState.tax_bases` (the Phase 2A field) is **removed entirely**. Tax bases are
purely derived and turn-local: recorded only in `TaxBaseDerivationReport`/`FinanceReport`, never
written back into `GameState`. There is no "opening"/"closing" tax-base concept — only **applied**,
the bases this turn's production produced and this turn's revenue used.

## Report design, self-validation, and the cross-report chain

`TaxBaseDerivationReport`/`SectorTaxBaseReport` (`app.simulation.report`) mirror `FinanceReport`'s/
`ProductionReport`'s self-validation pattern: every derived field is independently re-checked from
the report's own stored inputs, on every construction path. `sectors` covers all eleven categories
exactly once in canonical order, normalized the same way `ProductionReport.sectors` is.
`TaxBaseDerivationReport` is player-country-only, mirroring `FinanceReport`/`ProductionReport`.

Self-validation of each report in isolation is not enough to prove the *chain* is consistent —
three internally-valid reports could still describe three different calculations. `TurnReport`
therefore adds its own cross-report validators: per `SectorCategory`, matched by **category
identity, never tuple position**, `ProductionReport.actual_output` must equal what
`TaxBaseDerivationReport` used as its input for that category; `TaxBaseDerivationReport
.derived_tax_bases` must exactly equal `FinanceReport.tax_bases`; and `production`,
`tax_base_derivation`, and `finance` must be all present or all absent on a given `TurnReport` — a
partial combination is rejected rather than accepted as an incomplete audit trail.
`tests/test_tax_base_report.py` independently corrupts every direction of this chain (production
vs. derivation, derivation vs. finance, each missing-report combination) and proves each fails on
fresh construction *and* on `model_validate_json` — independently of history's hash-tampering
detection, which is a different failure mode (bytes changed after the fact, not "never consistent
to begin with").

Per-turn `TurnReportEntry` derivation entries stay concise: one `tax_bases_derived` entry carrying
the three national totals. The complete per-sector breakdown lives exclusively in
`TaxBaseDerivationReport`.

## Same-turn linkage — no hidden lag

`resolve_production_and_trade` (phase 3) always runs before
`resolve_government_revenue_and_expenditure` (phase 4) in the fixed `PHASE_ORDER` — unchanged, no
reordering. Derivation runs at the **start** of the revenue phase, reading `ctx.production_report`
that the same `resolve_turn` call already computed this turn — never a cached or previous-turn
value. `PhaseContext` is fresh per `resolve_turn` call, so there is no structural way for a stale
value to leak across turns. `tests/test_production_to_revenue_linkage.py` proves this holds across
a real multi-turn run, not just turn 0.

## Calibration — both scenario fixtures reproduce their original Phase 2A bases exactly

At a base-year price index of 1.0, Phase 2B1's original scenario production figures were roughly
three orders of magnitude too small to reproduce Phase 2A's authored tax bases. Both
`tiny_valid.yaml` and `deficit_demo.yaml` have their sector outputs re-authored (scaling
`quarterly_capacity_output`/`output_per_worker` only, never `employed_workers`) so the derived
bases reproduce the original authored bases **exactly** — verified by direct computation and by
resolving turn 0 through the real engine: `tiny_valid.yaml` reproduces personal=4,000,000,000 /
corporate=2,000,000,000 / consumption=3,000,000,000; `deficit_demo.yaml` reproduces
personal=1,000,000,000 / corporate=500,000,000 / consumption=800,000,000. Every downstream
revenue/interest/borrowing/reconciliation figure in both fixtures is therefore unchanged from
Phase 2A — see each YAML file's header comment for the full worked calibration.

## Version compatibility (Phase 2B2)

`RULESET_VERSION` bumps again, `0.3.0 -> 0.4.0`, and `content_version` bumps alongside it.
`CountryState`'s reachable finance shape changes in both directions: `tax_base_coefficients`
becomes newly required, each sector's `value_added_share_bps`/`labor_income_share_bps` become
newly required, and the previously-required `tax_bases` field is removed. An older save has no
coefficient data to backfill and no way to derive it retroactively — the same "nothing to migrate
from" policy as every prior bump. A Phase-2B1-ruleset save fixture
(`backend/tests/fixtures/phase2b1_save_ruleset_0.3.0.json`) was frozen **before** this bump
landed — the only way to produce a genuine one. `SAVE_FORMAT_VERSION` is unchanged.

## Explicitly not yet simulated (Phase 2A, 2B1, 2B2)

Not yet modeled at all, in Phase 2A, 2B1, or 2B2: tax-rate elasticity, tax avoidance/compliance
behavior, Laffer-curve effects, production responses to taxes, capacity investment or
depreciation, GDP/value-added/real-growth figures, prices, shortages, inflation, central banking,
exchange rates, trade, population approval effects, service-quality outcomes, corruption. All of
it stays honestly absent rather than faked — see the product spec's "no placeholder feature
claims" rule (§5.7).

---

# Phase 2B3: Labor Allocation and Unemployment at Fixed Prices

Sector employment (`SectorState.employed_workers` in Phase 2B1/2B2) is no longer scenario-authored.
It is derived every turn from the player's population and each sector's labor demand:

```
population -> effective labor force -> sector labor demand -> deterministic allocation
    -> employment and unemployment -> existing production -> existing tax-base and finance chain
```

Still fixed prices, still no wages — this connects population to production, nothing more. See
`docs/adr/0006-labor-allocation-at-fixed-prices.md` for the design decisions.

## Labor supply — a reduced-form coefficient, not a demographic model

```
effective_labor_force = floor(population * effective_labor_force_share_bps / 10_000)
```

`population` is `CountryState.population` — the single authoritative headcount;
`population_groups` merely partitions it and is not used here. `effective_labor_force_share_bps`
(a new `StrictBps` field on `EconomyState`) is a deliberately reduced-form placeholder: it
currently combines working-age share, labor-force participation, and any other structural
availability limitation into one number, exactly the kind of temporary simplification
`TaxBaseCoefficients.effective_consumption_base_share_bps` already is (see the Phase 2B2 section
above). Since `0 <= effective_labor_force_share_bps <= 10_000` and `population >= 0`, floor
division gives `0 <= effective_labor_force <= population` **by construction**, not by a runtime
clamp.

## Sector labor demand — a staffing requirement, not observed vacancies

```
required_workers = 0                                             [quarterly_capacity_output == 0]
                 = ceil(quarterly_capacity_output / output_per_worker)             [otherwise]
```

Integer ceiling division only (`(capacity + output_per_worker - 1) // output_per_worker`), no
floats — `output_per_worker` is already strictly positive (Phase 2B1), so no division-by-zero
path exists. This is the workers needed to run a sector at **full modeled capacity** — not
observed job openings, not wage-based labor demand, not profit-maximizing employment; none of
those concepts exist without a wage/price system, which Phase 2B3 does not add.

## Deterministic allocation — largest-remainder method, canonical tie-breaking

```
total_labor_demand = sum(required_workers)

if total_labor_demand <= effective_labor_force:      # abundant or exactly equal
    allocated[i] = required[i]
else:                                                 # scarce
    floor_i     = (effective_labor_force * required_i) // total_labor_demand
    remainder_i = (effective_labor_force * required_i) %  total_labor_demand
    leftover    = effective_labor_force - sum(floor_i)
    distribute +1 to the `leftover` sectors with the largest remainder_i,
      ties broken by ascending canonical SectorCategory declaration order
```

`allocated_i <= required_i` holds provably, not just empirically: in the abundant branch trivially
(`allocated_i == required_i`); in the scarce branch, `effective_labor_force < total_labor_demand`
implies `floor_i <= required_i - 1` whenever `required_i > 0`, and `leftover` is always strictly
less than the number of sectors with positive demand, so no sector ever receives more than one
extra unit above its floor. Verified by direct proof, by a hand-picked all-equal-remainder
fixture (eleven sectors, identical demand, tie-breaking resolved entirely by canonical order —
`tests/test_labor_allocation.py`), and by a committed property-based test (Hypothesis, 1,000
random cases per run) proving `0 <= allocated_i <= required_i` and `sum(allocated) ==
min(labor_force, sum(required))` for arbitrary nonnegative integer inputs.

## Identities

```
total_employment      = sum(allocated_i) = min(effective_labor_force, total_labor_demand)
unemployed_workers    = effective_labor_force - total_employment
unfilled_jobs          = total_labor_demand   - total_employment
unemployment_rate_bps  = floor(unemployed_workers * 10_000 / effective_labor_force)
                           [effective_labor_force > 0]
                       = 0                                        [effective_labor_force == 0]
```

`unemployment_rate_bps == 0` when the labor force is zero is a documented choice, not a division
guard worked around silently — 0/0 has no meaningful rate, and 0 is the only non-arbitrary answer.

## Production consumes allocated workers, not an authored field

`production_accounting.compute_sector_output` takes an explicit `allocated_workers` parameter
instead of reading `SectorState.employed_workers` (which no longer exists) —
`labor_limited_output = allocated_workers * output_per_worker`, otherwise identical to the Phase
2B1 formula. `aggregate_production` likewise sums employment from the allocation results rather
than from state.

## Report design and the four-report cross-validation chain

`LaborMarketReport`/`SectorLaborAllocationReport` (`app.simulation.report`) mirror the existing
self-validation pattern: every aggregate is independently re-derived from the report's own stored
sector rows on every construction path, `sectors` covers all eleven categories exactly once in
canonical order, and per-row `allocated_workers <= required_workers` plus `unfilled_workers ==
required_workers - allocated_workers` are each checked directly.

`TurnReport`'s cross-report chain extends from three reports to four: `LaborMarketReport
.allocated_workers` must equal `ProductionReport.employed_workers` for the same `SectorCategory`
(matched by category identity, never tuple position, for the same reason the Phase 2B2 chain
does), and `labor_market`/`production`/`tax_base_derivation`/`finance` must be all present or all
absent — every partial combination is rejected outright.

## Same-turn linkage — no hidden lag

No new `PHASE_ORDER` slot: allocation runs at the **very start** of `resolve_production_and_trade`
(phase 3), immediately before per-sector output — same phase, same turn. A population or
labor-force-share change takes effect the turn it applies, proven across a real multi-turn run
(`tests/test_labor_to_production_linkage.py`), the same way Phase 2B2's derivation linkage is
proven.

## Not an "acceptable unemployment" rule

Two new every-turn invariants (`effective_labor_force_share_out_of_range`,
`effective_labor_force_exceeds_population`) are defense-in-depth backstops against a bypassed
construction — mirroring `tax_base_coefficient_out_of_range`'s role in Phase 2B2 — **not** a claim
about what unemployment level is acceptable. No invariant enforces an unemployment range: that is
a scenario-calibration concern (see "Calibration" below), and a future crisis, war, or shock must
remain free to produce extreme unemployment without tripping an engine-level constraint.

## Calibration — both scenario fixtures land at a plausible ~10% unemployment

Deriving employment from capacity/productivity alone (holding every Phase 2B2 output/base/revenue
figure fixed) initially produced ~91%/~94.5% unemployment in the two fixtures — technically exact,
but implausible for developer fixtures that appear in CLI output, documentation, and future
political-effect tests. Both scenarios' `output_per_worker` (never population, capacity, or the
labor-force share) were retuned so labor demand rises to a plausible level while every sector's
`actual_output` — and therefore every output/tax-base/revenue figure — stays byte-for-byte
identical to Phase 2B2: `tiny_valid.yaml` — labor force 600,000, employment 540,000, unemployed
60,000 (exactly 10.00%), output 20,000,000,000, bases 4,000,000,000/2,000,000,000/3,000,000,000.
`deficit_demo.yaml` — labor force 200,000, employment 180,000, unemployed 20,000 (exactly 10.00%),
output 4,000,000,000, bases 1,000,000,000/500,000,000/800,000,000. Labor stays abundant in both —
scarcity is exercised only by a dedicated in-test fixture, not a committed scenario. One disclosed
consequence: since abundant-labor allocation always gives `allocated == required`, and that
implies `actual_output == capacity` whenever a sector is staffed at all, `labor_constrained`
becomes unreachable in `tiny_valid` specifically — a real structural consequence of deriving
employment, not a bug, covered by the scarce in-test fixture instead.

## Version compatibility (Phase 2B3)

`RULESET_VERSION` bumps again, `0.4.0 -> 0.5.0`, and `content_version` bumps alongside it.
`CountryState`'s reachable economy shape changes in both directions: `EconomyState
.effective_labor_force_share_bps` becomes newly required, and the previously-required
`SectorState.employed_workers` field is removed. An older save has no labor-force-share data to
backfill — the same "nothing to migrate from" policy as every prior bump. A Phase-2B2-ruleset save
fixture (`backend/tests/fixtures/phase2b2_save_ruleset_0.4.0.json`) was frozen **before** this
bump landed — the only way to produce a genuine one. `SAVE_FORMAT_VERSION` is unchanged.

## Explicitly not yet simulated (Phase 2B3)

Not modeled: wages or wage bargaining, minimum wage, hiring/firing delay or adjustment costs,
skills/education matching/occupations, worker mobility costs, labor unions or strikes,
unemployment benefits, demographic age structure, migration or population growth, tax-rate or
spending effects on labor supply/demand, and everything the Phase 2A/2B1/2B2 exclusion lists
above already cover. All of it stays honestly absent rather than faked.

---

# Phase 2C1: Resource Endowments and Extraction

Eight physical natural resources, deterministically extracted and depleted every turn, entirely
isolated from production/tax bases/revenue this phase:

```
resource endowments -> regeneration -> extraction-sector labor sub-allocation -> extraction
    -> depletion -> (nothing further this phase — see "Isolation" below)
```

This is the shallow **base-game** resource foundation, not the future Resources and Energy
expansion. See `docs/adr/0007-resource-endowments-and-extraction.md` for the design decisions,
including the R1–R9 corrections applied during two independent review rounds.

## Categories and units

Eight fixed categories (`app.simulation.state.ResourceCategory`), canonical declaration order:
timber, iron ore, coal, crude oil, natural gas, uranium, copper, critical minerals. Only **timber**
is renewable (`RENEWABLE_RESOURCES = frozenset({TIMBER})`); every other category is a finite
reserve that only ever depletes.

Each category's physical unit is a fixed property of the category, not authored per-deposit state
(`RESOURCE_UNITS`): timber m³; iron ore/coal/uranium/copper/critical minerals tonnes; crude oil
barrels; natural gas thousand m³. **Heterogeneous resource quantities are never summed together**
— there is no `total_extraction`/`total_resources` field anywhere; only worker counts and
per-status counts are aggregated.

## Units — a third distinct type family, with no bridge to `Money` or `RealOutput`

`ResourceQuantity`/`StrictResourceQuantity` (`ge=0`) and `StrictResourceQuantityPerWorker` (`gt=0`)
in `core/quantity.py` — a physical quantity is neither spendable money nor real production output,
and gets its own distinct type family for the same reason `RealOutput` was kept distinct from
`Money` in Phase 2B1. **No conversion function to either exists** — the deliberate absence is what
makes "resources feed nothing yet" structurally true, not merely documented.

## State — `EconomyState.resource_deposits`

All 8 categories exactly once, canonical order, zero-stock/zero-capacity entries legal (a
resource-poor country still declares every category, just at zero). **Unlike every other
canonical-order validator in this codebase** (`sectors` and every per-category report collection),
noncanonical resource order is **rejected outright, not silently normalized** — see the ADR's R3
for why.

```python
class ResourceDepositState(BaseModel):
    category: ResourceCategory
    remaining_stock: StrictResourceQuantity            # the ONLY field phase 3 ever mutates
    extraction_capacity_per_turn: StrictResourceQuantity
    output_per_worker: StrictResourceQuantityPerWorker  # strictly positive
    regeneration_per_turn: StrictResourceQuantity = 0   # nonzero only if renewable
    stock_ceiling: StrictResourceQuantity | None = None # not None only if renewable
```

Authored: all six fields above. Turn-local derived: regenerated, available, required workers,
allocated workers, extracted, closing stock, status. **Mutated by phase 3, once per turn:**
`remaining_stock` only.

## Formulas (integer, all floored, no randomness)

```
regenerated = 0                                                    [nonrenewable]
            = max(0, min(regeneration_per_turn,
                         stock_ceiling - remaining_stock))         [renewable]

available            = remaining_stock + regenerated
extractable_ceiling  = min(available, extraction_capacity_per_turn)
required_workers     = 0                                    [extractable_ceiling == 0]
                     = ceil(extractable_ceiling / output_per_worker)   [otherwise]

allocated_workers    = largest_remainder_allocation(
                           weights_by_category = required_workers per deposit (canonical order),
                           budget = extraction sector's allocated_workers)

extracted            = min(available, extraction_capacity_per_turn,
                           allocated_workers * output_per_worker)
closing_stock        = available - extracted
unassigned_resource_workers = extraction_sector_workers - sum(allocated_workers)
```

Regeneration happens **before** extraction — growth accrues over the quarter and is harvestable
within it; `available` is the single quantity every downstream bound is expressed against.

**Conservation, exact, per deposit, every turn:**

```
remaining_stock + regenerated == extracted + closing_stock          (renewable + nonrenewable)
remaining_stock              == extracted + closing_stock            (nonrenewable, regen == 0)
```

Holds by construction: `closing_stock` is *defined* as `available − extracted`, and
`extracted ≤ available` because `available` is one of the three terms of the `min`.
`ResourceDepositReport` independently re-derives it from its own stored fields, including
`regeneration_per_turn`/`stock_ceiling` (see "Self-validation" below).

## Status classification — the stock/capacity tie resolves to STOCK_CONSTRAINED

```
if extraction_capacity_per_turn == 0:            INACTIVE
elif available == 0:                             DEPLETED
elif extracted == available:                      STOCK_CONSTRAINED
elif extracted == extraction_capacity_per_turn:   CAPACITY_CONSTRAINED
else:                                              LABOR_CONSTRAINED
```

Checked top-down, mirroring `SectorConstraint`, so exactly one status applies. Stock exhaustion is
checked **before** the stock/capacity tie case: a deposit whose `available` stock exactly equals
its `extraction_capacity_per_turn` reports `STOCK_CONSTRAINED`, not `CAPACITY_CONSTRAINED` — the
stock, not the capacity, determined the outcome that turn, even though the two bounds happened to
coincide (see the worked `deficit_demo.yaml` example below).

**Edge cases, all defined and tested:**

| Case | Result |
|---|---|
| `extraction_capacity_per_turn == 0` | `required = 0` → `extracted = 0`, `closing = available`; `INACTIVE` |
| `remaining_stock == 0`, no regeneration | `available = 0` → `extracted = 0`; `DEPLETED` |
| zero labor budget | all `allocated = 0` → all `extracted = 0`; stocks unchanged (+regen) |
| zero total demand, positive budget | nothing allocated; `unassigned_resource_workers == budget` |
| `output_per_worker` | strictly positive at the type level — no division-by-zero path exists |
| stock at ceiling (renewable) | `regenerated = 0`; ceiling never exceeded |
| one-unit stock | `extracted = 1`, `closing = 0`, then `DEPLETED` next turn |

## Labor integration and its honest limitation

The extraction **sector's** `allocated_workers` (from `LaborMarketReport`, already validated) is
the budget, sub-allocated across the 8 deposits. Unused workers surface explicitly as
`unassigned_resource_workers` — never silently dropped, and documented explicitly as still-employed
sector activity (support, surveying, transport, …), **not unemployment**, and not double-counted
against `LaborMarketReport.unemployed_workers` (R6 — this field was originally named
"idle_extraction_workers," which implied a contradiction with the labor report already counting
these workers as employed).

**Honest limitation:** under the conservation-only isolation boundary (below), the extraction
sector's abstract `RealOutput` and the physical tonnage extracted this turn are **two descriptions
of the same workers' activity**, not two activities. No double-counting occurs *in the economy*
because physical quantities never convert to `RealOutput` or `Money` — but this is precisely why
the recommended follow-up ticket must *replace* the extraction sector's output derivation with a
physical-derived one, not add to it (see "Explicitly not yet simulated" below).

## The neutral allocation core — order-sensitive, not permutation-independent

The Phase 2B3 largest-remainder algorithm moved verbatim into a new, category-agnostic
`simulation/integer_allocation.py`, since it never had any labor-specific content. It is
**order-sensitive by contract**: it accepts `(category, weight)` pairs already in the caller's
order, preserves that order, and resolves ties by caller-supplied position — it does not promise
permutation independence, and pairing each weight with its category identity does not confer it.

- `labor_allocation.allocate_workers` keeps its existing canonical-tuple signature, byte-for-byte
  unchanged from Phase 2B3.
- `resource_extraction.allocate_extraction_workers` is the one caller that needs permutation
  independence: it accepts a category-keyed `Mapping`, verifies completeness, and canonicalizes to
  `tuple(ResourceCategory)` order *before* calling the order-sensitive core — so permuting the
  mapping's insertion order provably cannot change the result.

## Phase timing and mutation safety — depletion happens where extraction is computed

```
phase 3  resolve_production_and_trade
           +- labor allocation                    (existing, unchanged)
           +- resource extraction                   [NEW]
           |     1. compute every deposit's formulas (pure)
           |     2. write each deposit's closing_stock into economy.resource_deposits,
           |        by ResourceCategory identity — never tuple position — the ONLY
           |        state mutation this phase performs
           +- sector production                     (existing, unchanged)
phase 5  update_prices_inflation_employment_debt_reserves
           +- treasury cash/debt only (existing, unchanged) — needs NO resource code
```

No new `PHASE_ORDER` slot. Extraction and its resulting depletion are one domain operation,
performed together — a deliberate, narrow, explicitly-tested exception to phase 3's prior "never
mutates state" contract, scoped to `resource_deposits` alone. `resolve_turn`'s single deep copy
and post-phase invariant re-check are unaffected by *which* phase performed a mutation — an
invariant violation still discards the entire working copy.

## Report design and self-validation

```python
class ResourceDepositReport(BaseModel):     # one row per ResourceCategory, canonical order
    category: ResourceCategory
    opening_stock: StrictResourceQuantity
    regeneration_per_turn: StrictResourceQuantity      # carried so regeneration is re-derivable
    stock_ceiling: StrictResourceQuantity | None
    regenerated: StrictResourceQuantity
    available_stock: StrictResourceQuantity
    extraction_capacity_per_turn: StrictResourceQuantity
    output_per_worker: StrictResourceQuantityPerWorker
    required_workers: StrictWorkerCount
    allocated_workers: StrictWorkerCount
    extracted: StrictResourceQuantity
    closing_stock: StrictResourceQuantity
    status: DepositStatus
```

`regeneration_per_turn`/`stock_ceiling` are carried on the report specifically so
`_regenerated_matches_formula` can recompute the clamp formula from the row's **own** stored
fields — fresh build and `model_validate_json` history-loading alike — rather than trusting the
phase that built it (without them, the report could not independently verify the one number that
makes timber different from every other resource). One validator per equation, mirroring the
established pattern; noncanonical `deposits` order is **rejected**, not normalized (R3).

`TurnReport` gains `resources: ResourceExtractionReport | None` (a fifth report) and a new
cross-report link:

```
labor_market.sectors[EXTRACTION].allocated_workers == resources.extraction_sector_workers
```

The all-present-or-all-absent completeness rule extends from four reports to five — all 30 proper
nonempty partial combinations are rejected.

## Isolation — conservation-only, extraction is economically inert this phase (superseded by Phase 2C2)

Production, tax bases, revenue, and treasury stay **byte-identical** regardless of resource
endowments. The relationship is one-directional: resource endowments determine extraction;
extraction changes no production, tax base, revenue, price, trade, approval, or war outcome.
Actively tested in both directions, including that phase 3's mutation scope is limited to
`resource_deposits` and nothing else in state.

The alternative — deriving some extraction-sector `RealOutput` from physical extraction — would
**double-count**, since the sector already produces `RealOutput` from those same workers (see
"Labor integration" above). Making that connection non-duplicative requires *replacing* the
sector's output derivation, recorded as the Phase 2C2 follow-up, not attempted here.

**This isolation boundary no longer holds as of Phase 2C2** (below), which deliberately reverses
it: resource endowments now determine the extraction sector's `RealOutput` directly, and that
figure flows through to tax bases, revenue, and treasury exactly like every other sector's output.
This section is retained as an accurate historical record of Phase 2C1's own boundary, not a
statement of current behavior.

## Calibration — the corrected three-regime `deficit_demo.yaml` timber trajectory

Both scenarios keep every Phase 2B3 labor/production/tax-base/revenue/treasury figure
byte-identical. `tiny_valid.yaml` is resource-rich (all 8 categories active, labor abundant,
extraction-sector workers 20,000, total resource demand 13,500, unassigned 6,500); every deposit
is `CAPACITY_CONSTRAINED` and declines net of regeneration each turn, none reaching its own
stock/capacity boundary within any tested horizon (timber's own boundary sits around resolution
250). `deficit_demo.yaml` is resource-poor/import-dependent (only timber and iron ore endowed;
extraction-sector workers 10,000, total demand 800, unassigned 9,200) — imports are **not**
implemented, stated plainly rather than implied.

`deficit_demo.yaml`'s timber (opening 200,000; capacity 10,000; output-per-worker 25; regeneration
5,000/turn; ceiling 250,000), counted by completed resolutions, worked out **exactly** across
three distinct regimes:

| Resolutions | opening | regen | available | extracted | closing | status |
|---|---|---|---|---|---|---|
| 1–39 | 200,000 ↓ 10,000 | 5,000 | 205,000 ↓ 15,000 | 10,000 | 195,000 ↓ **5,000** | `CAPACITY_CONSTRAINED` |
| 40 (boundary) | 5,000 | 5,000 | **10,000** | 10,000 | **0** | **`STOCK_CONSTRAINED`** |
| 41 onward | 0 | 5,000 | 5,000 | 5,000 | 0 | `STOCK_CONSTRAINED` |

While capacity-bound, timber declines `10,000 − 5,000 = 5,000` net per resolution. At resolution
40, `available = 5,000 + 5,000 = 10,000` **ties** capacity exactly, so the status precedence —
checking `extracted == available` before `extracted == capacity` — classifies it
`STOCK_CONSTRAINED`, even though extraction is still the full 10,000. From resolution 41 the
deposit sits in a true steady state, extracting exactly the regenerated 5,000/turn forever
(`STOCK_CONSTRAINED`, never `DEPLETED`, since `available` is never exactly zero while regeneration
is active). `remaining_stock` is never negative at any point, and
`opening + regenerated == extracted + closing` holds exactly at every resolution including the
boundary. (An earlier draft of this document said "timber holds steady" and "39 turns, then steady
state" — both wrong, caught by independent review; see ADR 0007's R4/R8 for the correction.)

## Version compatibility (Phase 2C1)

`RULESET_VERSION` bumps again, `0.5.0 -> 0.6.0`, and `content_version` bumps alongside it.
`EconomyState`'s reachable shape changes: `resource_deposits` becomes newly required. An older
save has no endowment data to backfill — the same "nothing to migrate from" policy as every prior
bump. A Phase-2B3-ruleset save fixture
(`backend/tests/fixtures/phase2b3_save_ruleset_0.5.0.json`) was frozen **before** this bump
landed — the only way to produce a genuine one. `SAVE_FORMAT_VERSION` is unchanged.

## Explicitly not yet simulated (Phase 2C1)

Not modeled, and this is the **shallow base-game foundation**, not the future Resources and Energy
expansion: market prices, inflation, exchange-rate valuation for resources; imports, exports,
trade routes, tariffs, embargoes, stockpiles separate from deposits; resource-to-industry
input-output chains and energy conversion (see "Labor integration"'s honest limitation above);
pipelines, refineries, individual mines/fields, construction, maintenance; ownership, private
firms, state enterprises, royalties, concessions, foreign investment; nationalization,
privatization, cartels, lobbying, corruption, sanctions, smuggling; pollution, climate effects,
reclamation, accidents, environmental politics; military consumption, strategic reserves, resource
wars, nuclear-weapons inputs; exploration, discovery, technological substitution, reserve
reclassification; province/field/mine-level geography (waits for Phase 6's map); and everything
the Phase 2A/2B1/2B2/2B3 exclusion lists above already cover. All of it stays honestly absent
rather than faked.

Phase 2C1's own recommended follow-up — replacing the extraction sector's `RealOutput` derivation
with one computed from physical extraction — is Phase 2C2, below.

# Phase 2C2: Physical Extraction Drives Extraction-Sector Output

Replaces (never adds to) the extraction sector's `RealOutput` derivation with one computed from
that turn's physical extraction — resolving Phase 2C1's own "two descriptions of the same labor"
limitation:

```
resource endowments -> extraction -> extraction-sector RealOutput -> other-sector production
    -> production-derived tax bases -> tax revenue -> spending/interest -> treasury and debt
```

See `docs/adr/0008-physical-extraction-derived-sector-output.md` for the design decisions,
including the R1–R10 corrections applied during three independent review rounds.

## The bridge — physical quantity to real output, exactly once, no rounding

`core/quantity.py` gains `StrictRealOutputPerResourceUnit` (`gt=0`) and
`extracted_resource_to_real_output(*, extracted, real_output_per_unit) -> RealOutput` — the named
conversion point, mirroring `base_year_real_output_to_money`'s shape: a real function, explicit
type rejection, exact integer multiplication, **no division anywhere**. The same function converts
both the actual extracted quantity and the potential (stock/capacity-bounded) quantity for a
category — same bridge, two different inputs.

## Coefficients — scenario-authored, strictly positive, one per category

```python
class ResourceOutputCoefficient(BaseModel):
    category: ResourceCategory
    real_output_per_unit: StrictRealOutputPerResourceUnit   # gt=0 — zero is never legal
```

`EconomyState.resource_output_coefficients: tuple[ResourceOutputCoefficient, ...]` — all 8
categories required exactly once, canonical order **rejected, not normalized** (the resource
precedent, not the sector one). Zero is deliberately invalid: it keeps "zero contribution because
nothing was extracted" (the only legal path) cleanly distinct from "zero contribution despite
extraction" (impossible by type). Persisted in `state_json`, hash-protected, validated on every
construction and re-checked by `check_invariants` every turn — identical treatment to every other
piece of scenario-authored state.

## Formulas — potential output eliminates the need for a clamp

```
per category, canonical order:
    contribution_i           = extracted_i * real_output_per_unit_i
    potential_quantity_i     = min(available_stock_i, extraction_capacity_per_turn_i)
    potential_contribution_i = potential_quantity_i * real_output_per_unit_i

extraction_sector_real_output      = sum(contribution_i)
extraction_sector_potential_output = sum(potential_contribution_i)

capacity_utilization_bps (extraction row only)
    = floor(extraction_sector_real_output * 10_000 / extraction_sector_potential_output)
      if extraction_sector_potential_output > 0 else 0
```

`potential_quantity_i` reuses fields `DepositExtractionResult` already carries
(`resource_extraction.py` — **unmodified** by this phase) — `available_stock` and
`extraction_capacity_per_turn`, the same two terms `min()`-bounded in the extraction formula
itself. Since `extracted_i = min(available_i, capacity_i, allocated_i * output_per_worker_i)` is a
`min` over those same two terms plus one more, `extracted_i <= potential_quantity_i`
unconditionally; multiplying by a positive coefficient and summing preserves the inequality, so
`extraction_sector_real_output <= extraction_sector_potential_output` **always, by construction**.
`capacity_utilization_bps` therefore never needs clamping to satisfy `StrictBps`'s `[0, 10_000]`
bound — exact and lossless, exactly like every other sector. When the denominator is `0`, the
numerator is provably `0` too (the same proof), so `capacity_utilization_bps := 0` by convention,
never a `ZeroDivisionError`.

## Constraint classification — `PHYSICAL_RESOURCE_CONSTRAINED`, and rejection over classification

```python
class SectorProductionConstraint(StrEnum):   # report.py-local; superset of the engine's own
    CAPACITY_CONSTRAINED = "capacity_constrained"              # STANDARD basis only
    LABOR_CONSTRAINED = "labor_constrained"                    # both bases
    EXACTLY_BALANCED = "exactly_balanced"                      # STANDARD basis only
    INACTIVE = "inactive"                                      # both bases
    PHYSICAL_RESOURCE_CONSTRAINED = "physical_resource_constrained"   # RESOURCE_EXTRACTION only
```

```
potential_output == 0                              -> INACTIVE           (implies actual == 0)
potential_output >  0, actual_output <  potential   -> LABOR_CONSTRAINED  (includes zero
                                                          employment — a resource existing but
                                                          unstaffed is a labor fact, mirroring
                                                          the Phase 2B1 precedent)
potential_output >  0, actual_output == potential   -> PHYSICAL_RESOURCE_CONSTRAINED
```

**`actual_output > potential_output` is rejected outright — a `raise`, not a classifiable branch —
before any classification is attempted.** This state is invalid, not merely unreachable by
legitimate code paths; three independent layers guard it: a row-level check on each deposit's
contribution, an aggregate-level check on the sector totals, and the classification function's own
refusal to assign any status to it.

## `output_basis` — forced by category, never authored

```python
class SectorOutputBasis(StrEnum):
    STANDARD = "standard"
    RESOURCE_EXTRACTION = "resource_extraction"
```

`SectorProductionReport.output_basis` is cross-validated against `category` on every construction
— `EXTRACTION` must be `RESOURCE_EXTRACTION`, every other category must be `STANDARD`. The four
STANDARD-basis validators (`labor_limited_output`/`actual_output`/`capacity_utilization_bps`/
`constraint`) are byte-for-byte the pre-2C2 formulas for the ten non-extraction sectors; the
RESOURCE_EXTRACTION branch performs only a definitional self-consistency check
(`labor_limited_output == actual_output`) at the row level, deferring the *authoritative* checks
entirely to three new `TurnReport` cross-validators matching by category identity against
`ResourceExtractionReport`'s totals — `TurnReport` stays at five reports, the 30-subset
completeness rule unchanged.

## Legacy fields — completely inert for the extraction row

`SectorState.quarterly_capacity_output`/`.output_per_worker` remain on every sector, including
EXTRACTION, but are read **nowhere** in the RESOURCE_EXTRACTION derivation — not for output, not
for utilization, not for classification. A scenario author can set either to any value with zero
observable effect on the extraction row. (Both are still read by `labor_allocation.py`, unmodified
by this phase, to compute the sector's labor *demand* — a real, separate effect on
`employed_workers` that this phase's inertness claim deliberately does not cover.)
`employed_workers` itself is not legacy — it is true extraction-sector employment, simply no
longer an input to any *derived output* field on this row.

## Accounting identity — extraction counted exactly once

`ProductionReport._total_gross_output_matches_sum` — unmodified since before this phase — sums
`sectors[*].actual_output` unconditionally, and the extraction row's `actual_output` is now the
physical bridge total. No other code path adds it anywhere else; the eight per-category
contributions sum to `extraction_sector_real_output`, which equals the extraction row's
`actual_output`, which appears in `total_gross_output` exactly once alongside the other ten
sectors' untouched figures.

## Calibration — both fixtures preserve their pre-2C2 output exactly, at their own turn scope

`tiny_valid.yaml` — every deposit is capacity-bound throughout its full 100-turn tested horizon, so
Σ = 2,000,000,000 is preserved for all 100 turns:

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

`deficit_demo.yaml` — preserved at turn 1 only (Σ = 500,000,000), then diverges exactly at the
same two boundaries the physical timber trajectory (Phase 2C1, above) already established:

| Turns | timber | iron_ore | extraction output | driver |
|---|---|---|---|---|
| 1–25 | 10,000 | 20,000 | 500,000,000 | both deposits producing |
| 26–40 | 10,000 | 0 (depleted) | 100,000,000 | iron_ore exhausted after turn 25 |
| 41–100 | 5,000 | 0 | 50,000,000 | timber's renewable steady state |

No test in this suite asserts equality of any save, state, report, or hash across the 0.6.0/0.7.0
ruleset boundary — only these specific enumerated fields, at exactly these turn ranges.

## Version compatibility (Phase 2C2)

`RULESET_VERSION` bumps again, `0.6.0 -> 0.7.0`, `content_version` alongside it — schema-shape
compatibility, not a claim about content-value uniqueness (`tiny_valid.yaml` and
`deficit_demo.yaml` already carry different coefficient values under the same `content_version`,
exactly like every other piece of scenario content they already disagree on). A Phase-2C1-ruleset
save fixture (`backend/tests/fixtures/phase2c1_save_ruleset_0.6.0.json`) was frozen with the
genuinely unmodified 0.6.0 engine before this bump landed. `SAVE_FORMAT_VERSION` is unchanged.

## Explicitly not yet simulated (Phase 2C2)

Unchanged from Phase 2C1's own exclusion list: market prices, inflation, exchange-rate valuation;
imports, exports, trade routes, tariffs, embargoes, stockpiles separate from deposits; pipelines,
refineries, individual mines/fields; ownership, private firms, royalties, concessions,
nationalization; environmental effects; military consumption or strategic reserves; exploration,
discovery, reserve reclassification; province/field-level geography; education/productivity
policy; approval/politics; diplomacy/military/war; any new API route, database table, or gameplay
frontend. Neither committed fixture ever reaches `LABOR_CONSTRAINED` for the extraction row —
labor stays abundant throughout both — a known, documented limitation, not a defect in the
classification logic (see the ADR for the synthetic test that exercises that branch directly).

# Phase 3A: Constitutional Foundation, Legitimacy and Political Capital

The first political layer: a nine-axis constitutional structure with validity rules (never a
legitimacy judgment), scenario-authored public acceptance of that structure, a legitimacy score
that drifts toward that acceptance and responds to this economy's own performance, and political
capital that regenerates from legitimacy. See
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md` for the full design
rationale and the R1-R8 independent-review corrections applied before implementation.

## Constitutional structure — validity, never legitimacy

`ConstitutionState` (`simulation/constitution.py`) has seven axes — `executive_system`
(`presidential`/`parliamentary`/`semi_presidential`/`monarchical`), `executive_selection`
(`direct_election`/`legislative_selection`/`hereditary`/`appointed`), `legislature`
(`none`/`unicameral`/`bicameral`), `territorial_organization` (`unitary`/`federal`),
`judicial_review` (`none`/`weak`/`strong`), `amendment_difficulty`
(`simple_majority`/`supermajority`/`entrenched`), `decree_authority`
(`none`/`emergency_only`/`unlimited`) — plus two optional scalars, `executive_term_limit_terms` and
`national_election_interval_turns` (`None` means genuinely absent, mirroring
`ResourceDepositState.stock_ceiling`'s established convention).

Nine validity rules (C1-C9) reject internally incoherent combinations only — a hereditary
executive that is also presidential, a parliamentary system with no legislature, a scheduled
national election with nothing to elect. They say nothing about whether a valid arrangement is
accepted, good, or stable; that is entirely the job of `constitutional_order_support_bps` and
`legitimacy_bps` below, which are independent of every C1-C9 rule. The full 10,368-configuration
space (2,592 axis combinations × term-limit presence × election-interval presence) is enumerated
and checked computationally: 2,862 valid, 7,506 rejected, every rule independently reachable as a
first violation.

`constitution_digest(constitution)` is a deterministic structural version marker (via
`core.canonical_json.canonical_digest` over the nine axis fields) — an amendment-tracking
identifier for later phases, carrying no legitimacy meaning of its own.

## Legitimacy — form-blind by signature, not by convention

`simulation/legitimacy.py` is pure and accepts **no constitutional type anywhere in its public
function signatures** — a `mypy`-checked guarantee that government form cannot reach the
legitimacy formula, stronger than any test. Two sources feed legitimacy each turn, and nothing
else does:

```
closing_legitimacy_bps = clamp(
    opening_legitimacy_bps + clamp(order_support_contribution_bps + performance_contribution_bps,
                                    ±MAX_TOTAL_LEGITIMACY_CHANGE_BPS),
    0, 10_000)
```

**Order-support drift** — a partial-adjustment model closing a fixed fraction of the gap between
current legitimacy and the scenario-authored `constitutional_order_support_bps` every turn:

```
order_support_contribution_bps = trunc_div_toward_zero(
    (constitutional_order_support_bps - opening_legitimacy_bps) * DRIFT_RATE_BPS, 10_000)
```

`DRIFT_RATE_BPS = 1,000` (10% of the gap per turn) is a single engine constant applied identically
to every government form — the neutrality guarantee in formula form: there is no per-form rate,
no per-axis modifier, no scoring table of any kind.

**Performance contribution** — the two signals this economy actually models, output and
unemployment, each independently sensitivity-weighted and capped:

```
output_change_bps        = 0 if baseline_output == 0 else
                            trunc_div_toward_zero((current_output - baseline_output) * 10_000,
                                                   baseline_output)
output_contribution_bps  = trunc_div_toward_zero(output_change_bps * OUTPUT_SENSITIVITY_BPS,
                                                  10_000)

unemployment_change_bps       = current_unemployment_bps - baseline_unemployment_bps
unemployment_contribution_bps = trunc_div_toward_zero(-unemployment_change_bps *
                                                        UNEMPLOYMENT_SENSITIVITY_BPS, 10_000)

performance_contribution_bps = clamp(output_contribution_bps + unemployment_contribution_bps,
                                      ±MAX_PERFORMANCE_CONTRIBUTION_BPS)
```

| Constant | Value | Meaning |
|---|---|---|
| `OUTPUT_SENSITIVITY_BPS` | 2,500 | a 1% output change moves legitimacy 0.25pp |
| `UNEMPLOYMENT_SENSITIVITY_BPS` | 5,000 | a 1pp unemployment rise costs 0.5pp — twice as sharp per point as output |
| `MAX_PERFORMANCE_CONTRIBUTION_BPS` | 300 | caps a single turn's performance swing at 3pp |
| `MAX_TOTAL_LEGITIMACY_CHANGE_BPS` | 500 | caps the combined per-turn swing at 5pp |
| `DRIFT_RATE_BPS` | 1,000 | 10% gap closure per turn |

**The zero-baseline case is handled by the caller, before any division**, not by the divisor
helper: `assess_economic_performance` tests `baseline_output == 0` and returns
`output_change_bps = 0` directly, since there is no proportional change to measure against
nothing. `trunc_div_toward_zero` itself **requires a positive denominator and raises otherwise** —
the one legitimate zero-denominator case is stated explicitly by its caller, never silently
absorbed. Truncation is toward zero, not floor: `deficit_demo` turn 41 gives `output_change_bps ==
-138`, not floor's `-139` — a hundredfold rebound illustrates why this matters:
`trunc(999,900,000/100) = 9,999` while `floor` on the negative-direction equivalent would round an
equal-magnitude loss one bps further away from zero, a systematic pessimism bias with no modeling
justification.

`output_change_bps`/`output_contribution_bps` are genuinely unbounded (a baseline of 1 rising to 3
is +20,000 bps) and carry `StrictSignedBps`, not the ±10,000-bounded `StrictSignedLegitimacyBps`
every other signed political field uses — see `docs/architecture.md`'s "Money and bounded values"
for the type distinction.

## The economic-baseline lifecycle — a turn-scoped observation record

`EconomicBaselineState` (`source_turn`, `total_gross_output`, `unemployment_rate_bps`) is written
by the political phase from that same turn's own already-validated `ProductionReport`/
`LaborMarketReport`, never scenario-authored. Four stages every turn: **read** the previous
closing baseline as this turn's opening (`None` only on the first resolved turn — never a
fabricated zero-output baseline); **assess** performance against it; **write** this turn's own
observations as the new closing baseline; **report** the whole chain into `PoliticalReport`. A
turn's closing baseline always has `source_turn == state.turn` (the turn *after* the one whose
economy it describes — `resolving_turn` in the resolver is the pre-resolution turn number, the
mutated state's own `turn` is post-resolution); the following turn's opening baseline is exactly
the previous turn's closing baseline, proven to hold across a 100-turn horizon by
`test_baseline_lifecycle.py`.

## Political capital

```
regeneration = POLITICAL_CAPITAL_BASE_REGENERATION
             + trunc_div_toward_zero(legitimacy_bps * LEGITIMACY_REGENERATION_COEFFICIENT, 10_000)
closing      = min(capacity, opening + regeneration - spent)
```

| Constant | Value | Meaning |
|---|---|---|
| `POLITICAL_CAPITAL_BASE_REGENERATION` | 200 | any functioning government recovers some capacity each turn regardless of standing |
| `LEGITIMACY_REGENERATION_COEFFICIENT` | 300 | at full legitimacy, regeneration is 500 — 2.5x the illegitimate-government floor |

Regeneration depends on legitimacy alone, never on government form: a legitimate monarchy and a
legitimate democracy at the same `legitimacy_bps` regenerate identically. `spent` is always 0 in
Phase 3A — nothing spends political capital yet, so it pins to `capacity` once regeneration
outpaces the gap (as `tiny_valid.yaml` does from turn 2 onward). The report still carries
`political_capital_spent` so the reconciliation identity shipped here is the one Phase 3B will use
unchanged.

## Worked example — the resource-depletion shock reaches legitimacy

No special-cased resource-to-legitimacy formula exists. Depletion reduces
`extraction_sector_real_output` (Phase 2C2) → the extraction row's `actual_output` →
`ProductionReport.total_gross_output` → the `current_output` term above — the same chain every
prior phase built, simply read by one more consumer. `deficit_demo.yaml` turn 26 (iron-ore
depletion, legitimacy at 6,459 after 25 turns of drift toward its authored 6,500 support):

```
opening baseline (turn 25)   total_gross_output 4,000,000,000   unemployment 1000
observations      (turn 26)  total_gross_output 3,600,000,000   unemployment 1000
output_change_bps              = trunc((-400,000,000 * 10,000) / 4,000,000,000) = -1,000  (-10.00%)
output_contribution_bps        = trunc(-1,000 * 2,500 / 10,000)                 =   -250
performance_contribution_bps   = clamp(-250, +-300)                             =   -250
order_support_contribution_bps = trunc((6,500 - 6,459) * 1,000 / 10,000)        =     +4
total_change                   = clamp(4 + (-250), +-500)                       =   -246
closing_legitimacy             = clamp(6,459 - 246, 0, 10,000)                  =  6,213
```

Turn 41 (timber's renewable steady state, the truncation case, legitimacy at 6,431):
`output_change_bps = trunc(-50,000,000 * 10,000 / 3,600,000,000) = -138` (not floor's `-139`),
`output_contribution_bps = -34`, `order_support_contribution_bps = +6`, total `-28`, closing
`6,403`. Both figures are reproduced exactly through the real resolver by
`test_political_economy_linkage.py`.

## Report design and self-validation

`PoliticalReport` carries ten independent `@model_validator(mode="after")` checks, each
re-deriving one equation from the report's own stored fields — never by calling
`simulation.legitimacy`'s functions, so a bug in one code path is caught by the other. `TurnReport`
gains `political: PoliticalReport | None`, three cross-validators matching
`current_total_gross_output`/`current_unemployment_rate_bps` against `production`/`labor_market`
by field identity (never tuple position) and the closing/opening baseline `source_turn`s against
`resolved_turn`, and the all-present-or-all-absent completeness rule extends from five reports (30
rejected subsets) to six (62).

`simulation/reconciliation.py`'s `reconcile_political_report` is the report-vs-*state* check
`TurnReport` itself cannot own (it has no `GameState` reference) — eleven check groups comparing
the political report against both the opening and closing state: opening/closing
legitimacy/political-capital, the opening/closing economic baseline, all nine constitutional
fields against both states independently (not just the digest — the report's summary fields and
digest are stored independently and could disagree with each other), the digest itself against
both states, authored `constitutional_order_support_bps`, and `political_capital_capacity`. A
nonempty result discards the turn atomically, exactly like an invariant violation.
`validate_history` re-runs the same reconciliation per history entry, which is what makes a
consistently re-hashed tamper (edit a value, recompute `entry_hash` to match) detectable — the
hash chain alone would miss it.

## Calibration

`tiny_valid.yaml` — parliamentary/legislative-selection/bicameral/unitary, strong judicial review,
`constitutional_order_support_bps = 8,000`, opening `legitimacy_bps = 7,000`, political capital
500/1,000. Flat economy means legitimacy moves by order-support drift alone: 7,000 → 7,100 (turn
1) → ... → 7,991 (turn 100), monotone, never overshooting; political capital clamps to its 1,000
capacity from turn 2 onward.

`deficit_demo.yaml` — presidential/direct-election/unicameral/unitary, weak judicial review,
`constitutional_order_support_bps = 6,500`, opening `legitimacy_bps = 6,000`, political capital
300/800. Reuses Phase 2C2's own iron-ore/timber depletion calibration: legitimacy dips exactly at
turns 26 and 41 (see the worked example above), closing at 6,491 by turn 100.

## Version compatibility (Phase 3A)

`RULESET_VERSION` bumps `0.7.0 -> 0.8.0`, `content_version` alongside it — schema-shape
compatibility, since `CountryState.politics` becomes required for the player. A Phase-2C2-ruleset
save fixture (`backend/tests/fixtures/phase2c2_save_ruleset_0.7.0.json`) was frozen with the
genuinely unmodified 0.7.0 engine before this bump landed. `SAVE_FORMAT_VERSION` is unchanged. No
fabricated migration: an older save has no constitution, no authored order support, no legitimacy
and no political capital, and none is invented — it is rejected outright by
`UnsupportedRulesetVersionError` before any entry payload is parsed.

## Explicitly not yet simulated (Phase 3A)

Political-capital expenditure (nothing spends it yet); parties, legislators, law passage;
elections, coups, removal from power; characters, appointments, institutional loyalty/power/
competence; courts deciding cases; repression, protests, uprisings, civil war; military; diplomacy;
AI-country politics (rejected outright — `non_player_politics_not_supported` — rather than silently
unmodeled, since only the player has an economy to derive performance from); `PopulationGroupState`/
`InstitutionState`'s float approval/trust/loyalty fields (unconverted, read by no formula);
`FinanceReport`/`TreasuryState` reconciliation (a real, pre-existing, unrelated gap, tracked
separately); any new API route, database table, or gameplay frontend.

**Phase 3B1 has since closed the first two of those** — see the next section.

---

# Phase 3B1: Legislative Gating of the Budget

Phase 3B1 is not an economic phase, and it adds no economic formula. It is included here for one
reason: **it decides whether the budget this document's entire chain is computed against is the one
the player submitted.** Full mechanism, calibration and rationale live in
`docs/adr/0010-legislature-parties-and-political-capital-bargaining.md`; only the economic
consequence is described here.

## Where the gate sits in the chain

A `BudgetDecision` is a **proposal**. Before Phase 3B1 it was applied unconditionally at slot 2.
Now slot 1 resolves it against the legislature (or the constitution's decree authority) first, and
slot 2 commits the proposed `TaxPolicyState`/`SpendingPlanState` **only** when the outcome is
`PASSED_LEGISLATIVE` or `ENACTED_BY_DECREE`:

```
proposal -> [slot 1: vote or decree] -> outcome
                                          |
              passed / enacted ---------->+--> proposed tax policy + spending plan committed
              failed / no proposal ------>+--> OPENING policy preserved byte-for-byte
                                          |
                                          v
   tax bases (derived from production, unchanged by this phase)
        x committed tax rates  ->  revenue  ->  balance  ->  cash/debt
```

Everything downstream of "committed tax rates" is exactly as documented earlier in this file. The
gate changes *which* rates enter that multiplication, never how the multiplication works. A failed
vote is therefore not a no-op with a different label: revenue, the pre-financing balance, borrowing
and closing cash/debt all follow the *unchanged* budget, and the two trajectories genuinely diverge
from that turn onward.

## The no-decision path is unchanged, by requirement

With **no** `BudgetDecision` the outcome is `NO_PROPOSAL`, zero capital is committed, and slot 2
behaves exactly as it did before Phase 3B1. This is what makes the phase additive rather than a
recalibration: every committed Phase 2A–2C2 figure in this document — `tiny_valid`'s flat 100-turn
trajectory, `deficit_demo`'s turn-26/turn-41 depletion boundaries, every soak bound — is produced
on that path and is unaffected. It is a hard requirement with its own test, not an observation.

## Political capital is spent, so slot 10's identity finally has a nonzero term

Phase 3A's `political_capital_spent` was hardcoded to 0. It is now the capital the player committed
at slot 1, and the identity is otherwise unchanged:

```
closing_political_capital = min(capacity, opening - committed + regeneration)
```

with `committed <= opening` enforced at slot 1 (never against this turn's regeneration, which is
derived from *closing* legitimacy and is not knowable when the commitment is made). **A failed vote
still consumes its committed capital** — the commitment is a bid, not an escrow.

One consequence is documented rather than hidden: because regeneration is applied in the same
identity, a government at or near capacity may have part or all of a commitment refunded within the
same turn. The exact cost has three branches — full face value when `opening + regeneration <=
capacity`, zero when `opening - committed + regeneration >= capacity`, and strictly between
otherwise — all three pinned by tests. ADR 0010 states the consequence plainly and **retracts** the
stronger claim that every route always carries a lasting opportunity cost.

## Legislative calibration

Every figure is derived from the scenario files themselves through the real voting and
apportionment modules, never hardcoded. The walkthrough proposal is **+5 percentage points on the
personal income rate, spending unchanged**, measured from each scenario's own authored opening rate.

`tiny_valid.yaml` — bicameral, majority coalition. Lower **58/100** against a required 51; upper
**33/60** against a required 31. **Passes unaided**, committing 0 capital, which is why every
pre-3B1 `tiny_valid` figure in this document is reproduced exactly when the walkthrough budget is
submitted.

`deficit_demo.yaml` — unicameral minority government, opening rate 15%. **47/100** against a
required 51: the budget **fails** unaided, four seats short, and the tax rise does not happen. The
cheapest bargain that carries it is **162** political capital on `citizens_bloc/moderates` → 51/100
— affordable against its opening 300, and cheaper than a decree would be, which is the point.

`decree_state.yaml` (new) — monarchical/hereditary/unicameral with **unlimited** decree authority,
opening rate 20%, political capital 500/1,000. **282** capital fails at 50/100; **283** passes at
51/100; a decree enacts the identical budget for **250** and produces no chamber rows at all. Both
routes reach byte-identical tax policy and spending plan from an identical opening state, differing
only in route, report structure and capital committed.

The ordering `0 < 162 < 250 < 283` is established by an exhaustive dynamic program over each bloc's
full marginal support curve — exact, not sampled.

## Version compatibility (Phase 3B1)

`RULESET_VERSION` bumps `0.8.0 -> 0.9.0`, `content_version` alongside it. A genuine 0.8.0 save
fixture (`backend/tests/fixtures/phase3a_save_ruleset_0.8.0.json`) was frozen with the unmodified
0.8.0 engine **before** any model or constant change and is rejected by
`UnsupportedRulesetVersionError` before any entry payload is parsed. `SAVE_FORMAT_VERSION` is
unchanged. **No fabricated migration**: an older save has no chambers, parties, blocs or seats, and
none may be invented — composition is authored content, not something an engine can guess.

## Explicitly not yet simulated (Phase 3B1)

Legislature composition is **static** — no relationship evolution, realignment, defections,
confidence votes or coalition collapse. The **budget is the only proposal kind**, so there are no
general laws. There are no competing political-capital uses within a turn, which is why the
opportunity cost above is notional at capacity. `EMERGENCY_ONLY` decree authority confers no decree
power (no emergency system exists to read). Elections, coups and removal from power remain Phase
3C, as do courts, judicial review and any consequence for habitual decree use.
