"""External Wars W1 commit 8: the frozen plan's sec.12 tamper matrix, historically named "16-case"
but enumerating 21 -- the original 16 plus five later group-52 cases. All 21 are implemented here.

Every case is a "knowledgeable tamperer": it edits one `HistoryEntry`'s stored state or report
JSON, then RE-LINKS AND RE-HASHES THE ENTIRE DOWNSTREAM CHAIN (`history_tamper_helpers`), so
`validate_history` finds a perfectly green hash chain. Only semantic reconciliation -- not
hashing, not even `TurnReport`'s own schema self-validators, which a JSON round-trip DOES
re-run -- can still catch it. Each ordinary case proves the chain is green FIRST (via the
independent `hash_chain_problems` verifier, not merely the absence of one substring), then
asserts a DISTINGUISHING, correctly-attributed reconciliation problem.

A tamper here must itself stay schema-valid on re-parse: `model_copy(update=...)` never
revalidates, but the tampered JSON DOES get re-parsed by `TurnReport.model_validate` during
`validate_history`'s replay (unlike the direct in-memory `reconcile_foreign_affairs_report(...)`
calls in `test_foreign_affairs_reconciliation.py`), so any tamper that only breaks a report-level
cross-field formula would be caught as a SCHEMA failure, not a reconciliation one --
disqualifying it under this file's own correction 6 requirement ("do not accept ... a parsing
failure ... as proof"). Several cases therefore build a fully self-consistent ALTERNATE formula
chain (reusing the exact same pure functions the engine and reconciler use) rather than
tampering one field in isolation; each says so in its docstring.

Case 15 (non-canonical ordering) is the one deliberate exception: `ForeignAffairsReport`'s own
`_progressions_are_canonically_ordered` construction-time-equivalent validator makes a
non-canonical `progressions` tuple unrepresentable in any report that survives re-parse at all,
so for THIS case only, a schema/parsing failure naming canonical order IS the correct semantic
defense -- the frozen plan assigns ordering to the report self-validator, not to reconciliation.
It uses its own assertion helper, `_assert_green_chain_and_schema_rejection`, rather than
`_assert_green_chain_and_group`.

Not commit 7's per-group focused suite, and not a repeat of it: this file's distinguishing
feature is running every case through the FULL history/hash-chain machinery end to end.
"""

from __future__ import annotations

from app.core.canonical_json import canonical_dumps
from app.core.politics import clamp_bps
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import (
    CEASEFIRE_RECOVERY_BPS,
    MIN_ACTIVE_INTENSITY_BPS,
    MIN_OUTBREAK_WEIGHT_BPS,
    TERMINAL_STATUSES,
    ConflictStatus,
    WarAim,
    active_closing_status,
    apply_active_intensity_floor,
    average_exhaustion_bps,
    closing_position_bps,
    closing_readiness_bps,
    exhaustion_gain_bps,
    initial_intensity_bps,
    outbreak_probability_bps,
    raw_closing_intensity_bps,
)
from app.simulation.history import validate_history
from app.simulation.report import ForeignConflictProgressionRow
from app.simulation.save_format import SAVE_FORMAT_VERSION, GameSave
from app.simulation.state import (
    ConflictDyadState,
    ForeignConflictState,
    ForeignProfileState,
    GameState,
)
from tests.conftest import make_game_state
from tests.history_tamper_helpers import (
    advance_n,
    hash_chain_problems,
    retamper_report_with_consistent_hash,
    retamper_state_with_consistent_hash,
)

DECLARED_SEEDS = (42, 1337, 20260826, 7, 99991)

PAIR_A = ("alpha", "beta")
PAIR_B = ("delta", "gamma")
PAIR_C = ("epsilon", "zeta")
_ALL_COUNTRIES = ("alpha", "beta", "delta", "gamma", "epsilon", "zeta")
_PROFILES = {
    name: ForeignProfileState(display_name="Profile", war_capability_bps=5_000)
    for name in _ALL_COUNTRIES
}


# --- shared construction helpers (mirrors test_foreign_affairs_reconciliation.py's own) --------


def _dyad(
    country_a: str,
    country_b: str,
    *,
    tension: int = 9_500,
    grievance: int = 9_500,
    eligible: bool = True,
    exposure: int = 2_000,
) -> ConflictDyadState:
    return ConflictDyadState(
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        eligible=eligible,
        player_security_exposure_bps=exposure,
        tension_bps=tension,
        grievance_bps=grievance,
    )


def _conflict(
    country_a: str,
    country_b: str,
    *,
    status: ConflictStatus,
    opened_turn: int = 0,
    intensity: int = 3_000,
    position: int = 0,
    exhaustion_a: int = 0,
    exhaustion_b: int = 0,
    readiness: int = 0,
    ceasefire_run_turns: int = 0,
    resolved_turn: int | None = None,
    capability_a: int = 5_000,
    capability_b: int = 5_000,
) -> ForeignConflictState:
    return ForeignConflictState(
        conflict_id=f"{country_a}__{country_b}__t{opened_turn}",
        country_a=country_a,
        country_b=country_b,
        aggressor=country_a,
        defender=country_b,
        war_capability_a_bps=capability_a,
        war_capability_b_bps=capability_b,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        opened_turn=opened_turn,
        intensity_bps=intensity,
        position_bps=position,
        exhaustion_a_bps=exhaustion_a,
        exhaustion_b_bps=exhaustion_b,
        negotiation_readiness_bps=readiness,
        status=status,
        ceasefire_run_turns=ceasefire_run_turns,
        resolved_turn=resolved_turn,
    )


