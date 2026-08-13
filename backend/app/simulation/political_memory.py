"""How a legislative bloc's relationship with the government moves on its own, without a fresh
investment decision (Phase 3B2B).

`simulation.relationships` answers "how much does committed capital improve a relationship, this
turn?" — and, by its own admission, is a ratchet: nothing there ever returns a negative value. This
module answers the three questions that make a relationship genuinely a *memory* rather than a
one-way meter: how far does an unmaintained relationship drift back toward the bloc's authored
disposition, how does a bloc react to policy content the government actually enacted, and what does
it cost a bloc to be governed by decree instead of a vote?

No I/O, no randomness, no state mutation, no clock, no floating point. Four plain functions of
their arguments, in the same shape as `apportionment`, `legislative_voting` and `relationships`.

## Decay: proportional, with a minimum step, and no overshoot

    magnitude = trunc(|deviation| * 1, 8)      then     magnitude = max(1, min(magnitude, |deviation|))

Plain truncation alone would let a deviation of 7 bps freeze forever (`trunc(7/8) == 0`), reviving
the ratchet in miniature. The minimum-one-bps floor guarantees strict progress and **exact
termination** at the baseline; the `min(magnitude, |deviation|)` cap guarantees the trajectory never
overshoots past it. `core.politics.trunc_div_toward_zero` is exactly symmetric
(`f(-n, d) == -f(n, d)`), so a bloc above its baseline and a bloc equally far below it decay by
identical magnitudes in opposite directions.

## Policy reaction: the same axis shape as the vote, computed independently

`legislative_voting.policy_compatibility_bps` is the vote-scoring formula and is not imported here —
this module reimplements the same two-axis shape (`core.politics.trunc_div_toward_zero`, a
preference scaled by intensity then by an axis weight, signed by direction) as an intentionally
separate, independently-written calculation, so a bug in one is not silently mirrored by the other.
`UNCHANGED` is a hard branch, not a numeric coincidence: re-submitting or holding an already-active
absolute target has a well-defined, exactly-zero reaction, never a value that happens to round to
zero. That is also why a policy reaction can never repeat indefinitely on a fixed target — the
moment a proposal stops moving, its direction is `UNCHANGED` and the reaction is provably zero.

## Decree bypass: uniform and procedural, never content-dependent

A flat penalty for every bloc that holds at least one seat when the government enacts by decree,
regardless of whether the decreed content itself changed. Bypassing an assembly is only a bypass for
a bloc that would otherwise have had a vote to cast — a bloc with no seats receives nothing, and
there is no such thing as a "partial" bypass tied to how much policy moved.

## Combining: one order-independent identity, exactly once

    uncapped_total_change_bps = decay + investment + policy + decree      # plain integer sum
    closing_relationship_bps  = clamp_relationship_bps(opening + uncapped_total_change_bps)
    applied_total_change_bps  = closing_relationship_bps - opening

All four components are computed from the same **opening** relationship, never a partially-updated
value, so the closing result is provably independent of the order the four are evaluated in.
Boundary truncation (when the clamp binds) is exposed as `applied != uncapped`, never absorbed into
one component to make the sum come out even — that would be a fabricated attribution of which cause
"lost" its change.

## Government-form neutrality

No function here accepts a `ConstitutionState` or any constitutional enum, and this module does not
import `simulation.constitution` at all. A monarchy's blocs and a republic's blocs, holding
identical relationships and preferences, decay and react identically — the constitution decides
*procedure* (whether a decree is legal at all), never how a caucus feels. Enforced structurally by
`test_legislative_neutrality.py`, alongside `apportionment`, `legislative_voting` and
`relationships`.
"""

from __future__ import annotations

from app.core.money import BPS_DENOMINATOR
from app.core.politics import (
    DECREE_BYPASS_PENALTY_BPS,
    POLICY_REACTION_CAP_BPS,
    POLICY_REACTION_WEIGHT_BPS,
    RELATIONSHIP_DECAY_DENOMINATOR,
    RELATIONSHIP_DECAY_NUMERATOR,
    clamp_relationship_bps,
    trunc_div_toward_zero,
)
from app.simulation.legislature import ChangeDirection

TAX_REACTION_WEIGHT_BPS = 2_000
"""How far the tax axis alone can move a policy reaction's compatibility term: at most ±20
percentage points of the ±40-point compatibility scale — deliberately the same magnitude
`legislative_voting.TAX_WEIGHT_BPS` uses for the vote, computed independently rather than
imported, per this module's two-code-paths discipline (see module docstring)."""

SPENDING_REACTION_WEIGHT_BPS = 2_000
"""The policy-reaction twin of `TAX_REACTION_WEIGHT_BPS`, for the spending axis."""


