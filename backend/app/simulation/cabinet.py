"""Who holds a cabinet post, what their competence is worth, and what hiring them costs.

Pure reads over already-parsed state: no I/O, no randomness, no mutation, no floating point. The
module exists so that the two places which need the answer -- `phases.py`, which computes a turn,
and `reconciliation.py`, which re-derives it from a save -- ask exactly the same question of the
same state and cannot drift. A second implementation of "is this appointment effective yet?" is
precisely the kind of duplicated rule the reconciliation layer exists to catch, so there is one.

Unlike `government_survival.py`, these functions do accept state models. They are lookups across
two containers (`CabinetState.offices` and `WorldState.characters`), not formulas over metrics, and
threading a pre-flattened mapping through every caller would move the lookup rule into the callers
-- which is the drift this module prevents. `military.py` sets the same precedent.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.money import BPS_DENOMINATOR
from app.core.politics import trunc_div_toward_zero
from app.simulation.state import (
    CabinetPost,
    CabinetState,
    CharacterState,
    PlayerCountryRef,
    StrictCharacterId,
)


def effective_holder_id(
    *, cabinet: CabinetState | None, post: CabinetPost, resolving_turn: int
) -> StrictCharacterId | None:
    """The character actually doing `post`'s job on `resolving_turn`, or `None`.

    `None` covers three genuinely different situations that all mean the same thing to a consumer
    -- no cabinet is modelled, the post is vacant, or the holder was appointed too recently to have
    started -- and deliberately does not distinguish them, because a bonus of nothing is a bonus of
    nothing. Anything that needs the difference (a UI explaining *why* there is no bonus) reads the
    cabinet directly.

    The timing rule lives here and nowhere else: a holder contributes if and only if
    `effective_from_turn <= resolving_turn`. An appointment resolved on turn `t` is stored at
    `t + 1`, so it never supplies the turn that hired it, and appointing three people to the same
    post within one turn still yields whatever the OPENING state had.
    """
    if cabinet is None:
        return None
    appointment = cabinet.offices.get(post)
    if appointment is None:
        return None
    if appointment.effective_from_turn > resolving_turn:
        return None
    return appointment.character_id


def holder_competence_bps(
    *,
    cabinet: CabinetState | None,
    characters: dict[StrictCharacterId, CharacterState],
    post: CabinetPost,
    resolving_turn: int,
) -> int:
    """`post`'s serving holder's competence on `resolving_turn`, or `0` when nobody is serving.

    `0` is the correct answer for a vacant post and for an utterly incompetent holder alike: both
    contribute nothing, and collapsing them keeps every consumer free of a special case. It is also
    what makes the office bonuses safely additive -- a government with no cabinet at all computes
    exactly the figures it computed before this layer existed.

    A holder id that is not in `characters` also yields `0` rather than raising.
    `simulation.invariants` (`cabinet_holder_unknown`) rejects that state before and after every
    resolution, so this is unreachable in a valid game; it is guarded anyway because this module is
    also read by reconciliation, which must produce a problem string for a tampered save rather
    than an exception.
    """
    holder_id = effective_holder_id(cabinet=cabinet, post=post, resolving_turn=resolving_turn)
    if holder_id is None:
        return 0
    holder = characters.get(holder_id)
    return 0 if holder is None else holder.competence


CABINET_APPOINTMENT_BASE_COST = 120
"""What any appointment costs before the appointee's own demands are counted.

A GAME-BALANCE CHOICE, not a measurement, sized against the sinks that already exist: a decree is
250, an amendment by decree 400, and a scenario opens with 300-500 capital. A cheap hire is
affordable in the turn it is wanted; nobody can staff a government for free.
"""

CABINET_INDEPENDENCE_SURCHARGE_MAX = 180
"""What a maximally independent appointee adds on top, linear in `independence`.

