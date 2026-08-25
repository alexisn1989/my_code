"""Gate 4A3A: the server-authored policy-card catalog.

`build_policy_cards` is the single generator behind `DecisionOptionsProjection
.policy_cards`. It turns the real legal decision space -- the same three
decision kinds `DecisionSet` accepts, the same five amendable constitutional
axes, the same route rules `/preview` and `/resolve` enforce -- into named,
understood choices, without inventing anything the engine does not already
support.

**Every card's legality is decided by re-running `first_decision_problem`**
(`decision_preflight.py`), the exact same structural preflight `/preview`
calls before scoring a draft. This module never re-derives "is this route
legal" or "is this constitution coherent" on its own: it builds a candidate
`BudgetDecision` or `ConstitutionalAmendmentDecision` with EMPTY influence,
wraps it in a throwaway `DecisionSet`, and asks the shared preflight whether
resolving it would be structurally rejected. A card or route is available iff
the preflight found no problem. This is what makes the R3 guarantee
mechanical rather than promised: `test_policy_cards.py` proves it by
re-running the SAME check over every emitted template and asserting agreement.

Two things this module deliberately does NOT decide:

* **Affordability.** Per R11, a route the player cannot currently afford is
  still a legal, selectable choice -- `/preview`'s `committed_capital` /
  `opening_capital` / `affordable` fields explain the shortfall once a card
  is chosen, not this catalog.
* **Bloc targeting.** Every template carries empty `influence`; whipping a
  vote is a bargaining action layered on top of a selected card, not part of
  the card itself.

Generic step sizes (how far one tax or spending card moves a rate or amount)
come from `policy_card_calibration.py`, not from anything authored here.
"""

from __future__ import annotations

from collections.abc import Callable

from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    ConstitutionalAxisTarget,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
    SpendingUpdate,
    TermLimitTarget,
)
from app.simulation.legislative_voting import (
    CONSTITUTIONAL_AMENDMENT_DECREE_COST,
    DECREE_POLITICAL_CAPITAL_COST,
    required_amendment_yes_seats,
    required_yes_seats,
)
from app.simulation.legislature import AmendmentThreshold, ProposalRoute
from app.simulation.state import GameState, GovernmentFinanceState, PoliticalState, SpendingCategory

from .decision_preflight import DecisionProblem, first_decision_problem
from .policy_card_calibration import TAX_STEP_BPS, spending_step
from .projections import (
    DecisionOptionsProjection,
    PolicyCard,
    PolicyCardChamberRequirement,
    PolicyCardEffect,
    PolicyCardRoute,
    PolicyCardUnavailableReason,
    build_decision_options,
)

_BPS_MIN = 0
_BPS_MAX = 10_000

#: Maps `DecisionProblem.code` (decision_preflight.py) onto the closed
#: player-facing reason set. Exhaustive over every code that module can
#: return -- deliberately indexed, not `.get`-with-a-default, so a future
#: code decision_preflight starts returning fails this module's own tests
#: loudly instead of silently being mis-mapped.
_REASON_MAP: dict[str, PolicyCardUnavailableReason] = {
    "amendment_target_changes_nothing": "no_change_from_current",
    "amendment_constitution_incoherent": "requires_companion_constitutional_change",
    "decree_route_unavailable": "route_constitutionally_unavailable",
    "decree_cannot_amend_with_legislature": "decree_cannot_amend_with_legislature",
    "no_legislature": "no_legislature",
    "unknown_bloc_target": "route_constitutionally_unavailable",
}

_GAME_CONCLUDED_DETAIL = "The campaign has already ended; no further turn can be resolved."

