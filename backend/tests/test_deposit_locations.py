"""Resource deposits have a place on the map (map-resources slice).

Until this slice a deposit was a national aggregate with no location, so the strategic map and the
economy were two unrelated models of the same country. `ResourceDepositState.theater_id` closes
that, and the three things worth proving about it are proven here:

* every shipped scenario places its nine deposits on theaters the player actually holds, and
  places them in more than one, so "located" is not a synonym for "all in the capital";
* both new invariant codes are REACHABLE, from a real state -- an unknown theater and a
  foreign-held one;
* the report, the CLI and the state cannot disagree about where a deposit is, and a deposit cannot
  move during a turn (reconciliation group 55).

What this slice deliberately does NOT do is let location change a quantity. Extraction still reads
stock, capacity and labor and nothing else, which `test_location_does_not_change_extraction` pins
so the next gate's terrain rule has to be a visible change rather than an accidental one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import main
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.invariants import check_invariants
from app.simulation.reconciliation import reconcile_deposit_locations
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import GameState, PlayerCountryRef, ResourceCategory
from tests.conftest import SCENARIO_DIR

_SCENARIOS = ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml")
_TURNS = 3


def _load(scenario_file: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / scenario_file)


def _resolve_once(state: GameState):
    return resolve_turn(
        state,
        DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        ),
    )


def _with_deposit_at(state: GameState, category: ResourceCategory, theater_id: str) -> GameState:
    """`state` with one deposit relocated. Goes through a real `model_copy` of the tuple, so the
    result is a state the engine would accept structurally -- the point is to make the INVARIANT
    reject it, not the constructor."""
    player = state.world.countries[state.world.player_country_id]
    assert player.economy is not None
    deposits = tuple(
        deposit.model_copy(update={"theater_id": theater_id})
        if deposit.category is category
        else deposit
        for deposit in player.economy.resource_deposits
    )
    economy = player.economy.model_copy(update={"resource_deposits": deposits})
    countries = dict(state.world.countries)
    countries[player.id] = player.model_copy(update={"economy": economy})
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": countries})}
    )


@pytest.mark.parametrize("scenario_file", _SCENARIOS)
class TestEveryScenarioPlacesItsDeposits:
    def test_every_deposit_sits_on_a_theater_the_player_holds(self, scenario_file: str) -> None:
        state = _load(scenario_file)
        player = state.world.countries[state.world.player_country_id]
        assert player.economy is not None
        theaters = state.world.strategic_map.theaters
        for deposit in player.economy.resource_deposits:
            theater = theaters.get(deposit.theater_id)
            assert theater is not None, f"{deposit.category.value} -> {deposit.theater_id}"
            assert isinstance(theater.owner, PlayerCountryRef)
            assert theater.owner.country_id == player.id

    def test_the_deposits_are_spread_across_more_than_one_theater(self, scenario_file: str) -> None:
        """Anti-vacuity for the whole slice: placing all nine in the capital would satisfy every
        rule above while leaving location meaningless."""
        state = _load(scenario_file)
        player = state.world.countries[state.world.player_country_id]
        assert player.economy is not None
        used = {deposit.theater_id for deposit in player.economy.resource_deposits}
        assert len(used) >= 2, used

    def test_the_scenario_is_valid_under_every_invariant(self, scenario_file: str) -> None:
        assert check_invariants(_load(scenario_file)) == []


class TestBothInvariantCodesAreReachable:
    def test_a_deposit_on_a_theater_the_map_does_not_contain(self) -> None:
        state = _with_deposit_at(_load("tiny_valid.yaml"), ResourceCategory.GOLD, "no_such_place")
        codes = [violation.code for violation in check_invariants(state)]
        assert codes == ["resource_deposit_theater_unknown"]

    def test_a_deposit_on_a_foreign_held_theater(self) -> None:
        """The case the rule exists for: a country cannot mine what it does not hold. Reachable
        today only by authoring it -- nothing in this ruleset transfers a theater -- which is
        exactly why it is an invariant rather than a phase check."""
        state = _with_deposit_at(_load("tiny_valid.yaml"), ResourceCategory.GOLD, "kessia_south")
        violations = check_invariants(state)
        assert [violation.code for violation in violations] == [
            "resource_deposit_theater_not_owned_by_country"
        ]
        assert "kessia_south" in violations[0].message

    def test_a_valid_placement_produces_neither(self) -> None:
        """Anti-vacuity for both cases above."""
        state = _with_deposit_at(_load("tiny_valid.yaml"), ResourceCategory.GOLD, "arken_coast")
        assert check_invariants(state) == []


class TestTheReportSaysWhere:
    def test_every_row_carries_the_state_location_and_the_map_name(self) -> None:
        state = _load("tiny_valid.yaml")
        player = state.world.countries[state.world.player_country_id]
        assert player.economy is not None
        placed = {d.category: d.theater_id for d in player.economy.resource_deposits}
        theaters = state.world.strategic_map.theaters

        report = _resolve_once(state).report
        assert report.resources is not None
        for row in report.resources.deposits:
            assert row.theater_id == placed[row.category]
            assert row.theater_display_name == theaters[row.theater_id].display_name

    def test_the_cli_names_the_theater_on_both_surfaces(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`inspect` reads endowments from state and `resolve` prints the turn's report rows --
        two independently wired call sites, so both are checked."""
        scenario = str(SCENARIO_DIR / "tiny_valid.yaml")
        save0, save1 = tmp_path / "s0.json", tmp_path / "s1.json"

        assert main(["new", "--scenario", scenario, "--out", str(save0)]) == 0
        assert main(["inspect", "--state", str(save0)]) == 0
        assert "gold at Northern March:" in capsys.readouterr().out

        assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
        assert "gold at Northern March:" in capsys.readouterr().out


