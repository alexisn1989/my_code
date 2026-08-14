from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from app.core.money import Money
from app.simulation.constitution import (
    AmendmentDifficulty,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    Legislature,
    TerritorialOrganization,
)
from app.simulation.legislature import GovernmentRole, LegislativeChamber
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    RULESET_VERSION,
    BlocSeats,
    ChamberState,
    ConstitutionState,
    CountryState,
    EconomicBaselineState,
    EconomyState,
    GameState,
    GovernmentFinanceState,
    InstitutionState,
    LegislativeBlocState,
    LegislatureState,
    PartyState,
    PoliticalState,
    PopulationGroupState,
    ResourceCategory,
    ResourceDepositState,
    ResourceOutputCoefficient,
    SectorCategory,
    SectorState,
    SpendingPlanState,
    TaxBaseCoefficients,
    TaxPolicyState,
    TreasuryState,
    WorldState,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
TINY_VALID_SCENARIO_PATH = SCENARIO_DIR / "tiny_valid.yaml"


@pytest.fixture
def tiny_valid_scenario_path() -> Path:
    assert TINY_VALID_SCENARIO_PATH.exists(), (
        f"fixture scenario missing at {TINY_VALID_SCENARIO_PATH}"
    )
    return TINY_VALID_SCENARIO_PATH


def make_finance(
    *,
    personal_taxable_share_bps: int = 8_000,
    corporate_taxable_share_bps: int = 4_000,
    effective_consumption_base_share_bps: int = 3_000,
    personal_income_rate_bps: int = 2_000,
    corporate_rate_bps: int = 2_500,
    consumption_rate_bps: int = 1_000,
    compliance_rate_bps: int = 9_000,
    health: Money = 30_000_00,
    education: Money = 24_000_00,
    welfare: Money = 36_000_00,
    infrastructure: Money = 18_000_00,
    defense: Money = 27_000_00,
    security: Money = 12_000_00,
    administration: Money = 9_000_00,
    annual_debt_interest_rate_bps: int = 600,
) -> GovernmentFinanceState:
    """Build a valid `GovernmentFinanceState` with reasonable round-number defaults.

    As of Phase 2B2, tax bases are no longer authored here — they are derived every turn
    from the player's `EconomyState` (see `make_economy` below) and these
    `tax_base_coefficients`. Paired with `make_economy`'s defaults, the derived bases
    comfortably exceed default total spending (15,600,000) plus interest on the (tiny, per
    `make_country`'s default treasury) opening debt — so a long run of no-decision turns
    (e.g. the 100-turn soak) grows cash without ever borrowing, keeping that test's timing
    signal meaningful rather than dominated by an ever-growing debt figure.
    """
    return GovernmentFinanceState(
        tax_base_coefficients=TaxBaseCoefficients(
            personal_taxable_share_bps=personal_taxable_share_bps,
            corporate_taxable_share_bps=corporate_taxable_share_bps,
            effective_consumption_base_share_bps=effective_consumption_base_share_bps,
        ),
        tax_policy=TaxPolicyState(
            personal_income_rate_bps=personal_income_rate_bps,
            corporate_rate_bps=corporate_rate_bps,
            consumption_rate_bps=consumption_rate_bps,
            compliance_rate_bps=compliance_rate_bps,
        ),
        spending_plan=SpendingPlanState(
            health=health,
            education=education,
            welfare=welfare,
            infrastructure=infrastructure,
            defense=defense,
            security=security,
            administration=administration,
        ),
        annual_debt_interest_rate_bps=annual_debt_interest_rate_bps,
    )


