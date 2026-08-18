"""Pure legislative-support formulas: how a bloc votes, and whether a chamber carries (Phase 3B1).

**No function in this module accepts a constitutional type.** Not `ConstitutionState`, not
`Legislature`, `DecreeAuthority`, `JudicialReview` or any other axis — this module does not import
`simulation.constitution` at all. Every signature takes integers and legislative enums and returns
integers. That is the same structural guarantee `simulation.legitimacy` carries, for the same
reason: the *form* of a government must never decide how a vote *goes*. The constitution is read
in exactly one place in Phase 3B1 — routing, which decides which chambers must approve and whether
a decree is legal. That is structure deciding procedure, never deservingness.
`test_legislative_neutrality.py` pins both halves.

## The support chain

A bloc's vote is built in four named steps, each of which the report keeps so a reader can
re-derive the total without trusting it:

1. **Baseline** — the party's formal role, adjusted by this bloc's own relationship with the
   government. Role sets where a caucus starts; relationship is what moves it from there.
2. **Policy compatibility** — how the proposal's actual content sits with what this bloc wants,
   on two independent axes (tax and spending).
3. **Influence** — political capital spent on this bloc specifically, linear then hard-capped.
4. **Discipline** — amplification of whichever way the bloc already leans, away from the 50%
   midpoint. Zero discipline gives pure proportionality; full discipline doubles the lean.

Every step is exact integer arithmetic rounded by `core.politics.trunc_div_toward_zero`, which
truncates toward zero rather than negative infinity, so a preference against a change and an
equal-magnitude preference for it produce equal-magnitude opposite components with no directional
bias. No floats, no randomness, no time access.

## Change direction is stored separately from change intensity

A proposal's effect on a bloc needs both *which way* policy moves and *how far*. Storing a single
signed "percent change" cannot express raising spending from zero: the relative change is
undefined, and the honest-looking answer — 0% — reads as "nothing changed" when creating a program
where none existed is the *largest* spending change available. So direction is a
`ChangeDirection` and intensity is a saturated magnitude, and the `old == 0` cases are decided
**before any division** — the same rule, and the same reason, as `legitimacy.py`'s zero-baseline
branch.

## What is deliberately not here

No quorum, no casting vote, no speaker, no conference committee, no override, no abstention. None
of those exist anywhere in state, and inventing one would be an undefined mechanism. A chamber
carries on a strict majority of its own seats or it does not carry; **a tie fails**, and no
tie-breaker is consulted because there is none to consult.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.politics import clamp_bps, trunc_div_toward_zero
from app.simulation.legislature import AmendmentThreshold, ChangeDirection, GovernmentRole

ROLE_ANCHOR_BPS: dict[GovernmentRole, int] = {
    GovernmentRole.COALITION: 8_000,
    GovernmentRole.CONFIDENCE_AND_SUPPLY: 6_000,
    GovernmentRole.OPPOSITION: 2_000,
}
"""Where a bloc's support starts, from its party's formal role alone.

A party formally in government begins strongly supportive (8,000). A confidence-and-supply partner
supports the government's *survival*, which is not the same as supporting its policy, so it starts
lower (6,000). Opposition starts hostile but **not at zero** (2,000): an unbuyable opposition would
make every minority government's arithmetic identical, and would delete the bargaining this phase
exists to introduce.
"""

RELATIONSHIP_WEIGHT_BPS = 2_000
"""How far a bloc's own relationship with the government moves it off its role anchor: at most
±20 percentage points. Deliberately smaller than the gaps between the anchors, so a formal role
still dominates — a hostile coalition bloc remains more supportive than a friendly opposition
bloc, which is what makes joining a government mean something."""

TAX_FULL_INTENSITY_BPS = 1_000
"""The combined tax-rate change that counts as maximum intensity: 10 percentage points. Larger
changes saturate rather than scaling without limit."""

SPENDING_FULL_INTENSITY_BPS = 1_000
"""The relative change in total program spending that counts as maximum intensity: 10%."""

TAX_WEIGHT_BPS = 2_000
"""How far the tax axis alone can move a bloc's support: at most ±20 percentage points."""

