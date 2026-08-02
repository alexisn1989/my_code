from __future__ import annotations

from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import ScenarioValidationError
from app.simulation.scenario import load_scenario_text


def test_tiny_valid_scenario_loads_successfully(tiny_valid_scenario_path: Path) -> None:
    state = load_scenario_file(tiny_valid_scenario_path)

    assert state.turn == 0
    assert state.state_version == 0
    assert state.seed == 42
    assert state.world.player_country_id == "arken"
    assert set(state.world.countries) == {"arken", "neighbor"}

    arken = state.world.countries["arken"]
    assert arken.population == 1_000_000
    assert len(arken.population_groups) == 3
    assert {g.id for g in arken.population_groups} == {
        "urban_workers",
        "rural_farmers",
        "business_owners",
    }
    assert {i.id for i in arken.institutions} == {"executive", "legislature", "military"}


def test_scenario_missing_required_fields_rejected() -> None:
    with pytest.raises(ScenarioValidationError):
        load_scenario_text("schema_version: 1\nscenario_id: broken\n", source="broken.yaml")


def test_scenario_unknown_top_level_field_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text + "\nunknown_top_level_field: true\n"
    with pytest.raises(ScenarioValidationError):
        load_scenario_text(broken, source="broken.yaml")


def test_scenario_invalid_yaml_rejected() -> None:
    with pytest.raises(ScenarioValidationError):
        load_scenario_text("this: is: not: valid: yaml: [", source="broken.yaml")


def test_scenario_non_mapping_top_level_rejected() -> None:
    with pytest.raises(ScenarioValidationError):
        load_scenario_text("- just\n- a\n- list\n", source="broken.yaml")


def test_scenario_unnormalized_group_shares_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text.replace("population_share: 0.40", "population_share: 0.90")
    assert broken != text, "fixture text did not contain the expected value to mutate"

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any("shares sum to" in problem for problem in exc_info.value.problems)


def test_scenario_unknown_player_country_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text.replace("player_country_id: arken", "player_country_id: nowhere")

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any("nowhere" in problem for problem in exc_info.value.problems)


def test_scenario_duplicate_country_id_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text.replace("id: neighbor", "id: arken")

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any("duplicate country id" in problem for problem in exc_info.value.problems)
