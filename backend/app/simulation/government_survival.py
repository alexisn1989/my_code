"""Government-survival formulas: elections, coups, popular unrest, impeachment, and the transition
pressure a constitutional amendment leaves behind (Phase 3C).

No I/O, no randomness, no state mutation, no clock, no floating point — the same shape every other
pure formula module in this package follows (`legislative_voting`, `apportionment`, `legitimacy`,
`relationships`, `political_memory`). **Deliberately not added to `NEUTRAL_MODULES`**
(`tests/test_legislative_neutrality.py`): elections and coups are the opposite case from that
discipline by design — a scheduled election only exists because of
`national_election_interval_turns`, impeachment eligibility genuinely depends on `judicial_review`/
`executive_selection`. Every function here still accepts only plain ints/enums it declares itself,
never `ConstitutionState` — the constitution is read in `phases.py`'s slot handlers, the same split
`legislature.py`'s own routing check already uses.

Gate 3C1 implements the election channel (§3.4). Gate 3C2 adds the coup, popular-unrest, and
impeachment channels (§3.1-3.3). Transition pressure (§3.5) is added in Gate 3C2 too, since slot 12
(the coup/unrest/impeachment slot) is its sole write site. `ConstitutionalAmendmentDecision` itself
-- the only thing that can ever make `transition_pressure_added_bps` nonzero -- does not exist until
Gate 3C3, so every Gate 3C2 call site passes `axes_changed=0`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.politics import clamp_bps, trunc_div_toward_zero
from app.simulation.constitution import AmendmentDifficulty, JudicialReview

REQUIRED_ELECTION_SUPPORT_BPS = 5_000
LEGISLATIVE_SUPPORT_WEIGHT_BPS = 5_000
POPULATION_APPROVAL_WEIGHT_BPS = 4_000
LEGITIMACY_WEIGHT_BPS = 1_000
MAX_POLLING_UNCERTAINTY_SWING_BPS = 1_000
"""+/- 10 percentage points -- the widest a single seeded polling-uncertainty draw can move the
baseline support figure in either direction."""


@dataclass(frozen=True, slots=True)
class ElectionSupportAssessment:
    """Every intermediate value behind one election's baseline support figure, so the report can
    publish each one and a reader can re-derive the total without trusting it."""

    legislative_support_bps: int | None
    population_approval_bps: int
    legitimacy_bps: int
    baseline_support_bps: int


def legislative_support_bps(
    *, bloc_seats_and_relationships: tuple[tuple[int, int], ...], total_seats: int
) -> int:
    """One chamber's seat-weighted support for the incumbent's continuation, from
    `(seats, government_relationship_bps)` pairs across every bloc in that chamber -- reads exact
    seat counts, never a party's own already-rounded seat-share.

    Each bloc's relationship is rescaled from `[-10,000, +10,000]` to a `[0, 10,000]` support
    contribution (`(relationship_bps + 10,000) // 2`, via `trunc_div_toward_zero` on the summed
    numerator, never per-bloc, so a single rounding step governs the whole chamber), then
    seat-weighted.
    """
    if total_seats <= 0:
        raise ValueError(
            f"legislative_support_bps: total_seats must be positive, got {total_seats}"
        )
    weighted_sum = sum(
        seats * trunc_div_toward_zero(relationship_bps + BPS_DENOMINATOR, 2)
        for seats, relationship_bps in bloc_seats_and_relationships
    )
    return trunc_div_toward_zero(weighted_sum, total_seats)


def election_baseline_support_bps(
    *, legislative_support_bps: int | None, population_approval_bps: int, legitimacy_bps: int
) -> ElectionSupportAssessment:
    """The incumbent's baseline support ahead of a scheduled election's polling-uncertainty draw.

    `legislative_support_bps=None` means no legislature exists at all: the weighted mean
    renormalizes over the two remaining signals rather than fabricating a legislature that isn't
    there. No shipped scenario exercises this branch (all three ship with a legislature), but the
    formula must still be well-defined for one that doesn't.
    """
    if legislative_support_bps is None:
        weighted_sum = (
            population_approval_bps
            * (POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS)
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        )
        denominator = (
            POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
        )
    else:
        weighted_sum = (
            legislative_support_bps * LEGISLATIVE_SUPPORT_WEIGHT_BPS
            + population_approval_bps * POPULATION_APPROVAL_WEIGHT_BPS
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        )
        denominator = (
            LEGISLATIVE_SUPPORT_WEIGHT_BPS + POPULATION_APPROVAL_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
        )
    baseline_bps = trunc_div_toward_zero(weighted_sum, denominator)
    return ElectionSupportAssessment(
        legislative_support_bps=legislative_support_bps,
        population_approval_bps=population_approval_bps,
        legitimacy_bps=legitimacy_bps,
        baseline_support_bps=baseline_bps,
    )


def final_election_support_bps(*, baseline_support_bps: int, polling_swing_bps: int) -> int:
    """`baseline_support_bps` plus the seeded polling-uncertainty draw, clamped to the support
    scale. A separate, tiny function so slot 13 and reconciliation both call the identical, single
    combining step rather than each re-deriving `clamp_bps(baseline + swing)` independently."""
    return clamp_bps(baseline_support_bps + polling_swing_bps)


def population_weighted_mean_bps(*, shares_and_metrics: tuple[tuple[int, int], ...]) -> int:
    """A population-share-weighted mean of an already-bps metric (e.g. approval, radicalization),
    over `(population_share_bps, metric_bps)` pairs. Plain integer arithmetic throughout -- no
    float is ever involved, since `PopulationGroupState`'s metrics are strict bps by construction
    (R8) and shares are supplied here already rescaled to bps by the caller."""
    total_share = sum(share for share, _ in shares_and_metrics)
    if total_share == 0:
        return 0
    weighted_sum = sum(share * metric for share, metric in shares_and_metrics)
    return trunc_div_toward_zero(weighted_sum, total_share)


# --- Gate 3C2: coup channel ----------------------------------------------------------------

BASE_COUP_ATTEMPT_RISK_BPS = 8
COUP_LOYALTY_THRESHOLD_BPS = 5_000
"""Below 50% loyalty, disloyalty starts contributing to attempt risk. At or above the threshold,
this term is exactly zero -- a threshold-gated design (not a pure linear weight) is what makes a
"stable, loyal" military (every shipped scenario authors loyalty >= 75%) contribute nothing from
this term, rather than requiring the weight itself to be hand-tuned to near-zero at 75%."""
COUP_LOYALTY_SHORTFALL_WEIGHT_BPS = 3_000
COUP_LEGITIMACY_THRESHOLD_BPS = 3_000
"""Below 30% legitimacy, a coup becomes easier to justify. At or above, zero contribution."""
COUP_LEGITIMACY_SHORTFALL_WEIGHT_BPS = 2_000
COUP_OPPOSITION_WEIGHT_BPS = 80
"""Linear, not threshold-gated -- a hostile legislature is meaningfully destabilizing at any
share, even a modest one, so there is no "safe" opposition level."""
COUP_TRANSITION_PRESSURE_WEIGHT_BPS = 1_000
MAX_COUP_ATTEMPT_RISK_BPS = 2_500

COUP_SUCCESS_BASE_BPS = 500
COUP_SUCCESS_POWER_WEIGHT_BPS = 2_000
COUP_SUCCESS_COMPETENCE_WEIGHT_BPS = 1_000
COUP_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_COUP_SUCCESS_PROBABILITY_BPS = 7_000


@dataclass(frozen=True, slots=True)
class CoupAttemptRiskAssessment:
    """Every named contribution behind the coup channel's attempt-risk figure, so the report can
    publish each one and a reader can re-derive the total without trusting it."""

    loyalty_contribution_bps: int
    legitimacy_contribution_bps: int
    opposition_contribution_bps: int
    transition_pressure_contribution_bps: int
    attempt_risk_bps: int


def coup_attempt_risk_bps(
    *,
    military_loyalty_bps: int,
    military_power_bps: int,
    legitimacy_bps: int,
    opposition_seat_share_bps: int | None,
    transition_pressure_bps: int,
) -> CoupAttemptRiskAssessment:
    """The coup channel's per-turn attempt risk -- pure, no RNG. `opposition_seat_share_bps=None`
    (no legislature at all) contributes nothing from that term, the same "nothing to read"
    treatment `election_baseline_support_bps` gives a missing legislature."""
    loyalty_shortfall_bps = max(0, COUP_LOYALTY_THRESHOLD_BPS - military_loyalty_bps)
    loyalty_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(loyalty_shortfall_bps * military_power_bps, BPS_DENOMINATOR)
        * COUP_LOYALTY_SHORTFALL_WEIGHT_BPS,
        BPS_DENOMINATOR,
    )
    legitimacy_shortfall_bps = max(0, COUP_LEGITIMACY_THRESHOLD_BPS - legitimacy_bps)
    legitimacy_contribution_bps = trunc_div_toward_zero(
        legitimacy_shortfall_bps * COUP_LEGITIMACY_SHORTFALL_WEIGHT_BPS, BPS_DENOMINATOR
    )
    opposition_contribution_bps = trunc_div_toward_zero(
        (opposition_seat_share_bps or 0) * COUP_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR
    )
    pressure_contribution_bps = trunc_div_toward_zero(
        transition_pressure_bps * COUP_TRANSITION_PRESSURE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        BASE_COUP_ATTEMPT_RISK_BPS
        + loyalty_contribution_bps
        + legitimacy_contribution_bps
        + opposition_contribution_bps
        + pressure_contribution_bps
    )
    return CoupAttemptRiskAssessment(
        loyalty_contribution_bps=loyalty_contribution_bps,
        legitimacy_contribution_bps=legitimacy_contribution_bps,
        opposition_contribution_bps=opposition_contribution_bps,
        transition_pressure_contribution_bps=pressure_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_COUP_ATTEMPT_RISK_BPS, total_bps)),
    )


def coup_success_probability_bps(
    *, military_power_bps: int, military_competence_bps: int, legitimacy_bps: int
) -> int:
    """The coup channel's success probability, given an attempt occurred -- pure, no RNG.
    Legitimacy is a pure defense term (it always subtracts): a well-regarded government is harder
    to overthrow even once a coup is underway."""
    power_contribution_bps = trunc_div_toward_zero(
        military_power_bps * COUP_SUCCESS_POWER_WEIGHT_BPS, BPS_DENOMINATOR
    )
    competence_contribution_bps = trunc_div_toward_zero(
        military_competence_bps * COUP_SUCCESS_COMPETENCE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    legitimacy_contribution_bps = -trunc_div_toward_zero(
        legitimacy_bps * COUP_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        COUP_SUCCESS_BASE_BPS
        + power_contribution_bps
        + competence_contribution_bps
        + legitimacy_contribution_bps
    )
    return max(0, min(MAX_COUP_SUCCESS_PROBABILITY_BPS, total_bps))


# --- Gate 3C2: popular-unrest channel ------------------------------------------------------

BASE_UNREST_ATTEMPT_RISK_BPS = 15
UNREST_RADICALIZATION_THRESHOLD_BPS = 2_000
"""Above 20% population-weighted radicalization, this term starts contributing."""
UNREST_RADICALIZATION_WEIGHT_BPS = 2_500
UNREST_DISAPPROVAL_THRESHOLD_BPS = 5_500
"""Above 55% population-weighted disapproval, this term starts contributing."""
UNREST_DISAPPROVAL_WEIGHT_BPS = 1_500
MAX_UNREST_ATTEMPT_RISK_BPS = 1_500

UNREST_SUCCESS_BASE_BPS = 500
UNREST_SUCCESS_ORGANIZATION_WEIGHT_BPS = 3_000
UNREST_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_UNREST_SUCCESS_PROBABILITY_BPS = 6_000
ASSASSINATION_SEVERITY_THRESHOLD_BPS = 1_500
"""The worst 15% of severity draws, GIVEN success, label the outcome ASSASSINATION rather than
FORCED_ABDICATION."""


@dataclass(frozen=True, slots=True)
class UnrestAttemptRiskAssessment:
    """Every named contribution behind the popular-unrest channel's attempt-risk figure."""

    radicalization_contribution_bps: int
    disapproval_contribution_bps: int
    attempt_risk_bps: int