_EXECUTIVE_SYSTEM_LABELS: dict[ExecutiveSystem, str] = {
    ExecutiveSystem.PRESIDENTIAL: "Presidential",
    ExecutiveSystem.PARLIAMENTARY: "Parliamentary",
    ExecutiveSystem.SEMI_PRESIDENTIAL: "Semi-presidential",
    ExecutiveSystem.MONARCHICAL: "Monarchical",
}
_EXECUTIVE_SELECTION_LABELS: dict[ExecutiveSelection, str] = {
    ExecutiveSelection.DIRECT_ELECTION: "Direct election",
    ExecutiveSelection.LEGISLATIVE_SELECTION: "Selected by the legislature",
    ExecutiveSelection.HEREDITARY: "Hereditary succession",
    ExecutiveSelection.APPOINTED: "Appointed",
}
_DECREE_AUTHORITY_LABELS: dict[DecreeAuthority, str] = {
    DecreeAuthority.NONE: "No decree authority",
    DecreeAuthority.EMERGENCY_ONLY: "Emergency decree authority only",
    DecreeAuthority.UNLIMITED: "Unlimited decree authority",
}
_SPENDING_CATEGORY_LABELS: dict[SpendingCategory, str] = {
    SpendingCategory.HEALTH: "Health",
    SpendingCategory.EDUCATION: "Education",
    SpendingCategory.WELFARE: "Welfare",
    SpendingCategory.INFRASTRUCTURE: "Infrastructure",
    SpendingCategory.DEFENSE: "Defense",
    SpendingCategory.SECURITY: "Security",
    SpendingCategory.ADMINISTRATION: "Administration",
}


def _term_limit_label(terms: int | None) -> str:
    if terms is None:
        return "No term limit"
    return f"{terms} term" if terms == 1 else f"{terms} terms"


def _election_interval_label(turns: int | None) -> str:
    if turns is None:
        return "No scheduled national election"
    return f"Every {turns} turn" if turns == 1 else f"Every {turns} turns"


def _politics(state: GameState) -> PoliticalState | None:
    country = state.world.countries.get(state.world.player_country_id)
    return None if country is None else country.politics


def _decision_set(
    state: GameState, decision: BudgetDecision | ConstitutionalAmendmentDecision
) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=(decision,)
    )


def _check(
    state: GameState, decision: BudgetDecision | ConstitutionalAmendmentDecision
) -> DecisionProblem | None:
    """The one call every route legality decision in this module goes through."""
    return first_decision_problem(state, _decision_set(state, decision))


def _route_from_problem(
    *,
    route: ProposalRoute,
    decision: BudgetDecision | ConstitutionalAmendmentDecision,
    problem: DecisionProblem | None,
    base_route_cost: int,
    bargaining_available: bool,
    chambers: tuple[PolicyCardChamberRequirement, ...],
) -> PolicyCardRoute:
    if problem is None:
        return PolicyCardRoute(
            route=route,
            available=True,
            base_route_cost=base_route_cost,
            bargaining_available=bargaining_available,
            chambers=chambers,
            template=decision,
        )
    return PolicyCardRoute(
        route=route,
        available=False,
        unavailable_reason=_REASON_MAP[problem.code],
        unavailable_detail=problem.message,
        base_route_cost=base_route_cost,
        bargaining_available=bargaining_available,
        chambers=(),
        template=None,
    )


def _budget_chambers(politics: PoliticalState) -> tuple[PolicyCardChamberRequirement, ...]:
    legislature = politics.legislature
    if legislature is None:
        return ()
    return tuple(
        PolicyCardChamberRequirement(
            chamber=chamber.chamber.value,
            total_seats=chamber.total_seats,
            required_seats=required_yes_seats(total_seats=chamber.total_seats),
        )
        for chamber in legislature.chambers
    )


def _amendment_chambers(politics: PoliticalState) -> tuple[PolicyCardChamberRequirement, ...]:
    legislature = politics.legislature
    if legislature is None:
        return ()
    threshold = AmendmentThreshold(politics.constitution.amendment_difficulty.value)
    return tuple(
        PolicyCardChamberRequirement(
            chamber=chamber.chamber.value,
            total_seats=chamber.total_seats,
            required_seats=required_amendment_yes_seats(
                total_seats=chamber.total_seats, difficulty=threshold
            ),
        )
        for chamber in legislature.chambers
    )


def _budget_routes(
    state: GameState, politics: PoliticalState, budget: BudgetDecision
) -> tuple[PolicyCardRoute, ...]:
    bargaining_available = politics.legislature is not None
    chambers = _budget_chambers(politics)

    legislative = budget.model_copy(update={"route": ProposalRoute.LEGISLATIVE})
    decree = budget.model_copy(update={"route": ProposalRoute.DECREE})
    return (
        _route_from_problem(
            route=ProposalRoute.LEGISLATIVE,
            decision=legislative,
            problem=_check(state, legislative),
            base_route_cost=0,
            bargaining_available=bargaining_available,
            chambers=chambers,
        ),
        _route_from_problem(
            route=ProposalRoute.DECREE,
            decision=decree,
            problem=_check(state, decree),
            base_route_cost=DECREE_POLITICAL_CAPITAL_COST,
            bargaining_available=False,
            chambers=(),
        ),
    )


