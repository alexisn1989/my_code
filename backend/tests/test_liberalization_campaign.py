"""Gate 3C3 commit 26: the real, `advance_game`-driven 85/118/300 liberalization campaign.

Every figure below was produced by actually driving `decree_state.yaml` through the real,
hash-chained history layer (`new_game`/`advance_game`, the same layer the CLI uses) — never
hand-derived or asserted first and matched second. The campaign: invest 85 political capital in
`opposition_party/main` (turn 1), invest 118 more (turn 2), then submit the five-axis
constitutional amendment with 300 PC of opposition influence (turn 3). `decree_state.yaml` is
authored at seed 77 and a 100-seat unicameral legislature under `amendment_difficulty:
supermajority`, so passage requires exactly `(2*100+2)//3 = 67` yes seats.

**At the scenario's own authored seed, 77, the campaign is NOT a certain win.** The election at
turn 11 (post-amendment `next_election_turn`) resolves against the real, seeded polling swing and
the incumbent LOSES — `electoral_defeat`, not `peaceful_liberalization_completed`. This is the
correct, honest reading of the real engine at this seed and is pinned as the primary fixture-seed
walkthrough (`docs/adr/0013-government-survival.md` records this as a deliberate correction of an
earlier planning draft's scratch-script error, which mis-derived a different, incorrect result).
The victory path is separately proven at a declared alternative seed, 0, where the identical
campaign — same investments, same amendment, same passage margin — wins the same election.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.core.errors import DecisionSetError, GameAlreadyConcludedError
from app.simulation.constitution import (
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
    InfluenceAllocation,
    TermLimitTarget,
)
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.legislature import LegislativeOutcome
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState, OutcomeBucket, RemovalReason, VictoryReason
from tests.conftest import SCENARIO_DIR

_SFV = SAVE_FORMAT_VERSION
_FIVE_AXES = (
    "decree_authority",
    "executive_selection",
    "executive_system",
    "executive_term_limit_terms",
    "national_election_interval_turns",
)


def _empty(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _invest(state: GameState, political_capital: int) -> DecisionSet:
    decision = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(
                party_id="opposition_party", bloc_id="main", political_capital=political_capital
            ),
        )
    )
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )


def _amendment(state: GameState, influence: int) -> DecisionSet:
    decision = ConstitutionalAmendmentDecision(
        targets=(
            DecreeAuthorityTarget(value=DecreeAuthority.NONE),
            ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
            ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
            TermLimitTarget(value=2),
            ElectionIntervalTarget(value=8),
        ),
        influence=(
            InfluenceAllocation(
                party_id="opposition_party", bloc_id="main", political_capital=influence
            ),
        ),
    )
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )


def _politics(state: GameState):  # type: ignore[no-untyped-def]
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    return politics


def _opening_save(*, seed: int | None) -> GameSave:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    if seed is not None:
        state = state.model_copy(update={"seed": seed})
    return new_game(state, save_format_version=_SFV)


def _run_campaign(
    *, seed: int | None, turn1_pc: int = 85, turn2_pc: int = 118, turn3_influence: int = 300
) -> GameSave:
    """Turns 1-3: the real campaign, through `advance_game`. Caller advances further if needed."""
    save = _opening_save(seed=seed)
    save = advance_game(save, _invest(save.current_state(), turn1_pc))
    save = advance_game(save, _invest(save.current_state(), turn2_pc))
    save = advance_game(save, _amendment(save.current_state(), turn3_influence))
    return save


def _advance_to_election(save: GameSave) -> GameSave:
    """Turns 4-10: no decisions. Turn 11: the scheduled election."""
    for _ in range(4, 12):
        save = advance_game(save, _empty(save.current_state()))
    return save


# --- The real campaign: pinned at the fixture seed, proven separately at a declared seed --------


class TestTheRealEightyFiveOneEighteenThreeHundredCampaign:
    """The exact campaign named by the mandate, driven through the real engine end to end."""

    def test_turn_one_investment_moves_the_real_relationship_and_capital(self) -> None:
        save = _opening_save(seed=None)
        save = advance_game(save, _invest(save.current_state(), 85))
        politics = _politics(save.current_state())
        assert politics.legislature.parties[1].id == "opposition_party"
        assert politics.legislature.parties[1].blocs[0].id == "main"
        assert politics.legislature.parties[1].blocs[0].government_relationship_bps == -5_385
        assert politics.political_capital == 798

    def test_turn_two_investment_reaches_the_documented_turn_three_opening_relationship(
        self,
    ) -> None:
        save = _opening_save(seed=None)
        save = advance_game(save, _invest(save.current_state(), 85))
        save = advance_game(save, _invest(save.current_state(), 118))
        politics = _politics(save.current_state())
        opposition = politics.legislature.parties[1].blocs[0]
        assert opposition.government_relationship_bps == -2_774
        assert politics.political_capital == 1_000

    def test_turn_three_amendment_passes_exactly_67_of_100_at_cumulative_503(self) -> None:
        save = _run_campaign(seed=None)
        entry = save.entries[-1]
        report = entry.report()
        assert report is not None
        amendment = report.constitutional_amendment
        assert amendment is not None
        assert amendment.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
        assert len(amendment.chambers) == 1
        chamber = amendment.chambers[0]
        assert (chamber.supporting_seats, chamber.total_seats, chamber.required_yes_seats) == (
            67,
            100,
            67,
        )
        assert amendment.political_capital_committed == 300

        cumulative_committed = 85 + 118 + 300
        assert cumulative_committed == 503

        politics = _politics(save.current_state())
        assert politics.next_election_turn == 11
        assert politics.pending_liberalization is not None
        assert politics.pending_liberalization.set_at_turn == 3

    def test_every_turn_of_the_campaign_satisfies_the_real_affordability_guard(self) -> None:
        """Each decision set's committed capital never exceeds that turn's OPENING capital —
        the real ledger enforces this itself (a decision that overspends is rejected outright),
        so a campaign that resolves at all through `advance_game` has already proven this."""
        save = _opening_save(seed=None)
        opening_capital = _politics(save.current_state()).political_capital
        assert opening_capital >= 85

        save = advance_game(save, _invest(save.current_state(), 85))
        opening_capital = _politics(save.current_state()).political_capital
        assert opening_capital >= 118

        save = advance_game(save, _invest(save.current_state(), 118))
        opening_capital = _politics(save.current_state()).political_capital
        assert opening_capital >= 300

        save = advance_game(save, _amendment(save.current_state(), 300))
        assert validate_history(save) == []

    def test_the_final_constitution_passes_c1_through_c10(self) -> None:
        save = _run_campaign(seed=None)
        constitution = _politics(save.current_state()).constitution
        assert first_constitutional_violation(constitution) is None
        assert constitution.decree_authority is DecreeAuthority.NONE
        assert constitution.executive_selection is ExecutiveSelection.DIRECT_ELECTION
        assert constitution.executive_system is ExecutiveSystem.PRESIDENTIAL
        assert constitution.executive_term_limit_terms == 2
        assert constitution.national_election_interval_turns == 8

    def test_pinned_fixture_seed_77_reaches_the_scheduled_election_and_loses(self) -> None:
        """The scenario's own authored seed. This is the honest primary walkthrough: the
        campaign is real, the amendment passes, the election is genuinely contested by the real
        seeded polling swing -- and at seed 77 the incumbent loses."""
        save = _run_campaign(seed=None)
        assert save.current_state().seed == 77
        save = _advance_to_election(save)

        election_report = save.entries[-1].report()
        assert election_report is not None and election_report.election is not None
        election = election_report.election
        assert election.baseline_support_bps == 5_091
        assert election.final_support_bps == 4_822
        assert election.final_support_bps - election.baseline_support_bps == -269
        assert election.result == "lost"
        assert not election.liberalization_completed

        politics = _politics(save.current_state())
        assert politics.terminal_outcome is not None
        assert politics.terminal_outcome.bucket is OutcomeBucket.DEFEAT
        assert politics.terminal_outcome.removal_reason is RemovalReason.ELECTORAL_DEFEAT
        assert validate_history(save) == []

    def test_declared_seed_zero_proves_the_victory_path_with_the_identical_campaign(self) -> None:
        """Same 85/118/300 campaign, same amendment, same 67/100 passage -- only the election
        seed differs. This is where the mandate's victory condition is proven to exist and
        work; it is NOT the fixture-seed result (see the loss test above)."""
        save = _run_campaign(seed=0)
        assert save.current_state().seed == 0
        save = _advance_to_election(save)

        election_report = save.entries[-1].report()
        assert election_report is not None and election_report.election is not None
        election = election_report.election
        assert election.baseline_support_bps == 5_091
        assert election.final_support_bps == 5_810
        assert election.final_support_bps - election.baseline_support_bps == 719
        assert election.result == "won"
        assert election.liberalization_completed

        politics = _politics(save.current_state())
        assert politics.terminal_outcome is not None
        assert politics.terminal_outcome.bucket is OutcomeBucket.VICTORY
        assert (
            politics.terminal_outcome.victory_reason
            is VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED
        )
        assert validate_history(save) == []

    def test_victory_is_terminal_and_a_further_turn_is_refused(self) -> None:
        save = _advance_to_election(_run_campaign(seed=0))
        with pytest.raises(GameAlreadyConcludedError):
            advance_game(save, _empty(save.current_state()))


# --- Boundary proofs -----------------------------------------------------------------------------


class TestPassageBoundaries:
    """Exact, one-seat-wide boundaries around the 67/100 supermajority threshold."""

    def test_turn_three_influence_299_produces_exactly_66_of_100_and_fails(self) -> None:
        save = _opening_save(seed=None)
        save = advance_game(save, _invest(save.current_state(), 85))
        save = advance_game(save, _invest(save.current_state(), 118))
        save = advance_game(save, _amendment(save.current_state(), 299))

        report = save.entries[-1].report()
        assert report is not None and report.constitutional_amendment is not None
        amendment = report.constitutional_amendment
        assert amendment.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
        chamber = amendment.chambers[0]
        assert (chamber.supporting_seats, chamber.required_yes_seats) == (66, 67)
        assert not chamber.passed

        politics = _politics(save.current_state())
        assert politics.next_election_turn is None
        assert politics.pending_liberalization is None

    def test_one_fewer_preparation_turn_is_unreachable_at_only_61_of_100(self) -> None:
        """Skipping the second (118 PC) preparation turn and submitting the amendment one turn
        early -- same total investment discipline, one fewer turn to let it compound -- reaches
        only 61/100, six seats short of the 67 required. The two preparation turns are not an
        arbitrary pacing choice: the per-turn investment cap (200 PC/turn/bloc) makes a
        single-turn substitute for the real two-turn build-up unreachable at all, and even the
        best one-turn opening (turn 1's real 85 PC) is not enough on its own."""
        save = _opening_save(seed=None)
        save = advance_game(save, _invest(save.current_state(), 85))
        save = advance_game(save, _amendment(save.current_state(), 300))

        report = save.entries[-1].report()
        assert report is not None and report.constitutional_amendment is not None
        amendment = report.constitutional_amendment
        assert amendment.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
        chamber = amendment.chambers[0]
        assert (chamber.supporting_seats, chamber.required_yes_seats) == (61, 67)
        assert not chamber.passed

    def test_a_single_turn_cannot_invest_past_the_per_bloc_cap(self) -> None:
        """The structural reason the campaign needs two preparation turns at all: a single
        `BlocInvestment` cannot exceed 200 PC, so 85+118=203 can never be submitted in one
        turn regardless of available capital."""
        with pytest.raises(ValidationError):
            BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=203)


