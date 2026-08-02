"""Pure Phase 2B1 sector production formulas.

No I/O, no randomness, no state mutation — plain functions of their
arguments, callable independently of the phase pipeline (and directly by
tests). `phases.py` calls these to compute the numbers it stores on
`ProductionReport`; `ProductionReport` itself independently re-derives and
checks these same formulas from its own stored fields on construction (see
`report.py`) rather than trusting whatever `phases.py` handed it — the two
are deliberately not the same code path, so a bug in one is likely to be
caught by the other.

## Formulas (all integer, all floored, no randomness)

Per sector::

    labor_limited_output    = employed_workers * output_per_worker
    actual_output            = min(quarterly_capacity_output, labor_limited_output)
    capacity_utilization_bps = floor(actual_output * 10_000 / quarterly_capacity_output)
                                if quarterly_capacity_output > 0 else 0

Floor division is used for the same reason `core.money.apply_bps` floors:
it guarantees `capacity_utilization_bps == 10_000` if and only if
`actual_output == quarterly_capacity_output` exactly — a rounded value could
falsely report "100% utilized" for a sector that is genuinely short of full
capacity by a rounding margin, inside a hash-protected, self-validating
report where every derived number must be exactly recomputable.

## Classification

    if quarterly_capacity_output == 0:                        INACTIVE
    elif labor_limited_output <  quarterly_capacity_output:    LABOR_CONSTRAINED
    elif labor_limited_output >  quarterly_capacity_output:    CAPACITY_CONSTRAINED
    else:                                                      EXACTLY_BALANCED

Capacity is checked *first*. This resolves the degenerate case
`quarterly_capacity_output == 0 and employed_workers == 0` as `INACTIVE`
rather than the trivial `labor_limited_output (0) == quarterly_capacity_output (0)`
reading of "exactly balanced" — a sector with no capacity at all has not
achieved full utilization of anything. Conversely, `quarterly_capacity_output
> 0 and employed_workers == 0` is `LABOR_CONSTRAINED`, not `INACTIVE`: capacity
exists and is simply unstaffed, a materially different fact from "this
sector has no capacity." See `docs/economy_methodology.md` for the full
worked derivation and both edge cases.

## Terminology

These are "gross sector output at fixed base-year prices" / "production
capacity" / "labor-limited output" / "capacity utilization" — never GDP,
value added, real GDP, inflation, or economic growth. No value-added
accounting exists yet, so summing sector output (`total_gross_output`) can
include intermediate production and must not be read as GDP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.money import BPS_DENOMINATOR
from app.core.quantity import StrictRealOutput
from app.simulation.state import SectorState


class SectorConstraint(StrEnum):
    CAPACITY_CONSTRAINED = "capacity_constrained"
    LABOR_CONSTRAINED = "labor_constrained"
    EXACTLY_BALANCED = "exactly_balanced"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class SectorProductionResult:
    """One sector's computed Phase 2B1 production result, before it becomes a report row."""

    labor_limited_output: StrictRealOutput
    actual_output: StrictRealOutput
    capacity_utilization_bps: int
    constraint: SectorConstraint


def compute_sector_output(sector: SectorState) -> SectorProductionResult:
    """Apply the formulas and classification rule documented in the module docstring
    to one sector's inputs. Pure — reads only `sector`'s own fields."""
    labor_limited_output = sector.employed_workers * sector.output_per_worker
    actual_output = min(sector.quarterly_capacity_output, labor_limited_output)

    if sector.quarterly_capacity_output > 0:
        capacity_utilization_bps = (
            actual_output * BPS_DENOMINATOR
        ) // sector.quarterly_capacity_output
    else:
        capacity_utilization_bps = 0

    if sector.quarterly_capacity_output == 0:
        constraint = SectorConstraint.INACTIVE
    elif labor_limited_output < sector.quarterly_capacity_output:
        constraint = SectorConstraint.LABOR_CONSTRAINED
    elif labor_limited_output > sector.quarterly_capacity_output:
        constraint = SectorConstraint.CAPACITY_CONSTRAINED
    else:
        constraint = SectorConstraint.EXACTLY_BALANCED

    return SectorProductionResult(
        labor_limited_output=labor_limited_output,
        actual_output=actual_output,
        capacity_utilization_bps=capacity_utilization_bps,
        constraint=constraint,
    )


@dataclass(frozen=True, slots=True)
class ProductionAggregates:
    total_employment: StrictRealOutput
    total_gross_output: StrictRealOutput


def aggregate_production(
    sectors: tuple[SectorState, ...], results: tuple[SectorProductionResult, ...]
) -> ProductionAggregates:
    """Sum employment (from inputs) and actual output (from computed results) across all sectors.
    `sectors`/`results` must be the same length and in the same order (the caller — the
    `resolve_production_and_trade` phase — always builds them together, one result per sector).
    """
    return ProductionAggregates(
        total_employment=sum(sector.employed_workers for sector in sectors),
        total_gross_output=sum(result.actual_output for result in results),
    )
