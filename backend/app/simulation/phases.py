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

from app.core.money import Money
from app.core.rng import derive_rng
from app.simulation.accounting import (
    compute_quarterly_interest,
    compute_tax_revenue,
    compute_total_program_spending,
    resolve_cash_and_debt,
)
from app.simulation.decisions import DecisionSet
from app.simulation.production_accounting import (
    SectorConstraint,
    SectorProductionResult,
    aggregate_production,
    compute_sector_output,
)
from app.simulation.report import (
    TAX_RATE_CHANGE_FIELDS,
    BudgetChangeEntry,
    ChangeDirection,
    FinanceReport,
    PhaseStatus,
    ProductionReport,
    RevenueBreakdown,
    SectorProductionReport,
    TurnReportEntry,
    direction_for,
)
from app.simulation.state import GameState, SpendingPlanState, TaxBaseState, TaxPolicyState

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
    is applied (R3). Frozen and holding only immutable-by-convention Pydantic model
    instances captured by value at the start of `apply_legal_and_administrative_changes`
    — before any mutation — so later phases (and a mutated working `CountryState`) can
    never retroactively change what this turn's report says "opening" was.

    Needed for: computing interest from *opening* debt, explaining old-to-new tax and
    spending changes, proving omitted `BudgetDecision` fields were preserved, and
    distinguishing the player's *submitted* changes from the *resulting active* budget.
    """

    opening_cash: Money
    opening_debt: Money
    annual_debt_interest_rate_bps: int
    tax_bases: TaxBaseState
    previous_tax_policy: TaxPolicyState
    previous_spending_plan: SpendingPlanState


@dataclass
class FinanceScratch:
    """Mutable, turn-local accounting workspace threaded through the Phase 2A phases
    via `PhaseContext.finance`. Not itself part of `GameState` or the report — purely
    a way to pass intermediate values from one phase handler to the next without
    global state (product spec's ban on "hidden side effects" for phase handlers).
    """

    opening: OpeningFinanceSnapshot
    active_tax_policy: TaxPolicyState
    active_spending_plan: SpendingPlanState
    budget_changes: tuple[BudgetChangeEntry, ...] = ()
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
    finance: FinanceScratch | None = None
    """Set by `apply_legal_and_administrative_changes`; read by the two phases after it."""
    finance_report: FinanceReport | None = None
    """Set by `generate_turn_report`; `resolver.py` copies this onto the final `TurnReport`."""
    production_report: ProductionReport | None = None
    """Set by `resolve_production_and_trade`; `resolver.py` copies this onto the final
    `TurnReport`. No scratch workspace for production (unlike `finance`): the phase reads
    only current-turn `state...economy` and never spans multiple phases, so it builds this
    report directly. Deliberately never read or written by any finance phase, and vice versa
    — see `_resolve_production_and_trade`'s docstring."""
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


def _apply_legal_and_administrative_changes(ctx: PhaseContext) -> None:
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

    # .model_copy() (not a bare reference) for every Pydantic-model-typed field:
    # TaxBaseState/TaxPolicyState/SpendingPlanState all have `validate_assignment=True`,
    # which permits in-place field mutation (`obj.field = x`) on a live instance. A bare
    # reference here would mean a *future* phase handler mutating `finance.tax_policy`
    # or `finance.spending_plan` in place — rather than replacing them wholesale, as this
    # module's handlers currently do — would silently corrupt what this turn's report
    # calls "opening," even though `OpeningFinanceSnapshot` itself is frozen. These models
    # have only scalar fields, so a shallow `model_copy()` is already a full, independent
    # copy — there is no nested mutable object left to worry about.
    opening = OpeningFinanceSnapshot(
        opening_cash=player.treasury.cash_on_hand,
        opening_debt=player.treasury.debt,
        annual_debt_interest_rate_bps=finance.annual_debt_interest_rate_bps,
        tax_bases=finance.tax_bases.model_copy(),
        previous_tax_policy=finance.tax_policy.model_copy(),
        previous_spending_plan=finance.spending_plan.model_copy(),
    )

    budget_decision = ctx.decisions.decisions[0] if ctx.decisions.decisions else None
    active_tax_policy = finance.tax_policy
    active_spending_plan = finance.spending_plan
    budget_changes: list[BudgetChangeEntry] = []

    if budget_decision is not None:
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


def _resolve_government_revenue_and_expenditure(ctx: PhaseContext) -> None:
    scratch = ctx.finance
    assert scratch is not None, "apply_legal_and_administrative_changes always runs first"

    revenue_breakdown = compute_tax_revenue(scratch.opening.tax_bases, scratch.active_tax_policy)
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


def _resolve_production_and_trade(ctx: PhaseContext) -> None:
    """Phase 2B1 sector production only — trade (imports/exports, cross-country flows) is
    fully out of scope this phase despite the phase's name; that name is the fixed §7 phase
    slot this fills, not a claim about what's implemented.

    Deliberately isolated from Phase 2A's government accounting: reads only the player's
    current-turn `EconomyState` (never `player.finance`/`player.treasury`), writes only
    `ctx.production_report` (never `ctx.finance`/`ctx.finance_report`/treasury/debt), and
    never mutates `state`. This phase runs *before* the finance phases in `PHASE_ORDER`, so
    `ctx.production_report` is already populated by the time they execute — those phases must
    never read it (see `tests/test_phase_isolation.py`, which asserts the two field sets each
    phase touches are disjoint).
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

    sector_reports: list[SectorProductionReport] = []
    results: list[SectorProductionResult] = []
    counts: dict[str, int] = {}
    for sector in economy.sectors:
        result = compute_sector_output(sector)
        results.append(result)
        sector_reports.append(
            SectorProductionReport(
                category=sector.category,
                capacity_output=sector.quarterly_capacity_output,
                output_per_worker=sector.output_per_worker,
                employed_workers=sector.employed_workers,
                labor_limited_output=result.labor_limited_output,
                actual_output=result.actual_output,
                capacity_utilization_bps=result.capacity_utilization_bps,
                constraint=result.constraint,
            )
        )
        counts[result.constraint.value] = counts.get(result.constraint.value, 0) + 1
        if result.constraint.value == SectorConstraint.INACTIVE.value:
            ctx.report_entries.append(
                TurnReportEntry(
                    category="production",
                    reason_id="sector_inactive",
                    params={"category": sector.category.value},
                )
            )

    aggregates = aggregate_production(economy.sectors, tuple(results))
    ctx.production_report = ProductionReport(
        sectors=tuple(sector_reports),
        total_employment=aggregates.total_employment,
        total_gross_output=aggregates.total_gross_output,
    )
    ctx.report_entries.append(
        TurnReportEntry(
            category="production",
            reason_id="production_summary",
            params={
                "total_employment": aggregates.total_employment,
                "total_gross_output": aggregates.total_gross_output,
                "sectors_capacity_constrained": counts.get(
                    SectorConstraint.CAPACITY_CONSTRAINED.value, 0
                ),
                "sectors_labor_constrained": counts.get(
                    SectorConstraint.LABOR_CONSTRAINED.value, 0
                ),
                "sectors_exactly_balanced": counts.get(SectorConstraint.EXACTLY_BALANCED.value, 0),
                "sectors_inactive": counts.get(SectorConstraint.INACTIVE.value, 0),
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
            tax_bases=scratch.opening.tax_bases,
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

    ctx.mark_implemented()


# The fifteen-step resolution order from product spec §7. Order matters and is tested.
PHASE_ORDER: tuple[tuple[str, PhaseHandler], ...] = (
    ("validate_and_reserve_actions", _noop),
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
    ("update_group_welfare_approval_trust_radicalization", _noop),
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
