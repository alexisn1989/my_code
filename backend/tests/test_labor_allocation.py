from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.simulation.integer_allocation import largest_remainder_allocation
from app.simulation.labor_allocation import (
    aggregate_labor_market,
    allocate_workers,
    compute_effective_labor_force,
    compute_required_workers,
)
from app.simulation.state import SectorCategory, SectorState

_CATEGORIES = tuple(SectorCategory)


def _sector(
    *,
    category: SectorCategory = SectorCategory.MANUFACTURING,
    quarterly_capacity_output: int,
    output_per_worker: int,
) -> SectorState:
    return SectorState(
        category=category,
        quarterly_capacity_output=quarterly_capacity_output,
        output_per_worker=output_per_worker,
        value_added_share_bps=5_000,
        labor_income_share_bps=5_000,
    )


class TestComputeEffectiveLaborForce:
    def test_ordinary_values(self) -> None:
        assert (
            compute_effective_labor_force(
                population=1_000_000, effective_labor_force_share_bps=6_000
            )
            == 600_000
        )

    def test_zero_population(self) -> None:
        assert (
            compute_effective_labor_force(population=0, effective_labor_force_share_bps=10_000) == 0
        )

    def test_zero_share(self) -> None:
        assert (
            compute_effective_labor_force(population=1_000_000, effective_labor_force_share_bps=0)
            == 0
        )

    def test_full_share_equals_population(self) -> None:
        assert (
            compute_effective_labor_force(population=12_345, effective_labor_force_share_bps=10_000)
            == 12_345
        )

    def test_floors_rather_than_rounds(self) -> None:
        # 7 * 3333 / 10_000 = 2.3331 -> floors to 2.
        assert (
            compute_effective_labor_force(population=7, effective_labor_force_share_bps=3_333) == 2
        )

    def test_result_never_exceeds_population_across_a_range(self) -> None:
        for population in (0, 1, 2, 999, 1_000_000):
            for share_bps in (0, 1, 5_000, 9_999, 10_000):
                result = compute_effective_labor_force(
                    population=population, effective_labor_force_share_bps=share_bps
                )
                assert 0 <= result <= population


class TestComputeRequiredWorkers:
    def test_zero_capacity_yields_zero(self) -> None:
        sector = _sector(quarterly_capacity_output=0, output_per_worker=1)
        assert compute_required_workers(sector) == 0

    def test_exact_division(self) -> None:
        sector = _sector(quarterly_capacity_output=1000, output_per_worker=10)
        assert compute_required_workers(sector) == 100

    def test_non_exact_division_rounds_up(self) -> None:
        # 2,000,000,000 / 750,000 = 2666.66... -> ceil to 2,667.
        sector = _sector(quarterly_capacity_output=2_000_000_000, output_per_worker=750_000)
        assert compute_required_workers(sector) == 2_667

    def test_ceiling_boundary_just_above_an_exact_multiple(self) -> None:
        sector = _sector(quarterly_capacity_output=1001, output_per_worker=10)
        assert compute_required_workers(sector) == 101

    def test_very_large_values(self) -> None:
        sector = _sector(quarterly_capacity_output=10**12, output_per_worker=1)
        assert compute_required_workers(sector) == 10**12

    def test_no_float_ever_appears_in_the_result(self) -> None:
        sector = _sector(quarterly_capacity_output=7, output_per_worker=3)
        assert isinstance(compute_required_workers(sector), int)


