"""Military Movement, commit 4 -- the directed LAND helper and the single legality classifier.

Commit 4 is PURE INSPECTION. The last class in this file is the atomicity guard: a structural
proof that nothing here made a new player action acceptable. Everything before it proves the rule
itself is directed, one-edge, ownership-first, deterministic and side-effect free.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation import military as military_module
from app.simulation.geography import (
    LabelAnchor,
    RouteKind,
    TheaterKind,
    land_destinations_from,
    outgoing_and_incoming,
)
from app.simulation.invariants import check_invariants
from app.simulation.military import DestinationClassification, classify_destinations
from app.simulation.state import (
    CountryShapeState,
    FormationBranch,
    FormationState,
    MilitaryState,
    PlayerCountryRef,
    RouteState,
    StrategicMapState,
    TheaterPresentation,
    TheaterState,
)
from tests.conftest import make_game_state

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

#: Per scenario: player country, formation id, capital, the two player flanks, the two foreign
#: theaters. Literals, so a test cannot pass by re-deriving whatever the YAML happens to say.
SCENARIO_SHAPE: dict[str, tuple[str, str, str, tuple[str, str], tuple[str, str]]] = {
    "tiny_valid.yaml": (
        "arken",
        "arken_first_army",
        "arken_capital",
        ("arken_coast", "arken_north"),
        ("kessia_south", "vetruska_frontier"),
    ),
    "decree_state.yaml": (
        "valdrun",
        "valdrun_first_army",
        "valdrun_capital",
        ("valdrun_east", "valdrun_highlands"),
        ("marnil_border", "sorrend_plain"),
    ),
    "deficit_demo.yaml": (
        "strapped",
        "strapped_first_army",
        "home_capital",
        ("home_lowlands", "home_port"),
        ("marnil_march", "tolvane_isle"),
    ),
}

_SCENARIO_FILES = sorted(SCENARIO_SHAPE)


def _classify(scenario_file: str, *, at: str | None = None):
    """Classify the shipped formation, optionally relocated to `at` WITHOUT touching production
    state -- `model_copy` returns a new formation and leaves the loaded one untouched."""
    country_id, formation_id, *_ = SCENARIO_SHAPE[scenario_file]
    state = load_scenario_file(SCENARIOS_DIR / scenario_file)
    military = state.world.countries[country_id].military
    assert military is not None
    formation = military.formations[formation_id]
    if at is not None:
        formation = formation.model_copy(update={"location_theater_id": at})
    rows = classify_destinations(
        formation=formation,
        player_country_id=country_id,
        map_state=state.world.strategic_map,
    )
    return state, rows


def _reason(rows, theater_id: str) -> str | None:
    return next(row.ineligible_reason_code for row in rows if row.theater_id == theater_id)


def _eligible_ids(rows) -> list[str]:
    return [row.theater_id for row in rows if row.eligible]


# --------------------------------------------------------------------------
# Part 1: the directed LAND helper
# --------------------------------------------------------------------------


def _edge(from_theater: str, to_theater: str) -> RouteState:
    return RouteState(from_theater=from_theater, to_theater=to_theater, kind=RouteKind.LAND)


class TestLandDestinationsFrom:
    def test_an_outgoing_land_destination_is_returned(self) -> None:
        assert land_destinations_from("a", [_edge("a", "b")]) == ("b",)

    def test_an_incoming_only_route_is_not_an_outgoing_one(self) -> None:
        """The single most important property: direction is data, not a suggestion."""
        assert land_destinations_from("a", [_edge("b", "a")]) == ()

    def test_a_reciprocal_pair_is_two_directional_facts(self) -> None:
        routes = [_edge("a", "b"), _edge("b", "a")]
        assert land_destinations_from("a", routes) == ("b",)
        assert land_destinations_from("b", routes) == ("a",)

    def test_results_are_sorted(self) -> None:
        routes = [_edge("a", "c"), _edge("a", "b"), _edge("a", "d")]
        assert land_destinations_from("a", routes) == ("b", "c", "d")

    def test_route_input_order_does_not_affect_output(self) -> None:
        routes = [_edge("a", "c"), _edge("a", "b")]
        assert land_destinations_from("a", routes) == land_destinations_from(
            "a", list(reversed(routes))
        )

    def test_structurally_equivalent_repeats_cannot_duplicate_a_destination(self) -> None:
        """`RouteState` is a value, so two equal rows are indistinguishable; the set comprehension
        makes duplicate-insensitivity structural rather than something a caller must avoid."""
        assert land_destinations_from("a", [_edge("a", "b"), _edge("a", "b")]) == ("b",)

    def test_no_outgoing_route_returns_an_empty_tuple(self) -> None:
        assert land_destinations_from("a", [_edge("b", "c")]) == ()

    def test_a_theater_is_never_its_own_destination_via_this_helper(self) -> None:
        """`RouteState` rejects a self-loop, so no self-destination can be authored at all."""
        with pytest.raises(ValidationError):
            _edge("a", "a")

    def test_the_existing_adjacency_helper_is_unchanged_in_shape(self) -> None:
        """`outgoing_and_incoming` keeps its signature: the new helper is a sibling, not a
        replacement, and the projection that calls it is untouched by this commit."""
        params = list(inspect.signature(outgoing_and_incoming).parameters)
        assert params == ["theater_id", "routes"]


# --------------------------------------------------------------------------
# Part 2: the classifier over the shipped scenarios
# --------------------------------------------------------------------------


class TestClassifierOnShippedScenarios:
    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_one_row_per_theater_sorted_by_id(self, scenario_file: str) -> None:
        state, rows = _classify(scenario_file)
        ids = [row.theater_id for row in rows]
        assert ids == sorted(state.world.strategic_map.theaters)
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_the_capital_is_the_origin(self, scenario_file: str) -> None:
        _, _, capital, _, _ = SCENARIO_SHAPE[scenario_file]
        _, rows = _classify(scenario_file)
        assert _reason(rows, capital) == "destination_is_origin"

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_both_player_flanks_are_eligible_from_the_capital(self, scenario_file: str) -> None:
        _, _, _, flanks, _ = SCENARIO_SHAPE[scenario_file]
        _, rows = _classify(scenario_file)
        assert _eligible_ids(rows) == sorted(flanks)

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_both_foreign_theaters_are_ineligible_by_ownership(self, scenario_file: str) -> None:
        _, _, _, _, foreign = SCENARIO_SHAPE[scenario_file]
        _, rows = _classify(scenario_file)
        for theater_id in foreign:
            assert _reason(rows, theater_id) == "destination_not_player_owned"

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_eligibility_and_reason_are_exclusive_on_every_row(self, scenario_file: str) -> None:
        _, rows = _classify(scenario_file)
        for row in rows:
            assert row.eligible is (row.ineligible_reason_code is None)


class TestExclusivityIsEnforcedByTheModel:
    def test_an_eligible_row_may_not_carry_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            DestinationClassification(
                theater_id="a", eligible=True, ineligible_reason_code="destination_is_origin"
            )

    def test_an_ineligible_row_must_carry_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            DestinationClassification(theater_id="a", eligible=False)

    def test_an_unknown_reason_code_is_rejected_by_the_type(self) -> None:
        """The codes are enumerated in `DestinationIneligibilityCode`, so a typo or a code that
        belongs to commit 5's submission wrapper cannot be smuggled in as free text."""
        with pytest.raises(ValidationError):
            DestinationClassification(
                theater_id="a", eligible=False, ineligible_reason_code="formation_unknown"
            )

    def test_rows_are_frozen(self) -> None:
        row = DestinationClassification(theater_id="a", eligible=True)
        with pytest.raises(ValidationError):
            row.eligible = False  # type: ignore[misc]


