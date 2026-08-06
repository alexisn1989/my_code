"""End-to-end tests for the Phase 2C1 resource-extraction chain through the real engine:
report-closing-stocks-match-returned-state (T12, proving R2's same-step phase-3 write is
correct, not merely structural), two-independent-games determinism (T14), and exact
hand-computed calibration for both real scenarios including the corrected three-regime
`deficit_demo` timber trajectory (T20, R4/R8).

Phase 2C2 adds the physical-extraction-to-real-output bridge end to end: the accounting
identity proving extraction output is counted exactly once (T21), and the exact hand-computed
turn-26/turn-41 boundaries and turn-26..40 plateau for `deficit_demo`'s extraction-sector output
(T28/T29/T30) — see `data/scenarios/deficit_demo.yaml`'s header and
`docs/economy_methodology.md` for the underlying trajectory this pins.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.report import SectorProductionConstraint
from app.simulation.resolver import resolve_turn
from app.simulation.resource_extraction import DepositStatus
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import ResourceCategory, SectorCategory
from tests.conftest import SCENARIO_DIR

# --- T12: report closing stocks == returned state stocks, matched by category identity ----------


def test_report_closing_stocks_match_returned_state_every_turn() -> None:
    """R2: `_extract_resources` writes each deposit's closing stock into the working state in the
    same step that built the report row. Proven across 5 real turns, matched by
    `ResourceCategory` identity — never tuple position — against the state each entry actually
    stores, not merely asserted as a structural property of the code.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(5):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn, expected_state_version=current.state_version, decisions=()
        )
        save = advance_game(save, decisions)

    for entry in save.entries[1:]:
        report = entry.report()
        assert report is not None
        assert report.resources is not None
        entry_state = entry.state()
        player = entry_state.world.countries[entry_state.world.player_country_id]
        assert player.economy is not None
        stock_by_category = {
            d.category: d.remaining_stock for d in player.economy.resource_deposits
        }
        for deposit_report in report.resources.deposits:
            assert deposit_report.closing_stock == stock_by_category[deposit_report.category], (
                f"{deposit_report.category.value} at turn {entry.turn}"
            )


