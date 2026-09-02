"""Strategic Military Map Gate M0 commit 8 -- the sec.10.2 simulation-inertness proof.

A variant of `tiny_valid` is built that changes ONLY genuinely presentational values: theater
centroids, label anchors, and shape polygon vertices. Theater ids, kinds, owners, the capital,
every route row and every shape id -- and their ordering -- are all held fixed.

Resolving several turns from both the baseline and the variant must produce: identical turn
reports (every domain field, so every RNG-observable outcome too), identical closing state
outside the map itself, and a strategic-map projection that differs in EXACTLY the deliberately
changed fields -- proving both that the changed values really do reach the API (the projection
would be broken otherwise) and that nothing else moved. Save bytes/history hashes are allowed to
differ (the saved presentation genuinely differs), so this file does not assert on them.
"""

from __future__ import annotations

from app.api.projections import build_strategic_map
from app.content.scenarios import load_scenario_file
from app.simulation.geography import LabelAnchor
from app.simulation.history import new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState, StrategicMapState
from tests.conftest import TINY_VALID_SCENARIO_PATH
from tests.history_tamper_helpers import advance_n

_TURNS = 5
_COORD_OFFSET = 500
"""Added to every centroid/vertex coordinate. `tiny_valid`'s largest authored coordinate is 9,400
(`shape_vetruska`'s [9400, 4600] vertex); +500 keeps every translated value within the map's own
0..10,000 grid (`geography.MAP_GRID_MAX`)."""

_ANCHOR_CYCLE: dict[LabelAnchor, LabelAnchor] = {
    LabelAnchor.CENTER: LabelAnchor.NORTH,
    LabelAnchor.NORTH: LabelAnchor.SOUTH,
    LabelAnchor.SOUTH: LabelAnchor.EAST,
    LabelAnchor.EAST: LabelAnchor.WEST,
    LabelAnchor.WEST: LabelAnchor.CENTER,
}
"""A fixed derangement: every anchor `tiny_valid` actually authors (center/w/n/e) is guaranteed to
map to something different, so the projection-level "did change" assertions are never vacuous."""


def _presentation_only_variant(map_state: StrategicMapState) -> StrategicMapState:
    """A variant of `map_state` differing ONLY in centroid/label-anchor/polygon values.

    Theater ids (the dict keys), kinds, owners, `capital_theater_id`, and every route and shape id
    -- plus their ordering -- are copied through untouched.
    """
    translated_theaters = {
        theater_id: theater.model_copy(
            update={
                "presentation": theater.presentation.model_copy(
                    update={
                        "centroid_x": theater.presentation.centroid_x + _COORD_OFFSET,
                        "centroid_y": theater.presentation.centroid_y + _COORD_OFFSET,
                        "label_anchor": _ANCHOR_CYCLE[theater.presentation.label_anchor],
                    }
                )
            }
        )
        for theater_id, theater in map_state.theaters.items()
    }
    translated_shapes = tuple(
        shape.model_copy(
            update={
                "polygon": tuple((x + _COORD_OFFSET, y + _COORD_OFFSET) for x, y in shape.polygon)
            }
        )
        for shape in map_state.shapes
    )
    return map_state.model_copy(
        update={"theaters": translated_theaters, "shapes": translated_shapes}
    )


def _baseline_and_variant() -> tuple[GameState, GameState]:
    baseline = load_scenario_file(TINY_VALID_SCENARIO_PATH)
    variant_map = _presentation_only_variant(baseline.world.strategic_map)
    variant = baseline.model_copy(
        update={"world": baseline.world.model_copy(update={"strategic_map": variant_map})}
    )
    return baseline, variant


def test_variant_construction_actually_changes_every_presentation_field_and_nothing_else() -> None:
    """Sanity check on the fixture itself, independent of any turn resolution: every theater's
    centroid/anchor and every shape's polygon differs, while every non-presentational field --
    including dict/tuple ORDER -- is untouched."""
    baseline, variant = _baseline_and_variant()
    baseline_map = baseline.world.strategic_map
    variant_map = variant.world.strategic_map

    assert baseline_map.map_id == variant_map.map_id
    assert baseline_map.capital_theater_id == variant_map.capital_theater_id
    assert baseline_map.routes == variant_map.routes
    assert list(baseline_map.theaters) == list(variant_map.theaters)
    assert [s.shape_id for s in baseline_map.shapes] == [s.shape_id for s in variant_map.shapes]

    for theater_id, baseline_theater in baseline_map.theaters.items():
        variant_theater = variant_map.theaters[theater_id]
        assert baseline_theater.display_name == variant_theater.display_name
        assert baseline_theater.kind == variant_theater.kind
        assert baseline_theater.owner == variant_theater.owner
        assert baseline_theater.presentation.centroid_x != variant_theater.presentation.centroid_x
        assert baseline_theater.presentation.centroid_y != variant_theater.presentation.centroid_y
        assert (
            baseline_theater.presentation.label_anchor != variant_theater.presentation.label_anchor
        )

    for baseline_shape, variant_shape in zip(baseline_map.shapes, variant_map.shapes, strict=True):
        assert baseline_shape.shape_id == variant_shape.shape_id
        assert baseline_shape.owner == variant_shape.owner
        assert baseline_shape.polygon != variant_shape.polygon


