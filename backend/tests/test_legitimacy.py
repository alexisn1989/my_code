"""Tests for `simulation.legitimacy`'s formulas (Phase 3A, T-L2..T-L8).

Every figure asserted here is one of the plan's hand-worked calibration values, so this file is
also the regression pin for the numbers quoted in ADR 0009 and `docs/economy_methodology.md`.
Government-form neutrality is proven separately, in `test_legitimacy_neutrality.py`.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.politics import LEGITIMACY_MAX_BPS, LEGITIMACY_MIN_BPS
from app.simulation.legitimacy import (
    MAX_PERFORMANCE_CONTRIBUTION_BPS,
    MAX_SECURITY_CONTRIBUTION_BPS,
    MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
    PerformanceSignals,
    aggregate_security_contribution_bps,
    assess_economic_performance,
    foreign_conflict_security_anxiety_bps,
    order_support_contribution_bps,
    resolve_legitimacy,
)


def _signals(
    baseline_output: int,
    current_output: int,
    baseline_unemployment: int = 1_000,
    current_unemployment: int = 1_000,
) -> PerformanceSignals:
    return PerformanceSignals(
        baseline_total_gross_output=baseline_output,
        current_total_gross_output=current_output,
        baseline_unemployment_rate_bps=baseline_unemployment,
        current_unemployment_rate_bps=current_unemployment,
    )


# --- T-L2: positive / negative / zero performance ----------------------------


def test_deficit_demo_turn_26_resource_depletion_shock_exactly() -> None:
    """The plan's headline figure: iron-ore depletion drops output 4.0e9 -> 3.6e9, exactly -10%."""
    assessment = assess_economic_performance(_signals(4_000_000_000, 3_600_000_000))
    assert assessment.output_change_bps == -1_000
    assert assessment.output_contribution_bps == -250
    assert assessment.unemployment_change_bps == 0
    assert assessment.unemployment_contribution_bps == 0
    assert assessment.performance_contribution_bps == -250


def test_deficit_demo_turn_41_is_the_signed_truncation_boundary() -> None:
    """3.6e9 -> 3.55e9 is -138.888...%, which must truncate toward zero to -138, not floor to
    -139 — the case that motivated `trunc_div_toward_zero`."""
    assessment = assess_economic_performance(_signals(3_600_000_000, 3_550_000_000))
    assert assessment.output_change_bps == -138
    assert assessment.output_contribution_bps == -34
    assert assessment.performance_contribution_bps == -34


def test_flat_economy_contributes_exactly_zero() -> None:
    """`tiny_valid`'s every turn: output and unemployment both constant."""
    assessment = assess_economic_performance(_signals(20_000_000_000, 20_000_000_000))
    assert assessment.output_change_bps == 0
    assert assessment.performance_contribution_bps == 0


def test_output_growth_contributes_positively() -> None:
    assessment = assess_economic_performance(_signals(4_000_000_000, 4_400_000_000))
    assert assessment.output_change_bps == 1_000
    assert assessment.performance_contribution_bps == 250


def test_gains_and_losses_of_equal_magnitude_are_exactly_symmetric() -> None:
    """No pessimism bias: a +10% gain and a -10% loss move legitimacy by equal opposite amounts."""
    gain = assess_economic_performance(_signals(4_000_000_000, 4_400_000_000))
    loss = assess_economic_performance(_signals(4_000_000_000, 3_600_000_000))
    assert gain.performance_contribution_bps == -loss.performance_contribution_bps


# --- T-L3: unemployment effects ----------------------------------------------


def test_rising_unemployment_reduces_legitimacy() -> None:
    """10% -> 14% unemployment, output flat."""
    assessment = assess_economic_performance(_signals(20_000_000_000, 20_000_000_000, 1_000, 1_400))
    assert assessment.unemployment_change_bps == 400
    assert assessment.unemployment_contribution_bps == -200
    assert assessment.performance_contribution_bps == -200


def test_falling_unemployment_raises_legitimacy() -> None:
    assessment = assess_economic_performance(_signals(20_000_000_000, 20_000_000_000, 1_400, 1_000))
    assert assessment.unemployment_change_bps == -400
    assert assessment.unemployment_contribution_bps == 200


