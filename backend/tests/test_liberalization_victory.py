"""Gate 3C3 commit 21: the persisted liberalization election test."""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import DecreeAuthority, constitution_digest
from app.simulation.decisions import (
    ConstitutionalAmendmentDecision,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    TermLimitTarget,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState, PendingLiberalizationState
from tests.conftest import SCENARIO_DIR
from tests.test_constitutional_amendment_gating import _make_every_bloc_supportive


def _empty(state: GameState) -> DecisionSet:
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _advance(state: GameState, turns: int) -> GameState:
    for _ in range(turns):
        state = resolve_turn(state, _empty(state)).state
    return state


def _with_prior_pending(state: GameState) -> GameState:
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    assert politics is not None
    noncompetitive = politics.constitution.model_copy(
        update={"decree_authority": DecreeAuthority.EMERGENCY_ONLY}
    )
    pending = PendingLiberalizationState(
        set_at_turn=1,
        opening_constitution_digest=constitution_digest(noncompetitive),
        closing_constitution_digest=constitution_digest(politics.constitution),
    )
    player.politics = politics.model_copy(update={"pending_liberalization": pending})
    return state


def test_persisted_pending_won_election_is_victory_with_frozen_schedule() -> None:
    state = _with_prior_pending(_advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15))
    resolution = resolve_turn(state, _empty(state))
    election = resolution.report.election
    assert election is not None and election.result == "won"
    assert election.liberalization_completed
    assert election.next_election_turn == 16
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None and politics.terminal_outcome is not None
    assert politics.consecutive_terms_held == 2
    assert politics.next_election_turn == 16
    assert politics.pending_liberalization is None
    assert politics.terminal_outcome.bucket.value == "victory"
    assert politics.terminal_outcome.victory_reason is not None
    assert politics.terminal_outcome.victory_reason.value == "peaceful_liberalization_completed"
    concluded = [
        entry for entry in resolution.report.entries if entry.reason_id == "game_concluded"
    ]
    assert concluded[0].params["reason"] == "peaceful_liberalization_completed"


def test_persisted_pending_loss_clears_pending_and_freezes_schedule() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml").model_copy(update={"seed": 3})
    state = _with_prior_pending(_advance(state, 15))
    resolution = resolve_turn(state, _empty(state))
    election = resolution.report.election
    assert election is not None and election.result == "lost"
    assert not election.liberalization_completed and election.next_election_turn == 16
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None
    assert politics.pending_liberalization is None
    assert politics.consecutive_terms_held == 1


def test_term_limit_exit_preserves_pending_and_freezes_schedule() -> None:
    state = _with_prior_pending(_advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 31))
    opening_politics = state.world.countries["arken"].politics
    assert opening_politics is not None
    opening_pending = opening_politics.pending_liberalization
    resolution = resolve_turn(state, _empty(state))
    election = resolution.report.election
    assert election is not None and election.result == "term_limit_exit"
    assert election.next_election_turn == 32
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None
    assert politics.pending_liberalization == opening_pending
    assert politics.consecutive_terms_held == 2


def test_same_turn_qualifying_amendment_win_is_continuing_and_pending_persists() -> None:
    state = _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    assert politics is not None
    player.politics = politics.model_copy(
        update={
            "constitution": politics.constitution.model_copy(
                update={"decree_authority": DecreeAuthority.EMERGENCY_ONLY}
            )
        }
    )
    state = _make_every_bloc_supportive(state)
    amendment = ConstitutionalAmendmentDecision(
        targets=(DecreeAuthorityTarget(value=DecreeAuthority.NONE),)
    )
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None and election.result == "won"
    assert not election.liberalization_completed
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None and politics.terminal_outcome is None
    assert politics.pending_liberalization is not None
    assert politics.pending_liberalization.set_at_turn == 16
    assert politics.next_election_turn == 32


def test_starting_democracy_win_without_pending_remains_continuing() -> None:
    state = _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    resolution = resolve_turn(state, _empty(state))
    assert resolution.report.election is not None
    assert not resolution.report.election.liberalization_completed
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None and politics.terminal_outcome is None


def test_same_turn_interval_amendment_cancels_the_old_election_milestone() -> None:
    state = _make_every_bloc_supportive(
        _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    )
    amendment = ConstitutionalAmendmentDecision(targets=(ElectionIntervalTarget(value=8),))
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None and not election.scheduled
    assert election.next_election_turn == 24
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None and politics.consecutive_terms_held == 1


def test_same_turn_term_limit_amendment_is_read_by_the_scheduled_election() -> None:
    state = _make_every_bloc_supportive(
        _advance(load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml"), 15)
    )
    amendment = ConstitutionalAmendmentDecision(targets=(TermLimitTarget(value=1),))
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None and election.result == "term_limit_exit"
    assert election.polling_uncertainty_bps == 0


def test_slot_12_removal_keeps_the_election_inert_and_pending_unchanged() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml").model_copy(update={"seed": 40})
    state = _advance(state, 4)
    player = state.world.countries[state.world.player_country_id]
    institutions = [
        row.model_copy(update={"loyalty": 2_000}) if row.id == "military" else row
        for row in player.institutions
    ]
    player.institutions = institutions
    state = _with_prior_pending(state)
    opening_pending = state.world.countries["arken"].politics
    assert opening_pending is not None
    resolution = resolve_turn(state, _empty(state))
    assert resolution.report.coup_unrest is not None
    assert resolution.report.coup_unrest.removal_triggered is not None
    election = resolution.report.election
    assert election is not None and not election.scheduled
    politics = resolution.state.world.countries["arken"].politics
    assert politics is not None
    assert politics.pending_liberalization == opening_pending.pending_liberalization