# --------------------------------------------------------------------------
# One-edge behaviour and ownership precedence
# --------------------------------------------------------------------------


class TestOneEdgeOnly:
    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_from_a_flank_only_the_capital_is_reachable(self, scenario_file: str) -> None:
        """Each scenario's player subgraph is a star centred on the capital, so from a flank the
        other flank is exactly two hops away -- and must NOT be accepted. This is where a BFS
        would betray itself."""
        _, _, capital, flanks, _ = SCENARIO_SHAPE[scenario_file]
        here, far = flanks
        _, rows = _classify(scenario_file, at=here)

        assert _eligible_ids(rows) == [capital]
        assert _reason(rows, here) == "destination_is_origin"
        assert _reason(rows, far) == "destination_not_directly_reachable"

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_the_two_hop_destination_is_genuinely_two_hops(self, scenario_file: str) -> None:
        """Guards the case above against being vacuous: the far flank really is reachable from
        the near one via the capital, so rejecting it is a one-edge decision and not an accident
        of a disconnected map."""
        _, _, capital, flanks, _ = SCENARIO_SHAPE[scenario_file]
        here, far = flanks
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        routes = state.world.strategic_map.routes

        assert capital in land_destinations_from(here, routes)
        assert far in land_destinations_from(capital, routes)
        assert far not in land_destinations_from(here, routes)


