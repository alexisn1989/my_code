from __future__ import annotations

from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_digest, canonical_dumps
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
        "          theater_id: arken_capital\n"
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
# `strategic_map` WITHOUT its `rivers` key (via `app.core.canonical_json.canonical_digest`),
# recorded at M0 authoring time. Any accidental edit to a theater, route or shape -- including
# reordering, a moved centroid, or a changed vertex -- changes the digest and fails this test,
# rather than silently drifting.
#
# The `rivers` key is excluded rather than the digests re-pinned. The map-resources slice authored
# rivers into every scenario, which necessarily moves the whole-map digest; excluding exactly that
# one key and requiring the ORIGINAL M0 value to come back is what proves the river authoring
# touched no theater, route or vertex. The rivers themselves are pinned separately just below, so
# nothing goes unchecked -- and `test_the_map_digest_covers_rivers_when_they_are_not_excluded`
# keeps this exclusion from being a place things could hide.
_STRATEGIC_MAP_DIGEST_BLAKE2B: dict[str, str] = {
    "tiny_valid.yaml": "920b3a149f909267d9fa82eb564b77dc5fc1c51758152aa28ee6f09faf78281e",
    "decree_state.yaml": "a4480c83d1d6f298baf7c7e3711d748b3f21b7336bf0bce5a4438cfa51fd6e99",
    "deficit_demo.yaml": "d542a2cf42b1451b234c36871cc80a9cae5a4724954d57feb32a126a172ff067",
}

# The authored river courses, digested on their own (map-resources slice). Separate table rather
# than a re-pin of the one above, so the two claims stay independently readable: "M0's geometry is
# unchanged" and "these are the rivers".
_RIVER_DIGEST_BLAKE2B: dict[str, str] = {
    "tiny_valid.yaml": "1f89af0e1fa6aa25f8ef37241a870e897c9adefd65b9b6faad596bce7b5631e8",
    "decree_state.yaml": "88d6735e99b94ae637b1c548878f267283728b78ca7f5b132b44b4ee13ff0ddd",
    "deficit_demo.yaml": "53abe7280e0f64e876bf6043e698c357e1c1ad3d4963d0ff34ae5ae8f1490728",
}


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_strategic_map_geometry_digest_is_pinned(scenario_file: str) -> None:
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    payload = state.world.strategic_map.model_dump(mode="json")
    payload.pop("rivers")
    assert canonical_digest(payload) == _STRATEGIC_MAP_DIGEST_BLAKE2B[scenario_file]


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_the_map_digest_covers_rivers_when_they_are_not_excluded(scenario_file: str) -> None:
    """Anti-vacuity for the exclusion above: with `rivers` left in, the digest does NOT match the
    M0 pin. Without this, an exclusion that silently dropped more than one key would still look
    like a passing proof."""
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    whole = canonical_digest(state.world.strategic_map.model_dump(mode="json"))
    assert whole != _STRATEGIC_MAP_DIGEST_BLAKE2B[scenario_file]


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_authored_river_courses_are_pinned(scenario_file: str) -> None:
    """The other half: the rivers get their own pin, so "excluded from that digest" never means
    "unchecked". A moved vertex, a reordered course or a renamed river fails here."""
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    rivers = state.world.strategic_map.model_dump(mode="json")["rivers"]
    assert len(rivers) == 2
    assert canonical_digest(rivers) == _RIVER_DIGEST_BLAKE2B[scenario_file]


@pytest.mark.parametrize(
    "scenario_file", ["tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml"]
)
def test_authoring_a_military_roster_did_not_move_the_map_digest(scenario_file: str) -> None:
    """Military Movement commit 3 authored a `military:` block into each scenario's player
    country and left the map alone, so these pinned digests are deliberately UNCHANGED.

    Worth its own case rather than relying on the pin above: the digests cover `strategic_map`
    only, so an edit that reached the map while adding a roster would move them, and reading the
    pin as "still passing" is easy to mistake for "nothing was checked". The assertion here is
    that the formations live outside the digested subtree at all.
    """
    state = load_scenario_file(SCENARIO_DIR / scenario_file)
    military = state.world.countries[state.world.player_country_id].military
    assert military is not None and len(military.formations) == 1

    map_payload = state.world.strategic_map.model_dump(mode="json")
    assert "military" not in canonical_dumps(map_payload)
    map_payload.pop("rivers")
    assert canonical_digest(map_payload) == _STRATEGIC_MAP_DIGEST_BLAKE2B[scenario_file]
