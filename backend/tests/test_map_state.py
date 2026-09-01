"""Tests for `StrategicMapState`/`WorldState.strategic_map` construction (Strategic Military
Map, Gate M0). Covers the required-field, min-length and dict-key-strictness guarantees; the
per-code construction-validator tests (self-edge, duplicate/ordering, polygon shape) live in
`test_geography.py`, and the cross-referencing state invariants live in `test_map_invariants.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.geography import LabelAnchor, TheaterKind
from app.simulation.state import (
    CountryShapeState,
    PlayerCountryRef,
    StrategicMapState,
    TheaterPresentation,
    TheaterState,
    WorldState,
)
from tests.conftest import make_game_state, make_minimal_strategic_map


def _presentation(x: int = 5_000, y: int = 5_000) -> TheaterPresentation:
    return TheaterPresentation(centroid_x=x, centroid_y=y, label_anchor=LabelAnchor.CENTER)


def _player_theater(owner_id: str = "arken") -> TheaterState:
    return TheaterState(
        display_name="Capital",
        kind=TheaterKind.LAND,
        owner=PlayerCountryRef(country_id=owner_id),
        presentation=_presentation(),
    )


def _shape(shape_id: str = "shape_arken", owner_id: str = "arken") -> CountryShapeState:
    return CountryShapeState(
        shape_id=shape_id,
        owner=PlayerCountryRef(country_id=owner_id),
        polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
    )


class TestRequiredMap:
    def test_world_state_without_strategic_map_is_rejected(self) -> None:
        base = make_game_state()
        with pytest.raises(ValidationError) as exc_info:
            WorldState(
                countries=base.world.countries,
                player_country_id=base.world.player_country_id,
                foreign_profiles=base.world.foreign_profiles,
                dyads=base.world.dyads,
                conflicts=base.world.conflicts,
                # strategic_map deliberately omitted
            )
        assert "strategic_map" in str(exc_info.value)

    def test_a_minimal_authored_map_round_trips_through_make_game_state(self) -> None:
        state = make_game_state()
        assert state.world.strategic_map is not None
        assert len(state.world.strategic_map.theaters) >= 1


class TestEmptyCollectionsRejected:
    def test_empty_theaters_dict_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategicMapState(
                map_id="m",
                capital_theater_id="capital",
                theaters={},
                shapes=(_shape(),),
            )

    def test_empty_shapes_tuple_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategicMapState(
                map_id="m",
                capital_theater_id="capital",
                theaters={"capital": _player_theater()},
                shapes=(),
            )

    def test_empty_routes_tuple_is_accepted_for_a_single_theater_map(self) -> None:
        # A one-theater map has nowhere to route to; an empty tuple is a legal map, not a defect.
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _player_theater()},
            routes=(),
            shapes=(_shape(),),
        )
        assert state_map.routes == ()


class TestTheaterDictKeyStrictness:
    def test_empty_string_theater_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategicMapState(
                map_id="m",
                capital_theater_id="capital",
                theaters={"": _player_theater()},
                shapes=(_shape(),),
            )

    def test_non_string_theater_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategicMapState.model_validate(
                {
                    "map_id": "m",
                    "capital_theater_id": "capital",
                    "theaters": {123: _player_theater().model_dump()},
                    "shapes": [_shape().model_dump()],
                }
            )

    def test_overlength_theater_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategicMapState(
                map_id="m",
                capital_theater_id="capital",
                theaters={"x" * 65: _player_theater()},
                shapes=(_shape(),),
            )

    def test_sixty_four_char_theater_key_is_accepted(self) -> None:
        key = "x" * 64
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id=key,
            theaters={key: _player_theater()},
            shapes=(_shape(),),
        )
        assert key in state_map.theaters


class TestHelperFixture:
    def test_make_minimal_strategic_map_is_itself_valid_and_player_owned(self) -> None:
        state_map = make_minimal_strategic_map("arken")
        capital = state_map.theaters[state_map.capital_theater_id]
        assert isinstance(capital.owner, PlayerCountryRef)
        assert capital.owner.country_id == "arken"
