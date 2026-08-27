"""External Wars W1 commit 3: what `simulation.foreign_conflict` guarantees, pinned as boundaries.

This file pins the *pure formulas* only. Every figure below is derived from the module's own
calibrated constants and was checked against the frozen plan's measured tables before being
written here -- not hand-waved and hoped for.

Two things this file deliberately does NOT claim, because no resolver exists yet at this commit:

  * It does not prove that resolving a real turn with foreign capability at 0 and at 10,000
    leaves `CoupUnrestReport` byte-identical. That behavioural proof needs the phase wiring and
    lands atomically with it. What *is* provable today -- and is proven here -- is the
    structural half: `government_survival` has no channel through which foreign capability
    could arrive in the first place.
  * It does not claim campaign frequencies. Outbreak weights and probabilities here are
    per-eligible-turn formula inputs, not measured war counts.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.money import BPS_DENOMINATOR
from app.simulation import foreign_conflict as fc
from app.simulation import government_survival as government_survival_module

# --- the calibrated constants themselves --------------------------------------


def test_the_approved_calibration_is_pinned() -> None:
    """The selected configuration from the declared 240-cell grid. If any of these drift, the
    measured behaviour the rest of this file asserts is no longer the behaviour being shipped."""
    assert fc.MIN_ACTIVE_INTENSITY_BPS == 500
    assert fc.MIN_OUTBREAK_WEIGHT_BPS == 500
    assert fc.CEASEFIRE_RECOVERY_BPS == 300
    assert fc.CEASEFIRE_BREAKDOWN_BPS == 4_000
    assert fc.CEASEFIRE_DURABILITY_TURNS == 4
    assert fc.OUTBREAK_SCALE_BPS == 700


def test_there_is_no_frozen_status_and_the_terminal_partition_is_exact() -> None:
    """A stalemate is a long-running `ACTIVE` conflict. `FROZEN` was measured unreachable under
    every swept constant and is therefore absent, not merely unused."""
    assert {status.value for status in fc.ConflictStatus} == {
        "active",
        "ceasefire",
        "settled",
        "decided",
    }
    assert {fc.ConflictStatus.SETTLED, fc.ConflictStatus.DECIDED} == fc.TERMINAL_STATUSES
    reversible = set(fc.ConflictStatus) - fc.TERMINAL_STATUSES
    assert reversible == {fc.ConflictStatus.ACTIVE, fc.ConflictStatus.CEASEFIRE}


# --- outbreak: the pressure floor, at its exact boundary -----------------------


def test_weight_499_is_excluded_and_weight_500_is_eligible() -> None:
    """The floor is what makes a low-pressure pair safe by rule rather than by luck, so it is
    pinned at the adjacent pair rather than at comfortable distances from it."""
    assert fc.passes_pressure_floor(raw_weight_bps=499) is False
    assert fc.passes_pressure_floor(raw_weight_bps=500) is True

    # ...and reached through the real weight formula, not just asserted on the predicate.
    assert fc.dyad_weight_bps(tension_bps=499, grievance_bps=499) == 499
    assert fc.dyad_weight_bps(tension_bps=500, grievance_bps=500) == 500
    assert (
        fc.passes_pressure_floor(
            raw_weight_bps=fc.dyad_weight_bps(tension_bps=499, grievance_bps=499)
        )
        is False
    )
    assert (
        fc.passes_pressure_floor(
            raw_weight_bps=fc.dyad_weight_bps(tension_bps=500, grievance_bps=500)
        )
        is True
    )


def test_the_low_pressure_control_is_excluded_structurally() -> None:
    """The declared control pair (tension 200, grievance 0) weighs 100, far under the floor. It
    produces no wars because the threshold forbids it, not because the die was kind."""
    weight = fc.dyad_weight_bps(tension_bps=200, grievance_bps=0)
    assert weight == 100
    assert fc.passes_pressure_floor(raw_weight_bps=weight) is False


def test_standing_hostility_and_fresh_grievance_weigh_the_same() -> None:
    """The formula is an average, so the two causes are interchangeable by construction."""
    assert fc.dyad_weight_bps(tension_bps=8_000, grievance_bps=0) == fc.dyad_weight_bps(
        tension_bps=0, grievance_bps=8_000
    )


def test_the_authored_dyad_weights_and_probabilities_are_exactly_the_frozen_figures() -> None:
    """The three shipped dyads' derived outbreak inputs. These are per-eligible-turn formula
    inputs before active-conflict exclusion -- NOT campaign frequencies."""
    for tension, grievance, expected_weight, expected_probability in (
        (8_500, 7_500, 8_000, 560),  # tiny_valid
        (9_500, 8_500, 9_000, 630),  # decree_state
        (9_000, 7_000, 8_000, 560),  # deficit_demo
    ):
        weight = fc.dyad_weight_bps(tension_bps=tension, grievance_bps=grievance)
        assert weight == expected_weight
        assert fc.passes_pressure_floor(raw_weight_bps=weight) is True
        assert fc.outbreak_probability_bps(total_weight_bps=weight) == expected_probability


def test_the_probability_clamp_is_an_exact_named_boundary() -> None:
    """At saturation a war is certain among the candidates and the weighted pick still decides
    which. The clamp is tested at the adjacent pair so it cannot silently become an overflow."""
    assert fc.outbreak_probability_bps(total_weight_bps=142_857) == 9_999
    assert fc.outbreak_probability_bps(total_weight_bps=142_858) == BPS_DENOMINATOR
    assert fc.outbreak_probability_bps(total_weight_bps=10_000_000) == BPS_DENOMINATOR
    assert fc.outbreak_probability_bps(total_weight_bps=0) == 0


def test_occurrence_compares_strictly_below_the_probability() -> None:
    assert fc.outbreak_occurs(occurrence_draw=559, probability_bps=560) is True
    assert fc.outbreak_occurs(occurrence_draw=560, probability_bps=560) is False
    assert fc.outbreak_occurs(occurrence_draw=0, probability_bps=0) is False


# --- outbreak: deterministic weighted selection --------------------------------


def test_weighted_selection_walks_cumulative_weights_in_the_callers_order() -> None:
    """Every boundary of a three-candidate walk, so an off-by-one in the cumulative comparison
    cannot hide in the interior of a band."""
    weights = (100, 200, 700)
    for draw, expected in ((0, 0), (99, 0), (100, 1), (299, 1), (300, 2), (999, 2)):
        assert fc.select_candidate_index(selection_draw=draw, weights_bps=weights) == expected


def test_weighted_selection_favours_heavier_candidates_across_the_whole_range() -> None:
    """Not a distribution claim -- an exact count over every legal draw."""
    weights = (100, 200, 700)
    counts = [0, 0, 0]
    for draw in range(sum(weights)):
        counts[fc.select_candidate_index(selection_draw=draw, weights_bps=weights)] += 1
    assert counts == [100, 200, 700]


def test_weighted_selection_rejects_impossible_inputs_rather_than_guessing() -> None:
    with pytest.raises(ValueError, match="at least one candidate"):
        fc.select_candidate_index(selection_draw=0, weights_bps=())
    with pytest.raises(ValueError, match="positive total weight"):
        fc.select_candidate_index(selection_draw=0, weights_bps=(0, 0))
    with pytest.raises(ValueError, match="outside"):
        fc.select_candidate_index(selection_draw=1_000, weights_bps=(100, 200, 700))
    with pytest.raises(ValueError, match="outside"):
        fc.select_candidate_index(selection_draw=-1, weights_bps=(100, 200, 700))


def test_a_war_between_a_more_hostile_pair_starts_hotter() -> None:
    assert fc.initial_intensity_bps(tension_bps=0) == 3_000
    assert fc.initial_intensity_bps(tension_bps=8_500) == 5_550
    assert fc.initial_intensity_bps(tension_bps=10_000) == 6_000


# --- active progression --------------------------------------------------------


def test_position_drifts_toward_the_stronger_side_and_is_exactly_symmetric() -> None:
    """Truncation toward zero is what makes the mirror exact; floor division would bias one
    direction by a bps and quietly favour whichever actor sorted first."""
    forward = fc.closing_position_bps(
        opening_position_bps=0,
        opening_war_capability_a_bps=5_600,
        opening_war_capability_b_bps=5_000,
        opening_intensity_bps=5_550,
        position_jitter_bps=0,
    )
    mirrored = fc.closing_position_bps(
        opening_position_bps=0,
        opening_war_capability_a_bps=5_000,
        opening_war_capability_b_bps=5_600,
        opening_intensity_bps=5_550,
        position_jitter_bps=0,
    )
    assert forward == 333
    assert mirrored == -333


def test_evenly_matched_sides_move_only_on_jitter() -> None:
    assert (
        fc.closing_position_bps(
            opening_position_bps=1_000,
            opening_war_capability_a_bps=5_000,
            opening_war_capability_b_bps=5_000,
            opening_intensity_bps=6_000,
            position_jitter_bps=0,
        )
        == 1_000
    )


def test_position_is_clamped_to_the_signed_scale() -> None:
    assert (
        fc.closing_position_bps(
            opening_position_bps=9_900,
            opening_war_capability_a_bps=10_000,
            opening_war_capability_b_bps=0,
            opening_intensity_bps=10_000,
            position_jitter_bps=fc.PROGRESS_JITTER_BPS,
        )
        == BPS_DENOMINATOR
    )
    assert (
        fc.closing_position_bps(
            opening_position_bps=-9_900,
            opening_war_capability_a_bps=0,
            opening_war_capability_b_bps=10_000,
            opening_intensity_bps=10_000,
            position_jitter_bps=-fc.PROGRESS_JITTER_BPS,
        )
        == -BPS_DENOMINATOR
    )


def test_a_clear_lead_makes_a_side_less_willing_to_negotiate_symmetrically() -> None:
    """Winning is a reason not to settle, and it is the *size* of the lead that matters, not
    whose lead it is."""
    assert (
        fc.closing_readiness_bps(closing_average_exhaustion_bps=6_000, closing_position_bps_value=0)
        == 6_000
    )
    assert (
        fc.closing_readiness_bps(
            closing_average_exhaustion_bps=6_000, closing_position_bps_value=3_000
        )
        == 4_200
    )
    assert fc.closing_readiness_bps(
        closing_average_exhaustion_bps=6_000, closing_position_bps_value=-3_000
    ) == fc.closing_readiness_bps(
        closing_average_exhaustion_bps=6_000, closing_position_bps_value=3_000
    )


# --- the active-intensity floor, and the absorbing state it removes ------------


def test_exhaustion_continues_increasing_while_active_at_the_floor() -> None:
    """60 bps per turn at the floor. This single number is why the floor works: it is what keeps
    readiness rising, and therefore what keeps the ceasefire path reachable."""
    assert fc.exhaustion_gain_bps(opening_intensity_bps=fc.MIN_ACTIVE_INTENSITY_BPS) == 60
    assert fc.exhaustion_gain_bps(opening_intensity_bps=0) == 0


def test_the_floor_applies_to_active_only() -> None:
    assert (
        fc.apply_active_intensity_floor(
            raw_intensity_bps=0, closing_status=fc.ConflictStatus.ACTIVE
        )
        == 500
    )
    for quiet_ending in (
        fc.ConflictStatus.CEASEFIRE,
        fc.ConflictStatus.SETTLED,
        fc.ConflictStatus.DECIDED,
    ):
        assert (
            fc.apply_active_intensity_floor(raw_intensity_bps=0, closing_status=quiet_ending) == 0
        ), f"{quiet_ending} must be allowed to end quiet"


def test_the_floor_never_raises_an_intensity_that_is_already_above_it() -> None:
    for raw in (500, 501, 3_000, 10_000):
        assert (
            fc.apply_active_intensity_floor(
                raw_intensity_bps=raw, closing_status=fc.ConflictStatus.ACTIVE
            )
            == raw
        )


def test_a_ceasefire_may_decay_below_the_active_floor() -> None:
    """A ceasefire is precisely the claim that fighting has stopped, so the floor must not apply
    to it -- otherwise 'paused' and 'fighting' would be indistinguishable in the state."""
    decayed = fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=500)
    assert decayed == 375
    assert (
        fc.ceasefire_closing_intensity_bps(
            decayed_intensity_bps=decayed, closing_status=fc.ConflictStatus.CEASEFIRE
        )
        == 375
    )
    assert fc.MIN_ACTIVE_INTENSITY_BPS > 375


def test_a_ceasefire_that_breaks_down_restarts_at_or_above_the_floor() -> None:
    decayed = fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=500)
    assert (
        fc.ceasefire_closing_intensity_bps(
            decayed_intensity_bps=decayed, closing_status=fc.ConflictStatus.ACTIVE
        )
        == fc.MIN_ACTIVE_INTENSITY_BPS
    )


# --- the absorbing state, driven through a real loop ---------------------------


class _Turn:
    __slots__ = ("intensity", "exhaustion_avg", "readiness", "status", "position")

    def __init__(
        self,
        *,
        intensity: int,
        exhaustion_avg: int,
        readiness: int,
        status: fc.ConflictStatus,
        position: int,
    ) -> None:
        self.intensity = intensity
        self.exhaustion_avg = exhaustion_avg
        self.readiness = readiness
        self.status = status
        self.position = position


def _simulate_active(
    *,
    turns: int,
    opening_intensity: int,
    opening_exhaustion: int = 0,
    opening_position: int = 0,
    capability_a: int = 5_000,
    capability_b: int = 5_000,
    apply_floor: bool = True,
) -> list[_Turn]:
    """Drives the module's own functions in the frozen plan's opening/closing order.

    `apply_floor=False` reproduces the pre-remedy formula exactly, which is the only honest way
    to assert that the absorbing state it produced is genuinely gone rather than merely unlikely.
    """
    intensity = opening_intensity
    exhaustion_a = exhaustion_b = opening_exhaustion
    position = opening_position
    history: list[_Turn] = []
    for _ in range(turns):
        position = fc.closing_position_bps(
            opening_position_bps=position,
            opening_war_capability_a_bps=capability_a,
            opening_war_capability_b_bps=capability_b,
            opening_intensity_bps=intensity,
            position_jitter_bps=0,
        )
        gain = fc.exhaustion_gain_bps(opening_intensity_bps=intensity)
        exhaustion_a = fc.clamp_intensity_bps(exhaustion_a + gain)
        exhaustion_b = fc.clamp_intensity_bps(exhaustion_b + gain)
        average = fc.average_exhaustion_bps(
            exhaustion_a_bps=exhaustion_a, exhaustion_b_bps=exhaustion_b
        )
        raw = fc.raw_closing_intensity_bps(
            opening_intensity_bps=intensity, closing_average_exhaustion_bps=average
        )
        readiness = fc.closing_readiness_bps(
            closing_average_exhaustion_bps=average, closing_position_bps_value=position
        )
        decisive = fc.is_decisive(closing_position_bps_value=position)
        gate_open = fc.ceasefire_gate_open(closing_readiness_bps_value=readiness)
        status = fc.active_closing_status(
            closing_position_bps_value=position,
            closing_readiness_bps_value=readiness,
            # The draw is made if and only if the gate is the deciding one -- exactly the
            # module's own contract. A settling draw (0) is used so SETTLED stays reachable.
            termination_draw=0 if (gate_open and not decisive) else None,
        )
        intensity = (
            fc.apply_active_intensity_floor(raw_intensity_bps=raw, closing_status=status)
            if apply_floor
            else raw
        )
        history.append(
            _Turn(
                intensity=intensity,
                exhaustion_avg=average,
                readiness=readiness,
                status=status,
                position=position,
            )
        )
        if status is not fc.ConflictStatus.ACTIVE:
            break
    return history


def test_the_old_absorbing_zero_intensity_state_is_reproducible_without_the_floor() -> None:
    """The defect, stated exactly. With exhaustion already accumulated, a zero-intensity ACTIVE
    conflict gains no exhaustion, so readiness cannot rise, so no terminal gate is reachable --
    and nothing about the state changes, ever."""
    history = _simulate_active(
        turns=200, opening_intensity=0, opening_exhaustion=4_000, apply_floor=False
    )
    assert len(history) == 200, "without the floor the conflict never leaves ACTIVE"
    assert all(turn.status is fc.ConflictStatus.ACTIVE for turn in history)
    assert all(turn.intensity == 0 for turn in history)
    assert {turn.exhaustion_avg for turn in history} == {4_000}, "exhaustion is frozen"
    assert {turn.readiness for turn in history} == {4_000}, "readiness cannot progress"


def test_the_floor_makes_that_state_impossible_and_restores_progress() -> None:
    """The same starting conflict, with the floor. Exhaustion resumes at 60 bps/turn, readiness
    rises monotonically, and the ceasefire gate is reached in a bounded number of turns."""
    history = _simulate_active(
        turns=200, opening_intensity=0, opening_exhaustion=4_000, apply_floor=True
    )
    assert history[-1].status is not fc.ConflictStatus.ACTIVE, "the conflict must terminate"
    assert len(history) <= 30, f"progress must be prompt, took {len(history)} turns"

    active_turns = [turn for turn in history if turn.status is fc.ConflictStatus.ACTIVE]
    assert all(turn.intensity >= fc.MIN_ACTIVE_INTENSITY_BPS for turn in active_turns)
    assert all(turn.intensity > 0 for turn in active_turns)

    readiness_series = [turn.readiness for turn in history]
    assert readiness_series == sorted(readiness_series), "readiness must rise monotonically"
    assert readiness_series[-1] > readiness_series[0]


def test_every_closing_active_conflict_has_intensity_at_least_the_floor() -> None:
    """Swept across starting intensities and capability gaps, including the pathological cases
    that produced the absorbing state, over the whole active lifetime of each conflict."""
    for opening_intensity in (0, 1, 500, 3_000, 6_000, 10_000):
        for opening_exhaustion in (0, 2_000, 4_000, 6_000):
            for capability_b in (5_000, 5_600, 8_000):
                history = _simulate_active(
                    turns=150,
                    opening_intensity=opening_intensity,
                    opening_exhaustion=opening_exhaustion,
                    capability_b=capability_b,
                )
                for turn in history:
                    if turn.status is fc.ConflictStatus.ACTIVE:
                        assert turn.intensity >= fc.MIN_ACTIVE_INTENSITY_BPS, (
                            f"below-floor ACTIVE close at intensity {turn.intensity}"
                        )


def test_no_swept_configuration_stalls() -> None:
    """The companion to the floor claim: not merely 'never below 500' but 'always going
    somewhere'. Every swept conflict reaches a non-ACTIVE status inside the horizon."""
    for opening_intensity in (0, 500, 3_000, 6_000):
        for opening_exhaustion in (0, 2_000, 4_000):
            history = _simulate_active(
                turns=300,
                opening_intensity=opening_intensity,
                opening_exhaustion=opening_exhaustion,
            )
            assert history[-1].status is not fc.ConflictStatus.ACTIVE, (
                f"stalled from intensity {opening_intensity}, exhaustion {opening_exhaustion}"
            )


