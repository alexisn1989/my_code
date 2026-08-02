from __future__ import annotations

from app.simulation.invariants import check_invariants
from app.simulation.state import InstitutionState, PopulationGroupState
from tests.conftest import make_country, make_game_state


def test_valid_state_has_no_violations() -> None:
    state = make_game_state()
    assert check_invariants(state) == []


def test_group_shares_summing_to_one_within_tolerance_is_valid() -> None:
    state = make_game_state(
        countries={"a": make_country("a", group_shares=(1.0 / 3, 1.0 / 3, 1.0 / 3))},
        player_country_id="a",
    )
    assert check_invariants(state) == []


def test_group_shares_not_summing_to_one_is_a_violation() -> None:
    state = make_game_state(
        countries={"a": make_country("a", group_shares=(0.9, 0.4))},
        player_country_id="a",
    )
    violations = check_invariants(state)
    assert len(violations) == 1
    assert violations[0].code == "group_shares_not_normalized"


def test_duplicate_population_group_id_is_a_violation() -> None:
    country = make_country("a", group_shares=(0.5, 0.5))
    country.population_groups[1] = country.population_groups[1].model_copy(
        update={"id": country.population_groups[0].id}
    )
    state = make_game_state(countries={"a": country}, player_country_id="a")

    codes = {v.code for v in check_invariants(state)}
    assert "duplicate_population_group_id" in codes


def test_duplicate_institution_id_is_a_violation() -> None:
    country = make_country("a")
    country.institutions.append(InstitutionState(id="executive", name="Executive Again"))
    state = make_game_state(countries={"a": country}, player_country_id="a")

    codes = {v.code for v in check_invariants(state)}
    assert "duplicate_institution_id" in codes


def test_unknown_player_country_id_is_a_violation() -> None:
    state = make_game_state(player_country_id="testland")
    state.world.player_country_id = "does-not-exist"

    violations = check_invariants(state)
    assert any(v.code == "unknown_player_country" for v in violations)


def test_country_with_no_population_groups_yet_is_not_a_share_violation() -> None:
    # A country with zero authored population groups shouldn't trip the share-sum
    # check (there is nothing to sum); it's simply not politically modeled yet.
    country = make_country("a", group_shares=())
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []


def test_multiple_violations_are_all_reported() -> None:
    country = make_country("a", group_shares=(0.9, 0.4))
    country.institutions.append(InstitutionState(id="executive", name="Executive Again"))
    state = make_game_state(countries={"a": country}, player_country_id="a")

    codes = {v.code for v in check_invariants(state)}
    assert codes == {"group_shares_not_normalized", "duplicate_institution_id"}


def test_population_group_share_below_zero_rejected_at_construction() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PopulationGroupState(id="x", name="X", population_share=-0.1)
