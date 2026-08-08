"""Tests for `app.simulation.apportionment` — the chamber-level largest-remainder algorithm and
its five guaranteed properties (Phase 3B1, T-A1..T-A8).

The five proofs P1-P5 are stated in the module docstring; each has a dedicated section below. The
randomized sections use a seeded `random.Random`, so a failure is reproducible from the seed alone
rather than only on the run that happened to find it.
"""

from __future__ import annotations

import random

import pytest

from app.simulation.apportionment import (
    SeatSupport,
    apportion_supporting_seats,
)

FULL_SUPPORT_BPS = 10_000

# Deliberately includes both ends of the scale and both values adjacent to them: a row at 10,000
# has `base == seats` and would break P2 if it ever won a bonus, and a row at 1 has the smallest
# possible positive remainder.
EDGE_SUPPORT_VALUES = (0, 1, 9_999, 10_000)


def _random_chamber(rng: random.Random, *, max_rows: int = 10) -> tuple[SeatSupport, ...]:
    """A random chamber, biased toward the values most likely to break the guarantees: every row
    has a one-in-three chance of taking an edge support value rather than a uniform one."""
    return tuple(
        SeatSupport(
            party_id=f"p{party}",
            bloc_id=f"b{bloc}",
            seats=rng.randint(0, 200),
            effective_support_bps=(
                rng.choice(EDGE_SUPPORT_VALUES)
                if rng.random() < 1 / 3
                else rng.randint(0, FULL_SUPPORT_BPS)
            ),
        )
        # A flat `(party, bloc)` grid keeps every pair unique without a rejection loop.
        for party in range(rng.randint(1, max_rows))
        for bloc in range(rng.randint(1, 3))
    )


# --- T-A1 (P1): the rows sum to the chamber's true support mass ---------------


def test_rows_sum_to_the_reported_chamber_total() -> None:
    rng = random.Random(20260808)
    for _ in range(20_000):
        rows = _random_chamber(rng)
        result = apportion_supporting_seats(rows=rows)

        expected_total = sum(r.seats * r.effective_support_bps for r in rows) // FULL_SUPPORT_BPS
        assert result.supporting_seats == expected_total
        assert sum(row.supporting_seats for row in result.rows) == expected_total


def test_the_total_is_the_undivided_sum_divided_once() -> None:
    """The whole point of the design: one division of the summed numerator, not a division per
    row. Two rows at 50% of one seat each support one seat between them — per-row truncation
    would say zero."""
    rows = (
        SeatSupport(party_id="pA", bloc_id="b1", seats=1, effective_support_bps=5_000),
        SeatSupport(party_id="pA", bloc_id="b2", seats=1, effective_support_bps=5_000),
    )
    assert apportion_supporting_seats(rows=rows).supporting_seats == 1


# --- T-A2 (P2): every row stays within its own seat count ---------------------


def test_supporting_seats_never_exceed_the_rows_own_seats() -> None:
    rng = random.Random(19890420)
    for _ in range(20_000):
        result = apportion_supporting_seats(rows=_random_chamber(rng))
        for row in result.rows:
            assert 0 <= row.supporting_seats <= row.seats
            assert row.supporting_seats == row.base + row.bonus
            assert row.bonus in (0, 1)


def test_a_row_at_full_support_never_receives_a_bonus_seat() -> None:
    """The only way P2 could fail. A full-support row already has `base == seats`, so one extra
    seat would put it over its own total — and its remainder is exactly 0, which is why the award
    list can never reach it."""
    rng = random.Random(20250101)
    for _ in range(20_000):
        result = apportion_supporting_seats(rows=_random_chamber(rng))
        for row in result.rows:
            if row.effective_support_bps == FULL_SUPPORT_BPS:
                assert row.remainder == 0
                assert row.bonus == 0
                assert row.supporting_seats == row.seats


def test_extras_are_strictly_fewer_than_the_positive_remainder_rows() -> None:
    """The P2 lemma itself, asserted directly rather than only through its consequence:
    `extras < |{i : remainder_i > 0}|`, so the sorted award list stops before the zero-remainder
    rows begin."""
    rng = random.Random(20240630)
    for _ in range(20_000):
        result = apportion_supporting_seats(rows=_random_chamber(rng))
        extras = sum(row.bonus for row in result.rows)
        positive_remainders = sum(1 for row in result.rows if row.remainder > 0)
        assert extras <= max(0, positive_remainders - 1)


def test_recorded_intermediates_replay_the_arithmetic() -> None:
    """The row keeps `numerator`, `base` and `remainder` so a validator can re-derive the result
    without recomputing support. They must actually agree with it."""
    rng = random.Random(20231111)
    for _ in range(5_000):
        result = apportion_supporting_seats(rows=_random_chamber(rng))
        for row in result.rows:
            assert row.numerator == row.seats * row.effective_support_bps
            assert row.base == row.numerator // FULL_SUPPORT_BPS
            assert row.remainder == row.numerator % FULL_SUPPORT_BPS


