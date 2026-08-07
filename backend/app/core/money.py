"""Fixed-point money and bounded-metric helpers.

Financial state (treasury, debt, revenue, expenditure) must reconcile exactly,
which binary floating point cannot guarantee. `Money` is a plain integer count
of the smallest unit of the in-fiction currency (1 unit = 1/100 "denar"), so
all financial arithmetic is exact integer arithmetic.

Targets Python 3.11, so this uses `TypeAlias` (PEP 613) rather than the
`type X = ...` statement introduced in Python 3.12 (PEP 695).
"""

from __future__ import annotations

import math
from typing import Annotated, TypeAlias

from pydantic import Field

Money: TypeAlias = int
"""An amount of currency in minor units (1/100 of one denar). Always exact."""

MINOR_UNITS_PER_DENAR = 100

BPS_DENOMINATOR = 10_000
"""10,000 basis points = 100%."""

QUARTERLY_BPS_DENOMINATOR = 40_000
"""One turn is a quarter; an *annual* bps rate divides by 4 quarters x 10,000 bps/unit in a
single floor division: ``floor(x / 40_000)``. This is mathematically IDENTICAL to the two-step
form ``floor(floor(x / 10_000) / 4)`` — floor division is associative for nonnegative integers
(``floor(floor(a/b)/c) == floor(a/(b*c))``), which is verified for 200k random cases in
`test_money.py::test_single_step_and_two_step_quarterly_division_are_mathematically_equivalent`.
The single-step form is used purely because it is one operation instead of two, not because it
avoids a rounding discrepancy — there isn't one.
"""

# Pydantic's `strict=True` on an `int`-typed field already rejects bool (despite `bool` being an
# `int` subclass in plain Python), whole-number floats like `10.0`, numeric strings like `"10"`,
# NaN, and +/-inf — verified empirically and pinned by `test_money.py::test_strict_int_rejects_*`.
# No custom validator is needed to reject those; only the value-range constraints below are ours.
StrictMoney: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A nonnegative `Money` value with strict-integer input validation.

Used for balances and amounts that can never legitimately be negative: treasury cash, public
debt, tax bases, spending amounts, revenue totals. For a value that *can* be negative by
definition (e.g. a signed pre-financing balance), use `StrictSignedMoney` instead.
"""

StrictSignedMoney: TypeAlias = Annotated[int, Field(strict=True)]
"""A `Money` value with strict-integer input validation and no sign constraint."""

StrictBps: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=BPS_DENOMINATOR)]
"""A basis-point rate (0-10,000, i.e. 0%-100%) with strict-integer input validation."""


def apply_bps(amount: Money, rate_bps: int) -> Money:
    """`amount * rate_bps / 10_000`, floored. The single rounding step used throughout accounting."""
    return (amount * rate_bps) // BPS_DENOMINATOR


def apply_quarterly_bps(amount: Money, annual_rate_bps: int) -> Money:
    """`amount * annual_rate_bps / 40_000`, floored — one quarter's share of an annual bps rate,
    in a single floor division. See `QUARTERLY_BPS_DENOMINATOR` for why this is not two divisions.
    """
    return (amount * annual_rate_bps) // QUARTERLY_BPS_DENOMINATOR


def denars(whole: int, minor: int = 0) -> Money:
    """Construct a `Money` value from whole denars and minor units.

    Example: `denars(1_500, 50)` is 1,500.50 denars.
    """
    if minor < 0 or minor >= MINOR_UNITS_PER_DENAR:
        raise ValueError(f"minor units must be in [0, {MINOR_UNITS_PER_DENAR}), got {minor}")
    sign = -1 if whole < 0 else 1
    return sign * (abs(whole) * MINOR_UNITS_PER_DENAR + minor)


def format_money(amount: Money) -> str:
    """Render a `Money` value as a fixed-point denar string, e.g. `-12.05`."""
    sign = "-" if amount < 0 else ""
    whole, minor = divmod(abs(amount), MINOR_UNITS_PER_DENAR)
    return f"{sign}{whole}.{minor:02d}"


def clamp01_100(value: float) -> float:
    """Clamp a bounded political/social metric to the documented [0, 100] range.

    Used for `PopulationGroupState`/`InstitutionState`'s float approval/trust/loyalty scores
    (Phase 0 scaffolding, read by no formula anywhere yet). NOT used for legitimacy: Phase 3A's
    `legitimacy_bps` is a strict integer basis-point quantity (`core.politics.
    StrictLegitimacyBps`), validated by Pydantic, never by this helper.
    """
    if math.isnan(value):
        raise ValueError("bounded metric value must not be NaN")
    return max(0.0, min(100.0, value))
