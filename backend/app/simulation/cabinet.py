"""Who holds a cabinet post, and what their competence is worth this turn.

Pure reads over already-parsed state: no I/O, no randomness, no mutation, no floating point. The
module exists so that the two places which need the answer -- `phases.py`, which computes a turn,
and `reconciliation.py`, which re-derives it from a save -- ask exactly the same question of the
same state and cannot drift. A second implementation of "is this appointment effective yet?" is
precisely the kind of duplicated rule the reconciliation layer exists to catch, so there is one.

Unlike `government_survival.py`, these functions do accept state models. They are lookups across
two containers (`CabinetState.offices` and `WorldState.characters`), not formulas over metrics, and
threading a pre-flattened mapping through every caller would move the lookup rule into the callers
-- which is the drift this module prevents. `military.py` sets the same precedent.
"""

from __future__ import annotations

from app.simulation.state import (
    CabinetPost,
    CabinetState,
    CharacterState,
    StrictCharacterId,
)


def effective_holder_id(
    *, cabinet: CabinetState | None, post: CabinetPost, resolving_turn: int
) -> StrictCharacterId | None:
    """The character actually doing `post`'s job on `resolving_turn`, or `None`.

    `None` covers three genuinely different situations that all mean the same thing to a consumer
    -- no cabinet is modelled, the post is vacant, or the holder was appointed too recently to have
    started -- and deliberately does not distinguish them, because a bonus of nothing is a bonus of
    nothing. Anything that needs the difference (a UI explaining *why* there is no bonus) reads the
    cabinet directly.

    The timing rule lives here and nowhere else: a holder contributes if and only if
    `effective_from_turn <= resolving_turn`. An appointment resolved on turn `t` is stored at
    `t + 1`, so it never supplies the turn that hired it, and appointing three people to the same
    post within one turn still yields whatever the OPENING state had.
    """
    if cabinet is None:
        return None
    appointment = cabinet.offices.get(post)
    if appointment is None:
        return None
    if appointment.effective_from_turn > resolving_turn:
        return None
    return appointment.character_id


def holder_competence_bps(
    *,
    cabinet: CabinetState | None,
    characters: dict[StrictCharacterId, CharacterState],
    post: CabinetPost,
    resolving_turn: int,
) -> int:
    """`post`'s serving holder's competence on `resolving_turn`, or `0` when nobody is serving.

    `0` is the correct answer for a vacant post and for an utterly incompetent holder alike: both
    contribute nothing, and collapsing them keeps every consumer free of a special case. It is also
    what makes the office bonuses safely additive -- a government with no cabinet at all computes
    exactly the figures it computed before this layer existed.

    A holder id that is not in `characters` also yields `0` rather than raising.
    `simulation.invariants` (`cabinet_holder_unknown`) rejects that state before and after every
    resolution, so this is unreachable in a valid game; it is guarded anyway because this module is
    also read by reconciliation, which must produce a problem string for a tampered save rather
    than an exception.
    """
    holder_id = effective_holder_id(cabinet=cabinet, post=post, resolving_turn=resolving_turn)
    if holder_id is None:
        return 0
    holder = characters.get(holder_id)
    return 0 if holder is None else holder.competence