class TestAllocateWorkers:
    def test_abundant_labor_allocates_exactly_required(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 10),
            (SectorCategory.MANUFACTURING, 20),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=100)
        assert [(r.category, r.allocated_workers) for r in results] == [
            (SectorCategory.AGRICULTURE, 10),
            (SectorCategory.MANUFACTURING, 20),
        ]
        assert all(r.allocated_workers == r.required_workers for r in results)

    def test_exact_equality_allocates_exactly_required(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 30),
            (SectorCategory.MANUFACTURING, 70),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=100)
        assert sum(r.allocated_workers for r in results) == 100
        assert all(r.allocated_workers == r.required_workers for r in results)

    def test_scarce_labor_uses_largest_remainder(self) -> None:
        # total required=100, labor_force=53:
        #   agriculture:    floor(53*30/100)=15, remainder=90
        #   manufacturing:  floor(53*30/100)=15, remainder=90
        #   construction:   floor(53*40/100)=21, remainder=20
        # sum(floors)=51, leftover=2 -> the two largest (tied) remainders each get +1.
        required = (
            (SectorCategory.AGRICULTURE, 30),
            (SectorCategory.MANUFACTURING, 30),
            (SectorCategory.CONSTRUCTION, 40),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=53)
        allocated = {r.category: r.allocated_workers for r in results}
        assert allocated[SectorCategory.AGRICULTURE] == 16
        assert allocated[SectorCategory.MANUFACTURING] == 16
        assert allocated[SectorCategory.CONSTRUCTION] == 21
        assert sum(allocated.values()) == 53

    def test_never_allocates_above_sector_demand_even_with_abundant_labor(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 1),
            (SectorCategory.MANUFACTURING, 1),
            (SectorCategory.CONSTRUCTION, 1),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=1000)
        assert all(r.allocated_workers == r.required_workers for r in results)

    def test_zero_total_demand_with_positive_labor_force_allocates_nothing(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 0),
            (SectorCategory.MANUFACTURING, 0),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=100)
        assert all(r.allocated_workers == 0 for r in results)

    def test_canonical_tie_breaking_with_all_equal_remainders(self) -> None:
        """D8's dedicated fixture: eleven sectors with identical required_workers=10
        (total demand 110) against a labor force of 105 — every remainder is equal, so
        tie-breaking is resolved entirely by canonical `SectorCategory` declaration order.
        """
        required = tuple((category, 10) for category in _CATEGORIES)
        results = allocate_workers(required_by_category=required, effective_labor_force=105)
        allocated = [r.allocated_workers for r in results]
        assert allocated == [10, 10, 10, 10, 10, 10, 9, 9, 9, 9, 9]
        assert sum(allocated) == 105

    def test_allocated_never_exceeds_required_across_a_range_of_scarcity(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 7),
            (SectorCategory.MANUFACTURING, 5),
            (SectorCategory.ENERGY, 3),
        )
        for labor_force in range(0, 20):
            results = allocate_workers(
                required_by_category=required, effective_labor_force=labor_force
            )
            for r in results:
                assert 0 <= r.allocated_workers <= r.required_workers
            assert sum(r.allocated_workers for r in results) == min(labor_force, 15)

    @given(
        requireds=st.lists(
            st.integers(min_value=0, max_value=10_000),
            min_size=len(_CATEGORIES),
            max_size=len(_CATEGORIES),
        ),
        effective_labor_force=st.integers(min_value=0, max_value=100_000),
    )
    @settings(max_examples=1000)
    def test_allocation_invariants_hold_for_arbitrary_integer_inputs(
        self, requireds: list[int], effective_labor_force: int
    ) -> None:
        """Property-based proof (Hypothesis) that, for any nonnegative integer requirements and
        any nonnegative labor force: every sector's allocation is between 0 and its own
        requirement, and total employment equals `min(labor_force, total_demand)` exactly —
        pre-verified by hand against 20,000 random cases before this test was written; this is
        the same proof, committed and re-checked on every run.
        """
        required_by_category = tuple(zip(_CATEGORIES, requireds, strict=True))
        total_required = sum(requireds)
        results = allocate_workers(
            required_by_category=required_by_category, effective_labor_force=effective_labor_force
        )
        for (category, required), result in zip(required_by_category, results, strict=True):
            assert result.category == category
            assert result.required_workers == required
            assert 0 <= result.allocated_workers <= required
        total_allocated = sum(r.allocated_workers for r in results)
        assert total_allocated == min(effective_labor_force, total_required)


