"""Pure Phase 2C1 resource-endowment regeneration, extraction, and depletion formulas.

No I/O, no randomness, no state mutation — plain functions of their arguments, callable
independently of the phase pipeline (and directly by tests), mirroring
`production_accounting.py`'s and `labor_allocation.py`'s existing patterns. `phases.py` calls
these, inside `resolve_production_and_trade` (phase 3) immediately after labor allocation, to
compute the numbers stored on `ResourceExtractionReport` — and, per
`docs/adr/0007-resource-endowments-and-extraction.md` (R2), to write each deposit's resulting
`closing_stock` back into the working `EconomyState.resource_deposits` in that same step.
`ResourceExtractionReport` itself independently re-derives and checks these same formulas from its
own stored fields on construction (see `report.py`) — deliberately not the same code path.

## Regeneration and available stock

    regenerated = 0                                                    [nonrenewable]
                = max(0, min(regeneration_per_turn,
                             stock_ceiling - remaining_stock))         [renewable]

    available = remaining_stock + regenerated

Regeneration happens *before* extraction each turn — growth accrues over the quarter and is
harvestable within it. `ResourceDepositState`'s own validators already guarantee
`stock_ceiling >= remaining_stock` for renewables and `stock_ceiling is None` for nonrenewables,
so `regenerated` is always well-defined and never exceeds the ceiling.

## Labor demand

    extractable_ceiling = min(available, extraction_capacity_per_turn)
    required_workers     = 0                                    [extractable_ceiling == 0]
                          = ceil(extractable_ceiling / output_per_worker)   [otherwise]

`output_per_worker` is strictly positive (`StrictResourceQuantityPerWorker`), so no
division-by-zero path exists. Integer ceiling division only, computed as
`(extractable_ceiling + opw - 1) // opw` — a full-capacity staffing requirement, not observed
demand, mirroring `labor_allocation.compute_required_workers`.

## Allocation

The extraction *sector's* allocated workers (already computed by `labor_allocation` earlier this
same phase) are the budget, sub-allocated across the eight deposits by the shared
`integer_allocation.largest_remainder_allocation` core. Unlike `labor_allocation.allocate_workers`
(which keeps a tuple input, already in canonical order, unchanged from Phase 2B3),
`allocate_extraction_workers` below takes a category-keyed *mapping* and explicitly canonicalizes
to `tuple(ResourceCategory)` order before calling the core — so permuting the mapping's insertion
order cannot change the result. See `integer_allocation`'s module docstring (R7) for why this
split exists.

## Extraction and conservation

    extracted     = min(available, extraction_capacity_per_turn,
                        allocated_workers * output_per_worker)
    closing_stock = available - extracted

Exact conservation holds by construction, every deposit, every turn:

    remaining_stock + regenerated == extracted + closing_stock

`closing_stock` is *defined* as `available - extracted`, and `extracted <= available` because
`available` is one of the three terms of the `min` — there is no path to a negative
`closing_stock`.

## Status classification

    if extraction_capacity_per_turn == 0:            INACTIVE
    elif available == 0:                             DEPLETED
    elif extracted == available:                     STOCK_CONSTRAINED
    elif extracted == extraction_capacity_per_turn:   CAPACITY_CONSTRAINED
    else:                                             LABOR_CONSTRAINED

Checked top-down so exactly one status applies, mirroring `production_accounting.SectorConstraint`.
Capacity is checked first (a deposit with zero capacity is inactive regardless of stock or
labor); stock exhaustion is checked before the stock/capacity *tie* case, so a deposit whose
`available` stock exactly equals its `extraction_capacity_per_turn` — extracting everything it
has, at exactly the rate its capacity allows — reports `STOCK_CONSTRAINED`, not
`CAPACITY_CONSTRAINED`: it was the stock, not the capacity, that determined the outcome that
turn, even though the two bounds happened to coincide. See `docs/economy_methodology.md` for a
fully worked multi-turn example of this exact boundary.

## Terminology and isolation

`unassigned_resource_workers` (not "idle" — R6) are extraction-sector workers the labor market
already counts as employed, performing support, surveying, transport, or other aggregate
extraction-sector activity not assigned to a modeled deposit; they are not unemployment and are
not double-counted against `LaborMarketReport.unemployed_workers`. Heterogeneous resource
quantities (tonnes, barrels, cubic metres) are never summed together — only worker counts and
per-status counts are aggregated (D4). This module performs no conversion to `RealOutput` or
`Money`; extraction changes no production, tax base, revenue, price, trade, approval, or war
outcome this phase (D8) — see `docs/adr/0007-resource-endowments-and-extraction.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.core.quantity import ResourceQuantity, WorkerCount
from app.simulation.integer_allocation import largest_remainder_allocation
from app.simulation.state import RENEWABLE_RESOURCES, ResourceCategory, ResourceDepositState


class DepositStatus(StrEnum):
    INACTIVE = "inactive"
    DEPLETED = "depleted"
    STOCK_CONSTRAINED = "stock_constrained"
    CAPACITY_CONSTRAINED = "capacity_constrained"
    LABOR_CONSTRAINED = "labor_constrained"


def compute_regeneration(deposit: ResourceDepositState) -> ResourceQuantity:
    """`0` for nonrenewables; for renewables, `max(0, min(regeneration_per_turn, stock_ceiling -
    remaining_stock))` — clamped so the ceiling is never exceeded. Pure — reads only `deposit`'s
    own fields."""
    if deposit.category not in RENEWABLE_RESOURCES:
        return 0
    # ResourceDepositState's own validator guarantees stock_ceiling is not None here.
    ceiling = deposit.stock_ceiling
    assert ceiling is not None, "renewable deposit without a stock_ceiling should be unreachable"
    return max(0, min(deposit.regeneration_per_turn, ceiling - deposit.remaining_stock))


def compute_available_stock(deposit: ResourceDepositState) -> ResourceQuantity:
    """`remaining_stock + compute_regeneration(deposit)`. Pure — reads only `deposit`'s own
    fields."""
    return deposit.remaining_stock + compute_regeneration(deposit)


def compute_required_workers(deposit: ResourceDepositState) -> WorkerCount:
    """Full-capacity staffing requirement for one deposit: 0 if nothing is extractable this turn
    (zero available stock or zero capacity), otherwise
    `ceil(min(available_stock, extraction_capacity_per_turn) / output_per_worker)`. Pure — reads
    only `deposit`'s own fields."""
    extractable_ceiling = min(
        compute_available_stock(deposit), deposit.extraction_capacity_per_turn
    )
    if extractable_ceiling == 0:
        return 0
    opw = deposit.output_per_worker
    return (extractable_ceiling + opw - 1) // opw


