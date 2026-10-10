"""Gate 4A3 victory path: the campaign objective, checked against the ENGINE, not against itself.

Three layers are kept apart throughout, because a draft's constitutional effect, what resolving it
does, and what the turn finally leaves behind are three different facts:

1. **Effect if enacted** -- `objective_effect_if_enacted` against the engine's own slot-2 outcome
   for the same amendment on a copy whose legislature carries it (so enactment is forced).
2. **The amendment phase** -- on the real state, slots 1 and 2 only: an enacted amendment's
   `qualifies_as_liberalization_transition` and marker must match the prediction; one that is not
   enacted records nothing, whatever the preview predicted.
3. **The final turn state** -- after the election and any campaign-ending event, the stage and the
   result line are derived from the closing state and are never compared with a preview.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.decision_preflight import COMPANION_CHANGE_TEXT, first_decision_problem
from app.api.main import ApiSettings, create_app
from app.api.objective import (
    QUALIFYING_INTERVAL_TURNS,
    QUALIFYING_REFORM_CARD_ID,
    amendment_effect_if_enacted,
    build_objective,
    condition_met,
    constitution_class,
    objective_line,
    trial_constitution,
)
from app.api.policy_cards import _ELECTION_INTERVAL_PRESETS, build_policy_cards
from app.api.preview import preview_decisions
from app.api.projections import build_turn_result
from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.core.errors import TurnResolutionError
from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    Legislature,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    ConstitutionalAmendmentDecision,
    ConstitutionalAxisTarget,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
    InfluenceAllocation,
    TermLimitTarget,
)
from app.simulation.government_survival import (
    is_competitive_elected_constitution,
    is_noncompetitive_constitution,
)
from app.simulation.legislature import GovernmentRole, LegislativeOutcome
from app.simulation.phases import (
    PhaseContext,
    _apply_legal_and_administrative_changes,
    _validate_and_reserve_actions,
)
from app.simulation.resolver import TurnResolution, resolve_turn
from app.simulation.state import GameState, OutcomeBucket, PoliticalState, RemovalReason
from tests.conftest import SCENARIO_DIR

SCENARIOS = ("deficit_demo", "tiny_valid", "decree_state")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _load(name: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / f"{name}.yaml")


def _politics(state: GameState) -> PoliticalState:
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    return politics


def _set_politics(state: GameState, **updates: object) -> GameState:
    player = state.world.countries[state.world.player_country_id]
    assert player.politics is not None
    player.politics = player.politics.model_copy(update=updates)
    return state


def _supportive(state: GameState) -> GameState:
    """Every bloc in coalition at the maximum relationship: the legislature carries amendments."""
    politics = _politics(state)
    assert politics.legislature is not None
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
    return _set_politics(
        state,
        legislature=politics.legislature.model_copy(update={"parties": parties}),
        political_capital=politics.political_capital_capacity,
    )


def _hostile(state: GameState) -> GameState:
    politics = _politics(state)
    assert politics.legislature is not None
    parties = tuple(
        party.model_copy(
            update={
                "blocs": tuple(
                    bloc.model_copy(update={"government_relationship_bps": -10_000})
                    for bloc in party.blocs
                ),
            }
        )
        for party in politics.legislature.parties
    )
    return _set_politics(
        state, legislature=politics.legislature.model_copy(update={"parties": parties})
    )


def _election_next(state: GameState) -> GameState:
    """Schedule the national election for the turn the next resolution produces, so it is held
    in that resolution. (Jumping `turn` instead would break the economic-baseline invariants.)"""
    return _set_politics(state, next_election_turn=state.turn + 1)


def _amend(
    *targets: ConstitutionalAxisTarget, influence: int = 0
) -> ConstitutionalAmendmentDecision:
    return ConstitutionalAmendmentDecision(
        targets=tuple(sorted(targets, key=lambda target: target.axis)),
        influence=(
            (
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=influence
                ),
            )
            if influence
            else ()
        ),
    )


def _set(state: GameState, *decisions: object) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(sorted(decisions, key=lambda d: d.kind)),  # type: ignore[attr-defined]
    )


def _slots_1_and_2(state: GameState, amendment: ConstitutionalAmendmentDecision) -> PhaseContext:
    """The amendment phase alone, on a copy: the marker as slot 2 commits it, before any election."""
    working = state.model_copy(deep=True)
    working.turn += 1
    working.state_version += 1
    ctx = PhaseContext(state=working, decisions=_set(state, amendment), resolving_turn=state.turn)
    ctx._current_phase_id = "validate_and_reserve_actions"
    _validate_and_reserve_actions(ctx)
    ctx._current_phase_id = "apply_legal_and_administrative_changes"
    _apply_legal_and_administrative_changes(ctx)
    ctx._current_phase_id = None
    return ctx


def _resolve(state: GameState, *decisions: object) -> TurnResolution:
    return resolve_turn(state, _set(state, *decisions))


def _enact(state: GameState, amendment: ConstitutionalAmendmentDecision) -> GameState:
    """`state` advanced by one fully resolved turn that enacts `amendment` (legislature supportive)."""
    resolution = _resolve(_supportive(state), amendment)
    amendment_report = resolution.report.constitutional_amendment
    assert amendment_report is not None
    assert amendment_report.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    return resolution.state


FOUR_AXIS = (
    DecreeAuthorityTarget(value=DecreeAuthority.NONE),
    ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
    ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
    ElectionIntervalTarget(value=QUALIFYING_INTERVAL_TURNS),
)
GOVERNMENT_FORM = (
    ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
    ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
)
DECREE_NONE = (DecreeAuthorityTarget(value=DecreeAuthority.NONE),)
INTERVAL = (ElectionIntervalTarget(value=QUALIFYING_INTERVAL_TURNS),)


def _valdrun_stuck() -> GameState:
    """Valdrun after the UNSAFE order: government form, then decree none -- class `neither`."""
    state = _enact(_load("decree_state"), _amend(*GOVERNMENT_FORM))
    return _enact(state, _amend(*DECREE_NONE))


def _valdrun_with_marker() -> GameState:
    return _enact(_load("decree_state"), _amend(*FOUR_AXIS))


# --------------------------------------------------------------------------
# The classes: a partition, by the engine's predicates
# --------------------------------------------------------------------------


def _coherent_constitutions() -> list[ConstitutionState]:
    base = _politics(_load("decree_state")).constitution
    rows = []
    for system, selection, decree, interval, legislature, term_limit in itertools.product(
        ExecutiveSystem,
        ExecutiveSelection,
        DecreeAuthority,
        (None, QUALIFYING_INTERVAL_TURNS),
        Legislature,
        (None, 2),
    ):
        payload = base.model_dump(mode="python")
        payload.update(
            executive_system=system,
            executive_selection=selection,
            decree_authority=decree,
            national_election_interval_turns=interval,
            legislature=legislature,
            executive_term_limit_terms=term_limit,
        )
        if first_constitutional_violation(ConstitutionState.model_construct(**payload)) is None:
            rows.append(ConstitutionState.model_validate(payload))
    return rows


def test_constitution_classes_partition_every_coherent_constitution() -> None:
    seen = set()
    for constitution in _coherent_constitutions():
        noncompetitive = is_noncompetitive_constitution(
            executive_selection=constitution.executive_selection,
            decree_authority=constitution.decree_authority,
        )
        competitive = is_competitive_elected_constitution(
            executive_selection=constitution.executive_selection,
            decree_authority=constitution.decree_authority,
            national_election_interval_turns=constitution.national_election_interval_turns,
        )
        assert not (noncompetitive and competitive)
        expected = (
            "noncompetitive" if noncompetitive else "competitive" if competitive else "neither"
        )
        assert constitution_class(constitution) == expected
        # The three conditions together are exactly the competitive-elected predicate.
        all_met = all(
            condition_met(constitution, c)
            for c in ("elected_executive", "no_decree_authority", "election_interval")
        )
        assert all_met == competitive
        seen.add(expected)
    assert seen == {"noncompetitive", "competitive", "neither"}, "the `neither` class is reachable"


def test_each_condition_turns_on_its_own_axis_alone() -> None:
    """Changing one axis to a value the predicate accepts flips exactly that condition."""
    for constitution in _coherent_constitutions():
        for condition, axis, accepted in (
            ("elected_executive", "executive_selection", ExecutiveSelection.DIRECT_ELECTION),
            ("no_decree_authority", "decree_authority", DecreeAuthority.NONE),
            ("election_interval", "national_election_interval_turns", QUALIFYING_INTERVAL_TURNS),
        ):
            moved = constitution.model_copy(update={axis: accepted})
            assert condition_met(moved, condition)  # type: ignore[arg-type]
            others = [
                c
                for c in ("elected_executive", "no_decree_authority", "election_interval")
                if c != condition
            ]
            for other in others:
                assert condition_met(moved, other) == condition_met(constitution, other)  # type: ignore[arg-type]


def test_objective_module_restates_no_enum_set_of_the_predicates() -> None:
    """Secondary to the behavioural tests above: `objective.py` imports the two predicates and
    holds no literal copy of the sets they test (no HEREDITARY/APPOINTED/LEGISLATIVE_SELECTION
    member is named, and decree authority is never compared with a member directly)."""
    source = Path("app/api/objective.py").read_text(encoding="utf-8")
    assert "is_noncompetitive_constitution" in source
    assert "is_competitive_elected_constitution" in source
    for member in ("HEREDITARY", "APPOINTED", "LEGISLATIVE_SELECTION", "DIRECT_ELECTION"):
        assert f"ExecutiveSelection.{member}" not in source
    for member in ("NONE", "EMERGENCY_ONLY", "UNLIMITED"):
        assert f"DecreeAuthority.{member}" not in source
    ast.parse(source)


# --------------------------------------------------------------------------
# Stages over real states
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scenario", "met", "card"),
    [
        ("deficit_demo", 2, "constitution_decree_authority_to_none"),
        ("tiny_valid", 2, "constitution_decree_authority_to_none"),
        ("decree_state", 0, QUALIFYING_REFORM_CARD_ID),
    ],
)
def test_every_scenario_opens_in_the_reform_stage(scenario: str, met: int, card: str) -> None:
    objective = build_objective(_politics(_load(scenario)))
    assert objective.stage == "reform"
    assert objective.conditions_met == met
    assert objective.headline == f"Reform the constitution: {met} of 3 conditions met."
    assert objective.transition_text == "Qualifying transition: not recorded"
    assert objective.qualifying_card_id == card
    assert "%" not in objective.model_dump_json()


def test_the_qualifying_card_is_the_audited_valdrun_amendment_and_is_in_the_catalog() -> None:
    state = _load("decree_state")
    cards = {card.card_id: card for card in build_policy_cards(state)}
    card = cards[QUALIFYING_REFORM_CARD_ID]
    assert card.available
    legislative = next(route for route in card.routes if route.route.value == "legislative")
    assert legislative.template is not None
    assert legislative.template.targets == tuple(sorted(FOUR_AXIS, key=lambda t: t.axis))
    # It meets the ENGINE's qualifying test (opening non-competitive, enacted competitive).
    ctx = _slots_1_and_2(_supportive(state), legislative.template)  # type: ignore[arg-type]
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None and scratch.qualifies_as_liberalization_transition


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_offered_link_names_an_available_catalog_card(scenario: str) -> None:
    state = _load(scenario)
    cards = {card.card_id: card for card in build_policy_cards(state)}
    objective = build_objective(_politics(state))
    linked = [row.link_card_id for row in objective.conditions if row.link_card_id]
    assert linked, "a reform-stage objective offers at least one link"
    for card_id in [*linked, objective.qualifying_card_id]:
        assert card_id in cards and cards[card_id].available, card_id


def test_qualifying_interval_is_a_catalog_preset() -> None:
    assert QUALIFYING_INTERVAL_TURNS in _ELECTION_INTERVAL_PRESETS
    assert min(p for p in _ELECTION_INTERVAL_PRESETS if p is not None) == QUALIFYING_INTERVAL_TURNS


def test_only_the_combined_card_exists_when_two_or_more_conditions_are_unmet() -> None:
    for scenario in ("deficit_demo", "tiny_valid"):
        ids = {card.card_id for card in build_policy_cards(_load(scenario))}
        assert QUALIFYING_REFORM_CARD_ID not in ids


# --------------------------------------------------------------------------
# §1 engine resolutions -- the marker as RESOLVED, and the stage derived from it
# --------------------------------------------------------------------------


def test_unsafe_order_leaves_no_marker_and_the_cannot_qualify_stage() -> None:
    stuck = _valdrun_stuck()
    politics = _politics(stuck)
    assert constitution_class(politics.constitution) == "neither"
    assert politics.pending_liberalization is None
    objective = build_objective(politics)
    assert objective.stage == "cannot_qualify"
    assert objective.cannot_qualify_reason == "missing_interval"
    assert objective.headline == "Your constitution can't qualify as it stands."
    assert objective.conditions_text == "Constitutional conditions: 2 of 3 met"
    assert all(row.link_card_id is None for row in objective.conditions)
    assert objective.qualifying_card_id is None

    # The third step, the interval, meets all three conditions -- and the engine records NOTHING.
    final = _enact(stuck, _amend(*INTERVAL))
    politics = _politics(final)
    assert constitution_class(politics.constitution) == "competitive"
    assert politics.pending_liberalization is None
    objective = build_objective(politics)
    assert objective.stage == "cannot_qualify"
    assert objective.cannot_qualify_reason == "already_competitive"
    assert objective.conditions_met == 3
    assert objective.transition_text == "Qualifying transition: not recorded"


def test_safe_order_interval_then_form_then_decree_records_the_marker() -> None:
    state = _enact(_load("decree_state"), _amend(*INTERVAL))
    assert build_objective(_politics(state)).stage == "reform"
    state = _enact(state, _amend(*GOVERNMENT_FORM))
    assert build_objective(_politics(state)).stage == "reform"
    state = _enact(state, _amend(*DECREE_NONE))
    politics = _politics(state)
    assert politics.pending_liberalization is not None
    # Recorded on the turn this resolution produced (`phases.py`: slot 2 runs on `state.turn`).
    assert politics.pending_liberalization.set_at_turn == state.turn
    objective = build_objective(politics)
    assert objective.stage == "qualifying_election"
    assert objective.transition_turn == state.turn


def test_the_one_amendment_four_axis_reform_records_the_marker() -> None:
    politics = _politics(_valdrun_with_marker())
    assert politics.pending_liberalization is not None
    objective = build_objective(politics)
    assert objective.stage == "qualifying_election"
    assert objective.headline == f"Win the qualifying election: turn {politics.next_election_turn}."
    assert objective.detail == "Transition recorded on turn 1. Losing it ends the campaign."
    assert objective.transition_text == "Qualifying transition: recorded on turn 1"


def test_the_stated_way_back_from_the_stuck_state_records_the_marker() -> None:
    restored = _enact(
        _valdrun_stuck(), _amend(DecreeAuthorityTarget(value=DecreeAuthority.EMERGENCY_ONLY))
    )
    assert build_objective(_politics(restored)).stage == "reform"
    final = _enact(restored, _amend(*DECREE_NONE, *INTERVAL))
    assert _politics(final).pending_liberalization is not None
    assert build_objective(_politics(final)).stage == "qualifying_election"


def test_removing_the_interval_after_the_marker_clears_it() -> None:
    final = _enact(_valdrun_with_marker(), _amend(ElectionIntervalTarget(value=None)))
    politics = _politics(final)
    assert politics.pending_liberalization is None
    objective = build_objective(politics)
    assert objective.stage == "cannot_qualify"
    assert objective.cannot_qualify_reason == "missing_interval"


def test_changing_the_interval_after_the_marker_keeps_it_and_reschedules() -> None:
    marked = _valdrun_with_marker()
    opening_marker = _politics(marked).pending_liberalization
    final = _enact(marked, _amend(ElectionIntervalTarget(value=8)))
    politics = _politics(final)
    assert politics.pending_liberalization == opening_marker
    assert politics.next_election_turn == marked.turn + 1 + 8
    assert build_objective(politics).election_turn == marked.turn + 1 + 8


def _deficit_demo_on_election_turn() -> GameState:
    return _election_next(_supportive(_load("deficit_demo")))


def test_a_qualifying_reform_on_an_election_turn_faces_that_election_too_soon() -> None:
    state = _deficit_demo_on_election_turn()
    resolution = _resolve(state, _amend(*DECREE_NONE))
    election = resolution.report.election
    assert election is not None and election.result == "won"
    politics = _politics(resolution.state)
    assert politics.terminal_outcome is None, "won, but too soon: not victory"
    assert politics.pending_liberalization is not None
    interval = politics.constitution.national_election_interval_turns
    assert interval is not None
    assert politics.next_election_turn == state.turn + 1 + interval
    assert build_objective(politics).stage == "qualifying_election"


def test_any_lost_election_is_defeat_with_or_without_a_marker() -> None:
    no_marker = _hostile(_load("deficit_demo"))
    no_marker = _election_next(_set_politics(no_marker, legitimacy_bps=0))
    lost = _resolve(no_marker)
    assert lost.report.election is not None and lost.report.election.result == "lost"
    outcome = _politics(lost.state).terminal_outcome
    assert outcome is not None and outcome.removal_reason is RemovalReason.ELECTORAL_DEFEAT
    assert build_objective(_politics(lost.state)).stage == "concluded"

    marked = _election_next(_set_politics(_hostile(_valdrun_with_marker()), legitimacy_bps=0))
    lost = _resolve(marked)
    assert lost.report.election is not None and lost.report.election.result == "lost"
    politics = _politics(lost.state)
    assert politics.terminal_outcome is not None
    assert politics.pending_liberalization is None, "defeat clears the marker"
    objective = build_objective(politics)
    assert objective.stage == "concluded"
    assert objective.headline == "The campaign has ended."


def test_winning_the_qualifying_election_is_victory_and_consumes_the_marker() -> None:
    won = _resolve(_election_next(_supportive(_valdrun_with_marker())))
    politics = _politics(won.state)
    assert politics.terminal_outcome is not None
    assert politics.terminal_outcome.bucket is OutcomeBucket.VICTORY
    assert politics.pending_liberalization is None
    objective = build_objective(politics)
    assert objective.stage == "concluded"
    assert objective.headline == "Objective complete: the qualifying election was won."


def test_a_term_limit_exit_concludes_even_with_the_marker_still_set() -> None:
    """The engine KEEPS the marker on a term-limit exit; the terminal outcome takes precedence."""
    marked = _enact(_valdrun_with_marker(), _amend(TermLimitTarget(value=1)))
    marked = _election_next(_set_politics(marked, consecutive_terms_held=1))
    ended = _resolve(marked)
    politics = _politics(ended.state)
    assert ended.report.election is not None and ended.report.election.result == "term_limit_exit"
    assert politics.pending_liberalization is not None
    assert politics.terminal_outcome is not None
    assert build_objective(politics).stage == "concluded"
    line = objective_line(_politics(marked), politics, ended.report)
    assert line == "The campaign ended before the objective was completed."


# --------------------------------------------------------------------------
# Links: safe ordering, from the state each link would be clicked in
# --------------------------------------------------------------------------


def test_a_link_that_would_strand_the_constitution_is_withheld_with_its_reason() -> None:
    after_decree = _enact(_load("decree_state"), _amend(*DECREE_NONE))
    objective = build_objective(_politics(after_decree))
    rows = {row.id: row for row in objective.conditions}
    executive = rows["elected_executive"]
    assert executive.if_enacted_alone == "cannot_qualify"
    assert executive.link_card_id is None
    assert executive.note is not None and executive.note.startswith("Not on its own:")
    # The interval link is safe, and the combined card still qualifies.
    assert rows["election_interval"].link_card_id == "constitution_election_interval_to_4"
    assert rows["election_interval"].if_enacted_alone == "reform_continues"
    assert objective.qualifying_card_id == QUALIFYING_REFORM_CARD_ID
    # The withheld verdict is the ENGINE's: enacting that card alone really strands it.
    stranded = _enact(after_decree, _amend(*GOVERNMENT_FORM))
    assert build_objective(_politics(stranded)).stage == "cannot_qualify"


# --------------------------------------------------------------------------
# §2 preview parity -- three layers, kept apart
# --------------------------------------------------------------------------


def _reference_effect(state: GameState, amendment: ConstitutionalAmendmentDecision) -> str:
    """Layer 1's reference: the ENGINE's slot-2 outcome with enactment forced."""
    opening = _politics(state)
    ctx = _slots_1_and_2(_supportive(state.model_copy(deep=True)), amendment)
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None and scratch.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    closing = _politics(ctx.state)
    if scratch.qualifies_as_liberalization_transition:
        assert closing.pending_liberalization is not None
        return "qualifies"
    if opening.pending_liberalization is not None:
        return (
            "keeps_transition" if closing.pending_liberalization is not None else "ends_transition"
        )
    assert closing.pending_liberalization is None
    klass = constitution_class(closing.constitution)
    if klass == "noncompetitive":
        return (
            "reform_continues"
            if constitution_class(opening.constitution) == "noncompetitive"
            else "reopens_route"
        )
    return "cannot_qualify"


def _cases() -> list[tuple[str, GameState, ConstitutionalAmendmentDecision]]:
    return [
        ("valdrun four-axis", _load("decree_state"), _amend(*FOUR_AXIS)),
        ("valdrun interval only", _load("decree_state"), _amend(*INTERVAL)),
        ("valdrun form only", _load("decree_state"), _amend(*GOVERNMENT_FORM)),
        ("deficit decree none", _load("deficit_demo"), _amend(*DECREE_NONE)),
        ("tiny decree none", _load("tiny_valid"), _amend(*DECREE_NONE)),
        ("stuck: interval", _valdrun_stuck(), _amend(*INTERVAL)),
        (
            "stuck: restore decree",
            _valdrun_stuck(),
            _amend(DecreeAuthorityTarget(value=DecreeAuthority.EMERGENCY_ONLY)),
        ),
        ("marker: term limit", _valdrun_with_marker(), _amend(TermLimitTarget(value=2))),
        (
            "marker: remove interval",
            _valdrun_with_marker(),
            _amend(ElectionIntervalTarget(value=None)),
        ),
        (
            "marker: restore decree",
            _valdrun_with_marker(),
            _amend(DecreeAuthorityTarget(value=DecreeAuthority.EMERGENCY_ONLY)),
        ),
    ]


@pytest.mark.parametrize("index", range(10))
def test_layer_1_effect_if_enacted_matches_the_engine_with_enactment_forced(index: int) -> None:
    name, state, amendment = _cases()[index]
    preview = preview_decisions(state, _set(state, amendment))
    effect = preview.objective_effect_if_enacted
    assert effect is not None, name
    assert effect.effect == _reference_effect(state, amendment), name


@pytest.mark.parametrize("index", range(10))
def test_layer_2_the_amendment_phase_records_exactly_what_was_predicted_when_enacted(
    index: int,
) -> None:
    name, state, amendment = _cases()[index]
    state = _supportive(state)
    effect = preview_decisions(state, _set(state, amendment)).objective_effect_if_enacted
    assert effect is not None
    opening = _politics(state)
    ctx = _slots_1_and_2(state, amendment)
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None and scratch.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    closing = _politics(ctx.state)  # slot 2's committed state: no election has run yet
    assert scratch.qualifies_as_liberalization_transition == (effect.effect == "qualifies"), name
    if effect.effect == "qualifies":
        assert closing.pending_liberalization is not None
        assert closing.pending_liberalization.set_at_turn == state.turn + 1
    elif effect.effect == "keeps_transition":
        assert closing.pending_liberalization == opening.pending_liberalization
    else:
        assert closing.pending_liberalization is None
    assert effect.conditions_met == sum(
        condition_met(closing.constitution, c)
        for c in ("elected_executive", "no_decree_authority", "election_interval")
    )


def test_layer_2_a_failed_vote_predicts_qualifies_but_records_nothing() -> None:
    state = _load("decree_state")
    amendment = _amend(*FOUR_AXIS)
    preview = preview_decisions(state, _set(state, amendment))
    assert preview.would_pass is False
    assert preview.objective_effect_if_enacted is not None
    assert preview.objective_effect_if_enacted.effect == "qualifies"
    opening = _politics(state)
    ctx = _slots_1_and_2(state, amendment)
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None and scratch.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    assert scratch.qualifies_as_liberalization_transition is False
    closing = _politics(ctx.state)
    assert closing.pending_liberalization is None
    assert closing.constitution == opening.constitution
    # Layer 3: the full turn's result line says it failed, and the stage is unchanged.
    resolution = _resolve(state, amendment)
    closing = _politics(resolution.state)
    assert build_objective(closing).stage == "reform"
    assert objective_line(opening, closing, resolution.report) == (
        "The amendment failed; the constitution and checklist are unchanged."
    )


def test_layer_2_an_unaffordable_draft_predicts_qualifies_and_resolution_refuses_it() -> None:
    state = _load("decree_state")
    assert _politics(state).political_capital == 500
    amendment = _amend(*FOUR_AXIS, influence=400)
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=200),
        )
    )
    preview = preview_decisions(state, _set(state, amendment, investment))
    assert preview.affordable is False
    assert preview.objective_effect_if_enacted is not None
    assert preview.objective_effect_if_enacted.effect == "qualifies"
    before = canonical_dumps(state.model_dump(mode="json"))
    with pytest.raises(TurnResolutionError, match="exceeds opening political capital 500"):
        resolve_turn(state, _set(state, amendment, investment))
    assert canonical_dumps(state.model_dump(mode="json")) == before
    assert _politics(state).pending_liberalization is None


def test_preview_names_the_deciding_election_including_the_same_turn_case() -> None:
    state = _load("decree_state")
    effect = preview_decisions(state, _set(state, _amend(*FOUR_AXIS))).objective_effect_if_enacted
    assert effect is not None
    assert (effect.deciding_election_turn, effect.election_this_turn_too_soon) == (
        state.turn + 1 + QUALIFYING_INTERVAL_TURNS,
        False,
    )
    on_election = _deficit_demo_on_election_turn()
    effect = preview_decisions(
        on_election, _set(on_election, _amend(*DECREE_NONE))
    ).objective_effect_if_enacted
    assert effect is not None and effect.election_this_turn_too_soon
    interval = _politics(on_election).constitution.national_election_interval_turns
    assert interval is not None
    assert effect.deciding_election_turn == on_election.turn + 1 + interval
    # ... and that is what the engine then does (layer 3, separately).
    resolution = _resolve(on_election, _amend(*DECREE_NONE))
    assert _politics(resolution.state).next_election_turn == effect.deciding_election_turn


def test_preview_has_no_effect_without_an_amendment() -> None:
    state = _load("decree_state")
    assert preview_decisions(state, _set(state)).objective_effect_if_enacted is None


def test_effect_function_and_trial_agree_with_preflight_refusals() -> None:
    """A structurally refused amendment never reaches an effect: the trial is `None` exactly when
    `decision_preflight` refuses the targets."""
    state = _load("decree_state")
    for targets in (
        (ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),),
        (DecreeAuthorityTarget(value=DecreeAuthority.UNLIMITED),),
        DECREE_NONE,
    ):
        amendment = _amend(*targets)
        problem = first_decision_problem(state, _set(state, amendment))
        trial = trial_constitution(_politics(state).constitution, amendment.targets)
        assert (trial is None) == (problem is not None)
        if trial is not None:
            assert amendment_effect_if_enacted(_politics(state), trial) == "reform_continues"


# --------------------------------------------------------------------------
# §3 result lines from the closing stage (real resolved turns)
# --------------------------------------------------------------------------


def _line(opening: GameState, resolution: TurnResolution) -> str | None:
    return objective_line(_politics(opening), _politics(resolution.state), resolution.report)


def test_line_qualifying_reform() -> None:
    state = _supportive(_load("decree_state"))
    resolution = _resolve(state, _amend(*FOUR_AXIS))
    assert _line(state, resolution) == (
        "The constitution now qualifies, and the transition is recorded. Win the election on "
        f"turn {1 + QUALIFYING_INTERVAL_TURNS} to complete it."
    )


def test_line_qualifying_reform_on_an_election_turn() -> None:
    state = _deficit_demo_on_election_turn()
    resolution = _resolve(state, _amend(*DECREE_NONE))
    interval = _politics(state).constitution.national_election_interval_turns
    assert interval is not None
    assert _line(state, resolution) == (
        "The constitution now qualifies, and the transition is recorded. Win the election on "
        f"turn {state.turn + 1 + interval} to complete it. This turn's election came too soon "
        "to count."
    )


def test_line_keeps_the_transition() -> None:
    state = _supportive(_valdrun_with_marker())
    resolution = _resolve(state, _amend(TermLimitTarget(value=2)))
    assert _line(state, resolution) == (
        "The constitution still qualifies; the transition recorded on turn 1 stands. Election: "
        f"turn {1 + QUALIFYING_INTERVAL_TURNS}."
    )


def test_line_ends_the_transition_into_cannot_qualify() -> None:
    state = _supportive(_valdrun_with_marker())
    resolution = _resolve(state, _amend(ElectionIntervalTarget(value=None)))
    assert _line(state, resolution) == (
        "This amendment ended the qualifying transition: a national election schedule no longer "
        "met. Your constitution can't qualify as it stands."
    )


def test_line_ends_the_transition_into_reform() -> None:
    state = _supportive(_valdrun_with_marker())
    resolution = _resolve(
        state, _amend(DecreeAuthorityTarget(value=DecreeAuthority.EMERGENCY_ONLY))
    )
    assert _line(state, resolution) == (
        "This amendment ended the qualifying transition: no decree authority no longer met. "
        "Reform the constitution: 2 of 3 conditions met."
    )


def test_line_reform_continues() -> None:
    state = _supportive(_load("decree_state"))
    resolution = _resolve(state, _amend(*INTERVAL))
    assert _line(state, resolution) == (
        "1 of 3 constitutional conditions met. Still needed: an elected executive and no decree "
        "authority."
    )


def test_line_cannot_qualify_variants() -> None:
    after_form = _enact(_load("decree_state"), _amend(*GOVERNMENT_FORM))
    state = _supportive(after_form)
    resolution = _resolve(state, _amend(*DECREE_NONE))
    assert _line(state, resolution) == (
        "2 of 3 conditions are met, but the constitution can no longer qualify: it is no longer "
        "under non-competitive rule, and only a reform from non-competitive rule counts."
    )
    stuck = _supportive(resolution.state)
    resolution = _resolve(stuck, _amend(*INTERVAL))
    assert _line(stuck, resolution) == (
        "All three conditions are met, but this did not count as the qualifying reform: the "
        "constitution was not under non-competitive rule before it."
    )


def test_line_election_won_without_a_transition() -> None:
    state = _deficit_demo_on_election_turn()
    resolution = _resolve(state)
    assert resolution.report.election is not None
    assert resolution.report.election.result == "won"
    interval = _politics(state).constitution.national_election_interval_turns
    assert interval is not None
    assert _line(state, resolution) == (
        "Election won, but no qualifying transition was recorded, so the objective is not "
        f"complete. Next election: turn {state.turn + 1 + interval}."
    )


def test_line_victory_and_qualifying_defeat() -> None:
    marked = _election_next(_supportive(_valdrun_with_marker()))
    won = _resolve(marked)
    assert _line(marked, won) == "Objective complete: you won the qualifying election."

    hostile = _election_next(_set_politics(_hostile(_valdrun_with_marker()), legitimacy_bps=0))
    lost = _resolve(hostile)
    assert _line(hostile, lost) == "The qualifying election was lost; the campaign is over."


def test_line_nothing_touched_and_unknown_opening() -> None:
    state = _load("decree_state")
    resolution = _resolve(state)
    assert _line(state, resolution) is None
    resolution = _resolve(state, _amend(*FOUR_AXIS))
    assert objective_line(None, _politics(resolution.state), resolution.report) is None


# --------------------------------------------------------------------------
# History equals live, through the API
# --------------------------------------------------------------------------


def test_objective_line_and_stage_are_identical_live_and_from_history(tmp_path: Path) -> None:
    app = create_app(ApiSettings(port=48993, save_root=tmp_path, serve_spa=False))
    client = TestClient(app, base_url="http://127.0.0.1:48993")
    assert client.post("/api/game/new", json={"scenario_id": "deficit_demo"}).status_code == 200
    state = client.get("/api/game/state").json()
    assert state["objective"]["stage"] == "reform"
    body = {
        "revision": state["revision"],
        "campaign_id": state["campaign_id"],
        "decisions": [
            {
                "kind": "constitutional_amendment",
                "targets": [{"axis": "decree_authority", "value": "none"}],
                "route": "legislative",
                "influence": [
                    {"party_id": "citizens_bloc", "bloc_id": "hardliners", "political_capital": 300}
                ],
            }
        ],
    }
    preview = client.post("/api/game/preview", json=body).json()
    assert preview["would_pass"] is True
    assert preview["objective_effect_if_enacted"]["effect"] == "qualifies"
    live = client.post("/api/game/resolve", json=body).json()
    line = live["turnResult"]["objective_line"]
    assert line == (
        "The constitution now qualifies, and the transition is recorded. Win the election on "
        "turn 20 to complete it."
    )
    assert live["dashboard"]["objective"]["stage"] == "qualifying_election"
    history = client.get(f"/api/game/history/{live['turnResult']['turn']}").json()
    assert history["turnResult"] == live["turnResult"]
    assert history["dashboardAsOfTurn"]["objective"] == live["dashboard"]["objective"]
    # D-V2 and D-V3 on the same real turn.
    legislature = _politics(_load("deficit_demo")).legislature
    assert legislature is not None
    hardliners = next(
        bloc.name
        for party in legislature.parties
        for bloc in party.blocs
        if (party.id, bloc.id) == ("citizens_bloc", "hardliners")
    )
    targets = {row["target"] for row in live["turnResult"]["ledger"] if row["target"]}
    assert targets == {hardliners}
    assert "/" not in hardliners
    assert "No budget was proposed." in live["turnResult"]["unchanged"]
    assert "No policy proposal was submitted." not in live["turnResult"]["unchanged"]


def test_build_turn_result_without_opening_state_omits_the_line() -> None:
    state = _supportive(_load("decree_state"))
    resolution = _resolve(state, _amend(*FOUR_AXIS))
    assert build_turn_result(resolution.state, resolution.report).objective_line is None
    assert (
        build_turn_result(resolution.state, resolution.report, opening_state=state).objective_line
        is not None
    )


# --------------------------------------------------------------------------
# D-V2 to D-V4
# --------------------------------------------------------------------------


def test_ledger_targets_name_the_bloc_not_its_identifier() -> None:
    state = _load("decree_state")
    resolution = _resolve(state, _amend(*FOUR_AXIS, influence=300))
    result = build_turn_result(resolution.state, resolution.report, opening_state=state)
    names = {
        bloc.name
        for party in (_politics(state).legislature.parties if _politics(state).legislature else ())
        for bloc in party.blocs
        if (party.id, bloc.id) == ("opposition_party", "main")
    }
    targets = {row.target for row in result.ledger if row.target is not None}
    assert targets == names
    assert all("/" not in target for target in targets)


def test_no_policy_proposal_line_is_kept_when_nothing_was_proposed() -> None:
    state = _load("decree_state")
    resolution = _resolve(state)
    result = build_turn_result(resolution.state, resolution.report, opening_state=state)
    assert "No policy proposal was submitted." in result.unchanged
    assert "No budget was proposed." not in result.unchanged


def _reachable_violation_codes() -> set[str]:
    base = _politics(_load("decree_state")).constitution
    codes = set()
    for system, selection, decree, interval, legislature, term_limit in itertools.product(
        ExecutiveSystem,
        ExecutiveSelection,
        DecreeAuthority,
        (None, QUALIFYING_INTERVAL_TURNS),
        Legislature,
        (None, 2),
    ):
        payload = base.model_dump(mode="python")
        payload.update(
            executive_system=system,
            executive_selection=selection,
            decree_authority=decree,
            national_election_interval_turns=interval,
            legislature=legislature,
            executive_term_limit_terms=term_limit,
        )
        violation = first_constitutional_violation(ConstitutionState.model_construct(**payload))
        if violation is not None:
            codes.add(violation[0])
    return codes


def test_every_coherence_rule_has_an_authored_companion_sentence() -> None:
    codes = _reachable_violation_codes()
    assert len(codes) == 10
    assert set(COMPANION_CHANGE_TEXT) == codes


def test_the_valdrun_three_axis_refusal_names_the_executive_system() -> None:
    state = _load("decree_state")
    amendment = _amend(
        DecreeAuthorityTarget(value=DecreeAuthority.NONE),
        ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
        ElectionIntervalTarget(value=QUALIFYING_INTERVAL_TURNS),
    )
    problem = first_decision_problem(state, _set(state, amendment))
    assert problem is not None
    assert problem.code == "amendment_constitution_incoherent"
    assert problem.diagnostic_code == "monarchical_requires_hereditary_or_appointed"
    assert problem.message == (
        "This change would leave the constitution internally inconsistent: a monarch can't be "
        "directly elected or selected by the legislature. Change Executive system too (for "
        "example, to presidential for a directly elected executive), or keep a hereditary or "
        "appointed executive."
    )