def unrest_attempt_risk_bps(
    *, radicalization_bps: int, organization_bps: int, disapproval_bps: int
) -> UnrestAttemptRiskAssessment:
    """The popular-unrest channel's per-turn attempt risk -- pure, no RNG.

    `radicalization_bps`/`organization_bps`/`disapproval_bps` are population-share-weighted means
    over the current population groups (`population_weighted_mean_bps`), already bps (R8) -- no
    float involved anywhere. Radicalization only contributes once BOTH it is above threshold AND
    the population is organized enough to act on it (the excess is scaled by raw `organization_bps`,
    not threshold-gated itself, since organization is a capacity, not a trigger)."""
    radicalization_excess_bps = max(0, radicalization_bps - UNREST_RADICALIZATION_THRESHOLD_BPS)
    radicalization_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(radicalization_excess_bps * organization_bps, BPS_DENOMINATOR)
        * UNREST_RADICALIZATION_WEIGHT_BPS,
        BPS_DENOMINATOR,
    )
    disapproval_excess_bps = max(0, disapproval_bps - UNREST_DISAPPROVAL_THRESHOLD_BPS)
    disapproval_contribution_bps = trunc_div_toward_zero(
        disapproval_excess_bps * UNREST_DISAPPROVAL_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        BASE_UNREST_ATTEMPT_RISK_BPS
        + radicalization_contribution_bps
        + disapproval_contribution_bps
    )
    return UnrestAttemptRiskAssessment(
        radicalization_contribution_bps=radicalization_contribution_bps,
        disapproval_contribution_bps=disapproval_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_UNREST_ATTEMPT_RISK_BPS, total_bps)),
    )


