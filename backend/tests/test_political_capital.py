"""Tests for `simulation.legitimacy`'s political-capital formulas (Phase 3A, T-P1..T-P4).

Political capital is a bounded, spendable governing resource. Nothing spends it in Phase 3A — the
`spent` parameter exists so the reconciliation identity shipped now is already the final one — so
these tests pin the regeneration curve, the capacity clamp, and the identity itself.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.simulation.legitimacy import (
    LEGITIMACY_REGENERATION_COEFFICIENT,
    POLITICAL_CAPITAL_BASE_REGENERATION,
    political_capital_regeneration,
    resolve_political_capital,
)

# --- T-P1: the regeneration curve --------------------------------------------


@pytest.mark.parametrize(
    ("legitimacy_bps", "expected"),
    [
        pytest.param(0, 200, id="zero-legitimacy-floor"),
        pytest.param(2_500, 275, id="quarter"),
        pytest.param(5_000, 350, id="half"),
        pytest.param(6_000, 380, id="deficit-demo-opening"),
        pytest.param(7_000, 410, id="tiny-valid-opening"),
        pytest.param(7_500, 425, id="three-quarters"),
        pytest.param(10_000, 500, id="full-legitimacy-ceiling"),
    ],
)
def test_regeneration_matches_the_calibration_table(legitimacy_bps: int, expected: int) -> None:
    assert political_capital_regeneration(legitimacy_bps=legitimacy_bps) == expected


def test_an_illegitimate_government_is_constrained_never_frozen() -> None:
    """The base floor exists so zero legitimacy still permits some capacity to act; a government
    unable to regenerate at all would be a removal condition, and removal is Phase 3C."""
    assert political_capital_regeneration(legitimacy_bps=0) == POLITICAL_CAPITAL_BASE_REGENERATION
    assert POLITICAL_CAPITAL_BASE_REGENERATION > 0


def test_full_legitimacy_regenerates_two_and_a_half_times_the_floor() -> None:
    full = political_capital_regeneration(legitimacy_bps=10_000)
    assert full == POLITICAL_CAPITAL_BASE_REGENERATION + LEGITIMACY_REGENERATION_COEFFICIENT
    assert full * 2 == POLITICAL_CAPITAL_BASE_REGENERATION * 5  # 500 == 200 * 2.5


# --- T-P2: the capacity clamp -------------------------------------------------


@pytest.mark.parametrize(
    ("opening", "capacity", "legitimacy_bps", "expected_closing"),
    [
        pytest.param(900, 1_000, 6_000, 1_000, id="clamped-from-1280"),
        pytest.param(980, 1_000, 6_000, 1_000, id="clamped-from-1360"),
        pytest.param(1_000, 1_000, 6_000, 1_000, id="already-at-capacity"),
        pytest.param(500, 1_000, 7_100, 913, id="tiny-valid-turn-1-uncapped"),
        pytest.param(300, 800, 6_050, 681, id="deficit-demo-turn-1-uncapped"),
    ],
)
def test_capacity_clamp(
    opening: int, capacity: int, legitimacy_bps: int, expected_closing: int
) -> None:
    _, closing = resolve_political_capital(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=0
    )
    assert closing == expected_closing


def test_capital_at_capacity_stays_there_indefinitely() -> None:
    """`tiny_valid` reaches capacity at turn 2 and holds it for the rest of the soak."""
    capital = 1_000
    for _ in range(50):
        _, capital = resolve_political_capital(
            opening=capital, capacity=1_000, legitimacy_bps=7_500, spent=0
        )
        assert capital == 1_000


# --- T-P3: the reconciliation identity ---------------------------------------


@given(
    opening=st.integers(min_value=0, max_value=100_000),
    capacity=st.integers(min_value=1, max_value=100_000),
    legitimacy_bps=st.integers(min_value=0, max_value=10_000),
)
def test_closing_matches_the_identity_and_is_never_negative(
    opening: int, capacity: int, legitimacy_bps: int
) -> None:
    regeneration, closing = resolve_political_capital(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=0
    )
    assert closing == min(capacity, opening + regeneration - 0)
    assert closing >= 0


@given(
    opening=st.integers(min_value=0, max_value=100_000),
    capacity=st.integers(min_value=1, max_value=100_000),
    legitimacy_bps=st.integers(min_value=0, max_value=10_000),
    spent=st.integers(min_value=0, max_value=100_000),
)
def test_identity_holds_for_arbitrary_spending_too(
    opening: int, capacity: int, legitimacy_bps: int, spent: int
) -> None:
    """Phase 3A never spends, but the identity is already the final one, so it is property-tested
    across the whole spending range Phase 3B uses."""
    regeneration = political_capital_regeneration(legitimacy_bps=legitimacy_bps)
    if spent > opening:
        with pytest.raises(ValueError, match="exceeds opening"):
            resolve_political_capital(
                opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=spent
            )
        return
    reported_regeneration, closing = resolve_political_capital(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=spent
    )
    assert reported_regeneration == regeneration
    assert closing == min(capacity, opening + regeneration - spent)
    assert closing >= 0


def test_spending_more_than_available_is_rejected_not_silently_floored() -> None:
    with pytest.raises(ValueError, match="exceeds opening"):
        resolve_political_capital(opening=10, capacity=1_000, legitimacy_bps=0, spent=1_000)


def test_negative_spending_is_rejected() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        resolve_political_capital(opening=10, capacity=1_000, legitimacy_bps=0, spent=-1)


# --- T-S1b (Phase 3B1): capital is spent against opening, never against income ---


def test_spending_against_this_turns_regeneration_is_rejected() -> None:
    """The band the tightened guard closes. A government holding 100 with 200 of regeneration
    coming could once have committed 300; it can no longer commit 101.

    Regeneration is derived from *closing* legitimacy, which does not exist when a government
    decides what to attempt. Allowing a commitment against it would be a rule no player could
    follow, because the amount would be unknowable at the moment of the choice.
    """
    regeneration = political_capital_regeneration(legitimacy_bps=0)
    assert regeneration > 0  # sanity: there really is income to spend against

    with pytest.raises(ValueError, match="exceeds opening"):
        resolve_political_capital(opening=100, capacity=10_000, legitimacy_bps=0, spent=101)


def test_spending_exactly_the_opening_stock_is_allowed() -> None:
    """The boundary is inclusive: a government may commit everything it holds, and ends the turn
    on that turn's regeneration alone."""
    regeneration, closing = resolve_political_capital(
        opening=250, capacity=10_000, legitimacy_bps=6_000, spent=250
    )
    assert closing == regeneration