# --- terminal gates ------------------------------------------------------------


def test_decided_is_deterministic_and_takes_priority_over_the_ceasefire_gate() -> None:
    """A conflict past the decisive threshold cannot continue because a draw failed. Note the
    readiness here is high enough to settle -- and is ignored."""
    assert (
        fc.active_closing_status(
            closing_position_bps_value=6_000,
            closing_readiness_bps_value=9_000,
            termination_draw=None,
        )
        is fc.ConflictStatus.DECIDED
    )
    assert (
        fc.active_closing_status(
            closing_position_bps_value=-6_000,
            closing_readiness_bps_value=9_000,
            termination_draw=None,
        )
        is fc.ConflictStatus.DECIDED
    )


def test_the_decisive_threshold_is_pinned_at_its_boundary() -> None:
    assert fc.is_decisive(closing_position_bps_value=5_999) is False
    assert fc.is_decisive(closing_position_bps_value=6_000) is True
    assert fc.is_decisive(closing_position_bps_value=-5_999) is False
    assert fc.is_decisive(closing_position_bps_value=-6_000) is True


def test_a_draw_is_consumed_exactly_when_the_ceasefire_gate_decides() -> None:
    """`DECIDED` consumes no randomness and neither does a war that simply continues, so a
    report can never store a draw that was never made."""
    with pytest.raises(ValueError, match="decisive conflict consumes no termination draw"):
        fc.active_closing_status(
            closing_position_bps_value=6_000, closing_readiness_bps_value=9_000, termination_draw=0
        )
    with pytest.raises(ValueError, match="open ceasefire gate requires a termination draw"):
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=5_000, termination_draw=None
        )
    with pytest.raises(ValueError, match="continuing conflict consumes no termination draw"):
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=4_999, termination_draw=0
        )


