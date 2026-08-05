"""Tests for the pure Phase 2C1 formulas in `simulation.resource_extraction`, plus
`ResourceCategory`/`RESOURCE_UNITS`/`EconomyState.resource_deposits` structural properties (T1).

Covers: enum stability/canonical order/completeness/identity matching (T1), exact nonrenewable
conservation (T3), timber regeneration/ceiling/timing including the three-regime multi-turn
dynamic (T4), extraction bounded independently by stock/capacity/labor (T5), zero/edge cases (T6),
deterministic sub-allocation with mapping-permutation resistance (T9), and a resource-formula
property-based test (T10).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.simulation.resource_extraction import (
    DepositAllocationResult,
    DepositStatus,
    aggregate_extraction,
    allocate_extraction_workers,
    compute_available_stock,
    compute_deposit_extraction,
    compute_regeneration,
    compute_required_workers,
)
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    RESOURCE_UNITS,
    EconomyState,
    ResourceCategory,
    ResourceDepositState,
    SectorCategory,
    SectorState,
)
from tests.conftest import make_economy

_CATEGORIES = tuple(ResourceCategory)


def _deposit(
    *,
    category: ResourceCategory = ResourceCategory.IRON_ORE,
    remaining_stock: int = 1_000,
    extraction_capacity_per_turn: int = 1_000,
    output_per_worker: int = 1,
    regeneration_per_turn: int = 0,
    stock_ceiling: int | None = None,
) -> ResourceDepositState:
    if category in RENEWABLE_RESOURCES and stock_ceiling is None:
        stock_ceiling = remaining_stock
    return ResourceDepositState(
        category=category,
        remaining_stock=remaining_stock,
        extraction_capacity_per_turn=extraction_capacity_per_turn,
        output_per_worker=output_per_worker,
        regeneration_per_turn=regeneration_per_turn,
        stock_ceiling=stock_ceiling,
    )


def _minimal_sectors() -> tuple[SectorState, ...]:
    return tuple(
        SectorState(
            category=category,
            quarterly_capacity_output=1,
            output_per_worker=1,
            value_added_share_bps=5_000,
            labor_income_share_bps=5_000,
        )
        for category in SectorCategory
    )


def _all_deposits(
    overrides: dict[ResourceCategory, ResourceDepositState] | None = None,
) -> tuple[ResourceDepositState, ...]:
    overrides = overrides or {}
    return tuple(
        overrides.get(
            category, _deposit(category=category, remaining_stock=0, extraction_capacity_per_turn=0)
        )
        for category in ResourceCategory
    )


# --- T1: enum stability, canonical order (reject, not normalize), completeness, units ----------


class TestResourceCategoryAndUnits:
    def test_canonical_declaration_order(self) -> None:
        assert tuple(ResourceCategory) == (
            ResourceCategory.TIMBER,
            ResourceCategory.IRON_ORE,
            ResourceCategory.COAL,
            ResourceCategory.CRUDE_OIL,
            ResourceCategory.NATURAL_GAS,
            ResourceCategory.URANIUM,
            ResourceCategory.COPPER,
            ResourceCategory.CRITICAL_MINERALS,
        )

    def test_resource_units_covers_all_eight_categories(self) -> None:
        assert set(RESOURCE_UNITS) == set(ResourceCategory)
        assert all(isinstance(unit, str) and unit for unit in RESOURCE_UNITS.values())

    def test_only_timber_is_renewable(self) -> None:
        assert frozenset({ResourceCategory.TIMBER}) == RENEWABLE_RESOURCES


class TestEconomyStateResourceDepositsCompletenessAndOrder:
    def test_duplicate_category_is_rejected(self) -> None:
        deposits = list(_all_deposits())
        deposits[1] = _deposit(
            category=deposits[0].category, remaining_stock=0, extraction_capacity_per_turn=0
        )
        with pytest.raises(ValueError, match="duplicate resource category"):
            EconomyState(
                effective_labor_force_share_bps=10_000,
                sectors=_minimal_sectors(),
                resource_deposits=tuple(deposits),
            )

    def test_missing_category_is_rejected(self) -> None:
        deposits = tuple(_all_deposits())[:-1]  # drop critical_minerals
        with pytest.raises(ValueError, match="missing resource categories"):
            EconomyState(
                effective_labor_force_share_bps=10_000,
                sectors=_minimal_sectors(),
                resource_deposits=deposits,
            )

    def test_reversed_order_is_rejected_not_normalized(self) -> None:
        """R3: unlike `sectors`, noncanonical resource order RAISES with an actionable message
        naming the reversed order — it is never silently reassigned to canonical order."""
        deposits = tuple(reversed(_all_deposits()))
        with pytest.raises(ValueError, match="not in canonical ResourceCategory order"):
            EconomyState(
                effective_labor_force_share_bps=10_000,
                sectors=_minimal_sectors(),
                resource_deposits=deposits,
            )

    def test_valid_complete_canonical_order_constructs_cleanly(self) -> None:
        economy = EconomyState(
            effective_labor_force_share_bps=10_000,
            sectors=_minimal_sectors(),
            resource_deposits=_all_deposits(),
        )
        assert tuple(d.category for d in economy.resource_deposits) == tuple(ResourceCategory)


# --- ResourceDepositState's own renewability validators -----------------------------------------


class TestResourceDepositStateRenewabilityValidators:
    def test_nonrenewable_with_nonzero_regeneration_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="nonrenewable"):
            _deposit(category=ResourceCategory.IRON_ORE, regeneration_per_turn=1)

    def test_nonrenewable_with_a_stock_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="nonrenewable"):
            ResourceDepositState(
                category=ResourceCategory.IRON_ORE,
                remaining_stock=100,
                extraction_capacity_per_turn=10,
                output_per_worker=1,
                regeneration_per_turn=0,
                stock_ceiling=100,
            )

    def test_renewable_without_a_stock_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="renewable"):
            ResourceDepositState(
                category=ResourceCategory.TIMBER,
                remaining_stock=100,
                extraction_capacity_per_turn=10,
                output_per_worker=1,
                regeneration_per_turn=5,
                stock_ceiling=None,
            )

    def test_renewable_with_ceiling_below_stock_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="below its own remaining_stock"):
            ResourceDepositState(
                category=ResourceCategory.TIMBER,
                remaining_stock=100,
                extraction_capacity_per_turn=10,
                output_per_worker=1,
                regeneration_per_turn=5,
                stock_ceiling=99,
            )

    def test_renewable_with_ceiling_equal_to_stock_is_valid(self) -> None:
        deposit = ResourceDepositState(
            category=ResourceCategory.TIMBER,
            remaining_stock=100,
            extraction_capacity_per_turn=10,
            output_per_worker=1,
            regeneration_per_turn=5,
            stock_ceiling=100,
        )
        assert deposit.stock_ceiling == 100


# --- T3: exact nonrenewable conservation --------------------------------------------------------


class TestNonrenewableConservation:
    @pytest.mark.parametrize(
        "remaining_stock,extraction_capacity_per_turn,output_per_worker,allocated_workers",
        [
            (1_000, 100, 10, 10),
            (50, 100, 10, 10),  # stock-bound
            (1_000_000, 1, 1, 1),  # capacity-bound to a trickle
            (0, 100, 10, 10),  # already empty
        ],
    )
    def test_opening_equals_extracted_plus_closing(
        self,
        remaining_stock: int,
        extraction_capacity_per_turn: int,
        output_per_worker: int,
        allocated_workers: int,
    ) -> None:
        deposit = _deposit(
            category=ResourceCategory.COAL,
            remaining_stock=remaining_stock,
            extraction_capacity_per_turn=extraction_capacity_per_turn,
            output_per_worker=output_per_worker,
        )
        required = compute_required_workers(deposit)
        allocation = allocate_extraction_workers(
            required_by_category={
                **{c: 0 for c in ResourceCategory},
                ResourceCategory.COAL: required,
            },
            extraction_sector_workers=allocated_workers,
        )
        coal_allocation = next(a for a in allocation if a.category == ResourceCategory.COAL)
        result = compute_deposit_extraction(deposit=deposit, allocation=coal_allocation)
        assert deposit.remaining_stock == result.extracted + result.closing_stock
        assert compute_regeneration(deposit) == 0


# --- T4: timber regeneration, ceiling, timing, and the three-regime dynamic ----------------------


class TestTimberRegeneration:
    def test_regeneration_is_zero_for_a_nonrenewable(self) -> None:
        deposit = _deposit(category=ResourceCategory.COPPER, remaining_stock=100)
        assert compute_regeneration(deposit) == 0

    def test_regeneration_is_clamped_by_the_ceiling(self) -> None:
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=95,
            regeneration_per_turn=10,
            stock_ceiling=100,
        )
        # Would overshoot to 105 uncapped; clamped to the 5 units of headroom.
        assert compute_regeneration(deposit) == 5

    def test_regeneration_is_zero_exactly_at_the_ceiling(self) -> None:
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=100,
            regeneration_per_turn=10,
            stock_ceiling=100,
        )
        assert compute_regeneration(deposit) == 0
        assert compute_available_stock(deposit) == 100

    def test_available_stock_is_opening_plus_regeneration(self) -> None:
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=50,
            regeneration_per_turn=10,
            stock_ceiling=1_000,
        )
        assert compute_available_stock(deposit) == 60

    def test_regeneration_happens_before_extraction_this_same_turn(self) -> None:
        """The regenerated amount is included in `available_stock`, which bounds
        `required_workers`/`extracted` — proving regeneration is applied before, not after,
        extraction within the same turn's formulas."""
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=0,
            extraction_capacity_per_turn=1_000,
            output_per_worker=1,
            regeneration_per_turn=50,
            stock_ceiling=1_000,
        )
        required = compute_required_workers(deposit)
        assert required == 50  # only reachable if the 50 regenerated units are already available


