"""T-L4 (§6.5a/b): the resource-depletion shock reaches legitimacy end to end, through the real
resolver, reproducing the plan's hand-worked `deficit_demo` figures for turns 26 and 41 exactly.
No special-cased resource-to-legitimacy formula exists anywhere -- depletion reduces
`extraction_sector_real_output`, which reduces `ProductionReport.total_gross_output`, which the
political phase (slot 10) reads as `current_total_gross_output` against the previous turn's
baseline. This test is the proof that chain actually holds at the two turns where
`test_soak.py`'s three-regime timber trajectory (2C2, T31) changes extraction-sector output.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR


def _resolve_to_turn(n: int) -> list:  # type: ignore[type-arg]
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    reports = []
    for _ in range(n):
        decisions = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        resolution = resolve_turn(state, decisions)
        reports.append(resolution.report)
        state = resolution.state
    return reports


def test_turn_26_iron_ore_depletion_shock_matches_the_hand_worked_figures_exactly() -> None:
    reports = _resolve_to_turn(26)
    turn_25, turn_26 = reports[24], reports[25]
    assert turn_25.political is not None
    assert turn_26.political is not None

    assert turn_25.political.closing_legitimacy_bps == 6_459
    political = turn_26.political
    assert political.opening_legitimacy_bps == 6_459
    assert political.output_change_bps == -1_000
    assert political.output_contribution_bps == -250
    assert political.unemployment_change_bps == 0
    assert political.unemployment_contribution_bps == 0
    assert political.performance_contribution_bps == -250
    assert political.order_support_contribution_bps == 4
    assert political.total_legitimacy_change_bps == -246
    assert political.closing_legitimacy_bps == 6_213


def test_turn_40_electoral_defeat_concludes_the_game_before_timber_steady_state() -> None:
    """Phase 3C: `deficit_demo` concludes via `ELECTORAL_DEFEAT` at turn 40 -- the same turn as
    the timber `STOCK_CONSTRAINED` boundary (`test_soak.py`, 2C2/T31) -- so the turn-41 timber
    steady-state truncation this test pinned pre-3C is no longer reachable through ordinary play;
    `resolve_turn` refuses the 41st call instead (`docs.adr` 0013). Turn 40's own closing
    legitimacy, 6,431, is unchanged from the pre-3C figure -- the trajectory is identical up to
    this point, simply observed at its new, real conclusion."""
    reports = _resolve_to_turn(40)
    turn_40 = reports[39]
    assert turn_40.political is not None
    assert turn_40.political.closing_legitimacy_bps == 6_431

    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    for _ in range(40):
        decisions = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        state = resolve_turn(state, decisions).state

    stale_decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    try:
        resolve_turn(state, stale_decisions)
        raise AssertionError("expected GameAlreadyConcludedError")
    except GameAlreadyConcludedError:
        pass