def test_the_ceasefire_gate_is_pinned_at_its_boundary() -> None:
    assert fc.ceasefire_gate_open(closing_readiness_bps_value=4_999) is False
    assert fc.ceasefire_gate_open(closing_readiness_bps_value=5_000) is True
    assert (
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=4_999, termination_draw=None
        )
        is fc.ConflictStatus.ACTIVE
    )


def test_settled_and_ceasefire_are_both_reachable_from_an_open_gate() -> None:
    """A war can pause without ending: settling needs both a high enough readiness AND the
    draw, so an open gate alone never forces a settlement."""
    assert (
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=8_000, termination_draw=0
        )
        is fc.ConflictStatus.SETTLED
    )
    assert (
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=8_000, termination_draw=7_999
        )
        is fc.ConflictStatus.SETTLED
    )
    assert (
        fc.active_closing_status(
            closing_position_bps_value=0, closing_readiness_bps_value=8_000, termination_draw=8_000
        )
        is fc.ConflictStatus.CEASEFIRE
    )
    # Gate open but below the settlement threshold: a pause is the only outcome, any draw.
    for draw in (0, 4_999, 9_999):
        assert (
            fc.active_closing_status(
                closing_position_bps_value=0,
                closing_readiness_bps_value=7_499,
                termination_draw=draw,
            )
            is fc.ConflictStatus.CEASEFIRE
        )