def test_flat_unemployment_contributes_nothing() -> None:
    assessment = assess_economic_performance(_signals(20_000_000_000, 20_000_000_000, 1_000, 1_000))
    assert assessment.unemployment_change_bps == 0
    assert assessment.unemployment_contribution_bps == 0


def test_output_and_unemployment_contributions_combine_additively() -> None:
    assessment = assess_economic_performance(_signals(4_000_000_000, 3_600_000_000, 1_000, 1_200))
    assert assessment.output_contribution_bps == -250
    assert assessment.unemployment_contribution_bps == -100
    # -350 raw, capped to the +/-300 performance bound.
    assert assessment.performance_contribution_bps == -MAX_PERFORMANCE_CONTRIBUTION_BPS


# --- T-L1 (unit half): first turn --------------------------------------------


def test_absent_baseline_produces_an_all_zero_assessment() -> None:
    """First turn: there is no prior turn, so there is no performance to assess."""
    assessment = assess_economic_performance(None)
    assert assessment.output_change_bps == 0
    assert assessment.output_contribution_bps == 0
    assert assessment.unemployment_change_bps == 0
    assert assessment.unemployment_contribution_bps == 0
    assert assessment.performance_contribution_bps == 0


# --- T-L7: a zero baseline is not the same as an absent one ------------------


def test_zero_output_baseline_yields_zero_change_without_raising() -> None:
    assessment = assess_economic_performance(_signals(0, 5_000_000))
    assert assessment.output_change_bps == 0
    assert assessment.performance_contribution_bps == 0


def test_zero_output_baseline_is_distinct_from_an_absent_baseline() -> None:
    """Both give a zero output contribution, but for different reasons, and a genuine zero-output
    economy still reports its unemployment change — an absent baseline reports nothing at all."""
    zero_baseline = assess_economic_performance(_signals(0, 5_000_000, 1_000, 1_400))
    absent_baseline = assess_economic_performance(None)
    assert zero_baseline.unemployment_change_bps == 400
    assert zero_baseline.performance_contribution_bps == -200
    assert absent_baseline.unemployment_change_bps == 0
    assert absent_baseline.performance_contribution_bps == 0


# --- T-M7 (R5): capped contribution alongside its uncapped intermediate ------


def test_a_tripled_baseline_produces_an_uncapped_intermediate_and_a_capped_final() -> None:
    """Baseline 1 -> current 3 is +20,000 bps raw -- unbounded and larger than the legitimacy
    scale itself -- but the published `performance_contribution_bps` is still capped to +/-300.
    Both values are published: the uncapped intermediate is not hidden once capping applies."""
    assessment = assess_economic_performance(_signals(1, 3))
    assert assessment.output_change_bps == 20_000
    assert assessment.output_contribution_bps == 5_000  # uncapped: 20,000 * 2,500 / 10,000
    assert assessment.performance_contribution_bps == MAX_PERFORMANCE_CONTRIBUTION_BPS


def test_a_millionfold_rebound_is_unbounded_before_the_cap() -> None:
    assessment = assess_economic_performance(_signals(1, 1_000_000))
    assert assessment.output_change_bps == 9_999_990_000
    assert assessment.performance_contribution_bps == MAX_PERFORMANCE_CONTRIBUTION_BPS


def test_complete_collapse_is_exactly_negative_10000_output_change_bps() -> None:
    assessment = assess_economic_performance(_signals(5_000_000, 0))
    assert assessment.output_change_bps == -10_000
    assert assessment.performance_contribution_bps == -MAX_PERFORMANCE_CONTRIBUTION_BPS


# --- T-L5: per-turn caps ------------------------------------------------------


def test_extreme_collapse_is_capped_at_the_performance_bound() -> None:
    assessment = assess_economic_performance(_signals(10_000_000_000, 1))
    assert assessment.performance_contribution_bps == -MAX_PERFORMANCE_CONTRIBUTION_BPS


def test_extreme_growth_is_capped_at_the_performance_bound() -> None:
    assessment = assess_economic_performance(_signals(1, 10_000_000_000))
    assert assessment.performance_contribution_bps == MAX_PERFORMANCE_CONTRIBUTION_BPS


