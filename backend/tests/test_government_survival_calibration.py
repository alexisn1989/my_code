"""Gate 3C1 calibration: real, `resolve_turn`-driven election figures for all three shipped
scenarios, pinned as literals -- never hand-derived. Every number below was produced by actually
resolving turns through the real engine (a small verification script, not part of the repository)
and transcribed here, exactly the discipline `test_full_political_memory_calibration.py`
established for Phase 3B2B: these are the real engine's own numbers, not numbers asserted and then
matched against.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.government_survival import MAX_POLLING_UNCERTAINTY_SWING_BPS
from app.simulation.history import advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import OutcomeBucket
from tests.conftest import SCENARIO_DIR


def _empty_decisions(current) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=current.turn, expected_state_version=current.state_version, decisions=()
    )


def _run(  # type: ignore[no-untyped-def]
    scenario: str, turns: int, *, seed: int | None = None, disable_dyads: bool = False
):
    state = load_scenario_file(SCENARIO_DIR / scenario)
    if seed is not None:
        state = state.model_copy(update={"seed": seed})
    if disable_dyads:
        dyads_disabled = tuple(
            dyad.model_copy(update={"eligible": False}) for dyad in state.world.dyads
        )
        state = state.model_copy(
            update={"world": state.world.model_copy(update={"dyads": dyads_disabled})}
        )
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(turns):
        current = save.current_state()
        save = advance_game(save, _empty_decisions(current))
    return save


class TestTinyValidTermLimitExit:
    """A 2-term limit x 16-turn election interval: the incumbent wins its first election (turn
    16), then hits the term limit at its second (turn 32) -- `TERM_LIMIT_EXIT`, not an electoral
    defeat, since it never loses a vote."""

    def test_turn_16_first_election_is_won_unaided(self) -> None:
        """External Wars Gate W1: `tiny_valid`'s eligible kessia/vetruska dyad (exposure 2,000)
        starts a war on this seed before turn 16, and the security-anxiety contribution
        (frozen plan sec.9.4/9.5) legitimately lowers legitimacy and therefore support -- both
        figures below are re-measured against the real engine post-W1, -29 bps from their
        pre-W1 values (5,568/5,449). `polling_uncertainty_bps` is untouched -- it is a pure RNG
        draw independent of legitimacy -- and the election OUTCOME (won, term-limit path) does
        not change."""
        save = _run("tiny_valid.yaml", 16)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.scheduled
        assert election.result == "won"
        assert election.baseline_support_bps == 5_539
        assert election.polling_uncertainty_bps == -119
        assert election.final_support_bps == 5_420
        assert election.required_support_bps == 5_000
        assert not election.liberalization_completed

        politics = save.current_state().world.countries["arken"].politics
        assert politics is not None
        assert politics.consecutive_terms_held == 2
        assert politics.next_election_turn == 32
        assert politics.terminal_outcome is None

    def test_turn_32_term_limit_exit_concludes_the_game(self) -> None:
        save = _run("tiny_valid.yaml", 32)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.scheduled
        assert election.result == "term_limit_exit"
        assert election.required_support_bps == 0
        assert election.polling_uncertainty_bps == 0, "no RNG swing is drawn on a term-limit exit"
        assert not election.eligible_to_stand
        assert election.parties == ()

        politics = save.current_state().world.countries["arken"].politics
        assert politics is not None
        assert politics.terminal_outcome is not None
        assert politics.terminal_outcome.bucket.value == "defeat"
        assert politics.terminal_outcome.removal_reason is not None
        assert politics.terminal_outcome.removal_reason.value == "term_limit_exit"
        assert politics.terminal_outcome.turn == 32

    def test_the_concluded_game_refuses_further_resolution(self) -> None:
        save = _run("tiny_valid.yaml", 32)
        current = save.current_state()
        try:
            advance_game(save, _empty_decisions(current))
            raise AssertionError("expected GameAlreadyConcludedError")
        except GameAlreadyConcludedError as exc:
            assert exc.bucket == "defeat"
            assert exc.reason == "term_limit_exit"
            assert exc.turn == 32


class TestDeficitDemoContestedElections:
    """`deficit_demo` wins its turn-20 election (a genuine contest -- baseline support opens
    below the required threshold, and a favorable polling swing carries it over), then loses its
    turn-40 election via `ELECTORAL_DEFEAT` when the swing goes the other way against the same
    baseline."""

    def test_turn_20_is_won_by_a_favorable_polling_swing_no_foreign_war_control(self) -> None:
        """External Wars Gate W1: `deficit_demo` authors an eligible dyad (exposure 2,000, frozen
        plan sec.9.6). With it live, the war's security-anxiety contribution (sec.9.4/9.5) grows
        turn over turn, so the baseline at turn 20 (4,683) and turn 40 (4,671) would no longer be
        the SAME figure -- breaking this class's own "same structural baseline, only the swing
        differs" claim. The dyad is disabled here so no war can ever start, restoring the exact
        pre-W1 structural-baseline-invariance conditions this class was written to prove."""
        save = _run("deficit_demo.yaml", 20, disable_dyads=True)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.result == "won"
        assert election.baseline_support_bps == 4_708
        assert election.baseline_support_bps < election.required_support_bps, (
            "the baseline alone is BELOW the threshold -- this win is genuinely carried by the "
            "polling swing, not a foregone conclusion"
        )
        assert election.polling_uncertainty_bps == 644
        assert election.final_support_bps == 5_352

        politics = save.current_state().world.countries["strapped"].politics
        assert politics is not None
        assert politics.consecutive_terms_held == 2
        assert politics.next_election_turn == 40
        assert politics.terminal_outcome is None

    def test_turn_40_is_lost_by_an_unfavorable_polling_swing_electoral_defeat_no_foreign_war_control(
        self,
    ) -> None:
        """External Wars Gate W1: see the war-free rationale on the turn-20 test above -- the
        dyad is disabled here for the same reason, preserving the SAME structural baseline as
        turn 20."""
        save = _run("deficit_demo.yaml", 40, disable_dyads=True)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.result == "lost"
        assert election.baseline_support_bps == 4_708, (
            "the SAME structural baseline as turn 20 -- nothing in the economy shifted the "
            "underlying support; only the polling swing differs"
        )
        assert election.polling_uncertainty_bps == -16
        assert election.final_support_bps == 4_692

        politics = save.current_state().world.countries["strapped"].politics
        assert politics is not None
        assert politics.terminal_outcome is not None
        assert politics.terminal_outcome.removal_reason is not None
        assert politics.terminal_outcome.removal_reason.value == "electoral_defeat"
        assert politics.terminal_outcome.turn == 40


class TestTinyValidFixtureSeedElectionResult:
    """The pinned, authored fixture seed (42, `tiny_valid.yaml`'s own `seed:` line) produces this
    exact turn-16 election result -- a single, fully specified literal, not folded into the
    seed-range sweep below (which deliberately does not single out any one seed as special)."""

    def test_fixture_seed_42_result(self) -> None:
        """External Wars Gate W1: same -29 bps security-anxiety shift as
        `TestTinyValidTermLimitExit::test_turn_16_first_election_is_won_unaided` above (same
        scenario, seed, and turn) -- the war is live and un-disabled here on purpose, since this
        class makes no cross-seed invariance claim for the dyad to break."""
        save = _run("tiny_valid.yaml", 16, seed=42)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.baseline_support_bps == 5_539
        assert election.polling_uncertainty_bps == -119
        assert election.final_support_bps == 5_420
        assert election.result == "won"


class TestTinyValidSeedZeroToNineteenSweepProvesTheElectionIsGenuinelyContested:
    """The declared, fixed seed range 0 through 19 inclusive (20 seeds), chosen as a range rather
    than hand-picked after observing results, against `tiny_valid`'s real turn-16 election: the
    baseline is seed-independent (a structural fact about seats/approval/legitimacy), but the
    polling swing genuinely varies by seed and can flip the result in either direction -- proving
    the election is a real contest, not a foregone conclusion dressed up with cosmetic
    randomness. Every figure below was produced by actually resolving each seed through the real
    engine (a small verification script, not part of the repository), the same discipline this
    whole file follows.

    External Wars Gate W1: `tiny_valid` authors an eligible dyad (exposure 2,000, frozen plan
    sec.9.6), and outbreak timing is itself seed-dependent -- on this seed range, some seeds see
    a war live by turn 16 and others don't, which would make baseline_support_bps genuinely vary
    by seed and break this class's central "baseline is seed-independent" claim. The dyad is
    disabled in every `_run` call below so no war can ever start on any seed, restoring the exact
    pre-W1 conditions this class was written to prove -- verified to reproduce every figure below
    byte-identically to the pre-W1 measurements."""

    _SEED_RANGE = range(20)

    _EXPECTED_BY_SEED = {
        0: (910, 6_478, "won"),
        1: (-459, 5_109, "won"),
        2: (713, 6_281, "won"),
        3: (-856, 4_712, "lost"),
        4: (-757, 4_811, "lost"),
        5: (-121, 5_447, "won"),
        6: (628, 6_196, "won"),
        7: (967, 6_535, "won"),
        8: (188, 5_756, "won"),
        9: (-343, 5_225, "won"),
        10: (-495, 5_073, "won"),
        11: (331, 5_899, "won"),
        12: (-829, 4_739, "lost"),
        13: (-877, 4_691, "lost"),
        14: (-955, 4_613, "lost"),
        15: (-698, 4_870, "lost"),
        16: (59, 5_627, "won"),
        17: (-743, 4_825, "lost"),
        18: (-98, 5_470, "won"),
        19: (-740, 4_828, "lost"),
    }

    def test_seed_0_through_19_sweep_matches_pinned_figures_no_foreign_war_control(self) -> None:
        assert set(self._EXPECTED_BY_SEED) == set(self._SEED_RANGE)
        for seed in self._SEED_RANGE:
            swing, final, result = self._EXPECTED_BY_SEED[seed]
            save = _run("tiny_valid.yaml", 16, seed=seed, disable_dyads=True)
            election = save.entries[-1].report().election
            assert election is not None
            assert election.baseline_support_bps == 5_568, seed
            assert election.polling_uncertainty_bps == swing, seed
            assert election.final_support_bps == final, seed
            assert election.result == result, seed

    def test_seed_0_through_19_won_and_lost_counts(self) -> None:
        """Exact WON/LOST counts over the declared range -- both outcomes are real and reachable,
        not a near-certainty in either direction."""
        results = [result for _, _, result in self._EXPECTED_BY_SEED.values()]
        assert results.count("won") == 12
        assert results.count("lost") == 8
        assert results.count("won") + results.count("lost") == 20

    def test_seed_0_through_19_baseline_is_invariant_no_foreign_war_control(self) -> None:
        """The baseline is a pure function of state (seats, relationships, population approval,
        legitimacy) at the moment of the election -- never of the seed -- so it must be identical
        across all 20 seeds despite the final result varying."""
        baselines = set()
        for seed in self._SEED_RANGE:
            save = _run("tiny_valid.yaml", 16, seed=seed, disable_dyads=True)
            election = save.entries[-1].report().election
            assert election is not None
            baselines.add(election.baseline_support_bps)
        assert baselines == {5_568}

    def test_seed_0_through_19_swing_stays_within_the_declared_bound(self) -> None:
        swings = [swing for swing, _, _ in self._EXPECTED_BY_SEED.values()]
        assert min(swings) >= -MAX_POLLING_UNCERTAINTY_SWING_BPS
        assert max(swings) <= MAX_POLLING_UNCERTAINTY_SWING_BPS
        # Confirmed genuinely wide, not merely inside the bound by luck.
        assert min(swings) == -955
        assert max(swings) == 967

    def test_the_same_seed_is_fully_deterministic(self) -> None:
        first = _run("tiny_valid.yaml", 16, seed=3)
        second = _run("tiny_valid.yaml", 16, seed=3)
        assert first.entries[-1].report().election == second.entries[-1].report().election


class TestDecreeStateNeverSchedulesAnElection:
    """`decree_state` authors no `national_election_interval_turns` -- Gate 3C1's election
    channel can therefore never fire for it, across any horizon, ABSENT a constitutional
    amendment. Gate 3C3 gives `decree_state` exactly one way past this: a
    `ConstitutionalAmendmentDecision` targeting `national_election_interval_turns` (see
    `test_liberalization_campaign.py`'s real 85/118/300 campaign, which does exactly that and
    schedules `next_election_turn == 11`). This test drives an unmodified `decree_state` with NO
    decisions at all, so the absence remains real and structural for that specific path."""

    def test_no_election_is_ever_scheduled_across_a_long_horizon(self) -> None:
        save = _run("decree_state.yaml", 60)
        for entry in save.entries[1:]:
            report = entry.report()
            assert report is not None
            election = report.election
            assert election is not None
            assert not election.scheduled
            assert election.result == "not_scheduled"
            assert election.next_election_turn is None

        politics = save.current_state().world.countries["valdrun"].politics
        assert politics is not None
        assert politics.next_election_turn is None
        assert politics.terminal_outcome is None
        assert politics.consecutive_terms_held == 1, (
            "unchanged from genesis -- nothing can increment it without a scheduled election"
        )


class TestAStartingDemocracyCannotWinLiberalizationVictory:
    """The mandate's own explicit stop condition: `tiny_valid` already ships competitive-elected
    at genesis (parliamentary/legislative_selection), so it never has a qualifying
    noncompetitive-to-competitive TRANSITION to record. As of Gate 3C3, a
    `ConstitutionalAmendmentDecision` is exactly what sets `pending_liberalization` -- this test
    drives `tiny_valid` with NO decisions at all, so the mechanism is simply never invoked, and
    reconciliation group 42 (`opening_pending.set_at_turn < closing_state.turn`) additionally
    makes the exploit structurally unreachable even for a tampered save that tries to fabricate a
    same-turn win as a liberalization victory (`test_history.py`, case 27). Asserted directly,
    turn by turn, through a real, natural win-then-term-limit-exit trajectory, rather than left to
    be merely implied by the absence of a submitted amendment."""

    def test_every_election_through_the_real_trajectory_has_no_pending_liberalization(
        self,
    ) -> None:
        save = _run("tiny_valid.yaml", 32)
        for entry in save.entries[1:]:
            report = entry.report()
            assert report is not None
            election = report.election
            assert election is not None
            assert not election.liberalization_completed
        for entry in save.entries:
            state = entry.state()
            politics = state.world.countries["arken"].politics
            assert politics is not None
            assert politics.pending_liberalization is None

        final_politics = save.current_state().world.countries["arken"].politics
        assert final_politics is not None
        assert final_politics.terminal_outcome is not None
        assert final_politics.terminal_outcome.bucket.value == "defeat", (
            "a starting democracy running out its term limit is a DEFEAT (term_limit_exit), "
            "never a VICTORY -- winning re-election is not the same thing as completing a "
            "liberalization that never began"
        )


# --- Phase 3C, Gate 3C2: coup/unrest/impeachment calibration ------------------------------------


_DECREE_STATE_SWEEP_SEEDS = range(20)
_DECREE_STATE_SWEEP_HORIZON = 100


@pytest.fixture(scope="module")
def decree_state_sweep() -> dict[str, object]:
    """Twenty 100-turn `decree_state` campaigns, resolved ONCE and reduced to raw integer facts.

    One aggregation shared by every test below, following
    `test_foreign_conflict_calibration.py`'s own `_measure` discipline: raw integers and sorted
    lists only, never a rounded percentage, and completed campaigns kept strictly separate from
    right-censored ones. Resolving the sweep per test instead would multiply a two-minute
    measurement by the number of assertions made about it.

    `disable_dyads=True` throughout. External Wars W1's security-anxiety channel can itself drive
    a coup on this seed range, and mixing the two would make it impossible to attribute a removal
    to government structure. War-driven termination is real and covered separately by
    `test_foreign_conflict_wiring.py`.
    """
    coup_attempts = 0
    unrest_attempts = 0
    unrest_successes = 0
    impeachment_eligible_turns = 0
    turns_at_risk = 0
    removals: dict[int, tuple[str, int]] = {}
    survivors: list[int] = []
    fatal_coup_rows: dict[int, tuple[int, int]] = {}

    for seed in _DECREE_STATE_SWEEP_SEEDS:
        save = _run_until_concluded(
            "decree_state.yaml", _DECREE_STATE_SWEEP_HORIZON, seed=seed, disable_dyads=True
        )
        for entry in save.entries[1:]:
            report = entry.report()
            assert report is not None and report.coup_unrest is not None
            coup_unrest = report.coup_unrest
            turns_at_risk += 1
            coup_attempts += bool(coup_unrest.coup.attempted)
            unrest_attempts += bool(coup_unrest.popular_unrest.attempted)
            unrest_successes += bool(coup_unrest.popular_unrest.succeeded)
            impeachment_eligible_turns += bool(coup_unrest.impeachment.eligible)

        politics = save.current_state().world.countries["valdrun"].politics
        assert politics is not None
        outcome = politics.terminal_outcome
        if outcome is None:
            survivors.append(seed)
            continue
        assert outcome.removal_reason is not None, seed
        removals[seed] = (outcome.removal_reason.value, outcome.turn)
        assert outcome.bucket is OutcomeBucket.DEFEAT, seed
        final = save.entries[-1].report()
        assert final is not None and final.coup_unrest is not None
        fatal_coup_rows[seed] = (
            final.coup_unrest.coup.structural_exposure_bps,
            final.coup_unrest.coup.structural_contribution_bps,
        )

    return {
        "coup_attempts": coup_attempts,
        "unrest_attempts": unrest_attempts,
        "unrest_successes": unrest_successes,
        "impeachment_eligible_turns": impeachment_eligible_turns,
        "turns_at_risk": turns_at_risk,
        "removals": removals,
        "survivors": sorted(survivors),
        "fatal_coup_rows": fatal_coup_rows,
    }


class TestDecreeStateSeedZeroToNineteenSweepProvesADictatorshipIsAtRiskAndSurvivable:
    """The SAME declared seed range 0-19 the election sweep above uses, now driving `decree_state`
    (the one scenario with no scheduled election at all) through a full 100 turns each.

    **This class's claim was deliberately changed by the government-structure feature**
    (`docs/adr/0019-government-structure-and-violent-removal-risk.md`). It previously asserted that
    no seed in this range ever terminates and that no channel ever succeeds -- true while the coup
    formula could not see that `decree_state` is a hereditary monarchy ruling by unlimited decree.
    That silence is exactly what the feature removes, so the old assertion is not weakened here; it
    is REPLACED by the stronger pair of facts the engine now actually produces.

    Every figure below was measured by resolving all twenty campaigns through the real engine.
    Over 1,812 resolved turns: 70 coup attempts, three of which succeeded; 40 popular-unrest
    attempts, none of which succeeded; and no eligible impeachment turn at all.

    Both halves are load-bearing:

    * **A dictatorship is genuinely in danger** -- three of twenty campaigns end in a coup, at
      turns 9, 23 and 80 rather than clustered at one point.
    * **A dictatorship remains playable** -- the other seventeen survive the entire horizon. A
      future re-tune of `COUP_STRUCTURAL_WEIGHT_BPS` that made most campaigns fall would be a
      balance regression, and this is where it surfaces.
    """

    def test_exactly_three_seeds_end_in_a_coup_at_the_measured_turns(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        assert decree_state_sweep["removals"] == {
            1: ("coup", 9),
            12: ("coup", 23),
            19: ("coup", 80),
        }

    def test_the_other_seventeen_seeds_survive_the_full_horizon(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        """The playability half. A structural weight that made a dictatorship unplayable would
        empty this list rather than pass quietly."""
        survivors = decree_state_sweep["survivors"]
        assert isinstance(survivors, list)
        assert len(survivors) == 17
        assert set(survivors).isdisjoint({1, 12, 19})

    def test_coups_are_attempted_far_more_often_than_they_succeed(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        """70 attempts, 3 removals. Structure decides how often the army MOVES, never whether it
        wins -- `coup_success_probability_bps` is untouched by this feature."""
        assert decree_state_sweep["coup_attempts"] == 70
        assert decree_state_sweep["turns_at_risk"] == 1_812

    def test_popular_unrest_attempts_happen_and_never_once_succeed(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        """The zero-conditional-success exception, end to end over 1,812 real turns.

        Structural exposure raises how often unrest is ATTEMPTED -- 40 attempts, from 15 bps of
        base risk plus 225 bps of structure -- and cannot raise how often it succeeds, because
        `unrest_success_probability_bps` is untouched and floors at 0 for `decree_state`'s
        organization and legitimacy. More attempts, still no removals: structure cannot manufacture
        an outcome the conditional formula rules out."""
        assert decree_state_sweep["unrest_attempts"] == 40
        assert decree_state_sweep["unrest_successes"] == 0

    def test_impeachment_is_never_even_eligible(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        """Unchanged by this feature, and asserted so: eligibility still reads
        `executive_selection`/`legislature`/`judicial_review` exactly as before, and a hereditary
        executive is ineligible however exposed the government is."""
        assert decree_state_sweep["impeachment_eligible_turns"] == 0

    def test_every_fatal_coup_was_scored_with_the_full_structural_exposure(
        self, decree_state_sweep: dict[str, object]
    ) -> None:
        """Attribution rather than correlation: each fatal turn is checked to have carried
        `decree_state`'s 7,500-bps exposure and the 300-bps coup contribution it implies, so the
        removals are demonstrably this feature's doing and not an unrelated drift in loyalty or
        legitimacy."""
        rows = decree_state_sweep["fatal_coup_rows"]
        assert isinstance(rows, dict)
        assert rows == {1: (7_500, 300), 12: (7_500, 300), 19: (7_500, 300)}


def _run_until_concluded(  # type: ignore[no-untyped-def]
    scenario: str, max_turns: int, *, seed: int, disable_dyads: bool = False
):
    """Like `_run`, but stops cleanly the moment the game concludes (the same "stop, don't crash"
    discipline `_cmd_resolve`'s own mid-batch-conclusion handling uses, R10) rather than assuming
    every seed survives to `max_turns` -- `tiny_valid`'s own turn-16 election can conclude the
    game immediately via ELECTORAL_DEFEAT on 8 of the declared 20 seeds (already established by
    `TestTinyValidSeedZeroToNineteenSweepProvesTheElectionIsGenuinelyContested` above), never
    reaching a term-limit-exit at all."""
    state = load_scenario_file(SCENARIO_DIR / scenario)
    state = state.model_copy(update={"seed": seed})
    if disable_dyads:
        dyads_disabled = tuple(
            dyad.model_copy(update={"eligible": False}) for dyad in state.world.dyads
        )
        state = state.model_copy(
            update={"world": state.world.model_copy(update={"dyads": dyads_disabled})}
        )
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(max_turns):
        current = save.current_state()
        try:
            save = advance_game(save, _empty_decisions(current))
        except GameAlreadyConcludedError:
            break
    return save


class TestTinyValidAndDeficitDemoSurviveToTheirRealScheduledConclusionUnchanged:
    """(R9/mandate requirement: "Gate 3C1 election behavior remaining byte-identical where
    survival does not terminate first") `tiny_valid` (WON turn 16 -> term-limit-exit at turn 32,
    or LOST turn 16 -> immediate electoral_defeat) and `deficit_demo` (its own real turn-20/40
    election horizon) both reach their Gate-3C1-established conclusion via the ELECTION channel
    alone, across the same declared seed 0-19 range -- neither scenario's coup/unrest/impeachment
    background risk (1bps/turn for both, per §11) is high enough to plausibly preempt these short
    horizons, and this is verified directly rather than assumed: every seed's real removal_reason
    is checked, not merely that SOME termination occurred."""

    _SEED_RANGE = range(20)

    def test_tiny_valid_seed_sweep_still_concludes_by_election_alone(self) -> None:
        for seed in self._SEED_RANGE:
            save = _run_until_concluded("tiny_valid.yaml", 32, seed=seed)
            politics = save.current_state().world.countries["arken"].politics
            assert politics is not None
            assert politics.terminal_outcome is not None, seed
            assert politics.terminal_outcome.removal_reason is not None
            assert politics.terminal_outcome.removal_reason.value in (
                "term_limit_exit",
                "electoral_defeat",
            ), (seed, politics.terminal_outcome.removal_reason)
            # Never a coup/unrest/impeachment reason -- confirms the added Gate 3C2 channels
            # stayed silent across this scenario's entire real horizon at every declared seed.
            assert politics.terminal_outcome.removal_reason.value not in (
                "coup",
                "forced_abdication",
                "assassination",
                "impeachment",
            ), seed

    def test_deficit_demo_seed_sweep_still_concludes_by_election_alone(self) -> None:
        for seed in self._SEED_RANGE:
            save = _run_until_concluded("deficit_demo.yaml", 40, seed=seed)
            politics = save.current_state().world.countries["strapped"].politics
            assert politics is not None
            assert politics.terminal_outcome is not None, seed
            assert politics.terminal_outcome.removal_reason is not None
            assert politics.terminal_outcome.removal_reason.value == "electoral_defeat", (
                seed,
                politics.terminal_outcome.removal_reason,
            )


class TestLowLoyaltyCoupSucceedsAgainstTheRealEngine:
    """§11's own deliberately-low-loyalty test case, driven to an actual coup SUCCESS (not merely
    the attempt-risk figure, already pinned as a pure-formula literal in
    `test_government_survival.py`): `tiny_valid`'s military edited to `loyalty_bps=2000` at
    genesis (everything else unchanged), then resolved turn by turn against the real engine at a
    declared seed until the coup succeeds -- seed 40, turn 5 (found by a declared, bounded search
    over the first 60 seeds x 32 turns each, the same "reachable, not cherry-picked" discipline
    the election sweep above uses). Confirms this is a real, checkable removal, not merely a risk
    number, and that the closing state faithfully records it.

    The government-structure feature moved the risk figure 623 -> 643 and nothing else about this
    case: seed 40 turn 5 is still the first success in the same bounded search, re-run after the
    change rather than assumed. `tiny_valid` is an accountable electoral government, so its
    structural charge is only 20 bps -- this campaign is lost to a disloyal army, not to its
    constitution."""

    def test_seed_40_turn_5_coup_succeeds_with_the_exact_computed_risk_figures(self) -> None:
        state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        player = state.world.countries[state.world.player_country_id]
        institutions = list(player.institutions)
        for index, institution_row in enumerate(institutions):
            if institution_row.id == "military":
                institutions[index] = institution_row.model_copy(update={"loyalty": 2_000})
        player.institutions = institutions
        state = state.model_copy(update={"seed": 40})
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

        for _ in range(5):
            current = save.current_state()
            save = advance_game(save, _empty_decisions(current))

        assert save.current_turn() == 5
        report = save.entries[-1].report()
        assert report is not None and report.coup_unrest is not None
        coup = report.coup_unrest.coup
        assert coup.attempt_risk_bps == 643
        # 585 of those bps are the disloyal army and only 20 are `tiny_valid`'s constitutional
        # form. An electoral democracy whose military has turned on it is in far more danger than
        # an untroubled dictatorship -- which is the "democracies remain susceptible under adverse
        # conditions" property, shown here on a real removal rather than argued.
        assert coup.loyalty_contribution_bps == 585
        assert coup.structural_exposure_bps == 500
        assert coup.structural_contribution_bps == 20
        assert coup.attempted is True
        assert coup.succeeded is True
        assert report.coup_unrest.removal_triggered is not None
        assert report.coup_unrest.removal_triggered.value == "coup"

        politics = save.current_state().world.countries["arken"].politics
        assert politics is not None
        assert politics.terminal_outcome is not None
        assert politics.terminal_outcome.bucket.value == "defeat"
        assert politics.terminal_outcome.removal_reason is not None
        assert politics.terminal_outcome.removal_reason.value == "coup"
        assert politics.terminal_outcome.turn == 5

        try:
            advance_game(save, _empty_decisions(save.current_state()))
        except GameAlreadyConcludedError:
            pass
        else:
            raise AssertionError("a concluded game must refuse any further resolution")
