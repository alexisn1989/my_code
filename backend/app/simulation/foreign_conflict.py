"""Persistent external conflicts between foreign countries (External Wars, Gate W1).

The world keeps changing whether or not the player acts. This module answers the four
questions that make a foreign war a *process* rather than an event: which authored pair is
under enough pressure to start fighting, how does an active war move each turn, when does it
stop, and how does a ceasefire either hold or collapse.

Nothing here is about the player. There is no stance, no engagement, no cost and no decision:
in W1 the player observes. `war_capability_bps` is an ABSTRACT AUTHORED CAPABILITY used only
for foreign conflict progression -- it is structurally separate from, and never read by, the
player's future `MilitaryState`, `InstitutionState(id="military")`, or the coup/unrest/
impeachment formulas in `simulation.government_survival`.

Two floors exist because their absence was measured, not imagined:

  * `MIN_ACTIVE_INTENSITY_BPS` -- without it, a conflict that decayed to zero intensity became
    ABSORBING. `exhaustion_gain` is computed from the OPENING intensity, so at zero intensity
    exhaustion stopped accruing, intensity could never recover, position random-walked on
    jitter alone, and no terminal gate was reachable. `ACTIVE` is a claim that fighting is
    still happening; the floor makes that claim true, which is what keeps exhaustion (and
    therefore readiness, and therefore the ceasefire path) moving.
  * `MIN_OUTBREAK_WEIGHT_BPS` -- without it, a deliberately low-pressure pair still produced
    occasional wars, so "low risk" was luck rather than a rule.

No I/O, no randomness, no state mutation, no clock, no floating point. Plain functions of
their arguments, in the same shape as `apportionment`, `legislative_voting`, `relationships`
and `political_memory`. The RNG draws these functions consume are passed in as integers by the
caller; this module never reaches for a generator itself.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.money import BPS_DENOMINATOR
from app.core.politics import clamp_bps, trunc_div_toward_zero

# --------------------------------------------------------------------------
# Calibrated constants (frozen plan sec.10.1, selected from a declared 240-cell grid)
# --------------------------------------------------------------------------

OUTBREAK_SCALE_BPS = 700
"""Scales total candidate pressure into a per-turn occurrence probability."""

MIN_OUTBREAK_WEIGHT_BPS = 500
"""An eligible dyad below this weight is not a candidate at all. Distinguishes three authored
meanings: `eligible=False` (the pair cannot fight), eligible but under-pressure (it could, but
tension is presently too low), and eligible at or above the floor (it participates)."""

INITIAL_INTENSITY_BPS = 3_000
TENSION_INTENSITY_WEIGHT_BPS = 3_000
PROGRESS_JITTER_BPS = 300
EXHAUSTION_RATE_BPS = 1_200
INTENSITY_GROWTH_BPS = 250
INTENSITY_DECAY_BPS = 900
DECISIVENESS_PENALTY_BPS = 6_000
DECISIVE_POSITION_BPS = 6_000
CEASEFIRE_THRESHOLD_BPS = 5_000
SETTLEMENT_THRESHOLD_BPS = 7_500
CEASEFIRE_INTENSITY_DECAY_BPS = 2_500

MIN_ACTIVE_INTENSITY_BPS = 250
"""The lowest floor that produces a passing configuration in the declared grid. See the module
docstring for why a floor is required at all.

