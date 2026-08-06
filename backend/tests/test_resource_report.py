"""Tests for `ResourceExtractionReport`/`ResourceDepositReport`'s self-validation (T11),
mirroring `test_labor_market_report.py`'s/`test_production_report.py`'s pattern: every derived
field — including the two new R1 fields (`regeneration_per_turn`/`stock_ceiling`) and the
renewability-rule validator — is independently re-checked on construction, on every path (a
fresh build, `model_validate` parsing stored JSON back out, or `model_validate_json` from history).

Unlike `ProductionReport.sectors`/`LaborMarketReport.sectors`, noncanonical order in
`ResourceExtractionReport.deposits` is REJECTED, not normalized (R3) — the trailing tests here
invert the corresponding production-report tests accordingly.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.simulation.decisions import DecisionSet
from app.simulation.report import ResourceDepositReport, ResourceExtractionReport
from app.simulation.resolver import resolve_turn
from app.simulation.resource_extraction import DepositStatus
from app.simulation.state import ResourceCategory, ResourceDepositState
from tests.conftest import make_country, make_economy, make_game_state


def _valid_resource_report_dict() -> dict:
    """A real, internally-consistent `ResourceExtractionReport` (via the actual resolver, not
    hand-built), dumped to a plain dict so tests can corrupt one field. Deliberately scarce
    (extraction-sector budget=1 under `make_economy`'s uniform sector defaults, total resource
    demand=20) so the TIMBER row exercises every field non-trivially, including regeneration and
    the ceiling clamp.
    """
    deposits = (
        ResourceDepositState(
            category=ResourceCategory.TIMBER,
            remaining_stock=1_000,
            extraction_capacity_per_turn=100,
            output_per_worker=10,
            regeneration_per_turn=20,
            stock_ceiling=2_000,
        ),
        ResourceDepositState(
            category=ResourceCategory.IRON_ORE,
            remaining_stock=500,
            extraction_capacity_per_turn=50,
            output_per_worker=5,
        ),
        *(
            ResourceDepositState(
                category=category,
                remaining_stock=0,
                extraction_capacity_per_turn=0,
                output_per_worker=1,
            )
            for category in ResourceCategory
            if category not in (ResourceCategory.TIMBER, ResourceCategory.IRON_ORE)
        ),
    )
    economy = make_economy(resource_deposits=deposits)
    country = make_country("testland", economy=economy)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    resources = resolution.report.resources
    assert resources is not None
    return resources.model_dump(mode="json")


def _valid_deposit_report() -> ResourceDepositReport:
    return ResourceDepositReport(
        category=ResourceCategory.TIMBER,
        opening_stock=1_000,
        regeneration_per_turn=20,
        stock_ceiling=2_000,
        regenerated=20,
        available_stock=1_020,
        extraction_capacity_per_turn=100,
        output_per_worker=10,
        required_workers=10,
        allocated_workers=1,
        extracted=10,
        closing_stock=1_010,
        status=DepositStatus.LABOR_CONSTRAINED,
        real_output_per_unit=1,
        real_output_contribution=10,
        potential_output_contribution=100,
    )


def test_a_valid_resource_report_round_trips_through_model_validate() -> None:
    data = _valid_resource_report_dict()
    report = ResourceExtractionReport.model_validate(data)
    assert len(report.deposits) == len(ResourceCategory)


def test_a_valid_resource_report_round_trips_through_model_validate_json() -> None:
    data = _valid_resource_report_dict()
    report = ResourceExtractionReport.model_validate_json(json.dumps(data))
    assert len(report.deposits) == len(ResourceCategory)


class TestResourceDepositReportSelfValidation:
    def test_valid_deposit_report_constructs_cleanly(self) -> None:
        report = _valid_deposit_report()
        assert report.extracted == 10

    def test_wrong_regenerated_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="regenerated"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=999,  # should be 20
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_regenerated_exceeding_the_ceiling_clamp_is_rejected(self) -> None:
        """The row's own `regeneration_per_turn`/`stock_ceiling` are the inputs to the clamp
        formula (R1) — an under-reported `regenerated` (still within the ceiling, so the
        renewability-rule validator alone can't catch it) must still be independently re-derived
        and rejected by the dedicated formula check. True clamp here is
        `min(20, 2000-1990) = 10`; `regenerated=5` is wrong but small enough that
        `available_stock=1995` still respects the ceiling, isolating this specific validator.
        """
        with pytest.raises(ValidationError, match="regenerated"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_990,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=5,  # should be clamped to 10
                available_stock=1_995,  # internally consistent with the (wrong) regenerated=5
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_985,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_nonrenewable_with_nonzero_regeneration_per_turn_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nonrenewable"):
            ResourceDepositReport(
                category=ResourceCategory.IRON_ORE,
                opening_stock=500,
                regeneration_per_turn=1,  # must be 0 for a nonrenewable
                stock_ceiling=None,
                regenerated=0,
                available_stock=500,
                extraction_capacity_per_turn=50,
                output_per_worker=5,
                required_workers=10,
                allocated_workers=10,
                extracted=50,
                closing_stock=450,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=50,
                potential_output_contribution=50,
            )

    def test_nonrenewable_with_a_stock_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nonrenewable"):
            ResourceDepositReport(
                category=ResourceCategory.IRON_ORE,
                opening_stock=500,
                regeneration_per_turn=0,
                stock_ceiling=1_000,  # must be None for a nonrenewable
                regenerated=0,
                available_stock=500,
                extraction_capacity_per_turn=50,
                output_per_worker=5,
                required_workers=10,
                allocated_workers=10,
                extracted=50,
                closing_stock=450,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=50,
                potential_output_contribution=50,
            )

    def test_renewable_without_a_stock_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="renewable"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=None,  # renewable must declare a ceiling
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_available_stock_exceeding_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exceeds stock_ceiling"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_995,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=5,  # matches the clamp formula...
                available_stock=2_005,  # ...but this claims MORE than the ceiling allows
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_995,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_wrong_available_stock_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="available_stock"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=999,  # should be 1020
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_wrong_required_workers_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="required_workers"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=999,  # should be ceil(min(1020,100)/10) = 10
                allocated_workers=1,
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_allocated_exceeding_required_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exceeds"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=11,  # exceeds required_workers
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_wrong_extracted_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extracted"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=999,  # should be min(1020, 100, 1*10)=10
                closing_stock=1_010,
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_wrong_closing_stock_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="closing_stock"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=999,  # should be 1020 - 10 = 1010
                status=DepositStatus.LABOR_CONSTRAINED,
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_wrong_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="status"):
            ResourceDepositReport(
                category=ResourceCategory.TIMBER,
                opening_stock=1_000,
                regeneration_per_turn=20,
                stock_ceiling=2_000,
                regenerated=20,
                available_stock=1_020,
                extraction_capacity_per_turn=100,
                output_per_worker=10,
                required_workers=10,
                allocated_workers=1,
                extracted=10,
                closing_stock=1_010,
                status=DepositStatus.CAPACITY_CONSTRAINED,  # should be labor_constrained
                real_output_per_unit=1,
                real_output_contribution=10,
                potential_output_contribution=100,
            )

    def test_output_per_worker_zero_is_rejected_at_the_field_level(self) -> None:
        with pytest.raises(ValidationError):
            ResourceDepositReport(
                category=ResourceCategory.IRON_ORE,
                opening_stock=0,
                regeneration_per_turn=0,
                stock_ceiling=None,
                regenerated=0,
                available_stock=0,
                extraction_capacity_per_turn=0,
                output_per_worker=0,
                required_workers=0,
                allocated_workers=0,
                extracted=0,
                closing_stock=0,
                status=DepositStatus.INACTIVE,
                real_output_per_unit=1,
                real_output_contribution=0,
                potential_output_contribution=0,
            )

    def test_real_output_contribution_does_not_exceed_potential_validator_detects_a_direct_violation(
        self,
    ) -> None:
        """T38 (R6): the row-level backstop of §6's `actual <= potential` proof, tested directly
        via `model_construct` (skips every validator) — a different granularity from the
        `ResourceExtractionReport`-level check above."""
        valid_row = _valid_deposit_report()
        unvalidated = ResourceDepositReport.model_construct(
            **{
                **valid_row.__dict__,
                "real_output_contribution": valid_row.potential_output_contribution + 1,
            }
        )
        with pytest.raises(ValueError, match="exceeds"):
            ResourceDepositReport._real_output_contribution_does_not_exceed_potential(unvalidated)


class TestResourceExtractionReportSelfValidation:
    def test_corrupted_total_extraction_workers_is_rejected(self) -> None:
        data = _valid_resource_report_dict()
        data["total_extraction_workers"] = int(data["total_extraction_workers"]) + 1
        with pytest.raises(ValidationError, match="total_extraction_workers"):
            ResourceExtractionReport.model_validate(data)

    def test_corrupted_unassigned_resource_workers_is_rejected(self) -> None:
        data = _valid_resource_report_dict()
        data["unassigned_resource_workers"] = int(data["unassigned_resource_workers"]) + 1
        with pytest.raises(ValidationError, match="unassigned_resource_workers"):
            ResourceExtractionReport.model_validate(data)

    def test_total_does_not_exceed_sector_workers_validator_detects_a_direct_violation(
        self,
    ) -> None:
        """`_total_does_not_exceed_sector_workers` restates, as one inequality, something the
        `_unassigned_matches_sector_workers_minus_total` check already implies: if
        `total_extraction_workers > extraction_sector_workers`, the correctly-computed
        `unassigned_resource_workers` would be negative — impossible for a `StrictWorkerCount` —
        so the unassigned check always fires first under ordinary corruption. This mirrors
        `FinanceReport`'s provably-redundant aggregate cash-flow equation (see
        `test_finance_report.py`): tested directly, via `model_construct` (which skips every
        validator), rather than through the full pipeline.
        """
        valid_report = ResourceExtractionReport.model_validate(_valid_resource_report_dict())
        unvalidated = ResourceExtractionReport.model_construct(
            **{**valid_report.__dict__, "extraction_sector_workers": 0}
        )
        with pytest.raises(ValueError, match="exceeds"):
            ResourceExtractionReport._total_does_not_exceed_sector_workers(unvalidated)

    def test_extraction_sector_real_output_does_not_exceed_potential_validator_detects_a_direct_violation(
        self,
    ) -> None:
        """T38 (R6): the aggregate-level backstop of §6's `actual <= potential` proof, tested
        directly via `model_construct` (skips every validator) — proving this check catches a
        corruption independently of the row-level `_real_output_contribution_does_not_exceed_
        potential` check on `ResourceDepositReport` (a different granularity, tested separately
        below)."""
        valid_report = ResourceExtractionReport.model_validate(_valid_resource_report_dict())
        unvalidated = ResourceExtractionReport.model_construct(
            **{
                **valid_report.__dict__,
                "extraction_sector_real_output": valid_report.extraction_sector_potential_output
                + 1,
            }
        )
        with pytest.raises(ValueError, match="exceeds"):
            ResourceExtractionReport._extraction_sector_real_output_does_not_exceed_potential(
                unvalidated
            )

    def test_duplicate_resource_category_is_rejected(self) -> None:
        data = _valid_resource_report_dict()
        # Duplicate two already-inactive (zero-stock, nonrenewable-shaped) rows' categories so
        # the renewability-rule validator stays satisfied regardless of which label either row
        # claims — isolating the report-level duplicate-category check specifically.
        inactive_indices = [i for i, d in enumerate(data["deposits"]) if d["stock_ceiling"] is None]
        assert len(inactive_indices) >= 2
        i, j = inactive_indices[0], inactive_indices[1]
        data["deposits"][j]["category"] = data["deposits"][i]["category"]
        with pytest.raises(ValidationError, match="duplicate resource category"):
            ResourceExtractionReport.model_validate(data)

    def test_missing_resource_category_is_rejected(self) -> None:
        data = _valid_resource_report_dict()
        data["deposits"].pop()
        with pytest.raises(ValidationError, match="missing resource categories"):
            ResourceExtractionReport.model_validate(data)

    def test_deposits_supplied_out_of_order_are_rejected_not_normalized(self) -> None:
        """R3: unlike `ProductionReport.sectors`, noncanonical order in `deposits` is REJECTED,
        never silently normalized."""
        data = _valid_resource_report_dict()
        data["deposits"] = list(reversed(data["deposits"]))
        with pytest.raises(ValidationError, match="not in canonical ResourceCategory order"):
            ResourceExtractionReport.model_validate(data)


def test_two_logically_identical_reports_in_different_order_are_both_rejected() -> None:
    """R3's inversion of the production-report precedent: two reports built from the same
    deposit data but supplied in a different input order are NOT both accepted and normalized to
    the same canonical JSON — the reordered one is rejected outright."""
    data = _valid_resource_report_dict()
    forward = ResourceExtractionReport.model_validate(data)
    assert forward.deposits[0].category == ResourceCategory.TIMBER

    reordered_data = {**data, "deposits": list(reversed(data["deposits"]))}
    with pytest.raises(ValidationError, match="not in canonical ResourceCategory order"):
        ResourceExtractionReport.model_validate(reordered_data)