class TestOwnershipPrecedence:
    """Ownership is decided before reachability, on real `tiny_valid` geography."""

    def test_a_foreign_theater_with_an_authored_route_is_still_ownership_ineligible(self) -> None:
        """`arken_north -> kessia_south` is a real authored LAND route. Standing on `arken_north`,
        Kessia is one edge away -- and still refused for ownership, never for reachability."""
        state = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        assert "kessia_south" in land_destinations_from(
            "arken_north", state.world.strategic_map.routes
        )

        _, rows = _classify("tiny_valid.yaml", at="arken_north")
        assert _reason(rows, "kessia_south") == "destination_not_player_owned"

    def test_a_foreign_theater_without_a_route_gets_the_same_ownership_reason(self) -> None:
        """`vetruska_frontier` has no route from any player theater. Reporting it as unreachable
        would imply that authoring one would authorize entry, which is false."""
        state = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        for origin in ("arken_capital", "arken_coast", "arken_north"):
            assert "vetruska_frontier" not in land_destinations_from(
                origin, state.world.strategic_map.routes
            )

        for origin in ("arken_capital", "arken_coast", "arken_north"):
            _, rows = _classify("tiny_valid.yaml", at=origin)
            assert _reason(rows, "vetruska_frontier") == "destination_not_player_owned"

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_no_foreign_theater_ever_receives_a_reachability_reason(
        self, scenario_file: str
    ) -> None:
        country_id, _, capital, flanks, foreign = SCENARIO_SHAPE[scenario_file]
        for origin in (capital, *flanks):
            _, rows = _classify(scenario_file, at=origin)
            for theater_id in foreign:
                assert _reason(rows, theater_id) != "destination_not_directly_reachable"


# --------------------------------------------------------------------------
# The synthetic one-way case
# --------------------------------------------------------------------------


