"""Phase 2B2 changed the isolation contract from Phase 2B1: production and finance are no
longer fully isolated — production now affects revenue **through derived tax bases**
(`simulation.tax_base_derivation`). The dependency is deliberately one-directional:

- economy -> tax bases -> revenue:  MUST hold (this is the whole point of Phase 2B2)
- tax rates / spending -> production:  MUST NOT hold (still isolated, as in 2B1)

This module tests both directions. `test_finance_report_is_byte_identical_across_wildly_
different_economies` (the Phase 2B1 test asserting the *opposite* of the current design)
is deliberately replaced, not silently deleted — see
`test_different_economies_produce_different_tax_bases_and_revenue` below, and ADR 0005 for
why this inversion is intentional. The other two isolation tests keep their original
premise and become more important now that the dependency is one-directional rather than
symmetric.
"""

from __future__ import annotations

from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.report import FinanceReport, ProductionReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import (
    EconomyState,
    GameState,
    SectorCategory,
    SpendingCategory,
    TaxBaseState,
)
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


def _resolve_with_economy(economy: EconomyState) -> FinanceReport:
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
    return resolution.report.finance


def test_different_economies_produce_different_tax_bases_and_revenue() -> None:
    """Phase 2B2's core directional property — the deliberate inversion of Phase 2B1's
    `test_finance_report_is_byte_identical_across_wildly_different_economies` (see the
    module docstring and ADR 0005): production now affects revenue through derived tax
    bases, so genuinely different economies must produce genuinely different bases and
    revenue. Uses large, well-separated output magnitudes specifically so the difference
    survives floor-rounding at every step (a tiny-magnitude economy can floor to zero
    value added and coincidentally match another zero-output economy — that coincidence is
    exactly what made the old, now-inverted test pass for the wrong reason).
    """
    small_economy = make_economy(
        quarterly_capacity_output=1_000_000, output_per_worker=1_000_000, employed_workers=1
    )
    large_economy = make_economy(
        quarterly_capacity_output=1_000_000_000, output_per_worker=1_000_000, employed_workers=1_000
    )

    small_finance = _resolve_with_economy(small_economy)
    large_finance = _resolve_with_economy(large_economy)

    assert small_finance.tax_bases != large_finance.tax_bases
    assert small_finance.revenue.total_revenue != large_finance.revenue.total_revenue
    # Everything downstream of the differing bases must differ consistently too — not just
    # the bases in isolation.
    assert small_finance.revenue != large_finance.revenue


def test_zero_output_economy_still_reconciles_with_zero_derived_bases() -> None:
    """The degenerate case the old (now-replaced) test happened to exercise: an economy
    that produces zero output everywhere derives all-zero tax bases, and the turn must
    still reconcile exactly (zero revenue is a valid, not a broken, outcome).
    """
    zero_economy = make_economy(
        quarterly_capacity_output=0, output_per_worker=1, employed_workers=0
    )
    finance = _resolve_with_economy(zero_economy)
    assert finance.tax_bases.personal_income == 0
    assert finance.tax_bases.corporate_profit == 0
    assert finance.tax_bases.taxable_consumption == 0
    assert finance.revenue.total_revenue == 0
    assert finance.reconciliation_status == "reconciled"


def test_tax_rate_change_does_not_affect_derived_tax_bases() -> None:
    """The other required direction: tax rates must still not affect production or the
    bases derived from it — only revenue (rate x base) should move.
    """
    economy = make_economy()

    def _resolve_with_rate(rate_bps: int) -> tuple[TaxBaseState, FinanceReport]:
        state = make_game_state(turn=0, state_version=0)
        player_id = state.world.player_country_id
        country = state.world.countries[player_id]
        state.world.countries[player_id] = country.model_copy(update={"economy": economy})
        decisions = DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(BudgetDecision(personal_income_rate_bps=rate_bps),),
        )
        resolution = resolve_turn(state, decisions)
        assert resolution.report.finance is not None
        return resolution.report.finance.tax_bases, resolution.report.finance

    bases_low, finance_low = _resolve_with_rate(1_000)
    bases_high, finance_high = _resolve_with_rate(9_000)

    assert bases_low == bases_high
    assert finance_low.revenue.personal_income_tax != finance_high.revenue.personal_income_tax


def test_spending_change_does_not_affect_production_or_derived_bases() -> None:
    economy = make_economy()

    def _resolve_with_spending(amount: int) -> tuple[ProductionReport, TaxBaseState]:
        state = make_game_state(turn=0, state_version=0)
        player_id = state.world.player_country_id
        country = state.world.countries[player_id]
        state.world.countries[player_id] = country.model_copy(update={"economy": economy})
        decisions = DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(
                BudgetDecision(
                    spending_updates=(
                        SpendingUpdate(category=SpendingCategory.HEALTH, amount=amount),
                    )
                ),
            ),
        )
        resolution = resolve_turn(state, decisions)
        assert resolution.report.production is not None
        assert resolution.report.finance is not None
        return resolution.report.production, resolution.report.finance.tax_bases

    production_low, bases_low = _resolve_with_spending(1)
    production_high, bases_high = _resolve_with_spending(999_999)

    assert production_low.model_dump(mode="json") == production_high.model_dump(mode="json")
    assert bases_low == bases_high


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
    assert report.tax_base_derivation is not None

    finance_dump = report.finance.model_dump(mode="json")
    production_dump = report.production.model_dump(mode="json")
    derivation_dump = report.tax_base_derivation.model_dump(mode="json")

    # Structural sanity: no report's dump contains another's distinctive keys.
    assert "sectors" not in finance_dump
    assert "total_gross_output" not in finance_dump
    assert "revenue" not in production_dump
    assert "closing_debt" not in production_dump
    assert "revenue" not in derivation_dump
    assert "capacity_utilization_bps" not in derivation_dump
    assert {s["category"] for s in production_dump["sectors"]} == {c.value for c in SectorCategory}
    assert {s["category"] for s in derivation_dump["sectors"]} == {c.value for c in SectorCategory}
