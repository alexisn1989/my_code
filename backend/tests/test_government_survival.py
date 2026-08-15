"""Phase 3C: election-channel formulas (Gate 3C1) and coup/popular-unrest/impeachment/transition-
pressure formulas (Gate 3C2), `simulation.government_survival`, pure and unit-tested in isolation.

The coup/unrest/impeachment worked examples below are computed directly from the three shipped
scenarios' real, authored data (military institution rows, population groups, legislature seat/
role composition) -- reproduced by hand against `data/scenarios/*.yaml` and cross-checked against
the plan's own §11 calibration table. **One real, reportable discrepancy was found and is recorded
here rather than silently absorbed**: the plan's §11 table states `deficit_demo`'s coup success
probability as 250 bps, but `deficit_demo`'s actual authored military row (loyalty 7,000, power
6,000, competence 5,500 -- authored in Gate 3C1, before these formulas existed to check it against)
computes to 450 bps under the exact formula this module implements. This does not change any
qualitative conclusion (still far under `MAX_COUP_SUCCESS_PROBABILITY_BPS`, and the resulting
compound per-turn coup risk, 2 bps rather than 1, keeps `deficit_demo` comfortably within the same
low-risk band the plan itself concludes for it) -- the tests below pin the REAL, computed value
(450), not the plan's illustrative one, matching this session's established discipline of verifying
plan-stated numbers against the real engine rather than trusting or silently tuning around them.

A second, structural finding: the plan's §11 table also shows `decree_state`'s impeachment channel
as active (37/900/3 bps) in the same baseline row used for its 100-turn "never scheduled" stability
sweep. But `decree_state`'s genesis constitution authors `executive_selection: hereditary`, which
the plan's own §3.3 eligibility rule (`executive_selection is not ExecutiveSelection.HEREDITARY`)
excludes from impeachment entirely. At genesis, `decree_state`'s real impeachment channel is
therefore INELIGIBLE (`eligible=False`), not 37/900/3 -- that figure can only apply after Gate 3C3's
liberalizing amendment replaces hereditary selection (§11(b)'s walkthrough, turn 3 onward), which
does not exist yet in Gate 3C2. The tests below pin the real genesis-eligibility outcome."""

from __future__ import annotations

import pytest

from app.simulation.constitution import AmendmentDifficulty, JudicialReview
from app.simulation.government_survival import (
    BASE_COUP_ATTEMPT_RISK_BPS,
    BASE_UNREST_ATTEMPT_RISK_BPS,
    LEGISLATIVE_SUPPORT_WEIGHT_BPS,
    LEGITIMACY_WEIGHT_BPS,
    MAX_COUP_ATTEMPT_RISK_BPS,
    MAX_COUP_SUCCESS_PROBABILITY_BPS,
    MAX_IMPEACHMENT_ATTEMPT_RISK_BPS,
    MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS,
    MAX_UNREST_ATTEMPT_RISK_BPS,
    MAX_UNREST_SUCCESS_PROBABILITY_BPS,
    POPULATION_APPROVAL_WEIGHT_BPS,
    REQUIRED_ELECTION_SUPPORT_BPS,
    coup_attempt_risk_bps,
    coup_success_probability_bps,
    election_baseline_support_bps,
    final_election_support_bps,
    impeachment_attempt_risk_bps,
    impeachment_success_probability_bps,
    legislative_support_bps,
    population_weighted_mean_bps,
    resolve_transition_pressure_bps,
    transition_pressure_added_bps,
    unrest_attempt_risk_bps,
    unrest_success_probability_bps,
)

# --- Real, authored scenario data (data/scenarios/*.yaml), used throughout Gate 3C2's worked
# examples below, so every literal is traceable to its source rather than invented.

TINY_VALID_MILITARY = {"loyalty_bps": 7_500, "power_bps": 6_500, "competence_bps": 6_000}
TINY_VALID_LEGITIMACY_BPS = 7_000
TINY_VALID_OPPOSITION_SEAT_SHARE_BPS = 3_800  # national_front (30+8 of 100 lower-chamber seats)
TINY_VALID_RADICALIZATION_BPS = 625
TINY_VALID_ORGANIZATION_BPS = 3_275
TINY_VALID_DISAPPROVAL_BPS = 4_670

