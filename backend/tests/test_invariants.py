from __future__ import annotations

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import HistoryValidationError, TurnResolutionError
from app.simulation.decisions import DecisionSet
from app.simulation.history import new_game
from app.simulation.invariants import check_invariants
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import (
    EconomyState,
    InstitutionState,
    PopulationGroupState,
    SectorState,
    TaxBaseCoefficients,
)
from tests.conftest import make_country, make_economy, make_finance, make_game_state


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


# --- Player-country economy requirement (Phase 2B1) --------------------------


def test_valid_player_economy_has_no_violation() -> None:
    country = make_country("a")
    assert country.economy is not None
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []


def test_missing_player_economy_is_a_violation() -> None:
    country = make_country("a", with_economy=False)
    assert country.economy is None
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "player_economy_required" in codes


def test_ai_country_without_economy_is_not_a_violation() -> None:
    player = make_country("player", with_economy=True)
    ai = make_country("ai_neighbor", with_economy=False)
    assert ai.economy is None

    state = make_game_state(
        countries={"player": player, "ai_neighbor": ai}, player_country_id="player"
    )
    assert check_invariants(state) == []


def test_player_economy_uses_the_shared_economy_factory() -> None:
    economy = make_economy(employed_workers=10)
    country = make_country("a", population=1_000, economy=economy)
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []
    assert state.world.countries["a"].economy is not None


def test_sector_employment_exceeding_population_is_a_violation() -> None:
    economy = make_economy(employed_workers=1_000)  # 11 sectors * 1000 = 11,000
    country = make_country("a", population=100, economy=economy)  # << total employment
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "sector_employment_exceeds_population" in codes


def test_sector_employment_exactly_equal_to_population_is_not_a_violation() -> None:
    economy = make_economy(employed_workers=10)  # 11 sectors * 10 = 110
    country = make_country("a", population=110, economy=economy)
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []


# --- R1: EconomyState's own construction-time invariant must be re-checked ---
# --- every turn, since SectorState is deliberately mutable -------------------


def test_nested_sector_mutation_into_a_duplicate_category_is_caught_by_invariants() -> None:
    """R1's central regression test: `EconomyState`'s `@model_validator` only runs
    at construction. A later `sector.category = ...` assignment on an already-built
    `EconomyState` can desynchronize it from "all 11 categories, exactly once"
    without ever re-running that validator — `check_invariants` is the independent,
    every-turn backstop that still catches it.
    """
    country = make_country("a")
    assert country.economy is not None
    # Mutate a live, already-validated SectorState's category to collide with
    # another sector already present — plain attribute assignment, an allowed
    # path since SectorState is deliberately kept mutable (R1).
    country.economy.sectors[1].category = country.economy.sectors[0].category
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "duplicate_sector_category" in codes
    assert "missing_sector_category" in codes  # whatever category got overwritten is now absent


def test_resolve_turn_rejects_a_nested_sector_mutation_without_mutating_input_or_history() -> None:
    """R1's full regression test: `resolve_turn` catches the desynchronized
    economy via `check_invariants` (not a crash), never mutates the caller's
    state, and `advance_game` appends no history entry for the failed turn.
    """
    from app.simulation.history import advance_game

    country = make_country("a")
    assert country.economy is not None
    country.economy.sectors[1].category = country.economy.sectors[0].category
    state = make_game_state(countries={"a": country}, player_country_id="a")

    before = canonical_dumps(state.model_dump(mode="json"))
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, decisions)
    assert canonical_dumps(state.model_dump(mode="json")) == before

    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    before_entry_count = save.entry_count
    # Once stored and reloaded from JSON, `EconomyState`'s own construction-time
    # validator catches the duplicate on re-parse (a stronger, independent check
    # than check_invariants alone) — surfacing as a history-integrity failure
    # rather than a turn-resolution failure, but either way nothing is appended.
    with pytest.raises((TurnResolutionError, HistoryValidationError)):
        advance_game(save, decisions)
    assert save.entry_count == before_entry_count


def test_noncanonical_sector_order_from_a_bypassed_construction_is_caught_by_invariants() -> None:
    """A plain reassignment of `economy.sectors` re-triggers `EconomyState`'s own
    `@model_validator` (via `validate_assignment=True`, which pydantic reruns
    even for an already-constructed nested instance) and would silently
    re-normalize the order back to canonical — it can't be used to produce a
    noncanonical-order economy. `model_construct()` bypasses validation
    entirely, and `model_copy(update=...)` (unlike a live attribute
    assignment) never re-validates either, so together they're the realistic
    way this state could arise — e.g. modeling a payload that was
    reconstructed without ever going through normal validation.
    `check_invariants` is the independent backstop that still catches it.
    """
    country = make_country("a")
    assert country.economy is not None
    sectors = list(country.economy.sectors)
    sectors[0], sectors[1] = sectors[1], sectors[0]
    bypassed = EconomyState.model_construct(sectors=tuple(sectors))
    country = country.model_copy(update={"economy": bypassed})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "noncanonical_sector_order" in codes
    assert "duplicate_sector_category" not in codes
    assert "missing_sector_category" not in codes


# --- Phase 2B2: tax-base coefficient range backstop --------------------------


def test_tax_base_coefficient_out_of_range_is_caught_by_invariants() -> None:
    """`StrictBps` already rejects an out-of-range coefficient at every legitimate
    construction/assignment path — this is defense-in-depth for a fully bypassed
    construction, mirroring the `noncanonical_sector_order` pattern above.
    """
    country = make_country("a")
    assert country.finance is not None
    bypassed_coefficients = TaxBaseCoefficients.model_construct(
        personal_taxable_share_bps=99_999,
        corporate_taxable_share_bps=4_000,
        effective_consumption_base_share_bps=3_000,
    )
    bypassed_finance = country.finance.model_copy(
        update={"tax_base_coefficients": bypassed_coefficients}
    )
    country = country.model_copy(update={"finance": bypassed_finance})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "tax_base_coefficient_out_of_range" in codes


def test_sector_tax_base_share_out_of_range_is_caught_by_invariants() -> None:
    country = make_country("a")
    assert country.economy is not None
    sectors = list(country.economy.sectors)
    original = sectors[0]
    bypassed_sector = SectorState.model_construct(
        category=original.category,
        quarterly_capacity_output=original.quarterly_capacity_output,
        output_per_worker=original.output_per_worker,
        employed_workers=original.employed_workers,
        value_added_share_bps=-1,
        labor_income_share_bps=original.labor_income_share_bps,
    )
    sectors[0] = bypassed_sector
    bypassed_economy = country.economy.model_copy(update={"sectors": tuple(sectors)})
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "sector_tax_base_share_out_of_range" in codes
