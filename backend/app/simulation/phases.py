"""The fixed, documented turn resolution order (product spec §7).

`PHASE_ORDER` is the fifteen-step resolution order from the brief, encoded as
data — a tuple of `(phase_id, handler)` pairs — rather than as a sequence of
separate calls buried in `resolver.py`. That makes the order declared exactly
once, testable exactly once (`tests/test_resolver.py` asserts the literal
sequence of phase IDs that ran), and impossible to silently reorder by
editing call sites.

Every phase handler has the same signature, `(ctx: PhaseContext) -> None`,
and is expected to mutate `ctx.state` in place and call
`ctx.mark_implemented()` if it does real work. As of Phase 2A, four phases
implement real government-accounting logic:

- `apply_legal_and_administrative_changes` — apply the submitted
  `BudgetDecision`'s targets (if any) to the player's active tax policy and
  spending plan. This is also where `OpeningFinanceSnapshot` is captured,
  *before* anything is mutated (see that class's docstring — R3).
- `resolve_government_revenue_and_expenditure` — compute revenue, total
  spending, and quarterly interest via `simulation.accounting`.
- `update_prices_inflation_employment_debt_reserves` — resolve cash and debt
  for the quarter and write the results back into the player's treasury.
- `generate_turn_report` — assemble the self-validating `FinanceReport` (see
  `report.py`) from the accumulated `FinanceScratch`, plus the always-present
  player-facing "turn resolved" entry.

Every other phase remains a registered, honest no-op (see
`docs/architecture.md`, "Turn resolution", and `simulation.report` for why
that's tracked as dev metadata rather than player-facing report noise).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.errors import DecisionSetError
from app.core.money import BPS_DENOMINATOR, Money
from app.core.rng import derive_rng
from app.simulation.accounting import (
    compute_quarterly_interest,
    compute_tax_revenue,
    compute_total_program_spending,
    resolve_cash_and_debt,
)
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.constitution import ConstitutionState, DecreeAuthority, constitution_digest
from app.simulation.decisions import BudgetDecision, DecisionSet
from app.simulation.labor_allocation import (
    aggregate_labor_market,
    allocate_workers,
    compute_effective_labor_force,
    compute_required_workers,
)
from app.simulation.legislative_voting import (
    DECREE_POLITICAL_CAPITAL_COST,
    chamber_carries,
    required_yes_seats,
    resolve_bloc_support,
    spending_policy_change,
    tax_policy_change,
)
from app.simulation.legislature import ChangeDirection as LegislativeChangeDirection
from app.simulation.legislature import LegislativeOutcome, ProposalRoute
from app.simulation.legitimacy import (
    PerformanceSignals,
    assess_economic_performance,
    order_support_contribution_bps,
    resolve_legitimacy,
    resolve_political_capital,
)
from app.simulation.production_accounting import compute_sector_output
from app.simulation.report import (
    TAX_RATE_CHANGE_FIELDS,
    BlocVoteReport,
    BudgetChangeEntry,
    ChamberVoteReport,
    ChangeDirection,
    ConstitutionSummary,
    EconomicBaselineReport,
    FinanceReport,
    LaborMarketReport,
    LegislativeReport,
    PhaseStatus,
    PoliticalReport,
    ProductionReport,
    ResourceDepositReport,
    ResourceExtractionReport,
    RevenueBreakdown,
    SectorLaborAllocationReport,
    SectorOutputBasis,
    SectorProductionConstraint,
    SectorProductionReport,
    SectorTaxBaseReport,
    TaxBaseDerivationReport,
    TurnReportEntry,
    classify_extraction_constraint,
    direction_for,
)
from app.simulation.resource_extraction import (
    DepositExtractionResult,
    DepositStatus,
    aggregate_extraction,
    allocate_extraction_workers,
    compute_deposit_extraction,
)
from app.simulation.resource_extraction import (
    compute_required_workers as compute_required_resource_workers,
)
from app.simulation.resource_output import (
    aggregate_extraction_sector_output,
    compute_resource_output_contributions,
)
from app.simulation.state import (
    EconomicBaselineState,
    GameState,
    LegislatureState,
    SectorCategory,
    SpendingPlanState,
    TaxBaseState,
    TaxPolicyState,
)
from app.simulation.tax_base_derivation import (
    aggregate_tax_base_contributions,
    compute_sector_tax_base_contribution,
)

if TYPE_CHECKING:
    # Only needed for the `random.Random` annotation below. A real (unguarded)
    # `import random` here would defeat the purpose of `core.rng.derive_rng` —
    # see `tests/test_no_forbidden_imports.py`, which allows TYPE_CHECKING-only
    # imports precisely because they can never execute and so can never
    # introduce non-determinism.
    import random


@dataclass(frozen=True, slots=True)
class OpeningFinanceSnapshot:
    """The player's complete financial position *before* this turn's budget decision
    is applied (R3, Phase 2A). Frozen and holding only immutable-by-convention Pydantic model
    instances captured by value at the start of `apply_legal_and_administrative_changes`
    — before any mutation — so later phases (and a mutated working `CountryState`) can
    never retroactively change what this turn's report says "opening" was.

    Needed for: computing interest from *opening* debt, explaining old-to-new tax and
    spending changes, proving omitted `BudgetDecision` fields were preserved, and
    distinguishing the player's *submitted* changes from the *resulting active* budget.

    As of Phase 2B2, tax bases are **not** part of this snapshot: they are no longer an
    authored, "opening" quantity at all — they are derived fresh every turn by
    `_resolve_government_revenue_and_expenditure` from that turn's own production (see
    `simulation.tax_base_derivation`), so there is nothing to snapshot "before mutation."
    """

    opening_cash: Money
    opening_debt: Money
    annual_debt_interest_rate_bps: int
    previous_tax_policy: TaxPolicyState
    previous_spending_plan: SpendingPlanState


@dataclass(frozen=True, slots=True)
class OpeningPoliticalSnapshot:
    """The player's complete political position *before* this turn's legitimacy/political-capital
    resolution (Phase 3A, §8). Frozen and holding only by-value copies, captured at the *start* of
    `_update_legitimacy_and_political_capital` — before any mutation — mirroring
    `OpeningFinanceSnapshot` exactly: later phases (and a mutated working `PoliticalState`) can
    never retroactively change what this turn's report calls "opening."

    Every field is either a plain `int` or an independently `.model_copy()`ed Pydantic model, so
    `PoliticalReport` can be built from scalars and frozen copies only — it never holds, and
    cannot reach, a `GameState` (R2)."""

    constitution: ConstitutionState
    constitutional_order_support_bps: int
    legitimacy_bps: int
    political_capital: int
    political_capital_capacity: int
    economic_baseline: EconomicBaselineState | None


@dataclass(frozen=True, slots=True)
class OpeningLegislativeSnapshot:
    """The player's complete legislative/political-capital position *before* this turn's budget
    proposal is resolved (Phase 3B1, §9). Captured by value at the very start of slot 1
    (`_validate_and_reserve_actions`) — before anything is mutated, and before slot 10 even knows
    what regeneration will be — mirroring `OpeningFinanceSnapshot`/`OpeningPoliticalSnapshot`
    exactly: later phases (and a mutated working `PoliticalState`/`GovernmentFinanceState`) can
    never retroactively change what this turn's report calls "opening."
    """

    legislature: LegislatureState | None
    political_capital: int
    tax_policy: TaxPolicyState
    spending_plan: SpendingPlanState


@dataclass
class LegislativeScratch:
    """Mutable, turn-local legislative workspace threaded through the Phase 3B1 phases via
    `PhaseContext.legislative_scratch`. Populated entirely by slot 1
    (`_validate_and_reserve_actions`) and never mutated afterward — mirroring `FinanceScratch`
    exactly: a way to pass intermediate values from one phase handler to the next without global
    state.

    `proposed_tax_policy`/`proposed_spending_plan` are what the budget WOULD become if the
    proposal takes effect — computed once here so slot 2 never recomputes them, and equal to
    `opening.tax_policy`/`opening.spending_plan` verbatim whenever there is no proposal (or when
    it names no target on that axis at all). Whether they are actually committed to state is
    slot 2's decision alone, gated on `outcome`.
    """

    opening: OpeningLegislativeSnapshot
    outcome: LegislativeOutcome
    route: ProposalRoute | None
    legislature_present: bool
    proposed_tax_policy: TaxPolicyState
    proposed_spending_plan: SpendingPlanState
    tax_delta_bps: int
    tax_direction: LegislativeChangeDirection
    tax_intensity_bps: int
    spending_direction: LegislativeChangeDirection
    spending_intensity_bps: int
    chambers: tuple[ChamberVoteReport, ...]
    blocs: tuple[BlocVoteReport, ...]
    political_capital_committed: int


@dataclass
class FinanceScratch:
    """Mutable, turn-local accounting workspace threaded through the Phase 2A/2B2 phases
    via `PhaseContext.finance`. Not itself part of `GameState` or the report — purely
    a way to pass intermediate values from one phase handler to the next without
    global state (product spec's ban on "hidden side effects" for phase handlers).
    """

    opening: OpeningFinanceSnapshot
    active_tax_policy: TaxPolicyState
    active_spending_plan: SpendingPlanState
    budget_changes: tuple[BudgetChangeEntry, ...] = ()
    applied_tax_bases: TaxBaseState | None = None
    """Set by `_resolve_government_revenue_and_expenditure`, derived fresh from this turn's
    `ctx.production_report` — see `simulation.tax_base_derivation`. There is no "opening" tax
    base anymore (Phase 2B2); this is the only tax-base value this turn ever has."""
    revenue: RevenueBreakdown | None = None
    total_program_spending: Money | None = None
    quarterly_interest_expense: Money | None = None
    pre_financing_balance: int | None = None
    new_borrowing: Money | None = None
    closing_cash: Money | None = None
    closing_debt: Money | None = None


@dataclass
class PhaseContext:
    """Mutable working state threaded through phase handlers during one resolution."""

    state: GameState
    """The working copy being mutated. Never the caller's original object."""
    decisions: DecisionSet
    resolving_turn: int
    """The turn number being resolved (i.e. `state.turn` as it was *before* this resolution)."""
    report_entries: list[TurnReportEntry] = field(default_factory=list)
    phase_statuses: dict[str, PhaseStatus] = field(default_factory=dict)
    legislative_scratch: LegislativeScratch | None = None
    """Set by `_validate_and_reserve_actions` (slot 1); read by slot 2 (gating), slot 10
    (political-capital commitment) and slot 15 (report assembly). Slot 1 itself never mutates
    `ctx.state` — see that function's docstring."""
    legislative_report: LegislativeReport | None = None
    """Set by `generate_turn_report` (slot 15) from `legislative_scratch`; `resolver.py` copies
    this onto the final `TurnReport`."""
    finance: FinanceScratch | None = None
    """Set by `apply_legal_and_administrative_changes`; read by the two phases after it."""
    finance_report: FinanceReport | None = None
    """Set by `generate_turn_report`; `resolver.py` copies this onto the final `TurnReport`."""
    labor_market_report: LaborMarketReport | None = None
    """Set at the very start of `resolve_production_and_trade`, before any sector output is
    computed; `resolver.py` copies this onto the final `TurnReport`. No scratch workspace (like
    `production_report`): allocation reads only current-turn `state...economy`/`population` and
    never spans multiple phases."""
    resources_report: ResourceExtractionReport | None = None
    """Set by `_extract_resources`, immediately after `labor_market_report` and before any sector
    output is computed; `resolver.py` copies this onto the final `TurnReport`. Unlike every other
    field on this class, building this report is not the only thing `_extract_resources` does:
    it also writes each deposit's `closing_stock` back into `ctx.state...economy.resource_deposits`
    in that same step (Phase 2C1, R2) — the one deliberate, narrow exception to this phase's
    otherwise-unchanged "never mutates state" contract, scoped to `resource_deposits` alone. See
    `_extract_resources`'s docstring and `docs/adr/0007-resource-endowments-and-extraction.md`."""
    production_report: ProductionReport | None = None
    """Set by `resolve_production_and_trade`; `resolver.py` copies this onto the final
    `TurnReport`. No scratch workspace for production (unlike `finance`): the phase reads
    only current-turn `state...economy` and never spans multiple phases, so it builds this
    report directly. Deliberately never read or written by any finance phase, and vice versa
    — see `_resolve_production_and_trade`'s docstring."""
    tax_base_derivation_report: TaxBaseDerivationReport | None = None
    """Set by `_resolve_government_revenue_and_expenditure`, at the start of that phase, from
    `production_report` — see that function's docstring. `resolver.py` copies this onto the
    final `TurnReport`, where it is cross-validated against both `production_report` and
    `finance_report` (Phase 2B2 R1)."""
    political_report: PoliticalReport | None = None
    """Set by `_update_legitimacy_and_political_capital` (slot 10), from
    `OpeningPoliticalSnapshot` plus `production_report`/`labor_market_report`; `resolver.py`
    copies this onto the final `TurnReport`, where it is cross-validated against both of those
    reports and, after resolution, against the resulting state (`simulation.reconciliation`)."""
    _current_phase_id: str | None = field(default=None, repr=False)

    def rng(self, stream: str) -> random.Random:
        """A deterministic RNG for `stream`, namespaced to this game/turn/stream triple."""
        return derive_rng(self.state.seed, self.resolving_turn, stream)

    def mark_implemented(self) -> None:
        """Call from within a phase handler to record that it did real work."""
        if self._current_phase_id is None:
            raise RuntimeError("mark_implemented() called outside of phase execution")
        self.phase_statuses[self._current_phase_id] = PhaseStatus.IMPLEMENTED


PhaseHandler = Callable[[PhaseContext], None]


def _noop(_ctx: PhaseContext) -> None:
    """Placeholder for a resolution step not yet implemented (tracked in dev metadata)."""


def _compute_proposed_tax_policy(
    *, opening: TaxPolicyState, decision: BudgetDecision
) -> TaxPolicyState:
    rate_updates = {
        field_name: target_value
        for field_name, target_value in (
            ("personal_income_rate_bps", decision.personal_income_rate_bps),
            ("corporate_rate_bps", decision.corporate_rate_bps),
            ("consumption_rate_bps", decision.consumption_rate_bps),
        )
        if target_value is not None
    }
    return opening.model_copy(update=rate_updates) if rate_updates else opening


def _compute_proposed_spending_plan(
    *, opening: SpendingPlanState, decision: BudgetDecision
) -> SpendingPlanState:
    proposed = opening
    for spending_update in decision.spending_updates:
        proposed = proposed.with_update(spending_update.category, spending_update.amount)
    return proposed


def _validate_and_reserve_actions(ctx: PhaseContext) -> None:  # noqa: C901
    """Phase 3B1, slot 1: resolve this turn's budget proposal against the legislature (or decree
    authority) BEFORE anything is mutated (§9 of the plan). Computes the vote (or decree, or
    NO_PROPOSAL) entirely from a by-value `OpeningLegislativeSnapshot` and writes only
    `ctx.legislative_scratch` — this function never mutates `ctx.state`, matching its name:
    "validate and reserve", not "apply".

    An invalid decision — a legislative route with no legislature, a decree the constitution does
    not authorize, an influence allocation naming an unknown party/bloc or a zero-seat bloc, or a
    commitment exceeding opening political capital — raises `DecisionSetError` here, which
    `resolve_turn` (`resolver.py`) catches and re-raises as `TurnResolutionError`, discarding the
    entire working copy exactly like an invariant violation. A **failed** legislative vote is not
    one of these: it is a normal, valid outcome that still advances the turn (§7.8, §8.1).
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    finance = player.finance
    if politics is None or finance is None:
        # Unreachable in practice: simulation.invariants requires player politics and finance
        # before resolve_turn ever copies state, let alone runs phases.
        raise RuntimeError(
            "validate_and_reserve_actions: player country is missing PoliticalState or "
            "GovernmentFinanceState (this should have been caught by check_invariants)"
        )

    opening = OpeningLegislativeSnapshot(
        legislature=politics.legislature.model_copy() if politics.legislature is not None else None,
        political_capital=politics.political_capital,
        tax_policy=finance.tax_policy.model_copy(),
        spending_plan=finance.spending_plan.model_copy(),
    )

    budget_decision = ctx.decisions.decisions[0] if ctx.decisions.decisions else None

    if budget_decision is None:
        ctx.legislative_scratch = LegislativeScratch(
            opening=opening,
            outcome=LegislativeOutcome.NO_PROPOSAL,
            route=None,
            legislature_present=opening.legislature is not None,
            proposed_tax_policy=opening.tax_policy,
            proposed_spending_plan=opening.spending_plan,
            tax_delta_bps=0,
            tax_direction=LegislativeChangeDirection.UNCHANGED,
            tax_intensity_bps=0,
            spending_direction=LegislativeChangeDirection.UNCHANGED,
            spending_intensity_bps=0,
            chambers=(),
            blocs=(),
            political_capital_committed=0,
        )
        ctx.mark_implemented()
        return

    route = budget_decision.route

    if route is ProposalRoute.LEGISLATIVE and opening.legislature is None:
        raise DecisionSetError(
            "budget decision requests route=legislative but the country has no legislature"
        )
    if route is ProposalRoute.DECREE and politics.constitution.decree_authority is not (
        DecreeAuthority.UNLIMITED
    ):
        raise DecisionSetError(
            "budget decision requests route=decree but decree_authority is "
            f"{politics.constitution.decree_authority.value!r} (requires 'unlimited')"
        )

    proposed_tax_policy = _compute_proposed_tax_policy(
        opening=opening.tax_policy, decision=budget_decision
    )
    proposed_spending_plan = _compute_proposed_spending_plan(
        opening=opening.spending_plan, decision=budget_decision
    )

    rate_changes = tuple(
        (getattr(opening.tax_policy, field_name), target_value)
        for field_name, target_value in (
            ("personal_income_rate_bps", budget_decision.personal_income_rate_bps),
            ("corporate_rate_bps", budget_decision.corporate_rate_bps),
            ("consumption_rate_bps", budget_decision.consumption_rate_bps),
        )
        if target_value is not None
    )
    tax_delta_bps = sum(target - current for current, target in rate_changes)
    tax_change = tax_policy_change(rate_changes=rate_changes)
    spending_change = spending_policy_change(
        opening_total=opening.spending_plan.total(), proposed_total=proposed_spending_plan.total()
    )

    if route is ProposalRoute.DECREE:
        commitment = DECREE_POLITICAL_CAPITAL_COST
        if commitment > opening.political_capital:
            raise DecisionSetError(
                f"decree commitment {commitment} exceeds opening political capital "
                f"{opening.political_capital}"
            )
        outcome = LegislativeOutcome.ENACTED_BY_DECREE
        chamber_reports: tuple[ChamberVoteReport, ...] = ()
        bloc_reports: tuple[BlocVoteReport, ...] = ()
    else:
        legislature = opening.legislature
        assert legislature is not None, "route=legislative was already rejected above otherwise"

        party_ids = {party.id for party in legislature.parties}
        blocs_by_key = {
            (party.id, bloc.id): bloc for party in legislature.parties for bloc in party.blocs
        }
        allocation_by_key: dict[tuple[str, str], int] = {}
        for allocation in budget_decision.influence:
            if allocation.party_id not in party_ids:
                raise DecisionSetError(f"influence targets unknown party {allocation.party_id!r}")
            bloc = blocs_by_key.get((allocation.party_id, allocation.bloc_id))
            if bloc is None:
                raise DecisionSetError(
                    "influence targets unknown bloc "
                    f"({allocation.party_id!r}, {allocation.bloc_id!r})"
                )
            if sum(entry.seats for entry in bloc.seats) == 0:
                raise DecisionSetError(
                    "influence targets bloc "
                    f"({allocation.party_id!r}, {allocation.bloc_id!r}) which holds zero seats "
                    "across every chamber"
                )
            allocation_by_key[(allocation.party_id, allocation.bloc_id)] = (
                allocation.political_capital
            )

        commitment = sum(allocation_by_key.values())
        if commitment > opening.political_capital:
            raise DecisionSetError(
                f"legislative influence commitment {commitment} exceeds opening political "
                f"capital {opening.political_capital}"
            )

        bloc_report_rows: list[BlocVoteReport] = []
        chamber_report_rows: list[ChamberVoteReport] = []
        chamber_passed: list[bool] = []
        for chamber_state in legislature.chambers:
            seat_supports: list[SeatSupport] = []
            chamber_bloc_data = []
            for party in legislature.parties:
                for bloc in party.blocs:
                    seats_in_chamber = next(
                        (
                            entry.seats
                            for entry in bloc.seats
                            if entry.chamber == chamber_state.chamber
                        ),
                        0,
                    )
                    if seats_in_chamber == 0:
                        continue
                    allocated = allocation_by_key.get((party.id, bloc.id), 0)
                    support = resolve_bloc_support(
                        role=party.government_role,
                        relationship_bps=bloc.government_relationship_bps,
                        tax_change=tax_change,
                        tax_preference_bps=bloc.tax_preference_bps,
                        spending_change=spending_change,
                        spending_preference_bps=bloc.spending_preference_bps,
                        allocated_political_capital=allocated,
                        discipline_bps=bloc.discipline_bps,
                    )
                    seat_supports.append(
                        SeatSupport(
                            party_id=party.id,
                            bloc_id=bloc.id,
                            seats=seats_in_chamber,
                            effective_support_bps=support.effective_support_bps,
                        )
                    )
                    chamber_bloc_data.append((party, bloc, seats_in_chamber, allocated, support))

            apportionment = apportion_supporting_seats(rows=tuple(seat_supports))
            apportioned_by_key = {(row.party_id, row.bloc_id): row for row in apportionment.rows}
            for party, bloc, seats_in_chamber, allocated, support in chamber_bloc_data:
                apportioned = apportioned_by_key[(party.id, bloc.id)]
                bloc_report_rows.append(
                    BlocVoteReport(
                        party_id=party.id,
                        bloc_id=bloc.id,
                        chamber=chamber_state.chamber,
                        seats=seats_in_chamber,
                        government_role=party.government_role,
                        government_relationship_bps=bloc.government_relationship_bps,
                        discipline_bps=bloc.discipline_bps,
                        tax_preference_bps=bloc.tax_preference_bps,
                        spending_preference_bps=bloc.spending_preference_bps,
                        baseline_support_bps=support.baseline_support_bps,
                        policy_compatibility_bps=support.policy_compatibility_bps,
                        raw_support_bps=support.raw_support_bps,
                        political_capital_allocated=allocated,
                        influence_bps=support.influence_bps,
                        final_support_bps=support.final_support_bps,
                        effective_support_bps=support.effective_support_bps,
                        numerator=apportioned.numerator,
                        base_seats=apportioned.base,
                        remainder=apportioned.remainder,
                        bonus_seat=bool(apportioned.bonus),
                        supporting_seats=apportioned.supporting_seats,
                    )
                )

            required = required_yes_seats(total_seats=chamber_state.total_seats)
            passed = chamber_carries(
                supporting_seats=apportionment.supporting_seats,
                total_seats=chamber_state.total_seats,
            )
            chamber_passed.append(passed)
            extras_awarded = apportionment.supporting_seats - sum(
                row.base for row in apportionment.rows
            )
            chamber_report_rows.append(
                ChamberVoteReport(
                    chamber=chamber_state.chamber,
                    total_seats=chamber_state.total_seats,
                    supporting_seats=apportionment.supporting_seats,
                    required_yes_seats=required,
                    shortfall_seats=max(0, required - apportionment.supporting_seats),
                    target_total=apportionment.supporting_seats,
                    extras_awarded=extras_awarded,
                    passed=passed,
                )
            )

        # (R1) Never `all([])`: `legislature.chambers` is required non-empty by `LegislatureState`
        # itself, so `chamber_passed` always has at least one entry here.
        outcome = (
            LegislativeOutcome.PASSED_LEGISLATIVE
            if all(chamber_passed)
            else LegislativeOutcome.FAILED_LEGISLATIVE
        )
        chamber_reports = tuple(chamber_report_rows)
        bloc_reports = tuple(bloc_report_rows)

    ctx.legislative_scratch = LegislativeScratch(
        opening=opening,
        outcome=outcome,
        route=route,
        legislature_present=opening.legislature is not None,
        proposed_tax_policy=proposed_tax_policy,
        proposed_spending_plan=proposed_spending_plan,
        tax_delta_bps=tax_delta_bps,
        tax_direction=tax_change.direction,
        tax_intensity_bps=tax_change.intensity_bps,
        spending_direction=spending_change.direction,
        spending_intensity_bps=spending_change.intensity_bps,
        chambers=chamber_reports,
        blocs=bloc_reports,
        political_capital_committed=commitment,
    )
    ctx.mark_implemented()


def _apply_legal_and_administrative_changes(ctx: PhaseContext) -> None:
    """Phase 2A slot 2; Phase 3B1 (D6) gates it on slot 1's vote: the proposed policy is only
    ever committed to state when `outcome` is `PASSED_LEGISLATIVE` or `ENACTED_BY_DECREE`. For
    `FAILED_LEGISLATIVE` or `NO_PROPOSAL`, the opening tax policy and spending plan are preserved
    byte-for-byte — a failed vote still advances the turn and still consumes the capital slot 1
    already committed, but the budget itself genuinely does not change.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    finance = player.finance
    if finance is None:
        # Unreachable in practice: simulation.invariants requires player finance
        # before resolve_turn ever copies state, let alone runs phases. Guarded
        # explicitly rather than silently assumed.
        raise RuntimeError(
            "apply_legal_and_administrative_changes: player country has no "
            "GovernmentFinanceState (this should have been caught by check_invariants)"
        )
    scratch = ctx.legislative_scratch
    assert scratch is not None, "validate_and_reserve_actions always runs first (slot 1)"

    # .model_copy() (not a bare reference) for every Pydantic-model-typed field:
    # TaxPolicyState/SpendingPlanState both have `validate_assignment=True`, which permits
    # in-place field mutation (`obj.field = x`) on a live instance. A bare reference here
    # would mean a *future* phase handler mutating `finance.tax_policy` or
    # `finance.spending_plan` in place — rather than replacing them wholesale, as this
    # module's handlers currently do — would silently corrupt what this turn's report
    # calls "opening," even though `OpeningFinanceSnapshot` itself is frozen. These models
    # have only scalar fields, so a shallow `model_copy()` is already a full, independent
    # copy — there is no nested mutable object left to worry about. (Tax bases are not
    # captured here at all as of Phase 2B2 — see `OpeningFinanceSnapshot`'s docstring.)
    opening = OpeningFinanceSnapshot(
        opening_cash=player.treasury.cash_on_hand,
        opening_debt=player.treasury.debt,
        annual_debt_interest_rate_bps=finance.annual_debt_interest_rate_bps,
        previous_tax_policy=finance.tax_policy.model_copy(),
        previous_spending_plan=finance.spending_plan.model_copy(),
    )

    budget_decision = ctx.decisions.decisions[0] if ctx.decisions.decisions else None
    applies = scratch.outcome in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    )
    # Default to the live (pre-mutation) objects, never `opening.previous_tax_policy`/
    # `opening.previous_spending_plan` directly — those are `OpeningFinanceSnapshot`'s own
    # independent `.model_copy()`s, and aliasing them here would mean a later in-place mutation
    # of the *committed* state (both models have `validate_assignment=True`) silently corrupts
    # what this turn's report calls "opening" too. `finance.tax_policy`/`finance.spending_plan`
    # are distinct objects from their `opening` counterparts by construction, above.
    active_tax_policy = finance.tax_policy
    active_spending_plan = finance.spending_plan
    budget_changes: list[BudgetChangeEntry] = []

    if applies and budget_decision is not None:
        rate_updates: dict[str, int] = {}
        for field_name, target_value in (
            ("personal_income_rate_bps", budget_decision.personal_income_rate_bps),
            ("corporate_rate_bps", budget_decision.corporate_rate_bps),
            ("consumption_rate_bps", budget_decision.consumption_rate_bps),
        ):
            if target_value is None:
                continue
            rate_updates[field_name] = target_value
            previous_value = getattr(opening.previous_tax_policy, field_name)
            budget_changes.append(
                BudgetChangeEntry(
                    field=field_name,
                    previous_value=previous_value,
                    new_value=target_value,
                    direction=direction_for(previous_value, target_value),
                )
            )
        if rate_updates:
            active_tax_policy = active_tax_policy.model_copy(update=rate_updates)

        for spending_update in budget_decision.spending_updates:
            category = spending_update.category
            previous_value = opening.previous_spending_plan.get(category)
            active_spending_plan = active_spending_plan.with_update(
                category, spending_update.amount
            )
            budget_changes.append(
                BudgetChangeEntry(
                    field=f"spending.{category.value}",
                    previous_value=previous_value,
                    new_value=spending_update.amount,
                    direction=direction_for(previous_value, spending_update.amount),
                )
            )

    ctx.finance = FinanceScratch(
        opening=opening,
        active_tax_policy=active_tax_policy,
        active_spending_plan=active_spending_plan,
        budget_changes=tuple(budget_changes),
    )

    # Commit the (possibly unchanged) active policy back into working state — this
    # *is* the administrative/legal-changes step; later phases read finance.tax_policy
    # and finance.spending_plan expecting them already updated.
    player.finance = finance.model_copy(
        update={"tax_policy": active_tax_policy, "spending_plan": active_spending_plan}
    )

    if budget_decision is None:
        ctx.report_entries.append(
            TurnReportEntry(category="budget", reason_id="no_budget_changes_submitted")
        )
    for change in budget_changes:
        if change.direction == ChangeDirection.UNCHANGED:
            continue
        if change.field in TAX_RATE_CHANGE_FIELDS:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="budget",
                    reason_id="tax_rate_changed",
                    params={
                        "field": change.field,
                        "old_bps": change.previous_value,
                        "new_bps": change.new_value,
                    },
                )
            )
        else:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="budget",
                    reason_id="spending_category_changed",
                    params={
                        "category": change.field.removeprefix("spending."),
                        "old_amount": change.previous_value,
                        "new_amount": change.new_value,
                    },
                )
            )

    ctx.mark_implemented()