DEFICIT_DEMO_MILITARY = {"loyalty_bps": 7_000, "power_bps": 6_000, "competence_bps": 5_500}
DEFICIT_DEMO_LEGITIMACY_BPS = 6_000
DEFICIT_DEMO_OPPOSITION_SEAT_SHARE_BPS = 5_000  # citizens_bloc (30+20 of 100 seats)
DEFICIT_DEMO_RADICALIZATION_BPS = 800
DEFICIT_DEMO_ORGANIZATION_BPS = 2_500
DEFICIT_DEMO_DISAPPROVAL_BPS = 5_500

DECREE_STATE_MILITARY = {"loyalty_bps": 7_500, "power_bps": 6_500, "competence_bps": 6_000}
DECREE_STATE_LEGITIMACY_BPS = 6_000
DECREE_STATE_OPPOSITION_SEAT_SHARE_BPS = 5_500  # opposition_party (55 of 100 seats)
DECREE_STATE_RADICALIZATION_BPS = 625
DECREE_STATE_ORGANIZATION_BPS = 3_275
DECREE_STATE_DISAPPROVAL_BPS = 4_670


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


# --- Gate 3C2: coup channel ------------------------------------------------------------------


def test_coup_attempt_risk_bps_tiny_valid_worked_example() -> None:
    """Loyalty (7,500) and legitimacy (7,000) both clear their thresholds, so only the base and
    opposition-seat-share terms contribute: 8 + trunc(3,800*80/10,000) = 8 + 30 = 38."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=TINY_VALID_MILITARY["loyalty_bps"],
        military_power_bps=TINY_VALID_MILITARY["power_bps"],
        legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
        opposition_seat_share_bps=TINY_VALID_OPPOSITION_SEAT_SHARE_BPS,
        transition_pressure_bps=0,
    )
    assert assessment.loyalty_contribution_bps == 0
    assert assessment.legitimacy_contribution_bps == 0
    assert assessment.opposition_contribution_bps == 30
    assert assessment.transition_pressure_contribution_bps == 0
    assert assessment.attempt_risk_bps == 38


def test_coup_attempt_risk_bps_deficit_demo_worked_example() -> None:
    """8 + trunc(5,000*80/10,000) = 8 + 40 = 48."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=DEFICIT_DEMO_MILITARY["loyalty_bps"],
        military_power_bps=DEFICIT_DEMO_MILITARY["power_bps"],
        legitimacy_bps=DEFICIT_DEMO_LEGITIMACY_BPS,
        opposition_seat_share_bps=DEFICIT_DEMO_OPPOSITION_SEAT_SHARE_BPS,
        transition_pressure_bps=0,
    )
    assert assessment.attempt_risk_bps == 48


def test_coup_attempt_risk_bps_decree_state_worked_example() -> None:
    """8 + trunc(5,500*80/10,000) = 8 + 44 = 52."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=DECREE_STATE_MILITARY["loyalty_bps"],
        military_power_bps=DECREE_STATE_MILITARY["power_bps"],
        legitimacy_bps=DECREE_STATE_LEGITIMACY_BPS,
        opposition_seat_share_bps=DECREE_STATE_OPPOSITION_SEAT_SHARE_BPS,
        transition_pressure_bps=0,
    )
    assert assessment.attempt_risk_bps == 52


def test_coup_attempt_risk_bps_low_loyalty_case_from_the_plan() -> None:
    """§11's deliberately-low-loyalty test case: tiny_valid's military with loyalty edited down to
    2,000, everything else unchanged -- 623 bps, a real, sharply visible jump from the baseline 38,
    confirming the formula is genuinely sensitive."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=2_000,
        military_power_bps=TINY_VALID_MILITARY["power_bps"],
        legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
        opposition_seat_share_bps=TINY_VALID_OPPOSITION_SEAT_SHARE_BPS,
        transition_pressure_bps=0,
    )
    assert assessment.loyalty_contribution_bps == 585
    assert assessment.attempt_risk_bps == 623


def test_coup_attempt_risk_bps_no_legislature_contributes_nothing_from_opposition() -> None:
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=9_000,
        military_power_bps=5_000,
        legitimacy_bps=9_000,
        opposition_seat_share_bps=None,
        transition_pressure_bps=0,
    )
    assert assessment.opposition_contribution_bps == 0
    assert assessment.attempt_risk_bps == BASE_COUP_ATTEMPT_RISK_BPS


