"""What a party leader charges to back one proposal, and whether they will deal at all.

Pure formulas over metrics: no I/O, no randomness, no state mutation, no clock, no floating point --
the `government_survival.py` shape. Every function takes plain ints it declares itself and never a
`CharacterState`, because these are formulas over traits rather than lookups across containers. The
traits are read out of state in `phases.py`'s slot handlers, which is the same split
`government_survival` uses for the constitution.

**Named for the legislature, deliberately.** A later slice adds foreign negotiation, and a module
called `bargaining.py` with a `BargainOutcome` would collide with it the moment it lands -- not in
the type checker, which is the easy half, but conceptually, where two different mechanics would
answer to one name. Every public symbol here is prefixed accordingly. That matters more than it
looks: `CapitalExpenditureCategory.LEGISLATIVE_BARGAIN`'s value is serialised into `report_json` and
covered by the entry hash, so renaming it afterwards is a save-format change rather than a refactor.

**There is no offer.** The price is a fact about the counterparty in the opening state, derived here
and nowhere else, and a leader who will deal is paid exactly it. An earlier design let the player
name an offer and accepted anything at or above the price, which made the offer a free variable with
one optimal value -- and a second design that charged the offer did not fix it, because the price is
projected on `DecisionOptionsProjection.legislative_bargain_counterparties` and so the only rational
offer was still the displayed number. Both are gone: the player chooses whom to approach, not how
much to pay.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.politics import trunc_div_toward_zero

LEGISLATIVE_BARGAIN_BASE_PRICE = 60
"""What any leader charges before their own character is counted.

A GAME-BALANCE CHOICE, not a measurement, sized against the sinks that already exist: a decree is
250, an amendment by decree 400, a cabinet hire 120-300, and a scenario opens with 300-500 capital.
The band this produces across the shipped rosters is 105-113, so a bargain is affordable on its own
and genuinely competes with a cabinet appointment in the same turn.
"""

LEGISLATIVE_BARGAIN_INDEPENDENCE_PRICE_MAX = 90
"""What a maximally independent leader adds, linear in `independence`."""

LEGISLATIVE_BARGAIN_AMBITION_PRICE_MAX = 50
"""What a maximally ambitious leader adds, linear in `ambition`."""

LEGISLATIVE_BARGAIN_TRUST_DISCOUNT_MAX = 60
"""What maximal `personal_trust` takes off, linear.

The only term that lowers the price, and the only one the player can change: independence and
ambition are who somebody is, trust is what your record with them is worth. It is subtracted rather
than folded into a multiplier so the discount stays legible -- a player can see what a kept promise
bought.
"""

LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS = 2_000
"""Below this loyalty, a leader deals only if they trust the player anyway (see `will_deal`)."""

LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS = 5_000
"""The trust that makes a disloyal leader deal regardless.

Two conditions with different subjects, so the gate is not a second loyalty score: a leader who
despises the government will still do business with a player who has kept their word.
"""

LEGISLATIVE_ENDORSEMENT_BPS = 2_000
"""What a purchased endorsement adds to every bloc of the endorsed party, in every chamber.

