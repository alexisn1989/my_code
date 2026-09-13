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

from app.simulation.cabinet import (
    CabinetRefusal,
    appointment_refusal,
    effective_holder_id,
    is_domestic_to,
)
from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    Legislature,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BudgetDecision,
    CabinetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
)
from app.simulation.legislature import GovernmentRole, ProposalRoute
from app.simulation.state import CabinetPost, GameState, PoliticalState


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


def _cabinet_problem(state: GameState, decision: CabinetDecision) -> DecisionProblem | None:
    """Mirrors `phases._resolve_cabinet_orders`' rejection order exactly, so a draft that previews
    green cannot be refused at resolve -- and a draft that previews red names the same reason the
    resolver would.

    Per-order problems come first, in canonical post order, then the whole-RESULT duplicate check.
    That ordering is what lets a same-turn transfer preview correctly: only the assembled result
    knows whether anybody ends up holding two posts, so judging orders pairwise would refuse a
    legal move.

    Affordability is deliberately absent, matching this module's documented exclusion: it is a
    property of the whole decision set's total, which `/preview` reports through `affordable` and
    the capital terms beside it.
    """
    player = state.world.countries[state.world.player_country_id]
    politics = player.politics
    if politics is None:  # pragma: no cover - guarded by the caller
        return None
    cabinet = player.cabinet
    if cabinet is None:
        return DecisionProblem(
            code="cabinet_not_modelled",
            message="This country has no cabinet to staff.",
        )

    # Holder IDS only, not appointments: this function judges who ends up where, and the
    # effectivity turn is the resolver's business. Keeping the value type simple is what makes the
    # duplicate-occupancy check below a plain comparison.
    closing: dict[CabinetPost, str] = {
        post: appointment.character_id for post, appointment in cabinet.offices.items()
    }
    for order in decision.orders:
        incumbent = effective_holder_id(cabinet=cabinet, post=order.post, resolving_turn=state.turn)
        label = order.post.value.replace("_", " ")
        if order.character_id is None:
            if incumbent is None:
                return DecisionProblem(
                    code="cabinet_dismissal_of_a_vacant_post",
                    message=f"The post of {label} is already vacant.",
                )
            del closing[order.post]
            continue

        character = state.world.characters.get(order.character_id)
        if character is None:
            return DecisionProblem(
                code="cabinet_character_unknown",
                message="There is no such person to appoint.",
            )
        if not is_domestic_to(character=character, country_id=player.id):
            return DecisionProblem(
                code="cabinet_character_not_domestic",
                message=(
                    f"{character.display_name} is not one of this country's own people, and a "
                    "government may only appoint its own."
                ),
            )
        if incumbent == order.character_id:
            return DecisionProblem(
                code="cabinet_post_already_held_by_this_character",
                message=f"{character.display_name} already holds the post of {label}.",
            )
        refusal = appointment_refusal(
            character=character, post=order.post, legitimacy_bps=politics.legitimacy_bps
        )
        if refusal is CabinetRefusal.LEADS_A_PARTY:
            return DecisionProblem(
                code=refusal.value,
                message=(
                    f"{character.display_name} leads a party, and a party leader does not take a "
                    "cabinet post."
                ),
            )
        if refusal is CabinetRefusal.LOW_LEGITIMACY:
            return DecisionProblem(
                code=refusal.value,
                message=(
                    f"{character.display_name} will not serve a government with this little "
                    "legitimacy."
                ),
            )
        if refusal is CabinetRefusal.THIS_POST:
            return DecisionProblem(
                code=refusal.value,
                message=f"{character.display_name} considers {label} beneath them.",
            )
        closing[order.post] = order.character_id

    seated: dict[str, str] = {}
    for post in sorted(closing, key=lambda p: p.value):
        holder_id = closing[post]
        first = seated.get(holder_id)
        if first is not None:
            return DecisionProblem(
                code="cabinet_character_would_hold_two_posts",
                message=(
                    "This would put one person in two cabinet posts at once. To move somebody "
                    "between posts, order the post they are leaving in the same decision."
                ),
            )
        seated[holder_id] = post.value
    return None


