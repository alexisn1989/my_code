"""Military Movement, commit 9 -- determinism, insertion-order independence, and persistence.

Deliberately not a second pass over commits 5 to 8. Commit 5 proved one turn deterministic in one
scenario and one formation-mapping insertion order; this is the full matrix the frozen sequence
assigns here: several turns, all three shipped scenarios, movement in both directions, and the
authored collections whose order must never reach a digest.

Everything is asserted on CANONICAL BYTES, because that is what the save's hash chain covers. A
difference that canonical JSON cannot see is not a difference this engine can persist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.decisions import (
    DecisionSet,
    FormationMovementOrder,
    MilitaryMovementDecision,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

#: Per scenario: player country, formation id, capital, one flank reachable from it.
SCENARIO_SHAPE: dict[str, tuple[str, str, str, str]] = {
    "tiny_valid": ("arken", "arken_first_army", "arken_capital", "arken_north"),
    "decree_state": ("valdrun", "valdrun_first_army", "valdrun_capital", "valdrun_east"),
    "deficit_demo": ("strapped", "strapped_first_army", "home_capital", "home_port"),
}

ALL_SCENARIOS = sorted(SCENARIO_SHAPE)

#: Enough turns to re-resolve against a state a previous movement produced, in both directions.
TURNS = 4


def _location(state: GameState, country_id: str, formation_id: str) -> str:
    military = state.world.countries[country_id].military
    assert military is not None
    return military.formations[formation_id].location_theater_id


def _run(scenario_id: str, turns: int = TURNS) -> tuple[GameState, list[str]]:
    """Resolve `turns` turns, moving the formation back and forth, and return the closing state
    with each turn's canonical report bytes.

    Alternating means turn 2 onward resolves against a state a previous MOVEMENT produced, rather
    than replaying turn 0 several times -- which would prove only that one turn is repeatable.
    """
    country_id, formation_id, capital, flank = SCENARIO_SHAPE[scenario_id]
    state = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
    reports: list[str] = []

    for _ in range(turns):
        here = _location(state, country_id, formation_id)
        destination = flank if here == capital else capital
        decisions = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=(
                MilitaryMovementDecision(
                    orders=(
                        FormationMovementOrder(
                            formation_id=formation_id, destination_theater_id=destination
                        ),
                    )
                ),
            ),
        )
        resolution = resolve_turn(state, decisions)
        state = resolution.state
        reports.append(canonical_dumps(resolution.report.model_dump(mode="json")))

    return state, reports


class TestDeterminismAcrossTurnsAndScenarios:
    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_two_independent_runs_agree_byte_for_byte(self, scenario_id: str) -> None:
        first_state, first_reports = _run(scenario_id)
        second_state, second_reports = _run(scenario_id)

        assert first_reports == second_reports
        assert canonical_dumps(first_state.model_dump(mode="json")) == canonical_dumps(
            second_state.model_dump(mode="json")
        )

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_the_matrix_actually_moves_the_formation_both_ways(self, scenario_id: str) -> None:
        """Anti-vacuity: identical bytes prove nothing if no movement was applied. Each turn must
        carry exactly one row, and the destinations must alternate."""
        country_id, formation_id, capital, flank = SCENARIO_SHAPE[scenario_id]
        state = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
        assert _location(state, country_id, formation_id) == capital

        destinations: list[str] = []
        for _ in range(TURNS):
            here = _location(state, country_id, formation_id)
            destination = flank if here == capital else capital
            resolution = resolve_turn(
                state,
                DecisionSet(
                    expected_turn=state.turn,
                    expected_state_version=state.state_version,
                    decisions=(
                        MilitaryMovementDecision(
                            orders=(
                                FormationMovementOrder(
                                    formation_id=formation_id,
                                    destination_theater_id=destination,
                                ),
                            )
                        ),
                    ),
                ),
            )
            assert resolution.report.movement is not None
            assert len(resolution.report.movement.movements) == 1
            destinations.append(destination)
            state = resolution.state

        assert destinations == [flank, capital, flank, capital][:TURNS]

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_a_quiet_run_and_a_movement_run_are_not_the_same(self, scenario_id: str) -> None:
        """The other half of anti-vacuity: if movement made no difference to the persisted bytes,
        every determinism assertion above would hold for the wrong reason."""
        country_id, _, _, _ = SCENARIO_SHAPE[scenario_id]
        moved, _ = _run(scenario_id, turns=1)

        quiet_state = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
        quiet = resolve_turn(
            quiet_state,
            DecisionSet(
                expected_turn=quiet_state.turn,
                expected_state_version=quiet_state.state_version,
                decisions=(),
            ),
        ).state

        assert canonical_dumps(moved.model_dump(mode="json")) != canonical_dumps(
            quiet.model_dump(mode="json")
        )


def _reordered_map(state: GameState, *, theaters: bool) -> GameState:
    """The same map with its authored collections rebuilt in reverse order.

    Reversal is the strongest single perturbation available: it changes every pairwise position at
    once, so a comparison that survives it cannot be depending on any of them.
    """
    strategic_map = state.world.strategic_map
    update: dict[str, object] = {}
    if theaters:
        update["theaters"] = dict(reversed(list(strategic_map.theaters.items())))
    copied = state.model_copy(deep=True)
    copied.world.strategic_map = strategic_map.model_copy(update=update)
    return copied


class TestInsertionOrderCannotReachTheOutput:
    """Every collection below is a mapping or an authored sequence the engine sorts or addresses by
    key. If any of them reached a digest, a hash-covered payload would depend on the order someone
    happened to type YAML in."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_formation_mapping_order_is_irrelevant(self, scenario_id: str) -> None:
        country_id, formation_id, capital, flank = SCENARIO_SHAPE[scenario_id]
        results = []
        for reverse in (False, True):
            state = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
            military = state.world.countries[country_id].military
            assert military is not None
            shipped = military.formations[formation_id]
            second = shipped.model_copy(
                update={"display_name": "Second Army", "location_theater_id": capital}
            )
            pairs = [(formation_id, shipped), ("zz_second_army", second)]
            state.world.countries[country_id].military = military.model_copy(
                update={"formations": dict(reversed(pairs) if reverse else pairs)}
            )
            resolution = resolve_turn(
                state,
                DecisionSet(
                    expected_turn=state.turn,
                    expected_state_version=state.state_version,
                    decisions=(
                        MilitaryMovementDecision(
                            orders=(
                                FormationMovementOrder(
                                    formation_id=formation_id, destination_theater_id=flank
                                ),
                            )
                        ),
                    ),
                ),
            )
            results.append(
                (
                    canonical_dumps(resolution.report.model_dump(mode="json")),
                    canonical_dumps(resolution.state.model_dump(mode="json")),
                )
            )
        assert results[0] == results[1]

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_theater_mapping_order_is_irrelevant(self, scenario_id: str) -> None:
        _, formation_id, _, flank = SCENARIO_SHAPE[scenario_id]
        base = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
        decisions = DecisionSet(
            expected_turn=base.turn,
            expected_state_version=base.state_version,
            decisions=(
                MilitaryMovementDecision(
                    orders=(
                        FormationMovementOrder(
                            formation_id=formation_id, destination_theater_id=flank
                        ),
                    )
                ),
            ),
        )
        straight = resolve_turn(base, decisions)
        reversed_run = resolve_turn(_reordered_map(base, theaters=True), decisions)

        assert canonical_dumps(straight.report.model_dump(mode="json")) == canonical_dumps(
            reversed_run.report.model_dump(mode="json")
        )

    def test_routes_have_no_insertion_order_to_be_independent_of(self) -> None:
        """Routes are the exception, and for a stronger reason than independence.

        `StrategicMapState` REJECTS a noncanonical route sequence at construction
        (`route_not_canonical`) rather than sorting it, so there is no second ordering a caller
        could supply and no digest that could depend on one. Asserting "reversing routes changes
        nothing" would be untestable here -- the reversed map does not exist.
        """
        from pydantic import ValidationError

        base = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        strategic_map = base.world.strategic_map

        with pytest.raises(ValidationError, match="route_not_canonical"):
            strategic_map.model_copy(
                update={"routes": tuple(reversed(strategic_map.routes))}
            ).model_validate(
                strategic_map.model_copy(
                    update={"routes": tuple(reversed(strategic_map.routes))}
                ).model_dump()
            )

    def test_the_reordering_helper_actually_reorders(self) -> None:
        """Anti-vacuity: a helper that quietly returned its input would make all three pass."""
        base = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        shuffled = _reordered_map(base, theaters=True)

        assert list(shuffled.world.strategic_map.theaters) != list(
            base.world.strategic_map.theaters
        )


