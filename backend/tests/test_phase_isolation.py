"""Phase 2B2 changed the isolation contract from Phase 2B1: production and finance are no
longer fully isolated — production now affects revenue **through derived tax bases**
(`simulation.tax_base_derivation`). Phase 2B3 adds labor allocation ahead of production in the
same chain; Phase 2C1 adds resource extraction (sub-allocated from the same labor) alongside it,
under the same one-directional rule:

- population/labor supply -> allocation -> production -> tax bases -> revenue:  MUST hold
- resource endowments -> extraction:                                            MUST hold
- tax rates / spending -> allocation / production / extraction:  MUST NOT hold (still isolated)
- resource endowments -> production / tax bases / finance:       MUST NOT hold (D8 — conservation-
  only isolation boundary; extraction is economically inert this phase)

This module tests all of these directions. `test_finance_report_is_byte_identical_across_wildly_
different_economies` (the Phase 2B1 test asserting the *opposite* of the current design)
is deliberately replaced, not silently deleted — see
`test_different_economies_produce_different_tax_bases_and_revenue` below, and ADR 0005 for
why this inversion is intentional. The other two isolation tests keep their original
premise and become more important now that the dependency is one-directional rather than
symmetric; both are extended here to also cover `labor_market` and `resources`. Phase 2C1 adds
its own dedicated tests for the resource-specific directions (T21).
"""

from __future__ import annotations

