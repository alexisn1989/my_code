"""Gate 3C1 calibration: real, `resolve_turn`-driven election figures for all three shipped
scenarios, pinned as literals -- never hand-derived. Every number below was produced by actually
resolving turns through the real engine (a small verification script, not part of the repository)
and transcribed here, exactly the discipline `test_full_political_memory_calibration.py`
established for Phase 3B2B: these are the real engine's own numbers, not numbers asserted and then
matched against.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError
from app.simulation.decisions import DecisionSet
from app.simulation.government_survival import MAX_POLLING_UNCERTAINTY_SWING_BPS
from app.simulation.history import advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import SCENARIO_DIR


def _empty_decisions(current) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=current.turn, expected_state_version=current.state_version, decisions=()
    )


def _run(scenario: str, turns: int, *, seed: int | None = None):  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / scenario)
    if seed is not None:
        state = state.model_copy(update={"seed": seed})
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
        save = _run("tiny_valid.yaml", 16)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.scheduled
        assert election.result == "won"
        assert election.baseline_support_bps == 5_568
        assert election.polling_uncertainty_bps == -119
        assert election.final_support_bps == 5_449
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

    def test_turn_20_is_won_by_a_favorable_polling_swing(self) -> None:
        save = _run("deficit_demo.yaml", 20)
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

    def test_turn_40_is_lost_by_an_unfavorable_polling_swing_electoral_defeat(self) -> None:
        save = _run("deficit_demo.yaml", 40)
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
        save = _run("tiny_valid.yaml", 16, seed=42)
        election = save.entries[-1].report().election
        assert election is not None
        assert election.baseline_support_bps == 5_568
        assert election.polling_uncertainty_bps == -119
        assert election.final_support_bps == 5_449
        assert election.result == "won"


class TestTinyValidSeedZeroToNineteenSweepProvesTheElectionIsGenuinelyContested:
    """The declared, fixed seed range 0 through 19 inclusive (20 seeds), chosen as a range rather
    than hand-picked after observing results, against `tiny_valid`'s real turn-16 election: the
    baseline is seed-independent (a structural fact about seats/approval/legitimacy), but the
    polling swing genuinely varies by seed and can flip the result in either direction -- proving
    the election is a real contest, not a foregone conclusion dressed up with cosmetic
    randomness. Every figure below was produced by actually resolving each seed through the real
    engine (a small verification script, not part of the repository), the same discipline this
    whole file follows."""

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

    def test_seed_0_through_19_sweep_matches_pinned_figures(self) -> None:
        assert set(self._EXPECTED_BY_SEED) == set(self._SEED_RANGE)
        for seed in self._SEED_RANGE:
            swing, final, result = self._EXPECTED_BY_SEED[seed]
            save = _run("tiny_valid.yaml", 16, seed=seed)
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

    def test_seed_0_through_19_baseline_is_invariant(self) -> None:
        """The baseline is a pure function of state (seats, relationships, population approval,
        legitimacy) at the moment of the election -- never of the seed -- so it must be identical
        across all 20 seeds despite the final result varying."""
        baselines = set()
        for seed in self._SEED_RANGE:
            save = _run("tiny_valid.yaml", 16, seed=seed)
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
    channel can therefore never fire for it, across any horizon, and the scenario can never
    conclude via this mechanic (a real, structural absence, not an oversight)."""

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
    noncompetitive-to-competitive TRANSITION to record. Gate 3C1 has no constitutional-amendment
    mechanism at all yet (`pending_liberalization` is set only by a `ConstitutionalAmendmentDecision`,
    Gate 3C3), so this holds structurally and trivially in this gate -- but it is asserted
    directly, turn by turn through a real, natural win-then-term-limit-exit trajectory, rather
    than left to be merely implied by the absence of the mechanism."""

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


class TestDecreeStateSeedZeroToNineteenSweepProvesStabilityUnderAddedRisk:
    """The SAME declared seed range 0-19 the election sweep above uses, now driving `decree_state`
    (the one scenario with no scheduled election at all -- §11's own choice of which scenario can
    host a genuine, unmodified 100-turn nonterminal run) through a full 100 turns each, with the
    coup/unrest/impeachment channels now live for the first time. Every seed was actually run
    through the real engine (a small verification script, not part of the repository): none
    terminate early, confirming Gate 3C2's added background risk does not break the non-
    termination property Gate 3C1 established -- re-verified, not merely assumed unchanged."""

    _SEED_RANGE = range(20)

    def test_no_seed_in_the_declared_range_terminates_within_100_turns(self) -> None:
        for seed in self._SEED_RANGE:
            save = _run("decree_state.yaml", 100, seed=seed)
            politics = save.current_state().world.countries["valdrun"].politics
            assert politics is not None
            assert politics.terminal_outcome is None, seed
            assert save.current_turn() == 100, seed

    def test_no_channel_ever_succeeds_across_any_seed_in_the_declared_range(self) -> None:
        """`decree_state`'s calibrated background risk (coup 52bps, unrest 15bps attempt;
        impeachment ineligible at genesis, hereditary selection) genuinely produces occasional
        low-probability ATTEMPTS over a 100-turn x 20-seed sweep (2,000 independent draws each on
        the coup/unrest RNG streams; impeachment is skipped entirely, ineligible) -- an attempt is
        expected background noise at these odds, not itself a finding. What must never happen is
        a SUCCESS, since that would silently terminate the game this sweep is asserting stays
        alive for the full 100 turns."""
        for seed in self._SEED_RANGE:
            save = _run("decree_state.yaml", 100, seed=seed)
            for entry in save.entries[1:]:
                report = entry.report()
                assert report is not None and report.coup_unrest is not None
                coup_unrest = report.coup_unrest
                assert not coup_unrest.coup.succeeded, (seed, entry.turn)
                assert not coup_unrest.popular_unrest.succeeded, (seed, entry.turn)
                assert not coup_unrest.impeachment.eligible, (seed, entry.turn)


def _run_until_concluded(scenario: str, max_turns: int, *, seed: int):  # type: ignore[no-untyped-def]
    """Like `_run`, but stops cleanly the moment the game concludes (the same "stop, don't crash"
    discipline `_cmd_resolve`'s own mid-batch-conclusion handling uses, R10) rather than assuming
    every seed survives to `max_turns` -- `tiny_valid`'s own turn-16 election can conclude the
    game immediately via ELECTORAL_DEFEAT on 8 of the declared 20 seeds (already established by
    `TestTinyValidSeedZeroToNineteenSweepProvesTheElectionIsGenuinelyContested` above), never
    reaching a term-limit-exit at all."""
    state = load_scenario_file(SCENARIO_DIR / scenario)
    state = state.model_copy(update={"seed": seed})
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
    number, and that the closing state faithfully records it."""

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
        assert coup.attempt_risk_bps == 623
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
