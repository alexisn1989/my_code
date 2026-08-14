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
        assert election.baseline_support_bps == 5_544
        assert election.polling_uncertainty_bps == -119
        assert election.final_support_bps == 5_425
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


class TestDeficitDemoSeedSweepProvesTheElectionIsGenuinelyContested:
    """A fixed-seed range sweep against the SAME `tiny_valid` turn-16 election: the baseline is
    seed-independent (a structural fact about seats/approval/legitimacy), but the polling swing
    genuinely varies by seed and can flip the result -- proving the election is a real contest,
    not a foregone conclusion dressed up with cosmetic randomness."""

    _EXPECTED = {
        42: (5_544, -119, 5_425, "won"),
        1: (5_544, -459, 5_085, "won"),
        2: (5_544, 713, 6_257, "won"),
        3: (5_544, -856, 4_688, "lost"),
        77: (5_544, -374, 5_170, "won"),
    }

    def test_seed_sweep_matches_pinned_figures_and_seed_3_flips_the_outcome(self) -> None:
        for seed, (baseline, swing, final, result) in self._EXPECTED.items():
            save = _run("tiny_valid.yaml", 16, seed=seed)
            election = save.entries[-1].report().election
            assert election is not None
            assert election.baseline_support_bps == baseline, seed
            assert election.polling_uncertainty_bps == swing, seed
            assert election.final_support_bps == final, seed
            assert election.result == result, seed

        assert self._EXPECTED[3][3] == "lost", (
            "seed 3 loses the SAME election every other pinned seed wins, purely from polling "
            "variance around an identical baseline -- the required proof that this is a genuine "
            "contest, not a scripted outcome"
        )

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
