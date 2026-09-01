"""Tests for `app.simulation.geography` — the strategic map's pure enums, identifier/coordinate
types, construction-layer error codes and the two pure helpers (Strategic Military Map, Gate M0),
plus the construction-validator tests for `RouteState`/`CountryShapeState`/`StrategicMapState`.

Those three Pydantic models live in `app.simulation.state`, not here (`geography.py` cannot
import them without a circular import -- see `DirectedEdge`'s docstring), but their tests live in
this file per the plan's test-matrix mapping of every map construction code to
`test_geography.py`.
"""

from __future__ import annotations

import math
import random

import pytest
from pydantic import ValidationError

from app.simulation.geography import (
    MAP_CONSTRUCTION_CODES,
    MAP_GRID_MAX,
    ROUTE_DUPLICATE,
    ROUTE_NOT_CANONICAL,
    ROUTE_SELF_EDGE,
    SHAPE_ID_DUPLICATE,
    SHAPE_NOT_CANONICAL,
    SHAPE_POLYGON_CLOSING_VERTEX_REPEATED,
    SHAPE_POLYGON_REPEATS_VERTEX,
    SHAPE_POLYGON_ZERO_AREA,
    LabelAnchor,
    RouteKind,
    TheaterKind,
    outgoing_and_incoming,
    shoelace_doubled_area,
)
from app.simulation.state import (
    CountryShapeState,
    ForeignProfileRef,
    PlayerCountryRef,
    RouteState,
    StrategicMapState,
    TheaterPresentation,
    TheaterState,
)


class _Edge:
    """A minimal `DirectedEdge`-shaped object for exercising `outgoing_and_incoming` without
    depending on `state.RouteState`, which `geography.py` cannot import."""

    def __init__(self, from_theater: str, to_theater: str) -> None:
        self.from_theater = from_theater
        self.to_theater = to_theater


class TestEnums:
    def test_theater_kind_is_exactly_land_and_coastal(self) -> None:
        assert {member.value for member in TheaterKind} == {"land", "coastal"}

    def test_route_kind_is_exactly_land(self) -> None:
        assert {member.value for member in RouteKind} == {"land"}

    def test_label_anchor_is_exactly_the_five_compass_and_center_values(self) -> None:
        assert {member.value for member in LabelAnchor} == {"n", "s", "e", "w", "center"}


class TestConstructionCodes:
    def test_map_construction_codes_contains_exactly_the_eight_named_constants(self) -> None:
        assert (
            frozenset(
                {
                    ROUTE_SELF_EDGE,
                    ROUTE_DUPLICATE,
                    ROUTE_NOT_CANONICAL,
                    SHAPE_ID_DUPLICATE,
                    SHAPE_NOT_CANONICAL,
                    SHAPE_POLYGON_CLOSING_VERTEX_REPEATED,
                    SHAPE_POLYGON_REPEATS_VERTEX,
                    SHAPE_POLYGON_ZERO_AREA,
                }
            )
            == MAP_CONSTRUCTION_CODES
        )

    def test_every_construction_code_is_a_distinct_nonempty_string(self) -> None:
        assert len(MAP_CONSTRUCTION_CODES) == 8
        for code in MAP_CONSTRUCTION_CODES:
            assert isinstance(code, str)
            assert code


