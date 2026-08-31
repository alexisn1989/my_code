"""Tests for `app.simulation.geography` — the strategic map's pure enums, identifier/coordinate
types, construction-layer error codes and the two pure helpers (Strategic Military Map, Gate M0
commit 3).

The Pydantic models that USE these types (`RouteState`, `CountryShapeState`, `StrategicMapState`)
live in `app.simulation.state` and land in a later commit; their construction-validator tests are
appended to this file once those models exist, matching the plan's test-matrix mapping of every
map construction code to `test_geography.py`.
"""

from __future__ import annotations

import math
import random

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
        assert frozenset({
            ROUTE_SELF_EDGE,
            ROUTE_DUPLICATE,
            ROUTE_NOT_CANONICAL,
            SHAPE_ID_DUPLICATE,
            SHAPE_NOT_CANONICAL,
            SHAPE_POLYGON_CLOSING_VERTEX_REPEATED,
            SHAPE_POLYGON_REPEATS_VERTEX,
            SHAPE_POLYGON_ZERO_AREA,
        }) == MAP_CONSTRUCTION_CODES

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
