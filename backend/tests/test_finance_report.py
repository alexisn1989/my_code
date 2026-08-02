"""Tests for `FinanceReport`'s self-validation (R4): every reconciliation
equation and cross-total is independently re-checked on construction, on
every path — a fresh build, `model_validate` parsing stored JSON back out,
loading a save, or CLI history inspection all go through the same
`@model_validator` methods since they're all just "construct a `FinanceReport`."
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import BudgetDecision, DecisionSet
from app.simulation.report import FinanceReport
from app.simulation.resolver import resolve_turn
from tests.conftest import make_game_state


def _valid_finance_report_dict() -> dict:
    """A real, internally-consistent `FinanceReport` (via the actual resolver,
    not hand-built), dumped to a plain dict so tests can corrupt one field."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    finance = resolution.report.finance
    assert finance is not None
    return finance.model_dump(mode="json")


def test_a_valid_finance_report_round_trips_through_model_validate() -> None:
    data = _valid_finance_report_dict()
    report = FinanceReport.model_validate(data)
    assert report.reconciliation_status == "reconciled"


@pytest.mark.parametrize(
    ("path", "expected_message_substring"),
    [
        (("revenue", "total_revenue"), "revenue categories sum to"),
        (("revenue", "personal_income_tax"), "revenue.personal_income_tax does not match"),
        (("revenue", "corporate_tax"), "revenue.corporate_tax does not match"),
        (("revenue", "consumption_tax"), "revenue.consumption_tax does not match"),
        (("total_program_spending",), "active_spending_plan categories sum to"),
        (("quarterly_interest_expense",), "quarterly_interest_expense does not match"),
        (
            ("pre_financing_balance",),
            "does not equal total_revenue - total_program_spending",
        ),
        (("new_borrowing",), "does not equal the remaining shortfall"),
        (("closing_cash",), "does not match max(0, opening_cash"),
        (("closing_debt",), "does not equal opening_debt + new_borrowing"),
    ],
)
def test_each_corrupted_field_fails_with_its_own_specific_error(
    path: tuple[str, ...], expected_message_substring: str
) -> None:
    data = _valid_finance_report_dict()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = int(target[path[-1]]) + 1

    with pytest.raises(ValidationError) as exc_info:
        FinanceReport.model_validate(data)
    assert expected_message_substring in str(exc_info.value)


def test_corrupted_revenue_and_spending_together_still_fails_specifically() -> None:
    # Not required to report both at once (each @model_validator raises on
    # its own first failure) — but the FIRST one found must still be specific
    # and correct, not a generic catch-all.
    data = _valid_finance_report_dict()
    data["revenue"]["total_revenue"] = int(data["revenue"]["total_revenue"]) + 1
    data["closing_debt"] = int(data["closing_debt"]) + 1

    with pytest.raises(ValidationError) as exc_info:
        FinanceReport.model_validate(data)
    assert "revenue categories sum to" in str(exc_info.value)


def test_budget_change_entry_disagreeing_with_policy_snapshots_is_rejected() -> None:
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(
        expected_turn=0,
        expected_state_version=0,
        decisions=(BudgetDecision(personal_income_rate_bps=2_500),),
    )
    resolution = resolve_turn(state, decisions)
    finance = resolution.report.finance
    assert finance is not None
    data = finance.model_dump(mode="json")

    assert data["budget_changes"], "expected at least one recorded budget change"
    data["budget_changes"][0]["new_value"] += 1  # no longer matches active_tax_policy

    with pytest.raises(ValidationError) as exc_info:
        FinanceReport.model_validate(data)
    assert "disagrees with the" in str(exc_info.value)


def test_budget_change_entry_with_wrong_direction_label_is_rejected() -> None:
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(
        expected_turn=0,
        expected_state_version=0,
        decisions=(BudgetDecision(personal_income_rate_bps=2_500),),
    )
    resolution = resolve_turn(state, decisions)
    finance = resolution.report.finance
    assert finance is not None
    data = finance.model_dump(mode="json")

    assert data["budget_changes"][0]["direction"] == "increased"
    data["budget_changes"][0]["direction"] = "decreased"

    with pytest.raises(ValidationError) as exc_info:
        FinanceReport.model_validate(data)
    assert "has direction" in str(exc_info.value)


# --- the aggregate cash-flow equation: provably redundant given the other ---
# --- checks (see below), tested directly rather than via black-box corruption


def test_cash_flow_equation_validator_detects_a_direct_violation() -> None:
    """`_cash_flow_equation_holds` restates, as one aggregate equation, exactly
    what the more granular per-field checks (_pre_financing_balance_matches_formula,
    _borrowing_and_closing_cash_match_formula) already enforce individually.
    Algebraically, once those pass, the aggregate is implied — it can never be
    the *first* validator to fail under single-field corruption, since an
    earlier-declared validator always catches it first. This test proves the
    validator method itself is correct in isolation by calling it directly on
    an unvalidated instance (built via `model_construct`, which skips every
    validator), rather than trying to reach it through the full pipeline.
    """
    data = _valid_finance_report_dict()
    valid_report = FinanceReport.model_validate(data)

    # model_construct() skips every validator, letting us hold an
    # intentionally-inconsistent instance just long enough to call one
    # validator directly. Built from __dict__ (real field *instances*, e.g.
    # RevenueBreakdown objects) rather than model_dump() (which would give
    # plain dicts for nested models — model_construct does not re-validate
    # or re-instantiate them from that).
    unvalidated = FinanceReport.model_construct(
        **{**valid_report.__dict__, "closing_cash": valid_report.closing_cash + 1}
    )

    with pytest.raises(ValueError, match="cash-flow reconciliation failed"):
        FinanceReport._cash_flow_equation_holds(unvalidated)