class TestShoelaceDoubledArea:
    def test_unit_square_has_doubled_area_two(self) -> None:
        square = ((0, 0), (1, 0), (1, 1), (0, 1))
        assert shoelace_doubled_area(square) == 2

    def test_reversed_winding_negates_the_result(self) -> None:
        ccw = ((0, 0), (1, 0), (1, 1), (0, 1))
        cw = tuple(reversed(ccw))
        assert shoelace_doubled_area(cw) == -shoelace_doubled_area(ccw)

    def test_odd_area_triangle_stays_exact_and_integral(self) -> None:
        # Area 1.5 -> doubled area 3, an odd integer: proves no floor/round hides a fraction.
        triangle = ((0, 0), (3, 0), (0, 1))
        assert shoelace_doubled_area(triangle) == 3

    def test_collinear_points_have_zero_doubled_area(self) -> None:
        collinear = ((0, 0), (1, 0), (2, 0))
        assert shoelace_doubled_area(collinear) == 0

    def test_degenerate_backtracking_polygon_has_zero_doubled_area(self) -> None:
        # Goes out and immediately back along the same line: encloses no area.
        backtrack = ((0, 0), (5, 0), (0, 0))
        assert shoelace_doubled_area(backtrack) == 0

    def test_rotating_the_starting_vertex_does_not_change_the_area(self) -> None:
        square = ((0, 0), (1, 0), (1, 1), (0, 1))
        rotated = ((1, 0), (1, 1), (0, 1), (0, 0))
        assert shoelace_doubled_area(square) == shoelace_doubled_area(rotated)

    def test_exactness_over_many_random_convex_polygons(self) -> None:
        # Cross-checks the shoelace formula against an independently-written reference
        # accumulation for 200 random convex polygons generated on a circle, so no case is
        # special-cased by hand.
        rng = random.Random(20260831)
        for _ in range(200):
            n = rng.randint(3, 12)
            angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
            radius = 1000
            points = tuple(
                (
                    round(radius * (1 + math.cos(a))),
                    round(radius * (1 + math.sin(a))),
                )
                for a in angles
            )
            # Skip the rare case where rounding collapsed two vertices onto each other.
            if len(set(points)) != len(points):
                continue
            assert shoelace_doubled_area(points) == _reference_shoelace_doubled_area(points)


def _reference_shoelace_doubled_area(polygon: tuple[tuple[int, int], ...]) -> int:
    """An independently-written reference implementation of the same formula, used only to
    cross-check `shoelace_doubled_area` over randomized input rather than exercising the same
    code path against itself."""
    total = 0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2
        total -= x2 * y1
    return total


class TestOutgoingAndIncoming:
    def test_no_routes_yields_two_empty_tuples(self) -> None:
        assert outgoing_and_incoming("a", []) == ((), ())

    def test_one_directed_route_is_outgoing_for_the_source_only(self) -> None:
        routes = [_Edge("a", "b")]
        assert outgoing_and_incoming("a", routes) == (("b",), ())
        assert outgoing_and_incoming("b", routes) == ((), ("a",))

    def test_reciprocal_routes_appear_on_both_sides(self) -> None:
        routes = [_Edge("a", "b"), _Edge("b", "a")]
        assert outgoing_and_incoming("a", routes) == (("b",), ("b",))
        assert outgoing_and_incoming("b", routes) == (("a",), ("a",))

    def test_results_are_sorted_regardless_of_input_order(self) -> None:
        routes = [_Edge("a", "z"), _Edge("a", "m"), _Edge("a", "b")]
        outgoing, _incoming = outgoing_and_incoming("a", routes)
        assert outgoing == ("b", "m", "z")

    def test_duplicate_neighbours_are_deduplicated(self) -> None:
        # Two routes of different kinds between the same pair (not representable once RouteKind
        # has more than LAND, but the helper must not double-count even so).
        routes = [_Edge("a", "b"), _Edge("a", "b")]
        assert outgoing_and_incoming("a", routes) == (("b",), ())

    def test_theater_with_no_matching_routes_is_isolated(self) -> None:
        routes = [_Edge("a", "b"), _Edge("b", "c")]
        assert outgoing_and_incoming("z", routes) == ((), ())


class TestGridBounds:
    def test_map_grid_max_is_ten_thousand(self) -> None:
        assert MAP_GRID_MAX == 10_000


# ===========================================================================
# Construction-validator tests for RouteState/CountryShapeState/StrategicMapState
# (Strategic Military Map, Gate M0 commit 4).
# ===========================================================================


def _presentation() -> TheaterPresentation:
    return TheaterPresentation(centroid_x=1, centroid_y=1, label_anchor=LabelAnchor.CENTER)


def _theater(owner_country_id: str = "arken") -> TheaterState:
    return TheaterState(
        display_name="Capital",
        kind=TheaterKind.LAND,
        owner=PlayerCountryRef(country_id=owner_country_id),
        presentation=_presentation(),
    )


