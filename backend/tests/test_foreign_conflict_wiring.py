"""External Wars W1 commit 6: the resolver-dependent proofs `test_foreign_conflict.py` could not
make before phase wiring existed (see that file's own docstring on the split).

Two are explicitly mandated:

  * The behavioural half of the R5 isolation guarantee -- resolving a real turn twice, with every
    foreign profile's `war_capability_bps` at 0 and at 10,000, and asserting a byte-identical
    `CoupUnrestReport` (and, for the same reason, every other domestic report).
  * Existing stochastic-stream independence -- the eight pre-W1 RNG streams
    (`election`, `coup_attempt`, `coup_outcome`, `unrest_attempt`, `unrest_outcome`,
    `unrest_severity`, `impeachment_attempt`, `impeachment_outcome`) draw identically whether or
    not a foreign conflict is active, because `core.rng.derive_rng` namespaces every draw by
    `(seed, turn, stream)` and a new stream name cannot alter an existing one's derived seed.

The rest pin the turn-by-turn lifecycle claims specific to slots 7/8/10/15: outbreak in slot 7,
same-turn progression in slot 8, a quiet turn's thirteenth report is present and empty (never
`None` during live resolution), and slot 10 reads the POST-slot-8 conflict snapshot.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.core.rng import derive_rng
from app.simulation.decisions import DecisionSet
from app.simulation.foreign_conflict import ConflictStatus
from app.simulation.history import advance_game, new_game
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR

EXISTING_STREAMS = (
    "election",
    "coup_attempt",
    "coup_outcome",
    "unrest_attempt",
    "unrest_outcome",
    "unrest_severity",
    "impeachment_attempt",
    "impeachment_outcome",
)


def _with_all_capabilities(state: GameState, capability_bps: int) -> GameState:
    profiles = {
        profile_id: profile.model_copy(update={"war_capability_bps": capability_bps})
        for profile_id, profile in state.world.foreign_profiles.items()
    }
    return state.model_copy(
        update={"world": state.world.model_copy(update={"foreign_profiles": profiles})}
    )


def _empty_decisions(state: GameState) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )


# --- mandated: behavioural capability isolation --------------------------------


def test_foreign_capability_0_vs_10000_leaves_every_domestic_report_byte_identical() -> None:
    """The behavioural half of R5, deferred from commit 3 (`test_foreign_conflict.py`) to here,
    now that a resolver exists to run it against. `decree_state` is used because it authors a
    genuinely eligible dyad -- a war can start and progress -- so this is not a vacuous check on a
    scenario where nothing foreign-conflict-related ever happens."""
    base = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    low = _with_all_capabilities(base, 0)
    high = _with_all_capabilities(base, 10_000)

    save_low = new_game(low, save_format_version=SAVE_FORMAT_VERSION)
    save_high = new_game(high, save_format_version=SAVE_FORMAT_VERSION)

    for _ in range(30):
        current_low = save_low.current_state()
        current_high = save_high.current_state()
        save_low = advance_game(save_low, _empty_decisions(current_low))
        save_high = advance_game(save_high, _empty_decisions(current_high))

        report_low = save_low.entries[-1].report()
        report_high = save_high.entries[-1].report()
        assert report_low is not None
        assert report_high is not None

        assert report_low.coup_unrest == report_high.coup_unrest
        assert report_low.political == report_high.political
        assert report_low.legislative == report_high.legislative
        assert report_low.election == report_high.election
        assert report_low.constitutional_amendment == report_high.constitutional_amendment


# --- mandated: existing RNG streams are unaffected ------------------------------


def test_existing_rng_streams_draw_identically_regardless_of_foreign_conflict_state() -> None:
    """Direct proof at the `derive_rng` level, independent of whatever `resolve_turn` happens to
    consume on a given turn: every pre-W1 stream's derived sequence at a given (seed, turn) is a
    pure function of the stream NAME, structurally incapable of shifting when a new, differently
    named stream (`foreign_conflict_outbreak`, `foreign_conflict_progress:{cid}`,
    `foreign_conflict_termination:{cid}`) is introduced alongside it."""
    seed = 20260826
    for turn in range(20):
        for stream in EXISTING_STREAMS:
            before = tuple(derive_rng(seed, turn, stream).getrandbits(32) for _ in range(5))
            # Drawing from brand-new W1 streams in between must not perturb the above.
            derive_rng(seed, turn, "foreign_conflict_outbreak").getrandbits(32)
            derive_rng(seed, turn, "foreign_conflict_progress:kessia__vetruska__t0").getrandbits(32)
            derive_rng(seed, turn, "foreign_conflict_termination:kessia__vetruska__t0").getrandbits(
                32
            )
            after = tuple(derive_rng(seed, turn, stream).getrandbits(32) for _ in range(5))
            assert before == after, f"stream {stream!r} at turn {turn} was perturbed"


def test_real_resolution_produces_identical_domestic_reports_with_and_without_a_live_war() -> None:
    """End to end through a real `resolve_turn`, not just at the `derive_rng` level: a scenario
    with a live foreign war and the same scenario with its dyad made ineligible (so no war can
    ever start) draw every one of the eight pre-W1 RNG streams identically at every turn.

    This does NOT mean every domestic report stays byte-identical for the whole run -- it must
    not, or the security-anxiety channel (frozen plan sec.9.4/9.5, the entire point of W1) would
    be a no-op. Once a live conflict's security contribution first goes nonzero, legitimacy
    itself legitimately diverges between the two runs, and `coup_unrest`/`election` (both of
    which read legitimacy as a formula input) diverge downstream of it -- exactly the cascade
    this session diagnosed and the user approved re-pinning regression tests for elsewhere.
    `legislative` reads no legitimacy input at all (F13: seats/influence/discipline only) and so
    stays identical for the full run regardless of the war -- that is the part of this claim that
    is actually about stream independence, and it is asserted unconditionally below. Both
    legitimacy-dependent reports are instead asserted equal only up through the last turn before
    the war has any legitimacy effect, which is still a real, non-vacuous stream-independence
    proof for every turn where nothing foreign-conflict-related has happened yet."""
    base = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    with_war = base
    dyads_disabled = tuple(dyad.model_copy(update={"eligible": False}) for dyad in base.world.dyads)
    without_war = base.model_copy(
        update={"world": base.world.model_copy(update={"dyads": dyads_disabled})}
    )

    save_with = new_game(with_war, save_format_version=SAVE_FORMAT_VERSION)
    save_without = new_game(without_war, save_format_version=SAVE_FORMAT_VERSION)

    saw_a_war = False
    security_effect_started = False
    for _ in range(30):
        current_with = save_with.current_state()
        current_without = save_without.current_state()
        save_with = advance_game(save_with, _empty_decisions(current_with))
        save_without = advance_game(save_without, _empty_decisions(current_without))

        report_with = save_with.entries[-1].report()
        report_without = save_without.entries[-1].report()
        assert report_with is not None
        assert report_without is not None
        assert report_with.foreign_affairs is not None
        assert report_with.political is not None
        if report_with.foreign_affairs.outbreak.occurred:
            saw_a_war = True
        if report_with.political.security_contribution_bps != 0:
            security_effect_started = True

        assert report_with.legislative == report_without.legislative
        if not security_effect_started:
            assert report_with.coup_unrest == report_without.coup_unrest
            assert report_with.election == report_without.election

    assert saw_a_war, "sanity: the eligible-dyad run must actually produce a war within 30 turns"


# --- turn-by-turn lifecycle claims specific to slots 7/8/10/15 -----------------


def test_outbreak_occurs_in_slot_7_and_the_new_conflict_progresses_in_slot_8_same_turn() -> None:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

    for _ in range(30):
        current = save.current_state()
        save = advance_game(save, _empty_decisions(current))
        report = save.entries[-1].report()
        assert report is not None
        assert report.foreign_affairs is not None
        if report.foreign_affairs.outbreak.occurred:
            conflict_id = report.foreign_affairs.outbreak.conflict_id
            progressed_ids = {row.conflict_id for row in report.foreign_affairs.progressions}
            assert conflict_id in progressed_ids, (
                "a conflict opened this turn must also appear, progressed, in this SAME turn's "
                "progressions (frozen plan sec.7 rule 1)"
            )
            matching_row = next(
                row for row in report.foreign_affairs.progressions if row.conflict_id == conflict_id
            )
            assert matching_row.opened_turn == report.foreign_affairs.outbreak.turn
            live_conflict = next(
                c for c in save.current_state().world.conflicts if c.conflict_id == conflict_id
            )
            assert live_conflict.status in (ConflictStatus.ACTIVE, ConflictStatus.DECIDED)
            return
    raise AssertionError("no war started within 30 turns; cannot exercise this claim")


def test_a_quiet_turn_still_has_a_present_nonempty_but_empty_shaped_foreign_affairs_report() -> (
    None
):
    """Turn 0 of `tiny_valid` (weight far above the floor, but the occurrence draw at seed 7,
    turn 0 happens not to fire): `foreign_affairs` is present -- never `None` during live
    resolution -- with a real outbreak row (nonzero candidates) and an empty `progressions`
    tuple, since no conflict is yet live."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    report = resolve_turn(state, decisions).report
    assert report.foreign_affairs is not None
    assert len(report.foreign_affairs.outbreak.candidates) > 0
    if not report.foreign_affairs.outbreak.occurred:
        assert report.foreign_affairs.progressions == ()


