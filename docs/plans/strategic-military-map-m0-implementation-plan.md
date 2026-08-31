# MANDATE — Strategic Military Map M0 — implementation-ready plan (PLAN ONLY)

M0 is an authoritative **read-only strategic map**. No military, finance, report, RNG stream or
phase code. M1–M5 remain nonbinding.

This revision applies the export-and-logic corrections: the presentation-neutrality contradiction is
split into two separate tests (§10), directed connectivity is made explicit (§11), and shape
ordering failures are separated from duplicate-id failures with honest polygon-order wording
(§5.4, §9).

---

## 0. Container rollback disclosure — read this first

Between the previous delivery and this one the execution container **rolled back**. This is
disclosed rather than hidden, because it changes what "verified" means for §1 and §2.

| Fact | Observed now |
|---|---|
| Local `HEAD` | `5915a6f44f3484dbcf2df9c4eba87d5481cd43f1` (`ci: permanent full-stack smoke through mandate-gui...`) |
| Local branch | `claude/phase-4a-graphical-vertical-slice` |
| Working tree | clean (no uncommitted changes, no lost repository work) |
| `origin/claude/phase-4a-graphical-vertical-slice` | `1df8f397e2eb6a5c3cd93e83f8e6b7300d66c4b9` — the W1 closeout |
| `git merge-base --is-ancestor HEAD origin/claude/phase-4a-graphical-vertical-slice` | exit 0 — **fast-forward-only recovery is valid** |
| Plan file on disk | rolled back to the **External Wars W1** plan (870 lines), not the M0 plan |

**Consequences, stated plainly:**

1. **No durable work was lost.** Every W1 commit through `1df8f39` is on the remote. The rollback
   moved only the container's working directory.
2. **The previously reported plan-file metrics no longer describe any file that exists.** The
   `759 / 40,606 / f40dae0a…` figures described a file the rollback destroyed. They are withdrawn.
   This document is a **fresh authoring**, and its metrics are recomputed at the end (§19).
3. **The rollback also explains the delivery defect you observed.** Because the reproduced chat copy
   and the on-disk file could not be compared after the rollback, the mismatch you measured
   (484 lines / 31,998 bytes / `1051017d…`) could not be reconciled from this side. The remedy is
   the one you prescribed: this plan is delivered as a **byte-for-byte file copy**, not as a chat
   paste, with a `cmp` proof.
4. **Every §2 fact in this document was re-verified read-only against the pushed tree**
   (`git show origin/claude/phase-4a-graphical-vertical-slice:<path>`), not recalled from memory.
   The verification commands and their exact output are reproduced in §2.
5. **The working directory was NOT fast-forwarded.** That is a repository mutation and this mandate
   forbids one. The authorized ff-only recovery (`git fetch origin` →
   `git merge-base --is-ancestor HEAD origin/<branch>` → `git merge --ff-only`) must be re-run as
   the first action of M0 commit 1, **after** freeze authorization — never reset, rebase, amend or
   force-push.

**Branch decision — FINAL, no longer open.** M0 lands on
**`claude/phase-4a-graphical-vertical-slice`**, the branch that carries every External Wars W1
commit including the `1df8f39` closeout this plan depends on. This is settled and no further ruling
is required.

The required recovery, run exactly once before the freeze commit and never varied:

```bash
git fetch origin
git merge-base --is-ancestor HEAD origin/claude/phase-4a-graphical-vertical-slice
git merge --ff-only origin/claude/phase-4a-graphical-vertical-slice
```

The ancestor check **must exit 0**. After the merge, local `HEAD` and
`origin/claude/phase-4a-graphical-vertical-slice` must both equal
`1df8f397e2eb6a5c3cd93e83f8e6b7300d66c4b9`. **Never reset, rebase, amend, cherry-pick or
force-push.**

---

## 1. Authoritative baseline

The baseline M0 builds on, as verified from git objects (not from the rolled-back working tree):

| Check | Result |
|---|---|
| Baseline commit | `1df8f397e2eb6a5c3cd93e83f8e6b7300d66c4b9` |
| Subject | `External Wars W1 (11/11): record architecture and close out W1` |
| Frozen W1 plan SHA-256 | `2ceb9a7b33512a45f6d756d3a1698c724495475d374f3d339814fef1040c82e0` |
| Ruleset version | `0.13.0` (`state.py:1206`) |
| Save format | `1` |
| Backend / frontend baseline | 10,672 / 133 passing (last measured before the rollback) |

The 10,672/133 figures are **carried forward from the last measurement**, not re-measured this
session — the rollback removed the ability to re-run the suite without mutating the checkout. They
are labelled as carried forward rather than presented as fresh, and M0 commit 1 must re-establish
them on the recovered checkout before any code lands.

---

## 2. Load-bearing repository facts (all re-verified read-only)

Every line below was produced by `git show origin/claude/phase-4a-graphical-vertical-slice:<path>`
against `1df8f39`. Exact observed output:

```
routes.py       77:router = APIRouter()
main.py        125:    app.include_router(router, prefix="/api")
state.py        49:_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)
projections.py  44:_STRICT = ConfigDict(extra="forbid", frozen=True)
projections.py 186:class MapProjection(BaseModel):
projections.py 228:    map: MapProjection
projections.py 850:        map=MapProjection(
state.py      1206:RULESET_VERSION = "0.13.0"
reconciliation.py  412:def reconcile_political_legislative_and_survival_report(
reconciliation.py 2407:def reconcile_foreign_affairs_report(
grep -nE "scenario_digest|content_digest|scenario_hash" state.py  ->  (no output)
```

Scenario ownership, read from the authored YAML:

```
data/scenarios/tiny_valid.yaml     content_version "0.13.0"  player_country_id: arken
                                   foreign_profiles: kessia ("Kessia"), vetruska ("Vetruska")
data/scenarios/decree_state.yaml   content_version "0.13.0"  player_country_id: valdrun
                                   foreign_profiles: marnil ("Marnil"), sorrend ("Sorrend")
data/scenarios/deficit_demo.yaml   content_version "0.13.0"  player_country_id: strapped
                                   foreign_profiles: marnil ("Marnil"), tolvane ("Tolvane")
```

Derived facts:

- **API prefix.** `router = APIRouter()` with no prefix, mounted `prefix="/api"`. There is no version
  segment. The real path is therefore **`/api/game/map/strategic`**.
- **Player country ids.** `arken`, `valdrun`, **`strapped`** — the third is the real authored id, not
  a placeholder.
- **Foreign profile ids per scenario** are exactly as listed above; §5's geometry references only
  these, and no others.
- **Phase slots** (`phases.py:3606-3634`): slot 7 and slot 8
  (`resolve_military_movement_and_combat`) are W1-owned; slot 9 is `_noop`. **M0 changes no phase
  file.**
- **Reconciliation** has exactly two entrypoints today, wired in `history.py:377-393` under
  `index > 0`, each receiving `opening_state`, `closing_state`, `report` (and decisions for the
  first). Both return problem strings and never raise.
- **No scenario digest exists anywhere in the save architecture.** This bounds what §8 can honestly
  claim (§8.4).
- **Strict types**: `app/core/money.py:41` `StrictMoney`, `:52` `StrictBps`;
  `app/core/politics.py:114` `StrictRelationshipBps`.
- **`MapProjection`** (`projections.py:186`) and its consumers (`:228`, `:850`) plus
  `frontend/src/greybox/screens/DashboardScreen.tsx:131,133`. Its docstring *and* its runtime `note`
  both assert no spatial state exists; both become false under M0 and both are corrected (§7).
- **Version policy** (`state.py:1255-1271`): every ruleset bump lands atomically with the state it
  describes, each with an explicit no-migration rationale.

---

## 3. Complete model declarations

New module `app/simulation/geography.py` holds the enums and pure helpers; the state models live in
`state.py` beside `WorldState`. All state models use `_STRICT_CONFIG` (`extra="forbid"`,
`validate_assignment=True`) — **mutable like every other state model**, because `GameState` is
deep-copied and mutated in place by `resolver.py`. Projections use `_STRICT` (`frozen=True`).