def test_combined_change_is_capped_at_the_total_bound() -> None:
    """Drift and performance both pulling the same way still cannot exceed +/-500 in one turn."""
    applied, closing = resolve_legitimacy(
        opening_bps=5_000,
        order_support_contribution=400,
        performance_contribution=300,
        security_contribution=0,
    )
    assert applied == MAX_TOTAL_LEGITIMACY_CHANGE_BPS
    assert closing == 5_500


# --- T-L6: scale bounds -------------------------------------------------------


def test_upper_bound_reports_the_applied_change_not_the_requested_one() -> None:
    applied, closing = resolve_legitimacy(
        opening_bps=9_950,
        order_support_contribution=5,
        performance_contribution=300,
        security_contribution=0,
    )
    assert closing == LEGITIMACY_MAX_BPS
    assert applied == 50  # not the requested +305


def test_lower_bound_reports_the_applied_change_not_the_requested_one() -> None:
    applied, closing = resolve_legitimacy(
        opening_bps=30,
        order_support_contribution=-5,
        performance_contribution=-300,
        security_contribution=0,
    )
    assert closing == LEGITIMACY_MIN_BPS
    assert applied == -30  # not the requested -305


def test_applied_change_always_equals_closing_minus_opening() -> None:
    for opening in (0, 1, 5_000, 9_999, 10_000):
        applied, closing = resolve_legitimacy(
            opening_bps=opening,
            order_support_contribution=250,
            performance_contribution=-100,
            security_contribution=0,
        )
        assert applied == closing - opening


# --- order-support drift ------------------------------------------------------


def test_drift_closes_ten_percent_of_the_gap_upward() -> None:
    assert order_support_contribution_bps(support_bps=8_000, opening_legitimacy_bps=7_000) == 100


def test_drift_closes_ten_percent_of_the_gap_downward() -> None:
    """Bidirectional: a government more accepted than its order's support drifts back toward it."""
    assert order_support_contribution_bps(support_bps=6_000, opening_legitimacy_bps=8_000) == -200


def test_drift_is_zero_when_legitimacy_already_matches_support() -> None:
    assert order_support_contribution_bps(support_bps=7_500, opening_legitimacy_bps=7_500) == 0


def test_drift_never_overshoots_its_target() -> None:
    """Repeated drift approaches support asymptotically and never crosses it."""
    legitimacy, support = 7_000, 8_000
    for _ in range(500):
        drift = order_support_contribution_bps(
            support_bps=support, opening_legitimacy_bps=legitimacy
        )
        _, legitimacy = resolve_legitimacy(
            opening_bps=legitimacy,
            order_support_contribution=drift,
            performance_contribution=0,
            security_contribution=0,
        )
        assert legitimacy <= support
    assert 7_990 <= legitimacy <= support


def test_tiny_valid_first_seven_turns_match_the_calibration_table() -> None:
    """The plan's `tiny_valid` table: support 8,000, opening 7,000, performance 0 every turn."""
    legitimacy = 7_000
    observed = []
    for _ in range(7):
        drift = order_support_contribution_bps(support_bps=8_000, opening_legitimacy_bps=legitimacy)
        _, legitimacy = resolve_legitimacy(
            opening_bps=legitimacy,
            order_support_contribution=drift,
            performance_contribution=0,
            security_contribution=0,
        )
        observed.append(legitimacy)
    assert observed == [7_100, 7_190, 7_271, 7_343, 7_408, 7_467, 7_520]


def test_tiny_valid_reaches_the_pinned_turn_100_value() -> None:
    legitimacy = 7_000
    for _ in range(100):
        drift = order_support_contribution_bps(support_bps=8_000, opening_legitimacy_bps=legitimacy)
        _, legitimacy = resolve_legitimacy(
            opening_bps=legitimacy,
            order_support_contribution=drift,
            performance_contribution=0,
            security_contribution=0,
        )
    assert legitimacy == 7_991


# --- T-L8: bounds hold for arbitrary valid inputs ----------------------------


