"""Player-facing money text for the API's projections (Gate 4A3 UX-4a, U9).

`app.core.money.format_money` renders a `Money` value as a bare fixed-point string -- `100000000.00`
-- and the CLI and the reports keep using it unchanged. The browser shows the same amounts to a
player, who should not have to count zeros, so the projections that build player-facing text use
this instead: the same value, with digit grouping, and with an explicit sign where the text is a
change rather than a level.

Presentation only, like `outcome_labels.py`: no resolution reads it.
"""

from __future__ import annotations

from app.core.money import MINOR_UNITS_PER_DENAR, Money


def format_money_display(amount: Money, *, signed: bool = False) -> str:
    """`100000000_00` -> `"100,000,000.00"`; with `signed=True`, `+3,150,000.00` / `-12.05`.

    A negative amount always carries `-`. `signed` adds `+` to a positive amount, for text that
    states a change; zero is never signed, since it is neither a gain nor a loss.
    """
    sign = "-" if amount < 0 else ("+" if signed and amount > 0 else "")
    whole, minor = divmod(abs(amount), MINOR_UNITS_PER_DENAR)
    return f"{sign}{whole:,}.{minor:02d}"