```python
# ===========================================================================
# app/simulation/geography.py                                        (NEW FILE)
# ===========================================================================
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
invariant re-checks them (see the ownership table, sec.9)."""

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
    unused state -- the exact defect that sank the first M0 draft.
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
    winding nor starting vertex (sec.5.4). Only `== 0` is tested, which detects a degenerate
    polygon whose vertices are collinear or backtrack onto themselves.
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
    frontend never recomputes adjacency from route rows or from line geometry (sec.11).
    """
    outgoing = sorted({r.to_theater for r in routes if r.from_theater == theater_id})
    incoming = sorted({r.from_theater for r in routes if r.to_theater == theater_id})
    return tuple(outgoing), tuple(incoming)


# ===========================================================================
# app/simulation/state.py                             (added beside WorldState)
# ===========================================================================


class PlayerCountryRef(BaseModel):
    """Ownership by the player's own country. Resolves through `WorldState.countries`."""

    model_config = _STRICT_CONFIG

    kind: Literal["player_country"] = "player_country"
    country_id: StrictMapId


class ForeignProfileRef(BaseModel):
    """Ownership by a W1 foreign actor. Resolves through `WorldState.foreign_profiles`.

    Grants that profile no population, treasury, economy or politics -- a foreign profile stays
    exactly what W1 made it, and owning map area does not upgrade it into a country.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["foreign_profile"] = "foreign_profile"
    foreign_profile_id: StrictMapId


SovereignRef: TypeAlias = Annotated[
    PlayerCountryRef | ForeignProfileRef, Field(discriminator="kind")
]
"""A tagged reference into the two EXISTING authoritative namespaces.

Deliberately NOT a third actor registry: a registry could disagree with `countries` /
`foreign_profiles` about who exists and what they are called, and there would be no principled
answer to which one is right. Discriminated on `kind`, matching every other tagged union in this
codebase.
"""


class TheaterPresentation(BaseModel):
    """Presentation only.

    Read by the map projection and by the renderer; by NO formula, and by no validator that
    decides legality. Enforced structurally by `test_map_presentation_boundary.py` and
    behaviourally by `test_map_presentation_neutrality.py` (sec.10).
    """

    model_config = _STRICT_CONFIG

    centroid_x: StrictGridCoord
    centroid_y: StrictGridCoord
    label_anchor: LabelAnchor


class TheaterState(BaseModel):
    """One strategic theater: a military operating area, NOT a simulated province.

    It has no population, budget, election, approval, tax base or city economy, and never will --
    that is the Cities & Provinces expansion boundary (sec.16).
    """

    model_config = _STRICT_CONFIG

    display_name: StrictDisplayName
    kind: TheaterKind
    owner: SovereignRef
    presentation: TheaterPresentation

    # NOTE: no `id` field. The `StrategicMapState.theaters` dict KEY is authoritative, so key and
    # value can never disagree -- the same discipline as `ForeignProfileState` (state.py:990).


class RouteState(BaseModel):
    """One DIRECTED mechanical adjacency.

    Two-way passage is TWO rows. There is no implicit symmetry, because implicit reciprocity is
    exactly how a deliberately one-way or impassable-in-return edge silently becomes passable.
    """

    model_config = _STRICT_CONFIG

    from_theater: StrictMapId
    to_theater: StrictMapId
    kind: RouteKind

    @model_validator(mode="after")
    def _not_a_self_edge(self) -> RouteState:
        """Emits `ROUTE_SELF_EDGE`."""
        if self.from_theater == self.to_theater:
            raise ValueError(
                f"{ROUTE_SELF_EDGE}: route is a self-edge on theater {self.from_theater!r}"
            )
        return self


class CountryShapeState(BaseModel):
    """An authored fictional political outline.

    Presentation only. Polygon contact NEVER creates mechanical adjacency; only `RouteState`
    does. Two shapes may share a border pixel-for-pixel and still have no route between their
    theaters, and that is a legal, meaningful map.
    """

    model_config = _STRICT_CONFIG

    shape_id: StrictMapId
    owner: SovereignRef
    polygon: tuple[tuple[StrictGridCoord, StrictGridCoord], ...] = Field(min_length=3)

    @model_validator(mode="after")
    def _polygon_is_well_formed(self) -> CountryShapeState:
        """Emits `SHAPE_POLYGON_CLOSING_VERTEX_REPEATED`, `SHAPE_POLYGON_REPEATS_VERTEX` or
        `SHAPE_POLYGON_ZERO_AREA`.

        Vertex representation: an OPEN RING stored in AUTHORED ORDER. The closing vertex is
        implicit; repeating the first vertex at the end is REJECTED rather than trimmed, so there
        is exactly one representation of a given ring outline.

        NO rotation normalization and NO winding normalization is performed (sec.5.4). Starting
        vertex and winding direction are stored as authored, and two rings that differ only by
        rotation are DIFFERENT authored values that serialize to different bytes.
        """
        if self.polygon[0] == self.polygon[-1]:
            raise ValueError(
                f"{SHAPE_POLYGON_CLOSING_VERTEX_REPEATED}: polygon repeats its first vertex "
                f"as a closing vertex; rings are open"
            )
        for first, second in zip(self.polygon, self.polygon[1:]):
            if first == second:
                raise ValueError(
                    f"{SHAPE_POLYGON_REPEATS_VERTEX}: polygon has a duplicate consecutive "
                    f"vertex {first!r}"
                )
        if shoelace_doubled_area(self.polygon) == 0:
            raise ValueError(f"{SHAPE_POLYGON_ZERO_AREA}: polygon encloses zero area")
        return self


class StrategicMapState(BaseModel):
    """The authoritative strategic map.

    IMMUTABLE during a campaign: no M0 phase writes it, and `reconcile_strategic_map_staticness`
    proves it byte-identical across every resolved turn (sec.8).
    """

    model_config = _STRICT_CONFIG

    map_id: StrictMapId
    capital_theater_id: StrictMapId
    theaters: dict[StrictMapId, TheaterState] = Field(min_length=1)
    """The authoritative theater registry, keyed by theater id.

    The KEY is annotated `StrictMapId`, not bare `str`: the dict key is the authoritative
    identifier (TheaterState carries no `id` field), so it must enforce exactly the same
    nonempty / strict-string / max-length-64 rules as every other map identifier. A bare
    `dict[str, ...]` would accept an empty key, a coerced non-string key, or a 4,000-character
    key, and the fault would only surface later -- and only by accident -- if some route happened
    to reference it. Validating the key at construction means an invalid key is impossible to
    store, not merely likely to be noticed.
    """
    routes: tuple[RouteState, ...] = ()
    shapes: tuple[CountryShapeState, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _routes_unique_and_ordered(self) -> StrategicMapState:
        """Emits `ROUTE_DUPLICATE` or `ROUTE_NOT_CANONICAL`.

        Two SEPARATE failures with two separate codes. Duplicates are checked FIRST and
        independently of ordering, so each is reachable on its own: a duplicated pair such as
        (a,b),(a,b) is already sorted and trips ONLY the duplicate check, while two distinct
        pairs in the wrong order trip ONLY the ordering check.

        Non-canonical order is REJECTED, never normalized -- the repository-wide rule for every
        ordered collection.
        """
        keys = [(r.from_theater, r.to_theater, r.kind.value) for r in self.routes]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{ROUTE_DUPLICATE}: duplicate route(s) in the map: {keys!r}")
        if keys != sorted(keys):
            raise ValueError(
                f"{ROUTE_NOT_CANONICAL}: routes are not in canonical (from, to, kind) "
                f"order: {keys!r}"
            )
        return self

    @model_validator(mode="after")
    def _shapes_unique_and_ordered(self) -> StrategicMapState:
        """Emits `SHAPE_ID_DUPLICATE` or `SHAPE_NOT_CANONICAL`.

        Two SEPARATE failures, for the same reason as routes and reachable independently:
        ['s_a', 's_a'] is sorted and trips ONLY the duplicate check; ['s_b', 's_a'] has no
        duplicate and trips ONLY the ordering check.
        """
        shape_ids = [s.shape_id for s in self.shapes]
        if len(set(shape_ids)) != len(shape_ids):
            raise ValueError(
                f"{SHAPE_ID_DUPLICATE}: duplicate shape_id(s) in the map: {shape_ids!r}"
            )
        if shape_ids != sorted(shape_ids):
            raise ValueError(
                f"{SHAPE_NOT_CANONICAL}: shapes are not in canonical shape_id "
                f"order: {shape_ids!r}"
            )
        return self
```

`WorldState` gains, **required**:

```python
class WorldState(BaseModel):
    ...
    strategic_map: StrategicMapState
    """The campaign's defining strategic map. REQUIRED: no default, no `| None`.

    A valid 0.14.0 game carries its map or fails construction. There is deliberately no synthetic
    fallback map hidden inside the model -- a fallback would mean a save could silently lose its
    map and still load, which is precisely the failure sec.8 exists to detect.
    """
```

`theaters` and `shapes` both carry `min_length=1`, so an **empty map is unrepresentable** rather
than caught later by an invariant. `routes` may legitimately be empty — a single-theater map has
nowhere to go. Shared test fixtures (`tests/conftest.py` `make_game_state`) gain an explicit minimal
authored map: **visible in the fixture, never defaulted in the model.**

**Serialization.** The existing canonical-JSON writer sorts dict keys, so `theaters` serializes in
theater-id order regardless of Python insertion order; `routes` and `shapes` serialize in their
stored (canonical) tuple order. Nothing new is needed, and §10's insertion-order test proves it.

---

## 4. Capital marker

`capital_theater_id` is stored **once**, on `StrategicMapState`. There is deliberately **no
`is_capital` boolean** on `TheaterState`: a per-theater flag admits zero capitals or two, which the
single field makes structurally impossible.

