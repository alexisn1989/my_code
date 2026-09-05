"""Military Movement, commit 5 -- the complete backend movement atom.

Covers decision shape, the single state-dependent legality gate as both boundaries expose it,
slot-8 application, the fourteenth report, the canonical `formation_moved` entry, and the two
backend presentation surfaces. Reconciliation Group 54 lives in `test_military_reconciliation.py`;
the scoped 0.14.0 quiet-turn baseline lives in `test_military_movement_regression.py`.
"""

from __future__ import annotations

import inspect
import json
import textwrap
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.api.preview import preview_decisions
from app.api.projections import REASON_LABELS, build_turn_result
from app.cli import REASON_RENDERERS, main, render_entry
from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.core.errors import DecisionSetError, TurnResolutionError
from app.simulation import military as military_module
from app.simulation.decisions import (
    MOVEMENT_DUPLICATE_FORMATION,
    MOVEMENT_ORDERS_EMPTY,
    MOVEMENT_ORDERS_NOT_CANONICAL,
    MOVEMENT_ORDERS_PER_DECISION,
    MOVEMENT_SHAPE_CODES,
    MOVEMENT_TOO_MANY_ORDERS,
    BudgetDecision,
    DecisionSet,
    FormationMovementOrder,
    MilitaryMovementDecision,
)
from app.simulation.military import (
    MOVEMENT_SUBMISSION_CODES,
    DestinationIneligibilityCode,
    movement_order_problems,
)
from app.simulation.report import MovementReport
from app.simulation.resolver import resolve_turn

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
TINY_VALID = SCENARIOS_DIR / "tiny_valid.yaml"

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

#: tiny_valid's authored display names, as literals. The rendered sentence the frozen plan
#: specifies is built from these, so re-deriving them from the scenario would let a renaming bug
#: pass unnoticed.
FIRST_ARMY = "First Army of Arken"
ARKEN_CAPITAL_NAME = "Arken Capital Region"
NORTHERN_MARCH_NAME = "Northern March"
APPLIED_SENTENCE = f"{FIRST_ARMY} moved from {ARKEN_CAPITAL_NAME} to {NORTHERN_MARCH_NAME}."
QUIET_SENTENCE = "No formations moved."


def _order(formation_id: str, destination: str) -> MilitaryMovementDecision:
    return MilitaryMovementDecision(
        orders=(
            FormationMovementOrder(formation_id=formation_id, destination_theater_id=destination),
        )
    )


def _decision_set(state, *decisions) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(decisions),
    )


def _move(scenario_file: str, destination: str):
    """Resolve one turn of `scenario_file` with the shipped formation ordered to `destination`."""
    _, formation_id, *_ = SCENARIO_SHAPE[scenario_file]
    state = load_scenario_file(SCENARIOS_DIR / scenario_file)
    decisions = _decision_set(state, _order(formation_id, destination))
    return state, decisions, resolve_turn(state, decisions)


# ==========================================================================
# Part 1 -- decision shape
# ==========================================================================