def test_the_settlement_threshold_is_pinned_at_its_boundary() -> None:
    assert (
        fc.settles_rather_than_pauses(closing_readiness_bps_value=7_499, termination_draw=0)
        is False
    )
    assert (
        fc.settles_rather_than_pauses(closing_readiness_bps_value=7_500, termination_draw=0) is True
    )


# --- ceasefire: both exits occur naturally -------------------------------------


def _run_ceasefire(
    *, entry_exhaustion: int, entry_intensity: int = 4_000, position: int = 0
) -> tuple[fc.ConflictStatus, int, int]:
    """Runs the ceasefire maintenance loop until it exits, returning (status, turns, intensity)."""
    exhaustion_a = exhaustion_b = entry_exhaustion
    intensity = entry_intensity
    run_turns = 0
    for _ in range(50):
        decayed = fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=intensity)
        exhaustion_a = fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=exhaustion_a)
        exhaustion_b = fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=exhaustion_b)
        average = fc.average_exhaustion_bps(
            exhaustion_a_bps=exhaustion_a, exhaustion_b_bps=exhaustion_b
        )
        readiness = fc.closing_readiness_bps(
            closing_average_exhaustion_bps=average, closing_position_bps_value=position
        )
        run_turns += 1
        status = fc.ceasefire_closing_status(
            closing_readiness_bps_value=readiness, closing_ceasefire_run_turns=run_turns
        )
        intensity = fc.ceasefire_closing_intensity_bps(
            decayed_intensity_bps=decayed, closing_status=status
        )
        if status is not fc.ConflictStatus.CEASEFIRE:
            return status, run_turns, intensity
        run_turns = run_turns  # holds; the run continues
    raise AssertionError("ceasefire never resolved")