class TestDeficitDemoTimberThreeRegimeTrajectory:
    """Reproduces `deficit_demo.yaml`'s exact hand-worked timber trajectory (R4/R8) turn by turn,
    via the pure formulas directly (not the resolver) — the fast, dedicated proof that the three
    regimes are real, not a documentation artifact. `test_resource_conservation.py`'s soak-style
    test re-observes the same dynamic through the real engine.
    """

    def _simulate(self, turns: int) -> list[dict]:
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=200_000,
            extraction_capacity_per_turn=10_000,
            output_per_worker=25,
            regeneration_per_turn=5_000,
            stock_ceiling=250_000,
        )
        rows = []
        for _ in range(turns):
            required = compute_required_workers(deposit)
            allocation = allocate_extraction_workers(
                required_by_category={
                    **{c: 0 for c in ResourceCategory},
                    ResourceCategory.TIMBER: required,
                },
                extraction_sector_workers=10_000,  # abundant relative to required <= 400
            )
            timber_allocation = next(a for a in allocation if a.category == ResourceCategory.TIMBER)
            result = compute_deposit_extraction(deposit=deposit, allocation=timber_allocation)
            rows.append(
                {
                    "opening": deposit.remaining_stock,
                    "regenerated": result.regenerated,
                    "available": result.available_stock,
                    "extracted": result.extracted,
                    "closing": result.closing_stock,
                    "status": result.status,
                }
            )
            assert (
                result.opening_stock + result.regenerated == result.extracted + result.closing_stock
            )
            assert result.closing_stock >= 0
            deposit.remaining_stock = result.closing_stock
        return rows

    def test_resolutions_1_to_39_are_capacity_constrained_declining_by_5000_net(self) -> None:
        rows = self._simulate(39)
        for i, row in enumerate(rows, start=1):
            assert row["status"] == DepositStatus.CAPACITY_CONSTRAINED, f"resolution {i}"
            assert row["extracted"] == 10_000
        assert rows[38]["closing"] == 5_000  # resolution 39

    def test_resolution_40_is_the_stock_constrained_boundary_tie(self) -> None:
        rows = self._simulate(40)
        boundary = rows[39]  # resolution 40
        assert boundary["opening"] == 5_000
        assert boundary["available"] == 10_000  # ties extraction_capacity_per_turn exactly
        assert boundary["extracted"] == 10_000
        assert boundary["closing"] == 0
        assert boundary["status"] == DepositStatus.STOCK_CONSTRAINED  # not CAPACITY_CONSTRAINED

    def test_resolutions_41_plus_are_the_steady_state(self) -> None:
        rows = self._simulate(45)
        for i, row in enumerate(rows[40:], start=41):
            assert row["opening"] == 0, f"resolution {i}"
            assert row["regenerated"] == 5_000, f"resolution {i}"
            assert row["extracted"] == 5_000, f"resolution {i}"
            assert row["closing"] == 0, f"resolution {i}"
            assert row["status"] == DepositStatus.STOCK_CONSTRAINED, f"resolution {i}"
            assert row["status"] != DepositStatus.DEPLETED, f"resolution {i}"


