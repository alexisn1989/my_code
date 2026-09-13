"""What a foreign counterpart will give the player, and how much of their pool it costs.

Pure formulas over metrics: no I/O, no randomness, no state mutation, no clock, no floating point --
the `government_survival.py` / `legislative_bargaining.py` shape. Every function takes plain ints it
declares itself and never a state model; the traits, the standing and the remaining pool are read
out of state in `phases.py`'s slot handlers.

**This module never reads `war_capability_bps`, and must never import `foreign_conflict` or
`government_survival`.** That fence is not stylistic. `ForeignProfileState.war_capability_bps` is
documented as an abstract capability "used ONLY for non-player conflict progression", and it is
already fenced away from the player's military and from the coup/unrest formulas by AST scans. Aid
is a diplomatic fact about a relationship, not a military one: letting a counterpart's war-making
capacity decide how generous they are would silently couple two systems the repository has gone to
some trouble to keep apart. `tests/test_foreign_assistance.py` asserts the fence with its own AST
scan rather than trusting this paragraph.

**The foreign minister raises the fraction; they never unlock the grant.** A government with no
foreign minister can still receive aid and simply receives less. That is what makes `deficit_demo`'s
vacant post a measurable difference rather than a wall -- and it is why `holder_competence_bps`'s
"vacant, unmodelled and not-yet-effective all return 0" collapse is exactly the right input here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.money import BPS_DENOMINATOR, Money
from app.core.politics import trunc_div_toward_zero

FOREIGN_ASSISTANCE_BASE_SHARE_BPS = 1_000
"""The share of a counterpart's REMAINING pool a bare request draws, before anything is counted.

A GAME-BALANCE CHOICE, not a measurement. 10% means a pool supports several approaches before it is
exhausted, so "this counterpart is nearly tapped out" becomes a state a player can reach and read,
rather than a cliff they fall off in one turn.
"""

FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS = 1_200
"""What maximal `personal_trust` in the player adds to that share.

The largest single term, and the only one the player's own conduct moves. It is additive rather than
multiplicative so the contribution stays legible: a kept promise buys a visible, statable amount.
"""

FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS = 800
"""What a maximal bilateral standing adds. Standing is the relationship between STATES; trust is
between a counterpart and the player personally, and the two are deliberately separate inputs with
separate weights -- a well-regarded country whose leader distrusts the player is representable, and
so is the reverse."""

FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS = 600
"""What a maximally competent serving foreign minister adds.

Smaller than trust and standing on purpose: a good diplomat improves terms, they do not substitute
for a relationship. Read through `cabinet.holder_competence_bps`, so the effectivity rule is applied
exactly once and a minister appointed in the same decision set contributes nothing.
"""

FOREIGN_ASSISTANCE_INDEPENDENCE_PENALTY_MAX_BPS = 700
"""What a maximally independent counterpart withholds. The mirror of the bargaining module's
independence term: autonomy makes somebody harder to move, whichever direction they are being
moved in."""

MINIMUM_ASSISTANCE_STANDING_BPS = -4_000
"""Below this bilateral standing, a counterpart refuses outright and no share is computed.

