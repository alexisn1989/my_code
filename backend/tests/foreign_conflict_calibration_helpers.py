"""External Wars W1 commit 9: an isolated calibration harness -- turn iteration and per-conflict
status dispatch only. Every outbreak, progression, ceasefire, floor, termination and security-
anxiety CALCULATION calls a production function from `app.simulation.foreign_conflict`,
`app.simulation.legitimacy`, or `app.core.rng`. No formula is reimplemented here.

This mirrors `phases.py`'s own slot 7 (`_resolve_foreign_conflict_outbreak`), slot 8
(`_progress_active_conflict` / `_progress_ceasefire_conflict`), and the slot-10 security-anxiety
block, control flow for control flow -- it exists only because the real resolver also runs
unrelated phases (term limits, coups, elections) that can end a campaign
(`GameAlreadyConcludedError`) well inside the calibration's 40/80-turn horizons, which a
foreign-conflict-only loop is immune to. `TestCalibrationHarnessParity` in
`test_foreign_conflict_calibration.py` proves this loop reproduces `resolve_turn`'s own
foreign-affairs output byte-for-byte on every turn the two can be compared -- not a claim to take
on faith, but a passing test in the suite.

Test-support module, deliberately not registered in `conftest.py`: these are ordinary functions,
not pytest fixtures, matching this test suite's existing `history_tamper_helpers.py` convention.
"""

from __future__ import annotations

import dataclasses

from app.core.money import BPS_DENOMINATOR
from app.core.rng import derive_rng
from app.simulation import foreign_conflict as fc
from app.simulation.legitimacy import (
    aggregate_security_contribution_bps,
    foreign_conflict_security_anxiety_bps,
)
from app.simulation.state import ConflictDyadState, ForeignConflictState, GameState

# (conflict_id, opening_status, closing_status, closing_intensity_bps, active_intensity_floor_applied)
ProgressionRow = tuple[str, str, str, int, bool]


@dataclasses.dataclass(frozen=True, slots=True)
class TurnTrace:
    """One turn's isolated-harness output, field-aligned with `ForeignAffairsReport` plus the
    resulting conflict snapshot, for direct comparison against `resolve_turn`."""

    turn: int
    occurrence_draw: int
    occurred: bool
    selection_draw: int | None
    opened_conflict_id: str | None
    security_contribution_bps: int
    conflicts: tuple[ForeignConflictState, ...]
    progressions: tuple[ProgressionRow, ...]


def _slot7_outbreak(
    *,
    seed: int,
    turn: int,
    dyads: tuple[ConflictDyadState, ...],
    profiles: dict[str, object],
    conflicts: tuple[ForeignConflictState, ...],
) -> tuple[tuple[ForeignConflictState, ...], int, bool, int | None, str | None]:
    """Mirrors `phases._resolve_foreign_conflict_outbreak`'s control flow exactly."""
    excluded_pairs = {
        (c.country_a, c.country_b)
        for c in conflicts
        if c.status in (fc.ConflictStatus.ACTIVE, fc.ConflictStatus.CEASEFIRE)
    }
    at_capacity = not fc.concurrency_capacity_available(live_conflict_count=len(excluded_pairs))

    passing_dyads: list[ConflictDyadState] = []
    total_weight = 0
    for dyad in dyads:
        if at_capacity or not dyad.eligible or (dyad.country_a, dyad.country_b) in excluded_pairs:
            continue
        weight = fc.dyad_weight_bps(tension_bps=dyad.tension_bps, grievance_bps=dyad.grievance_bps)
        if fc.passes_pressure_floor(raw_weight_bps=weight):
            passing_dyads.append(dyad)
            total_weight += weight

    probability = fc.outbreak_probability_bps(total_weight_bps=total_weight)
    rng = derive_rng(seed, turn, "foreign_conflict_outbreak")
    occurrence_draw = rng.randrange(BPS_DENOMINATOR)
    occurred = fc.outbreak_occurs(occurrence_draw=occurrence_draw, probability_bps=probability)

    selection_draw = None
    opened_id = None
    if occurred:
        assert passing_dyads, "outbreak occurred but no candidate dyad passed the pressure floor"
        weights = tuple(
            fc.dyad_weight_bps(tension_bps=d.tension_bps, grievance_bps=d.grievance_bps)
            for d in passing_dyads
        )
        selection_draw = rng.randrange(total_weight)
        selected = passing_dyads[
            fc.select_candidate_index(selection_draw=selection_draw, weights_bps=weights)
        ]
        opened_id = f"{selected.country_a}__{selected.country_b}__t{turn}"
        new_conflict = ForeignConflictState(
            conflict_id=opened_id,
            country_a=selected.country_a,
            country_b=selected.country_b,
            aggressor=selected.aggressor,
            defender=selected.defender,
            war_capability_a_bps=profiles[selected.country_a].war_capability_bps,  # type: ignore[attr-defined]
            war_capability_b_bps=profiles[selected.country_b].war_capability_bps,  # type: ignore[attr-defined]
            aim_a=selected.aim_a,
            aim_b=selected.aim_b,
            opened_turn=turn,
            intensity_bps=fc.initial_intensity_bps(tension_bps=selected.tension_bps),
            position_bps=0,
            exhaustion_a_bps=0,
            exhaustion_b_bps=0,
            negotiation_readiness_bps=0,
            status=fc.ConflictStatus.ACTIVE,
            ceasefire_run_turns=0,
            resolved_turn=None,
        )
        conflicts = tuple(sorted((*conflicts, new_conflict), key=lambda c: c.conflict_id))
    return conflicts, occurrence_draw, occurred, selection_draw, opened_id