# --- T5: extraction bounded independently by stock / capacity / labor ---------------------------


class TestExtractionBoundIndependence:
    def _extract(self, deposit: ResourceDepositState, allocated_workers: int) -> object:

        required = compute_required_workers(deposit)
        allocation = DepositAllocationResult(
            category=deposit.category,
            required_workers=required,
            allocated_workers=allocated_workers,
        )
        return compute_deposit_extraction(deposit=deposit, allocation=allocation)

    def test_stock_is_the_uniquely_binding_bound(self) -> None:
        deposit = _deposit(
            remaining_stock=10, extraction_capacity_per_turn=1_000, output_per_worker=1
        )
        result = self._extract(deposit, allocated_workers=1_000)
        assert result.extracted == 10
        assert result.status == DepositStatus.STOCK_CONSTRAINED

    def test_capacity_is_the_uniquely_binding_bound(self) -> None:
        deposit = _deposit(
            remaining_stock=1_000_000, extraction_capacity_per_turn=10, output_per_worker=1
        )
        result = self._extract(deposit, allocated_workers=1_000)
        assert result.extracted == 10
        assert result.status == DepositStatus.CAPACITY_CONSTRAINED

    def test_labor_is_the_uniquely_binding_bound(self) -> None:
        deposit = _deposit(
            remaining_stock=1_000_000, extraction_capacity_per_turn=1_000_000, output_per_worker=1
        )
        result = self._extract(deposit, allocated_workers=5)
        assert result.extracted == 5
        assert result.status == DepositStatus.LABOR_CONSTRAINED