def _empty_decisions(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _new_synthetic_save(
    *,
    dyads: tuple[ConflictDyadState, ...] = (),
    conflicts: tuple[ForeignConflictState, ...] = (),
    foreign_profiles: dict[str, ForeignProfileState] | None = None,
    seed: int = 7,
) -> GameSave:
    from app.simulation.history import new_game

    state = make_game_state(
        seed=seed,
        foreign_profiles=foreign_profiles if foreign_profiles is not None else _PROFILES,
        dyads=dyads,
        conflicts=conflicts,
    )
    return new_game(state, save_format_version=SAVE_FORMAT_VERSION)


# --- the shared "prove it, then attribute it" assertion -----------------------------------------


def _assert_green_chain_and_group(tampered: GameSave, *, group_substring: str) -> list[str]:
    """Independently prove the ENTIRE chain is intact (not merely that one substring is absent),
    then assert a distinguishing, correctly-attributed reconciliation problem."""
    chain_problems = hash_chain_problems(tampered)
    assert chain_problems == [], (
        f"hash chain corrupted by the tamper helper itself: {chain_problems!r}"
    )

    problems = validate_history(tampered)
    hash_leak = [
        p
        for p in problems
        if "entry_hash" in p or "previous_entry_hash" in p or "head_entry_hash" in p
    ]
    assert hash_leak == [], f"a hash-chain complaint leaked into validate_history: {hash_leak!r}"

    parse_leak = [p for p in problems if "schema validation" in p or "not valid JSON" in p]
    assert parse_leak == [], (
        f"the tamper was caught by parsing/schema, not reconciliation: {parse_leak!r}"
    )

    matches = [p for p in problems if group_substring in p]
    assert matches, f"expected a problem containing {group_substring!r}, got {problems!r}"
    return problems


def _assert_green_chain_and_schema_rejection(tampered: GameSave, *, substring: str) -> list[str]:
    """Case 15's own counterpart: the chain must still be green (this is not a hash-tamper
    test), but here a schema/parsing-failure problem naming canonical order IS the correct,
    deliberate outcome -- ordering is the report self-validator's job, not reconciliation's."""
    chain_problems = hash_chain_problems(tampered)
    assert chain_problems == [], (
        f"hash chain corrupted by the tamper helper itself: {chain_problems!r}"
    )

    problems = validate_history(tampered)
    hash_leak = [
        p
        for p in problems
        if "entry_hash" in p or "previous_entry_hash" in p or "head_entry_hash" in p
    ]
    assert hash_leak == [], f"a hash-chain complaint leaked into validate_history: {hash_leak!r}"

    matches = [p for p in problems if substring in p]
    assert matches, (
        f"expected a schema-rejection problem containing {substring!r}, got {problems!r}"
    )
    return problems


def _tamper_last_state(save: GameSave, mutate) -> GameSave:  # type: ignore[no-untyped-def]
    """Tamper the LAST entry's STATE via `mutate(GameState) -> GameState`. Deliberately always
    the last entry: this is the only choice that can never also become someone's OPENING-side
    tamper (there is no turn after it), so its effect is single and unambiguous."""
    index = len(save.entries) - 1
    state = save.entries[index].state()
    tampered_json = canonical_dumps(mutate(state).model_dump(mode="json"))
    return retamper_state_with_consistent_hash(save, index=index, tampered_state_json=tampered_json)


def _tamper_genesis_state(save: GameSave, mutate) -> GameSave:  # type: ignore[no-untyped-def]
    """Tamper entry 0 (genesis) via `mutate`. Genesis is the only entry that is NEVER anyone's
    CLOSING state (there is no turn -1), so this is the single-effect way to corrupt an OPENING
    side only -- used for group-46 opening-provenance cases."""
    state = save.entries[0].state()
    tampered_json = canonical_dumps(mutate(state).model_dump(mode="json"))
    return retamper_state_with_consistent_hash(save, index=0, tampered_state_json=tampered_json)


def _tamper_last_report(save: GameSave, mutate) -> GameSave:  # type: ignore[no-untyped-def]
    """Tamper the LAST entry's REPORT via `mutate(TurnReport) -> TurnReport`."""
    index = len(save.entries) - 1
    report = save.entries[index].report()
    assert report is not None
    tampered_json = canonical_dumps(mutate(report).model_dump(mode="json"))
    return retamper_report_with_consistent_hash(
        save, index=index, tampered_report_json=tampered_json
    )


def _recompute_active_row_closing_fields(
    row: ForeignConflictProgressionRow, *, jitter: int, termination_draw: int | None
) -> dict[str, object]:
    """Recompute EVERY ACTIVE-branch closing_* field from `row`'s own opening_* fields plus a
    CHOSEN jitter/termination_draw, mirroring report.py's `_active_branch_matches_the_progression_
    formulas` self-validator formula-for-formula. Produces a fully self-consistent alternate
    closing chain -- one that survives re-parse -- built from a DIFFERENT die roll than the real
    engine actually drew, so it disagrees with the real redraw without tripping any schema check.
    """
    position = closing_position_bps(
        opening_position_bps=row.opening_position_bps,
        opening_war_capability_a_bps=row.opening_war_capability_a_bps,
        opening_war_capability_b_bps=row.opening_war_capability_b_bps,
        opening_intensity_bps=row.opening_intensity_bps,
        position_jitter_bps=jitter,
    )
    gain = exhaustion_gain_bps(opening_intensity_bps=row.opening_intensity_bps)
    exhaustion_a = clamp_bps(row.opening_exhaustion_a_bps + gain)
    exhaustion_b = clamp_bps(row.opening_exhaustion_b_bps + gain)
    avg = average_exhaustion_bps(exhaustion_a_bps=exhaustion_a, exhaustion_b_bps=exhaustion_b)
    raw_intensity = raw_closing_intensity_bps(
        opening_intensity_bps=row.opening_intensity_bps, closing_average_exhaustion_bps=avg
    )
    readiness = closing_readiness_bps(
        closing_average_exhaustion_bps=avg, closing_position_bps_value=position
    )
    status = active_closing_status(
        closing_position_bps_value=position,
        closing_readiness_bps_value=readiness,
        termination_draw=termination_draw,
    )
    closing_intensity = apply_active_intensity_floor(
        raw_intensity_bps=raw_intensity, closing_status=status
    )
    floor_applied = (
        status is ConflictStatus.ACTIVE and raw_intensity < row.minimum_active_intensity_bps
    )
    return {
        "position_jitter_bps": jitter,
        "closing_position_bps": position,
        "exhaustion_gain_bps": gain,
        "closing_exhaustion_a_bps": exhaustion_a,
        "closing_exhaustion_b_bps": exhaustion_b,
        "closing_avg_exhaustion_bps": avg,
        "raw_closing_intensity_bps": raw_intensity,
        "closing_readiness_bps": readiness,
        "termination_draw": termination_draw,
        "closing_status": status,
        "closing_intensity_bps": closing_intensity,
        "active_intensity_floor_applied": floor_applied,
        "resolved_turn": (row.opened_turn if status in TERMINAL_STATUSES else None),
        "closing_ceasefire_run_turns": 0,
    }


# --- case 1: tampered opening/closing position (group 46) ---------------------------------------


def test_case01_tampered_opening_position_is_caught() -> None:
    """Genesis (turn 0) carries the real opening conflict; tampering ONLY genesis's stored
    position leaves the real report (built from the REAL genesis) internally correct, but now
    disagreeing with the (corrupted) opening_state -- group 46's opening-provenance concern."""
    save = _new_synthetic_save(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    save = advance_n(save, 1)
    assert save.entries[1].report().foreign_affairs.progressions  # sanity: a row exists

    def mutate(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(update={"position_bps": conflict.position_bps + 500})
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    tampered = _tamper_genesis_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 46)")


# --- case 2: tampered component (group 47) --- interpreted as a closing-state component field --


def test_case02_tampered_closing_exhaustion_component_is_caught() -> None:
    """Frozen plan sec.12 leaves this case's group unlabeled (only draws/capability/profile/dyad/
    exposure/floor cases carry an explicit tag); group 47 owns "membership and projection," and a
    per-side exhaustion figure is exactly a projected CLOSING component of the conflict, so this
    is attributed there. Tampering the LAST entry's closing state leaves the real report's closing
    claim (matching the real, untampered resolution) disagreeing with the now-corrupted state."""
    save = _new_synthetic_save(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    save = advance_n(save, 1)

    def mutate(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(
            update={"exhaustion_a_bps": min(10_000, conflict.exhaustion_a_bps + 777)}
        )
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 47)")


# --- case 3: tampered stored constant (group 47) -- `ceasefire_recovery_bps` on a CEASEFIRE row -


def test_case03_tampered_stored_ceasefire_recovery_constant_is_caught() -> None:
    """The row stores `ceasefire_recovery_bps` and its OWN self-validator ties it to
    `exhaustion_gain_bps`/`closing_exhaustion_a/b_bps` (report.py's
    `_ceasefire_branch_matches_the_maintenance_formulas`) -- but reconciliation never reads that
    stored field at all; it always uses the real `CEASEFIRE_RECOVERY_BPS` module constant. So a
    tampered stored constant, kept self-consistent with its OWN dependents (surviving re-parse),
    still disagrees with the REAL closing state. Opening exhaustion 800/800 (well above 0, so the
    recovery delta is actually visible) and 0 position keep both the real and the fake chain's
    readiness far below `CEASEFIRE_BREAKDOWN_BPS` (4,000), so closing_status stays ACTIVE either
    way -- isolating the constant itself as the only semantic difference."""
    save = _new_synthetic_save(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.CEASEFIRE,
                exhaustion_a=800,
                exhaustion_b=800,
                position=0,
                readiness=0,
            ),
        )
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.opening_status is ConflictStatus.CEASEFIRE
    assert real_row.closing_status is ConflictStatus.ACTIVE, "sanity: breaks down as designed"

    fake_recovery = CEASEFIRE_RECOVERY_BPS + 10
    fake_gain = -fake_recovery
    fake_exhaustion_a = max(0, real_row.opening_exhaustion_a_bps - fake_recovery)
    fake_exhaustion_b = max(0, real_row.opening_exhaustion_b_bps - fake_recovery)
    fake_avg = average_exhaustion_bps(
        exhaustion_a_bps=fake_exhaustion_a, exhaustion_b_bps=fake_exhaustion_b
    )
    fake_readiness = closing_readiness_bps(
        closing_average_exhaustion_bps=fake_avg,
        closing_position_bps_value=real_row.closing_position_bps,
    )
    assert fake_readiness < 4_000, "sanity: must not flip the real breakdown outcome"

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(
                update={
                    "ceasefire_recovery_bps": fake_recovery,
                    "exhaustion_gain_bps": fake_gain,
                    "closing_exhaustion_a_bps": fake_exhaustion_a,
                    "closing_exhaustion_b_bps": fake_exhaustion_b,
                    "closing_avg_exhaustion_bps": fake_avg,
                    "closing_readiness_bps": fake_readiness,
                }
            )
            if row.conflict_id == real_row.conflict_id
            else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 47)")


# --- case 4: tampered status transition (group 47) -----------------------------------------------


def test_case04_tampered_status_transition_is_caught() -> None:
    """The LAST entry's real conflict never became decisive; the report is forged with a
    self-consistent alternate chain built from an extreme jitter (6,000, far outside the real
    +/-300 draw range the field's own type does not itself constrain) that DOES cross the
    decisive threshold, flipping closing_status to DECIDED -- a full, internally consistent
    downstream recompute (`_recompute_active_row_closing_fields`), not a bare status swap, so it
    survives report.py's own terminal-status/formula self-validators on re-parse."""
    save = _new_synthetic_save(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.closing_status is ConflictStatus.ACTIVE

    fake_fields = _recompute_active_row_closing_fields(
        real_row, jitter=6_000, termination_draw=None
    )
    assert fake_fields["closing_status"] is ConflictStatus.DECIDED

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(update=fake_fields) if row.conflict_id == real_row.conflict_id else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 47)")


# --- case 5: deleted row (group 47) ---------------------------------------------------------------


def test_case05_deleted_progression_row_is_caught() -> None:
    save = _new_synthetic_save(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    save = advance_n(save, 1)

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": ()})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 47)")


# --- case 6: fabricated conflict (group 46) -------------------------------------------------------


def test_case06_fabricated_conflict_with_no_valid_source_is_caught() -> None:
    """A progression row for a conflict_id matching neither a real opening conflict nor a
    validated outbreak initialization -- group 46's "neither source" failure."""
    save = _new_synthetic_save(dyads=(_dyad(*PAIR_A),))
    save = advance_n(save, 1)
    real_report = save.entries[1].report()
    assert real_report.foreign_affairs is not None

    fabricated_conflict_id = "alpha__beta__t999"
    # opening_intensity_bps=0 makes every downstream figure computable by hand from the real
    # pure formulas without a full recompute helper: exhaustion_gain_bps(0)=0 (no fighting, no
    # attrition), so exhaustion/avg/readiness/position all stay 0, and only raw intensity moves
    # (the constant escalation term) -- computed via the real function, not guessed.
    fake_gain = exhaustion_gain_bps(opening_intensity_bps=0)
    fake_raw_intensity = raw_closing_intensity_bps(
        opening_intensity_bps=0, closing_average_exhaustion_bps=0
    )
    fake_closing_intensity = apply_active_intensity_floor(
        raw_intensity_bps=fake_raw_intensity, closing_status=ConflictStatus.ACTIVE
    )
    fabricated_row = ForeignConflictProgressionRow(
        conflict_id=fabricated_conflict_id,
        opened_turn=0,
        resolved_turn=None,
        opening_status=ConflictStatus.ACTIVE,
        closing_status=ConflictStatus.ACTIVE,
        opening_war_capability_a_bps=5_000,
        opening_war_capability_b_bps=5_000,
        opening_intensity_bps=0,
        raw_closing_intensity_bps=fake_raw_intensity,
        closing_intensity_bps=fake_closing_intensity,
        minimum_active_intensity_bps=MIN_ACTIVE_INTENSITY_BPS,
        active_intensity_floor_applied=fake_raw_intensity < MIN_ACTIVE_INTENSITY_BPS,
        opening_position_bps=0,
        closing_position_bps=0,
        position_jitter_bps=0,
        opening_exhaustion_a_bps=0,
        opening_exhaustion_b_bps=0,
        closing_exhaustion_a_bps=0,
        closing_exhaustion_b_bps=0,
        closing_avg_exhaustion_bps=0,
        exhaustion_rate_bps=0,
        exhaustion_gain_bps=fake_gain,
        intensity_growth_bps=0,
        intensity_decay_bps=0,
        opening_readiness_bps=0,
        closing_readiness_bps=0,
        decisiveness_penalty_bps=0,
        decisive_position_threshold_bps=6_000,
        ceasefire_threshold_bps=5_000,
        settlement_threshold_bps=7_500,
        ceasefire_intensity_decay_bps=0,
        ceasefire_recovery_bps=CEASEFIRE_RECOVERY_BPS,
        ceasefire_breakdown_bps=4_000,
        ceasefire_durability_turns=4,
        opening_ceasefire_run_turns=0,
        closing_ceasefire_run_turns=0,
        termination_draw=None,
    )

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        return report.model_copy(
            update={
                "foreign_affairs": fa.model_copy(
                    update={"progressions": (*fa.progressions, fabricated_row)}
                )
            }
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 46)")


# --- cases 7-11: RNG redraw with guard parity (all via group 48) --------------------------------


def _save_with_a_fresh_outbreak() -> GameSave:
    """A single high-weight dyad, advanced turn by turn until an outbreak genuinely occurs.
    Bounded, declared-seed search -- every outcome is the real engine's, only WHICH turn fires
    varies by seed, mirroring `test_foreign_affairs_reconciliation.py`'s own established pattern."""
    for seed in DECLARED_SEEDS:
        save = _new_synthetic_save(dyads=(_dyad(*PAIR_A),), seed=seed)
        for _ in range(60):
            save = advance_n(save, 1)
            report = save.entries[-1].report()
            if (
                report is not None
                and report.foreign_affairs is not None
                and report.foreign_affairs.outbreak.occurred
            ):
                return save
    raise AssertionError("no outbreak occurred within the declared-seed search bound")


def _save_with_a_quiet_outbreak_turn() -> GameSave:
    """A single high-weight dyad, advanced ONE turn, on a seed where the outbreak draw did NOT
    fire this turn (the common case: weight 9,500 gives ~6.65% occurrence odds) -- still a
    genuine candidate is present, so an occurrence CAN be forged onto it."""
    for seed in DECLARED_SEEDS:
        save = _new_synthetic_save(dyads=(_dyad(*PAIR_A),), seed=seed)
        save = advance_n(save, 1)
        report = save.entries[-1].report()
        assert report is not None and report.foreign_affairs is not None
        if not report.foreign_affairs.outbreak.occurred:
            return save
    raise AssertionError(
        "every declared seed's turn 0 outbreak fired; none left quiet to forge onto"
    )


def test_case07_fabricated_outbreak_occurrence_is_caught() -> None:
    """A real turn where the outbreak draw did NOT fire is forged to claim it did, selecting the
    one real (above-floor) candidate with a fully self-consistent initialization AND a matching
    fabricated progression row (`ForeignAffairsReport`'s own cross-field validator requires one
    whenever `outbreak.occurred=True`) -- so the whole forged report survives every one of
    report.py's own schema self-validators on re-parse, and only the real redrawn
    occurrence_draw/occurred disagree."""
    save = _save_with_a_quiet_outbreak_turn()
    real_report = save.entries[-1].report()
    outbreak = real_report.foreign_affairs.outbreak
    assert not outbreak.occurred
    candidate = outbreak.candidates[0]
    assert candidate.passed_pressure_floor

    fake_occurrence_draw = 0
    fake_selection_draw = 0
    fake_probability = outbreak.clamped_probability_bps
    assert fake_occurrence_draw < fake_probability, "sanity: this draw must legitimately fire"

    turn = outbreak.turn
    fake_conflict_id = f"{candidate.country_a}__{candidate.country_b}__t{turn}"
    fake_opening_intensity = initial_intensity_bps(tension_bps=candidate.tension_bps)
    # A brand-new conflict progresses in the SAME turn it opens (slot 7 then slot 8): jitter=0 and
    # capability_a==capability_b (drift=0) keep position at 0, well short of any gate, so the
    # ACTIVE branch closes deterministically with no termination draw.
    fake_gain = exhaustion_gain_bps(opening_intensity_bps=fake_opening_intensity)
    fake_exhaustion = clamp_bps(0 + fake_gain)
    fake_avg = average_exhaustion_bps(
        exhaustion_a_bps=fake_exhaustion, exhaustion_b_bps=fake_exhaustion
    )
    fake_raw_intensity = raw_closing_intensity_bps(
        opening_intensity_bps=fake_opening_intensity, closing_average_exhaustion_bps=fake_avg
    )
    fake_readiness = closing_readiness_bps(
        closing_average_exhaustion_bps=fake_avg, closing_position_bps_value=0
    )
    assert fake_readiness < 5_000, "sanity: gate must stay closed so termination_draw is None"
    fake_closing_intensity = apply_active_intensity_floor(
        raw_intensity_bps=fake_raw_intensity, closing_status=ConflictStatus.ACTIVE
    )
    fake_progression_row = ForeignConflictProgressionRow(
        conflict_id=fake_conflict_id,
        opened_turn=turn,
        resolved_turn=None,
        opening_status=ConflictStatus.ACTIVE,
        closing_status=ConflictStatus.ACTIVE,
        opening_war_capability_a_bps=5_000,
        opening_war_capability_b_bps=5_000,
        opening_intensity_bps=fake_opening_intensity,
        raw_closing_intensity_bps=fake_raw_intensity,
        closing_intensity_bps=fake_closing_intensity,
        minimum_active_intensity_bps=MIN_ACTIVE_INTENSITY_BPS,
        active_intensity_floor_applied=fake_raw_intensity < MIN_ACTIVE_INTENSITY_BPS,
        opening_position_bps=0,
        closing_position_bps=0,
        position_jitter_bps=0,
        opening_exhaustion_a_bps=0,
        opening_exhaustion_b_bps=0,
        closing_exhaustion_a_bps=fake_exhaustion,
        closing_exhaustion_b_bps=fake_exhaustion,
        closing_avg_exhaustion_bps=fake_avg,
        exhaustion_rate_bps=0,
        exhaustion_gain_bps=fake_gain,
        intensity_growth_bps=0,
        intensity_decay_bps=0,
        opening_readiness_bps=0,
        closing_readiness_bps=fake_readiness,
        decisiveness_penalty_bps=0,
        decisive_position_threshold_bps=6_000,
        ceasefire_threshold_bps=5_000,
        settlement_threshold_bps=7_500,
        ceasefire_intensity_decay_bps=0,
        ceasefire_recovery_bps=CEASEFIRE_RECOVERY_BPS,
        ceasefire_breakdown_bps=4_000,
        ceasefire_durability_turns=4,
        opening_ceasefire_run_turns=0,
        closing_ceasefire_run_turns=0,
        termination_draw=None,
    )

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        forged_outbreak = fa.outbreak.model_copy(
            update={
                "occurrence_draw": fake_occurrence_draw,
                "occurred": True,
                "selection_draw": fake_selection_draw,
                "selected_country_a": candidate.country_a,
                "selected_country_b": candidate.country_b,
                "conflict_id": fake_conflict_id,
                "opened_turn": turn,
                "initial_intensity_bps": fake_opening_intensity,
                "initial_position_bps": 0,
                "initial_exhaustion_a_bps": 0,
                "initial_exhaustion_b_bps": 0,
                "initial_readiness_bps": 0,
            }
        )
        return report.model_copy(
            update={
                "foreign_affairs": fa.model_copy(
                    update={
                        "outbreak": forged_outbreak,
                        "progressions": (*fa.progressions, fake_progression_row),
                    }
                )
            }
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 48)")


def test_case08_tampered_occurrence_draw_is_caught() -> None:
    """A genuine outbreak turn's `occurrence_draw` is swapped for a DIFFERENT value that still
    legitimately produces `occurred=True` under the report's own stored probability (so
    `_occurred_matches_the_draw` stays satisfied on re-parse), yet disagrees with the real
    redrawn value from the real seeded stream."""
    save = _save_with_a_fresh_outbreak()
    outbreak = save.entries[-1].report().foreign_affairs.outbreak
    assert outbreak.occurred
    probability = outbreak.clamped_probability_bps
    assert probability > 1, "sanity: need at least two valid draw values to pick a different one"
    fake_draw = (outbreak.occurrence_draw + 1) % probability
    assert fake_draw != outbreak.occurrence_draw

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        return report.model_copy(
            update={
                "foreign_affairs": fa.model_copy(
                    update={
                        "outbreak": fa.outbreak.model_copy(update={"occurrence_draw": fake_draw})
                    }
                )
            }
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 48)")


def test_case09_tampered_selection_draw_is_caught() -> None:
    """The same genuine outbreak turn's `selection_draw` is swapped for a different value that
    still lands on the SAME candidate (the sole passing dyad's weight span covers the whole
    range), so `_selected_pair_and_initialization_match_the_formulas` stays satisfied, yet
    disagrees with the real redrawn selection draw."""
    save = _save_with_a_fresh_outbreak()
    outbreak = save.entries[-1].report().foreign_affairs.outbreak
    assert outbreak.selection_draw is not None
    total_weight = outbreak.total_weight_bps
    assert total_weight > 1
    fake_draw = (outbreak.selection_draw + 1) % total_weight
    assert fake_draw != outbreak.selection_draw

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        return report.model_copy(
            update={
                "foreign_affairs": fa.model_copy(
                    update={
                        "outbreak": fa.outbreak.model_copy(update={"selection_draw": fake_draw})
                    }
                )
            }
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 48)")


def test_case10_tampered_progress_jitter_is_caught() -> None:
    """An ACTIVE-opening row's `position_jitter_bps` is swapped for a small alternate value (the
    real +/-300 range is the RNG's, not a schema constraint), with the ENTIRE downstream chain
    self-consistently recomputed from it, so the row survives re-parse while disagreeing with the
    real redrawn jitter stream."""
    save = _new_synthetic_save(conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE),))
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    fake_jitter = real_row.position_jitter_bps + 50
    fake_fields = _recompute_active_row_closing_fields(
        real_row, jitter=fake_jitter, termination_draw=None
    )
    assert fake_fields["closing_status"] is ConflictStatus.ACTIVE, "sanity: must not cross a gate"

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(update=fake_fields) if row.conflict_id == real_row.conflict_id else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 48)")