def test_coup_attempt_risk_bps_transition_pressure_at_maximum() -> None:
    """Full 10,000-bps transition pressure (a just-enacted five-axis amendment) contributes the
    full weight: trunc(10,000*1,000/10,000) = 1,000."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=9_000,
        military_power_bps=0,
        legitimacy_bps=9_000,
        opposition_seat_share_bps=0,
        transition_pressure_bps=10_000,
    )
    assert assessment.transition_pressure_contribution_bps == 1_000
    assert assessment.attempt_risk_bps == BASE_COUP_ATTEMPT_RISK_BPS + 1_000


def test_coup_attempt_risk_bps_clamps_at_the_maximum() -> None:
    """Zero loyalty, zero legitimacy, full opposition, full transition pressure -- every term
    maxed -- must clamp to MAX_COUP_ATTEMPT_RISK_BPS, not overflow past it."""
    assessment = coup_attempt_risk_bps(
        military_loyalty_bps=0,
        military_power_bps=10_000,
        legitimacy_bps=0,
        opposition_seat_share_bps=10_000,
        transition_pressure_bps=10_000,
    )
    assert assessment.attempt_risk_bps == MAX_COUP_ATTEMPT_RISK_BPS


def test_coup_success_probability_bps_tiny_valid_worked_example() -> None:
    """500 + trunc(6,500*2,000/10,000) + trunc(6,000*1,000/10,000) - trunc(7,000*3,000/10,000)
    = 500 + 1,300 + 600 - 2,100 = 300."""
    success = coup_success_probability_bps(
        military_power_bps=TINY_VALID_MILITARY["power_bps"],
        military_competence_bps=TINY_VALID_MILITARY["competence_bps"],
        legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
    )
    assert success == 300


def test_coup_success_probability_bps_deficit_demo_worked_example() -> None:
    """500 + trunc(6,000*2,000/10,000) + trunc(5,500*1,000/10,000) - trunc(6,000*3,000/10,000)
    = 500 + 1,200 + 550 - 1,800 = 450 -- see the module docstring's discrepancy note: the plan's
    own §11 table states 250, but 450 is what deficit_demo's real, Gate-3C1-authored military row
    actually computes to under this exact formula."""
    success = coup_success_probability_bps(
        military_power_bps=DEFICIT_DEMO_MILITARY["power_bps"],
        military_competence_bps=DEFICIT_DEMO_MILITARY["competence_bps"],
        legitimacy_bps=DEFICIT_DEMO_LEGITIMACY_BPS,
    )
    assert success == 450


def test_coup_success_probability_bps_decree_state_worked_example() -> None:
    """500 + 1,300 + 600 - 1,800 = 600."""
    success = coup_success_probability_bps(
        military_power_bps=DECREE_STATE_MILITARY["power_bps"],
        military_competence_bps=DECREE_STATE_MILITARY["competence_bps"],
        legitimacy_bps=DECREE_STATE_LEGITIMACY_BPS,
    )
    assert success == 600


def test_coup_success_probability_bps_floors_at_zero_under_overwhelming_legitimacy() -> None:
    assert (
        coup_success_probability_bps(
            military_power_bps=0, military_competence_bps=0, legitimacy_bps=10_000
        )
        == 0
    )


def test_coup_success_probability_bps_at_maximum_inputs_stays_under_the_defensive_cap() -> None:
    """The formula's own positive terms (base 500 + power weight 2,000 + competence weight 1,000)
    sum to at most 3,500, strictly below `MAX_COUP_SUCCESS_PROBABILITY_BPS` (7,000) -- the cap is
    a defensive bound against a future weight change, never reached by this formula's own weights
    at any legal input, which this test pins directly."""
    at_maximum = coup_success_probability_bps(
        military_power_bps=10_000, military_competence_bps=10_000, legitimacy_bps=0
    )
    assert at_maximum == 3_500
    assert at_maximum < MAX_COUP_SUCCESS_PROBABILITY_BPS


# --- Gate 3C2: popular-unrest channel --------------------------------------------------------


def test_unrest_attempt_risk_bps_tiny_valid_and_decree_state_share_the_baseline() -> None:
    """Both scenarios author the identical urban_workers/rural_farmers/business_owners population
    data, so both land on the same population-weighted figures: radicalization 625 (below the
    2,000 threshold) and disapproval 4,670 (below the 5,500 threshold) -- neither term
    contributes, leaving the flat base risk of 15."""
    for radicalization, organization, disapproval in (
        (TINY_VALID_RADICALIZATION_BPS, TINY_VALID_ORGANIZATION_BPS, TINY_VALID_DISAPPROVAL_BPS),
        (
            DECREE_STATE_RADICALIZATION_BPS,
            DECREE_STATE_ORGANIZATION_BPS,
            DECREE_STATE_DISAPPROVAL_BPS,
        ),
    ):
        assessment = unrest_attempt_risk_bps(
            radicalization_bps=radicalization,
            organization_bps=organization,
            disapproval_bps=disapproval,
        )
        assert assessment.radicalization_contribution_bps == 0
        assert assessment.disapproval_contribution_bps == 0
        assert assessment.attempt_risk_bps == BASE_UNREST_ATTEMPT_RISK_BPS


def test_unrest_attempt_risk_bps_deficit_demo_worked_example() -> None:
    """disapproval_bps = 5,500 exactly equals its threshold -- max(0, 5500-5500) = 0, so the
    excess term is exactly zero at the boundary, not a rounding artifact."""
    assessment = unrest_attempt_risk_bps(
        radicalization_bps=DEFICIT_DEMO_RADICALIZATION_BPS,
        organization_bps=DEFICIT_DEMO_ORGANIZATION_BPS,
        disapproval_bps=DEFICIT_DEMO_DISAPPROVAL_BPS,
    )
    assert assessment.disapproval_contribution_bps == 0
    assert assessment.attempt_risk_bps == BASE_UNREST_ATTEMPT_RISK_BPS


def test_unrest_attempt_risk_bps_above_both_thresholds() -> None:
    assessment = unrest_attempt_risk_bps(
        radicalization_bps=10_000, organization_bps=10_000, disapproval_bps=10_000
    )
    radicalization_excess = 10_000 - 2_000
    radicalization_contribution = radicalization_excess * 10_000 // 10_000 * 2_500 // 10_000
    disapproval_excess = 10_000 - 5_500
    disapproval_contribution = disapproval_excess * 1_500 // 10_000
    assert assessment.radicalization_contribution_bps == radicalization_contribution
    assert assessment.disapproval_contribution_bps == disapproval_contribution
    expected_total = (
        BASE_UNREST_ATTEMPT_RISK_BPS + radicalization_contribution + disapproval_contribution
    )
    assert assessment.attempt_risk_bps == min(MAX_UNREST_ATTEMPT_RISK_BPS, expected_total)


def test_unrest_attempt_risk_bps_clamps_at_the_maximum() -> None:
    assessment = unrest_attempt_risk_bps(
        radicalization_bps=10_000, organization_bps=10_000, disapproval_bps=10_000
    )
    assert assessment.attempt_risk_bps == MAX_UNREST_ATTEMPT_RISK_BPS


def test_unrest_attempt_risk_bps_zero_organization_zeroes_radicalization_term() -> None:
    """Radicalization alone, with no organized capacity to act on it, contributes nothing --
    organization is a multiplicative capacity term, not an independent trigger."""
    assessment = unrest_attempt_risk_bps(
        radicalization_bps=10_000, organization_bps=0, disapproval_bps=0
    )
    assert assessment.radicalization_contribution_bps == 0
    assert assessment.attempt_risk_bps == BASE_UNREST_ATTEMPT_RISK_BPS


def test_unrest_success_probability_bps_tiny_valid_and_decree_state_worked_example() -> None:
    """500 + trunc(3,275*3,000/10,000) - trunc(7,000*3,000/10,000) for tiny_valid (legitimacy
    7,000) = 500 + 982 - 2,100 = -618 -> floors at 0. decree_state shares the same organization
    figure but a lower legitimacy (6,000): 500 + 982 - 1,800 = -318 -> also floors at 0."""
    assert (
        unrest_success_probability_bps(
            organization_bps=TINY_VALID_ORGANIZATION_BPS,
            legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
        )
        == 0
    )
    assert (
        unrest_success_probability_bps(
            organization_bps=DECREE_STATE_ORGANIZATION_BPS,
            legitimacy_bps=DECREE_STATE_LEGITIMACY_BPS,
        )
        == 0
    )


def test_unrest_success_probability_bps_deficit_demo_worked_example() -> None:
    """500 + trunc(2,500*3,000/10,000) - trunc(6,000*3,000/10,000) = 500 + 750 - 1,800 = -550 ->
    floors at 0."""
    assert (
        unrest_success_probability_bps(
            organization_bps=DEFICIT_DEMO_ORGANIZATION_BPS,
            legitimacy_bps=DEFICIT_DEMO_LEGITIMACY_BPS,
        )
        == 0
    )


def test_unrest_success_probability_bps_at_maximum_inputs_stays_under_the_defensive_cap() -> None:
    """base 500 + organization weight 3,000 sum to at most 3,500, strictly below
    `MAX_UNREST_SUCCESS_PROBABILITY_BPS` (6,000) -- again a defensive bound, never reached."""
    at_maximum = unrest_success_probability_bps(organization_bps=10_000, legitimacy_bps=0)
    assert at_maximum == 3_500
    assert at_maximum < MAX_UNREST_SUCCESS_PROBABILITY_BPS


# --- Gate 3C2: impeachment channel -----------------------------------------------------------


def test_impeachment_attempt_risk_bps_tiny_valid_worked_example() -> None:
    """Legitimacy (7,000) clears its threshold and opposition (3,800) is below its threshold
    (5,000), so both named terms are zero -- unlike coup/unrest, impeachment carries no flat base,
    so the total is exactly 0."""
    assessment = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=TINY_VALID_OPPOSITION_SEAT_SHARE_BPS,
        legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
        judicial_review=JudicialReview.STRONG,
    )
    assert assessment.legitimacy_contribution_bps == 0
    assert assessment.opposition_contribution_bps == 0
    assert assessment.attempt_risk_bps == 0


def test_impeachment_attempt_risk_bps_deficit_demo_worked_example() -> None:
    """Opposition (5,000) exactly equals its threshold -- max(0, 5000-5000) = 0 -- and legitimacy
    (6,000) clears its own threshold, so this is also exactly 0."""
    assessment = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=DEFICIT_DEMO_OPPOSITION_SEAT_SHARE_BPS,
        legitimacy_bps=DEFICIT_DEMO_LEGITIMACY_BPS,
        judicial_review=JudicialReview.WEAK,
    )
    assert assessment.attempt_risk_bps == 0


def test_impeachment_attempt_risk_bps_judicial_review_none_zeroes_every_contribution() -> None:
    """A judiciary with no review power at all scales BOTH contributions to zero, regardless of
    how far past threshold legitimacy/opposition sit."""
    assessment = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=10_000, legitimacy_bps=0, judicial_review=JudicialReview.NONE
    )
    assert assessment.legitimacy_contribution_bps == 0
    assert assessment.opposition_contribution_bps == 0
    assert assessment.attempt_risk_bps == 0


def test_impeachment_attempt_risk_bps_strong_review_scales_up_from_weak() -> None:
    """At inputs moderate enough that neither scale hits `MAX_IMPEACHMENT_ATTEMPT_RISK_BPS`,
    STRONG review's 10,000-bps scale is exactly double WEAK's 5,000-bps scale."""
    weak = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=6_000, legitimacy_bps=2_000, judicial_review=JudicialReview.WEAK
    )
    strong = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=6_000,
        legitimacy_bps=2_000,
        judicial_review=JudicialReview.STRONG,
    )
    assert weak.attempt_risk_bps == 275
    assert strong.attempt_risk_bps == 550
    assert strong.attempt_risk_bps == 2 * weak.attempt_risk_bps


def test_impeachment_attempt_risk_bps_clamps_at_the_maximum() -> None:
    assessment = impeachment_attempt_risk_bps(
        opposition_seat_share_bps=10_000, legitimacy_bps=0, judicial_review=JudicialReview.STRONG
    )
    assert assessment.attempt_risk_bps == MAX_IMPEACHMENT_ATTEMPT_RISK_BPS


def test_impeachment_success_probability_bps_tiny_valid_worked_example() -> None:
    """500 + trunc(3,800*4,000/10,000) - trunc(7,000*3,000/10,000) = 500 + 1,520 - 2,100 = -80 ->
    floors at 0."""
    assert (
        impeachment_success_probability_bps(
            opposition_seat_share_bps=TINY_VALID_OPPOSITION_SEAT_SHARE_BPS,
            legitimacy_bps=TINY_VALID_LEGITIMACY_BPS,
        )
        == 0
    )


def test_impeachment_success_probability_bps_deficit_demo_worked_example() -> None:
    """500 + trunc(5,000*4,000/10,000) - trunc(6,000*3,000/10,000) = 500 + 2,000 - 1,800 = 700.
    Computed independently of eligibility/attempt -- this channel's success formula is pure and
    always well-defined, matching every other channel's report-transparency requirement."""
    assert (
        impeachment_success_probability_bps(
            opposition_seat_share_bps=DEFICIT_DEMO_OPPOSITION_SEAT_SHARE_BPS,
            legitimacy_bps=DEFICIT_DEMO_LEGITIMACY_BPS,
        )
        == 700
    )