SPENDING_WEIGHT_BPS = 2_000
"""How far the spending axis alone can move a bloc's support: at most ±20 percentage points, so
policy content moves support by at most ±40 pp combined — enough to flip a marginal bloc, never
enough to turn a committed opponent into a supporter on content alone."""

INFLUENCE_BPS_PER_CAPITAL = 10
"""Support bought per unit of political capital: 100 capital buys +10 percentage points in one
bloc. Linear, so the price of a vote is trivially re-derivable rather than being a curve."""

MAX_INFLUENCE_BPS = 3_000
"""The hard ceiling on bought support: +30 percentage points in any one bloc, no matter how much
capital is committed. Money alone can never carry a chamber — this is what keeps a sufficiently
hostile legislature genuinely unpassable rather than merely expensive."""

DECREE_POLITICAL_CAPITAL_COST = 250
"""What committing to a decree costs, where the constitution authorises one.

Fixed rather than scaled by the size of the change: a size-scaled cost would need a second
calibration axis, and would make "split the change across two turns" a dominant exploit.
"""

CONSTITUTIONAL_AMENDMENT_DECREE_COST = 400
"""Flat political-capital cost for the legislature-absent amendment route (Phase 3C)."""


@dataclass(frozen=True, slots=True)
class PolicyChange:
    """One policy axis's proposed movement: which way, and how far on a saturated 0-10,000 scale.

    `intensity_bps` is always nonnegative — direction carries the sign. `UNCHANGED` always pairs
    with intensity 0, but the converse does not hold: a change too small to register against its
    full-intensity constant keeps its true direction and an intensity of 0, because reporting it
    as `UNCHANGED` would assert that nothing moved when something did.
    """

    direction: ChangeDirection
    intensity_bps: int


@dataclass(frozen=True, slots=True)
class BlocSupport:
    """One bloc's support for a proposal, with every step of the chain that produced it.

    Kept in full rather than collapsed to the final number so the report can show a player *why*
    a caucus voted as it did, and so a validator can replay each step independently.
    """

    baseline_support_bps: int
    policy_compatibility_bps: int
    influence_bps: int
    raw_support_bps: int
    final_support_bps: int
    effective_support_bps: int


def baseline_support_bps(*, role: GovernmentRole, relationship_bps: int) -> int:
    """Where this bloc starts before the proposal's content is considered at all: its party's role
    anchor, moved by its own relationship with the government."""
    _reject_out_of_range(relationship_bps, name="relationship_bps", signed=True)
    return clamp_bps(
        ROLE_ANCHOR_BPS[role]
        + trunc_div_toward_zero(relationship_bps * RELATIONSHIP_WEIGHT_BPS, BPS_DENOMINATOR)
    )


def tax_policy_change(*, rate_changes: tuple[tuple[int, int], ...]) -> PolicyChange:
    """The proposal's combined tax movement, from `(current_rate_bps, target_rate_bps)` pairs for
    the rates the decision actually sets — rates it leaves alone contribute nothing.

    Always well defined, because this is a difference of rates and never a ratio: there is no
    undefined case to branch on, unlike spending.
    """
    delta_bps = sum(target - current for current, target in rate_changes)
    intensity_bps = min(
        BPS_DENOMINATOR,
        trunc_div_toward_zero(abs(delta_bps) * BPS_DENOMINATOR, TAX_FULL_INTENSITY_BPS),
    )
    return PolicyChange(direction=_direction_of(delta_bps), intensity_bps=intensity_bps)