# --- T6: zero/edge cases --------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_capacity_is_inactive_regardless_of_stock_or_labor(self) -> None:
        deposit = _deposit(
            remaining_stock=1_000, extraction_capacity_per_turn=0, output_per_worker=1
        )
        required = compute_required_workers(deposit)
        assert required == 0

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=0, allocated_workers=0
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        assert result.extracted == 0
        assert result.closing_stock == 1_000
        assert result.status == DepositStatus.INACTIVE

    def test_zero_stock_no_regeneration_is_depleted(self) -> None:
        deposit = _deposit(remaining_stock=0, extraction_capacity_per_turn=100, output_per_worker=1)

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=0, allocated_workers=0
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        assert result.extracted == 0
        assert result.status == DepositStatus.DEPLETED

    def test_zero_labor_budget_extracts_nothing_but_still_regenerates(self) -> None:
        deposit = _deposit(
            category=ResourceCategory.TIMBER,
            remaining_stock=100,
            extraction_capacity_per_turn=1_000,
            output_per_worker=1,
            regeneration_per_turn=10,
            stock_ceiling=1_000,
        )

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=1_000, allocated_workers=0
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        assert result.extracted == 0
        assert result.regenerated == 10
        assert result.closing_stock == 110

    def test_zero_total_demand_with_positive_budget_leaves_everything_unassigned(self) -> None:
        results = allocate_extraction_workers(
            required_by_category={c: 0 for c in ResourceCategory}, extraction_sector_workers=500
        )
        assert all(r.allocated_workers == 0 for r in results)

    def test_output_per_worker_is_strictly_positive_at_the_type_level(self) -> None:
        with pytest.raises(ValidationError):
            ResourceDepositState(
                category=ResourceCategory.IRON_ORE,
                remaining_stock=0,
                extraction_capacity_per_turn=0,
                output_per_worker=0,
            )

    def test_one_unit_stock_extracts_exactly_one_then_depletes_next_turn(self) -> None:
        deposit = _deposit(remaining_stock=1, extraction_capacity_per_turn=100, output_per_worker=1)

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=1, allocated_workers=1
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        assert result.extracted == 1
        assert result.closing_stock == 0
        deposit.remaining_stock = result.closing_stock
        next_allocation = DepositAllocationResult(
            category=deposit.category, required_workers=0, allocated_workers=0
        )
        next_result = compute_deposit_extraction(deposit=deposit, allocation=next_allocation)
        assert next_result.status == DepositStatus.DEPLETED


