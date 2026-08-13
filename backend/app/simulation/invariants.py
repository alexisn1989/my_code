"""Cross-field invariant checks over a `GameState`.

Per-field constraints (non-negative population, 0-100 bounded metrics) are
already enforced by Pydantic field validators on `simulation.state` models
and don't need to be re-checked here. This module checks invariants that spa
multiple fields or multiple objects, which Pydantic field validation cannot
express: population-group shares summing to 1.0, treasury non-negativity as
a whole-object property, and so on.

`resolver.resolve_turn` calls `check_invariants` both before copying the
input state and after running all phases on the working copy — a violation
either way aborts the resolution (see `docs/architecture.md`, "Turn
resolution").
"""

from __future__ import annotations

from app.core.errors import InvariantViolation
from app.simulation.constitution import DecreeAuthority, Legislature, first_constitutional_violation
from app.simulation.legislature import LegislativeChamber
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    CountryState,
    GameState,
    ResourceCategory,
    SectorCategory,
)

_RELATIONSHIP_MIN = -10_000
_RELATIONSHIP_MAX = 10_000
_CANONICAL_CHAMBER_ORDER = tuple(LegislativeChamber)

GROUP_SHARE_TOLERANCE = 1e-6
"""Documented rounding tolerance (product spec §8) for population-group share reconciliation."""


def _check_country(country: CountryState) -> list[InvariantViolation]:
    violations: list[InvariantViolation] = []

    if country.population_groups:
        total_share = sum(g.population_share for g in country.population_groups)
        if abs(total_share - 1.0) > GROUP_SHARE_TOLERANCE:
            violations.append(
                InvariantViolation(
                    code="group_shares_not_normalized",
                    message=(
                        f"country {country.id!r}: population_group shares sum to "
                        f"{total_share!r}, expected 1.0 within tolerance "
                        f"{GROUP_SHARE_TOLERANCE!r}"
                    ),
                )
            )

    seen_group_ids: set[str] = set()
    for group in country.population_groups:
        if group.id in seen_group_ids:
            violations.append(
                InvariantViolation(
                    code="duplicate_population_group_id",
                    message=f"country {country.id!r}: duplicate population_group id {group.id!r}",
                )
            )
        seen_group_ids.add(group.id)

    seen_institution_ids: set[str] = set()
    for institution in country.institutions:
        if institution.id in seen_institution_ids:
            violations.append(
                InvariantViolation(
                    code="duplicate_institution_id",
                    message=f"country {country.id!r}: duplicate institution id {institution.id!r}",
                )
            )
        seen_institution_ids.add(institution.id)

    violations.extend(_check_economy(country))
    violations.extend(_check_tax_base_coefficients(country))

    return violations


_BPS_MIN = 0
_BPS_MAX = 10_000


def _check_tax_base_coefficients(country: CountryState) -> list[InvariantViolation]:
    """Every-turn backstop re-checking basis-point range on the Phase 2B2 tax-base
    coefficients, mirroring `_check_economy`'s role for `EconomyState`: `StrictBps` already
    rejects an out-of-range value at every legitimate construction/assignment path, but a
    fully bypassed construction (`model_construct`, or a raw dict smuggled in through some
    future non-validating restore path) skips that entirely. This is defense-in-depth, not a
    claim that the gap is reachable through ordinary Pydantic-validated code today.
    """
    violations: list[InvariantViolation] = []

    if country.finance is not None:
        coefficients = country.finance.tax_base_coefficients
        for field_name, value in (
            ("personal_taxable_share_bps", coefficients.personal_taxable_share_bps),
            ("corporate_taxable_share_bps", coefficients.corporate_taxable_share_bps),
            (
                "effective_consumption_base_share_bps",
                coefficients.effective_consumption_base_share_bps,
            ),
        ):
            if not (_BPS_MIN <= value <= _BPS_MAX):
                violations.append(
                    InvariantViolation(
                        code="tax_base_coefficient_out_of_range",
                        message=(
                            f"country {country.id!r}: tax_base_coefficients.{field_name}="
                            f"{value} is outside [{_BPS_MIN}, {_BPS_MAX}]"
                        ),
                    )
                )

    if country.economy is not None:
        for sector in country.economy.sectors:
            for field_name, value in (
                ("value_added_share_bps", sector.value_added_share_bps),
                ("labor_income_share_bps", sector.labor_income_share_bps),
            ):
                if not (_BPS_MIN <= value <= _BPS_MAX):
                    violations.append(
                        InvariantViolation(
                            code="sector_tax_base_share_out_of_range",
                            message=(
                                f"country {country.id!r}: sector {sector.category.value!r} "
                                f"{field_name}={value} is outside [{_BPS_MIN}, {_BPS_MAX}]"
                            ),
                        )
                    )

    return violations


