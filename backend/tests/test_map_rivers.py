"""Authored rivers -- the map's first NATURAL feature (map-resources slice).

Rivers are presentation only, and "presentation only" has to be a proven property rather than a
promise, because a river is exactly the kind of feature a later gate will be tempted to make
mechanical. Three separate things are established here:

* the model rejects every malformed course rather than repairing it, with an assertable code;
* a river's DIRECTION is authored data, not something normalized away;
* rivers are inert twice over -- `test_map_presentation_neutrality.py` proves moving them changes
  nothing, and `TestRiversAreInert` below proves REMOVING them changes nothing either. Those are
  different statements: the first says the values do not matter, the second says the existence
  does not. A rule that fired only when a river was present would pass the first and fail the
  second.

Adjacency is deliberately untouched: a river running between two theaters neither opens passage
nor blocks it, exactly as a shared polygon border does not. Only `RouteState` decides that.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.projections import build_strategic_map
from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.geography import (
    MAP_GRID_MAX,
    RIVER_ID_DUPLICATE,
    RIVER_NOT_CANONICAL,
    RIVER_REPEATS_VERTEX,
)
from app.simulation.history import new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState, RiverState, StrategicMapState
from tests.conftest import SCENARIO_DIR, TINY_VALID_SCENARIO_PATH
from tests.history_tamper_helpers import advance_n

_SCENARIOS = ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml")
_TURNS = 3


def _river(river_id: str = "river_a", polyline: tuple = ((0, 0), (10, 10))) -> RiverState:
    return RiverState(river_id=river_id, display_name="A River", polyline=polyline)


def _map_with_rivers(river_ids: tuple[str, ...]) -> StrategicMapState:
    """`tiny_valid`'s real map, revalidated from a payload carrying `river_ids` instead of its
    authored rivers. Goes through `model_validate` rather than `model_copy`, because only a real
    construction runs the validators these tests are about."""
    payload = load_scenario_file(TINY_VALID_SCENARIO_PATH).world.strategic_map.model_dump()
    payload["rivers"] = [_river(river_id).model_dump() for river_id in river_ids]
    return StrategicMapState.model_validate(payload)


class TestTheModelRejectsMalformedCourses:
    def test_a_repeated_consecutive_vertex_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _river(polyline=((0, 0), (5, 5), (5, 5), (10, 10)))
        assert RIVER_REPEATS_VERTEX in str(exc_info.value)

    def test_a_two_vertex_river_with_coincident_ends_is_rejected(self) -> None:
        """The degenerate zero-length case falls out of the same rule, which is why there is no
        separate zero-length code to keep alive."""
        with pytest.raises(ValidationError) as exc_info:
            _river(polyline=((7, 7), (7, 7)))
        assert RIVER_REPEATS_VERTEX in str(exc_info.value)

    def test_a_single_vertex_river_is_rejected(self) -> None:
        """A point is not a course."""
        with pytest.raises(ValidationError):
            _river(polyline=((0, 0),))

    def test_a_vertex_outside_the_authored_grid_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _river(polyline=((0, 0), (MAP_GRID_MAX + 1, 10)))
        with pytest.raises(ValidationError):
            _river(polyline=((0, 0), (10, -1)))

    def test_a_non_consecutive_repeat_is_legal(self) -> None:
        """Only CONSECUTIVE repeats are zero-length segments. A course that genuinely revisits a
        point -- a meander touching itself -- draws something, so it is authored data, not a
        defect to reject."""
        river = _river(polyline=((0, 0), (10, 0), (0, 0), (0, 10)))
        assert len(river.polyline) == 4

    def test_duplicate_river_ids_are_rejected(self) -> None:
        """Checked FIRST and independently of ordering, so it is reachable on its own: two rows
        with the same id are already sorted and trip only this code."""
        with pytest.raises(ValidationError) as exc_info:
            _map_with_rivers(("river_a", "river_a"))
        assert RIVER_ID_DUPLICATE in str(exc_info.value)

    def test_noncanonical_river_order_is_rejected_not_sorted(self) -> None:
        """Reject, never normalize -- the repository rule for every ordered collection. A build
        that sorted for you would let two different authored files serialize to the same bytes.
        Two distinct ids in the wrong order have no duplicate, so this trips only this code."""
        with pytest.raises(ValidationError) as exc_info:
            _map_with_rivers(("river_b", "river_a"))
        assert RIVER_NOT_CANONICAL in str(exc_info.value)

    def test_the_same_two_rivers_in_canonical_order_are_accepted(self) -> None:
        """Anti-vacuity for the case above: the rejection is about ORDER, not about the rivers."""
        assert len(_map_with_rivers(("river_a", "river_b")).rivers) == 2


class TestDirectionIsAuthoredData:
    def test_a_reversed_course_is_a_different_value(self) -> None:
        """No direction normalization: a river authored source-to-mouth is not silently flipped,
        so the two orders serialize to different bytes. Both are legal -- this is about the model
        preserving what was authored, not about one direction being correct."""
        forward = _river(polyline=((0, 0), (5, 5), (10, 20)))
        reversed_course = _river(polyline=((10, 20), (5, 5), (0, 0)))
        assert forward != reversed_course
        assert canonical_dumps(forward.model_dump(mode="json")) != canonical_dumps(
            reversed_course.model_dump(mode="json")
        )


@pytest.mark.parametrize("scenario_file", _SCENARIOS)
class TestEveryScenarioAuthorsRivers:
    def test_two_named_rivers_in_canonical_order(self, scenario_file: str) -> None:
        rivers = load_scenario_file(SCENARIO_DIR / scenario_file).world.strategic_map.rivers
        assert len(rivers) == 2
        ids = [river.river_id for river in rivers]
        assert ids == sorted(ids)
        assert len(set(ids)) == 2
        for river in rivers:
            assert river.display_name.strip() == river.display_name
            assert len(river.polyline) >= 2

    def test_the_projection_carries_them_in_authored_vertex_order(self, scenario_file: str) -> None:
        state = load_scenario_file(SCENARIO_DIR / scenario_file)
        projection = build_strategic_map(state)
        assert [r.river_id for r in projection.rivers] == [
            r.river_id for r in state.world.strategic_map.rivers
        ]
        for projected, authored in zip(
            projection.rivers, state.world.strategic_map.rivers, strict=True
        ):
            assert projected.display_name == authored.display_name
            assert projected.polyline == authored.polyline


def _without_rivers(state: GameState) -> GameState:
    return state.model_copy(
        update={
            "world": state.world.model_copy(
                update={
                    "strategic_map": state.world.strategic_map.model_copy(update={"rivers": ()})
                }
            )
        }
    )


class TestRiversAreInert:
    def test_removing_every_river_leaves_reports_and_non_map_state_byte_identical(self) -> None:
        """The existence half of inertness. `test_map_presentation_neutrality.py` proves moving a
        river changes nothing; this proves deleting every one of them changes nothing either, so a
        rule that fired only on a river's presence could not hide."""
        with_rivers = load_scenario_file(TINY_VALID_SCENARIO_PATH)
        assert with_rivers.world.strategic_map.rivers, "the baseline must actually have rivers"
        without = _without_rivers(with_rivers)

        with_save = advance_n(
            new_game(with_rivers, save_format_version=SAVE_FORMAT_VERSION), _TURNS
        )
        without_save = advance_n(new_game(without, save_format_version=SAVE_FORMAT_VERSION), _TURNS)

        for turn in range(1, _TURNS + 1):
            assert with_save.entry_at(turn).report() == without_save.entry_at(turn).report()

        exclude = {"world": {"strategic_map"}}
        assert with_save.current_state().model_dump(
            mode="json", exclude=exclude
        ) == without_save.current_state().model_dump(mode="json", exclude=exclude)

    def test_rivers_do_not_change_which_theaters_are_adjacent(self) -> None:
        """Stated directly rather than left to follow from the turn-report comparison: the routes
        a theater has are exactly the authored ones, with or without a river between them."""
        with_rivers = load_scenario_file(TINY_VALID_SCENARIO_PATH)
        without = _without_rivers(with_rivers)
        with_projection = build_strategic_map(with_rivers)
        without_projection = build_strategic_map(without)

        assert with_projection.routes == without_projection.routes
        assert {
            t.theater_id: (t.outgoing_theater_ids, t.incoming_theater_ids)
            for t in with_projection.theaters
        } == {
            t.theater_id: (t.outgoing_theater_ids, t.incoming_theater_ids)
            for t in without_projection.theaters
        }
        assert without_projection.rivers == ()
        assert with_projection.rivers != ()

    def test_rivers_survive_a_resolved_turn_byte_identical(self) -> None:
        """The map is immutable during a campaign (reconciliation group 53 proves the whole map
        static); pinned here for rivers specifically so a future writable river would name itself
        in this file rather than only in a group-53 failure."""
        state = load_scenario_file(TINY_VALID_SCENARIO_PATH)
        opening = canonical_dumps(
            [river.model_dump(mode="json") for river in state.world.strategic_map.rivers]
        )
        save = advance_n(new_game(state, save_format_version=SAVE_FORMAT_VERSION), _TURNS)
        closing = canonical_dumps(
            [
                river.model_dump(mode="json")
                for river in save.current_state().world.strategic_map.rivers
            ]
        )
        assert opening == closing