def _one_way_state():
    """A COMPLETE, valid game state whose player map has `capital -> flank` and no return route.

    Built from real models -- no `model_construct`, no bypass. It is legal because nothing
    requires reciprocity (`StrategicMapState._routes_unique_and_ordered` checks only uniqueness
    and canonical order) and because `player_land_component_disconnected` walks DIRECTED edges
    FORWARD from the capital, so a flank reached by `capital -> flank` alone is connected.
    """
    player = "testland"
    presentation = TheaterPresentation(
        centroid_x=5_000, centroid_y=5_000, label_anchor=LabelAnchor.CENTER
    )
    owner = PlayerCountryRef(country_id=player)
    strategic_map = StrategicMapState(
        map_id="one_way_map",
        capital_theater_id="capital",
        theaters={
            "capital": TheaterState(
                display_name="Capital",
                kind=TheaterKind.LAND,
                owner=owner,
                presentation=presentation,
            ),
            "flank": TheaterState(
                display_name="Flank", kind=TheaterKind.LAND, owner=owner, presentation=presentation
            ),
        },
        routes=(RouteState(from_theater="capital", to_theater="flank", kind=RouteKind.LAND),),
        shapes=(
            CountryShapeState(
                shape_id="testland_shape",
                owner=owner,
                polygon=((0, 0), (10, 0), (10, 10), (0, 10)),
            ),
        ),
    )
    base = make_game_state()
    country = base.world.countries[player].model_copy(
        update={
            "military": MilitaryState(
                formations={
                    "first_army": FormationState(
                        display_name="First Army",
                        branch=FormationBranch.ARMY,
                        location_theater_id="flank",
                    )
                }
            )
        }
    )
    return base.model_copy(
        update={
            "world": base.world.model_copy(
                update={"strategic_map": strategic_map, "countries": {player: country}}
            )
        }
    )


class TestSyntheticOneWayRoute:
    def test_the_one_way_state_is_valid_production_state(self) -> None:
        """Asserted BEFORE the classifier runs: this proves zero eligible destinations is
        reachable from a state the engine accepts, not merely from map models that happen to
        construct."""
        assert [violation.code for violation in check_invariants(_one_way_state())] == []

    def test_an_incoming_route_is_not_read_as_outgoing(self) -> None:
        state = _one_way_state()
        assert check_invariants(state) == []
        routes = state.world.strategic_map.routes
        assert land_destinations_from("capital", routes) == ("flank",)
        assert land_destinations_from("flank", routes) == ()

    def test_zero_eligible_destinations_is_a_valid_result(self) -> None:
        state = _one_way_state()
        assert check_invariants(state) == []
        formation = state.world.countries["testland"].military.formations["first_army"]  # type: ignore[union-attr]
        rows = classify_destinations(
            formation=formation,
            player_country_id="testland",
            map_state=state.world.strategic_map,
        )

        assert _eligible_ids(rows) == []
        assert _reason(rows, "flank") == "destination_is_origin"
        assert _reason(rows, "capital") == "destination_not_directly_reachable"


# --------------------------------------------------------------------------
# Determinism and purity
# --------------------------------------------------------------------------