def _check_economy(country: CountryState) -> list[InvariantViolation]:
    """Re-check `EconomyState`'s own construction-time invariant every turn.

    `EconomyState.sectors` is a tuple of mutable `SectorState` objects, so a nested
    `sector.category = ...` assignment performed *after* construction can desynchronize a
    previously-valid `EconomyState` from "all 11 categories, exactly once" without ever
    re-running `EconomyState`'s own `@model_validator`. This is the independent, every-turn
    backstop for that gap — not a duplicate of the constructor check, a catch for what the
    constructor check cannot see.

    Also re-checks `effective_labor_force_share_bps` range and the derived
    `effective_labor_force <= population` bound (Phase 2B3) — `StrictBps` already rejects an
    out-of-range share at every legitimate construction/assignment path, so this is
    defense-in-depth against a fully bypassed construction, mirroring
    `_check_tax_base_coefficients`'s role for the Phase 2B2 coefficients.

    Also re-checks `resource_deposits`'s own completeness/order rule and each deposit's
    renewability rules (Phase 2C1), for the identical reason: `ResourceDepositState` is mutable,
    so a nested `deposit.category = ...`/`deposit.regeneration_per_turn = ...` assignment after
    construction can desynchronize an already-valid `EconomyState` without re-running its own
    validator. Unlike `noncanonical_sector_order` above, `noncanonical_resource_order` is *even
    more* purely defense-in-depth (R3): `EconomyState`'s own constructor already **rejects**
    reordered `resource_deposits` outright (it does not merely normalize, the way the sector
    validator does), so this backstop is reachable only through a fully bypassed construction on
    every path, not just the noncanonical-order one.
    """
    if country.economy is None:
        return []

    violations: list[InvariantViolation] = []
    categories = [sector.category for sector in country.economy.sectors]

    seen: set[SectorCategory] = set()
    duplicates: set[SectorCategory] = set()
    for category in categories:
        if category in seen:
            duplicates.add(category)
        seen.add(category)
    if duplicates:
        violations.append(
            InvariantViolation(
                code="duplicate_sector_category",
                message=(
                    f"country {country.id!r}: duplicate sector categories "
                    f"{sorted(c.value for c in duplicates)!r}"
                ),
            )
        )

    missing = [c for c in SectorCategory if c not in seen]
    if missing:
        violations.append(
            InvariantViolation(
                code="missing_sector_category",
                message=(
                    f"country {country.id!r}: missing sector categories "
                    f"{[c.value for c in missing]!r} — all {len(SectorCategory)} are required"
                ),
            )
        )

    if not duplicates and not missing and tuple(categories) != tuple(SectorCategory):
        violations.append(
            InvariantViolation(
                code="noncanonical_sector_order",
                message=(
                    f"country {country.id!r}: economy.sectors is not ordered in canonical "
                    "SectorCategory declaration order"
                ),
            )
        )

    share_bps = country.economy.effective_labor_force_share_bps
    if not (_BPS_MIN <= share_bps <= _BPS_MAX):
        violations.append(
            InvariantViolation(
                code="effective_labor_force_share_out_of_range",
                message=(
                    f"country {country.id!r}: economy.effective_labor_force_share_bps="
                    f"{share_bps} is outside [{_BPS_MIN}, {_BPS_MAX}]"
                ),
            )
        )
    else:
        effective_labor_force = (country.population * share_bps) // _BPS_MAX
        if effective_labor_force > country.population:
            violations.append(
                InvariantViolation(
                    code="effective_labor_force_exceeds_population",
                    message=(
                        f"country {country.id!r}: effective_labor_force "
                        f"{effective_labor_force} exceeds population {country.population}"
                    ),
                )
            )

    resource_categories = [deposit.category for deposit in country.economy.resource_deposits]

    seen_resources: set[ResourceCategory] = set()
    duplicate_resources: set[ResourceCategory] = set()
    for resource_category in resource_categories:
        if resource_category in seen_resources:
            duplicate_resources.add(resource_category)
        seen_resources.add(resource_category)
    if duplicate_resources:
        violations.append(
            InvariantViolation(
                code="duplicate_resource_category",
                message=(
                    f"country {country.id!r}: duplicate resource categories "
                    f"{sorted(c.value for c in duplicate_resources)!r}"
                ),
            )
        )

    missing_resources = [c for c in ResourceCategory if c not in seen_resources]
    if missing_resources:
        violations.append(
            InvariantViolation(
                code="missing_resource_category",
                message=(
                    f"country {country.id!r}: missing resource categories "
                    f"{[c.value for c in missing_resources]!r} — all {len(ResourceCategory)} "
                    "are required"
                ),
            )
        )

    if (
        not duplicate_resources
        and not missing_resources
        and tuple(resource_categories) != tuple(ResourceCategory)
    ):
        violations.append(
            InvariantViolation(
                code="noncanonical_resource_order",
                message=(
                    f"country {country.id!r}: economy.resource_deposits is not ordered in "
                    "canonical ResourceCategory declaration order"
                ),
            )
        )

    for deposit in country.economy.resource_deposits:
        if deposit.category not in RENEWABLE_RESOURCES:
            if deposit.regeneration_per_turn != 0 or deposit.stock_ceiling is not None:
                violations.append(
                    InvariantViolation(
                        code="resource_regeneration_on_nonrenewable",
                        message=(
                            f"country {country.id!r}: nonrenewable deposit "
                            f"{deposit.category.value!r} has regeneration_per_turn="
                            f"{deposit.regeneration_per_turn} and/or stock_ceiling="
                            f"{deposit.stock_ceiling}; both must be 0/None"
                        ),
                    )
                )
        elif deposit.stock_ceiling is None:
            violations.append(
                InvariantViolation(
                    code="renewable_missing_stock_ceiling",
                    message=(
                        f"country {country.id!r}: renewable deposit "
                        f"{deposit.category.value!r} has no stock_ceiling"
                    ),
                )
            )
        elif deposit.remaining_stock > deposit.stock_ceiling:
            violations.append(
                InvariantViolation(
                    code="resource_stock_exceeds_ceiling",
                    message=(
                        f"country {country.id!r}: deposit {deposit.category.value!r} "
                        f"remaining_stock={deposit.remaining_stock} exceeds "
                        f"stock_ceiling={deposit.stock_ceiling}"
                    ),
                )
            )

    coefficient_categories = [
        coefficient.category for coefficient in country.economy.resource_output_coefficients
    ]

    seen_coefficients: set[ResourceCategory] = set()
    duplicate_coefficients: set[ResourceCategory] = set()
    for coefficient_category in coefficient_categories:
        if coefficient_category in seen_coefficients:
            duplicate_coefficients.add(coefficient_category)
        seen_coefficients.add(coefficient_category)
    if duplicate_coefficients:
        violations.append(
            InvariantViolation(
                code="duplicate_resource_output_coefficient",
                message=(
                    f"country {country.id!r}: duplicate resource output coefficient categories "
                    f"{sorted(c.value for c in duplicate_coefficients)!r}"
                ),
            )
        )

    missing_coefficients = [c for c in ResourceCategory if c not in seen_coefficients]
    if missing_coefficients:
        violations.append(
            InvariantViolation(
                code="missing_resource_output_coefficient",
                message=(
                    f"country {country.id!r}: missing resource output coefficient categories "
                    f"{[c.value for c in missing_coefficients]!r} — all {len(ResourceCategory)} "
                    "are required"
                ),
            )
        )

    if (
        not duplicate_coefficients
        and not missing_coefficients
        and tuple(coefficient_categories) != tuple(ResourceCategory)
    ):
        violations.append(
            InvariantViolation(
                code="noncanonical_resource_output_coefficient_order",
                message=(
                    f"country {country.id!r}: economy.resource_output_coefficients is not "
                    "ordered in canonical ResourceCategory declaration order"
                ),
            )
        )

    for coefficient in country.economy.resource_output_coefficients:
        if coefficient.real_output_per_unit <= 0:
            violations.append(
                InvariantViolation(
                    code="resource_output_coefficient_out_of_range",
                    message=(
                        f"country {country.id!r}: resource output coefficient for "
                        f"{coefficient.category.value!r} has real_output_per_unit="
                        f"{coefficient.real_output_per_unit}, must be > 0"
                    ),
                )
            )

    return violations


