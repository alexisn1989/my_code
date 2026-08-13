"""Phase 3B2B T3-T15: what `simulation.political_memory` guarantees, pinned as measured behaviour.

Every figure below was verified by direct simulation of the real formulas before this file was
written (the plan's R7/R12/R13 revisions), not hand-derived and hoped for. The decay table in
particular reproduces the plan's own §7.1 table exactly, including the honest, non-oversold
tail-duration claim (large deviations halve quickly; small residuals still take real turns to reach
exactly zero).
"""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.politics import (
    DECREE_BYPASS_PENALTY_BPS,
    POLICY_REACTION_CAP_BPS,
    POLICY_REACTION_WEIGHT_BPS,
    RELATIONSHIP_DECAY_DENOMINATOR,
    RELATIONSHIP_DECAY_NUMERATOR,
)
from app.simulation.legislature import ChangeDirection
from app.simulation.political_memory import (
    combine_relationship_components,
    decree_bypass_reaction_bps,
    enacted_policy_reaction_bps,
    relationship_decay_bps,
)

RELATIONSHIP_FLOOR_BPS = -10_000
RELATIONSHIP_CEILING_BPS = 10_000

relationships = st.integers(min_value=RELATIONSHIP_FLOOR_BPS, max_value=RELATIONSHIP_CEILING_BPS)
preferences = st.integers(min_value=-10_000, max_value=10_000)
intensities = st.integers(min_value=0, max_value=10_000)


# --- the constants themselves -------------------------------------------------


def test_the_calibrated_constants_are_pinned() -> None:
    assert RELATIONSHIP_DECAY_NUMERATOR == 1
    assert RELATIONSHIP_DECAY_DENOMINATOR == 8
    assert POLICY_REACTION_WEIGHT_BPS == 2_500
    assert POLICY_REACTION_CAP_BPS == 1_000
    assert DECREE_BYPASS_PENALTY_BPS == 200


# --- T3: decay from above AND below, exact mirror -----------------------------


def _run_decay(opening: int, baseline: int, turns: int) -> int:
    for _ in range(turns):
        opening += relationship_decay_bps(
            opening_relationship_bps=opening, baseline_relationship_bps=baseline
        )
    return opening


@pytest.mark.parametrize(
    ("deviation0", "t1", "t4", "t8", "t20", "t100"),
    [
        pytest.param(1, 0, 0, 0, 0, 0, id="dev-1"),
        pytest.param(10, 9, 6, 2, 0, 0, id="dev-10"),
        pytest.param(100, 88, 60, 37, 11, 0, id="dev-100"),
        pytest.param(1_000, 875, 588, 346, 72, 0, id="dev-1000"),
        pytest.param(10_000, 8_750, 5_863, 3_438, 695, 0, id="dev-10000"),
    ],
)
def test_decay_trajectory_matches_the_plans_own_table_above_baseline(
    deviation0: int, t1: int, t4: int, t8: int, t20: int, t100: int
) -> None:
    baseline = 0
    opening = baseline + deviation0
    assert _run_decay(opening, baseline, 1) - baseline == t1
    assert _run_decay(opening, baseline, 4) - baseline == t4
    assert _run_decay(opening, baseline, 8) - baseline == t8
    assert _run_decay(opening, baseline, 20) - baseline == t20
    assert _run_decay(opening, baseline, 100) - baseline == t100