def spending_policy_change(*, opening_total: int, proposed_total: int) -> PolicyChange:
    """The proposal's movement in total program spending, as a direction and a saturated
    intensity.

    Four exhaustive branches, and the two with `opening_total == 0` are decided **before any
    division**, so the ratio is never evaluated where it is undefined:

    | opening | proposed | direction | intensity |
    |---|---|---|---|
    | 0 | 0 | `UNCHANGED` | 0 — nothing changed |
    | 0 | > 0 | `INCREASE` | maximum — creating a program where none existed is the largest
      spending change available, not the smallest |
    | > 0 | 0 | `DECREASE` | maximum — exactly -100%, which saturates |
    | > 0 | > 0 | sign of the difference | the relative change, saturated |
    """
    if opening_total < 0 or proposed_total < 0:
        raise ValueError(
            f"program spending cannot be negative, got opening={opening_total} "
            f"proposed={proposed_total}"
        )

    if opening_total == 0:
        if proposed_total == 0:
            return PolicyChange(direction=ChangeDirection.UNCHANGED, intensity_bps=0)
        return PolicyChange(direction=ChangeDirection.INCREASE, intensity_bps=BPS_DENOMINATOR)

    if proposed_total == 0:
        return PolicyChange(direction=ChangeDirection.DECREASE, intensity_bps=BPS_DENOMINATOR)

    relative_change_bps = trunc_div_toward_zero(
        (proposed_total - opening_total) * BPS_DENOMINATOR, opening_total
    )
    intensity_bps = min(
        BPS_DENOMINATOR,
        trunc_div_toward_zero(
            abs(relative_change_bps) * BPS_DENOMINATOR, SPENDING_FULL_INTENSITY_BPS
        ),
    )
    return PolicyChange(
        direction=_direction_of(proposed_total - opening_total), intensity_bps=intensity_bps
    )


def policy_compatibility_bps(
    *,
    tax_change: PolicyChange,
    tax_preference_bps: int,
    spending_change: PolicyChange,
    spending_preference_bps: int,
) -> int:
    """How the proposal's content sits with this bloc's own preferences, on `[-4,000, +4,000]`.

    The two axes are independent and simply add: a bloc can like a budget's spending and hate its
    taxes, and the sum is how it feels about the budget.
    """
    _reject_out_of_range(tax_preference_bps, name="tax_preference_bps", signed=True)
    _reject_out_of_range(spending_preference_bps, name="spending_preference_bps", signed=True)
    return _axis_component_bps(
        preference_bps=tax_preference_bps, change=tax_change, weight_bps=TAX_WEIGHT_BPS
    ) + _axis_component_bps(
        preference_bps=spending_preference_bps,
        change=spending_change,
        weight_bps=SPENDING_WEIGHT_BPS,
    )


def influence_bps(*, political_capital: int) -> int:
    """Support bought in one bloc with `political_capital`: linear, then hard-capped.

    One rounding-free multiplication and one `min`, so a player can compute the price of a vote in
    their head — and the cap makes the ceiling a rule rather than an emergent accident.
    """
    if political_capital < 0:
        raise ValueError(f"political_capital cannot be negative, got {political_capital}")
    return min(MAX_INFLUENCE_BPS, political_capital * INFLUENCE_BPS_PER_CAPITAL)


def resolve_bloc_support(
    *,
    role: GovernmentRole,
    relationship_bps: int,
    tax_change: PolicyChange,
    tax_preference_bps: int,
    spending_change: PolicyChange,
    spending_preference_bps: int,
    allocated_political_capital: int,
    discipline_bps: int,
) -> BlocSupport:
    """The whole chain for one bloc, from role anchor to whipped final position.

    Discipline amplifies the bloc's lean away from the 50% midpoint: a caucus that already favours
    the proposal is whipped further toward it, one that opposes it further against. Zero discipline
    leaves the bloc exactly where content and bargaining put it; full discipline doubles its
    distance from the midpoint, saturating at the ends of the scale. It is applied **last**, after
    influence, so bought support is amplified by the same whip as authentic support — a
    well-disciplined party delivers the votes it was paid for.
    """
    _reject_out_of_range(discipline_bps, name="discipline_bps", signed=False)

    baseline = baseline_support_bps(role=role, relationship_bps=relationship_bps)
    compatibility = policy_compatibility_bps(
        tax_change=tax_change,
        tax_preference_bps=tax_preference_bps,
        spending_change=spending_change,
        spending_preference_bps=spending_preference_bps,
    )
    influence = influence_bps(political_capital=allocated_political_capital)

    raw = clamp_bps(baseline + compatibility)
    final = clamp_bps(raw + influence)
    midpoint = BPS_DENOMINATOR // 2
    effective = clamp_bps(
        final + trunc_div_toward_zero((final - midpoint) * discipline_bps, BPS_DENOMINATOR)
    )

    return BlocSupport(
        baseline_support_bps=baseline,
        policy_compatibility_bps=compatibility,
        influence_bps=influence,
        raw_support_bps=raw,
        final_support_bps=final,
        effective_support_bps=effective,
    )


