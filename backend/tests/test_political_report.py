"""Tests for `PoliticalReport`'s ten self-validators and `TurnReport`'s political-specific
cross-validators (Phase 3A, T-R1/T-R3).

Each of the ten self-validators is corrupted independently, proving each one is checked -- not
merely that *some* validator catches a broadly-wrong report. Corruption is via direct dict
mutation on a real, freshly-resolved report's `model_dump(mode="json")` output, then re-parsed
with `TurnReport.model_validate` (and, for the first two, also `model_validate_json`) — proving
the self-validation survives both parse paths, matching every other report's established pattern.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.simulation.decisions import DecisionSet
from app.simulation.report import PoliticalReport, TurnReport
from app.simulation.resolver import resolve_turn
from tests.conftest import make_game_state


def _first_turn_report_dict() -> dict:
    """Turn 1: `opening_economic_baseline is None`, exercising the None-baseline branch."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    report = resolve_turn(state, decisions).report
    return report.model_dump(mode="json")


def _second_turn_report_dict() -> dict:
    """Turn 2: `opening_economic_baseline` is present, exercising the has-baseline branch."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    first = resolve_turn(state, decisions)
    second = resolve_turn(
        first.state, DecisionSet(expected_turn=1, expected_state_version=1, decisions=())
    )
    return second.report.model_dump(mode="json")


# --- T-R1: one corruption test per self-validator, 10 total ------------------


def test_valid_report_round_trips_through_model_validate_and_model_validate_json() -> None:
    data = _first_turn_report_dict()
    TurnReport.model_validate(data)
    TurnReport.model_validate_json(json.dumps(data))


def test_corrupted_constitution_digest_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["constitution"]["constitution_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="constitution_digest"):
        TurnReport.model_validate(data)
    with pytest.raises(ValidationError, match="constitution_digest"):
        TurnReport.model_validate_json(json.dumps(data))


def test_corrupted_output_change_bps_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["output_change_bps"] += 1
    with pytest.raises(ValidationError, match="output_change_bps"):
        TurnReport.model_validate(data)


def test_corrupted_output_contribution_bps_is_rejected() -> None:
    data = _second_turn_report_dict()
    data["political"]["output_contribution_bps"] += 1
    with pytest.raises(ValidationError, match="output_contribution_bps"):
        TurnReport.model_validate(data)


def test_corrupted_unemployment_change_bps_is_rejected() -> None:
    data = _second_turn_report_dict()
    data["political"]["unemployment_change_bps"] += 1
    with pytest.raises(ValidationError, match="unemployment_change_bps"):
        TurnReport.model_validate(data)


def test_corrupted_unemployment_contribution_bps_is_rejected() -> None:
    data = _second_turn_report_dict()
    data["political"]["unemployment_contribution_bps"] += 1
    with pytest.raises(ValidationError, match="unemployment_contribution_bps"):
        TurnReport.model_validate(data)


def test_corrupted_performance_contribution_bps_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["performance_contribution_bps"] += 1
    with pytest.raises(ValidationError, match="performance_contribution_bps"):
        TurnReport.model_validate(data)


def test_corrupted_order_support_contribution_bps_is_rejected() -> None:
    """The corruption itself proves R1's structural claim: this validator's re-derivation reads
    only `constitutional_order_support_bps` and `opening_legitimacy_bps` -- there is no
    `constitution` reference anywhere the formula could use, so no constitutional-axis corruption
    could ever affect it."""
    data = _first_turn_report_dict()
    data["political"]["order_support_contribution_bps"] += 1
    with pytest.raises(ValidationError, match="order_support_contribution_bps"):
        TurnReport.model_validate(data)


def test_corrupted_total_legitimacy_change_bps_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["total_legitimacy_change_bps"] += 1
    with pytest.raises(ValidationError, match="total_legitimacy_change_bps"):
        TurnReport.model_validate(data)


def test_corrupted_closing_legitimacy_bps_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["closing_legitimacy_bps"] += 1
    with pytest.raises(ValidationError, match="closing_legitimacy_bps"):
        TurnReport.model_validate(data)


def test_corrupted_political_capital_regeneration_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["political_capital_regeneration"] += 1
    with pytest.raises(ValidationError, match="political_capital_regeneration"):
        TurnReport.model_validate(data)


def test_corrupted_closing_political_capital_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["closing_political_capital"] += 1
    with pytest.raises(ValidationError, match="closing_political_capital"):
        TurnReport.model_validate(data)


# --- T-S1c (Phase 3B1): a report cannot claim more was spent than was held ----


def test_a_report_spending_more_than_the_opening_stock_is_rejected() -> None:
    """The report's guard mirrors `resolve_political_capital`'s, so a hand-edited or
    maliciously-constructed save cannot describe a turn the engine would have refused to resolve.

    Corrupting `political_capital_spent` alone would also break the closing identity, so the
    closing value is repaired to what the identity demands — leaving the spend guard as the only
    thing that can reject this report.
    """
    data = _first_turn_report_dict()
    political = data["political"]
    overspend = political["opening_political_capital"] + 1
    political["political_capital_spent"] = overspend
    political["closing_political_capital"] = min(
        political["political_capital_capacity"],
        political["opening_political_capital"]
        + political["political_capital_regeneration"]
        - overspend,
    )
    with pytest.raises(ValidationError, match="exceeds opening_political_capital"):
        TurnReport.model_validate(data)


def test_a_report_spending_exactly_the_opening_stock_is_accepted() -> None:
    """The boundary stays inclusive at the report layer too — otherwise a government that
    committed everything it held could resolve a turn it could not then record.

    Validated against `PoliticalReport` directly (not the full `TurnReport`): as of Phase 3B1,
    `political_capital_spent` must also agree with `LegislativeReport.political_capital_committed`
    (see `test_legislative_report.py`), so an arbitrary hand-patched spend value can no longer be
    round-tripped through `TurnReport` in isolation — but `PoliticalReport`'s own boundary
    validator is exactly what this test means to exercise.
    """
    data = _first_turn_report_dict()
    political = data["political"]
    spent = political["opening_political_capital"]
    political["political_capital_spent"] = spent
    political["closing_political_capital"] = min(
        political["political_capital_capacity"],
        political["opening_political_capital"]
        + political["political_capital_regeneration"]
        - spent,
    )
    PoliticalReport.model_validate(political)


def test_baseline_lifecycle_none_opening_with_nonzero_change_is_rejected() -> None:
    """(R2) On the None-opening-baseline branch, ALL FOUR performance/change fields must be
    exactly 0. `_output_change_matches_formula` (an earlier validator) already independently
    derives 0 for this same case, so corrupting `output_change_bps` alone is caught there first
    (see `test_corrupted_output_change_bps_is_rejected`) -- isolating
    `_baseline_lifecycle_is_coherent`'s OWN copy of this check requires bypassing every earlier
    validator via `model_construct` and invoking this one method directly."""
    data = _first_turn_report_dict()
    valid_report = TurnReport.model_validate(data)
    assert valid_report.political is not None
    assert valid_report.political.opening_economic_baseline is None
    bypassed_political = valid_report.political.__class__.model_construct(
        **{
            **dict(valid_report.political),
            "output_change_bps": 100,
            "output_contribution_bps": 25,
        }
    )
    with pytest.raises(ValueError, match="opening_economic_baseline is None"):
        bypassed_political.__class__._baseline_lifecycle_is_coherent(bypassed_political)


def test_baseline_lifecycle_closing_output_mismatch_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["closing_economic_baseline"]["total_gross_output"] += 1
    with pytest.raises(ValidationError, match="closing_economic_baseline.total_gross_output"):
        TurnReport.model_validate(data)


def test_baseline_lifecycle_source_turn_gap_is_rejected() -> None:
    """Turn 2's opening baseline (turn 1's closing) must be exactly one turn before its own
    closing baseline (turn 2) -- a two-turn gap is rejected by `_baseline_lifecycle_is_coherent`,
    independent of `TurnReport`'s own `resolved_turn` cross-check (T-R3, below)."""
    data = _second_turn_report_dict()
    data["political"]["opening_economic_baseline"]["source_turn"] -= 1
    with pytest.raises(
        ValidationError, match="does not equal opening_economic_baseline.source_turn"
    ):
        TurnReport.model_validate(data)


