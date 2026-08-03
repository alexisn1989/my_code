"""Pure Phase 2B3 labor-supply, labor-demand, and deterministic-allocation formulas.

No I/O, no randomness, no state mutation — plain functions of their arguments, callable
independently of the phase pipeline (and directly by tests), mirroring `production_accounting.py`'s
and `tax_base_derivation.py`'s existing patterns. `phases.py` calls these, at the start of
`resolve_production_and_trade`, to compute the numbers stored on `LaborMarketReport`; production
then consumes the resulting `allocated_workers` per sector instead of reading an authored field.
`LaborMarketReport` itself independently re-derives and checks these same formulas from its own
stored fields on construction (see `report.py`) — deliberately not the same code path, so a bug in
one is likely to be caught by the other, exactly as the finance/production/tax-base pairs already do.

## Labor supply (reduced form)

    effective_labor_force = floor(population * effective_labor_force_share_bps / 10_000)

`effective_labor_force_share_bps` temporarily combines working-age share, labor-force
participation, and any other structural availability factor into one coefficient — see
`docs/economy_methodology.md` and ADR 0006 for why this is deliberately a placeholder, mirroring
`TaxBaseCoefficients.effective_consumption_base_share_bps` (ADR 0005 R4). Since
`0 <= effective_labor_force_share_bps <= 10_000` (`StrictBps`) and `population >= 0`, floor
division gives `0 <= effective_labor_force <= population` by construction.

## Sector labor demand

Full-capacity staffing requirement — *not* observed vacancies, wage-based demand, or
profit-maximizing employment:

    required_workers = 0                                              if quarterly_capacity_output == 0
                     = ceil(quarterly_capacity_output / output_per_worker)   otherwise

`output_per_worker` is strictly positive (`StrictRealOutputPerWorker`), so no division-by-zero
path exists. Integer ceiling division only, computed as `(capacity + opw - 1) // opw`.

## Deterministic allocation (largest-remainder method)

    total_labor_demand = sum(required_workers over all sectors)

    if total_labor_demand <= effective_labor_force:      # abundant or exactly equal
        allocated[i] = required[i]
    else:                                                 # scarce
        floor_i     = (effective_labor_force * required_i) // total_labor_demand
        remainder_i = (effective_labor_force * required_i) %  total_labor_demand
        leftover    = effective_labor_force - sum(floor_i)
        distribute +1 to the `leftover` sectors with the largest remainder_i,
          ties broken by ascending canonical SectorCategory declaration order

`allocated_i <= required_i` always: in the abundant branch trivially (`allocated_i == required_i`);
in the scarce branch, `effective_labor_force < total_labor_demand` implies `floor_i <= required_i -
1` whenever `required_i > 0` (so even the +1 leftover unit cannot push `allocated_i` past
`required_i`), and `floor_i == 0 == required_i` whenever `required_i == 0`. `leftover` is always
strictly less than the number of sectors with positive demand, so no sector receives more than one
extra unit.

## Identities (all nonnegative exact integers)

    total_employment       = sum(allocated_i) = min(effective_labor_force, total_labor_demand)
    unemployed_workers     = effective_labor_force - total_employment
    unfilled_jobs           = total_labor_demand   - total_employment
    unemployment_rate_bps   = floor(unemployed_workers * 10_000 / effective_labor_force)
                                if effective_labor_force > 0 else 0

`unemployment_rate_bps == 0` when the labor force is zero is a documented choice, not a division
guard worked around silently: 0/0 has no meaningful rate, and 0 is the only non-arbitrary answer.

## Terminology

None of this is a wage, hiring-friction, or participation model. Allocation is instantaneous each
turn: nothing here represents job search time, employer preference, skill matching, or sector
switching cost. See `docs/economy_methodology.md` for the full worked derivation and both scarcity
edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.quantity import WorkerCount
from app.simulation.state import SectorCategory, SectorState


def compute_effective_labor_force(
    *, population: int, effective_labor_force_share_bps: int
) -> WorkerCount:
    """`floor(population * effective_labor_force_share_bps / 10_000)`. Pure — no other inputs."""
    return (population * effective_labor_force_share_bps) // BPS_DENOMINATOR


def compute_required_workers(sector: SectorState) -> WorkerCount:
    """Full-capacity staffing requirement for one sector: 0 if the sector has no capacity,
    otherwise `ceil(quarterly_capacity_output / output_per_worker)`. Pure — reads only `sector`'s
    own fields."""
    if sector.quarterly_capacity_output == 0:
        return 0
    capacity = sector.quarterly_capacity_output
    opw = sector.output_per_worker
    return (capacity + opw - 1) // opw


@dataclass(frozen=True, slots=True)
class SectorLaborAllocationResult:
    """One sector's computed Phase 2B3 labor-allocation result, before it becomes a report row."""

    category: SectorCategory
    required_workers: WorkerCount
    allocated_workers: WorkerCount


