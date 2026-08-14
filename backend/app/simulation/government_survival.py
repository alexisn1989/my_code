"""Government-survival formulas: elections, coups, popular unrest, impeachment, and the transition
pressure a constitutional amendment leaves behind (Phase 3C).

No I/O, no randomness, no state mutation, no clock, no floating point — the same shape every other
pure formula module in this package follows (`legislative_voting`, `apportionment`, `legitimacy`,
`relationships`, `political_memory`). **Deliberately not added to `NEUTRAL_MODULES`**
(`tests/test_legislative_neutrality.py`): elections and coups are the opposite case from that
discipline by design — a scheduled election only exists because of
`national_election_interval_turns`, impeachment eligibility genuinely depends on `judicial_review`/
`executive_selection`. Every function here still accepts only plain ints/enums it declares itself,
never `ConstitutionState` — the constitution is read in `phases.py`'s slot handlers, the same split
`legislature.py`'s own routing check already uses.

Gate 3C1 implements only the election channel (§3.4). Coup/unrest/impeachment (§3.1-3.3) and
transition pressure (§3.5) are added in Gate 3C2/3C3.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.politics import clamp_bps, trunc_div_toward_zero

REQUIRED_ELECTION_SUPPORT_BPS = 5_000
LEGISLATIVE_SUPPORT_WEIGHT_BPS = 5_000
POPULATION_APPROVAL_WEIGHT_BPS = 4_000
LEGITIMACY_WEIGHT_BPS = 1_000
MAX_POLLING_UNCERTAINTY_SWING_BPS = 1_000
"""+/- 10 percentage points -- the widest a single seeded polling-uncertainty draw can move the
baseline support figure in either direction."""


@dataclass(frozen=True, slots=True)
class ElectionSupportAssessment:
    """Every intermediate value behind one election's baseline support figure, so the report can
    publish each one and a reader can re-derive the total without trusting it."""

    legislative_support_bps: int | None
    population_approval_bps: int
    legitimacy_bps: int
    baseline_support_bps: int


def legislative_support_bps(
    *, bloc_seats_and_relationships: tuple[tuple[int, int], ...], total_seats: int
) -> int:
    """One chamber's seat-weighted support for the incumbent's continuation, from
    `(seats, government_relationship_bps)` pairs across every bloc in that chamber -- reads exact
    seat counts, never a party's own already-rounded seat-share.

    Each bloc's relationship is rescaled from `[-10,000, +10,000]` to a `[0, 10,000]` support
    contribution (`(relationship_bps + 10,000) // 2`, via `trunc_div_toward_zero` on the summed
    numerator, never per-bloc, so a single rounding step governs the whole chamber), then
    seat-weighted.
    """
    if total_seats <= 0:
        raise ValueError(
            f"legislative_support_bps: total_seats must be positive, got {total_seats}"
        )
    weighted_sum = sum(
        seats * trunc_div_toward_zero(relationship_bps + BPS_DENOMINATOR, 2)
        for seats, relationship_bps in bloc_seats_and_relationships
    )
    return trunc_div_toward_zero(weighted_sum, total_seats)


def election_baseline_support_bps(
    *, legislative_support_bps: int | None, population_approval_bps: int, legitimacy_bps: int
) -> ElectionSupportAssessment:
    """The incumbent's baseline support ahead of a scheduled election's polling-uncertainty draw.

    `legislative_support_bps=None` means no legislature exists at all: the weighted mean
    renormalizes over the two remaining signals rather than fabricating a legislature that isn't
    there. No shipped scenario exercises this branch (all three ship with a legislature), but the
    formula must still be well-defined for one that doesn't.
    """
    if legislative_support_bps is None:
        weighted_sum = (
            population_approval_bps
            * (POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS)
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        )
        denominator = (
            POPULATION_APPROVAL_WEIGHT_BPS + LEGISLATIVE_SUPPORT_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
        )
    else:
        weighted_sum = (
            legislative_support_bps * LEGISLATIVE_SUPPORT_WEIGHT_BPS
            + population_approval_bps * POPULATION_APPROVAL_WEIGHT_BPS
            + legitimacy_bps * LEGITIMACY_WEIGHT_BPS
        )
        denominator = (
            LEGISLATIVE_SUPPORT_WEIGHT_BPS + POPULATION_APPROVAL_WEIGHT_BPS + LEGITIMACY_WEIGHT_BPS
        )
    baseline_bps = trunc_div_toward_zero(weighted_sum, denominator)
    return ElectionSupportAssessment(
        legislative_support_bps=legislative_support_bps,
        population_approval_bps=population_approval_bps,
        legitimacy_bps=legitimacy_bps,
        baseline_support_bps=baseline_bps,
    )


def final_election_support_bps(*, baseline_support_bps: int, polling_swing_bps: int) -> int:
    """`baseline_support_bps` plus the seeded polling-uncertainty draw, clamped to the support
    scale. A separate, tiny function so slot 13 and reconciliation both call the identical, single
    combining step rather than each re-deriving `clamp_bps(baseline + swing)` independently."""
    return clamp_bps(baseline_support_bps + polling_swing_bps)


def population_weighted_mean_bps(*, shares_and_metrics: tuple[tuple[int, int], ...]) -> int:
    """A population-share-weighted mean of an already-bps metric (e.g. approval, radicalization),
    over `(population_share_bps, metric_bps)` pairs. Plain integer arithmetic throughout -- no
    float is ever involved, since `PopulationGroupState`'s metrics are strict bps by construction
    (R8) and shares are supplied here already rescaled to bps by the caller."""
    total_share = sum(share for share, _ in shares_and_metrics)
    if total_share == 0:
        return 0
    weighted_sum = sum(share * metric for share, metric in shares_and_metrics)
    return trunc_div_toward_zero(weighted_sum, total_share)