# --- T-R3: TurnReport's political<->production/labor_market cross-checks -----


def test_current_total_gross_output_mismatch_with_production_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["current_total_gross_output"] += 1
    with pytest.raises(ValidationError, match="current_total_gross_output"):
        TurnReport.model_validate(data)


def test_current_unemployment_rate_mismatch_with_labor_market_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["current_unemployment_rate_bps"] += 1
    with pytest.raises(ValidationError, match="current_unemployment_rate_bps"):
        TurnReport.model_validate(data)


def test_closing_baseline_source_turn_mismatch_with_resolved_turn_is_rejected() -> None:
    data = _first_turn_report_dict()
    data["political"]["closing_economic_baseline"]["source_turn"] += 1
    with pytest.raises(ValidationError, match="does not match resolved_turn"):
        TurnReport.model_validate(data)


def test_opening_baseline_source_turn_mismatch_with_resolved_turn_is_rejected() -> None:
    """Given `closing.source_turn == resolved_turn + 1` (TurnReport's own check) and
    `closing.source_turn == opening.source_turn + 1` (PoliticalReport's own internal check),
    `opening.source_turn == resolved_turn` is already mathematically implied through any
    normally-validated path -- so isolating THIS specific redundant check requires bypassing
    every validator on the way in via `model_construct` and invoking the method directly."""
    data = _second_turn_report_dict()
    valid_report = TurnReport.model_validate(data)
    assert valid_report.political is not None
    assert valid_report.political.opening_economic_baseline is not None
    bypassed_opening = valid_report.political.opening_economic_baseline.model_copy(
        update={"source_turn": valid_report.political.opening_economic_baseline.source_turn - 1}
    )
    bypassed_political = PoliticalReport.model_construct(
        **{**dict(valid_report.political), "opening_economic_baseline": bypassed_opening}
    )
    bypassed_report = TurnReport.model_construct(
        **{**dict(valid_report), "political": bypassed_political}
    )
    with pytest.raises(ValueError, match="does not match resolved_turn"):
        TurnReport._political_baseline_source_turns_match_resolved_turn(bypassed_report)