def test_tightening_the_guard_did_not_move_any_closing_value() -> None:
    """Only admissibility changed, never arithmetic. Every commitment that was legal before is
    legal now and produces the identical closing stock."""
    for spent in (0, 1, 125, 249, 250):
        _, closing = resolve_political_capital(
            opening=250, capacity=1_000, legitimacy_bps=6_000, spent=spent
        )
        assert closing == min(1_000, 250 + 380 - spent)


# --- T-P4: regeneration rises monotonically with legitimacy ------------------


@given(
    legitimacy_a=st.integers(min_value=0, max_value=10_000),
    legitimacy_b=st.integers(min_value=0, max_value=10_000),
)
def test_regeneration_is_monotonic_in_legitimacy(legitimacy_a: int, legitimacy_b: int) -> None:
    low, high = sorted((legitimacy_a, legitimacy_b))
    assert political_capital_regeneration(legitimacy_bps=low) <= political_capital_regeneration(
        legitimacy_bps=high
    )


# --- Phase 3B1: political capital is per-turn governing bandwidth, not lasting depletion ------
#
# Phase 3B1 makes `spent` reachable for the first time, which makes ONE claim load-bearing that
# Phase 3A never had to state: what a commitment actually COSTS a government. The honest answer
# is "it depends where the government sits relative to its capacity", and ADR 0010 documents it
# as such -- explicitly RETRACTING the stronger claim that every route always carries a lasting
# opportunity cost. These tests pin all three branches of that rule so the documented behavior
# cannot drift away from the code silently.
#
# The cost of committing `C` is measured against the no-action counterfactual -- what closing
# capital WOULD have been had the government committed nothing that turn:
#     counterfactual = min(capacity, opening + regeneration)
#     actual         = min(capacity, opening - C + regeneration)
#     stock_cost     = counterfactual - actual