def test_case11_tampered_termination_draw_is_caught() -> None:
    """Opening exhaustion authored high enough (5,300/5,300) that ONE turn's gain pushes closing
    readiness into [5,000, 7,500) -- above `CEASEFIRE_THRESHOLD_BPS` (gate open) but below
    `SETTLEMENT_THRESHOLD_BPS`, so `settles_rather_than_pauses` is False for EVERY possible
    termination_draw value: the outcome (CEASEFIRE) is invariant to the draw's exact value, so
    tampering `termination_draw` ALONE stays self-consistent on re-parse while disagreeing with
    the real redrawn value from the real seeded stream."""
    save = _new_synthetic_save(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.ACTIVE,
                intensity=1_667,
                exhaustion_a=5_300,
                exhaustion_b=5_300,
            ),
        )
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.termination_draw is not None, "sanity: the gate must be open this turn"
    assert real_row.closing_status is ConflictStatus.CEASEFIRE, "sanity: must not settle"
    fake_draw = (real_row.termination_draw + 1) % 10_000
    assert fake_draw != real_row.termination_draw

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(update={"termination_draw": fake_draw})
            if row.conflict_id == real_row.conflict_id
            else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 48)")


# --- case 12: tampered capability (group 50) ------------------------------------------------------


def test_case12_tampered_capability_is_caught() -> None:
    """The row's `opening_war_capability_a_bps` is tampered to disagree with the real (unchanged)
    `foreign_profiles` entry -- group 50's capability-provenance concern. `intensity=0` keeps the
    position-drift term's capability-difference factor multiplied by zero, so the row's OWN
    self-validator (which recomputes `closing_position_bps` from the row's own capability fields)
    stays satisfied regardless of what capability the row claims."""
    save = _new_synthetic_save(
        conflicts=(
            _conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=0, capability_a=5_000),
        )
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(update={"opening_war_capability_a_bps": 9_999})
            if row.conflict_id == real_row.conflict_id
            else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 50)")