def _amendment_routes(
    state: GameState, politics: PoliticalState, amendment: ConstitutionalAmendmentDecision
) -> tuple[PolicyCardRoute, ...]:
    bargaining_available = politics.legislature is not None
    chambers = _amendment_chambers(politics)

    legislative = amendment.model_copy(update={"route": ProposalRoute.LEGISLATIVE})
    decree = amendment.model_copy(update={"route": ProposalRoute.DECREE})
    return (
        _route_from_problem(
            route=ProposalRoute.LEGISLATIVE,
            decision=legislative,
            problem=_check(state, legislative),
            base_route_cost=0,
            bargaining_available=bargaining_available,
            chambers=chambers,
        ),
        _route_from_problem(
            route=ProposalRoute.DECREE,
            decision=decree,
            problem=_check(state, decree),
            base_route_cost=CONSTITUTIONAL_AMENDMENT_DECREE_COST,
            bargaining_available=False,
            chambers=(),
        ),
    )


def _proposal_card(
    *,
    card_id: str,
    category: str,
    category_label: str,
    title: str,
    description: str,
    effects: tuple[PolicyCardEffect, ...],
    routes: tuple[PolicyCardRoute, ...],
) -> PolicyCard:
    """Assemble a proposal card whose availability is whatever its routes say --
    the mechanical consequence of `PolicyCard`'s own rule 4 validator, never
    decided a second time here."""
    available = any(route.available for route in routes)
    if available:
        return PolicyCard(
            card_id=card_id,
            category=category,  # type: ignore[arg-type]
            category_label=category_label,
            title=title,
            description=description,
            available=True,
            effects=effects,
            routes=routes,
        )
    # Every unavailable route agrees on why (both routes are checked against
    # the SAME target-level problem first; they can only disagree once past
    # it, and past it means at least one is available). Use the first
    # unavailable route's reason as the card's own.
    first_unavailable = next(route for route in routes if not route.available)
    return PolicyCard(
        card_id=card_id,
        category=category,  # type: ignore[arg-type]
        category_label=category_label,
        title=title,
        description=description,
        available=False,
        unavailable_reason=first_unavailable.unavailable_reason,
        unavailable_detail=first_unavailable.unavailable_detail,
        effects=effects,
        routes=routes,
    )


def _out_of_bounds_card(
    *,
    card_id: str,
    category: str,
    category_label: str,
    title: str,
    description: str,
    effects: tuple[PolicyCardEffect, ...],
    detail: str,
    reason: PolicyCardUnavailableReason,
) -> PolicyCard:
    """A card whose target fails a construction-time bound (StrictBps range,
    or a zero spending baseline) before `first_decision_problem` is ever
    reachable -- there is no legal template to check either route against."""
    return PolicyCard(
        card_id=card_id,
        category=category,  # type: ignore[arg-type]
        category_label=category_label,
        title=title,
        description=description,
        available=False,
        unavailable_reason=reason,
        unavailable_detail=detail,
        effects=effects,
        routes=(),
    )


# --------------------------------------------------------------------------
# Taxation cards
# --------------------------------------------------------------------------

_TAX_AXES: tuple[
    tuple[str, str, Callable[[GovernmentFinanceState], int], Callable[[int], BudgetDecision]], ...
] = (
    (
        "personal_income",
        "Personal income tax",
        lambda finance: int(finance.tax_policy.personal_income_rate_bps),
        lambda value: BudgetDecision(personal_income_rate_bps=value),
    ),
    (
        "corporate",
        "Corporate tax",
        lambda finance: int(finance.tax_policy.corporate_rate_bps),
        lambda value: BudgetDecision(corporate_rate_bps=value),
    ),
    (
        "consumption",
        "Consumption tax",
        lambda finance: int(finance.tax_policy.consumption_rate_bps),
        lambda value: BudgetDecision(consumption_rate_bps=value),
    ),
)


