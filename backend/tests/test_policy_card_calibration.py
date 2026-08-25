"""Gate 4A3A (R7/R8): the generic policy-card presets, pinned against real
scenario content.

`policy_card_calibration.py`'s constants are a presentation-layer choice, not
a simulation rule -- but a presentation choice can still be silently broken by
a future change to either constant or to a scenario's authored spending plan.
Pinning the exact measured numbers here (not just "step > 0") is what catches
that: if `SPENDING_STEP_DENOMINATOR` or a scenario's `welfare` amount ever
changes, this test fails with the stale number rather than staying green on a
now-wrong catalog.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.policy_card_calibration import (
    SPENDING_STEP_DENOMINATOR,
    SPENDING_STEP_NUMERATOR,
    TAX_STEP_BPS,
    spending_step,
)
from app.content.scenarios import load_scenario_file
from app.simulation.state import SpendingCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

#: category -> (current amount, exact step). Measured directly from each
#: scenario's authored `spending_plan` and pinned as of Gate 4A3A (plan §5).
#: `tiny_valid` and `decree_state` share identical finance content.
_TINY_VALID_AND_DECREE_STATE = {
    "health": (200_000_000, 20_000_000),
    "education": (150_000_000, 15_000_000),
    "welfare": (250_000_000, 25_000_000),
    "infrastructure": (120_000_000, 12_000_000),
    "defense": (180_000_000, 18_000_000),
    "security": (90_000_000, 9_000_000),
    "administration": (60_000_000, 6_000_000),
}
_TINY_VALID_AND_DECREE_STATE_TOTAL = 1_050_000_000

_DEFICIT_DEMO = {
    "health": (150_000_000, 15_000_000),
    "education": (100_000_000, 10_000_000),
    "welfare": (150_000_000, 15_000_000),
    "infrastructure": (80_000_000, 8_000_000),
    "defense": (100_000_000, 10_000_000),
    "security": (50_000_000, 5_000_000),
    "administration": (40_000_000, 4_000_000),
}
_DEFICIT_DEMO_TOTAL = 670_000_000

#: category -> the step's share of TOTAL program spending, in bps, floored --
#: NOT the category's own share of the total (an earlier plan draft conflated
#: the two; see policy_card_calibration.py's docstring). Measured range across
#: every row of both tables: 57-238 bps, i.e. 0.57%-2.38%.
_TINY_VALID_AND_DECREE_STATE_STEP_SHARE_BPS = {
    "health": 190,
    "education": 142,
    "welfare": 238,
    "infrastructure": 114,
    "defense": 171,
    "security": 85,
    "administration": 57,
}
_DEFICIT_DEMO_STEP_SHARE_BPS = {
    "health": 223,
    "education": 149,
    "welfare": 223,
    "infrastructure": 119,
    "defense": 149,
    "security": 74,
    "administration": 59,
}


def _spending_plan(scenario_filename: str) -> dict[str, int]:
    state = load_scenario_file(SCENARIO_DIR / scenario_filename)
    player = state.world.countries[state.world.player_country_id]
    assert player.finance is not None
    plan = player.finance.spending_plan
    return {category.value: plan.get(category) for category in SpendingCategory}


@pytest.mark.parametrize(
    ("scenario_filename", "expected", "expected_total"),
    [
        ("tiny_valid.yaml", _TINY_VALID_AND_DECREE_STATE, _TINY_VALID_AND_DECREE_STATE_TOTAL),
        ("decree_state.yaml", _TINY_VALID_AND_DECREE_STATE, _TINY_VALID_AND_DECREE_STATE_TOTAL),
        ("deficit_demo.yaml", _DEFICIT_DEMO, _DEFICIT_DEMO_TOTAL),
    ],
)
def test_spending_step_matches_pinned_values_for_every_category(
    scenario_filename: str, expected: dict[str, tuple[int, int]], expected_total: int
) -> None:
    plan = _spending_plan(scenario_filename)
    assert sum(plan.values()) == expected_total

    for category, (expected_current, expected_step) in expected.items():
        current = plan[category]
        assert current == expected_current, f"{scenario_filename}/{category}: current drifted"
        assert spending_step(current) == expected_step, f"{scenario_filename}/{category}"


@pytest.mark.parametrize(
    ("scenario_filename", "expected_shares", "total"),
    [
        (
            "tiny_valid.yaml",
            _TINY_VALID_AND_DECREE_STATE_STEP_SHARE_BPS,
            _TINY_VALID_AND_DECREE_STATE_TOTAL,
        ),
        (
            "decree_state.yaml",
            _TINY_VALID_AND_DECREE_STATE_STEP_SHARE_BPS,
            _TINY_VALID_AND_DECREE_STATE_TOTAL,
        ),
        ("deficit_demo.yaml", _DEFICIT_DEMO_STEP_SHARE_BPS, _DEFICIT_DEMO_TOTAL),
    ],
)
def test_step_share_of_total_spending_matches_pinned_bps(
    scenario_filename: str, expected_shares: dict[str, int], total: int
) -> None:
    """The step is 0.57%-2.38% of TOTAL program spending in every category of
    every scenario -- a real budgetary choice, never a no-op, never a shock."""
    plan = _spending_plan(scenario_filename)

    for category, expected_bps in expected_shares.items():
        step = spending_step(plan[category])
        assert step * 10_000 // total == expected_bps, f"{scenario_filename}/{category}"
        assert 57 <= expected_bps <= 238


def test_every_shipped_category_has_a_nonzero_step_and_never_targets_a_no_op() -> None:
    for scenario_filename in ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"):
        plan = _spending_plan(scenario_filename)
        for category, current in plan.items():
            step = spending_step(current)
            assert step > 0, f"{scenario_filename}/{category}: step must be nonzero"
            assert current + step != current, f"{scenario_filename}/{category}: increase is a no-op"
            assert current - step != current, f"{scenario_filename}/{category}: decrease is a no-op"
            # A decrease step never goes negative for any shipped category.
            assert current - step >= 0


def test_spending_step_formula_is_ten_percent_integer_floor() -> None:
    assert (SPENDING_STEP_NUMERATOR, SPENDING_STEP_DENOMINATOR) == (1, 10)
    assert spending_step(100) == 10
    assert spending_step(109) == 10  # integer floor, never rounds up
    assert spending_step(9) == 0  # below the floor's resolution: no baseline to scale
    assert spending_step(0) == 0


def test_tax_step_matches_the_engines_own_calibration_test_step() -> None:
    """`TAX_STEP_BPS` is not a new number: it is the exact +5.00pp step
    `tests/test_scenario_legislature_calibration.py`'s `_tax_rise_5pp` already
    exercises, reused rather than authored fresh."""
    assert TAX_STEP_BPS == 500


@pytest.mark.parametrize(
    ("rate_bps", "expect_increase_in_bounds", "expect_decrease_in_bounds"),
    [
        (0, True, False),  # decreasing from 0 would leave [0, 10_000]
        (10_000, False, True),  # increasing from 100% would leave [0, 10_000]
        (2_000, True, True),
        (300, True, False),  # 300 - 500 < 0
        (9_600, False, True),  # 9,600 + 500 > 10,000
    ],
)
def test_tax_step_bounds_checking_matches_the_strict_bps_range(
    rate_bps: int, expect_increase_in_bounds: bool, expect_decrease_in_bounds: bool
) -> None:
    """A card generator must disable a direction whose step would leave
    `[0, 10_000]` -- this pins the exact boundary arithmetic it must use."""
    assert (0 <= rate_bps + TAX_STEP_BPS <= 10_000) is expect_increase_in_bounds
    assert (0 <= rate_bps - TAX_STEP_BPS <= 10_000) is expect_decrease_in_bounds