# --- case 13: tampered foreign_profiles entry (group 49) ------------------------------------------


def test_case13_tampered_foreign_profile_is_caught() -> None:
    """`foreign_profiles` must be authored and static across a turn (group 49) -- a pure
    closing-state tamper, no report involvement at all."""
    save = _new_synthetic_save(dyads=(_dyad(*PAIR_A),))
    save = advance_n(save, 1)

    def mutate(state: GameState) -> GameState:
        mutated_profiles = dict(state.world.foreign_profiles)
        mutated_profiles["alpha"] = mutated_profiles["alpha"].model_copy(
            update={"war_capability_bps": mutated_profiles["alpha"].war_capability_bps + 1}
        )
        return state.model_copy(
            update={"world": state.world.model_copy(update={"foreign_profiles": mutated_profiles})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 49)")


# --- case 14: tampered authored dyad (group 49) ---------------------------------------------------


def test_case14_tampered_dyad_is_caught() -> None:
    """`world.dyads` must likewise be authored and static across a turn (group 49)."""
    save = _new_synthetic_save(dyads=(_dyad(*PAIR_A),))
    save = advance_n(save, 1)

    def mutate(state: GameState) -> GameState:
        mutated_dyads = tuple(
            d.model_copy(update={"tension_bps": 1}) if d.country_a == "alpha" else d
            for d in state.world.dyads
        )
        return state.model_copy(
            update={"world": state.world.model_copy(update={"dyads": mutated_dyads})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 49)")


# --- case 15: non-canonical ordering (schema-owner exception, NOT a reconciliation group) -------


def test_case15_non_canonical_progression_ordering_is_rejected_by_schema() -> None:
    """`ForeignAffairsReport._progressions_are_canonically_ordered` requires strictly increasing
    `conflict_id` order and is re-run on every re-parse, so a report whose stored `progressions`
    tuple is reversed can never survive `TurnReport.model_validate` -- there is no way to
    construct this tamper that reconciliation would ever see. Canonical ordering is the report
    self-validator's job, not reconciliation's, exactly as the frozen plan's group definitions
    assign it; a schema-rejection naming canonical order IS the correct, deliberate outcome for
    this one case, verified via `_assert_green_chain_and_schema_rejection` rather than
    `_assert_green_chain_and_group`.

    `world.foreign_profiles`' dict insertion order is a DIFFERENT, deliberately order-INDEPENDENT
    concern (group 49/52, already covered by
    `test_group49_and_52_foreign_profile_insertion_order_is_irrelevant` in the commit-7 focused
    suite) and is not reordered here."""
    save = _new_synthetic_save(
        conflicts=(
            _conflict(*PAIR_A, status=ConflictStatus.ACTIVE),
            _conflict(*PAIR_B, status=ConflictStatus.ACTIVE),
        )
    )
    save = advance_n(save, 1)
    real_report = save.entries[-1].report()
    real_ids = [row.conflict_id for row in real_report.foreign_affairs.progressions]
    assert real_ids == sorted(real_ids) and len(real_ids) == 2, (
        "sanity: two genuinely canonically-ordered rows must exist to reverse"
    )

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        reversed_rows = tuple(reversed(fa.progressions))
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": reversed_rows})}
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_schema_rejection(tampered, substring="canonical conflict_id order")


def test_case16_fabricated_security_exposure_effect_is_caught() -> None:
    """The political report is left completely genuine and untouched (self-consistent by
    construction, since it is the real resolver's own output) -- only the CLOSING state's real
    conflict intensity is tampered. Group 51 recomputes the security contribution from scratch
    off the real closing conflict state, independent of either report, so this alone is enough to
    disagree with the political report's (real, unmodified) claim -- proving the cross-report
    check does not require touching the political report itself to trip."""
    save = _new_synthetic_save(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=6_000),),
    )
    # exposure lives on the dyad (sec.9.2), so it must exist even though the conflict already
    # started -- add it directly to the genesis state used for resolution.
    genesis_state = save.entries[0].state()
    genesis_state = genesis_state.model_copy(
        update={
            "world": genesis_state.world.model_copy(
                update={"dyads": (_dyad(*PAIR_A, exposure=3_000),)}
            )
        }
    )
    save = retamper_state_with_consistent_hash(
        save, index=0, tampered_state_json=canonical_dumps(genesis_state.model_dump(mode="json"))
    )
    save = advance_n(save, 1)
    real_political = save.entries[1].report().political
    assert real_political is not None
    assert real_political.security_contribution_bps != 0, "sanity: must be nonzero"

    def mutate(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(update={"intensity_bps": 9_999})
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 51)")


