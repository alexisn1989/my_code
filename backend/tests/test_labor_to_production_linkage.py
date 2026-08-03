"""End-to-end tests for the labor allocation -> production -> tax-base derivation -> revenue
chain: same-turn linkage (no hidden one-turn lag), calibration exactness against both real
scenario fixtures (labor allocation must reproduce the exact R1-verified figures, and every
downstream production/tax-base/revenue figure must stay unchanged from Phase 2B2), determinism,
and that a labor-supply change moves production/bases/revenue the same turn it applies.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import SCENARIO_DIR, make_game_state


def test_no_hidden_one_turn_lag_across_multiple_turns() -> None:
    """Every turn's report must show current-turn labor allocation feeding current-turn
    production immediately — never one turn behind. `TurnReport`'s own cross-report validator
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
        assert report.labor_market is not None
        assert report.production is not None
        allocated_by_category = {
            s.category: s.allocated_workers for s in report.labor_market.sectors
        }
        for row in report.production.sectors:
            assert row.employed_workers == allocated_by_category[row.category]


def test_tiny_valid_calibration_reproduces_r1_labor_market_figures_exactly() -> None:
    """The re-authored `tiny_valid.yaml` economy is calibrated (R1) so labor allocation lands
    at exactly 10.00% unemployment, while every Phase 2B2 output/tax-base/revenue figure stays
    byte-for-byte identical.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    labor_market = resolution.report.labor_market
    finance = resolution.report.finance
    production = resolution.report.production
    assert labor_market is not None
    assert finance is not None
    assert production is not None

    assert labor_market.effective_labor_force == 600_000
    assert labor_market.total_labor_demand == 540_000
    assert labor_market.total_employment == 540_000
    assert labor_market.unemployed_workers == 60_000
    assert labor_market.unfilled_jobs == 0
    assert labor_market.unemployment_rate_bps == 1_000  # exactly 10.00%

    # Unchanged from Phase 2B2's exact calibration.
    assert production.total_gross_output == 20_000_000_000
    assert finance.tax_bases.personal_income == 4_000_000_000
    assert finance.tax_bases.corporate_profit == 2_000_000_000
    assert finance.tax_bases.taxable_consumption == 3_000_000_000
    assert finance.revenue.total_revenue == 1_440_000_000
    assert finance.reconciliation_status == "reconciled"


def test_deficit_demo_calibration_reproduces_r1_labor_market_figures_exactly() -> None:
    """The re-authored `deficit_demo.yaml` economy is calibrated (R1) so labor allocation lands
    at exactly 10.00% unemployment, while every Phase 2B2 output/revenue/interest/borrowing/
    reconciliation figure stays byte-for-byte identical, including the documented worked example.
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    labor_market = resolution.report.labor_market
    finance = resolution.report.finance
    production = resolution.report.production
    assert labor_market is not None
    assert finance is not None
    assert production is not None

    assert labor_market.effective_labor_force == 200_000
    assert labor_market.total_labor_demand == 180_000
    assert labor_market.total_employment == 180_000
    assert labor_market.unemployed_workers == 20_000
    assert labor_market.unfilled_jobs == 0
    assert labor_market.unemployment_rate_bps == 1_000  # exactly 10.00%

    # Unchanged from Phase 2A/2B2's documented worked example.
    assert production.total_gross_output == 4_000_000_000
    assert finance.tax_bases.personal_income == 1_000_000_000
    assert finance.tax_bases.corporate_profit == 500_000_000
    assert finance.tax_bases.taxable_consumption == 800_000_000
    assert finance.revenue.total_revenue == 251_200_000
    assert finance.total_program_spending == 670_000_000
    assert finance.quarterly_interest_expense == 40_000_000
    assert finance.pre_financing_balance == -458_800_000
    assert finance.new_borrowing == 408_800_000
    assert finance.closing_cash == 0
    assert finance.closing_debt == 2_408_800_000
    assert finance.reconciliation_status == "reconciled"


def test_eight_turns_of_labor_production_derivation_finance_are_byte_identical_across_two_runs() -> (
    None
):
    """Determinism, extended to the full four-report chain: two independent 8-turn runs from
    the same scenario/seed/decisions must produce byte-identical labor-market, production,
    tax-base derivation, and finance reports at every turn.
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


def test_labor_supply_change_moves_production_and_revenue_the_same_turn() -> None:
    """The required positive-direction property: a change to `effective_labor_force_share_bps`
    (the one legitimate lever on labor supply) must move production output, derived tax bases,
    and revenue immediately — the same turn it applies, not one turn later.
    """
    low_state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    player_id = low_state.world.player_country_id
    low_country = low_state.world.countries[player_id]
    assert low_country.economy is not None
    # Cut the labor-force share sharply so demand (540,000) is no longer fully met.
    scarce_economy = low_country.economy.model_copy(
        update={"effective_labor_force_share_bps": 1_000}  # 10% instead of 60%
    )
    low_state.world.countries[player_id] = low_country.model_copy(
        update={"economy": scarce_economy}
    )
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    scarce_resolution = resolve_turn(low_state, decisions)

    abundant_state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    abundant_resolution = resolve_turn(abundant_state, decisions)

    scarce_labor = scarce_resolution.report.labor_market
    abundant_labor = abundant_resolution.report.labor_market
    scarce_production = scarce_resolution.report.production
    abundant_production = abundant_resolution.report.production
    scarce_finance = scarce_resolution.report.finance
    abundant_finance = abundant_resolution.report.finance
    assert scarce_labor is not None
    assert abundant_labor is not None
    assert scarce_production is not None
    assert abundant_production is not None
    assert scarce_finance is not None
    assert abundant_finance is not None

    assert scarce_labor.effective_labor_force == 100_000  # floor(1,000,000 * 1000 / 10_000)
    assert scarce_labor.total_employment < abundant_labor.total_employment
    assert scarce_production.total_gross_output < abundant_production.total_gross_output
    assert scarce_finance.tax_bases != abundant_finance.tax_bases
    assert scarce_finance.revenue.total_revenue < abundant_finance.revenue.total_revenue