# --- T-A3 (P3): splitting a bloc changes nothing ------------------------------


def test_the_fragmentation_regression_one_hundred_blocs_at_sixty_percent() -> None:
    """The defect this module exists to fix. Per-row truncation gave **0** supporting seats for
    100 one-seat blocs at 60% support, and 60 for a single 100-seat bloc at the same support —
    a party was punished for recognising its own caucuses."""
    fragmented = tuple(
        SeatSupport(party_id="pA", bloc_id=f"b{i:03d}", seats=1, effective_support_bps=6_000)
        for i in range(100)
    )
    whole = (SeatSupport(party_id="pA", bloc_id="b1", seats=100, effective_support_bps=6_000),)

    assert apportion_supporting_seats(rows=fragmented).supporting_seats == 60
    assert apportion_supporting_seats(rows=whole).supporting_seats == 60


def test_splitting_a_row_leaves_the_chamber_total_unchanged() -> None:
    """`S1 * E + S2 * E == S * E` for `S1 + S2 == S`, and the total depends only on the summed
    numerator — so where the seats sit among identically-inclined blocs cannot matter."""
    rng = random.Random(20220314)
    for _ in range(5_000):
        rest = _random_chamber(rng, max_rows=4)
        seats = rng.randint(2, 200)
        support = rng.randint(0, FULL_SUPPORT_BPS)
        split_at = rng.randint(1, seats - 1)

        merged = (
            SeatSupport(party_id="zz", bloc_id="whole", seats=seats, effective_support_bps=support),
            *rest,
        )
        split = (
            SeatSupport(
                party_id="zz", bloc_id="part1", seats=split_at, effective_support_bps=support
            ),
            SeatSupport(
                party_id="zz",
                bloc_id="part2",
                seats=seats - split_at,
                effective_support_bps=support,
            ),
            *rest,
        )

        assert (
            apportion_supporting_seats(rows=merged).supporting_seats
            == apportion_supporting_seats(rows=split).supporting_seats
        )


# --- T-A4 (P4): input order cannot change the result --------------------------


def test_shuffling_the_input_produces_an_identical_mapping() -> None:
    """A scenario file that lists its parties in a different order must not get a different
    legislature. This is the property `integer_allocation` deliberately does NOT provide, and the
    reason this module sorts on row content instead of input position."""
    rng = random.Random(20210917)
    for _ in range(20_000):
        rows = _random_chamber(rng)
        shuffled = list(rows)
        rng.shuffle(shuffled)

        original = apportion_supporting_seats(rows=rows)
        reordered = apportion_supporting_seats(rows=tuple(shuffled))

        assert original.supporting_seats == reordered.supporting_seats
        assert {(r.party_id, r.bloc_id): r.supporting_seats for r in original.rows} == {
            (r.party_id, r.bloc_id): r.supporting_seats for r in reordered.rows
        }


def test_rows_are_returned_in_the_order_supplied() -> None:
    """Order-independence is about the *result*, not the layout: the caller's row order is
    preserved so it can zip the output against its own input."""
    rows = (
        SeatSupport(party_id="pZ", bloc_id="b1", seats=10, effective_support_bps=5_000),
        SeatSupport(party_id="pA", bloc_id="b1", seats=10, effective_support_bps=5_000),
    )
    result = apportion_supporting_seats(rows=rows)
    assert [(r.party_id, r.bloc_id) for r in result.rows] == [("pZ", "b1"), ("pA", "b1")]


# --- T-A5 (P5): ties break canonically ----------------------------------------


def test_identical_remainders_are_awarded_in_canonical_id_order() -> None:
    """Four rows, identical remainders, three seats to award. The winners are the three
    lexicographically smallest `(party_id, bloc_id)` pairs — and reversing the input does not
    move them."""
    rows = (
        SeatSupport(party_id="pA", bloc_id="b1", seats=1, effective_support_bps=7_500),
        SeatSupport(party_id="pA", bloc_id="b2", seats=1, effective_support_bps=7_500),
        SeatSupport(party_id="pB", bloc_id="b1", seats=1, effective_support_bps=7_500),
        SeatSupport(party_id="pB", bloc_id="b2", seats=1, effective_support_bps=7_500),
    )
    expected = {("pA", "b1"), ("pA", "b2"), ("pB", "b1")}

    for candidate in (rows, tuple(reversed(rows))):
        result = apportion_supporting_seats(rows=candidate)
        assert result.supporting_seats == 3
        assert {(r.party_id, r.bloc_id) for r in result.rows if r.bonus == 1} == expected