# --- cases 17-19: both intensity floors (group 52) ------------------------------------------------


def test_case17_closing_active_intensity_below_floor_is_caught() -> None:
    """The real turn keeps the conflict ACTIVE with intensity above the floor (report.py's own
    row self-validator ties `closing_intensity_bps` to `apply_active_intensity_floor`, using the
    REAL module constant, so a schema-valid ACTIVE row can never claim a sub-floor closing
    intensity -- this must therefore be a pure STATE tamper, leaving the genuine report as-is)."""
    save = _new_synthetic_save(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=3_000),)
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.closing_status is ConflictStatus.ACTIVE
    assert real_row.closing_intensity_bps >= MIN_ACTIVE_INTENSITY_BPS

    def mutate(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(update={"intensity_bps": 1})
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 52)")


def test_case18_inflated_stored_minimum_decoy_does_not_excuse_the_floor_violation() -> None:
    """Same violation as case 17, PLUS the report row's own stored `minimum_active_intensity_bps`
    is inflated as a decoy, "justifying" the (still schema-valid, still real-floor-respecting)
    reported intensity. Reconciliation never reads the row's stored minimum at all -- it always
    compares the REAL closing_state intensity against the REAL `MIN_ACTIVE_INTENSITY_BPS` module
    constant -- so the decoy changes nothing about the outcome."""
    save = _new_synthetic_save(
        conflicts=(_conflict(*PAIR_A, status=ConflictStatus.ACTIVE, intensity=3_000),)
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.closing_status is ConflictStatus.ACTIVE

    def mutate_state(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(update={"intensity_bps": 1})
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    def mutate_report(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        rows = tuple(
            row.model_copy(update={"minimum_active_intensity_bps": 1})
            if row.conflict_id == real_row.conflict_id
            else row
            for row in fa.progressions
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"progressions": rows})}
        )

    index = len(save.entries) - 1
    state_json = canonical_dumps(mutate_state(save.entries[index].state()).model_dump(mode="json"))
    report_json = canonical_dumps(
        mutate_report(save.entries[index].report()).model_dump(mode="json")
    )
    tampered = retamper_state_with_consistent_hash(
        save, index=index, tampered_state_json=state_json
    )
    tampered = retamper_report_with_consistent_hash(
        tampered, index=index, tampered_report_json=report_json
    )
    _assert_green_chain_and_group(tampered, group_substring="(group 52)")


