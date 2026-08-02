from __future__ import annotations

from app.simulation.invariants import check_invariants
from app.simulation.state import InstitutionState, PopulationGroupState
from tests.conftest import make_country, make_finance, make_game_state


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


# --- Player-country finance requirement (R6) ---------------------------------


def test_valid_player_finance_has_no_violation() -> None:
    # make_country defaults to with_finance=True for exactly this reason.
    country = make_country("a")
    assert country.finance is not None
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []


def test_missing_player_finance_is_a_violation() -> None:
    country = make_country("a", with_finance=False)
    assert country.finance is None
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "player_finance_required" in codes


def test_ai_country_without_finance_is_not_a_violation() -> None:
    player = make_country("player", with_finance=True)
    ai = make_country("ai_neighbor", with_finance=False)
    assert ai.finance is None

    state = make_game_state(
        countries={"player": player, "ai_neighbor": ai}, player_country_id="player"
    )
    assert check_invariants(state) == []


def test_incorrect_player_country_reference_is_a_violation_not_a_finance_check() -> None:
    # player_country_id pointing at a country that doesn't exist is caught by
    # the existing unknown_player_country check; it must not also (or instead)
    # produce a misleading player_finance_required violation, since there is
    # no player country object to even inspect for finance.
    country = make_country("a", with_finance=True)
    state = make_game_state(countries={"a": country}, player_country_id="a")
    state.world.player_country_id = "does-not-exist"

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert codes == {"unknown_player_country"}


def test_player_finance_uses_the_shared_finance_factory() -> None:
    # Exercises the finance_factory/make_finance path directly (not just via
    # make_country's default), matching the way real scenario/CLI code builds
    # a GovernmentFinanceState from its component parts.
    finance = make_finance(personal_income_rate_bps=3_000)
    country = make_country("a", finance=finance)
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []
    assert state.world.countries["a"].finance is not None
    assert state.world.countries["a"].finance.tax_policy.personal_income_rate_bps == 3_000
