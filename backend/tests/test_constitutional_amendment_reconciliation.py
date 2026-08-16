"""Gate 3C3 commit 22: reconciliation groups 41-44."""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import (
    AmendmentDifficulty,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    TerritorialOrganization,
)
from app.simulation.decisions import (
    ConstitutionalAmendmentDecision,
    DecisionSet,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    TermLimitTarget,
)
from app.simulation.legislature import ProposalRoute
from app.simulation.reconciliation import reconcile_political_legislative_and_survival_report
from app.simulation.report import TurnReport
from app.simulation.resolver import TurnResolution, resolve_turn
from app.simulation.state import (
    GameState,
    OutcomeBucket,
    TerminalOutcomeState,
    VictoryReason,
)
from tests.conftest import SCENARIO_DIR
from tests.test_constitutional_amendment_gating import (
    _decree_state_at_turn_three_opening,
    _liberalizing_amendment,
    _make_every_bloc_supportive,
    _make_legislature_absent,
)
from tests.test_liberalization_victory import _advance, _empty, _with_prior_pending


def _amendment_resolution(*, influence: int = 300) -> tuple[GameState, DecisionSet, TurnResolution]:
    state = _decree_state_at_turn_three_opening()
    advanced = _advance(load_scenario_file(SCENARIO_DIR / "decree_state.yaml"), 2)
    state_politics = state.world.countries["valdrun"].politics
    advanced_politics = advanced.world.countries["valdrun"].politics
    assert state_politics is not None and advanced_politics is not None
    state.world.countries["valdrun"].politics = state_politics.model_copy(
        update={"economic_baseline": advanced_politics.economic_baseline}
    )
    amendment = _liberalizing_amendment(influence=influence)
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )
    return state, decisions, resolve_turn(state, decisions)


def _replace_closing_politics(resolution: TurnResolution, **updates: object) -> GameState:
    state = resolution.state
    player_id = state.world.player_country_id
    player = state.world.countries[player_id]
    assert player.politics is not None
    updated_player = player.model_copy(
        update={"politics": player.politics.model_copy(update=updates)}
    )
    countries = dict(state.world.countries)
    countries[player_id] = updated_player
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": countries})}
    )


def _problems(
    opening: GameState,
    decisions: DecisionSet,
    resolution: TurnResolution,
    *,
    closing: GameState | None = None,
    report: TurnReport | None = None,
) -> list[str]:
    return reconcile_political_legislative_and_survival_report(
        opening_state=opening,
        closing_state=closing if closing is not None else resolution.state,
        report=report if report is not None else resolution.report,
        decisions=decisions,
    )


def test_real_passed_and_failed_amendments_reconcile() -> None:
    for influence in (300, 299):
        opening, decisions, resolution = _amendment_resolution(influence=influence)
        assert _problems(opening, decisions, resolution) == []


def test_real_decree_amendment_reconciles() -> None:
    opening = _make_legislature_absent(load_scenario_file(SCENARIO_DIR / "decree_state.yaml"))
    amendment = ConstitutionalAmendmentDecision(
        targets=(ExecutiveSelectionTarget(value=ExecutiveSelection.APPOINTED),),
        route=ProposalRoute.DECREE,
    )
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=(amendment,))
    resolution = resolve_turn(opening, decisions)
    assert _problems(opening, decisions, resolution) == []


@pytest.mark.parametrize(
    ("target", "cleared"),
    [(TermLimitTarget(value=2), False), (ElectionIntervalTarget(value=None), True)],
)
def test_group_41_preserves_pending_while_competitive_and_clears_on_reversal(
    target: object, cleared: bool
) -> None:
    _, _, first = _amendment_resolution()
    opening = _make_every_bloc_supportive(first.state)
    pending = opening.world.countries["valdrun"].politics
    assert pending is not None and pending.pending_liberalization is not None
    amendment = ConstitutionalAmendmentDecision(targets=(target,))  # type: ignore[arg-type]
    decisions = DecisionSet(
        expected_turn=opening.turn,
        expected_state_version=opening.state_version,
        decisions=(amendment,),
    )
    resolution = resolve_turn(opening, decisions)
    closing = resolution.state.world.countries["valdrun"].politics
    assert closing is not None
    assert (closing.pending_liberalization is None) is cleared


