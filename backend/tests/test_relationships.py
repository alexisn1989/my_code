"""Phase 3B2A T8/T8b: what `simulation.relationships` actually guarantees.

This file exists as much to pin what is **not** true as what is. Two properties the continuous
function has are destroyed by integer truncation, both were claimed in an earlier draft of the
plan, and both are asserted here **as measured behaviour** so nobody can quietly reintroduce them
as guarantees:

- per-integer *strict* monotonicity (ties exist for small gaps), and
- *discrete* concavity (the realised marginal gain oscillates across floor boundaries).

The six statements in `test_*` names beginning `test_guarantee_` are the whole contract.
"""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.politics import RELATIONSHIP_INVESTMENT_CAP
from app.simulation.relationships import (
    RELATIONSHIP_CEILING_BPS,
    RELATIONSHIP_HALF_GAP_CAPITAL,
    relationship_gain_bps,
)

RELATIONSHIP_FLOOR_BPS = -RELATIONSHIP_CEILING_BPS

relationships = st.integers(min_value=RELATIONSHIP_FLOOR_BPS, max_value=RELATIONSHIP_CEILING_BPS)
investments = st.integers(min_value=1, max_value=RELATIONSHIP_INVESTMENT_CAP)


def _gain(gap: int, capital: int) -> int:
    """Helper phrased in terms of the *gap*, which is how every guarantee below reads."""
    return relationship_gain_bps(
        opening_relationship_bps=RELATIONSHIP_CEILING_BPS - gap, political_capital=capital
    )


# --- the constants themselves ------------------------------------------------


def test_the_calibrated_constants_are_pinned() -> None:
    """H = 500 was selected by sweeping against real scenario data, and the eight-turn break-even
    it produces is an accepted design property rather than an accident. Changing either value
    silently would move every figure in the calibration suite."""
    assert RELATIONSHIP_HALF_GAP_CAPITAL == 500
    assert RELATIONSHIP_CEILING_BPS == 10_000
    assert RELATIONSHIP_INVESTMENT_CAP == 200


def test_half_the_gap_capital_is_named_for_what_it_does() -> None:
    """Committing exactly `RELATIONSHIP_HALF_GAP_CAPITAL` would close half the remaining gap. It
    is above the per-turn cap, so no single turn can reach it -- the constant names the shape of
    the curve, not an attainable purchase."""
    gap = 12_000
    hypothetical = (
        gap
        * RELATIONSHIP_HALF_GAP_CAPITAL
        // (RELATIONSHIP_HALF_GAP_CAPITAL + RELATIONSHIP_HALF_GAP_CAPITAL)
    )
    assert hypothetical == gap // 2
    assert RELATIONSHIP_HALF_GAP_CAPITAL > RELATIONSHIP_INVESTMENT_CAP


# --- guarantee 1: monotonic non-decreasing (universal) -----------------------


@given(opening=relationships, capital=investments)
def test_guarantee_monotonic_non_decreasing(opening: int, capital: int) -> None:
    gain = relationship_gain_bps(opening_relationship_bps=opening, political_capital=capital)
    if capital < RELATIONSHIP_INVESTMENT_CAP:
        nxt = relationship_gain_bps(opening_relationship_bps=opening, political_capital=capital + 1)
        assert nxt >= gain


# --- guarantee 2: strictly below the remaining gap (universal) ---------------


@given(opening=relationships, capital=investments)
def test_guarantee_gain_is_non_negative_and_strictly_below_the_gap(
    opening: int, capital: int
) -> None:
    gap = RELATIONSHIP_CEILING_BPS - opening
    gain = relationship_gain_bps(opening_relationship_bps=opening, political_capital=capital)
    assert gain >= 0
    if gap > 0:
        assert gain < gap
    assert opening + gain < RELATIONSHIP_CEILING_BPS or gap == 0


