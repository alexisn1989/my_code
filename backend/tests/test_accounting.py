from __future__ import annotations

import pytest

from app.simulation.accounting import (
    compute_quarterly_interest,
    compute_tax_revenue,
    compute_total_program_spending,
    resolve_cash_and_debt,
)
from app.simulation.state import SpendingCategory, SpendingPlanState, TaxBaseState, TaxPolicyState


def _bases(
    personal: int = 1_000_000, corporate: int = 1_000_000, consumption: int = 1_000_000
) -> TaxBaseState:
    return TaxBaseState(
        personal_income=personal, corporate_profit=corporate, taxable_consumption=consumption
    )


def _policy(
    personal_bps: int = 2_000,
    corporate_bps: int = 2_500,
    consumption_bps: int = 1_000,
    compliance_bps: int = 9_000,
) -> TaxPolicyState:
    return TaxPolicyState(
        personal_income_rate_bps=personal_bps,
        corporate_rate_bps=corporate_bps,
        consumption_rate_bps=consumption_bps,
        compliance_rate_bps=compliance_bps,
    )


class TestComputeTaxRevenue:
    def test_zero_rate_yields_zero_revenue(self) -> None:
        breakdown = compute_tax_revenue(_bases(), _policy(personal_bps=0))
        assert breakdown.personal_income_tax == 0

    def test_hundred_percent_rate_and_compliance_yields_full_base(self) -> None:
        breakdown = compute_tax_revenue(
            _bases(personal=500_000), _policy(personal_bps=10_000, compliance_bps=10_000)
        )
        assert breakdown.personal_income_tax == 500_000

    def test_zero_compliance_yields_zero_revenue_regardless_of_rate(self) -> None:
        breakdown = compute_tax_revenue(
            _bases(personal=500_000), _policy(personal_bps=10_000, compliance_bps=0)
        )
        assert breakdown.personal_income_tax == 0

    def test_ordinary_rate_exact_value(self) -> None:
        # base=1,000,000; 20% rate -> gross 200,000; 90% compliance -> 180,000.
        breakdown = compute_tax_revenue(
            _bases(personal=1_000_000), _policy(personal_bps=2_000, compliance_bps=9_000)
        )
        assert breakdown.personal_income_tax == 180_000

    def test_each_category_computed_independently(self) -> None:
        breakdown = compute_tax_revenue(
            _bases(personal=1_000_000, corporate=2_000_000, consumption=3_000_000),
            _policy(
                personal_bps=1_000, corporate_bps=2_000, consumption_bps=500, compliance_bps=10_000
            ),
        )
        assert breakdown.personal_income_tax == 100_000
        assert breakdown.corporate_tax == 400_000
        assert breakdown.consumption_tax == 150_000

    def test_total_revenue_is_sum_of_categories(self) -> None:
        breakdown = compute_tax_revenue(
            _bases(personal=1_000_000, corporate=2_000_000, consumption=3_000_000),
            _policy(
                personal_bps=1_000, corporate_bps=2_000, consumption_bps=500, compliance_bps=10_000
            ),
        )
        assert breakdown.total_revenue == 100_000 + 400_000 + 150_000

    def test_a_rate_change_affects_only_its_own_category(self) -> None:
        baseline = compute_tax_revenue(_bases(), _policy())
        changed = compute_tax_revenue(_bases(), _policy(personal_bps=5_000))

        assert changed.personal_income_tax != baseline.personal_income_tax
        assert changed.corporate_tax == baseline.corporate_tax
        assert changed.consumption_tax == baseline.consumption_tax

    def test_large_values(self) -> None:
        breakdown = compute_tax_revenue(
            _bases(personal=10**12), _policy(personal_bps=3_333, compliance_bps=8_765)
        )
        expected = (10**12 * 3_333 // 10_000) * 8_765 // 10_000
        assert breakdown.personal_income_tax == expected

    def test_no_float_ever_appears_in_the_result(self) -> None:
        breakdown = compute_tax_revenue(_bases(), _policy())
        assert isinstance(breakdown.personal_income_tax, int)
        assert isinstance(breakdown.corporate_tax, int)
        assert isinstance(breakdown.consumption_tax, int)
        assert isinstance(breakdown.total_revenue, int)


class TestComputeQuarterlyInterest:
    def test_zero_debt_yields_zero_interest(self) -> None:
        assert compute_quarterly_interest(0, 600) == 0

    def test_zero_rate_yields_zero_interest(self) -> None:
        assert compute_quarterly_interest(1_000_000, 0) == 0

    def test_exact_value(self) -> None:
        # 5,000,000,000 debt at 6% annual -> 6% * 5e9 = 300,000,000 annual;
        # one quarter = 75,000,000.
        assert compute_quarterly_interest(5_000_000_000, 600) == 75_000_000


class TestComputeTotalProgramSpending:
    def test_sums_all_seven_categories(self) -> None:
        plan = SpendingPlanState(
            health=1,
            education=2,
            welfare=3,
            infrastructure=4,
            defense=5,
            security=6,
            administration=7,
        )
        assert compute_total_program_spending(plan) == 28

    def test_a_spending_change_affects_only_its_own_category_total(self) -> None:
        base_plan = SpendingPlanState(
            health=100,
            education=100,
            welfare=100,
            infrastructure=100,
            defense=100,
            security=100,
            administration=100,
        )
        changed_plan = base_plan.with_update(SpendingCategory.HEALTH, 500)

        assert changed_plan.health == 500
        assert changed_plan.education == base_plan.education
        assert compute_total_program_spending(changed_plan) == compute_total_program_spending(
            base_plan
        ) + (500 - 100)


class TestResolveCashAndDebt:
    def test_surplus_increases_cash_and_does_not_touch_debt(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=1_000_000,
            opening_debt=500_000,
            total_revenue=800_000,
            total_program_spending=500_000,
            quarterly_interest=50_000,
        )
        assert result.pre_financing_balance == 250_000
        assert result.new_borrowing == 0
        assert result.closing_cash == 1_250_000
        assert result.closing_debt == 500_000

    def test_deficit_first_consumes_available_cash_without_borrowing(self) -> None:
        # Deficit of 100,000 but opening cash of 500,000 comfortably covers it.
        result = resolve_cash_and_debt(
            opening_cash=500_000,
            opening_debt=1_000_000,
            total_revenue=200_000,
            total_program_spending=250_000,
            quarterly_interest=50_000,
        )
        assert result.pre_financing_balance == -100_000
        assert result.new_borrowing == 0
        assert result.closing_cash == 400_000
        assert result.closing_debt == 1_000_000

    def test_borrowing_occurs_only_once_cash_is_exhausted(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=100_000,
            opening_debt=1_000_000,
            total_revenue=200_000,
            total_program_spending=500_000,
            quarterly_interest=50_000,
        )
        # deficit = 350,000; cash covers 100,000; shortfall = 250,000.
        assert result.pre_financing_balance == -350_000
        assert result.new_borrowing == 250_000
        assert result.closing_cash == 0

    def test_borrowing_equals_the_remaining_shortfall_exactly(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=1,
            opening_debt=0,
            total_revenue=0,
            total_program_spending=999_999,
            quarterly_interest=0,
        )
        assert result.new_borrowing == 999_998
        assert result.closing_cash == 0

    def test_debt_increases_by_new_borrowing_exactly(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=0,
            opening_debt=1_000_000,
            total_revenue=0,
            total_program_spending=300_000,
            quarterly_interest=0,
        )
        assert result.closing_debt == 1_000_000 + result.new_borrowing

    def test_surplus_does_not_automatically_repay_debt(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=0,
            opening_debt=1_000_000,
            total_revenue=10_000_000,
            total_program_spending=0,
            quarterly_interest=0,
        )
        assert result.closing_debt == 1_000_000  # unchanged despite a huge surplus
        assert result.closing_cash == 10_000_000

    def test_closing_cash_never_becomes_negative(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=0,
            opening_debt=0,
            total_revenue=0,
            total_program_spending=10**9,
            quarterly_interest=10**9,
        )
        assert result.closing_cash == 0
        assert result.closing_cash >= 0

    def test_exact_break_even_borrows_nothing_and_zeroes_cash(self) -> None:
        result = resolve_cash_and_debt(
            opening_cash=100_000,
            opening_debt=0,
            total_revenue=0,
            total_program_spending=100_000,
            quarterly_interest=0,
        )
        assert result.new_borrowing == 0
        assert result.closing_cash == 0


class TestReconciliationHoldsExactly:
    """`resolve_cash_and_debt` + revenue/spending totals must always satisfy the two
    reconciliation equations from `docs/economy_methodology.md`, for every case above
    and a battery of additional pseudo-random ones."""

    @staticmethod
    def _assert_reconciles(
        *,
        opening_cash: int,
        opening_debt: int,
        total_revenue: int,
        total_program_spending: int,
        quarterly_interest: int,
    ) -> None:
        result = resolve_cash_and_debt(
            opening_cash=opening_cash,
            opening_debt=opening_debt,
            total_revenue=total_revenue,
            total_program_spending=total_program_spending,
            quarterly_interest=quarterly_interest,
        )
        # opening_cash + total_revenue + new_borrowing
        #   == closing_cash + total_program_spending + quarterly_interest
        lhs = opening_cash + total_revenue + result.new_borrowing
        rhs = result.closing_cash + total_program_spending + quarterly_interest
        assert lhs == rhs

        # closing_public_debt == opening_public_debt + new_borrowing
        assert result.closing_debt == opening_debt + result.new_borrowing

    @pytest.mark.parametrize(
        ("opening_cash", "opening_debt", "revenue", "spending", "interest"),
        [
            (0, 0, 0, 0, 0),
            (1_000_000, 500_000, 800_000, 500_000, 50_000),  # surplus
            (500_000, 1_000_000, 200_000, 250_000, 50_000),  # small deficit, cash covers
            (100_000, 1_000_000, 200_000, 500_000, 50_000),  # deficit requiring borrowing
            (0, 0, 0, 999_999, 0),  # pure deficit from zero
            (10**12, 0, 0, 0, 0),  # huge opening cash, no activity
            (1, 2, 3, 4, 5),  # small arbitrary values
            (10**9, 10**9, 10**9, 10**9, 10**9),  # everything equal and large
        ],
    )
    def test_reconciles_for_representative_cases(
        self, opening_cash: int, opening_debt: int, revenue: int, spending: int, interest: int
    ) -> None:
        self._assert_reconciles(
            opening_cash=opening_cash,
            opening_debt=opening_debt,
            total_revenue=revenue,
            total_program_spending=spending,
            quarterly_interest=interest,
        )

    def test_reconciles_across_a_random_search(self) -> None:
        import random

        rng = random.Random(20260802)  # local, test-only randomness — not simulation code
        for _ in range(2_000):
            self._assert_reconciles(
                opening_cash=rng.randint(0, 10**10),
                opening_debt=rng.randint(0, 10**10),
                total_revenue=rng.randint(0, 10**9),
                total_program_spending=rng.randint(0, 10**9),
                quarterly_interest=rng.randint(0, 10**8),
            )