def _derive_tax_bases_from_production(ctx: PhaseContext) -> TaxBaseDerivationReport:
    """Phase 2B2: derive this turn's tax bases from this turn's already-computed
    `ctx.production_report` (production is phase 3; this revenue phase is phase 4, so
    production is always populated by the time this runs — no lag, same-turn linkage).

    Reads `actual_output` from the production report row for each category, never
    re-deriving it from `SectorState` — this is what R1's cross-report validation on
    `TurnReport` later confirms: the exact same figure production computed is the exact
    figure derivation used as its input. Structural per-sector shares
    (`value_added_share_bps`/`labor_income_share_bps`) come from the player's current
    `EconomyState`; the country-level fiscal coefficients come from
    `GovernmentFinanceState.tax_base_coefficients`. Pure with respect to `ctx.state` — reads
    it, does not mutate it; the derived result is turn-local (`ctx.tax_base_derivation_report`),
    never written back into `GameState`.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    economy = player.economy
    finance = player.finance
    assert economy is not None, "resolve_production_and_trade already required this"
    assert finance is not None, "apply_legal_and_administrative_changes already required this"
    assert ctx.production_report is not None, "resolve_production_and_trade always runs first"

    production_by_category = {
        row.category: row.actual_output for row in ctx.production_report.sectors
    }
    shares_by_category = {sector.category: sector for sector in economy.sectors}

    results = []
    sector_reports: list[SectorTaxBaseReport] = []
    for category in SectorCategory:
        sector_state = shares_by_category[category]
        actual_output = production_by_category[category]
        result = compute_sector_tax_base_contribution(
            actual_output=actual_output,
            value_added_share_bps=sector_state.value_added_share_bps,
            labor_income_share_bps=sector_state.labor_income_share_bps,
            coefficients=finance.tax_base_coefficients,
        )
        results.append(result)
        sector_reports.append(
            SectorTaxBaseReport(
                category=category,
                actual_output=actual_output,
                value_added_share_bps=sector_state.value_added_share_bps,
                labor_income_share_bps=sector_state.labor_income_share_bps,
                modeled_value_added=result.modeled_value_added,
                labor_income=result.labor_income,
                operating_surplus=result.operating_surplus,
                personal_contribution=result.personal_contribution,
                corporate_contribution=result.corporate_contribution,
                consumption_contribution=result.consumption_contribution,
            )
        )

    aggregates = aggregate_tax_base_contributions(tuple(results))
    return TaxBaseDerivationReport(
        coefficients=finance.tax_base_coefficients,
        sectors=tuple(sector_reports),
        total_modeled_value_added=aggregates.total_modeled_value_added,
        total_labor_income=aggregates.total_labor_income,
        total_operating_surplus=aggregates.total_operating_surplus,
        derived_tax_bases=aggregates.derived_tax_bases,
    )


def _resolve_government_revenue_and_expenditure(ctx: PhaseContext) -> None:
    scratch = ctx.finance
    assert scratch is not None, "apply_legal_and_administrative_changes always runs first"

    derivation = _derive_tax_bases_from_production(ctx)
    ctx.tax_base_derivation_report = derivation
    scratch.applied_tax_bases = derivation.derived_tax_bases

    ctx.report_entries.append(
        TurnReportEntry(
            category="production",
            reason_id="tax_bases_derived",
            params={
                "personal_income": derivation.derived_tax_bases.personal_income,
                "corporate_profit": derivation.derived_tax_bases.corporate_profit,
                "taxable_consumption": derivation.derived_tax_bases.taxable_consumption,
            },
        )
    )

    revenue_breakdown = compute_tax_revenue(scratch.applied_tax_bases, scratch.active_tax_policy)
    scratch.revenue = RevenueBreakdown(
        personal_income_tax=revenue_breakdown.personal_income_tax,
        corporate_tax=revenue_breakdown.corporate_tax,
        consumption_tax=revenue_breakdown.consumption_tax,
        total_revenue=revenue_breakdown.total_revenue,
    )
    scratch.total_program_spending = compute_total_program_spending(scratch.active_spending_plan)
    scratch.quarterly_interest_expense = compute_quarterly_interest(
        scratch.opening.opening_debt, scratch.opening.annual_debt_interest_rate_bps
    )

    ctx.mark_implemented()


def _update_prices_inflation_employment_debt_reserves(ctx: PhaseContext) -> None:
    scratch = ctx.finance
    assert scratch is not None
    assert scratch.revenue is not None
    assert scratch.total_program_spending is not None
    assert scratch.quarterly_interest_expense is not None

    resolution = resolve_cash_and_debt(
        opening_cash=scratch.opening.opening_cash,
        opening_debt=scratch.opening.opening_debt,
        total_revenue=scratch.revenue.total_revenue,
        total_program_spending=scratch.total_program_spending,
        quarterly_interest=scratch.quarterly_interest_expense,
    )
    scratch.pre_financing_balance = resolution.pre_financing_balance
    scratch.new_borrowing = resolution.new_borrowing
    scratch.closing_cash = resolution.closing_cash
    scratch.closing_debt = resolution.closing_debt

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    player.treasury = player.treasury.model_copy(
        update={"cash_on_hand": resolution.closing_cash, "debt": resolution.closing_debt}
    )

    if resolution.new_borrowing > 0:
        ctx.report_entries.append(
            TurnReportEntry(
                category="budget",
                reason_id="deficit_financed_with_new_borrowing",
                params={"amount": resolution.new_borrowing},
            )
        )

    ctx.mark_implemented()


def _allocate_labor(ctx: PhaseContext) -> LaborMarketReport:
    """Phase 2B3: deterministic labor allocation, run at the very start of
    `resolve_production_and_trade` — before any sector output is computed — so production
    consumes this same turn's allocation with no lag. Reads `player.population` and
    `economy.effective_labor_force_share_bps`/`economy.sectors`, never `player.finance`/
    `player.treasury`; writes only `ctx.labor_market_report`; never mutates `state`. Pure with
    respect to `ctx.state`, mirroring `_derive_tax_bases_from_production`'s isolation.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    economy = player.economy
    assert economy is not None, "resolve_production_and_trade already required this"

    effective_labor_force = compute_effective_labor_force(
        population=player.population,
        effective_labor_force_share_bps=economy.effective_labor_force_share_bps,
    )
    required_by_category = tuple(
        (sector.category, compute_required_workers(sector)) for sector in economy.sectors
    )
    allocation_results = allocate_workers(
        required_by_category=required_by_category,
        effective_labor_force=effective_labor_force,
    )
    market_aggregates = aggregate_labor_market(
        total_population=player.population,
        effective_labor_force=effective_labor_force,
        results=allocation_results,
    )

    sector_reports = tuple(
        SectorLaborAllocationReport(
            category=result.category,
            required_workers=result.required_workers,
            allocated_workers=result.allocated_workers,
            unfilled_workers=result.required_workers - result.allocated_workers,
        )
        for result in allocation_results
    )

    return LaborMarketReport(
        total_population=market_aggregates.total_population,
        effective_labor_force_share_bps=economy.effective_labor_force_share_bps,
        effective_labor_force=market_aggregates.effective_labor_force,
        sectors=sector_reports,
        total_labor_demand=market_aggregates.total_labor_demand,
        total_employment=market_aggregates.total_employment,
        unemployed_workers=market_aggregates.unemployed_workers,
        unfilled_jobs=market_aggregates.unfilled_jobs,
        unemployment_rate_bps=market_aggregates.unemployment_rate_bps,
    )


