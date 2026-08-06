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

StrictSignedLegitimacyBps: TypeAlias = Annotated[
    int, Field(strict=True, ge=-BPS_DENOMINATOR, le=BPS_DENOMINATOR)
]
"""A legitimacy *change* or *contribution*: signed, bounded by the metric's own full range.

Separate from `StrictLegitimacyBps` because a level and a delta are different quantities: a level
can never be negative, a delta routinely is. The bound is the full scale rather than a per-turn cap
so that a report field can hold any arithmetically reachable contribution before clamping, and the
clamp itself stays an explicit, re-derivable step in `simulation.legitimacy` rather than something
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


def trunc_div_toward_zero(numerator: int, denominator: int) -> int:
    """Exact integer division truncated **toward zero** — the single rounding step used by every
    signed political formula in `simulation.legitimacy`.

    Returns `0` when `denominator == 0`, which is the defined behavior for the one place that can
    happen: a zero previous-turn output baseline, where there is no proportional change to measure
    against nothing (see `simulation.legitimacy.assess_economic_performance`). No
    `ZeroDivisionError` path exists.

    Deliberately **not** Python's `//`, which floors toward negative infinity. Every prior phase
    applied `//` to strictly nonnegative values, where flooring and truncation coincide; political
    deltas are this codebase's first genuinely signed quantities. Flooring them would round a
    -1.39% loss to -139 bps while rounding a +1.39% gain to +138 — a systematic one-basis-point
    pessimism bias with no modeling justification. Truncation is symmetric by construction:
    `trunc_div_toward_zero(-n, d) == -trunc_div_toward_zero(n, d)` exactly, for every `n` and `d`.
    """
    if denominator == 0:
        return 0
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def clamp_bps(value: int, *, low: int = LEGITIMACY_MIN_BPS, high: int = LEGITIMACY_MAX_BPS) -> int:
    """Clamp an integer basis-point value into `[low, high]` (inclusive).

    Used for the legitimacy scale bound and, with explicit arguments, for the symmetric per-turn
    change caps. Kept as a named helper rather than inline `max(min(...))` so every clamp site in
    `simulation.legitimacy` is greppable and each report validator can re-derive the same step.
    """
    if low > high:
        raise ValueError(f"clamp_bps: low={low} exceeds high={high}")
    return max(low, min(high, value))