def _progress_active(
    *, seed: int, turn: int, conflict: ForeignConflictState
) -> tuple[ForeignConflictState, ProgressionRow]:
    """Mirrors `phases._progress_active_conflict`'s control flow exactly."""
    rng = derive_rng(seed, turn, f"foreign_conflict_progress:{conflict.conflict_id}")
    jitter = rng.randint(-fc.PROGRESS_JITTER_BPS, fc.PROGRESS_JITTER_BPS)
    position = fc.closing_position_bps(
        opening_position_bps=conflict.position_bps,
        opening_war_capability_a_bps=conflict.war_capability_a_bps,
        opening_war_capability_b_bps=conflict.war_capability_b_bps,
        opening_intensity_bps=conflict.intensity_bps,
        position_jitter_bps=jitter,
    )
    gain = fc.exhaustion_gain_bps(opening_intensity_bps=conflict.intensity_bps)
    exhaustion_a = min(BPS_DENOMINATOR, max(0, conflict.exhaustion_a_bps + gain))
    exhaustion_b = min(BPS_DENOMINATOR, max(0, conflict.exhaustion_b_bps + gain))
    avg = fc.average_exhaustion_bps(exhaustion_a_bps=exhaustion_a, exhaustion_b_bps=exhaustion_b)
    raw_intensity = fc.raw_closing_intensity_bps(
        opening_intensity_bps=conflict.intensity_bps, closing_average_exhaustion_bps=avg
    )
    readiness = fc.closing_readiness_bps(
        closing_average_exhaustion_bps=avg, closing_position_bps_value=position
    )
    termination_draw = None
    if not fc.is_decisive(closing_position_bps_value=position) and fc.ceasefire_gate_open(
        closing_readiness_bps_value=readiness
    ):
        termination_draw = derive_rng(
            seed, turn, f"foreign_conflict_termination:{conflict.conflict_id}"
        ).randrange(BPS_DENOMINATOR)
    status = fc.active_closing_status(
        closing_position_bps_value=position,
        closing_readiness_bps_value=readiness,
        termination_draw=termination_draw,
    )
    closing_intensity = fc.apply_active_intensity_floor(
        raw_intensity_bps=raw_intensity, closing_status=status
    )
    floor_applied = (
        status is fc.ConflictStatus.ACTIVE and raw_intensity < fc.MIN_ACTIVE_INTENSITY_BPS
    )
    updated = conflict.model_copy(
        update={
            "intensity_bps": closing_intensity,
            "position_bps": position,
            "exhaustion_a_bps": exhaustion_a,
            "exhaustion_b_bps": exhaustion_b,
            "negotiation_readiness_bps": readiness,
            "status": status,
            "ceasefire_run_turns": 0,
            "resolved_turn": turn if status in fc.TERMINAL_STATUSES else None,
        }
    )
    return updated, (conflict.conflict_id, "active", status.value, closing_intensity, floor_applied)


