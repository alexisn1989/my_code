"""How committed political capital improves a legislative bloc's relationship with the government.

Given a bloc's current relationship and the capital committed to it this turn, this module answers
one question: **how many basis points does that relationship improve?**

No I/O, no randomness, no state mutation, no clock, no floating point. A plain function of its
arguments, in the same shape as `apportionment` and `legislative_voting`.

## The shape of the formula, and why

    gain = trunc(gap * capital / (HALF_GAP_CAPITAL + capital))     where gap = 10,000 - opening

It buys a **fraction of the remaining gap**, never a fixed number of basis points. That single
choice produces every property the design needs at once:

- It is **bounded without a clamp**: the fraction is strictly less than 1 for any finite capital,
  so `closing < RELATIONSHIP_CEILING_BPS` always. The clamp in the caller is a defence against a
  bypassed construction, not part of the arithmetic.
- It **diminishes on its own**: the gap shrinks every turn, so an identical commitment buys
  strictly fewer basis points each time. Nothing has to remember how much was already spent, which
  matters because remembering would mean new state that Phase 3B2A never reads back.
- A relationship can be **approached but never reached**. `+10,000` is unattainable in finitely
  many turns, so there is no "maxed out" bloc and no point at which investment becomes free.

`RELATIONSHIP_HALF_GAP_CAPITAL` is named for what it does: committing exactly that much closes half
the remaining gap. At 500, against `RELATIONSHIP_INVESTMENT_CAP = 200`, one turn closes at most
`200/700 = 2/7` of what is left.

## What is guaranteed, and what is deliberately not

The truthful list is shorter than it first appears, because integer truncation breaks two
properties the continuous function has. Both were claimed in an earlier draft and are withdrawn:

1. **Monotonic non-decreasing** in `political_capital`. Universal.
2. **Strictly below the remaining gap**: `0 <= gain < gap` whenever `gap > 0`. Universal.
3. **A smaller remaining gap never yields a larger gain** at fixed capital. Universal.
4. The **unrounded rational envelope** `gap*c/(H+c)` is concave, so it has diminishing marginal
   returns. True of the envelope -- stated *as* an envelope property.
5. The `1..200` cap prevents unlimited one-turn purchasing.
6. Repeated equal investments reduce the remaining gap, so successive turns buy strictly less.

**Not guaranteed, and not asserted anywhere:**

- *Strict* monotonicity at every integer step. For small gaps adjacent capital values tie: at a gap
  of 700 there are 16 tied steps in `[1, 200]`, and 910 is the smallest gap with none. That figure
  is a measured artefact of `H` and the cap, not a promise -- it is recorded in the tests as
  behaviour and must not be reintroduced as a threshold.
- *Discrete* concavity. The realised marginal gain oscillates across floor boundaries: at a gap of
  12,000 it rises at 46 of 198 steps (24, 24, 24, 23, 24 ...), and at a gap of 8,000 it goes
  15 -> 16 at c = 6. Only the envelope is concave.

## Government-form neutrality

No function here accepts a `ConstitutionState` or any constitutional enum, and this module does not
import `simulation.constitution` at all. A monarchy's blocs and a republic's blocs, holding
identical relationships, forgive identically -- the constitution decides *procedure*, never how a
caucus feels. Enforced structurally by `test_legislative_neutrality.py`, alongside
`apportionment` and `legislative_voting`.

## Not in Phase 3B2A

`relationship_gain_bps` never returns a negative value, because nothing decays yet. Relationship
decay, and automatic reactions to being bypassed by decree or to a policy a bloc dislikes, are
Phase 3B2B -- the phase that makes this quantity genuinely signed. Until then a relationship is a
ratchet, which is an interim limitation rather than a balance claim.
"""

from __future__ import annotations

from app.core.money import BPS_DENOMINATOR
from app.core.politics import RELATIONSHIP_INVESTMENT_CAP, trunc_div_toward_zero

RELATIONSHIP_CEILING_BPS = BPS_DENOMINATOR
"""The relationship scale's upper bound: +10,000 bps, a bloc fully aligned with the government.
Approached asymptotically, never reached -- see the module docstring."""

RELATIONSHIP_HALF_GAP_CAPITAL = 500
"""Committing exactly this much capital closes half the remaining gap.

Chosen by sweeping it against real scenario data rather than by intuition. On `deficit_demo`'s
cheapest bargaining target (opening relationship -2,000, a 162-point bargain), one 100-capital
investment moves the next turn's bargain to:

    H = 100 -> 42      far too strong; 300 capital once buys a permanently free budget
    H = 200 -> 82
    H = 300 -> 102
    H = 500 -> 122     selected
    H = 800 -> 135     too weak to be worth a decision

At 500 the relationship strategy is behind its baseline for seven consecutive resolved turns and
first becomes cheaper after resolved turn 8 -- roughly a two-year strategic horizon. That is
deliberate: relationship investment is meant to be a long game, and ignoring it entirely stays
viable, merely worse over time. A faster setting would also accelerate the improve-only ratchet
before Phase 3B2B introduces decay and adverse reactions to counterweight it.
"""


def relationship_gain_bps(*, opening_relationship_bps: int, political_capital: int) -> int:
    """The improvement `political_capital` buys against `opening_relationship_bps`.

    `political_capital` is **asserted** in `[1, RELATIONSHIP_INVESTMENT_CAP]` rather than clamped.
    `decisions.BlocInvestment` already rejects anything else at construction, so a value outside
    the band means those two have drifted apart -- and silently clamping is precisely how that
    drift would go unnoticed. Raising is the point.

    Returns `0` when the gap is already closed, and can also return `0` for a small gap that
    truncates away. Callers must treat "no applied change" as a decision to reject
    (`phases._validate_and_reserve_actions`), and must test the **computed gain** rather than
    `gap == 0`: at a gap of 100, one point of capital also buys nothing.
    """
    if not 1 <= political_capital <= RELATIONSHIP_INVESTMENT_CAP:
        raise ValueError(
            "political_capital committed to a bloc relationship must be in "
            f"[1, {RELATIONSHIP_INVESTMENT_CAP}], got {political_capital}; "
            "decisions.BlocInvestment is expected to have rejected this already"
        )
    gap = RELATIONSHIP_CEILING_BPS - opening_relationship_bps
    return trunc_div_toward_zero(
        gap * political_capital, RELATIONSHIP_HALF_GAP_CAPITAL + political_capital
    )