def make_resource_deposits(
    *,
    remaining_stock: int = 0,
    extraction_capacity_per_turn: int = 0,
    output_per_worker: int = 1,
    regeneration_per_turn: int = 0,
    stock_ceiling: int | None = None,
) -> tuple[ResourceDepositState, ...]:
    """Build a valid `ResourceDepositState` tuple covering all 8 `ResourceCategory` values.

    Defaults to all-inactive (zero stock, zero capacity) rather than a uniform active shape like
    `make_economy`'s sectors — the overwhelming majority of existing tests predate Phase 2C1 and
    don't care about resources at all, so the default must be a trivially valid, side-effect-free
    block: every deposit's `required_workers == 0` regardless of how many workers the extraction
    sector happens to have allocated, so adding this field to every `EconomyState` cannot change
    any pre-Phase-2C1 test's labor/production/finance figures. Tests exercising specific resource
    behavior build `ResourceDepositState` tuples directly instead of overriding this factory's
    uniform shape, mirroring `make_economy`'s own documented convention for `SectorState`.

    `output_per_worker` defaults to `1` (the minimum legal `StrictResourceQuantityPerWorker`)
    since it is never exercised at zero capacity. For the one renewable category (`TIMBER`),
    `stock_ceiling` defaults to `remaining_stock` when not given explicitly — the minimum legal
    ceiling (`stock_ceiling >= remaining_stock`) — so the all-zero default satisfies
    `ResourceDepositState`'s renewability validators without the caller needing to think about it.
    """
    deposits: list[ResourceDepositState] = []
    for category in ResourceCategory:
        if category in RENEWABLE_RESOURCES:
            deposits.append(
                ResourceDepositState(
                    category=category,
                    remaining_stock=remaining_stock,
                    extraction_capacity_per_turn=extraction_capacity_per_turn,
                    output_per_worker=output_per_worker,
                    regeneration_per_turn=regeneration_per_turn,
                    stock_ceiling=(stock_ceiling if stock_ceiling is not None else remaining_stock),
                )
            )
        else:
            deposits.append(
                ResourceDepositState(
                    category=category,
                    remaining_stock=remaining_stock,
                    extraction_capacity_per_turn=extraction_capacity_per_turn,
                    output_per_worker=output_per_worker,
                )
            )
    return tuple(deposits)


def make_resource_output_coefficients(
    *,
    real_output_per_unit: int = 1,
) -> tuple[ResourceOutputCoefficient, ...]:
    """Build a valid `ResourceOutputCoefficient` tuple covering all 8 `ResourceCategory` values,
    uniform, defaulting to `1` (the minimum legal `StrictRealOutputPerResourceUnit`, `gt=0`).

    Unlike `make_resource_deposits`, there is no "inactive" zero shape available here — every
    coefficient must be strictly positive regardless of whether the paired deposit is active
    (Phase 2C2, D5) — so this default is chosen purely to be side-effect-free: paired with
    `make_resource_deposits()`'s all-inactive default (`extracted == 0` for every category), the
    actual `real_output_per_unit` value is multiplied by zero every turn, so it cannot change any
    pre-Phase-2C2 test's figures regardless of what it's set to. Tests exercising specific
    resource-output behavior build `ResourceOutputCoefficient` tuples directly instead.
    """
    return tuple(
        ResourceOutputCoefficient(category=category, real_output_per_unit=real_output_per_unit)
        for category in ResourceCategory
    )


def make_economy(
    *,
    quarterly_capacity_output: int = 25_000_000,
    output_per_worker: int = 25_000_000,
    effective_labor_force_share_bps: int = 10_000,
    value_added_share_bps: int = 5_000,
    labor_income_share_bps: int = 5_000,
    resource_deposits: tuple[ResourceDepositState, ...] | None = None,
    resource_output_coefficients: tuple[ResourceOutputCoefficient, ...] | None = None,
) -> EconomyState:
    """Build a valid `EconomyState` covering all 11 `SectorCategory` values with uniform,
    round-number defaults (every sector exactly-balanced: `required_workers * output_per_worker
    == quarterly_capacity_output`, since `quarterly_capacity_output == output_per_worker` by
    default gives `required_workers == 1` per sector) — tests that need a specific
    classification or edge case build `SectorState`/`EconomyState` directly instead of
    overriding this factory's uniform shape.

    As of Phase 2B3, employment is not authored here — `simulation.labor_allocation` derives it
    every turn from `effective_labor_force_share_bps` plus each sector's capacity/productivity.
    The default `effective_labor_force_share_bps=10_000` (100%), paired with `make_country`'s
    default `population=100`, gives an effective labor force of 100 — comfortably above the 11
    workers (`len(SectorCategory)`) required at full capacity, so labor stays abundant and every
    sector gets exactly the one worker it asks for, matching the pre-Phase-2B3 authored shape.

    As of Phase 2C1, `resource_deposits` defaults to `make_resource_deposits()`'s all-inactive
    shape (see that function's docstring) — pass an explicit tuple to exercise real extraction.

    As of Phase 2C2, `resource_output_coefficients` defaults to
    `make_resource_output_coefficients()`'s uniform shape — paired with the all-inactive deposits
    default above, every category's `extracted == 0`, so the coefficient value multiplies to zero
    regardless, keeping this default side-effect-free for the overwhelming majority of tests that
    predate Phase 2C2 and don't care about resource output.

    Paired with `make_finance`'s default `tax_base_coefficients`, this produces derived tax
    bases (personal=55,000,000, corporate=27,500,000, consumption=41,250,000) that keep
    `make_finance`'s "comfortably sustainable" default budget claim true post-Phase-2B2 — see
    that function's docstring.
    """
    return EconomyState(
        effective_labor_force_share_bps=effective_labor_force_share_bps,
        sectors=tuple(
            SectorState(
                category=category,
                quarterly_capacity_output=quarterly_capacity_output,
                output_per_worker=output_per_worker,
                value_added_share_bps=value_added_share_bps,
                labor_income_share_bps=labor_income_share_bps,
            )
            for category in SectorCategory
        ),
        resource_deposits=(
            resource_deposits if resource_deposits is not None else make_resource_deposits()
        ),
        resource_output_coefficients=(
            resource_output_coefficients
            if resource_output_coefficients is not None
            else make_resource_output_coefficients()
        ),
    )