def _progress_ceasefire(
    *, turn: int, conflict: ForeignConflictState
) -> tuple[ForeignConflictState, ProgressionRow]:
    """Mirrors `phases._progress_ceasefire_conflict` exactly. Consumes no randomness (frozen
    plan sec.8.7)."""
    decayed = fc.ceasefire_decayed_intensity_bps(opening_intensity_bps=conflict.intensity_bps)
    exhaustion_a = fc.ceasefire_recovered_exhaustion_bps(
        opening_exhaustion_bps=conflict.exhaustion_a_bps
    )
    exhaustion_b = fc.ceasefire_recovered_exhaustion_bps(
        opening_exhaustion_bps=conflict.exhaustion_b_bps
    )
    avg = fc.average_exhaustion_bps(exhaustion_a_bps=exhaustion_a, exhaustion_b_bps=exhaustion_b)
    readiness = fc.closing_readiness_bps(
        closing_average_exhaustion_bps=avg, closing_position_bps_value=conflict.position_bps
    )
    provisional = conflict.ceasefire_run_turns + 1
    status = fc.ceasefire_closing_status(
        closing_readiness_bps_value=readiness, closing_ceasefire_run_turns=provisional
    )
    run_turns = 0 if status is fc.ConflictStatus.ACTIVE else provisional
    closing_intensity = fc.ceasefire_closing_intensity_bps(
        decayed_intensity_bps=decayed, closing_status=status
    )
    floor_applied = status is fc.ConflictStatus.ACTIVE and decayed < fc.MIN_ACTIVE_INTENSITY_BPS
    updated = conflict.model_copy(
        update={
            "intensity_bps": closing_intensity,
            "exhaustion_a_bps": exhaustion_a,
            "exhaustion_b_bps": exhaustion_b,
            "negotiation_readiness_bps": readiness,
            "status": status,
            "ceasefire_run_turns": run_turns,
            "resolved_turn": turn if status in fc.TERMINAL_STATUSES else None,
        }
    )
    return updated, (
        conflict.conflict_id,
        "ceasefire",
        status.value,
        closing_intensity,
        floor_applied,
    )


def _slot10_security(
    *, dyads: tuple[ConflictDyadState, ...], conflicts: tuple[ForeignConflictState, ...]
) -> int:
    """Mirrors the slot-10 security-anxiety block: post-slot-8 snapshot, `ACTIVE` conflicts only,
    exposure looked up from the originating dyad, raw contributions summed then capped exactly
    once."""
    exposure_by_pair = {(d.country_a, d.country_b): d.player_security_exposure_bps for d in dyads}
    uncapped = 0
    for conflict in conflicts:
        if conflict.status is not fc.ConflictStatus.ACTIVE:
            continue
        exposure = exposure_by_pair.get((conflict.country_a, conflict.country_b), 0)
        if exposure == 0:
            continue
        uncapped += foreign_conflict_security_anxiety_bps(
            exposure_bps=exposure, intensity_bps=conflict.intensity_bps
        )
    return aggregate_security_contribution_bps(uncapped_total_bps=uncapped)


def run_calibration(state: GameState, *, turns: int) -> list[TurnTrace]:
    """Drive `turns` foreign-affairs-only turns from `state`'s opening world: slot 7, then slot 8,
    then slot 10, in the frozen plan's sec.7/sec.8 opening/closing discipline. Immune to unrelated
    campaign-terminal outcomes (term limits, coups, elections) because it never touches those
    phases at all."""
    seed = state.seed
    dyads = state.world.dyads
    profiles = state.world.foreign_profiles
    conflicts = state.world.conflicts
    traces: list[TurnTrace] = []

    for turn in range(state.turn, state.turn + turns):
        conflicts, occ_draw, occurred, sel_draw, opened_id = _slot7_outbreak(
            seed=seed, turn=turn, dyads=dyads, profiles=profiles, conflicts=conflicts
        )
        rows: list[ProgressionRow] = []
        updated_by_id: dict[str, ForeignConflictState] = {}
        for conflict in conflicts:
            if conflict.status is fc.ConflictStatus.ACTIVE:
                updated, row = _progress_active(seed=seed, turn=turn, conflict=conflict)
            elif conflict.status is fc.ConflictStatus.CEASEFIRE:
                updated, row = _progress_ceasefire(turn=turn, conflict=conflict)
            else:
                continue
            updated_by_id[conflict.conflict_id] = updated
            rows.append(row)
        conflicts = tuple(updated_by_id.get(c.conflict_id, c) for c in conflicts)
        security = _slot10_security(dyads=dyads, conflicts=conflicts)
        traces.append(
            TurnTrace(
                turn=turn,
                occurrence_draw=occ_draw,
                occurred=occurred,
                selection_draw=sel_draw,
                opened_conflict_id=opened_id,
                security_contribution_bps=security,
                conflicts=conflicts,
                progressions=tuple(rows),
            )
        )
    return traces