Frozen plan sec.10.1 recorded 500 here on the reasoning that "250 produced none". That rested on an
invalid `no_indefinite_ceasefire` criterion which counted any conflict whose FINAL-turn status read
`CEASEFIRE` -- a horizon right-censoring artifact, not a stuck ceasefire. Measured honestly (one
uninterrupted `CEASEFIRE` episode exceeding `CEASEFIRE_DURABILITY_TURNS`), floor 250 has four
passing configurations and the frozen selection order returns this row. See
`docs/plans/external-wars-w1-calibration-erratum.md`."""

CEASEFIRE_RECOVERY_BPS = 200
CEASEFIRE_BREAKDOWN_BPS = 4_500
CEASEFIRE_DURABILITY_TURNS = 3

MAX_CONCURRENT_CONFLICTS = 2
"""Frozen plan sec.10.1: global cap on simultaneously live conflicts, measured against a
synthetic multi-dyad fixture (sec.10.5: 20 conflicts across five seeds, cap never exceeded).
`SETTLED`/`DECIDED` are permanent history (sec.8.6) and occupy no capacity -- only `ACTIVE` and
`CEASEFIRE` count."""


class ConflictStatus(StrEnum):
    """`ACTIVE` and `CEASEFIRE` are reversible; `SETTLED` and `DECIDED` are terminal.

    There is deliberately no `FROZEN`: a stalemate is a long-running `ACTIVE` conflict. An
    earlier draft specified one and measurement proved it unreachable under every swept
    constant, because exhaustion rises monotonically and readiness tracks it, so any
    sufficiently long war crosses the ceasefire threshold before an intensity-burnout gate
    could fire.
    """

    ACTIVE = "active"
    CEASEFIRE = "ceasefire"
    SETTLED = "settled"
    DECIDED = "decided"


TERMINAL_STATUSES = frozenset({ConflictStatus.SETTLED, ConflictStatus.DECIDED})
"""The terminal half of the partition above. Lives with the enum it partitions so the
`resolved_turn` rule -- required for exactly these two, forbidden for the other two -- has one
definition rather than one per consumer."""


class WarAim(StrEnum):
    """Authored per dyad, never drawn. `aim_a` belongs to the canonical A actor and `aim_b` to
    the canonical B actor -- aims follow canonical ordering, never aggressor/defender roles."""

    TERRITORIAL = "territorial"
    REGIME_CHANGE = "regime_change"
    RESOURCE_ACCESS = "resource_access"
    DETERRENCE = "deterrence"


def clamp_intensity_bps(value: int) -> int:
    """Intensity, exhaustion and readiness all live on the same unsigned [0, 10000] scale.

    Delegates to `core.politics.clamp_bps` rather than open-coding `max(min(...))`, so the
    codebase keeps exactly one clamp implementation. The domain name is kept so every clamp
    site here is greppable by what it bounds -- the convention `clamp_relationship_bps`
    already sets.
    """
    return clamp_bps(value)


def clamp_position_bps(value: int) -> int:
    """Position is SIGNED: positive favours the canonical A actor, negative favours B."""
    return clamp_bps(value, low=-BPS_DENOMINATOR, high=BPS_DENOMINATOR)


# --------------------------------------------------------------------------
# Outbreak
# --------------------------------------------------------------------------


def dyad_weight_bps(*, tension_bps: int, grievance_bps: int) -> int:
    """A dyad's raw outbreak pressure, before the pressure floor is applied.

    Standing hostility and accumulated grievance contribute equally: a pair that has always
    disliked each other and a pair with one specific fresh quarrel are both plausible wars.
    """
    return clamp_intensity_bps(trunc_div_toward_zero(tension_bps + grievance_bps, 2))


def passes_pressure_floor(*, raw_weight_bps: int) -> bool:
    """Whether a dyad's raw weight qualifies it as an outbreak candidate at all."""
    return raw_weight_bps >= MIN_OUTBREAK_WEIGHT_BPS


def concurrency_capacity_available(*, live_conflict_count: int) -> bool:
    """Whether another conflict may open this turn, against `MAX_CONCURRENT_CONFLICTS`.
    `live_conflict_count` is the count of `ACTIVE`/`CEASEFIRE` conflicts only -- terminal
    conflicts never occupy capacity (sec.8.6)."""
    return live_conflict_count < MAX_CONCURRENT_CONFLICTS


def outbreak_probability_bps(*, total_weight_bps: int) -> int:
    """Per-turn occurrence probability, explicitly clamped at certainty.

    The clamp is a named, tested boundary rather than an accident of arithmetic: at saturation
    a war is certain among the eligible candidates, and the weighted pick still decides which.
    """
    return min(
        BPS_DENOMINATOR,
        trunc_div_toward_zero(total_weight_bps * OUTBREAK_SCALE_BPS, BPS_DENOMINATOR),
    )


def outbreak_occurs(*, occurrence_draw: int, probability_bps: int) -> bool:
    """`occurrence_draw` is an integer in [0, 9999] supplied by the caller's RNG."""
    return occurrence_draw < probability_bps


