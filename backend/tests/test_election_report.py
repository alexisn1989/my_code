"""Validation-hardening audit for `ElectionReport`/`PartyElectionStanceReport`'s self-validation
(Gate 3C1), mirroring `test_political_capital_report.py`'s own audit pattern exactly.

Each responsibility declared directly on `ElectionReport` (or on `PartyElectionStanceReport`, one
row model) gets at least one dedicated corruption test, exercised through **both**
`model_validate` (dict) and `model_validate_json` (equivalent JSON string) via the
`_ELECTION_LOADERS` parametrize decorator -- so each corruption case is actually two
separately-collected pytest items, not one loop hiding two assertions.

Sourcing strategy: a genuinely valid `ElectionReport` comes out of `resolve_turn` against
`tiny_valid.yaml` at its real, scheduled, WON turn-16 election (see
`test_government_survival_calibration.py` for the pinned figures this reproduces), dumped to a
dict, then exactly one claim is mutated per test.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.report import ElectionReport
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR

_ELECTION_LOADERS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(ElectionReport.model_validate, id="model_validate"),
        pytest.param(
            lambda data: ElectionReport.model_validate_json(json.dumps(data)),
            id="model_validate_json",
        ),
    ],
)


def _valid_election_dict() -> dict:  # type: ignore[type-arg]
    """A real, internally-consistent `ElectionReport` (scheduled, WON, with party rows) via the
    actual resolver driving `tiny_valid` to its real turn-16 election -- not hand-built."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    for _ in range(15):
        decisions = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        state = resolve_turn(state, decisions).state
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None
    assert election.scheduled
    assert election.result == "won"
    assert election.parties
    return election.model_dump(mode="json")


def _lost_election_dict() -> dict:  # type: ignore[type-arg]
    """A real, internally-consistent `ElectionReport` where the incumbent LOSES -- `deficit_demo`
    at its real turn-40 electoral defeat (see `test_government_survival_calibration.py`)."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    for _ in range(39):
        decisions = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        state = resolve_turn(state, decisions).state
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None
    assert election.result == "lost"
    return election.model_dump(mode="json")


def _not_scheduled_election_dict() -> dict:  # type: ignore[type-arg]
    """A real inert (`scheduled=False`) `ElectionReport`, from any turn before tiny_valid's first
    scheduled election."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    resolution = resolve_turn(state, decisions)
    election = resolution.report.election
    assert election is not None
    assert not election.scheduled
    return election.model_dump(mode="json")


@_ELECTION_LOADERS
def test_a_valid_scheduled_report_round_trips(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    report = load(data)
    assert report.scheduled
    assert report.result == "won"


@_ELECTION_LOADERS
def test_a_valid_not_scheduled_report_round_trips(load) -> None:  # type: ignore[no-untyped-def]
    data = _not_scheduled_election_dict()
    report = load(data)
    assert not report.scheduled
    assert report.result == "not_scheduled"


@_ELECTION_LOADERS
def test_1_not_scheduled_with_a_result_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _not_scheduled_election_dict()
    data["result"] = "won"
    with pytest.raises(ValidationError, match="scheduled=False requires"):
        load(data)


@_ELECTION_LOADERS
def test_1_not_scheduled_with_parties_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["scheduled"] = False
    data["result"] = "not_scheduled"
    # parties is left non-empty -- the other half of validator 1's requirement.
    with pytest.raises(ValidationError, match="scheduled=False requires"):
        load(data)


@_ELECTION_LOADERS
def test_2_final_support_not_matching_the_clamp_identity_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["final_support_bps"] += 1
    with pytest.raises(ValidationError, match="does not match"):
        load(data)


@_ELECTION_LOADERS
def test_3_required_support_bps_not_the_scale_constant_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["required_support_bps"] = 4_999
    with pytest.raises(ValidationError, match="REQUIRED_ELECTION_SUPPORT_BPS"):
        load(data)


@_ELECTION_LOADERS
def test_4_result_not_matching_support_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    assert data["result"] == "won"
    data["result"] = "lost"
    with pytest.raises(ValidationError, match="does not match expected"):
        load(data)


@_ELECTION_LOADERS
def test_4_term_limited_result_not_term_limit_exit_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["consecutive_terms_held"] = 2
    data["executive_term_limit_terms"] = 2
    # result stays "won" -- term_limited is now True, which requires "term_limit_exit".
    with pytest.raises(ValidationError, match="term_limit_exit"):
        load(data)


@_ELECTION_LOADERS
def test_5_liberalization_completed_without_a_win_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _lost_election_dict()
    data["liberalization_completed"] = True
    with pytest.raises(ValidationError, match="liberalization_completed=True requires"):
        load(data)


@_ELECTION_LOADERS
def test_6_parties_nonempty_while_ineligible_to_stand_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["eligible_to_stand"] = False
    with pytest.raises(ValidationError, match="parties must be empty"):
        load(data)


@_ELECTION_LOADERS
def test_7_parties_disagree_on_total_seats_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    assert len(data["parties"]) >= 2
    data["parties"][0]["total_seats"] += 1
    with pytest.raises(ValidationError, match="disagree on total_seats"):
        load(data)


@_ELECTION_LOADERS
def test_7_party_seats_do_not_sum_to_total_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    data["parties"][0]["seats"] += 1
    with pytest.raises(ValidationError, match="does not match parties\\[0\\].total_seats"):
        load(data)


@_ELECTION_LOADERS
def test_party_row_seats_exceeding_total_seats_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    data = _valid_election_dict()
    row = data["parties"][0]
    row["seats"] = row["total_seats"] + 1
    # Also fix up the OTHER rows' seats so validator 7 (sum == total_seats) doesn't mask this
    # case -- inflate this row's total_seats consistency is not the point; the per-row bound is.
    for other in data["parties"][1:]:
        other["seats"] = 0
    with pytest.raises(ValidationError, match="exceeds total_seats"):
        load(data)