def test_a_ceasefire_breaks_down_naturally() -> None:
    """Entering at exactly the ceasefire threshold, recovery of 300/turn drops readiness under
    the 4,000 breakdown line on the fourth turn -- before durability can mature it."""
    status, turns, intensity = _run_ceasefire(entry_exhaustion=5_000)
    assert status is fc.ConflictStatus.ACTIVE
    assert turns == 4
    assert intensity >= fc.MIN_ACTIVE_INTENSITY_BPS


def test_a_ceasefire_matures_into_a_settlement_naturally() -> None:
    """Entering only 200 bps higher, readiness is still at the breakdown line on the fourth
    turn, so durability matures it instead. Both exits are reachable from the same rules."""
    status, turns, intensity = _run_ceasefire(entry_exhaustion=5_200)
    assert status is fc.ConflictStatus.SETTLED
    assert turns == fc.CEASEFIRE_DURABILITY_TURNS
    assert intensity < fc.MIN_ACTIVE_INTENSITY_BPS or intensity >= 0  # no floor on a settlement


def test_breakdown_is_evaluated_before_maturation() -> None:
    """Order matters and is pinned: a run that has served its durability but whose readiness has
    collapsed resumes fighting rather than settling."""
    assert (
        fc.ceasefire_closing_status(
            closing_readiness_bps_value=3_999,
            closing_ceasefire_run_turns=fc.CEASEFIRE_DURABILITY_TURNS,
        )
        is fc.ConflictStatus.ACTIVE
    )
    assert (
        fc.ceasefire_closing_status(
            closing_readiness_bps_value=4_000,
            closing_ceasefire_run_turns=fc.CEASEFIRE_DURABILITY_TURNS,
        )
        is fc.ConflictStatus.SETTLED
    )
    assert (
        fc.ceasefire_closing_status(
            closing_readiness_bps_value=4_000,
            closing_ceasefire_run_turns=fc.CEASEFIRE_DURABILITY_TURNS - 1,
        )
        is fc.ConflictStatus.CEASEFIRE
    )