@given(
    opening=st.integers(min_value=0, max_value=10_000),
    support=st.integers(min_value=0, max_value=10_000),
    baseline_output=st.integers(min_value=0, max_value=10**12),
    current_output=st.integers(min_value=0, max_value=10**12),
    baseline_unemployment=st.integers(min_value=0, max_value=10_000),
    current_unemployment=st.integers(min_value=0, max_value=10_000),
)
def test_closing_legitimacy_always_stays_within_the_scale(
    opening: int,
    support: int,
    baseline_output: int,
    current_output: int,
    baseline_unemployment: int,
    current_unemployment: int,
) -> None:
    assessment = assess_economic_performance(
        _signals(baseline_output, current_output, baseline_unemployment, current_unemployment)
    )
    drift = order_support_contribution_bps(support_bps=support, opening_legitimacy_bps=opening)
    applied, closing = resolve_legitimacy(
        opening_bps=opening,
        order_support_contribution=drift,
        performance_contribution=assessment.performance_contribution_bps,
        security_contribution=0,
    )
    assert LEGITIMACY_MIN_BPS <= closing <= LEGITIMACY_MAX_BPS
    assert applied == closing - opening
    assert abs(applied) <= MAX_TOTAL_LEGITIMACY_CHANGE_BPS


@given(
    baseline_output=st.integers(min_value=1, max_value=10**12),
    current_output=st.integers(min_value=0, max_value=10**12),
    baseline_unemployment=st.integers(min_value=0, max_value=10_000),
    current_unemployment=st.integers(min_value=0, max_value=10_000),
)
def test_performance_contribution_always_respects_its_cap(
    baseline_output: int,
    current_output: int,
    baseline_unemployment: int,
    current_unemployment: int,
) -> None:
    assessment = assess_economic_performance(
        _signals(baseline_output, current_output, baseline_unemployment, current_unemployment)
    )
    assert abs(assessment.performance_contribution_bps) <= MAX_PERFORMANCE_CONTRIBUTION_BPS


@pytest.mark.parametrize("magnitude", [1, 10, 1_000, 10**6, 10**9])
def test_identical_output_at_any_magnitude_contributes_nothing(magnitude: int) -> None:
    assessment = assess_economic_performance(_signals(magnitude, magnitude))
    assert assessment.performance_contribution_bps == 0


# --- External Wars Gate W1: security-anxiety contribution --------------------


def test_zero_exposure_contributes_exactly_zero_at_any_intensity() -> None:
    for intensity in (0, 1, 3_000, 5_668, 10_000):
        assert foreign_conflict_security_anxiety_bps(exposure_bps=0, intensity_bps=intensity) == 0


def test_zero_intensity_contributes_exactly_zero_at_any_exposure() -> None:
    for exposure in (0, 1, 2_000, 3_000, 10_000):
        assert foreign_conflict_security_anxiety_bps(exposure_bps=exposure, intensity_bps=0) == 0


def test_security_anxiety_is_never_positive() -> None:
    for exposure in (0, 500, 2_000, 3_000, 10_000):
        for intensity in (0, 500, 3_000, 5_668, 10_000):
            assert (
                foreign_conflict_security_anxiety_bps(
                    exposure_bps=exposure, intensity_bps=intensity
                )
                <= 0
            )


def test_security_anxiety_matches_the_measured_calibration_figures() -> None:
    """Frozen plan sec.9.5's own worked figures at the selected weight (600): exposure 3,000 at
    median measured intensity (4,642 bps) contributes a median 83 bps of anxiety."""
    assert foreign_conflict_security_anxiety_bps(exposure_bps=3_000, intensity_bps=4_642) == -83


def test_per_conflict_anxiety_is_uncapped_before_aggregation() -> None:
    """A single conflict's raw contribution can itself exceed MAX_SECURITY_CONTRIBUTION_BPS in
    magnitude -- the cap is deliberately NOT applied here (sec.7 rule 10); only the aggregate step
    caps it."""
    raw = foreign_conflict_security_anxiety_bps(exposure_bps=10_000, intensity_bps=10_000)
    assert raw < -MAX_SECURITY_CONTRIBUTION_BPS


