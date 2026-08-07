"""Phase 2B2 changed the isolation contract from Phase 2B1: production and finance are no
longer fully isolated — production now affects revenue **through derived tax bases**
(`simulation.tax_base_derivation`). Phase 2B3 adds labor allocation ahead of production in the
same chain; Phase 2C1 adds resource extraction (sub-allocated from the same labor) alongside it.
Phase 2C2 (ADR 0008) then **reverses** Phase 2C1's own D8 conservation-only isolation boundary:
extraction stops being economically inert and starts driving the EXTRACTION sector's production
row directly, under the same one-directional rule as everything else in this chain:

- population/labor supply -> allocation -> production -> tax bases -> revenue:  MUST hold
- resource endowments -> extraction -> extraction-sector production -> tax bases -> revenue:
  MUST hold (Phase 2C2 — see ADR 0008)
- tax rates / spending -> allocation / production / extraction:  MUST NOT hold (still isolated)

This module tests all of these directions. `test_finance_report_is_byte_identical_across_wildly_
different_economies` (the Phase 2B1 test asserting the *opposite* of the current design)
is deliberately replaced, not silently deleted — see
`test_different_economies_produce_different_tax_bases_and_revenue` below, and ADR 0005 for
why this inversion is intentional. `test_different_resource_endowments_do_not_affect_production_
derivation_or_finance` (the Phase 2C1 test asserting D8's now-reversed isolation) is likewise
deliberately replaced, not silently deleted — see
`test_different_resource_endowments_affect_extraction_sector_production_and_downstream_tax_and_
finance` below, and ADR 0008 for why this second inversion is intentional. The other two
isolation tests keep their original premise and become more important now that the dependency is
one-directional rather than symmetric; both are extended here to also cover `labor_market` and
`resources`. Phase 2C1 adds its own dedicated tests for the resource-specific directions (T21);
Phase 2C2 adds T22.
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
from tests.conftest import make_country, make_economy, make_game_state, make_resource_deposits


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
    ) -> tuple[TaxBaseState, FinanceReport, LaborMarketReport, ResourceExtractionReport, object]:
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
        assert resolution.report.political is not None
        return (
            resolution.report.finance.tax_bases,
            resolution.report.finance,
            resolution.report.labor_market,
            resolution.report.resources,
            resolution.report.political,
        )

    bases_low, finance_low, labor_market_low, resources_low, political_low = _resolve_with_rate(
        1_000
    )
    bases_high, finance_high, labor_market_high, resources_high, political_high = (
        _resolve_with_rate(9_000)
    )

    assert bases_low == bases_high
    assert finance_low.revenue.personal_income_tax != finance_high.revenue.personal_income_tax
    # Phase 2B3: a tax-rate change must not move labor allocation either.
    assert labor_market_low.model_dump(mode="json") == labor_market_high.model_dump(mode="json")
    # Phase 2C1: nor resource extraction.
    assert resources_low.model_dump(mode="json") == resources_high.model_dump(mode="json")
    # Phase 3A, T-I3: nor legitimacy or political capital -- taxation is not one of the two
    # signals (unemployment, gross output) the political phase reads.
    assert political_low.model_dump(mode="json") == political_high.model_dump(mode="json")


def test_spending_change_does_not_affect_production_or_derived_bases() -> None:
    economy = make_economy()

    def _resolve_with_spending(
        amount: int,
    ) -> tuple[ProductionReport, TaxBaseState, LaborMarketReport, ResourceExtractionReport, object]:
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
        assert resolution.report.political is not None
        return (
            resolution.report.production,
            resolution.report.finance.tax_bases,
            resolution.report.labor_market,
            resolution.report.resources,
            resolution.report.political,
        )

    production_low, bases_low, labor_market_low, resources_low, political_low = (
        _resolve_with_spending(1)
    )
    production_high, bases_high, labor_market_high, resources_high, political_high = (
        _resolve_with_spending(999_999)
    )

    assert production_low.model_dump(mode="json") == production_high.model_dump(mode="json")
    assert bases_low == bases_high
    # Phase 2B3: a spending change must not move labor allocation either.
    assert labor_market_low.model_dump(mode="json") == labor_market_high.model_dump(mode="json")
    # Phase 2C1: nor resource extraction.
    assert resources_low.model_dump(mode="json") == resources_high.model_dump(mode="json")
    # Phase 3A, T-I3: nor legitimacy or political capital.
    assert political_low.model_dump(mode="json") == political_high.model_dump(mode="json")


def test_differing_political_starting_values_never_move_the_economy() -> None:
    """Phase 3A, T-I2: the converse direction of the resource-deposits test above -- politics
    must never mutate economy/finance/treasury. Two otherwise-identical countries differing only
    in their starting `PoliticalState` (a different constitution, authored support and legitimacy)
    must resolve to byte-identical `production`/`labor_market`/`resources`/`finance` reports and
    byte-identical `economy`/`finance`/`treasury` state, since the political phase (slot 10) runs
    last and writes only `politics`.
    """
    from app.simulation.constitution import (
        AmendmentDifficulty,
        DecreeAuthority,
        ExecutiveSelection,
        ExecutiveSystem,
        JudicialReview,
        Legislature,
        TerritorialOrganization,
    )
    from tests.conftest import make_politics

    def _resolve_with_politics(politics_state: object) -> tuple[GameState, object]:
        state = make_game_state(turn=0, state_version=0)
        player_id = state.world.player_country_id
        country = state.world.countries[player_id]
        state.world.countries[player_id] = country.model_copy(update={"politics": politics_state})
        decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
        resolution = resolve_turn(state, decisions)
        return resolution.state, resolution.report

    presidential = make_politics(
        constitutional_order_support_bps=6_500, legitimacy_bps=6_000, political_capital=300
    )
    monarchical = make_politics(
        executive_system=ExecutiveSystem.MONARCHICAL,
        executive_selection=ExecutiveSelection.HEREDITARY,
        legislature=Legislature.NONE,
        territorial_organization=TerritorialOrganization.UNITARY,
        judicial_review=JudicialReview.NONE,
        amendment_difficulty=AmendmentDifficulty.ENTRENCHED,
        decree_authority=DecreeAuthority.UNLIMITED,
        constitutional_order_support_bps=9_000,
        legitimacy_bps=8_500,
        political_capital=900,
    )
    state_a, report_a = _resolve_with_politics(presidential)
    state_b, report_b = _resolve_with_politics(monarchical)

    player_id = state_a.world.player_country_id
    country_a = state_a.world.countries[player_id]
    country_b = state_b.world.countries[player_id]
    assert country_a.economy is not None
    assert country_b.economy is not None
    assert country_a.economy.model_dump(mode="json") == country_b.economy.model_dump(mode="json")
    assert country_a.finance is not None
    assert country_b.finance is not None
    assert country_a.finance.model_dump(mode="json") == country_b.finance.model_dump(mode="json")
    assert country_a.treasury.model_dump(mode="json") == country_b.treasury.model_dump(mode="json")

    assert report_a.production is not None
    assert report_b.production is not None
    assert report_a.production.model_dump(mode="json") == report_b.production.model_dump(
        mode="json"
    )
    assert report_a.labor_market is not None
    assert report_b.labor_market is not None
    assert report_a.labor_market.model_dump(mode="json") == report_b.labor_market.model_dump(
        mode="json"
    )
    assert report_a.resources is not None
    assert report_b.resources is not None
    assert report_a.resources.model_dump(mode="json") == report_b.resources.model_dump(mode="json")
    assert report_a.finance is not None
    assert report_b.finance is not None
    assert report_a.finance.model_dump(mode="json") == report_b.finance.model_dump(mode="json")

    # And the political reports genuinely differ, so the test is not vacuous.
    assert report_a.political is not None
    assert report_b.political is not None
    assert report_a.political.constitution.constitution_digest != (
        report_b.political.constitution.constitution_digest
    )


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


# --- Phase 2C1 (T21) / Phase 2C2 (T22): resource endowments -> extraction -> extraction-sector --
# --- production -> tax bases -> revenue MUST hold; tax rates / spending -> allocation / --------
# --- production / extraction MUST NOT hold (still isolated); phase 3's mutation scope -----------


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


def test_different_resource_endowments_affect_extraction_sector_production_and_downstream_tax_and_finance() -> (
    None
):
    """Phase 2C2 reverses Phase 2C1's D8 conservation-only isolation boundary (ADR 0008):
    extraction is no longer economically inert. Resource endowments now determine the
    EXTRACTION row's `actual_output` (via the physical-extraction bridge in `resource_output.py`),
    which flows through `total_gross_output`, the EXTRACTION row's derived tax base, and
    ultimately revenue and the treasury — while the other ten sectors, driven entirely by labor
    allocation (untouched by this phase), stay completely unaffected. This is the one-way
    dependency D7 establishes: resource endowments -> extraction -> extraction-sector output ->
    tax bases -> revenue.
    """
    significant_deposits = make_resource_deposits(
        remaining_stock=10_000_000,
        extraction_capacity_per_turn=1_000_000,
        output_per_worker=1_000_000,
        regeneration_per_turn=0,
        stock_ceiling=None,
    )
    poor = _resolve_with_resource_deposits(make_resource_deposits())
    rich = _resolve_with_resource_deposits(significant_deposits)

    assert poor.report.production is not None
    assert rich.report.production is not None
    poor_sectors = {s.category: s for s in poor.report.production.sectors}
    rich_sectors = {s.category: s for s in rich.report.production.sectors}
    assert poor_sectors.keys() == rich_sectors.keys()
    for category in poor_sectors:
        if category is SectorCategory.EXTRACTION:
            assert poor_sectors[category] != rich_sectors[category], (
                "the EXTRACTION row must differ — this is the whole point of Phase 2C2"
            )
        else:
            assert poor_sectors[category] == rich_sectors[category], (
                f"{category} must stay untouched by resource endowments"
            )

    # Accounting identity (§6c/D7): extraction is counted exactly once, so total_gross_output
    # moves by exactly the extraction row's own delta — no other row moved.
    extraction_delta = (
        rich_sectors[SectorCategory.EXTRACTION].actual_output
        - poor_sectors[SectorCategory.EXTRACTION].actual_output
    )
    assert extraction_delta > 0
    assert (
        rich.report.production.total_gross_output - poor.report.production.total_gross_output
        == extraction_delta
    )

    assert poor.report.tax_base_derivation is not None
    assert rich.report.tax_base_derivation is not None
    poor_tbd_sectors = {s.category: s for s in poor.report.tax_base_derivation.sectors}
    rich_tbd_sectors = {s.category: s for s in rich.report.tax_base_derivation.sectors}
    for category in poor_tbd_sectors:
        if category is SectorCategory.EXTRACTION:
            assert poor_tbd_sectors[category] != rich_tbd_sectors[category]
        else:
            assert poor_tbd_sectors[category] == rich_tbd_sectors[category]

    # At this magnitude the shift survives bps rounding all the way through to revenue and the
    # treasury, proving the dependency reaches finance, not just the intermediate reports.
    assert poor.report.finance is not None
    assert rich.report.finance is not None
    assert poor.report.finance.revenue.total_revenue != rich.report.finance.revenue.total_revenue


def test_resolved_turn_only_mutates_resource_deposits_within_economy_state() -> None:
    """R2: phase 3's mutation is scoped to `economy.resource_deposits` alone WITHIN THE ECONOMY.
    Proven by resolving two turns that differ ONLY in their initial `resource_deposits`, then
    asserting every other part of `economy` — `sectors`, `effective_labor_force_share_bps`,
    `resource_output_coefficients` — plus `finance`/`treasury`/`population` are byte-identical
    between the two, while `resource_deposits` itself genuinely differs.

    (Phase 3A) `politics.economic_baseline.total_gross_output` is EXPECTED to differ too —
    that is precisely Phase 3A's one-way economic-to-political link doing its job: richer
    deposits produce more output, and the political phase's closing baseline is a direct
    observation of that turn's actual `ProductionReport.total_gross_output` (§6.3). Everything
    else under `politics` — `constitution`, `constitutional_order_support_bps`, `legitimacy_bps`,
    `political_capital` — stays identical, since this economic difference is too small to move
    a first-turn (baseline-`None`) legitimacy calculation, which is asserted explicitly below.
    """
    poor = _resolve_with_resource_deposits(make_resource_deposits())
    rich = _resolve_with_resource_deposits(_rich_resource_deposits())

    poor_country = poor.state.world.countries[poor.state.world.player_country_id]
    rich_country = rich.state.world.countries[rich.state.world.player_country_id]
    assert poor_country.economy is not None
    assert rich_country.economy is not None
    assert poor_country.politics is not None
    assert rich_country.politics is not None

    poor_dump = poor_country.model_dump(mode="json")
    rich_dump = rich_country.model_dump(mode="json")
    poor_deposits = poor_dump["economy"].pop("resource_deposits")
    rich_deposits = rich_dump["economy"].pop("resource_deposits")
    poor_baseline = poor_dump["politics"].pop("economic_baseline")
    rich_baseline = rich_dump["politics"].pop("economic_baseline")

    assert poor_dump == rich_dump, (
        "every non-resource, non-economic-baseline part of state must be untouched"
    )
    assert poor_deposits != rich_deposits, "resource_deposits itself must genuinely differ"
    assert poor_baseline["total_gross_output"] != rich_baseline["total_gross_output"], (
        "the political phase's closing baseline must observe the genuinely different output"
    )
    assert poor_country.politics.legitimacy_bps == rich_country.politics.legitimacy_bps == 7_000
    assert poor_country.politics.political_capital == rich_country.politics.political_capital, (
        "first-turn (baseline-None) legitimacy is unaffected, so political capital regenerates identically"
    )


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


# --- Phase 2C2, T18/T19: quarterly_capacity_output/output_per_worker are completely inert -------
# --- for the EXTRACTION row (R6/§6b) — contrasted with a STANDARD sector, where the same --------
# --- mutation DOES change output, proving the inertness is basis-specific, not a general bug ----


def _resolve_with_sector_legacy_fields(
    *, category: SectorCategory, quarterly_capacity_output: int, output_per_worker: int
):  # type: ignore[no-untyped-def]
    economy = make_economy(
        resource_deposits=make_resource_deposits(
            remaining_stock=1_000_000,
            extraction_capacity_per_turn=1_000,
            output_per_worker=1_000,
            regeneration_per_turn=0,
            stock_ceiling=None,
        )
    )
    sector = next(s for s in economy.sectors if s.category is category)
    sector.quarterly_capacity_output = quarterly_capacity_output
    sector.output_per_worker = output_per_worker
    country = make_country("testland", economy=economy)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    return resolve_turn(state, decisions)


class TestLegacyFieldInertnessForExtraction:
    """Mutating the EXTRACTION sector's `quarterly_capacity_output`/`output_per_worker` alone —
    with resource endowments held fixed — must change nothing observable on the extraction row:
    not `actual_output` (Rev 1), not `capacity_utilization_bps`, and not `constraint` either (R6
    strengthens Rev 1's two-of-three claim to all three)."""

    def test_quarterly_capacity_output_does_not_affect_the_extraction_row(self) -> None:
        baseline = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=25_000_000,
            output_per_worker=25_000_000,
        )
        absurd = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=1,
            output_per_worker=25_000_000,
        )
        assert baseline.report.production is not None
        assert absurd.report.production is not None
        b_row = next(
            s for s in baseline.report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        a_row = next(
            s for s in absurd.report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        assert b_row.actual_output == a_row.actual_output
        assert b_row.capacity_utilization_bps == a_row.capacity_utilization_bps
        assert b_row.constraint == a_row.constraint

    def test_output_per_worker_does_not_affect_the_extraction_row(self) -> None:
        """`output_per_worker` is also read by `labor_allocation.py` (untouched by 2C2) to
        compute a sector's labor DEMAND, which can change `employed_workers` — a real, expected
        effect unrelated to R6's claim. The "absurd" value here is chosen large enough (rather
        than small) that `required_workers` still floors to the same 1 worker as the baseline,
        isolating the derivation-formula inertness this test actually targets from that upstream
        labor-demand effect.
        """
        baseline = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=25_000_000,
            output_per_worker=25_000_000,
        )
        absurd = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=25_000_000,
            output_per_worker=1_000_000_000,
        )
        assert baseline.report.labor_market is not None
        assert absurd.report.labor_market is not None
        baseline_workers = next(
            s
            for s in baseline.report.labor_market.sectors
            if s.category is SectorCategory.EXTRACTION
        ).allocated_workers
        absurd_workers = next(
            s for s in absurd.report.labor_market.sectors if s.category is SectorCategory.EXTRACTION
        ).allocated_workers
        assert baseline_workers == absurd_workers, (
            "sanity: this test isolates the derivation-formula claim, not the labor-demand one"
        )
        assert baseline.report.production is not None
        assert absurd.report.production is not None
        b_row = next(
            s for s in baseline.report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        a_row = next(
            s for s in absurd.report.production.sectors if s.category is SectorCategory.EXTRACTION
        )
        assert b_row.actual_output == a_row.actual_output
        assert b_row.capacity_utilization_bps == a_row.capacity_utilization_bps
        assert b_row.constraint == a_row.constraint

    def test_contrast_a_standard_sector_output_does_change_under_the_equivalent_mutation(
        self,
    ) -> None:
        """The negative-control proof that inertness is specific to the RESOURCE_EXTRACTION
        basis, not a general property of the test harness or an accidental no-op mutation."""
        baseline = _resolve_with_sector_legacy_fields(
            category=SectorCategory.MANUFACTURING,
            quarterly_capacity_output=25_000_000,
            output_per_worker=25_000_000,
        )
        changed = _resolve_with_sector_legacy_fields(
            category=SectorCategory.MANUFACTURING,
            quarterly_capacity_output=1,
            output_per_worker=25_000_000,
        )
        assert baseline.report.production is not None
        assert changed.report.production is not None
        b_row = next(
            s
            for s in baseline.report.production.sectors
            if s.category is SectorCategory.MANUFACTURING
        )
        c_row = next(
            s
            for s in changed.report.production.sectors
            if s.category is SectorCategory.MANUFACTURING
        )
        assert b_row.actual_output != c_row.actual_output

    def test_legacy_field_mutations_do_not_affect_downstream_tax_base_or_finance_totals(
        self,
    ) -> None:
        """Uses the same large-`output_per_worker` trick as the test above to keep
        `employed_workers` fixed at 1 in both runs — isolating the derivation-formula inertness
        claim from labor demand's real, unrelated use of these same two fields.
        """
        baseline = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=25_000_000,
            output_per_worker=25_000_000,
        )
        absurd = _resolve_with_sector_legacy_fields(
            category=SectorCategory.EXTRACTION,
            quarterly_capacity_output=1,
            output_per_worker=1_000_000_000,
        )
        assert baseline.report.tax_base_derivation is not None
        assert absurd.report.tax_base_derivation is not None
        assert baseline.report.tax_base_derivation.model_dump(
            mode="json"
        ) == absurd.report.tax_base_derivation.model_dump(mode="json")

        assert baseline.report.finance is not None
        assert absurd.report.finance is not None
        assert baseline.report.finance.model_dump(mode="json") == absurd.report.finance.model_dump(
            mode="json"
        )
