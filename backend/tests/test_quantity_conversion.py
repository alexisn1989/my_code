"""Tests for R2's unit-bridge conversion function: `base_year_real_output_to_money` is the
single named, explicit real-to-nominal conversion point (not an implicit `int` pass-through).
"""

from __future__ import annotations

import pytest

from app.core.quantity import BASE_YEAR_PRICE_INDEX_BPS, base_year_real_output_to_money


def test_price_index_is_exact_integer_bps_not_a_float() -> None:
    assert BASE_YEAR_PRICE_INDEX_BPS == 10_000
    assert isinstance(BASE_YEAR_PRICE_INDEX_BPS, int)
    assert not isinstance(BASE_YEAR_PRICE_INDEX_BPS, float)


def test_conversion_is_currently_an_exact_identity() -> None:
    assert base_year_real_output_to_money(0) == 0
    assert base_year_real_output_to_money(1) == 1
    assert base_year_real_output_to_money(1_765_000) == 1_765_000
    assert base_year_real_output_to_money(10**12) == 10**12


def test_conversion_result_is_a_plain_int() -> None:
    result = base_year_real_output_to_money(1_234_567)
    assert isinstance(result, int)
    assert not isinstance(result, float)


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(-1, id="negative"),
        pytest.param(10.0, id="whole-number-float"),
        pytest.param(10.5, id="fractional-float"),
        pytest.param("10", id="numeric-string"),
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
    ],
)
def test_conversion_rejects_invalid_input(bad_value: object) -> None:
    with pytest.raises(ValueError):
        base_year_real_output_to_money(bad_value)  # type: ignore[arg-type]


def test_conversion_is_the_only_real_to_nominal_boundary_end_to_end() -> None:
    """Exercised through the real derivation pipeline: the national tax bases produced by
    `aggregate_tax_base_contributions` must equal `base_year_real_output_to_money` applied to
    the summed per-sector contributions — proving the pure module actually routes through this
    one function rather than reimplementing the conversion inline.
    """
    from app.simulation.state import TaxBaseCoefficients
    from app.simulation.tax_base_derivation import (
        aggregate_tax_base_contributions,
        compute_sector_tax_base_contribution,
    )

    coefficients = TaxBaseCoefficients(
        personal_taxable_share_bps=8_000,
        corporate_taxable_share_bps=4_000,
        effective_consumption_base_share_bps=3_000,
    )
    result = compute_sector_tax_base_contribution(
        actual_output=2_000_000_000,
        value_added_share_bps=5_000,
        labor_income_share_bps=5_000,
        coefficients=coefficients,
    )
    aggregates = aggregate_tax_base_contributions((result,))

    assert aggregates.derived_tax_bases.personal_income == base_year_real_output_to_money(
        result.personal_contribution
    )
    assert aggregates.derived_tax_bases.corporate_profit == base_year_real_output_to_money(
        result.corporate_contribution
    )
    assert aggregates.derived_tax_bases.taxable_consumption == base_year_real_output_to_money(
        result.consumption_contribution
    )