def _check_politics(
    country: CountryState, *, state_turn: int, is_player: bool
) -> list[InvariantViolation]:
    """Phase 3A structural backstops for `PoliticalState` (§10), mirroring `_check_economy`'s
    role: every field here is already enforced at every legitimate construction/assignment path
    by `PoliticalState`/`ConstitutionState`'s own Pydantic validators, but both are mutable, so a
    nested assignment after construction can desynchronize an already-valid instance without
    re-running those validators. This is the every-turn, bypassed-construction backstop.

    `state_turn` and `is_player` come from `check_invariants` (this function has no access to
    `GameState` itself) — needed for the R6 baseline-lifecycle checks (which turn is this?) and
    the non-player-politics check (is this country allowed to have politics at all?).
    """
    violations: list[InvariantViolation] = []

    if not is_player and country.politics is not None:
        violations.append(
            InvariantViolation(
                code="non_player_politics_not_supported",
                message=(
                    f"country {country.id!r} is not the player but has a PoliticalState; "
                    "Phase 3A cannot resolve politics for a country with no economy to derive "
                    "performance from — AI-country politics is deferred (see roadmap ticket "
                    "POL-4)"
                ),
            )
        )

    if country.politics is None:
        return violations

    politics = country.politics

    if not (_BPS_MIN <= politics.constitutional_order_support_bps <= _BPS_MAX):
        violations.append(
            InvariantViolation(
                code="constitutional_order_support_out_of_range",
                message=(
                    f"country {country.id!r}: constitutional_order_support_bps="
                    f"{politics.constitutional_order_support_bps} outside "
                    f"[{_BPS_MIN}, {_BPS_MAX}]"
                ),
            )
        )

    if not (_BPS_MIN <= politics.legitimacy_bps <= _BPS_MAX):
        violations.append(
            InvariantViolation(
                code="legitimacy_out_of_range",
                message=(
                    f"country {country.id!r}: legitimacy_bps={politics.legitimacy_bps} outside "
                    f"[{_BPS_MIN}, {_BPS_MAX}]"
                ),
            )
        )

    if politics.political_capital < 0:
        violations.append(
            InvariantViolation(
                code="political_capital_negative",
                message=(
                    f"country {country.id!r}: political_capital={politics.political_capital} "
                    "is negative"
                ),
            )
        )

    if politics.political_capital_capacity <= 0:
        violations.append(
            InvariantViolation(
                code="political_capital_capacity_not_positive",
                message=(
                    f"country {country.id!r}: political_capital_capacity="
                    f"{politics.political_capital_capacity} is not positive"
                ),
            )
        )
    elif politics.political_capital > politics.political_capital_capacity:
        violations.append(
            InvariantViolation(
                code="political_capital_exceeds_capacity",
                message=(
                    f"country {country.id!r}: political_capital={politics.political_capital} "
                    f"exceeds political_capital_capacity={politics.political_capital_capacity}"
                ),
            )
        )

    problem = first_constitutional_violation(politics.constitution)
    if problem is not None:
        rule_code, rule_message = problem
        # (Phase 3B1) C10 is deliberately NOT reported here as "invalid_constitutional_combination"
        # -- `_check_legislature` below reports it under its own dedicated
        # `legislature_absent_requires_unlimited_decree` code, so a country with no legislature
        # and no unlimited decree gets exactly one violation for that one defect, not two. Every
        # other rule (C1-C9) is unaffected and still reported here exactly as before.
        if rule_code != "legislature_absent_requires_unlimited_decree":
            violations.append(
                InvariantViolation(
                    code="invalid_constitutional_combination",
                    message=f"country {country.id!r}: {rule_code}: {rule_message}",
                )
            )

    baseline = politics.economic_baseline
    if state_turn == 0:
        if baseline is not None:
            violations.append(
                InvariantViolation(
                    code="economic_baseline_present_at_genesis",
                    message=(
                        f"country {country.id!r}: state.turn == 0 but politics.economic_baseline "
                        "is present; no turn has been resolved, so no observations can exist"
                    ),
                )
            )
    elif baseline is None:
        violations.append(
            InvariantViolation(
                code="economic_baseline_missing_after_genesis",
                message=(
                    f"country {country.id!r}: state.turn={state_turn} but "
                    "politics.economic_baseline is None; every resolved turn writes one"
                ),
            )
        )
    elif baseline.source_turn != state_turn:
        violations.append(
            InvariantViolation(
                code="economic_baseline_turn_mismatch",
                message=(
                    f"country {country.id!r}: politics.economic_baseline.source_turn="
                    f"{baseline.source_turn} does not equal state.turn={state_turn}"
                ),
            )
        )

    if baseline is not None and not (_BPS_MIN <= baseline.unemployment_rate_bps <= _BPS_MAX):
        violations.append(
            InvariantViolation(
                code="economic_baseline_unemployment_out_of_range",
                message=(
                    f"country {country.id!r}: economic_baseline.unemployment_rate_bps="
                    f"{baseline.unemployment_rate_bps} outside [{_BPS_MIN}, {_BPS_MAX}]"
                ),
            )
        )

    return violations


