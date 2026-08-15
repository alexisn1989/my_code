"""Phase 3C, Gate 3C2: `CoupChannelReport`/`PopularUnrestChannelReport`/`ImpeachmentChannelReport`/
`CoupUnrestReport` self-validation, mirroring `test_election_report.py`'s own audit pattern.

Every genuinely reachable state (attempted vs not, succeeded vs not, eligible vs not, each of
popular unrest's four outcomes, and the fixed coup -> popular_unrest -> impeachment priority order)
is sourced from the REAL engine -- `resolve_turn` against `tiny_valid`/`deficit_demo`, sometimes
with a deliberately edited military/population/legitimacy value to make a low-probability branch
reachable within a small, declared seed search -- never hand-built from scratch. Each corruption
case is exercised through both `model_validate` (dict) and `model_validate_json` (equivalent JSON
string) via `_LOADERS`.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.report import (
    CoupChannelReport,
    CoupUnrestReport,
    ImpeachmentChannelReport,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import RemovalReason
from tests.conftest import SCENARIO_DIR


def _resolve_with_edits(
    *,
    scenario: str = "tiny_valid",
    seed: int | None = None,
    military_loyalty: int | None = None,
    legitimacy_bps: int | None = None,
    unrest_boost: bool = False,
) -> CoupUnrestReport:
    """A real `resolve_turn` call against `scenario`'s genesis state, with an optional edited
    seed/military-loyalty/legitimacy/population-unrest-boost -- exactly the same "edit one input,
    run the real engine" methodology `test_government_survival.py`'s own low-loyalty worked
    example uses (§11), never a hand-assembled report."""
    state = load_scenario_file(SCENARIO_DIR / f"{scenario}.yaml")
    if seed is not None:
        state = state.model_copy(update={"seed": seed})
    player = state.world.countries[state.world.player_country_id]
    if military_loyalty is not None:
        institutions = list(player.institutions)
        for index, institution_row in enumerate(institutions):
            if institution_row.id == "military":
                institutions[index] = institution_row.model_copy(
                    update={"loyalty": military_loyalty, "power": 10_000, "competence": 10_000}
                )
        player.institutions = institutions
    if unrest_boost:
        groups = list(player.population_groups)
        for index, group_row in enumerate(groups):
            groups[index] = group_row.model_copy(
                update={"approval": 0, "radicalization": 10_000, "organization": 10_000}
            )
        player.population_groups = groups
    if legitimacy_bps is not None:
        assert player.politics is not None
        player.politics = player.politics.model_copy(update={"legitimacy_bps": legitimacy_bps})
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    resolution = resolve_turn(state, decisions)
    coup_unrest = resolution.report.coup_unrest
    assert coup_unrest is not None
    return coup_unrest


def _baseline_dict() -> dict:  # type: ignore[type-arg]
    """A real, quiet turn: no channel attempts anything (`tiny_valid` genesis, seed 42)."""
    return _resolve_with_edits().model_dump(mode="json")


def _coup_attempted_not_succeeded_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(military_loyalty=0, seed=0).model_dump(mode="json")


def _coup_succeeded_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(military_loyalty=0, legitimacy_bps=0, seed=6).model_dump(mode="json")


def _unrest_contained_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(unrest_boost=True, seed=1).model_dump(mode="json")


def _unrest_forced_abdication_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(unrest_boost=True, legitimacy_bps=0, seed=1).model_dump(mode="json")


def _unrest_assassination_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(unrest_boost=True, legitimacy_bps=0, seed=149).model_dump(
        mode="json"
    )


def _impeachment_ineligible_dict() -> dict:  # type: ignore[type-arg]
    """`decree_state`'s genesis (`executive_selection: hereditary`) -- a real, structural
    ineligibility, not an edited one (see `test_government_survival.py`'s module docstring)."""
    return _resolve_with_edits(scenario="decree_state").model_dump(mode="json")


def _impeachment_attempted_not_succeeded_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(legitimacy_bps=0, seed=40).model_dump(mode="json")


def _impeachment_succeeded_dict() -> dict:  # type: ignore[type-arg]
    return _resolve_with_edits(legitimacy_bps=0, seed=129).model_dump(mode="json")


def _priority_order_both_succeed_dict() -> dict:  # type: ignore[type-arg]
    """A genuinely rare real state: coup AND popular unrest both succeed on the same real turn
    (found by a declared brute-force seed search, `military_loyalty=0`/`legitimacy_bps=0`/
    `unrest_boost=True`, seed 566 of the first 1,500 tried) -- proves the fixed priority order
    end-to-end against the real engine, not merely against a hand-constructed report."""
    return _resolve_with_edits(
        military_loyalty=0, legitimacy_bps=0, unrest_boost=True, seed=566
    ).model_dump(mode="json")


class TestRealEngineOutputsAreSelfConsistent:
    """Sanity: every fixture above is genuinely reachable and shaped the way its name claims,
    before any corruption test relies on it."""

    def test_baseline_nothing_attempted(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_baseline_dict())
        assert coup_unrest.coup.attempted is False
        assert coup_unrest.popular_unrest.attempted is False
        assert coup_unrest.popular_unrest.outcome == "none"
        assert coup_unrest.impeachment.eligible is True
        assert coup_unrest.impeachment.attempted is False
        assert coup_unrest.removal_triggered is None

    def test_coup_attempted_not_succeeded(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_coup_attempted_not_succeeded_dict())
        assert coup_unrest.coup.attempted is True
        assert coup_unrest.coup.succeeded is False
        assert coup_unrest.removal_triggered is None

    def test_coup_succeeded(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_coup_succeeded_dict())
        assert coup_unrest.coup.succeeded is True
        assert coup_unrest.removal_triggered == RemovalReason.COUP

    def test_unrest_contained(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_unrest_contained_dict())
        assert coup_unrest.popular_unrest.attempted is True
        assert coup_unrest.popular_unrest.succeeded is False
        assert coup_unrest.popular_unrest.outcome == "contained"
        assert coup_unrest.removal_triggered is None

    def test_unrest_forced_abdication(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_unrest_forced_abdication_dict())
        assert coup_unrest.popular_unrest.outcome == "forced_abdication"
        assert coup_unrest.removal_triggered == RemovalReason.FORCED_ABDICATION

    def test_unrest_assassination(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_unrest_assassination_dict())
        assert coup_unrest.popular_unrest.outcome == "assassination"
        assert coup_unrest.removal_triggered == RemovalReason.ASSASSINATION

    def test_impeachment_ineligible(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_impeachment_ineligible_dict())
        assert coup_unrest.impeachment.eligible is False
        assert coup_unrest.impeachment.attempted is None

    def test_impeachment_attempted_not_succeeded(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_impeachment_attempted_not_succeeded_dict())
        assert coup_unrest.impeachment.attempted is True
        assert coup_unrest.impeachment.succeeded is False
        assert coup_unrest.removal_triggered is None

    def test_impeachment_succeeded(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_impeachment_succeeded_dict())
        assert coup_unrest.impeachment.succeeded is True
        assert coup_unrest.removal_triggered == RemovalReason.IMPEACHMENT

    def test_priority_order_coup_wins_over_a_real_simultaneous_unrest_success(self) -> None:
        coup_unrest = CoupUnrestReport.model_validate(_priority_order_both_succeed_dict())
        assert coup_unrest.coup.succeeded is True
        assert coup_unrest.popular_unrest.succeeded is True
        assert coup_unrest.removal_triggered == RemovalReason.COUP


_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(CoupUnrestReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: CoupUnrestReport.model_validate_json(json.dumps(data)),
            id="model_validate_json",
        ),
    ],
)


