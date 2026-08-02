"""Tests for `ProductionReport`/`SectorProductionReport`'s self-validation,
mirroring `test_finance_report.py`'s pattern: every derived field is
independently re-checked on construction, on every path — a fresh build,
`model_validate` parsing stored JSON back out, or CLI history inspection all
go through the same `@model_validator` methods.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import DecisionSet
from app.simulation.production_accounting import SectorConstraint
from app.simulation.report import ProductionReport, SectorProductionReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import SectorCategory
from tests.conftest import make_game_state


def _valid_production_report_dict() -> dict:
    """A real, internally-consistent `ProductionReport` (via the actual resolver,
    not hand-built), dumped to a plain dict so tests can corrupt one field."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    production = resolution.report.production
    assert production is not None
    return production.model_dump(mode="json")


def _valid_sector_report() -> SectorProductionReport:
    return SectorProductionReport(
        category=SectorCategory.MANUFACTURING,
        capacity_output=1000,
        output_per_worker=100,
        employed_workers=5,
        labor_limited_output=500,
        actual_output=500,
        capacity_utilization_bps=5_000,
        constraint=SectorConstraint.LABOR_CONSTRAINED,
    )


def test_a_valid_production_report_round_trips_through_model_validate() -> None:
    data = _valid_production_report_dict()
    report = ProductionReport.model_validate(data)
    assert len(report.sectors) == len(SectorCategory)


class TestSectorProductionReportSelfValidation:
    def test_valid_sector_report_constructs_cleanly(self) -> None:
        report = _valid_sector_report()
        assert report.actual_output == 500

    def test_wrong_labor_limited_output_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="labor_limited_output"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=999,  # should be 500
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_actual_output_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="actual_output"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=999,  # should be min(1000, 500) = 500
                capacity_utilization_bps=5_000,
                constraint=SectorConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_capacity_utilization_bps_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="capacity_utilization_bps"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=9_999,  # should be 5000
                constraint=SectorConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_constraint_classification_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="constraint"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorConstraint.EXACTLY_BALANCED,  # should be labor_constrained
            )

    def test_output_per_worker_zero_is_rejected_at_the_field_level(self) -> None:
        with pytest.raises(ValidationError):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                capacity_output=1000,
                output_per_worker=0,
                employed_workers=5,
                labor_limited_output=0,
                actual_output=0,
                capacity_utilization_bps=0,
                constraint=SectorConstraint.LABOR_CONSTRAINED,
            )


class TestProductionReportSelfValidation:
    @pytest.mark.parametrize(
        ("field", "expected_message_substring"),
        [
            ("total_employment", "total_employment"),
            ("total_gross_output", "total_gross_output"),
        ],
    )
    def test_corrupted_total_fails_with_its_own_specific_error(
        self, field: str, expected_message_substring: str
    ) -> None:
        data = _valid_production_report_dict()
        data[field] = int(data[field]) + 1
        with pytest.raises(ValidationError) as exc_info:
            ProductionReport.model_validate(data)
        assert expected_message_substring in str(exc_info.value)

    def test_duplicate_sector_category_is_rejected(self) -> None:
        data = _valid_production_report_dict()
        data["sectors"][1]["category"] = data["sectors"][0]["category"]
        with pytest.raises(ValidationError, match="duplicate sector category"):
            ProductionReport.model_validate(data)

    def test_missing_sector_category_is_rejected(self) -> None:
        data = _valid_production_report_dict()
        data["sectors"].pop()
        with pytest.raises(ValidationError, match="missing sector categories"):
            ProductionReport.model_validate(data)

    def test_sectors_supplied_out_of_order_are_normalized_not_rejected(self) -> None:
        """R3: prefer normalization over rejection for ordering alone."""
        data = _valid_production_report_dict()
        data["sectors"] = list(reversed(data["sectors"]))
        report = ProductionReport.model_validate(data)
        assert [s.category.value for s in report.sectors] == [c.value for c in SectorCategory]


def test_two_logically_identical_reports_in_different_order_serialize_identically() -> None:
    """R3: two reports built from the same sector data but supplied in a
    different input order must normalize to byte-identical canonical JSON."""
    data = _valid_production_report_dict()
    forward = ProductionReport.model_validate(data)

    reordered_data = {**data, "sectors": list(reversed(data["sectors"]))}
    reversed_report = ProductionReport.model_validate(reordered_data)

    assert forward.model_dump(mode="json") == reversed_report.model_dump(mode="json")