def _taxation_cards(
    state: GameState, politics: PoliticalState, finance: GovernmentFinanceState
) -> tuple[PolicyCard, ...]:
    cards: list[PolicyCard] = []
    for slug, label, get_current, build in _TAX_AXES:
        current = get_current(finance)
        for direction_word, sign in (("Raise", 1), ("Lower", -1)):
            proposed = current + sign * TAX_STEP_BPS
            card_id = f"tax_{slug}_{'increase' if sign > 0 else 'decrease'}"
            effects = (
                PolicyCardEffect(
                    label=label,
                    unit="bps",
                    current_value=current,
                    proposed_value=proposed,
                    direction="up" if sign > 0 else "down",
                ),
            )
            if not (_BPS_MIN <= proposed <= _BPS_MAX):
                cards.append(
                    _out_of_bounds_card(
                        card_id=card_id,
                        category="taxation",
                        category_label="Taxation",
                        title=f"{direction_word} the {label.lower()}",
                        description=f"{direction_word} the {label.lower()} rate.",
                        effects=effects,
                        detail=(
                            f"{direction_word}ing the {label.lower()} by this step would leave "
                            "the legal 0%-100% range."
                        ),
                        reason="outside_legal_bounds",
                    )
                )
                continue
            budget = build(proposed)
            routes = _budget_routes(state, politics, budget)
            cards.append(
                _proposal_card(
                    card_id=card_id,
                    category="taxation",
                    category_label="Taxation",
                    title=f"{direction_word} the {label.lower()}",
                    description=f"{direction_word} the {label.lower()} rate.",
                    effects=effects,
                    routes=routes,
                )
            )
    return tuple(cards)


# --------------------------------------------------------------------------
# Spending cards
# --------------------------------------------------------------------------


def _spending_cards(
    state: GameState, politics: PoliticalState, finance: GovernmentFinanceState
) -> tuple[PolicyCard, ...]:
    cards: list[PolicyCard] = []
    plan = finance.spending_plan
    for category in SpendingCategory:
        current = plan.get(category)
        label = _SPENDING_CATEGORY_LABELS[category]
        step = spending_step(current)
        for direction_word, sign in (("Increase", 1), ("Reduce", -1)):
            card_id = f"spending_{category.value}_{'increase' if sign > 0 else 'decrease'}"
            proposed = current + sign * step
            effects = (
                PolicyCardEffect(
                    label=label,
                    unit="money",
                    current_value=current,
                    proposed_value=proposed if step > 0 else current,
                    direction=("up" if sign > 0 else "down") if step > 0 else "unchanged",
                ),
            )
            if step == 0:
                cards.append(
                    _out_of_bounds_card(
                        card_id=card_id,
                        category="spending",
                        category_label="Spending",
                        title=f"{direction_word} {label.lower()} spending",
                        description=f"{direction_word} the {label.lower()} spending category.",
                        effects=effects,
                        detail=f"There is no current {label.lower()} spending to scale from.",
                        reason="no_baseline_to_scale",
                    )
                )
                continue
            budget = BudgetDecision(
                spending_updates=(SpendingUpdate(category=category, amount=proposed),)
            )
            routes = _budget_routes(state, politics, budget)
            cards.append(
                _proposal_card(
                    card_id=card_id,
                    category="spending",
                    category_label="Spending",
                    title=f"{direction_word} {label.lower()} spending",
                    description=f"{direction_word} the {label.lower()} spending category.",
                    effects=effects,
                    routes=routes,
                )
            )
    return tuple(cards)


# --------------------------------------------------------------------------
# Constitutional cards
# --------------------------------------------------------------------------


def _amendment_diagnostic(
    politics: PoliticalState, targets: tuple[ConstitutionalAxisTarget, ...]
) -> str | None:
    opening = politics.constitution
    updates: dict[str, object] = {target.axis: target.value for target in targets}
    trial_payload = opening.model_dump(mode="python")
    trial_payload.update(updates)
    violation = first_constitutional_violation(ConstitutionState.model_construct(**trial_payload))
    return None if violation is None else violation[0]


