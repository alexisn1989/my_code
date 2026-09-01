"""Rehashed tamper matrix for group 53 (`reconcile_strategic_map_staticness`), Strategic
Military Map Gate M0 commit 5 -- mirroring `test_foreign_conflict_tamper_matrix.py`'s method.

A naive tamper edits a payload and forgets the hash, so the chain check catches it and nothing
deeper is ever exercised. Every case here instead RE-LINKS AND RE-HASHES the entire downstream
chain via `tests/history_tamper_helpers.py`, so `hash_chain_problems` reports a genuinely green
chain, and whatever `validate_history` still reports is therefore attributable to semantic
reconciliation (group 53), not to hashing.

Each case tampers the LAST entry's state -- the only choice that can never also become someone
else's OPENING-side tamper (there is no turn after it), so its effect on group 53 is single and
unambiguous: it corrupts exactly the final turn's closing map relative to the second-to-last
entry's (untampered) opening map.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.canonical_json import canonical_dumps
from app.simulation.geography import LabelAnchor
from app.simulation.history import new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION, GameSave
from app.simulation.state import (
    GameState,
    PlayerCountryRef,
    RouteState,
    StrategicMapState,
    TheaterPresentation,
    WorldState,
)
from tests.conftest import make_game_state, make_minimal_strategic_map
from tests.history_tamper_helpers import (
    advance_n,
    hash_chain_problems,
    retamper_state_with_consistent_hash,
)


def _two_theater_map(player_country_id: str) -> StrategicMapState:
    base = make_minimal_strategic_map(player_country_id)
    capital = next(iter(base.theaters.values()))
    second = capital.model_copy(update={"display_name": "Northern Theater"})
    return StrategicMapState(
        map_id=base.map_id,
        capital_theater_id=base.capital_theater_id,
        theaters={base.capital_theater_id: capital, "north": second},
        routes=(
            RouteState(from_theater=base.capital_theater_id, to_theater="north", kind="land"),
            RouteState(from_theater="north", to_theater=base.capital_theater_id, kind="land"),
        ),
        shapes=base.shapes,
    )


def _new_save() -> GameSave:
    state = make_game_state(strategic_map=_two_theater_map("testland"))
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    return advance_n(save, 2)


def _tamper_last_state(save: GameSave, mutate: Callable[[GameState], GameState]) -> GameSave:
    index = len(save.entries) - 1
    state = save.entries[index].state()
    tampered_json = canonical_dumps(mutate(state).model_dump(mode="json"))
    return retamper_state_with_consistent_hash(save, index=index, tampered_state_json=tampered_json)


def _assert_green_chain_and_group_53(tampered: GameSave, *, substring: str) -> list[str]:
    chain_problems = hash_chain_problems(tampered)
    assert chain_problems == [], (
        f"hash chain corrupted by the tamper helper itself: {chain_problems!r}"
    )

    problems = validate_history(tampered)
    hash_leak = [
        p
        for p in problems
        if "entry_hash" in p or "previous_entry_hash" in p or "head_entry_hash" in p
    ]
    assert hash_leak == [], f"a hash-chain complaint leaked into validate_history: {hash_leak!r}"

    matches = [p for p in problems if substring in p]
    assert matches, f"expected a problem containing {substring!r}, got {problems!r}"
    return problems


def _with_map(state: GameState, new_map: StrategicMapState) -> GameState:
    return state.model_copy(
        update={"world": state.world.model_copy(update={"strategic_map": new_map})}
    )


CANONICAL_BYTES_DIFFER = "canonical map bytes differ"


def test_case01_theater_owner_changed_mid_history_is_caught() -> None:
    save = _new_save()

    def mutate(state: GameState) -> GameState:
        world: WorldState = state.world
        old_map = world.strategic_map
        capital = old_map.theaters[old_map.capital_theater_id]
        tampered_capital = capital.model_copy(
            update={"owner": PlayerCountryRef(country_id="a_different_owner_zzz")}
        )
        new_theaters = dict(old_map.theaters)
        new_theaters[old_map.capital_theater_id] = tampered_capital
        return _with_map(state, old_map.model_copy(update={"theaters": new_theaters}))

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group_53(tampered, substring=CANONICAL_BYTES_DIFFER)


def test_case02_route_row_added_mid_history_is_caught() -> None:
    save = _new_save()

    def mutate(state: GameState) -> GameState:
        old_map = state.world.strategic_map
        # The two-theater fixture already carries both directed rows between its theaters, so
        # deleting one is the reachable half of "added or deleted" here -- there is no
        # additional legal route left to add.
        remaining = tuple(r for r in old_map.routes if r != old_map.routes[0])
        assert len(remaining) == len(old_map.routes) - 1
        return _with_map(state, old_map.model_copy(update={"routes": remaining}))

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group_53(tampered, substring=CANONICAL_BYTES_DIFFER)


def test_case03_capital_theater_id_changed_mid_history_is_caught() -> None:
    save = _new_save()

    def mutate(state: GameState) -> GameState:
        old_map = state.world.strategic_map
        return _with_map(state, old_map.model_copy(update={"capital_theater_id": "north"}))

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group_53(tampered, substring=CANONICAL_BYTES_DIFFER)


def test_case04_presentation_coordinate_changed_mid_history_is_caught() -> None:
    """The deliberate case: presentation is inert to SIMULATION (no formula reads it), but it is
    still authored authoritative content, so silently rewriting it mid-campaign is still a
    tamper -- inert to simulation is not the same as inert to integrity."""
    save = _new_save()

    def mutate(state: GameState) -> GameState:
        old_map = state.world.strategic_map
        capital = old_map.theaters[old_map.capital_theater_id]
        moved = capital.model_copy(
            update={
                "presentation": TheaterPresentation(
                    centroid_x=9_999, centroid_y=9_999, label_anchor=LabelAnchor.SOUTH
                )
            }
        )
        new_theaters = dict(old_map.theaters)
        new_theaters[old_map.capital_theater_id] = moved
        return _with_map(state, old_map.model_copy(update={"theaters": new_theaters}))

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group_53(tampered, substring=CANONICAL_BYTES_DIFFER)


def test_case05_polygon_vertex_changed_mid_history_is_caught() -> None:
    save = _new_save()

    def mutate(state: GameState) -> GameState:
        old_map = state.world.strategic_map
        shape = old_map.shapes[0]
        tampered_polygon = ((0, 0), (10, 0), (10, 10), (1, 10))
        assert tampered_polygon != shape.polygon
        tampered_shape = shape.model_copy(update={"polygon": tampered_polygon})
        new_shapes = (tampered_shape, *old_map.shapes[1:])
        return _with_map(state, old_map.model_copy(update={"shapes": new_shapes}))

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group_53(tampered, substring=CANONICAL_BYTES_DIFFER)


def test_clean_campaign_after_the_helper_relink_produces_no_group_53_problems() -> None:
    """Sanity check on the tamper harness itself: re-linking and re-hashing an UNTAMPERED chain
    (mutate is the identity function) must still produce zero group-53 problems, proving the
    tamper cases above are caught by the mutation, not by an artifact of re-hashing itself."""
    save = _new_save()
    untouched = _tamper_last_state(save, lambda state: state)
    assert hash_chain_problems(untouched) == []
    problems = validate_history(untouched)
    assert not any("strategic map" in p for p in problems)