def unrest_success_probability_bps(*, organization_bps: int, legitimacy_bps: int) -> int:
    """The popular-unrest channel's success probability, given an attempt occurred -- pure, no
    RNG. Failure means "unrest occurred but was contained": reported, no removal."""
    organization_contribution_bps = trunc_div_toward_zero(
        organization_bps * UNREST_SUCCESS_ORGANIZATION_WEIGHT_BPS, BPS_DENOMINATOR
    )
    legitimacy_contribution_bps = -trunc_div_toward_zero(
        legitimacy_bps * UNREST_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        UNREST_SUCCESS_BASE_BPS + organization_contribution_bps + legitimacy_contribution_bps
    )
    return max(0, min(MAX_UNREST_SUCCESS_PROBABILITY_BPS, total_bps))


# --- Gate 3C2: impeachment channel ---------------------------------------------------------

IMPEACHMENT_LEGITIMACY_THRESHOLD_BPS = 4_000
"""Below 40% legitimacy, impeachment becomes live."""
IMPEACHMENT_LEGITIMACY_SHORTFALL_WEIGHT_BPS = 2_000
IMPEACHMENT_OPPOSITION_THRESHOLD_BPS = 5_000
"""Opposition needs a real majority-adjacent bloc before this term contributes."""
IMPEACHMENT_OPPOSITION_WEIGHT_BPS = 1_500
IMPEACHMENT_JUDICIAL_REVIEW_SCALE_BPS: dict[JudicialReview, int] = {
    JudicialReview.NONE: 0,
    JudicialReview.WEAK: 5_000,
    JudicialReview.STRONG: 10_000,
}
"""Both attempt-risk contributions are scaled by this factor -- a genuine constitutional-axis
dependency: impeachment's mechanism (never its removal REASON, which is form-blind like every
other channel) depends on how much courts can actually constrain the other branches."""
MAX_IMPEACHMENT_ATTEMPT_RISK_BPS = 1_200