def _extract_resources(
    ctx: PhaseContext, *, extraction_sector_workers: int
) -> ResourceExtractionReport:
    """Phase 2C1: deterministic resource regeneration, extraction, and depletion, run immediately
    after labor allocation and before aggregate sector production, inside
    `resolve_production_and_trade`. `extraction_sector_workers` is this same turn's
    `LaborMarketReport.sectors[EXTRACTION].allocated_workers` — the worker budget sub-allocated
    across the eight deposits. As of Phase 2C2, also computes each deposit's actual and potential
    physical-to-output bridge contribution (`simulation.resource_output`), which the caller
    (`_resolve_production_and_trade`) uses to derive the extraction sector's
    `SectorProductionReport` row — replacing, never adding to, that sector's former
    capacity/productivity formula.

    Unlike `_allocate_labor` and every other helper in this phase, this function is **not** pure
    with respect to `ctx.state` (R2, `docs/adr/0007-resource-endowments-and-extraction.md`):
    extraction and its resulting depletion are one domain operation, so after computing each
    deposit's closing stock this function writes it straight back into
    `ctx.state...economy.resource_deposits`, matched by `ResourceCategory` identity — never tuple
    position, and never any field but `remaining_stock`. This is a deliberate, narrow exception to
    the phase's otherwise-unchanged "never mutates state" contract; `resolve_production_and_trade`
    still never reads or writes `ctx.finance`/`ctx.finance_report`/treasury/debt, and this function
    itself never touches anything but `resource_deposits`. Safe because the resolver's single deep
    copy and its post-phase invariant re-check (`resolver.py`) are unaffected by *which* phase
    performed a mutation — an invariant violation later in the same `resolve_turn` call still
    discards the entire working copy.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    economy = player.economy
    assert economy is not None, "resolve_production_and_trade already required this"

    required_by_category = {
        deposit.category: compute_required_resource_workers(deposit)
        for deposit in economy.resource_deposits
    }
    allocation_results = allocate_extraction_workers(
        required_by_category=required_by_category,
        extraction_sector_workers=extraction_sector_workers,
    )
    allocation_by_category = {result.category: result for result in allocation_results}

    extraction_results: list[DepositExtractionResult] = []
    for deposit in economy.resource_deposits:
        allocation = allocation_by_category[deposit.category]
        extraction_result = compute_deposit_extraction(deposit=deposit, allocation=allocation)
        extraction_results.append(extraction_result)
        # R2: extraction and its depletion are one domain operation, performed together right
        # here — `deposit` is the live model instance inside `ctx.state`'s working copy (not a
        # fresh parse), so this assignment mutates the working state directly. Matched by
        # `deposit.category` identity, never by loop/tuple position.
        deposit.remaining_stock = extraction_result.closing_stock

    coefficients_by_category = {
        coefficient.category: coefficient.real_output_per_unit
        for coefficient in economy.resource_output_coefficients
    }
    contributions = compute_resource_output_contributions(
        extraction_results=tuple(extraction_results),
        coefficients=coefficients_by_category,
    )
    contribution_by_category = {
        contribution.category: contribution for contribution in contributions
    }

    deposit_reports: list[ResourceDepositReport] = []
    for extraction_result in extraction_results:
        contribution = contribution_by_category[extraction_result.category]
        deposit_reports.append(
            ResourceDepositReport(
                category=extraction_result.category,
                opening_stock=extraction_result.opening_stock,
                regeneration_per_turn=extraction_result.regeneration_per_turn,
                stock_ceiling=extraction_result.stock_ceiling,
                regenerated=extraction_result.regenerated,
                available_stock=extraction_result.available_stock,
                extraction_capacity_per_turn=extraction_result.extraction_capacity_per_turn,
                output_per_worker=extraction_result.output_per_worker,
                required_workers=extraction_result.required_workers,
                allocated_workers=extraction_result.allocated_workers,
                extracted=extraction_result.extracted,
                closing_stock=extraction_result.closing_stock,
                status=extraction_result.status,
                real_output_per_unit=contribution.real_output_per_unit,
                real_output_contribution=contribution.real_output_contribution,
                potential_output_contribution=contribution.potential_output_contribution,
            )
        )

    aggregates = aggregate_extraction(
        extraction_sector_workers=extraction_sector_workers,
        results=tuple(extraction_results),
    )
    extraction_sector_real_output, extraction_sector_potential_output = (
        aggregate_extraction_sector_output(contributions)
    )

    return ResourceExtractionReport(
        deposits=tuple(deposit_reports),
        extraction_sector_workers=aggregates.extraction_sector_workers,
        total_extraction_workers=aggregates.total_extraction_workers,
        unassigned_resource_workers=aggregates.unassigned_resource_workers,
        extraction_sector_real_output=extraction_sector_real_output,
        extraction_sector_potential_output=extraction_sector_potential_output,
    )


def _resolve_production_and_trade(ctx: PhaseContext) -> None:
    """Phase 2B1 sector production, plus (Phase 2B3) the labor allocation that feeds it, plus
    (Phase 2C1) the resource extraction sub-allocated from the extraction sector's workers —
    trade (imports/exports, cross-country flows) is fully out of scope this phase despite the
    phase's name; that name is the fixed §7 phase slot this fills, not a claim about what's
    implemented.

    Deliberately isolated from Phase 2A's government accounting: reads only the player's
    current-turn `EconomyState`/`population` (never `player.finance`/`player.treasury`), writes
    only `ctx.labor_market_report`/`ctx.resources_report`/`ctx.production_report` (never
    `ctx.finance`/`ctx.finance_report`/treasury/debt). This phase runs *before* the finance phases
    in `PHASE_ORDER`, so all three reports are already populated by the time they execute — those
    phases must never read them (see `tests/test_phase_isolation.py`).

    As of Phase 2C1 (R2), this phase is **not** entirely free of state mutation: `_extract_resources`
    writes each deposit's closing stock into `economy.resource_deposits` as part of computing the
    resource report — see that function's docstring for why, and for the exact scope of the
    exception (`resource_deposits` only, nothing else).
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    economy = player.economy
    if economy is None:
        # Unreachable in practice: simulation.invariants requires player economy before
        # resolve_turn ever copies state, let alone runs phases. Guarded explicitly rather
        # than silently assumed.
        raise RuntimeError(
            "resolve_production_and_trade: player country has no EconomyState "
            "(this should have been caught by check_invariants)"
        )

    labor_market = _allocate_labor(ctx)
    ctx.labor_market_report = labor_market
    ctx.report_entries.append(
        TurnReportEntry(
            category="production",
            reason_id="labor_market_resolved",
            params={
                "effective_labor_force": labor_market.effective_labor_force,
                "total_employment": labor_market.total_employment,
                "unemployed_workers": labor_market.unemployed_workers,
                "unfilled_jobs": labor_market.unfilled_jobs,
                "unemployment_rate_bps": labor_market.unemployment_rate_bps,
            },
        )
    )

    allocated_by_category = {row.category: row.allocated_workers for row in labor_market.sectors}

    resources = _extract_resources(
        ctx, extraction_sector_workers=allocated_by_category[SectorCategory.EXTRACTION]
    )
    ctx.resources_report = resources
    status_counts = {status.value: 0 for status in DepositStatus}
    for deposit_report in resources.deposits:
        status_counts[deposit_report.status.value] += 1
    ctx.report_entries.append(
        TurnReportEntry(
            category="production",
            reason_id="resource_extraction_resolved",
            params={
                "deposits_active": len(resources.deposits)
                - status_counts[DepositStatus.INACTIVE.value],
                "deposits_depleted": status_counts[DepositStatus.DEPLETED.value],
                "total_extraction_workers": resources.total_extraction_workers,
                "unassigned_resource_workers": resources.unassigned_resource_workers,
                "extraction_sector_real_output": resources.extraction_sector_real_output,
                "extraction_sector_potential_output": resources.extraction_sector_potential_output,
            },
        )
    )

    sector_reports: list[SectorProductionReport] = []
    allocated_workers_in_order: list[int] = []
    counts: dict[str, int] = {}
    for sector in economy.sectors:
        allocated_workers = allocated_by_category[sector.category]
        allocated_workers_in_order.append(allocated_workers)

        if sector.category is SectorCategory.EXTRACTION:
            # Phase 2C2 (D3, R6): the extraction sector's output IS the physical bridge total —
            # REPLACING, never adding to, the standard capacity/productivity formula in the else
            # branch below. `compute_sector_output` (production_accounting.py, unmodified) is
            # simply never called for this one category. sector.quarterly_capacity_output/
            # .output_per_worker are read NOWHERE in this branch — completely inert for this
            # basis (see docs/adr/0008-physical-extraction-derived-sector-output.md, "Legacy
            # field semantics").
            actual_output = resources.extraction_sector_real_output
            potential_output = resources.extraction_sector_potential_output
            constraint: SectorProductionConstraint = classify_extraction_constraint(
                potential_output=potential_output, actual_output=actual_output
            )
            capacity_utilization_bps = (
                (actual_output * BPS_DENOMINATOR) // potential_output if potential_output > 0 else 0
            )
            sector_reports.append(
                SectorProductionReport(
                    category=sector.category,
                    output_basis=SectorOutputBasis.RESOURCE_EXTRACTION,
                    capacity_output=sector.quarterly_capacity_output,
                    output_per_worker=sector.output_per_worker,
                    employed_workers=allocated_workers,
                    labor_limited_output=actual_output,
                    actual_output=actual_output,
                    capacity_utilization_bps=capacity_utilization_bps,
                    constraint=constraint,
                )
            )
        else:
            result = compute_sector_output(sector, allocated_workers)
            constraint = SectorProductionConstraint(result.constraint.value)
            sector_reports.append(
                SectorProductionReport(
                    category=sector.category,
                    output_basis=SectorOutputBasis.STANDARD,
                    capacity_output=sector.quarterly_capacity_output,
                    output_per_worker=sector.output_per_worker,
                    employed_workers=allocated_workers,
                    labor_limited_output=result.labor_limited_output,
                    actual_output=result.actual_output,
                    capacity_utilization_bps=result.capacity_utilization_bps,
                    constraint=constraint,
                )
            )

        counts[constraint.value] = counts.get(constraint.value, 0) + 1
        if constraint is SectorProductionConstraint.INACTIVE:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="production",
                    reason_id="sector_inactive",
                    params={"category": sector.category.value},
                )
            )

    # production_accounting.aggregate_production is not called here (Phase 2C2): it takes a
    # tuple of SectorProductionResult, a type the extraction row no longer has (it never calls
    # compute_sector_output). total_employment/total_gross_output are simple, basis-agnostic
    # sums, computed directly from sector_reports — which already has all 11 rows — instead.
    total_employment = sum(row.employed_workers for row in sector_reports)
    total_gross_output = sum(row.actual_output for row in sector_reports)
    ctx.production_report = ProductionReport(
        sectors=tuple(sector_reports),
        total_employment=total_employment,
        total_gross_output=total_gross_output,
    )
    ctx.report_entries.append(
        TurnReportEntry(
            category="production",
            reason_id="production_summary",
            params={
                "total_employment": total_employment,
                "total_gross_output": total_gross_output,
                "sectors_capacity_constrained": counts.get(
                    SectorProductionConstraint.CAPACITY_CONSTRAINED.value, 0
                ),
                "sectors_labor_constrained": counts.get(
                    SectorProductionConstraint.LABOR_CONSTRAINED.value, 0
                ),
                "sectors_exactly_balanced": counts.get(
                    SectorProductionConstraint.EXACTLY_BALANCED.value, 0
                ),
                "sectors_physical_resource_constrained": counts.get(
                    SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED.value, 0
                ),
                "sectors_inactive": counts.get(SectorProductionConstraint.INACTIVE.value, 0),
            },
        )
    )

    ctx.mark_implemented()