# --- T9: deterministic sub-allocation, tie-break, mapping-permutation resistance (R7) ------------


class TestAllocateExtractionWorkers:
    def test_all_equal_remainder_eight_deposit_fixture_resolved_by_canonical_order(self) -> None:
        # Every category requires 10, budget 25 (scarce): all remainders equal, so tie-breaking is
        # resolved entirely by tuple(ResourceCategory) canonical order regardless of mapping order.
        required = {c: 10 for c in ResourceCategory}
        results = allocate_extraction_workers(
            required_by_category=required, extraction_sector_workers=25
        )
        allocated = [r.allocated_workers for r in results]
        # 8 categories * floor(25*10/80)=3 each = 24, leftover=1 -> first category (TIMBER) gets it.
        assert allocated == [4, 3, 3, 3, 3, 3, 3, 3]
        assert sum(allocated) == 25

    def test_permuting_mapping_insertion_order_yields_identical_results(self) -> None:
        forward = {ResourceCategory.TIMBER: 10, ResourceCategory.IRON_ORE: 10}
        forward.update({c: 0 for c in ResourceCategory if c not in forward})
        reversed_dict = dict(reversed(list(forward.items())))

        forward_results = allocate_extraction_workers(
            required_by_category=forward, extraction_sector_workers=5
        )
        reversed_results = allocate_extraction_workers(
            required_by_category=reversed_dict, extraction_sector_workers=5
        )
        forward_by_category = {r.category: r.allocated_workers for r in forward_results}
        reversed_by_category = {r.category: r.allocated_workers for r in reversed_results}
        assert forward_by_category == reversed_by_category

    def test_results_are_always_returned_in_canonical_order(self) -> None:
        required = {c: 1 for c in ResourceCategory}
        results = allocate_extraction_workers(
            required_by_category=required, extraction_sector_workers=8
        )
        assert tuple(r.category for r in results) == tuple(ResourceCategory)

    def test_missing_category_in_mapping_is_rejected(self) -> None:
        required = {c: 0 for c in ResourceCategory if c != ResourceCategory.URANIUM}
        with pytest.raises(ValueError, match="missing="):
            allocate_extraction_workers(required_by_category=required, extraction_sector_workers=10)

    def test_unknown_key_in_mapping_is_rejected(self) -> None:
        required = {c: 0 for c in ResourceCategory}
        required["not_a_real_category"] = 5  # type: ignore[index]
        with pytest.raises(ValueError, match="unknown="):
            allocate_extraction_workers(required_by_category=required, extraction_sector_workers=10)

    def test_abundant_budget_allocates_exactly_each_requirement(self) -> None:
        required = {c: 5 for c in ResourceCategory}
        results = allocate_extraction_workers(
            required_by_category=required, extraction_sector_workers=1_000
        )
        assert all(r.allocated_workers == r.required_workers == 5 for r in results)


