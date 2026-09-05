"""The single production rule for military movement legality (Military Movement, commit 4).

This module is PURE INSPECTION. It reads an already-resolved `FormationState` and an authored
`StrategicMapState` and reports, for every theater, whether that formation could legally be
ordered there. It mutates nothing, draws no randomness, accepts no decision, and adds no player
action -- after commit 4 a player can submit exactly what they could submit before it.

It is the SINGLE implementation of movement legality. Commit 5's draft preview and its
authoritative submission validator both call `classify_destinations`; commit 6's
`/api/game/military` projection converts its results into displayable options. None of the three
re-derives the rule, so they cannot disagree about what is legal or about why.

Lives in its own module rather than in `geography.py`: this needs `FormationState` and
`StrategicMapState` from `state.py`, and `geography.py` is imported BY `state.py`. Importing
`state.py` from here closes no loop -- `state.py` imports only `constitution`,
`foreign_conflict`, `geography`, `legislature` and `app.core.*`.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, model_validator

from app.simulation.geography import StrictMapId, land_destinations_from
from app.simulation.state import (
    FormationState,
    PlayerCountryRef,
    StrategicMapState,
)

_STRICT_FROZEN_CONFIG = ConfigDict(extra="forbid", frozen=True)

DestinationIneligibilityCode: TypeAlias = Literal[
    "destination_is_origin",
    "destination_not_player_owned",
    "destination_not_directly_reachable",
]
"""Every reason this classifier can give, enumerated in the type rather than left as free text.

Exactly three, and deliberately not more:

- `formation_unknown` and `destination_theater_unknown` cannot arise HERE. This function receives
  an already-resolved `FormationState` and enumerates the map's own theater keys, so there is no
  unknown formation and no unknown theater to find. Commit 5's submission wrapper emits them,
  before it calls this.
- `formation_origin_unresolved` and `origin_not_player_owned` are state-integrity failures, not
  player-submission errors: commit 3's `formation_location_unknown_theater` and
  `formation_location_not_owned_by_country` invariants already guarantee neither can occur in a
  valid state.
- `route_kind_not_land` is unreachable while `RouteKind` has a single member, so the LAND
  requirement is folded into `destination_not_directly_reachable`. A future ruleset adding SEA or
  AIR may split it out once it becomes genuinely reachable.
"""


class DestinationClassification(BaseModel):
    """One theater's verdict. Frozen and minimal, by design.

    Carries no display name, owner, route row, distance or presentation text: this is an internal
    result, and a projection that needed a name can resolve it from the map it already has. Adding
    presentation here would make the classifier a second place display data is assembled.
    """

    model_config = _STRICT_FROZEN_CONFIG

    theater_id: StrictMapId
    eligible: bool
    ineligible_reason_code: DestinationIneligibilityCode | None = None

    @model_validator(mode="after")
    def _eligibility_and_reason_are_exclusive(self) -> DestinationClassification:
        """An eligible row carries no reason; an ineligible row carries exactly one.

        Enforced in the model rather than trusted at the call site, so no caller has to decide how
        to read an eligible row that also states why it is not.
        """
        if self.eligible and self.ineligible_reason_code is not None:
            raise ValueError(
                f"theater {self.theater_id!r} is eligible but carries reason "
                f"{self.ineligible_reason_code!r}"
            )
        if not self.eligible and self.ineligible_reason_code is None:
            raise ValueError(f"theater {self.theater_id!r} is ineligible but carries no reason")
        return self


def classify_destinations(
    *,
    formation: FormationState,
    player_country_id: str,
    map_state: StrategicMapState,
) -> tuple[DestinationClassification, ...]:
    """Classify EVERY theater for one formation, using the single movement-legality rule.

    Returns one row per theater in `map_state.theaters`, sorted by `theater_id`, so the output
    depends on the ids and never on mapping insertion order. Ineligible theaters are returned
    rather than filtered out: the UI has to explain why a destination is unavailable, and a caller
    cannot explain what it was never given.

    Precedence, applied in this order per theater:

      1. the destination IS the formation's current location -> `destination_is_origin`
      2. the destination is not owned by this player country  -> `destination_not_player_owned`
      3. the destination is one authored outgoing LAND route away -> ELIGIBLE
      4. otherwise                                            -> `destination_not_directly_reachable`

    **Ownership is checked before reachability, and that ordering is load-bearing.** A
    foreign-owned theater gets the ownership reason whether or not a directed route reaches it. If
    a foreign theater that merely lacked a route were reported as unreachable, the explanation
    would imply that authoring a route would authorize entry -- which is false. Foreign entry is
    excluded by product decision, not by graph topology.

    Pure: no mutation, no I/O and no randomness. There is no `rng` parameter to pass, and
    `tests/test_no_forbidden_imports.py` already forbids this module from importing `random` at
    all.
    """
    origin = formation.location_theater_id
    reachable = frozenset(land_destinations_from(origin, map_state.routes))

    rows: list[DestinationClassification] = []
    for theater_id in sorted(map_state.theaters):
        reason: DestinationIneligibilityCode | None
        if theater_id == origin:
            reason = "destination_is_origin"
        elif not _is_owned_by(map_state.theaters[theater_id].owner, player_country_id):
            reason = "destination_not_player_owned"
        elif theater_id in reachable:
            reason = None
        else:
            reason = "destination_not_directly_reachable"

        rows.append(
            DestinationClassification(
                theater_id=theater_id,
                eligible=reason is None,
                ineligible_reason_code=reason,
            )
        )

    return tuple(rows)


def _is_owned_by(owner: object, player_country_id: str) -> bool:
    """True only for a `PlayerCountryRef` naming this exact country.

    A `ForeignProfileRef` is never a match, and neither is a player ref for a different country --
    the check is on identity, not merely on the reference's kind.
    """
    return isinstance(owner, PlayerCountryRef) and owner.country_id == player_country_id
