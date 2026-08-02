"""The single required determinism guarantee (product spec §5.1):

Given the same starting state, decisions, seed, and ruleset version, turn
resolution must produce an identical result. Compared via `canonical_json`
(sorted keys, fixed separators, no timestamps/UUIDs/unordered sets) so the
comparison is a real byte-for-byte structural equality check, not an eyeball
comparison of two Python objects that happen to define `__eq__` loosely.
"""

from __future__ import annotations

from pathlib import Path

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.decisions import DecisionSet
from app.simulation.report import TurnReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState
from tests.conftest import make_game_state


def _run_n_turns(scenario_path: Path, n: int) -> tuple[GameState, list[TurnReport]]:
    state = load_scenario_file(scenario_path)
    reports: list[TurnReport] = []
    for _ in range(n):
        decisions = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=[],
        )
        resolution = resolve_turn(state, decisions)
        reports.append(resolution.report)
        state = resolution.state
    return state, reports


def test_identical_seed_and_decisions_produce_byte_identical_output(
    tiny_valid_scenario_path: Path,
) -> None:
    state_a, reports_a = _run_n_turns(tiny_valid_scenario_path, 8)
    state_b, reports_b = _run_n_turns(tiny_valid_scenario_path, 8)

    assert canonical_dumps(state_a.model_dump(mode="json")) == canonical_dumps(
        state_b.model_dump(mode="json")
    )
    assert canonical_dumps([r.model_dump(mode="json") for r in reports_a]) == canonical_dumps(
        [r.model_dump(mode="json") for r in reports_b]
    )


def test_identical_in_memory_states_resolve_identically() -> None:
    state_a = make_game_state(seed=123, turn=0, state_version=0)
    state_b = make_game_state(seed=123, turn=0, state_version=0)

    decisions_a = DecisionSet(expected_turn=0, expected_state_version=0, decisions=[])
    decisions_b = DecisionSet(expected_turn=0, expected_state_version=0, decisions=[])

    resolution_a = resolve_turn(state_a, decisions_a)
    resolution_b = resolve_turn(state_b, decisions_b)

    assert canonical_dumps(resolution_a.state.model_dump(mode="json")) == canonical_dumps(
        resolution_b.state.model_dump(mode="json")
    )


def test_two_independent_games_produce_byte_identical_complete_histories(
    tiny_valid_scenario_path: Path,
) -> None:
    """Same scenario + seed + decisions, built and advanced independently twice,
    must yield byte-identical *complete histories* (not just final state) —
    every entry_hash, decisions_json, and report_json included."""
    from app.simulation.history import advance_game, new_game
    from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json

    def _play(n: int) -> str:
        state = load_scenario_file(tiny_valid_scenario_path)
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for _ in range(n):
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=[],
            )
            save = advance_game(save, decisions)
        return dump_save_json(save)

    assert _play(8) == _play(8)


def test_canonical_dumps_rejects_non_canonical_value_types() -> None:
    import datetime
    import uuid

    from app.core.canonical_json import NonCanonicalValueError

    for bad_value in (
        {1, 2, 3},
        datetime.datetime(2026, 1, 1),
        uuid.uuid4(),
    ):
        try:
            canonical_dumps({"bad": bad_value})
        except NonCanonicalValueError:
            continue
        raise AssertionError(f"expected NonCanonicalValueError for {bad_value!r}")
