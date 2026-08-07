"""End-to-end tests for the economic-baseline lifecycle through the real resolver (Phase 3A,
T-B1..T-B4, §6.4). Complements `test_political_report.py` (which corrupts a report's baseline
fields in isolation) by proving the REAL resolver produces a coherent lifecycle across many
consecutive turns, with no corruption involved.
"""

from __future__ import annotations

from app.simulation.decisions import DecisionSet
from app.simulation.resolver import resolve_turn
from tests.conftest import make_game_state


def _empty_decisions_for(state) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=[]
    )


def _resolve_n(n: int):  # type: ignore[no-untyped-def]
    """Resolve `n` consecutive turns from a fresh state; return the list of `TurnResolution`s
    in order."""
    state = make_game_state(turn=0, state_version=0)
    resolutions = []
    for _ in range(n):
        resolution = resolve_turn(state, _empty_decisions_for(state))
        resolutions.append(resolution)
        state = resolution.state
    return resolutions


# --- T-B1: first turn -- None baseline, exactly zero performance -------------


def test_first_turn_has_no_opening_baseline_and_zero_performance() -> None:
    resolution = _resolve_n(1)[0]
    political = resolution.report.political
    assert political is not None
    assert political.opening_economic_baseline is None
    assert political.output_change_bps == 0
    assert political.output_contribution_bps == 0
    assert political.unemployment_change_bps == 0
    assert political.unemployment_contribution_bps == 0
    assert political.performance_contribution_bps == 0


# --- T-B2: closing baseline equals this turn's observations ------------------


def test_closing_baseline_matches_this_turns_observations_every_turn() -> None:
    for resolution in _resolve_n(8):
        political = resolution.report.political
        assert political is not None
        assert political.closing_economic_baseline.total_gross_output == (
            political.current_total_gross_output
        )
        assert political.closing_economic_baseline.unemployment_rate_bps == (
            political.current_unemployment_rate_bps
        )
        assert (
            political.closing_economic_baseline.source_turn == resolution.report.resolved_turn + 1
        )


# --- T-B3: opening baseline equals the previous turn's closing ---------------


def test_opening_baseline_equals_previous_turns_closing_across_eight_turns() -> None:
    resolutions = _resolve_n(8)
    for previous, current in zip(resolutions, resolutions[1:], strict=False):
        previous_closing = previous.report.political.closing_economic_baseline
        current_opening = current.report.political.opening_economic_baseline
        assert current_opening is not None
        assert current_opening == previous_closing


# --- T-B4: the baseline round-trips through state -----------------------------


def test_resolved_baseline_matches_the_reports_closing_baseline_every_turn() -> None:
    for resolution in _resolve_n(8):
        player = resolution.state.world.countries[resolution.state.world.player_country_id]
        assert player.politics is not None
        assert player.politics.economic_baseline is not None
        political = resolution.report.political
        assert political is not None
        assert player.politics.economic_baseline.source_turn == (
            political.closing_economic_baseline.source_turn
        )
        assert player.politics.economic_baseline.total_gross_output == (
            political.closing_economic_baseline.total_gross_output
        )
        assert player.politics.economic_baseline.unemployment_rate_bps == (
            political.closing_economic_baseline.unemployment_rate_bps
        )


def test_baseline_lifecycle_holds_across_a_hundred_turns() -> None:
    """A longer-horizon stress version of T-B2/T-B3/T-B4 combined -- every turn's closing
    baseline becomes exactly the next turn's opening baseline, with no drift or corruption
    accumulating over a long run."""
    resolutions = _resolve_n(100)
    for previous, current in zip(resolutions, resolutions[1:], strict=False):
        assert current.report.political.opening_economic_baseline == (
            previous.report.political.closing_economic_baseline
        )