def select_candidate_index(*, selection_draw: int, weights_bps: tuple[int, ...]) -> int:
    """Cumulative-weight pick over candidates the caller has already put in canonical order.

    Returns the index of the selected candidate. `selection_draw` is an integer in
    [0, total_weight - 1]. Iteration order is the caller's canonical order, never a mapping's
    insertion order, so the same world selects the same dyad however it was constructed.
    """
    if not weights_bps:
        raise ValueError("select_candidate_index requires at least one candidate")
    total = sum(weights_bps)
    if total <= 0:
        raise ValueError("select_candidate_index requires a positive total weight")
    if not 0 <= selection_draw < total:
        raise ValueError(f"selection_draw {selection_draw} outside [0, {total})")
    accumulated = 0
    for index, weight in enumerate(weights_bps):
        accumulated += weight
        if selection_draw < accumulated:
            return index
    raise AssertionError("unreachable: cumulative weights did not cover the draw")


def initial_intensity_bps(*, tension_bps: int) -> int:
    """A war between a more hostile pair starts hotter."""
    return clamp_intensity_bps(
        INITIAL_INTENSITY_BPS
        + trunc_div_toward_zero(tension_bps * TENSION_INTENSITY_WEIGHT_BPS, BPS_DENOMINATOR)
    )


# --------------------------------------------------------------------------
# Active progression
# --------------------------------------------------------------------------


def closing_position_bps(
    *,
    opening_position_bps: int,
    opening_war_capability_a_bps: int,
    opening_war_capability_b_bps: int,
    opening_intensity_bps: int,
    position_jitter_bps: int,
) -> int:
    """Advantage drifts toward the stronger side, in proportion to how hard they are fighting.

    Every input is an OPENING value plus this turn's jitter -- never a closing value.
    """
    drift = trunc_div_toward_zero(
        (opening_war_capability_a_bps - opening_war_capability_b_bps) * opening_intensity_bps,
        BPS_DENOMINATOR,
    )
    return clamp_position_bps(opening_position_bps + drift + position_jitter_bps)


def exhaustion_gain_bps(*, opening_intensity_bps: int) -> int:
    """Both sides tire at the same rate, set by how hard the war is being fought.

    Computed from the OPENING intensity. That is precisely why `MIN_ACTIVE_INTENSITY_BPS`
    exists: at zero opening intensity this returns zero, exhaustion freezes, and the conflict
    can never progress to any terminal gate.
    """
    return trunc_div_toward_zero(opening_intensity_bps * EXHAUSTION_RATE_BPS, BPS_DENOMINATOR)


def average_exhaustion_bps(*, exhaustion_a_bps: int, exhaustion_b_bps: int) -> int:
    return trunc_div_toward_zero(exhaustion_a_bps + exhaustion_b_bps, 2)


def raw_closing_intensity_bps(
    *, opening_intensity_bps: int, closing_average_exhaustion_bps: int
) -> int:
    """Intensity before the active floor: escalation pressure minus what exhaustion removes."""
    return clamp_intensity_bps(
        opening_intensity_bps
        + INTENSITY_GROWTH_BPS
        - trunc_div_toward_zero(
            closing_average_exhaustion_bps * INTENSITY_DECAY_BPS, BPS_DENOMINATOR
        )
    )


def closing_readiness_bps(
    *, closing_average_exhaustion_bps: int, closing_position_bps_value: int
) -> int:
    """Willingness to negotiate: exhaustion pushes toward the table, a decisive lead pulls away.

    A side that is winning clearly has little reason to settle, which is why the decisiveness
    term subtracts.
    """
    return clamp_intensity_bps(
        closing_average_exhaustion_bps
        - trunc_div_toward_zero(
            abs(closing_position_bps_value) * DECISIVENESS_PENALTY_BPS, BPS_DENOMINATOR
        )
    )


def apply_active_intensity_floor(*, raw_intensity_bps: int, closing_status: ConflictStatus) -> int:
    """The floor applies to `ACTIVE` only, and only AFTER the status is known.

    Terminal statuses keep the formula-derived intensity with no floor, so a war can end quiet.
    `CEASEFIRE` may likewise decay below the floor -- a ceasefire is precisely the claim that
    fighting has stopped.
    """
    if closing_status is ConflictStatus.ACTIVE:
        return max(MIN_ACTIVE_INTENSITY_BPS, raw_intensity_bps)
    return raw_intensity_bps


