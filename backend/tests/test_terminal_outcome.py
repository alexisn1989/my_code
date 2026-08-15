"""Phase 3C: the removal mechanism — `resolve_turn`'s top-of-function refusal
(`GameAlreadyConcludedError`) and `validate_history`'s independent tail-truncation guard (§6)."""

from __future__ import annotations

import dataclasses

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.history import _make_entry, advance_game, new_game, validate_history
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
    """`tiny_valid`'s real, natural conclusion (turn 32, `TERM_LIMIT_EXIT` -- the SAME real
    horizon `test_soak.py` and `test_government_survival_calibration.py` establish), driven
    entirely through genuine `resolve_turn` calls with no fabricated report or state at all,
    followed by a hand-assembled 33rd entry appended directly, never through
    `resolve_turn`/`advance_game` (which would themselves refuse via `GameAlreadyConcludedError`)
    -- exactly the "hand-crafted save smuggling extra turns" gap that guard alone cannot reach."""
    genesis_state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(genesis_state, save_format_version=1)
    for _ in range(32):
        current = save.current_state()
        save = advance_game(save, _empty_decisions_for(current))
    assert validate_history(save) == []
    last_report = save.entries[-1].report()
    assert last_report is not None
    concluded_state = save.current_state()
    assert concluded_state.world.countries["arken"].politics.terminal_outcome is not None

    smuggled_state = concluded_state.model_copy(update={"turn": 33, "state_version": 33})
    smuggled_entry = _make_entry(
        turn=33,
        previous_entry_hash=save.head_entry_hash,
        state=smuggled_state,
        decisions=_empty_decisions_for(smuggled_state),
        report=last_report,
        ruleset_version=save.ruleset_version,
        content_version=save.content_version,
    )
    save = dataclasses.replace(
        save,
        entry_count=save.entry_count + 1,
        head_entry_hash=smuggled_entry.entry_hash,
        entries=(*save.entries, smuggled_entry),
    )

    problems = validate_history(save)
    assert any("entry exists after the game concluded at turn 32" in p for p in problems), problems