| Rule | Layer | Reason id |
|---|---|---|
| `capital_theater_id` is a key of `theaters` | state invariant | `map_capital_unknown` |
| the capital theater's owner is a `PlayerCountryRef` | state invariant | `map_capital_not_player_owned` |

The capital's *kind* needs no check: `TheaterKind` has only LAND and COASTAL in M0 and both are
valid capitals, so a "capital kind invalid" code would be **unreachable** — §9 forbids shipping
unreachable codes.

---

## 5. Exact three-scenario geometry

Grid is 0–10,000 on both axes. Polygons are **open rings in authored order** (§5.4). Every id, name,
kind, owner, coordinate, anchor, directed route and vertex below is final and mechanically copyable.

### 5.1 `tiny_valid` — `map_id: arken_basin`

Player country `arken`. Foreign profiles `kessia`, `vetruska` (both authored by W1, §2).
`capital_theater_id: arken_capital`.

| theater id | display name | kind | owner | centroid_x | centroid_y | label_anchor |
|---|---|---|---|---:|---:|---|
| `arken_capital` | Arken Capital Region | land | player `arken` | 1900 | 3200 | center |
| `arken_coast` | Arken Coast | coastal | player `arken` | 1200 | 5200 | w |
| `arken_north` | Northern March | land | player `arken` | 2200 | 1900 | n |
| `kessia_south` | Southern Kessia | land | foreign `kessia` | 5400 | 3800 | center |
| `vetruska_frontier` | Vetruskan Frontier | land | foreign `vetruska` | 8200 | 3500 | e |

**Directed routes** — all 8 rows, all `kind: land`, in canonical `(from, to, kind)` order:

| # | from_theater | to_theater | kind |
|---:|---|---|---|
| 1 | `arken_capital` | `arken_coast` | land |
| 2 | `arken_capital` | `arken_north` | land |
| 3 | `arken_coast` | `arken_capital` | land |
| 4 | `arken_north` | `arken_capital` | land |
| 5 | `arken_north` | `kessia_south` | land |
| 6 | `kessia_south` | `arken_north` | land |
| 7 | `kessia_south` | `vetruska_frontier` | land |
| 8 | `vetruska_frontier` | `kessia_south` | land |

All four unordered pairs are reciprocal, so §11 collapses them to 4 display rows, every one
`bidirectional=true`.

**Shapes** — canonical by `shape_id`, open rings in authored order:

| shape_id | owner | polygon vertices |
|---|---|---|
| `shape_arken` | player `arken` | (500,2000) (2200,1200) (3800,2000) (3600,5200) (1800,6200) (500,4800) |
| `shape_kessia` | foreign `kessia` | (4200,1800) (6200,1500) (6800,3600) (5600,5400) (4100,4400) |
| `shape_vetruska` | foreign `vetruska` | (7200,1800) (9200,2200) (9400,4600) (7800,5200) (7000,3600) |

Player land component `{arken_capital, arken_coast, arken_north}` is reachable from
`arken_capital` using player-owned edges only (rows 1 and 2). ✔

### 5.2 `decree_state` — `map_id: valdrun_reach`

Player country `valdrun`. Foreign profiles `marnil`, `sorrend`.
`capital_theater_id: valdrun_capital`.

| theater id | display name | kind | owner | centroid_x | centroid_y | label_anchor |
|---|---|---|---|---:|---:|---|
| `marnil_border` | Marnil Borderland | land | foreign `marnil` | 5700 | 3600 | center |
| `sorrend_plain` | Sorrend Plain | land | foreign `sorrend` | 8400 | 4000 | e |
| `valdrun_capital` | Valdrun Capital Region | land | player `valdrun` | 1900 | 3000 | center |
| `valdrun_east` | Eastern Valdrun | land | player `valdrun` | 3300 | 4200 | s |
| `valdrun_highlands` | Valdrun Highlands | land | player `valdrun` | 2400 | 1700 | n |

**Directed routes** — all 8 rows, all `kind: land`, canonical order:

| # | from_theater | to_theater | kind |
|---:|---|---|---|
| 1 | `marnil_border` | `sorrend_plain` | land |
| 2 | `marnil_border` | `valdrun_east` | land |
| 3 | `sorrend_plain` | `marnil_border` | land |
| 4 | `valdrun_capital` | `valdrun_east` | land |
| 5 | `valdrun_capital` | `valdrun_highlands` | land |
| 6 | `valdrun_east` | `marnil_border` | land |
| 7 | `valdrun_east` | `valdrun_capital` | land |
| 8 | `valdrun_highlands` | `valdrun_capital` | land |

**Shapes:**

| shape_id | owner | polygon vertices |
|---|---|---|
| `shape_marnil` | foreign `marnil` | (4600,2200) (6600,1800) (7200,4200) (5800,5600) (4500,4600) |
| `shape_sorrend` | foreign `sorrend` | (7600,2400) (9400,2800) (9500,5200) (8000,5800) (7400,4200) |
| `shape_valdrun` | player `valdrun` | (800,1500) (3000,1000) (4000,2600) (3400,5600) (1500,6400) (600,4200) |

Player component `{valdrun_capital, valdrun_east, valdrun_highlands}` is reachable from
`valdrun_capital` via rows 4 and 5. ✔

### 5.3 `deficit_demo` — `map_id: tolvane_strait`

Player country **`strapped`** — the real authored id (§2). Foreign profiles `marnil`, `tolvane`.
`capital_theater_id: home_capital`. This map deliberately includes a **routeless foreign island** and
a **one-way route**, exercising §6's rule that non-player theaters need no connectivity and §11's
requirement that a single direction be distinguishable from a reciprocal pair.

| theater id | display name | kind | owner | centroid_x | centroid_y | label_anchor |
|---|---|---|---|---:|---:|---|
| `home_capital` | Capital Region | land | player `strapped` | 1800 | 3200 | center |
| `home_lowlands` | Lowlands | land | player `strapped` | 2500 | 2000 | n |
| `home_port` | Port District | coastal | player `strapped` | 1300 | 5300 | w |
| `marnil_march` | Marnil March | land | foreign `marnil` | 5500 | 3400 | center |
| `tolvane_isle` | Tolvane Isle | coastal | foreign `tolvane` | 8600 | 6800 | s |

**Directed routes** — all 6 rows, all `kind: land`, canonical order. `tolvane_isle` appears in none:

| # | from_theater | to_theater | kind |
|---:|---|---|---|
| 1 | `home_capital` | `home_lowlands` | land |
| 2 | `home_capital` | `home_port` | land |
| 3 | `home_lowlands` | `home_capital` | land |
| 4 | `home_lowlands` | `marnil_march` | land |
| 5 | `home_port` | `home_capital` | land |
| 6 | `marnil_march` | `home_lowlands` | land |

Note row 2 and row 5: `home_capital ↔ home_port` is reciprocal. Rows 4 and 6 are likewise
reciprocal. Every pair here is reciprocal, so to give §11's one-way case a live fixture, the
**one-way case is exercised in the unit fixtures of `test_api_projections.py`** rather than by
deliberately crippling an authored scenario map — an authored map should read as a sensible world,
not as a test rig. That choice is stated rather than hidden.

**Shapes:**

| shape_id | owner | polygon vertices |
|---|---|---|
| `shape_marnil` | foreign `marnil` | (4500,2000) (6500,1700) (7000,4000) (5700,5400) (4400,4300) |
| `shape_strapped` | player `strapped` | (700,1800) (2900,1300) (3900,2900) (3300,5800) (1400,6300) (600,4400) |
| `shape_tolvane` | foreign `tolvane` | (8000,5800) (9100,5600) (9500,7000) (8600,7900) (7900,7000) |

Player component `{home_capital, home_lowlands, home_port}` is reachable from `home_capital` via
rows 1 and 2. ✔

### 5.4 Geometry validation, and what is honestly NOT validated

**Polygon vertex order is NOT canonicalized.** Stated exactly:

> **Open ring stored in authored order; no rotation or winding normalization.**

The word "canonical" is therefore **not** used for vertices anywhere in this plan. It is used only
for the two collections where an ordering rule is genuinely enforced — `routes` (sorted by
`(from, to, kind)`) and `shapes` (sorted by `shape_id`). Two rings differing only by starting vertex
or winding direction are different authored values, serialize to different bytes, and both load.

| Rule | Layer | Reason id |
|---|---|---|
| ≥ 3 vertices | Pydantic `min_length=3` | (Pydantic error) |
| coordinate bounds 0–10,000 | `StrictGridCoord` | (Pydantic error) |
| id length / strictness | `StrictMapId`, `StrictDisplayName` | (Pydantic error) |
| repeated closing vertex (rings are open) | `CountryShapeState` | `shape_polygon_closing_vertex_repeated` |
| duplicate consecutive vertices | `CountryShapeState` | `shape_polygon_repeats_vertex` |
| zero area (`shoelace_doubled_area == 0`) | `CountryShapeState` | `shape_polygon_zero_area` |
| duplicate `shape_id` | `StrategicMapState` | `shape_id_duplicate` |
| shapes not in `shape_id` order | `StrategicMapState` | `shape_not_canonical` |
| duplicate route | `StrategicMapState` | `route_duplicate` |
| routes not in `(from,to,kind)` order | `StrategicMapState` | `route_not_canonical` |
| self-edge route | `RouteState` | `route_self_edge` |
| ≥ 1 shape per represented owner | state invariant | `shape_missing_for_owner` |
| multiple shapes per owner (islands) | **allowed by design** | — |