def is_decisive(*, closing_position_bps_value: int) -> bool:
    return abs(closing_position_bps_value) >= DECISIVE_POSITION_BPS


def ceasefire_gate_open(*, closing_readiness_bps_value: int) -> bool:
    return closing_readiness_bps_value >= CEASEFIRE_THRESHOLD_BPS


def settles_rather_than_pauses(*, closing_readiness_bps_value: int, termination_draw: int) -> bool:
    """Given the ceasefire gate is open, whether this becomes a durable settlement now.

    Requires both a high enough readiness and the draw. A war can pause without ending.
    """
    if closing_readiness_bps_value < SETTLEMENT_THRESHOLD_BPS:
        return False
    return termination_draw < closing_readiness_bps_value


def active_closing_status(
    *,
    closing_position_bps_value: int,
    closing_readiness_bps_value: int,
    termination_draw: int | None,
) -> ConflictStatus:
    """The terminal-gate priority for a conflict that opened the turn `ACTIVE`.

    Fixed order: DECIDED first and purely deterministically -- a conflict past the decisive
    threshold cannot continue because a draw failed -- then the ceasefire gate, where one draw
    decides settlement versus pause. `termination_draw` is required exactly when the ceasefire
    gate is open and must be `None` otherwise, so a report cannot store a draw it never made.
    """
    if is_decisive(closing_position_bps_value=closing_position_bps_value):
        if termination_draw is not None:
            raise ValueError("a decisive conflict consumes no termination draw")
        return ConflictStatus.DECIDED
    if ceasefire_gate_open(closing_readiness_bps_value=closing_readiness_bps_value):
        if termination_draw is None:
            raise ValueError("an open ceasefire gate requires a termination draw")
        if settles_rather_than_pauses(
            closing_readiness_bps_value=closing_readiness_bps_value,
            termination_draw=termination_draw,
        ):
            return ConflictStatus.SETTLED
        return ConflictStatus.CEASEFIRE
    if termination_draw is not None:
        raise ValueError("a continuing conflict consumes no termination draw")
    return ConflictStatus.ACTIVE


# --------------------------------------------------------------------------
# Ceasefire
# --------------------------------------------------------------------------


def ceasefire_decayed_intensity_bps(*, opening_intensity_bps: int) -> int:
    """Fighting winds down while a ceasefire holds."""
    return clamp_intensity_bps(
        opening_intensity_bps
        - trunc_div_toward_zero(
            opening_intensity_bps * CEASEFIRE_INTENSITY_DECAY_BPS, BPS_DENOMINATOR
        )
    )


def ceasefire_recovered_exhaustion_bps(*, opening_exhaustion_bps: int) -> int:
    """Both sides recover while not fighting. Position is frozen during a ceasefire, so
    readiness falls by exactly `CEASEFIRE_RECOVERY_BPS` per turn."""
    return max(0, opening_exhaustion_bps - CEASEFIRE_RECOVERY_BPS)


def ceasefire_closing_status(
    *, closing_readiness_bps_value: int, closing_ceasefire_run_turns: int
) -> ConflictStatus:
    """Breakdown is evaluated BEFORE maturation.

    A recovered pair whose readiness has fallen back below the breakdown threshold resumes
    fighting; one that holds long enough converts the pause into a settlement.
    """
    if closing_readiness_bps_value < CEASEFIRE_BREAKDOWN_BPS:
        return ConflictStatus.ACTIVE
    if closing_ceasefire_run_turns >= CEASEFIRE_DURABILITY_TURNS:
        return ConflictStatus.SETTLED
    return ConflictStatus.CEASEFIRE


def ceasefire_closing_intensity_bps(
    *, decayed_intensity_bps: int, closing_status: ConflictStatus
) -> int:
    """A conflict returning to `ACTIVE` restarts at or above the floor; anything else keeps the
    decayed value."""
    if closing_status is ConflictStatus.ACTIVE:
        return max(MIN_ACTIVE_INTENSITY_BPS, decayed_intensity_bps)
    return decayed_intensity_bps
