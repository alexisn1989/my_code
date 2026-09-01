"""Tests for `_check_strategic_map` (Strategic Military Map, Gate M0 sec.9) -- the every-turn,
bypassed-construction backstop for `StrategicMapState`/`TheaterState`/`RouteState`/
`CountryShapeState`, mirroring `test_foreign_state.py`'s role for `_check_foreign_conflicts`.

Every rule here is already enforced at construction time by the models themselves; these tests
prove the SAME defect is also caught by `check_invariants` once construction is bypassed via
`model_copy` (which never revalidates), and that each of the eight reachable codes fires
independently.
"""

from __future__ import annotations

from app.simulation.geography import LabelAnchor, TheaterKind
from app.simulation.invariants import check_invariants
from app.simulation.state import (
    CountryShapeState,
    ForeignProfileRef,
    ForeignProfileState,
    GameState,
    PlayerCountryRef,
    RouteState,
    SovereignRef,
    StrategicMapState,
    TheaterPresentation,
    TheaterState,
)
from tests.conftest import make_country, make_game_state

_ALL_MAP_CODES = {
    "route_endpoint_unknown",
    "map_owner_country_unknown",
    "map_player_ref_not_player",
    "map_owner_profile_unknown",
    "shape_missing_for_owner",
    "map_capital_unknown",
    "map_capital_not_player_owned",
    "player_land_component_disconnected",
}


def _codes(state: GameState) -> set[str]:
    return {v.code for v in check_invariants(state)}


def _foreign_profile(display_name: str = "Kessia", capability: int = 5_000) -> ForeignProfileState:
    return ForeignProfileState(display_name=display_name, war_capability_bps=capability)


def _presentation() -> TheaterPresentation:
    return TheaterPresentation(centroid_x=1, centroid_y=1, label_anchor=LabelAnchor.CENTER)


def _theater(owner: SovereignRef) -> TheaterState:
    return TheaterState(
        display_name="Theater", kind=TheaterKind.LAND, owner=owner, presentation=_presentation()
    )


def _shape(shape_id: str, owner: SovereignRef) -> CountryShapeState:
    return CountryShapeState(
        shape_id=shape_id, owner=owner, polygon=((0, 0), (10, 0), (10, 10), (0, 10))
    )


def _with_map_bypassed(state: GameState, strategic_map: StrategicMapState) -> GameState:
    """Splice `strategic_map` into `state.world` via a `model_copy` chain, which never
    revalidates anything -- unlike a normal constructor call, which would re-run
    `StrategicMapState`'s own validators and defeat the bypass before `check_invariants` is ever
    reached. Mirrors `test_foreign_state.py`'s `_with_dyads_bypassed`."""
    bad_world = state.world.model_copy(update={"strategic_map": strategic_map})
    return state.model_copy(update={"world": bad_world})


def _valid_two_theater_map(player_country_id: str) -> StrategicMapState:
    owner = PlayerCountryRef(country_id=player_country_id)
    return StrategicMapState(
        map_id="m",
        capital_theater_id="capital",
        theaters={"capital": _theater(owner), "north": _theater(owner)},
        routes=(
            RouteState(from_theater="capital", to_theater="north", kind="land"),
            RouteState(from_theater="north", to_theater="capital", kind="land"),
        ),
        shapes=(_shape("s_owner", owner),),
    )


class TestCleanMap:
    def test_the_default_minimal_map_produces_no_strategic_map_violations(self) -> None:
        state = make_game_state()
        assert _codes(state).isdisjoint(_ALL_MAP_CODES)

    def test_a_valid_two_theater_connected_map_produces_no_violations(self) -> None:
        state = make_game_state()
        state = make_game_state(strategic_map=_valid_two_theater_map(state.world.player_country_id))
        assert _codes(state).isdisjoint(_ALL_MAP_CODES)


class TestRouteEndpointUnknown:
    def test_route_referencing_unknown_theater_is_caught_when_bypassed(self) -> None:
        base = make_game_state()
        good_map = _valid_two_theater_map(base.world.player_country_id)
        bad_map = good_map.model_copy(
            update={
                "routes": (RouteState(from_theater="capital", to_theater="nowhere", kind="land"),)
            }
        )
        bypassed = _with_map_bypassed(base, bad_map)
        assert "route_endpoint_unknown" in _codes(bypassed)