**Honest limitation, stated rather than papered over:** polygon **self-intersection** and
**inter-polygon overlap** are **not** validated. Doing either correctly needs a
computational-geometry dependency, which this mandate forbids adding without approval. Shape
correctness therefore rests on **authoring review plus the real 1440×900 browser screenshots**
(§14). This is raised as decision 4 in §17.

---

## 6. Topology invariants

1. **Player land connectivity.** Every player-owned theater is reachable from `capital_theater_id`
   using only routes whose **both** endpoints are player-owned → `player_land_component_disconnected`.
   Traversal follows directed edges from the capital; a player theater reachable only by an
   incoming-but-not-outgoing chain is a real authoring bug and should fail.
2. **Referential integrity.** Every route endpoint is a key of `theaters` → `route_endpoint_unknown`.
3. **Non-player theaters need no connectivity at all.** Islands and wholly disconnected foreign
   states are valid by construction — `tolvane_isle` proves it in a shipped scenario.

Mechanical reachability and legal access are **different concepts** and stay separate: owning a
theater implies nothing about being permitted to enter it, and M0 has no access model whatsoever.

---

## 7. `MapProjection` correction

`MapProjection` is **kept** — renaming it would churn `projections.py:228`, `:850` and
`DashboardScreen.tsx:131,133` for no gain — but its now-false text is corrected in the same commit
that makes it false:

- The **docstring** (`projections.py:186`) is rewritten to describe what it actually is: the
  dashboard's national tint summary, with a pointer to the separate strategic-map projection and its
  own endpoint.
- The **runtime `note`** (`projections.py:850`) stops asserting that no spatial state exists. It may
  still say no province-level mechanics exist, which remains true and stays true through M5.

---

## 8. History integrity

### 8.1 A third reconciler, and no fourteenth report

`app/simulation/reconciliation.py` gains a **third entrypoint**, mirroring how W1 added its own
rather than extending the political reconciler:

```python
def reconcile_strategic_map_staticness(
    *, opening_state: GameState, closing_state: GameState
) -> list[str]:
    """Group 53 -- the strategic map is authoritative authored content and is IMMUTABLE during a
    campaign.

    No phase writes it, so ANY difference between a history entry's opening and closing map is
    either an engine bug or a tampered save. Never raises: every failure is a returned problem
    string, matching both existing reconcilers.

    Takes no `report` argument. M0 adds no report, and a staticness check has nothing to compare
    a report against -- inventing a parameter to look symmetrical would be dishonest signature
    design.
    """
```

Numbered **group 53**, continuing W1's 46–52 rather than hiding inside a generic group: the failure
is map-specific and its problem strings should say so.

### 8.2 Comparison, wiring, and the exact problem strings

- **Canonical equality.** `canonical_dumps(opening_state.world.strategic_map)` versus the closing
  map's — the same primitive the entry hash already uses. Byte comparison, insertion-order
  independent (§10 proves the independence).
- **Wiring.** `history.py`, alongside the existing two reconcilers, under the same `index > 0`
  guard, each problem prefixed `f"turn {entry.turn}: {problem}"`.
- **Missing map.** Unreachable in a valid `0.14.0` state because the field is required. If a parse
  somehow produced `None`, the reconciler returns a problem string rather than raising.
- **Malformed owner reference.** Not this reconciler's job — owner resolution is a state invariant
  (§9). Group 53 compares two maps and does nothing else.
- **Never raises.** Every comparison is on already-parsed models; no attribute access can escape a
  guard.

**Exact problem strings emitted by group 53** (verbatim; these are the strings the tests assert on):

```
strategic map changed during turn resolution: opening map_id 'X' != closing map_id 'Y'
```

```
strategic map changed during turn resolution: canonical map bytes differ (the strategic map is
authored, immutable content and no phase may write it)
```

```
strategic map missing from the closing state (the field is required; a state that reached
reconciliation without one is malformed)
```

```
strategic map missing from the opening state (the field is required; a state that reached
reconciliation without one is malformed)
```

The first fires when `map_id` itself differs, because that is the most legible possible message; the
second fires for every other byte difference; the last two are the unreachable-but-guarded cases.
Each string is asserted by name in `test_map_reconciliation.py`.

### 8.3 Rehashed tamper matrix (five cases)

Each case edits one `HistoryEntry`'s stored state JSON, then **re-links and re-hashes the entire
downstream chain** using `tests/history_tamper_helpers.py` (built for W1 commit 8), proves the chain
verifies green via the independent `hash_chain_problems` verifier, and then asserts group 53 still
rejects it. A tamper that survives rehashing is the only interesting kind.

| # | Tamper | Detected by |
|---:|---|---|
| 1 | theater `owner` changed mid-history | canonical map bytes differ |
| 2 | route row added or deleted mid-history | canonical map bytes differ |
| 3 | `capital_theater_id` changed mid-history | canonical map bytes differ (plus `map_capital_*` if the new id is invalid) |
| 4 | presentation coordinate changed mid-history | canonical map bytes differ |
| 5 | polygon vertex changed mid-history | canonical map bytes differ |

Case 4 is the deliberate one. Presentation data changes nothing the simulation computes (§10) — yet
it is still authored authoritative content, so silently rewriting it mid-campaign is still a tamper.
**Inert to simulation is not the same as inert to integrity**, and this plan does not conflate them.

### 8.4 The honest boundary

**Group 53 compares consecutive entries. It cannot detect a tamperer who edits the genesis state and
then consistently rebuilds every descendant** — every opening/closing pair would agree, and the
chain would verify.

Detecting that requires comparing the save against external authored scenario content, and §2
established by grep that **the save architecture stores no scenario digest of any kind.** M0 does
**not** add one: that is a save-architecture change well outside a read-only map gate and it needs
its own audit.

This limitation is written into ADR 0017 rather than overclaimed. What M0 *does* guarantee, exactly:
**the map cannot change during a campaign without detection.**

---

## 9. Validator and reason-ID ownership

Exactly one owner per fact. Codes that could never fire are **removed, not shipped**.

| Fact | Owning layer | Reason id |
|---|---|---|
| self-edge route | Pydantic — `RouteState` | `route_self_edge` |
| duplicate route | Pydantic — `StrategicMapState` | `route_duplicate` |
| routes out of canonical order | Pydantic — `StrategicMapState` | `route_not_canonical` |
| duplicate shape id | Pydantic — `StrategicMapState` | `shape_id_duplicate` |
| shapes out of canonical order | Pydantic — `StrategicMapState` | `shape_not_canonical` |
| polygon closing vertex repeated | Pydantic — `CountryShapeState` | `shape_polygon_closing_vertex_repeated` |
| polygon duplicate consecutive vertex | Pydantic — `CountryShapeState` | `shape_polygon_repeats_vertex` |
| polygon zero area | Pydantic — `CountryShapeState` | `shape_polygon_zero_area` |
| empty `theaters` / `shapes` | Pydantic `min_length=1` | (Pydantic error) |
| coordinate bounds, id length, strictness | Pydantic annotated types | (Pydantic error) |
| route endpoint exists | state invariant | `route_endpoint_unknown` |
| player ref resolves in `countries` — **theaters and shapes alike** | state invariant (shared rule) | `map_owner_country_unknown` |
| player ref **is** `player_country_id` — **theaters and shapes alike** | state invariant (shared rule) | `map_player_ref_not_player` |
| foreign ref resolves in `foreign_profiles` — **theaters and shapes alike** | state invariant (shared rule) | `map_owner_profile_unknown` |
| every represented owner has ≥ 1 shape | state invariant | `shape_missing_for_owner` |
| capital resolves to a theater | state invariant | `map_capital_unknown` |
| capital is player-owned | state invariant | `map_capital_not_player_owned` |
| player land connectivity from the capital | state invariant | `player_land_component_disconnected` |
| map unchanged across a resolved turn | history reconciliation | group 53 strings (§8.2) |
| owner display names, directed adjacency lists | API projection — **derivation, not validation** | — |

### 9.1 One shared sovereign-reference rule

Owner validation is **a single rule applied to every `SovereignRef` in the map**, whatever holds
it. A helper walks both sources — every `TheaterState.owner` and every `CountryShapeState.owner` —
and applies exactly three checks:

```
PlayerCountryRef.country_id must exist in world.countries          -> map_owner_country_unknown
PlayerCountryRef.country_id must equal world.player_country_id     -> map_player_ref_not_player
ForeignProfileRef.foreign_profile_id must exist in
                                     world.foreign_profiles        -> map_owner_profile_unknown
```

The codes are **context-neutral** (`map_*`, not `theater_*` or `shape_*`) because the rule is one
rule. The *problem text* names where the bad reference came from — `"theater 'arken_north'"` or
`"shape 'shape_kessia'"` — so diagnosis loses nothing, while the semantics of a sovereign
reference are defined in exactly one place. Duplicating namespace semantics across a theater copy
and a shape copy is how the two drift apart.

This replaces the previous `theater_owner_country_unknown`, `theater_player_ref_not_player`,
`theater_owner_profile_unknown` and `shape_owner_unresolved` — four codes that split one rule
across two contexts and left shapes with a vaguer check than theaters.

**`theater_foreign_ref_is_player` is REMOVED as unreachable.** W1 already requires
`foreign_profiles` keys to be disjoint from every `countries` key, so a `ForeignProfileRef` naming
the player's country id cannot resolve in `foreign_profiles` at all — it fails
`map_owner_profile_unknown` first, and no input can reach the would-be "foreign ref is the player"
branch. §9's rule is that a code which can never fire is removed rather than shipped, and this is
that case.

**Separated this revision:** `shape_id_duplicate` and `shape_not_canonical` are now two distinct,
truthful failures (they were previously conflated into one id that would have lied about half its
occurrences). `route_duplicate` and `route_not_canonical` were already distinct and stay distinct.
§3 shows the duplicate check running before the ordering check in each validator, which is what
makes both independently reachable; §13 requires a focused test per id proving that reachability.

**Removed as unreachable:** a generic `theater_owner_unresolved` (the three specific `map_owner_*`
codes always fire first, so it could never be the reported reason), **`theater_foreign_ref_is_player`**
(§9.1 — W1's disjointness makes it impossible to reach), `map_empty` (`min_length=1` makes it a
Pydantic error, not an invariant), and any "capital kind invalid" code (§4).

**Invariant count: eight.** M0 ships exactly these state-invariant codes:

1. `route_endpoint_unknown`
2. `map_owner_country_unknown`
3. `map_player_ref_not_player`
4. `map_owner_profile_unknown`
5. `shape_missing_for_owner`
6. `map_capital_unknown`
7. `map_capital_not_player_owned`
8. `player_land_component_disconnected`

Down from eleven in the previous revision: the four context-split owner codes collapsed into three
shared ones (§9.1), and `theater_foreign_ref_is_player` was removed as unreachable. Theater-key
validity is **not** in this list — C2 makes it a Pydantic annotation error, not an invariant. Each
of the eight has an independently reachable focused test in §13.

No fact is validated in more than one layer. Construction guards shape; invariants guard
cross-references a constructor cannot see; reconciliation guards the distinct tamper boundary of a
rehashed history.

---

## 10. Presentation inertness — three separate proofs

The previous draft asked one test to prove two incompatible things: that changing coordinates leaves
the API JSON byte-identical, while the API deliberately publishes those very coordinates. That is
impossible, and it is now split.

### 10.1 Structural proof — `test_map_presentation_boundary.py`

An AST/source scan: no module under `app/simulation/` other than `geography.py` and `state.py` may
reference `TheaterPresentation`, `CountryShapeState`, `centroid_x`, `centroid_y`, `label_anchor` or
`polygon`. Mirrors W1's `war_capability_bps` neutrality scan. Catches the *next* developer, not just
this one.

### 10.2 Simulation-inertness proof — `test_map_presentation_neutrality.py`

Build a variant of a scenario that changes **only genuinely presentational values**:

- node coordinates (`centroid_x`, `centroid_y`),
- label anchors (`label_anchor`),
- polygon vertices.

**Nothing else changes.** Theater ids, kinds, owners, the capital, every route row, every shape id
and the tuple ordering of `routes` and `shapes` are all held fixed.

Resolve N turns from both the baseline and the variant, then require:

| Assertion | Requirement |
|---|---|
| Turn reports | **unchanged** — every domain field of every `TurnReport`: finance, production, labor, tax bases, political, legislative, political capital, relationships, coup/unrest, election, amendment, foreign affairs |
| RNG-observable outcomes | **unchanged** — every draw visible in reports (outbreak, selection, jitter, termination) |
| Closing non-map state | **unchanged** — treasury, economy, politics, institutions, world conflicts |
| Strategic-map projection | **changed in exactly and only the deliberately changed presentation fields** — asserted field-by-field, not merely "differs": every other projection field is asserted equal |
| Save bytes / history hashes | **allowed to differ** — the saved presentation genuinely differs, so the hashes *should*; requiring otherwise would be incorrect |

The fourth row is the one that makes the test meaningful in both directions: it proves the changed
values really do reach the API (otherwise the API would be broken), *and* that nothing else moved.

### 10.3 Insertion-order-independence proof — `test_map_insertion_order_independence.py`

Rebuild the map's dictionaries with **the exact same keys and the exact same values**, differing
**only in Python insertion order**. Concretely: `StrategicMapState.theaters` is reconstructed from a
reversed / shuffled item sequence, as is any nested dict, and nothing else differs at all.

**`routes` and `shapes` are NOT reordered.** Their tuple ordering is canonical and enforced;
reordering them is an *invalid* map that §3 must **reject, not normalize**, and that rejection is
tested in `test_geography.py` as `route_not_canonical` / `shape_not_canonical`. Using them here
would test the opposite of the intended property.

Require, for the reordered-insertion variant:

| Assertion | Requirement |
|---|---|
| Canonical state serialization | **byte-identical** (`canonical_dumps` sorts dict keys) |
| API projection JSON | **byte-identical** (§11 sorts every emitted collection) |
| Simulation outputs | **byte-identical** — reports, RNG-observable outcomes and closing state |
| Save bytes / history hashes | **byte-identical** — unlike §10.2, nothing authored differs here |

§10.2 and §10.3 are complementary and non-overlapping: one varies values and permits byte
divergence; the other varies only ordering and forbids any divergence at all.

---

## 11. API contract

Real path, derived in §2 from `routes.py:77` + `main.py:125`: **`GET /api/game/map/strategic`**.

```python
class StrategicTheaterProjection(BaseModel):
    """One theater, fully resolved for display. The client renders these fields and derives
    nothing: ownership, capital status and directed adjacency all arrive resolved."""

    model_config = _STRICT                       # extra="forbid", frozen=True

    theater_id: str
    display_name: str
    kind: Literal["land", "coastal"]
    owner_id: str
    owner_namespace: Literal["player_country", "foreign_profile"]
    owner_display_name: str
    is_player_owned: bool
    is_capital: bool
    centroid_x: int
    centroid_y: int
    label_anchor: Literal["n", "s", "e", "w", "center"]
    outgoing_theater_ids: tuple[str, ...]
    """Theaters reachable FROM this one in one step. Sorted. Server-derived by
    `geography.outgoing_and_incoming`."""
    incoming_theater_ids: tuple[str, ...]
    """Theaters from which this one is reachable in one step. Sorted. Server-derived.

    Two fields, not one merged `connected_theater_ids`: with a single merged list the client
    cannot tell A->B from B->A from A<->B, and the whole point of storing directed routes is
    lost the moment the projection flattens them.
    """


class StrategicRouteProjection(BaseModel):
    """One DISPLAY edge. Reciprocal directed pairs are collapsed into a single row so the map
    draws one line, never two overlapping ones."""

    model_config = _STRICT

    from_theater_id: str
    to_theater_id: str
    bidirectional: bool
    """True iff BOTH directed rows exist in authoritative state.

    When False, `from_theater_id` -> `to_theater_id` is the ONE authored direction, emitted as
    authored -- it is never reordered for determinism, because reordering it would destroy the
    only information the field carries.
    """


class StrategicShapeProjection(BaseModel):
    """One authored political outline. Presentation only; never implies adjacency."""

    model_config = _STRICT

    shape_id: str
    owner_id: str
    owner_namespace: Literal["player_country", "foreign_profile"]
    owner_display_name: str
    polygon: tuple[tuple[int, int], ...]
    """Open ring, emitted in stored authored order. No rotation or winding normalization."""


class StrategicMapProjection(BaseModel):
    """The whole read-only strategic map. Contains no order, no command, no pending action and
    no affordance for one."""

    model_config = _STRICT

    map_id: str
    capital_theater_id: str
    theaters: tuple[StrategicTheaterProjection, ...]
    routes: tuple[StrategicRouteProjection, ...]
    shapes: tuple[StrategicShapeProjection, ...]
```

### 11.1 Directed connectivity, stated exactly

The client must be able to distinguish **A → B**, **B → A** and **A ↔ B** without inferring
mechanics from line shapes, arrowheads or geometry. Two independent mechanisms guarantee it:

