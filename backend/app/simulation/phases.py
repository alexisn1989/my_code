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
from typing import TYPE_CHECKING, Literal

from app.core.errors import DecisionSetError
from app.core.money import BPS_DENOMINATOR, Money
from app.core.politics import trunc_div_toward_zero
from app.core.rng import derive_rng
from app.simulation.accounting import (
    compute_quarterly_interest,
    compute_tax_revenue,
    compute_total_program_spending,
    resolve_cash_and_debt,
)
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.constitution import (
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    JudicialReview,
    Legislature,
    constitution_digest,
    first_constitutional_violation,
)
from app.simulation.decisions import (
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
    InfluenceAllocation,
    bloc_relationship_investment_digest,
    budget_decision_digest,
    constitutional_amendment_decision_digest,
)
from app.simulation.government_survival import (
    ASSASSINATION_SEVERITY_THRESHOLD_BPS,
    MAX_POLLING_UNCERTAINTY_SWING_BPS,
    REQUIRED_ELECTION_SUPPORT_BPS,
    coup_attempt_risk_bps,
    coup_success_probability_bps,
    election_baseline_support_bps,
    final_election_support_bps,
    impeachment_attempt_risk_bps,
    impeachment_success_probability_bps,
    is_competitive_elected_constitution,
    is_noncompetitive_constitution,
    legislative_support_bps,
    population_weighted_mean_bps,
    resolve_transition_pressure_bps,
    transition_pressure_added_bps,
    unrest_attempt_risk_bps,
    unrest_success_probability_bps,
)
from app.simulation.labor_allocation import (
    aggregate_labor_market,
    allocate_workers,
    compute_effective_labor_force,
    compute_required_workers,
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
from app.simulation.legislature import (
    AmendmentThreshold,
    CapitalExpenditureCategory,
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.legislature import ChangeDirection as LegislativeChangeDirection
from app.simulation.legitimacy import (
    PerformanceSignals,
    assess_economic_performance,
    order_support_contribution_bps,
    resolve_legitimacy,
    resolve_political_capital,
)
from app.simulation.political_memory import (
    combine_relationship_components,
    decree_bypass_reaction_bps,
    enacted_policy_reaction_bps,
    relationship_decay_bps,
)
from app.simulation.production_accounting import compute_sector_output
from app.simulation.relationships import relationship_gain_bps
from app.simulation.report import (
    TAX_RATE_CHANGE_FIELDS,
    BlocRelationshipMemoryReport,
    BlocVoteReport,
    BudgetChangeEntry,
    CapitalExpenditureReport,
    ChamberVoteReport,
    ChangeDirection,
    ConstitutionalAmendmentConstitutionSnapshot,
    ConstitutionalAmendmentReport,
    ConstitutionalAmendmentTargetReport,
    ConstitutionSummary,
    CoupChannelReport,
    CoupUnrestReport,
    EconomicBaselineReport,
    ElectionReport,
    FinanceReport,
    ImpeachmentChannelReport,
    LaborMarketReport,
    LegislativeReport,
    PartyElectionStanceReport,
    PhaseStatus,
    PoliticalCapitalReport,
    PoliticalRelationshipReport,
    PoliticalReport,
    PopularUnrestChannelReport,
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
    LegislativeBlocState,
    LegislatureState,
    OutcomeBucket,
    PendingLiberalizationState,
    RemovalReason,
    SectorCategory,
    SpendingPlanState,
    TaxBaseState,
    TaxPolicyState,
    TerminalOutcomeState,
    VictoryReason,
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
    budget_decision_digest: str | None
    """(R8) `budget_decision_digest(decision)` over the actually-submitted `BudgetDecision`, or
    `None` for `NO_PROPOSAL` — see `LegislativeReport.budget_decision_digest`'s docstring."""


@dataclass(frozen=True, slots=True)
class AmendmentChamberTally:
    """One slot-1 amendment tally, kept report-agnostic until Gate 3C3 commit 20."""

    chamber: LegislativeChamber
    total_seats: int
    supporting_seats: int
    required_yes_seats: int
    shortfall_seats: int
    target_total: int
    extras_awarded: int
    passed: bool


@dataclass
class ConstitutionalAmendmentScratch:
    """Turn-local result of validating and resolving the amendment proposal in slot 1."""

    opening_constitution: ConstitutionState
    proposed_constitution: ConstitutionState
    outcome: LegislativeOutcome
    route: ProposalRoute | None
    chambers: tuple[AmendmentChamberTally, ...]
    political_capital_committed: int
    amendment_decision_digest: str | None
    axes_changed: int
    transition_pressure_added_bps: int
    qualifies_as_liberalization_transition: bool


@dataclass
class CapitalLedgerScratch:
    """Mutable, turn-local political-capital ledger threaded through the Phase 3B2A phases via
    `PhaseContext.capital_ledger`. Populated entirely by slot 1 (`_validate_and_reserve_actions`)
    and never mutated afterward — mirroring `LegislativeScratch` exactly.

    `total_committed` generalizes `LegislativeScratch.political_capital_committed`: where that
    field is the legislative/decree commitment alone, this is the sum of every sink a turn used,
    and it is what slot 10 spends against and what `PoliticalReport.political_capital_spent`
    ultimately records. `expenditures` is already in the canonical `(category, party_id, bloc_id)`
    order `PoliticalCapitalReport` requires, computed once here so slot 15 never recomputes it.

    (Phase 3B2B) No longer carries relationship-change detail: decay, policy reaction, decree
    bypass and investment are now computed TOGETHER, from the OPENING state, by slot 11 alone
    (§6.2's three-step validate-before-write procedure) — building a `BlocRelationshipChangeReport`
    here, before decay/policy/decree exist, would have meant either recomputing investment's share
    twice or letting slot 11 mutate a report row after the fact. `expenditures`' own
    `BLOC_RELATIONSHIP_INVESTMENT` rows remain the single source of truth for how much capital was
    committed to which bloc; slot 11 reads them directly.
    """

    expenditures: tuple[CapitalExpenditureReport, ...]
    total_committed: int


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
    constitutional_amendment_scratch: ConstitutionalAmendmentScratch | None = None
    """Set by slot 1 for every turn, committed by slot 2 on passage, and read by slot 12."""
    constitutional_amendment_report: ConstitutionalAmendmentReport | None = None
    """Assembled in slot 15 from the exact amendment scratch and submitted decision."""
    capital_ledger: CapitalLedgerScratch | None = None
    """Set by `_validate_and_reserve_actions` (slot 1); read by slot 10 (total commitment), slot
    11 (relationship application) and slot 15 (report assembly). Phase 3B2A."""
    political_capital_report: PoliticalCapitalReport | None = None
    """Set by `generate_turn_report` (slot 15) from `capital_ledger`; `resolver.py` copies this
    onto the final `TurnReport`. Phase 3B2A."""
    relationship_memory_rows: tuple[BlocRelationshipMemoryReport, ...] | None = None
    """Set by `_apply_bloc_relationship_investments` (slot 11), Phase 3B2B: every bloc's already-
    validated decay/investment/policy/decree-bypass row, in canonical `(party_id, bloc_id)` order.
    §6.2's three-step procedure constructs and validates every row BEFORE slot 11 writes anything
    to `ctx.state`, so by the time this is set, each row's own formulas have already been checked
    by Pydantic. Slot 15 wraps these SAME rows into `PoliticalRelationshipReport` — never
    recomputing them — so the report and the state provably came from identical validated values."""
    political_relationship_report: PoliticalRelationshipReport | None = None
    """Set by `generate_turn_report` (slot 15) from `relationship_memory_rows`; `resolver.py`
    copies this onto the final `TurnReport`. Phase 3B2B."""
    election_report: ElectionReport | None = None
    """Set directly by `_evaluate_elections` (slot 13, Phase 3C Gate 3C1); `resolver.py` copies
    this onto the final `TurnReport`. Unlike the legislative/capital/relationship reports, this one
    has no separate scratch object -- slot 13 both resolves the election and builds its own report
    in one function, since nothing later in the same turn needs the intermediate values."""
    coup_unrest_report: CoupUnrestReport | None = None
    """Set directly by `_evaluate_unrest_and_coup_risk` (slot 12, Phase 3C Gate 3C2); `resolver.py`
    copies this onto the final `TurnReport`. No separate scratch object, for the same reason as
    `election_report` -- slot 12 both resolves the three channels and builds its own report in one
    function."""
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


def _resolve_constitutional_amendment(
    ctx: PhaseContext,
    *,
    opening: OpeningLegislativeSnapshot,
    decision: ConstitutionalAmendmentDecision | None,
    party_ids: set[str],
    blocs_by_key: dict[tuple[str, str], LegislativeBlocState],
) -> tuple[tuple[CapitalExpenditureReport, ...], int]:
    """Resolve an amendment from opening state without mutating state (Gate 3C3, slot 1)."""
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    assert politics is not None, "checked by the caller"
    opening_constitution = politics.constitution.model_copy()

    if decision is None:
        ctx.constitutional_amendment_scratch = ConstitutionalAmendmentScratch(
            opening_constitution=opening_constitution,
            proposed_constitution=opening_constitution.model_copy(),
            outcome=LegislativeOutcome.NO_PROPOSAL,
            route=None,
            chambers=(),
            political_capital_committed=0,
            amendment_decision_digest=None,
            axes_changed=0,
            transition_pressure_added_bps=0,
            qualifies_as_liberalization_transition=False,
        )
        return (), 0

    updates: dict[str, object] = {}
    for target in decision.targets:
        opening_value = getattr(opening_constitution, target.axis)
        if target.value == opening_value:
            raise DecisionSetError(
                f"constitutional amendment target {target.axis!r} changes nothing "
                f"(opening value is {opening_value!r})"
            )
        updates[target.axis] = target.value

    trial_payload = opening_constitution.model_dump(mode="python")
    trial_payload.update(updates)
    unvalidated_trial = ConstitutionState.model_construct(**trial_payload)
    violation = first_constitutional_violation(unvalidated_trial)
    if violation is not None:
        code, message = violation
        raise DecisionSetError(
            f"constitutional amendment final constitution violates {code}: {message}"
        )
    proposed_constitution = ConstitutionState.model_validate(trial_payload)

    digest = constitutional_amendment_decision_digest(decision)
    expenditure_rows: list[CapitalExpenditureReport] = []
    chamber_tallies: tuple[AmendmentChamberTally, ...]
    commitment: int
    if decision.route is ProposalRoute.DECREE:
        if (
            opening_constitution.legislature is not Legislature.NONE
            or opening.legislature is not None
            or opening_constitution.decree_authority is not DecreeAuthority.UNLIMITED
        ):
            raise DecisionSetError(
                "constitutional amendment route=decree requires legislature='none', no "
                "LegislatureState, and decree_authority='unlimited'"
            )
        commitment = CONSTITUTIONAL_AMENDMENT_DECREE_COST
        expenditure_rows.append(
            CapitalExpenditureReport(
                category=CapitalExpenditureCategory.CONSTITUTIONAL_AMENDMENT,
                party_id=None,
                bloc_id=None,
                political_capital=commitment,
                decision_digest=digest,
            )
        )
        chamber_tallies = ()
        outcome = LegislativeOutcome.ENACTED_BY_DECREE
    else:
        legislature = opening.legislature
        if opening_constitution.legislature is Legislature.NONE or legislature is None:
            raise DecisionSetError(
                "constitutional amendment route=legislative requires a legislature"
            )

        allocation_by_key: dict[tuple[str, str], int] = {}
        for allocation in decision.influence:
            if allocation.party_id not in party_ids:
                raise DecisionSetError(
                    f"constitutional amendment influence targets unknown party "
                    f"{allocation.party_id!r}"
                )
            bloc = blocs_by_key.get((allocation.party_id, allocation.bloc_id))
            if bloc is None:
                raise DecisionSetError(
                    "constitutional amendment influence targets unknown bloc "
                    f"({allocation.party_id!r}, {allocation.bloc_id!r})"
                )
            if sum(entry.seats for entry in bloc.seats) == 0:
                raise DecisionSetError(
                    "constitutional amendment influence targets bloc "
                    f"({allocation.party_id!r}, {allocation.bloc_id!r}) which holds zero seats"
                )
            allocation_by_key[(allocation.party_id, allocation.bloc_id)] = (
                allocation.political_capital
            )

        commitment = sum(allocation_by_key.values())
        for (party_id, bloc_id), allocated in allocation_by_key.items():
            expenditure_rows.append(
                CapitalExpenditureReport(
                    category=CapitalExpenditureCategory.CONSTITUTIONAL_AMENDMENT,
                    party_id=party_id,
                    bloc_id=bloc_id,
                    political_capital=allocated,
                    decision_digest=digest,
                )
            )

        threshold = AmendmentThreshold(opening_constitution.amendment_difficulty.value)
        tallies: list[AmendmentChamberTally] = []
        for chamber_state in legislature.chambers:
            support_rows: list[SeatSupport] = []
            for party in legislature.parties:
                for bloc in party.blocs:
                    seats = next(
                        (
                            entry.seats
                            for entry in bloc.seats
                            if entry.chamber is chamber_state.chamber
                        ),
                        0,
                    )
                    if seats == 0:
                        continue
                    support = resolve_amendment_support(
                        role=party.government_role,
                        relationship_bps=bloc.government_relationship_bps,
                        discipline_bps=bloc.discipline_bps,
                        allocated_political_capital=allocation_by_key.get((party.id, bloc.id), 0),
                    )
                    support_rows.append(
                        SeatSupport(
                            party_id=party.id,
                            bloc_id=bloc.id,
                            seats=seats,
                            effective_support_bps=support.effective_support_bps,
                        )
                    )
            apportionment = apportion_supporting_seats(rows=tuple(support_rows))
            required = required_amendment_yes_seats(
                total_seats=chamber_state.total_seats, difficulty=threshold
            )
            passed = apportionment.supporting_seats >= required
            tallies.append(
                AmendmentChamberTally(
                    chamber=chamber_state.chamber,
                    total_seats=chamber_state.total_seats,
                    supporting_seats=apportionment.supporting_seats,
                    required_yes_seats=required,
                    shortfall_seats=max(0, required - apportionment.supporting_seats),
                    target_total=apportionment.supporting_seats,
                    extras_awarded=apportionment.supporting_seats
                    - sum(row.base for row in apportionment.rows),
                    passed=passed,
                )
            )
        chamber_tallies = tuple(tallies)
        outcome = (
            LegislativeOutcome.PASSED_LEGISLATIVE
            if all(tally.passed for tally in chamber_tallies)
            else LegislativeOutcome.FAILED_LEGISLATIVE
        )

    enacted = outcome in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    )
    qualifies = (
        enacted
        and is_noncompetitive_constitution(
            executive_selection=opening_constitution.executive_selection,
            decree_authority=opening_constitution.decree_authority,
        )
        and is_competitive_elected_constitution(
            executive_selection=proposed_constitution.executive_selection,
            decree_authority=proposed_constitution.decree_authority,
            national_election_interval_turns=(
                proposed_constitution.national_election_interval_turns
            ),
        )
    )
    added_pressure = (
        transition_pressure_added_bps(
            difficulty=opening_constitution.amendment_difficulty,
            axes_changed=len(decision.targets),
        )
        if enacted
        else 0
    )
    ctx.constitutional_amendment_scratch = ConstitutionalAmendmentScratch(
        opening_constitution=opening_constitution,
        proposed_constitution=proposed_constitution,
        outcome=outcome,
        route=decision.route,
        chambers=chamber_tallies,
        political_capital_committed=commitment,
        amendment_decision_digest=digest,
        axes_changed=len(decision.targets),
        transition_pressure_added_bps=added_pressure,
        qualifies_as_liberalization_transition=qualifies,
    )
    return tuple(expenditure_rows), commitment


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

    # (Phase 3B2A) `budget_decision()`/`relationship_investment_decision()`, never `decisions[0]`.
    # Canonical kind order sorts "bloc_relationship_investment" BEFORE "budget", so on a turn
    # carrying both, index 0 is the investment -- and this vote would have been held on the wrong
    # object, silently.
    budget_decision = ctx.decisions.budget_decision()
    investment_decision = ctx.decisions.relationship_investment_decision()
    amendment_decision = ctx.decisions.constitutional_amendment_decision()

    legislature = opening.legislature
    party_ids = {party.id for party in legislature.parties} if legislature is not None else set()
    blocs_by_key = (
        {(party.id, bloc.id): bloc for party in legislature.parties for bloc in party.blocs}
        if legislature is not None
        else {}
    )

    # --- relationship investment: resolved independently of the budget route (§9) -------------
    # (Phase 3B2B) Only the no-op guard and the expenditure row are built here; the actual
    # investment COMPONENT (and its combination with decay/policy/decree-bypass into one closing
    # value) is computed by slot 11 alone, from the opening state, per §6.2's three-step
    # procedure -- see `CapitalLedgerScratch`'s docstring for why that moved.
    investment_expenditure_rows: list[CapitalExpenditureReport] = []
    investment_total = 0
    if investment_decision is not None:
        investment_digest = bloc_relationship_investment_digest(investment_decision)
        for investment in investment_decision.investments:
            if investment.party_id not in party_ids:
                raise DecisionSetError(
                    f"relationship investment targets unknown party {investment.party_id!r}"
                )
            bloc = blocs_by_key.get((investment.party_id, investment.bloc_id))
            if bloc is None:
                raise DecisionSetError(
                    "relationship investment targets unknown bloc "
                    f"({investment.party_id!r}, {investment.bloc_id!r})"
                )
            opening_relationship_bps = bloc.government_relationship_bps
            gain = relationship_gain_bps(
                opening_relationship_bps=opening_relationship_bps,
                political_capital=investment.political_capital,
            )
            if gain == 0:
                # (R13) A guaranteed no-op, knowable before resolution -- not an attempted
                # political outcome that could have succeeded, so it is refused rather than
                # charged. Written against the COMPUTED gain, never against a bare `gap == 0`
                # check: truncation alone can zero out a tiny gap at low capital, and a rule
                # keyed only on the ceiling would miss that case.
                raise DecisionSetError(
                    "relationship investment in "
                    f"({investment.party_id!r}, {investment.bloc_id!r}) would have no effect: "
                    f"{investment.political_capital} capital against an opening relationship of "
                    f"{opening_relationship_bps} buys a gain of 0"
                )
            investment_expenditure_rows.append(
                CapitalExpenditureReport(
                    category=CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT,
                    party_id=investment.party_id,
                    bloc_id=investment.bloc_id,
                    political_capital=investment.political_capital,
                    decision_digest=investment_digest,
                )
            )
            investment_total += investment.political_capital

    amendment_expenditure_rows, amendment_total = _resolve_constitutional_amendment(
        ctx,
        opening=opening,
        decision=amendment_decision,
        party_ids=party_ids,
        blocs_by_key=blocs_by_key,
    )

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
            budget_decision_digest=None,
        )
        _finish_validate_and_reserve_actions(
            ctx,
            opening=opening,
            legislative_expenditure_rows=(),
            investment_expenditure_rows=tuple(investment_expenditure_rows),
            investment_total=investment_total,
            amendment_expenditure_rows=amendment_expenditure_rows,
            amendment_total=amendment_total,
        )
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

    legislative_expenditure_rows: list[CapitalExpenditureReport] = []
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
        legislative_expenditure_rows.append(
            CapitalExpenditureReport(
                category=CapitalExpenditureCategory.DECREE,
                party_id=None,
                bloc_id=None,
                political_capital=commitment,
                decision_digest=budget_decision_digest(budget_decision),
            )
        )
    else:
        legislature = opening.legislature
        assert legislature is not None, "route=legislative was already rejected above otherwise"

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
        budget_digest = budget_decision_digest(budget_decision)
        for (party_id, bloc_id), allocated in allocation_by_key.items():
            legislative_expenditure_rows.append(
                CapitalExpenditureReport(
                    category=CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE,
                    party_id=party_id,
                    bloc_id=bloc_id,
                    political_capital=allocated,
                    decision_digest=budget_digest,
                )
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
        budget_decision_digest=budget_decision_digest(budget_decision),
    )
    _finish_validate_and_reserve_actions(
        ctx,
        opening=opening,
        legislative_expenditure_rows=tuple(legislative_expenditure_rows),
        investment_expenditure_rows=tuple(investment_expenditure_rows),
        investment_total=investment_total,
        amendment_expenditure_rows=amendment_expenditure_rows,
        amendment_total=amendment_total,
    )


def _finish_validate_and_reserve_actions(
    ctx: PhaseContext,
    *,
    opening: OpeningLegislativeSnapshot,
    legislative_expenditure_rows: tuple[CapitalExpenditureReport, ...],
    investment_expenditure_rows: tuple[CapitalExpenditureReport, ...],
    investment_total: int,
    amendment_expenditure_rows: tuple[CapitalExpenditureReport, ...] = (),
    amendment_total: int = 0,
) -> None:
    """The shared tail of slot 1 (Phase 3B2A): combine the legislative/decree commitment
    `ctx.legislative_scratch` already recorded with this turn's relationship investment into one
    ledger, check the TOTAL against opening capital, and write `ctx.capital_ledger`.

    Called from both the `NO_PROPOSAL` early path and the budget-decision path, so a
    relationship-only turn and a budget-plus-investment turn go through exactly the same total-
    commitment guard rather than two independently-maintained copies of it.
    """
    assert ctx.legislative_scratch is not None, "the caller always sets this first"
    legislative_commitment = ctx.legislative_scratch.political_capital_committed
    total_committed = legislative_commitment + investment_total + amendment_total
    if total_committed > opening.political_capital:
        raise DecisionSetError(
            f"total political capital commitment {total_committed} (route commitment "
            f"{legislative_commitment} + relationship investment {investment_total} + "
            f"constitutional amendment {amendment_total}) exceeds "
            f"opening political capital {opening.political_capital}"
        )

    expenditures = tuple(
        sorted(
            (
                *legislative_expenditure_rows,
                *investment_expenditure_rows,
                *amendment_expenditure_rows,
            ),
            key=lambda row: (row.category.value, row.party_id or "", row.bloc_id or ""),
        )
    )
    ctx.capital_ledger = CapitalLedgerScratch(
        expenditures=expenditures,
        total_committed=total_committed,
    )
    ctx.mark_implemented()


def _commit_constitutional_amendment(ctx: PhaseContext) -> None:
    """Commit slot 1's successful amendment atomically in slot 2."""
    scratch = ctx.constitutional_amendment_scratch
    assert scratch is not None, "validate_and_reserve_actions always sets amendment scratch"
    if scratch.outcome not in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    ):
        return

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    assert politics is not None, "checked by check_invariants before phase execution"
    decision = ctx.decisions.constitutional_amendment_decision()
    assert decision is not None, "an enacted amendment always has a real submitted decision"

    updates: dict[str, object] = {"constitution": scratch.proposed_constitution}
    interval_target = next(
        (
            target
            for target in decision.targets
            if target.axis == "national_election_interval_turns"
        ),
        None,
    )
    if interval_target is not None:
        updates["next_election_turn"] = (
            None if interval_target.value is None else ctx.state.turn + interval_target.value
        )

    if scratch.qualifies_as_liberalization_transition:
        updates["pending_liberalization"] = PendingLiberalizationState(
            set_at_turn=ctx.state.turn,
            opening_constitution_digest=constitution_digest(scratch.opening_constitution),
            closing_constitution_digest=constitution_digest(scratch.proposed_constitution),
        )
    elif politics.pending_liberalization is not None and not is_competitive_elected_constitution(
        executive_selection=scratch.proposed_constitution.executive_selection,
        decree_authority=scratch.proposed_constitution.decree_authority,
        national_election_interval_turns=(
            scratch.proposed_constitution.national_election_interval_turns
        ),
    ):
        updates["pending_liberalization"] = None

    candidate = politics.model_copy(update=updates)
    player.politics = type(politics).model_validate(candidate.model_dump(mode="python"))


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

    budget_decision = ctx.decisions.budget_decision()
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

    # Gate 3C3: the constitution/schedule/pending-provenance write is one validated state update.
    # Transition pressure is deliberately NOT written here; slot 12 is its sole writer.
    _commit_constitutional_amendment(ctx)

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

    # (Phase 3B2A) The LEDGER total, not the legislative-only commitment: this turn may also have
    # invested in a bloc relationship, and the affordability guard (and therefore what capital
    # actually gets spent) is against the SUM of every sink, never one sink in isolation.
    capital_ledger = ctx.capital_ledger
    assert capital_ledger is not None, "validate_and_reserve_actions always runs first"
    political_capital_committed = capital_ledger.total_committed

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