def _check_legislature(country: CountryState, *, is_player: bool) -> list[InvariantViolation]:
    """Phase 3B1 structural backstops for `PoliticalState.legislature` (§10), mirroring
    `_check_politics`'s role: every rule here is already enforced at every legitimate
    construction/assignment path by `LegislatureState`/`PartyState`/`LegislativeBlocState`/
    `PoliticalState`'s own Pydantic validators, but those are all mutable, so a nested assignment
    after construction can desynchronize an already-valid instance without re-running them. This
    is the every-turn, bypassed-construction backstop — every rule below is recomputed directly
    from `country`'s fields, never by re-invoking a Pydantic validator.

    Ordering deliberately avoids cascaded noise: a check that cannot be meaningfully evaluated
    once an earlier structural defect has been found is skipped rather than reported a second time
    under a different code (duplicate chambers/parties/blocs suppress their own order checks;
    an unknown-chamber seat reference is excluded from that chamber's seat-total accumulation
    rather than crashing or silently corrupting a real chamber's total).

    `legislature_absent_requires_unlimited_decree` (C10) is deliberately **not** also reported by
    `_check_politics` as `invalid_constitutional_combination` — see that function's comment. Every
    other code here is independent of, and additional to, `_check_politics`'s checks.
    """
    violations: list[InvariantViolation] = []
    politics = country.politics
    if politics is None:
        return violations  # nothing to check; player_politics_required already covers this

    legislature = politics.legislature

    if not is_player:
        if legislature is not None:
            violations.append(
                InvariantViolation(
                    code="non_player_legislature_not_supported",
                    message=(
                        f"country {country.id!r} is not the player but has a legislature; "
                        "Phase 3A already forbids non-player politics entirely, and Phase 3B1 "
                        "does not extend legislative resolution to AI countries"
                    ),
                )
            )
        # Non-player politics is unsupported at all (see `_check_politics`'s
        # `non_player_politics_not_supported`); running the structural checks below against
        # content that should not exist at all would only add noise, not signal.
        return violations

    constitution = politics.constitution
    declared = constitution.legislature

    if declared is not Legislature.NONE and legislature is None:
        violations.append(
            InvariantViolation(
                code="legislature_required_by_constitution",
                message=(
                    f"country {country.id!r}: constitution.legislature is {declared.value!r} "
                    "but politics.legislature is None"
                ),
            )
        )
    if declared is Legislature.NONE and legislature is not None:
        violations.append(
            InvariantViolation(
                code="legislature_forbidden_by_constitution",
                message=(
                    f"country {country.id!r}: constitution.legislature is 'none' but a "
                    "legislature is present"
                ),
            )
        )

    if (
        declared is Legislature.NONE
        and constitution.decree_authority is not DecreeAuthority.UNLIMITED
    ):
        violations.append(
            InvariantViolation(
                code="legislature_absent_requires_unlimited_decree",
                message=(
                    f"country {country.id!r}: legislature is 'none' but decree_authority is "
                    f"{constitution.decree_authority.value!r}, so no organ can make law"
                ),
            )
        )

    if legislature is None:
        return violations  # nothing further to check without a legislature to inspect

    chambers = legislature.chambers
    parties = legislature.parties

    seen_chambers: set[LegislativeChamber] = set()
    duplicate_chamber_found = False
    for chamber_state in chambers:
        if chamber_state.chamber in seen_chambers:
            violations.append(
                InvariantViolation(
                    code="duplicate_chamber",
                    message=(
                        f"country {country.id!r}: duplicate chamber {chamber_state.chamber.value!r}"
                    ),
                )
            )
            duplicate_chamber_found = True
        seen_chambers.add(chamber_state.chamber)

    if not duplicate_chamber_found:
        chamber_sequence = [c.chamber for c in chambers]
        canonical_sequence = sorted(chamber_sequence, key=_CANONICAL_CHAMBER_ORDER.index)
        if chamber_sequence != canonical_sequence:
            violations.append(
                InvariantViolation(
                    code="noncanonical_chamber_order",
                    message=(
                        f"country {country.id!r}: chambers must be in canonical order "
                        f"{[c.value for c in _CANONICAL_CHAMBER_ORDER]!r}, got "
                        f"{[c.value for c in chamber_sequence]!r}"
                    ),
                )
            )

    if declared in (Legislature.UNICAMERAL, Legislature.BICAMERAL):
        expected_chamber_count = 1 if declared is Legislature.UNICAMERAL else 2
        if len(chambers) != expected_chamber_count:
            violations.append(
                InvariantViolation(
                    code="chamber_count_mismatch_with_constitution",
                    message=(
                        f"country {country.id!r}: constitution.legislature is {declared.value!r} "
                        f"but the legislature has {len(chambers)} chamber(s), expected "
                        f"{expected_chamber_count}"
                    ),
                )
            )
        elif (
            declared is Legislature.UNICAMERAL
            and chambers[0].chamber is not LegislativeChamber.LOWER
        ):
            violations.append(
                InvariantViolation(
                    code="unicameral_chamber_must_be_lower",
                    message=(
                        f"country {country.id!r}: a unicameral legislature's single chamber must "
                        f"be 'lower', got {chambers[0].chamber.value!r}"
                    ),
                )
            )

    for chamber_state in chambers:
        if chamber_state.total_seats <= 0:
            violations.append(
                InvariantViolation(
                    code="chamber_total_seats_not_positive",
                    message=(
                        f"country {country.id!r}: chamber {chamber_state.chamber.value!r} "
                        f"total_seats={chamber_state.total_seats} is not positive"
                    ),
                )
            )

    seen_party_ids: set[str] = set()
    duplicate_party_found = False
    for party in parties:
        if party.id in seen_party_ids:
            violations.append(
                InvariantViolation(
                    code="duplicate_party_id",
                    message=f"country {country.id!r}: duplicate party id {party.id!r}",
                )
            )
            duplicate_party_found = True
        seen_party_ids.add(party.id)

    if not duplicate_party_found:
        party_ids = [party.id for party in parties]
        if party_ids != sorted(party_ids):
            violations.append(
                InvariantViolation(
                    code="noncanonical_party_order",
                    message=(
                        f"country {country.id!r}: parties must be sorted by id, got {party_ids!r}"
                    ),
                )
            )

    known_chambers = {chamber_state.chamber for chamber_state in chambers}
    seat_totals_by_chamber: dict[LegislativeChamber, int] = dict.fromkeys(known_chambers, 0)

    for party in parties:
        if not party.blocs:
            violations.append(
                InvariantViolation(
                    code="party_has_no_blocs",
                    message=f"country {country.id!r}: party {party.id!r} has no blocs",
                )
            )
            continue  # nothing further to check for a party with no blocs to inspect

        seen_bloc_ids: set[str] = set()
        duplicate_bloc_found = False
        for bloc in party.blocs:
            if bloc.id in seen_bloc_ids:
                violations.append(
                    InvariantViolation(
                        code="duplicate_bloc_id",
                        message=(
                            f"country {country.id!r}: party {party.id!r} has duplicate bloc id "
                            f"{bloc.id!r}"
                        ),
                    )
                )
                duplicate_bloc_found = True
            seen_bloc_ids.add(bloc.id)

        if not duplicate_bloc_found:
            bloc_ids = [bloc.id for bloc in party.blocs]
            if bloc_ids != sorted(bloc_ids):
                violations.append(
                    InvariantViolation(
                        code="noncanonical_bloc_order",
                        message=(
                            f"country {country.id!r}: blocs of party {party.id!r} must be sorted "
                            f"by id, got {bloc_ids!r}"
                        ),
                    )
                )

        for bloc in party.blocs:
            seen_bloc_chambers: set[LegislativeChamber] = set()
            duplicate_bloc_seats_found = False
            for entry in bloc.seats:
                if entry.chamber in seen_bloc_chambers:
                    violations.append(
                        InvariantViolation(
                            code="duplicate_bloc_chamber_seats",
                            message=(
                                f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} has "
                                f"duplicate seats for chamber {entry.chamber.value!r}"
                            ),
                        )
                    )
                    duplicate_bloc_seats_found = True
                seen_bloc_chambers.add(entry.chamber)

            if not duplicate_bloc_seats_found:
                entry_chambers = [entry.chamber for entry in bloc.seats]
                canonical_entry_chambers = sorted(
                    entry_chambers, key=_CANONICAL_CHAMBER_ORDER.index
                )
                if entry_chambers != canonical_entry_chambers:
                    violations.append(
                        InvariantViolation(
                            code="noncanonical_bloc_seats_order",
                            message=(
                                f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} seats "
                                f"must be in canonical chamber order, got "
                                f"{[c.value for c in entry_chambers]!r}"
                            ),
                        )
                    )

            for entry in bloc.seats:
                if entry.chamber not in known_chambers:
                    violations.append(
                        InvariantViolation(
                            code="bloc_seats_reference_unknown_chamber",
                            message=(
                                f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} holds "
                                f"seats in {entry.chamber.value!r}, which this legislature does "
                                "not have"
                            ),
                        )
                    )
                    continue  # no bucket exists for an unknown chamber; do not accumulate into it
                seat_totals_by_chamber[entry.chamber] += entry.seats

            if not (_RELATIONSHIP_MIN <= bloc.government_relationship_bps <= _RELATIONSHIP_MAX):
                violations.append(
                    InvariantViolation(
                        code="bloc_relationship_out_of_range",
                        message=(
                            f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} "
                            f"government_relationship_bps={bloc.government_relationship_bps} "
                            f"outside [{_RELATIONSHIP_MIN}, {_RELATIONSHIP_MAX}]"
                        ),
                    )
                )
            if not (
                _RELATIONSHIP_MIN <= bloc.baseline_government_relationship_bps <= _RELATIONSHIP_MAX
            ):
                violations.append(
                    InvariantViolation(
                        code="bloc_baseline_relationship_out_of_range",
                        message=(
                            f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} "
                            "baseline_government_relationship_bps="
                            f"{bloc.baseline_government_relationship_bps} "
                            f"outside [{_RELATIONSHIP_MIN}, {_RELATIONSHIP_MAX}]"
                        ),
                    )
                )
            if not (_BPS_MIN <= bloc.discipline_bps <= _BPS_MAX):
                violations.append(
                    InvariantViolation(
                        code="bloc_discipline_out_of_range",
                        message=(
                            f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} "
                            f"discipline_bps={bloc.discipline_bps} outside "
                            f"[{_BPS_MIN}, {_BPS_MAX}]"
                        ),
                    )
                )
            if not (_RELATIONSHIP_MIN <= bloc.tax_preference_bps <= _RELATIONSHIP_MAX):
                violations.append(
                    InvariantViolation(
                        code="bloc_preference_out_of_range",
                        message=(
                            f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} "
                            f"tax_preference_bps={bloc.tax_preference_bps} outside "
                            f"[{_RELATIONSHIP_MIN}, {_RELATIONSHIP_MAX}]"
                        ),
                    )
                )
            if not (_RELATIONSHIP_MIN <= bloc.spending_preference_bps <= _RELATIONSHIP_MAX):
                violations.append(
                    InvariantViolation(
                        code="bloc_preference_out_of_range",
                        message=(
                            f"country {country.id!r}: bloc {party.id!r}/{bloc.id!r} "
                            f"spending_preference_bps={bloc.spending_preference_bps} outside "
                            f"[{_RELATIONSHIP_MIN}, {_RELATIONSHIP_MAX}]"
                        ),
                    )
                )

    for chamber_state in chambers:
        recomputed_total = seat_totals_by_chamber.get(chamber_state.chamber, 0)
        if recomputed_total != chamber_state.total_seats:
            violations.append(
                InvariantViolation(
                    code="chamber_seat_total_mismatch",
                    message=(
                        f"country {country.id!r}: blocs hold {recomputed_total} seats in the "
                        f"{chamber_state.chamber.value!r} chamber, which has "
                        f"{chamber_state.total_seats}; every seat must be held by exactly one "
                        "bloc"
                    ),
                )
            )

    return violations


