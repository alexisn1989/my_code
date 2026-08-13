"""Strict integer types for bounded political metrics.

Legitimacy is neither money (`app.core.money`) nor a physical or real
production quantity (`app.core.quantity`) — it is a bounded measure of how
accepted a government's authority currently is. Distinct concepts get distinct
aliases rather than one generic "bounded metric" type, so a field's annotation
alone states what kind of number it holds. That is the same rule that kept
`RealOutput` distinct from `Money` in Phase 2B1 and `ResourceQuantity` distinct
from both in Phase 2C1.

**Four concepts this module deliberately keeps apart** (Phase 3A, ADR 0009):

- *Constitutional structure* — how authority is legally organised
  (`simulation.constitution`). Says nothing about acceptance.
- *Constitutional-order support* — scenario-authored public acceptance of that
  order, the value legitimacy drifts toward. Authored, never derived from the
  form of government.
- *Legitimacy* — how accepted authority actually is right now. Not popularity,
  not approval, not military loyalty, not political capital.
- *Political capital* — a bounded, spendable governing resource.

Phase 0's `money.clamp01_100` mentions "legitimacy" in its docstring and uses
runtime floats; it predates the strict-integer discipline, is referenced
nowhere, and is superseded by the integer basis-point aliases below.

Targets Python 3.11, so this uses `TypeAlias` (PEP 613) rather than the
`type X = ...` statement introduced in Python 3.12 (PEP 695).
"""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field

from app.core.money import BPS_DENOMINATOR

# Pydantic's `strict=True` on an `int`-typed field rejects bool, whole-number
# floats, numeric strings, NaN, and +/-inf — verified for `StrictMoney` in
# `test_money.py` and re-verified for these aliases in `test_politics_types.py`.

LEGITIMACY_MIN_BPS = 0
"""The floor of the legitimacy scale. A government at 0 is entirely unaccepted, which is a
constrained state, not a removal condition — removal is Phase 3C."""

LEGITIMACY_MAX_BPS = BPS_DENOMINATOR
"""The ceiling of the legitimacy scale: 10,000 bps == 100%."""


StrictLegitimacyBps: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""How accepted the government's authority currently is, in basis points (0-10,000).

Explicitly NOT popularity, NOT per-group approval, NOT military or institutional loyalty, NOT
political capital, and — the load-bearing guarantee of Phase 3A — NOT derived from the form of
government. Nothing in `simulation.legitimacy` accepts a constitutional type, so a monarchy and a
democracy with the same authored order support and the same economic observations produce the same
legitimacy. See `docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`.
"""

StrictSignedBps: TypeAlias = Annotated[int, Field(strict=True)]
"""An **unbounded** signed basis-point quantity: a raw rate of change, or any uncapped intermediate
derived directly from one.

Deliberately carries no range constraint, because the arithmetic genuinely produces values outside
the legitimacy scale. A previous-turn output baseline of 1 rising to 3 is a `+20,000 bps` change,
and a hundredfold rebound is `+9,999,990,000`; typing those `StrictSignedLegitimacyBps` would reject
values that are arithmetically correct. The negative direction happens to fit — a complete collapse
to zero output is exactly `-10,000 bps`, since output cannot fall below nothing — but a type must be
symmetric about what the formula can actually produce, not about what looks tidy.

Only `strict=True` applies, which still rejects bool, whole-number floats, numeric strings, NaN and
+/-inf. The bound arrives later, as an explicit and independently re-derivable clamp in
`simulation.legitimacy`, which is stronger than a type bound: a validator can tell a correctly
capped value from an uncapped one, whereas a type can only refuse to hold it.
"""

StrictSignedLegitimacyBps: TypeAlias = Annotated[
    int, Field(strict=True, ge=-BPS_DENOMINATOR, le=BPS_DENOMINATOR)
]
"""A legitimacy *change* or *contribution* that the formula provably keeps within the scale.

