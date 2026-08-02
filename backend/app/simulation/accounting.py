"""Pure Phase 2A government accounting formulas.

No I/O, no randomness, no state mutation — plain functions of their
arguments, callable independently of the phase pipeline (and directly by
tests). `phases.py` calls these to compute the numbers it stores on
`FinanceReport`; `FinanceReport` itself independently re-derives and checks
these same formulas from its own stored fields on construction (see
`report.py`) rather than trusting whatever `phases.py` handed it — the two
are deliberately not the same code path, so a bug in one is likely to be
caught by the other.

## Formulas (all integer, all floored — see `core.money` for the rounding
policy and why `apply_bps`/`apply_quarterly_bps` floor rather than round)

Per tax category::

    gross_tax      = floor(tax_base * rate_bps / 10_000)
    collected_tax  = floor(gross_tax * compliance_rate_bps / 10_000)

Then::

    total_revenue           = personal_income_tax + corporate_tax + consumption_tax
    total_program_spending  = health + education + welfare + infrastructure
                             + defense + security + administration
    quarterly_interest      = floor(opening_debt * annual_rate_bps / 40_000)
    pre_financing_balance   = total_revenue - total_program_spending - quarterly_interest
    cash_before_financing   = opening_cash + pre_financing_balance
    new_borrowing           = max(0, -cash_before_financing)
    closing_cash            = max(0, cash_before_financing)
    closing_debt            = opening_debt + new_borrowing

A surplus (`pre_financing_balance >= -opening_cash`) increases treasury cash
and never touches debt. A deficit first consumes available cash; only once
cash would go negative does the shortfall become new borrowing — cash never
goes negative, and no debt is *repaid* automatically even when there's a
large surplus (that stays scenario-authored/player-decided going forward,
not modeled in Phase 2A). See `docs/economy_methodology.md` for the full
worked derivation of why both reconciliation equations below hold exactly
for every input, not just the common cases.

## Reconciliation (must hold exactly, in integer minor units, for every input)

    opening_cash + total_revenue + new_borrowing
        == closing_cash + total_program_spending + quarterly_interest

    closing_public_debt == opening_public_debt + new_borrowing
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import Money, apply_bps, apply_quarterly_bps
from app.simulation.state import SpendingPlanState, TaxBaseState, TaxPolicyState


@dataclass(frozen=True, slots=True)
class TaxRevenueBreakdown:
    """Collected revenue per category, plus their total."""

    personal_income_tax: Money
    corporate_tax: Money
    consumption_tax: Money

    @property
    def total_revenue(self) -> Money:
        return self.personal_income_tax + self.corporate_tax + self.consumption_tax


def compute_tax_revenue(tax_bases: TaxBaseState, tax_policy: TaxPolicyState) -> TaxRevenueBreakdown:
    """Per-category `collected = floor(floor(base * rate_bps / 10_000) * compliance_bps / 10_000)`."""

    def _collected(base: Money, rate_bps: int) -> Money:
        gross = apply_bps(base, rate_bps)
        return apply_bps(gross, tax_policy.compliance_rate_bps)

    return TaxRevenueBreakdown(
        personal_income_tax=_collected(
            tax_bases.personal_income, tax_policy.personal_income_rate_bps
        ),
        corporate_tax=_collected(tax_bases.corporate_profit, tax_policy.corporate_rate_bps),
        consumption_tax=_collected(tax_bases.taxable_consumption, tax_policy.consumption_rate_bps),
    )


def compute_quarterly_interest(opening_debt: Money, annual_rate_bps: int) -> Money:
    """`floor(opening_debt * annual_rate_bps / 40_000)` — interest on *opening* debt only, so
    debt newly issued this quarter (via `new_borrowing`) is interest-free until next quarter.
    """
    return apply_quarterly_bps(opening_debt, annual_rate_bps)


@dataclass(frozen=True, slots=True)
class CashDebtResolution:
    """The result of resolving one quarter's cash flow against opening cash and debt."""

    pre_financing_balance: int
    """Signed: `total_revenue - total_program_spending - quarterly_interest`."""
    new_borrowing: Money
    closing_cash: Money
    closing_debt: Money


def resolve_cash_and_debt(
    *,
    opening_cash: Money,
    opening_debt: Money,
    total_revenue: Money,
    total_program_spending: Money,
    quarterly_interest: Money,
) -> CashDebtResolution:
    """Apply one quarter's revenue/spending/interest to opening cash and debt.

    A deficit consumes available cash first; borrowing covers only the
    remaining shortfall exactly (`new_borrowing = max(0, -cash_before_financing)`),
    and `closing_cash = max(0, cash_before_financing)` never goes negative. A
    surplus is retained as cash — debt is never automatically repaid.
    """
    pre_financing_balance = total_revenue - total_program_spending - quarterly_interest
    cash_before_financing = opening_cash + pre_financing_balance
    new_borrowing = max(0, -cash_before_financing)
    closing_cash = max(0, cash_before_financing)
    closing_debt = opening_debt + new_borrowing

    return CashDebtResolution(
        pre_financing_balance=pre_financing_balance,
        new_borrowing=new_borrowing,
        closing_cash=closing_cash,
        closing_debt=closing_debt,
    )


def compute_total_program_spending(spending_plan: SpendingPlanState) -> Money:
    return spending_plan.total()
