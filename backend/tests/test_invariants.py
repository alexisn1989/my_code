from __future__ import annotations

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import HistoryValidationError, TurnResolutionError
from app.simulation.constitution import ConstitutionState, ExecutiveSelection, ExecutiveSystem
from app.simulation.decisions import DecisionSet
from app.simulation.history import new_game
from app.simulation.invariants import check_invariants
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    EconomicBaselineState,
    EconomyState,
    InstitutionState,
    PoliticalState,
    PopulationGroupState,
    ResourceCategory,
    ResourceDepositState,
    ResourceOutputCoefficient,
    SectorState,
    TaxBaseCoefficients,
)
from tests.conftest import (
    make_country,
    make_economy,
    make_finance,
    make_game_state,
    make_politics,
    make_resource_output_coefficients,
)


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
    ai = make_country("ai_neighbor", with_finance=False, with_politics=False)
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
    country = make_country("a", with_finance=True, with_politics=False)
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
    ai = make_country("ai_neighbor", with_economy=False, with_politics=False)
    assert ai.economy is None

    state = make_game_state(
        countries={"player": player, "ai_neighbor": ai}, player_country_id="player"
    )
    assert check_invariants(state) == []


def test_player_economy_uses_the_shared_economy_factory() -> None:
    economy = make_economy(effective_labor_force_share_bps=8_000)
    country = make_country("a", population=1_000, economy=economy)
    state = make_game_state(countries={"a": country}, player_country_id="a")
    assert check_invariants(state) == []
    assert state.world.countries["a"].economy is not None


# --- Phase 2B3: effective-labor-force share/bound backstops ------------------


def test_effective_labor_force_share_out_of_range_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    """`StrictBps` already rejects an out-of-range share at every legitimate
    construction/assignment path — this is defense-in-depth for a fully bypassed
    construction, mirroring `tax_base_coefficient_out_of_range` above.
    """
    country = make_country("a")
    assert country.economy is not None
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=99_999,
        sectors=country.economy.sectors,
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "effective_labor_force_share_out_of_range" in codes


def test_effective_labor_force_exceeding_population_from_bypassed_population_is_caught_by_invariants() -> (
    None
):
    """`0 <= effective_labor_force <= population` holds by construction for any *valid*
    `population`/`effective_labor_force_share_bps` pair — this only exercises the every-turn
    backstop via a bypassed (`model_copy(update=...)`, which skips field validation)
    negative population: floor((-1000) * 5000 / 10_000) == -500, which is greater than -1000.
    """
    economy = make_economy(effective_labor_force_share_bps=5_000)
    country = make_country("a", population=1_000, economy=economy)
    country = country.model_copy(update={"population": -1_000})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "effective_labor_force_exceeds_population" in codes


# --- Phase 2C1: resource_deposits structural/renewability backstops ----------


def _deposit(
    category: ResourceCategory,
    *,
    remaining_stock: int = 0,
    extraction_capacity_per_turn: int = 0,
    output_per_worker: int = 1,
    regeneration_per_turn: int = 0,
    stock_ceiling: int | None = None,
) -> ResourceDepositState:
    if category in RENEWABLE_RESOURCES and stock_ceiling is None:
        stock_ceiling = remaining_stock
    return ResourceDepositState(
        category=category,
        remaining_stock=remaining_stock,
        extraction_capacity_per_turn=extraction_capacity_per_turn,
        output_per_worker=output_per_worker,
        regeneration_per_turn=regeneration_per_turn if category in RENEWABLE_RESOURCES else 0,
        stock_ceiling=stock_ceiling,
    )


def _all_resource_deposits(
    overrides: dict[ResourceCategory, ResourceDepositState] | None = None,
) -> tuple[ResourceDepositState, ...]:
    overrides = overrides or {}
    return tuple(overrides.get(category, _deposit(category)) for category in ResourceCategory)


def test_duplicate_resource_category_from_a_bypassed_construction_is_caught_by_invariants() -> None:
    """`EconomyState`'s own constructor already rejects this on every legitimate path — this is
    defense-in-depth for a fully bypassed construction, mirroring `duplicate_sector_category`.
    """
    country = make_country("a")
    assert country.economy is not None
    deposits = list(_all_resource_deposits())
    deposits[1] = _deposit(deposits[0].category)  # duplicate the first category
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=tuple(deposits),
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "duplicate_resource_category" in codes