def _apply_bloc_relationship_investments(ctx: PhaseContext) -> None:
    """Phase 3B2A/3B2B, slot 11 (`update_institutional_loyalty_competence_corruption_power`):
    apply this turn's relationship memory to `politics.legislature`.

    **The semantically correct home for this, not a scheduling convenience.** It runs after the
    vote (slot 1, which already scored every bloc against the OPENING relationship) and after
    capital resolution (slot 10, which already spent against the ledger total) — exactly the
    ordering §9 requires, so investment (or decay, or a policy reaction, or a decree-bypass
    penalty) can never retroactively affect the vote it was committed alongside.
    `government_relationship_bps` is a caucus's loyalty to the government; this slot's registered
    name is literally "institutional loyalty ... power". No 16th `PHASE_ORDER` slot.

    `politics.legislature` gains its ONLY writer here (D7's staticness held through Phase 3B1
    precisely because nothing wrote it; 3B2A/3B2B end that, deliberately, in exactly one place). A
    turn with no relationship memory to record leaves `legislature` byte-identical — this function
    still runs and still calls `mark_implemented()`, matching every other slot's "implemented
    means the phase has real logic, not that this turn happened to use it" rule.

    **§6.2's three-step validate-before-write procedure, exactly:**

    1. **Compute.** For every bloc that needs a row (§8's row-coverage rule: a nonzero opening
       deviation, an investment target, or — because policy/decree facts are report-level, not
       per-bloc — every authored bloc whenever the outcome enacted a proposal), compute all four
       components from the OPENING legislature's values alone, then one sum and one clamp
       (`political_memory.combine_relationship_components`).
    2. **Validate.** Construct the corresponding `BlocRelationshipMemoryReport` row from those
       computed values. Pydantic validation runs here, on real data, for every row, before
       anything is written to `ctx.state` — a formula bug raises immediately and the whole turn
       is discarded by `resolve_turn`'s existing atomic-failure handling, exactly like any other
       report-construction site in this module.
    3. **Write.** Only after every row has validated does this function write
       `closing_relationship_bps` into state, and only from each row's OWN validated field —
       never from the raw values computed in step 1 directly (M8's discipline, preserved).

    Slot 15 does not repeat this work: it wraps these SAME validated rows
    (`ctx.relationship_memory_rows`) into `PoliticalRelationshipReport`, so the report and the
    state provably came from identical values, never two independent computations that could
    drift apart.
    """
    capital_ledger = ctx.capital_ledger
    assert capital_ledger is not None, "validate_and_reserve_actions always runs first"
    legislative_scratch = ctx.legislative_scratch
    assert legislative_scratch is not None, "validate_and_reserve_actions always runs first"

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    assert politics is not None, "checked by check_invariants before resolve_turn runs"
    legislature = politics.legislature

    memory_rows: list[BlocRelationshipMemoryReport] = []

    if legislature is not None:
        investment_by_key = {
            (row.party_id, row.bloc_id): row.political_capital
            for row in capital_ledger.expenditures
            if row.category is CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT
        }
        outcome = legislative_scratch.outcome
        policy_enacted = outcome in (
            LegislativeOutcome.PASSED_LEGISLATIVE,
            LegislativeOutcome.ENACTED_BY_DECREE,
        )
        decree_bypass_active = (
            outcome is LegislativeOutcome.ENACTED_BY_DECREE
            and legislative_scratch.legislature_present
        )

        # --- 1. Compute, from the OPENING legislature alone -- nothing above has mutated it. ----
        for party in legislature.parties:
            for bloc in party.blocs:
                key = (party.id, bloc.id)
                opening_relationship_bps = bloc.government_relationship_bps
                baseline_relationship_bps = bloc.baseline_government_relationship_bps
                opening_deviation_bps = opening_relationship_bps - baseline_relationship_bps
                investment_capital = investment_by_key.get(key, 0)

                if not (opening_deviation_bps != 0 or investment_capital > 0 or policy_enacted):
                    continue  # §8 row-coverage: this bloc needs no row on this turn.

                decay_component_bps = relationship_decay_bps(
                    opening_relationship_bps=opening_relationship_bps,
                    baseline_relationship_bps=baseline_relationship_bps,
                )
                investment_component_bps = (
                    relationship_gain_bps(
                        opening_relationship_bps=opening_relationship_bps,
                        political_capital=investment_capital,
                    )
                    if investment_capital > 0
                    else 0
                )
                policy_reaction_component_bps = (
                    enacted_policy_reaction_bps(
                        tax_preference_bps=bloc.tax_preference_bps,
                        tax_direction=legislative_scratch.tax_direction,
                        tax_intensity_bps=legislative_scratch.tax_intensity_bps,
                        spending_preference_bps=bloc.spending_preference_bps,
                        spending_direction=legislative_scratch.spending_direction,
                        spending_intensity_bps=legislative_scratch.spending_intensity_bps,
                    )
                    if policy_enacted
                    else 0
                )
                is_seated = sum(entry.seats for entry in bloc.seats) > 0
                decree_bypass_component_bps = (
                    decree_bypass_reaction_bps(is_seated_bloc=is_seated)
                    if decree_bypass_active
                    else 0
                )
                uncapped_total_change_bps, applied_total_change_bps, closing_relationship_bps = (
                    combine_relationship_components(
                        opening_relationship_bps=opening_relationship_bps,
                        decay_component_bps=decay_component_bps,
                        investment_component_bps=investment_component_bps,
                        policy_reaction_component_bps=policy_reaction_component_bps,
                        decree_bypass_component_bps=decree_bypass_component_bps,
                    )
                )

                # --- 2. Validate: constructing the row runs every self-validator now, on real ----
                # data, before step 3 ever touches `ctx.state`.
                memory_rows.append(
                    BlocRelationshipMemoryReport(
                        party_id=party.id,
                        bloc_id=bloc.id,
                        baseline_relationship_bps=baseline_relationship_bps,
                        opening_relationship_bps=opening_relationship_bps,
                        opening_deviation_bps=opening_deviation_bps,
                        decay_component_bps=decay_component_bps,
                        investment_component_bps=investment_component_bps,
                        investment_capital=investment_capital,
                        tax_preference_bps=bloc.tax_preference_bps,
                        spending_preference_bps=bloc.spending_preference_bps,
                        policy_reaction_component_bps=policy_reaction_component_bps,
                        decree_bypass_component_bps=decree_bypass_component_bps,
                        uncapped_total_change_bps=uncapped_total_change_bps,
                        applied_total_change_bps=applied_total_change_bps,
                        closing_relationship_bps=closing_relationship_bps,
                    )
                )

        memory_rows.sort(key=lambda row: (row.party_id, row.bloc_id))

        # --- 3. Write, only from each row's OWN validated field, only after every row validated. -
        if memory_rows:
            closing_by_key = {
                (row.party_id, row.bloc_id): row.closing_relationship_bps for row in memory_rows
            }
            updated_parties = []
            for party in legislature.parties:
                updated_blocs = []
                party_changed = False
                for bloc in party.blocs:
                    new_relationship = closing_by_key.get((party.id, bloc.id))
                    if new_relationship is None:
                        updated_blocs.append(bloc)
                        continue
                    updated_blocs.append(
                        bloc.model_copy(update={"government_relationship_bps": new_relationship})
                    )
                    party_changed = True
                updated_parties.append(
                    party.model_copy(update={"blocs": tuple(updated_blocs)})
                    if party_changed
                    else party
                )

            player.politics = politics.model_copy(
                update={
                    "legislature": legislature.model_copy(
                        update={"parties": tuple(updated_parties)}
                    )
                }
            )

    ctx.relationship_memory_rows = tuple(memory_rows)
    ctx.mark_implemented()


