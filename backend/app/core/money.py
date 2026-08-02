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
from typing import TypeAlias

Money: TypeAlias = int
"""An amount of currency in minor units (1/100 of one denar). Always exact."""

MINOR_UNITS_PER_DENAR = 100


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

    Used for approval, trust, loyalty, legitimacy, and similar scores. Unlike
    `Money`, these do not need to reconcile to zero across a ledger — they only
    need to stay within their documented bounds, which `simulation.invariants`
    checks independently of this helper.
    """
    if math.isnan(value):
        raise ValueError("bounded metric value must not be NaN")
    return max(0.0, min(100.0, value))