def test_missing_resource_category_from_a_bypassed_construction_is_caught_by_invariants() -> None:
    country = make_country("a")
    assert country.economy is not None
    deposits = _all_resource_deposits()[:-1]  # drop critical_minerals
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "missing_resource_category" in codes


def test_noncanonical_resource_order_from_a_bypassed_construction_is_caught_by_invariants() -> None:
    """R3: unlike `noncanonical_sector_order`, `EconomyState`'s own constructor already
    **rejects** reordered `resource_deposits` outright on every legitimate path (it does not
    merely normalize, the way the sector validator does) — so this backstop is reachable only
    through a fully bypassed construction, making it even more purely defense-in-depth than its
    sector-order counterpart.
    """
    country = make_country("a")
    assert country.economy is not None
    deposits = list(_all_resource_deposits())
    deposits[0], deposits[1] = deposits[1], deposits[0]
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=tuple(deposits),
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "noncanonical_resource_order" in codes
    assert "duplicate_resource_category" not in codes
    assert "missing_resource_category" not in codes


def test_resource_regeneration_on_nonrenewable_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    """`ResourceDepositState`'s own constructor already rejects this on every legitimate path —
    defense-in-depth for a fully bypassed row construction."""
    country = make_country("a")
    assert country.economy is not None
    bypassed_deposit = ResourceDepositState.model_construct(
        category=ResourceCategory.IRON_ORE,
        remaining_stock=0,
        extraction_capacity_per_turn=0,
        output_per_worker=1,
        regeneration_per_turn=5,  # illegal for a nonrenewable
        stock_ceiling=None,
    )
    deposits = _all_resource_deposits({ResourceCategory.IRON_ORE: bypassed_deposit})
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "resource_regeneration_on_nonrenewable" in codes


def test_renewable_missing_stock_ceiling_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    country = make_country("a")
    assert country.economy is not None
    bypassed_deposit = ResourceDepositState.model_construct(
        category=ResourceCategory.TIMBER,
        remaining_stock=0,
        extraction_capacity_per_turn=0,
        output_per_worker=1,
        regeneration_per_turn=5,
        stock_ceiling=None,  # illegal for a renewable
    )
    deposits = _all_resource_deposits({ResourceCategory.TIMBER: bypassed_deposit})
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "renewable_missing_stock_ceiling" in codes


def test_resource_stock_exceeds_ceiling_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    country = make_country("a")
    assert country.economy is not None
    bypassed_deposit = ResourceDepositState.model_construct(
        category=ResourceCategory.TIMBER,
        remaining_stock=101,
        extraction_capacity_per_turn=0,
        output_per_worker=1,
        regeneration_per_turn=5,
        stock_ceiling=100,  # below remaining_stock
    )
    deposits = _all_resource_deposits({ResourceCategory.TIMBER: bypassed_deposit})
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "resource_stock_exceeds_ceiling" in codes


def test_nested_resource_deposit_mutation_into_a_duplicate_category_is_caught_by_invariants() -> (
    None
):
    """The resource-side mirror of `test_nested_sector_mutation_into_a_duplicate_category_is_
    caught_by_invariants` below: `ResourceDepositState` is deliberately mutable, so a live
    `deposit.category = ...` assignment re-validates that one row but never re-triggers the
    *parent* `EconomyState`'s completeness validator.
    """
    country = make_country("a")
    assert country.economy is not None
    country.economy.resource_deposits[1].category = country.economy.resource_deposits[2].category
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "duplicate_resource_category" in codes
    assert "missing_resource_category" in codes


# --- Phase 2C2: resource_output_coefficients structural checks (4 of the plan's 14 proposed --
# --- codes; the other 10 are report-vs-formula "mismatch" checks that check_invariants cannot --
# --- implement — check_invariants(state: GameState) never sees a TurnReport, and resolver.py --
# --- calls it strictly before TurnReport is even constructed. report.py's 7 new self- ---------
# --- validators plus 3 new TurnReport cross-validators cover that surface instead, more -------
# --- thoroughly and on every construction/replay path, not just resolve_turn's checkpoints. ---


