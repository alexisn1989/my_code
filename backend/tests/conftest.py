from __future__ import annotations

from pathlib import Path

import pytest

from app.core.money import Money
from app.simulation.state import (
    RULESET_VERSION,
    CountryState,
    EconomyState,
    GameState,
    GovernmentFinanceState,
    InstitutionState,
    PopulationGroupState,
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


def make_economy(
    *,
    quarterly_capacity_output: int = 25_000_000,
    output_per_worker: int = 25_000_000,
    effective_labor_force_share_bps: int = 10_000,
    value_added_share_bps: int = 5_000,
    labor_income_share_bps: int = 5_000,
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
) -> CountryState:
    """Build a minimal, valid `CountryState` for unit tests that don't need YAML.

    Has finance and economy by default (`with_finance=True`, `with_economy=True`) because
    every existing caller uses this to build what ends up being the player country, and the
    player is required to have both `GovernmentFinanceState` and `EconomyState` (see
    `simulation.invariants`). Pass `with_finance=False`/`with_economy=False` to build an
    AI-style country with neither, or `finance=...`/`economy=...` to supply a specific one
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
    return CountryState(
        id=country_id,
        name=country_id.title(),
        population=population,
        population_groups=groups,
        institutions=[InstitutionState(id="executive", name="Executive Government")],
        treasury=TreasuryState(cash_on_hand=1_000_00, debt=100_00),
        finance=resolved_finance,
        economy=resolved_economy,
    )


def make_game_state(
    *,
    seed: int = 7,
    countries: dict[str, CountryState] | None = None,
    player_country_id: str = "testland",
    turn: int = 0,
    state_version: int = 0,
) -> GameState:
    """Build a minimal, valid `GameState` for unit tests that don't need YAML."""
    if countries is None:
        countries = {player_country_id: make_country(player_country_id)}
    return GameState(
        ruleset_version=RULESET_VERSION,
        content_version="0.5.0",
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