Separate from `StrictLegitimacyBps` because a level and a delta are different quantities: a level
can never be negative, a delta routinely is. Used **only** where a bound is genuinely imposed by the
arithmetic itself — an unemployment change (a difference of two `StrictBps` values), a contribution
that is a fraction of a within-scale gap, or a value the formula has already clamped. Anything
upstream of such a bound uses `StrictSignedBps` instead.

The bound is the full scale rather than a per-turn cap, so a report field can hold any contribution
reachable before clamping and the clamp stays an explicit, re-derivable step rather than something
the type silently performs.
"""


PoliticalCapital: TypeAlias = int
"""A quantity of political capital, for plain function signatures (mirrors `Money`/`RealOutput`)."""

StrictPoliticalCapital: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A nonnegative amount of political capital — a bounded, spendable governing resource.

A named integer count, deliberately not a basis-point rate: political capital is a stock of
governing capacity, not a percentage of anything, and giving it a bps type would invite treating it
as one. Nothing spends it in Phase 3A (there is no legislature, faction or reform system yet to
consume it honestly); expenditure begins in Phase 3B.
"""

StrictPoliticalCapitalCapacity: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""The maximum political capital a government can hold. Strictly positive: a government with zero
capacity to act could never regenerate and would be permanently unable to govern, which is a
removal condition — and removal is Phase 3C, not this phase."""


# --- Phase 3B1: legislative composition -------------------------------------

StrictRelationshipBps: TypeAlias = Annotated[
    int, Field(strict=True, ge=-BPS_DENOMINATOR, le=BPS_DENOMINATOR)
]
"""How a legislative bloc regards the current government: -10,000 (implacably hostile) through
+10,000 (fully loyal).

A *relationship*, not a legitimacy and not an approval: it says nothing about whether the
government deserves support, only whether this particular caucus currently gives it. Signed and
symmetric, because hostility and loyalty are the same axis measured in opposite directions.
"""

StrictPreferenceBps: TypeAlias = Annotated[
    int, Field(strict=True, ge=-BPS_DENOMINATOR, le=BPS_DENOMINATOR)
]
"""A bloc's directional policy preference on one axis: negative prefers a decrease, positive
prefers an increase, zero is indifferent.

Separate from `StrictRelationshipBps` because preference and loyalty are independent: a bloc can
be devoted to the government and still hate its tax policy, and modelling both with one number
would make that combination unrepresentable.
"""

StrictSeatCount: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A count of legislative seats. Zero is meaningful: a bloc may hold no seats in a given chamber
(or none at all, after a future phase's defections) while still existing as a caucus."""

StrictPositiveSeatCount: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""A count of seats that cannot be zero — a chamber's size, or the majority required to carry it.

Distinct from `StrictSeatCount` because the two genuinely differ at zero: a chamber with no seats
is not a chamber, and a required majority of zero would mean a proposal passes with no support at
all. Both are `total_seats // 2 + 1`-adjacent quantities where zero indicates a construction bug,
not a representable state.
"""

StrictSeatNumerator: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""`seats * effective_support_bps` for one bloc — the exact, undivided product that
`simulation.apportionment` sums before its single division.

Typed separately from `StrictSeatCount` because it is not a seat count: it is a seat count scaled
by 10,000, and confusing the two is exactly the error that produces a hundredfold seat total. Kept
in the report so a validator can replay the apportionment without recomputing support from
scratch.
"""


# --- Phase 3B2A: competing capital uses and bloc relationships ---------------

RELATIONSHIP_INVESTMENT_CAP = 200
"""The most political capital one bloc's relationship can absorb in one turn.

**Defined once, here, and consumed by exactly two places**: `simulation.decisions.BlocInvestment`,
which *rejects* anything outside `[1, CAP]`, and `simulation.relationships.relationship_gain_bps`,
which *asserts* the same band. That pairing is deliberate. An earlier draft capped the amount
inside the formula while letting the decision accept any positive integer, which meant committing
500 bought exactly what 200 buys — 300 capital silently destroyed, and a strictly dominated action
the engine accepted without complaint. A bound that the player can hit must be a bound the player
is told about, so it lives in the decision schema and the formula merely agrees with it.

Also the single lever holding the diminishing-returns guarantee: one turn can close at most
`CAP / (RELATIONSHIP_HALF_GAP_CAPITAL + CAP)` of the remaining gap, so no amount of capital buys a
relationship outright.
"""

