"""Gate 3C3 commit 19: slot 1/2 constitutional-amendment wiring."""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.core.errors import DecisionSetError
from app.simulation.constitution import (
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    Legislature,
)
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
    InfluenceAllocation,
    TermLimitTarget,
)
from app.simulation.legislature import GovernmentRole, LegislativeOutcome, ProposalRoute
from app.simulation.phases import (
    PhaseContext,
    _apply_legal_and_administrative_changes,
    _evaluate_elections,
    _validate_and_reserve_actions,
)
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR


def _decisions(state: GameState, amendment: ConstitutionalAmendmentDecision) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(amendment,),
    )


def _run_slots_1_and_2(
    state: GameState, amendment: ConstitutionalAmendmentDecision
) -> PhaseContext:
    working = state.model_copy(deep=True)
    working.turn += 1
    working.state_version += 1
    ctx = PhaseContext(
        state=working,
        decisions=_decisions(state, amendment),
        resolving_turn=state.turn,
    )
    ctx._current_phase_id = "validate_and_reserve_actions"
    _validate_and_reserve_actions(ctx)
    ctx._current_phase_id = "apply_legal_and_administrative_changes"
    _apply_legal_and_administrative_changes(ctx)
    ctx._current_phase_id = None
    return ctx


def _liberalizing_amendment(*, influence: int = 300) -> ConstitutionalAmendmentDecision:
    return ConstitutionalAmendmentDecision(
        targets=(
            DecreeAuthorityTarget(value=DecreeAuthority.NONE),
            ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
            ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
            ElectionIntervalTarget(value=8),
        ),
        influence=(
            InfluenceAllocation(
                party_id="opposition_party",
                bloc_id="main",
                political_capital=influence,
            ),
        ),
    )


def _decree_state_at_turn_three_opening() -> GameState:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    state.turn = 2
    state.state_version = 2
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    assert politics is not None and politics.legislature is not None
    parties = []
    for party in politics.legislature.parties:
        blocs = tuple(
            bloc.model_copy(
                update={
                    "government_relationship_bps": (
                        -2_774
                        if (party.id, bloc.id) == ("opposition_party", "main")
                        else bloc.government_relationship_bps
                    )
                }
            )
            for bloc in party.blocs
        )
        parties.append(party.model_copy(update={"blocs": blocs}))
    legislature = politics.legislature.model_copy(update={"parties": tuple(parties)})
    player.politics = politics.model_copy(
        update={"legislature": legislature, "political_capital": 1_000}
    )
    return state


def _make_legislature_absent(state: GameState) -> GameState:
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    assert politics is not None
    constitution = politics.constitution.model_copy(
        update={
            "legislature": Legislature.NONE,
            "decree_authority": DecreeAuthority.UNLIMITED,
            "national_election_interval_turns": None,
        }
    )
    player.politics = politics.model_copy(
        update={"constitution": constitution, "legislature": None, "next_election_turn": None}
    )
    return state


def _make_every_bloc_supportive(state: GameState) -> GameState:
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    assert politics is not None and politics.legislature is not None
    parties = tuple(
        party.model_copy(
            update={
                "government_role": GovernmentRole.COALITION,
                "blocs": tuple(
                    bloc.model_copy(update={"government_relationship_bps": 10_000})
                    for bloc in party.blocs
                ),
            }
        )
        for party in politics.legislature.parties
    )
    player.politics = politics.model_copy(
        update={"legislature": politics.legislature.model_copy(update={"parties": parties})}
    )
    return state


def test_decree_state_turn_three_hits_exact_67_of_100_and_commits_atomically() -> None:
    state = _decree_state_at_turn_three_opening()
    opening_pressure = state.world.countries[state.world.player_country_id].politics
    assert opening_pressure is not None
    ctx = _run_slots_1_and_2(state, _liberalizing_amendment())
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None
    assert scratch.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert len(scratch.chambers) == 1
    assert (scratch.chambers[0].supporting_seats, scratch.chambers[0].required_yes_seats) == (
        67,
        67,
    )
    assert scratch.political_capital_committed == 300
    assert scratch.transition_pressure_added_bps == 10_000
    assert ctx.legislative_scratch is not None
    assert ctx.legislative_scratch.outcome is LegislativeOutcome.NO_PROPOSAL
    assert ctx.capital_ledger is not None and ctx.capital_ledger.total_committed == 300

    politics = ctx.state.world.countries[ctx.state.world.player_country_id].politics
    assert politics is not None
    assert politics.constitution == scratch.proposed_constitution
    assert politics.next_election_turn == 11
    assert politics.pending_liberalization is not None
    assert politics.pending_liberalization.set_at_turn == 3
    assert (
        politics.regime_transition_pressure_bps == opening_pressure.regime_transition_pressure_bps
    )


def test_each_no_op_target_rejects_the_whole_turn_without_mutation() -> None:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = ConstitutionalAmendmentDecision(
        targets=(DecreeAuthorityTarget(value=DecreeAuthority.UNLIMITED),)
    )
    with pytest.raises(DecisionSetError, match="changes nothing"):
        _run_slots_1_and_2(state, decision)
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_final_constitution_is_validated_after_all_targets_not_one_at_a_time() -> None:
    state = _decree_state_at_turn_three_opening()
    invalid = ConstitutionalAmendmentDecision(
        targets=(ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),)
    )
    with pytest.raises(DecisionSetError, match="hereditary_requires_monarchical_system"):
        _run_slots_1_and_2(state, invalid)

    # The individually-invalid system/selection intermediate states are legal as one atomic set.
    valid = _liberalizing_amendment()
    assert _run_slots_1_and_2(state, valid).constitutional_amendment_scratch is not None


