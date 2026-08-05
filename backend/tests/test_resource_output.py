"""Tests for the pure Phase 2C2 formulas in `simulation.resource_output` (T1-T10, R6).

Covers: exact bridge conversion for all 8 resources including boundary magnitudes (T1),
no-rounding/no-division claim (T2), canonical ordering / mapping-permutation resistance (T3),
coefficient-map validation (T4), zero-labor vs. zero-capacity distinction between actual and
potential (T5/T6), mixed-resource aggregation (T9), and a property-based test proving
`actual_total <= potential_total` and the zero-extraction biconditional hold for arbitrary inputs
(T10).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.simulation.resource_extraction import DepositExtractionResult, DepositStatus
from app.simulation.resource_output import (
    ResourceOutputContribution,
    aggregate_extraction_sector_output,
    compute_resource_output_contributions,
)
from app.simulation.state import ResourceCategory

_CATEGORIES = tuple(ResourceCategory)


def _extraction_result(
    *,
    category: ResourceCategory,
    available_stock: int = 1_000,
    extraction_capacity_per_turn: int = 1_000,
    extracted: int = 1_000,
    allocated_workers: int = 1,
) -> DepositExtractionResult:
    """A minimal, self-consistent `DepositExtractionResult` for exercising
    `resource_output.py`'s functions directly, without needing a full `resolve_deposit_extraction`
    call. Only the fields `resource_output.py` actually reads (`category`, `extracted`,
    `available_stock`, `extraction_capacity_per_turn`) need to be meaningful; the rest are filled
    with harmless placeholders.
    """
    return DepositExtractionResult(
        category=category,
        opening_stock=available_stock,
        regeneration_per_turn=0,
        stock_ceiling=None,
        regenerated=0,
        available_stock=available_stock,
        extraction_capacity_per_turn=extraction_capacity_per_turn,
        output_per_worker=1,
        required_workers=1,
        allocated_workers=allocated_workers,
        extracted=extracted,
        closing_stock=available_stock - extracted,
        status=DepositStatus.LABOR_CONSTRAINED,
    )


def _all_results(
    overrides: dict[ResourceCategory, DepositExtractionResult] | None = None,
) -> tuple[DepositExtractionResult, ...]:
    overrides = overrides or {}
    return tuple(
        overrides.get(category, _extraction_result(category=category))
        for category in ResourceCategory
    )


def _uniform_coefficients(value: int = 1_000) -> dict[ResourceCategory, int]:
    return {category: value for category in ResourceCategory}


# --- T1: exact bridge conversion for all 8 resources, boundary magnitudes ----------------------


class TestComputeResourceOutputContributionsExactness:
    def test_every_category_converts_exactly(self) -> None:
        results = tuple(
            _extraction_result(
                category=category,
                available_stock=100_000,
                extraction_capacity_per_turn=100_000,
                extracted=50_000,
            )
            for category in ResourceCategory
        )
        coefficients = {
            ResourceCategory.TIMBER: 1_000,
            ResourceCategory.IRON_ORE: 1_500,
            ResourceCategory.COAL: 1_000,
            ResourceCategory.CRUDE_OIL: 1_200,
            ResourceCategory.NATURAL_GAS: 1_000,
            ResourceCategory.URANIUM: 100_000,
            ResourceCategory.COPPER: 1_000,
            ResourceCategory.CRITICAL_MINERALS: 5_000,
        }
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        by_category = {c.category: c for c in contributions}
        for category in ResourceCategory:
            coeff = coefficients[category]
            assert by_category[category].real_output_contribution == 50_000 * coeff
            assert by_category[category].potential_output_contribution == 100_000 * coeff

    def test_boundary_magnitude_large_values_stay_exact(self) -> None:
        results = _all_results(
            {
                ResourceCategory.URANIUM: _extraction_result(
                    category=ResourceCategory.URANIUM,
                    available_stock=10**12,
                    extraction_capacity_per_turn=10**12,
                    extracted=10**12,
                )
            }
        )
        coefficients = _uniform_coefficients(10**6)
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        uranium = next(c for c in contributions if c.category is ResourceCategory.URANIUM)
        assert uranium.real_output_contribution == 10**12 * 10**6
        assert uranium.potential_output_contribution == 10**12 * 10**6

    def test_zero_coefficient_is_rejected_by_the_underlying_bridge(self) -> None:
        results = _all_results()
        coefficients = _uniform_coefficients(0)
        with pytest.raises(ValueError):
            compute_resource_output_contributions(
                extraction_results=results, coefficients=coefficients
            )

    def test_negative_coefficient_is_rejected(self) -> None:
        results = _all_results()
        coefficients = _uniform_coefficients(-1)
        with pytest.raises(ValueError):
            compute_resource_output_contributions(
                extraction_results=results, coefficients=coefficients
            )


# --- T2: no-rounding / no-division claim ---------------------------------------------------------


class TestNoRounding:
    def test_no_division_anywhere_sum_of_contributions_equals_contribution_of_sum(self) -> None:
        """For a single category, converting then summing (trivially, one term) must equal
        converting the already-known product directly — proving there is no intermediate
        division/truncation step that could make the two differ."""
        result = _extraction_result(
            category=ResourceCategory.TIMBER, available_stock=777, extracted=333
        )
        results = _all_results({ResourceCategory.TIMBER: result})
        coefficients = _uniform_coefficients(997)  # deliberately not a round number
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        timber = next(c for c in contributions if c.category is ResourceCategory.TIMBER)
        assert timber.real_output_contribution == 333 * 997
        assert timber.potential_output_contribution == 777 * 997


# --- T3: canonical ordering / mapping-permutation resistance ------------------------------------


class TestCanonicalOrderingAndPermutationResistance:
    def test_output_is_always_in_canonical_category_order(self) -> None:
        results = _all_results()
        coefficients = _uniform_coefficients()
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        assert tuple(c.category for c in contributions) == _CATEGORIES

    def test_permuting_extraction_results_input_order_yields_identical_output(self) -> None:
        results = _all_results()
        reversed_results = tuple(reversed(results))
        coefficients = _uniform_coefficients()
        forward = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        backward = compute_resource_output_contributions(
            extraction_results=reversed_results, coefficients=coefficients
        )
        assert forward == backward

    def test_permuting_coefficients_mapping_insertion_order_yields_identical_output(self) -> None:
        results = _all_results()
        forward_coefficients = dict(_uniform_coefficients())
        reversed_coefficients = dict(reversed(list(_uniform_coefficients().items())))
        forward = compute_resource_output_contributions(
            extraction_results=results, coefficients=forward_coefficients
        )
        backward = compute_resource_output_contributions(
            extraction_results=results, coefficients=reversed_coefficients
        )
        assert forward == backward


# --- T4: coefficient/result map validation -------------------------------------------------------


class TestInputCompletenessValidation:
    def test_missing_category_in_extraction_results_is_rejected(self) -> None:
        results = _all_results()[:-1]
        with pytest.raises(ValueError, match="missing"):
            compute_resource_output_contributions(
                extraction_results=results, coefficients=_uniform_coefficients()
            )

    def test_missing_category_in_coefficients_is_rejected(self) -> None:
        coefficients = _uniform_coefficients()
        del coefficients[ResourceCategory.CRITICAL_MINERALS]
        with pytest.raises(ValueError, match="missing"):
            compute_resource_output_contributions(
                extraction_results=_all_results(), coefficients=coefficients
            )

    def test_duplicate_category_in_extraction_results_is_rejected(self) -> None:
        results = list(_all_results())
        results[1] = _extraction_result(category=results[0].category)
        with pytest.raises(ValueError, match="missing"):
            compute_resource_output_contributions(
                extraction_results=tuple(results), coefficients=_uniform_coefficients()
            )


# --- T5/T6: zero labor (actual=0, potential unaffected) vs. zero capacity (both=0) --------------


class TestZeroLaborVersusZeroCapacity:
    def test_zero_labor_zeroes_actual_but_not_potential(self) -> None:
        """Zero extraction-sector workers means extracted == 0 for every category, but the
        potential quantity depends only on stock/capacity — it is unaffected by labor."""
        result = _extraction_result(
            category=ResourceCategory.IRON_ORE,
            available_stock=500_000,
            extraction_capacity_per_turn=20_000,
            extracted=0,  # zero labor -> zero extracted, regardless of available stock/capacity
        )
        results = _all_results({ResourceCategory.IRON_ORE: result})
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=_uniform_coefficients(1_000)
        )
        iron_ore = next(c for c in contributions if c.category is ResourceCategory.IRON_ORE)
        assert iron_ore.real_output_contribution == 0
        assert iron_ore.potential_output_contribution == 20_000 * 1_000
        assert iron_ore.potential_output_contribution > 0

    def test_zero_capacity_or_zero_stock_zeroes_both(self) -> None:
        result = _extraction_result(
            category=ResourceCategory.COAL,
            available_stock=0,
            extraction_capacity_per_turn=0,
            extracted=0,
        )
        results = _all_results({ResourceCategory.COAL: result})
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=_uniform_coefficients(1_000)
        )
        coal = next(c for c in contributions if c.category is ResourceCategory.COAL)
        assert coal.real_output_contribution == 0
        assert coal.potential_output_contribution == 0


# --- T9: mixed-resource aggregation ---------------------------------------------------------------


class TestAggregateExtractionSectorOutput:
    def test_eight_category_mix_sums_exactly(self) -> None:
        results = tuple(
            _extraction_result(
                category=category,
                available_stock=(i + 1) * 10_000,
                extraction_capacity_per_turn=(i + 1) * 5_000,
                extracted=(i + 1) * 5_000,
            )
            for i, category in enumerate(ResourceCategory)
        )
        coefficients = {category: (i + 1) * 100 for i, category in enumerate(ResourceCategory)}
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=coefficients
        )
        actual_total, potential_total = aggregate_extraction_sector_output(contributions)
        expected_actual = sum(c.real_output_contribution for c in contributions)
        expected_potential = sum(c.potential_output_contribution for c in contributions)
        assert actual_total == expected_actual
        assert potential_total == expected_potential
        assert actual_total > 0
        assert potential_total > 0

    def test_all_zero_categories_sum_to_zero_for_both_totals(self) -> None:
        results = tuple(
            _extraction_result(
                category=category,
                available_stock=0,
                extraction_capacity_per_turn=0,
                extracted=0,
            )
            for category in ResourceCategory
        )
        contributions = compute_resource_output_contributions(
            extraction_results=results, coefficients=_uniform_coefficients()
        )
        actual_total, potential_total = aggregate_extraction_sector_output(contributions)
        assert actual_total == 0
        assert potential_total == 0

    def test_aggregation_is_a_pure_function_of_contributions_not_reordering_sensitive(
        self,
    ) -> None:
        contributions = compute_resource_output_contributions(
            extraction_results=_all_results(), coefficients=_uniform_coefficients()
        )
        reversed_contributions = tuple(reversed(contributions))
        assert aggregate_extraction_sector_output(
            contributions
        ) == aggregate_extraction_sector_output(reversed_contributions)


# --- T10: property-based tests (Hypothesis) --------------------------------------------------


@st.composite
def _deposit_inputs(draw: st.DrawFn) -> tuple[int, int, int, int]:
    """(available_stock, extraction_capacity_per_turn, extracted, real_output_per_unit) satisfying
    the real invariant `extracted <= min(available_stock, extraction_capacity_per_turn)`."""
    available_stock = draw(st.integers(min_value=0, max_value=10**9))
    extraction_capacity_per_turn = draw(st.integers(min_value=0, max_value=10**9))
    potential = min(available_stock, extraction_capacity_per_turn)
    extracted = draw(st.integers(min_value=0, max_value=potential))
    real_output_per_unit = draw(st.integers(min_value=1, max_value=10**6))
    return available_stock, extraction_capacity_per_turn, extracted, real_output_per_unit


@given(inputs=st.lists(_deposit_inputs(), min_size=8, max_size=8))
@settings(max_examples=1000)
def test_actual_never_exceeds_potential_for_arbitrary_valid_inputs(
    inputs: list[tuple[int, int, int, int]],
) -> None:
    results = tuple(
        _extraction_result(
            category=category,
            available_stock=available_stock,
            extraction_capacity_per_turn=extraction_capacity_per_turn,
            extracted=extracted,
        )
        for category, (available_stock, extraction_capacity_per_turn, extracted, _) in zip(
            ResourceCategory, inputs, strict=True
        )
    )
    coefficients = {
        category: real_output_per_unit
        for category, (_, _, _, real_output_per_unit) in zip(ResourceCategory, inputs, strict=True)
    }
    contributions = compute_resource_output_contributions(
        extraction_results=results, coefficients=coefficients
    )
    for c in contributions:
        assert c.real_output_contribution <= c.potential_output_contribution
    actual_total, potential_total = aggregate_extraction_sector_output(contributions)
    assert actual_total <= potential_total


@given(inputs=st.lists(_deposit_inputs(), min_size=8, max_size=8))
@settings(max_examples=1000)
def test_zero_extraction_biconditional_holds_for_arbitrary_valid_inputs(
    inputs: list[tuple[int, int, int, int]],
) -> None:
    """contribution == 0 iff extracted == 0 (true biconditional, D5 — coefficients are always
    strictly positive, so this can never fail in the other direction)."""
    results = tuple(
        _extraction_result(
            category=category,
            available_stock=available_stock,
            extraction_capacity_per_turn=extraction_capacity_per_turn,
            extracted=extracted,
        )
        for category, (available_stock, extraction_capacity_per_turn, extracted, _) in zip(
            ResourceCategory, inputs, strict=True
        )
    )
    coefficients = {
        category: real_output_per_unit
        for category, (_, _, _, real_output_per_unit) in zip(ResourceCategory, inputs, strict=True)
    }
    contributions = compute_resource_output_contributions(
        extraction_results=results, coefficients=coefficients
    )
    for c in contributions:
        assert (c.real_output_contribution == 0) == (c.extracted == 0)


@given(inputs=st.lists(_deposit_inputs(), min_size=8, max_size=8))
@settings(max_examples=1000)
def test_determinism_across_repeat_calls(inputs: list[tuple[int, int, int, int]]) -> None:
    results = tuple(
        _extraction_result(
            category=category,
            available_stock=available_stock,
            extraction_capacity_per_turn=extraction_capacity_per_turn,
            extracted=extracted,
        )
        for category, (available_stock, extraction_capacity_per_turn, extracted, _) in zip(
            ResourceCategory, inputs, strict=True
        )
    )
    coefficients = {
        category: real_output_per_unit
        for category, (_, _, _, real_output_per_unit) in zip(ResourceCategory, inputs, strict=True)
    }
    first = compute_resource_output_contributions(
        extraction_results=results, coefficients=coefficients
    )
    second = compute_resource_output_contributions(
        extraction_results=results, coefficients=coefficients
    )
    assert first == second
    assert aggregate_extraction_sector_output(first) == aggregate_extraction_sector_output(second)


def test_resource_output_contribution_is_a_frozen_dataclass() -> None:
    contribution = ResourceOutputContribution(
        category=ResourceCategory.TIMBER,
        extracted=100,
        potential_quantity=200,
        real_output_per_unit=10,
        real_output_contribution=1_000,
        potential_output_contribution=2_000,
    )
    with pytest.raises(AttributeError):
        contribution.extracted = 999  # type: ignore[misc]