def resolve_amendment_support(
    *,
    role: GovernmentRole,
    relationship_bps: int,
    discipline_bps: int,
    allocated_political_capital: int,
) -> BlocSupport:
    """Resolve support for a constitutional amendment without inventing policy content.

    The chain is the budget-vote chain with the tax/spending compatibility step fixed at zero:
    role plus relationship establishes the baseline, influence moves it, and discipline amplifies
    the resulting lean away from the midpoint.
    """
    _reject_out_of_range(discipline_bps, name="discipline_bps", signed=False)

    baseline = baseline_support_bps(role=role, relationship_bps=relationship_bps)
    influence = influence_bps(political_capital=allocated_political_capital)
    final = clamp_bps(baseline + influence)
    midpoint = BPS_DENOMINATOR // 2
    effective = clamp_bps(
        final + trunc_div_toward_zero((final - midpoint) * discipline_bps, BPS_DENOMINATOR)
    )
    return BlocSupport(
        baseline_support_bps=baseline,
        policy_compatibility_bps=0,
        influence_bps=influence,
        raw_support_bps=baseline,
        final_support_bps=final,
        effective_support_bps=effective,
    )


def required_yes_seats(*, total_seats: int) -> int:
    """The strict majority of a chamber: `total_seats // 2 + 1`.

    100 seats require 51, so an even split of 50 does not carry; 99 seats require 50, so 49 does
    not. **A tie fails**, and nothing is consulted to break it.
    """
    if total_seats <= 0:
        raise ValueError(f"a chamber must have at least one seat, got {total_seats}")
    return total_seats // 2 + 1


def required_amendment_yes_seats(*, total_seats: int, difficulty: AmendmentThreshold) -> int:
    """The constitutional passage threshold for one chamber."""
    if total_seats <= 0:
        raise ValueError(f"a chamber must have at least one seat, got {total_seats}")
    if difficulty is AmendmentThreshold.SIMPLE_MAJORITY:
        return required_yes_seats(total_seats=total_seats)
    if difficulty is AmendmentThreshold.SUPERMAJORITY:
        return (total_seats * 2 + 2) // 3
    return (total_seats * 3 + 3) // 4


def chamber_carries(*, supporting_seats: int, total_seats: int) -> bool:
    """Whether one chamber carries the proposal on its own seats, against its own size.

    Each chamber is judged independently and never against a pooled bicameral tally: two chambers
    that vote as one are one chamber, and pooling would let a large friendly lower house drown out
    a hostile upper house entirely.
    """
    return supporting_seats >= required_yes_seats(total_seats=total_seats)


def _direction_of(delta: int) -> ChangeDirection:
    if delta > 0:
        return ChangeDirection.INCREASE
    if delta < 0:
        return ChangeDirection.DECREASE
    return ChangeDirection.UNCHANGED


def _axis_component_bps(*, preference_bps: int, change: PolicyChange, weight_bps: int) -> int:
    """One axis's contribution: preference scaled by how far policy moves, then by the axis
    weight, then signed by which way it moved.

    A bloc that wants higher taxes is pleased by a rise and displeased by a cut of the same size,
    so the direction flips the sign of an otherwise identical magnitude.
    """
    if change.direction is ChangeDirection.UNCHANGED:
        return 0
    magnitude = trunc_div_toward_zero(preference_bps * change.intensity_bps, BPS_DENOMINATOR)
    weighted = trunc_div_toward_zero(magnitude * weight_bps, BPS_DENOMINATOR)
    return -weighted if change.direction is ChangeDirection.DECREASE else weighted


def _reject_out_of_range(value: int, *, name: str, signed: bool) -> None:
    low = -BPS_DENOMINATOR if signed else 0
    if not low <= value <= BPS_DENOMINATOR:
        raise ValueError(f"{name} must be within [{low}, {BPS_DENOMINATOR}], got {value}")
