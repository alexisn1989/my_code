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
from app.simulation.constitution import (
    AmendmentDifficulty,
    DecreeAuthority,
    ExecutiveSelection,
    JudicialReview,
    Legislature,
)

REQUIRED_ELECTION_SUPPORT_BPS = 5_000
LEGISLATIVE_SUPPORT_WEIGHT_BPS = 5_000
POPULATION_APPROVAL_WEIGHT_BPS = 4_000
LEGITIMACY_WEIGHT_BPS = 1_000
MAX_POLLING_UNCERTAINTY_SWING_BPS = 1_000
"""+/- 10 percentage points -- the widest a single seeded polling-uncertainty draw can move the
baseline support figure in either direction."""


def is_noncompetitive_constitution(
    *, executive_selection: ExecutiveSelection, decree_authority: DecreeAuthority
) -> bool:
    """Whether the constitution fails Phase 3C's minimum competitive-origin test."""
    return (
        executive_selection
        in (
            ExecutiveSelection.HEREDITARY,
            ExecutiveSelection.APPOINTED,
        )
        or decree_authority is not DecreeAuthority.NONE
    )


def is_competitive_elected_constitution(
    *,
    executive_selection: ExecutiveSelection,
    decree_authority: DecreeAuthority,
    national_election_interval_turns: int | None,
) -> bool:
    """Whether elections, executive selection, and decree power meet §5's victory shape."""
    return (
        executive_selection
        in (ExecutiveSelection.DIRECT_ELECTION, ExecutiveSelection.LEGISLATIVE_SELECTION)
        and decree_authority is DecreeAuthority.NONE
        and national_election_interval_turns is not None
    )


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


# --- Structural removal exposure: how much a government's FORM exposes it to violent removal --
#
# The one place government form enters the coup and popular-unrest channels. Everything else in
# this module that reads the constitution reads it for a *procedural* reason -- a scheduled
# election exists because of `national_election_interval_turns`, impeachment runs through courts
# and a legislature. This is the one genuinely structural claim: an executive that no electorate
# can remove, and that no other organ constrains, is more exposed to being removed by force.
#
# What it deliberately is NOT:
#
#   * It is not `is_noncompetitive_constitution` (above), and must never be replaced by it. That
#     helper answers Phase 3C's victory question and counts ANY non-NONE decree authority as
#     noncompetitive -- which makes all three shipped scenarios noncompetitive, two of them purely
#     because they author `emergency_only`. Emergency powers held by an accountable elected
#     government are not a dictatorship, and the weights below say so: they are worth 500 of a
#     possible 10,000.
#   * It is not a legitimacy judgement. Nothing here reaches `legitimacy.py`, whose neutrality is
#     structural (no function there accepts a constitutional type) and stays that way. A
#     dictatorship is not less *accepted* for being one; it is more exposed to a particular kind of
#     removal.
#   * It is not derived from a scenario's name, its display labels, or a persisted regime-type
#     field. There is no such field, and adding one would be a second source of truth for something
#     the axes already say.
#
# The weights are GAME-BALANCE CHOICES. They are not measurements of real countries and were not
# supplied by anyone; they are the smallest set that separates the cases the design has to tell
# apart, and they are meant to be re-tuned from calibration rather than defended as facts.

UNELECTED_EXECUTIVE_EXPOSURE_BPS = 4_000
"""No electorate can remove this executive at all (`HEREDITARY`/`APPOINTED`). The single largest
component, because it is the difference the whole feature exists to express: an electoral
government under strain still has a scheduled, lawful way out, and that is exactly the pressure
valve a coup or an uprising substitutes for."""
ELECTED_WITHOUT_SCHEDULED_ELECTION_EXPOSURE_BPS = 2_000
"""Elected in principle, with no election actually scheduled (`national_election_interval_turns`
is `None`). Half the unelected weight rather than zero: the office is answerable in form but the
answering never comes due."""

UNLIMITED_DECREE_EXPOSURE_BPS = 3_000
"""The executive can legislate alone. Constraint by other organs is gone, not merely weakened."""
EMERGENCY_DECREE_EXPOSURE_BPS = 500
"""Emergency powers, and nothing more. Deliberately small: this is the component that must NOT be
able to make an accountable electoral government read as a dictatorship."""

NO_LEGISLATURE_EXPOSURE_BPS = 2_000
"""No chamber exists to constrain the executive. Note this is never a standalone case -- rule C10
(`constitution.first_constitutional_violation`) requires `decree_authority='unlimited'` wherever
the legislature is `none`, so a legislature-less constitution always carries the decree weight
too."""

