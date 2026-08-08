"""Tests for `LegislativeReport`/`ChamberVoteReport`/`BlocVoteReport`'s self-validation
(Phase 3B1), focused on the cross-row checks a single row cannot perform on itself: the (R4)
chamber-level largest-remainder replay, and the report-corrections-§2/§3 outcome matrix and
unique-target commitment reconstruction.

Corruption is via direct dict mutation on a real, freshly-resolved report's `model_dump(mode=
"json")` output, then re-parsed with `LegislativeReport.model_validate` -- the same pattern
`test_political_report.py`/`test_tax_base_report.py` already use.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import BudgetDecision, DecisionSet, InfluenceAllocation
from app.simulation.report import LegislativeReport
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR


def _valid_legislative_report_dict() -> dict:
    """A real, internally-consistent `LegislativeReport` (via the actual resolver, not
    hand-built): `tiny_valid`'s bicameral coalition passing the walkthrough proposal unaided in
    both chambers, so at least one chamber has a nonzero `extras_awarded` to corrupt."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    resolution = resolve_turn(state, decisions)
    legislative = resolution.report.legislative
    assert legislative is not None
    return legislative.model_dump(mode="json")


def _row_index(data: dict, *, party_id: str, bloc_id: str, chamber: str) -> int:
    return next(
        i
        for i, row in enumerate(data["blocs"])
        if row["party_id"] == party_id and row["bloc_id"] == bloc_id and row["chamber"] == chamber
    )


def test_a_valid_legislative_report_round_trips_through_model_validate() -> None:
    data = _valid_legislative_report_dict()
    LegislativeReport.model_validate(data)


def test_corrupted_bonus_seat_ordering_is_rejected() -> None:
    """(R4) A bonus seat moved from the row with the largest remainder to a row with a smaller
    one, while every individual row stays locally self-consistent (its own `numerator`/
    `base_seats`/`remainder`/`supporting_seats` still agree with each other) -- the one
    corruption class only `_chamber_apportionment_is_correct`'s cross-row replay can catch."""
    data = _valid_legislative_report_dict()
    chamber_report = next(c for c in data["chambers"] if c["extras_awarded"] >= 1)
    chamber_name = chamber_report["chamber"]
    rows = [row for row in data["blocs"] if row["chamber"] == chamber_name]

    bonus_row = next(row for row in rows if row["bonus_seat"])
    # Only rows that could physically accept a bonus without exceeding their own seat count
    # (P2) are eligible targets -- a full-support row (`base_seats == seats`, `remainder == 0`)
    # would trip the row-level P2 bound instead of exercising the largest-remainder cross-check
    # this test means to isolate.
    false_rows = sorted(
        (row for row in rows if not row["bonus_seat"] and row["base_seats"] < row["seats"]),
        key=lambda r: r["remainder"],
    )
    assert false_rows, "need at least one bonus-eligible non-bonus row to move the bonus to"
    target_row = false_rows[0]
    assert target_row["remainder"] < bonus_row["remainder"], (
        "the smallest-remainder row must have a strictly smaller remainder than the bonus row, "
        "or this isn't a genuine corruption"
    )

    bonus_idx = _row_index(
        data, party_id=bonus_row["party_id"], bloc_id=bonus_row["bloc_id"], chamber=chamber_name
    )
    target_idx = _row_index(
        data, party_id=target_row["party_id"], bloc_id=target_row["bloc_id"], chamber=chamber_name
    )
    data["blocs"][bonus_idx]["bonus_seat"] = False
    data["blocs"][bonus_idx]["supporting_seats"] = data["blocs"][bonus_idx]["base_seats"]
    data["blocs"][target_idx]["bonus_seat"] = True
    data["blocs"][target_idx]["supporting_seats"] = data["blocs"][target_idx]["base_seats"] + 1

    with pytest.raises(ValidationError, match="largest-remainder ordering"):
        LegislativeReport.model_validate(data)


def test_corrupted_chamber_aggregate_target_total_is_rejected() -> None:
    """The chamber-level largest-remainder aggregate (`target_total`/`extras_awarded`) is
    independently replayed from every bloc row seated in that chamber -- corrupting it alone,
    with no per-row change at all, must still be caught."""
    data = _valid_legislative_report_dict()
    data["chambers"][0]["target_total"] += 1
    data["chambers"][0]["supporting_seats"] += 1
    with pytest.raises(ValidationError, match="does not match"):
        LegislativeReport.model_validate(data)


def test_bicameral_commitment_is_reconstructed_from_unique_targets_not_summed_rows() -> None:
    """Report corrections §3: `civic_union/mainstream` is seated in both `tiny_valid` chambers and
    receives one allocation. The real commitment is that single allocation, not the allocation
    summed once per chamber row it happens to appear in."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(party_id="civic_union", bloc_id="mainstream", political_capital=50),
        ),
    )
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )
    resolution = resolve_turn(state, decisions)
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.political_capital_committed == 50

    data = legislative.model_dump(mode="json")
    mainstream_rows = [
        row
        for row in data["blocs"]
        if (row["party_id"], row["bloc_id"]) == ("civic_union", "mainstream")
    ]
    assert len(mainstream_rows) == 2  # seated in both chambers
    assert all(row["political_capital_allocated"] == 50 for row in mainstream_rows)

    data["political_capital_committed"] = 100  # the double-counted bug this guards against
    with pytest.raises(ValidationError, match="political_capital_committed"):
        LegislativeReport.model_validate(data)


def test_legislative_outcome_with_zero_chambers_is_rejected() -> None:
    """A legislative outcome (`PASSED_LEGISLATIVE`/`FAILED_LEGISLATIVE`) with zero chamber rows is
    never valid -- the matrix validator must not rely on Python's vacuous `all([])`."""
    data = _valid_legislative_report_dict()
    assert data["outcome"] == "passed_legislative"
    data["chambers"] = []
    data["blocs"] = []
    with pytest.raises(ValidationError, match="zero chambers"):
        LegislativeReport.model_validate(data)