class TestOwnerResolutionSharedRule:
    """§9.1: one rule, applied identically to theater owners and shape owners."""

    def test_theater_with_unknown_player_country_id_is_caught(self) -> None:
        base = make_game_state()
        owner = PlayerCountryRef(country_id="nonexistent_country")
        bad_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(owner)},
            shapes=(_shape("s", owner),),
        )
        bypassed = _with_map_bypassed(base, bad_map)
        assert "map_owner_country_unknown" in _codes(bypassed)

    def test_theater_owned_by_a_real_but_non_player_country_is_caught(self) -> None:
        state = make_game_state()
        countries = dict(state.world.countries)
        countries["otherland"] = make_country("otherland")
        state = state.model_copy(
            update={"world": state.world.model_copy(update={"countries": countries})}
        )
        owner = PlayerCountryRef(country_id="otherland")
        bad_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(owner)},
            shapes=(_shape("s", owner),),
        )
        bypassed = _with_map_bypassed(state, bad_map)
        assert "map_player_ref_not_player" in _codes(bypassed)

    def test_theater_with_unknown_foreign_profile_id_is_caught(self) -> None:
        base = make_game_state()
        player_owner = PlayerCountryRef(country_id=base.world.player_country_id)
        foreign_owner = ForeignProfileRef(foreign_profile_id="nonexistent_profile")
        bad_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(player_owner), "abroad": _theater(foreign_owner)},
            shapes=(_shape("s_foreign", foreign_owner), _shape("s_player", player_owner)),
        )
        bypassed = _with_map_bypassed(base, bad_map)
        assert "map_owner_profile_unknown" in _codes(bypassed)

    def test_the_same_code_fires_identically_for_a_bad_theater_owner_and_a_bad_shape_owner(
        self,
    ) -> None:
        base = make_game_state()
        cid = base.world.player_country_id
        bad_owner = PlayerCountryRef(country_id="nonexistent_country")

        bad_theater_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(bad_owner)},
            shapes=(_shape("s", bad_owner),),
        )
        theater_violation = next(
            v
            for v in check_invariants(_with_map_bypassed(base, bad_theater_map))
            if v.code == "map_owner_country_unknown"
        )
        assert "theater" in theater_violation.message

        good_owner = PlayerCountryRef(country_id=cid)
        bad_shape_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(good_owner)},
            shapes=(_shape("s", bad_owner),),
        )
        shape_violation = next(
            v
            for v in check_invariants(_with_map_bypassed(base, bad_shape_map))
            if v.code == "map_owner_country_unknown"
        )
        assert "shape" in shape_violation.message


class TestShapeMissingForOwner:
    def test_theater_owner_missing_a_shape_is_caught(self) -> None:
        base = make_game_state(foreign_profiles={"kessia": _foreign_profile()})
        player_owner = PlayerCountryRef(country_id=base.world.player_country_id)
        foreign_owner = ForeignProfileRef(foreign_profile_id="kessia")
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(player_owner), "abroad": _theater(foreign_owner)},
            # Only kessia has a shape; the player theater owner has none.
            shapes=(_shape("s_foreign", foreign_owner),),
        )
        bypassed = _with_map_bypassed(base, state_map)
        assert "shape_missing_for_owner" in _codes(bypassed)


class TestCapitalInvariants:
    def test_capital_theater_id_not_a_key_is_caught(self) -> None:
        base = make_game_state()
        bad_map = _valid_two_theater_map(base.world.player_country_id).model_copy(
            update={"capital_theater_id": "nowhere"}
        )
        bypassed = _with_map_bypassed(base, bad_map)
        assert "map_capital_unknown" in _codes(bypassed)

    def test_capital_owned_by_a_foreign_profile_is_caught(self) -> None:
        base = make_game_state(foreign_profiles={"kessia": _foreign_profile()})
        foreign_owner = ForeignProfileRef(foreign_profile_id="kessia")
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(foreign_owner)},
            shapes=(_shape("s", foreign_owner),),
        )
        bypassed = _with_map_bypassed(base, state_map)
        assert "map_capital_not_player_owned" in _codes(bypassed)


class TestPlayerLandConnectivity:
    def test_disconnected_player_theater_is_caught(self) -> None:
        base = make_game_state()
        owner = PlayerCountryRef(country_id=base.world.player_country_id)
        bad_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(owner), "isolated": _theater(owner)},
            routes=(),  # no route connects them
            shapes=(_shape("s", owner),),
        )
        bypassed = _with_map_bypassed(base, bad_map)
        assert "player_land_component_disconnected" in _codes(bypassed)

    def test_routeless_foreign_island_is_valid_and_does_not_trip_connectivity(self) -> None:
        player_owner_holder = make_game_state()
        cid = player_owner_holder.world.player_country_id
        player_owner = PlayerCountryRef(country_id=cid)
        foreign_owner = ForeignProfileRef(foreign_profile_id="tolvane")
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id="capital",
            theaters={"capital": _theater(player_owner), "isle": _theater(foreign_owner)},
            routes=(),
            shapes=(_shape("s_foreign", foreign_owner), _shape("s_player", player_owner)),
        )
        state = make_game_state(
            foreign_profiles={"tolvane": _foreign_profile("Tolvane")}, strategic_map=state_map
        )
        assert "player_land_component_disconnected" not in _codes(state)