1. **Per-theater directed adjacency is authoritative and never collapsed.**
   `outgoing_theater_ids` and `incoming_theater_ids` together reproduce the full directed graph
   exactly. `B ∈ A.outgoing` ⟺ the row `A→B` exists. This alone is sufficient; the route rows are a
   drawing convenience layered on top.
2. **Display route rows carry their own direction.**

   | Authoritative rows for the pair {A, B} | Emitted row | `bidirectional` |
   |---|---|---|
   | `A→B` and `B→A` | `from=min(A,B)`, `to=max(A,B)` | `true` |
   | `A→B` only | `from=A`, `to=B` (**as authored**) | `false` |
   | `B→A` only | `from=B`, `to=A` (**as authored**) | `false` |

   Exactly one row is emitted per unordered pair that has at least one directed row. Lexicographic
   ordering is applied **only** to the reciprocal case, where both directions exist and the choice
   carries no information; a one-way row is emitted in its true direction and is never flipped.

Authoritative state keeps both directed rows in `StrategicMapState.routes`. Only the projection
collapses reciprocal pairs, and it never loses a direction in doing so.

### 11.2 Ordering (canonical, server-applied)

| Collection | Order |
|---|---|
| `theaters` | sorted by `theater_id` |
| `routes` | sorted by `(from_theater_id, to_theater_id)` |
| `shapes` | sorted by `shape_id` |
| `outgoing_theater_ids`, `incoming_theater_ids` | sorted |
| `polygon` | stored authored order (no sort — sorting vertices would destroy the ring) |

Sorting makes the response **insertion-order independent by construction**, which is what §10.3
asserts byte-for-byte.

### 11.3 Boundary behaviours

- **No active game.** The endpoint follows the existing convention of the other `/api/game/*`
  readers and returns the same error shape they do. There is **no `present: false` flag**: §3 makes
  an absent map impossible inside a loaded game, so "no game" and "no map" are different conditions
  and only the first is representable.
- **Invalid state.** A save whose invariants fail is rejected by the existing load path long before
  this endpoint is reachable. The projection never repairs, defaults or patches state.
- **Never mutates.** No RNG draw, no turn resolution, no state write, no history append.

### 11.4 Exact contract delta

One new path `/api/game/map/strategic`; four new schema components
(`StrategicMapProjection`, `StrategicTheaterProjection`, `StrategicRouteProjection`,
`StrategicShapeProjection`); the two corrected description strings from §7. **Any other drift is a
stop condition.** `npm run generate:api` regenerates both `docs/contracts/phase4a-openapi.json` and
`frontend/src/api/schema.d.ts` in the same commit; the frontend owns no hand-written types for this.

**The frontend must not infer** owner identity (server sends `owner_id`, `owner_namespace`,
`owner_display_name`), route direction (server sends `bidirectional` plus true `from`/`to`), or
adjacency (server sends `outgoing_theater_ids` and `incoming_theater_ids`).

---

## 12. Frontend integration

- **Component**: `frontend/src/greybox/screens/StrategicMapScreen.tsx`, registered in the existing
  `greybox/registry.tsx` screen registry beside Dashboard / Decisions / History.
- **Screen-state identifier**: `"strategic-map"`, matching the registry's existing string-keyed
  screen-state convention (the app is screen-state driven, not URL-routed).
- **Navigation entry**: a "Strategic map" item in the existing primary navigation, adjacent to
  History.
- **Query ownership and cache invalidation**: the screen owns one fetch of
  `GET /api/game/map/strategic` through the same client wrapper the other screens use. The map is
  campaign-static, so it is **not** refetched on turn resolution.

  "Fetched once per loaded game" is only safe if *loaded game* changes are observed, so the query
  key includes the loaded-game identity and the cache is invalidated on the two events that change
  it, using the **existing** query-cache conventions — no second frontend cache is introduced:

  | Event | Required behaviour |
  |---|---|
  | Create a new game | strategic-map query **invalidated**; next render fetches the new map |
  | Load a different save | strategic-map query **invalidated** |
  | Switch `tiny_valid` → `decree_state` or `deficit_demo` | the prior map **cannot** be retained or displayed |
  | Resolve an ordinary turn | **no** refetch — the map is immutable within a campaign (§8) |
  | Loaded game changes | **selection state clears** — a `theater_id` from the previous map must not survive into the new one |

  A stale map is worse than a missing one: it would show the player a coherent-looking map of a
  country they are no longer governing. §13 tests all five rows.
- **Loading state**: a labelled busy region announcing "Loading strategic map".
- **API error state**: the existing error presentation with a retry control. No partial map renders.
- **Keyboard focus on entry**: focus lands on the screen heading; the theater list is the next tab
  stop.
- **Return navigation**: the standard back-to-dashboard control, same as every other screen.
- **Theater selection state**: local component state holding at most one `theater_id`.
- **Mouse/keyboard synchronisation**: a node click and a list-row focus write the same state, and
  each reflects the other's selection.
- **Directional display**: each selected theater's panel lists **"Routes out"** and **"Routes in"**
  as two separate labelled lists, fed directly by `outgoing_theater_ids` / `incoming_theater_ids`.
  A one-way edge is stated in words, never left to an arrowhead.
- **Screen-reader announcement on selection change**: an `aria-live="polite"` region announcing
  "<name>, <kind>, owned by <owner display name>, N routes out, M routes in".
- **Small width (< 900px)**: the map panel is not rendered; the theater list becomes the whole
  screen and carries identical information, directions included.
- **Empty session (no game loaded)**: the navigation entry is disabled with an explanatory label;
  the screen is unreachable rather than rendering an empty map.
- **Terminal campaign**: the map stays fully inspectable — inspection is not an action, and W1's CLI
  set the precedent that concluded campaigns remain readable.

**Selection is inspection only.** No pending order is created, no order panel exists, nothing is
queued, and no control implies movement is available. The accessibility tree contains no button,
menu item or form control referring to orders, movement, deployment or units — asserted by a test
(§13).

---

## 13. Test matrix

| Requirement | Test file |
|---|---|
| `WorldState` without `strategic_map` is rejected | `test_map_state.py` |
| Empty `theaters` rejected; empty `shapes` rejected | `test_map_state.py` |
| Empty `routes` accepted (single-theater map) | `test_map_state.py` |
| **Empty theater dict key rejected** (C2) | `test_map_state.py` |
| **Non-string theater dict key rejected** (C2) | `test_map_state.py` |
| **Overlength (>64 char) theater dict key rejected** (C2) | `test_map_state.py` |
| `route_self_edge` — **asserts the emitted code string** | `test_geography.py` |
| `route_duplicate` — emitted code, **without** tripping ordering | `test_geography.py` |
| `route_not_canonical` — emitted code, **without** any duplicate | `test_geography.py` |
| `shape_id_duplicate` — emitted code, **without** tripping ordering | `test_geography.py` |
| `shape_not_canonical` — emitted code, **without** any duplicate | `test_geography.py` |
| `shape_polygon_closing_vertex_repeated` — emitted code | `test_geography.py` |
| `shape_polygon_repeats_vertex` — emitted code | `test_geography.py` |
| `shape_polygon_zero_area` — emitted code (collinear ring) | `test_geography.py` |
| **Every member of `MAP_CONSTRUCTION_CODES` is reachable and appears in a real emitted error** (C4) | `test_geography.py` |
| Polygon < 3 vertices, coordinate out of range | `test_geography.py` |
| Rings differing only by rotation/winding both load and differ in bytes | `test_geography.py` |
| Multiple island shapes for one owner accepted | `test_geography.py` |
| `shoelace_doubled_area` exactness incl. odd-area polygons | `test_geography.py` |
| **`outgoing_and_incoming` type-checks under mypy with no circular import** (C4) | mypy gate |
| Each of the **8** state-invariant codes fires, one focused test each (§9) | `test_map_invariants.py` |
| **`map_owner_*` codes fire identically for a bad THEATER owner and a bad SHAPE owner** (C3) | `test_map_invariants.py` |
| **Problem text names the theater or shape the bad reference came from** (C3) | `test_map_invariants.py` |
| Capital resolves and is player-owned | `test_map_invariants.py` |
| Player connectivity holds; routeless foreign island valid | `test_map_invariants.py` |
| Exact scenario geometry digests (canonical-JSON SHA-256, one per scenario map, pinned) | `test_scenarios.py` |
| API canonical ordering: theaters, routes, shapes, both adjacency lists | `test_api_projections.py` |
| API reciprocal pair collapses to one row with `bidirectional=true` | `test_api_projections.py` |
| API one-way route emits its **authored** direction with `bidirectional=false`, not a flipped one | `test_api_projections.py` |
| API `outgoing`/`incoming` reproduce the directed graph exactly | `test_api_projections.py` |
| Group 53 clean campaign produces no problems | `test_map_reconciliation.py` |
| Each of the four group-53 problem strings asserted verbatim | `test_map_reconciliation.py` |
| `resolve_turn` leaves the map byte-identical | `test_map_reconciliation.py` |
| Rehashed map tampering, 5 cases: chain verifies green **and** group 53 rejects | `test_map_tamper_matrix.py` |
| **Simulation inertness** (§10.2), incl. projection changed in exactly the changed fields | `test_map_presentation_neutrality.py` |
| **Insertion-order independence** (§10.3), byte-identical state, projection and outputs | `test_map_insertion_order_independence.py` |
| Presentation AST/source boundary | `test_map_presentation_boundary.py` |
| Save/reload map identity | `test_save_format.py` (extension) |
| A `0.13.0` save is rejected before payload parse | `test_compatibility.py` (extension) |
| **New game invalidates the strategic-map query** (C5) | `StrategicMapScreen.test.tsx` |
| **Loading another save invalidates it** (C5) | `StrategicMapScreen.test.tsx` |
| **Switching `tiny_valid` → `decree_state` / `deficit_demo` cannot retain the prior map** (C5) | `StrategicMapScreen.test.tsx` |
| **Resolving an ordinary turn does not refetch the immutable map** (C5) | `StrategicMapScreen.test.tsx` |
| **Selection state clears when the loaded game changes** (C5) | `StrategicMapScreen.test.tsx` |
| Terminal campaign map still inspectable | `StrategicMapScreen.test.tsx` |
| **No military-order control anywhere in the accessibility tree** | `StrategicMapScreen.test.tsx` |
| **No raw ids or raw enum text exposed to players** | `StrategicMapScreen.test.tsx` |
| "Routes out" / "Routes in" rendered separately; one-way stated in words | `StrategicMapScreen.test.tsx` |
| Kind and owner conveyed by more than colour | `StrategicMapScreen.test.tsx` |
| < 900px list-only degradation retains directional information | `StrategicMapScreen.test.tsx` |
| Keyboard nav, accessible names, live-region announcement | `GreyboxApp.accessibility.test.tsx` (extension) |
| Contract regeneration produces zero unexplained drift | contract-drift check |
| Real 1440×900 screenshots, all three maps | browser walkthrough (§14) |
| Narrow-width list-only screenshot | browser walkthrough (§14) |

