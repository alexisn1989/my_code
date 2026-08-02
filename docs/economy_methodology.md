# MANDATE — Economy Methodology (Phase 2A + 2B1)

Scope of this document: the government-finance slice implemented in Phase 2A (tax revenue,
spending, quarterly debt interest, deficit financing) and the sector-production slice implemented
in Phase 2B1 (aggregate sector capacity, labor productivity, employment, deterministic quarterly
output at fixed base-year prices). Nothing else in §13 of the product spec (tax-base derivation,
prices, inflation, wages, central banking, exchange rates) is implemented yet; see "Explicitly not
yet simulated" below.

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
applied to anything. Every nested Pydantic sub-model is captured via `.model_copy()`, not a bare
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

## Employment boundary — deliberately static this phase

`employed_workers` is fixed scenario/decision input. Phase 2B1 does **not** implement wage
formation, an unemployment rate, labor-force participation, hiring/layoffs, worker movement,
population-group occupations, immigration, strikes, or tax-driven employment changes. The one
cross-field check that does exist — `sector_employment_exceeds_population`
(`simulation.invariants`) — only guards against `sum(employed_workers) > population`; it is not a
labor-force model.

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

## Interaction with Phase 2A accounting — full isolation, both directions

`resolve_production_and_trade` runs **before** the finance phases in `PHASE_ORDER`, so
`ctx.production_report` is already populated by the time they execute — a real risk, since nothing
in the type system stops a finance phase from reaching across the shared `PhaseContext` and reading
it. Phase 2B1 keeps the two systems fully isolated in both directions: production reads only
`economy`, never `finance`/`treasury`; finance reads only its own opening snapshot and the
decision, never `production_report`/`economy`. `tests/test_phase_isolation.py` actively tests this
(not just documents it): a `FinanceReport` produced against wildly different `EconomyState` fixtures
is byte-identical, and vice versa for `ProductionReport` against different finance/budget states.
Tax bases, spending, treasury, and debt behave **exactly as Phase 2A implemented them** — sector
output does not change tax revenue, spending does not change sector capacity, infrastructure
spending does not improve production, defense spending does not improve defense-industry output,
and there is no "higher taxes → lower output" rule (that connection, if it ever exists, is
Phase 2B2+ territory).

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

## Explicitly not yet simulated

Not yet modeled at all, in either Phase 2A or Phase 2B1: tax-base derivation from production,
GDP/value-added/real-growth figures, prices, shortages, inflation, wages, employment/unemployment
dynamics, labor-force participation, hiring/layoffs, household consumption response, central
banking, exchange rates, trade, population approval effects, service-quality outcomes, corruption.
All of it stays honestly absent rather than faked — see the product spec's "no placeholder feature
claims" rule (§5.7).
