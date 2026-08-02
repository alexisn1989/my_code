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

    return violations


def _check_economy(country: CountryState) -> list[InvariantViolation]:
    """Re-check `EconomyState`'s own construction-time invariant every turn.

    `EconomyState.sectors` is a tuple of mutable `SectorState` objects (kept
    mutable deliberately — a later economy phase makes `employed_workers`
    adjustable), so a nested `sector.category = ...` assignment performed
    *after* construction can desynchronize a previously-valid `EconomyState`
    from "all 11 categories, exactly once" without ever re-running
    `EconomyState`'s own `@model_validator`. This is the independent,
    every-turn backstop for that gap — not a duplicate of the constructor
    check, a catch for what the constructor check cannot see.
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

    total_employment = sum(sector.employed_workers for sector in country.economy.sectors)
    if total_employment > country.population:
        violations.append(
            InvariantViolation(
                code="sector_employment_exceeds_population",
                message=(
                    f"country {country.id!r}: total sector employment {total_employment} "
                    f"exceeds population {country.population}"
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