class TestDeterminismAndPurity:
    def test_theater_insertion_order_does_not_change_the_result(self) -> None:
        state = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
        strategic_map = state.world.strategic_map
        reversed_map = strategic_map.model_copy(
            update={"theaters": dict(reversed(list(strategic_map.theaters.items())))}
        )
        assert list(strategic_map.theaters) != list(reversed_map.theaters)

        formation = state.world.countries["arken"].military.formations["arken_first_army"]  # type: ignore[union-attr]
        forward = classify_destinations(
            formation=formation, player_country_id="arken", map_state=strategic_map
        )
        backward = classify_destinations(
            formation=formation, player_country_id="arken", map_state=reversed_map
        )
        assert forward == backward

    def test_route_order_does_not_change_the_result(self) -> None:
        """Routes are canonically ordered on the model, so the reordering is applied to the
        helper directly -- the level where a caller could realistically vary it."""
        routes = [_edge("a", "c"), _edge("a", "b"), _edge("c", "a")]
        assert land_destinations_from("a", routes) == land_destinations_from(
            "a", list(reversed(routes))
        )

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_repeated_calls_are_equal(self, scenario_file: str) -> None:
        _, first = _classify(scenario_file)
        _, second = _classify(scenario_file)
        assert first == second

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_classification_mutates_neither_formation_nor_map(self, scenario_file: str) -> None:
        country_id, formation_id, *_ = SCENARIO_SHAPE[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        formation = state.world.countries[country_id].military.formations[formation_id]  # type: ignore[union-attr]
        strategic_map = state.world.strategic_map

        before_formation = canonical_dumps(formation.model_dump(mode="json"))
        before_map = canonical_dumps(strategic_map.model_dump(mode="json"))
        classify_destinations(
            formation=formation, player_country_id=country_id, map_state=strategic_map
        )
        assert canonical_dumps(formation.model_dump(mode="json")) == before_formation
        assert canonical_dumps(strategic_map.model_dump(mode="json")) == before_map

    def test_the_classifier_accepts_no_rng(self) -> None:
        """The positive half of the RNG proof. The structural half already exists and covers this
        module for free: `tests/test_no_forbidden_imports.py` walks every file under
        `app/simulation` and fails on an import of `random`."""
        params = set(inspect.signature(classify_destinations).parameters)
        assert params == {"formation", "player_country_id", "map_state"}
        assert not any("rng" in name or "random" in name for name in params)

    def test_legality_reads_authored_rows_not_the_collapsed_projection(self) -> None:
        """`build_strategic_map` collapses a reciprocal pair into one `bidirectional` display row.
        Legality must never be decided from that. Proved structurally: this module imports nothing
        from `app.api`.
        """
        tree = ast.parse(Path(inspect.getfile(military_module)).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert not any(name.startswith("app.api") for name in imported), imported


# --------------------------------------------------------------------------
# Atomicity: commit 5 accepts and applies movement in the SAME commit
# --------------------------------------------------------------------------


class TestMovementIsAcceptedAndAppliedTogether:
    """Commit 4's guard asserted the ABSENCE of every symbol commit 5 adds. Commit 5 makes those
    assertions false by design, so the guard is not deleted -- it is turned around to assert the
    property it was protecting.

    The defect it existed to prevent was never "these symbols exist". It was a state in which a
    player could submit a valid `military_movement` decision, have it ACCEPTED, and have the turn
    resolve with the order silently discarded. So the replacement proves acceptance and
    application are inseparable: the union accepts the decision, and the same resolution applies
    it to state, reports it in `MovementReport`, and records it as a `formation_moved` entry.

    Structural, not textual -- it asks the real modules what they expose, so prose in a docstring
    or a frozen plan cannot make it pass or fail.
    """

    def test_the_decision_union_contains_exactly_the_expected_kinds(self) -> None:
        """Reads the real `Decision` alias: `Annotated[A | B | ..., FieldInfo(discriminator=...)]`,
        so the members are the args of the union inside the annotation.

        Renamed from `..._has_grown_by_exactly_one_kind`: the Military Movement slice added
        `military_movement`, the characters slice added `cabinet`, then `legislative_bargain`, then
        `foreign_assistance`, so "one" stopped being true while the structural claim -- these kinds
        and no others -- did not. A membership assertion keeps catching an accidentally-added kind
        either way.

        Deliberately kept as SET EQUALITY rather than relaxed to a subset check when the union grew:
        a subset assertion would stop catching the very thing this test exists for, an accidentally
        added seventh or eighth kind.
        """
        import typing

        from app.simulation.decisions import Decision

        members = typing.get_args(typing.get_args(Decision)[0])
        kinds = {member.model_fields["kind"].default for member in members}
        assert kinds == {
            "bloc_relationship_investment",
            "budget",
            "cabinet",
            "constitutional_amendment",
            "foreign_assistance",
            "legislative_bargain",
            "military_movement",
        }

    def test_military_movement_sorts_last_so_no_existing_canonical_order_changes(self) -> None:
        """Canonical kind order is ascending by `kind`. If `"military_movement"` did not sort
        last, every already-serialised multi-kind `decisions_json` would digest differently."""
        existing = ["bloc_relationship_investment", "budget", "constitutional_amendment"]
        assert sorted([*existing, "military_movement"]) == [*existing, "military_movement"]

    def test_the_decision_models_and_accessor_exist(self) -> None:
        import app.simulation.decisions as decisions_module
        from app.simulation.decisions import DecisionSet

        for symbol in ("MilitaryMovementDecision", "FormationMovementOrder"):
            assert hasattr(decisions_module, symbol), symbol
        assert hasattr(DecisionSet, "military_movement_decision")

    def test_the_movement_report_is_the_fourteenth_turn_report_field(self) -> None:
        import app.simulation.report as report_module

        assert hasattr(report_module, "MovementReport")
        assert "movement" in report_module.TurnReport.model_fields

    def test_the_movement_reconciler_exists(self) -> None:
        import app.simulation.reconciliation as reconciliation_module

        assert hasattr(reconciliation_module, "reconcile_formation_movement")

    def test_the_military_endpoint_is_routed_and_reuses_this_classifier(self) -> None:
        """Commit 4 asserted this path's ABSENCE and commit 5 kept that assertion; commit 6 is the
        commit that adds it, so the guard is turned around rather than deleted.

        What it protects has not changed: the endpoint must REUSE the classifier, never re-derive
        legality. `test_api_military.py` proves the verdicts match row for row; this proves the
        route exists and that its builder actually calls the shared function.

        Asks the generated OpenAPI document for the served paths rather than walking `app.routes`,
        which mixes `Route` and `_IncludedRouter` objects and has no uniform `.path`.
        """
        from app.api import projections as projections_module
        from app.api.main import ApiSettings, create_app

        app = create_app(ApiSettings(serve_spa=False))
        paths = set(app.openapi()["paths"])
        assert paths, "expected a non-empty path set; an empty one would pass vacuously"
        assert "/api/game/military" in paths, sorted(paths)

        source = inspect.getsource(projections_module.build_military)
        assert "classify_destinations(" in source
        assert "PlayerCountryRef" not in source
        assert "land_destinations_from" not in source

    def test_the_legality_rule_is_now_reachable_from_the_resolver(self) -> None:
        """Commit 4 asserted the opposite: nothing in turn resolution could reach this module, so
        no submitted decision could be affected by it. Commit 5 is precisely the commit that wires
        it in, and the same AST scan proves the wiring exists rather than assuming it."""
        import app.simulation.resolver as resolver_module

        source = Path(inspect.getfile(resolver_module)).read_text(encoding="utf-8")
        imported = [
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        assert "app.simulation.military" in imported

    def test_the_scan_actually_fires_a_self_check(self) -> None:
        """Anti-vacuity, kept from commit 4 and inverted with it: the same import scan run against
        a module that does NOT import `app.simulation.military` must fail to find it. Without
        this, the assertion above would pass just as happily if the scan were broken."""
        synthetic = "from app.simulation.geography import RouteKind\n"
        imported = [
            node.module
            for node in ast.walk(ast.parse(synthetic))
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        assert "app.simulation.military" not in imported

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_an_accepted_order_is_applied_and_reported_in_the_same_resolution(
        self, scenario_file: str
    ) -> None:
        """THE atomicity property, end to end and per scenario: one accepted order produces one
        moved formation, one `MovementReport` row and one `formation_moved` entry.

        No accepted movement is silently ignored, and none is reported without being applied.
        """
        from app.simulation.decisions import (
            DecisionSet,
            FormationMovementOrder,
            MilitaryMovementDecision,
        )
        from app.simulation.resolver import resolve_turn

        country_id, formation_id, capital, flanks, _ = SCENARIO_SHAPE[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        destination = flanks[0]

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

        military = resolution.state.world.countries[country_id].military
        assert military is not None
        assert military.formations[formation_id].location_theater_id == destination

        movement = resolution.report.movement
        assert movement is not None
        assert [row.formation_id for row in movement.movements] == [formation_id]
        assert movement.movements[0].origin_theater_id == capital
        assert movement.movements[0].destination_theater_id == destination

        entries = [e for e in resolution.report.entries if e.reason_id == "formation_moved"]
        assert len(entries) == 1
        assert entries[0].category == "military"