M0 adds **no** report test, **no** RNG-stream test, **no** military formula and **no** phase-slot
test, because it adds none of those things. The 13-report completeness test is untouched.

---

## 14. Browser walkthrough

Against the real `mandate-gui` process and the built SPA, for **each** of `tiny_valid`,
`decree_state` and `deficit_demo`:

new game → open Strategic map → confirm shapes render with distinct fill **and** hatch → confirm
every authored theater appears with the correct name, kind and owner → confirm the capital marker →
click a theater and confirm the list row syncs → traverse every theater by keyboard alone → confirm
the live-region announcement → confirm "Routes out" and "Routes in" match the authored directed rows
in §5 → (`deficit_demo`) confirm `tolvane_isle` shows zero routes in **and** zero routes out →
resolve a turn and confirm the map is byte-identical → **capture a 1440×900 screenshot**.

Then shrink below 900px, confirm the list-only layout still states directions, and **capture one
narrow screenshot**. Every command and screenshot is recorded in the closeout.

---

## 15. Commit sequence

0. **Recover the checkout** on `claude/phase-4a-graphical-vertical-slice` with the exact three
   commands in §0. The ancestor check must exit 0; local and remote must both then read
   `1df8f397e2eb6a5c3cd93e83f8e6b7300d66c4b9`. Never reset, rebase, amend, cherry-pick or
   force-push.
1. **Freeze the approved M0 plan** — copy it to
   `docs/plans/strategic-military-map-m0-implementation-plan.md`, prove source and worktree copy
   byte-identical with `cmp`, commit **exactly that one file**, push immediately, then verify local
   `HEAD` equals remote, the tree is clean, and the committed blob rehashes to the same value.

   **The long baseline is deliberately NOT run before this commit.** Making the plan durable comes
   first; this container has destroyed the plan file twice, and a 10,672-test gate is a long window
   in which to lose it again. The baseline is re-established immediately *after* the freeze commit
   and before any fixture or code.
2. Re-establish the 10,672 / 133 baseline on the recovered checkout, then freeze an authentic
   `0.13.0` save fixture produced by the unmodified build.
3. Pure geography types and helpers + construction tests (`geography.py`, `test_geography.py`).
4. **Atomic:** `StrategicMapState`, `SovereignRef`, required `WorldState.strategic_map`,
   `capital_theater_id`, every state invariant, all three complete scenario maps, the conftest
   fixture map, and the **ruleset bump `0.13.0 → 0.14.0`**. Atomic because `state.py:1255-1271`
   establishes that a bump lands with the state it describes.
5. Group 53 reconciler + `history.py` wiring + rehashed tamper tests.
6. Read-only API projection + `/api/game/map/strategic` + `MapProjection` text correction +
   **contract regeneration**.
7. Accessible read-only frontend map + navigation + component and accessibility tests.
8. Simulation-inertness (§10.2) and insertion-order-independence (§10.3) tests + full-stack tests.
9. Real browser walkthrough evidence (screenshots).
10. ADR 0017 + roadmap closeout + the complete regression gate.

**Every commit green before push. Never push while the required gate is still running** — the
explicit correction of W1 commit 10's process deviation.

**Files M0 may touch:** `geography.py` (new), `state.py`, `invariants.py`, `reconciliation.py`,
`history.py`, `projections.py`, `routes.py`, the three scenario YAMLs, `conftest.py`, the new tests,
the new frontend screen + registry + navigation, the generated contract artifacts, the ADR and the
roadmap. **No military, finance, constitution, report, phase or W1 file.** If one becomes
necessary — stop and ask.

---

## 16. Nonbinding M1–M5 (not implementation-ready)

**M1 — Army formations and movement**, restricted to player-owned territory. Readiness, supply,
finance, the 14th report, its reconciliation and tamper cases, interactive orders, slot-8
orchestration. All formation content from earlier drafts (personnel counts, readiness bands, supply
rates, command capacity) is **illustrative and nonbinding**: prefer abstract capacity, drop force
size entirely if movement does not consume it, calibrate before freezing anything, and obtain
explicit approval. No formulas are written yet. On finance, this plan makes **no** claim that an
unaffordable order cannot create debt — the engine has established deficit and borrowing behaviour,
and the M1 audit decides.

**M2 — `WarPowers` axis** and the war-powers audit: foreign access, mobilization, border crossing,
joining a conflict, declaring war, withdrawal. **Blocked on the W1 player-participation problem:**
W1 conflict dyads resolve only through `foreign_profiles` and structurally reject the player.
Options — (A) generalize conflict parties to a tagged ref (breaking; every W1 reconciliation group
revised), (B) keep W1 intact and add a linked player-intervention state (additive; W1 untouched),
(C) a broader unified war state with migration (most expressive, most expensive). **B looks
strongest, is not decided, and W1 is not modified during M0.**

**M3 — Navy and Air.** `TheaterKind` and `RouteKind` gain SEA / AIR here, where consumers finally
exist.
**M4 — Abstract combat and occupation.**
**M5 — Peace and territorial outcomes.**

**Completeness testing at report 14 (M1):** keep exhaustive coverage (16,382 subsets) if the
isolated runtime stays **under 90 seconds** — measured, not assumed. Only above that may
deterministic combinatorial coverage be considered; **no new dependency and no random sampling
without separate authorization**; mandatory revisit at report 15. Baseline: 8,190 + 1 = 8,191 in
~26s.

**Expansion boundary:** the base game may express **abstract national-level** occupation, annexation
and insurgency outcomes at M4/M5. Province granularity, city capture and local economies belong to
Cities & Provinces; Marines, Space Force, equipment and arms markets to Armed Forces; the spy agency
and covert action to Intelligence. **No empty models are added now for any of them.**

---

## 17. Resolved approvals — no open decisions remain

Every decision this plan previously held open has been ruled on. Nothing here is pending.

| # | Decision | Ruling |
|---:|---|---|
| 1 | Implementation branch | **`claude/phase-4a-graphical-vertical-slice`** — final (§0) |
| 2 | Required nonempty map in ruleset `0.14.0` | approved (§3) |
| 3 | Tagged `SovereignRef` | approved (§3) |
| 4 | LAND / COASTAL only in M0 | approved (§3) |
| 5 | Exact three-scenario geometry | approved (§5) |
| 6 | Multiple shapes per owner | approved (§5.4) |
| 7 | No computational-geometry dependency; browser review suffices for these authored polygons | approved (§5.4) |
| 8 | Group 53 staticness reconciliation and its honest genesis limitation | approved (§8) |
| 9 | Keep and correct the existing dashboard `MapProjection` | approved (§7) |
| 10 | `/api/game/map/strategic` | approved (§11) |
| 11 | Political polygons with theater nodes | approved (§5, §12) |
| 12 | No pan/zoom in M0 | approved (§12) |
| 13 | `"strategic-map"` screen-state identifier | approved (§12) |
| 14 | Navigation adjacent to History | approved (§12) |
| 15 | All three scenario `content_version` changes | approved (§15) |
| 16 | Atomic ruleset bump with the authoritative state | approved (§15) |
| 17 | M1–M5 remain nonbinding | approved (§16) |

