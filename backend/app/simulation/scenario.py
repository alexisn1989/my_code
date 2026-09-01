"""Scenario parsing and validation — pure, no disk I/O.

Scenarios are authored as YAML (product spec §5.6, "content is data-driven").
A scenario file is parsed into a `ScenarioDefinition` — reusing the exact same
`CountryState`/`PopulationGroupState`/`InstitutionState`/`TreasuryState`
models that make up a live `GameState`, so there is one definition of "what a
country looks like," not a parallel authoring schema that can drift from the
runtime schema — then converted into an initial `GameState` at `turn=0`.

Any Pydantic structural failure (missing field, wrong type, out-of-range
value, unknown key under `extra="forbid"`) and any semantic failure (duplicate
country id, group shares that don't sum to 1.0, unknown `player_country_id`)
are collected and raised together as a single `ScenarioValidationError`,
rather than failing on the first problem found.

This module takes YAML *text*, not file paths — `app.simulation` has no I/O
dependencies (see `docs/architecture.md`, "System boundaries"). Reading a
scenario file from disk is `app.content.scenarios.load_scenario_file`, which
calls `load_scenario_text` here.

Scenarios declare `content_version` (the authored data they provide) but
**not** `ruleset_version` — that comes from the engine's `state.RULESET_VERSION`
constant, stamped onto every `GameState` built here. A scenario file does not
get to declare which simulation rules it runs under; `extra="forbid"` on
`ScenarioDefinition` means a scenario YAML that still has a `ruleset_version:`
key (e.g. an old one, before this changed) fails to parse rather than being
silently accepted with a value nobody checks.
"""

from __future__ import annotations

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.errors import ScenarioValidationError
from app.simulation.invariants import check_invariants
from app.simulation.state import (
    RULESET_VERSION,
    ConflictDyadState,
    CountryState,
    ForeignProfileState,
    GameState,
    StrategicMapState,
    WorldState,
)


class ScenarioDefinition(BaseModel):
    """The authored shape of a scenario file, before conversion to a `GameState`."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    scenario_id: str
    name: str
    content_version: str
    seed: int
    player_country_id: str
    countries: list[CountryState]
    foreign_profiles: dict[str, ForeignProfileState] = {}
    """External Wars Gate W1: abstract foreign actors (`WorldState.foreign_profiles`'s
    docstring). Defaults to empty so pre-W1 scenario shape stays representable in principle,
    though `RULESET_VERSION` still gates which saves this build accepts — see the
    `RULESET_VERSION` docstring's `"0.12.0" -> "0.13.0"` entry."""
    dyads: list[ConflictDyadState] = []
    """External Wars Gate W1: authored bilateral relationships (`ConflictDyadState`'s
    docstring)."""
    strategic_map: StrategicMapState
    """Strategic Military Map Gate M0: the campaign's defining map (`StrategicMapState`'s
    docstring). Required, matching `WorldState.strategic_map` -- every scenario authors its own
    map; there is no default map to fall back to."""


def _parse(source: str, raw_text: str) -> ScenarioDefinition:
    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ScenarioValidationError(source, [f"invalid YAML: {exc}"]) from exc

    if not isinstance(raw, dict):
        raise ScenarioValidationError(source, ["scenario file must contain a YAML mapping"])

    try:
        return ScenarioDefinition.model_validate(raw)
    except ValidationError as exc:
        problems = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise ScenarioValidationError(source, problems) from exc


def _to_game_state(source: str, scenario: ScenarioDefinition) -> GameState:
    problems: list[str] = []

    countries: dict[str, CountryState] = {}
    for country in scenario.countries:
        if country.id in countries:
            problems.append(f"duplicate country id {country.id!r}")
            continue
        countries[country.id] = country

    if scenario.player_country_id not in countries:
        problems.append(
            f"player_country_id {scenario.player_country_id!r} is not among the defined countries"
        )

    if problems:
        raise ScenarioValidationError(source, problems)

    state = GameState(
        schema_version=scenario.schema_version,
        ruleset_version=RULESET_VERSION,
        content_version=scenario.content_version,
        seed=scenario.seed,
        turn=0,
        state_version=0,
        world=WorldState(
            countries=countries,
            player_country_id=scenario.player_country_id,
            foreign_profiles=scenario.foreign_profiles,
            # Passed through AS AUTHORED, never sorted here: `WorldState`'s own validator
            # rejects a non-canonically-ordered tuple rather than silently normalizing it
            # (reject-not-normalize, matching `resource_deposits`'s policy).
            dyads=tuple(scenario.dyads),
            strategic_map=scenario.strategic_map,
        ),
    )

    violations = check_invariants(state)
    if violations:
        raise ScenarioValidationError(source, [v.message for v in violations])

    return state


def load_scenario_text(raw_text: str, *, source: str = "<string>") -> GameState:
    """Parse and validate scenario YAML text into an initial `GameState`."""
    scenario = _parse(source, raw_text)
    return _to_game_state(source, scenario)