@given(opening=relationships, capital=investments)
def test_guarantee_closing_never_reaches_the_ceiling(opening: int, capital: int) -> None:
    """The bound is arithmetic, not a clamp: there is no capital amount that buys a bloc outright,
    so no relationship is ever 'maxed out' and investment never becomes free."""
    gain = relationship_gain_bps(opening_relationship_bps=opening, political_capital=capital)
    assert opening + gain <= RELATIONSHIP_CEILING_BPS
    if opening < RELATIONSHIP_CEILING_BPS:
        assert opening + gain < RELATIONSHIP_CEILING_BPS


# --- guarantee 3: a smaller gap never buys more (universal) ------------------


@given(
    smaller=st.integers(min_value=0, max_value=20_000),
    larger=st.integers(min_value=0, max_value=20_000),
    capital=investments,
)
def test_guarantee_a_smaller_gap_never_yields_a_larger_gain(
    smaller: int, larger: int, capital: int
) -> None:
    if smaller > larger:
        smaller, larger = larger, smaller
    assert _gain(smaller, capital) <= _gain(larger, capital)


# --- guarantee 4: the ENVELOPE is concave (stated as an envelope property) ----


@given(gap=st.integers(min_value=0, max_value=20_000), capital=investments)
def test_guarantee_the_unrounded_envelope_has_diminishing_marginal_returns(
    gap: int, capital: int
) -> None:
    """Concavity is asserted against the exact rational envelope, compared cross-multiplied so no
    float ever enters the test. The *truncated* result is a different thing and is deliberately
    not asserted -- see `test_measured_the_realised_marginal_gain_oscillates`."""
    if capital + 2 > RELATIONSHIP_INVESTMENT_CAP:
        return
    h = RELATIONSHIP_HALF_GAP_CAPITAL

    def envelope_delta_num_den(c: int) -> tuple[int, int]:
        # gap*(c+1)/(h+c+1) - gap*c/(h+c)  ==  gap*h / ((h+c)*(h+c+1))
        return gap * h, (h + c) * (h + c + 1)

    first_num, first_den = envelope_delta_num_den(capital)
    second_num, second_den = envelope_delta_num_den(capital + 1)
    assert first_num * second_den >= second_num * first_den


# --- guarantee 5: the cap bounds one turn's purchase -------------------------


@given(opening=relationships)
def test_guarantee_one_turn_closes_at_most_two_sevenths_of_the_gap(opening: int) -> None:
    """`CAP / (H + CAP) == 200/700 == 2/7`. Asserted by cross-multiplication, integers only."""
    gap = RELATIONSHIP_CEILING_BPS - opening
    gain = relationship_gain_bps(
        opening_relationship_bps=opening, political_capital=RELATIONSHIP_INVESTMENT_CAP
    )
    assert gain * 7 <= gap * 2


# --- guarantee 6: repeated equal investment buys strictly less ---------------


def test_guarantee_repeated_equal_investments_buy_strictly_less_each_turn() -> None:
    """The ratchet slows itself down with no stored history: the gap is the only memory, and it
    shrinks every turn. These are `deficit_demo`'s real figures at 100 capital per turn."""
    opening = -2_000
    gains = []
    for _ in range(5):
        gain = relationship_gain_bps(opening_relationship_bps=opening, political_capital=100)
        gains.append(gain)
        opening += gain

    assert gains == [2_000, 1_666, 1_389, 1_157, 964]
    assert gains == sorted(gains, reverse=True)
    assert all(later < earlier for earlier, later in itertools.pairwise(gains))


# --- MEASURED BEHAVIOUR: the two properties that are NOT guaranteed ----------


def test_measured_adjacent_capital_values_tie_for_small_gaps() -> None:
    """NOT a guarantee. Per-integer strict monotonicity is false, and this records how false.

    910 is the smallest gap with no tied step in `[1, 200]`. It is an artefact of H and the cap,
    recorded so the withdrawn claim is not reintroduced with a convenient threshold attached.
    """

    def tie_count(gap: int) -> int:
        return sum(
            1 for c in range(1, RELATIONSHIP_INVESTMENT_CAP) if _gain(gap, c + 1) == _gain(gap, c)
        )

    assert tie_count(100) == 171
    assert tie_count(700) == 16
    assert tie_count(910) == 0
    assert tie_count(12_000) == 0

    smallest_tie_free = next(gap for gap in range(1, 30_001) if tie_count(gap) == 0)
    assert smallest_tie_free == 910


