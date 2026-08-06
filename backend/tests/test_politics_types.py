"""Tests for `app.core.politics`' bounded political metric aliases and the signed-division
helper every legitimacy formula rounds with (Phase 3A, T-M1..T-M4).

Mirrors `test_quantity.py`'s structure: a tiny holder model per alias, one shared table of
invalid integer representations, then boundary and behavior tests.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from app.core.politics import (
    LEGITIMACY_MAX_BPS,
    LEGITIMACY_MIN_BPS,
    StrictLegitimacyBps,
    StrictPoliticalCapital,
    StrictPoliticalCapitalCapacity,
    StrictSignedLegitimacyBps,
    clamp_bps,
    trunc_div_toward_zero,
)


class _LegitimacyHolder(BaseModel):
    value: StrictLegitimacyBps


class _SignedLegitimacyHolder(BaseModel):
    value: StrictSignedLegitimacyBps


class _PoliticalCapitalHolder(BaseModel):
    value: StrictPoliticalCapital


class _PoliticalCapitalCapacityHolder(BaseModel):
    value: StrictPoliticalCapitalCapacity


INVALID_INT_REPRESENTATIONS = [
    pytest.param(10.0, id="whole-number-float"),
    pytest.param(10.5, id="fractional-float"),
    pytest.param("5000", id="numeric-string"),
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


# --- T-M1: metric boundaries -------------------------------------------------


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_legitimacy_bps_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _LegitimacyHolder(value=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_political_capital_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _PoliticalCapitalHolder(value=bad_value)


def test_legitimacy_accepts_both_documented_bounds() -> None:
    assert _LegitimacyHolder(value=LEGITIMACY_MIN_BPS).value == 0
    assert _LegitimacyHolder(value=LEGITIMACY_MAX_BPS).value == 10_000


@pytest.mark.parametrize("out_of_range", [-1, 10_001, 20_000])
def test_legitimacy_rejects_values_outside_the_scale(out_of_range: int) -> None:
    with pytest.raises(ValidationError):
        _LegitimacyHolder(value=out_of_range)


def test_signed_legitimacy_accepts_the_full_signed_range() -> None:
    """A contribution may be as large as the scale itself in either direction; the per-turn caps
    are an explicit, re-derivable formula step, deliberately not a type bound (see the alias
    docstring)."""
    assert _SignedLegitimacyHolder(value=-10_000).value == -10_000
    assert _SignedLegitimacyHolder(value=0).value == 0
    assert _SignedLegitimacyHolder(value=10_000).value == 10_000


@pytest.mark.parametrize("out_of_range", [-10_001, 10_001])
def test_signed_legitimacy_rejects_values_beyond_the_scale(out_of_range: int) -> None:
    with pytest.raises(ValidationError):
        _SignedLegitimacyHolder(value=out_of_range)


def test_political_capital_is_nonnegative_and_unbounded_above() -> None:
    assert _PoliticalCapitalHolder(value=0).value == 0
    assert _PoliticalCapitalHolder(value=10**12).value == 10**12
    with pytest.raises(ValidationError):
        _PoliticalCapitalHolder(value=-1)


# --- T-M2: capacity strictly positive ----------------------------------------


def test_political_capital_capacity_rejects_zero_and_accepts_one() -> None:
    """Zero capacity would mean a government permanently unable to act — a removal condition, and
    removal is Phase 3C."""
    with pytest.raises(ValidationError):
        _PoliticalCapitalCapacityHolder(value=0)
    assert _PoliticalCapitalCapacityHolder(value=1).value == 1


def test_political_capital_capacity_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _PoliticalCapitalCapacityHolder(value=-1)


# --- T-M3: truncation toward zero is symmetric -------------------------------


def test_truncation_rounds_toward_zero_not_negative_infinity() -> None:
    """The exact case from the Phase 3A calibration: `deficit_demo` turn 41 computes
    -50,000,000 * 10,000 / 3,600,000,000 = -138.888..., which must truncate to -138.
    Python's `//` would floor it to -139."""
    numerator = -50_000_000 * 10_000
    denominator = 3_600_000_000
    assert trunc_div_toward_zero(numerator, denominator) == -138
    assert numerator // denominator == -139  # what we deliberately do NOT do


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        pytest.param(7, 2, 3, id="positive-non-exact"),
        pytest.param(-7, 2, -3, id="negative-non-exact"),
        pytest.param(8, 2, 4, id="positive-exact"),
        pytest.param(-8, 2, -4, id="negative-exact"),
        pytest.param(0, 5, 0, id="zero-numerator"),
        pytest.param(7, -2, -3, id="negative-denominator"),
        pytest.param(-7, -2, 3, id="both-negative"),
        pytest.param(1, 2, 0, id="truncates-toward-zero-not-away"),
        pytest.param(-1, 2, 0, id="negative-truncates-to-zero"),
    ],
)
def test_truncation_covers_positive_negative_exact_and_non_exact(
    numerator: int, denominator: int, expected: int
) -> None:
    assert trunc_div_toward_zero(numerator, denominator) == expected


@given(
    numerator=st.integers(min_value=-(10**12), max_value=10**12),
    denominator=st.integers(min_value=1, max_value=10**12),
)
def test_truncation_is_exactly_symmetric_for_arbitrary_inputs(
    numerator: int, denominator: int
) -> None:
    """`f(-n, d) == -f(n, d)` exactly — the property that makes a loss and an equal-magnitude gain
    produce equal-magnitude opposite contributions, with no pessimism bias."""
    assert trunc_div_toward_zero(-numerator, denominator) == -trunc_div_toward_zero(
        numerator, denominator
    )


@given(
    numerator=st.integers(min_value=-(10**9), max_value=10**9),
    denominator=st.integers(min_value=1, max_value=10**9),
)
def test_truncation_never_exceeds_the_true_quotient_magnitude(
    numerator: int, denominator: int
) -> None:
    result = trunc_div_toward_zero(numerator, denominator)
    assert abs(result) * denominator <= abs(numerator)


# --- T-M4: zero denominator --------------------------------------------------


@pytest.mark.parametrize("numerator", [-(10**9), -1, 0, 1, 10**9])
def test_zero_denominator_returns_zero_and_never_raises(numerator: int) -> None:
    """The one reachable zero-denominator case is a zero previous-turn output baseline: there is no
    proportional change to measure against nothing."""
    assert trunc_div_toward_zero(numerator, 0) == 0


# --- clamp_bps ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(-1, 0, id="below-floor"),
        pytest.param(0, 0, id="at-floor"),
        pytest.param(5_000, 5_000, id="inside"),
        pytest.param(10_000, 10_000, id="at-ceiling"),
        pytest.param(10_255, 10_000, id="above-ceiling"),
    ],
)
def test_clamp_bps_bounds_to_the_legitimacy_scale_by_default(value: int, expected: int) -> None:
    assert clamp_bps(value) == expected


def test_clamp_bps_supports_symmetric_per_turn_caps() -> None:
    assert clamp_bps(-800, low=-500, high=500) == -500
    assert clamp_bps(800, low=-500, high=500) == 500
    assert clamp_bps(-246, low=-500, high=500) == -246


def test_clamp_bps_rejects_an_inverted_range() -> None:
    with pytest.raises(ValueError, match="exceeds high"):
        clamp_bps(0, low=10, high=5)
