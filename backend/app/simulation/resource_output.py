"""Pure Phase 2C2 physical-extraction-to-real-output bridge.

No I/O, no randomness, no state mutation — plain functions of their arguments, callable
independently of the phase pipeline (and directly by tests), mirroring `resource_extraction.py`'s
and `production_accounting.py`'s existing patterns. `phases.py` calls these, inside
`resolve_production_and_trade` (phase 3) immediately after `_extract_resources`, to compute the
numbers stored on `ResourceDepositReport`/`ResourceExtractionReport` and to derive the extraction
sector's `SectorProductionReport` row — **replacing**, never adding to, that sector's former
`allocated_workers * output_per_worker` formula (see `docs/adr/0008-…`). `ResourceDepositReport`/
`ResourceExtractionReport` themselves independently re-derive and check these same formulas from
their own stored fields on construction (see `report.py`) — deliberately not the same code path.

## Actual and potential contributions

    contribution_i           = extracted_i * real_output_per_unit_i             [exact, no division]
    potential_quantity_i      = min(available_stock_i, extraction_capacity_per_turn_i)
    potential_contribution_i  = potential_quantity_i * real_output_per_unit_i    [exact, no division]

Both conversions route through the single named
`core.quantity.extracted_resource_to_real_output` bridge — called once on the actually-extracted
quantity, once on the potential (stock/capacity-bounded, labor-independent) quantity. No division
anywhere on this path: there is no rounding step and therefore no rounding policy to get wrong.

`potential_quantity_i` reuses `DepositExtractionResult.available_stock`/`.extraction_capacity_per_turn`
— both already computed by `resource_extraction.compute_deposit_extraction` — so this module never
imports from, and never modifies, `resource_extraction.py`.

## Aggregation

    extraction_sector_real_output      = sum(contribution_i)            [i in canonical order]
    extraction_sector_potential_output = sum(potential_contribution_i)  [i in canonical order]

Both sums are over homogeneous `RealOutput` values (never raw physical quantities — tonnes,
barrels, and cubic metres are never summed together, mirroring D4 of ADR 0007).

## The `actual <= potential` guarantee, proved once here, relied on throughout Phase 2C2

Per deposit (2C1, `resource_extraction.py`, unmodified): `extracted_i = min(available_i,
capacity_i, allocated_i * opw_i)`. Since this `min` includes the same two terms as
`potential_quantity_i = min(available_i, capacity_i)` plus one additional term,
`extracted_i <= potential_quantity_i` unconditionally — dropping a `min` term can only keep or
raise the result. Multiplying by the same positive coefficient and summing both preserve the
inequality, so `extraction_sector_real_output <= extraction_sector_potential_output` always holds
*by construction* — the reason `SectorProductionReport`'s `capacity_utilization_bps` for the
extraction row never needs a clamp (see `report.py`, `classify_extraction_constraint`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.quantity import RealOutput, ResourceQuantity, extracted_resource_to_real_output
from app.simulation.resource_extraction import DepositExtractionResult
from app.simulation.state import ResourceCategory


@dataclass(frozen=True, slots=True)
class ResourceOutputContribution:
    """One deposit's fully computed Phase 2C2 output-contribution result — every value a
    `ResourceDepositReport` row's new fields need, before it becomes part of that row."""

    category: ResourceCategory
    extracted: ResourceQuantity
    potential_quantity: ResourceQuantity
    real_output_per_unit: int
    real_output_contribution: RealOutput
    potential_output_contribution: RealOutput


def compute_resource_output_contributions(
    *,
    extraction_results: tuple[DepositExtractionResult, ...],
    coefficients: Mapping[ResourceCategory, int],
) -> tuple[ResourceOutputContribution, ...]:
    """Verifies both inputs cover all eight `ResourceCategory` members exactly once, then iterates
    `tuple(ResourceCategory)` — canonical order, never `extraction_results`'/`coefficients`'
    incoming order — calling the bridge twice per category: once on `extracted`, once on
    `potential_quantity := min(result.available_stock, result.extraction_capacity_per_turn)`.
    """
    results_by_category = {r.category: r for r in extraction_results}
    provided_results = set(results_by_category)
    canonical = set(ResourceCategory)
    missing_results = canonical - provided_results
    unknown_results = provided_results - canonical
    if missing_results or unknown_results:
        raise ValueError(
            "extraction_results must cover exactly the eight ResourceCategory members, once "
            f"each; missing={sorted(c.value for c in missing_results)!r} "
            f"unknown={sorted(repr(k) for k in unknown_results)!r}"
        )

    provided_coefficients = set(coefficients)
    missing_coefficients = canonical - provided_coefficients
    unknown_coefficients = provided_coefficients - canonical
    if missing_coefficients or unknown_coefficients:
        raise ValueError(
            "coefficients must cover exactly the eight ResourceCategory members, once each; "
            f"missing={sorted(c.value for c in missing_coefficients)!r} "
            f"unknown={sorted(repr(k) for k in unknown_coefficients)!r}"
        )

    contributions: list[ResourceOutputContribution] = []
    for category in ResourceCategory:
        result = results_by_category[category]
        coefficient = coefficients[category]
        potential_quantity = min(result.available_stock, result.extraction_capacity_per_turn)
        contributions.append(
            ResourceOutputContribution(
                category=category,
                extracted=result.extracted,
                potential_quantity=potential_quantity,
                real_output_per_unit=coefficient,
                real_output_contribution=extracted_resource_to_real_output(
                    extracted=result.extracted, real_output_per_unit=coefficient
                ),
                potential_output_contribution=extracted_resource_to_real_output(
                    extracted=potential_quantity, real_output_per_unit=coefficient
                ),
            )
        )
    return tuple(contributions)


def aggregate_extraction_sector_output(
    contributions: tuple[ResourceOutputContribution, ...],
) -> tuple[RealOutput, RealOutput]:
    """Deterministic sums of homogeneous `RealOutput` contributions, in canonical order (the
    order `contributions` is already in, since `compute_resource_output_contributions` always
    returns it that way). Returns `(actual_total, potential_total)` — callers (`phases.py`, and
    independently `report.py`'s `TurnReport` cross-validator) use both to derive the extraction
    row's `capacity_utilization_bps`/`constraint` (see `report.classify_extraction_constraint`).
    """
    actual_total = sum(c.real_output_contribution for c in contributions)
    potential_total = sum(c.potential_output_contribution for c in contributions)
    return actual_total, potential_total