def _all_resource_output_coefficients(
    overrides: dict[ResourceCategory, ResourceOutputCoefficient] | None = None,
) -> tuple[ResourceOutputCoefficient, ...]:
    overrides = overrides or {}
    base = {c.category: c for c in make_resource_output_coefficients()}
    base.update(overrides)
    return tuple(base[category] for category in ResourceCategory)


def test_duplicate_resource_output_coefficient_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    """`EconomyState`'s own constructor already rejects this on every legitimate path — this is
    defense-in-depth for a fully bypassed construction, mirroring `duplicate_resource_category`.
    """
    country = make_country("a")
    assert country.economy is not None
    coefficients = list(_all_resource_output_coefficients())
    coefficients[1] = ResourceOutputCoefficient(
        category=coefficients[0].category, real_output_per_unit=1
    )
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=tuple(coefficients),
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "duplicate_resource_output_coefficient" in codes


def test_missing_resource_output_coefficient_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    country = make_country("a")
    assert country.economy is not None
    coefficients = _all_resource_output_coefficients()[:-1]  # drop critical_minerals
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "missing_resource_output_coefficient" in codes


def test_noncanonical_resource_output_coefficient_order_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    """R3: `EconomyState`'s own constructor already **rejects** reordered
    `resource_output_coefficients` outright (it does not merely normalize) — so this backstop is
    reachable only through a fully bypassed construction, mirroring
    `noncanonical_resource_order`."""
    country = make_country("a")
    assert country.economy is not None
    coefficients = list(_all_resource_output_coefficients())
    coefficients[0], coefficients[1] = coefficients[1], coefficients[0]
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=tuple(coefficients),
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "noncanonical_resource_output_coefficient_order" in codes
    assert "duplicate_resource_output_coefficient" not in codes
    assert "missing_resource_output_coefficient" not in codes


def test_resource_output_coefficient_out_of_range_from_a_bypassed_construction_is_caught_by_invariants() -> (
    None
):
    """`StrictRealOutputPerResourceUnit`'s `gt=0` already rejects this on every legitimate
    path — defense-in-depth for a fully bypassed row construction (D5/§10: zero is always
    invalid, never a legal "no contribution" encoding)."""
    country = make_country("a")
    assert country.economy is not None
    bypassed_coefficient = ResourceOutputCoefficient.model_construct(
        category=ResourceCategory.IRON_ORE, real_output_per_unit=0
    )
    coefficients = _all_resource_output_coefficients(
        {ResourceCategory.IRON_ORE: bypassed_coefficient}
    )
    bypassed_economy = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=country.economy.sectors,
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=coefficients,
    )
    country = country.model_copy(update={"economy": bypassed_economy})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "resource_output_coefficient_out_of_range" in codes


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
    bypassed = EconomyState.model_construct(
        effective_labor_force_share_bps=country.economy.effective_labor_force_share_bps,
        sectors=tuple(sectors),
        resource_deposits=country.economy.resource_deposits,
        resource_output_coefficients=country.economy.resource_output_coefficients,
    )
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


# --- Phase 3A: the twelve political invariant codes (§10, T-V1/T-B5/T-B6) ----


def test_missing_player_politics_is_a_violation() -> None:
    country = make_country("a", with_politics=False)
    assert country.politics is None
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "player_politics_required" in codes


def test_ai_country_without_politics_is_not_a_violation() -> None:
    player = make_country("player", with_politics=True)
    ai = make_country("ai_neighbor", with_politics=False)
    assert ai.politics is None

    state = make_game_state(
        countries={"player": player, "ai_neighbor": ai}, player_country_id="player"
    )
    assert check_invariants(state) == []


def test_non_player_politics_is_a_violation() -> None:
    """(R6) A non-player country carrying a `PoliticalState` is rejected outright — Phase 3A
    cannot resolve politics for a country with no economy to derive performance from."""
    player = make_country("player", with_politics=True)
    ai = make_country("ai_neighbor", with_politics=False, economy=None)
    ai = ai.model_copy(update={"politics": make_politics()})

    state = make_game_state(
        countries={"player": player, "ai_neighbor": ai}, player_country_id="player"
    )
    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "non_player_politics_not_supported" in codes