def test_slot_10_security_anxiety_reads_the_post_slot_8_conflict_snapshot() -> None:
    """A conflict that TERMINATES in slot 8 (closing_status DECIDED/SETTLED, not ACTIVE) must
    contribute zero security anxiety this same turn -- proving slot 10 reads the CLOSING, not the
    OPENING, conflict status. Constructed by running decree_state (exposure 3,000, sec.9.6) until
    a conflict reaches DECIDED, then checking that turn's security_contribution_bps is 0 despite
    the conflict having been ACTIVE (and therefore anxiety-contributing) on every prior turn."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

    saw_nonzero_while_active = False
    for _ in range(30):
        current = save.current_state()
        save = advance_game(save, _empty_decisions(current))
        report = save.entries[-1].report()
        assert report is not None
        assert report.political is not None
        assert report.foreign_affairs is not None
        conflicts = save.current_state().world.conflicts
        if not conflicts:
            continue
        conflict = conflicts[0]
        if conflict.status is ConflictStatus.ACTIVE:
            if report.political.security_contribution_bps != 0:
                saw_nonzero_while_active = True
        elif conflict.status in (ConflictStatus.DECIDED, ConflictStatus.SETTLED):
            progression = next(
                (
                    row
                    for row in report.foreign_affairs.progressions
                    if row.conflict_id == conflict.conflict_id
                ),
                None,
            )
            if progression is not None and progression.closing_status is not ConflictStatus.ACTIVE:
                assert report.political.security_contribution_bps == 0, (
                    "a conflict that just left ACTIVE this turn must contribute zero anxiety -- "
                    "slot 10 must be reading the closing (post-slot-8) status"
                )
                assert saw_nonzero_while_active, (
                    "sanity: the conflict must have contributed nonzero anxiety on at least one "
                    "earlier ACTIVE turn, or this test proves nothing"
                )
                return
    raise AssertionError("no conflict reached a terminal state within 30 turns")
