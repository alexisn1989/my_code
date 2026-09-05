"""The single production rule for military movement legality (Military Movement, commits 4-5).

This module is PURE INSPECTION. Nothing here mutates state, writes a file or draws randomness;
it reads state and a submitted decision and returns verdicts. Application lives in `phases.py`.

Two layers, and the second is written entirely in terms of the first:

- `classify_destinations` (commit 4) reads an already-resolved `FormationState` and an authored
  `StrategicMapState` and reports, for EVERY theater, whether that formation could legally be
  ordered there.
- `movement_order_problems` (commit 5) resolves a submitted order's formation and destination and
  then asks `classify_destinations`. It re-derives no ownership or reachability rule of its own,
  so the ordering precedence in §3.4 is inherited rather than restated.

It is the SINGLE implementation of movement legality. `/api/game/preview` and the authoritative
`resolver._validate_decision_set` both call `movement_order_problems`; commit 6's
`/api/game/military` projection converts `classify_destinations`' results into displayable
options. None of the three re-derives the rule, so they cannot disagree about what is legal or
about why.

Lives in its own module rather than in `geography.py`: this needs `FormationState` and
`StrategicMapState` from `state.py`, and `geography.py` is imported BY `state.py`. Importing
`state.py` from here closes no loop -- `state.py` imports only `constitution`,
`foreign_conflict`, `geography`, `legislature` and `app.core.*`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

from pydantic import BaseModel, ConfigDict, model_validator

from app.simulation.decisions import DecisionSet, FormationMovementOrder
from app.simulation.geography import StrictMapId, land_destinations_from
from app.simulation.state import (
    FormationState,
    GameState,
    MilitaryState,
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


# --- Submission validation (commit 5) --------------------------------------

MovementSubmissionCode: TypeAlias = Literal[
    "formation_unknown",
    "destination_theater_unknown",
    "destination_is_origin",
    "destination_not_player_owned",
    "destination_not_directly_reachable",
]
"""Every state-dependent reason a submitted movement order can be rejected. Exactly five.

The first two are resolved HERE, because `classify_destinations` cannot express them: it receives
an already-resolved formation and enumerates the map's own theater keys, so neither an unknown
formation nor an unknown theater exists by the time it runs. The remaining three are
`DestinationIneligibilityCode` verbatim -- the same three strings, propagated, never re-derived.

Three codes earlier drafts listed are deliberately ABSENT. `tests/test_military_movement.py`
asserts each is a member of neither this set nor `DestinationIneligibilityCode`, so no boundary
can emit one:

- `formation_origin_unresolved` and `origin_not_player_owned` are state-integrity failures, not
  player-submission errors. Commit 3's `formation_location_unknown_theater` and
  `formation_location_not_owned_by_country` invariants already guarantee neither can occur in a
  valid state, and a stable player-facing code no valid state can produce is decoration.
- `route_kind_not_land` is unreachable while `RouteKind` has a single member; the LAND requirement
  is folded into `destination_not_directly_reachable`.
"""

MOVEMENT_SUBMISSION_CODES: frozenset[str] = frozenset(get_args(MovementSubmissionCode))
"""Derived from the type by `get_args`, never retyped as a second literal list -- a hand-written
copy could drift from the type it claims to enumerate, and this set is what the disjointness test
against the report reason-id namespace compares."""


@dataclass(frozen=True)
class MovementOrderProblem:
    """One rejected order: its stable code, the order it came from, and a player-facing sentence.

    `message` ALWAYS begins with `code` followed by ": ", the same convention as
    `geography.MAP_CONSTRUCTION_CODES`. That is not decoration -- it is what lets the two public
    boundaries surface the stable code without either of them gaining a new response field:
    `/preview` and `/resolve` both carry the message through the existing `DecisionSetError`
    envelope, and `code in body` is then a true statement about emitted behaviour rather than a
    promise made in a docstring. `_problem` builds every instance, so no call site can construct a
    problem whose message omits its own code.
    """

    code: MovementSubmissionCode
    formation_id: str
    message: str


def _problem(code: MovementSubmissionCode, formation_id: str, detail: str) -> MovementOrderProblem:
    return MovementOrderProblem(code=code, formation_id=formation_id, message=f"{code}: {detail}")


def movement_order_problems(
    state: GameState, decision_set: DecisionSet
) -> tuple[MovementOrderProblem, ...]:
    """Every reason this decision set's movement orders cannot be resolved, in submitted order.

    Returns problems; never raises, and never mutates. The two callers differ only in what they do
    with the result, which is exactly why they cannot disagree about legality or about why:

    - `/api/game/preview` explains, changing nothing;
    - `resolver._validate_decision_set` rejects, so the turn does not advance.

    Returns `()` when no movement decision was submitted -- reading no military state at all, so a
    turn with no movement behaves exactly as it did before this commit.
    """
    decision = decision_set.military_movement_decision()
    if decision is None:
        return ()

    player_country_id = state.world.player_country_id
    country = state.world.countries.get(player_country_id)
    military = None if country is None else country.military
    map_state = state.world.strategic_map

    return tuple(
        problem
        for problem in (
            _order_problem(
                order=order,
                military=military,
                player_country_id=player_country_id,
                map_state=map_state,
            )
            for order in decision.orders
        )
        if problem is not None
    )


def _order_problem(
    *,
    order: FormationMovementOrder,
    military: MilitaryState | None,
    player_country_id: str,
    map_state: StrategicMapState,
) -> MovementOrderProblem | None:
    """One order's verdict, or `None` when it is legal.

    `military` may be `None` only in a state that already fails commit 3's
    `player_military_state_required` invariant; it is handled as `formation_unknown` rather than
    raising, because this function's contract is to return problems and a crash is not a problem
    string.
    """
    formations = {} if military is None else military.formations
    formation = formations.get(order.formation_id)
    if formation is None:
        return _problem(
            "formation_unknown",
            order.formation_id,
            f"no formation {order.formation_id!r} exists in your military",
        )

    destination = order.destination_theater_id
    if destination not in map_state.theaters:
        return _problem(
            "destination_theater_unknown",
            order.formation_id,
            f"no theater {destination!r} exists on the strategic map",
        )

    classification = next(
        row
        for row in classify_destinations(
            formation=formation,
            player_country_id=player_country_id,
            map_state=map_state,
        )
        if row.theater_id == destination
    )
    if classification.eligible:
        return None

    reason = classification.ineligible_reason_code
    assert reason is not None, "DestinationClassification enforces the exclusive pair"
    return _problem(reason, order.formation_id, _INELIGIBILITY_DETAIL[reason].format(destination))


_INELIGIBILITY_DETAIL: dict[DestinationIneligibilityCode, str] = {
    "destination_is_origin": "that formation is already in {0!r}",
    "destination_not_player_owned": "{0!r} is not one of your theaters",
    "destination_not_directly_reachable": (
        "no land route leads directly from that formation's theater to {0!r}"
    ),
}
"""One sentence per ineligibility code, keyed by the code itself so a new classifier code cannot
be added without a matching sentence -- `tests/test_military_movement.py` asserts the key set
equals `DestinationIneligibilityCode`'s members."""
