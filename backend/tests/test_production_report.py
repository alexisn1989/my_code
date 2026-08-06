"""Tests for `ProductionReport`/`SectorProductionReport`'s self-validation,
mirroring `test_finance_report.py`'s pattern: every derived field is
independently re-checked on construction, on every path — a fresh build,
`model_validate` parsing stored JSON back out, or CLI history inspection all
go through the same `@model_validator` methods.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.money import BPS_DENOMINATOR
from app.simulation.decisions import DecisionSet
from app.simulation.production_accounting import SectorConstraint
from app.simulation.report import (
    ProductionReport,
    SectorOutputBasis,
    SectorProductionConstraint,
    SectorProductionReport,
    classify_extraction_constraint,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import SectorCategory
from tests.conftest import make_game_state


def _valid_extraction_sector_report(
    *, potential_output: int = 100, actual_output: int = 100, employed_workers: int = 7
) -> SectorProductionReport:
    """A RESOURCE_EXTRACTION-basis row, built directly (not via the resolver) so tests can
    control `potential_output`/`actual_output` precisely. `capacity_output`/`output_per_worker`
    are set to values that would make the pre-2C2 STANDARD formula misbehave, on purpose — R6/T15
    proves they're read nowhere on this basis.
    """
    return SectorProductionReport(
        category=SectorCategory.EXTRACTION,
        output_basis=SectorOutputBasis.RESOURCE_EXTRACTION,
        capacity_output=1,
        output_per_worker=1,
        employed_workers=employed_workers,
        labor_limited_output=actual_output,
        actual_output=actual_output,
        capacity_utilization_bps=(
            (actual_output * BPS_DENOMINATOR) // potential_output if potential_output > 0 else 0
        ),
        constraint=classify_extraction_constraint(
            potential_output=potential_output, actual_output=actual_output
        ),
    )


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
        output_basis=SectorOutputBasis.STANDARD,
        capacity_output=1000,
        output_per_worker=100,
        employed_workers=5,
        labor_limited_output=500,
        actual_output=500,
        capacity_utilization_bps=5_000,
        constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
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
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=999,  # should be 500
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_actual_output_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="actual_output"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=999,  # should be min(1000, 500) = 500
                capacity_utilization_bps=5_000,
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_capacity_utilization_bps_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="capacity_utilization_bps"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=9_999,  # should be 5000
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
            )

    def test_wrong_constraint_classification_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="constraint"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorProductionConstraint.EXACTLY_BALANCED,  # should be labor_constrained
            )

    def test_output_per_worker_zero_is_rejected_at_the_field_level(self) -> None:
        with pytest.raises(ValidationError):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=0,
                employed_workers=5,
                labor_limited_output=0,
                actual_output=0,
                capacity_utilization_bps=0,
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
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
        # Indices 2/3 (MANUFACTURING/CONSTRUCTION) are both STANDARD-basis — avoids index 1
        # (EXTRACTION), whose output_basis would otherwise trip
        # `_output_basis_matches_category` before this duplicate-category check ever runs.
        data = _valid_production_report_dict()
        data["sectors"][3]["category"] = data["sectors"][2]["category"]
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


class TestOutputBasisStructuralDesign:
    """T14: `output_basis` is forced entirely by category identity — never an authored or
    scenario choice — and the STANDARD-basis validators remain byte-for-byte identical to the
    pre-2C2 formulas."""

    def test_output_basis_matches_category_for_a_standard_sector(self) -> None:
        report = _valid_sector_report()
        assert report.category is SectorCategory.MANUFACTURING
        assert report.output_basis is SectorOutputBasis.STANDARD

    def test_output_basis_matches_category_for_the_extraction_sector(self) -> None:
        report = _valid_extraction_sector_report()
        assert report.category is SectorCategory.EXTRACTION
        assert report.output_basis is SectorOutputBasis.RESOURCE_EXTRACTION

    def test_standard_category_with_resource_extraction_basis_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="output_basis"):
            SectorProductionReport(
                category=SectorCategory.MANUFACTURING,
                output_basis=SectorOutputBasis.RESOURCE_EXTRACTION,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
            )

    def test_extraction_category_with_standard_basis_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="output_basis"):
            SectorProductionReport(
                category=SectorCategory.EXTRACTION,
                output_basis=SectorOutputBasis.STANDARD,
                capacity_output=1000,
                output_per_worker=100,
                employed_workers=5,
                labor_limited_output=500,
                actual_output=500,
                capacity_utilization_bps=5_000,
                constraint=SectorProductionConstraint.LABOR_CONSTRAINED,
            )

    def test_standard_validators_are_untouched_by_the_extraction_basis_branch(self) -> None:
        """The ten non-extraction sectors' formulas are exercised by the pre-existing
        `TestSectorProductionReportSelfValidation` tests above, unmodified in substance — this is
        an explicit regression pin that a STANDARD row still round-trips with the exact same
        field values as before Phase 2C2, output_basis aside."""
        report = _valid_sector_report()
        dumped = report.model_dump(mode="json")
        assert dumped["output_basis"] == "standard"
        assert dumped["constraint"] == "labor_constrained"
        assert dumped["actual_output"] == 500


class TestNoClampNeededForExtractionUtilization:
    """T15: R6 replaced the saturating clamp with a formula (against `potential_output`, not
    nominal `capacity_output`) that never exceeds `StrictBps`'s `le=10_000` bound by
    construction. `capacity_output`/`output_per_worker` are proven inert for this basis: a
    combination that would have blown the pre-2C2 formula way past 10,000 bps (`capacity_output=1`
    against a large `actual_output`) constructs cleanly because `capacity_utilization_bps` is
    supplied independently, from the potential-output-based formula, never derived from
    `capacity_output` on this basis.
    """

    def test_extraction_row_constructs_cleanly_despite_a_tiny_legacy_capacity_output(self) -> None:
        report = _valid_extraction_sector_report(potential_output=100_000, actual_output=50_000)
        assert report.capacity_output == 1
        assert report.capacity_utilization_bps == 5_000

    def test_extraction_row_at_the_maximum_bound_constructs_cleanly(self) -> None:
        report = _valid_extraction_sector_report(potential_output=100, actual_output=100)
        assert report.capacity_utilization_bps == BPS_DENOMINATOR

    def test_extraction_row_capacity_utilization_bps_never_needs_clamping(self) -> None:
        for potential, actual in [(1, 1), (10**12, 10**12), (10**12, 0), (7, 3), (0, 0)]:
            report = _valid_extraction_sector_report(
                potential_output=potential, actual_output=actual
            )
            assert 0 <= report.capacity_utilization_bps <= BPS_DENOMINATOR

    def test_zero_potential_output_gives_zero_utilization_by_the_defined_convention(self) -> None:
        """T37 (R6): `potential_output == 0` implies `actual_output == 0` too (§6's proof), and
        `capacity_utilization_bps` is defined as exactly `0` in that case — not a
        `ZeroDivisionError`, not an arbitrary sentinel."""
        report = _valid_extraction_sector_report(potential_output=0, actual_output=0)
        assert report.capacity_utilization_bps == 0
        assert report.constraint is SectorProductionConstraint.INACTIVE


class TestExtractionConstraintRejectedNotClassified:
    """T16 (R9): `actual_output > potential_output` is an invalid state, rejected by
    `classify_extraction_constraint` itself — never assigned a business status."""

    def test_actual_exceeding_potential_is_rejected_not_classified(self) -> None:
        with pytest.raises(ValueError, match="exceeds potential_output"):
            classify_extraction_constraint(potential_output=100, actual_output=101)

    def test_actual_exceeding_potential_never_returns_a_value(self) -> None:
        """Belt-and-suspenders: confirm the function's only response to an invalid pair is to
        raise — there is no code path where it returns any `SectorProductionConstraint` member
        for `actual_output > potential_output`, e.g. by falling through to a default."""
        for potential, actual in [(0, 1), (1, 2), (10**12, 10**12 + 1)]:
            with pytest.raises(ValueError, match="exceeds potential_output"):
                classify_extraction_constraint(potential_output=potential, actual_output=actual)


class TestExtractionConstraintZeroEmploymentConsistency:
    """T16a (R9): zero employment with positive potential stays LABOR_CONSTRAINED, matching the
    2B1 precedent that potential/capacity existing but unstaffed is a labor fact, not an
    inactivity fact."""

    def test_zero_actual_with_positive_potential_is_labor_constrained_not_inactive(self) -> None:
        assert (
            classify_extraction_constraint(potential_output=100, actual_output=0)
            is SectorProductionConstraint.LABOR_CONSTRAINED
        )

    def test_zero_potential_is_inactive(self) -> None:
        assert (
            classify_extraction_constraint(potential_output=0, actual_output=0)
            is SectorProductionConstraint.INACTIVE
        )

    def test_zero_employment_extraction_sector_report_constructs_as_labor_constrained(
        self,
    ) -> None:
        report = _valid_extraction_sector_report(
            potential_output=100, actual_output=0, employed_workers=0
        )
        assert report.constraint is SectorProductionConstraint.LABOR_CONSTRAINED


class TestExtractionConstraintDeterministicTieSemantics:
    """T16b (R9): the classification depends only on `(potential_output, actual_output)` — it
    does not, and cannot, distinguish "labor was exactly sufficient" from "labor was abundant and
    the resource itself was the true ceiling"; both produce PHYSICAL_RESOURCE_CONSTRAINED."""

    def test_tie_is_physical_resource_constrained_regardless_of_employment_level(self) -> None:
        scarce_labor = classify_extraction_constraint(potential_output=100, actual_output=100)
        # The function signature has no employment parameter at all — calling it identically
        # twice, as would happen for both a scarce-but-sufficient and an abundant-labor scenario
        # that happen to realize the same (potential, actual) pair, is the proof itself.
        abundant_labor = classify_extraction_constraint(potential_output=100, actual_output=100)
        assert (
            scarce_labor
            is abundant_labor
            is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED
        )

    def test_extraction_sector_report_at_the_tie_point_constructs_as_physical_resource_constrained(
        self,
    ) -> None:
        report = _valid_extraction_sector_report(potential_output=250, actual_output=250)
        assert report.constraint is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED


class TestSectorProductionConstraintValueParity:
    """T16c: `SectorProductionConstraint`'s four members shared with
    `production_accounting.SectorConstraint` keep identical string values, so a STANDARD row's
    canonical JSON is byte-for-byte unaffected by the enum-type swap (§5.4)."""

    def test_shared_member_values_are_identical(self) -> None:
        shared_names = {"CAPACITY_CONSTRAINED", "LABOR_CONSTRAINED", "EXACTLY_BALANCED", "INACTIVE"}
        assert shared_names == {member.name for member in SectorConstraint}
        for name in shared_names:
            assert SectorConstraint[name].value == SectorProductionConstraint[name].value

    def test_physical_resource_constrained_has_no_counterpart_in_the_engine_enum(self) -> None:
        assert "PHYSICAL_RESOURCE_CONSTRAINED" not in {m.name for m in SectorConstraint}
        assert "PHYSICAL_RESOURCE_CONSTRAINED" in {m.name for m in SectorProductionConstraint}

    def test_standard_row_canonical_json_constraint_value_is_a_plain_string(self) -> None:
        report = _valid_sector_report()
        assert (
            report.model_dump(mode="json")["constraint"] == SectorConstraint.LABOR_CONSTRAINED.value
        )
