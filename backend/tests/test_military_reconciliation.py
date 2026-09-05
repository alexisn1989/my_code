"""Military Movement, commit 5 -- reconciliation Group 54.

Group 54 proves the three records of one turn's movement agree: the submitted `DecisionSet`, the
opening->closing state transition, and the `MovementReport` with its paired `formation_moved`
entries.

**Every negative control tampers with an already-resolved result**, using `model_copy(update=...)`,
which bypasses validation exactly as a hand-edited save file would. That is deliberate and is not
the reachability discipline §4.1 imposes on player-facing error codes: a reconciler's entire job is
to catch state that a correct engine cannot produce -- an engine bug or a tampered save -- so its
controls must construct precisely what construction otherwise forbids. `branch` is the clearest
case: `FormationBranch` has a single member, so a mutated branch has no valid form at all, and a
control that could only be written with a valid value would prove nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    DecisionSet,
    FormationMovementOrder,
    MilitaryMovementDecision,
)
from app.simulation.reconciliation import reconcile_formation_movement
from app.simulation.report import MovementReport
from app.simulation.resolver import resolve_turn
from tests.history_tamper_helpers import (
    advance_n,
    hash_chain_problems,
    retamper_report_with_consistent_hash,
    retamper_state_with_consistent_hash,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
TINY_VALID = SCENARIOS_DIR / "tiny_valid.yaml"

COUNTRY = "arken"
FORMATION = "arken_first_army"
CAPITAL = "arken_capital"
DESTINATION = "arken_north"
OTHER_FLANK = "arken_coast"


def _decision_set(state, *decisions) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(decisions),
    )


def _movement_decisions(state) -> DecisionSet:
    return _decision_set(
        state,
        MilitaryMovementDecision(
            orders=(
                FormationMovementOrder(formation_id=FORMATION, destination_theater_id=DESTINATION),
            )
        ),
    )


def _resolved_move():
    """opening, closing, decisions, report for one real capital -> Northern March move."""
    opening = load_scenario_file(TINY_VALID)
    decisions = _movement_decisions(opening)
    resolution = resolve_turn(opening, decisions)
    return opening, resolution.state, decisions, resolution.report


def _resolved_quiet():
    opening = load_scenario_file(TINY_VALID)
    decisions = _decision_set(opening)
    resolution = resolve_turn(opening, decisions)
    return opening, resolution.state, decisions, resolution.report


def _with_formations(state, formations: dict):
    """A copy of `state` whose player military carries exactly `formations`."""
    copied = state.model_copy(deep=True)
    military = copied.world.countries[COUNTRY].military
    assert military is not None
    copied.world.countries[COUNTRY].military = military.model_copy(
        update={"formations": formations}
    )
    return copied


def _formations(state) -> dict:
    military = state.world.countries[COUNTRY].military
    assert military is not None
    return dict(military.formations)


def _with_row(report, **field_updates):
    """A copy of `report` whose single movement row has `field_updates` applied."""
    assert report.movement is not None
    row = report.movement.movements[0]
    return report.model_copy(
        update={"movement": MovementReport(movements=(row.model_copy(update=field_updates),))}
    )


def _reconcile(opening, closing, decisions, report) -> list[str]:
    return reconcile_formation_movement(
        opening_state=opening, closing_state=closing, decisions=decisions, report=report
    )


# ==========================================================================
# The eleven proofs, on real resolved turns
# ==========================================================================


class TestGroup54AcceptsCorrectResolutions:
    def test_a_real_movement_turn_reconciles(self) -> None:
        assert _reconcile(*_resolved_move()) == []

    def test_a_real_quiet_turn_reconciles(self) -> None:
        """Proof 11: zero entries and an empty tuple satisfy every check, which is precisely the
        statement that a quiet turn has neither."""
        opening, closing, decisions, report = _resolved_quiet()
        assert report.movement is not None
        assert report.movement.movements == ()
        assert not [e for e in report.entries if e.reason_id == "formation_moved"]
        assert _reconcile(opening, closing, decisions, report) == []

    def test_an_unordered_formation_keeps_its_opening_location(self) -> None:
        """Proof 1, with a second formation that is never ordered anywhere."""
        opening = load_scenario_file(TINY_VALID)
        shipped = _formations(opening)[FORMATION]
        opening = _with_formations(
            opening,
            {
                FORMATION: shipped,
                "arken_second_army": shipped.model_copy(
                    update={
                        "display_name": "Second Army of Arken",
                        "location_theater_id": OTHER_FLANK,
                    }
                ),
            },
        )
        decisions = _movement_decisions(opening)
        resolution = resolve_turn(opening, decisions)

        assert _formations(resolution.state)["arken_second_army"].location_theater_id == OTHER_FLANK
        assert _reconcile(opening, resolution.state, decisions, resolution.report) == []

    def test_it_still_runs_when_the_decision_payload_is_unparseable(self) -> None:
        """`decisions=None` (a malformed `decisions_json` upstream) skips only the checks that
        genuinely need a submitted order. Everything else still runs, so a tampered movement
        paired with an unreadable decision payload is not silently excused."""
        opening, closing, _, report = _resolved_move()
        assert _reconcile(opening, closing, None, report) == []

        tampered = _with_formations(closing, {FORMATION: _formations(opening)[FORMATION]})
        problems = _reconcile(opening, tampered, None, report)
        assert problems, "a report row with no transition must still be detected"


# ==========================================================================
# Ten independent negative controls
# ==========================================================================


class TestGroup54NegativeControls:
    def test_a_teleport_with_no_submitted_order_is_detected(self) -> None:
        opening, closing, _, report = _resolved_move()
        quiet_decisions = _decision_set(opening)
        empty_report = report.model_copy(update={"movement": MovementReport(movements=())})
        problems = _reconcile(opening, closing, quiet_decisions, empty_report)
        assert any("no submitted order naming it" in problem for problem in problems)

    def test_a_formation_appearing_in_the_closing_state_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        extra = dict(_formations(closing))
        extra["arken_ghost_army"] = _formations(opening)[FORMATION]
        problems = _reconcile(opening, _with_formations(closing, extra), decisions, report)
        assert any("appeared=['arken_ghost_army']" in problem for problem in problems)

    def test_a_formation_disappearing_from_the_closing_state_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        problems = _reconcile(opening, _with_formations(closing, {}), decisions, report)
        assert any(f"disappeared=['{FORMATION}']" in problem for problem in problems)

    def test_a_mutated_branch_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        mutated = _formations(closing)[FORMATION].model_copy(update={"branch": "navy"})
        problems = _reconcile(
            opening, _with_formations(closing, {FORMATION: mutated}), decisions, report
        )
        assert any("branch changed during turn resolution" in problem for problem in problems)

    def test_a_mutated_display_name_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        mutated = _formations(closing)[FORMATION].model_copy(
            update={"display_name": "Renamed Army"}
        )
        problems = _reconcile(
            opening, _with_formations(closing, {FORMATION: mutated}), decisions, report
        )
        assert any("display_name changed during turn resolution" in problem for problem in problems)

    def test_a_report_row_with_no_transition_is_detected(self) -> None:
        """The formation is put back where it started, so the row describes nothing real."""
        opening, closing, decisions, report = _resolved_move()
        unmoved = _with_formations(closing, {FORMATION: _formations(opening)[FORMATION]})
        problems = _reconcile(opening, unmoved, decisions, report)
        assert any("did not change theater during this turn" in problem for problem in problems)

    def test_a_transition_with_no_report_row_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        stripped = report.model_copy(update={"movement": MovementReport(movements=())})
        problems = _reconcile(opening, closing, decisions, stripped)
        assert any("contains no row for it" in problem for problem in problems)

    def test_a_row_reporting_the_wrong_destination_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        problems = _reconcile(
            opening,
            closing,
            decisions,
            _with_row(report, destination_theater_id=OTHER_FLANK),
        )
        assert any("destination_theater_id" in problem for problem in problems)

    def test_a_duplicated_movement_entry_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        entry = next(e for e in report.entries if e.reason_id == "formation_moved")
        doubled = report.model_copy(update={"entries": [*report.entries, entry]})
        problems = _reconcile(opening, closing, decisions, doubled)
        assert any("recorded exactly once in each" in problem for problem in problems)

    def test_a_missing_movement_entry_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        stripped = report.model_copy(
            update={"entries": [e for e in report.entries if e.reason_id != "formation_moved"]}
        )
        problems = _reconcile(opening, closing, decisions, stripped)
        assert any("recorded exactly once in each" in problem for problem in problems)

    def test_a_changed_strategic_map_is_detected(self) -> None:
        """Proof 8. Group 53 proves this independently; Group 54 asserts it too, so a bug that
        disabled one is not masked by the other."""
        opening, closing, decisions, report = _resolved_move()
        tampered = closing.model_copy(deep=True)
        theaters = dict(tampered.world.strategic_map.theaters)
        theaters[CAPITAL] = theaters[CAPITAL].model_copy(update={"display_name": "Renamed"})
        tampered.world.strategic_map = tampered.world.strategic_map.model_copy(
            update={"theaters": theaters}
        )
        problems = _reconcile(opening, tampered, decisions, report)
        assert any("also reported by group 54" in problem for problem in problems)

    def test_an_ordered_formation_that_did_not_move_is_detected(self) -> None:
        """The exact defect commit 5's atomicity requirement exists to forbid: an order accepted
        and then silently discarded."""
        opening, closing, decisions, report = _resolved_move()
        unmoved = _with_formations(closing, {FORMATION: _formations(opening)[FORMATION]})
        empty_report = report.model_copy(update={"movement": MovementReport(movements=())})
        stripped = empty_report.model_copy(
            update={"entries": [e for e in report.entries if e.reason_id != "formation_moved"]}
        )
        problems = _reconcile(opening, unmoved, decisions, stripped)
        assert any("did not move" in problem for problem in problems)

    def test_a_missing_movement_report_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        problems = _reconcile(
            opening, closing, decisions, report.model_copy(update={"movement": None})
        )
        assert any("movement report missing" in problem for problem in problems)


# ==========================================================================
# Six single-field row tamper controls -- one field each, never combined
# ==========================================================================

#: (row field, tampered value, the substring the detection must name). One per field, because a
#: single combined control would let five of the six checks be absent without failing.
ROW_TAMPER_CASES = [
    ("origin_theater_id", OTHER_FLANK, "origin_theater_id"),
    ("destination_theater_id", OTHER_FLANK, "destination_theater_id"),
    ("origin_theater_display_name", "Not The Capital", "origin_theater_display_name"),
    ("destination_theater_display_name", "Not The March", "destination_theater_display_name"),
    ("display_name", "Not The First Army", "display_name"),
    ("branch", "navy", "branch"),
]


class TestGroup54RowFieldTamperControls:
    @pytest.mark.parametrize(("field_name", "value", "expected"), ROW_TAMPER_CASES)
    def test_each_row_field_is_independently_checked(
        self, field_name: str, value: str, expected: str
    ) -> None:
        opening, closing, decisions, report = _resolved_move()
        problems = _reconcile(opening, closing, decisions, _with_row(report, **{field_name: value}))
        assert any(expected in problem for problem in problems), problems

    @pytest.mark.parametrize(("field_name", "value", "expected"), ROW_TAMPER_CASES)
    def test_the_untampered_row_is_accepted_for_the_same_field(
        self, field_name: str, value: str, expected: str
    ) -> None:
        """Anti-vacuity, per field: the identical call path with the ORIGINAL value must return
        no problems, so a control cannot pass because the reconciler rejects everything."""
        opening, closing, decisions, report = _resolved_move()
        assert report.movement is not None
        original = getattr(report.movement.movements[0], field_name)
        assert original != value
        assert (
            _reconcile(opening, closing, decisions, _with_row(report, **{field_name: original}))
            == []
        )


class TestGroup54EntryAgreement:
    @pytest.mark.parametrize(
        "param",
        [
            "formation_id",
            "formation_display_name",
            "branch",
            "origin_theater_id",
            "origin_theater_display_name",
            "destination_theater_id",
            "destination_theater_display_name",
        ],
    )
    def test_each_entry_param_must_equal_its_row_field(self, param: str) -> None:
        """Proof 10, field by field: the entry and the row are one record written twice."""
        opening, closing, decisions, report = _resolved_move()
        entries = []
        for entry in report.entries:
            if entry.reason_id == "formation_moved":
                entry = entry.model_copy(
                    update={"params": {**entry.params, param: "tampered_value"}}
                )
            entries.append(entry)
        problems = _reconcile(
            opening, closing, decisions, report.model_copy(update={"entries": entries})
        )
        assert problems, param

    def test_an_entry_with_a_missing_param_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        entries = []
        for entry in report.entries:
            if entry.reason_id == "formation_moved":
                params = {k: v for k, v in entry.params.items() if k != "branch"}
                entry = entry.model_copy(update={"params": params})
            entries.append(entry)
        problems = _reconcile(
            opening, closing, decisions, report.model_copy(update={"entries": entries})
        )
        assert any("expected exactly" in problem for problem in problems)

    def test_an_entry_with_the_wrong_category_is_detected(self) -> None:
        opening, closing, decisions, report = _resolved_move()
        entries = [
            e.model_copy(update={"category": "budget"}) if e.reason_id == "formation_moved" else e
            for e in report.entries
        ]
        problems = _reconcile(
            opening, closing, decisions, report.model_copy(update={"entries": entries})
        )
        assert any("expected 'military'" in problem for problem in problems)


class TestGroup54IsWiredIntoHistoryValidation:
    """Group 54 must be reachable through the aggregation, not only by direct call.

    Uses the repository's existing "knowledgeable tamperer" harness, which re-links and re-hashes
    the whole downstream chain, so `validate_history` finds no hash problem at all and whatever it
    does report is attributable to semantic reconciliation.
    """

    def _quiet_save(self):
        from app.simulation.history import new_game
        from app.simulation.save_format import SAVE_FORMAT_VERSION

        opening = load_scenario_file(TINY_VALID)
        return advance_n(new_game(opening, save_format_version=SAVE_FORMAT_VERSION), 1)

    def test_an_untampered_history_validates_cleanly(self) -> None:
        """Anti-vacuity for the control below: the detection must not be an artefact of how the
        save is assembled."""
        from app.simulation.history import validate_history

        save = self._quiet_save()
        assert hash_chain_problems(save) == []
        assert validate_history(save) == []

    def test_a_formation_teleported_in_a_stored_state_is_caught(self) -> None:
        from app.simulation.history import validate_history

        save = self._quiet_save()
        state = json.loads(save.entries[-1].state_json)
        formations = state["world"]["countries"][COUNTRY]["military"]["formations"]
        formations[FORMATION]["location_theater_id"] = DESTINATION
        tampered = retamper_state_with_consistent_hash(
            save, index=len(save.entries) - 1, tampered_state_json=json.dumps(state)
        )

        assert hash_chain_problems(tampered) == [], "the chain must be intact, not the point here"
        problems = validate_history(tampered)
        assert any("group 54" in problem for problem in problems), problems

    def test_a_forged_movement_row_in_a_stored_report_is_caught(self) -> None:
        """The symmetric case: real state left alone, the stored REPORT forged to claim a move
        that never happened."""
        from app.simulation.history import validate_history

        save = self._quiet_save()
        report = json.loads(save.entries[-1].report_json)
        report["movement"]["movements"] = [
            {
                "formation_id": FORMATION,
                "display_name": "First Army of Arken",
                "branch": "army",
                "origin_theater_id": CAPITAL,
                "origin_theater_display_name": "Arken Capital Region",
                "destination_theater_id": DESTINATION,
                "destination_theater_display_name": "Northern March",
            }
        ]
        tampered = retamper_report_with_consistent_hash(
            save, index=len(save.entries) - 1, tampered_report_json=json.dumps(report)
        )

        assert hash_chain_problems(tampered) == []
        problems = validate_history(tampered)
        assert any("group 54" in problem for problem in problems), problems
