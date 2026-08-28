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
    # As of External Wars Gate W1: government accounting (3 phases) + sector production
    # (1 phase) + foreign-conflict outbreak and progression (2 phases, slots 7-8) +
    # legitimacy/political-capital resolution (1 phase, slot 10) + legislative vote and
    # capital-ledger resolution (1 phase, slot 1) + bloc-relationship application (1 phase,
    # slot 11) + report generation are real; every other resolution-order step remains an honest
    # no-op. This test's job is to track that boundary exactly as it moves phase by phase —
    # update the IMPLEMENTED set here, not the underlying assertion, as more phases gain real
    # logic.
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions_for(state))
    statuses = resolution.report.dev.phase_statuses

    implemented_phase_ids = {
        "validate_and_reserve_actions",
        "apply_legal_and_administrative_changes",
        "resolve_production_and_trade",
        "resolve_government_revenue_and_expenditure",
        "update_prices_inflation_employment_debt_reserves",
        "resolve_diplomacy_and_sanctions",
        "resolve_military_movement_and_combat",
        "update_group_welfare_approval_trust_radicalization",
        "update_institutional_loyalty_competence_corruption_power",
        "evaluate_protests_strikes_insurgency_coups_revolutions",
        "evaluate_elections_and_constitutional_events",
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
    """(T-D4, Phase 3A; extended Phase 3B1, R8) A forced reconciliation mismatch raises
    `TurnResolutionError`, leaves the caller's input `state` byte-identical -- whole-state, and
    field-by-field for `politics`/`finance` specifically -- and produces no `TurnResolution`,
    exactly like an invariant violation. `reconcile_political_legislative_and_survival_report` is
    monkeypatched to force a mismatch, since the real resolver's own output never disagrees with
    itself (see `test_reconciliation.py::test_a_clean_resolution_reconciles_with_no_problems`)."""
    import app.simulation.resolver as resolver_module

    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))
    original_player = state.world.countries[state.world.player_country_id]
    assert original_player.politics is not None and original_player.finance is not None
    before_politics = original_player.politics.model_copy(deep=True)
    before_finance = original_player.finance.model_copy(deep=True)

    monkeypatch.setattr(
        resolver_module,
        "reconcile_political_legislative_and_survival_report",
        lambda **_kwargs: ["forced mismatch for T-D4"],
    )

    with pytest.raises(TurnResolutionError, match="does not reconcile"):
        resolve_turn(state, _empty_decisions_for(state))

    after = canonical_dumps(state.model_dump(mode="json"))
    assert after == before, "input state must be byte-identical after a discarded resolution"

    player = state.world.countries[state.world.player_country_id]
    assert player.politics == before_politics, "politics must be untouched by a discarded turn"
    assert player.finance == before_finance, "finance must be untouched by a discarded turn"


def test_political_reconciliation_failure_appends_no_history_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(Phase 3B1, R8) The same forced mismatch, driven through `advance_game`: no new
    `HistoryEntry` is appended, and `entry_count`/`head_entry_hash` are unmoved."""
    import app.simulation.resolver as resolver_module
    from app.simulation.history import advance_game, new_game
    from app.simulation.save_format import SAVE_FORMAT_VERSION

    state = make_game_state(turn=0, state_version=0)
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    before_entry_count = save.entry_count
    before_head_hash = save.head_entry_hash
    before_entries = len(save.entries)

    monkeypatch.setattr(
        resolver_module,
        "reconcile_political_legislative_and_survival_report",
        lambda **_kwargs: ["forced mismatch for T-D4"],
    )

    with pytest.raises(TurnResolutionError, match="does not reconcile"):
        advance_game(save, _empty_decisions_for(state))

    assert save.entry_count == before_entry_count
    assert save.head_entry_hash == before_head_hash
    assert len(save.entries) == before_entries


def test_stale_decision_set_leaves_politics_and_its_baseline_untouched() -> None:
    """(T-D2, Phase 3A) `test_stale_decision_set_is_rejected_and_state_is_untouched` already
    proves whole-state byte identity at turn 0 (baseline `None`); this variant runs one real turn
    first so a genuine `EconomicBaselineState` exists, then submits a stale decision set and
    checks `politics` specifically -- not just via the whole-state dump, but field by field, so
    the political phase's opening-snapshot pattern (§8) cannot be silently bypassed on a rejected
    turn."""
    state = make_game_state(turn=0, state_version=0)
    first = resolve_turn(state, _empty_decisions_for(state))
    resolved_state = first.state
    player_id = resolved_state.world.player_country_id
    politics_before = resolved_state.world.countries[player_id].politics
    assert politics_before is not None
    assert politics_before.economic_baseline is not None
    before = canonical_dumps(resolved_state.model_dump(mode="json"))

    stale_decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        resolve_turn(resolved_state, stale_decisions)

    after = canonical_dumps(resolved_state.model_dump(mode="json"))
    assert after == before
    politics_after = resolved_state.world.countries[player_id].politics
    assert politics_after is not None
    assert politics_after.legitimacy_bps == politics_before.legitimacy_bps
    assert politics_after.political_capital == politics_before.political_capital
    assert politics_after.economic_baseline == politics_before.economic_baseline


def test_invalid_political_state_is_rejected_atomically() -> None:
    """(T-D3, Phase 3A) A bypassed-construction out-of-range `legitimacy_bps` on the *input*
    state is rejected by `check_invariants` before any phase runs -- mirroring
    `test_invalid_input_state_is_rejected_without_running_phases` for the finance/population
    case, now for politics."""
    from app.simulation.state import PoliticalState

    country = make_country("a")
    assert country.politics is not None
    bypassed_politics = PoliticalState.model_construct(
        constitution=country.politics.constitution,
        constitutional_order_support_bps=country.politics.constitutional_order_support_bps,
        legitimacy_bps=10_001,
        political_capital=country.politics.political_capital,
        political_capital_capacity=country.politics.political_capital_capacity,
        economic_baseline=None,
    )
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")
    before = canonical_dumps(state.model_dump(mode="json"))

    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _empty_decisions_for(state))

    after = canonical_dumps(state.model_dump(mode="json"))
    assert after == before