def _stock_cost(*, opening: int, capacity: int, legitimacy_bps: int, committed: int) -> int:
    _regen, counterfactual = resolve_political_capital(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=0
    )
    _regen, actual = resolve_political_capital(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, spent=committed
    )
    return counterfactual - actual


def test_below_capacity_a_commitment_costs_exactly_its_face_value() -> None:
    """Branch 1 -- `opening + regeneration <= capacity`. This is the government under pressure,
    the case where the choice matters most: `deficit_demo` opens at 300/800 with regeneration 380
    (300 + 380 = 680 <= 800), so committing 250 costs the full 250."""
    regeneration = political_capital_regeneration(legitimacy_bps=6_000)
    assert regeneration == 380
    assert 300 + regeneration <= 800  # the branch precondition, stated not assumed

    assert _stock_cost(opening=300, capacity=800, legitimacy_bps=6_000, committed=250) == 250

    _regen, closing = resolve_political_capital(
        opening=300, capacity=800, legitimacy_bps=6_000, spent=250
    )
    assert closing == 430  # 300 - 250 + 380


def test_at_capacity_regeneration_can_refund_a_commitment_entirely() -> None:
    """Branch 2 -- `opening - committed + regeneration >= capacity`. THE RETRACTED CLAIM, pinned:
    a government sitting at capacity can commit 250 (a decree) and close the turn still at
    capacity, having paid nothing from stock. The commitment is still real -- it is bounded by
    opening capital, recorded in the report and reconciled -- but it leaves no mark on the stock.
    This is why Phase 3B1 calls political capital per-turn governing BANDWIDTH rather than a
    budget that draws down."""
    regeneration = political_capital_regeneration(legitimacy_bps=6_100)
    assert regeneration == 383
    assert 1_000 - 250 + regeneration >= 1_000  # the branch precondition

    assert _stock_cost(opening=1_000, capacity=1_000, legitimacy_bps=6_100, committed=250) == 0

    _regen, closing = resolve_political_capital(
        opening=1_000, capacity=1_000, legitimacy_bps=6_100, spent=250
    )
    assert closing == 1_000  # still exactly at capacity


def test_straddling_the_cap_a_commitment_costs_strictly_between_zero_and_its_face_value() -> None:
    """Branch 3 -- neither precondition holds, so the commitment is partially refunded. At
    700/1,000 with regeneration 439 the no-action close would clamp at 1,000, but committing 250
    lands at 889 -- a real cost of 111, strictly inside `(0, 250)`."""
    regeneration = political_capital_regeneration(legitimacy_bps=7_991)
    assert regeneration == 439
    assert 700 + regeneration > 1_000  # not branch 1
    assert 700 - 250 + regeneration < 1_000  # not branch 2

    cost = _stock_cost(opening=700, capacity=1_000, legitimacy_bps=7_991, committed=250)
    assert cost == 111
    assert 0 < cost < 250


@given(
    opening=st.integers(min_value=0, max_value=100_000),
    capacity=st.integers(min_value=1, max_value=100_000),
    legitimacy_bps=st.integers(min_value=0, max_value=10_000),
    committed=st.integers(min_value=0, max_value=100_000),
)
def test_the_stock_cost_of_a_commitment_is_always_between_zero_and_its_face_value(
    opening: int, capacity: int, legitimacy_bps: int, committed: int
) -> None:
    """The general bound the three worked branches above are instances of: a commitment can never
    cost a government MORE than it committed, and can never pay it back extra."""
    if committed > opening:
        return  # rejected outright by the R2 guard; covered by its own test above
    cost = _stock_cost(
        opening=opening, capacity=capacity, legitimacy_bps=legitimacy_bps, committed=committed
    )
    assert 0 <= cost <= committed