@pytest.mark.parametrize(
    "field", ["set_at_turn", "opening_constitution_digest", "closing_constitution_digest"]
)
def test_group_41_rejects_each_pending_provenance_field(field: str) -> None:
    opening, decisions, resolution = _amendment_resolution()
    politics = resolution.state.world.countries["valdrun"].politics
    assert politics is not None and politics.pending_liberalization is not None
    pending = politics.pending_liberalization
    replacement: object = pending.set_at_turn + 1 if field == "set_at_turn" else "f" * 64
    corrupted = pending.model_copy(update={field: replacement})
    closing = _replace_closing_politics(resolution, pending_liberalization=corrupted)
    assert any(
        "group 41" in problem
        for problem in _problems(opening, decisions, resolution, closing=closing)
    )


def test_group_41_rejects_missing_pending_after_a_qualifying_transition() -> None:
    opening, decisions, resolution = _amendment_resolution()
    closing = _replace_closing_politics(resolution, pending_liberalization=None)
    assert any(
        "group 41" in problem
        for problem in _problems(opening, decisions, resolution, closing=closing)
    )


def _starting_democracy_win() -> tuple[GameState, DecisionSet, TurnResolution]:
    opening = _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    decisions = _empty(opening)
    return opening, decisions, resolve_turn(opening, decisions)


def test_group_42_catches_the_starting_democracy_exploit() -> None:
    opening, decisions, resolution = _starting_democracy_win()
    election = resolution.report.election
    assert election is not None and election.result == "won"
    fabricated_election = election.model_copy(
        update={"liberalization_completed": True, "next_election_turn": 16}
    )
    fabricated_report = resolution.report.model_copy(update={"election": fabricated_election})
    victory = TerminalOutcomeState(
        bucket=OutcomeBucket.VICTORY,
        victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
        turn=16,
    )
    closing = _replace_closing_politics(resolution, terminal_outcome=victory, next_election_turn=16)
    problems = _problems(opening, decisions, resolution, closing=closing, report=fabricated_report)
    assert any("group 42" in problem for problem in problems)


def test_group_39_rejects_missing_and_wrong_victory_terminal_outcomes() -> None:
    opening = _with_prior_pending(
        _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    )
    decisions = _empty(opening)
    resolution = resolve_turn(opening, decisions)
    missing = _replace_closing_politics(resolution, terminal_outcome=None)
    assert any(
        "exact peaceful" in p for p in _problems(opening, decisions, resolution, closing=missing)
    )
    wrong_turn = TerminalOutcomeState(
        bucket=OutcomeBucket.VICTORY,
        victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
        turn=15,
    )
    corrupted = _replace_closing_politics(resolution, terminal_outcome=wrong_turn)
    assert any(
        "exact peaceful" in p for p in _problems(opening, decisions, resolution, closing=corrupted)
    )


def test_group_39_rejects_victory_terminal_on_an_ordinary_win() -> None:
    opening, decisions, resolution = _starting_democracy_win()
    victory = TerminalOutcomeState(
        bucket=OutcomeBucket.VICTORY,
        victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
        turn=16,
    )
    closing = _replace_closing_politics(resolution, terminal_outcome=victory)
    assert any(
        "ordinary won election" in p
        for p in _problems(opening, decisions, resolution, closing=closing)
    )


def test_groups_39_42_reject_a_tampered_ordinary_win_false_story() -> None:
    opening = _with_prior_pending(
        _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    )
    decisions = _empty(opening)
    resolution = resolve_turn(opening, decisions)
    election = resolution.report.election
    politics = opening.world.countries["arken"].politics
    assert election is not None and election.result == "won" and politics is not None
    assert politics.pending_liberalization is not None
    fabricated_election = election.model_copy(
        update={"liberalization_completed": False, "next_election_turn": 32}
    )
    report = resolution.report.model_copy(update={"election": fabricated_election})
    closing = _replace_closing_politics(
        resolution,
        terminal_outcome=None,
        pending_liberalization=politics.pending_liberalization,
        next_election_turn=32,
    )
    problems = _problems(opening, decisions, resolution, closing=closing, report=report)
    assert any("should_complete=True" in problem for problem in problems)
    assert any("exact peaceful" in problem for problem in problems)


@pytest.mark.parametrize(
    "field",
    [
        "proposed",
        "route",
        "amendment_decision_digest",
        "targets",
        "influence",
        "political_capital_committed",
        "outcome",
        "chambers",
        "opening_constitution_digest",
        "closing_constitution_digest",
    ],
)
def test_group_43_rejects_each_report_provenance_surface(field: str) -> None:
    opening, decisions, resolution = _amendment_resolution()
    amendment = resolution.report.constitutional_amendment
    assert amendment is not None
    value: object
    if field == "proposed":
        value = False
    elif field == "route":
        value = ProposalRoute.DECREE
    elif field in (
        "amendment_decision_digest",
        "opening_constitution_digest",
        "closing_constitution_digest",
    ):
        value = "f" * 64
    elif field in ("targets", "influence"):
        value = ()
    elif field == "political_capital_committed":
        value = 299
    elif field == "outcome":
        value = "failed_legislative"
    else:
        chamber = amendment.chambers[0].model_copy(update={"required_yes_seats": 66})
        value = (chamber,)
    corrupted = amendment.model_copy(update={field: value})
    report = resolution.report.model_copy(update={"constitutional_amendment": corrupted})
    assert any(
        "group 43" in problem
        for problem in _problems(opening, decisions, resolution, report=report)
    )