class TestCoupChannelReportValidation:
    @_LOADERS
    def test_valid_reports_round_trip(self, load) -> None:
        for source in (_baseline_dict, _coup_attempted_not_succeeded_dict, _coup_succeeded_dict):
            load(source())

    @_LOADERS
    def test_attempt_risk_inconsistent_with_named_contributions_is_rejected(self, load) -> None:
        data = _baseline_dict()
        data["coup"]["attempt_risk_bps"] += 1
        with pytest.raises(ValidationError, match="does not match the four named contributions"):
            load(data)

    @_LOADERS
    def test_attempted_true_without_success_fields_is_rejected(self, load) -> None:
        data = _coup_attempted_not_succeeded_dict()
        data["coup"]["success_probability_bps"] = None
        data["coup"]["succeeded"] = None
        with pytest.raises(ValidationError, match="attempted=True requires"):
            load(data)

    @_LOADERS
    def test_attempted_false_with_success_fields_present_is_rejected(self, load) -> None:
        data = _baseline_dict()
        data["coup"]["success_probability_bps"] = 300
        data["coup"]["succeeded"] = False
        with pytest.raises(ValidationError, match="attempted=False forbids"):
            load(data)

    @_LOADERS
    def test_success_probability_inconsistent_with_military_and_legitimacy_is_rejected(
        self,
        load,
    ) -> None:
        data = _coup_attempted_not_succeeded_dict()
        data["coup"]["success_probability_bps"] += 1
        with pytest.raises(ValidationError, match="independently re-derived"):
            load(data)

    def test_coup_channel_report_alone_validates_out_of_context(self) -> None:
        """`CoupChannelReport` is a standalone model -- valid on its own, not only nested inside
        `CoupUnrestReport`."""
        data = _coup_succeeded_dict()["coup"]
        CoupChannelReport.model_validate(data)