def _shape(shape_id: str = "s", owner_country_id: str = "arken") -> CountryShapeState:
    return CountryShapeState(
        shape_id=shape_id,
        owner=PlayerCountryRef(country_id=owner_country_id),
        polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
    )


class TestRouteSelfEdge:
    def test_self_edge_route_is_rejected_with_the_route_self_edge_code(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            RouteState(from_theater="a", to_theater="a", kind=RouteKind.LAND)
        assert ROUTE_SELF_EDGE in str(exc_info.value)

    def test_distinct_endpoints_are_accepted(self) -> None:
        route = RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND)
        assert route.from_theater == "a"
        assert route.to_theater == "b"


class TestPlayerCountryRefAndForeignProfileRef:
    def test_player_country_ref_default_kind(self) -> None:
        assert PlayerCountryRef(country_id="arken").kind == "player_country"

    def test_foreign_profile_ref_default_kind(self) -> None:
        assert ForeignProfileRef(foreign_profile_id="kessia").kind == "foreign_profile"


class TestPolygonConstructionCodes:
    def test_repeated_closing_vertex_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CountryShapeState(
                shape_id="s",
                owner=PlayerCountryRef(country_id="arken"),
                polygon=((0, 0), (10, 0), (10, 10), (0, 0)),
            )
        assert SHAPE_POLYGON_CLOSING_VERTEX_REPEATED in str(exc_info.value)

    def test_duplicate_consecutive_vertex_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CountryShapeState(
                shape_id="s",
                owner=PlayerCountryRef(country_id="arken"),
                polygon=((0, 0), (5, 0), (5, 0), (10, 10)),
            )
        assert SHAPE_POLYGON_REPEATS_VERTEX in str(exc_info.value)

    def test_zero_area_collinear_polygon_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CountryShapeState(
                shape_id="s",
                owner=PlayerCountryRef(country_id="arken"),
                polygon=((0, 0), (5, 0), (10, 0)),
            )
        assert SHAPE_POLYGON_ZERO_AREA in str(exc_info.value)

    def test_fewer_than_three_vertices_is_a_pydantic_error(self) -> None:
        with pytest.raises(ValidationError):
            CountryShapeState(
                shape_id="s",
                owner=PlayerCountryRef(country_id="arken"),
                polygon=((0, 0), (10, 0)),
            )

    def test_coordinate_out_of_range_is_a_pydantic_error(self) -> None:
        with pytest.raises(ValidationError):
            CountryShapeState(
                shape_id="s",
                owner=PlayerCountryRef(country_id="arken"),
                polygon=((0, 0), (10, 0), (10, 10_001)),
            )

    def test_valid_polygon_is_accepted(self) -> None:
        shape = CountryShapeState(
            shape_id="s",
            owner=PlayerCountryRef(country_id="arken"),
            polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
        )
        assert len(shape.polygon) == 4

    def test_rings_differing_only_by_rotation_both_load_and_differ_in_stored_bytes(self) -> None:
        original = CountryShapeState(
            shape_id="s",
            owner=PlayerCountryRef(country_id="arken"),
            polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
        )
        rotated = CountryShapeState(
            shape_id="s",
            owner=PlayerCountryRef(country_id="arken"),
            polygon=((10, 0), (10, 10), (0, 10), (0, 0)),
        )
        assert original.polygon != rotated.polygon  # no rotation normalization

    def test_winding_is_stored_as_authored_not_normalized(self) -> None:
        ccw = CountryShapeState(
            shape_id="s",
            owner=PlayerCountryRef(country_id="arken"),
            polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
        )
        cw = CountryShapeState(
            shape_id="s",
            owner=PlayerCountryRef(country_id="arken"),
            polygon=tuple(reversed(ccw.polygon)),
        )
        assert ccw.polygon != cw.polygon  # both loaded; neither was reordered


