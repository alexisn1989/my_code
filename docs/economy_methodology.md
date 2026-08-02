# MANDATE — Economy Methodology (Phase 2A: Government Accounting)

Scope of this document: the government-finance slice implemented in Phase 2A —
tax revenue, spending, quarterly debt interest, and deficit financing. Nothing else in §13 of the
product spec (production sectors, prices, inflation, employment, wages, central banking, exchange
rates) is implemented yet; see "Explicitly not yet simulated" below.

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

## Explicitly not yet simulated

Changing a tax rate does **not** move the tax base it applies to — `TaxBaseState` is fixed,
scenario-authored data for the whole of Phase 2A. Not yet modeled at all: production sectors, GDP
growth, prices, shortages, inflation, wages, employment/unemployment, household consumption
response, central banking, exchange rates, population approval effects, service-quality outcomes,
corruption. All of it stays honestly absent rather than faked — see the product spec's "no
placeholder feature claims" rule (§5.7).
