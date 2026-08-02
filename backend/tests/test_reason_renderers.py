"""Proves every `reason_id` this build can actually emit has a registered
English renderer (R7), and that an unknown id gets a safe fallback rather
than a crash or a wrong display.
"""

from __future__ import annotations

from app.cli import REASON_RENDERERS, render_entry
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.report import TurnReportEntry
from app.simulation.resolver import resolve_turn
from app.simulation.state import SpendingCategory
from tests.conftest import SCENARIO_DIR

_SAMPLE_PARAMS: dict[str, dict[str, str | int]] = {
    "turn_resolved": {"turn": 3},
    "no_budget_changes_submitted": {},
    "tax_rate_changed": {"field": "personal_income_rate_bps", "old_bps": 2000, "new_bps": 2500},
    "spending_category_changed": {"category": "health", "old_amount": 100, "new_amount": 200},
    "deficit_financed_with_new_borrowing": {"amount": 12345},
}


def test_every_registered_reason_id_has_a_sample_and_renders_cleanly() -> None:
    assert set(_SAMPLE_PARAMS) == set(REASON_RENDERERS)
    for reason_id, params in _SAMPLE_PARAMS.items():
        entry = TurnReportEntry(category="budget", reason_id=reason_id, params=params)
        rendered = render_entry(entry)
        assert "unrendered reason_id" not in rendered
        assert "error rendering reason_id" not in rendered
        assert rendered  # non-empty


def test_unknown_reason_id_falls_back_safely_instead_of_crashing() -> None:
    entry = TurnReportEntry(category="budget", reason_id="not_a_real_reason", params={"x": 1})
    rendered = render_entry(entry)
    assert "unrendered reason_id='not_a_real_reason'" in rendered


def test_renderer_with_missing_expected_param_falls_back_instead_of_raising() -> None:
    # tax_rate_changed expects "field"/"old_bps"/"new_bps"; give it nothing.
    entry = TurnReportEntry(category="budget", reason_id="tax_rate_changed", params={})
    rendered = render_entry(entry)
    assert "error rendering reason_id='tax_rate_changed'" in rendered


def _resolve_with(scenario_name: str, decisions_tuple: tuple = ()) -> list[TurnReportEntry]:
    state = load_scenario_file(SCENARIO_DIR / scenario_name)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=decisions_tuple)
    resolution = resolve_turn(state, decisions)
    return resolution.report.entries


def test_real_resolver_output_never_hits_the_fallback_no_decision() -> None:
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "no_budget_changes_submitted" in ids
    assert "turn_resolved" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
        assert "unrendered" not in render_entry(entry)


def test_real_resolver_output_never_hits_the_fallback_tax_rate_change() -> None:
    entries = _resolve_with(
        "tiny_valid.yaml",
        (BudgetDecision(personal_income_rate_bps=2500),),
    )
    ids = {e.reason_id for e in entries}
    assert "tax_rate_changed" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS


def test_real_resolver_output_never_hits_the_fallback_spending_change() -> None:
    entries = _resolve_with(
        "tiny_valid.yaml",
        (
            BudgetDecision(
                spending_updates=(SpendingUpdate(category=SpendingCategory.HEALTH, amount=1),)
            ),
        ),
    )
    ids = {e.reason_id for e in entries}
    assert "spending_category_changed" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS


def test_real_resolver_output_never_hits_the_fallback_deficit_borrowing() -> None:
    entries = _resolve_with("deficit_demo.yaml")
    ids = {e.reason_id for e in entries}
    assert "deficit_financed_with_new_borrowing" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
