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

# Pydantic's `strict=True` on an `int`-typed field rejects bool, whole-number
# floats, numeric strings, NaN, and +/-inf — verified for `StrictMoney` in
# `test_money.py` and re-verified for these aliases in `test_quantity.py`.

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