def test_amendment_routes_are_strictly_separated_by_legislature_presence() -> None:
    with_legislature = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    illegal_decree = ConstitutionalAmendmentDecision(
        targets=(ExecutiveSelectionTarget(value=ExecutiveSelection.APPOINTED),),
        route=ProposalRoute.DECREE,
    )
    with pytest.raises(DecisionSetError, match="requires legislature='none'"):
        _run_slots_1_and_2(with_legislature, illegal_decree)

    without_legislature = _make_legislature_absent(
        load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    )
    illegal_legislative = ConstitutionalAmendmentDecision(
        targets=(ExecutiveSelectionTarget(value=ExecutiveSelection.APPOINTED),)
    )
    with pytest.raises(DecisionSetError, match="requires a legislature"):
        _run_slots_1_and_2(without_legislature, illegal_legislative)

    legal_decree = ConstitutionalAmendmentDecision(
        targets=(ExecutiveSelectionTarget(value=ExecutiveSelection.APPOINTED),),
        route=ProposalRoute.DECREE,
    )
    ctx = _run_slots_1_and_2(without_legislature, legal_decree)
    assert ctx.constitutional_amendment_scratch is not None
    assert ctx.constitutional_amendment_scratch.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    assert ctx.capital_ledger is not None and ctx.capital_ledger.total_committed == 400


def test_interval_change_reschedules_before_slot_13_and_reversal_clears_pending() -> None:
    first = _run_slots_1_and_2(
        _decree_state_at_turn_three_opening(), _liberalizing_amendment()
    ).state
    first = _make_every_bloc_supportive(first)
    first.turn = 10
    first.state_version = 10
    player = first.world.countries[first.world.player_country_id]
    politics = player.politics
    assert politics is not None
    player.politics = politics.model_copy(update={"next_election_turn": 11})

    clear_interval = ConstitutionalAmendmentDecision(targets=(ElectionIntervalTarget(value=None),))
    ctx = _run_slots_1_and_2(first, clear_interval)
    politics = ctx.state.world.countries[ctx.state.world.player_country_id].politics
    assert politics is not None
    assert politics.next_election_turn is None
    assert politics.pending_liberalization is None

    ctx._current_phase_id = "evaluate_elections_and_constitutional_events"
    _evaluate_elections(ctx)
    assert ctx.election_report is not None and not ctx.election_report.scheduled


def test_failed_amendment_preserves_state_and_pressure_but_charges_influence() -> None:
    state = _decree_state_at_turn_three_opening()
    player = state.world.countries[state.world.player_country_id]
    opening_politics = player.politics
    assert opening_politics is not None
    ctx = _run_slots_1_and_2(state, _liberalizing_amendment(influence=299))
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None
    assert scratch.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    assert scratch.chambers[0].supporting_seats == 66
    assert scratch.transition_pressure_added_bps == 0
    assert scratch.political_capital_committed == 299
    assert ctx.capital_ledger is not None and ctx.capital_ledger.total_committed == 299

    closing = ctx.state.world.countries[ctx.state.world.player_country_id].politics
    assert closing is not None
    assert closing.constitution == opening_politics.constitution
    assert closing.next_election_turn == opening_politics.next_election_turn
    assert closing.pending_liberalization == opening_politics.pending_liberalization
    assert closing.regime_transition_pressure_bps == opening_politics.regime_transition_pressure_bps


def test_combined_amendment_and_relationship_investment_unaffordability_is_atomic() -> None:
    state = _decree_state_at_turn_three_opening()
    before = canonical_dumps(state.model_dump(mode="json"))
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=200),
        )
    )
    amendment = _liberalizing_amendment(influence=900)
    decisions = DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(investment, amendment),
    )
    working = state.model_copy(deep=True)
    working.turn += 1
    working.state_version += 1
    ctx = PhaseContext(state=working, decisions=decisions, resolving_turn=state.turn)
    ctx._current_phase_id = "validate_and_reserve_actions"
    with pytest.raises(DecisionSetError, match="total political capital commitment 1100"):
        _validate_and_reserve_actions(ctx)
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_non_reversing_enacted_amendment_preserves_pending_provenance() -> None:
    first = _run_slots_1_and_2(
        _decree_state_at_turn_three_opening(), _liberalizing_amendment()
    ).state
    first = _make_every_bloc_supportive(first)
    player = first.world.countries[first.world.player_country_id]
    politics = player.politics
    assert politics is not None and politics.pending_liberalization is not None
    opening_pending = politics.pending_liberalization.model_copy()

    ctx = _run_slots_1_and_2(
        first,
        ConstitutionalAmendmentDecision(targets=(TermLimitTarget(value=2),)),
    )
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None and scratch.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    closing = ctx.state.world.countries[ctx.state.world.player_country_id].politics
    assert closing is not None
    assert closing.constitution.executive_term_limit_terms == 2
    assert closing.pending_liberalization == opening_pending