**Measured, not chosen.** Sweeping every reachable proposal shape against all three shipped
scenarios shows an endorsement of 1,200 bps cannot change a single vote outcome through any
counterparty who would actually accept one -- it would have been purchasable and inert. The smallest
value that makes the one acceptable pivotal counterparty (`deficit_demo`'s `leader_independents`)
actually decisive is 1,600; 2,000 is that figure with margin, so the demonstration is not a knife
edge that any unrelated retune would break.

This is emphatically NOT bounded by `MAX_INFLUENCE_BPS`, and it must not be described as though it
were. That constant caps DIRECT bloc influence -- what one bloc's support can be moved by buying it.
An endorsement is a separate, party-level channel: it is not purchased per bloc, is not subject to
that cap, and combines with influence as an independent addend. Either channel can be pivotal on its
own; in the measured `deficit_demo` case, 200 capital of direct influence carries the chamber
unaided, and so does this endorsement. What actually bounds the pair is the existing `final` clamp,
which saturates their sum at `BPS_DENOMINATOR` like any other. No treasury money is spent by either:
the resource is political capital, which is a separate account from the fiscal one.
"""


@dataclass(frozen=True)
class LegislativeBargainAssessment:
    """What one leader's answer is, in the opening state, before anything is committed.

    `asking_price` is `None` exactly when `will_deal` is false. A leader who will not deal has no
    price -- not a high one -- and carrying a number here would let a refusal be rendered as a
    quotation, which is the counteroffer this design deliberately does not have. The same exclusivity
    is enforced on `LegislativeBargainReport` and on the API projection.
    """

    will_deal: bool
    asking_price: int | None

    def __post_init__(self) -> None:
        if self.will_deal and self.asking_price is None:
            raise ValueError("a willing counterparty must carry an asking price")
        if not self.will_deal and self.asking_price is not None:
            raise ValueError(
                f"an unwilling counterparty must carry no asking price, got {self.asking_price}"
            )


def asking_price_capital(
    *, independence_bps: int, ambition_bps: int, personal_trust_bps: int
) -> int:
    """The political capital this leader charges to back one proposal.

    `60 + ind*90//10_000 + amb*50//10_000 - trust*60//10_000`, floored at 1, in exact integers.
    `trunc_div_toward_zero` rather than `//` because that is the house rule everywhere; the two
    agree here, since every trait is bounded `ge=0`.

    `loyalty` is deliberately absent. It is the GATE (`will_deal`) and never the price: mixing it in
    would make a disloyal leader merely expensive, when the point is that some leaders cannot be
    bought at any figure and only a changed relationship opens them.

    The floor at 1 is reachable in principle -- maximal trust with no independence or ambition would
    price at `60 - 60 = 0` -- and exists so a bargain is always a real commitment. A price of zero
    would produce a ledger row that `StrictPoliticalCapitalCommitment` (`ge=1`) refuses to construct.
    """
    return max(
        1,
        LEGISLATIVE_BARGAIN_BASE_PRICE
        + trunc_div_toward_zero(
            independence_bps * LEGISLATIVE_BARGAIN_INDEPENDENCE_PRICE_MAX, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            ambition_bps * LEGISLATIVE_BARGAIN_AMBITION_PRICE_MAX, BPS_DENOMINATOR
        )
        - trunc_div_toward_zero(
            personal_trust_bps * LEGISLATIVE_BARGAIN_TRUST_DISCOUNT_MAX, BPS_DENOMINATOR
        ),
    )


def will_deal(*, loyalty_bps: int, personal_trust_bps: int) -> bool:
    """Whether this leader will do business with the player at all.

    False only when BOTH `loyalty < 2,000` and `personal_trust < 5,000`: a leader hostile to the
    government will still deal with a player whose word has been good. Because the two conditions
    have different subjects, and because `personal_trust` is the one trait a later slice moves, a
    leader who refuses today can become available later without their loyalty changing at all --
    which is the entire payoff of the trust layer.

    Every shipped opposition leader currently fails this gate, and every accept path runs through a
    confidence-and-supply party. That is a fact about the authored content, not a bug in the rule:
    `decree_state` in particular has no acceptable counterparty, which is a coherent statement about
    a decree state rather than a gap to be tuned away.
    """
    return not (
        loyalty_bps < LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS
        and personal_trust_bps < LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS
    )


def assess_legislative_bargain(
    *,
    loyalty_bps: int,
    independence_bps: int,
    ambition_bps: int,
    personal_trust_bps: int,
) -> LegislativeBargainAssessment:
    """The whole answer for one leader: will they deal, and for how much.

    The single entry point `phases.py` and `app.api` use, so the price a player is quoted, the price
    `/preview` reserves and the price the resolver charges are the same number by construction.

    `reconciliation.py` deliberately does NOT call this. It re-derives the gate and the price by
    transcribing the same formulas over the same constants, because a reconciliation check that
    calls the function which produced the report cannot fail when that function is wrong -- it would
    agree with the defect and certify it. Sharing the CONSTANTS is a different thing: a constant is
    one number both sides read, so a transcription error still surfaces. `tests/test_legislative_
    bargain.py` enforces that boundary with an AST scan rather than trusting this docstring.
    """
    if not will_deal(loyalty_bps=loyalty_bps, personal_trust_bps=personal_trust_bps):
        return LegislativeBargainAssessment(will_deal=False, asking_price=None)
    return LegislativeBargainAssessment(
        will_deal=True,
        asking_price=asking_price_capital(
            independence_bps=independence_bps,
            ambition_bps=ambition_bps,
            personal_trust_bps=personal_trust_bps,
        ),
    )
