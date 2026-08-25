"""Structural preflight for a drafted decision set, shared by preview and the
policy-card catalog.

Gate 4A3A found a real Gate 4A1 correctness defect: `/api/game/preview` accepted
three classes of amendment decision that `/api/game/resolve` refuses, so a
player could preview a green result and then have the turn abort. Concretely,
`preview.py`'s `_require_route_is_permitted` checked only `decree_authority is
UNLIMITED`, which misses:

  * a no-op target (`phases.py` aborts the whole turn when any target equals its
    opening value),
  * a target set whose FINAL constitution violates C1-C10, and
  * an amendment-by-decree in a country that still has a legislature.

This module is an **API-layer preflight that mirrors the resolver's structural
semantics**. It is deliberately NOT shared code with the resolver: `/resolve`
remains governed entirely by `app/simulation/phases.py` and never calls
anything here. The parity tests in `tests/test_api_preview_parity.py` are what
keep the two from drifting -- both must reject the same payload class.

It composes existing primitives (`first_constitutional_violation`, the real
enums, the real state) and copies no constitutional or vote formula.

**Affordability is deliberately absent.** A structurally valid but unaffordable
decision must PREVIEW successfully and come back with `affordable=False`,
`committed_capital` and `opening_capital` populated, so the interface can
explain the shortfall. Rejecting it here would make `PreviewProjection.affordable`
permanently `True` and the field dead. `/resolve` stays authoritative and refuses
the same decision atomically through the engine's own affordability check, which
is neither duplicated nor weakened here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    Legislature,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
)
from app.simulation.legislature import ProposalRoute
from app.simulation.state import GameState, PoliticalState


@dataclass(frozen=True)
class DecisionProblem:
    """One structural reason a decision set cannot be resolved.

    `code` is a stable identifier safe to branch on. `message` is the
    player-facing sentence. `diagnostic_code` carries the raw internal rule id
    (e.g. a C-rule name) for logs and card diagnostics, and is kept SEPARATE so
    it never leaks into player-facing text.
    """

    code: str
    message: str
    diagnostic_code: str | None = None


def _politics(state: GameState) -> PoliticalState | None:
    country = state.world.countries[state.world.player_country_id]
    return country.politics


def _seated_bloc_keys(politics: PoliticalState) -> set[tuple[str, str]]:
    legislature = politics.legislature
    if legislature is None:
        return set()
    return {(party.id, bloc.id) for party in legislature.parties for bloc in party.blocs}


def _amendment_target_problem(
    politics: PoliticalState, amendment: ConstitutionalAmendmentDecision
) -> DecisionProblem | None:
    """No-op targets and final-constitution coherence.

    Mirrors `phases.py`'s amendment resolver: every target must change
    something, and the trial constitution is built by updating ALL targets at
    once and then validated -- never one axis at a time, which is exactly what
    lets a multi-axis reform be legal where each single step is not.
    """
    opening = politics.constitution

    updates: dict[str, object] = {}
    for target in amendment.targets:
        opening_value = getattr(opening, target.axis)
        if target.value == opening_value:
            return DecisionProblem(
                code="amendment_target_changes_nothing",
                message=(
                    f"This amendment would leave {target.axis!r} exactly as it already is, "
                    "so there is nothing to enact."
                ),
            )
        updates[target.axis] = target.value

    trial_payload = opening.model_dump(mode="python")
    trial_payload.update(updates)
    violation = first_constitutional_violation(ConstitutionState.model_construct(**trial_payload))
    if violation is not None:
        code, detail = violation
        return DecisionProblem(
            code="amendment_constitution_incoherent",
            message=(
                "This change would leave the constitution internally inconsistent; "
                "it needs a companion change to another part of the constitution."
            ),
            diagnostic_code=code,
        )
    return None


def _route_problem(
    politics: PoliticalState,
    proposal: BudgetDecision | ConstitutionalAmendmentDecision,
) -> DecisionProblem | None:
    """Route legality, mirroring the two different rules `phases.py` applies.

    A budget decree needs only `decree_authority == unlimited`. An amendment
    decree additionally needs `legislature == none` AND no `LegislatureState` --
    a stricter rule the previous preview did not check at all, which is how an
    amendment-by-decree could preview green on a scenario that has a sitting
    legislature and then abort at resolve.
    """
    constitution = politics.constitution
    is_amendment = isinstance(proposal, ConstitutionalAmendmentDecision)

    if proposal.route is ProposalRoute.DECREE:
        if constitution.decree_authority is not DecreeAuthority.UNLIMITED:
            return DecisionProblem(
                code="decree_route_unavailable",
                message=(
                    "This government does not hold the decree authority needed to enact "
                    "policy without a legislative vote."
                ),
            )
        if is_amendment and (
            constitution.legislature is not Legislature.NONE or politics.legislature is not None
        ):
            return DecisionProblem(
                code="decree_cannot_amend_with_legislature",
                message=(
                    "A decree cannot amend the constitution while a legislature sits; "
                    "this reform must go to a vote."
                ),
            )
        return None

    # Legislative route.
    if constitution.legislature is Legislature.NONE or politics.legislature is None:
        return DecisionProblem(
            code="no_legislature",
            message="There is no legislature to vote on this proposal.",
        )
    return None


def first_decision_problem(state: GameState, decision_set: DecisionSet) -> DecisionProblem | None:
    """The first structural reason this decision set could not be resolved, if any.

    Returns `None` when the set is structurally resolvable. Affordability is NOT
    considered -- see this module's docstring.
    """
    politics = _politics(state)
    if politics is None:  # pragma: no cover - every shipped scenario has politics
        return DecisionProblem(
            code="no_political_state",
            message="This scenario has no political state to act on.",
        )

    budget = decision_set.budget_decision()
    amendment = decision_set.constitutional_amendment_decision()
    investment = decision_set.relationship_investment_decision()
    proposal: BudgetDecision | ConstitutionalAmendmentDecision | None = budget or amendment

    if amendment is not None:
        target_problem = _amendment_target_problem(politics, amendment)
        if target_problem is not None:
            return target_problem

    if proposal is not None:
        route_problem = _route_problem(politics, proposal)
        if route_problem is not None:
            return route_problem

    # Influence and investment must name blocs that actually exist in the
    # opening state. The engine discovers this later; naming it here means a
    # preview cannot silently score a bloc that is not there.
    known = _seated_bloc_keys(politics)
    referenced: list[tuple[str, str]] = []
    if proposal is not None:
        referenced.extend((row.party_id, row.bloc_id) for row in proposal.influence)
    if investment is not None:
        referenced.extend((row.party_id, row.bloc_id) for row in investment.investments)
    for party_id, bloc_id in referenced:
        if (party_id, bloc_id) not in known:
            return DecisionProblem(
                code="unknown_bloc_target",
                message=(
                    f"There is no bloc {bloc_id!r} in party {party_id!r} to direct "
                    "political capital toward."
                ),
            )

    return None