class TestPopularUnrestChannelReportValidation:
    @_LOADERS
    def test_valid_reports_round_trip(self, load) -> None:
        for source in (
            _baseline_dict,
            _unrest_contained_dict,
            _unrest_forced_abdication_dict,
            _unrest_assassination_dict,
        ):
            load(source())

    @_LOADERS
    def test_attempt_risk_inconsistent_with_named_contributions_is_rejected(self, load) -> None:
        data = _baseline_dict()
        data["popular_unrest"]["attempt_risk_bps"] += 1
        with pytest.raises(ValidationError, match="does not match the two named contributions"):
            load(data)

    @_LOADERS
    def test_outcome_none_with_attempted_true_is_rejected(self, load) -> None:
        data = _unrest_contained_dict()
        data["popular_unrest"]["outcome"] = "none"
        with pytest.raises(ValidationError, match="is inconsistent with attempted"):
            load(data)

    @_LOADERS
    def test_outcome_contained_with_succeeded_true_is_rejected(self, load) -> None:
        data = _unrest_forced_abdication_dict()
        data["popular_unrest"]["outcome"] = "contained"
        with pytest.raises(ValidationError, match="is inconsistent with attempted"):
            load(data)

    @_LOADERS
    def test_success_probability_inconsistent_with_organization_and_legitimacy_is_rejected(
        self,
        load,
    ) -> None:
        data = _unrest_contained_dict()
        data["popular_unrest"]["success_probability_bps"] += 1
        with pytest.raises(ValidationError, match="independently re-derived"):
            load(data)


class TestImpeachmentChannelReportValidation:
    @_LOADERS
    def test_valid_reports_round_trip(self, load) -> None:
        for source in (
            _baseline_dict,
            _impeachment_ineligible_dict,
            _impeachment_attempted_not_succeeded_dict,
            _impeachment_succeeded_dict,
        ):
            load(source())

    @_LOADERS
    def test_eligible_true_with_a_missing_field_is_rejected(self, load) -> None:
        data = _baseline_dict()
        data["impeachment"]["attempt_risk_bps"] = None
        with pytest.raises(ValidationError, match="eligible=True requires"):
            load(data)

    @_LOADERS
    def test_eligible_false_with_a_stray_field_present_is_rejected(self, load) -> None:
        data = _impeachment_ineligible_dict()
        data["impeachment"]["legitimacy_bps"] = 5_000
        with pytest.raises(ValidationError, match="eligible=False forbids"):
            load(data)

    @_LOADERS
    def test_attempt_risk_inconsistent_with_named_contributions_is_rejected(self, load) -> None:
        data = _impeachment_attempted_not_succeeded_dict()
        data["impeachment"]["attempt_risk_bps"] += 1
        with pytest.raises(ValidationError, match="does not match the two named contributions"):
            load(data)

    @_LOADERS
    def test_success_probability_inconsistent_with_opposition_and_legitimacy_is_rejected(
        self,
        load,
    ) -> None:
        data = _impeachment_attempted_not_succeeded_dict()
        data["impeachment"]["success_probability_bps"] += 1
        with pytest.raises(ValidationError, match="independently re-derived"):
            load(data)

    def test_impeachment_channel_report_alone_validates_out_of_context(self) -> None:
        data = _impeachment_succeeded_dict()["impeachment"]
        ImpeachmentChannelReport.model_validate(data)


class TestCoupUnrestReportValidation:
    @_LOADERS
    def test_removal_triggered_inconsistent_with_priority_order_is_rejected(self, load) -> None:
        data = _coup_succeeded_dict()
        data["removal_triggered"] = "impeachment"
        with pytest.raises(ValidationError, match="does not match the fixed"):
            load(data)

    @_LOADERS
    def test_removal_triggered_none_when_a_channel_actually_succeeded_is_rejected(
        self,
        load,
    ) -> None:
        data = _coup_succeeded_dict()
        data["removal_triggered"] = None
        with pytest.raises(ValidationError, match="does not match the fixed"):
            load(data)

    @_LOADERS
    def test_forced_abdication_reported_as_removal_by_coup_is_rejected(self, load) -> None:
        data = _unrest_forced_abdication_dict()
        data["removal_triggered"] = "coup"
        with pytest.raises(ValidationError, match="does not match the fixed"):
            load(data)

    @_LOADERS
    def test_closing_transition_pressure_inconsistent_with_the_single_identity_is_rejected(
        self,
        load,
    ) -> None:
        data = _baseline_dict()
        data["closing_transition_pressure_bps"] += 1
        with pytest.raises(ValidationError, match="does not match opening - decayed \\+ added"):
            load(data)

    @_LOADERS
    def test_valid_reports_round_trip(self, load) -> None:
        for source in (
            _baseline_dict,
            _coup_succeeded_dict,
            _unrest_forced_abdication_dict,
            _unrest_assassination_dict,
            _impeachment_succeeded_dict,
            _impeachment_ineligible_dict,
            _priority_order_both_succeed_dict,
        ):
            load(source())
