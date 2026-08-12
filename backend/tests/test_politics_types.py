"""Tests for `app.core.politics`' bounded political metric aliases and the signed-division
helper every legitimacy formula rounds with (Phase 3A, T-M1..T-M6), plus the five
legislative-composition aliases added in Phase 3B1 (T-M1).

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
    RELATIONSHIP_INVESTMENT_CAP,
    StrictLegitimacyBps,
    StrictPoliticalCapital,
    StrictPoliticalCapitalCapacity,
    StrictPoliticalCapitalCommitment,
    StrictPositiveSeatCount,
    StrictPreferenceBps,
    StrictRelationshipBps,
    StrictRelationshipGainBps,
    StrictRelationshipInvestment,
    StrictSeatCount,
    StrictSeatNumerator,
    StrictSignedBps,
    StrictSignedLegitimacyBps,
    clamp_bps,
    trunc_div_toward_zero,
)


class _LegitimacyHolder(BaseModel):
    value: StrictLegitimacyBps


class _SignedLegitimacyHolder(BaseModel):
    value: StrictSignedLegitimacyBps


class _SignedBpsHolder(BaseModel):
    value: StrictSignedBps


class _PoliticalCapitalHolder(BaseModel):
    value: StrictPoliticalCapital


class _PoliticalCapitalCapacityHolder(BaseModel):
    value: StrictPoliticalCapitalCapacity


class _RelationshipHolder(BaseModel):
    value: StrictRelationshipBps


class _PreferenceHolder(BaseModel):
    value: StrictPreferenceBps


class _SeatCountHolder(BaseModel):
    value: StrictSeatCount


class _PositiveSeatCountHolder(BaseModel):
    value: StrictPositiveSeatCount


class _RelationshipInvestmentHolder(BaseModel):
    value: StrictRelationshipInvestment


class _CapitalCommitmentHolder(BaseModel):
    value: StrictPoliticalCapitalCommitment


class _RelationshipGainHolder(BaseModel):
    value: StrictRelationshipGainBps


class _SeatNumeratorHolder(BaseModel):
    value: StrictSeatNumerator


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


# --- T-M4 (R5): the helper requires a positive denominator -------------------


@pytest.mark.parametrize("numerator", [-(10**9), -1, 0, 1, 10**9])
def test_zero_denominator_raises(numerator: int) -> None:
    """A zero denominator is never silently absorbed. The one reachable case — a zero previous-turn
    output baseline — is handled by the CALLER (`assess_economic_performance`'s explicit
    `baseline_output == 0` branch) before this function is ever invoked."""
    with pytest.raises(ValueError, match="denominator must be positive"):
        trunc_div_toward_zero(numerator, 0)


@pytest.mark.parametrize("denominator", [-1, -2, -(10**9)])
@pytest.mark.parametrize("numerator", [-1, 0, 1, 10**9])
def test_negative_denominator_raises(numerator: int, denominator: int) -> None:
    """Every real denominator in this codebase is either `BPS_DENOMINATOR` or a magnitude (an
    output baseline); a negative denominator has no meaning here at all."""
    with pytest.raises(ValueError, match="denominator must be positive"):
        trunc_div_toward_zero(numerator, denominator)


# --- T-M5 (R5): unbounded signed rates ----------------------------------------


def test_output_change_from_a_tripled_baseline_is_20000_bps() -> None:
    """The R5 motivating case: a previous-turn output baseline of 1 rising to 3 is a +200% change,
    +20,000 bps — arithmetically correct, and larger than the legitimacy scale itself."""
    change = trunc_div_toward_zero((3 - 1) * 10_000, 1)
    assert change == 20_000
    assert _SignedBpsHolder(value=change).value == 20_000
    with pytest.raises(ValidationError):
        _SignedLegitimacyHolder(value=change)


def test_output_change_from_a_millionfold_rebound_is_unbounded() -> None:
    """Baseline 1 -> current 1,000,000 is +9,999,990,000 bps; `StrictSignedBps` holds it,
    `StrictSignedLegitimacyBps` rejects it."""
    change = trunc_div_toward_zero((1_000_000 - 1) * 10_000, 1)
    assert change == 9_999_990_000
    assert _SignedBpsHolder(value=change).value == 9_999_990_000
    with pytest.raises(ValidationError):
        _SignedLegitimacyHolder(value=change)


def test_complete_output_collapse_is_exactly_negative_10000_bps() -> None:
    """Current output 0 against any positive baseline is a complete collapse: -100%, -10,000 bps.
    The negative direction happens to fit the legitimacy scale; the positive direction does not."""
    change = trunc_div_toward_zero((0 - 5_000_000) * 10_000, 5_000_000)
    assert change == -10_000
    assert _SignedLegitimacyHolder(value=change).value == -10_000
    assert _SignedBpsHolder(value=change).value == -10_000


# --- T-M6 (R5): strict rejection on both signed aliases -----------------------


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_signed_bps_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _SignedBpsHolder(value=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_signed_legitimacy_bps_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _SignedLegitimacyHolder(value=bad_value)


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


# --- Phase 3B1 T-M1: the five legislative-composition aliases -----------------

LEGISLATIVE_HOLDERS = [
    pytest.param(_RelationshipHolder, id="relationship-bps"),
    pytest.param(_PreferenceHolder, id="preference-bps"),
    pytest.param(_SeatCountHolder, id="seat-count"),
    pytest.param(_PositiveSeatCountHolder, id="positive-seat-count"),
    pytest.param(_SeatNumeratorHolder, id="seat-numerator"),
]


@pytest.mark.parametrize("holder", LEGISLATIVE_HOLDERS)
@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_legislative_aliases_reject_invalid_representations(
    holder: type[BaseModel], bad_value: object
) -> None:
    """All five are `strict=True`, so a seat count of `3.0` or `"3"` is rejected rather than
    coerced. Seats and support are hash-covered state; a silent float coercion would be a
    difference the digest could not see."""
    with pytest.raises(ValidationError):
        holder(value=bad_value)


@pytest.mark.parametrize(
    "holder",
    [
        pytest.param(_RelationshipHolder, id="relationship"),
        pytest.param(_PreferenceHolder, id="preference"),
    ],
)
def test_signed_legislative_aliases_accept_the_symmetric_bounds(holder: type[BaseModel]) -> None:
    """Hostility and loyalty are the same axis measured in opposite directions, so both ends of
    the scale are representable and the midpoint is indifference."""
    assert holder(value=-10_000).value == -10_000
    assert holder(value=0).value == 0
    assert holder(value=10_000).value == 10_000


@pytest.mark.parametrize(
    "holder",
    [
        pytest.param(_RelationshipHolder, id="relationship"),
        pytest.param(_PreferenceHolder, id="preference"),
    ],
)
@pytest.mark.parametrize("out_of_range", [-10_001, -20_000, 10_001, 20_000])
def test_signed_legislative_aliases_reject_values_beyond_the_scale(
    holder: type[BaseModel], out_of_range: int
) -> None:
    with pytest.raises(ValidationError):
        holder(value=out_of_range)


def test_seat_count_accepts_zero_and_rejects_negative() -> None:
    """A bloc may hold no seats in a given chamber and still exist as a caucus — an upper-house
    absence is ordinary, not a construction bug."""
    assert _SeatCountHolder(value=0).value == 0
    assert _SeatCountHolder(value=650).value == 650
    with pytest.raises(ValidationError):
        _SeatCountHolder(value=-1)


def test_positive_seat_count_rejects_zero_and_negative() -> None:
    """A chamber with no seats is not a chamber, and a required majority of zero would mean a
    proposal passes with no support at all."""
    with pytest.raises(ValidationError):
        _PositiveSeatCountHolder(value=0)
    with pytest.raises(ValidationError):
        _PositiveSeatCountHolder(value=-1)
    assert _PositiveSeatCountHolder(value=1).value == 1


def test_zero_is_exactly_what_separates_the_two_seat_types() -> None:
    """The whole reason both aliases exist. If this ever passes for both, one of them is
    redundant and the distinction has been quietly lost."""
    assert _SeatCountHolder(value=0).value == 0
    with pytest.raises(ValidationError):
        _PositiveSeatCountHolder(value=0)


def test_seat_numerator_holds_the_undivided_product() -> None:
    """`seats * effective_support_bps`, before the single division. The worked example: 45 seats at
    full support is 450,000 — a hundredfold larger than any seat count, which is precisely why it
    is not typed as one."""
    assert _SeatNumeratorHolder(value=45 * 10_000).value == 450_000
    assert _SeatNumeratorHolder(value=0).value == 0
    with pytest.raises(ValidationError):
        _SeatNumeratorHolder(value=-1)


# --- Phase 3B2A T8b: the investment cap is a decision-level bound -------------

PHASE_3B2A_HOLDERS = [
    pytest.param(_RelationshipInvestmentHolder, id="relationship-investment"),
    pytest.param(_CapitalCommitmentHolder, id="capital-commitment"),
    pytest.param(_RelationshipGainHolder, id="relationship-gain"),
]


@pytest.mark.parametrize("holder", PHASE_3B2A_HOLDERS)
@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_phase_3b2a_aliases_reject_invalid_representations(
    holder: type[BaseModel], bad_value: object
) -> None:
    with pytest.raises(ValidationError):
        holder(value=bad_value)


def test_relationship_investment_spans_exactly_one_through_the_cap() -> None:
    """T8b's four boundaries. `0` and `201` are rejected *by the type*, so no resolution-time code
    has to defend against either — and 201 is refused rather than truncated to 200, because
    silently spending 201 to buy what 200 buys destroys a point of capital the player never agreed
    to lose."""
    assert _RelationshipInvestmentHolder(value=1).value == 1
    assert _RelationshipInvestmentHolder(value=RELATIONSHIP_INVESTMENT_CAP).value == 200

    with pytest.raises(ValidationError):
        _RelationshipInvestmentHolder(value=0)
    with pytest.raises(ValidationError):
        _RelationshipInvestmentHolder(value=RELATIONSHIP_INVESTMENT_CAP + 1)


def test_the_investment_cap_is_two_hundred() -> None:
    """Pinned as a value, not just as a bound: `RELATIONSHIP_INVESTMENT_CAP` is part of the accepted
    decision schema (a player can hit it), so changing it is a compatibility event and must not
    happen by accident."""
    assert RELATIONSHIP_INVESTMENT_CAP == 200


def test_capital_commitment_rejects_zero_so_a_ledger_row_is_always_real() -> None:
    """Every stored expenditure row is a positive commitment; a zero commitment produces no row.
    This is the padding defence: an attacker cannot add zero-cost rows to change what the ledger
    appears to describe while keeping `total_committed == sum(rows)` intact."""
    assert _CapitalCommitmentHolder(value=1).value == 1
    with pytest.raises(ValidationError):
        _CapitalCommitmentHolder(value=0)
    with pytest.raises(ValidationError):
        _CapitalCommitmentHolder(value=-1)


def test_relationship_gain_is_non_negative_and_spans_the_widest_gap() -> None:
    """Non-negative because nothing decays in Phase 3B2A. The bound is the widest gap the scale
    admits (-10,000 -> +10,000); it is unreachable in one turn, and is a range backstop rather
    than a modelled maximum."""
    assert _RelationshipGainHolder(value=0).value == 0
    assert _RelationshipGainHolder(value=20_000).value == 20_000
    with pytest.raises(ValidationError):
        _RelationshipGainHolder(value=-1)
    with pytest.raises(ValidationError):
        _RelationshipGainHolder(value=20_001)
