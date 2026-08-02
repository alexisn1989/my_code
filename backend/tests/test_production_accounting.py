from __future__ import annotations

from app.simulation.production_accounting import (
    SectorConstraint,
    aggregate_production,
    compute_sector_output,
)
from app.simulation.state import SectorCategory, SectorState


def _sector(
    *,
    category: SectorCategory = SectorCategory.MANUFACTURING,
    quarterly_capacity_output: int,
    output_per_worker: int,
    employed_workers: int,
    value_added_share_bps: int = 5_000,
    labor_income_share_bps: int = 5_000,
) -> SectorState:
    return SectorState(
        category=category,
        quarterly_capacity_output=quarterly_capacity_output,
        output_per_worker=output_per_worker,
        employed_workers=employed_workers,
        value_added_share_bps=value_added_share_bps,
        labor_income_share_bps=labor_income_share_bps,
    )


class TestClassification:
    def test_capacity_constrained_when_labor_limited_output_exceeds_capacity(self) -> None:
        sector = _sector(quarterly_capacity_output=100, output_per_worker=10, employed_workers=20)
        result = compute_sector_output(sector)
        assert result.labor_limited_output == 200
        assert result.actual_output == 100
        assert result.constraint == SectorConstraint.CAPACITY_CONSTRAINED
        assert result.capacity_utilization_bps == 10_000

    def test_labor_constrained_when_labor_limited_output_is_below_capacity(self) -> None:
        sector = _sector(quarterly_capacity_output=1000, output_per_worker=10, employed_workers=20)
        result = compute_sector_output(sector)
        assert result.labor_limited_output == 200
        assert result.actual_output == 200
        assert result.constraint == SectorConstraint.LABOR_CONSTRAINED
        assert result.capacity_utilization_bps == 2_000  # 200/1000 = 20% = 2000 bps

    def test_exactly_balanced_when_labor_limited_output_equals_capacity(self) -> None:
        sector = _sector(quarterly_capacity_output=200, output_per_worker=10, employed_workers=20)
        result = compute_sector_output(sector)
        assert result.labor_limited_output == 200
        assert result.actual_output == 200
        assert result.constraint == SectorConstraint.EXACTLY_BALANCED
        assert result.capacity_utilization_bps == 10_000

    def test_inactive_when_capacity_is_zero_and_no_employment(self) -> None:
        # R4/degenerate tie case: capacity == 0 AND employed_workers == 0 is INACTIVE,
        # not "exactly balanced" (0 == 0 would be a meaningless reading here).
        sector = _sector(quarterly_capacity_output=0, output_per_worker=1, employed_workers=0)
        result = compute_sector_output(sector)
        assert result.labor_limited_output == 0
        assert result.actual_output == 0
        assert result.constraint == SectorConstraint.INACTIVE
        assert result.capacity_utilization_bps == 0

    def test_inactive_when_capacity_is_zero_even_with_employment(self) -> None:
        # capacity == 0 always wins regardless of employed_workers/output_per_worker.
        sector = _sector(quarterly_capacity_output=0, output_per_worker=50, employed_workers=100)
        result = compute_sector_output(sector)
        assert result.actual_output == 0
        assert result.constraint == SectorConstraint.INACTIVE

    def test_labor_constrained_not_inactive_when_capacity_positive_but_unstaffed(self) -> None:
        """R4: positive capacity with zero workers is LABOR_CONSTRAINED, not INACTIVE —
        capacity exists and is simply unstaffed, a different fact from "no capacity
        at all." Zero output/utilization is still correct, but the classification
        must distinguish "unstaffed" from "no capacity."
        """
        sector = _sector(quarterly_capacity_output=500, output_per_worker=10, employed_workers=0)
        result = compute_sector_output(sector)
        assert result.labor_limited_output == 0
        assert result.actual_output == 0
        assert result.capacity_utilization_bps == 0
        assert result.constraint == SectorConstraint.LABOR_CONSTRAINED


class TestCapacityUtilizationBps:
    def test_floors_rather_than_rounds(self) -> None:
        # actual_output=1, capacity=3 -> 1/3 = 3333.33... bps, floors to 3333.
        sector = _sector(quarterly_capacity_output=3, output_per_worker=1, employed_workers=1)
        result = compute_sector_output(sector)
        assert result.capacity_utilization_bps == 3333

    def test_is_10000_if_and_only_if_actual_output_equals_capacity(self) -> None:
        exact = _sector(quarterly_capacity_output=100, output_per_worker=10, employed_workers=10)
        short = _sector(quarterly_capacity_output=101, output_per_worker=10, employed_workers=10)
        assert compute_sector_output(exact).capacity_utilization_bps == 10_000
        assert compute_sector_output(short).capacity_utilization_bps != 10_000

    def test_zero_capacity_yields_zero_bps_not_a_division_error(self) -> None:
        sector = _sector(quarterly_capacity_output=0, output_per_worker=1, employed_workers=0)
        assert compute_sector_output(sector).capacity_utilization_bps == 0

    def test_no_float_ever_appears_in_the_result(self) -> None:
        sector = _sector(quarterly_capacity_output=7, output_per_worker=3, employed_workers=5)
        result = compute_sector_output(sector)
        assert isinstance(result.labor_limited_output, int)
        assert isinstance(result.actual_output, int)
        assert isinstance(result.capacity_utilization_bps, int)


class TestAggregateProduction:
    def test_sums_employment_from_inputs_and_actual_output_from_results(self) -> None:
        sectors = (
            _sector(
                category=SectorCategory.AGRICULTURE,
                quarterly_capacity_output=100,
                output_per_worker=10,
                employed_workers=5,
            ),
            _sector(
                category=SectorCategory.MANUFACTURING,
                quarterly_capacity_output=50,
                output_per_worker=10,
                employed_workers=20,
            ),
        )
        results = tuple(compute_sector_output(s) for s in sectors)
        aggregates = aggregate_production(sectors, results)
        assert aggregates.total_employment == 25
        assert (
            aggregates.total_gross_output == 50 + 50
        )  # first labor-limited(50), second capped(50)

    def test_empty_sectors_yield_zero_totals(self) -> None:
        aggregates = aggregate_production((), ())
        assert aggregates.total_employment == 0
        assert aggregates.total_gross_output == 0