StrictRelationshipInvestment: TypeAlias = Annotated[
    int, Field(strict=True, ge=1, le=RELATIONSHIP_INVESTMENT_CAP)
]
"""Political capital committed to improving one bloc's relationship, in one turn.

`0` is not "no investment", it is a malformed one — an allocation naming a target and committing
nothing. `201` is not "200 plus some waste", it is out of range. Both are rejected rather than
normalised, the same reject-not-normalize rule every ordered collection in this codebase follows.
"""

StrictPoliticalCapitalCommitment: TypeAlias = Annotated[int, Field(strict=True, ge=1)]
"""One row of the political-capital expenditure ledger.

Every *stored* row represents a real, positive commitment; a zero commitment produces no row at
all. This introduces no new policy — `simulation.decisions.InfluenceAllocation` has required
`gt=0` since Phase 3B1, so no valid decision has ever carried a zero allocation. What it adds is
that the *report* cannot carry one either, which closes a padding channel: an attacker cannot add
arbitrary zero-cost rows to change what the ledger appears to describe while keeping
`total_committed == sum(rows)` intact.
"""

StrictRelationshipGainBps: TypeAlias = Annotated[
    int, Field(strict=True, ge=0, le=2 * BPS_DENOMINATOR)
]
"""An applied improvement to a bloc's relationship, in basis points.

Non-negative **by construction in Phase 3B2A**: the gap to the ceiling is never negative and
nothing decays yet. Relationship decay and adverse reactions are Phase 3B2B, and that is the
phase that makes this quantity genuinely signed.

The upper bound is the widest gap the scale admits (-10,000 to +10,000). It is never reached: the
formula returns a strict fraction of the remaining gap, so a single turn cannot close it.
"""


def trunc_div_toward_zero(numerator: int, denominator: int) -> int:
    """Exact integer division truncated **toward zero** — the single rounding step used by every
    signed political formula in `simulation.legitimacy`.

    **Requires `denominator > 0` and raises `ValueError` otherwise.** Every denominator this
    codebase divides by is either `BPS_DENOMINATOR` or a magnitude (an output baseline), so a
    negative denominator has no meaning here at all. A zero denominator is not silently absorbed
    either: it is only reachable from a zero previous-turn output baseline, and that case carries a
    specific meaning — "no proportional change to measure against nothing" — that the caller must
    state explicitly (see `simulation.legitimacy.assess_economic_performance`'s
    `baseline_output == 0` branch, checked *before* this function is ever called). Absorbing that
    precondition here would hide it instead of stating it where the decision is actually made.

    Deliberately **not** Python's `//`, which floors toward negative infinity. Every prior phase
    applied `//` to strictly nonnegative values, where flooring and truncation coincide; political
    deltas are this codebase's first genuinely signed quantities. Flooring them would round a
    -1.39% loss to -139 bps while rounding a +1.39% gain to +138 — a systematic one-basis-point
    pessimism bias with no modeling justification. Truncation is symmetric by construction:
    `trunc_div_toward_zero(-n, d) == -trunc_div_toward_zero(n, d)` exactly, for every `n` and `d`.
    """
    if denominator <= 0:
        raise ValueError(f"trunc_div_toward_zero: denominator must be positive, got {denominator}")
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def clamp_bps(value: int, *, low: int = LEGITIMACY_MIN_BPS, high: int = LEGITIMACY_MAX_BPS) -> int:
    """Clamp an integer basis-point value into `[low, high]` (inclusive).

    Used for the legitimacy scale bound and, with explicit arguments, for the symmetric per-turn
    change caps. Kept as a named helper rather than inline `max(min(...))` so every clamp site in
    `simulation.legitimacy` is greppable and each report validator can re-derive the same step.
    """
    if low > high:
        raise ValueError(f"clamp_bps: low={low} exceeds high={high}")
    return max(low, min(high, value))