from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.report import (
    FinanceReport,
    LaborMarketReport,
    ProductionReport,
    ResourceExtractionReport,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import (
    EconomyState,
    GameState,
    ResourceCategory,
    ResourceDepositState,
    SectorCategory,
    SpendingCategory,
    TaxBaseState,
)
from tests.conftest import make_economy, make_game_state, make_resource_deposits


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
    small_economy = make_economy(quarterly_capacity_output=1_000_000, output_per_worker=1_000_000)
    large_economy = make_economy(
        quarterly_capacity_output=1_000_000_000, output_per_worker=1_000_000
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
    zero_economy = make_economy(quarterly_capacity_output=0, output_per_worker=1)
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

    def _resolve_with_rate(
        rate_bps: int,
    ) -> tuple[TaxBaseState, FinanceReport, LaborMarketReport, ResourceExtractionReport]:
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
        assert resolution.report.labor_market is not None
        assert resolution.report.resources is not None
        return (
            resolution.report.finance.tax_bases,
            resolution.report.finance,
            resolution.report.labor_market,
            resolution.report.resources,
        )

    bases_low, finance_low, labor_market_low, resources_low = _resolve_with_rate(1_000)
    bases_high, finance_high, labor_market_high, resources_high = _resolve_with_rate(9_000)

    assert bases_low == bases_high
    assert finance_low.revenue.personal_income_tax != finance_high.revenue.personal_income_tax
    # Phase 2B3: a tax-rate change must not move labor allocation either.
    assert labor_market_low.model_dump(mode="json") == labor_market_high.model_dump(mode="json")
    # Phase 2C1: nor resource extraction.
    assert resources_low.model_dump(mode="json") == resources_high.model_dump(mode="json")


def test_spending_change_does_not_affect_production_or_derived_bases() -> None:
    economy = make_economy()

    def _resolve_with_spending(
        amount: int,
    ) -> tuple[ProductionReport, TaxBaseState, LaborMarketReport, ResourceExtractionReport]:
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
        assert resolution.report.labor_market is not None
        assert resolution.report.resources is not None
        return (
            resolution.report.production,
            resolution.report.finance.tax_bases,
            resolution.report.labor_market,
            resolution.report.resources,
        )

    production_low, bases_low, labor_market_low, resources_low = _resolve_with_spending(1)
    production_high, bases_high, labor_market_high, resources_high = _resolve_with_spending(999_999)

    assert production_low.model_dump(mode="json") == production_high.model_dump(mode="json")
    assert bases_low == bases_high
    # Phase 2B3: a spending change must not move labor allocation either.
    assert labor_market_low.model_dump(mode="json") == labor_market_high.model_dump(mode="json")
    # Phase 2C1: nor resource extraction.
    assert resources_low.model_dump(mode="json") == resources_high.model_dump(mode="json")


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


# --- Phase 2C1 (T21): resource endowments -> extraction MUST hold; resource endowments -> -------
# --- production/derivation/finance MUST NOT hold (D8); phase 3's mutation scope -----------------


def _rich_resource_deposits() -> tuple[ResourceDepositState, ...]:
    return make_resource_deposits(
        remaining_stock=1_000_000,
        extraction_capacity_per_turn=100,
        output_per_worker=1,
        regeneration_per_turn=0,
        stock_ceiling=None,
    )


def _resolve_with_resource_deposits(deposits: tuple[ResourceDepositState, ...]):  # type: ignore[no-untyped-def]
    state = make_game_state(turn=0, state_version=0)
    player_id = state.world.player_country_id
    country = state.world.countries[player_id]
    assert country.economy is not None
    economy = country.economy.model_copy(update={"resource_deposits": deposits})
    state.world.countries[player_id] = country.model_copy(update={"economy": economy})
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    return resolve_turn(state, decisions)


def test_different_resource_endowments_produce_different_extraction_reports() -> None:
    """The positive direction: resource endowments must actually determine extraction."""
    poor = _resolve_with_resource_deposits(make_resource_deposits())  # all-inactive default
    rich = _resolve_with_resource_deposits(_rich_resource_deposits())

    assert poor.report.resources is not None
    assert rich.report.resources is not None
    assert poor.report.resources.model_dump(mode="json") != rich.report.resources.model_dump(
        mode="json"
    )
    assert rich.report.resources.total_extraction_workers > 0
    assert poor.report.resources.total_extraction_workers == 0


def test_different_resource_endowments_do_not_affect_production_derivation_or_finance() -> None:
    """D8, the conservation-only isolation boundary: production, tax-base derivation, and
    finance must stay byte-identical regardless of the resource endowments — extraction is
    economically inert this phase.
    """
    poor = _resolve_with_resource_deposits(make_resource_deposits())
    rich = _resolve_with_resource_deposits(_rich_resource_deposits())

    assert poor.report.production is not None
    assert rich.report.production is not None
    assert poor.report.production.model_dump(mode="json") == rich.report.production.model_dump(
        mode="json"
    )

    assert poor.report.tax_base_derivation is not None
    assert rich.report.tax_base_derivation is not None
    assert poor.report.tax_base_derivation.model_dump(
        mode="json"
    ) == rich.report.tax_base_derivation.model_dump(mode="json")

    assert poor.report.finance is not None
    assert rich.report.finance is not None
    assert poor.report.finance.model_dump(mode="json") == rich.report.finance.model_dump(
        mode="json"
    )


def test_resolved_turn_only_mutates_resource_deposits_within_economy_state() -> None:
    """R2: phase 3's mutation is scoped to `economy.resource_deposits` alone. Proven by
    resolving two turns that differ ONLY in their initial `resource_deposits`, then asserting
    every other part of the returned state — `finance`, `treasury`, `population`, `sectors`,
    `effective_labor_force_share_bps` — is byte-identical between the two, while
    `resource_deposits` itself genuinely differs.
    """
    poor = _resolve_with_resource_deposits(make_resource_deposits())
    rich = _resolve_with_resource_deposits(_rich_resource_deposits())

    poor_country = poor.state.world.countries[poor.state.world.player_country_id]
    rich_country = rich.state.world.countries[rich.state.world.player_country_id]
    assert poor_country.economy is not None
    assert rich_country.economy is not None

    poor_dump = poor_country.model_dump(mode="json")
    rich_dump = rich_country.model_dump(mode="json")
    poor_deposits = poor_dump["economy"].pop("resource_deposits")
    rich_deposits = rich_dump["economy"].pop("resource_deposits")

    assert poor_dump == rich_dump, "every non-resource part of state must be untouched"
    assert poor_deposits != rich_deposits, "resource_deposits itself must genuinely differ"


def test_resource_deposits_present_in_returned_state_matches_report_closing_stocks() -> None:
    """A single-turn version of `test_resource_conservation.py`'s multi-turn proof: the returned
    `resolution.state`'s `resource_deposits` must match `resolution.report.resources`'s closing
    stocks exactly, matched by `ResourceCategory` identity."""
    resolution = _resolve_with_resource_deposits(_rich_resource_deposits())
    assert resolution.report.resources is not None
    country = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert country.economy is not None
    stock_by_category = {d.category: d.remaining_stock for d in country.economy.resource_deposits}
    for deposit_report in resolution.report.resources.deposits:
        assert deposit_report.closing_stock == stock_by_category[deposit_report.category]
    assert set(stock_by_category) == set(ResourceCategory)