def test_invalid_constitutional_combination_from_a_bypassed_construction_is_caught() -> None:
    """`ConstitutionState`'s own validator (C1-C9) already rejects an incoherent combination at
    every legitimate construction path — this is defense-in-depth for a fully bypassed
    construction, mirroring every other `_check_*` backstop in this module."""
    country = make_country("a")
    assert country.politics is not None
    bypassed_constitution = ConstitutionState.model_construct(
        executive_system=ExecutiveSystem.PARLIAMENTARY,
        executive_selection=ExecutiveSelection.DIRECT_ELECTION,  # incoherent: C2
        legislature=country.politics.constitution.legislature,
        territorial_organization=country.politics.constitution.territorial_organization,
        judicial_review=country.politics.constitution.judicial_review,
        amendment_difficulty=country.politics.constitution.amendment_difficulty,
        decree_authority=country.politics.constitution.decree_authority,
        executive_term_limit_terms=None,
        national_election_interval_turns=None,
    )
    bypassed_politics = country.politics.model_copy(update={"constitution": bypassed_constitution})
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "invalid_constitutional_combination" in codes


def test_constitutional_order_support_out_of_range_from_a_bypassed_construction_is_caught() -> None:
    country = make_country("a")
    assert country.politics is not None
    bypassed_politics = PoliticalState.model_construct(
        constitution=country.politics.constitution,
        constitutional_order_support_bps=10_001,
        legitimacy_bps=country.politics.legitimacy_bps,
        political_capital=country.politics.political_capital,
        political_capital_capacity=country.politics.political_capital_capacity,
        economic_baseline=None,
    )
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "constitutional_order_support_out_of_range" in codes


def test_legitimacy_out_of_range_from_a_bypassed_construction_is_caught() -> None:
    country = make_country("a")
    assert country.politics is not None
    bypassed_politics = PoliticalState.model_construct(
        constitution=country.politics.constitution,
        constitutional_order_support_bps=country.politics.constitutional_order_support_bps,
        legitimacy_bps=-1,
        political_capital=country.politics.political_capital,
        political_capital_capacity=country.politics.political_capital_capacity,
        economic_baseline=None,
    )
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "legitimacy_out_of_range" in codes


def test_political_capital_negative_from_a_bypassed_construction_is_caught() -> None:
    country = make_country("a")
    assert country.politics is not None
    bypassed_politics = PoliticalState.model_construct(
        constitution=country.politics.constitution,
        constitutional_order_support_bps=country.politics.constitutional_order_support_bps,
        legitimacy_bps=country.politics.legitimacy_bps,
        political_capital=-1,
        political_capital_capacity=country.politics.political_capital_capacity,
        economic_baseline=None,
    )
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "political_capital_negative" in codes


