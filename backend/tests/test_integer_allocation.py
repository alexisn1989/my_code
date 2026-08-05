"""Tests for the neutral, category-agnostic `integer_allocation.largest_remainder_allocation`
core (Phase 2C1, D7/R7) — extracted verbatim from the Phase 2B3 labor-allocation algorithm.

The central contract this module pins down is R7's: the core is **order-sensitive by design**,
not permutation-independent. `test_labor_allocation.py` proves the labor wrapper is byte-identical
to the pre-refactor algorithm (T8); `test_resource_extraction.py` proves the resource wrapper is
permutation-independent despite the core not being so (T9). This file proves the core itself,
directly, matches neither of those — it just does exactly what its docstring says.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.simulation.integer_allocation import largest_remainder_allocation


class TestAbundantAndExactBranches:
    def test_abundant_budget_allocates_exactly_each_weight(self) -> None:
        pairs = (("a", 10), ("b", 20), ("c", 5))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=100)
        assert [(r.category, r.allocated) for r in results] == [("a", 10), ("b", 20), ("c", 5)]
        assert all(r.allocated == r.weight for r in results)

    def test_exactly_sufficient_budget_allocates_exactly_each_weight(self) -> None:
        pairs = (("a", 30), ("b", 70))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=100)
        assert sum(r.allocated for r in results) == 100
        assert all(r.allocated == r.weight for r in results)

    def test_zero_total_weight_with_positive_budget_allocates_nothing(self) -> None:
        pairs = (("a", 0), ("b", 0))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=100)
        assert all(r.allocated == 0 for r in results)

    def test_empty_input_with_zero_budget(self) -> None:
        results = largest_remainder_allocation(weights_by_category=(), budget=0)
        assert results == ()


class TestScarceBranch:
    def test_scarce_budget_uses_largest_remainder(self) -> None:
        # total=100, budget=53: a floor(53*30/100)=15 rem=90; b floor(53*30/100)=15 rem=90;
        # c floor(53*40/100)=21 rem=20. sum(floors)=51, leftover=2 -> the two largest (tied)
        # remainders each get +1, in input position order (a then b).
        pairs = (("a", 30), ("b", 30), ("c", 40))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=53)
        by_category = {r.category: r.allocated for r in results}
        assert by_category["a"] == 16
        assert by_category["b"] == 16
        assert by_category["c"] == 21
        assert sum(by_category.values()) == 53

    def test_never_allocates_above_weight_even_under_scarcity(self) -> None:
        pairs = (("a", 1), ("b", 1), ("c", 1))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=2)
        assert all(r.allocated <= r.weight for r in results)
        assert sum(r.allocated for r in results) == 2


class TestOrderSensitivity:
    """Pins R7's central contract: this core is order-sensitive by design, not permutation-
    independent — carrying category identity alongside each weight does not by itself make the
    tie-break immune to input order. Callers needing permutation independence (only
    `resource_extraction.allocate_extraction_workers`) must canonicalize before calling."""

    def test_reordering_tied_inputs_can_change_which_category_gets_the_leftover_unit(self) -> None:
        # Two categories tied at remainder 0.5 each (weight=1, total=2, budget=1): whichever is
        # positioned FIRST in the input tuple wins the sole leftover unit. This is not a
        # coincidence of implementation — it's the documented, tested contract.
        forward = largest_remainder_allocation(weights_by_category=(("a", 1), ("b", 1)), budget=1)
        reversed_ = largest_remainder_allocation(weights_by_category=(("b", 1), ("a", 1)), budget=1)
        forward_winner = next(r.category for r in forward if r.allocated == 1)
        reversed_winner = next(r.category for r in reversed_ if r.allocated == 1)
        assert forward_winner == "a"
        assert reversed_winner == "b"
        assert forward_winner != reversed_winner

    def test_non_orderable_category_values_are_accepted(self) -> None:
        """Tie-breaking is purely by input position, never by comparing category values — so
        `CategoryT` need not support ordering. A plain unhashable-comparison object (only
        equality, no `<`) as the category proves this."""

        class Opaque:
            def __init__(self, label: str) -> None:
                self.label = label

        a, b = Opaque("a"), Opaque("b")
        results = largest_remainder_allocation(weights_by_category=((a, 1), (b, 1)), budget=1)
        assert results[0].category is a
        assert results[1].category is b
        assert results[0].allocated == 1  # first position wins the tie


class TestAllocationResultInvariants:
    @given(
        weights=st.lists(st.integers(min_value=0, max_value=1000), min_size=0, max_size=15),
        budget=st.integers(min_value=0, max_value=5000),
    )
    @settings(max_examples=1000)
    def test_bounds_and_total_hold_for_arbitrary_inputs(
        self, weights: list[int], budget: int
    ) -> None:
        pairs = tuple((f"cat{i}", w) for i, w in enumerate(weights))
        results = largest_remainder_allocation(weights_by_category=pairs, budget=budget)

        assert len(results) == len(pairs)
        for r in results:
            assert 0 <= r.allocated <= r.weight

        total_weight = sum(weights)
        assert sum(r.allocated for r in results) == min(budget, total_weight)

    @given(
        weights=st.lists(st.integers(min_value=0, max_value=1000), min_size=0, max_size=15),
        budget=st.integers(min_value=0, max_value=5000),
    )
    @settings(max_examples=1000)
    def test_deterministic_across_repeat_calls(self, weights: list[int], budget: int) -> None:
        pairs = tuple((f"cat{i}", w) for i, w in enumerate(weights))
        first = largest_remainder_allocation(weights_by_category=pairs, budget=budget)
        second = largest_remainder_allocation(weights_by_category=pairs, budget=budget)
        assert first == second
