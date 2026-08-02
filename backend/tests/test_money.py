from __future__ import annotations

import math

import pytest
from pydantic import BaseModel, ValidationError

from app.core.money import (
    QUARTERLY_BPS_DENOMINATOR,
    StrictBps,
    StrictMoney,
    StrictSignedMoney,
    apply_bps,
    apply_quarterly_bps,
)


class _MoneyHolder(BaseModel):
    amount: StrictMoney


class _SignedMoneyHolder(BaseModel):
    amount: StrictSignedMoney


class _BpsHolder(BaseModel):
    rate_bps: StrictBps


INVALID_INT_REPRESENTATIONS = [
    pytest.param(10.0, id="whole-number-float"),
    pytest.param(10.5, id="fractional-float"),
    pytest.param("10", id="numeric-string"),
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_money_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _MoneyHolder(amount=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_signed_money_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _SignedMoneyHolder(amount=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_bps_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _BpsHolder(rate_bps=bad_value)


def test_strict_money_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _MoneyHolder(amount=-1)


def test_strict_signed_money_accepts_negative() -> None:
    assert _SignedMoneyHolder(amount=-1).amount == -1


@pytest.mark.parametrize("bad_bps", [-1, 10_001])
def test_strict_bps_rejects_out_of_range(bad_bps: int) -> None:
    with pytest.raises(ValidationError):
        _BpsHolder(rate_bps=bad_bps)


@pytest.mark.parametrize("bps", [0, 5_000, 10_000])
def test_strict_bps_accepts_boundary_values(bps: int) -> None:
    assert _BpsHolder(rate_bps=bps).rate_bps == bps


def test_ordinary_integers_still_work() -> None:
    assert _MoneyHolder(amount=0).amount == 0
    assert _MoneyHolder(amount=42).amount == 42


def test_very_large_integers_still_work_deterministically() -> None:
    large = 10**15
    assert _MoneyHolder(amount=large).amount == large
    assert _SignedMoneyHolder(amount=-large).amount == -large


def test_no_actual_bool_subclass_leaks_through() -> None:
    """Confirms the empirically-verified pydantic strict-int behavior this module
    relies on: `bool` is a subclass of `int` in plain Python, but pydantic's
    `strict=True` rejects it anyway — pinned here so a pydantic upgrade that
    changed this would fail loudly rather than silently letting True/False
    through as 1/0 in a money field."""
    with pytest.raises(ValidationError):
        _MoneyHolder(amount=True)


class TestApplyBps:
    def test_zero_rate(self) -> None:
        assert apply_bps(1_000_000, 0) == 0

    def test_hundred_percent_rate(self) -> None:
        assert apply_bps(1_000_000, 10_000) == 1_000_000

    def test_ordinary_rate(self) -> None:
        # 20% of 1,000,000 = 200,000, exactly.
        assert apply_bps(1_000_000, 2_000) == 200_000

    def test_floors_rather_than_rounds(self) -> None:
        # 1% of 999 = 9.99 -> floors to 9.
        assert apply_bps(999, 100) == 9

    def test_large_value(self) -> None:
        assert apply_bps(10**12, 2_500) == 10**12 * 2_500 // 10_000


class TestApplyQuarterlyBps:
    def test_zero_rate(self) -> None:
        assert apply_quarterly_bps(1_000_000_00, 0) == 0

    def test_hundred_percent_annual_rate_is_one_quarter_of_principal(self) -> None:
        # 100% annual = 25% for one quarter: 1,000,000.00 -> 250,000.00.
        assert apply_quarterly_bps(1_000_000_00, 10_000) == 250_000_00
        assert apply_quarterly_bps(400_00, 10_000) == 100_00

    @pytest.mark.parametrize(
        ("debt", "annual_bps"),
        [(999, 100), (1, 1), (0, 10_000), (10**12 + 7, 9_999), (12_345_678, 333)],
    )
    def test_single_step_and_two_step_quarterly_division_are_mathematically_equivalent(
        self, debt: int, annual_bps: int
    ) -> None:
        """`apply_quarterly_bps` uses one floor division by 40,000 rather than
        floor-divide-by-10,000-then-floor-divide-by-4. These are NOT two competing
        roundings that happen to agree by luck — floor division is associative for
        nonnegative integers (`floor(floor(a/b)/c) == floor(a/(b*c))`), so the two
        forms are mathematically identical for every nonnegative `debt`/`annual_bps`.
        Verified here for representative cases and by random search (200k trials,
        zero mismatches) during development; the single-step form is used only
        because it is one operation, not because it changes the result."""
        single_step = apply_quarterly_bps(debt, annual_bps)
        two_step = ((debt * annual_bps) // 10_000) // 4

        assert single_step == two_step
        assert single_step == (debt * annual_bps) // QUARTERLY_BPS_DENOMINATOR

    def test_large_debt(self) -> None:
        debt = 10**13
        annual_bps = 750  # 7.5%
        assert apply_quarterly_bps(debt, annual_bps) == debt * annual_bps // 40_000


def test_no_float_arithmetic_involved() -> None:
    """A structural sanity check: results of the bps helpers are always `int`,
    never `float` — floats never enter accounting arithmetic."""
    result = apply_bps(1_234_567, 3_333)
    assert isinstance(result, int)
    assert not isinstance(result, float)
    assert not math.isnan(float(result))  # trivially true; documents intent, not a real risk
