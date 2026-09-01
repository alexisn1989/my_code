"""Tests for `reconcile_strategic_map_staticness` (group 53, Strategic Military Map Gate M0
commit 5) -- the core comparison behaviour and its four exact problem strings, plus the
`history.py` wiring. The rehashed tamper matrix lives in `test_map_tamper_matrix.py`.
"""

from __future__ import annotations

from app.simulation.history import new_game, validate_history
from app.simulation.reconciliation import reconcile_strategic_map_staticness
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import make_game_state
from tests.history_tamper_helpers import advance_n


class TestCleanCampaign:
    def test_a_clean_campaign_produces_no_group_53_problems(self) -> None:
        state = make_game_state()
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        save = advance_n(save, 5)
        problems = validate_history(save)
        assert not any("strategic map" in p for p in problems)

    def test_resolve_turn_leaves_the_map_byte_identical_across_five_turns(self) -> None:
        state = make_game_state()
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        save = advance_n(save, 5)
        maps = [entry.state().world.strategic_map for entry in save.entries]
        first = maps[0]
        for later in maps[1:]:
            assert later == first

    def test_identical_opening_and_closing_state_produces_no_problems(self) -> None:
        state = make_game_state()
        assert reconcile_strategic_map_staticness(opening_state=state, closing_state=state) == []


class TestExactProblemStrings:
    """Each string is asserted verbatim -- these are the strings the frozen plan sec.8.2 fixes
    as the exact wording, not paraphrases."""

    def test_map_id_mismatch_emits_the_map_id_string(self) -> None:
        opening = make_game_state()
        closing_map = opening.world.strategic_map.model_copy(update={"map_id": "a_different_map"})
        closing = opening.model_copy(
            update={"world": opening.world.model_copy(update={"strategic_map": closing_map})}
        )
        problems = reconcile_strategic_map_staticness(opening_state=opening, closing_state=closing)
        assert problems == [
            "strategic map changed during turn resolution: opening map_id "
            f"{opening.world.strategic_map.map_id!r} != closing map_id 'a_different_map'"
        ]

    def test_any_other_byte_difference_emits_the_canonical_bytes_string(self) -> None:
        opening = make_game_state()
        old_map = opening.world.strategic_map
        capital = old_map.theaters[old_map.capital_theater_id]
        moved = capital.model_copy(
            update={"presentation": capital.presentation.model_copy(update={"centroid_x": 1})}
        )
        new_theaters = dict(old_map.theaters)
        new_theaters[old_map.capital_theater_id] = moved
        closing_map = old_map.model_copy(update={"theaters": new_theaters})
        closing = opening.model_copy(
            update={"world": opening.world.model_copy(update={"strategic_map": closing_map})}
        )
        problems = reconcile_strategic_map_staticness(opening_state=opening, closing_state=closing)
        assert problems == [
            "strategic map changed during turn resolution: canonical map bytes differ (the "
            "strategic map is authored, immutable content and no phase may write it)"
        ]

    def test_missing_closing_map_emits_the_closing_missing_string(self) -> None:
        opening = make_game_state()
        closing = opening.model_copy(
            update={"world": opening.world.model_copy(update={"strategic_map": None})}
        )
        problems = reconcile_strategic_map_staticness(opening_state=opening, closing_state=closing)
        assert problems == [
            "strategic map missing from the closing state (the field is required; a state "
            "that reached reconciliation without one is malformed)"
        ]

    def test_missing_opening_map_emits_the_opening_missing_string(self) -> None:
        state = make_game_state()
        opening = state.model_copy(
            update={"world": state.world.model_copy(update={"strategic_map": None})}
        )
        closing = state
        problems = reconcile_strategic_map_staticness(opening_state=opening, closing_state=closing)
        assert problems == [
            "strategic map missing from the opening state (the field is required; a state "
            "that reached reconciliation without one is malformed)"
        ]

    def test_missing_closing_is_checked_before_missing_opening(self) -> None:
        """When BOTH are missing, only the closing-side string fires -- matching the frozen
        plan's stated order ("the first fires when map_id differs... the last two are the
        unreachable-but-guarded cases", listed closing before opening)."""
        state = make_game_state()
        both_missing_world = state.world.model_copy(update={"strategic_map": None})
        both_missing_state = state.model_copy(update={"world": both_missing_world})
        problems = reconcile_strategic_map_staticness(
            opening_state=both_missing_state, closing_state=both_missing_state
        )
        assert problems == [
            "strategic map missing from the closing state (the field is required; a state "
            "that reached reconciliation without one is malformed)"
        ]


class TestNeverRaises:
    def test_reconciler_returns_problems_rather_than_raising_on_a_bypassed_none(self) -> None:
        state = make_game_state()
        bypassed = state.model_copy(
            update={"world": state.world.model_copy(update={"strategic_map": None})}
        )
        # Must not raise -- this call itself is the assertion.
        problems = reconcile_strategic_map_staticness(
            opening_state=bypassed, closing_state=bypassed
        )
        assert problems
