"""Phase 3C, Gate 3C1: election-channel formulas (`simulation.government_survival`), pure and
unit-tested in isolation. Coup/unrest/impeachment/transition-pressure formulas are added in
Gate 3C2/3C3."""

from __future__ import annotations

import pytest

from app.simulation.government_survival import (
    LEGISLATIVE_SUPPORT_WEIGHT_BPS,
    LEGITIMACY_WEIGHT_BPS,
    POPULATION_APPROVAL_WEIGHT_BPS,
    REQUIRED_ELECTION_SUPPORT_BPS,
    election_baseline_support_bps,
    final_election_support_bps,
    legislative_support_bps,
    population_weighted_mean_bps,
)


def test_weight_constants_sum_to_the_full_scale() -> None:
    assert (
        LEGISLATIVE_SUPPORT_WEIGHT_BPS + POPULATION_APPROVAL_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
        == 10_000
    )


def test_legislative_support_bps_rejects_a_nonpositive_chamber() -> None:
    with pytest.raises(ValueError, match="total_seats must be positive"):
        legislative_support_bps(bloc_seats_and_relationships=(), total_seats=0)


def test_legislative_support_bps_tiny_valid_lower_chamber_worked_example() -> None:
    """The plan's own §11 worked example, computed from tiny_valid.yaml's real authored data:
    100 seats, mainstream 40 @ +6,000, reform 12 @ +3,000, conservatives 30 @ -7,000,
    populists 8 @ -3,000, farmers 10 @ +2,000."""
    support = legislative_support_bps(
        bloc_seats_and_relationships=(
            (40, 6_000),
            (12, 3_000),
            (30, -7_000),
            (8, -3_000),
            (10, 2_000),
        ),
        total_seats=100,
    )
    assert support == 5_310


def test_legislative_support_bps_full_support_and_full_hostility_bound_the_scale() -> None:
    assert (
        legislative_support_bps(bloc_seats_and_relationships=((100, 10_000),), total_seats=100)
        == 10_000
    )
    assert (
        legislative_support_bps(bloc_seats_and_relationships=((100, -10_000),), total_seats=100)
        == 0
    )


def test_population_weighted_mean_bps_worked_example() -> None:
    """Three groups, shares 4,000/3,500/2,500 bps, approvals 5,200/5,000/6,000 bps."""
    mean = population_weighted_mean_bps(
        shares_and_metrics=((4_000, 5_200), (3_500, 5_000), (2_500, 6_000))
    )
    assert mean == 5_330


def test_population_weighted_mean_bps_zero_total_share_returns_zero() -> None:
    assert population_weighted_mean_bps(shares_and_metrics=()) == 0
    assert population_weighted_mean_bps(shares_and_metrics=((0, 9_999),)) == 0


def test_election_baseline_support_bps_tiny_valid_worked_example() -> None:
    """legislative=5,310, population_approval=5,330, legitimacy=7,000 ->
    (5310*5000 + 5330*4000 + 7000*1000) / 10000 = 5,487."""
    assessment = election_baseline_support_bps(
        legislative_support_bps=5_310, population_approval_bps=5_330, legitimacy_bps=7_000
    )
    assert assessment.baseline_support_bps == 5_487
    assert assessment.legislative_support_bps == 5_310


def test_election_baseline_support_bps_renormalizes_when_no_legislature_exists() -> None:
    """No shipped scenario exercises this branch, but the formula must stay well-defined: weighted
    mean over population approval and legitimacy alone, at their relative weights."""
    assessment = election_baseline_support_bps(
        legislative_support_bps=None, population_approval_bps=6_000, legitimacy_bps=4_000
    )
    expected = (6_000 * 9_000 + 4_000 * 1_000) // 10_000
    assert assessment.baseline_support_bps == expected
    assert assessment.legislative_support_bps is None


def test_final_election_support_bps_clamps_to_the_scale() -> None:
    assert final_election_support_bps(baseline_support_bps=9_500, polling_swing_bps=1_000) == 10_000
    assert final_election_support_bps(baseline_support_bps=500, polling_swing_bps=-1_000) == 0
    assert final_election_support_bps(baseline_support_bps=5_000, polling_swing_bps=200) == 5_200


def test_required_election_support_is_the_scale_midpoint() -> None:
    assert REQUIRED_ELECTION_SUPPORT_BPS == 5_000
