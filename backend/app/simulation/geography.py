"""Strategic map geography (Strategic Military Map, Gate M0).

Pure enums, identifier/coordinate types and construction-layer error codes for the strategic
map. The state models that use these (`TheaterState`, `RouteState`, `CountryShapeState`,
`StrategicMapState`) live in `simulation.state` beside `WorldState`; this module holds only what
has no dependency on `state.py`, so `state.py` can import it with no risk of a cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Protocol, TypeAlias

from pydantic import Field

MAP_GRID_MAX = 10_000
"""The strategic map is authored on a fixed integer grid, 0..MAP_GRID_MAX on both axes.

Integers, not floats: the map is hashed into the save's canonical bytes, and float formatting is
not a stable serialization basis. A 10,001 x 10,001 lattice is far finer than any authored map
needs and leaves no reason to reach for fractional coordinates later.
"""

StrictMapId: TypeAlias = Annotated[str, Field(strict=True, min_length=1, max_length=64)]
"""Identifier for a map, theater, shape or owner reference. `strict=True` refuses int/None
coercion, the same discipline as `StrictMoney` (`app/core/money.py:41`)."""

StrictGridCoord: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=MAP_GRID_MAX)]
"""One axis of an authored grid position. Bounds are enforced by the annotation, so no
invariant re-checks them (see the ownership table, `docs/plans/strategic-military-map-m0-
implementation-plan.md` sec.9)."""

StrictDisplayName: TypeAlias = Annotated[str, Field(strict=True, min_length=1, max_length=64)]


# --- Construction-layer error codes ----------------------------------------
#
# These are STABLE, ASSERTABLE identifiers, not documentation. Every custom construction
# ValueError raised by the map models begins with its code followed by ": ", so a test can
# assert the code that actually reaches the caller rather than asserting a comment, a docstring
# or its own function name. Pydantic wraps the message but preserves it verbatim, so
# `code in str(exc_info.value)` is a true statement about emitted behaviour.

ROUTE_SELF_EDGE = "route_self_edge"
ROUTE_DUPLICATE = "route_duplicate"
ROUTE_NOT_CANONICAL = "route_not_canonical"
SHAPE_ID_DUPLICATE = "shape_id_duplicate"
SHAPE_NOT_CANONICAL = "shape_not_canonical"
SHAPE_POLYGON_CLOSING_VERTEX_REPEATED = "shape_polygon_closing_vertex_repeated"
SHAPE_POLYGON_REPEATS_VERTEX = "shape_polygon_repeats_vertex"
SHAPE_POLYGON_ZERO_AREA = "shape_polygon_zero_area"

MAP_CONSTRUCTION_CODES: frozenset[str] = frozenset({
    ROUTE_SELF_EDGE,
    ROUTE_DUPLICATE,
    ROUTE_NOT_CANONICAL,
    SHAPE_ID_DUPLICATE,
    SHAPE_NOT_CANONICAL,
    SHAPE_POLYGON_CLOSING_VERTEX_REPEATED,
    SHAPE_POLYGON_REPEATS_VERTEX,
    SHAPE_POLYGON_ZERO_AREA,
})
"""Every construction code M0 can emit. `test_geography.py` asserts that each member is
reachable by a real constructor call, so a code that stops firing fails the suite instead of
lingering as dead documentation."""


class TheaterKind(StrEnum):
    """M0 ships only the two kinds an army map needs.

    SEA and AIR_REGION arrive at M3, where they gain consumers. Declaring them now would ship
    unused state.
    """

    LAND = "land"
    COASTAL = "coastal"


class RouteKind(StrEnum):
    """M0 ships only LAND. SEA/AIR arrive at M3 alongside their theater kinds."""

    LAND = "land"


class LabelAnchor(StrEnum):
    """Where a theater's label sits relative to its node. Presentation only."""

    NORTH = "n"
    SOUTH = "s"
    EAST = "e"
    WEST = "w"
    CENTER = "center"


def shoelace_doubled_area(polygon: tuple[tuple[int, int], ...]) -> int:
    """Twice the signed area of a polygon, by the shoelace formula.

    Returns an EXACT integer: every term is a product of two integers, so there is no floating
    point anywhere and no epsilon comparison. Doubled (never halved) so the result stays integral
    for odd-area polygons.

    The SIGN encodes winding (positive = counter-clockwise in a y-up frame) and is deliberately
    NOT used by any validator: M0 stores polygons exactly as authored and normalizes neither
    winding nor starting vertex. Only `== 0` is tested, which detects a degenerate polygon whose
    vertices are collinear or backtrack onto themselves.
    """
    total = 0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return total


class DirectedEdge(Protocol):
    """Structural type for anything with a directed from/to pair.

    `geography.py` is imported BY `state.py`, so it can never import `RouteState` back -- not at
    runtime, and not under `TYPE_CHECKING` without inviting a cycle the next refactor trips over.
    A Protocol resolves this properly instead of papering over it: `RouteState` satisfies it
    structurally, mypy checks the call site against real attribute types, and there is no
    forward-reference string left dangling for a name that this module cannot see.
    """

    @property
    def from_theater(self) -> str: ...

    @property
    def to_theater(self) -> str: ...


def outgoing_and_incoming(
    theater_id: str, routes: Sequence[DirectedEdge]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Sorted (outgoing, incoming) neighbour ids for one theater.

    Pure, and the SINGLE derivation of directed adjacency. The API projection calls it; the
    frontend never recomputes adjacency from route rows or from line geometry.
    """
    outgoing = sorted({r.to_theater for r in routes if r.from_theater == theater_id})
    incoming = sorted({r.from_theater for r in routes if r.to_theater == theater_id})
    return tuple(outgoing), tuple(incoming)
