from __future__ import annotations

from pathlib import Path

import pytest

from app.core.money import Money
from app.simulation.state import (
    RULESET_VERSION,
    CountryState,
    GameState,
    GovernmentFinanceState,
    InstitutionState,
    PopulationGroupState,
    SpendingPlanState,
    TaxBaseState,
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
    personal_income: Money = 500_000_00,
    corporate_profit: Money = 300_000_00,
    taxable_consumption: Money = 400_000_00,
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

    Deliberately sustainable: with the default rates/compliance, total revenue
    (19,350,000) comfortably exceeds default total spending (15,600,000) plus
    interest on the (tiny, per `make_country`'s default treasury) opening debt —
    so a long run of no-decision turns (e.g. the 100-turn soak) grows cash
    without ever borrowing, keeping that test's timing signal meaningful rather
    than dominated by an ever-growing debt figure.
    """
    return GovernmentFinanceState(
        tax_bases=TaxBaseState(
            personal_income=personal_income,
            corporate_profit=corporate_profit,
            taxable_consumption=taxable_consumption,
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


def make_country(
    country_id: str = "testland",
    *,
    population: int = 100,
    group_shares: tuple[float, ...] = (0.6, 0.4),
    with_finance: bool = True,
    finance: GovernmentFinanceState | None = None,
) -> CountryState:
    """Build a minimal, valid `CountryState` for unit tests that don't need YAML.

    Has finance by default (`with_finance=True`) because every existing caller
    uses this to build what ends up being the player country, and the player
    is required to have `GovernmentFinanceState` (see `simulation.invariants`).
    Pass `with_finance=False` to build an AI-style country with none, or
    `finance=...` to supply a specific one (implies `with_finance` is ignored).
    """
    groups = [
        PopulationGroupState(id=f"group_{i}", name=f"Group {i}", population_share=share)
        for i, share in enumerate(group_shares)
    ]
    resolved_finance = (
        finance if finance is not None else (make_finance() if with_finance else None)
    )
    return CountryState(
        id=country_id,
        name=country_id.title(),
        population=population,
        population_groups=groups,
        institutions=[InstitutionState(id="executive", name="Executive Government")],
        treasury=TreasuryState(cash_on_hand=1_000_00, debt=100_00),
        finance=resolved_finance,
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
        content_version="0.2.0",
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