def test_case19_ceasefire_to_active_breakdown_below_floor_is_caught() -> None:
    """CEASEFIRE consumes no randomness at all (sec.8.7): with opening exhaustion 0/0, recovery
    cannot lower it further, so readiness stays 0 -- deterministically below
    `CEASEFIRE_BREAKDOWN_BPS` (4,000) regardless of seed, so this conflict breaks down to ACTIVE
    every time. The real breakdown intensity is genuinely at/above the floor (the engine applies
    it too); only the CLOSING STATE's intensity is tampered below it, for the same schema reason
    as case 17."""
    save = _new_synthetic_save(
        conflicts=(
            _conflict(
                *PAIR_A,
                status=ConflictStatus.CEASEFIRE,
                intensity=100,
                exhaustion_a=0,
                exhaustion_b=0,
                ceasefire_run_turns=0,
            ),
        )
    )
    save = advance_n(save, 1)
    real_row = save.entries[1].report().foreign_affairs.progressions[0]
    assert real_row.opening_status is ConflictStatus.CEASEFIRE
    assert real_row.closing_status is ConflictStatus.ACTIVE, "sanity: deterministic breakdown"
    assert real_row.closing_intensity_bps >= MIN_ACTIVE_INTENSITY_BPS

    def mutate(state: GameState) -> GameState:
        conflict = state.world.conflicts[0]
        tampered = conflict.model_copy(update={"intensity_bps": 1})
        return state.model_copy(
            update={"world": state.world.model_copy(update={"conflicts": (tampered,)})}
        )

    tampered = _tamper_last_state(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 52)")


