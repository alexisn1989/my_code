from __future__ import annotations

from app.simulation.state import TaxBaseCoefficients
from app.simulation.tax_base_derivation import (
    aggregate_tax_base_contributions,
    compute_sector_tax_base_contribution,
)


def _coefficients(
    *,
    personal_taxable_share_bps: int = 8_000,
    corporate_taxable_share_bps: int = 4_000,
    effective_consumption_base_share_bps: int = 3_000,
) -> TaxBaseCoefficients:
    return TaxBaseCoefficients(
        personal_taxable_share_bps=personal_taxable_share_bps,
        corporate_taxable_share_bps=corporate_taxable_share_bps,
        effective_consumption_base_share_bps=effective_consumption_base_share_bps,
    )


class TestComputeSectorTaxBaseContribution:
    def test_ordinary_values_exact(self) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=2_000_000_000,
            value_added_share_bps=5_000,
            labor_income_share_bps=5_000,
            coefficients=_coefficients(),
        )
        assert result.modeled_value_added == 1_000_000_000
        assert result.labor_income == 500_000_000
        assert result.operating_surplus == 500_000_000
        assert result.personal_contribution == 400_000_000  # 500M * 0.8
        assert result.corporate_contribution == 200_000_000  # 500M * 0.4
        assert result.consumption_contribution == 300_000_000  # 1B * 0.3

    def test_labor_income_plus_operating_surplus_equals_modeled_value_added_exactly(self) -> None:
        # A non-round case chosen so intermediate floors are non-trivial.
        result = compute_sector_tax_base_contribution(
            actual_output=999_999,
            value_added_share_bps=3_333,
            labor_income_share_bps=6_667,
            coefficients=_coefficients(),
        )
        assert result.labor_income + result.operating_surplus == result.modeled_value_added

    def test_zero_actual_output_yields_all_zeros(self) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=0,
            value_added_share_bps=5_000,
            labor_income_share_bps=5_000,
            coefficients=_coefficients(),
        )
        assert result.modeled_value_added == 0
        assert result.labor_income == 0
        assert result.operating_surplus == 0
        assert result.personal_contribution == 0
        assert result.corporate_contribution == 0
        assert result.consumption_contribution == 0

    def test_zero_value_added_share_yields_all_zeros_regardless_of_output(self) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=10**12,
            value_added_share_bps=0,
            labor_income_share_bps=5_000,
            coefficients=_coefficients(),
        )
        assert result.modeled_value_added == 0
        assert result.labor_income == 0
        assert result.operating_surplus == 0

    def test_zero_coefficients_yield_zero_contributions_even_with_nonzero_value_added(
        self,
    ) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=1_000_000,
            value_added_share_bps=10_000,
            labor_income_share_bps=5_000,
            coefficients=_coefficients(
                personal_taxable_share_bps=0,
                corporate_taxable_share_bps=0,
                effective_consumption_base_share_bps=0,
            ),
        )
        assert result.modeled_value_added == 1_000_000
        assert result.personal_contribution == 0
        assert result.corporate_contribution == 0
        assert result.consumption_contribution == 0

    def test_hundred_percent_shares_yield_full_pass_through(self) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=1_000_000,
            value_added_share_bps=10_000,
            labor_income_share_bps=10_000,
            coefficients=_coefficients(
                personal_taxable_share_bps=10_000,
                corporate_taxable_share_bps=10_000,
                effective_consumption_base_share_bps=10_000,
            ),
        )
        assert result.modeled_value_added == 1_000_000
        assert result.labor_income == 1_000_000
        assert result.operating_surplus == 0
        assert result.personal_contribution == 1_000_000
        assert result.corporate_contribution == 0  # operating_surplus is 0
        assert result.consumption_contribution == 1_000_000

    def test_floors_rather_than_rounds_at_a_rounding_boundary(self) -> None:
        # actual_output=3, share=3333 bps -> 3*3333/10000 = 0.9999 -> floors to 0.
        result = compute_sector_tax_base_contribution(
            actual_output=3,
            value_added_share_bps=3_333,
            labor_income_share_bps=5_000,
            coefficients=_coefficients(),
        )
        assert result.modeled_value_added == 0

    def test_no_float_ever_appears_in_the_result(self) -> None:
        result = compute_sector_tax_base_contribution(
            actual_output=1_234_567,
            value_added_share_bps=3_333,
            labor_income_share_bps=6_667,
            coefficients=_coefficients(),
        )
        for field in (
            result.modeled_value_added,
            result.labor_income,
            result.operating_surplus,
            result.personal_contribution,
            result.corporate_contribution,
            result.consumption_contribution,
        ):
            assert isinstance(field, int)
            assert not isinstance(field, float)