_UNSET: Final[object] = object()
"""Distinguishes 'caller didn't pass `legislature_state`' from 'caller explicitly passed `None`'
in `make_politics` — `None` is itself a legal, meaningful value (no legislature at all), so a
default of `None` could not tell the two cases apart."""


def make_legislature(*, shape: Legislature = Legislature.UNICAMERAL) -> LegislatureState:
    """Build a minimal, valid `LegislatureState` (Phase 3B1): one coalition bloc holding every
    seat in every chamber `shape` implies, plus a single, small opposition bloc so the legislature
    is not a rubber stamp with nobody to bargain against.

    Every seat in every chamber is accounted for (`LegislatureState`'s own validator requires
    it) — 90 seats to the coalition, 10 to the opposition, in each chamber `shape` calls for.
    Round numbers, chosen for readability in tests that don't care about the legislature's
    internals, not for any particular vote outcome; tests that do care build their own.
    """
    if shape not in (Legislature.UNICAMERAL, Legislature.BICAMERAL):
        raise ValueError(f"make_legislature has no chamber shape for {shape!r}")
    chambers = (
        (LegislativeChamber.LOWER,)
        if shape is Legislature.UNICAMERAL
        else tuple(LegislativeChamber)
    )
    return LegislatureState(
        chambers=tuple(ChamberState(chamber=c, total_seats=100) for c in chambers),
        parties=(
            PartyState(
                id="governing_party",
                name="Governing Party",
                government_role=GovernmentRole.COALITION,
                blocs=(
                    LegislativeBlocState(
                        id="core",
                        name="Governing Party Core",
                        seats=tuple(BlocSeats(chamber=c, seats=90) for c in chambers),
                        discipline_bps=5_000,
                        government_relationship_bps=6_000,
                        baseline_government_relationship_bps=6_000,
                        tax_preference_bps=2_000,
                        spending_preference_bps=2_000,
                    ),
                ),
            ),
            PartyState(
                id="opposition_party",
                name="Opposition Party",
                government_role=GovernmentRole.OPPOSITION,
                blocs=(
                    LegislativeBlocState(
                        id="main",
                        name="Opposition Party Main",
                        seats=tuple(BlocSeats(chamber=c, seats=10) for c in chambers),
                        discipline_bps=5_000,
                        government_relationship_bps=-6_000,
                        baseline_government_relationship_bps=-6_000,
                        tax_preference_bps=-2_000,
                        spending_preference_bps=-2_000,
                    ),
                ),
            ),
        ),
    )


def make_politics(
    *,
    executive_system: ExecutiveSystem = ExecutiveSystem.PRESIDENTIAL,
    executive_selection: ExecutiveSelection = ExecutiveSelection.DIRECT_ELECTION,
    legislature: Legislature = Legislature.UNICAMERAL,
    territorial_organization: TerritorialOrganization = TerritorialOrganization.UNITARY,
    judicial_review: JudicialReview = JudicialReview.WEAK,
    amendment_difficulty: AmendmentDifficulty = AmendmentDifficulty.SUPERMAJORITY,
    decree_authority: DecreeAuthority = DecreeAuthority.EMERGENCY_ONLY,
    executive_term_limit_terms: int | None = None,
    national_election_interval_turns: int | None = None,
    constitutional_order_support_bps: int = 7_000,
    legitimacy_bps: int = 7_000,
    political_capital: int = 500,
    political_capital_capacity: int = 1_000,
    economic_baseline: EconomicBaselineState | None = None,
    legislature_state: LegislatureState | None | object = _UNSET,
) -> PoliticalState:
    """Build a valid `PoliticalState` (Phase 3A, extended Phase 3B1) with reasonable round-number
    defaults: a coherent presidential republic, moderate authored support, and legitimacy already
    at that same 7,000 level so a fresh test country starts at drift-equilibrium.
    `economic_baseline` defaults to `None` (legal only at `state.turn == 0`) — pass one explicitly
    for a country built at a later turn; see `make_game_state`, which does this automatically.

    `legislature_state` defaults to `make_legislature(shape=legislature)` whenever `legislature`
    is not `Legislature.NONE`, and to `None` when it is — matching `PoliticalState`'s own
    both-directions rule automatically, so most callers never think about it. Pass an explicit
    `LegislatureState` to control the legislature's content, or `None` to (with a legislature
    shape other than `NONE`) deliberately construct an invalid state for a validator test.
    """
    resolved_legislature = (
        (make_legislature(shape=legislature) if legislature is not Legislature.NONE else None)
        if legislature_state is _UNSET
        else legislature_state
    )
    return PoliticalState(
        constitution=ConstitutionState(
            executive_system=executive_system,
            executive_selection=executive_selection,
            legislature=legislature,
            territorial_organization=territorial_organization,
            judicial_review=judicial_review,
            amendment_difficulty=amendment_difficulty,
            decree_authority=decree_authority,
            executive_term_limit_terms=executive_term_limit_terms,
            national_election_interval_turns=national_election_interval_turns,
        ),
        constitutional_order_support_bps=constitutional_order_support_bps,
        legitimacy_bps=legitimacy_bps,
        political_capital=political_capital,
        political_capital_capacity=political_capital_capacity,
        economic_baseline=economic_baseline,
        legislature=resolved_legislature,  # type: ignore[arg-type]
    )