def _update_legitimacy_and_political_capital(ctx: PhaseContext) -> None:
    """Phase 3A, slot 10 (`update_group_welfare_approval_trust_radicalization`): resolves this
    turn's legitimacy and political-capital change from the two economic signals the engine
    genuinely models against the persisted baseline, plus drift toward the scenario-authored
    `constitutional_order_support_bps`. See `simulation.legitimacy` and
    `docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`.

    Runs after `_resolve_production_and_trade` (phase 3) so `ctx.production_report` and
    `ctx.labor_market_report` are both already self-validated. Reads only those two reports and
    `player.politics`; writes only `player.politics` — never `economy`/`finance`/`treasury`
    (Phase 3A's economy-to-politics linkage is strictly one-way).

    No `PHASE_ORDER` change: this implements the existing slot 10, exactly as four consecutive
    prior phases (2B2, 2B3, 2C1, 2C2) added real logic to an existing slot rather than adding a
    16th one.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    if politics is None:
        # Unreachable in practice: simulation.invariants requires player politics before
        # resolve_turn ever copies state, let alone runs phases. Guarded explicitly rather than
        # silently assumed.
        raise RuntimeError(
            "update_legitimacy_and_political_capital: player country has no PoliticalState "
            "(this should have been caught by check_invariants)"
        )
    assert ctx.production_report is not None, "resolve_production_and_trade always runs first"
    assert ctx.labor_market_report is not None, "labor allocation always runs before production"

    # By-value snapshot, mirroring OpeningFinanceSnapshot exactly (R2): every field is a plain
    # int or an independently `.model_copy()`ed Pydantic model, captured BEFORE any mutation
    # below, so a later mutation of `politics` cannot retroactively change what the report calls
    # "opening."
    opening = OpeningPoliticalSnapshot(
        constitution=politics.constitution.model_copy(),
        constitutional_order_support_bps=politics.constitutional_order_support_bps,
        legitimacy_bps=politics.legitimacy_bps,
        political_capital=politics.political_capital,
        political_capital_capacity=politics.political_capital_capacity,
        economic_baseline=(
            politics.economic_baseline.model_copy()
            if politics.economic_baseline is not None
            else None
        ),
    )

    current_total_gross_output = ctx.production_report.total_gross_output
    current_unemployment_rate_bps = ctx.labor_market_report.unemployment_rate_bps

    signals = (
        None
        if opening.economic_baseline is None
        else PerformanceSignals(
            baseline_total_gross_output=opening.economic_baseline.total_gross_output,
            current_total_gross_output=current_total_gross_output,
            baseline_unemployment_rate_bps=opening.economic_baseline.unemployment_rate_bps,
            current_unemployment_rate_bps=current_unemployment_rate_bps,
        )
    )
    assessment = assess_economic_performance(signals)

    legislative_scratch = ctx.legislative_scratch
    assert legislative_scratch is not None, "validate_and_reserve_actions always runs first"
    political_capital_committed = legislative_scratch.political_capital_committed

    drift = order_support_contribution_bps(
        support_bps=opening.constitutional_order_support_bps,
        opening_legitimacy_bps=opening.legitimacy_bps,
    )
    total_change, closing_legitimacy = resolve_legitimacy(
        opening_bps=opening.legitimacy_bps,
        order_support_contribution=drift,
        performance_contribution=assessment.performance_contribution_bps,
    )
    regeneration, closing_capital = resolve_political_capital(
        opening=opening.political_capital,
        capacity=opening.political_capital_capacity,
        legitimacy_bps=closing_legitimacy,
        spent=political_capital_committed,
    )

    closing_baseline_state = EconomicBaselineState(
        source_turn=ctx.state.turn,
        total_gross_output=current_total_gross_output,
        unemployment_rate_bps=current_unemployment_rate_bps,
    )

    # Whole-model replace via model_copy(update=...), matching every other phase's convention for
    # committing a mutated sub-model back into working state (see
    # `_update_prices_inflation_employment_debt_reserves`) — never an in-place field assignment.
    player.politics = politics.model_copy(
        update={
            "legitimacy_bps": closing_legitimacy,
            "political_capital": closing_capital,
            "economic_baseline": closing_baseline_state,
        }
    )

    opening_baseline_report = (
        None
        if opening.economic_baseline is None
        else EconomicBaselineReport(
            source_turn=opening.economic_baseline.source_turn,
            total_gross_output=opening.economic_baseline.total_gross_output,
            unemployment_rate_bps=opening.economic_baseline.unemployment_rate_bps,
        )
    )
    closing_baseline_report = EconomicBaselineReport(
        source_turn=closing_baseline_state.source_turn,
        total_gross_output=closing_baseline_state.total_gross_output,
        unemployment_rate_bps=closing_baseline_state.unemployment_rate_bps,
    )

    ctx.political_report = PoliticalReport(
        constitution=ConstitutionSummary(
            executive_system=opening.constitution.executive_system,
            executive_selection=opening.constitution.executive_selection,
            legislature=opening.constitution.legislature,
            territorial_organization=opening.constitution.territorial_organization,
            judicial_review=opening.constitution.judicial_review,
            amendment_difficulty=opening.constitution.amendment_difficulty,
            decree_authority=opening.constitution.decree_authority,
            executive_term_limit_terms=opening.constitution.executive_term_limit_terms,
            national_election_interval_turns=opening.constitution.national_election_interval_turns,
            constitution_digest=constitution_digest(opening.constitution),
        ),
        constitutional_order_support_bps=opening.constitutional_order_support_bps,
        opening_legitimacy_bps=opening.legitimacy_bps,
        opening_economic_baseline=opening_baseline_report,
        current_total_gross_output=current_total_gross_output,
        current_unemployment_rate_bps=current_unemployment_rate_bps,
        output_change_bps=assessment.output_change_bps,
        output_contribution_bps=assessment.output_contribution_bps,
        unemployment_change_bps=assessment.unemployment_change_bps,
        unemployment_contribution_bps=assessment.unemployment_contribution_bps,
        performance_contribution_bps=assessment.performance_contribution_bps,
        order_support_contribution_bps=drift,
        total_legitimacy_change_bps=total_change,
        closing_legitimacy_bps=closing_legitimacy,
        closing_economic_baseline=closing_baseline_report,
        opening_political_capital=opening.political_capital,
        political_capital_regeneration=regeneration,
        political_capital_spent=political_capital_committed,
        political_capital_capacity=opening.political_capital_capacity,
        closing_political_capital=closing_capital,
    )

    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="legitimacy_resolved",
            params={
                "opening_legitimacy_bps": opening.legitimacy_bps,
                "order_support_contribution_bps": drift,
                "performance_contribution_bps": assessment.performance_contribution_bps,
                "total_legitimacy_change_bps": total_change,
                "closing_legitimacy_bps": closing_legitimacy,
                "constitutional_order_support_bps": opening.constitutional_order_support_bps,
            },
        )
    )
    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="political_capital_resolved",
            params={
                "opening": opening.political_capital,
                "regeneration": regeneration,
                "spent": political_capital_committed,
                "capacity": opening.political_capital_capacity,
                "closing": closing_capital,
            },
        )
    )

    ctx.mark_implemented()


def _generate_turn_report(ctx: PhaseContext) -> None:
    ctx.report_entries.append(
        TurnReportEntry(
            category="administration",
            reason_id="turn_resolved",
            params={"turn": ctx.resolving_turn},
        )
    )

    scratch = ctx.finance
    if scratch is not None:
        assert scratch.applied_tax_bases is not None
        assert scratch.revenue is not None
        assert scratch.total_program_spending is not None
        assert scratch.quarterly_interest_expense is not None
        assert scratch.pre_financing_balance is not None
        assert scratch.new_borrowing is not None
        assert scratch.closing_cash is not None
        assert scratch.closing_debt is not None
        ctx.finance_report = FinanceReport(
            opening_cash=scratch.opening.opening_cash,
            opening_debt=scratch.opening.opening_debt,
            annual_debt_interest_rate_bps=scratch.opening.annual_debt_interest_rate_bps,
            tax_bases=scratch.applied_tax_bases,
            previous_tax_policy=scratch.opening.previous_tax_policy,
            active_tax_policy=scratch.active_tax_policy,
            previous_spending_plan=scratch.opening.previous_spending_plan,
            active_spending_plan=scratch.active_spending_plan,
            revenue=scratch.revenue,
            total_program_spending=scratch.total_program_spending,
            quarterly_interest_expense=scratch.quarterly_interest_expense,
            pre_financing_balance=scratch.pre_financing_balance,
            new_borrowing=scratch.new_borrowing,
            closing_cash=scratch.closing_cash,
            closing_debt=scratch.closing_debt,
            budget_changes=scratch.budget_changes,
        )

    legislative_scratch = ctx.legislative_scratch
    assert legislative_scratch is not None, "validate_and_reserve_actions always runs first"
    ctx.legislative_report = LegislativeReport(
        outcome=legislative_scratch.outcome,
        route=legislative_scratch.route,
        legislature_present=legislative_scratch.legislature_present,
        tax_delta_bps=legislative_scratch.tax_delta_bps,
        tax_direction=legislative_scratch.tax_direction,
        tax_intensity_bps=legislative_scratch.tax_intensity_bps,
        opening_total_program_spending=legislative_scratch.opening.spending_plan.total(),
        proposed_total_program_spending=legislative_scratch.proposed_spending_plan.total(),
        spending_direction=legislative_scratch.spending_direction,
        spending_intensity_bps=legislative_scratch.spending_intensity_bps,
        chambers=legislative_scratch.chambers,
        blocs=legislative_scratch.blocs,
        opening_political_capital=legislative_scratch.opening.political_capital,
        political_capital_committed=legislative_scratch.political_capital_committed,
    )

    ctx.mark_implemented()


# The fifteen-step resolution order from product spec §7. Order matters and is tested.
PHASE_ORDER: tuple[tuple[str, PhaseHandler], ...] = (
    ("validate_and_reserve_actions", _validate_and_reserve_actions),
    ("apply_legal_and_administrative_changes", _apply_legal_and_administrative_changes),
    ("resolve_production_and_trade", _resolve_production_and_trade),
    (
        "resolve_government_revenue_and_expenditure",
        _resolve_government_revenue_and_expenditure,
    ),
    (
        "update_prices_inflation_employment_debt_reserves",
        _update_prices_inflation_employment_debt_reserves,
    ),
    ("resolve_public_services_and_infrastructure", _noop),
    ("resolve_diplomacy_and_sanctions", _noop),
    ("resolve_military_movement_and_combat", _noop),
    ("apply_casualties_occupation_disruption_war_costs", _noop),
    (
        "update_group_welfare_approval_trust_radicalization",
        _update_legitimacy_and_political_capital,
    ),
    ("update_institutional_loyalty_competence_corruption_power", _noop),
    ("evaluate_protests_strikes_insurgency_coups_revolutions", _noop),
    ("evaluate_elections_and_constitutional_events", _noop),
    ("trigger_narrative_events", _noop),
    ("generate_turn_report", _generate_turn_report),
)

PHASE_IDS: tuple[str, ...] = tuple(phase_id for phase_id, _ in PHASE_ORDER)


def run_phases(ctx: PhaseContext) -> None:
    """Run every phase in `PHASE_ORDER`, in order, recording a status for each."""
    for phase_id, handler in PHASE_ORDER:
        ctx._current_phase_id = phase_id  # same-module access to the phase-execution protocol
        ctx.phase_statuses.setdefault(phase_id, PhaseStatus.NOT_IMPLEMENTED)
        handler(ctx)
        ctx._current_phase_id = None