def relationship_decay_bps(*, opening_relationship_bps: int, baseline_relationship_bps: int) -> int:
    """How far `opening_relationship_bps` decays back toward `baseline_relationship_bps` this turn.

    Returns `0` exactly when the two are already equal. Otherwise returns a signed magnitude that
    moves the deviation toward zero: `max(1, min(trunc(|deviation| / 8), |deviation|))`, signed
    opposite the deviation. The minimum-one-bps floor guarantees the trajectory reaches exactly
    `baseline_relationship_bps` in finitely many turns rather than asymptotically approaching it
    forever; the cap guarantees it never overshoots past that point.
    """
    deviation = opening_relationship_bps - baseline_relationship_bps
    if deviation == 0:
        return 0
    magnitude = trunc_div_toward_zero(
        abs(deviation) * RELATIONSHIP_DECAY_NUMERATOR, RELATIONSHIP_DECAY_DENOMINATOR
    )
    magnitude = max(1, min(magnitude, abs(deviation)))
    return -magnitude if deviation > 0 else magnitude


def _reaction_axis_bps(
    *, preference_bps: int, direction: ChangeDirection, intensity_bps: int, weight_bps: int
) -> int:
    """One axis's contribution to policy compatibility: a preference scaled by how far policy
    moved, then by the axis weight, then signed by which way it moved. `UNCHANGED` is a hard
    branch returning exactly `0`, never a numeric coincidence."""
    if direction is ChangeDirection.UNCHANGED:
        return 0
    magnitude = trunc_div_toward_zero(preference_bps * intensity_bps, BPS_DENOMINATOR)
    weighted = trunc_div_toward_zero(magnitude * weight_bps, BPS_DENOMINATOR)
    return -weighted if direction is ChangeDirection.DECREASE else weighted


def enacted_policy_reaction_bps(
    *,
    tax_preference_bps: int,
    tax_direction: ChangeDirection,
    tax_intensity_bps: int,
    spending_preference_bps: int,
    spending_direction: ChangeDirection,
    spending_intensity_bps: int,
) -> int:
    """How a bloc reacts to policy that was genuinely enacted this turn, on `[-1,000, +1,000]`.

    Callers must pass `ChangeDirection.UNCHANGED` (intensity `0`) for a proposal that did not
    genuinely change, or omit calling this at all on a turn with no enacted policy (`FAILED_LEGISLATIVE`,
    `NO_PROPOSAL`) — this function does not know the outcome, only the content, and returns exactly
    `0` whenever both axes are `UNCHANGED`. Compatibility (`[-4,000, +4,000]`, the same range
    `legislative_voting.policy_compatibility_bps` produces) is weighted by
    `POLICY_REACTION_WEIGHT_BPS` and clamped to `POLICY_REACTION_CAP_BPS` — structurally
    `[-1,000, +1,000]` before the explicit clamp is even reached, confirmed never to bind on real
    scenario data (`test_relationship_memory_calibration.py`).
    """
    compatibility = _reaction_axis_bps(
        preference_bps=tax_preference_bps,
        direction=tax_direction,
        intensity_bps=tax_intensity_bps,
        weight_bps=TAX_REACTION_WEIGHT_BPS,
    ) + _reaction_axis_bps(
        preference_bps=spending_preference_bps,
        direction=spending_direction,
        intensity_bps=spending_intensity_bps,
        weight_bps=SPENDING_REACTION_WEIGHT_BPS,
    )
    reaction = trunc_div_toward_zero(compatibility * POLICY_REACTION_WEIGHT_BPS, BPS_DENOMINATOR)
    return max(-POLICY_REACTION_CAP_BPS, min(POLICY_REACTION_CAP_BPS, reaction))


def decree_bypass_reaction_bps(*, is_seated_bloc: bool) -> int:
    """`-DECREE_BYPASS_PENALTY_BPS` for a bloc holding at least one seat when the government
    enacts by decree, `0` otherwise. Callers must pass `is_seated_bloc=False` (or not call this at
    all) on any turn that is not `ENACTED_BY_DECREE`, and for any bloc holding no seats at all —
    bypassing an assembly is only a bypass for a bloc that would otherwise have had a vote."""
    return -DECREE_BYPASS_PENALTY_BPS if is_seated_bloc else 0


def combine_relationship_components(
    *,
    opening_relationship_bps: int,
    decay_component_bps: int,
    investment_component_bps: int,
    policy_reaction_component_bps: int,
    decree_bypass_component_bps: int,
) -> tuple[int, int, int]:
    """Sum the four components computed from the same opening value, clamp exactly once, and
    report what actually happened.

    Returns `(uncapped_total_change_bps, applied_total_change_bps, closing_relationship_bps)`.
    `uncapped_total_change_bps` is the plain sum before clamping; `applied_total_change_bps` is
    `closing - opening`, which differs from the uncapped sum exactly when the clamp bound —
    visible, reconcilable truncation, never silently attributed to any one component.
    """
    uncapped_total_change_bps = (
        decay_component_bps
        + investment_component_bps
        + policy_reaction_component_bps
        + decree_bypass_component_bps
    )
    closing_relationship_bps = clamp_relationship_bps(
        opening_relationship_bps + uncapped_total_change_bps
    )
    applied_total_change_bps = closing_relationship_bps - opening_relationship_bps
    return uncapped_total_change_bps, applied_total_change_bps, closing_relationship_bps