def test_measured_the_realised_marginal_gain_oscillates() -> None:
    """NOT a guarantee. Discrete concavity is false: flooring a concave function does not yield a
    discretely concave sequence. The 15 -> 16 step at a gap of 8,000 is the clearest case."""

    def marginals(gap: int) -> list[int]:
        return [_gain(gap, c + 1) - _gain(gap, c) for c in range(1, RELATIONSHIP_INVESTMENT_CAP)]

    twelve_k = marginals(12_000)
    assert twelve_k[:5] == [24, 24, 24, 23, 24]
    rises = sum(1 for a, b in itertools.pairwise(twelve_k) if b > a)
    assert rises == 46

    eight_k = marginals(8_000)
    assert eight_k[4] == 15
    assert eight_k[5] == 16


# --- boundaries, and the zero-effect cases the caller must reject -------------


def test_capital_outside_the_band_raises_rather_than_clamping() -> None:
    """T8b. Raising is the point: `BlocInvestment` already rejects these, so reaching this function
    with one means the decision schema and the formula have drifted, and clamping is exactly how
    that drift would go unnoticed."""
    for bad in (0, -1, RELATIONSHIP_INVESTMENT_CAP + 1, 500):
        with pytest.raises(ValueError, match=r"\[1, 200\]"):
            relationship_gain_bps(opening_relationship_bps=0, political_capital=bad)


@pytest.mark.parametrize(
    ("gap", "capital"),
    [
        pytest.param(0, RELATIONSHIP_INVESTMENT_CAP, id="at-the-ceiling"),
        pytest.param(1, RELATIONSHIP_INVESTMENT_CAP, id="gap-1-truncates-away"),
        pytest.param(2, RELATIONSHIP_INVESTMENT_CAP, id="gap-2-truncates-away"),
        pytest.param(100, 1, id="small-gap-small-capital"),
        pytest.param(400, 1, id="larger-gap-one-point"),
    ],
)
def test_guaranteed_zero_effect_cases_return_zero(gap: int, capital: int) -> None:
    """These are what slot 1 must refuse. Note that only the first has `gap == 0`: a rejection rule
    written against the gap instead of the computed gain would let the other four through and
    charge the player for nothing."""
    assert _gain(gap, capital) == 0


def test_a_positive_gap_can_still_buy_nothing() -> None:
    """Stated on its own because it is the whole reason the caller tests the gain, not the gap."""
    assert _gain(400, 1) == 0
    assert 400 > 0


def test_one_point_of_capital_buys_something_at_every_real_scenario_gap() -> None:
    """The three calibrated targets open far above any tie or truncation region, so the mechanic is
    never degenerate where a player actually meets it: `deficit_demo` 12,000,
    `decree_state` 18,000, `tiny_valid` 8,000."""
    for gap in (12_000, 18_000, 8_000):
        assert _gain(gap, 1) > 0


@pytest.mark.parametrize("gap", [12_000, 18_000, 8_000])
def test_strict_improvement_holds_at_the_three_calibrated_gaps(gap: int) -> None:
    """Strictness is claimed ONLY here, as three concrete cases -- never as a rule with a gap
    threshold attached (see `test_measured_adjacent_capital_values_tie_for_small_gaps`)."""
    for c in range(1, RELATIONSHIP_INVESTMENT_CAP):
        assert _gain(gap, c + 1) > _gain(gap, c)


def test_the_worked_scenario_gains_are_exact() -> None:
    """The three figures the calibration suite and the manual walkthrough both quote."""
    assert relationship_gain_bps(opening_relationship_bps=-2_000, political_capital=100) == 2_000
    assert relationship_gain_bps(opening_relationship_bps=-8_000, political_capital=200) == 5_142
    assert relationship_gain_bps(opening_relationship_bps=2_000, political_capital=100) == 1_333