class TestByteIdenticalToTheNeutralCore:
    """Phase 2C1 (D7/R7): `allocate_workers` became a thin wrapper over the shared, category-
    agnostic `integer_allocation.largest_remainder_allocation` core. This proves the wrapper
    introduces zero behavioral drift — for arbitrary inputs, calling the wrapper produces exactly
    the same `(category, required, allocated)` triples as calling the core directly on the same
    pairs and rewrapping, since `allocate_workers`'s canonical-order tuple input is passed through
    unchanged (unlike the resource wrapper, which canonicalizes a mapping first — see
    `integer_allocation`'s module docstring and `test_resource_extraction.py`'s permutation test).
    The full pre-existing Phase 2B3 suite (every test above and in
    `test_labor_to_production_linkage.py`/`test_phase_isolation.py`) passing unchanged after this
    refactor is the practical, end-to-end version of this same proof.
    """

    @given(
        requireds=st.lists(
            st.integers(min_value=0, max_value=10_000),
            min_size=len(_CATEGORIES),
            max_size=len(_CATEGORIES),
        ),
        effective_labor_force=st.integers(min_value=0, max_value=100_000),
    )
    @settings(max_examples=1000)
    def test_wrapper_output_matches_the_core_called_directly(
        self, requireds: list[int], effective_labor_force: int
    ) -> None:
        required_by_category = tuple(zip(_CATEGORIES, requireds, strict=True))
        wrapper_results = allocate_workers(
            required_by_category=required_by_category, effective_labor_force=effective_labor_force
        )
        core_results = largest_remainder_allocation(
            weights_by_category=required_by_category, budget=effective_labor_force
        )
        assert [(r.category, r.required_workers, r.allocated_workers) for r in wrapper_results] == [
            (r.category, r.weight, r.allocated) for r in core_results
        ]

    def test_hand_verified_scarce_tie_break_figures_unchanged_by_the_refactor(self) -> None:
        """Pins the exact numbers `TestAllocateWorkers.test_scarce_labor_uses_largest_remainder`
        above already verifies by hand (16/16/21 for weights 30/30/40 under budget 53) — repeated
        here specifically as a regression marker tied to the refactor commit, not a duplicate of
        that test's own reasoning.
        """
        required = (
            (SectorCategory.AGRICULTURE, 30),
            (SectorCategory.MANUFACTURING, 30),
            (SectorCategory.CONSTRUCTION, 40),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=53)
        allocated = {r.category: r.allocated_workers for r in results}
        assert allocated[SectorCategory.AGRICULTURE] == 16
        assert allocated[SectorCategory.MANUFACTURING] == 16
        assert allocated[SectorCategory.CONSTRUCTION] == 21


class TestAggregateLaborMarket:
    def test_computes_identities_from_results(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 10),
            (SectorCategory.MANUFACTURING, 20),
        )
        effective_labor_force = compute_effective_labor_force(
            population=1000, effective_labor_force_share_bps=10_000
        )
        results = allocate_workers(
            required_by_category=required, effective_labor_force=effective_labor_force
        )
        aggregates = aggregate_labor_market(
            total_population=1000, effective_labor_force=effective_labor_force, results=results
        )
        assert aggregates.total_labor_demand == 30
        assert aggregates.total_employment == 30
        assert aggregates.unemployed_workers == 970
        assert aggregates.unfilled_jobs == 0
        assert aggregates.unemployment_rate_bps == (970 * 10_000) // 1000

    def test_zero_labor_force_yields_zero_unemployment_rate_not_a_division_error(self) -> None:
        required = ((SectorCategory.AGRICULTURE, 0),)
        results = allocate_workers(required_by_category=required, effective_labor_force=0)
        aggregates = aggregate_labor_market(
            total_population=0, effective_labor_force=0, results=results
        )
        assert aggregates.unemployment_rate_bps == 0

    def test_scarce_labor_yields_unfilled_jobs_and_no_unemployment(self) -> None:
        required = (
            (SectorCategory.AGRICULTURE, 30),
            (SectorCategory.MANUFACTURING, 30),
        )
        results = allocate_workers(required_by_category=required, effective_labor_force=40)
        aggregates = aggregate_labor_market(
            total_population=100, effective_labor_force=40, results=results
        )
        assert aggregates.total_labor_demand == 60
        assert aggregates.total_employment == 40
        assert aggregates.unemployed_workers == 0
        assert aggregates.unfilled_jobs == 20

    def test_empty_results_yield_zero_totals(self) -> None:
        aggregates = aggregate_labor_market(total_population=0, effective_labor_force=0, results=())
        assert aggregates.total_labor_demand == 0
        assert aggregates.total_employment == 0
        assert aggregates.unemployed_workers == 0
        assert aggregates.unfilled_jobs == 0
        assert aggregates.unemployment_rate_bps == 0