def test_group_43_missing_report_is_a_problem_not_a_crash() -> None:
    opening, decisions, resolution = _amendment_resolution()
    report = resolution.report.model_copy(update={"constitutional_amendment": None})
    assert any(
        "group 43" in problem
        for problem in _problems(opening, decisions, resolution, report=report)
    )


def test_group_43_wrong_runtime_report_type_is_a_problem_not_a_crash() -> None:
    opening, decisions, resolution = _amendment_resolution()
    report = resolution.report.model_copy(update={"constitutional_amendment": {"bad": "shape"}})
    assert any(
        "missing or has an invalid runtime type" in problem
        for problem in _problems(opening, decisions, resolution, report=report)
    )


@pytest.mark.parametrize("field", ["party_id", "decision_digest"])
def test_group_43_rejects_amendment_ledger_identity_and_digest_tampering(field: str) -> None:
    opening, decisions, resolution = _amendment_resolution()
    capital = resolution.report.political_capital
    assert capital is not None
    amendment_rows = [
        (index, row)
        for index, row in enumerate(capital.expenditures)
        if row.category.value == "constitutional_amendment"
    ]
    assert amendment_rows
    index, row = amendment_rows[0]
    value = "invented_party" if field == "party_id" else "f" * 64
    expenditures = list(capital.expenditures)
    expenditures[index] = row.model_copy(update={field: value})
    corrupted_capital = capital.model_copy(update={"expenditures": tuple(expenditures)})
    report = resolution.report.model_copy(update={"political_capital": corrupted_capital})
    assert any(
        "capital ledger rows do not exactly match" in problem
        for problem in _problems(opening, decisions, resolution, report=report)
    )


def test_group_43_rejects_illegal_decree_route_with_an_opening_legislature() -> None:
    opening, decisions, resolution = _amendment_resolution()
    amendment = decisions.constitutional_amendment_decision()
    assert amendment is not None
    illegal = amendment.model_copy(update={"route": ProposalRoute.DECREE, "influence": ()})
    corrupted_decisions = decisions.model_copy(update={"decisions": (illegal,)})
    assert any(
        "route=decree is illegal" in problem
        for problem in _problems(opening, corrupted_decisions, resolution)
    )


def test_group_43_rejects_unknown_influence_identity_before_tallying() -> None:
    opening, decisions, resolution = _amendment_resolution()
    amendment = decisions.constitutional_amendment_decision()
    assert amendment is not None and amendment.influence
    unknown = amendment.influence[0].model_copy(update={"party_id": "invented_party"})
    corrupted = amendment.model_copy(update={"influence": (unknown,)})
    corrupted_decisions = decisions.model_copy(update={"decisions": (corrupted,)})
    problems = _problems(opening, corrupted_decisions, resolution)
    assert any("unknown opening-legislature identity" in problem for problem in problems)


def test_group_43_rejects_zero_seat_influence_identity_before_tallying() -> None:
    opening, decisions, resolution = _amendment_resolution()
    amendment = decisions.constitutional_amendment_decision()
    politics = opening.world.countries["valdrun"].politics
    assert amendment is not None and amendment.influence and politics is not None
    legislature = politics.legislature
    assert legislature is not None
    target = amendment.influence[0]
    parties = []
    for party in legislature.parties:
        blocs = tuple(
            bloc.model_copy(
                update={"seats": tuple(row.model_copy(update={"seats": 0}) for row in bloc.seats)}
            )
            if (party.id, bloc.id) == (target.party_id, target.bloc_id)
            else bloc
            for bloc in party.blocs
        )
        parties.append(party.model_copy(update={"blocs": blocs}))
    opening_legislature = legislature.model_copy(update={"parties": tuple(parties)})
    opening_player = opening.world.countries["valdrun"]
    opening_countries = dict(opening.world.countries)
    opening_countries["valdrun"] = opening_player.model_copy(
        update={"politics": politics.model_copy(update={"legislature": opening_legislature})}
    )
    corrupted_opening = opening.model_copy(
        update={"world": opening.world.model_copy(update={"countries": opening_countries})}
    )
    problems = _problems(corrupted_opening, decisions, resolution)
    assert any("zero-seat opening-legislature bloc" in problem for problem in problems)