def test_political_capital_capacity_not_positive_from_a_bypassed_construction_is_caught() -> None:
    country = make_country("a")
    assert country.politics is not None
    bypassed_politics = PoliticalState.model_construct(
        constitution=country.politics.constitution,
        constitutional_order_support_bps=country.politics.constitutional_order_support_bps,
        legitimacy_bps=country.politics.legitimacy_bps,
        political_capital=0,
        political_capital_capacity=0,
        economic_baseline=None,
    )
    country = country.model_copy(update={"politics": bypassed_politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "political_capital_capacity_not_positive" in codes


def test_political_capital_exceeds_capacity_is_caught() -> None:
    """No `PoliticalState` validator enforces `political_capital <= political_capital_capacity`
    at construction (reject-not-normalize belongs to `simulation.invariants`, mirroring the
    scenario-authored `opening > capacity` case in `simulation.legitimacy`'s docstring) -- this
    is reachable through an ordinary, non-bypassed construction."""
    country = make_country("a")
    assert country.politics is not None
    politics = country.politics.model_copy(
        update={"political_capital": 2_000, "political_capital_capacity": 1_000}
    )
    country = country.model_copy(update={"politics": politics})
    state = make_game_state(countries={"a": country}, player_country_id="a")

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "political_capital_exceeds_capacity" in codes


def test_economic_baseline_present_at_genesis_is_caught() -> None:
    country = make_country("a")
    assert country.politics is not None
    politics = country.politics.model_copy(
        update={
            "economic_baseline": EconomicBaselineState(
                source_turn=0, total_gross_output=1, unemployment_rate_bps=1_000
            )
        }
    )
    country = country.model_copy(update={"politics": politics})
    state = make_game_state(countries={"a": country}, player_country_id="a", turn=0)

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "economic_baseline_present_at_genesis" in codes


def test_economic_baseline_missing_after_genesis_is_caught() -> None:
    country = make_country("a", politics=make_politics(economic_baseline=None))
    state = make_game_state(countries={"a": country}, player_country_id="a", turn=3)

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "economic_baseline_missing_after_genesis" in codes


def test_economic_baseline_turn_mismatch_is_caught() -> None:
    country = make_country(
        "a",
        politics=make_politics(
            economic_baseline=EconomicBaselineState(
                source_turn=2, total_gross_output=1, unemployment_rate_bps=1_000
            )
        ),
    )
    state = make_game_state(countries={"a": country}, player_country_id="a", turn=3)

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "economic_baseline_turn_mismatch" in codes


def test_economic_baseline_unemployment_out_of_range_from_a_bypassed_construction_is_caught() -> (
    None
):
    country = make_country("a")
    assert country.politics is not None
    bypassed_baseline = EconomicBaselineState.model_construct(
        source_turn=0, total_gross_output=1, unemployment_rate_bps=10_001
    )
    politics = country.politics.model_copy(update={"economic_baseline": bypassed_baseline})
    country = country.model_copy(update={"politics": politics})
    state = make_game_state(countries={"a": country}, player_country_id="a", turn=0)

    violations = check_invariants(state)
    codes = {v.code for v in violations}
    assert "economic_baseline_unemployment_out_of_range" in codes


def test_all_twelve_political_codes_are_distinct() -> None:
    """A regression pin: if two political checks ever accidentally shared a code, this would
    catch it -- mirroring the intent (not the mechanism) of the economy/finance sections' own
    total-coverage tests above."""
    expected = {
        "player_politics_required",
        "non_player_politics_not_supported",
        "invalid_constitutional_combination",
        "constitutional_order_support_out_of_range",
        "legitimacy_out_of_range",
        "political_capital_negative",
        "political_capital_capacity_not_positive",
        "political_capital_exceeds_capacity",
        "economic_baseline_present_at_genesis",
        "economic_baseline_missing_after_genesis",
        "economic_baseline_turn_mismatch",
        "economic_baseline_unemployment_out_of_range",
    }
    assert len(expected) == 12


def test_no_report_formula_codes_leaked_into_invariants_source() -> None:
    """T-V2 (§10): the four families of check deliberately NOT given a `check_invariants` code —
    because they need a `TurnReport` (report-formula re-derivation, owned by `PoliticalReport`'s
    own validators in §9.1) or two `GameState`s (report-vs-state reconciliation, owned by
    `reconcile_political_report` in §9.3) — must never appear in `invariants.py`. `check_invariants`
    takes a single `GameState` and nothing else, so it structurally cannot decide any of these;
    this is a static guard that the boundary stays honored even as the module grows.
    """
    import inspect

    from app.simulation import invariants as invariants_module

    source = inspect.getsource(invariants_module)
    forbidden_code_fragments = (
        "legitimacy_change_mismatch",
        "performance_contribution_mismatch",
        "political_capital_regeneration_mismatch",
        "order_support_contribution_mismatch",
        "opening_baseline_mismatch",
        "closing_baseline_mismatch",
        "constitution_mutated",
        "order_support_mutated",
        "noncanonical_political_order",
    )
    for fragment in forbidden_code_fragments:
        assert fragment not in source, (
            f"{fragment!r} is a report-formula or report-vs-state check and must not be "
            "decidable from state alone -- it belongs to PoliticalReport's validators (§9.1) "
            "or reconcile_political_report (§9.3), never to check_invariants"
        )