class TestAggregateTaxBaseContributions:
    def test_sums_per_sector_contributions_and_converts_to_money(self) -> None:
        coefficients = _coefficients()
        results = tuple(
            compute_sector_tax_base_contribution(
                actual_output=out,
                value_added_share_bps=5_000,
                labor_income_share_bps=5_000,
                coefficients=coefficients,
            )
            for out in (2_000_000_000, 2_000_000_000, 4_000_000_000)
        )
        aggregates = aggregate_tax_base_contributions(results)

        assert aggregates.total_modeled_value_added == sum(r.modeled_value_added for r in results)
        assert aggregates.total_labor_income == sum(r.labor_income for r in results)
        assert aggregates.total_operating_surplus == sum(r.operating_surplus for r in results)
        assert aggregates.derived_tax_bases.personal_income == sum(
            r.personal_contribution for r in results
        )
        assert aggregates.derived_tax_bases.corporate_profit == sum(
            r.corporate_contribution for r in results
        )
        assert aggregates.derived_tax_bases.taxable_consumption == sum(
            r.consumption_contribution for r in results
        )

    def test_empty_results_yield_zero_totals(self) -> None:
        aggregates = aggregate_tax_base_contributions(())
        assert aggregates.total_modeled_value_added == 0
        assert aggregates.total_labor_income == 0
        assert aggregates.total_operating_surplus == 0
        assert aggregates.derived_tax_bases.personal_income == 0
        assert aggregates.derived_tax_bases.corporate_profit == 0
        assert aggregates.derived_tax_bases.taxable_consumption == 0

    def test_sum_of_per_sector_floors_can_differ_from_a_national_recompute(self) -> None:
        """D6: national bases are defined as the SUM of per-sector floored contributions,
        not a value recomputed from national aggregates — because
        `sum(floor(xi * r)) <= floor(sum(xi) * r)` in general. This test proves the two
        approaches genuinely diverge for a hand-picked case, so "sum of parts" is a real
        design decision, not an arbitrary implementation detail with no observable effect.
        """
        coefficients = _coefficients(
            personal_taxable_share_bps=3_333,
            corporate_taxable_share_bps=10_000,
            effective_consumption_base_share_bps=10_000,
        )
        # Three sectors whose individual labor_income floors to a value that, summed,
        # differs from flooring the summed labor_income directly.
        results = tuple(
            compute_sector_tax_base_contribution(
                actual_output=3,
                value_added_share_bps=10_000,
                labor_income_share_bps=10_000,
                coefficients=coefficients,
            )
            for _ in range(3)
        )
        aggregates = aggregate_tax_base_contributions(results)

        # Per-sector: labor_income=3, personal_contribution=floor(3*3333/10000)=0 each -> sum=0.
        sum_of_parts = aggregates.derived_tax_bases.personal_income
        # A national recompute would instead floor the summed labor income (9) directly:
        national_recompute = (9 * 3_333) // 10_000  # == 2
        assert sum_of_parts == 0
        assert national_recompute == 2
        assert sum_of_parts != national_recompute
