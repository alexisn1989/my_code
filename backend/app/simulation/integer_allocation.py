"""A category-agnostic, order-sensitive largest-remainder allocation core.

This is the exact Phase 2B3 labor-allocation algorithm (formerly the body of
`labor_allocation.allocate_workers`), extracted verbatim into its own module because the
algorithm itself has no labor-specific content — it never names `SectorCategory`, only ever reads
weights and a budget. Phase 2C1's resource extraction needs the identical deterministic
allocation, and importing it out of a labor-specific module would be the wrong dependency
direction; this module has no knowledge of labor or resources at all.

No I/O, no randomness, no state mutation — a plain function of its arguments.

## Contract: ORDER-SENSITIVE, not permutation-independent

`largest_remainder_allocation` accepts `weights_by_category` as a tuple of `(category, weight)`
pairs **already in the caller's canonical order**, and resolves every remainder tie by that
caller-supplied position (ties go to the earliest-positioned category among those tied). It
returns results in the same order. Pairing each weight with its category identity from the first
line does **not**, by itself, make the tie-break permutation-independent — reordering the input
tuple can legitimately change which tied category receives a leftover unit, since the tie-break
key is `(-remainder, position)`.

Permutation independence, where it's needed, is a property callers must establish **before**
calling this function, not something this function provides. `labor_allocation.allocate_workers`
sidesteps the question entirely: it keeps its existing `tuple[tuple[SectorCategory, int], ...]`
signature, unchanged, and callers already pass it in canonical `SectorCategory` order (as they did
before this module existed) — so its behavior is byte-for-byte identical to the pre-refactor
Phase 2B3 algorithm. `resource_extraction.allocate_extraction_workers` (Phase 2C1) is the one
caller that genuinely needs permutation independence — it accepts a `Mapping[ResourceCategory,
int]` (whose iteration order is not a contract worth depending on) and explicitly canonicalizes
to `tuple(ResourceCategory)` order before ever reaching this function, so mapping insertion order
provably cannot reach the tie-break.

Ties are never broken by comparing `CategoryT` values themselves, which need not support
ordering — only by input position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

CategoryT = TypeVar("CategoryT")


@dataclass(frozen=True, slots=True)
class AllocationResult(Generic[CategoryT]):
    """One category's computed allocation result: what it asked for (`weight`) and what it
    received (`allocated`), always `0 <= allocated <= weight`."""

    category: CategoryT
    weight: int
    allocated: int


def largest_remainder_allocation(
    *,
    weights_by_category: tuple[tuple[CategoryT, int], ...],
    budget: int,
) -> tuple[AllocationResult[CategoryT], ...]:
    """Deterministic largest-remainder allocation of `budget` units across the categories in
    `weights_by_category`, in the exact order supplied. See the module docstring for the
    order-sensitivity contract.

    `allocated_i <= weight_i` always: in the abundant branch (`total_weight <= budget`) trivially
    (`allocated_i == weight_i`); in the scarce branch, `budget < total_weight` implies
    `floor_i <= weight_i - 1` whenever `weight_i > 0` (so even the +1 leftover unit cannot push
    `allocated_i` past `weight_i`), and `floor_i == 0 == weight_i` whenever `weight_i == 0`.
    `leftover` is always strictly less than the number of categories with positive weight, so no
    category receives more than one extra unit.

    `sum(allocated) == min(budget, total_weight)` always — the abundant branch returns every
    weight exactly, and the scarce branch's floors plus exactly `leftover` ones-units sum to
    `budget` by construction.
    """
    total_weight = sum(weight for _, weight in weights_by_category)

    if total_weight <= budget:
        # Abundant (or exactly sufficient) budget: every category gets exactly what it asked for.
        return tuple(
            AllocationResult(category=category, weight=weight, allocated=weight)
            for category, weight in weights_by_category
        )

    # Scarce: proportional floor allocation, then distribute the leftover units to the categories
    # with the largest remainders, ties broken by ascending input position (the order
    # `weights_by_category` is already in — see the module docstring's order-sensitivity note).
    floors: list[int] = []
    remainders: list[int] = []
    for _, weight in weights_by_category:
        numerator = budget * weight
        floors.append(numerator // total_weight)
        remainders.append(numerator % total_weight)

    leftover = budget - sum(floors)

    # Sort indices by (-remainder, position) so the largest remainder wins and ties break by
    # ascending input position — Python's sort is stable, but we sort explicitly on both keys so
    # the tie-break is provable from the sort key alone, not an incidental stability artifact.
    order = sorted(range(len(weights_by_category)), key=lambda i: (-remainders[i], i))
    bonus = [0] * len(weights_by_category)
    for i in order[:leftover]:
        bonus[i] = 1

    return tuple(
        AllocationResult(category=category, weight=weight, allocated=floors[i] + bonus[i])
        for i, (category, weight) in enumerate(weights_by_category)
    )