def test_presentation_only_variant_leaves_reports_and_non_map_state_byte_identical() -> None:
    baseline_state, variant_state = _baseline_and_variant()
    baseline_save = advance_n(
        new_game(baseline_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )
    variant_save = advance_n(
        new_game(variant_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )

    # Turn reports identical for every resolved turn: every domain field (finance, production,
    # labor, tax bases, political, legislative, political capital, relationships, coup/unrest,
    # election, amendment, foreign affairs) and every RNG-observable outcome.
    for turn in range(1, _TURNS + 1):
        baseline_report = baseline_save.entry_at(turn).report()
        variant_report = variant_save.entry_at(turn).report()
        assert baseline_report is not None
        assert baseline_report == variant_report

    # Closing state, excluding the map itself (which genuinely differs, by construction),
    # is byte-identical: treasury, economy, politics, institutions, world conflicts.
    baseline_closing = baseline_save.current_state()
    variant_closing = variant_save.current_state()
    exclude = {"world": {"strategic_map"}}
    assert baseline_closing.model_dump(mode="json", exclude=exclude) == variant_closing.model_dump(
        mode="json", exclude=exclude
    )


def test_presentation_only_variant_changes_the_projection_in_exactly_the_changed_fields() -> None:
    baseline_state, variant_state = _baseline_and_variant()
    baseline_save = advance_n(
        new_game(baseline_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )
    variant_save = advance_n(
        new_game(variant_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )

    baseline_projection = build_strategic_map(baseline_save.current_state())
    variant_projection = build_strategic_map(variant_save.current_state())

    assert baseline_projection.map_id == variant_projection.map_id
    assert baseline_projection.capital_theater_id == variant_projection.capital_theater_id
    assert baseline_projection.routes == variant_projection.routes

    baseline_theaters = {t.theater_id: t for t in baseline_projection.theaters}
    variant_theaters = {t.theater_id: t for t in variant_projection.theaters}
    assert set(baseline_theaters) == set(variant_theaters)
    for theater_id, baseline_theater in baseline_theaters.items():
        variant_theater = variant_theaters[theater_id]
        assert baseline_theater.display_name == variant_theater.display_name
        assert baseline_theater.kind == variant_theater.kind
        assert baseline_theater.is_capital == variant_theater.is_capital
        assert baseline_theater.is_player_owned == variant_theater.is_player_owned
        assert baseline_theater.owner_id == variant_theater.owner_id
        assert baseline_theater.owner_namespace == variant_theater.owner_namespace
        assert baseline_theater.owner_display_name == variant_theater.owner_display_name
        assert baseline_theater.outgoing_theater_ids == variant_theater.outgoing_theater_ids
        assert baseline_theater.incoming_theater_ids == variant_theater.incoming_theater_ids
        # The deliberately changed fields DO differ -- proving they really reach the API.
        assert baseline_theater.centroid_x != variant_theater.centroid_x
        assert baseline_theater.centroid_y != variant_theater.centroid_y
        assert baseline_theater.label_anchor != variant_theater.label_anchor

    baseline_shapes = {s.shape_id: s for s in baseline_projection.shapes}
    variant_shapes = {s.shape_id: s for s in variant_projection.shapes}
    assert set(baseline_shapes) == set(variant_shapes)
    for shape_id, baseline_shape in baseline_shapes.items():
        variant_shape = variant_shapes[shape_id]
        assert baseline_shape.owner_id == variant_shape.owner_id
        assert baseline_shape.owner_namespace == variant_shape.owner_namespace
        assert baseline_shape.owner_display_name == variant_shape.owner_display_name
        assert baseline_shape.polygon != variant_shape.polygon