class TestShapeCodesAreIndependentlyReachable:
    """Each of the four shape codes, reached by a real constructor call.

    The precedence between them is the point: an overlapping payload must report the SAME code
    every time, so a client can branch on it.
    """

    def test_an_empty_order_tuple_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            MilitaryMovementDecision(orders=())
        assert MOVEMENT_ORDERS_EMPTY in str(exc_info.value)

    def test_two_identical_formation_ids_report_the_duplicate_code(self) -> None:
        """`[a, a]` is already sorted, so an ordering-first precedence would misreport it."""
        with pytest.raises(ValidationError) as exc_info:
            MilitaryMovementDecision(
                orders=(
                    FormationMovementOrder(formation_id="a", destination_theater_id="x"),
                    FormationMovementOrder(formation_id="a", destination_theater_id="y"),
                )
            )
        message = str(exc_info.value)
        assert MOVEMENT_DUPLICATE_FORMATION in message
        assert MOVEMENT_ORDERS_NOT_CANONICAL not in message
        assert MOVEMENT_TOO_MANY_ORDERS not in message

    def test_two_distinct_reversed_ids_report_the_canonical_order_code(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            MilitaryMovementDecision(
                orders=(
                    FormationMovementOrder(formation_id="b", destination_theater_id="x"),
                    FormationMovementOrder(formation_id="a", destination_theater_id="y"),
                )
            )
        message = str(exc_info.value)
        assert MOVEMENT_ORDERS_NOT_CANONICAL in message
        assert MOVEMENT_TOO_MANY_ORDERS not in message

    def test_two_distinct_sorted_ids_report_the_ruleset_cap(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            MilitaryMovementDecision(
                orders=(
                    FormationMovementOrder(formation_id="a", destination_theater_id="x"),
                    FormationMovementOrder(formation_id="b", destination_theater_id="y"),
                )
            )
        assert MOVEMENT_TOO_MANY_ORDERS in str(exc_info.value)

    def test_noncanonical_input_is_rejected_and_never_reordered(self) -> None:
        """Reject-not-normalize: the tuple is hash-covered, so silently sorting it would make two
        semantically identical submissions digest differently depending on client behaviour."""
        with pytest.raises(ValidationError):
            MilitaryMovementDecision(
                orders=(
                    FormationMovementOrder(formation_id="b", destination_theater_id="x"),
                    FormationMovementOrder(formation_id="a", destination_theater_id="y"),
                )
            )

    def test_every_declared_shape_code_was_exercised_above(self) -> None:
        """Anti-decoration: the declared set is exactly the four this class reaches, so a code
        that stops firing fails here instead of lingering as documentation."""
        assert {
            MOVEMENT_ORDERS_EMPTY,
            MOVEMENT_DUPLICATE_FORMATION,
            MOVEMENT_ORDERS_NOT_CANONICAL,
            MOVEMENT_TOO_MANY_ORDERS,
        } == MOVEMENT_SHAPE_CODES

    def test_a_single_order_is_accepted(self) -> None:
        decision = _order("arken_first_army", "arken_north")
        assert decision.kind == "military_movement"
        assert len(decision.orders) == MOVEMENT_ORDERS_PER_DECISION


class TestUnionMembershipAndAccessor:
    def test_the_accessor_finds_the_decision_regardless_of_position(self) -> None:
        """`"military_movement"` sorts last, so a positional read would be right by accident on a
        movement-only turn and wrong on a mixed one."""
        state = load_scenario_file(TINY_VALID)
        movement = _order("arken_first_army", "arken_north")
        budget = BudgetDecision(personal_income_rate_bps=2_500)

        alone = _decision_set(state, movement)
        assert alone.decisions.index(movement) == 0
        assert alone.military_movement_decision() is movement

        mixed = _decision_set(state, budget, movement)
        assert mixed.decisions.index(movement) == 1
        assert mixed.military_movement_decision() is movement
        assert mixed.budget_decision() is budget

    def test_no_movement_decision_returns_none(self) -> None:
        state = load_scenario_file(TINY_VALID)
        assert _decision_set(state).military_movement_decision() is None

    def test_two_movement_decisions_are_rejected(self) -> None:
        state = load_scenario_file(TINY_VALID)
        with pytest.raises(ValidationError, match="at most one military-movement decision"):
            _decision_set(
                state,
                _order("arken_first_army", "arken_north"),
                _order("arken_first_army", "arken_coast"),
            )

    def test_a_decision_set_out_of_canonical_kind_order_is_rejected(self) -> None:
        state = load_scenario_file(TINY_VALID)
        with pytest.raises(ValidationError, match="sorted ascending by kind"):
            _decision_set(
                state,
                _order("arken_first_army", "arken_north"),
                BudgetDecision(personal_income_rate_bps=2_500),
            )


# ==========================================================================
# Part 2 -- one legality implementation, two boundaries
# ==========================================================================

#: Every reachable state-dependent code, with a tiny_valid payload that reaches it from a VALID
#: production state -- never `model_construct`, a hand-corrupted model or a malformed save.
REACHABLE_SUBMISSION_CASES: list[tuple[str, str, str]] = [
    ("formation_unknown", "no_such_army", "arken_north"),
    ("destination_theater_unknown", "arken_first_army", "no_such_theater"),
    ("destination_is_origin", "arken_first_army", "arken_capital"),
    ("destination_not_player_owned", "arken_first_army", "kessia_south"),
    ("destination_not_directly_reachable", "arken_first_army", "arken_north"),
]
"""The last case needs a formation NOT at the capital -- `arken_north` is one hop from
`arken_capital`, so from the capital it is eligible. `_state_for` relocates it for that case."""


def _state_for(code: str):
    """A VALID tiny_valid state that makes `code` reachable.

    Only `destination_not_directly_reachable` needs anything special: with the shipped star map,
    every player theater is one hop from the capital, so the formation is relocated to a flank --
    from which the OTHER flank is two hops away. The relocation is done by rebuilding the country
    with `model_copy`, and `check_invariants` is asserted clean, so the case is reached from a
    state the engine itself considers valid.
    """
    state = load_scenario_file(TINY_VALID)
    if code != "destination_not_directly_reachable":
        return state
    country = state.world.countries["arken"]
    military = country.military
    assert military is not None
    formation = military.formations["arken_first_army"]
    country.military = military.model_copy(
        update={
            "formations": {
                "arken_first_army": formation.model_copy(
                    update={"location_theater_id": "arken_coast"}
                )
            }
        }
    )
    from app.simulation.invariants import check_invariants

    assert check_invariants(state) == []
    return state


class TestReachableSubmissionCodes:
    @pytest.mark.parametrize(("code", "formation_id", "destination"), REACHABLE_SUBMISSION_CASES)
    def test_the_validator_emits_the_code(
        self, code: str, formation_id: str, destination: str
    ) -> None:
        state = _state_for(code)
        problems = movement_order_problems(
            state, _decision_set(state, _order(formation_id, destination))
        )
        assert [problem.code for problem in problems] == [code]
        assert problems[0].message.startswith(f"{code}: ")

    @pytest.mark.parametrize(("code", "formation_id", "destination"), REACHABLE_SUBMISSION_CASES)
    def test_submission_rejects_and_the_code_survives_to_the_boundary(
        self, code: str, formation_id: str, destination: str
    ) -> None:
        """Layer 3, authoritatively: the turn does not advance, and the stable code reaches the
        message a client actually receives -- which is what lets `/resolve` expose the code
        without any new response field."""
        state = _state_for(code)
        before = canonical_dumps(state.model_dump(mode="json"))

        with pytest.raises(TurnResolutionError) as exc_info:
            resolve_turn(state, _decision_set(state, _order(formation_id, destination)))

        assert code in str(exc_info.value)
        assert canonical_dumps(state.model_dump(mode="json")) == before

    @pytest.mark.parametrize(("code", "formation_id", "destination"), REACHABLE_SUBMISSION_CASES)
    def test_preview_explains_with_the_same_code_and_mutates_nothing(
        self, code: str, formation_id: str, destination: str
    ) -> None:
        """Layer 2: the SAME code, through preview's own established rejection channel, with the
        captured state byte-identical afterwards."""
        state = _state_for(code)
        before = canonical_dumps(state.model_dump(mode="json"))

        with pytest.raises(DecisionSetError) as exc_info:
            preview_decisions(state, _decision_set(state, _order(formation_id, destination)))

        assert code in str(exc_info.value)
        assert canonical_dumps(state.model_dump(mode="json")) == before

    @pytest.mark.parametrize(("code", "formation_id", "destination"), REACHABLE_SUBMISSION_CASES)
    def test_preview_and_submission_agree_on_the_reason_but_not_on_the_behaviour(
        self, code: str, formation_id: str, destination: str
    ) -> None:
        """The division of labour, asserted directly: preview explains without resolving anything;
        submission rejects and refuses to advance the turn. Both name the same reason, because
        both call one function."""
        state = _state_for(code)
        decisions = _decision_set(state, _order(formation_id, destination))

        with pytest.raises(DecisionSetError) as preview_error:
            preview_decisions(state, decisions)
        with pytest.raises(TurnResolutionError) as resolve_error:
            resolve_turn(state, decisions)

        assert code in str(preview_error.value)
        assert code in str(resolve_error.value)
        # Different behaviour: preview raised the API-layer rejection; resolve raised the
        # turn-level one, which is the type that aborts a resolution.
        assert not isinstance(preview_error.value, TurnResolutionError)

    def test_a_rejected_decision_leaves_turn_version_formations_and_report_untouched(
        self,
    ) -> None:
        state = _state_for("destination_not_player_owned")
        opening_turn, opening_version = state.turn, state.state_version
        military = state.world.countries["arken"].military
        assert military is not None
        opening_location = military.formations["arken_first_army"].location_theater_id

        with pytest.raises(TurnResolutionError):
            resolve_turn(state, _decision_set(state, _order("arken_first_army", "kessia_south")))

        assert (state.turn, state.state_version) == (opening_turn, opening_version)
        military_after = state.world.countries["arken"].military
        assert military_after is not None
        assert military_after.formations["arken_first_army"].location_theater_id == opening_location

    def test_every_declared_submission_code_was_exercised_above(self) -> None:
        assert {code for code, _, _ in REACHABLE_SUBMISSION_CASES} == MOVEMENT_SUBMISSION_CODES

    def test_the_removed_codes_are_absent_from_the_validator(self) -> None:
        """`formation_origin_unresolved` and `origin_not_player_owned` are state-invariant
        failures; `route_kind_not_land` is unreachable with one route kind. None may appear as a
        submission code. Scans the module's real source, so a docstring mentioning them by name
        (as this module's own docstring does) cannot make the check vacuous -- the assertion is
        about the emitted code set, not about text."""
        for removed in (
            "formation_origin_unresolved",
            "origin_not_player_owned",
            "route_kind_not_land",
        ):
            assert removed not in MOVEMENT_SUBMISSION_CODES
            assert removed not in get_args(DestinationIneligibilityCode)

    def test_the_validator_delegates_rather_than_restating_the_truth_table(self) -> None:
        """One legality implementation: the submission validator must CALL the classifier. If it
        ever re-derived ownership or reachability, the two boundaries could disagree."""
        source = inspect.getsource(military_module._order_problem)
        assert "classify_destinations(" in source
        assert "PlayerCountryRef" not in source
        assert "land_destinations_from" not in source

    def test_every_ineligibility_code_has_a_sentence(self) -> None:
        assert set(military_module._INELIGIBILITY_DETAIL) == set(
            get_args(DestinationIneligibilityCode)
        )

    def test_no_movement_decision_produces_no_problems_at_all(self) -> None:
        state = load_scenario_file(TINY_VALID)
        assert movement_order_problems(state, _decision_set(state)) == ()


class TestForeignAndTwoHopRejectionAcrossScenarios:
    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_flank_to_flank_is_two_hops_and_stays_rejected(self, scenario_file: str) -> None:
        country_id, formation_id, _, flanks, _ = SCENARIO_SHAPE[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        country = state.world.countries[country_id]
        military = country.military
        assert military is not None
        country.military = military.model_copy(
            update={
                "formations": {
                    formation_id: military.formations[formation_id].model_copy(
                        update={"location_theater_id": flanks[0]}
                    )
                }
            }
        )
        problems = movement_order_problems(
            state, _decision_set(state, _order(formation_id, flanks[1]))
        )
        assert [problem.code for problem in problems] == ["destination_not_directly_reachable"]

    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_foreign_entry_is_rejected_as_ownership_regardless_of_route(
        self, scenario_file: str
    ) -> None:
        """Both foreign theaters report OWNERSHIP, whether or not a route reaches them. Reporting
        the routed one as unreachable would imply that authoring a route authorizes entry."""
        _, formation_id, _, _, foreign = SCENARIO_SHAPE[scenario_file]
        state = load_scenario_file(SCENARIOS_DIR / scenario_file)
        for theater_id in foreign:
            problems = movement_order_problems(
                state, _decision_set(state, _order(formation_id, theater_id))
            )
            assert [problem.code for problem in problems] == ["destination_not_player_owned"]


# ==========================================================================
# Parts 3-5 -- application, the fourteenth report, the canonical entry
# ==========================================================================


class TestApplicationAndReport:
    @pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
    def test_capital_to_flank_and_flank_to_capital_both_resolve(self, scenario_file: str) -> None:
        country_id, formation_id, capital, flanks, _ = SCENARIO_SHAPE[scenario_file]
        _, _, outbound = _move(scenario_file, flanks[1])
        military = outbound.state.world.countries[country_id].military
        assert military is not None
        assert military.formations[formation_id].location_theater_id == flanks[1]

        # ... and back again, from the state the first move produced.
        state = outbound.state
        decisions = _decision_set(state, _order(formation_id, capital))
        inbound = resolve_turn(state, decisions)
        military = inbound.state.world.countries[country_id].military
        assert military is not None
        assert military.formations[formation_id].location_theater_id == capital
        assert inbound.report.movement is not None
        assert inbound.report.movement.movements[0].origin_theater_id == flanks[1]
        assert inbound.report.movement.movements[0].destination_theater_id == capital

    def test_the_opening_state_is_never_mutated(self) -> None:
        state = load_scenario_file(TINY_VALID)
        before = canonical_dumps(state.model_dump(mode="json"))
        resolve_turn(state, _decision_set(state, _order("arken_first_army", "arken_north")))
        assert canonical_dumps(state.model_dump(mode="json")) == before

    def test_the_move_is_applied_exactly_once(self) -> None:
        """One order, one row, one entry, one relocated formation -- and every other formation
        key preserved, since application replaces the whole mapping."""
        state, _, resolution = _move("tiny_valid.yaml", "arken_north")
        opening = state.world.countries["arken"].military
        closing = resolution.state.world.countries["arken"].military
        assert opening is not None and closing is not None
        assert set(opening.formations) == set(closing.formations)
        assert len(resolution.report.movement.movements) == 1  # type: ignore[union-attr]
        assert sum(1 for e in resolution.report.entries if e.reason_id == "formation_moved") == 1

    def test_a_quiet_turn_reports_present_and_empty_with_no_entry(self) -> None:
        state = load_scenario_file(TINY_VALID)
        resolution = resolve_turn(state, _decision_set(state))
        assert resolution.report.movement == MovementReport(movements=())
        assert not [e for e in resolution.report.entries if e.reason_id == "formation_moved"]

    def test_a_quiet_turn_leaves_military_state_byte_identical(self) -> None:
        state = load_scenario_file(TINY_VALID)
        opening = state.world.countries["arken"].military
        resolution = resolve_turn(state, _decision_set(state))
        closing = resolution.state.world.countries["arken"].military
        assert opening is not None and closing is not None
        assert canonical_dumps(opening.model_dump(mode="json")) == canonical_dumps(
            closing.model_dump(mode="json")
        )

    def test_the_row_carries_both_snapshotted_theater_display_names(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        row = resolution.report.movement.movements[0]  # type: ignore[union-attr]
        assert row.formation_id == "arken_first_army"
        assert row.display_name == FIRST_ARMY
        assert row.branch.value == "army"
        assert row.origin_theater_id == "arken_capital"
        assert row.origin_theater_display_name == ARKEN_CAPITAL_NAME
        assert row.destination_theater_id == "arken_north"
        assert row.destination_theater_display_name == NORTHERN_MARCH_NAME

    def test_the_entry_carries_exactly_the_seven_canonical_params(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        entry = next(e for e in resolution.report.entries if e.reason_id == "formation_moved")
        assert entry.category == "military"
        assert entry.params == {
            "formation_id": "arken_first_army",
            "formation_display_name": FIRST_ARMY,
            "branch": "army",
            "origin_theater_id": "arken_capital",
            "origin_theater_display_name": ARKEN_CAPITAL_NAME,
            "destination_theater_id": "arken_north",
            "destination_theater_display_name": NORTHERN_MARCH_NAME,
        }

    def test_a_budget_and_a_movement_resolve_together(self) -> None:
        """The atom must compose with the decision kinds that already exist."""
        state = load_scenario_file(TINY_VALID)
        decisions = _decision_set(
            state,
            BudgetDecision(personal_income_rate_bps=2_500),
            _order("arken_first_army", "arken_north"),
        )
        resolution = resolve_turn(state, decisions)
        military = resolution.state.world.countries["arken"].military
        assert military is not None
        assert military.formations["arken_first_army"].location_theater_id == "arken_north"
        finance = resolution.state.world.countries["arken"].finance
        assert finance is not None
        assert finance.tax_policy.personal_income_rate_bps == 2_500

    def test_phase_ids_and_ordering_are_unchanged(self) -> None:
        from app.simulation.phases import PHASE_IDS, PHASE_ORDER

        assert len(PHASE_ORDER) == 15
        assert PHASE_IDS[7] == "resolve_military_movement_and_combat"
        assert PHASE_IDS[8] == "apply_casualties_occupation_disruption_war_costs"

    def test_slot_eight_still_runs_the_w1_progression_after_movement(self) -> None:
        """Movement is a substep, not a replacement: the composite handler calls both, in order."""
        from app.simulation import phases as phases_module

        source = inspect.getsource(phases_module._resolve_military_movement_and_combat)
        assert source.index("_apply_military_movement(ctx)") < source.index(
            "_resolve_foreign_conflict_progression(ctx)"
        )

    def test_movement_application_draws_no_randomness(self) -> None:
        """Walks the real AST of the substep rather than its text: the function's own docstring
        says `ctx.rng(...)` in explaining that it never calls one, so a substring scan would fire
        on the explanation. The AST sees executable code only."""
        import ast

        from app.simulation import phases as phases_module

        tree = ast.parse(textwrap.dedent(inspect.getsource(phases_module._apply_military_movement)))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "rng" not in called
        assert "rng" not in inspect.signature(military_module.movement_order_problems).parameters

    def test_the_ast_randomness_scan_actually_fires(self) -> None:
        """Anti-vacuity for the scan above: the same walk over a function that DOES draw must
        find it, so a broken scan cannot pass by seeing nothing."""
        import ast

        from app.simulation import phases as phases_module

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(phases_module._resolve_foreign_conflict_outbreak))
        )
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "rng" in called

    def test_the_report_is_deterministic_across_repeated_resolutions(self) -> None:
        first = _move("tiny_valid.yaml", "arken_north")[2]
        second = _move("tiny_valid.yaml", "arken_north")[2]
        assert canonical_dumps(first.report.model_dump(mode="json")) == canonical_dumps(
            second.report.model_dump(mode="json")
        )
        assert canonical_dumps(first.state.model_dump(mode="json")) == canonical_dumps(
            second.state.model_dump(mode="json")
        )

    def test_formation_mapping_insertion_order_cannot_affect_rows_entries_or_state(self) -> None:
        """A second formation is added in both possible insertion orders. Rows are canonical by
        `formation_id`, the closing mapping is rebuilt from the opening one, and canonical JSON
        sorts keys -- so neither the report nor the state may differ."""
        results = []
        for reverse in (False, True):
            state = load_scenario_file(TINY_VALID)
            military = state.world.countries["arken"].military
            assert military is not None
            shipped = military.formations["arken_first_army"]
            second = shipped.model_copy(
                update={
                    "display_name": "Second Army of Arken",
                    "location_theater_id": "arken_coast",
                }
            )
            pairs = [("arken_first_army", shipped), ("arken_second_army", second)]
            state.world.countries["arken"].military = military.model_copy(
                update={"formations": dict(reversed(pairs) if reverse else pairs)}
            )
            resolution = resolve_turn(
                state, _decision_set(state, _order("arken_first_army", "arken_north"))
            )
            results.append(
                (
                    canonical_dumps(resolution.report.model_dump(mode="json")),
                    canonical_dumps(resolution.state.model_dump(mode="json")),
                )
            )
        assert results[0] == results[1]


class TestFourteenFieldCompleteness:
    def test_a_resolved_quiet_turn_carries_all_fourteen(self) -> None:
        state = load_scenario_file(TINY_VALID)
        report = resolve_turn(state, _decision_set(state)).report
        assert report.movement is not None
        assert report.foreign_affairs is not None

    def test_thirteen_present_with_movement_none_is_rejected(self) -> None:
        from app.simulation.report import TurnReport

        state = load_scenario_file(TINY_VALID)
        data = resolve_turn(state, _decision_set(state)).report.model_dump(mode="json")
        data["movement"] = None
        with pytest.raises(ValidationError, match="all present or all absent"):
            TurnReport.model_validate(data)

    def test_a_movement_turn_carries_exactly_one_row_in_this_ruleset(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        assert len(resolution.report.movement.movements) == 1  # type: ignore[union-attr]


class TestMovementReportModel:
    def test_rows_out_of_canonical_order_are_rejected(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        row = resolution.report.movement.movements[0]  # type: ignore[union-attr]
        other = row.model_copy(update={"formation_id": "arken_aaa_army"})
        with pytest.raises(ValidationError, match="canonical formation_id order"):
            MovementReport(movements=(row, other))

    def test_duplicate_rows_for_one_formation_are_rejected(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        row = resolution.report.movement.movements[0]  # type: ignore[union-attr]
        with pytest.raises(ValidationError, match="duplicate formation_id"):
            MovementReport(movements=(row, row))

    def test_an_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MovementReport(movements=(), extra_field=1)  # type: ignore[call-arg]


class TestTheTwoNamespacesAreDisjoint:
    def test_no_rejection_code_is_a_registered_report_reason_id(self) -> None:
        """Submission codes describe a REJECTED order and never reach a report; report reason ids
        describe a SUCCEEDED action on a resolved turn. A future contributor must not be able to
        register a rejection code as a turn event just because both need human-readable text."""
        assert MOVEMENT_SUBMISSION_CODES.isdisjoint(REASON_LABELS)
        assert MOVEMENT_SUBMISSION_CODES.isdisjoint(REASON_RENDERERS)
        assert MOVEMENT_SHAPE_CODES.isdisjoint(REASON_LABELS)

    def test_formation_moved_is_registered_in_both_tables(self) -> None:
        assert REASON_LABELS["formation_moved"] == "A formation moved."
        assert "formation_moved" in REASON_RENDERERS


# ==========================================================================
# Part 6 -- API projection and CLI presentation
# ==========================================================================


class TestApiProjection:
    def test_an_applied_movement_becomes_exactly_one_generic_driver(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        projection = build_turn_result(resolution.state, resolution.report)
        drivers = [d for d in projection.drivers if d.reason_id == "formation_moved"]
        assert len(drivers) == 1
        assert drivers[0].category == "military"
        assert drivers[0].label == "A formation moved."
        assert drivers[0].params == {
            "formation_id": "arken_first_army",
            "formation_display_name": FIRST_ARMY,
            "branch": "army",
            "origin_theater_id": "arken_capital",
            "origin_theater_display_name": ARKEN_CAPITAL_NAME,
            "destination_theater_id": "arken_north",
            "destination_theater_display_name": NORTHERN_MARCH_NAME,
        }

    def test_no_ledger_row_is_fabricated_for_a_movement(self) -> None:
        """A movement has no amount, and `LedgerEntry.amount_text` is required -- a placeholder
        there would be a fabricated field."""
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        projection = build_turn_result(resolution.state, resolution.report)
        assert not any("moved" in entry.label.lower() for entry in projection.ledger)
        assert QUIET_SENTENCE not in projection.unchanged

    def test_a_quiet_turn_says_so_in_unchanged_and_fabricates_nothing(self) -> None:
        state = load_scenario_file(TINY_VALID)
        resolution = resolve_turn(state, _decision_set(state))
        projection = build_turn_result(resolution.state, resolution.report)
        assert projection.unchanged.count(QUIET_SENTENCE) == 1
        assert not [d for d in projection.drivers if d.reason_id == "formation_moved"]

    def test_no_driver_label_falls_back_to_the_placeholder(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        projection = build_turn_result(resolution.state, resolution.report)
        assert not [d for d in projection.drivers if d.label.startswith("[")]


class TestCliRendering:
    def test_the_renderer_produces_the_exact_sentence_from_stored_params_only(self) -> None:
        _, _, resolution = _move("tiny_valid.yaml", "arken_north")
        entry = next(e for e in resolution.report.entries if e.reason_id == "formation_moved")
        assert render_entry(entry) == APPLIED_SENTENCE

    def test_the_renderer_reads_no_current_state(self) -> None:
        """Historical rendering must survive with no state in scope at all: the renderer takes
        `params` and nothing else, so it cannot resolve a name from current state."""
        assert list(inspect.signature(REASON_RENDERERS["formation_moved"]).parameters) == ["params"]

    def _resolve_with_movement(self, tmp_path: Path, capsys) -> tuple[Path, Path]:
        save0, save1 = tmp_path / "save0.json", tmp_path / "save1.json"
        decisions_file = tmp_path / "movement.json"
        assert main(["new", "--scenario", str(TINY_VALID), "--out", str(save0)]) == 0
        decisions_file.write_text(
            json.dumps(
                {
                    "expected_turn": 0,
                    "expected_state_version": 0,
                    "decisions": [
                        {
                            "kind": "military_movement",
                            "orders": [
                                {
                                    "formation_id": "arken_first_army",
                                    "destination_theater_id": "arken_north",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        capsys.readouterr()
        assert (
            main(
                [
                    "resolve",
                    "--state",
                    str(save0),
                    "--turns",
                    "1",
                    "--decisions-file",
                    str(decisions_file),
                    "--out",
                    str(save1),
                ]
            )
            == 0
        )
        return save0, save1

    def test_current_turn_output_prints_an_applied_movement_exactly_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Counts, not presence: both CLI paths render `report.entries` first and the per-report
        blocks second, so a block that also printed applied movements would double-print. A
        substring assertion could never catch that."""
        self._resolve_with_movement(tmp_path, capsys)
        out = capsys.readouterr().out
        assert out.count(APPLIED_SENTENCE) == 1
        assert out.count(QUIET_SENTENCE) == 0
        assert "[unrendered reason_id=" not in out
        assert "[reason_id]" not in out
        for raw_id in ("arken_first_army", "arken_capital", "arken_north"):
            assert raw_id not in out

    def test_history_output_prints_an_applied_movement_exactly_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Independently wired from the current-turn path, so independently asserted."""
        _, save1 = self._resolve_with_movement(tmp_path, capsys)
        capsys.readouterr()
        assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
        out = capsys.readouterr().out
        assert out.count(APPLIED_SENTENCE) == 1
        assert out.count(QUIET_SENTENCE) == 0
        assert "[unrendered reason_id=" not in out
        assert "[reason_id]" not in out
        for raw_id in ("arken_first_army", "arken_capital", "arken_north"):
            assert raw_id not in out

    def _resolve_quiet(self, tmp_path: Path, capsys) -> Path:
        save0, save1 = tmp_path / "q0.json", tmp_path / "q1.json"
        assert main(["new", "--scenario", str(TINY_VALID), "--out", str(save0)]) == 0
        capsys.readouterr()
        assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
        return save1

    def test_current_turn_output_prints_the_quiet_sentence_exactly_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._resolve_quiet(tmp_path, capsys)
        out = capsys.readouterr().out
        assert out.count(QUIET_SENTENCE) == 1
        assert out.count(APPLIED_SENTENCE) == 0

    def test_history_output_prints_the_quiet_sentence_exactly_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        save1 = self._resolve_quiet(tmp_path, capsys)
        capsys.readouterr()
        assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
        out = capsys.readouterr().out
        assert out.count(QUIET_SENTENCE) == 1
        assert out.count(APPLIED_SENTENCE) == 0

    def test_both_paths_use_the_one_shared_helper(self) -> None:
        """The Phase 3A dual-wiring trap: a second inline copy is how a block silently drifts
        between the two commands."""
        from app import cli as cli_module

        source = Path(inspect.getfile(cli_module)).read_text(encoding="utf-8")
        assert source.count("def _print_movement_report(") == 1
        assert source.count("_print_movement_report(report.movement)") == 2


class TestSaveReloadPreservesTheMovementRecord:
    def test_row_names_entry_params_and_rendering_survive_a_round_trip(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Historical rendering uses the STORED names. The map is deliberately not consulted, and
        the save is re-read from disk so nothing in memory can be supplying them."""
        from app.simulation.save_format import load_save_json

        save0, save1 = tmp_path / "s0.json", tmp_path / "s1.json"
        decisions_file = tmp_path / "m.json"
        assert main(["new", "--scenario", str(TINY_VALID), "--out", str(save0)]) == 0
        decisions_file.write_text(
            json.dumps(
                {
                    "expected_turn": 0,
                    "expected_state_version": 0,
                    "decisions": [
                        {
                            "kind": "military_movement",
                            "orders": [
                                {
                                    "formation_id": "arken_first_army",
                                    "destination_theater_id": "arken_north",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        capsys.readouterr()
        assert (
            main(
                [
                    "resolve",
                    "--state",
                    str(save0),
                    "--turns",
                    "1",
                    "--decisions-file",
                    str(decisions_file),
                    "--out",
                    str(save1),
                ]
            )
            == 0
        )
        capsys.readouterr()

        save = load_save_json(save1.read_text(encoding="utf-8"), source=str(save1))
        report = save.entries[-1].report()
        assert report is not None and report.movement is not None
        row = report.movement.movements[0]
        assert row.origin_theater_display_name == ARKEN_CAPITAL_NAME
        assert row.destination_theater_display_name == NORTHERN_MARCH_NAME
        entry = next(e for e in report.entries if e.reason_id == "formation_moved")
        assert entry.params["origin_theater_display_name"] == ARKEN_CAPITAL_NAME
        assert entry.params["destination_theater_display_name"] == NORTHERN_MARCH_NAME
        assert render_entry(entry) == APPLIED_SENTENCE

    def test_a_reloaded_save_still_reconciles(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Group 54 runs over the reloaded history chain, so a movement that did not survive
        persistence faithfully would surface here rather than silently."""
        from app.simulation.history import validate_history
        from app.simulation.save_format import load_save_json

        save0, save1 = tmp_path / "r0.json", tmp_path / "r1.json"
        decisions_file = tmp_path / "d.json"
        assert main(["new", "--scenario", str(TINY_VALID), "--out", str(save0)]) == 0
        decisions_file.write_text(
            json.dumps(
                {
                    "expected_turn": 0,
                    "expected_state_version": 0,
                    "decisions": [
                        {
                            "kind": "military_movement",
                            "orders": [
                                {
                                    "formation_id": "arken_first_army",
                                    "destination_theater_id": "arken_north",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        capsys.readouterr()
        assert (
            main(
                [
                    "resolve",
                    "--state",
                    str(save0),
                    "--turns",
                    "1",
                    "--decisions-file",
                    str(decisions_file),
                    "--out",
                    str(save1),
                ]
            )
            == 0
        )
        save = load_save_json(save1.read_text(encoding="utf-8"), source=str(save1))
        assert validate_history(save) == []