def test_impeachment_success_probability_bps_at_maximum_inputs_stays_under_the_defensive_cap() -> (
    None
):
    """base 500 + opposition weight 4,000 sum to at most 4,500, strictly below
    `MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS` (6,000) -- again a defensive bound, never reached."""
    at_maximum = impeachment_success_probability_bps(
        opposition_seat_share_bps=10_000, legitimacy_bps=0
    )
    assert at_maximum == 4_500
    assert at_maximum < MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS


# --- Gate 3C2: transition pressure -----------------------------------------------------------


def test_transition_pressure_added_bps_zero_axes_changed_is_zero() -> None:
    assert (
        transition_pressure_added_bps(difficulty=AmendmentDifficulty.ENTRENCHED, axes_changed=0)
        == 0
    )


def test_transition_pressure_added_bps_scales_linearly_with_axes_changed() -> None:
    assert (
        transition_pressure_added_bps(
            difficulty=AmendmentDifficulty.SIMPLE_MAJORITY, axes_changed=1
        )
        == 1_500
    )
    assert (
        transition_pressure_added_bps(
            difficulty=AmendmentDifficulty.SIMPLE_MAJORITY, axes_changed=2
        )
        == 3_000
    )


def test_transition_pressure_added_bps_five_axis_supermajority_clamps_to_the_scale() -> None:
    """§11(b)'s canonical decree_state liberalization: a five-axis SUPERMAJORITY change would
    compute 2,500*5 = 12,500, clamped to the scale maximum of 10,000."""
    assert (
        transition_pressure_added_bps(difficulty=AmendmentDifficulty.SUPERMAJORITY, axes_changed=5)
        == 10_000
    )