def _opposition_seat_share_bps(legislature: LegislatureState | None) -> int | None:
    """The share of LOWER-chamber seats held by OPPOSITION-role parties alone -- excludes
    `CONFIDENCE_AND_SUPPLY` blocs, which are not the coup/impeachment formulas' notion of a
    genuinely hostile bloc. `None` when no legislature exists at all, the same "nothing to read"
    treatment `election_baseline_support_bps` gives a missing legislature."""
    if legislature is None:
        return None
    lower_chamber = next(
        chamber_state
        for chamber_state in legislature.chambers
        if chamber_state.chamber == LegislativeChamber.LOWER
    )
    opposition_seats = sum(
        seat_entry.seats
        for party in legislature.parties
        if party.government_role == GovernmentRole.OPPOSITION
        for bloc in party.blocs
        for seat_entry in bloc.seats
        if seat_entry.chamber == LegislativeChamber.LOWER
    )
    return trunc_div_toward_zero(opposition_seats * BPS_DENOMINATOR, lower_chamber.total_seats)


def _evaluate_unrest_and_coup_risk(ctx: PhaseContext) -> None:  # noqa: C901
    """Phase 3C, Gate 3C2, slot 12 (`evaluate_protests_strikes_insurgency_coups_revolutions`):
    resolve this turn's coup, popular-unrest, and impeachment risk (§3.1-3.3/§4.1).

    Runs after slots 10/11 (legitimacy, capital, relationship investment/decay) have already
    mutated `ctx.state` this same turn -- every risk assessment reads the CURRENT (post-slot-11)
    legitimacy and legislature, per the same R7 ordering rule `_evaluate_elections` documents.
    `InstitutionState`/`PopulationGroupState` are untouched by every slot before this one, so
    reading them here is equivalent to reading them from either the turn's opening or closing
    state.

    `regime_transition_pressure_bps` is resolved here, and ONLY here (R6) -- reading this turn's
    OPENING pressure value (nothing before this slot ever writes it, so `politics`'s current value
    IS the opening value) plus whatever a successfully enacted `ConstitutionalAmendmentDecision`
    added this turn, carried from slot 1 without any earlier phase writing the pressure field.

    All three channels' full risk assessment and RNG draw sequence always run, regardless of
    whether an earlier channel (in the fixed coup -> popular_unrest -> impeachment priority order)
    already produced a removal this turn -- a later channel's draws must never depend on whether
    an earlier one fired. Only the FIRST channel (in that order) to succeed writes
    `politics.terminal_outcome`.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    assert politics is not None, "checked by check_invariants before resolve_turn runs"
    assert politics.terminal_outcome is None, "resolve_turn already refuses a concluded game"

    constitution = politics.constitution
    legitimacy = politics.legitimacy_bps
    legislature = politics.legislature

    amendment_scratch = ctx.constitutional_amendment_scratch
    assert amendment_scratch is not None, "slot 1 always sets amendment scratch"
    pressure_resolution = resolve_transition_pressure_bps(
        opening_pressure_bps=politics.regime_transition_pressure_bps,
        amendment_added_bps=amendment_scratch.transition_pressure_added_bps,
    )

    opposition_seat_share_bps = _opposition_seat_share_bps(legislature)
    military = next(row for row in player.institutions if row.id == "military")

    # --- Coup channel -------------------------------------------------------------------------
    coup_risk = coup_attempt_risk_bps(
        military_loyalty_bps=military.loyalty,
        military_power_bps=military.power,
        legitimacy_bps=legitimacy,
        opposition_seat_share_bps=opposition_seat_share_bps,
        transition_pressure_bps=pressure_resolution.closing_bps,
    )
    coup_attempted = (
        ctx.rng("coup_attempt").randint(1, BPS_DENOMINATOR) <= coup_risk.attempt_risk_bps
    )
    coup_success_probability: int | None = None
    coup_succeeded: bool | None = None
    if coup_attempted:
        coup_success_probability = coup_success_probability_bps(
            military_power_bps=military.power,
            military_competence_bps=military.competence,
            legitimacy_bps=legitimacy,
        )
        coup_succeeded = (
            ctx.rng("coup_outcome").randint(1, BPS_DENOMINATOR) <= coup_success_probability
        )

    # --- Popular-unrest channel ----------------------------------------------------------------
    radicalization_bps = population_weighted_mean_bps(
        shares_and_metrics=tuple(
            (round(group.population_share * BPS_DENOMINATOR), group.radicalization)
            for group in player.population_groups
        )
    )
    organization_bps = population_weighted_mean_bps(
        shares_and_metrics=tuple(
            (round(group.population_share * BPS_DENOMINATOR), group.organization)
            for group in player.population_groups
        )
    )
    disapproval_bps = population_weighted_mean_bps(
        shares_and_metrics=tuple(
            (round(group.population_share * BPS_DENOMINATOR), BPS_DENOMINATOR - group.approval)
            for group in player.population_groups
        )
    )
    unrest_risk = unrest_attempt_risk_bps(
        radicalization_bps=radicalization_bps,
        organization_bps=organization_bps,
        disapproval_bps=disapproval_bps,
    )
    unrest_attempted = (
        ctx.rng("unrest_attempt").randint(1, BPS_DENOMINATOR) <= unrest_risk.attempt_risk_bps
    )
    unrest_success_probability: int | None = None
    unrest_succeeded: bool | None = None
    unrest_outcome: Literal["none", "contained", "forced_abdication", "assassination"] = "none"
    if unrest_attempted:
        unrest_success_probability = unrest_success_probability_bps(
            organization_bps=organization_bps, legitimacy_bps=legitimacy
        )
        unrest_succeeded = (
            ctx.rng("unrest_outcome").randint(1, BPS_DENOMINATOR) <= unrest_success_probability
        )
        if unrest_succeeded:
            severity_draw = ctx.rng("unrest_severity").randint(1, BPS_DENOMINATOR)
            unrest_outcome = (
                "assassination"
                if severity_draw <= ASSASSINATION_SEVERITY_THRESHOLD_BPS
                else "forced_abdication"
            )
        else:
            unrest_outcome = "contained"

    # --- Impeachment channel -------------------------------------------------------------------
    impeachment_eligible = (
        constitution.legislature is not Legislature.NONE
        and constitution.judicial_review is not JudicialReview.NONE
        and constitution.executive_selection is not ExecutiveSelection.HEREDITARY
    )
    impeachment_legitimacy_contribution: int | None = None
    impeachment_opposition_contribution: int | None = None
    impeachment_attempt_risk_value: int | None = None
    impeachment_attempted: bool | None = None
    impeachment_success_probability: int | None = None
    impeachment_succeeded: bool | None = None
    if impeachment_eligible:
        assert opposition_seat_share_bps is not None, (
            "impeachment eligibility requires a legislature, which requires a seat share"
        )
        impeachment_risk = impeachment_attempt_risk_bps(
            opposition_seat_share_bps=opposition_seat_share_bps,
            legitimacy_bps=legitimacy,
            judicial_review=constitution.judicial_review,
        )
        impeachment_legitimacy_contribution = impeachment_risk.legitimacy_contribution_bps
        impeachment_opposition_contribution = impeachment_risk.opposition_contribution_bps
        impeachment_attempt_risk_value = impeachment_risk.attempt_risk_bps
        impeachment_attempted = (
            ctx.rng("impeachment_attempt").randint(1, BPS_DENOMINATOR)
            <= impeachment_attempt_risk_value
        )
        if impeachment_attempted:
            impeachment_success_probability = impeachment_success_probability_bps(
                opposition_seat_share_bps=opposition_seat_share_bps, legitimacy_bps=legitimacy
            )
            impeachment_succeeded = (
                ctx.rng("impeachment_outcome").randint(1, BPS_DENOMINATOR)
                <= impeachment_success_probability
            )

    # --- Fixed priority order: coup, then popular unrest, then impeachment ---------------------
    removal_reason: RemovalReason | None
    if coup_succeeded:
        removal_reason = RemovalReason.COUP
    elif unrest_succeeded:
        removal_reason = (
            RemovalReason.ASSASSINATION
            if unrest_outcome == "assassination"
            else RemovalReason.FORCED_ABDICATION
        )
    elif impeachment_succeeded:
        removal_reason = RemovalReason.IMPEACHMENT
    else:
        removal_reason = None

    politics_update: dict[str, object] = {
        "regime_transition_pressure_bps": pressure_resolution.closing_bps
    }
    if removal_reason is not None:
        politics_update["terminal_outcome"] = TerminalOutcomeState(
            bucket=OutcomeBucket.DEFEAT, removal_reason=removal_reason, turn=ctx.state.turn
        )
    player.politics = politics.model_copy(update=politics_update)

    ctx.coup_unrest_report = CoupUnrestReport(
        coup=CoupChannelReport(
            military_loyalty_bps=military.loyalty,
            military_power_bps=military.power,
            military_competence_bps=military.competence,
            legitimacy_bps=legitimacy,
            loyalty_contribution_bps=coup_risk.loyalty_contribution_bps,
            legitimacy_contribution_bps=coup_risk.legitimacy_contribution_bps,
            opposition_contribution_bps=coup_risk.opposition_contribution_bps,
            transition_pressure_contribution_bps=coup_risk.transition_pressure_contribution_bps,
            attempt_risk_bps=coup_risk.attempt_risk_bps,
            attempted=coup_attempted,
            success_probability_bps=coup_success_probability,
            succeeded=coup_succeeded,
        ),
        popular_unrest=PopularUnrestChannelReport(
            radicalization_bps=radicalization_bps,
            organization_bps=organization_bps,
            disapproval_bps=disapproval_bps,
            legitimacy_bps=legitimacy,
            radicalization_contribution_bps=unrest_risk.radicalization_contribution_bps,
            disapproval_contribution_bps=unrest_risk.disapproval_contribution_bps,
            attempt_risk_bps=unrest_risk.attempt_risk_bps,
            attempted=unrest_attempted,
            success_probability_bps=unrest_success_probability,
            succeeded=unrest_succeeded,
            outcome=unrest_outcome,
        ),
        impeachment=ImpeachmentChannelReport(
            eligible=impeachment_eligible,
            legitimacy_bps=legitimacy if impeachment_eligible else None,
            opposition_seat_share_bps=(opposition_seat_share_bps if impeachment_eligible else None),
            legitimacy_contribution_bps=impeachment_legitimacy_contribution,
            opposition_contribution_bps=impeachment_opposition_contribution,
            attempt_risk_bps=impeachment_attempt_risk_value,
            attempted=impeachment_attempted,
            success_probability_bps=impeachment_success_probability,
            succeeded=impeachment_succeeded,
        ),
        removal_triggered=removal_reason,
        opening_transition_pressure_bps=pressure_resolution.opening_bps,
        decayed_transition_pressure_bps=pressure_resolution.decayed_bps,
        added_transition_pressure_bps=pressure_resolution.added_bps,
        closing_transition_pressure_bps=pressure_resolution.closing_bps,
    )

    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="coup_risk_assessed",
            params={
                "coup_attempt_risk_bps": coup_risk.attempt_risk_bps,
                "unrest_attempt_risk_bps": unrest_risk.attempt_risk_bps,
                "impeachment_eligible": impeachment_eligible,
                "impeachment_attempt_risk_bps": impeachment_attempt_risk_value or 0,
            },
        )
    )
    if coup_attempted:
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="coup_attempt_occurred",
                params={"attempt_risk_bps": coup_risk.attempt_risk_bps},
            )
        )
    if coup_succeeded:
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="coup_succeeded",
                params={"success_probability_bps": coup_success_probability or 0},
            )
        )
    if unrest_outcome != "none":
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="popular_unrest_occurred",
                params={"outcome": unrest_outcome},
            )
        )
    if impeachment_attempted:
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="impeachment_motion_brought",
                params={"attempt_risk_bps": impeachment_attempt_risk_value or 0},
            )
        )
    if impeachment_succeeded:
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="impeachment_succeeded",
                params={"success_probability_bps": impeachment_success_probability or 0},
            )
        )
    if removal_reason is not None:
        ctx.report_entries.append(
            TurnReportEntry(
                category="administration",
                reason_id="game_concluded",
                params={
                    "bucket": OutcomeBucket.DEFEAT.value,
                    "reason": removal_reason.value,
                    "turn": ctx.state.turn,
                },
            )
        )

    ctx.mark_implemented()


def _evaluate_elections(ctx: PhaseContext) -> None:  # noqa: C901
    """Phase 3C, Gate 3C1, slot 13 (`evaluate_elections_and_constitutional_events`): resolve this
    turn's scheduled election, if any (§4.2/§4.4).

    Runs after slots 10/11 (legitimacy, capital, relationship investment/decay) have already
    mutated `ctx.state` this same turn -- support is scored against the CURRENT (post-slot-11)
    legislature and legitimacy, per the R7 ordering rule: there is no analogous "same-turn buy"
    loophole here the way there is for the budget vote (slot 1 scores against the OPENING
    relationship precisely so this turn's investment cannot buy the vote it is used in) -- nothing
    in this slot can retroactively cheapen itself using this turn's own legitimacy/relationship
    resolution.

    A liberalization victory requires a pending marker persisted before this resolving turn; a
    qualifying amendment committed by slot 2 on the same turn cannot immediately certify itself.
    """
    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    politics = player.politics
    assert politics is not None, "checked by check_invariants before resolve_turn runs"

    if politics.terminal_outcome is not None:
        ctx.election_report = ElectionReport(
            scheduled=False,
            eligible_to_stand=False,
            consecutive_terms_held=politics.consecutive_terms_held,
            executive_term_limit_terms=politics.constitution.executive_term_limit_terms,
            legislative_support_contribution_bps=None,
            population_approval_contribution_bps=0,
            legitimacy_contribution_bps=0,
            baseline_support_bps=0,
            polling_uncertainty_bps=0,
            final_support_bps=0,
            required_support_bps=0,
            result="not_scheduled",
            liberalization_completed=False,
            next_election_turn=politics.next_election_turn,
            parties=(),
        )
        ctx.mark_implemented()
        return

    scheduled = politics.next_election_turn == ctx.state.turn
    if not scheduled:
        ctx.election_report = ElectionReport(
            scheduled=False,
            eligible_to_stand=False,
            consecutive_terms_held=politics.consecutive_terms_held,
            executive_term_limit_terms=politics.constitution.executive_term_limit_terms,
            legislative_support_contribution_bps=None,
            population_approval_contribution_bps=0,
            legitimacy_contribution_bps=0,
            baseline_support_bps=0,
            polling_uncertainty_bps=0,
            final_support_bps=0,
            required_support_bps=0,
            result="not_scheduled",
            liberalization_completed=False,
            next_election_turn=politics.next_election_turn,
            parties=(),
        )
        ctx.mark_implemented()
        return

    term_limit = politics.constitution.executive_term_limit_terms
    term_limited = term_limit is not None and politics.consecutive_terms_held >= term_limit

    # §3.4/§13's worked example (tiny_valid: lower chamber alone = 5,310, feeding a baseline of
    # 5,487) reads confidence from the LOWER chamber only, never a seat-weighted blend across
    # chambers -- LegislativeChamber.LOWER is, by the enum's own convention, "the sole chamber of
    # a unicameral legislature" (legislature.py), so this one rule covers both shapes uniformly:
    # a unicameral legislature's only chamber IS its lower chamber.
    legislature = politics.legislature
    if legislature is not None:
        lower_chamber = next(
            chamber_state
            for chamber_state in legislature.chambers
            if chamber_state.chamber == LegislativeChamber.LOWER
        )
        lower_pairs = tuple(
            (seat_entry.seats, bloc.government_relationship_bps)
            for party in legislature.parties
            for bloc in party.blocs
            for seat_entry in bloc.seats
            if seat_entry.chamber == LegislativeChamber.LOWER
        )
        legislative_support = (
            legislative_support_bps(
                bloc_seats_and_relationships=lower_pairs, total_seats=lower_chamber.total_seats
            )
            if lower_pairs
            else None
        )
    else:
        legislative_support = None

    population_approval = population_weighted_mean_bps(
        shares_and_metrics=tuple(
            (round(group.population_share * BPS_DENOMINATOR), group.approval)
            for group in player.population_groups
        )
    )
    assessment = election_baseline_support_bps(
        legislative_support_bps=legislative_support,
        population_approval_bps=population_approval,
        legitimacy_bps=politics.legitimacy_bps,
    )

    result: Literal["not_scheduled", "term_limit_exit", "won", "lost"]
    if term_limited:
        result = "term_limit_exit"
        polling_swing = 0
        final_support = assessment.baseline_support_bps
        eligible_to_stand = False
        parties: tuple[PartyElectionStanceReport, ...] = ()
        new_terminal_outcome = TerminalOutcomeState(
            bucket=OutcomeBucket.DEFEAT,
            removal_reason=RemovalReason.TERM_LIMIT_EXIT,
            turn=ctx.state.turn,
        )
        new_next_election_turn = politics.next_election_turn  # frozen -- never read again
        new_terms_held = politics.consecutive_terms_held
        liberalization_completed = False
        new_pending_liberalization = politics.pending_liberalization
    else:
        eligible_to_stand = True
        polling_swing = ctx.rng("election").randint(
            -MAX_POLLING_UNCERTAINTY_SWING_BPS, MAX_POLLING_UNCERTAINTY_SWING_BPS
        )
        final_support = final_election_support_bps(
            baseline_support_bps=assessment.baseline_support_bps, polling_swing_bps=polling_swing
        )
        won = final_support >= REQUIRED_ELECTION_SUPPORT_BPS
        result = "won" if won else "lost"
        liberalization_completed = False
        party_rows = []
        if legislature is not None:
            lower_total_seats = next(
                chamber_state.total_seats
                for chamber_state in legislature.chambers
                if chamber_state.chamber == LegislativeChamber.LOWER
            )
            for party in legislature.parties:
                seats = sum(
                    seat_entry.seats
                    for bloc in party.blocs
                    for seat_entry in bloc.seats
                    if seat_entry.chamber == LegislativeChamber.LOWER
                )
                total_seats = lower_total_seats
                # Support-space, not raw relationship: the SAME (relationship_bps + 10,000) // 2
                # rescale legislative_support_bps applies per bloc, so this field genuinely lives
                # in [0, 10,000] as StrictRiskBps declares, consistent with what actually decided
                # the election (the lower chamber alone, per the fix above).
                weighted = sum(
                    seat_entry.seats
                    * trunc_div_toward_zero(bloc.government_relationship_bps + BPS_DENOMINATOR, 2)
                    for bloc in party.blocs
                    for seat_entry in bloc.seats
                    if seat_entry.chamber == LegislativeChamber.LOWER
                )
                relationship_weighted_support_bps = (
                    trunc_div_toward_zero(weighted, seats) if seats > 0 else 0
                )
                party_rows.append(
                    PartyElectionStanceReport(
                        party_id=party.id,
                        government_role=party.government_role,
                        seats=seats,
                        total_seats=total_seats,
                        relationship_weighted_support_bps=relationship_weighted_support_bps,
                    )
                )
        parties = tuple(party_rows)

        if won:
            new_terms_held = politics.consecutive_terms_held + 1
            pending = politics.pending_liberalization
            liberalization_completed = pending is not None and pending.set_at_turn < ctx.state.turn
            if liberalization_completed:
                new_next_election_turn = politics.next_election_turn
                new_terminal_outcome = TerminalOutcomeState(
                    bucket=OutcomeBucket.VICTORY,
                    victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
                    turn=ctx.state.turn,
                )
                new_pending_liberalization = None
            else:
                interval = politics.constitution.national_election_interval_turns
                assert interval is not None, "a scheduled election requires an authored interval"
                new_next_election_turn = ctx.state.turn + interval
                new_terminal_outcome = None
                new_pending_liberalization = pending
        else:
            new_terms_held = politics.consecutive_terms_held
            new_next_election_turn = politics.next_election_turn  # frozen -- never read again
            new_terminal_outcome = TerminalOutcomeState(
                bucket=OutcomeBucket.DEFEAT,
                removal_reason=RemovalReason.ELECTORAL_DEFEAT,
                turn=ctx.state.turn,
            )
            new_pending_liberalization = None

    player.politics = politics.model_copy(
        update={
            "consecutive_terms_held": new_terms_held,
            "next_election_turn": new_next_election_turn,
            "terminal_outcome": new_terminal_outcome,
            "pending_liberalization": new_pending_liberalization,
        }
    )

    ctx.election_report = ElectionReport(
        scheduled=True,
        eligible_to_stand=eligible_to_stand,
        consecutive_terms_held=politics.consecutive_terms_held,
        executive_term_limit_terms=term_limit,
        legislative_support_contribution_bps=assessment.legislative_support_bps,
        population_approval_contribution_bps=assessment.population_approval_bps,
        legitimacy_contribution_bps=assessment.legitimacy_bps,
        baseline_support_bps=assessment.baseline_support_bps,
        polling_uncertainty_bps=polling_swing,
        final_support_bps=final_support,
        required_support_bps=0 if term_limited else REQUIRED_ELECTION_SUPPORT_BPS,
        result=result,
        liberalization_completed=liberalization_completed,
        next_election_turn=new_next_election_turn,
        parties=parties,
    )

    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="election_scheduled",
            params={"turn": ctx.state.turn, "eligible_to_stand": eligible_to_stand},
        )
    )
    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="election_result",
            params={
                "result": result,
                "final_support_bps": final_support,
                "required_support_bps": 0 if term_limited else REQUIRED_ELECTION_SUPPORT_BPS,
            },
        )
    )
    if new_terminal_outcome is not None:
        reason = new_terminal_outcome.victory_reason or new_terminal_outcome.removal_reason
        assert reason is not None
        ctx.report_entries.append(
            TurnReportEntry(
                category="administration",
                reason_id="game_concluded",
                params={
                    "bucket": new_terminal_outcome.bucket.value,
                    "reason": reason.value,
                    "turn": new_terminal_outcome.turn,
                },
            )
        )

    ctx.mark_implemented()


def _generate_turn_report(ctx: PhaseContext) -> None:
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
        budget_decision_digest=legislative_scratch.budget_decision_digest,
    )
    _append_legislative_report_entries(ctx, ctx.legislative_report)

    amendment_scratch = ctx.constitutional_amendment_scratch
    assert amendment_scratch is not None, "validate_and_reserve_actions always runs first"
    amendment_decision = ctx.decisions.constitutional_amendment_decision()
    enacted_amendment = amendment_scratch.outcome in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    )
    closing_constitution = (
        amendment_scratch.proposed_constitution
        if enacted_amendment
        else amendment_scratch.opening_constitution
    )

    def amendment_snapshot(
        constitution: ConstitutionState,
    ) -> ConstitutionalAmendmentConstitutionSnapshot:
        return ConstitutionalAmendmentConstitutionSnapshot(
            decree_authority=constitution.decree_authority,
            executive_selection=constitution.executive_selection,
            executive_system=constitution.executive_system,
            executive_term_limit_terms=constitution.executive_term_limit_terms,
            national_election_interval_turns=constitution.national_election_interval_turns,
            amendment_difficulty=constitution.amendment_difficulty,
        )

    target_rows: tuple[ConstitutionalAmendmentTargetReport, ...] = ()
    influence: tuple[InfluenceAllocation, ...] = ()
    if amendment_decision is not None:

        def json_value(value: object) -> str:
            if value is None:
                return "null"
            enum_value = getattr(value, "value", None)
            return str(enum_value if enum_value is not None else value)

        target_rows = tuple(
            ConstitutionalAmendmentTargetReport(
                axis=target.axis,
                opening_value=json_value(
                    getattr(amendment_scratch.opening_constitution, target.axis)
                ),
                proposed_value=json_value(target.value),
            )
            for target in amendment_decision.targets
        )
        influence = amendment_decision.influence
    ctx.constitutional_amendment_report = ConstitutionalAmendmentReport(
        proposed=amendment_decision is not None,
        outcome=amendment_scratch.outcome,
        route=amendment_scratch.route,
        targets=target_rows,
        chambers=tuple(
            ChamberVoteReport(
                chamber=row.chamber,
                total_seats=row.total_seats,
                supporting_seats=row.supporting_seats,
                required_yes_seats=row.required_yes_seats,
                shortfall_seats=row.shortfall_seats,
                target_total=row.target_total,
                extras_awarded=row.extras_awarded,
                passed=row.passed,
            )
            for row in amendment_scratch.chambers
        ),
        influence=influence,
        political_capital_committed=amendment_scratch.political_capital_committed,
        amendment_decision_digest=amendment_scratch.amendment_decision_digest,
        opening_constitution=amendment_snapshot(amendment_scratch.opening_constitution),
        closing_constitution=amendment_snapshot(closing_constitution),
        opening_constitution_digest=constitution_digest(amendment_scratch.opening_constitution),
        closing_constitution_digest=constitution_digest(closing_constitution),
        transition_pressure_added_bps=amendment_scratch.transition_pressure_added_bps,
        qualifies_as_liberalization_transition=(
            amendment_scratch.qualifies_as_liberalization_transition
        ),
    )

    capital_ledger = ctx.capital_ledger
    assert capital_ledger is not None, "validate_and_reserve_actions always runs first"
    political_report = ctx.political_report
    assert political_report is not None, "update_legitimacy_and_political_capital always runs first"
    ctx.political_capital_report = PoliticalCapitalReport(
        opening_political_capital=political_report.opening_political_capital,
        political_capital_regeneration=political_report.political_capital_regeneration,
        political_capital_capacity=political_report.political_capital_capacity,
        total_committed=capital_ledger.total_committed,
        closing_political_capital=political_report.closing_political_capital,
        expenditures=capital_ledger.expenditures,
    )
    _append_capital_ledger_report_entries(ctx, ctx.political_capital_report)

    # (Phase 3B2B) Wraps slot 11's already-validated rows -- never recomputed here -- into the
    # ninth top-level report.
    relationship_memory_rows = ctx.relationship_memory_rows
    assert relationship_memory_rows is not None, (
        "apply_bloc_relationship_investments always runs first"
    )
    ctx.political_relationship_report = PoliticalRelationshipReport(
        outcome=legislative_scratch.outcome,
        legislature_present=legislative_scratch.legislature_present,
        tax_direction=legislative_scratch.tax_direction,
        tax_intensity_bps=legislative_scratch.tax_intensity_bps,
        spending_direction=legislative_scratch.spending_direction,
        spending_intensity_bps=legislative_scratch.spending_intensity_bps,
        blocs=relationship_memory_rows,
    )
    _append_political_relationship_report_entries(ctx, ctx.political_relationship_report)

    # (Phase 3B1) Appended LAST, after every other phase and after this slot's own legislative
    # entries, so `turn_resolved` stays the final line of every report exactly as it was before
    # Phase 3B1 -- it closes the turn, so nothing may follow it.
    ctx.report_entries.append(
        TurnReportEntry(
            category="administration",
            reason_id="turn_resolved",
            params={"turn": ctx.resolving_turn},
        )
    )

    ctx.mark_implemented()


def _append_legislative_report_entries(ctx: PhaseContext, report: LegislativeReport) -> None:
    """(Phase 3B1, §14) The two approved legislative reason IDs, derived from the
    already-constructed, already-self-validated `LegislativeReport` rather than from the scratch —
    so a reason payload can never describe a vote the report itself does not.

    `NO_PROPOSAL` emits nothing: no proposal was made, so there is no vote to report and no
    chamber to have blocked one. (An invalid or constitutionally unavailable route never reaches
    here at all — slot 1 raises `DecisionSetError` and the whole turn aborts before any report
    exists, so it likewise has no reason ID.)

    Payloads carry only stable ids, enum *values* and integers — never prose. Rendering them into
    English is `app.cli.REASON_RENDERERS`' job alone (report.py's module docstring: report text
    lives inside hash-protected history and could never be re-rendered otherwise).
    """
    if report.outcome is LegislativeOutcome.NO_PROPOSAL:
        return

    assert report.route is not None, "every non-NO_PROPOSAL outcome carries a route"
    # For a decree these are all zero by construction: `chambers` is empty, because no chamber
    # voted. The renderer says so explicitly rather than printing a bare "0 of 0 chambers".
    ctx.report_entries.append(
        TurnReportEntry(
            category="politics",
            reason_id="legislative_vote_resolved",
            params={
                "route": report.route.value,
                "outcome": report.outcome.value,
                "chambers_passed": sum(1 for chamber in report.chambers if chamber.passed),
                "chambers_total": len(report.chambers),
                "supporting_seats": sum(chamber.supporting_seats for chamber in report.chambers),
                "required_yes_seats": sum(
                    chamber.required_yes_seats for chamber in report.chambers
                ),
                "political_capital_committed": report.political_capital_committed,
            },
        )
    )

    # One entry per chamber that actually blocked the budget — never one summary entry for "the
    # legislature", because in a bicameral legislature each chamber blocks (or does not) on its
    # own, and a single pooled entry could not say which one did.
    for chamber in report.chambers:
        if chamber.passed:
            continue
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="budget_blocked_by_legislature",
                params={
                    "chamber": chamber.chamber.value,
                    "supporting_seats": chamber.supporting_seats,
                    "required_yes_seats": chamber.required_yes_seats,
                    "shortfall_seats": chamber.shortfall_seats,
                },
            )
        )


def _append_capital_ledger_report_entries(
    ctx: PhaseContext, report: PoliticalCapitalReport
) -> None:
    """(Phase 3B2A) The two approved capital-ledger reason IDs, derived from the
    already-constructed, already-self-validated `PoliticalCapitalReport` — never from the scratch
    — so a reason payload can never describe an expenditure the report itself does not, matching
    `_append_legislative_report_entries`'s discipline exactly.

    An empty ledger (no expenditures, no relationship changes) emits nothing: there is nothing to
    report, and printing "0 of 0 spent" every single turn would drown out the turns that matter.
    """
    if report.expenditures:
        ctx.report_entries.append(
            TurnReportEntry(
                category="politics",
                reason_id="political_capital_ledger_resolved",
                params={
                    "opening": report.opening_political_capital,
                    "total_committed": report.total_committed,
                    "legislative_committed": sum(
                        row.political_capital
                        for row in report.expenditures
                        if row.category
                        in (
                            CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE,
                            CapitalExpenditureCategory.DECREE,
                        )
                    ),
                    "relationship_committed": sum(
                        row.political_capital
                        for row in report.expenditures
                        if row.category is CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT
                    ),
                    "regeneration": report.political_capital_regeneration,
                    "closing": report.closing_political_capital,
                    "capacity": report.political_capital_capacity,
                },
            )
        )


def _append_political_relationship_report_entries(
    ctx: PhaseContext, report: PoliticalRelationshipReport
) -> None:
    """(Phase 3B2B, §13) The four approved political-memory reason IDs, derived from the
    already-constructed, already-self-validated `PoliticalRelationshipReport` — never from
    scratch — mirroring `_append_legislative_report_entries` and
    `_append_capital_ledger_report_entries` exactly.

    Supersedes 3B2A's `bloc_relationship_investment_resolved`: that reason ID read
    `PoliticalCapitalReport.relationship_changes`, which no longer exists (§8) — investment detail
    now lives on this report's own rows, alongside decay/policy/decree-bypass, and is folded into
    `bloc_relationship_resolved` below rather than reported a second time under its own ID.

    A component that is exactly zero emits no entry. `bloc_relationship_resolved` is emitted
    whenever ANY of the other three fired (or investment alone moved the relationship), so
    provenance is never ambiguous about which causes combined into one closing value.
    """
    for row in report.blocs:
        if row.decay_component_bps != 0:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="politics",
                    reason_id="relationship_decay_resolved",
                    params={
                        "party_id": row.party_id,
                        "bloc_id": row.bloc_id,
                        "baseline_relationship_bps": row.baseline_relationship_bps,
                        "opening_relationship_bps": row.opening_relationship_bps,
                        "opening_deviation_bps": row.opening_deviation_bps,
                        "decay_component_bps": row.decay_component_bps,
                    },
                )
            )
        if row.policy_reaction_component_bps != 0:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="politics",
                    reason_id="enacted_policy_relationship_reaction",
                    params={
                        "party_id": row.party_id,
                        "bloc_id": row.bloc_id,
                        "tax_direction": report.tax_direction.value,
                        "tax_intensity_bps": report.tax_intensity_bps,
                        "spending_direction": report.spending_direction.value,
                        "spending_intensity_bps": report.spending_intensity_bps,
                        "policy_reaction_component_bps": row.policy_reaction_component_bps,
                    },
                )
            )
        if row.decree_bypass_component_bps != 0:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="politics",
                    reason_id="decree_bypass_relationship_reaction",
                    params={
                        "party_id": row.party_id,
                        "bloc_id": row.bloc_id,
                        "decree_bypass_component_bps": row.decree_bypass_component_bps,
                    },
                )
            )
        if (
            row.decay_component_bps != 0
            or row.investment_component_bps != 0
            or row.policy_reaction_component_bps != 0
            or row.decree_bypass_component_bps != 0
        ):
            ctx.report_entries.append(
                TurnReportEntry(
                    category="politics",
                    reason_id="bloc_relationship_resolved",
                    params={
                        "party_id": row.party_id,
                        "bloc_id": row.bloc_id,
                        "opening_relationship_bps": row.opening_relationship_bps,
                        "uncapped_total_change_bps": row.uncapped_total_change_bps,
                        "applied_total_change_bps": row.applied_total_change_bps,
                        "closing_relationship_bps": row.closing_relationship_bps,
                    },
                )
            )


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
    (
        "update_institutional_loyalty_competence_corruption_power",
        _apply_bloc_relationship_investments,
    ),
    ("evaluate_protests_strikes_insurgency_coups_revolutions", _evaluate_unrest_and_coup_risk),
    ("evaluate_elections_and_constitutional_events", _evaluate_elections),
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