class TestLocationIsStableAndInert:
    def test_locations_do_not_change_across_resolved_turns(self) -> None:
        state = _load("tiny_valid.yaml")
        opening = {
            d.category: d.theater_id
            for d in state.world.countries[state.world.player_country_id].economy.resource_deposits
        }  # type: ignore[union-attr]
        save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
        for _ in range(_TURNS):
            current = save.current_state()
            save = advance_game(
                save,
                DecisionSet(
                    expected_turn=current.turn,
                    expected_state_version=current.state_version,
                    decisions=(),
                ),
            )
        closing_state = save.current_state()
        economy = closing_state.world.countries[closing_state.world.player_country_id].economy
        assert economy is not None
        assert {d.category: d.theater_id for d in economy.resource_deposits} == opening

    def test_location_does_not_change_extraction(self) -> None:
        """This slice ships the location and its enforcement WITHOUT a formula that reads it.
        Moving gold from the northern march to the coast must change nothing in the report except
        the two fields that say where it is -- which is what makes the next gate's terrain yield a
        deliberate change rather than something that crept in here.
        """
        baseline = _resolve_once(_load("tiny_valid.yaml")).report
        moved = _resolve_once(
            _with_deposit_at(_load("tiny_valid.yaml"), ResourceCategory.GOLD, "arken_coast")
        ).report
        assert baseline.resources is not None and moved.resources is not None

        baseline_rows = {row.category: row for row in baseline.resources.deposits}
        moved_rows = {row.category: row for row in moved.resources.deposits}
        for category, baseline_row in baseline_rows.items():
            moved_row = moved_rows[category]
            expected = baseline_row.model_dump(mode="json")
            actual = moved_row.model_dump(mode="json")
            if category is ResourceCategory.GOLD:
                assert actual.pop("theater_id") == "arken_coast"
                assert actual.pop("theater_display_name") == "Arken Coast"
                expected.pop("theater_id")
                expected.pop("theater_display_name")
            assert actual == expected, category

        assert baseline.production == moved.production
        assert baseline.finance == moved.finance


class TestGroup55:
    def _turn(self) -> tuple[GameState, GameState, object]:
        opening = _load("tiny_valid.yaml")
        resolution = _resolve_once(opening)
        return opening, resolution.state, resolution.report

    def test_a_clean_turn_reconciles(self) -> None:
        opening, closing, report = self._turn()
        assert (
            reconcile_deposit_locations(opening_state=opening, closing_state=closing, report=report)
            == []
        )

    def test_a_deposit_that_moved_during_the_turn_is_caught(self) -> None:
        opening, closing, report = self._turn()
        tampered = _with_deposit_at(closing, ResourceCategory.GOLD, "arken_coast")
        problems = reconcile_deposit_locations(
            opening_state=opening, closing_state=tampered, report=report
        )
        assert any("immobile" in problem for problem in problems)

    def test_a_report_row_pointing_somewhere_else_is_caught(self) -> None:
        opening, closing, report = self._turn()
        rows = tuple(
            row.model_copy(update={"theater_id": "arken_coast"})
            if row.category is ResourceCategory.GOLD
            else row
            for row in report.resources.deposits  # type: ignore[union-attr]
        )
        tampered_report = report.model_copy(  # type: ignore[attr-defined]
            update={"resources": report.resources.model_copy(update={"deposits": rows})}  # type: ignore[union-attr]
        )
        problems = reconcile_deposit_locations(
            opening_state=opening, closing_state=closing, report=tampered_report
        )
        assert any("but the closing state holds it at" in problem for problem in problems)

    def test_a_renamed_theater_on_a_report_row_is_caught(self) -> None:
        """The display name is carried for rendering, so it too has to be reconciled -- otherwise
        a surface could show a name the map never used and nothing would notice."""
        opening, closing, report = self._turn()
        rows = tuple(
            row.model_copy(update={"theater_display_name": "Somewhere Else"})
            if row.category is ResourceCategory.GOLD
            else row
            for row in report.resources.deposits  # type: ignore[union-attr]
        )
        tampered_report = report.model_copy(  # type: ignore[attr-defined]
            update={"resources": report.resources.model_copy(update={"deposits": rows})}  # type: ignore[union-attr]
        )
        problems = reconcile_deposit_locations(
            opening_state=opening, closing_state=closing, report=tampered_report
        )
        assert any("but the map calls it" in problem for problem in problems)

    def test_a_report_with_no_resources_is_a_problem_not_a_crash(self) -> None:
        opening, closing, report = self._turn()
        stripped = report.model_copy(update={"resources": None})  # type: ignore[attr-defined]
        problems = reconcile_deposit_locations(
            opening_state=opening, closing_state=closing, report=stripped
        )
        assert problems == [
            "turn report has no resources report to reconcile deposits against (group 55)"
        ]

    def test_a_missing_economy_is_a_problem_not_a_crash(self) -> None:
        """Every reconciler in this module compares already-parsed models and must return a
        problem string for a tampered save rather than raising."""
        opening, closing, report = self._turn()
        player = closing.world.countries[closing.world.player_country_id]
        countries = dict(closing.world.countries)
        countries[player.id] = player.model_construct(
            **{**player.model_dump(), "economy": None}  # type: ignore[arg-type]
        )
        tampered = closing.model_copy(
            update={
                "world": closing.world.model_construct(
                    **{**closing.world.model_dump(), "countries": countries}
                )
            }
        )
        problems = reconcile_deposit_locations(
            opening_state=opening, closing_state=tampered, report=report
        )
        assert any("cannot be reconciled" in problem for problem in problems)