def allocate_workers(
    *,
    required_by_category: tuple[tuple[SectorCategory, WorkerCount], ...],
    effective_labor_force: WorkerCount,
) -> tuple[SectorLaborAllocationResult, ...]:
    """Deterministic largest-remainder allocation across sectors, in canonical `SectorCategory`
    order. `required_by_category` must already be in canonical order (one entry per category,
    covering all of them) — the caller (`aggregate_labor_market`/`phases.py`) is responsible for
    that, mirroring how `production_accounting.aggregate_production` trusts its caller's ordering.

    Returns results in the same canonical order as the input.
    """
    total_labor_demand = sum(required for _, required in required_by_category)

    if total_labor_demand <= effective_labor_force:
        # Abundant (or exactly sufficient) labor: every sector gets exactly what it asked for.
        return tuple(
            SectorLaborAllocationResult(
                category=category, required_workers=required, allocated_workers=required
            )
            for category, required in required_by_category
        )

    # Scarce: proportional floor allocation, then distribute the leftover units to the sectors
    # with the largest remainders, ties broken by ascending canonical declaration order (the
    # order `required_by_category` is already in).
    floors: list[int] = []
    remainders: list[int] = []
    for _, required in required_by_category:
        numerator = effective_labor_force * required
        floors.append(numerator // total_labor_demand)
        remainders.append(numerator % total_labor_demand)

    leftover = effective_labor_force - sum(floors)

    # Sort indices by (-remainder, canonical index) so the largest remainder wins and ties break
    # by ascending canonical order — Python's sort is stable, but we sort explicitly on both keys
    # so the tie-break is provable from the sort key alone, not an incidental stability artifact.
    order = sorted(range(len(required_by_category)), key=lambda i: (-remainders[i], i))
    bonus = [0] * len(required_by_category)
    for i in order[:leftover]:
        bonus[i] = 1

    return tuple(
        SectorLaborAllocationResult(
            category=category,
            required_workers=required,
            allocated_workers=floors[i] + bonus[i],
        )
        for i, (category, required) in enumerate(required_by_category)
    )


@dataclass(frozen=True, slots=True)
class LaborMarketAggregates:
    total_population: WorkerCount
    effective_labor_force: WorkerCount
    total_labor_demand: WorkerCount
    total_employment: WorkerCount
    unemployed_workers: WorkerCount
    unfilled_jobs: WorkerCount
    unemployment_rate_bps: int


def aggregate_labor_market(
    *,
    total_population: int,
    effective_labor_force: WorkerCount,
    results: tuple[SectorLaborAllocationResult, ...],
) -> LaborMarketAggregates:
    """Sum per-sector allocation results into national totals and derive the identities
    documented in the module docstring."""
    total_labor_demand = sum(r.required_workers for r in results)
    total_employment = sum(r.allocated_workers for r in results)
    unemployed_workers = effective_labor_force - total_employment
    unfilled_jobs = total_labor_demand - total_employment
    unemployment_rate_bps = (
        (unemployed_workers * BPS_DENOMINATOR) // effective_labor_force
        if effective_labor_force > 0
        else 0
    )

    return LaborMarketAggregates(
        total_population=total_population,
        effective_labor_force=effective_labor_force,
        total_labor_demand=total_labor_demand,
        total_employment=total_employment,
        unemployed_workers=unemployed_workers,
        unfilled_jobs=unfilled_jobs,
        unemployment_rate_bps=unemployment_rate_bps,
    )
