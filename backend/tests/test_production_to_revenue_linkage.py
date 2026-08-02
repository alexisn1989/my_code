"""End-to-end tests for the production -> tax-base derivation -> revenue chain: same-turn
linkage (no hidden one-turn lag), and calibration exactness against both real scenario
fixtures (production-derived bases must reproduce the original Phase 2A hand-checked bases
and revenue figures exactly).
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import SCENARIO_DIR, make_game_state


def test_no_hidden_one_turn_lag_across_multiple_turns() -> None:
    """Every turn's report must show current-turn production feeding current-turn
    derivation immediately — never one turn behind. `TurnReport`'s own R1 validator
    already enforces this equality on every parse; this test exercises it across a real
    multi-turn run (not just a single turn 0) as an explicit regression guard.
    """
    save = new_game(
        make_game_state(turn=0, state_version=0), save_format_version=SAVE_FORMAT_VERSION
    )
    for _ in range(5):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn, expected_state_version=current.state_version, decisions=()
        )
        save = advance_game(save, decisions)

    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.production is not None
        assert report.tax_base_derivation is not None
        production_by_category = {s.category: s.actual_output for s in report.production.sectors}
        for row in report.tax_base_derivation.sectors:
            assert row.actual_output == production_by_category[row.category]


def test_tiny_valid_calibration_reproduces_original_phase_2a_tax_bases_exactly() -> None:
    """The re-authored `tiny_valid.yaml` economy is calibrated so derived bases equal the
    original Phase 2A authored bases (personal=4,000,000,000, corporate=2,000,000,000,
    consumption=3,000,000,000), so every downstream Phase 2A figure stays valid unchanged.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    finance = resolution.report.finance
    derivation = resolution.report.tax_base_derivation
    assert finance is not None
    assert derivation is not None

    assert finance.tax_bases.personal_income == 4_000_000_000
    assert finance.tax_bases.corporate_profit == 2_000_000_000
    assert finance.tax_bases.taxable_consumption == 3_000_000_000
    assert derivation.derived_tax_bases == finance.tax_bases

    # Unchanged from the original Phase 2A hand-checked figure.
    assert finance.revenue.total_revenue == 1_440_000_000
    assert finance.reconciliation_status == "reconciled"


def test_deficit_demo_calibration_reproduces_original_phase_2a_tax_bases_exactly() -> None:
    """The re-authored `deficit_demo.yaml` economy is calibrated so derived bases equal the
    original Phase 2A authored bases (personal=1,000,000,000, corporate=500,000,000,
    consumption=800,000,000) — reproducing the fixture's documented worked example exactly,
    including the borrowing outcome.
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    finance = resolution.report.finance
    derivation = resolution.report.tax_base_derivation
    assert finance is not None
    assert derivation is not None

    assert finance.tax_bases.personal_income == 1_000_000_000
    assert finance.tax_bases.corporate_profit == 500_000_000
    assert finance.tax_bases.taxable_consumption == 800_000_000
    assert derivation.derived_tax_bases == finance.tax_bases

    # Unchanged from the original Phase 2A/2B1 documented worked example.
    assert finance.revenue.total_revenue == 251_200_000
    assert finance.total_program_spending == 670_000_000
    assert finance.quarterly_interest_expense == 40_000_000
    assert finance.pre_financing_balance == -458_800_000
    assert finance.new_borrowing == 408_800_000
    assert finance.closing_cash == 0
    assert finance.closing_debt == 2_408_800_000
    assert finance.reconciliation_status == "reconciled"


def test_eight_turns_of_production_derivation_finance_are_byte_identical_across_two_runs() -> None:
    """Determinism, extended to the full three-report chain: two independent 8-turn runs
    from the same scenario/seed/decisions must produce byte-identical production, tax-base
    derivation, and finance reports at every turn — not just finance alone, as Phase 2A's
    determinism tests already covered.
    """

    def _run_eight_turns() -> list[str]:
        state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for _ in range(8):
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            )
            save = advance_game(save, decisions)
        return [entry.report_json for entry in save.entries[1:] if entry.report_json is not None]

    first_run = _run_eight_turns()
    second_run = _run_eight_turns()
    assert first_run == second_run
    assert len(first_run) == 8