def test_no_hidden_one_turn_lag_between_labor_and_resource_extraction() -> None:
    """Same-turn linkage (mirrors `test_labor_to_production_linkage.py`'s equivalent test):
    `LaborMarketReport.sectors[EXTRACTION].allocated_workers` must equal
    `ResourceExtractionReport.extraction_sector_workers` for the very same turn, across a
    multi-turn run — never one turn behind.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
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
        assert report.resources is not None
        extraction_row = next(
            s for s in report.labor_market.sectors if s.category.value == "extraction"
        )
        assert extraction_row.allocated_workers == report.resources.extraction_sector_workers


# --- T14: two independent games byte-identical ----------------------------------------------------


def test_eight_turns_of_resource_extraction_are_byte_identical_across_two_runs() -> None:
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


# --- T20: resource-rich and resource-poor scenarios, hand-computed exactly ----------------------


def test_tiny_valid_resource_calibration_reproduces_every_hand_worked_figure_exactly() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    resources = resolution.report.resources
    assert resources is not None

    assert resources.extraction_sector_workers == 20_000
    assert resources.total_extraction_workers == 13_500
    assert resources.unassigned_resource_workers == 6_500

    expected = {
        ResourceCategory.TIMBER: (5_000_000, 80_000, 100_000, 4_980_000),
        ResourceCategory.IRON_ORE: (40_000_000, 0, 200_000, 39_800_000),
        ResourceCategory.COAL: (60_000_000, 0, 300_000, 59_700_000),
        ResourceCategory.CRUDE_OIL: (90_000_000, 0, 500_000, 89_500_000),
        ResourceCategory.NATURAL_GAS: (70_000_000, 0, 400_000, 69_600_000),
        ResourceCategory.URANIUM: (100_000, 0, 500, 99_500),
        ResourceCategory.COPPER: (30_000_000, 0, 150_000, 29_850_000),
        ResourceCategory.CRITICAL_MINERALS: (2_000_000, 0, 20_000, 1_980_000),
    }
    by_category = {d.category: d for d in resources.deposits}
    for category, (opening, regenerated, extracted, closing) in expected.items():
        row = by_category[category]
        assert row.opening_stock == opening, category.value
        assert row.regenerated == regenerated, category.value
        assert row.extracted == extracted, category.value
        assert row.closing_stock == closing, category.value
        assert row.status == DepositStatus.CAPACITY_CONSTRAINED, category.value
        # Conservation, exact, every deposit.
        assert row.opening_stock + row.regenerated == row.extracted + row.closing_stock


def test_deficit_demo_resource_calibration_reproduces_every_hand_worked_figure_exactly() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    resources = resolution.report.resources
    assert resources is not None

    assert resources.extraction_sector_workers == 10_000
    assert resources.total_extraction_workers == 800
    assert resources.unassigned_resource_workers == 9_200

    by_category = {d.category: d for d in resources.deposits}

    timber = by_category[ResourceCategory.TIMBER]
    assert timber.opening_stock == 200_000
    assert timber.regenerated == 5_000
    assert timber.available_stock == 205_000
    assert timber.extracted == 10_000
    assert timber.closing_stock == 195_000
    assert timber.status == DepositStatus.CAPACITY_CONSTRAINED

    iron_ore = by_category[ResourceCategory.IRON_ORE]
    assert iron_ore.opening_stock == 500_000
    assert iron_ore.regenerated == 0
    assert iron_ore.extracted == 20_000
    assert iron_ore.closing_stock == 480_000
    assert iron_ore.status == DepositStatus.CAPACITY_CONSTRAINED

    inactive_categories = {
        ResourceCategory.COAL,
        ResourceCategory.CRUDE_OIL,
        ResourceCategory.NATURAL_GAS,
        ResourceCategory.URANIUM,
        ResourceCategory.COPPER,
        ResourceCategory.CRITICAL_MINERALS,
    }
    for category in inactive_categories:
        row = by_category[category]
        assert row.opening_stock == 0
        assert row.extracted == 0
        assert row.closing_stock == 0
        assert row.status == DepositStatus.INACTIVE

    for row in resources.deposits:
        assert row.opening_stock + row.regenerated == row.extracted + row.closing_stock


class TestDeficitDemoTimberThreeRegimeTrajectoryThroughTheRealEngine:
    """Reproduces the exact worked trajectory from `deficit_demo.yaml`'s header and
    `docs/economy_methodology.md` (R4/R8), driven through the real resolver + history layer
    rather than the pure formulas directly (that fast-running proof lives in
    `test_resource_extraction.py`) — the end-to-end version of the same guarantee.
    """

    def _run(self, turns: int) -> list:
        state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        rows = []
        for _ in range(turns):
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            )
            save = advance_game(save, decisions)
            report = save.entries[-1].report()
            assert report is not None
            assert report.resources is not None
            timber = next(
                d for d in report.resources.deposits if d.category == ResourceCategory.TIMBER
            )
            rows.append(timber)
        return rows

    def test_resolutions_1_to_39_are_capacity_constrained(self) -> None:
        rows = self._run(39)
        for i, row in enumerate(rows, start=1):
            assert row.status == DepositStatus.CAPACITY_CONSTRAINED, f"resolution {i}"
            assert row.extracted == 10_000, f"resolution {i}"
        assert rows[38].closing_stock == 5_000  # resolution 39

    def test_resolution_40_is_the_stock_constrained_boundary(self) -> None:
        rows = self._run(40)
        boundary = rows[39]
        assert boundary.opening_stock == 5_000
        assert boundary.available_stock == 10_000
        assert boundary.extracted == 10_000
        assert boundary.closing_stock == 0
        assert boundary.status == DepositStatus.STOCK_CONSTRAINED

    def test_resolutions_41_plus_are_the_steady_state(self) -> None:
        rows = self._run(45)
        for i, row in enumerate(rows[40:], start=41):
            assert row.opening_stock == 0, f"resolution {i}"
            assert row.regenerated == 5_000, f"resolution {i}"
            assert row.extracted == 5_000, f"resolution {i}"
            assert row.closing_stock == 0, f"resolution {i}"
            assert row.status == DepositStatus.STOCK_CONSTRAINED, f"resolution {i}"
            assert row.status != DepositStatus.DEPLETED, f"resolution {i}"


# --- Phase 2C2, T21: the direct accounting identity — extraction output is counted exactly ------
# --- once, end to end through the real engine ----------------------------------------------------


def test_tiny_valid_extraction_contribution_appears_exactly_once_in_total_gross_output() -> None:
    """Σ(deposit.real_output_contribution) == extraction_sector_real_output ==
    production.sectors[EXTRACTION].actual_output, and this exact figure appears in
    total_gross_output exactly once (proven by subtracting every other sector's contribution)."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    resources = resolution.report.resources
    production = resolution.report.production
    assert resources is not None
    assert production is not None

    summed_contributions = sum(d.real_output_contribution for d in resources.deposits)
    assert summed_contributions == resources.extraction_sector_real_output == 2_000_000_000

    extraction_row = next(s for s in production.sectors if s.category is SectorCategory.EXTRACTION)
    assert extraction_row.actual_output == resources.extraction_sector_real_output
    assert extraction_row.output_basis.value == "resource_extraction"
    assert extraction_row.constraint is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED

    other_sectors_total = sum(
        s.actual_output for s in production.sectors if s.category is not SectorCategory.EXTRACTION
    )
    assert production.total_gross_output == other_sectors_total + extraction_row.actual_output


class TestDeficitDemoExtractionSectorOutputTrajectoryThroughTheRealEngine:
    """Phase 2C2's extraction-sector output tracks the timber/iron_ore physical trajectory
    (`TestDeficitDemoTimberThreeRegimeTrajectoryThroughTheRealEngine` above) through the exact
    hand-worked figures from the plan's §8: 500,000,000 through turn 25, stepping to
    100,000,000 at turn 26 (iron_ore depletion), holding through turn 40, then stepping to
    50,000,000 at turn 41 (timber's steady state).
    """

    def _run(self, turns: int) -> list:
        state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        reports = []
        for _ in range(turns):
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            )
            save = advance_game(save, decisions)
            report = save.entries[-1].report()
            assert report is not None
            assert report.resources is not None
            reports.append(report.resources)
        return reports

    def test_turns_1_to_25_hold_at_500_million(self) -> None:
        reports = self._run(25)
        for i, resources in enumerate(reports, start=1):
            assert resources.extraction_sector_real_output == 500_000_000, f"turn {i}"
            assert resources.extraction_sector_potential_output == 500_000_000, f"turn {i}"

    def test_turn_26_is_the_first_divergent_turn_at_100_million(self) -> None:
        reports = self._run(26)
        turn_25, turn_26 = reports[24], reports[25]
        assert turn_25.extraction_sector_real_output == 500_000_000
        assert turn_26.extraction_sector_real_output == 100_000_000
        assert turn_26.extraction_sector_potential_output == 100_000_000

    def test_turns_26_to_40_plateau_at_100_million(self) -> None:
        reports = self._run(40)
        for i, resources in enumerate(reports[25:40], start=26):
            assert resources.extraction_sector_real_output == 100_000_000, f"turn {i}"
            assert resources.extraction_sector_potential_output == 100_000_000, f"turn {i}"

    def test_turn_41_is_the_second_boundary_at_50_million(self) -> None:
        reports = self._run(41)
        turn_40, turn_41 = reports[39], reports[40]
        assert turn_40.extraction_sector_real_output == 100_000_000
        assert turn_41.extraction_sector_real_output == 50_000_000
        assert turn_41.extraction_sector_potential_output == 50_000_000

    def test_extraction_row_stays_physical_resource_constrained_throughout(self) -> None:
        """Labor never binds in this fixture (a known, documented limitation, §18) — every turn
        classifies as PHYSICAL_RESOURCE_CONSTRAINED, never LABOR_CONSTRAINED, across all three
        regimes."""
        state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for i in range(1, 46):
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            )
            save = advance_game(save, decisions)
            report = save.entries[-1].report()
            assert report is not None
            assert report.production is not None
            extraction_row = next(
                s for s in report.production.sectors if s.category is SectorCategory.EXTRACTION
            )
            assert (
                extraction_row.constraint
                is SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED
            ), f"turn {i}"