# --- cases 20-21: exact weight-499/500 boundary (group 52) ----------------------------------------


def test_case20_weight_499_dyad_forged_as_a_war_is_caught() -> None:
    """A weight-499 dyad (one below `MIN_OUTBREAK_WEIGHT_BPS`, 500) that genuinely never starts a
    war is forged into a fully self-consistent new-conflict outbreak + matching progression row.

    A wrinkle unique to this case: `ForeignConflictOutbreakReport`'s own self-validators tie
    `total_weight_bps`/`clamped_probability_bps`/the selection walk to the CANDIDATE ROW's own
    stored `tension_bps`/`grievance_bps` (`_each_candidate_weight_and_floor_match_the_formula`),
    not to the real dyad -- so a schema-valid report can never claim `occurred=True` while its
    only candidate honestly reports weight 499 (a real, unchanged floor of 0 forces probability
    to 0, and `occurred=True` can never satisfy `occurrence_draw < 0`). The candidate row's own
    `tension_bps`/`grievance_bps`/`raw_dyad_weight_bps`/`passed_pressure_floor` are therefore ALSO
    forged to a self-consistent fictional 500/500 (still schema-valid, since the row's own
    validator only checks internal consistency) -- while the REAL authored dyad in `world.dyads`
    stays genuinely 499/499, untouched. Fix-forward 7b's group-52 check recomputes the selected
    pair's weight from the REAL dyad, not the row's claim, and catches the disagreement."""
    weight = 499
    fake_weight = 500
    assert weight < MIN_OUTBREAK_WEIGHT_BPS
    assert fake_weight == MIN_OUTBREAK_WEIGHT_BPS
    save = _new_synthetic_save(dyads=(_dyad(*PAIR_A, tension=weight, grievance=weight),))
    save = advance_n(save, 1)
    real_report = save.entries[-1].report()
    outbreak = real_report.foreign_affairs.outbreak
    assert outbreak.candidates[0].raw_dyad_weight_bps == weight
    assert not outbreak.candidates[0].passed_pressure_floor
    assert not outbreak.occurred, "sanity: this dyad must not genuinely start a war"

    country_a, country_b = PAIR_A
    turn = outbreak.turn
    fake_conflict_id = f"{country_a}__{country_b}__t{turn}"
    fake_opening_intensity = initial_intensity_bps(tension_bps=fake_weight)
    fake_probability = outbreak_probability_bps(total_weight_bps=fake_weight)
    fake_gain = exhaustion_gain_bps(opening_intensity_bps=fake_opening_intensity)
    fake_exhaustion = clamp_bps(0 + fake_gain)
    fake_avg = average_exhaustion_bps(
        exhaustion_a_bps=fake_exhaustion, exhaustion_b_bps=fake_exhaustion
    )
    fake_raw_intensity = raw_closing_intensity_bps(
        opening_intensity_bps=fake_opening_intensity, closing_average_exhaustion_bps=fake_avg
    )
    fake_readiness = closing_readiness_bps(
        closing_average_exhaustion_bps=fake_avg, closing_position_bps_value=0
    )
    assert fake_readiness < 5_000, "sanity: gate must stay closed so termination_draw is None"
    fake_closing_intensity = apply_active_intensity_floor(
        raw_intensity_bps=fake_raw_intensity, closing_status=ConflictStatus.ACTIVE
    )
    fake_progression_row = ForeignConflictProgressionRow(
        conflict_id=fake_conflict_id,
        opened_turn=turn,
        resolved_turn=None,
        opening_status=ConflictStatus.ACTIVE,
        closing_status=ConflictStatus.ACTIVE,
        opening_war_capability_a_bps=5_000,
        opening_war_capability_b_bps=5_000,
        opening_intensity_bps=fake_opening_intensity,
        raw_closing_intensity_bps=fake_raw_intensity,
        closing_intensity_bps=fake_closing_intensity,
        minimum_active_intensity_bps=MIN_ACTIVE_INTENSITY_BPS,
        active_intensity_floor_applied=fake_raw_intensity < MIN_ACTIVE_INTENSITY_BPS,
        opening_position_bps=0,
        closing_position_bps=0,
        position_jitter_bps=0,
        opening_exhaustion_a_bps=0,
        opening_exhaustion_b_bps=0,
        closing_exhaustion_a_bps=fake_exhaustion,
        closing_exhaustion_b_bps=fake_exhaustion,
        closing_avg_exhaustion_bps=fake_avg,
        exhaustion_rate_bps=0,
        exhaustion_gain_bps=fake_gain,
        intensity_growth_bps=0,
        intensity_decay_bps=0,
        opening_readiness_bps=0,
        closing_readiness_bps=fake_readiness,
        decisiveness_penalty_bps=0,
        decisive_position_threshold_bps=6_000,
        ceasefire_threshold_bps=5_000,
        settlement_threshold_bps=7_500,
        ceasefire_intensity_decay_bps=0,
        ceasefire_recovery_bps=CEASEFIRE_RECOVERY_BPS,
        ceasefire_breakdown_bps=4_000,
        ceasefire_durability_turns=4,
        opening_ceasefire_run_turns=0,
        closing_ceasefire_run_turns=0,
        termination_draw=None,
    )

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        fake_candidate = fa.outbreak.candidates[0].model_copy(
            update={
                "tension_bps": fake_weight,
                "grievance_bps": fake_weight,
                "raw_dyad_weight_bps": fake_weight,
                "passed_pressure_floor": True,
            }
        )
        forged_outbreak = fa.outbreak.model_copy(
            update={
                "candidates": (fake_candidate,),
                "total_weight_bps": fake_weight,
                "clamped_probability_bps": fake_probability,
                "occurrence_draw": 0,
                "occurred": True,
                "selection_draw": 0,
                "selected_country_a": country_a,
                "selected_country_b": country_b,
                "conflict_id": fake_conflict_id,
                "opened_turn": turn,
                "initial_intensity_bps": fake_opening_intensity,
                "initial_position_bps": 0,
                "initial_exhaustion_a_bps": 0,
                "initial_exhaustion_b_bps": 0,
                "initial_readiness_bps": 0,
            }
        )
        return report.model_copy(
            update={
                "foreign_affairs": fa.model_copy(
                    update={
                        "outbreak": forged_outbreak,
                        "progressions": (*fa.progressions, fake_progression_row),
                    }
                )
            }
        )

    tampered = _tamper_last_report(save, mutate)
    _assert_green_chain_and_group(tampered, group_substring="(group 52)")