IMPEACHMENT_SUCCESS_BASE_BPS = 500
IMPEACHMENT_SUCCESS_OPPOSITION_WEIGHT_BPS = 4_000
IMPEACHMENT_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS = 3_000
MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS = 6_000


@dataclass(frozen=True, slots=True)
class ImpeachmentAttemptRiskAssessment:
    """Every named contribution behind the impeachment channel's attempt-risk figure."""

    legitimacy_contribution_bps: int
    opposition_contribution_bps: int
    attempt_risk_bps: int


def impeachment_attempt_risk_bps(
    *, opposition_seat_share_bps: int, legitimacy_bps: int, judicial_review: JudicialReview
) -> ImpeachmentAttemptRiskAssessment:
    """The impeachment channel's per-turn attempt risk -- pure, no RNG. Eligibility itself
    (`legislature != NONE`, `judicial_review != NONE`, `executive_selection != HEREDITARY`) is
    checked by the caller (`phases.py`), not here -- this function assumes the channel is
    eligible; an ineligible turn never calls it."""
    scale_bps = IMPEACHMENT_JUDICIAL_REVIEW_SCALE_BPS[judicial_review]
    legitimacy_shortfall_bps = max(0, IMPEACHMENT_LEGITIMACY_THRESHOLD_BPS - legitimacy_bps)
    legitimacy_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(
            legitimacy_shortfall_bps * IMPEACHMENT_LEGITIMACY_SHORTFALL_WEIGHT_BPS,
            BPS_DENOMINATOR,
        )
        * scale_bps,
        BPS_DENOMINATOR,
    )
    opposition_excess_bps = max(0, opposition_seat_share_bps - IMPEACHMENT_OPPOSITION_THRESHOLD_BPS)
    opposition_contribution_bps = trunc_div_toward_zero(
        trunc_div_toward_zero(
            opposition_excess_bps * IMPEACHMENT_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR
        )
        * scale_bps,
        BPS_DENOMINATOR,
    )
    total_bps = legitimacy_contribution_bps + opposition_contribution_bps
    return ImpeachmentAttemptRiskAssessment(
        legitimacy_contribution_bps=legitimacy_contribution_bps,
        opposition_contribution_bps=opposition_contribution_bps,
        attempt_risk_bps=max(0, min(MAX_IMPEACHMENT_ATTEMPT_RISK_BPS, total_bps)),
    )