def make_country(
    country_id: str = "testland",
    *,
    population: int = 100,
    group_shares: tuple[float, ...] = (0.6, 0.4),
    with_finance: bool = True,
    finance: GovernmentFinanceState | None = None,
    with_economy: bool = True,
    economy: EconomyState | None = None,
    with_politics: bool = True,
    politics: PoliticalState | None = None,
) -> CountryState:
    """Build a minimal, valid `CountryState` for unit tests that don't need YAML.

    Has finance, economy, and politics by default (`with_finance=True`, `with_economy=True`,
    `with_politics=True`) because every existing caller uses this to build what ends up being
    the player country, and the player is required to have `GovernmentFinanceState`,
    `EconomyState`, and (Phase 3A) `PoliticalState` (see `simulation.invariants`). Pass
    `with_finance=False`/`with_economy=False`/`with_politics=False` to build an AI-style country
    with none of them, or `finance=...`/`economy=...`/`politics=...` to supply a specific one
    (implies the corresponding `with_*` flag is ignored).
    """
    groups = [
        PopulationGroupState(id=f"group_{i}", name=f"Group {i}", population_share=share)
        for i, share in enumerate(group_shares)
    ]
    resolved_finance = (
        finance if finance is not None else (make_finance() if with_finance else None)
    )
    resolved_economy = (
        economy if economy is not None else (make_economy() if with_economy else None)
    )
    resolved_politics = (
        politics if politics is not None else (make_politics() if with_politics else None)
    )
    return CountryState(
        id=country_id,
        name=country_id.title(),
        population=population,
        population_groups=groups,
        institutions=[
            InstitutionState(id="executive", name="Executive Government"),
            InstitutionState(id="military", name="Military"),
        ],
        treasury=TreasuryState(cash_on_hand=1_000_00, debt=100_00),
        finance=resolved_finance,
        economy=resolved_economy,
        politics=resolved_politics,
    )


def make_game_state(
    *,
    seed: int = 7,
    countries: dict[str, CountryState] | None = None,
    player_country_id: str = "testland",
    turn: int = 0,
    state_version: int = 0,
) -> GameState:
    """Build a minimal, valid `GameState` for unit tests that don't need YAML.

    When `countries` is omitted and `turn > 0`, the auto-built player's `politics` carries a
    baseline stamped `source_turn == turn` (R6: a baseline is legal only at `turn == 0` when
    absent) — `total_gross_output=0` is a deliberately inert placeholder (§6.3's explicit
    zero-baseline branch means it contributes no performance effect if this state is ever
    resolved). A caller who passes `countries=...` explicitly is responsible for its own
    politics, exactly as they already are for finance/economy.
    """
    if countries is None:
        politics = (
            make_politics(
                economic_baseline=EconomicBaselineState(
                    source_turn=turn, total_gross_output=0, unemployment_rate_bps=1_000
                )
            )
            if turn > 0
            else None
        )
        countries = {player_country_id: make_country(player_country_id, politics=politics)}
    return GameState(
        ruleset_version=RULESET_VERSION,
        content_version="0.11.0",
        seed=seed,
        turn=turn,
        state_version=state_version,
        world=WorldState(countries=countries, player_country_id=player_country_id),
    )


@pytest.fixture
def game_state_factory():
    return make_game_state


@pytest.fixture
def country_factory():
    return make_country


@pytest.fixture
def finance_factory():
    return make_finance


@pytest.fixture
def economy_factory():
    return make_economy
