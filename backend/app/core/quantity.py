"""Strict integer types for real production quantities.

Fixed-base-year sector output is neither a physical unit nor spendable
treasury money — it is a real (constant-price) production measure. It must
never be conflated with `Money` (`app.core.money`): a `StrictRealOutput`
value cannot be spent, taxed, or added to cash/debt, and nothing in this
phase performs such a conversion.

Worker counts and output amounts are also distinct concepts and get
distinct aliases rather than one generic "quantity" type, so a field's
annotation alone states what kind of number it holds.

Targets Python 3.11, so this uses `TypeAlias` (PEP 613) rather than the
`type X = ...` statement introduced in Python 3.12 (PEP 695).
"""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field

from app.core.money import BPS_DENOMINATOR, Money

# Pydantic's `strict=True` on an `int`-typed field rejects bool, whole-number
# floats, numeric strings, NaN, and +/-inf — verified for `StrictMoney` in
# `test_money.py` and re-verified for these aliases in `test_quantity.py`.

WorkerCount: TypeAlias = int
"""A count of employed workers, for plain function signatures (mirrors `Money` in `core.money`)."""

RealOutput: TypeAlias = int
"""An amount of fixed-base-year real output, for plain function signatures. Never `Money`."""

StrictWorkerCount: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A nonnegative count of employed workers in a sector. Not currency, not output."""

StrictRealOutput: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A nonnegative amount of production measured in fixed-base-year output minor units.

Used for `quarterly_capacity_output`, `labor_limited_output`, `actual_output`, and
`total_gross_output`. This is a real (constant-price) output measure, not spendable
money — see the module docstring.
"""

StrictRealOutputPerWorker: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""Fixed-base-year output minor units produced per worker per quarter. Strictly positive:
a sector with no per-worker output isn't modeled by zeroing this field, it's modeled by
`employed_workers == 0` (see `docs/economy_methodology.md` for why the two are kept distinct).
"""

BASE_YEAR_PRICE_INDEX_BPS = BPS_DENOMINATOR
"""The temporary real-output-to-money bridge (Phase 2B2), expressed as exact integer basis
points rather than a runtime float: `10_000 bps == 1.0`, i.e. one fixed-base-year real output
minor unit currently converts to exactly one nominal `Money` minor unit. This is a placeholder
for the price-level system that doesn't exist yet — see `base_year_real_output_to_money` below
and `docs/economy_methodology.md` for why this is deliberately temporary, not a permanent 1:1
economic claim.
"""


ResourceQuantity: TypeAlias = int
"""An amount of a physical natural resource (timber, ore, oil, ...), for plain function
signatures. A third distinct concept from `WorkerCount`/`RealOutput`/`Money` (Phase 2C1) — never
convertible to any of them. Each `ResourceCategory` has its own physical unit (cubic metres,
tonnes, barrels, or thousand cubic metres — see `simulation.state.RESOURCE_UNITS`), so quantities
of different resources must never be summed together; only worker counts and per-status counts
derived from resource activity may be aggregated (see `docs/economy_methodology.md`).
"""

StrictResourceQuantity: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
"""A nonnegative physical resource quantity: remaining stock, extraction capacity, regeneration,
extracted amount, or closing stock. Deliberately no upper bound at the type level (an authoring
typo in magnitude is not caught here — see `docs/adr/0007-resource-endowments-and-extraction.md`,
"Known limitations").
"""

StrictResourceQuantityPerWorker: TypeAlias = Annotated[int, Field(strict=True, gt=0)]
"""Physical resource units extractable per allocated extraction worker per turn. Strictly
positive for the same reason `StrictRealOutputPerWorker` is: "no extraction" is expressed only via
zero allocated workers or zero remaining stock, never by also allowing this to be zero.
"""


def base_year_real_output_to_money(value: RealOutput) -> Money:
    """The single named conversion point from fixed-base-year real output to nominal `Money`.

    Deliberately a real function — not an implicit `int` pass-through — because this is the
    single most important unit boundary in the economy simulation: everything upstream of this
    call is a real production measure that can never be spent, taxed, or added to cash/debt;
    everything downstream is spendable nominal currency. `RealOutput`/`Money` are both plain
    `int` `TypeAlias`es at runtime, so nothing but this function's name, types, and docstring
    marks the crossing — callers must route every real-to-nominal conversion through here rather
    than passing a real-output integer directly into a `Money`-typed field.

    Currently an identity conversion at `BASE_YEAR_PRICE_INDEX_BPS` (10,000 bps = 1.0), using
    integer basis points rather than a runtime float so the "price index" is exact and
    inspectable rather than an opaque `1.0` constant. This function — not the constant alone —
    is what a later price-level/inflation system replaces; call sites do not change when it does.

    Rejects negative and non-integer (including `bool`) input via `StrictRealOutput`'s own
    validation semantics, re-applied here explicitly since this is a plain function, not a
    Pydantic field.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"base_year_real_output_to_money requires a plain int, got {value!r}")
    if value < 0:
        raise ValueError(
            f"base_year_real_output_to_money requires a nonnegative value, got {value}"
        )
    return (value * BASE_YEAR_PRICE_INDEX_BPS) // BPS_DENOMINATOR