def impeachment_success_probability_bps(
    *, opposition_seat_share_bps: int, legitimacy_bps: int
) -> int:
    """The impeachment channel's success probability, given a motion was brought -- pure, no
    RNG."""
    opposition_contribution_bps = trunc_div_toward_zero(
        opposition_seat_share_bps * IMPEACHMENT_SUCCESS_OPPOSITION_WEIGHT_BPS, BPS_DENOMINATOR
    )
    legitimacy_contribution_bps = -trunc_div_toward_zero(
        legitimacy_bps * IMPEACHMENT_SUCCESS_LEGITIMACY_DEFENSE_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        IMPEACHMENT_SUCCESS_BASE_BPS + opposition_contribution_bps + legitimacy_contribution_bps
    )
    return max(0, min(MAX_IMPEACHMENT_SUCCESS_PROBABILITY_BPS, total_bps))


# --- Gate 3C2: transition pressure ---------------------------------------------------------

TRANSITION_PRESSURE_DECAY_NUMERATOR = 1
TRANSITION_PRESSURE_DECAY_DENOMINATOR = 6
"""A constitutional shock decays 1/6 of its magnitude every turn (deliberately faster than
`political_memory.py`'s 1/8 relationship decay: a shock is meant to fade within about a year and a
half of turns, not linger as long as a bloc's personal grudge), with a minimum one-bps step for
any nonzero residual so it always terminates exactly rather than freezing forever -- the identical
shape to `simulation.political_memory.relationship_decay_bps`."""

AMENDMENT_PRESSURE_PER_AXIS_BY_DIFFICULTY_BPS: dict[AmendmentDifficulty, int] = {
    AmendmentDifficulty.SIMPLE_MAJORITY: 1_500,
    AmendmentDifficulty.SUPERMAJORITY: 2_500,
    AmendmentDifficulty.ENTRENCHED: 4_000,
}


@dataclass(frozen=True, slots=True)
class TransitionPressureResolution:
    """Every intermediate value behind this turn's closing `regime_transition_pressure_bps`, so
    the report can publish each one and a reader can re-derive the total without trusting it."""

    opening_bps: int
    decayed_bps: int
    added_bps: int
    uncapped_bps: int
    closing_bps: int


def _transition_pressure_decay_magnitude_bps(opening_bps: int) -> int:
    """The identical shape to `political_memory.relationship_decay_bps`: a proportional 1/6 step
    toward zero, with a minimum one-bps step for any nonzero residual so decay always terminates
    exactly rather than asymptotically approaching zero forever."""
    if opening_bps == 0:
        return 0
    magnitude = trunc_div_toward_zero(
        opening_bps * TRANSITION_PRESSURE_DECAY_NUMERATOR, TRANSITION_PRESSURE_DECAY_DENOMINATOR
    )
    return max(1, magnitude)


def transition_pressure_added_bps(*, difficulty: AmendmentDifficulty, axes_changed: int) -> int:
    """How much pressure a constitutional amendment that changed `axes_changed` axes (0 in Gate
    3C2, since `ConstitutionalAmendmentDecision` does not exist until Gate 3C3) adds this turn.
    Direction-blind by construction: never reads which way any axis moved, only that it moved and
    by how much of the difficulty-scaled per-axis unit -- the literal mechanism making
    liberalization and consolidation cost-symmetric."""
    if axes_changed <= 0:
        return 0
    return min(
        BPS_DENOMINATOR, AMENDMENT_PRESSURE_PER_AXIS_BY_DIFFICULTY_BPS[difficulty] * axes_changed
    )


def resolve_transition_pressure_bps(
    *, opening_pressure_bps: int, amendment_added_bps: int
) -> TransitionPressureResolution:
    """The ONE place `regime_transition_pressure_bps` is ever computed -- called once, from slot
    12, reading the turn's OPENING pressure value and (if a `ConstitutionalAmendmentDecision`
    passed or was decreed this turn) its added-pressure amount. Never split across two phase
    steps (R6)."""
    decay_bps = _transition_pressure_decay_magnitude_bps(opening_pressure_bps)
    uncapped_bps = opening_pressure_bps - decay_bps + amendment_added_bps
    closing_bps = max(0, min(BPS_DENOMINATOR, uncapped_bps))
    return TransitionPressureResolution(
        opening_bps=opening_pressure_bps,
        decayed_bps=decay_bps,
        added_bps=amendment_added_bps,
        uncapped_bps=uncapped_bps,
        closing_bps=closing_bps,
    )
