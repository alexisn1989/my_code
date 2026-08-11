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
    "sector_inactive": {"category": "construction"},
    "labor_market_resolved": {
        "effective_labor_force": 600000,
        "total_employment": 540000,
        "unemployed_workers": 60000,
        "unfilled_jobs": 0,
        "unemployment_rate_bps": 1000,
    },
    "resource_extraction_resolved": {
        "deposits_active": 8,
        "deposits_depleted": 0,
        "total_extraction_workers": 13500,
        "unassigned_resource_workers": 6500,
        "extraction_sector_real_output": 2_000_000_000,
        "extraction_sector_potential_output": 2_000_000_000,
    },
    "production_summary": {
        "total_employment": 21550,
        "total_gross_output": 1765000,
        "sectors_capacity_constrained": 3,
        "sectors_labor_constrained": 3,
        "sectors_exactly_balanced": 3,
        "sectors_inactive": 2,
    },
    "tax_bases_derived": {
        "personal_income": 4000000000,
        "corporate_profit": 2000000000,
        "taxable_consumption": 3000000000,
    },
    "legitimacy_resolved": {
        "opening_legitimacy_bps": 6459,
        "order_support_contribution_bps": 4,
        "performance_contribution_bps": -250,
        "total_legitimacy_change_bps": -246,
        "closing_legitimacy_bps": 6213,
        "constitutional_order_support_bps": 6500,
    },
    "political_capital_resolved": {
        "opening": 500,
        "regeneration": 413,
        "spent": 0,
        "capacity": 1000,
        "closing": 913,
    },
    "legislative_vote_resolved": {
        "route": "legislative",
        "outcome": "passed_legislative",
        "chambers_passed": 2,
        "chambers_total": 2,
        "supporting_seats": 91,
        "required_yes_seats": 82,
        "political_capital_committed": 0,
    },
    "budget_blocked_by_legislature": {
        "chamber": "lower",
        "supporting_seats": 47,
        "required_yes_seats": 51,
        "shortfall_seats": 4,
    },
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


def test_real_resolver_output_never_hits_the_fallback_labor_market_resolved() -> None:
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "labor_market_resolved" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
        assert "unrendered" not in render_entry(entry)


def test_real_resolver_output_never_hits_the_fallback_resource_extraction_resolved() -> None:
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "resource_extraction_resolved" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
        assert "unrendered" not in render_entry(entry)


def test_real_resolver_output_never_hits_the_fallback_production_summary() -> None:
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "production_summary" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
        assert "unrendered" not in render_entry(entry)


def test_real_resolver_output_never_hits_the_fallback_sector_inactive() -> None:
    # tiny_valid.yaml's arken economy has two zero-capacity sectors (construction,
    # public_services) by design, so sector_inactive must be emitted for real.
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "sector_inactive" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS


def test_real_resolver_output_never_hits_the_fallback_tax_bases_derived() -> None:
    entries = _resolve_with("tiny_valid.yaml")
    ids = {e.reason_id for e in entries}
    assert "tax_bases_derived" in ids
    for entry in entries:
        assert entry.reason_id in REASON_RENDERERS
        assert "unrendered" not in render_entry(entry)


# --- Phase 3B1 (§14): the two approved legislative reason IDs --------------------------------


def test_legislative_vote_resolved_renders_a_bicameral_total_as_an_explicit_total() -> None:
    """(§14) `supporting_seats`/`required_yes_seats` MAY be sums for a bicameral report, but the
    renderer must say so — passage is decided per chamber, and a reader who took 91-against-82 as
    "the vote" would have the mechanism exactly wrong."""
    entry = TurnReportEntry(
        category="politics",
        reason_id="legislative_vote_resolved",
        params=_SAMPLE_PARAMS["legislative_vote_resolved"],
    )
    rendered = render_entry(entry)
    assert "2 of 2 chamber(s) passed" in rendered
    assert "totalled across 2 separately decided chambers" in rendered
    assert "each chamber must reach its own majority independently" in rendered
    assert "Political capital committed: 0." in rendered


def test_legislative_vote_resolved_renders_a_decree_without_implying_a_lost_vote() -> None:
    """A decree carries zeros for every chamber field because no chamber voted. Rendering that
    literally ("0 of 0 chambers passed") would read as a defeat; it must say no vote was held."""
    entry = TurnReportEntry(
        category="politics",
        reason_id="legislative_vote_resolved",
        params={
            "route": "decree",
            "outcome": "enacted_by_decree",
            "chambers_passed": 0,
            "chambers_total": 0,
            "supporting_seats": 0,
            "required_yes_seats": 0,
            "political_capital_committed": 250,
        },
    )
    rendered = render_entry(entry)
    assert "enacted through executive decree authority" in rendered
    assert "no chamber vote held" in rendered
    assert "0 of 0" not in rendered
    assert "Political capital committed: 250." in rendered