def test_case21_weight_500_dyad_omitted_from_candidacy_is_caught() -> None:
    """A weight-500 dyad (exactly at `MIN_OUTBREAK_WEIGHT_BPS`), eligible, non-excluded and with
    capacity available, is omitted from the reported `candidates` tuple entirely. Fix-forward
    7c's explicit group-52 candidate-omission check must catch it -- alongside group 47's own
    generic membership mismatch, not instead of it."""
    weight = 500
    assert weight == MIN_OUTBREAK_WEIGHT_BPS
    save = _new_synthetic_save(dyads=(_dyad(*PAIR_A, tension=weight, grievance=weight),))
    save = advance_n(save, 1)
    real_report = save.entries[-1].report()
    outbreak = real_report.foreign_affairs.outbreak
    assert outbreak.candidates[0].raw_dyad_weight_bps == weight
    assert outbreak.candidates[0].passed_pressure_floor

    def mutate(report):  # type: ignore[no-untyped-def]
        fa = report.foreign_affairs
        forged_outbreak = fa.outbreak.model_copy(
            update={"candidates": (), "total_weight_bps": 0, "clamped_probability_bps": 0}
        )
        return report.model_copy(
            update={"foreign_affairs": fa.model_copy(update={"outbreak": forged_outbreak})}
        )

    tampered = _tamper_last_report(save, mutate)
    problems = _assert_green_chain_and_group(tampered, group_substring="(group 52)")
    assert any("(group 47)" in p for p in problems), (
        "sanity: group 47's own generic membership check must still fire alongside group 52, "
        "not be replaced by it"
    )