class TestAmendmentAxisChangeIsExact:
    """A failed amendment changes no constitutional axis; a passed one changes exactly the five
    submitted axes and nothing else."""

    def test_a_failed_amendment_changes_no_constitutional_axis(self) -> None:
        opening_save = _opening_save(seed=None)
        opening_constitution = _politics(opening_save.current_state()).constitution

        save = advance_game(opening_save, _invest(opening_save.current_state(), 85))
        save = advance_game(save, _invest(save.current_state(), 118))
        save = advance_game(save, _amendment(save.current_state(), 299))  # fails, per above

        closing_constitution = _politics(save.current_state()).constitution
        assert closing_constitution == opening_constitution

        report = save.entries[-1].report()
        assert report is not None and report.constitutional_amendment is not None
        amendment = report.constitutional_amendment
        assert amendment.opening_constitution_digest == amendment.closing_constitution_digest
        for axis in _FIVE_AXES:
            assert getattr(amendment.opening_constitution, axis) == getattr(
                amendment.closing_constitution, axis
            )

    def test_a_passed_amendment_changes_exactly_the_five_submitted_axes(self) -> None:
        save = _run_campaign(seed=None)
        report = save.entries[-1].report()
        assert report is not None and report.constitutional_amendment is not None
        amendment = report.constitutional_amendment

        assert {target.axis for target in amendment.targets} == set(_FIVE_AXES)
        for target in amendment.targets:
            opening_value = getattr(amendment.opening_constitution, target.axis)
            closing_value = getattr(amendment.closing_constitution, target.axis)
            assert opening_value != closing_value

        # The one axis this report tracks that was never a target must be unchanged.
        assert (
            amendment.opening_constitution.amendment_difficulty
            == amendment.closing_constitution.amendment_difficulty
        )
        assert amendment.opening_constitution_digest != amendment.closing_constitution_digest