def test_group_43_binds_explicit_opening_and_closing_snapshots_to_real_state() -> None:
    opening, decisions, resolution = _amendment_resolution()
    amendment = resolution.report.constitutional_amendment
    assert amendment is not None
    bad_opening = amendment.opening_constitution.model_copy(
        update={"decree_authority": DecreeAuthority.EMERGENCY_ONLY}
    )
    bad_closing = amendment.closing_constitution.model_copy(
        update={"executive_selection": ExecutiveSelection.HEREDITARY}
    )
    corrupted = amendment.model_copy(
        update={"opening_constitution": bad_opening, "closing_constitution": bad_closing}
    )
    report = resolution.report.model_copy(update={"constitutional_amendment": corrupted})
    problems = _problems(opening, decisions, resolution, report=report)
    assert any("opening snapshot axis" in problem for problem in problems)
    assert any("closing snapshot axis" in problem for problem in problems)


def test_group_43_rejects_a_proposal_report_when_no_amendment_was_submitted() -> None:
    opening, decisions, resolution = _starting_democracy_win()
    _, _, amendment_resolution = _amendment_resolution()
    fabricated = amendment_resolution.report.constitutional_amendment
    assert fabricated is not None
    report = resolution.report.model_copy(update={"constitutional_amendment": fabricated})
    assert any(
        "no ConstitutionalAmendmentDecision" in problem
        for problem in _problems(opening, decisions, resolution, report=report)
    )


def test_group_44_rejects_unexplained_axis_change_without_an_amendment() -> None:
    opening, decisions, resolution = _starting_democracy_win()
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None
    constitution = politics.constitution.model_copy(
        update={"decree_authority": DecreeAuthority.NONE}
    )
    closing = _replace_closing_politics(resolution, constitution=constitution)
    opening_politics = opening.world.countries["arken"].politics
    closing_politics = closing.world.countries["arken"].politics
    assert opening_politics is not None and closing_politics is not None
    assert opening_politics.constitution.decree_authority is DecreeAuthority.EMERGENCY_ONLY
    assert closing_politics.constitution.decree_authority is DecreeAuthority.NONE
    problems = _problems(opening, decisions, resolution, closing=closing)
    assert any(
        "group 44 constitution axis 'decree_authority'" in problem for problem in problems
    ), problems


@pytest.mark.parametrize(
    ("axis", "value"),
    [
        ("territorial_organization", TerritorialOrganization.FEDERAL),
        ("judicial_review", JudicialReview.NONE),
        ("amendment_difficulty", AmendmentDifficulty.ENTRENCHED),
    ],
)
def test_group_44_rejects_every_never_amendable_axis(axis: str, value: object) -> None:
    opening, decisions, resolution = _amendment_resolution()
    politics = resolution.state.world.countries["valdrun"].politics
    assert politics is not None
    constitution = politics.constitution.model_copy(update={axis: value})
    closing = _replace_closing_politics(resolution, constitution=constitution)
    assert any(
        f"{axis!r} changed" in p for p in _problems(opening, decisions, resolution, closing=closing)
    )


@pytest.mark.parametrize(
    ("axis", "value"),
    [
        ("decree_authority", DecreeAuthority.UNLIMITED),
        ("executive_selection", ExecutiveSelection.HEREDITARY),
        ("executive_system", ExecutiveSystem.MONARCHICAL),
        ("executive_term_limit_terms", 2),
        ("national_election_interval_turns", 12),
    ],
)
def test_group_44_rejects_a_targeted_axis_closing_at_the_wrong_value(
    axis: str, value: object
) -> None:
    opening, decisions, resolution = _amendment_resolution()
    politics = resolution.state.world.countries["valdrun"].politics
    assert politics is not None
    constitution = politics.constitution.model_copy(update={axis: value})
    closing = _replace_closing_politics(resolution, constitution=constitution)
    assert any(
        f"axis {axis!r}" in p for p in _problems(opening, decisions, resolution, closing=closing)
    )


def test_group_44_rejects_state_change_after_failed_amendment() -> None:
    opening, decisions, resolution = _amendment_resolution(influence=299)
    politics = resolution.state.world.countries["valdrun"].politics
    assert politics is not None
    constitution = politics.constitution.model_copy(
        update={"decree_authority": DecreeAuthority.NONE}
    )
    closing = _replace_closing_politics(resolution, constitution=constitution)
    assert any(
        "group 44" in problem
        for problem in _problems(opening, decisions, resolution, closing=closing)
    )