def test_resolve_transition_pressure_bps_decays_by_one_sixth_with_a_minimum_step() -> None:
    resolution = resolve_transition_pressure_bps(opening_pressure_bps=6_000, amendment_added_bps=0)
    assert resolution.decayed_bps == 1_000
    assert resolution.closing_bps == 5_000

    small_residual = resolve_transition_pressure_bps(opening_pressure_bps=3, amendment_added_bps=0)
    assert small_residual.decayed_bps == 1
    assert small_residual.closing_bps == 2


def test_resolve_transition_pressure_bps_zero_opening_and_zero_added_stays_zero() -> None:
    resolution = resolve_transition_pressure_bps(opening_pressure_bps=0, amendment_added_bps=0)
    assert resolution.decayed_bps == 0
    assert resolution.closing_bps == 0


def test_resolve_transition_pressure_bps_added_pressure_combines_with_decay() -> None:
    """Decay and the new amendment's addition are applied in the SAME step, from the SAME opening
    value -- not sequentially through two separate writes (R6)."""
    resolution = resolve_transition_pressure_bps(opening_pressure_bps=0, amendment_added_bps=10_000)
    assert resolution.decayed_bps == 0
    assert resolution.uncapped_bps == 10_000
    assert resolution.closing_bps == 10_000


def test_resolve_transition_pressure_bps_clamps_the_closing_value_to_the_scale() -> None:
    resolution = resolve_transition_pressure_bps(
        opening_pressure_bps=9_000, amendment_added_bps=10_000
    )
    assert resolution.uncapped_bps > 10_000
    assert resolution.closing_bps == 10_000
