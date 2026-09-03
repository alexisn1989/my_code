from __future__ import annotations

from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_digest
from app.core.errors import ScenarioValidationError
from app.simulation.scenario import load_scenario_text
from app.simulation.state import ResourceCategory
from tests.conftest import SCENARIO_DIR


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
    assert {i.id for i in arken.institutions} == {"executive", "military"}

    assert arken.economy is not None
    assert {d.category for d in arken.economy.resource_deposits} == set(ResourceCategory)
    assert tuple(d.category for d in arken.economy.resource_deposits) == tuple(ResourceCategory)


def test_deficit_demo_scenario_loads_successfully_with_resource_deposits() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    strapped = state.world.countries["strapped"]
    assert strapped.economy is not None
    assert {d.category for d in strapped.economy.resource_deposits} == set(ResourceCategory)
    assert tuple(d.category for d in strapped.economy.resource_deposits) == tuple(ResourceCategory)


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


def test_scenario_duplicate_resource_category_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    # Relabel critical_minerals (nonrenewable) as iron_ore (also nonrenewable) so the
    # per-row renewability validator (which would fire first if either side were TIMBER) never
    # trips — isolating the report-level duplicate-category check specifically.
    broken = text.replace("category: critical_minerals", "category: iron_ore")
    assert broken != text

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any("duplicate resource category" in problem for problem in exc_info.value.problems)


def test_scenario_missing_resource_category_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    critical_minerals_block = (
        "        - category: critical_minerals\n"
        "          remaining_stock: 2000000\n"
        "          extraction_capacity_per_turn: 20000\n"
        "          output_per_worker: 20\n"
    )
    assert critical_minerals_block in text
    broken = text.replace(critical_minerals_block, "")

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any("missing resource categories" in problem for problem in exc_info.value.problems)


def test_scenario_reversed_resource_order_rejected(tiny_valid_scenario_path: Path) -> None:
    """R3: unlike sector order, noncanonical resource order is rejected outright, not
    normalized — even at the scenario-loading layer. Swaps two NONRENEWABLE categories
    (iron_ore <-> coal) specifically — swapping TIMBER's label would also trip the per-row
    renewability validator (its regeneration_per_turn/stock_ceiling fields wouldn't travel with
    the label), which would test a different thing than pure ordering.
    """
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text.replace("category: iron_ore", "category: __TMP__")
    broken = broken.replace("category: coal", "category: iron_ore")
    broken = broken.replace("category: __TMP__", "category: coal")
    assert broken != text

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario_text(broken, source="broken.yaml")

    assert any(
        "not in canonical ResourceCategory order" in problem for problem in exc_info.value.problems
    )


def test_scenario_unknown_resource_category_rejected(tiny_valid_scenario_path: Path) -> None:
    text = tiny_valid_scenario_path.read_text(encoding="utf-8")
    broken = text.replace("category: critical_minerals", "category: not_a_real_resource")
    assert broken != text

    with pytest.raises(ScenarioValidationError):
        load_scenario_text(broken, source="broken.yaml")


# --- Strategic Military Map Gate M0: exact authored geometry, pinned ----------
#
# Each digest is the canonical-JSON BLAKE2b digest of the loaded scenario's
# `strategic_map` (via `app.core.canonical_json.canonical_digest`), recorded at
# authoring time. Any accidental edit to a theater, route or shape -- including
# reordering, a moved centroid, or a changed vertex -- changes the digest and
# fails this test, rather than silently drifting.
_STRATEGIC_MAP_DIGEST_BLAKE2B: dict[str, str] = {
    "tiny_valid.yaml": "920b3a149f909267d9fa82eb564b77dc5fc1c51758152aa28ee6f09faf78281e",
    "decree_state.yaml": "a4480c83d1d6f298baf7c7e3711d748b3f21b7336bf0bce5a4438cfa51fd6e99",
    "deficit_demo.yaml": "d542a2cf42b1451b234c36871cc80a9cae5a4724954d57feb32a126a172ff067",
}


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_strategic_map_geometry_digest_is_pinned(scenario_file: str) -> None:
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    digest = canonical_digest(state.world.strategic_map.model_dump(mode="json"))
    assert digest == _STRATEGIC_MAP_DIGEST_BLAKE2B[scenario_file]