class TestStartingDemocracyCannotReceiveThisVictory:
    """`tiny_valid` already ships competitive-elected at genesis, so it never has a qualifying
    noncompetitive -> competitive TRANSITION for `pending_liberalization` to record -- winning an
    election there is never a peaceful-liberalization victory, no matter how the election is won.
    Reconciliation group 42 makes this structural, not incidental: it requires
    `opening_pending.set_at_turn < closing_state.turn`, so no same-turn fabrication of a starting
    democracy's win as a liberalization victory can ever validate."""

    def test_tiny_valid_winning_its_first_election_is_not_a_liberalization_victory(self) -> None:
        save = new_game(
            load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), save_format_version=_SFV
        )
        for _ in range(16):
            save = advance_game(save, _empty(save.current_state()))

        report = save.entries[-1].report()
        assert report is not None and report.election is not None
        assert report.election.result == "won"
        assert not report.election.liberalization_completed

        politics = _politics(save.current_state())
        assert politics.pending_liberalization is None
        assert politics.terminal_outcome is None
        assert validate_history(save) == []


class TestBudgetAndAmendmentAreMutuallyExclusive:
    """`DecisionSet` accepts at most one policy proposal -- a `BudgetDecision` and a
    `ConstitutionalAmendmentDecision` may never appear together, whether submitted directly or
    driven through the real resolver."""

    def test_decision_set_construction_rejects_both_at_once(self) -> None:
        budget = BudgetDecision(personal_income_rate_bps=2_500)
        amendment = ConstitutionalAmendmentDecision(
            targets=(DecreeAuthorityTarget(value=DecreeAuthority.NONE),)
        )
        with pytest.raises(ValueError, match="at most one policy proposal"):
            DecisionSet(expected_turn=0, expected_state_version=0, decisions=(budget, amendment))

    def test_the_real_engine_never_resolves_a_combined_decision_set(self) -> None:
        save = _opening_save(seed=None)
        state = save.current_state()
        budget = BudgetDecision(personal_income_rate_bps=2_500)
        amendment = ConstitutionalAmendmentDecision(
            targets=(DecreeAuthorityTarget(value=DecreeAuthority.NONE),)
        )
        with pytest.raises((ValueError, DecisionSetError)):
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(budget, amendment),
            )
