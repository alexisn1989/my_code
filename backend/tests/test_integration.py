"""Cross-module integration tests that don't naturally belong to a single
unit-under-test file: a full scenario-to-report workflow, and multi-turn
reconciliation held across a real save/history chain.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.history import advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import SpendingCategory
from tests.conftest import SCENARIO_DIR


def test_new_scenario_submit_decision_resolve_inspect_report() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

    decisions = DecisionSet(
        expected_turn=0,
        expected_state_version=0,
        decisions=(
            BudgetDecision(
                corporate_rate_bps=3_000,
                spending_updates=(
                    SpendingUpdate(category=SpendingCategory.DEFENSE, amount=999_000_00),
                ),
            ),
        ),
    )
    save = advance_game(save, decisions)

    report = save.entries[-1].report()
    assert report is not None
    finance = report.finance
    assert finance is not None
    assert finance.reconciliation_status == "reconciled"
    assert finance.active_tax_policy.corporate_rate_bps == 3_000
    assert finance.active_spending_plan.defense == 999_000_00

    field_names = {c.field for c in finance.budget_changes}
    assert "corporate_rate_bps" in field_names
    assert "spending.defense" in field_names

    reason_ids = {e.reason_id for e in report.entries}
    assert "tax_rate_changed" in reason_ids
    assert "spending_category_changed" in reason_ids


def test_eight_sequential_turns_each_reconcile_and_history_stays_valid() -> None:
    from app.simulation.history import validate_history

    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)

    for turn in range(8):
        current = save.current_state()
        # Alternate: some turns submit a decision, some don't — reconciliation
        # must hold either way.
        if turn % 2 == 0:
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(BudgetDecision(personal_income_rate_bps=2_000 + turn * 10),),
            )
        else:
            decisions = DecisionSet(
                expected_turn=current.turn, expected_state_version=current.state_version
            )
        save = advance_game(save, decisions)

    assert save.current_turn() == 8
    assert len(save.entries) == 9
    assert validate_history(save) == []

    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.finance is not None
        assert report.finance.reconciliation_status == "reconciled"

    # Cash should have grown across 8 turns of a sustainable budget with no
    # borrowing — a coarse sanity check that the whole chain, not just each
    # turn in isolation, behaves as expected.
    final_treasury = save.current_state().world.countries["arken"].treasury
    opening_treasury = state.world.countries["arken"].treasury
    assert final_treasury.cash_on_hand > opening_treasury.cash_on_hand
    assert final_treasury.debt == opening_treasury.debt