@dataclass(frozen=True, slots=True)
class DepositAllocationResult:
    """One deposit's computed Phase 2C1 sub-allocation result, before it becomes part of a
    report row."""

    category: ResourceCategory
    required_workers: WorkerCount
    allocated_workers: WorkerCount


def allocate_extraction_workers(
    *,
    required_by_category: Mapping[ResourceCategory, int],
    extraction_sector_workers: WorkerCount,
) -> tuple[DepositAllocationResult, ...]:
    """Deterministic largest-remainder allocation of the extraction sector's workers across the
    eight resource deposits, always returned in canonical `ResourceCategory` order.

    `required_by_category` must be a mapping covering every `ResourceCategory` exactly once — its
    *insertion order does not matter*: this function builds the `(category, weight)` pairs in
    `tuple(ResourceCategory)` order before delegating to the shared, order-sensitive
    `integer_allocation.largest_remainder_allocation` core (R7), so permuting the mapping's
    insertion order provably cannot change the result. This is the one deliberate difference from
    `labor_allocation.allocate_workers`, which keeps a tuple already in canonical order.
    """
    provided = set(required_by_category)
    canonical = set(ResourceCategory)
    missing = canonical - provided
    unknown = provided - canonical
    if missing or unknown:
        raise ValueError(
            "required_by_category must cover exactly the eight ResourceCategory members, once "
            f"each; missing={sorted(c.value for c in missing)!r} "
            f"unknown={sorted(repr(k) for k in unknown)!r}"
        )

    ordered_pairs = tuple(
        (category, required_by_category[category]) for category in ResourceCategory
    )
    results = largest_remainder_allocation(
        weights_by_category=ordered_pairs, budget=extraction_sector_workers
    )
    return tuple(
        DepositAllocationResult(
            category=r.category, required_workers=r.weight, allocated_workers=r.allocated
        )
        for r in results
    )


