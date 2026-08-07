from __future__ import annotations

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import HistoryValidationError, TurnResolutionError
from app.simulation.decisions import DecisionSet
from app.simulation.phases import PHASE_IDS
from app.simulation.report import PhaseStatus
from app.simulation.resolver import resolve_turn
from tests.conftest import make_country, make_game_state


def _empty_decisions_for(state) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=[],
    )


def test_turn_number_advances_exactly_once() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert resolution.state.turn == 1
    assert resolution.state.state_version == 1
    assert state.turn == 0, "input state must not be mutated"


def test_turn_number_advances_by_exactly_n_after_n_resolutions() -> None:
    state = make_game_state(turn=0, state_version=0)
    n = 8
    for _ in range(n):
        resolution = resolve_turn(state, _empty_decisions_for(state))
        state = resolution.state
    assert state.turn == n
    assert state.state_version == n


def test_stale_decision_set_is_rejected_and_state_is_untouched() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))

    stale_decisions = DecisionSet(expected_turn=99, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, stale_decisions)

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after, "a rejected decision set must not mutate the input state"


def test_stale_state_version_is_rejected_and_state_is_untouched() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))

    stale_decisions = DecisionSet(expected_turn=0, expected_state_version=99, decisions=[])
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, stale_decisions)

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after


def test_a_resolved_decision_set_cannot_be_resubmitted() -> None:
    state = make_game_state(turn=0, state_version=0)
    decisions = _empty_decisions_for(state)

    resolution = resolve_turn(state, decisions)
    assert resolution.state.turn == 1

    # Resubmitting the *same* decision set (still targeting turn 0) against the
    # new state must be rejected — it is now stale.
    with pytest.raises(TurnResolutionError):
        resolve_turn(resolution.state, decisions)


def test_invalid_input_state_is_rejected_without_running_phases() -> None:
    state = make_game_state(turn=0, state_version=0)
    # Corrupt a share sum in place to make the *input* state itself invalid.
    country = state.world.countries[state.world.player_country_id]
    country.population_groups[0].population_share = 0.99
    before = canonical_dumps(state.model_dump(mode="json"))

    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _empty_decisions_for(state))

    after = canonical_dumps(state.model_dump(mode="json"))
    assert before == after


def test_resolve_turn_rejects_a_nested_resource_deposit_mutation_without_mutating_input_or_history() -> (
    None
):
    """T17 (renamed per R9 — file-output guarantees belong to `test_cli.py`'s T18 exclusively):
    mirrors `test_invariants.py`'s nested-sector-mutation regression test exactly, for
    `resource_deposits` — `ResourceDepositState` is deliberately mutable, so a live
    `deposit.category = ...` assignment re-validates that ONE row (`validate_assignment=True`)
    but never re-triggers the *parent* `EconomyState`'s own completeness validator, desynchronizing
    it from "all eight categories, exactly once" without a full bypassed construction. Both
    `resolve_turn` (no input mutation) and `advance_game` (no appended history entry) must catch
    it independently.
    """
    from app.simulation.history import advance_game, new_game
    from app.simulation.save_format import SAVE_FORMAT_VERSION

    country = make_country("a")
    assert country.economy is not None
    # Both indices are nonrenewable (IRON_ORE, COAL) under the default all-inactive factory
    # shape, so relabeling one to match the other never trips ResourceDepositState's OWN
    # renewability validator on assignment (validate_assignment=True reruns it) — only the
    # *parent* EconomyState's completeness check, which this mutation never re-triggers, is
    # actually being tested here.
    country.economy.resource_deposits[1].category = country.economy.resource_deposits[2].category
    state = make_game_state(countries={"a": country}, player_country_id="a")

    before = canonical_dumps(state.model_dump(mode="json"))
    decisions = _empty_decisions_for(state)
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, decisions)
    assert canonical_dumps(state.model_dump(mode="json")) == before

    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    before_entry_count = save.entry_count
    with pytest.raises((TurnResolutionError, HistoryValidationError)):
        advance_game(save, decisions)
    assert save.entry_count == before_entry_count


def test_phases_run_in_the_documented_order() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert list(resolution.report.dev.phase_statuses.keys()) == list(PHASE_IDS)


def test_only_the_accounting_and_report_phases_are_implemented_so_far() -> None:
    # As of Phase 3A: government accounting (3 phases) + sector production (1 phase) +
    # legitimacy/political-capital resolution (1 phase, slot 10) + report generation are real;
    # every other resolution-order step remains an honest no-op. This test's job is to track
    # that boundary exactly as it moves phase by phase — update the IMPLEMENTED set here, not
    # the underlying assertion, as more phases gain real logic.
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    statuses = resolution.report.dev.phase_statuses

    implemented_phase_ids = {
        "apply_legal_and_administrative_changes",
        "resolve_production_and_trade",
        "resolve_government_revenue_and_expenditure",
        "update_prices_inflation_employment_debt_reserves",
        "update_group_welfare_approval_trust_radicalization",
        "generate_turn_report",
    }
    for phase_id, status in statuses.items():
        expected = (
            PhaseStatus.IMPLEMENTED
            if phase_id in implemented_phase_ids
            else PhaseStatus.NOT_IMPLEMENTED
        )
        assert status == expected, f"{phase_id}: expected {expected}, got {status}"


def test_report_resolved_turn_matches_the_turn_that_was_played() -> None:
    state = make_game_state(turn=3, state_version=3)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    assert resolution.report.resolved_turn == 3
    assert resolution.state.turn == 4


def test_political_reconciliation_failure_is_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    """(T-D4, Phase 3A) A forced reconciliation mismatch raises `TurnResolutionError`, leaves the
    caller's input `state` byte-identical, and produces no `TurnResolution` -- exactly like an
    invariant violation. `reconcile_political_report` is monkeypatched to force a mismatch,
    since the real resolver's own output never disagrees with itself (see
    `test_reconciliation.py::test_a_clean_resolution_reconciles_with_no_problems`)."""
    import app.simulation.resolver as resolver_module

    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))

    monkeypatch.setattr(
        resolver_module,
        "reconcile_political_report",
        lambda **_kwargs: ["forced mismatch for T-D4"],
    )

    with pytest.raises(TurnResolutionError, match="does not reconcile"):
        resolve_turn(state, _empty_decisions_for(state))

    after = canonical_dumps(state.model_dump(mode="json"))
    assert after == before, "input state must be byte-identical after a discarded resolution"