def test_budget_blocked_by_legislature_names_the_chamber_and_its_shortfall() -> None:
    entry = TurnReportEntry(
        category="politics",
        reason_id="budget_blocked_by_legislature",
        params=_SAMPLE_PARAMS["budget_blocked_by_legislature"],
    )
    rendered = render_entry(entry)
    assert "lower chamber" in rendered
    assert "47 supporting seats against 51 required" in rendered
    assert "short 4" in rendered


def test_both_legislative_reason_ids_fall_back_safely_on_missing_params() -> None:
    for reason_id in ("legislative_vote_resolved", "budget_blocked_by_legislature"):
        rendered = render_entry(
            TurnReportEntry(category="politics", reason_id=reason_id, params={})
        )
        assert f"error rendering reason_id={reason_id!r}" in rendered


def _legislative_entries(scenario_name: str, decisions_tuple: tuple = ()) -> list[TurnReportEntry]:
    return [
        entry
        for entry in _resolve_with(scenario_name, decisions_tuple)
        if entry.reason_id in ("legislative_vote_resolved", "budget_blocked_by_legislature")
    ]


def test_no_proposal_emits_neither_legislative_reason_id() -> None:
    """No proposal was made, so there is no vote to report and no chamber that blocked one."""
    assert _legislative_entries("tiny_valid.yaml") == []


def test_a_passed_vote_emits_only_the_vote_resolved_reason() -> None:
    entries = _legislative_entries(
        "tiny_valid.yaml", (BudgetDecision(personal_income_rate_bps=2500),)
    )
    assert [e.reason_id for e in entries] == ["legislative_vote_resolved"]
    params = entries[0].params
    assert params["route"] == "legislative"
    assert params["outcome"] == "passed_legislative"
    assert (params["chambers_passed"], params["chambers_total"]) == (2, 2)
    assert params["political_capital_committed"] == 0
    assert "unrendered" not in render_entry(entries[0])


def test_each_failed_chamber_emits_its_own_blocked_reason() -> None:
    """deficit_demo is unicameral and fails the walkthrough proposal 47/100 — exactly one blocked
    chamber, so exactly one blocked entry, naming that chamber."""
    entries = _legislative_entries(
        "deficit_demo.yaml", (BudgetDecision(personal_income_rate_bps=2000),)
    )
    assert [e.reason_id for e in entries] == [
        "legislative_vote_resolved",
        "budget_blocked_by_legislature",
    ]
    blocked = entries[1].params
    assert blocked["chamber"] == "lower"
    assert (blocked["supporting_seats"], blocked["required_yes_seats"]) == (47, 51)
    assert blocked["shortfall_seats"] == 4


def test_a_decree_emits_only_the_vote_resolved_reason_with_zeroed_chamber_fields() -> None:
    from app.simulation.legislature import ProposalRoute

    entries = _legislative_entries(
        "decree_state.yaml",
        (BudgetDecision(personal_income_rate_bps=2500, route=ProposalRoute.DECREE),),
    )
    assert [e.reason_id for e in entries] == ["legislative_vote_resolved"]
    params = entries[0].params
    assert params["route"] == "decree"
    assert params["outcome"] == "enacted_by_decree"
    assert params["chambers_passed"] == 0
    assert params["chambers_total"] == 0
    assert params["supporting_seats"] == 0
    assert params["required_yes_seats"] == 0
    assert params["political_capital_committed"] == 250


def test_every_reason_id_emitted_by_a_real_legislative_resolution_is_registered() -> None:
    """The umbrella guarantee, across all three routes: whatever the resolver actually emits has
    a registered renderer and a `_SAMPLE_PARAMS` entry."""
    from app.simulation.decisions import InfluenceAllocation
    from app.simulation.legislature import ProposalRoute

    cases: tuple[tuple[str, tuple], ...] = (
        ("tiny_valid.yaml", ()),
        ("tiny_valid.yaml", (BudgetDecision(personal_income_rate_bps=2500),)),
        ("deficit_demo.yaml", (BudgetDecision(personal_income_rate_bps=2000),)),
        (
            "decree_state.yaml",
            (
                BudgetDecision(
                    personal_income_rate_bps=2500,
                    influence=(
                        InfluenceAllocation(
                            party_id="opposition_party", bloc_id="main", political_capital=283
                        ),
                    ),
                ),
            ),
        ),
        (
            "decree_state.yaml",
            (BudgetDecision(personal_income_rate_bps=2500, route=ProposalRoute.DECREE),),
        ),
    )
    for scenario_name, decisions_tuple in cases:
        for entry in _resolve_with(scenario_name, decisions_tuple):
            assert entry.reason_id in REASON_RENDERERS, entry.reason_id
            assert entry.reason_id in _SAMPLE_PARAMS, entry.reason_id
            rendered = render_entry(entry)
            assert "unrendered" not in rendered
            assert "error rendering" not in rendered
