"""Phase 3C: the removal mechanism — `resolve_turn`'s top-of-function refusal
(`GameAlreadyConcludedError`) and `validate_history`'s independent tail-truncation guard (§6)."""

from __future__ import annotations

import dataclasses

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.history import _make_entry, new_game, validate_history
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


def test_validate_history_rejects_an_entry_after_the_game_concluded() -> None:
    """A genuine two-entry save whose LAST entry's state is replaced with a concluded one (same
    turn/report, only `terminal_outcome` added -- no reconciliation group in this gate reads that
    field, so this alone stays clean), followed by a THIRD entry hand-assembled directly, never
    through `resolve_turn`/`advance_game` (which would themselves refuse via
    `GameAlreadyConcludedError`) -- exactly the "hand-crafted save smuggling extra turns" gap that
    guard alone cannot reach."""
    genesis_state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(genesis_state, save_format_version=1)
    resolution = resolve_turn(genesis_state, _empty_decisions_for(genesis_state))

    concluded_turn1_state = _with_terminal_outcome(
        resolution.state,
        TerminalOutcomeState(
            bucket=OutcomeBucket.DEFEAT, removal_reason=RemovalReason.COUP, turn=1
        ),
    )
    turn1_entry = _make_entry(
        turn=1,
        previous_entry_hash=save.head_entry_hash,
        state=concluded_turn1_state,
        decisions=_empty_decisions_for(genesis_state),
        report=resolution.report,
        ruleset_version=save.ruleset_version,
        content_version=save.content_version,
    )
    save = dataclasses.replace(
        save,
        entry_count=2,
        head_entry_hash=turn1_entry.entry_hash,
        entries=(*save.entries, turn1_entry),
    )
    assert validate_history(save) == []

    turn2_state = concluded_turn1_state.model_copy(update={"turn": 2, "state_version": 2})
    turn2_entry = _make_entry(
        turn=2,
        previous_entry_hash=turn1_entry.entry_hash,
        state=turn2_state,
        decisions=_empty_decisions_for(turn2_state),
        report=resolution.report,
        ruleset_version=save.ruleset_version,
        content_version=save.content_version,
    )
    save = dataclasses.replace(
        save,
        entry_count=3,
        head_entry_hash=turn2_entry.entry_hash,
        entries=(*save.entries, turn2_entry),
    )

    problems = validate_history(save)
    assert any("entry exists after the game concluded at turn 1" in p for p in problems), problems
