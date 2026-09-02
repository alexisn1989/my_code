"""Strategic Military Map Gate M0 commit 8 -- the sec.10.3 insertion-order-independence proof.

`StrategicMapState.theaters` is rebuilt from the exact same keys and values, differing only in
Python dict insertion order (reversed). `routes` and `shapes` are NOT reordered: their tuple
order is canonical and enforced -- reordering them is an INVALID map that
`test_geography.py`/`test_map_state.py` already prove is rejected (`route_not_canonical` /
`shape_not_canonical`), so exercising that here would test the opposite property.

Unlike sec.10.2 (which varies presentation VALUES and permits byte divergence), nothing authored
differs here at all: canonical state serialization, the API projection JSON, every resolved turn's
report, and the save's own history hashes must all be byte-identical.
"""

from __future__ import annotations

from app.api.projections import build_strategic_map
from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.history import new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState, StrategicMapState
from tests.conftest import TINY_VALID_SCENARIO_PATH
from tests.history_tamper_helpers import advance_n

_TURNS = 5


def _reordered_insertion_variant(map_state: StrategicMapState) -> StrategicMapState:
    """A variant of `map_state` whose `theaters` dict holds the exact same keys and values, built
    from a REVERSED item sequence. `routes` and `shapes` are copied through untouched -- their
    canonical tuple order is enforced, not merely conventional, so reordering them would build an
    invalid map instead of exercising this property."""
    reversed_theaters = dict(reversed(list(map_state.theaters.items())))
    return map_state.model_copy(update={"theaters": reversed_theaters})


def _baseline_and_variant() -> tuple[GameState, GameState]:
    baseline = load_scenario_file(TINY_VALID_SCENARIO_PATH)
    variant_map = _reordered_insertion_variant(baseline.world.strategic_map)
    variant = baseline.model_copy(
        update={"world": baseline.world.model_copy(update={"strategic_map": variant_map})}
    )
    return baseline, variant


def test_the_reordered_variant_has_the_same_keys_and_values_in_a_genuinely_different_order() -> (
    None
):
    """Non-vacuity check on the fixture itself: an insertion-order change that happened to leave
    the order unchanged (e.g. a single-theater map) would make every assertion below trivially
    true. `tiny_valid` has five theaters, so reversal is a real reordering."""
    baseline, variant = _baseline_and_variant()
    baseline_theaters = baseline.world.strategic_map.theaters
    variant_theaters = variant.world.strategic_map.theaters

    assert baseline_theaters == variant_theaters
    assert list(baseline_theaters) != list(variant_theaters)
    assert len(baseline_theaters) >= 2


def test_canonical_state_serialization_is_byte_identical() -> None:
    baseline_state, variant_state = _baseline_and_variant()
    assert canonical_dumps(baseline_state.model_dump(mode="json")) == canonical_dumps(
        variant_state.model_dump(mode="json")
    )


def test_api_projection_json_is_byte_identical() -> None:
    baseline_state, variant_state = _baseline_and_variant()
    baseline_projection = build_strategic_map(baseline_state)
    variant_projection = build_strategic_map(variant_state)
    assert canonical_dumps(baseline_projection.model_dump(mode="json")) == canonical_dumps(
        variant_projection.model_dump(mode="json")
    )


def test_simulation_outputs_and_save_history_hashes_are_byte_identical() -> None:
    baseline_state, variant_state = _baseline_and_variant()
    baseline_save = advance_n(
        new_game(baseline_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )
    variant_save = advance_n(
        new_game(variant_state, save_format_version=SAVE_FORMAT_VERSION), _TURNS
    )

    assert baseline_save.head_entry_hash == variant_save.head_entry_hash
    assert baseline_save.entry_count == variant_save.entry_count
    assert len(baseline_save.entries) == len(variant_save.entries) == _TURNS + 1

    for baseline_entry, variant_entry in zip(
        baseline_save.entries, variant_save.entries, strict=True
    ):
        assert baseline_entry.state_json == variant_entry.state_json
        assert baseline_entry.decisions_json == variant_entry.decisions_json
        assert baseline_entry.report_json == variant_entry.report_json
        assert baseline_entry.entry_hash == variant_entry.entry_hash