NO_JUDICIAL_REVIEW_EXPOSURE_BPS = 1_000
WEAK_JUDICIAL_REVIEW_EXPOSURE_BPS = 500
"""Courts as the last remaining constraint. The smallest components, because a court alone rarely
stops an executive that has already lost both the electorate and the legislature -- but a
constrained monarchy keeps its courts, and this is part of what distinguishes it from personal
rule."""

MAX_STRUCTURAL_EXPOSURE_BPS = 10_000
"""The components sum to exactly this at the unrestricted-personal-rule endpoint (4,000 + 3,000 +
2,000 + 1,000), so the clamp below is DEFENSIVE, not load-bearing -- the same property
`coup_success_probability_bps`'s 3,500-of-7,000 headroom has, and pinned by a test for the same
reason: a future component that silently starts saturating the scale would stop being visible in
the total."""

COUP_STRUCTURAL_WEIGHT_BPS = 400
"""Full exposure adds 400 bps (4 percentage points) to the coup channel's per-turn attempt risk,
against a base of 8 and a cap of 2,500. Sized so an unaccountable government faces a genuinely
different threat level while staying far below the cap -- structure raises the odds, it does not
decide the outcome, and the conditional success formula is untouched."""
UNREST_STRUCTURAL_WEIGHT_BPS = 300
"""The same idea on the narrower unrest scale (base 15, cap 1,500). Lower than the coup weight
because an unaccountable executive is most directly exposed to the armed institution closest to
it; popular removal still depends mostly on how radicalized and organized the population is,
which the existing terms already carry."""


@dataclass(frozen=True, slots=True)
class StructuralExposureAssessment:
    """Every named component behind `exposure_bps`, so a report can publish the total and a reader
    can re-derive it from the constitution without trusting the engine that produced it."""

    executive_accountability_exposure_bps: int
    decree_authority_exposure_bps: int
    legislature_exposure_bps: int
    judicial_review_exposure_bps: int
    exposure_bps: int


def structural_removal_exposure_bps(
    *,
    executive_selection: ExecutiveSelection,
    decree_authority: DecreeAuthority,
    legislature: Legislature,
    judicial_review: JudicialReview,
    national_election_interval_turns: int | None,
) -> StructuralExposureAssessment:
    """How much this constitution's SHAPE exposes its executive to violent removal, in bps.

    Two orthogonal questions, both answered from axes that already exist:

    1. **Can voters remove this executive?** `HEREDITARY`/`APPOINTED` selection means no; an
       elected selection with no scheduled election means not in practice; an elected selection
       with a scheduled interval means yes, and contributes nothing.
    2. **Is the executive constrained by other organs?** Decree authority, whether a legislature
       exists at all, and how strong judicial review is.

    Accepts plain enums and an `int | None`, never a `ConstitutionState` -- the same split every
    other function in this module keeps, so `phases.py` stays the only place that reads the
    constitution object itself.

    Returns each component separately as well as the clamped total. The components are summed
    once and clamped once; there is no per-component rounding, because every component is a
    literal constant.
    """
    if executive_selection in (ExecutiveSelection.HEREDITARY, ExecutiveSelection.APPOINTED):
        executive_accountability_exposure_bps = UNELECTED_EXECUTIVE_EXPOSURE_BPS
    elif national_election_interval_turns is None:
        executive_accountability_exposure_bps = ELECTED_WITHOUT_SCHEDULED_ELECTION_EXPOSURE_BPS
    else:
        executive_accountability_exposure_bps = 0

    if decree_authority is DecreeAuthority.UNLIMITED:
        decree_authority_exposure_bps = UNLIMITED_DECREE_EXPOSURE_BPS
    elif decree_authority is DecreeAuthority.EMERGENCY_ONLY:
        decree_authority_exposure_bps = EMERGENCY_DECREE_EXPOSURE_BPS
    else:
        decree_authority_exposure_bps = 0

    legislature_exposure_bps = NO_LEGISLATURE_EXPOSURE_BPS if legislature is Legislature.NONE else 0

    if judicial_review is JudicialReview.NONE:
        judicial_review_exposure_bps = NO_JUDICIAL_REVIEW_EXPOSURE_BPS
    elif judicial_review is JudicialReview.WEAK:
        judicial_review_exposure_bps = WEAK_JUDICIAL_REVIEW_EXPOSURE_BPS
    else:
        judicial_review_exposure_bps = 0

    total_bps = (
        executive_accountability_exposure_bps
        + decree_authority_exposure_bps
        + legislature_exposure_bps
        + judicial_review_exposure_bps
    )
    return StructuralExposureAssessment(
        executive_accountability_exposure_bps=executive_accountability_exposure_bps,
        decree_authority_exposure_bps=decree_authority_exposure_bps,
        legislature_exposure_bps=legislature_exposure_bps,
        judicial_review_exposure_bps=judicial_review_exposure_bps,
        exposure_bps=min(MAX_STRUCTURAL_EXPOSURE_BPS, total_bps),
    )


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
    structural_contribution_bps: int
    attempt_risk_bps: int


