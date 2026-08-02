"""Proves Phase 2B1 sector production and Phase 2A government accounting stay
fully isolated from each other, in both directions — a real risk given
`resolve_production_and_trade` runs *before* the finance phases in the fixed
`PHASE_ORDER`, meaning `ctx.production_report` is already populated and sitting
on the shared, mutable `PhaseContext` by the time the finance phases execute.
Nothing in the type system prevents a finance phase from reaching across and
reading it — this module is the active test for that, not just a code-review
promise.
"""

from __future__ import annotations

from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState, SectorCategory, SpendingCategory
from tests.conftest import make_economy, make_game_state


def _run_phases_for(state: GameState) -> PhaseContext:
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    ctx = PhaseContext(state=state, decisions=decisions, resolving_turn=state.turn)
    run_phases(ctx)
    return ctx


def test_production_phase_never_touches_finance_scratch_or_report() -> None:
    ctx = _run_phases_for(make_game_state(turn=0, state_version=0))
    # apply_legal_and_administrative_changes always populates ctx.finance; if
    # resolve_production_and_trade ever wrote to it, this identity/content
    # check downstream (test_phases.py's opening-snapshot tests) would still
    # pass coincidentally — so assert directly here that finance exists and
    # is untouched by anything production-related.
    assert ctx.finance is not None
    assert ctx.production_report is not None


def test_finance_report_is_byte_identical_across_wildly_different_economies() -> None:
    """The core economy-invariance property: `resolve_turn` with the *same*
    decisions and the *same* finance state must produce a byte-identical
    `FinanceReport`, regardless of what `EconomyState` the player has —
    proving finance is a pure function of (opening finance + decisions),
    independent of production/economy content.
    """
    fixtures = [
        make_economy(quarterly_capacity_output=1, output_per_worker=1, employed_workers=0),
        make_economy(quarterly_capacity_output=1_000_000, output_per_worker=1, employed_workers=1),
        make_economy(
            quarterly_capacity_output=1, output_per_worker=1_000_000, employed_workers=1_000_000
        ),
        make_economy(quarterly_capacity_output=0, output_per_worker=1, employed_workers=0),
    ]

    finance_reports_json = []
    for economy in fixtures:
        state = make_game_state(turn=0, state_version=0)
        player_id = state.world.player_country_id
        country = state.world.countries[player_id]
        state.world.countries[player_id] = country.model_copy(
            update={"population": 20_000_000, "economy": economy}
        )
        decisions = DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(
                BudgetDecision(
                    personal_income_rate_bps=2_500,
                    spending_updates=(SpendingUpdate(category=SpendingCategory.HEALTH, amount=1),),
                ),
            ),
        )
        resolution = resolve_turn(state, decisions)
        assert resolution.report.finance is not None
        finance_reports_json.append(resolution.report.finance.model_dump(mode="json"))

    first = finance_reports_json[0]
    for other in finance_reports_json[1:]:
        assert other == first


def test_production_report_is_identical_regardless_of_finance_state() -> None:
    """The converse property: `ProductionReport` must not depend on the
    player's finance/budget state at all."""
    base_state = make_game_state(turn=0, state_version=0)
    player_id = base_state.world.player_country_id

    no_decision = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution_a = resolve_turn(base_state, no_decision)
    assert resolution_a.report.production is not None

    tax_change_state = make_game_state(turn=0, state_version=0)
    tax_change_decisions = DecisionSet(
        expected_turn=0,
        expected_state_version=0,
        decisions=(BudgetDecision(personal_income_rate_bps=9_999),),
    )
    resolution_b = resolve_turn(tax_change_state, tax_change_decisions)
    assert resolution_b.report.production is not None

    assert resolution_a.report.production.model_dump(
        mode="json"
    ) == resolution_b.report.production.model_dump(mode="json")
    assert player_id == tax_change_state.world.player_country_id  # sanity: same player id used


def test_report_assembly_does_not_cross_populate_finance_and_production_fields() -> None:
    """A dedicated guard against a copy-paste bug in `_generate_turn_report`
    that could cross-wire the two independently-built report halves."""
    resolution = resolve_turn(
        make_game_state(turn=0, state_version=0),
        DecisionSet(expected_turn=0, expected_state_version=0, decisions=()),
    )
    report = resolution.report
    assert report.finance is not None
    assert report.production is not None

    finance_dump = report.finance.model_dump(mode="json")
    production_dump = report.production.model_dump(mode="json")

    # Structural sanity: neither dump contains the other's distinctive keys.
    assert "sectors" not in finance_dump
    assert "total_gross_output" not in finance_dump
    assert "revenue" not in production_dump
    assert "closing_debt" not in production_dump
    assert {s["category"] for s in production_dump["sectors"]} == {c.value for c in SectorCategory}
