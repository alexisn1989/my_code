"""Chamber-level largest-remainder apportionment of support into seats.

Given a set of rows, each holding some number of seats and supporting a proposal to some degree
between 0 and 10,000 bps, this module answers one question: **how many of the chamber's seats
support the proposal?**

No I/O, no randomness, no state mutation, no clock. A plain function of its arguments.

## Why this is not `integer_allocation.largest_remainder_allocation`

Both use largest remainders; they solve different problems, and the difference is not cosmetic.

`integer_allocation` distributes a **fixed budget** across weights, so its divisor is the total
weight and its floors are `budget * weight_i // total_weight`. Here there is no budget to hand
out: each row's support mass is `seats_i * effective_support_bps_i`, and the divisor is the
**constant** `BPS_DENOMINATOR`. The chamber total is a consequence of the rows, not an input to be
divided among them.

The tie-break differs too, and that difference is the point. `integer_allocation` is explicitly
order-sensitive — it breaks ties by input position. This module breaks ties by
`(party_id, bloc_id)`, a key computed from row content alone, so the result cannot depend on the
order the caller happened to build its tuple in (P4 below). A legislature's seat count must not
change because a scenario file listed its parties differently.

## Why not the obvious per-row truncation

The naive version — `floor(seats_i * effective_i / 10_000)` per row, summed — discards every
row's remainder independently, which makes the answer depend on how finely the chamber happens to
be subdivided. **100 one-seat blocs at 60% support each yield 0 supporting seats**, while a single
100-seat bloc at 60% yields 60. That is a fragmentation bias with no political meaning: it says a
party that formally recognises its internal caucuses is worse at passing laws than an identical
party that does not. Apportioning at the chamber level removes it (P3).

## The five properties this module guarantees

- **P1** — `sum(supporting_seats) == target_total`, the chamber's true support mass.
- **P2** — `0 <= supporting_seats_i <= seats_i` for every row.
- **P3** — the chamber total is invariant to splitting or merging otherwise-identical rows.
- **P4** — the result does not depend on input order.
- **P5** — tie-breaking is deterministic, because `(party_id, bloc_id)` is unique.

P2 is the one that needs an argument rather than an inspection, since a row already at full
support has `base_i == seats_i` and one extra seat would break the bound. It cannot receive one:

> `numerator_i / 10_000 = base_i + remainder_i / 10_000`, so
> `target_total = sum(base_i) + floor(sum(remainder_i) / 10_000)`, hence
> `extras = floor(sum(remainder_i) / 10_000)`. Every `remainder_i < 10_000`, so
> `sum(remainder_i) < 10_000 * |{i : remainder_i > 0}|`, giving
> **`extras < |{i : remainder_i > 0}|`**.

`extras` is therefore *strictly fewer* than the number of rows with a positive remainder, and the
award list — sorted by descending remainder — never reaches a zero-remainder row. A full-support
row has `remainder_i == 0` and so is never awarded a bonus.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR


@dataclass(frozen=True, slots=True)
class SeatSupport:
    """One row entering apportionment: a bloc's seats in a single chamber, and how strongly it
    supports the proposal.

    `party_id` and `bloc_id` together address the bloc globally and are the canonical tie-break
    key. They carry no meaning to this module beyond being a unique, orderable label.
    """

    party_id: str
    bloc_id: str
    seats: int
    effective_support_bps: int


@dataclass(frozen=True, slots=True)
class ApportionedSeats:
    """One row's apportionment result, with every intermediate value it was derived from.

    The intermediates are kept rather than discarded so a reader — or a validator, or a save-file
    reconciler — can replay the arithmetic without recomputing support from scratch:
    `numerator == seats * effective_support_bps`, `base == numerator // 10_000`,
    `remainder == numerator % 10_000`, and `supporting_seats == base + bonus`.
    """

    party_id: str
    bloc_id: str
    seats: int
    effective_support_bps: int
    numerator: int
    base: int
    remainder: int
    bonus: int
    supporting_seats: int


@dataclass(frozen=True, slots=True)
class ChamberApportionment:
    """A whole chamber's apportionment: the per-row detail, and the total those rows sum to.

    `supporting_seats` is `sum(row.supporting_seats)` by construction (P1), stored once so callers
    comparing against a required majority do not each re-sum it.
    """

    rows: tuple[ApportionedSeats, ...]
    supporting_seats: int


def apportion_supporting_seats(*, rows: tuple[SeatSupport, ...]) -> ChamberApportionment:
    """Apportion one chamber's supporting seats by largest remainder.

    Raises `ValueError` for any input that would make the guarantees meaningless: a negative seat
    count, a support level outside `[0, 10_000]`, or a repeated `(party_id, bloc_id)` — the last
    because P5's determinism rests on that pair being a strict total order, and a duplicate would
    silently reduce it to a partial one.

    An empty chamber apportions to zero, which is the arithmetically correct answer rather than a
    special case: no rows means no support mass.
    """
    _reject_invalid_rows(rows)

    numerators = [row.seats * row.effective_support_bps for row in rows]
    bases = [numerator // BPS_DENOMINATOR for numerator in numerators]
    remainders = [numerator % BPS_DENOMINATOR for numerator in numerators]

    target_total = sum(numerators) // BPS_DENOMINATOR
    extras = target_total - sum(bases)

    # Sort by descending remainder, ties broken by ascending (party_id, bloc_id). Both keys come
    # from row content alone, never from input position — that is what makes P4 hold, and it is
    # the one place this module deliberately diverges from `integer_allocation`.
    order = sorted(
        range(len(rows)),
        key=lambda i: (-remainders[i], rows[i].party_id, rows[i].bloc_id),
    )
    bonuses = [0] * len(rows)
    for i in order[:extras]:
        bonuses[i] = 1

    return ChamberApportionment(
        rows=tuple(
            ApportionedSeats(
                party_id=row.party_id,
                bloc_id=row.bloc_id,
                seats=row.seats,
                effective_support_bps=row.effective_support_bps,
                numerator=numerators[i],
                base=bases[i],
                remainder=remainders[i],
                bonus=bonuses[i],
                supporting_seats=bases[i] + bonuses[i],
            )
            for i, row in enumerate(rows)
        ),
        supporting_seats=target_total,
    )


def _reject_invalid_rows(rows: tuple[SeatSupport, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.seats < 0:
            raise ValueError(
                f"seats must be nonnegative, got {row.seats} "
                f"for ({row.party_id!r}, {row.bloc_id!r})"
            )
        if not 0 <= row.effective_support_bps <= BPS_DENOMINATOR:
            raise ValueError(
                f"effective_support_bps must be within [0, {BPS_DENOMINATOR}], got "
                f"{row.effective_support_bps} for ({row.party_id!r}, {row.bloc_id!r})"
            )
        key = (row.party_id, row.bloc_id)
        if key in seen:
            raise ValueError(f"duplicate apportionment row for ({row.party_id!r}, {row.bloc_id!r})")
        seen.add(key)
