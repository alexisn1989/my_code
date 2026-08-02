from __future__ import annotations

from pathlib import Path

import pytest

from app.simulation.state import (
    CountryState,
    GameState,
    InstitutionState,
    PopulationGroupState,
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


def make_country(
    country_id: str = "testland",
    *,
    population: int = 100,
    group_shares: tuple[float, ...] = (0.6, 0.4),
) -> CountryState:
    """Build a minimal, valid `CountryState` for unit tests that don't need YAML."""
    groups = [
        PopulationGroupState(id=f"group_{i}", name=f"Group {i}", population_share=share)
        for i, share in enumerate(group_shares)
    ]
    return CountryState(
        id=country_id,
        name=country_id.title(),
        population=population,
        population_groups=groups,
        institutions=[InstitutionState(id="executive", name="Executive Government")],
        treasury=TreasuryState(cash_on_hand=1_000_00, debt=100_00),
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
        ruleset_version="0.1.0",
        content_version="0.1.0",
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
