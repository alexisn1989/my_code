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
from app.simulation.state import CountryState, GameState, SectorCategory

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

    for country in state.world.countries.values():
        violations.extend(_check_country(country))

    return violations