class TestAggregateExtraction:
    def test_never_sums_heterogeneous_physical_quantities(self) -> None:
        """D4: `ExtractionAggregates` has no summed-quantity field at all — only worker counts
        and per-status counts. This test documents that absence by construction: attempting to
        read a nonexistent `total_extracted` attribute fails."""
        deposit = _deposit(
            remaining_stock=100, extraction_capacity_per_turn=10, output_per_worker=1
        )

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=10, allocated_workers=10
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        aggregates = aggregate_extraction(extraction_sector_workers=10, results=(result,))
        assert not hasattr(aggregates, "total_extracted")

    def test_unassigned_equals_sector_workers_minus_total(self) -> None:
        deposit = _deposit(remaining_stock=0, extraction_capacity_per_turn=0, output_per_worker=1)

        allocation = DepositAllocationResult(
            category=deposit.category, required_workers=0, allocated_workers=0
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        aggregates = aggregate_extraction(extraction_sector_workers=100, results=(result,))
        assert aggregates.total_extraction_workers == 0
        assert aggregates.unassigned_resource_workers == 100

    def test_status_counts_cover_all_five_statuses_at_zero_by_default(self) -> None:
        aggregates = aggregate_extraction(extraction_sector_workers=0, results=())
        assert set(aggregates.status_counts) == set(DepositStatus)
        assert all(count == 0 for count in aggregates.status_counts.values())


# --- T10: resource-formula property-based test (Hypothesis) --------------------------------------


class TestResourceFormulaProperties:
    @given(
        remaining_stock=st.integers(min_value=0, max_value=10_000_000),
        extraction_capacity_per_turn=st.integers(min_value=0, max_value=1_000_000),
        output_per_worker=st.integers(min_value=1, max_value=100_000),
        regeneration_per_turn=st.integers(min_value=0, max_value=100_000),
        allocated_workers=st.integers(min_value=0, max_value=100_000),
        is_renewable=st.booleans(),
    )
    @settings(max_examples=1000)
    def test_conservation_and_bounds_hold_for_arbitrary_nonrenewable_and_renewable_inputs(
        self,
        remaining_stock: int,
        extraction_capacity_per_turn: int,
        output_per_worker: int,
        regeneration_per_turn: int,
        allocated_workers: int,
        is_renewable: bool,
    ) -> None:
        if is_renewable:
            deposit = _deposit(
                category=ResourceCategory.TIMBER,
                remaining_stock=remaining_stock,
                extraction_capacity_per_turn=extraction_capacity_per_turn,
                output_per_worker=output_per_worker,
                regeneration_per_turn=regeneration_per_turn,
                stock_ceiling=remaining_stock + regeneration_per_turn + 1,  # never binds the clamp
            )
        else:
            deposit = _deposit(
                category=ResourceCategory.IRON_ORE,
                remaining_stock=remaining_stock,
                extraction_capacity_per_turn=extraction_capacity_per_turn,
                output_per_worker=output_per_worker,
            )

        required = compute_required_workers(deposit)

        allocation = DepositAllocationResult(
            category=deposit.category,
            required_workers=required,
            allocated_workers=min(allocated_workers, required),
        )
        result = compute_deposit_extraction(deposit=deposit, allocation=allocation)

        assert result.closing_stock >= 0
        assert result.extracted <= result.available_stock
        assert result.opening_stock + result.regenerated == result.extracted + result.closing_stock
        if not is_renewable:
            assert result.regenerated == 0

        # Determinism: repeat calls with the same inputs produce the same result.
        result_again = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        assert result == result_again

    @given(
        weights=st.lists(st.integers(min_value=0, max_value=100_000), min_size=8, max_size=8),
        budget=st.integers(min_value=0, max_value=500_000),
    )
    @settings(max_examples=1000)
    def test_sub_allocation_bounds_and_total_hold_for_arbitrary_inputs(
        self, weights: list[int], budget: int
    ) -> None:
        required = dict(zip(ResourceCategory, weights, strict=True))
        results = allocate_extraction_workers(
            required_by_category=required, extraction_sector_workers=budget
        )
        for r in results:
            assert 0 <= r.allocated_workers <= r.required_workers
        assert sum(r.allocated_workers for r in results) == min(budget, sum(weights))


# --- Isolation: an all-inactive default economy never derives nonzero extraction ----------------


def test_default_factory_economy_has_all_inactive_resource_deposits() -> None:
    """`make_resource_deposits()`'s default (via `make_economy()`) must be a genuine no-op: zero
    required workers regardless of how many workers the extraction sector allocates, so adding
    this field could not have changed any pre-Phase-2C1 test's figures."""
    economy = make_economy()
    for deposit in economy.resource_deposits:
        assert compute_required_workers(deposit) == 0