This is the concession the mandate calls for: capable independent people generally demand more.
It is `independence` that is read and never `competence`, so the price is what a person DEMANDS
rather than what they are worth -- which is what keeps a cheap effective hire representable and
stops cost from becoming a second competence score.
"""

MINIMUM_ACCEPTANCE_LOYALTY_BPS = 5_000
"""Below this, a candidate's willingness depends on the government's legitimacy (see
`appointment_refusal`). At or above it, they serve whoever asks."""

GOVERNMENT_LEGITIMACY_FLOOR_BPS = 6_500
"""The legitimacy a government must have before a low-loyalty candidate will attach themselves to
it. Deliberately above every shipped scenario's authored 6,000 except `tiny_valid`'s 7,000, so both
sides of the rule are reachable from content rather than only from constructed states."""

FOREIGN_MINISTRY_AMBITION_CEILING_BPS = 8_000
"""Above this, a candidate will not take the foreign ministry -- the junior chair is beneath them.
They will still take the chief-of-staff post, which is what makes the refusal POST-specific rather
than a second willingness score."""


class CabinetRefusal(StrEnum):
    """Why one named person will not take one named post, right now.

    Values are the stable codes `app.api.decision_preflight` reports and slot 1 names in its
    rejection message. They are per-`(post, candidate)` and INTRINSIC: each is a fact about this
    person, this post and this state, true no matter what else the decision set contains. Failures
    that depend on the whole decision -- one person ending up in two posts, or the total commitment
    exceeding opening capital -- are deliberately NOT here, because a candidate cannot carry them
    without asserting a refusal that is not true of the candidate.
    """

    LEADS_A_PARTY = "cabinet_character_leads_a_party"
    LOW_LEGITIMACY = "cabinet_candidate_refuses_low_legitimacy"
    THIS_POST = "cabinet_candidate_refuses_this_post"


def appointment_cost_capital(*, independence_bps: int) -> int:
    """The political capital `independence_bps` worth of demands costs to satisfy.

    `120 + independence_bps * 180 // 10_000` in exact integers, so independence 0 / 5,000 / 10,000
    costs exactly 120 / 210 / 300. `trunc_div_toward_zero` rather than `//` because that is the
    house rule everywhere; the two agree here, since `independence_bps` is bounded `ge=0`.
    """
    return CABINET_APPOINTMENT_BASE_COST + trunc_div_toward_zero(
        independence_bps * CABINET_INDEPENDENCE_SURCHARGE_MAX, BPS_DENOMINATOR
    )


def appointment_refusal(
    *, character: CharacterState, post: CabinetPost, legitimacy_bps: int
) -> CabinetRefusal | None:
    """Why `character` would refuse `post` under a government at `legitimacy_bps`, or `None`.

    Three rules, in a fixed order so the reported reason never depends on evaluation accident:

    1. A party leader is not appointable at all. Their standing with the government is the
       legislative bloc layer's business; letting one also hold a cabinet post would give the
       engine two independent models of the same person's relationship to the player.
    2. A candidate refuses outright when `loyalty < MINIMUM_ACCEPTANCE_LOYALTY_BPS` **and**
       `legitimacy_bps < GOVERNMENT_LEGITIMACY_FLOOR_BPS`. A low-loyalty person will serve a
       legitimate government out of careerism; they will not attach themselves to a weak one. Two
       conditions with different subjects, so the same candidate accepts in one state and refuses
       in another -- and since legitimacy moves during play, a refusal can become an acceptance
       inside a single campaign.
    3. Only then, the post-specific rule: too much ambition for the foreign ministry.

    Rule 2 precedes rule 3 deliberately. Somebody who will not serve this government at all is not
    usefully told that they dislike one particular chair.

    **This is asked when an appointment is MADE. It never re-assesses a sitting holder.** A fall in
    legitimacy does not empty the cabinet; resignation is a different mechanic and is not modelled
    here. `decree_state` relies on exactly that: it seats a foreign minister whose loyalty is 3,400
    at legitimacy 6,000, and he keeps serving although the same person would refuse a fresh
    appointment there.
    """
    if character.party_id is not None:
        return CabinetRefusal.LEADS_A_PARTY
    if (
        character.loyalty < MINIMUM_ACCEPTANCE_LOYALTY_BPS
        and legitimacy_bps < GOVERNMENT_LEGITIMACY_FLOOR_BPS
    ):
        return CabinetRefusal.LOW_LEGITIMACY
    if (
        post is CabinetPost.FOREIGN_MINISTER
        and character.ambition > FOREIGN_MINISTRY_AMBITION_CEILING_BPS
    ):
        return CabinetRefusal.THIS_POST
    return None


def is_domestic_to(*, character: CharacterState, country_id: str) -> bool:
    """Whether `character` is this country's own person, and therefore appointable by it.

    One definition, used by slot 1's rejection, the preflight's code, the API's candidate listing
    and the `cabinet_holder_not_of_this_country` invariant -- so "a government may only appoint its
    own people" cannot mean four subtly different things.
    """
    return (
        isinstance(character.affiliation, PlayerCountryRef)
        and character.affiliation.country_id == country_id
    )
