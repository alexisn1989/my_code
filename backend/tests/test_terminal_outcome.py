"""Phase 3C: the removal mechanism — `resolve_turn`'s top-of-function refusal
(`GameAlreadyConcludedError`) and `validate_history`'s independent tail-truncation guard (§6)."""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.resolver import resolve_turn
from app.simulation.state import (
    GameState,
    OutcomeBucket,
    RemovalReason,
    TerminalOutcomeState,
    VictoryReason,
)
from tests.conftest import SCENARIO_DIR


def _empty_decisions_for(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _with_terminal_outcome(state: GameState, outcome: TerminalOutcomeState) -> GameState:
    player_id = state.world.player_country_id
    player = state.world.countries[player_id]
    politics = player.politics
    assert politics is not None
    updated_player = player.model_copy(
        update={"politics": politics.model_copy(update={"terminal_outcome": outcome})}
    )
    updated_countries = dict(state.world.countries)
    updated_countries[player_id] = updated_player
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": updated_countries})}
    )


def _concluded_tiny_valid(
    *, bucket: OutcomeBucket, removal_reason=None, victory_reason=None, turn: int = 1
) -> GameState:  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    for _ in range(turn):
        state = resolve_turn(state, _empty_decisions_for(state)).state
    outcome = TerminalOutcomeState(
        bucket=bucket, removal_reason=removal_reason, victory_reason=victory_reason, turn=turn
    )
    return _with_terminal_outcome(state, outcome)


def test_resolve_turn_refuses_after_terminal_outcome_is_set() -> None:
    state = _concluded_tiny_valid(bucket=OutcomeBucket.DEFEAT, removal_reason=RemovalReason.COUP)
    with pytest.raises(GameAlreadyConcludedError) as exc_info:
        resolve_turn(state, _empty_decisions_for(state))
    message = str(exc_info.value)
    assert "turn 1" in message
    assert "defeat" in message
    assert "coup" in message
    assert "not loaded" not in message  # distinct framing from SaveCompatibilityError
    assert "no further turn can be resolved" in message


def test_game_already_concluded_error_carries_structured_fields() -> None:
    state = _concluded_tiny_valid(
        bucket=OutcomeBucket.VICTORY,
        victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
        turn=2,
    )
    with pytest.raises(GameAlreadyConcludedError) as exc_info:
        resolve_turn(state, _empty_decisions_for(state))
    err = exc_info.value
    assert err.bucket == "victory"
    assert err.reason == "peaceful_liberalization_completed"
    assert err.turn == 2


def test_a_concluded_game_input_state_is_never_mutated() -> None:
    state = _concluded_tiny_valid(
        bucket=OutcomeBucket.DEFEAT, removal_reason=RemovalReason.IMPEACHMENT
    )
    before = state.model_dump(mode="json")
    with pytest.raises(GameAlreadyConcludedError):
        resolve_turn(state, _empty_decisions_for(state))
    assert state.model_dump(mode="json") == before
