"""The explainable output of one turn resolution.

Two audiences, kept structurally separate:

- `entries`: player-facing. What actually happened this turn, in terms a
  player can read. Nothing is added here for systems that don't exist yet —
  per the product spec's "no placeholder feature claims" rule (§5.7), an
  unimplemented system produces no player-facing claim about what it did.
  Each entry carries a stable `reason_id` plus structured `params` rather
  than pre-rendered English prose: the report is stored in hash-protected
  history (`simulation.history`), so whatever text was baked in at
  resolution time could never be re-translated or reworded later without
  invalidating the hash chain. Rendering `reason_id` + `params` into a
  sentence is a presentation-layer concern (`app.cli.REASON_RENDERERS`) that
  can change freely without touching history.
- `dev`: developer/test-facing. `phase_statuses` records, for every phase in
  `simulation.phases.PHASE_ORDER`, whether it actually ran real logic this
  session or is still a registered no-op — structured metadata for tests and
  future development tracking, not narrated to the player as 12-15 repetitive
  "nothing happened" report entries.

`FinanceReport` (Phase 2A government accounting) is *self-validating*: its
`@model_validator` independently re-derives every reconciliation equation
and cross-checks every stored total against its own component fields, on
every construction — including when Pydantic parses one back out of stored
history JSON (`HistoryEntry.report()`), out of a loaded save, or for CLI
`history` inspection. This is deliberately a second, independent code path
from `simulation.accounting` (which `phases.py` uses to *compute* these
numbers in the first place): a bug in one is likely to be caught by the
other, and a hand-edited/corrupted report can never claim reconciliation
succeeded when the numbers don't actually add up.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import StrictBps, StrictMoney, StrictSignedMoney
from app.simulation.accounting import compute_quarterly_interest, compute_tax_revenue
from app.simulation.state import SpendingPlanState, TaxBaseState, TaxPolicyState

_STRICT_CONFIG = ConfigDict(extra="forbid")


class PhaseStatus(StrEnum):
    IMPLEMENTED = "implemented"
    NOT_IMPLEMENTED = "not_implemented"


class TurnReportEntry(BaseModel):
    """A single player-facing line in the turn report.

    `reason_id` must have a registered renderer wherever the report is
    displayed (see `app.cli.REASON_RENDERERS` and
    `tests/test_reason_renderers.py`, which proves every `reason_id` Phase 2A
    can actually emit has one). An unmapped id at render time gets a safe
    fallback, not a crash — but it should never happen for ids this build emits.
    """

    model_config = _STRICT_CONFIG

    category: str
    reason_id: str
    params: dict[str, str | int] = Field(default_factory=dict)


class TurnReportDevMeta(BaseModel):
    """Developer-facing metadata, not shown to the player."""

    model_config = _STRICT_CONFIG

    phase_statuses: dict[str, PhaseStatus]


class RevenueBreakdown(BaseModel):
    """Collected tax revenue by category, plus the total (product spec §13)."""

    model_config = _STRICT_CONFIG

    personal_income_tax: StrictMoney
    corporate_tax: StrictMoney
    consumption_tax: StrictMoney
    total_revenue: StrictMoney


class ChangeDirection(StrEnum):
    UNCHANGED = "unchanged"
    INCREASED = "increased"
    DECREASED = "decreased"


class BudgetChangeEntry(BaseModel):
    """One field's before/after in this turn's budget, however it got there —
    an explicit player target (even one equal to the current value, per R5)
    or simply the unchanged carry-forward when no `BudgetDecision` was
    submitted at all.

    `field` is one of the three tax-rate field names on `TaxPolicyState`
    (`personal_income_rate_bps`, `corporate_rate_bps`, `consumption_rate_bps`)
    or `"spending.<category>"` for one of the seven `SpendingCategory` values.
    """

    model_config = _STRICT_CONFIG

    field: str
    previous_value: StrictSignedMoney
    new_value: StrictSignedMoney
    direction: ChangeDirection


TAX_RATE_CHANGE_FIELDS = frozenset(
    {"personal_income_rate_bps", "corporate_rate_bps", "consumption_rate_bps"}
)


def direction_for(previous_value: int, new_value: int) -> ChangeDirection:
    if new_value == previous_value:
        return ChangeDirection.UNCHANGED
    return ChangeDirection.INCREASED if new_value > previous_value else ChangeDirection.DECREASED


class FinanceReport(BaseModel):
    """Structured, machine-readable Phase 2A government accounting outcome for one turn.

    Every reconciliation equation and cross-total is independently re-checked
    on construction — see the module docstring. `reconciliation_status` is a
    derived property, not a field: it cannot exist as anything other than
    `"reconciled"`, because construction raises before a non-reconciling
    report could ever be returned.
    """

    model_config = _STRICT_CONFIG

    opening_cash: StrictMoney
    opening_debt: StrictMoney
    annual_debt_interest_rate_bps: StrictBps

    tax_bases: TaxBaseState
    previous_tax_policy: TaxPolicyState
    active_tax_policy: TaxPolicyState
    previous_spending_plan: SpendingPlanState
    active_spending_plan: SpendingPlanState

    revenue: RevenueBreakdown
    total_program_spending: StrictMoney
    quarterly_interest_expense: StrictMoney
    pre_financing_balance: StrictSignedMoney
    new_borrowing: StrictMoney
    closing_cash: StrictMoney
    closing_debt: StrictMoney

    budget_changes: tuple[BudgetChangeEntry, ...] = Field(default_factory=tuple)

    @property
    def reconciliation_status(self) -> str:
        """Always `"reconciled"` — a `FinanceReport` that failed to reconcile never
        finishes construction (see the validators below), so there is no other
        value this could hold. Exposed as a property (not a stored field) so it
        cannot be tampered with independently of the numbers it describes.
        """
        return "reconciled"

    @model_validator(mode="after")
    def _revenue_categories_match_their_inputs(self) -> FinanceReport:
        expected = compute_tax_revenue(self.tax_bases, self.active_tax_policy)
        if self.revenue.personal_income_tax != expected.personal_income_tax:
            raise ValueError(
                "revenue.personal_income_tax does not match tax_bases/active_tax_policy: "
                f"stored={self.revenue.personal_income_tax} expected={expected.personal_income_tax}"
            )
        if self.revenue.corporate_tax != expected.corporate_tax:
            raise ValueError(
                "revenue.corporate_tax does not match tax_bases/active_tax_policy: "
                f"stored={self.revenue.corporate_tax} expected={expected.corporate_tax}"
            )
        if self.revenue.consumption_tax != expected.consumption_tax:
            raise ValueError(
                "revenue.consumption_tax does not match tax_bases/active_tax_policy: "
                f"stored={self.revenue.consumption_tax} expected={expected.consumption_tax}"
            )
        return self

    @model_validator(mode="after")
    def _revenue_categories_sum_to_total(self) -> FinanceReport:
        summed = (
            self.revenue.personal_income_tax
            + self.revenue.corporate_tax
            + self.revenue.consumption_tax
        )
        if summed != self.revenue.total_revenue:
            raise ValueError(
                f"revenue categories sum to {summed}, but total_revenue={self.revenue.total_revenue}"
            )
        return self

    @model_validator(mode="after")
    def _spending_categories_sum_to_total(self) -> FinanceReport:
        summed = self.active_spending_plan.total()
        if summed != self.total_program_spending:
            raise ValueError(
                f"active_spending_plan categories sum to {summed}, but "
                f"total_program_spending={self.total_program_spending}"
            )
        return self

    @model_validator(mode="after")
    def _quarterly_interest_matches_opening_debt_and_rate(self) -> FinanceReport:
        expected = compute_quarterly_interest(self.opening_debt, self.annual_debt_interest_rate_bps)
        if self.quarterly_interest_expense != expected:
            raise ValueError(
                "quarterly_interest_expense does not match opening_debt/annual rate: "
                f"stored={self.quarterly_interest_expense} expected={expected}"
            )
        return self

    @model_validator(mode="after")
    def _pre_financing_balance_matches_formula(self) -> FinanceReport:
        expected = (
            self.revenue.total_revenue
            - self.total_program_spending
            - self.quarterly_interest_expense
        )
        if self.pre_financing_balance != expected:
            raise ValueError(
                f"pre_financing_balance={self.pre_financing_balance} does not equal "
                f"total_revenue - total_program_spending - quarterly_interest_expense ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _borrowing_and_closing_cash_match_formula(self) -> FinanceReport:
        cash_before_financing = self.opening_cash + self.pre_financing_balance
        expected_borrowing = max(0, -cash_before_financing)
        expected_closing_cash = max(0, cash_before_financing)
        if self.new_borrowing != expected_borrowing:
            raise ValueError(
                f"new_borrowing={self.new_borrowing} does not equal the remaining shortfall "
                f"after available cash ({expected_borrowing})"
            )
        if self.closing_cash != expected_closing_cash:
            raise ValueError(
                f"closing_cash={self.closing_cash} does not match "
                f"max(0, opening_cash + pre_financing_balance) ({expected_closing_cash})"
            )
        return self

    @model_validator(mode="after")
    def _debt_equation_holds(self) -> FinanceReport:
        expected = self.opening_debt + self.new_borrowing
        if self.closing_debt != expected:
            raise ValueError(
                f"closing_debt={self.closing_debt} does not equal "
                f"opening_debt + new_borrowing ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _cash_flow_equation_holds(self) -> FinanceReport:
        lhs = self.opening_cash + self.revenue.total_revenue + self.new_borrowing
        rhs = self.closing_cash + self.total_program_spending + self.quarterly_interest_expense
        if lhs != rhs:
            raise ValueError(
                "cash-flow reconciliation failed: "
                f"opening_cash + total_revenue + new_borrowing = {lhs}, but "
                f"closing_cash + total_program_spending + quarterly_interest_expense = {rhs}"
            )
        return self

    @model_validator(mode="after")
    def _budget_changes_agree_with_policy_snapshots(self) -> FinanceReport:
        for change in self.budget_changes:
            if change.field in TAX_RATE_CHANGE_FIELDS:
                expected_previous = getattr(self.previous_tax_policy, change.field)
                expected_new = getattr(self.active_tax_policy, change.field)
            elif change.field.startswith("spending."):
                category = change.field.removeprefix("spending.")
                if not hasattr(self.previous_spending_plan, category):
                    raise ValueError(f"budget_changes: unknown spending category {category!r}")
                expected_previous = getattr(self.previous_spending_plan, category)
                expected_new = getattr(self.active_spending_plan, category)
            else:
                raise ValueError(f"budget_changes: unrecognized field {change.field!r}")

            if change.previous_value != expected_previous or change.new_value != expected_new:
                raise ValueError(
                    f"budget_changes entry for {change.field!r} disagrees with the "
                    f"previous/active policy snapshots: stored "
                    f"({change.previous_value} -> {change.new_value}), expected "
                    f"({expected_previous} -> {expected_new})"
                )

            expected_direction = direction_for(expected_previous, expected_new)
            if change.direction != expected_direction:
                raise ValueError(
                    f"budget_changes entry for {change.field!r} has direction "
                    f"{change.direction!r}, expected {expected_direction!r}"
                )
        return self


class TurnReport(BaseModel):
    """The full report produced by one `resolve_turn` call."""

    model_config = _STRICT_CONFIG

    game_seed: int
    resolved_turn: int
    """The turn number that was just resolved (i.e. `state.turn` *before* resolution)."""
    entries: list[TurnReportEntry] = Field(default_factory=list)
    dev: TurnReportDevMeta
    finance: FinanceReport | None = None
    """`None` only when accounting did not run (never for a successful Phase 2A+ turn on a
    valid player state — `simulation.invariants` requires player finance before resolution
    can even begin)."""