class TestMapLevelDuplicateVsOrderingCodes:
    def test_route_duplicate_fires_without_tripping_ordering(self) -> None:
        # (a,b),(a,b) is already sorted, so ONLY the duplicate check can fire.
        with pytest.raises(ValidationError) as exc_info:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater(), "b": _theater()},
                routes=(
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                ),
                shapes=(_shape(),),
            )
        message = str(exc_info.value)
        assert ROUTE_DUPLICATE in message
        assert ROUTE_NOT_CANONICAL not in message

    def test_route_not_canonical_fires_without_any_duplicate(self) -> None:
        # (b,a) then (a,b): two DISTINCT pairs, out of order -- no duplicate exists.
        with pytest.raises(ValidationError) as exc_info:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater(), "b": _theater()},
                routes=(
                    RouteState(from_theater="b", to_theater="a", kind=RouteKind.LAND),
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                ),
                shapes=(_shape(),),
            )
        message = str(exc_info.value)
        assert ROUTE_NOT_CANONICAL in message
        assert ROUTE_DUPLICATE not in message

    def test_shape_id_duplicate_fires_without_tripping_ordering(self) -> None:
        # ['s_a', 's_a'] is already sorted, so ONLY the duplicate check can fire.
        with pytest.raises(ValidationError) as exc_info:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater()},
                shapes=(_shape("s_a"), _shape("s_a")),
            )
        message = str(exc_info.value)
        assert SHAPE_ID_DUPLICATE in message
        assert SHAPE_NOT_CANONICAL not in message

    def test_shape_not_canonical_fires_without_any_duplicate(self) -> None:
        # ['s_b', 's_a']: two DISTINCT ids, out of order -- no duplicate exists.
        with pytest.raises(ValidationError) as exc_info:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater()},
                shapes=(_shape("s_b"), _shape("s_a")),
            )
        message = str(exc_info.value)
        assert SHAPE_NOT_CANONICAL in message
        assert SHAPE_ID_DUPLICATE not in message

    def test_multiple_island_shapes_for_one_owner_are_accepted(self) -> None:
        state_map = StrategicMapState(
            map_id="m",
            capital_theater_id="a",
            theaters={"a": _theater()},
            shapes=(_shape("s_a"), _shape("s_b")),
        )
        assert len(state_map.shapes) == 2


class TestConstructionCodeReachability:
    """Confirms every member of `MAP_CONSTRUCTION_CODES` is reachable by a real constructor
    call -- so a code that stops firing fails this suite rather than lingering as dead
    documentation, per `MAP_CONSTRUCTION_CODES`'s own docstring."""

    def test_all_eight_codes_are_reachable(self) -> None:
        reached: set[str] = set()

        try:
            RouteState(from_theater="a", to_theater="a", kind=RouteKind.LAND)
        except ValidationError:
            reached.add(ROUTE_SELF_EDGE)

        for polygon, code in (
            (((0, 0), (10, 0), (10, 10), (0, 0)), SHAPE_POLYGON_CLOSING_VERTEX_REPEATED),
            (((0, 0), (5, 0), (5, 0), (10, 10)), SHAPE_POLYGON_REPEATS_VERTEX),
            (((0, 0), (5, 0), (10, 0)), SHAPE_POLYGON_ZERO_AREA),
        ):
            try:
                CountryShapeState(
                    shape_id="s", owner=PlayerCountryRef(country_id="arken"), polygon=polygon
                )
            except ValidationError:
                reached.add(code)

        try:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater(), "b": _theater()},
                routes=(
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                ),
                shapes=(_shape(),),
            )
        except ValidationError:
            reached.add(ROUTE_DUPLICATE)

        try:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater(), "b": _theater()},
                routes=(
                    RouteState(from_theater="b", to_theater="a", kind=RouteKind.LAND),
                    RouteState(from_theater="a", to_theater="b", kind=RouteKind.LAND),
                ),
                shapes=(_shape(),),
            )
        except ValidationError:
            reached.add(ROUTE_NOT_CANONICAL)

        try:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater()},
                shapes=(_shape("s_a"), _shape("s_a")),
            )
        except ValidationError:
            reached.add(SHAPE_ID_DUPLICATE)

        try:
            StrategicMapState(
                map_id="m",
                capital_theater_id="a",
                theaters={"a": _theater()},
                shapes=(_shape("s_b"), _shape("s_a")),
            )
        except ValidationError:
            reached.add(SHAPE_NOT_CANONICAL)

        assert reached == MAP_CONSTRUCTION_CODES