@pytest.mark.parametrize(
    ("deviation0", "t1", "t4", "t8", "t20", "t100"),
    [
        pytest.param(1, 0, 0, 0, 0, 0, id="dev-neg-1"),
        pytest.param(10, 9, 6, 2, 0, 0, id="dev-neg-10"),
        pytest.param(100, 88, 60, 37, 11, 0, id="dev-neg-100"),
        pytest.param(1_000, 875, 588, 346, 72, 0, id="dev-neg-1000"),
        pytest.param(10_000, 8_750, 5_863, 3_438, 695, 0, id="dev-neg-10000"),
    ],
)
def test_decay_trajectory_is_the_exact_mirror_below_baseline(
    deviation0: int, t1: int, t4: int, t8: int, t20: int, t100: int
) -> None:
    baseline = 0
    opening = baseline - deviation0
    assert baseline - _run_decay(opening, baseline, 1) == t1
    assert baseline - _run_decay(opening, baseline, 4) == t4
    assert baseline - _run_decay(opening, baseline, 8) == t8
    assert baseline - _run_decay(opening, baseline, 20) == t20
    assert baseline - _run_decay(opening, baseline, 100) == t100


def test_decay_is_zero_exactly_at_baseline() -> None:
    assert (
        relationship_decay_bps(opening_relationship_bps=1_234, baseline_relationship_bps=1_234) == 0
    )


# --- T4: no overshoot, any starting point -------------------------------------


@given(opening=relationships, baseline=relationships)
def test_decay_never_overshoots_the_baseline(opening: int, baseline: int) -> None:
    decay = relationship_decay_bps(
        opening_relationship_bps=opening, baseline_relationship_bps=baseline
    )
    closing = opening + decay
    deviation_before = abs(opening - baseline)
    deviation_after = abs(closing - baseline)
    assert deviation_after <= deviation_before
    # never crosses past the baseline to the other side
    if opening >= baseline:
        assert closing >= baseline
    else:
        assert closing <= baseline


@given(opening=relationships, baseline=relationships)
def test_decay_is_exactly_symmetric(opening: int, baseline: int) -> None:
    """`f(baseline + d) - baseline == -(f(baseline - d) - baseline)` for every deviation d."""
    deviation = opening - baseline
    mirrored_opening = baseline - deviation
    forward = relationship_decay_bps(
        opening_relationship_bps=opening, baseline_relationship_bps=baseline
    )
    backward = relationship_decay_bps(
        opening_relationship_bps=mirrored_opening, baseline_relationship_bps=baseline
    )
    assert forward == -backward


# --- T5: small residuals terminate, every deviation in [1, 10000] ------------


@pytest.mark.parametrize(
    "deviation0", [1, 2, 3, 7, 8, 9, 15, 16, 17, 63, 64, 65, 500, 4_999, 9_999]
)
def test_every_deviation_reaches_exactly_baseline(deviation0: int) -> None:
    baseline = 0
    opening = baseline + deviation0
    for _ in range(200):
        if opening == baseline:
            break
        opening += relationship_decay_bps(
            opening_relationship_bps=opening, baseline_relationship_bps=baseline
        )
    assert opening == baseline


def test_the_maximum_deviation_takes_exactly_65_turns() -> None:
    """The widest deviation the relationship scale can express (10,000, e.g. a bloc starting at
    its authored baseline's opposite pole) reaches the baseline exactly at turn 65 -- not the
    20,000-wide separation between the two poles themselves, which is not a deviation any single
    bloc's baseline-vs-current pair can have (both fields share the same [-10,000, 10,000] scale,
    so the largest possible |opening - baseline| is 10,000)."""
    baseline = -10_000
    opening = 0
    turns = 0
    while opening != baseline:
        opening += relationship_decay_bps(
            opening_relationship_bps=opening, baseline_relationship_bps=baseline
        )
        turns += 1
        assert turns <= 65
    assert turns == 65


# --- T6/T7: policy reaction signs and positive/negative symmetry -------------


def test_a_liked_increase_is_positive_and_a_disliked_increase_is_negative() -> None:
    liked = enacted_policy_reaction_bps(
        tax_preference_bps=2_000,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=5_000,
        spending_preference_bps=0,
        spending_direction=ChangeDirection.UNCHANGED,
        spending_intensity_bps=0,
    )
    disliked = enacted_policy_reaction_bps(
        tax_preference_bps=-6_000,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=5_000,
        spending_preference_bps=0,
        spending_direction=ChangeDirection.UNCHANGED,
        spending_intensity_bps=0,
    )
    assert liked > 0
    assert disliked < 0