def coup_attempt_risk_bps(
    *,
    military_loyalty_bps: int,
    military_power_bps: int,
    legitimacy_bps: int,
    opposition_seat_share_bps: int | None,
    transition_pressure_bps: int,
    structural_exposure_bps: int,
) -> CoupAttemptRiskAssessment:
    """The coup channel's per-turn attempt risk -- pure, no RNG. `opposition_seat_share_bps=None`
    (no legislature at all) contributes nothing from that term, the same "nothing to read"
    treatment `election_baseline_support_bps` gives a missing legislature.

    `structural_exposure_bps` comes from `structural_removal_exposure_bps` above and is the ONLY
    route by which government form reaches this figure. It is a separate term from
    `transition_pressure_bps` and cannot double-count it: exposure is a function of the
    constitution's axes as they now stand, pressure is a decaying memory of having recently
    changed them. A government that amended nothing has pressure 0 and whatever exposure its
    shape implies; one that liberalized last turn carries pressure while its exposure has already
    fallen."""
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
    structural_contribution_bps = trunc_div_toward_zero(
        structural_exposure_bps * COUP_STRUCTURAL_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        BASE_COUP_ATTEMPT_RISK_BPS
        + loyalty_contribution_bps
        + legitimacy_contribution_bps
        + opposition_contribution_bps
        + pressure_contribution_bps
        + structural_contribution_bps
    )
    # The structural term joins the sum BEFORE the clamp, exactly like every other contribution.
    # That is what makes the cap behave unchanged: a risk already saturated at the maximum does
    # not move when structure is added, so "greater or equal, never lower" holds everywhere while
    # "strictly greater" holds only below the cap.
    return CoupAttemptRiskAssessment(
        loyalty_contribution_bps=loyalty_contribution_bps,
        legitimacy_contribution_bps=legitimacy_contribution_bps,
        opposition_contribution_bps=opposition_contribution_bps,
        transition_pressure_contribution_bps=pressure_contribution_bps,
        structural_contribution_bps=structural_contribution_bps,
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
    structural_contribution_bps: int
    attempt_risk_bps: int


def unrest_attempt_risk_bps(
    *,
    radicalization_bps: int,
    organization_bps: int,
    disapproval_bps: int,
    structural_exposure_bps: int,
) -> UnrestAttemptRiskAssessment:
    """The popular-unrest channel's per-turn attempt risk -- pure, no RNG.

    `radicalization_bps`/`organization_bps`/`disapproval_bps` are population-share-weighted means
    over the current population groups (`population_weighted_mean_bps`), already bps (R8) -- no
    float involved anywhere. Radicalization only contributes once BOTH it is above threshold AND
    the population is organized enough to act on it (the excess is scaled by raw `organization_bps`,
    not threshold-gated itself, since organization is a capacity, not a trigger).

    `structural_exposure_bps` enters exactly as it does on the coup channel: a population with no
    lawful way to change its government is likelier to try an unlawful one. It raises how often
    unrest is ATTEMPTED and never how often it succeeds -- `unrest_success_probability_bps` below
    is untouched, so where organization is low enough that success is 0, more structural exposure
    produces more attempts and still no removals."""
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
    structural_contribution_bps = trunc_div_toward_zero(
        structural_exposure_bps * UNREST_STRUCTURAL_WEIGHT_BPS, BPS_DENOMINATOR
    )
    total_bps = (
        BASE_UNREST_ATTEMPT_RISK_BPS
        + radicalization_contribution_bps
        + disapproval_contribution_bps
        + structural_contribution_bps
    )
    return UnrestAttemptRiskAssessment(
        radicalization_contribution_bps=radicalization_contribution_bps,
        disapproval_contribution_bps=disapproval_contribution_bps,
        structural_contribution_bps=structural_contribution_bps,
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