def check_invariants(state: GameState) -> list[InvariantViolation]:
    """Return every invariant violation found in `state`. Empty list means valid.

    Never raises; callers decide what to do with the result (the resolver
    wraps a non-empty result in `StateValidationError`).
    """
    violations: list[InvariantViolation] = []

    if state.world.player_country_id not in state.world.countries:
        violations.append(
            InvariantViolation(
                code="unknown_player_country",
                message=(
                    f"player_country_id {state.world.player_country_id!r} is not a "
                    f"key of world.countries"
                ),
            )
        )
    else:
        player = state.world.countries[state.world.player_country_id]
        if player.finance is None:
            violations.append(
                InvariantViolation(
                    code="player_finance_required",
                    message=(
                        f"player country {player.id!r} has no GovernmentFinanceState; "
                        "government accounting (Phase 2A) cannot resolve without it — "
                        "AI countries may omit finance, the player country may not"
                    ),
                )
            )
        if player.economy is None:
            violations.append(
                InvariantViolation(
                    code="player_economy_required",
                    message=(
                        f"player country {player.id!r} has no EconomyState; "
                        "sector production (Phase 2B1) cannot resolve without it — "
                        "AI countries may omit economy, the player country may not"
                    ),
                )
            )
        if player.politics is None:
            violations.append(
                InvariantViolation(
                    code="player_politics_required",
                    message=(
                        f"player country {player.id!r} has no PoliticalState; "
                        "legitimacy/political-capital resolution (Phase 3A) cannot resolve "
                        "without it — AI countries may omit politics, the player country may not"
                    ),
                )
            )

    for country in state.world.countries.values():
        is_player = country.id == state.world.player_country_id
        violations.extend(_check_country(country))
        violations.extend(_check_politics(country, state_turn=state.turn, is_player=is_player))
        violations.extend(_check_legislature(country, is_player=is_player))

    return violations