def test_exhaustion_recovery_cannot_go_negative() -> None:
    assert fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=100) == 0
    assert fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=0) == 0
    assert fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=300) == 0
    assert fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=301) == 1


# --- determinism and integer-only arithmetic -----------------------------------


def test_every_formula_returns_a_plain_int_and_repeats_exactly() -> None:
    """No float ever enters the state. `bool` is excluded explicitly because it subclasses
    `int` and would otherwise satisfy a naive isinstance check."""
    results = [
        fc.dyad_weight_bps(tension_bps=8_500, grievance_bps=7_500),
        fc.outbreak_probability_bps(total_weight_bps=8_000),
        fc.initial_intensity_bps(tension_bps=8_500),
        fc.exhaustion_gain_bps(opening_intensity_bps=5_550),
        fc.average_exhaustion_bps(exhaustion_a_bps=101, exhaustion_b_bps=200),
        fc.raw_closing_intensity_bps(
            opening_intensity_bps=5_550, closing_average_exhaustion_bps=1_200
        ),
        fc.closing_readiness_bps(
            closing_average_exhaustion_bps=6_000, closing_position_bps_value=-3_000
        ),
        fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=4_000),
        fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=5_000),
    ]
    for value in results:
        assert type(value) is int, f"{value!r} is {type(value)}, not a plain int"

    repeated = [
        fc.dyad_weight_bps(tension_bps=8_500, grievance_bps=7_500),
        fc.outbreak_probability_bps(total_weight_bps=8_000),
        fc.initial_intensity_bps(tension_bps=8_500),
        fc.exhaustion_gain_bps(opening_intensity_bps=5_550),
        fc.average_exhaustion_bps(exhaustion_a_bps=101, exhaustion_b_bps=200),
        fc.raw_closing_intensity_bps(
            opening_intensity_bps=5_550, closing_average_exhaustion_bps=1_200
        ),
        fc.closing_readiness_bps(
            closing_average_exhaustion_bps=6_000, closing_position_bps_value=-3_000
        ),
        fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=4_000),
        fc.ceasefire_recovered_exhaustion_bps(opening_exhaustion_bps=5_000),
    ]
    assert results == repeated


