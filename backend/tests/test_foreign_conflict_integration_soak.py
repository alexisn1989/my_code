"""External Wars W1 fix-forward 6a: integrated soak coverage with a live foreign war.

Commit 6's checkpoint audit found that of `test_soak.py`'s five soaks, the two touched to
accommodate W1 became war-free controls (their scenario's dyad disabled, per the checkpoint's
own approved pattern), and the other three were never touched -- but *none* of the five asserts
anything W1-specific. The live resolver was therefore un-soaked: nothing proved a war actually
occurs, stays valid, or reconciles into legitimacy, when W1 runs against real shipped content
for a full campaign.

This file closes that gap. It drives `decree_state.yaml` and `tiny_valid.yaml`, UNMODIFIED
(their real authored eligible dyad live, their own authored seed), for up to 100 turns, and
proves exactly the properties named in the checkpoint:

 1. Non-vacuity -- a war genuinely occurs, and the security-anxiety channel is genuinely
    exercised (not merely present-but-always-zero).
 2. The 13th report is present every turn (already self-validating by construction -- every
    `ForeignAffairsReport`/`ForeignConflictProgressionRow` field validator in `report.py` runs
    on every `TurnReport` the real resolver builds).
 3. Conflict concurrency never exceeds `MAX_CONCURRENT_CONFLICTS` (fix-forward 6b), and in these
    two single-dyad scenarios never exceeds the tighter authored-dyad-count bound either (each
    dyad can host at most one live conflict at a time -- `state.py`'s own `ForeignConflictState.
    conflict_id` docstring: "a pair cannot re-fight while an existing conflict between them is
    still ACTIVE or CEASEFIRE"). An earlier version of this file claimed no such constant
    existed; that was a defect in the 6a audit, corrected in 6b, not a plan gap.
 4. Every conflict's terminal-status/`resolved_turn` legality holds turn by turn (already a
    Pydantic construction-time invariant; re-asserted directly here against the report).
 5. `validate_history` stays clean every turn, and the campaign either survives the full
    horizon or stops with a well-formed, attributable `terminal_outcome`.
 6. Determinism under independent replay.
 7. Save/reload introduces no reroll.
 8. Legitimacy movement is attributable: a nonzero `security_contribution_bps` never appears on
    a turn with no ACTIVE conflict.

The full five-seed calibration matrix (frozen plan sec.21) stays deferred to the calibration
commit, as the checkpoint allows; this file uses each scenario's own authored seed only.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import (
    MAX_CONCURRENT_CONFLICTS,
    TERMINAL_STATUSES,
    ConflictStatus,
)
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json, load_save_json
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR

TURNS = 100

# Each shipped scenario authors exactly one dyad today (verified directly against the YAML
# content, not assumed), which is a TIGHTER bound than MAX_CONCURRENT_CONFLICTS (fix-forward 6b)
# since a single dyad can host at most one live conflict at a time. If a future scenario authors
# more, this constant is the one place to update; it may never legitimately exceed
# MAX_CONCURRENT_CONFLICTS.
_AUTHORED_DYAD_COUNT = 1
assert _AUTHORED_DYAD_COUNT <= MAX_CONCURRENT_CONFLICTS


def _empty_decisions(state: GameState) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )


def _run(scenario: str, turns: int) -> GameSave:
    """Drives `scenario` UNMODIFIED (real authored dyad, real seed) for up to `turns` turns,
    stopping cleanly on `GameAlreadyConcludedError` -- the same "stop, don't crash" discipline
    `_cmd_resolve`'s own mid-batch-conclusion handling uses (R10)."""
    state = load_scenario_file(SCENARIO_DIR / scenario)
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(turns):
        current = save.current_state()
        try:
            save = advance_game(save, _empty_decisions(current))
        except GameAlreadyConcludedError:
            break
    return save


