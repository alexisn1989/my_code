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
from app.simulation.state import CountryState, GameState

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

    for country in state.world.countries.values():
        violations.extend(_check_country(country))

    return violations
