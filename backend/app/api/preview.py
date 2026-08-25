"""Deterministic preview: what the legislature would do with this draft.

Preview exists so the 67-of-100 moment is *decidable* rather than a coin flip.
It is composed from the engine's own primitives, in the same order `phases.py`
composes them, because no single high-level "score this vote" function exists to
call -- `phases.py:953-1042` (legislative) and `620-672` (amendment) build the
tally inline, mixed with report construction. Preview therefore repeats the
CALLS, never the formulas: every number comes out of `resolve_bloc_support`,
`resolve_amendment_support`, `apportion_supporting_seats`, `required_yes_seats`,
`required_amendment_yes_seats` and `chamber_carries` exactly as resolution does.
`test_api_preview_parity.py` is the safety net: preview and real resolution must
agree field-for-field on every deterministic quantity.

Three properties this module holds to, each tested:

  * **It mutates nothing.** No `GameSave`, `GameState`, report, session field or
    history entry is touched, and no file is written. It works from one captured
    immutable save reference handed in by the caller.
  * **It consumes no RNG.** `derive_rng` is never reached, so the seeded
    channels -- election swing, coup, unrest, impeachment -- are never previewed.
    Their uncertainty is the game, and a preview that leaked it would spoil it.
  * **It is an estimate, and says so.** The projection carries `estimate=True`
    and names the channels it deliberately excludes. Preview never presents
    itself as an authoritative resolved outcome.

Two imports deserve explicit justification. `_compute_proposed_tax_policy` and
`_compute_proposed_spending_plan` are private to `phases.py`, and importing them
is deliberately preferred over reimplementing what they do: reimplementation
would be exactly the formula duplication this design exists to avoid. Nothing in
`app/simulation/` is modified to make this possible.
"""

from __future__ import annotations

from app.core.errors import DecisionSetError
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.decisions import (
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
)
from app.simulation.legislative_voting import (
    CONSTITUTIONAL_AMENDMENT_DECREE_COST,
    DECREE_POLITICAL_CAPITAL_COST,
    chamber_carries,
    required_amendment_yes_seats,
    required_yes_seats,
    resolve_amendment_support,
    resolve_bloc_support,
    spending_policy_change,
    tax_policy_change,
)
from app.simulation.legislature import AmendmentThreshold, ProposalRoute
from app.simulation.phases import (
    _compute_proposed_spending_plan,
    _compute_proposed_tax_policy,
)
from app.simulation.state import GameState, LegislatureState, PoliticalState

from .decision_preflight import first_decision_problem
from .projections import ChamberPreview, PreviewProjection

#: Named once so the projection can say what it deliberately does not know.
EXCLUDED_STOCHASTIC_CHANNELS = (
    "election polling swing",
    "coup attempt and outcome",
    "popular unrest",
    "impeachment",
)


def _politics(state: GameState) -> PoliticalState:
    country = state.world.countries[state.world.player_country_id]
    politics = country.politics
    if politics is None:  # pragma: no cover - every shipped scenario has politics
        raise DecisionSetError("this scenario has no political state to preview")
    return politics


def _route_cost(decision: BudgetDecision | ConstitutionalAmendmentDecision) -> int:
    """The flat commitment a decree route costs, or 0 for a legislative vote."""
    if decision.route is not ProposalRoute.DECREE:
        return 0
    return (
        CONSTITUTIONAL_AMENDMENT_DECREE_COST
        if isinstance(decision, ConstitutionalAmendmentDecision)
        else DECREE_POLITICAL_CAPITAL_COST
    )


def _require_no_structural_problem(state: GameState, decision_set: DecisionSet) -> None:
    """Reject a decision `/resolve` would also reject, before scoring it.

    Delegates to the shared `first_decision_problem` preflight (Gate 4A3A) so
    `/preview` and `/resolve` agree on no-op targets, constitutional coherence,
    and route legality -- not just the single decree-availability check this
    function used to make on its own. Affordability is deliberately NOT part of
    this check; see `decision_preflight`'s own docstring.
    """
    problem = first_decision_problem(state, decision_set)
    if problem is not None:
        raise DecisionSetError(problem.message)


def _seated_blocs(
    legislature: LegislatureState, chamber: object
) -> list[tuple[str, str, int, object, object]]:
    """(party_id, bloc_id, seats, party, bloc) for blocs seated in this chamber."""
    rows: list[tuple[str, str, int, object, object]] = []
    for party in legislature.parties:
        for bloc in party.blocs:
            seats = next((entry.seats for entry in bloc.seats if entry.chamber == chamber), 0)
            if seats == 0:
                continue
            rows.append((party.id, bloc.id, seats, party, bloc))
    return rows


def preview_decisions(state: GameState, decision_set: DecisionSet) -> PreviewProjection:
    """Score the drafted proposal against the CAPTURED opening state.

    The caller passes one immutable state read once at request start, so preview
    observes either the complete pre-mutation state or the complete
    post-mutation state -- never a mixture of the two.
    """
    politics = _politics(state)
    country = state.world.countries[state.world.player_country_id]
    finance = country.finance

    budget = decision_set.budget_decision()
    amendment = decision_set.constitutional_amendment_decision()
    investment = decision_set.relationship_investment_decision()

    proposal: BudgetDecision | ConstitutionalAmendmentDecision | None = budget or amendment
    _require_no_structural_problem(state, decision_set)

    chambers: tuple[ChamberPreview, ...] = ()
    legislature = politics.legislature
    if proposal is not None and legislature is not None:
        chambers = (
            _preview_amendment(politics, legislature, amendment)
            if amendment is not None
            else _preview_budget(politics, legislature, budget, finance)
        )

    # Affordability is a sum-and-compare of submitted quantities against opening
    # capital -- the same three components `phases.py:1103` adds -- not a
    # simulation formula. The verdict is server-side so the client never has to
    # decide legality for itself.
    route_cost = _route_cost(proposal) if proposal is not None else 0
    influence_total = sum(row.political_capital for row in proposal.influence) if proposal else 0
    investment_total = (
        sum(row.political_capital for row in investment.investments) if investment else 0
    )
    committed = route_cost + influence_total + investment_total
    opening_capital = politics.political_capital

    return PreviewProjection(
        estimate=True,
        excludes_stochastic_channels=EXCLUDED_STOCHASTIC_CHANNELS,
        chambers=chambers,
        would_pass=bool(chambers) and all(row.carries for row in chambers),
        has_proposal=proposal is not None,
        route=None if proposal is None else proposal.route.value,
        route_capital_cost=route_cost,
        influence_capital=influence_total,
        investment_capital=investment_total,
        committed_capital=committed,
        opening_capital=opening_capital,
        affordable=committed <= opening_capital,
    )


