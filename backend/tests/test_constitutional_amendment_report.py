"""Gate 3C3 commit 20: amendment report assembly and self-validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import ExecutiveSelection
from app.simulation.decisions import (
    ConstitutionalAmendmentDecision,
    DecisionSet,
    ExecutiveSelectionTarget,
)
from app.simulation.legislature import LegislativeOutcome, ProposalRoute
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.report import (
    ConstitutionalAmendmentReport,
    TurnReport,
    TurnReportDevMeta,
)
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR
from tests.test_constitutional_amendment_gating import (
    _decree_state_at_turn_three_opening,
    _liberalizing_amendment,
    _make_legislature_absent,
)


def _assembled_context(
    state: GameState, amendment: ConstitutionalAmendmentDecision
) -> PhaseContext:
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )
    working = state.model_copy(deep=True)
    resolving_turn = state.turn
    working.turn += 1
    working.state_version += 1
    ctx = PhaseContext(state=working, decisions=decisions, resolving_turn=resolving_turn)
    run_phases(ctx)
    assert ctx.constitutional_amendment_report is not None
    return ctx


def _turn_report(ctx: PhaseContext) -> TurnReport:
    return TurnReport(
        game_seed=ctx.state.seed,
        resolved_turn=ctx.resolving_turn,
        entries=ctx.report_entries,
        dev=TurnReportDevMeta(phase_statuses=ctx.phase_statuses),
        labor_market=ctx.labor_market_report,
        resources=ctx.resources_report,
        finance=ctx.finance_report,
        production=ctx.production_report,
        tax_base_derivation=ctx.tax_base_derivation_report,
        political=ctx.political_report,
        legislative=ctx.legislative_report,
        political_capital=ctx.political_capital_report,
        political_relationship=ctx.political_relationship_report,
        election=ctx.election_report,
        coup_unrest=ctx.coup_unrest_report,
        constitutional_amendment=ctx.constitutional_amendment_report,
        foreign_affairs=ctx.foreign_affairs_report,
    )


def _reports() -> tuple[
    ConstitutionalAmendmentReport,
    ConstitutionalAmendmentReport,
    ConstitutionalAmendmentReport,
    TurnReport,
]:
    passed_ctx = _assembled_context(
        _decree_state_at_turn_three_opening(), _liberalizing_amendment()
    )
    failed_ctx = _assembled_context(
        _decree_state_at_turn_three_opening(), _liberalizing_amendment(influence=299)
    )
    decree_state = _make_legislature_absent(load_scenario_file(SCENARIO_DIR / "decree_state.yaml"))
    decree_ctx = _assembled_context(
        decree_state,
        ConstitutionalAmendmentDecision(
            targets=(ExecutiveSelectionTarget(value=ExecutiveSelection.APPOINTED),),
            route=ProposalRoute.DECREE,
        ),
    )
    assert passed_ctx.constitutional_amendment_report is not None
    assert failed_ctx.constitutional_amendment_report is not None
    assert decree_ctx.constitutional_amendment_report is not None
    return (
        passed_ctx.constitutional_amendment_report,
        failed_ctx.constitutional_amendment_report,
        decree_ctx.constitutional_amendment_report,
        _turn_report(passed_ctx),
    )


def test_real_slot_15_assembly_covers_all_three_proposal_outcomes_and_round_trips() -> None:
    passed, failed, decree, turn_report = _reports()
    assert passed.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert failed.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    assert decree.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    assert passed.proposed and failed.proposed and decree.proposed

    assert failed.targets and failed.chambers and failed.influence
    assert failed.opening_constitution == failed.closing_constitution
    assert failed.opening_constitution_digest == failed.closing_constitution_digest
    assert failed.transition_pressure_added_bps == 0
    assert failed.political_capital_committed == 299

    for report in (passed, failed, decree):
        ConstitutionalAmendmentReport.model_validate(report.model_dump(mode="json"))
        ConstitutionalAmendmentReport.model_validate_json(report.model_dump_json())
    TurnReport.model_validate_json(turn_report.model_dump_json())


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["chambers"][0].update(required_yes_seats=51), "threshold"),
        (lambda data: data["targets"][0].update(opening_value="limited"), "opening value"),
        (lambda data: data["targets"][0].update(proposed_value="unlimited"), "must change"),
        (lambda data: data.update(amendment_decision_digest="0" * 63), "digest"),
        (lambda data: data.update(transition_pressure_added_bps=9_999), "pressure"),
        (lambda data: data.update(political_capital_committed=299), "influence sum"),
    ],
)
def test_passed_report_rejects_independent_corruptions(mutation: object, message: str) -> None:
    passed, _, _, _ = _reports()
    data = passed.model_dump(mode="json")
    mutation(data)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        ConstitutionalAmendmentReport.model_validate(data)


@pytest.mark.parametrize(
    ("source_index", "corrupted_outcome"),
    [
        (0, LegislativeOutcome.FAILED_LEGISLATIVE),
        (1, LegislativeOutcome.PASSED_LEGISLATIVE),
        (2, LegislativeOutcome.PASSED_LEGISLATIVE),
    ],
)
def test_route_chamber_outcome_matrix_rejects_corruption(
    source_index: int, corrupted_outcome: LegislativeOutcome
) -> None:
    reports = _reports()[:3]
    data = reports[source_index].model_dump(mode="json")
    data["outcome"] = corrupted_outcome.value
    with pytest.raises(ValidationError, match="outcome|decree route"):
        ConstitutionalAmendmentReport.model_validate(data)


def test_failed_report_rejects_a_different_valid_closing_digest() -> None:
    _, failed, _, _ = _reports()
    data = failed.model_dump(mode="json")
    replacement = "f" * 64
    assert replacement != data["opening_constitution_digest"]
    data["closing_constitution_digest"] = replacement
    with pytest.raises(ValidationError, match="preserve constitution digest"):
        ConstitutionalAmendmentReport.model_validate(data)


def test_turn_report_rejects_amendment_commitment_that_disagrees_with_ledger() -> None:
    _, _, _, turn_report = _reports()
    data = turn_report.model_dump(mode="json")
    amendment = data["constitutional_amendment"]
    assert amendment is not None
    amendment["political_capital_committed"] = 299
    amendment["influence"][0]["political_capital"] = 299
    with pytest.raises(ValidationError, match="CONSTITUTIONAL_AMENDMENT ledger share"):
        TurnReport.model_validate(data)