class TestPersistenceOfAnAppliedMovement:
    """Commit 5 proved one round trip in one scenario. This proves the record survives disk in all
    three, and that the RELOADED chain still reconciles -- `validate_history` now runs Group 54, so
    a movement that did not persist faithfully fails here rather than silently."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIOS)
    def test_a_movement_survives_a_write_and_a_re_read(
        self, scenario_id: str, tmp_path: Path
    ) -> None:
        from app.cli import render_entry
        from app.saves import read_save_file, write_save_atomic
        from app.simulation.history import advance_game, new_game, validate_history
        from app.simulation.save_format import (
            SAVE_FORMAT_VERSION,
            dump_save_json,
            load_save_json,
        )

        country_id, formation_id, capital, flank = SCENARIO_SHAPE[scenario_id]
        state = load_scenario_file(SCENARIOS_DIR / f"{scenario_id}.yaml")
        save = advance_game(
            new_game(state, save_format_version=SAVE_FORMAT_VERSION),
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(
                    MilitaryMovementDecision(
                        orders=(
                            FormationMovementOrder(
                                formation_id=formation_id, destination_theater_id=flank
                            ),
                        )
                    ),
                ),
            ),
        )

        path = tmp_path / "save.json"
        write_save_atomic(path, dump_save_json(save).encode("utf-8"))
        reloaded = load_save_json(read_save_file(path), source=str(path))

        # The chain still reconciles, group 54 included.
        assert validate_history(reloaded) == []

        report = reloaded.entries[-1].report()
        assert report is not None and report.movement is not None
        row = report.movement.movements[0]
        assert row.formation_id == formation_id
        assert row.origin_theater_id == capital
        assert row.destination_theater_id == flank
        # Both snapshotted names survive, which is what lets a historical turn render itself.
        assert row.origin_theater_display_name
        assert row.destination_theater_display_name

        entry = next(e for e in report.entries if e.reason_id == "formation_moved")
        assert entry.params["origin_theater_display_name"] == row.origin_theater_display_name
        assert entry.params["destination_theater_display_name"] == (
            row.destination_theater_display_name
        )
        # Rendered from the reloaded entry alone -- no state is in scope to resolve a name from.
        assert render_entry(entry) == (
            f"{row.display_name} moved from {row.origin_theater_display_name} "
            f"to {row.destination_theater_display_name}."
        )

        # And the formation really is where the row says it went.
        assert _location(reloaded.current_state(), country_id, formation_id) == flank

    def test_a_save_with_a_movement_declares_this_builds_versions(self, tmp_path: Path) -> None:
        """The one compatibility statement neither commit 3 nor the campaign-identity tests make.
        Commit 3 owns the `0.14.0` rejection; this owns the positive direction."""
        from app.simulation.history import advance_game, new_game
        from app.simulation.save_format import (
            SAVE_FORMAT_VERSION,
            SUPPORTED_CONTENT_VERSIONS,
            dump_save_json,
            load_save_json,
        )
        from app.simulation.state import RULESET_VERSION

        state = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        save = advance_game(
            new_game(state, save_format_version=SAVE_FORMAT_VERSION),
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(
                    MilitaryMovementDecision(
                        orders=(
                            FormationMovementOrder(
                                formation_id="arken_first_army",
                                destination_theater_id="arken_north",
                            ),
                        )
                    ),
                ),
            ),
        )
        raw = dump_save_json(save)

        reloaded = load_save_json(raw, source="round-trip")
        assert reloaded.ruleset_version == RULESET_VERSION
        assert reloaded.content_version in SUPPORTED_CONTENT_VERSIONS
        assert reloaded.save_format_version == SAVE_FORMAT_VERSION
        # Byte-identical re-serialization: the movement added no field that fails to round trip.
        assert dump_save_json(reloaded) == raw
