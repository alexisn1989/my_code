"""Pure Phase 2B2 production-derived tax-base formulas.

No I/O, no randomness, no state mutation — plain functions of their arguments, callable
independently of the phase pipeline (and directly by tests), mirroring
`production_accounting.py`'s and `accounting.py`'s existing patterns. `phases.py` calls these,
reading each sector's `actual_output` from the already-computed `ProductionReport` (never
re-deriving it), to compute the numbers stored on `TaxBaseDerivationReport`.
`TaxBaseDerivationReport` itself independently re-derives and checks these same formulas from its
own stored fields on construction (see `report.py`) — the two are deliberately not the same code
path, so a bug in one is likely to be caught by the other, exactly as `accounting.py`/
`FinanceReport` and `production_accounting.py`/`ProductionReport` already do.

## The unit bridge

`actual_output` is fixed-base-year **real** output (`app.core.quantity.RealOutput`). Every
formula below stays in real units until the very end, where per-sector contributions are summed
nationally and converted to nominal `Money` through exactly one call to
`app.core.quantity.base_year_real_output_to_money` — see that function's docstring for why the
conversion is a named function, not an implicit `int` pass-through.

## Formulas (all integer, all floored, no randomness)

Per sector::

    modeled_value_added = floor(actual_output       * value_added_share_bps / 10_000)
    labor_income        = floor(modeled_value_added * labor_income_share_bps / 10_000)
    operating_surplus   = modeled_value_added - labor_income          # exact, no rounding

    personal_contribution    = floor(labor_income        * personal_taxable_share_bps          / 10_000)
    corporate_contribution   = floor(operating_surplus   * corporate_taxable_share_bps         / 10_000)
    consumption_contribution = floor(modeled_value_added * effective_consumption_base_share_bps / 10_000)

`operating_surplus` is computed by subtraction, not a second floored share, specifically so
`labor_income + operating_surplus == modeled_value_added` holds exactly for every input — there is
no rounding gap to explain away.

National tax bases are the **sum of per-sector contributions**, not a value recomputed from
national aggregates: `sum(floor(xi * r)) <= floor(sum(xi) * r)` in general (the gap can be up to
n-1), so summing per-sector floors is the only definition under which every reported national
figure is exactly the sum of the rows shown beneath it.

## Terminology

`modeled_value_added` is an explicitly-named internal decomposition proxy — `actual_output * an
authored share` — not national-accounts value added, GDP, or economic growth. It exists to prevent
gross-output double counting *within this derivation*, nothing more. `effective_consumption_base_
share_bps` is a deliberately reduced-form, country-level coefficient: it currently combines
household final-demand composition, government-vs-private consumption, exports/other non-domestic
demand, and exemptions/fiscal coverage into one number, because Phase 2B2 does not model final
demand or trade separately. See `docs/economy_methodology.md` and
`docs/adr/0005-production-derived-tax-bases.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.quantity import RealOutput, base_year_real_output_to_money
from app.simulation.state import TaxBaseCoefficients, TaxBaseState


@dataclass(frozen=True, slots=True)
class SectorTaxBaseResult:
    """One sector's computed Phase 2B2 tax-base contribution, before it becomes a report row."""

    modeled_value_added: RealOutput
    labor_income: RealOutput
    operating_surplus: RealOutput
    personal_contribution: RealOutput
    corporate_contribution: RealOutput
    consumption_contribution: RealOutput


def compute_sector_tax_base_contribution(
    *,
    actual_output: RealOutput,
    value_added_share_bps: int,
    labor_income_share_bps: int,
    coefficients: TaxBaseCoefficients,
) -> SectorTaxBaseResult:
    """Apply the formulas documented in the module docstring to one sector's already-computed
    `actual_output` (read from `ProductionReport`, not re-derived) plus its structural shares and
    the country's fiscal coefficients. Pure — no other inputs.
    """
    modeled_value_added = (actual_output * value_added_share_bps) // BPS_DENOMINATOR
    labor_income = (modeled_value_added * labor_income_share_bps) // BPS_DENOMINATOR
    operating_surplus = modeled_value_added - labor_income

    personal_contribution = (
        labor_income * coefficients.personal_taxable_share_bps
    ) // BPS_DENOMINATOR
    corporate_contribution = (
        operating_surplus * coefficients.corporate_taxable_share_bps
    ) // BPS_DENOMINATOR
    consumption_contribution = (
        modeled_value_added * coefficients.effective_consumption_base_share_bps
    ) // BPS_DENOMINATOR

    return SectorTaxBaseResult(
        modeled_value_added=modeled_value_added,
        labor_income=labor_income,
        operating_surplus=operating_surplus,
        personal_contribution=personal_contribution,
        corporate_contribution=corporate_contribution,
        consumption_contribution=consumption_contribution,
    )


@dataclass(frozen=True, slots=True)
class TaxBaseAggregates:
    total_modeled_value_added: RealOutput
    total_labor_income: RealOutput
    total_operating_surplus: RealOutput
    derived_tax_bases: TaxBaseState
    """The nominal `Money` bases handed to `accounting.compute_tax_revenue`, produced by summing
    per-sector real contributions and converting through `base_year_real_output_to_money` —
    the single real-to-nominal conversion point for this phase."""


def aggregate_tax_base_contributions(
    results: tuple[SectorTaxBaseResult, ...],
) -> TaxBaseAggregates:
    """Sum per-sector contributions into national totals, converting the three tax-base sums to
    `Money` at the very end (see the module docstring's "unit bridge" section)."""
    total_modeled_value_added = sum(r.modeled_value_added for r in results)
    total_labor_income = sum(r.labor_income for r in results)
    total_operating_surplus = sum(r.operating_surplus for r in results)

    total_personal = sum(r.personal_contribution for r in results)
    total_corporate = sum(r.corporate_contribution for r in results)
    total_consumption = sum(r.consumption_contribution for r in results)

    derived_tax_bases = TaxBaseState(
        personal_income=base_year_real_output_to_money(total_personal),
        corporate_profit=base_year_real_output_to_money(total_corporate),
        taxable_consumption=base_year_real_output_to_money(total_consumption),
    )

    return TaxBaseAggregates(
        total_modeled_value_added=total_modeled_value_added,
        total_labor_income=total_labor_income,
        total_operating_surplus=total_operating_surplus,
        derived_tax_bases=derived_tax_bases,
    )
