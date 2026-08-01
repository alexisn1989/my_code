from __future__ import annotations

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import TurnResolutionError
from app.simulation.decisions import DecisionSet
from app.simulation.phases import PHASE_IDS
from app.simulation.report import PhaseStatus
from app.simulation.resolver import resolve_turn
from tests.conftest import make_game_state


def _empty_decisions_for(state) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=[],
    )


def test_turn_number_advances_exactly_once() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert resolution.state.turn == 1
    assert resolution.state.state_version == 1
    assert state.turn == 0, "input state must not be mutated"


def test_turn_number_advances_by_exactly_n_after_n_resolutions() -> None:
    state = make_game_state(turn=0, state_version=0)
    n = 8
    for _ in range(n):
        resolution = resolve_turn(state, _empty_decisions_for(state))
        state = resolution.state
    assert state.turn == n
    assert state.state_version == n


def test_stale_decision_set_is_rejected_and_state_is_untouched() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))

    stale_decisions = DecisionSet(expected_turn=99, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, stale_decisions)

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after, "a rejected decision set must not mutate the input state"


def test_stale_state_version_is_rejected_and_state_is_untouched() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))

    stale_decisions = DecisionSet(expected_turn=0, expected_state_version=99, decisions=[])
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, stale_decisions)

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after


def test_a_resolved_decision_set_cannot_be_resubmitted() -> None:
    state = make_game_state(turn=0, state_version=0)
    decisions = _empty_decisions_for(state)

    resolution = resolve_turn(state, decisions)
    assert resolution.state.turn == 1

    # Resubmitting the *same* decision set (still targeting turn 0) against the
    # new state must be rejected — it is now stale.
    with pytest.raises(TurnResolutionError):
        resolve_turn(resolution.state, decisions)


def test_invalid_input_state_is_rejected_without_running_phases() -> None:
    state = make_game_state(turn=0, state_version=0)
    # Corrupt a share sum in place to make the *input* state itself invalid.
    country = state.world.countries[state.world.player_country_id]
    country.population_groups[0].population_share = 0.99
    before = canonical_dumps(state.model_dump(mode="json"))

    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _empty_decisions_for(state))

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after


def test_phases_run_in_the_documented_order() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert list(resolution.report.dev.phase_statuses.keys()) == list(PHASE_IDS)


def test_report_generation_phase_is_implemented_others_are_not_yet() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    statuses = resolution.report.dev.phase_statuses

    assert statuses["generate_turn_report"] == PhaseStatus.IMPLEMENTED
    other_statuses = {pid: s for pid, s in statuses.items() if pid != "generate_turn_report"}
    assert all(s == PhaseStatus.NOT_IMPLEMENTED for s in other_statuses.values())


def test_report_resolved_turn_matches_the_turn_that_was_played() -> None:
    state = make_game_state(turn=3, state_version=3)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert resolution.report.resolved_turn == 3
    assert resolution.state.turn == 4
