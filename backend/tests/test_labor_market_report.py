"""Tests for `LaborMarketReport`/`SectorLaborAllocationReport`'s self-validation (mirroring
`test_tax_base_report.py`'s pattern for `TaxBaseDerivationReport`).

`_effective_labor_force_does_not_exceed_population` is deliberately not exercised here via
`model_validate` corruption: given `0 <= effective_labor_force_share_bps <= 10_000`
(`StrictBps`, enforced at the field level before any model validator runs) and
`total_population >= 0` (`StrictWorkerCount`), `_effective_labor_force_matches_formula` — which
runs first — makes "formula-consistent but exceeds population" mathematically unreachable
through ordinary JSON reconstruction. It is genuine defense-in-depth against a fully bypassed
construction, exactly like `TaxBaseCoefficients`'s range backstops in `invariants.py` — see
`test_invariants.py`'s bypassed-construction tests for the equivalent proof at the state layer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import DecisionSet
from app.simulation.report import LaborMarketReport, SectorLaborAllocationReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import SectorCategory
from tests.conftest import make_game_state


def _valid_labor_market_report_dict() -> dict:
    """A real, internally-consistent `LaborMarketReport` (via the actual resolver, not
    hand-built), dumped to a plain dict so tests can corrupt one field."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    labor_market = resolution.report.labor_market
    assert labor_market is not None
    return labor_market.model_dump(mode="json")


def _valid_sector_allocation_report() -> SectorLaborAllocationReport:
    return SectorLaborAllocationReport(
        category=SectorCategory.MANUFACTURING,
        required_workers=10,
        allocated_workers=7,
        unfilled_workers=3,
    )


def test_a_valid_labor_market_report_round_trips_through_model_validate() -> None:
    data = _valid_labor_market_report_dict()
    report = LaborMarketReport.model_validate(data)
    assert len(report.sectors) == len(SectorCategory)


class TestSectorLaborAllocationReportSelfValidation:
    def test_valid_sector_report_constructs_cleanly(self) -> None:
        report = _valid_sector_allocation_report()
        assert report.allocated_workers == 7

    def test_allocated_exceeding_required_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exceeds"):
            SectorLaborAllocationReport(
                category=SectorCategory.MANUFACTURING,
                required_workers=10,
                allocated_workers=11,
                unfilled_workers=0,
            )

    def test_allocated_equal_to_required_is_valid(self) -> None:
        report = SectorLaborAllocationReport(
            category=SectorCategory.MANUFACTURING,
            required_workers=10,
            allocated_workers=10,
            unfilled_workers=0,
        )
        assert report.unfilled_workers == 0

    def test_wrong_unfilled_workers_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unfilled_workers"):
            SectorLaborAllocationReport(
                category=SectorCategory.MANUFACTURING,
                required_workers=10,
                allocated_workers=7,
                unfilled_workers=999,  # should be 3
            )


class TestLaborMarketReportSelfValidation:
    def test_duplicate_sector_category_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["sectors"][1]["category"] = data["sectors"][0]["category"]
        with pytest.raises(ValidationError, match="duplicate sector category"):
            LaborMarketReport.model_validate(data)

    def test_missing_sector_category_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["sectors"].pop()
        with pytest.raises(ValidationError, match="missing sector categories"):
            LaborMarketReport.model_validate(data)

    def test_sectors_supplied_out_of_order_are_normalized_not_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["sectors"] = list(reversed(data["sectors"]))
        report = LaborMarketReport.model_validate(data)
        assert [s.category.value for s in report.sectors] == [c.value for c in SectorCategory]

    def test_corrupted_effective_labor_force_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["effective_labor_force"] = int(data["effective_labor_force"]) + 1
        with pytest.raises(ValidationError, match="effective_labor_force"):
            LaborMarketReport.model_validate(data)

    def test_corrupted_total_labor_demand_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["total_labor_demand"] = int(data["total_labor_demand"]) + 1
        with pytest.raises(ValidationError, match="total_labor_demand"):
            LaborMarketReport.model_validate(data)

    def test_corrupted_total_employment_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["total_employment"] = int(data["total_employment"]) + 1
        with pytest.raises(ValidationError, match="total_employment"):
            LaborMarketReport.model_validate(data)

    def test_corrupted_unemployed_workers_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["unemployed_workers"] = int(data["unemployed_workers"]) + 1
        with pytest.raises(ValidationError, match="unemployed_workers"):
            LaborMarketReport.model_validate(data)

    def test_corrupted_unfilled_jobs_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        data["unfilled_jobs"] = int(data["unfilled_jobs"]) + 1
        with pytest.raises(ValidationError, match="unfilled_jobs"):
            LaborMarketReport.model_validate(data)

    def test_corrupted_unemployment_rate_bps_is_rejected(self) -> None:
        data = _valid_labor_market_report_dict()
        original = int(data["unemployment_rate_bps"])
        data["unemployment_rate_bps"] = original + 1 if original < 10_000 else original - 1
        with pytest.raises(ValidationError, match="unemployment_rate_bps"):
            LaborMarketReport.model_validate(data)

    def test_zero_labor_force_yields_zero_unemployment_rate_and_round_trips(self) -> None:
        report = LaborMarketReport(
            total_population=0,
            effective_labor_force_share_bps=10_000,
            effective_labor_force=0,
            sectors=tuple(
                SectorLaborAllocationReport(
                    category=category, required_workers=0, allocated_workers=0, unfilled_workers=0
                )
                for category in SectorCategory
            ),
            total_labor_demand=0,
            total_employment=0,
            unemployed_workers=0,
            unfilled_jobs=0,
            unemployment_rate_bps=0,
        )
        assert report.unemployment_rate_bps == 0

    def test_sector_row_allocation_exceeding_its_own_demand_is_rejected(self) -> None:
        """A sector row whose own `allocated_workers > required_workers` is rejected at the
        row level (`SectorLaborAllocationReport`'s own validator) before the report-level
        aggregate checks even get a chance to run.
        """
        data = _valid_labor_market_report_dict()
        data["sectors"][0]["allocated_workers"] = int(data["sectors"][0]["required_workers"]) + 1
        with pytest.raises(ValidationError):
            LaborMarketReport.model_validate(data)