def _assert_integrated_war_invariants(save: GameSave) -> None:
    assert validate_history(save) == []

    saw_a_war = False
    saw_nonzero_security_contribution = False

    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.foreign_affairs is not None
        assert report.political is not None

        if report.foreign_affairs.outbreak.occurred:
            saw_a_war = True
        if report.political.security_contribution_bps != 0:
            saw_nonzero_security_contribution = True

        # Item 3: concurrency never exceeds MAX_CONCURRENT_CONFLICTS (6b's global cap), and in
        # these single-dyad scenarios never exceeds the tighter authored-dyad-count bound either.
        live_conflicts = [
            c
            for c in entry.state().world.conflicts
            if c.status in (ConflictStatus.ACTIVE, ConflictStatus.CEASEFIRE)
        ]
        assert len(live_conflicts) <= MAX_CONCURRENT_CONFLICTS
        assert len(live_conflicts) <= _AUTHORED_DYAD_COUNT

        # Item 4: terminal-status/resolved_turn legality, re-checked directly against the
        # report's own progression rows for this turn (construction already enforces this on
        # `world.conflicts`; this checks the REPORT independently).
        for row in report.foreign_affairs.progressions:
            is_terminal = row.closing_status in TERMINAL_STATUSES
            assert is_terminal == (row.resolved_turn is not None), (
                f"conflict {row.conflict_id!r} at turn {entry.turn}: closing_status="
                f"{row.closing_status!r} but resolved_turn={row.resolved_turn!r}"
            )

        # Item 8: a nonzero security contribution must trace to an ACTIVE conflict THIS turn.
        active_this_turn = [
            row
            for row in report.foreign_affairs.progressions
            if row.closing_status is ConflictStatus.ACTIVE
        ]
        if not active_this_turn:
            assert report.political.security_contribution_bps == 0, (
                f"turn {entry.turn}: nonzero security_contribution_bps with no ACTIVE conflict "
                "-- legitimacy moved without an attributable cause"
            )

    # Item 1: non-vacuity -- this soak must actually exercise what it claims to.
    assert saw_a_war, f"sanity: no war started within {TURNS} turns; this soak proves nothing"
    assert saw_nonzero_security_contribution, (
        "sanity: the war never reached ACTIVE with nonzero exposure; the security-anxiety "
        "channel this soak exists to exercise was never exercised"
    )

    # Item 5: survive the full horizon, or stop with an attributable, well-formed conclusion --
    # never a silent truncation and never an unhandled crash (both already ruled out by `_run`
    # completing at all, but the shape of the stopping point is checked explicitly here too).
    player_id = save.current_state().world.player_country_id
    politics = save.current_state().world.countries[player_id].politics
    assert politics is not None
    if save.current_turn() < TURNS:
        assert politics.terminal_outcome is not None
        reason = (
            politics.terminal_outcome.removal_reason or politics.terminal_outcome.victory_reason
        )
        assert reason is not None
    else:
        assert save.current_turn() == TURNS


def test_decree_state_full_campaign_with_its_real_authored_war_stays_valid_and_attributable() -> (
    None
):
    _assert_integrated_war_invariants(_run("decree_state.yaml", TURNS))


def test_tiny_valid_full_campaign_with_its_real_authored_war_stays_valid_and_attributable() -> None:
    _assert_integrated_war_invariants(_run("tiny_valid.yaml", TURNS))


def test_decree_state_full_campaign_is_deterministic_under_independent_replay() -> None:
    """Item 6: two independent runs from the same scenario/seed/empty-decisions must produce a
    byte-identical complete history -- entry_hash, decisions_json and report_json included --
    exactly `test_determinism.py`'s own established pattern
    (`test_two_independent_games_produce_byte_identical_complete_histories`), applied here to a
    run where W1's new RNG streams and legitimacy cascade are actually live."""
    assert dump_save_json(_run("decree_state.yaml", TURNS)) == dump_save_json(
        _run("decree_state.yaml", TURNS)
    )


def test_decree_state_mid_campaign_save_reload_does_not_reroll() -> None:
    """Item 7: serialize mid-run, reload, and resolve the rest -- must be byte-identical to an
    uninterrupted run over the same horizon, regardless of whether the campaign has already
    concluded by the midpoint (the concluded-state branch is exercised for free on whichever
    seed/turn the real engine actually concludes at, rather than being separately constructed).
    Reconciliation's own stream-redraw proof (group 48) is deferred to commit 7; this is the
    narrower, already-available guarantee that a save/reload boundary itself introduces no draw."""
    uninterrupted = _run("decree_state.yaml", TURNS)

    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    midpoint = TURNS // 2
    for _ in range(midpoint):
        current = save.current_state()
        try:
            save = advance_game(save, _empty_decisions(current))
        except GameAlreadyConcludedError:
            break

    reloaded = load_save_json(dump_save_json(save))
    for _ in range(midpoint, TURNS):
        current = reloaded.current_state()
        try:
            reloaded = advance_game(reloaded, _empty_decisions(current))
        except GameAlreadyConcludedError:
            break

    assert dump_save_json(reloaded) == dump_save_json(uninterrupted)