def _preview_budget(
    politics: PoliticalState,
    legislature: LegislatureState,
    budget: BudgetDecision | None,
    finance: object,
) -> tuple[ChamberPreview, ...]:
    """The legislative tally, composed exactly as `phases.py:953-1042` composes it."""
    if budget is None or finance is None:
        return ()

    opening_tax = finance.tax_policy  # type: ignore[attr-defined]
    opening_spending = finance.spending_plan  # type: ignore[attr-defined]
    proposed_spending = _compute_proposed_spending_plan(opening=opening_spending, decision=budget)
    _compute_proposed_tax_policy(opening=opening_tax, decision=budget)

    rate_changes = tuple(
        (getattr(opening_tax, field_name), target_value)
        for field_name, target_value in (
            ("personal_income_rate_bps", budget.personal_income_rate_bps),
            ("corporate_rate_bps", budget.corporate_rate_bps),
            ("consumption_rate_bps", budget.consumption_rate_bps),
        )
        if target_value is not None
    )
    tax_change = tax_policy_change(rate_changes=rate_changes)
    spending_change = spending_policy_change(
        opening_total=opening_spending.total(), proposed_total=proposed_spending.total()
    )
    allocation_by_key = {
        (row.party_id, row.bloc_id): row.political_capital for row in budget.influence
    }

    previews: list[ChamberPreview] = []
    for chamber_state in legislature.chambers:
        supports: list[SeatSupport] = []
        for party_id, bloc_id, seats, party, bloc in _seated_blocs(
            legislature, chamber_state.chamber
        ):
            support = resolve_bloc_support(
                role=party.government_role,  # type: ignore[attr-defined]
                relationship_bps=bloc.government_relationship_bps,  # type: ignore[attr-defined]
                tax_change=tax_change,
                tax_preference_bps=bloc.tax_preference_bps,  # type: ignore[attr-defined]
                spending_change=spending_change,
                spending_preference_bps=bloc.spending_preference_bps,  # type: ignore[attr-defined]
                allocated_political_capital=allocation_by_key.get((party_id, bloc_id), 0),
                discipline_bps=bloc.discipline_bps,  # type: ignore[attr-defined]
            )
            supports.append(
                SeatSupport(
                    party_id=party_id,
                    bloc_id=bloc_id,
                    seats=seats,
                    effective_support_bps=support.effective_support_bps,
                )
            )
        apportionment = apportion_supporting_seats(rows=tuple(supports))
        required = required_yes_seats(total_seats=chamber_state.total_seats)
        previews.append(
            ChamberPreview(
                chamber=chamber_state.chamber.value,
                total_seats=chamber_state.total_seats,
                supporting_seats=apportionment.supporting_seats,
                required_seats=required,
                carries=chamber_carries(
                    supporting_seats=apportionment.supporting_seats,
                    total_seats=chamber_state.total_seats,
                ),
            )
        )
    return tuple(previews)


def _preview_amendment(
    politics: PoliticalState,
    legislature: LegislatureState,
    amendment: ConstitutionalAmendmentDecision,
) -> tuple[ChamberPreview, ...]:
    """The amendment tally, composed exactly as `phases.py:620-672` composes it."""
    threshold = AmendmentThreshold(politics.constitution.amendment_difficulty.value)
    allocation_by_key = {
        (row.party_id, row.bloc_id): row.political_capital for row in amendment.influence
    }

    previews: list[ChamberPreview] = []
    for chamber_state in legislature.chambers:
        supports: list[SeatSupport] = []
        for party_id, bloc_id, seats, party, bloc in _seated_blocs(
            legislature, chamber_state.chamber
        ):
            support = resolve_amendment_support(
                role=party.government_role,  # type: ignore[attr-defined]
                relationship_bps=bloc.government_relationship_bps,  # type: ignore[attr-defined]
                discipline_bps=bloc.discipline_bps,  # type: ignore[attr-defined]
                allocated_political_capital=allocation_by_key.get((party_id, bloc_id), 0),
            )
            supports.append(
                SeatSupport(
                    party_id=party_id,
                    bloc_id=bloc_id,
                    seats=seats,
                    effective_support_bps=support.effective_support_bps,
                )
            )
        apportionment = apportion_supporting_seats(rows=tuple(supports))
        required = required_amendment_yes_seats(
            total_seats=chamber_state.total_seats, difficulty=threshold
        )
        previews.append(
            ChamberPreview(
                chamber=chamber_state.chamber.value,
                total_seats=chamber_state.total_seats,
                supporting_seats=apportionment.supporting_seats,
                required_seats=required,
                # The amendment path compares directly rather than calling
                # `chamber_carries`, exactly as phases.py:661 does.
                carries=apportionment.supporting_seats >= required,
            )
        )
    return tuple(previews)