def test_unchanged_on_both_axes_is_always_exactly_zero() -> None:
    for tax_pref, spend_pref in itertools.product((-10_000, -1, 0, 1, 10_000), repeat=2):
        assert (
            enacted_policy_reaction_bps(
                tax_preference_bps=tax_pref,
                tax_direction=ChangeDirection.UNCHANGED,
                tax_intensity_bps=0,
                spending_preference_bps=spend_pref,
                spending_direction=ChangeDirection.UNCHANGED,
                spending_intensity_bps=0,
            )
            == 0
        )


@given(tax_pref=preferences, spend_pref=preferences, intensity=intensities)
def test_reaction_is_exactly_sign_symmetric(tax_pref: int, spend_pref: int, intensity: int) -> None:
    increase = enacted_policy_reaction_bps(
        tax_preference_bps=tax_pref,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=intensity,
        spending_preference_bps=spend_pref,
        spending_direction=ChangeDirection.INCREASE,
        spending_intensity_bps=intensity,
    )
    decrease = enacted_policy_reaction_bps(
        tax_preference_bps=tax_pref,
        tax_direction=ChangeDirection.DECREASE,
        tax_intensity_bps=intensity,
        spending_preference_bps=spend_pref,
        spending_direction=ChangeDirection.DECREASE,
        spending_intensity_bps=intensity,
    )
    assert increase == -decrease


# --- T8: the per-turn cap, real values never approach it ----------------------


@given(tax_pref=preferences, spend_pref=preferences, intensity=intensities)
def test_reaction_never_exceeds_the_cap(tax_pref: int, spend_pref: int, intensity: int) -> None:
    reaction = enacted_policy_reaction_bps(
        tax_preference_bps=tax_pref,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=intensity,
        spending_preference_bps=spend_pref,
        spending_direction=ChangeDirection.INCREASE,
        spending_intensity_bps=intensity,
    )
    assert -POLICY_REACTION_CAP_BPS <= reaction <= POLICY_REACTION_CAP_BPS


@pytest.mark.parametrize(
    ("tax_pref", "expected"),
    [
        pytest.param(-6_000, -150, id="hardliner-like-preference"),
        pytest.param(-2_000, -50, id="moderate-like-preference"),
        pytest.param(2_000, 50, id="mild-positive-preference"),
        pytest.param(3_000, 75, id="core-like-preference"),
        pytest.param(5_000, 125, id="strongly-positive-preference"),
    ],
)
def test_the_cap_never_binds_on_real_calibration_magnitudes(tax_pref: int, expected: int) -> None:
    """A genuine +500bps rise (intensity 5,000) against every authored preference magnitude in the
    three real scenarios never approaches ±1,000 -- confirmed directly rather than trusted."""
    reaction = enacted_policy_reaction_bps(
        tax_preference_bps=tax_pref,
        tax_direction=ChangeDirection.INCREASE,
        tax_intensity_bps=5_000,
        spending_preference_bps=0,
        spending_direction=ChangeDirection.UNCHANGED,
        spending_intensity_bps=0,
    )
    assert reaction == expected
    assert abs(reaction) < POLICY_REACTION_CAP_BPS


# --- T9/T10: decree bypass, separate from policy, seat-gated ------------------


def test_decree_bypass_is_flat_and_seat_gated() -> None:
    assert decree_bypass_reaction_bps(is_seated_bloc=True) == -DECREE_BYPASS_PENALTY_BPS
    assert decree_bypass_reaction_bps(is_seated_bloc=False) == 0


# --- T14: order independence of the four-component sum -----------------------