def _legislative_bargain_problem(
    state: GameState, decision_set: DecisionSet
) -> DecisionProblem | None:
    """The preflight mirror of slot 1's six legislative-bargain rejections, in the same precedence.

    Codes and order are identical to `phases._resolve_legislative_bargain` so a draft cannot preview
    green and then be refused; `tests/test_legislative_bargain.py` asserts both name the same
    literal for the same payload rather than trusting this comment.

    **A refusal is not here.** A structurally valid leader who will not deal previews and resolves
    normally, commits nothing, and produces a report row saying so. Making it a preflight problem
    would present a temporary state -- the gate reads `personal_trust`, which a later slice moves --
    as a permanent structural error, and would leave `decree_state`, which has no acceptable
    counterparty at all, showing a validation failure instead of a political answer.
    """
    decision = decision_set.legislative_bargain_decision()
    if decision is None:
        return None
    politics = _politics(state)
    player = state.world.countries[state.world.player_country_id]

    character = state.world.characters.get(decision.character_id)
    if character is None:
        return DecisionProblem(
            code="legislative_bargain_character_unknown",
            message="There is no such person to bargain with.",
        )
    if not is_domestic_to(character=character, country_id=player.id):
        return DecisionProblem(
            code="legislative_bargain_character_not_domestic",
            message=(
                f"{character.display_name} is not one of this country's own people, and leads no "
                "party in its legislature."
            ),
        )
    if character.party_id is None:
        return DecisionProblem(
            code="legislative_bargain_character_leads_no_party",
            message=f"{character.display_name} leads no party, and so has no support to offer.",
        )
    legislature = None if politics is None else politics.legislature
    party = (
        next((p for p in legislature.parties if p.id == character.party_id), None)
        if legislature is not None
        else None
    )
    if party is None:
        return DecisionProblem(
            code="legislative_bargain_party_not_in_legislature",
            message=(
                f"{character.display_name}'s party holds no seats in this legislature, so its "
                "backing would change no vote."
            ),
        )
    if party.government_role is GovernmentRole.COALITION:
        return DecisionProblem(
            code="legislative_bargain_party_is_in_government",
            message=(f"{party.name} is already in government, so it has no endorsement to sell."),
        )
    if decision.proposal_kind not in {d.kind for d in decision_set.decisions}:
        return DecisionProblem(
            code="legislative_bargain_proposal_absent",
            message="There is no such proposal in this turn for that support to apply to.",
        )
    return None


def _foreign_assistance_problem(
    state: GameState, decision_set: DecisionSet
) -> DecisionProblem | None:
    """The preflight mirror of slot 1's three assistance rejections, in the same precedence.

    **A refusal is not here.** A hostile counterpart and an exhausted pool are resolved OUTCOMES:
    they resolve the turn normally, move no money, and produce a report row saying which it was.
    Both `standing_bps` and the pool move over a campaign, so neither is a permanent structural
    fact, and making either a preflight error would present a temporary state as a broken request.
    """
    decision = decision_set.foreign_assistance_decision()
    if decision is None:
        return None
    world = state.world
    profile = world.foreign_profiles.get(decision.profile_id)
    if profile is None:
        return DecisionProblem(
            code="foreign_assistance_profile_unknown",
            message="There is no such foreign counterpart to ask.",
        )
    if profile.assistance_capacity <= 0:
        return DecisionProblem(
            code="foreign_assistance_profile_offers_none",
            message=f"{profile.display_name} has no assistance to offer at all.",
        )
    if decision.profile_id not in world.foreign_relationships:
        return DecisionProblem(
            code="foreign_assistance_no_relationship",
            message=(
                f"This country has no dealings with {profile.display_name} through which to ask."
            ),
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
    cabinet = decision_set.cabinet_decision()
    proposal: BudgetDecision | ConstitutionalAmendmentDecision | None = budget or amendment

    if cabinet is not None:
        cabinet_problem = _cabinet_problem(state, cabinet)
        if cabinet_problem is not None:
            return cabinet_problem

    bargain_problem = _legislative_bargain_problem(state, decision_set)
    if bargain_problem is not None:
        return bargain_problem

    assistance_problem = _foreign_assistance_problem(state, decision_set)
    if assistance_problem is not None:
        return assistance_problem

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