**No M1 implementation detail is binding.** §16 remains illustrative throughout; nothing in it may
be treated as a specification.

---

## 18. Contradiction and cross-reference sweep

Sweep items added for corrections C1–C5:

- **C1.** §0 fixes the branch as `claude/phase-4a-graphical-vertical-slice` and gives the exact
  three recovery commands; §15 step 0 uses that branch and no other; §17 records it as ruled. The
  superseded session branch name appears **zero** times in this document — verified by grep, and
  deliberately not quoted here so that the grep stays a real check rather than matching this
  sentence. **Consistent — no open branch question survives anywhere.**
- **C2.** §3 keys `theaters` as `dict[StrictMapId, TheaterState]`; §13 tests empty, non-string and
  overlength keys; §9's ownership table routes id-length and strictness to Pydantic annotations
  rather than to an invariant. **Consistent — the key is validated where it is declared, not
  discovered later through a route reference.**
- **C3.** §9.1 defines one shared sovereign-reference rule with three context-neutral `map_owner_*`
  / `map_player_ref_not_player` codes applied identically to theater owners and shape owners; the
  four previous context-split codes appear only in the sentence recording their replacement;
  `theater_foreign_ref_is_player` appears only in statements recording its removal; the invariant
  count is restated as **eight**; §13 tests that the same code fires for a bad theater owner and a
  bad shape owner, and that problem text still names the source. **Consistent — one rule, one
  definition, no duplicated namespace semantics.**
- **C4.** §3 declares `MAP_CONSTRUCTION_CODES` and every custom construction `ValueError` is
  prefixed with its exact code; §13 asserts the emitted code rather than a comment or a test-function
  name, and adds a reachability test over the whole frozen set. `outgoing_and_incoming` takes
  `Sequence[DirectedEdge]` via a `Protocol`, so `geography.py` carries no quoted forward reference
  to a state-module type and creates no runtime circular import — again not quoted here, so the
  grep remains a real check. **Consistent — the codes are real behaviour, not documentation.**
- **C5.** §12 states the map is not refetched on turn resolution **and** specifies invalidation on
  new game and on load, with selection state cleared when the loaded game changes; §13 tests all
  five behaviours. **Consistent — no claim anywhere says a map survives a New Game or a Load.**
- **M1 boundary.** §16 remains illustrative and §17 records M1–M5 as nonbinding; nothing added by
  C1–C5 introduces an M1 specification. **Consistent.**
- **Structure preserved.** The complete model declarations, the 22 directed route rows, the 9
  polygon rows, the four verbatim group-53 strings and the four projection class declarations all
  remain present after the corrections. **Verified by count, not by assertion.**

Pre-existing sweep items, re-checked:

- §3 makes the map **required**; §11.3 has no `present` flag; §12 disables navigation only when no
  game is loaded. **Consistent** — "no game" and "no map" are different conditions and only the first
  is representable.
- §3 declares `min_length=1` on theaters and shapes; §9 removes `map_empty` as unreachable.
  **Consistent.**
- §4 stores the capital once; §3's `TheaterState` has no `is_capital`; §11's *projection* carries
  `is_capital` as a derived display flag. **Consistent** — derived presentation, not stored state.
- §3 forbids a self-edge at construction; §9 assigns `route_self_edge` to Pydantic only and to no
  invariant. **Consistent — no double validation.**
- §3 checks route duplicates before route ordering, and shape duplicates before shape ordering; §9
  lists four separate ids; §13 requires a focused test per id proving independent reachability, and
  each id is now emitted in the error text itself (C4). **Consistent — no failure id covers two
  different faults, and no id exists only as a comment.**
- §5.4 states polygons are stored in authored order with no rotation or winding normalization; §3's
  validator only rejects a repeated closing vertex, duplicate consecutive vertices and zero area,
  and never reorders; §11.2 excludes `polygon` from sorting; §13 tests that rotation-variant rings
  both load and differ in bytes. **Consistent — the word "canonical" is used only where an ordering
  rule is genuinely enforced.**
- §5's three maps each satisfy §6's connectivity rule; `deficit_demo`'s `tolvane_isle` is routeless
  and foreign, which §6 explicitly permits and §14 verifies visually. **Consistent.**
- §5.3 notes every authored pair is reciprocal and places the one-way case in unit fixtures; §11.1
  and §13 test the one-way case there. **Consistent, and the choice is disclosed rather than
  silently skipped.**
- §5.4 admits self-intersection is unvalidated; §14 requires screenshots of all three maps; §17
  item 5 raises it as a decision. **Consistent — the gap is disclosed, mitigated and surfaced.**
- §8 adds reconciliation but **no report**; §13 lists no report test; §15 touches no report file;
  §16 places the 14th report at M1. **Consistent.**
- §8.3 case 4 tampers presentation and expects rejection; §10.2 proves presentation does not change
  *simulation outputs* while explicitly permitting save-hash divergence. **Consistent** — inert to
  simulation, not inert to integrity.
- §10.2 permits byte divergence (values changed) while §10.3 forbids it (only ordering changed); the
  two tests vary disjoint things and neither asserts the other's property. **Consistent — the
  previous draft's contradiction is resolved.**
- §10.3 reorders only dict insertion order and explicitly refuses to reorder `routes`/`shapes`; §3
  rejects non-canonical tuples; §13 tests that rejection separately. **Consistent — ordering is
  rejected, never normalized.**
- §11.1 collapses reciprocal pairs while §3 stores both directed rows, and §11's
  `outgoing_theater_ids`/`incoming_theater_ids` reproduce the directed graph exactly; §12 renders
  the two lists separately. **Consistent — no direction is lost and none is inferred.**
- §12 states selection is inspection only; §13 asserts no order control in the accessibility tree;
  §15 adds no decision or phase code. **Consistent.**
- §15 places the ruleset bump in commit 4 citing `state.py:1255-1271`; §3's required field lands in
  the same commit. **Consistent with repository version policy.**
- §16's M2 blocker (W1 structurally rejects the player) does not touch M0, and §15 forbids W1 file
  changes. **Consistent.**
- §0 withdraws the previous plan metrics and §19 recomputes them; no figure in this document is
  carried over from the destroyed file except the explicitly-labelled carried-forward test baseline
  in §1. **Consistent.**
- §15 step 1 freezes the plan before step 2 runs the baseline; §19 gives the same ordering and the
  same reason. **Consistent — durability precedes verification, deliberately.**

No contradiction found.

---

## 19. Freeze procedure

Chat-paste and file-attachment delivery have both now failed to reach the reviewer, and the
container has destroyed this plan file twice. **The repository is the durability mechanism**, so the
plan is made durable first and reviewed from the committed blob.

The freeze, executed as §15 step 1 and nothing more:

```bash
# 0. recover the checkout (sec.0) -- ancestor check must exit 0
git fetch origin
git merge-base --is-ancestor HEAD origin/claude/phase-4a-graphical-vertical-slice
git merge --ff-only origin/claude/phase-4a-graphical-vertical-slice

# 1. copy the plan into the repository and prove the copy is exact
cp /root/.claude/plans/mandate-master-build-breezy-puppy.md \
   docs/plans/strategic-military-map-m0-implementation-plan.md
cmp /root/.claude/plans/mandate-master-build-breezy-puppy.md \
    docs/plans/strategic-military-map-m0-implementation-plan.md
sha256sum /root/.claude/plans/mandate-master-build-breezy-puppy.md \
          docs/plans/strategic-military-map-m0-implementation-plan.md

# 2. commit EXACTLY this one file, then push immediately
git add docs/plans/strategic-military-map-m0-implementation-plan.md
git status --porcelain          # must show exactly one staged file, nothing else
git commit -m "Strategic Map M0 (1/N): freeze approved implementation plan"
git push -u origin claude/phase-4a-graphical-vertical-slice

# 3. verify durability from the Git object, not from the worktree
git rev-parse HEAD origin/claude/phase-4a-graphical-vertical-slice   # must be equal
git status --porcelain                                              # must be empty
git cat-file blob HEAD:docs/plans/strategic-military-map-m0-implementation-plan.md | sha256sum
```

Source hash, worktree-copy hash and Git-object hash must all be equal. **The long 10,672/133
baseline is not run before this commit** — durability first, per §15.

The measured line count, byte count and SHA-256 are reported in the accompanying message and are
deliberately **not** written into the file: a file cannot contain its own hash, and pretending
otherwise is the same class of unverifiable claim these correction rounds exist to eliminate.

**No implementation is authorized by this plan.** Freezing it commits one documentation file and
nothing else. No fixture, no code, no scenario, no test, no contract, no frontend file, no ADR and
no roadmap change accompanies the freeze commit, and M0 commit 2 does not begin.
