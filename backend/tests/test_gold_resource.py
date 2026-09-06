"""The ninth resource category, end to end (map-resources slice, ruleset 0.16.0).

`gold` is the first category added since Phase 2C1 authored the original eight, so these tests
cover the two things such an addition can get wrong that nothing else here would catch: the
catalogue itself (order, unit, renewability, per-scenario authoring), and the CALIBRATION claim
that adding it left every shipped scenario's fiscal position numerically untouched.

The second is the load-bearing one. `tiny_valid`/`decree_state` offset gold's output contribution
against `crude_oil`'s coefficient precisely so the extraction sector's total, and therefore gross
output, tax bases, revenue and treasury, do not move; `deficit_demo` authors gold at zero and needs
no offset. If a future edit changes gold's stock, capacity, per-worker yield or coefficient without
re-doing that offset, these tests fail here -- naming the calibration -- rather than surfacing as an
unexplained treasury delta in some unrelated fiscal test.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.resolver import resolve_turn
from app.simulation.resource_extraction import DepositStatus
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    RESOURCE_UNITS,
    ResourceCategory,
)
from tests.conftest import SCENARIO_DIR

_PRODUCING = ("tiny_valid.yaml", "decree_state.yaml")
_ALL_SCENARIOS = (*_PRODUCING, "deficit_demo.yaml")

# The two figures the offset exists to hold, for the two scenarios that author producing gold.
_EXTRACTION_SECTOR_OUTPUT = 2_000_000_000
_TOTAL_GROSS_OUTPUT = 20_000_000_000
_GOLD_CONTRIBUTION = 50_000_000


def _resolve_once(scenario_file: str):
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    return resolve_turn(state, decisions).report


class TestTheCatalogue:
    def test_gold_is_the_last_category_in_canonical_order(self) -> None:
        """Appended, not inserted -- so every pre-existing category keeps its canonical position
        and no earlier pairwise ordering silently changed meaning."""
        assert tuple(ResourceCategory)[-1] is ResourceCategory.GOLD
        assert tuple(ResourceCategory)[:-1] == (
            ResourceCategory.TIMBER,
            ResourceCategory.IRON_ORE,
            ResourceCategory.COAL,
            ResourceCategory.CRUDE_OIL,
            ResourceCategory.NATURAL_GAS,
            ResourceCategory.URANIUM,
            ResourceCategory.COPPER,
            ResourceCategory.CRITICAL_MINERALS,
        )

    def test_gold_has_its_own_physical_unit(self) -> None:
        assert RESOURCE_UNITS[ResourceCategory.GOLD] == "kg"

    def test_gold_is_not_renewable(self) -> None:
        """Ore in the ground does not grow back, so gold takes the nonrenewable path: no
        `regeneration_per_turn`, no `stock_ceiling`, monotonic depletion. Timber remains the only
        renewable."""
        assert ResourceCategory.GOLD not in RENEWABLE_RESOURCES
        assert frozenset({ResourceCategory.TIMBER}) == RENEWABLE_RESOURCES


class TestEveryScenarioAuthorsIt:
    @pytest.mark.parametrize("scenario_file", _ALL_SCENARIOS)
    def test_gold_has_both_a_deposit_and_a_coefficient(self, scenario_file: str) -> None:
        state = load_scenario_file(SCENARIO_DIR / scenario_file)
        player = state.world.countries[state.world.player_country_id]
        assert player.economy is not None
        deposits = {d.category: d for d in player.economy.resource_deposits}
        coefficients = {c.category: c for c in player.economy.resource_output_coefficients}
        assert ResourceCategory.GOLD in deposits
        assert ResourceCategory.GOLD in coefficients
        assert deposits[ResourceCategory.GOLD].regeneration_per_turn == 0
        assert deposits[ResourceCategory.GOLD].stock_ceiling is None

    @pytest.mark.parametrize("scenario_file", _PRODUCING)
    def test_the_producing_scenarios_actually_extract_gold(self, scenario_file: str) -> None:
        """Not merely present in the catalogue: 500 miners produce 500 kg on turn 1, and the
        deposit is capacity-bound rather than starved of labor."""
        report = _resolve_once(scenario_file)
        assert report.resources is not None
        gold = next(d for d in report.resources.deposits if d.category is ResourceCategory.GOLD)
        assert gold.allocated_workers == 500
        assert gold.extracted == 500
        assert gold.status is DepositStatus.CAPACITY_CONSTRAINED
        assert gold.real_output_contribution == _GOLD_CONTRIBUTION

    def test_deficit_demo_extracts_none(self) -> None:
        """A resource-poor country declares gold at zero rather than omitting it -- the same
        no-ambiguous-missing-vs-zero rule its six other empty categories already follow."""
        report = _resolve_once("deficit_demo.yaml")
        assert report.resources is not None
        gold = next(d for d in report.resources.deposits if d.category is ResourceCategory.GOLD)
        assert gold.extracted == 0
        assert gold.allocated_workers == 0
        assert gold.real_output_contribution == 0


class TestTheOffsetHolds:
    """Gold is offset, not added on top. These are the assertions a future re-tune has to face."""

    @pytest.mark.parametrize("scenario_file", _PRODUCING)
    def test_extraction_and_gross_output_are_unchanged_by_gold(self, scenario_file: str) -> None:
        report = _resolve_once(scenario_file)
        assert report.resources is not None
        assert report.resources.extraction_sector_real_output == _EXTRACTION_SECTOR_OUTPUT
        assert report.resources.extraction_sector_potential_output == _EXTRACTION_SECTOR_OUTPUT
        assert report.production is not None
        assert report.production.total_gross_output == _TOTAL_GROSS_OUTPUT

    @pytest.mark.parametrize("scenario_file", _PRODUCING)
    def test_gold_is_paid_for_out_of_crude_oil(self, scenario_file: str) -> None:
        """The offset made explicit: crude_oil's contribution is exactly `_GOLD_CONTRIBUTION`
        lower than the 600,000,000 it carried before gold existed, and gold contributes exactly
        that. Asserting the pair, rather than only the total, is what stops a future edit from
        holding the total by moving some other deposit instead and quietly rewriting what oil
        means in these fixtures."""
        report = _resolve_once(scenario_file)
        assert report.resources is not None
        by_category = {d.category: d for d in report.resources.deposits}
        oil = by_category[ResourceCategory.CRUDE_OIL]
        gold = by_category[ResourceCategory.GOLD]
        assert oil.real_output_contribution == 600_000_000 - _GOLD_CONTRIBUTION
        assert gold.real_output_contribution == _GOLD_CONTRIBUTION

    @pytest.mark.parametrize("scenario_file", _PRODUCING)
    def test_gold_takes_its_miners_from_the_unassigned_slack(self, scenario_file: str) -> None:
        """The other half of "nothing else moved": the extraction sector had 6,500 workers spare,
        gold's 500 come out of that, and no other deposit's allocation changes. If gold's labor
        demand ever grows past the slack, largest-remainder would start taking workers from other
        deposits and their extracted quantities would move -- which this catches."""
        report = _resolve_once(scenario_file)
        assert report.resources is not None
        assert report.resources.total_extraction_workers == 14_000
        assert report.resources.unassigned_resource_workers == 6_000
        assert report.resources.unassigned_resource_workers > 0


class TestDepletion:
    def test_gold_declines_by_exactly_what_was_extracted_every_turn(self) -> None:
        """Nonrenewable conservation for the new category specifically: opening - extracted ==
        closing, with no regeneration term, across five real turns of the engine."""
        state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for _ in range(5):
            current = save.current_state()
            save = advance_game(
                save,
                DecisionSet(
                    expected_turn=current.turn,
                    expected_state_version=current.state_version,
                    decisions=(),
                ),
            )

        for entry in save.entries[1:]:
            report = entry.report()
            assert report is not None and report.resources is not None
            gold = next(d for d in report.resources.deposits if d.category is ResourceCategory.GOLD)
            assert gold.regenerated == 0
            assert gold.opening_stock - gold.extracted == gold.closing_stock

        final = save.current_state()
        player = final.world.countries[final.world.player_country_id]
        assert player.economy is not None
        remaining = {d.category: d.remaining_stock for d in player.economy.resource_deposits}
        assert remaining[ResourceCategory.GOLD] == 250_000 - 5 * 500