@given(
    opening=relationships,
    decay=st.integers(min_value=-1_000, max_value=1_000),
    investment=st.integers(min_value=0, max_value=2_000),
    policy=st.integers(min_value=-POLICY_REACTION_CAP_BPS, max_value=POLICY_REACTION_CAP_BPS),
    decree=st.sampled_from([0, -DECREE_BYPASS_PENALTY_BPS]),
)
def test_combining_is_order_independent(
    opening: int, decay: int, investment: int, policy: int, decree: int
) -> None:
    """All 24 permutations of the four components produce an identical closing value, because the
    combiner sums plain integers (commutative) and clamps exactly once."""
    components = [decay, investment, policy, decree]
    results = set()
    for permutation in itertools.permutations(components):
        uncapped, applied, closing = combine_relationship_components(
            opening_relationship_bps=opening,
            decay_component_bps=permutation[0],
            investment_component_bps=permutation[1],
            policy_reaction_component_bps=permutation[2],
            decree_bypass_component_bps=permutation[3],
        )
        results.add((uncapped, applied, closing))
    assert len(results) == 1


# --- T15: boundary handling, uncapped vs applied differ exactly at the clamp --


def test_boundary_truncation_is_visible_not_absorbed() -> None:
    uncapped, applied, closing = combine_relationship_components(
        opening_relationship_bps=9_900,
        decay_component_bps=0,
        investment_component_bps=500,
        policy_reaction_component_bps=0,
        decree_bypass_component_bps=0,
    )
    assert uncapped == 500
    assert closing == 10_000
    assert applied == 100
    assert applied != uncapped


def test_no_boundary_truncation_when_the_sum_stays_in_range() -> None:
    uncapped, applied, closing = combine_relationship_components(
        opening_relationship_bps=0,
        decay_component_bps=-10,
        investment_component_bps=50,
        policy_reaction_component_bps=-5,
        decree_bypass_component_bps=0,
    )
    assert uncapped == 35
    assert applied == 35
    assert closing == 35


@given(
    opening=relationships,
    decay=st.integers(min_value=-2_000, max_value=2_000),
    investment=st.integers(min_value=0, max_value=2_000),
    policy=st.integers(min_value=-POLICY_REACTION_CAP_BPS, max_value=POLICY_REACTION_CAP_BPS),
    decree=st.sampled_from([0, -DECREE_BYPASS_PENALTY_BPS]),
)
def test_applied_equals_uncapped_unless_the_clamp_bound(
    opening: int, decay: int, investment: int, policy: int, decree: int
) -> None:
    uncapped, applied, closing = combine_relationship_components(
        opening_relationship_bps=opening,
        decay_component_bps=decay,
        investment_component_bps=investment,
        policy_reaction_component_bps=policy,
        decree_bypass_component_bps=decree,
    )
    assert closing == max(-10_000, min(10_000, opening + uncapped))
    if -10_000 <= opening + uncapped <= 10_000:
        assert applied == uncapped
    else:
        assert applied != uncapped


# --- controlled decay + 100-capital investment fixed point: +4,856 -----------


def test_controlled_decay_plus_investment_fixed_point_is_4856() -> None:
    """The plan's own headline calibration figure, reproduced here in isolation (decay + a fixed
    +857 investment component at the fixed point, no policy, no decree): the trajectory starting
    at baseline -2,000, investing 100/turn, reaches and holds exactly +4,856."""
    from app.simulation.relationships import relationship_gain_bps

    baseline = -2_000
    opening = baseline
    for _ in range(60):
        decay = relationship_decay_bps(
            opening_relationship_bps=opening, baseline_relationship_bps=baseline
        )
        investment = relationship_gain_bps(opening_relationship_bps=opening, political_capital=100)
        _uncapped, _applied, closing = combine_relationship_components(
            opening_relationship_bps=opening,
            decay_component_bps=decay,
            investment_component_bps=investment,
            policy_reaction_component_bps=0,
            decree_bypass_component_bps=0,
        )
        opening = closing
    assert opening == 4_856