def _amendment_card(
    state: GameState,
    politics: PoliticalState,
    *,
    card_id: str,
    title: str,
    description: str,
    effects: tuple[PolicyCardEffect, ...],
    targets: tuple[ConstitutionalAxisTarget, ...],
) -> PolicyCard:
    amendment = ConstitutionalAmendmentDecision(targets=targets)
    routes = _amendment_routes(state, politics, amendment)
    card = _proposal_card(
        card_id=card_id,
        category="constitution",
        category_label="Constitutional reform",
        title=title,
        description=description,
        effects=effects,
        routes=routes,
    )
    if card.available or card.unavailable_reason != "requires_companion_constitutional_change":
        # A no-op target, a decree-route problem, or a missing legislature are
        # not constitutional coherence violations -- there is no C-rule to
        # attach, and computing one anyway would attach a misleading code
        # from an unrelated trial (`_amendment_diagnostic` only makes sense
        # when the ACTUAL rejection was `amendment_constitution_incoherent`).
        return card
    # A blocked amendment target's diagnostic code (the real internal rule
    # id) is carried on the card, separate from the player-facing detail, so
    # a "companion change required" explanation can eventually point at what
    # rule is blocking it without ever printing that rule's raw name.
    diagnostic = _amendment_diagnostic(politics, targets)
    return card.model_copy(update={"diagnostic_code": diagnostic})


def _decree_authority_cards(state: GameState, politics: PoliticalState) -> tuple[PolicyCard, ...]:
    current = politics.constitution.decree_authority
    cards: list[PolicyCard] = []
    for value in DecreeAuthority:
        if value is current:
            continue
        effects = (
            PolicyCardEffect(
                label="Decree authority",
                unit="enum",
                current_label=_DECREE_AUTHORITY_LABELS[current],
                proposed_label=_DECREE_AUTHORITY_LABELS[value],
                direction="unchanged",
            ),
        )
        cards.append(
            _amendment_card(
                state,
                politics,
                card_id=f"constitution_decree_authority_to_{value.value}",
                title=f"Set decree authority to {_DECREE_AUTHORITY_LABELS[value].lower()}",
                description="Change the executive's authority to legislate by decree.",
                effects=effects,
                targets=(DecreeAuthorityTarget(value=value),),
            )
        )
    return tuple(cards)


def _government_form_cards(state: GameState, politics: PoliticalState) -> tuple[PolicyCard, ...]:
    current_system = politics.constitution.executive_system
    current_selection = politics.constitution.executive_selection
    cards: list[PolicyCard] = []
    for system in ExecutiveSystem:
        for selection in ExecutiveSelection:
            if system is current_system and selection is current_selection:
                continue
            effects = (
                PolicyCardEffect(
                    label="Executive system",
                    unit="enum",
                    current_label=_EXECUTIVE_SYSTEM_LABELS[current_system],
                    proposed_label=_EXECUTIVE_SYSTEM_LABELS[system],
                    direction="unchanged",
                ),
                PolicyCardEffect(
                    label="Executive selection",
                    unit="enum",
                    current_label=_EXECUTIVE_SELECTION_LABELS[current_selection],
                    proposed_label=_EXECUTIVE_SELECTION_LABELS[selection],
                    direction="unchanged",
                ),
            )
            cards.append(
                _amendment_card(
                    state,
                    politics,
                    card_id=f"constitution_government_form_{system.value}_{selection.value}",
                    title=(
                        f"Reform to {_EXECUTIVE_SYSTEM_LABELS[system].lower()}, "
                        f"{_EXECUTIVE_SELECTION_LABELS[selection].lower()}"
                    ),
                    description=(
                        "Change the executive's system of government and how it is selected."
                    ),
                    effects=effects,
                    # A no-op target aborts the whole amendment (mirrors
                    # phases.py:542), so an axis that already equals its
                    # current value must be OMITTED here, not submitted
                    # alongside the axis that does change -- even though
                    # `effects` above still shows both axes for context.
                    targets=tuple(
                        target
                        for target in (
                            ExecutiveSelectionTarget(value=selection)
                            if selection is not current_selection
                            else None,
                            ExecutiveSystemTarget(value=system)
                            if system is not current_system
                            else None,
                        )
                        if target is not None
                    ),
                )
            )
    return tuple(cards)


_TERM_LIMIT_PRESETS: tuple[int | None, ...] = (None, 1, 2, 3)
_ELECTION_INTERVAL_PRESETS: tuple[int | None, ...] = (None, 4, 8, 16)