@dataclass(frozen=True, slots=True)
class DepositExtractionResult:
    """One deposit's fully computed Phase 2C1 extraction result — every value a
    `ResourceDepositReport` row needs, before it becomes that row."""

    category: ResourceCategory
    opening_stock: ResourceQuantity
    regeneration_per_turn: ResourceQuantity
    stock_ceiling: ResourceQuantity | None
    regenerated: ResourceQuantity
    available_stock: ResourceQuantity
    extraction_capacity_per_turn: ResourceQuantity
    output_per_worker: ResourceQuantity
    required_workers: WorkerCount
    allocated_workers: WorkerCount
    extracted: ResourceQuantity
    closing_stock: ResourceQuantity
    status: DepositStatus


def compute_deposit_extraction(
    *, deposit: ResourceDepositState, allocation: DepositAllocationResult
) -> DepositExtractionResult:
    """Apply the formulas and classification rule documented in the module docstring to one
    deposit's inputs plus its already-computed worker allocation. Pure — reads only `deposit`'s
    own fields and `allocation`'s two ints."""
    regenerated = compute_regeneration(deposit)
    available = deposit.remaining_stock + regenerated
    extracted = min(
        available,
        deposit.extraction_capacity_per_turn,
        allocation.allocated_workers * deposit.output_per_worker,
    )
    closing_stock = available - extracted

    if deposit.extraction_capacity_per_turn == 0:
        status = DepositStatus.INACTIVE
    elif available == 0:
        status = DepositStatus.DEPLETED
    elif extracted == available:
        status = DepositStatus.STOCK_CONSTRAINED
    elif extracted == deposit.extraction_capacity_per_turn:
        status = DepositStatus.CAPACITY_CONSTRAINED
    else:
        status = DepositStatus.LABOR_CONSTRAINED

    return DepositExtractionResult(
        category=deposit.category,
        opening_stock=deposit.remaining_stock,
        regeneration_per_turn=deposit.regeneration_per_turn,
        stock_ceiling=deposit.stock_ceiling,
        regenerated=regenerated,
        available_stock=available,
        extraction_capacity_per_turn=deposit.extraction_capacity_per_turn,
        output_per_worker=deposit.output_per_worker,
        required_workers=allocation.required_workers,
        allocated_workers=allocation.allocated_workers,
        extracted=extracted,
        closing_stock=closing_stock,
        status=status,
    )


@dataclass(frozen=True, slots=True)
class ExtractionAggregates:
    extraction_sector_workers: WorkerCount
    total_extraction_workers: WorkerCount
    unassigned_resource_workers: WorkerCount
    status_counts: dict[DepositStatus, int]


def aggregate_extraction(
    *,
    extraction_sector_workers: WorkerCount,
    results: tuple[DepositExtractionResult, ...],
) -> ExtractionAggregates:
    """Sum worker allocation and per-status counts across all eight deposits — never a summed
    physical quantity (D4): tonnes, barrels, and cubic metres cannot be meaningfully added
    together."""
    total_extraction_workers = sum(r.allocated_workers for r in results)
    status_counts: dict[DepositStatus, int] = {status: 0 for status in DepositStatus}
    for r in results:
        status_counts[r.status] += 1

    return ExtractionAggregates(
        extraction_sector_workers=extraction_sector_workers,
        total_extraction_workers=total_extraction_workers,
        unassigned_resource_workers=extraction_sector_workers - total_extraction_workers,
        status_counts=status_counts,
    )