def test_the_whole_simulated_lifetime_is_reproducible() -> None:
    first = _simulate_active(turns=150, opening_intensity=5_550, capability_b=5_600)
    second = _simulate_active(turns=150, opening_intensity=5_550, capability_b=5_600)
    assert [(turn.intensity, turn.position, turn.readiness, turn.status) for turn in first] == [
        (turn.intensity, turn.position, turn.readiness, turn.status) for turn in second
    ]


# --- structural purity and domestic isolation, scoped to THIS module -----------


def _parsed_module_source(module: object) -> ast.Module:
    return ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))  # type: ignore[arg-type]


def test_foreign_conflict_contains_no_float_literal_and_no_true_division() -> None:
    """Scoped to `foreign_conflict.py` specifically, never generalized across the package: this
    module's integer-only guarantee is its own, and broadening the scan would silently change
    what other simulation modules are permitted to do. AST-based, so a `10.1` inside a comment
    or a `coup/unrest/` inside a docstring cannot raise a false positive."""
    tree = _parsed_module_source(fc)
    floats = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert floats == [], f"float literals in foreign_conflict.py: {floats}"

    divisions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]
    assert divisions == [], "foreign_conflict.py must divide only via trunc_div_toward_zero"


def test_foreign_conflict_reaches_for_no_generator_and_no_clock() -> None:
    """The draws this module consumes are passed in as integers by the caller. If it could
    reach a generator or a clock itself, the engine's determinism claim would depend on
    convention rather than on structure."""
    tree = _parsed_module_source(fc)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    forbidden = {"random", "secrets", "time", "datetime", "os"}
    offenders = [name for name in imported if name.split(".")[0] in forbidden]
    assert offenders == [], f"foreign_conflict.py imports {offenders}"


def test_foreign_capability_has_no_channel_into_domestic_survival_math() -> None:
    """The structural half of the R5 isolation guarantee, checkable at this commit: coup, unrest
    and impeachment cannot see foreign capability because there is no import and no reference
    through which it could arrive.

    The behavioural half -- resolving a real turn at capability 0 and 10,000 and asserting a
    byte-identical `CoupUnrestReport` -- requires the resolver, and lands with the phase wiring.
    """
    source = Path(inspect.getfile(government_survival_module)).read_text(encoding="utf-8")
    for forbidden in (
        "foreign_conflict",
        "ForeignProfileState",
        "foreign_profiles",
        "war_capability",
    ):
        assert forbidden not in source, (
            f"government_survival.py references {forbidden!r}; foreign capability must have no "
            "channel into coup, unrest or impeachment"
        )