def test_the_tie_break_is_by_party_then_bloc_not_by_bloc_alone() -> None:
    """`(party_id, bloc_id)` is compared as a pair. If only `bloc_id` were consulted, `pB/b1`
    would beat `pA/b2` here; it does not."""
    rows = (
        SeatSupport(party_id="pB", bloc_id="b1", seats=1, effective_support_bps=5_000),
        SeatSupport(party_id="pA", bloc_id="b2", seats=1, effective_support_bps=5_000),
    )
    result = apportion_supporting_seats(rows=rows)
    assert result.supporting_seats == 1
    assert {(r.party_id, r.bloc_id) for r in result.rows if r.bonus == 1} == {("pA", "b2")}


# --- T-A6: the worked example from the plan -----------------------------------


def test_the_worked_majority_coalition_example() -> None:
    """Plan §7.9 case A. `gov/left` wins the single extra seat on a remainder of 6,880, just ahead
    of `opp/regional`'s 6,800 — the seat the earlier per-row truncation threw away."""
    rows = (
        SeatSupport(party_id="gov", bloc_id="mainstream", seats=45, effective_support_bps=10_000),
        SeatSupport(party_id="gov", bloc_id="left", seats=13, effective_support_bps=9_760),
        SeatSupport(party_id="opp", bloc_id="conservative", seats=32, effective_support_bps=0),
        SeatSupport(party_id="opp", bloc_id="regional", seats=10, effective_support_bps=680),
    )
    result = apportion_supporting_seats(rows=rows)

    by_bloc = {(r.party_id, r.bloc_id): r for r in result.rows}
    assert by_bloc[("gov", "mainstream")].supporting_seats == 45
    assert by_bloc[("gov", "left")].supporting_seats == 13
    assert by_bloc[("gov", "left")].remainder == 6_880
    assert by_bloc[("gov", "left")].bonus == 1
    assert by_bloc[("opp", "conservative")].supporting_seats == 0
    assert by_bloc[("opp", "regional")].supporting_seats == 0
    assert by_bloc[("opp", "regional")].remainder == 6_800
    assert result.supporting_seats == 58


# --- T-A7: degenerate chambers ------------------------------------------------


def test_an_empty_chamber_apportions_to_zero() -> None:
    result = apportion_supporting_seats(rows=())
    assert result.rows == ()
    assert result.supporting_seats == 0


def test_a_row_with_no_seats_contributes_nothing_at_any_support_level() -> None:
    """A bloc absent from this chamber still exists as a caucus; it just has no seats to lend."""
    rows = (
        SeatSupport(party_id="pA", bloc_id="b1", seats=0, effective_support_bps=10_000),
        SeatSupport(party_id="pA", bloc_id="b2", seats=7, effective_support_bps=10_000),
    )
    result = apportion_supporting_seats(rows=rows)
    assert result.supporting_seats == 7
    assert result.rows[0].supporting_seats == 0


def test_unanimous_and_unanimously_hostile_chambers() -> None:
    rows_for = (SeatSupport(party_id="pA", bloc_id="b1", seats=200, effective_support_bps=10_000),)
    rows_against = (SeatSupport(party_id="pA", bloc_id="b1", seats=200, effective_support_bps=0),)
    assert apportion_supporting_seats(rows=rows_for).supporting_seats == 200
    assert apportion_supporting_seats(rows=rows_against).supporting_seats == 0


# --- T-A8: rejected inputs ----------------------------------------------------


def test_negative_seats_are_rejected() -> None:
    rows = (SeatSupport(party_id="pA", bloc_id="b1", seats=-1, effective_support_bps=5_000),)
    with pytest.raises(ValueError, match="seats must be nonnegative"):
        apportion_supporting_seats(rows=rows)


@pytest.mark.parametrize("support", [-1, 10_001, 20_000])
def test_support_outside_the_scale_is_rejected(support: int) -> None:
    rows = (SeatSupport(party_id="pA", bloc_id="b1", seats=5, effective_support_bps=support),)
    with pytest.raises(ValueError, match="effective_support_bps must be within"):
        apportion_supporting_seats(rows=rows)


def test_a_duplicate_party_bloc_pair_is_rejected() -> None:
    """P5's determinism rests on `(party_id, bloc_id)` being a strict total order. A duplicate
    would quietly reduce it to a partial one, making the award set depend on input position
    again — so it is refused rather than tolerated."""
    rows = (
        SeatSupport(party_id="pA", bloc_id="b1", seats=5, effective_support_bps=5_000),
        SeatSupport(party_id="pA", bloc_id="b1", seats=6, effective_support_bps=6_000),
    )
    with pytest.raises(ValueError, match="duplicate apportionment row"):
        apportion_supporting_seats(rows=rows)


def test_the_same_bloc_id_under_different_parties_is_allowed() -> None:
    """Bloc ids are unique only within their party; `pA/left` and `pB/left` are different blocs."""
    rows = (
        SeatSupport(party_id="pA", bloc_id="left", seats=5, effective_support_bps=10_000),
        SeatSupport(party_id="pB", bloc_id="left", seats=5, effective_support_bps=10_000),
    )
    assert apportion_supporting_seats(rows=rows).supporting_seats == 10