def test_aggregate_cap_binds_only_once_never_per_conflict() -> None:
    """Three conflicts, each individually under the aggregate cap in magnitude, but whose SUM
    exceeds it: the aggregate step must still clamp to exactly -150, not -450 (would happen if the
    cap were mistakenly applied per conflict) and not any value between (would happen from a
    partial per-conflict clamp)."""
    per_conflict = foreign_conflict_security_anxiety_bps(exposure_bps=3_000, intensity_bps=4_642)
    assert -MAX_SECURITY_CONTRIBUTION_BPS < per_conflict < 0  # each alone is under the cap
    uncapped_total = per_conflict * 3
    assert uncapped_total < -MAX_SECURITY_CONTRIBUTION_BPS  # but the sum is not
    assert aggregate_security_contribution_bps(uncapped_total_bps=uncapped_total) == (
        -MAX_SECURITY_CONTRIBUTION_BPS
    )


def test_aggregate_cap_does_not_bind_below_the_threshold() -> None:
    assert aggregate_security_contribution_bps(uncapped_total_bps=-50) == -50


def test_aggregate_of_zero_conflicts_is_exactly_zero() -> None:
    assert aggregate_security_contribution_bps(uncapped_total_bps=0) == 0


def test_aggregate_contribution_is_never_positive() -> None:
    for total in (-10_000, -151, -150, -100, -1, 0):
        assert aggregate_security_contribution_bps(uncapped_total_bps=total) <= 0


@given(
    exposure=st.integers(min_value=0, max_value=10_000),
    intensity=st.integers(min_value=0, max_value=10_000),
)
def test_security_anxiety_is_never_positive_for_any_valid_input(
    exposure: int, intensity: int
) -> None:
    assert (
        foreign_conflict_security_anxiety_bps(exposure_bps=exposure, intensity_bps=intensity) <= 0
    )


@given(total=st.integers(min_value=-(10**9), max_value=10**9))
def test_aggregate_contribution_always_respects_its_cap(total: int) -> None:
    capped = aggregate_security_contribution_bps(uncapped_total_bps=total)
    assert -MAX_SECURITY_CONTRIBUTION_BPS <= capped <= 0


# --- resolve_legitimacy: three contributions under one existing cap ----------


def test_zero_security_contribution_reproduces_pre_w1_behavior_byte_for_byte() -> None:
    """`(500, 5_500)` is the exact pre-W1 return value pinned by
    `test_combined_change_is_capped_at_the_total_bound` above, for these same three inputs, from
    before `security_contribution` existed as a parameter at all. Passing `0` here must reproduce
    it exactly -- proving the new required parameter changes nothing when its value is neutral."""
    applied, closing = resolve_legitimacy(
        opening_bps=5_000,
        order_support_contribution=400,
        performance_contribution=300,
        security_contribution=0,
    )
    assert (applied, closing) == (MAX_TOTAL_LEGITIMACY_CHANGE_BPS, 5_500)


def test_security_contribution_is_summed_with_the_other_two_under_the_same_cap() -> None:
    applied, closing = resolve_legitimacy(
        opening_bps=5_000,
        order_support_contribution=100,
        performance_contribution=100,
        security_contribution=-50,
    )
    assert applied == 150  # 100 + 100 - 50, well under the +/-500 cap
    assert closing == 5_150


def test_security_contribution_can_push_the_total_below_the_lower_bound() -> None:
    applied, closing = resolve_legitimacy(
        opening_bps=5_000,
        order_support_contribution=-200,
        performance_contribution=-200,
        security_contribution=-150,
    )
    assert applied == -MAX_TOTAL_LEGITIMACY_CHANGE_BPS  # -550 requested, capped at -500
    assert closing == 4_500


@given(
    opening=st.integers(min_value=0, max_value=10_000),
    order=st.integers(min_value=-10_000, max_value=10_000),
    performance=st.integers(
        min_value=-MAX_PERFORMANCE_CONTRIBUTION_BPS, max_value=MAX_PERFORMANCE_CONTRIBUTION_BPS
    ),
    security=st.integers(min_value=-MAX_SECURITY_CONTRIBUTION_BPS, max_value=0),
)
def test_closing_legitimacy_stays_within_scale_with_all_three_contributions(
    opening: int, order: int, performance: int, security: int
) -> None:
    _, closing = resolve_legitimacy(
        opening_bps=opening,
        order_support_contribution=order,
        performance_contribution=performance,
        security_contribution=security,
    )
    assert LEGITIMACY_MIN_BPS <= closing <= LEGITIMACY_MAX_BPS