Signed, and deliberately well below zero: a merely cool relationship still yields something, and
only real hostility closes the channel. That keeps refusal a state the player has to earn rather
than a default.
"""


class ForeignAssistanceRefusal(StrEnum):
    """Why a structurally valid request yields nothing.

    Both are RESOLVED OUTCOMES, not submission rejections -- the same distinction the legislative
    bargain draws, and for the same reason: a refusal has a report row of its own, so it is
    recordable, and `standing_bps` and the pool both move over a campaign, so today's refusal is not
    a permanent structural fact.
    """

    HOSTILE = "foreign_assistance_counterpart_is_hostile"
    POOL_EXHAUSTED = "foreign_assistance_pool_exhausted"


@dataclass(frozen=True)
class ForeignAssistanceAssessment:
    """One counterpart's answer, computed once from opening state and never recomputed.

    `granted` is `0` exactly when `refusal` is set. Threading both rather than a bare int keeps the
    two reasons for zero distinguishable all the way to the report: a hostile counterpart and an
    exhausted pool look identical in the treasury and are completely different politically.
    """

    granted: Money
    share_bps: int
    """The share of the remaining pool that was applied, `0` on a refusal. Stored so the report row
    can replay its own arithmetic without recomputing the formula."""
    refusal: ForeignAssistanceRefusal | None

    def __post_init__(self) -> None:
        if self.refusal is not None and self.granted != 0:
            raise ValueError(f"a refused request must grant nothing, got {self.granted}")
        if self.refusal is None and self.granted <= 0:
            raise ValueError(
                f"an accepted request must grant a positive amount, got {self.granted}"
            )


def remaining_pool(*, capacity: Money, drawn: Money) -> Money:
    """What this counterpart can still give.

    Derived, never stored: `capacity` is a fact about the counterpart and `drawn` a fact about this
    player's dealings with them, so a third stored field could disagree with the pair. Clamped at
    zero rather than allowed negative -- over-drawing is refused before it can happen, and a
    negative pool would be a bug wearing a value's clothes.
    """
    return max(0, capacity - drawn)


def assistance_share_bps(
    *,
    personal_trust_bps: int,
    standing_bps: int,
    foreign_minister_competence_bps: int,
    independence_bps: int,
) -> int:
    """The share of the remaining pool this request draws, in basis points.

    Four additive terms over `FOREIGN_ASSISTANCE_BASE_SHARE_BPS`, three raising it and one
    withholding. `standing_bps` is SIGNED, so a poor-but-not-hostile relationship subtracts; the
    result is floored at 1 bps so an accepted request always transfers something rather than
    resolving as a grant of nothing, which would be indistinguishable from a refusal in the
    treasury.

    `trunc_div_toward_zero` throughout because that is the house rule, and it matters here: with a
    negative `standing_bps` the sign of the division is exactly what `//` would get wrong.
    """
    return max(
        1,
        FOREIGN_ASSISTANCE_BASE_SHARE_BPS
        + trunc_div_toward_zero(
            personal_trust_bps * FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            standing_bps * FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            foreign_minister_competence_bps * FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS,
            BPS_DENOMINATOR,
        )
        - trunc_div_toward_zero(
            independence_bps * FOREIGN_ASSISTANCE_INDEPENDENCE_PENALTY_MAX_BPS, BPS_DENOMINATOR
        ),
    )


def assess_foreign_assistance(
    *,
    personal_trust_bps: int,
    standing_bps: int,
    foreign_minister_competence_bps: int,
    independence_bps: int,
    capacity: Money,
    drawn: Money,
) -> ForeignAssistanceAssessment:
    """The whole answer for one counterpart: will they give, and how much.

    The single entry point `phases.py` and `app.api` use, so the figure a player is shown, the
    figure `/preview` estimates and the figure the resolver transfers are the same number by
    construction.

    Order matters and is fixed: hostility is checked before the pool, because a counterpart who will
    not deal at all should be reported as hostile rather than as merely out of money -- those are
    different political facts and a player can act on only one of them.

    **`POOL_EXHAUSTED` means the pool is EMPTY, and nothing else.** An earlier version also returned
    it when a positive pool was small enough that the proportional share truncated to zero. That was
    a false report -- the counterpart still had money -- and it was absorbing: a pool below
    `10_000 // share` could never be drawn again, so authored capacity became permanently
    unreachable while the report claimed it was spent. The floor is applied to the GRANT instead,
    inside the `min`, so a willing counterpart with anything left always transfers between `1` and
    the whole remaining pool, and a small pool drains a unit at a time until it is genuinely zero.

    `reconciliation.py` deliberately does NOT call this. Group 59 transcribes the same formulas over
    the same constants, because a check that calls the function which produced the report cannot
    fail when that function is wrong. `tests/test_foreign_assistance.py` enforces that with an AST
    allowlist scan.
    """
    if standing_bps < MINIMUM_ASSISTANCE_STANDING_BPS:
        return ForeignAssistanceAssessment(
            granted=0, share_bps=0, refusal=ForeignAssistanceRefusal.HOSTILE
        )
    pool = remaining_pool(capacity=capacity, drawn=drawn)
    if pool <= 0:
        # `remaining_pool` clamps at zero, so this condition IS "the pool is empty" -- written `<= 0`
        # only so a negative can never slip past into the share arithmetic.
        return ForeignAssistanceAssessment(
            granted=0, share_bps=0, refusal=ForeignAssistanceRefusal.POOL_EXHAUSTED
        )
    share = assistance_share_bps(
        personal_trust_bps=personal_trust_bps,
        standing_bps=standing_bps,
        foreign_minister_competence_bps=foreign_minister_competence_bps,
        independence_bps=independence_bps,
    )
    granted = min(pool, max(1, trunc_div_toward_zero(pool * share, BPS_DENOMINATOR)))
    return ForeignAssistanceAssessment(granted=granted, share_bps=share, refusal=None)