def _term_limit_cards(state: GameState, politics: PoliticalState) -> tuple[PolicyCard, ...]:
    current = politics.constitution.executive_term_limit_terms
    cards: list[PolicyCard] = []
    for preset in _TERM_LIMIT_PRESETS:
        if preset == current:
            continue
        effects = (
            PolicyCardEffect(
                label="Executive term limit",
                unit="terms",
                current_value=current,
                proposed_value=preset,
                current_label=_term_limit_label(current),
                proposed_label=_term_limit_label(preset),
                direction="unchanged",
            ),
        )
        slug = str(preset) if preset is not None else "none"
        cards.append(
            _amendment_card(
                state,
                politics,
                card_id=f"constitution_term_limit_to_{slug}",
                title=f"Set the executive term limit to {_term_limit_label(preset).lower()}",
                description="Change how many terms the executive may serve.",
                effects=effects,
                targets=(TermLimitTarget(value=preset),),
            )
        )
    return tuple(cards)


def _election_interval_cards(state: GameState, politics: PoliticalState) -> tuple[PolicyCard, ...]:
    current = politics.constitution.national_election_interval_turns
    cards: list[PolicyCard] = []
    for preset in _ELECTION_INTERVAL_PRESETS:
        if preset == current:
            continue
        effects = (
            PolicyCardEffect(
                label="National election schedule",
                unit="turns",
                current_value=current,
                proposed_value=preset,
                current_label=_election_interval_label(current),
                proposed_label=_election_interval_label(preset),
                direction="unchanged",
            ),
        )
        slug = str(preset) if preset is not None else "none"
        cards.append(
            _amendment_card(
                state,
                politics,
                card_id=f"constitution_election_interval_to_{slug}",
                title=(
                    "Set the national election schedule to "
                    f"{_election_interval_label(preset).lower()}"
                ),
                description="Change how often a national election is constitutionally required.",
                effects=effects,
                targets=(ElectionIntervalTarget(value=preset),),
            )
        )
    return tuple(cards)


# --------------------------------------------------------------------------
# The no-proposal card
# --------------------------------------------------------------------------


def _no_proposal_card() -> PolicyCard:
    return PolicyCard(
        card_id="no_proposal",
        category="restraint",
        category_label="Take no major action",
        title="Take no major policy action",
        description=(
            "Submit no budget or constitutional proposal this turn. Automatic economic and "
            "political processes still advance."
        ),
        available=True,
        clears_proposal_slot=True,
    )


# --------------------------------------------------------------------------
# Terminal state
# --------------------------------------------------------------------------


def _disable_for_game_concluded(card: PolicyCard) -> PolicyCard:
    return card.model_copy(
        update={
            "available": False,
            "unavailable_reason": "game_concluded",
            "unavailable_detail": _GAME_CONCLUDED_DETAIL,
            "diagnostic_code": None,
            "routes": (),
        }
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_policy_cards(state: GameState) -> tuple[PolicyCard, ...]:
    """The full catalog for the CURRENT player country and state.

    Canonical order: taxation, then spending, then constitution (decree
    authority, government form, term limit, election interval, each in that
    family's own generation order), then the single restraint card -- stable
    across calls against the same state (`test_policy_cards.py` pins it
    directly).
    """
    politics = _politics(state)
    if politics is None:
        return ()

    finance = state.world.countries[state.world.player_country_id].finance
    cards: list[PolicyCard] = []
    if finance is not None:
        cards.extend(_taxation_cards(state, politics, finance))
        cards.extend(_spending_cards(state, politics, finance))
    cards.extend(_decree_authority_cards(state, politics))
    cards.extend(_government_form_cards(state, politics))
    cards.extend(_term_limit_cards(state, politics))
    cards.extend(_election_interval_cards(state, politics))
    cards.append(_no_proposal_card())

    if politics.terminal_outcome is not None:
        cards = [_disable_for_game_concluded(card) for card in cards]

    ids = [card.card_id for card in cards]
    assert len(ids) == len(set(ids)), f"duplicate policy card ids: {ids}"
    return tuple(cards)


def build_decision_options_with_policy_cards(state: GameState) -> DecisionOptionsProjection:
    """`build_decision_options` plus its `policy_cards` field, in one call.

    Lives here rather than in `projections.py` to avoid a circular import:
    this module already imports the card model classes FROM `projections.py`,
    so `projections.py` cannot import this module back. The route handler
    calls this wrapper instead of `build_decision_options` directly; nothing
    else changes about what `build_decision_options` itself computes.
    """
    options = build_decision_options(state)
    return options.model_copy(update={"policy_cards": build_policy_cards(state)})
