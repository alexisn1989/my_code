"""Durable proofs for the AUTHORED fictional map geometry (Strategic Military Map Gate M0,
fictional-geography revision, `docs/plans/strategic-map-m0-fictional-geography-revision.md`).

The maps stopped being 5-vertex placeholders and became authored coastlines with bays, capes,
peninsulas and an offshore island group. At that complexity the eye stops being a reliable
auditor: a 36-vertex ring can self-intersect, swallow a neighbour's interior, or strand a theater
centroid in open water without looking obviously wrong in a screenshot. So every property the
revision promises is proven here, mechanically.

WHY THE LAND-ROUTE CHECK IS EXACT, NOT SAMPLED. The proposal stage sampled 160 points along each
route. Sampling can only ever fail to find a gap -- it cannot prove one is absent, and the gap it
misses is exactly the narrow strait a sample step happens to straddle. This module instead
intersects each route with every polygon edge, partitions the segment at those crossings, and
classifies each resulting piece. Parameters stay exact `Fraction`s over integer vertex
coordinates, so there is no epsilon and no floating-point tolerance anywhere in the decision.

A validator that cannot fail proves nothing, so `TestTheValidatorActuallyFails` feeds this module
a route across a concave water gap and a deliberately self-intersecting ring, and requires both to
be REJECTED.

Everything here is test support. No runtime invariant, no production helper and no dependency is
added: the geometry uses the standard library only, and the state model's own construction-time
validators are untouched.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from app.content.scenarios import load_scenario_file
from app.simulation.geography import MAP_GRID_MAX, shoelace_doubled_area
from app.simulation.state import GameState, PlayerCountryRef
from tests.conftest import SCENARIO_DIR

SCENARIOS = ("tiny_valid", "decree_state", "deficit_demo")

Point = tuple[int, int]
Polygon = tuple[Point, ...]

# The borders the revision declares as deliberately shared, and the exact segment count each one
# contributes. A shared border is only a border if both rings walk the SAME vertices; two
# nearly-coincident coastlines would leave a sliver of no-man's-land no player could interpret.
DECLARED_SHARED_BORDERS: dict[str, list[tuple[str, str, int]]] = {
    "tiny_valid": [("shape_arken", "shape_kessia", 8), ("shape_kessia", "shape_vetruska", 6)],
    "decree_state": [("shape_valdrun", "shape_marnil", 8), ("shape_marnil", "shape_sorrend", 6)],
    "deficit_demo": [("shape_strapped", "shape_marnil", 8)],
}


def load(scenario: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / f"{scenario}.yaml")


def committed_yaml(scenario: str) -> dict:
    return yaml.safe_load((SCENARIO_DIR / f"{scenario}.yaml").read_text())


# --- exact integer / rational geometry ---------------------------------------


def cross(o: Point, a: Point, b: Point) -> int:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def on_segment(a: Point, point: tuple, b: Point) -> bool:
    """Whether `point` lies within segment `ab`'s bounding box (given the three are collinear)."""
    return min(a[0], b[0]) <= point[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= point[1] <= max(
        a[1], b[1]
    )


def edges(polygon: Polygon):
    count = len(polygon)
    for index in range(count):
        yield polygon[index], polygon[(index + 1) % count]


def segments_cross(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """A proper crossing, or a collinear overlap that is not merely a shared endpoint."""
    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    shared = {p1, p2} & {p3, p4}
    for a, b, c in ((p3, p4, p1), (p3, p4, p2), (p1, p2, p3), (p1, p2, p4)):
        if cross(a, b, c) == 0 and on_segment(a, c, b) and c not in shared:
            return True
    return False


def self_intersects(polygon: Polygon) -> bool:
    count = len(polygon)
    for i in range(count):
        a1, a2 = polygon[i], polygon[(i + 1) % count]
        for j in range(i + 1, count):
            if (j + 1) % count == i or (i + 1) % count == j:
                continue
            b1, b2 = polygon[j], polygon[(j + 1) % count]
            if segments_cross(a1, a2, b1, b2):
                return True
    return False


def point_strictly_inside(point: tuple, polygon: Polygon) -> bool:
    """Ray casting with exact arithmetic. A point ON the boundary is NOT strictly inside."""
    if point_on_boundary(point, polygon):
        return False
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in edges(polygon):
        if (y1 > y) != (y2 > y):
            crossing_x = Fraction(x2 - x1) * Fraction(y - y1) / Fraction(y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def point_on_boundary(point: tuple, polygon: Polygon) -> bool:
    for a, b in edges(polygon):
        # Collinear with the edge, and within its extent.
        if (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
            point[0] - a[0]
        ) == 0 and on_segment(a, point, b):
            return True
    return False


def point_in_or_on(point: tuple, polygon: Polygon) -> bool:
    return point_on_boundary(point, polygon) or point_strictly_inside(point, polygon)


def segment_stays_on_land(start: Point, end: Point, land: list[Polygon]) -> tuple[bool, str]:
    """EXACT containment: partition the segment at every boundary crossing, then classify each
    piece by its own midpoint. Returns (ok, explanation-when-not)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    parameters: set[Fraction] = {Fraction(0), Fraction(1)}

    for polygon in land:
        for a, b in edges(polygon):
            ex, ey = b[0] - a[0], b[1] - a[1]
            denominator = dx * ey - dy * ex
            if denominator == 0:
                continue  # parallel or collinear: contributes no isolated crossing parameter
            t = Fraction((a[0] - start[0]) * ey - (a[1] - start[1]) * ex, denominator)
            u = Fraction((a[0] - start[0]) * dy - (a[1] - start[1]) * dx, denominator)
            if 0 <= t <= 1 and 0 <= u <= 1:
                parameters.add(t)

    ordered = sorted(parameters)
    for left, right in zip(ordered, ordered[1:], strict=False):
        middle = (left + right) / 2
        midpoint = (start[0] + dx * middle, start[1] + dy * middle)
        if not any(point_in_or_on(midpoint, polygon) for polygon in land):
            return False, f"subsegment t=[{left}, {right}] leaves land at {midpoint}"
    return True, ""


# --- the authored maps -------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
class TestAuthoredPolygons:
    def test_every_polygon_is_a_valid_open_ring_inside_the_grid(self, scenario: str) -> None:
        for shape in load(scenario).world.strategic_map.shapes:
            polygon = shape.polygon
            assert len(polygon) >= 3, shape.shape_id
            assert len(set(polygon)) == len(polygon), f"{shape.shape_id} repeats a vertex"
            assert polygon[0] != polygon[-1], f"{shape.shape_id} repeats its closing vertex"
            for a, b in zip(polygon, polygon[1:], strict=False):
                assert a != b, f"{shape.shape_id} has a duplicate consecutive vertex {a}"
            for x, y in polygon:
                assert 0 <= x <= MAP_GRID_MAX and 0 <= y <= MAP_GRID_MAX, shape.shape_id
            assert shoelace_doubled_area(polygon) != 0, f"{shape.shape_id} encloses zero area"

    def test_no_polygon_self_intersects(self, scenario: str) -> None:
        for shape in load(scenario).world.strategic_map.shapes:
            assert not self_intersects(shape.polygon), f"{shape.shape_id} self-intersects"

    def test_no_two_sovereigns_overlap_in_their_interiors(self, scenario: str) -> None:
        """Shared BORDERS are legal and intended; shared INTERIOR is not. Every vertex of every
        shape is checked against every other sovereign's rings, which catches an overlap that a
        coarse point sweep could step over."""
        shapes = load(scenario).world.strategic_map.shapes
        for shape in shapes:
            for other in shapes:
                if other.owner == shape.owner:
                    continue
                for vertex in shape.polygon:
                    assert not point_strictly_inside(vertex, other.polygon), (
                        f"{shape.shape_id} vertex {vertex} lies inside {other.shape_id}"
                    )

    def test_shapes_stay_in_canonical_order(self, scenario: str) -> None:
        ids = [s.shape_id for s in load(scenario).world.strategic_map.shapes]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    def test_declared_shared_borders_are_exactly_matching_segments(self, scenario: str) -> None:
        by_id = {s.shape_id: s.polygon for s in load(scenario).world.strategic_map.shapes}
        for left, right, expected in DECLARED_SHARED_BORDERS[scenario]:
            shared = {frozenset(e) for e in edges(by_id[left])} & {
                frozenset(e) for e in edges(by_id[right])
            }
            assert len(shared) == expected, (
                f"{left}|{right}: {len(shared)} exactly shared segments, expected {expected}"
            )


@pytest.mark.parametrize("scenario", SCENARIOS)
class TestTheatersAndRoutes:
    def test_every_theater_centroid_sits_inside_its_own_sovereigns_territory(
        self, scenario: str
    ) -> None:
        strategic_map = load(scenario).world.strategic_map
        for theater_id, theater in strategic_map.theaters.items():
            owned = [s.polygon for s in strategic_map.shapes if s.owner == theater.owner]
            point = (theater.presentation.centroid_x, theater.presentation.centroid_y)
            assert owned, f"{theater_id}: its owner holds no shape at all"
            assert any(point_strictly_inside(point, polygon) for polygon in owned), (
                f"{theater_id}: centroid {point} is not inside its own sovereign's territory"
            )

    def test_the_capital_sits_inside_player_owned_territory(self, scenario: str) -> None:
        strategic_map = load(scenario).world.strategic_map
        capital = strategic_map.theaters[strategic_map.capital_theater_id]
        player_land = [
            s.polygon for s in strategic_map.shapes if isinstance(s.owner, PlayerCountryRef)
        ]
        point = (capital.presentation.centroid_x, capital.presentation.centroid_y)
        assert any(point_strictly_inside(point, polygon) for polygon in player_land)

    def test_every_route_endpoint_resolves(self, scenario: str) -> None:
        strategic_map = load(scenario).world.strategic_map
        for route in strategic_map.routes:
            assert route.from_theater in strategic_map.theaters
            assert route.to_theater in strategic_map.theaters

    def test_every_land_route_stays_on_land_by_exact_partition(self, scenario: str) -> None:
        """The route a player sees drawn between two theaters must not cross open sea. Checked by
        exact partition, never by sampling -- see this module's docstring."""
        strategic_map = load(scenario).world.strategic_map
        land = [s.polygon for s in strategic_map.shapes]
        for route in strategic_map.routes:
            if route.kind.value != "land":
                continue
            start_theater = strategic_map.theaters[route.from_theater]
            end_theater = strategic_map.theaters[route.to_theater]
            start = (start_theater.presentation.centroid_x, start_theater.presentation.centroid_y)
            end = (end_theater.presentation.centroid_x, end_theater.presentation.centroid_y)
            ok, why = segment_stays_on_land(start, end, land)
            assert ok, f"land route {route.from_theater}->{route.to_theater}: {why}"


class TestTopologyIsUnchangedByTheRevision:
    """The revision re-authored geometry only. These pin the things it promised NOT to move."""

    EXPECTED_ROUTES: dict[str, list[tuple[str, str, str]]] = {
        "tiny_valid": [
            ("arken_capital", "arken_coast", "land"),
            ("arken_capital", "arken_north", "land"),
            ("arken_coast", "arken_capital", "land"),
            ("arken_north", "arken_capital", "land"),
            ("arken_north", "kessia_south", "land"),
            ("kessia_south", "arken_north", "land"),
            ("kessia_south", "vetruska_frontier", "land"),
            ("vetruska_frontier", "kessia_south", "land"),
        ],
        "decree_state": [
            ("marnil_border", "sorrend_plain", "land"),
            ("marnil_border", "valdrun_east", "land"),
            ("sorrend_plain", "marnil_border", "land"),
            ("valdrun_capital", "valdrun_east", "land"),
            ("valdrun_capital", "valdrun_highlands", "land"),
            ("valdrun_east", "marnil_border", "land"),
            ("valdrun_east", "valdrun_capital", "land"),
            ("valdrun_highlands", "valdrun_capital", "land"),
        ],
        "deficit_demo": [
            ("home_capital", "home_lowlands", "land"),
            ("home_capital", "home_port", "land"),
            ("home_lowlands", "home_capital", "land"),
            ("home_lowlands", "marnil_march", "land"),
            ("home_port", "home_capital", "land"),
            ("marnil_march", "home_lowlands", "land"),
        ],
    }
    EXPECTED_CAPITAL = {
        "tiny_valid": "arken_capital",
        "decree_state": "valdrun_capital",
        "deficit_demo": "home_capital",
    }

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_the_directed_route_graph_is_exactly_as_before(self, scenario: str) -> None:
        routes = [
            (r.from_theater, r.to_theater, r.kind.value)
            for r in load(scenario).world.strategic_map.routes
        ]
        assert routes == self.EXPECTED_ROUTES[scenario]

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_the_capital_is_exactly_as_before(self, scenario: str) -> None:
        assert (
            load(scenario).world.strategic_map.capital_theater_id == self.EXPECTED_CAPITAL[scenario]
        )

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_theater_identity_kind_and_owner_are_exactly_as_before(self, scenario: str) -> None:
        expected = {
            "tiny_valid": {
                "arken_capital": ("Arken Capital Region", "land", "arken"),
                "arken_coast": ("Arken Coast", "coastal", "arken"),
                "arken_north": ("Northern March", "land", "arken"),
                "kessia_south": ("Southern Kessia", "land", "kessia"),
                "vetruska_frontier": ("Vetruskan Frontier", "land", "vetruska"),
            },
            "decree_state": {
                "marnil_border": ("Marnil Borderland", "land", "marnil"),
                "sorrend_plain": ("Sorrend Plain", "land", "sorrend"),
                "valdrun_capital": ("Valdrun Capital Region", "land", "valdrun"),
                "valdrun_east": ("Eastern Valdrun", "land", "valdrun"),
                "valdrun_highlands": ("Valdrun Highlands", "land", "valdrun"),
            },
            "deficit_demo": {
                "home_capital": ("Capital Region", "land", "strapped"),
                "home_lowlands": ("Lowlands", "land", "strapped"),
                "home_port": ("Port District", "coastal", "strapped"),
                "marnil_march": ("Marnil March", "land", "marnil"),
                "tolvane_isle": ("Tolvane Isle", "coastal", "tolvane"),
            },
        }[scenario]
        theaters = load(scenario).world.strategic_map.theaters
        assert set(theaters) == set(expected)
        for theater_id, (name, kind, owner_id) in expected.items():
            theater = theaters[theater_id]
            assert theater.display_name == name
            assert theater.kind.value == kind
            owner = theater.owner
            actual_owner = (
                owner.country_id
                if isinstance(owner, PlayerCountryRef)
                else owner.foreign_profile_id
            )
            assert actual_owner == owner_id

    def test_marnil_is_byte_identical_in_both_scenarios_it_appears_in(self) -> None:
        """A recurring foreign power with two unrelated silhouettes would be a continuity error the
        player would notice before any test did."""

        def marnil(scenario: str):
            return next(
                s.polygon
                for s in load(scenario).world.strategic_map.shapes
                if s.shape_id == "shape_marnil"
            )

        assert marnil("decree_state") == marnil("deficit_demo")
        assert len(marnil("decree_state")) >= 20

    def test_tolvane_isle_is_routeless_and_its_island_touches_nobody(self) -> None:
        strategic_map = load("deficit_demo").world.strategic_map
        touching = [
            (r.from_theater, r.to_theater)
            for r in strategic_map.routes
            if "tolvane_isle" in (r.from_theater, r.to_theater)
        ]
        assert touching == [], f"tolvane_isle must stay routeless; found {touching}"

        by_id = {s.shape_id: s.polygon for s in strategic_map.shapes}
        island_edges = {frozenset(e) for e in edges(by_id["shape_tolvane"])}
        for other in ("shape_marnil", "shape_strapped"):
            assert not (island_edges & {frozenset(e) for e in edges(by_id[other])}), (
                f"shape_tolvane shares a border with {other}; it must be an isle"
            )

    def test_shape_arken_isles_is_decoration_and_owns_no_mechanic(self) -> None:
        """The isles are scenery: player-owned area with no theater, no route and no other game
        object anywhere in the scenario referring to them."""
        state = load("tiny_valid")
        strategic_map = state.world.strategic_map
        isles = next(s for s in strategic_map.shapes if s.shape_id == "shape_arken_isles")
        assert isinstance(isles.owner, PlayerCountryRef)
        assert isles.owner == next(
            s.owner for s in strategic_map.shapes if s.shape_id == "shape_arken"
        )

        # No theater sits on the isles, so nothing can be routed to or from them.
        for theater_id, theater in strategic_map.theaters.items():
            point = (theater.presentation.centroid_x, theater.presentation.centroid_y)
            assert not point_in_or_on(point, isles.polygon), (
                f"{theater_id} sits on the decorative isles"
            )

        # And the id appears nowhere else in the scenario document.
        raw = (SCENARIO_DIR / "tiny_valid.yaml").read_text()
        assert raw.count("shape_arken_isles") == 1


class TestTheValidatorActuallyFails:
    """Negative controls. Without these, every assertion above could be vacuously true."""

    def test_a_route_across_a_concave_water_gap_is_rejected(self) -> None:
        """Two lobes joined only in the north, with a bay between them: a straight route between
        the lobes crosses water even though both endpoints are on land. This is exactly the case
        point-sampling can step over, and it must be caught."""
        horseshoe: Polygon = (
            (0, 0),
            (1000, 0),
            (1000, 1000),
            (600, 1000),
            (600, 200),
            (400, 200),
            (400, 1000),
            (0, 1000),
        )
        inside_left = (200, 900)
        inside_right = (800, 900)
        assert point_strictly_inside(inside_left, horseshoe)
        assert point_strictly_inside(inside_right, horseshoe)

        ok, why = segment_stays_on_land(inside_left, inside_right, [horseshoe])
        assert not ok, "the validator failed to notice a route crossing the bay"
        assert "leaves land" in why

        # ...and a route that genuinely stays on land is accepted, so it is not simply rejecting
        # everything.
        ok_north, _ = segment_stays_on_land((200, 100), (800, 100), [horseshoe])
        assert ok_north

    def test_a_self_intersecting_ring_is_rejected(self) -> None:
        bowtie: Polygon = ((0, 0), (1000, 1000), (1000, 0), (0, 1000))
        assert self_intersects(bowtie)
        # A plain rectangle is not flagged, so the check is not simply always true.
        assert not self_intersects(((0, 0), (1000, 0), (1000, 1000), (0, 1000)))

    def test_interior_overlap_detection_is_not_vacuous(self) -> None:
        outer: Polygon = ((0, 0), (1000, 0), (1000, 1000), (0, 1000))
        assert point_strictly_inside((500, 500), outer)
        assert not point_strictly_inside((2000, 500), outer)
        # A point exactly on the boundary is a shared BORDER, not an interior overlap.
        assert not point_strictly_inside((1000, 500), outer)
        assert point_on_boundary((1000, 500), outer)


def test_the_authored_maps_are_actually_rich_enough_to_need_these_checks() -> None:
    """Guards the whole module against silently reverting to placeholder geometry: if the maps
    were simplified back to 5-vertex blobs, every check above would still pass while the reviewed
    design was gone."""
    counts = {
        shape.shape_id: len(shape.polygon)
        for scenario in SCENARIOS
        for shape in load(scenario).world.strategic_map.shapes
    }
    majors = {name: count for name, count in counts.items() if name != "shape_arken_isles"}
    assert min(majors.values()) >= 15, majors
    assert max(majors.values()) <= 50, majors
    assert counts["shape_arken_isles"] >= 4


def test_the_scenario_files_still_parse_as_yaml_with_only_the_expected_map_keys() -> None:
    for scenario in SCENARIOS:
        strategic_map = committed_yaml(scenario)["strategic_map"]
        assert set(strategic_map) == {
            "map_id",
            "capital_theater_id",
            "theaters",
            "routes",
            "shapes",
        }
        assert Path(SCENARIO_DIR / f"{scenario}.yaml").read_bytes().count(b"\x00") == 0
