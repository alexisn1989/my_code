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

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.canonical_json import canonical_digest
from app.core.money import BPS_DENOMINATOR, StrictBps, StrictMoney, StrictSignedMoney
from app.core.politics import (
    StrictLegitimacyBps,
    StrictPoliticalCapital,
    StrictPoliticalCapitalCapacity,
    StrictPositiveSeatCount,
    StrictPreferenceBps,
    StrictRelationshipBps,
    StrictSeatCount,
    StrictSeatNumerator,
    StrictSignedBps,
    StrictSignedLegitimacyBps,
    clamp_bps,
    trunc_div_toward_zero,
)
from app.core.quantity import (
    StrictRealOutput,
    StrictRealOutputPerResourceUnit,
    StrictRealOutputPerWorker,
    StrictResourceQuantity,
    StrictResourceQuantityPerWorker,
    StrictWorkerCount,
    base_year_real_output_to_money,
)
from app.simulation.accounting import compute_quarterly_interest, compute_tax_revenue
from app.simulation.constitution import (
    AmendmentDifficulty,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    Legislature,
    TerritorialOrganization,
)
from app.simulation.legislative_voting import (
    DECREE_POLITICAL_CAPITAL_COST,
    INFLUENCE_BPS_PER_CAPITAL,
    MAX_INFLUENCE_BPS,
    RELATIONSHIP_WEIGHT_BPS,
    ROLE_ANCHOR_BPS,
    SPENDING_FULL_INTENSITY_BPS,
    TAX_FULL_INTENSITY_BPS,
    TAX_WEIGHT_BPS,
)
from app.simulation.legislative_voting import SPENDING_WEIGHT_BPS as SPENDING_WEIGHT_BPS
from app.simulation.legislature import ChangeDirection as LegislativeChangeDirection
from app.simulation.legislature import (
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.legitimacy import (
    DRIFT_RATE_BPS,
    LEGITIMACY_REGENERATION_COEFFICIENT,
    MAX_PERFORMANCE_CONTRIBUTION_BPS,
    MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
    OUTPUT_SENSITIVITY_BPS,
    POLITICAL_CAPITAL_BASE_REGENERATION,
    UNEMPLOYMENT_SENSITIVITY_BPS,
)
from app.simulation.resource_extraction import DepositStatus
from app.simulation.state import (
    RENEWABLE_RESOURCES,
    ResourceCategory,
    SectorCategory,
    SpendingPlanState,
    TaxBaseCoefficients,
    TaxBaseState,
    TaxPolicyState,
)

_STRICT_CONFIG = ConfigDict(extra="forbid")

_HEX_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
"""What `budget_decision_digest(...)` (`simulation.decisions`) always produces: a lowercase,
64-character BLAKE2b-256 hex digest, the same shape `HistoryEntry.entry_hash`/
`constitution_digest` already use. `LegislativeReport` checks only this *syntax* — that a stored
digest is even shaped like one — never recomputes or compares it against a real decision; that
semantic check is `simulation.reconciliation`'s alone (group 18), so a report can be syntax-valid
in isolation without ever holding a `DecisionSet`."""


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


class SectorLaborAllocationReport(BaseModel):
    """One sector's self-validated Phase 2B3 labor-allocation outcome.

    `unfilled_workers` and `allocated_workers <= required_workers` are independently re-checked
    here, from this row's own stored fields — see the validators below. The allocation
    *algorithm* itself (largest-remainder, canonical tie-breaking) is not re-derived at the report
    level, the same way `ProductionReport` does not re-derive the labor allocation that produced
    its own `employed_workers` — it is proven correct by `test_labor_allocation.py` and enforced
    cross-report by `TurnReport` (allocation matches what `ProductionReport` actually used).
    """

    model_config = _STRICT_CONFIG

    category: SectorCategory
    required_workers: StrictWorkerCount
    allocated_workers: StrictWorkerCount
    unfilled_workers: StrictWorkerCount

    @model_validator(mode="after")
    def _allocated_does_not_exceed_required(self) -> SectorLaborAllocationReport:
        if self.allocated_workers > self.required_workers:
            raise ValueError(
                f"allocated_workers={self.allocated_workers} exceeds "
                f"required_workers={self.required_workers} for sector {self.category.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _unfilled_workers_matches_formula(self) -> SectorLaborAllocationReport:
        expected = self.required_workers - self.allocated_workers
        if self.unfilled_workers != expected:
            raise ValueError(
                f"unfilled_workers={self.unfilled_workers} does not equal "
                f"required_workers - allocated_workers ({expected})"
            )
        return self


class LaborMarketReport(BaseModel):
    """Structured, machine-readable Phase 2B3 labor-allocation outcome for the player country,
    for one turn. Player-only, mirroring `ProductionReport`/`TaxBaseDerivationReport`'s scope —
    AI countries may have `economy=None` and get no labor-market report.

    `sectors` must contain exactly one entry per `SectorCategory`, in canonical declaration
    order — enforced and (absent duplicates/missing categories) normalized by the same policy
    the other per-sector reports already apply to their own collections.
    """

    model_config = _STRICT_CONFIG

    total_population: StrictWorkerCount
    effective_labor_force_share_bps: StrictBps
    effective_labor_force: StrictWorkerCount
    sectors: tuple[SectorLaborAllocationReport, ...]
    total_labor_demand: StrictWorkerCount
    total_employment: StrictWorkerCount
    unemployed_workers: StrictWorkerCount
    unfilled_jobs: StrictWorkerCount
    unemployment_rate_bps: StrictBps

    @model_validator(mode="after")
    def _sectors_cover_all_categories_exactly_once_in_canonical_order(self) -> LaborMarketReport:
        seen: set[SectorCategory] = set()
        for sector in self.sectors:
            if sector.category in seen:
                raise ValueError(
                    f"duplicate sector category in labor market report: {sector.category.value!r}"
                )
            seen.add(sector.category)
        missing = [c for c in SectorCategory if c not in seen]
        if missing:
            raise ValueError(
                "labor market report is missing sector categories: "
                f"{[c.value for c in missing]!r} — all {len(SectorCategory)} are required"
            )
        by_category = {sector.category: sector for sector in self.sectors}
        canonical_order = tuple(by_category[category] for category in SectorCategory)
        if canonical_order != self.sectors:
            self.sectors = canonical_order
        return self

    @model_validator(mode="after")
    def _effective_labor_force_matches_formula(self) -> LaborMarketReport:
        expected = (self.total_population * self.effective_labor_force_share_bps) // BPS_DENOMINATOR
        if self.effective_labor_force != expected:
            raise ValueError(
                f"effective_labor_force={self.effective_labor_force} does not equal "
                f"floor(total_population * effective_labor_force_share_bps / 10_000) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _effective_labor_force_does_not_exceed_population(self) -> LaborMarketReport:
        if self.effective_labor_force > self.total_population:
            raise ValueError(
                f"effective_labor_force={self.effective_labor_force} exceeds "
                f"total_population={self.total_population}"
            )
        return self

    @model_validator(mode="after")
    def _total_labor_demand_matches_sum(self) -> LaborMarketReport:
        expected = sum(sector.required_workers for sector in self.sectors)
        if self.total_labor_demand != expected:
            raise ValueError(
                f"total_labor_demand={self.total_labor_demand} does not equal the sum of "
                f"sectors[*].required_workers ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_employment_matches_sum(self) -> LaborMarketReport:
        expected = sum(sector.allocated_workers for sector in self.sectors)
        if self.total_employment != expected:
            raise ValueError(
                f"total_employment={self.total_employment} does not equal the sum of "
                f"sectors[*].allocated_workers ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_employment_matches_min_identity(self) -> LaborMarketReport:
        expected = min(self.effective_labor_force, self.total_labor_demand)
        if self.total_employment != expected:
            raise ValueError(
                f"total_employment={self.total_employment} does not equal "
                f"min(effective_labor_force, total_labor_demand) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unemployed_workers_matches_formula(self) -> LaborMarketReport:
        expected = self.effective_labor_force - self.total_employment
        if self.unemployed_workers != expected:
            raise ValueError(
                f"unemployed_workers={self.unemployed_workers} does not equal "
                f"effective_labor_force - total_employment ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unfilled_jobs_matches_formula(self) -> LaborMarketReport:
        expected = self.total_labor_demand - self.total_employment
        if self.unfilled_jobs != expected:
            raise ValueError(
                f"unfilled_jobs={self.unfilled_jobs} does not equal "
                f"total_labor_demand - total_employment ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unemployment_rate_bps_matches_formula(self) -> LaborMarketReport:
        expected = (
            (self.unemployed_workers * BPS_DENOMINATOR) // self.effective_labor_force
            if self.effective_labor_force > 0
            else 0
        )
        if self.unemployment_rate_bps != expected:
            raise ValueError(
                f"unemployment_rate_bps={self.unemployment_rate_bps} does not match "
                "floor(unemployed_workers * 10_000 / effective_labor_force), or 0 when "
                f"effective_labor_force is 0 ({expected})"
            )
        return self


class ResourceDepositReport(BaseModel):
    """One resource deposit's self-validated Phase 2C1 extraction outcome, extended (Phase 2C2)
    with its physical-to-output bridge contribution.

    Every derived field is independently re-checked against this row's own stored inputs on
    construction — see the validators below — mirroring `SectorProductionReport`'s pattern
    exactly. `regeneration_per_turn`/`stock_ceiling` (R1) are carried here specifically so
    `_regenerated_matches_formula` can recompute regeneration from the row's own fields rather
    than trusting the phase that built it — without them this row could not independently verify
    the one number that makes timber different from every other resource.

    `real_output_per_unit`/`real_output_contribution`/`potential_output_contribution` (Phase 2C2,
    R6) carry both the actual and potential (stock/capacity-bounded, labor-independent) converted
    contributions on the same row as the physical inputs they're derived from — so both are
    independently re-derivable from fields this row already stores, without needing a second
    report. `potential_output_contribution` is what gives the extraction sector's
    `capacity_utilization_bps` a principled, non-legacy denominator (see
    `docs/adr/0008-physical-extraction-derived-sector-output.md`).

    Units: every physical-quantity field except the worker counts is a `StrictResourceQuantity`/
    `StrictResourceQuantityPerWorker` in the category's own unit (`state.RESOURCE_UNITS`) — never
    `Money`. `real_output_per_unit`/`real_output_contribution`/`potential_output_contribution` are
    the one deliberate exception: they are `RealOutput`, the single named conversion boundary
    (`core.quantity.extracted_resource_to_real_output`).
    """

    model_config = _STRICT_CONFIG

    category: ResourceCategory
    opening_stock: StrictResourceQuantity
    regeneration_per_turn: StrictResourceQuantity
    stock_ceiling: StrictResourceQuantity | None
    regenerated: StrictResourceQuantity
    available_stock: StrictResourceQuantity
    extraction_capacity_per_turn: StrictResourceQuantity
    output_per_worker: StrictResourceQuantityPerWorker
    required_workers: StrictWorkerCount
    allocated_workers: StrictWorkerCount
    extracted: StrictResourceQuantity
    closing_stock: StrictResourceQuantity
    status: DepositStatus
    real_output_per_unit: StrictRealOutputPerResourceUnit
    real_output_contribution: StrictRealOutput
    potential_output_contribution: StrictRealOutput

    @model_validator(mode="after")
    def _regeneration_and_ceiling_respect_renewability_rule(self) -> ResourceDepositReport:
        if self.category not in RENEWABLE_RESOURCES:
            if self.regeneration_per_turn != 0:
                raise ValueError(
                    f"{self.category.value} is nonrenewable but regeneration_per_turn="
                    f"{self.regeneration_per_turn} — must be 0"
                )
            if self.stock_ceiling is not None:
                raise ValueError(
                    f"{self.category.value} is nonrenewable but stock_ceiling="
                    f"{self.stock_ceiling} — must be None"
                )
        else:
            if self.stock_ceiling is None:
                raise ValueError(f"{self.category.value} is renewable but stock_ceiling is None")
            if self.available_stock > self.stock_ceiling:
                raise ValueError(
                    f"available_stock={self.available_stock} exceeds stock_ceiling="
                    f"{self.stock_ceiling} for renewable {self.category.value}"
                )
        return self

    @model_validator(mode="after")
    def _regenerated_matches_formula(self) -> ResourceDepositReport:
        if self.category not in RENEWABLE_RESOURCES:
            expected = 0
        else:
            # stock_ceiling is guaranteed not None here by the renewability-rule validator above
            # (Pydantic "after" validators on the same model run in declaration order).
            assert self.stock_ceiling is not None
            expected = max(
                0, min(self.regeneration_per_turn, self.stock_ceiling - self.opening_stock)
            )
        if self.regenerated != expected:
            raise ValueError(
                f"regenerated={self.regenerated} does not match the regeneration formula "
                f"applied to opening_stock/regeneration_per_turn/stock_ceiling ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _available_stock_matches_formula(self) -> ResourceDepositReport:
        expected = self.opening_stock + self.regenerated
        if self.available_stock != expected:
            raise ValueError(
                f"available_stock={self.available_stock} does not equal "
                f"opening_stock + regenerated ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _required_workers_matches_ceiling_division(self) -> ResourceDepositReport:
        extractable_ceiling = min(self.available_stock, self.extraction_capacity_per_turn)
        expected = (
            0
            if extractable_ceiling == 0
            else (extractable_ceiling + self.output_per_worker - 1) // self.output_per_worker
        )
        if self.required_workers != expected:
            raise ValueError(
                f"required_workers={self.required_workers} does not equal "
                f"ceil(min(available_stock, extraction_capacity_per_turn) / output_per_worker) "
                f"({expected})"
            )
        return self

    @model_validator(mode="after")
    def _allocated_does_not_exceed_required(self) -> ResourceDepositReport:
        if self.allocated_workers > self.required_workers:
            raise ValueError(
                f"allocated_workers={self.allocated_workers} exceeds "
                f"required_workers={self.required_workers} for {self.category.value}"
            )
        return self

    @model_validator(mode="after")
    def _extracted_matches_three_way_min(self) -> ResourceDepositReport:
        expected = min(
            self.available_stock,
            self.extraction_capacity_per_turn,
            self.allocated_workers * self.output_per_worker,
        )
        if self.extracted != expected:
            raise ValueError(
                f"extracted={self.extracted} does not equal min(available_stock, "
                f"extraction_capacity_per_turn, allocated_workers * output_per_worker) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _closing_stock_matches_conservation(self) -> ResourceDepositReport:
        expected = self.available_stock - self.extracted
        if self.closing_stock != expected:
            raise ValueError(
                f"closing_stock={self.closing_stock} does not equal "
                f"available_stock - extracted ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _status_matches_classification_rule(self) -> ResourceDepositReport:
        if self.extraction_capacity_per_turn == 0:
            expected = DepositStatus.INACTIVE
        elif self.available_stock == 0:
            expected = DepositStatus.DEPLETED
        elif self.extracted == self.available_stock:
            expected = DepositStatus.STOCK_CONSTRAINED
        elif self.extracted == self.extraction_capacity_per_turn:
            expected = DepositStatus.CAPACITY_CONSTRAINED
        else:
            expected = DepositStatus.LABOR_CONSTRAINED
        if self.status != expected:
            raise ValueError(
                f"status={self.status!r} does not match the classification rule applied to "
                f"extraction_capacity_per_turn/available_stock/extracted (expected {expected!r})"
            )
        return self

    @model_validator(mode="after")
    def _real_output_contribution_matches_bridge(self) -> ResourceDepositReport:
        expected = self.extracted * self.real_output_per_unit
        if self.real_output_contribution != expected:
            raise ValueError(
                f"real_output_contribution={self.real_output_contribution} does not equal "
                f"extracted * real_output_per_unit ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _potential_output_contribution_matches_bridge(self) -> ResourceDepositReport:
        potential_quantity = min(self.available_stock, self.extraction_capacity_per_turn)
        expected = potential_quantity * self.real_output_per_unit
        if self.potential_output_contribution != expected:
            raise ValueError(
                f"potential_output_contribution={self.potential_output_contribution} does not "
                "equal min(available_stock, extraction_capacity_per_turn) * real_output_per_unit "
                f"({expected})"
            )
        return self

    @model_validator(mode="after")
    def _zero_extraction_yields_zero_contribution(self) -> ResourceDepositReport:
        """Stated separately from `_real_output_contribution_matches_bridge` (which already
        implies this) so a violation fails with its own, more specific message: output can never
        be created from resources that were not physically extracted this turn."""
        if self.extracted == 0 and self.real_output_contribution != 0:
            raise ValueError(
                f"real_output_contribution={self.real_output_contribution} is nonzero despite "
                f"extracted == 0 for {self.category.value} — output cannot be created from "
                "resources that were not physically extracted"
            )
        return self

    @model_validator(mode="after")
    def _real_output_contribution_does_not_exceed_potential(self) -> ResourceDepositReport:
        """Row-level restatement of the `actual <= potential` inequality proven by construction
        in `simulation.resource_output` — defense-in-depth at the smallest possible granularity,
        belt-and-suspenders alongside `ResourceExtractionReport`'s aggregate-level check below."""
        if self.real_output_contribution > self.potential_output_contribution:
            raise ValueError(
                f"real_output_contribution={self.real_output_contribution} exceeds "
                f"potential_output_contribution={self.potential_output_contribution} for "
                f"{self.category.value}"
            )
        return self


class ResourceExtractionReport(BaseModel):
    """Structured, machine-readable Phase 2C1 resource-extraction outcome for the player country,
    for one turn, extended (Phase 2C2) with the extraction sector's aggregate physical-to-output
    bridge totals. Player-only, mirroring `LaborMarketReport`/`ProductionReport`'s scope — AI
    countries may have `economy=None` and get no resource-extraction report.

    `deposits` must contain exactly one entry per `ResourceCategory`, in canonical declaration
    order. **Unlike every other per-category report collection in this module, noncanonical order
    is REJECTED here, not normalized (R3)** — see `state.EconomyState`'s sibling validator and
    `docs/adr/0007-resource-endowments-and-extraction.md` for why.

    No `total_extracted` field: physical quantities of different resources (tonnes, barrels,
    cubic metres) are never summed together (D4) — only worker counts are aggregated. But
    `extraction_sector_real_output`/`extraction_sector_potential_output` (Phase 2C2) sum
    homogeneous `RealOutput` contributions across all eight deposits — a different, legal kind of
    sum, since every deposit's contribution is already in the same converted unit. These are the
    values `TurnReport` cross-validates against `ProductionReport.sectors[EXTRACTION]`, since this
    row cannot self-validate `actual_output`/`capacity_utilization_bps`/`constraint` in isolation.
    """

    model_config = _STRICT_CONFIG

    deposits: tuple[ResourceDepositReport, ...]
    extraction_sector_workers: StrictWorkerCount
    total_extraction_workers: StrictWorkerCount
    unassigned_resource_workers: StrictWorkerCount
    extraction_sector_real_output: StrictRealOutput
    extraction_sector_potential_output: StrictRealOutput

    @model_validator(mode="after")
    def _deposits_cover_all_categories_exactly_once_in_canonical_order(
        self,
    ) -> ResourceExtractionReport:
        seen: set[ResourceCategory] = set()
        for deposit in self.deposits:
            if deposit.category in seen:
                raise ValueError(
                    f"duplicate resource category in extraction report: {deposit.category.value!r}"
                )
            seen.add(deposit.category)
        missing = [c for c in ResourceCategory if c not in seen]
        if missing:
            raise ValueError(
                "resource extraction report is missing resource categories: "
                f"{[c.value for c in missing]!r} — all {len(ResourceCategory)} are required"
            )
        by_category = {deposit.category: deposit for deposit in self.deposits}
        canonical_order = tuple(by_category[category] for category in ResourceCategory)
        if canonical_order != self.deposits:
            got = [d.category.value for d in self.deposits]
            expected = [c.value for c in ResourceCategory]
            raise ValueError(
                "extraction report deposits are not in canonical ResourceCategory order: "
                f"got {got!r}, expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _total_extraction_workers_matches_sum(self) -> ResourceExtractionReport:
        expected = sum(deposit.allocated_workers for deposit in self.deposits)
        if self.total_extraction_workers != expected:
            raise ValueError(
                f"total_extraction_workers={self.total_extraction_workers} does not equal the "
                f"sum of deposits[*].allocated_workers ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unassigned_matches_sector_workers_minus_total(self) -> ResourceExtractionReport:
        expected = self.extraction_sector_workers - self.total_extraction_workers
        if self.unassigned_resource_workers != expected:
            raise ValueError(
                f"unassigned_resource_workers={self.unassigned_resource_workers} does not equal "
                f"extraction_sector_workers - total_extraction_workers ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_does_not_exceed_sector_workers(self) -> ResourceExtractionReport:
        if self.total_extraction_workers > self.extraction_sector_workers:
            raise ValueError(
                f"total_extraction_workers={self.total_extraction_workers} exceeds "
                f"extraction_sector_workers={self.extraction_sector_workers}"
            )
        return self

    @model_validator(mode="after")
    def _extraction_sector_real_output_matches_summed_contributions(
        self,
    ) -> ResourceExtractionReport:
        expected = sum(deposit.real_output_contribution for deposit in self.deposits)
        if self.extraction_sector_real_output != expected:
            raise ValueError(
                f"extraction_sector_real_output={self.extraction_sector_real_output} does not "
                f"equal the sum of deposits[*].real_output_contribution ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _extraction_sector_potential_output_matches_summed_potential_contributions(
        self,
    ) -> ResourceExtractionReport:
        expected = sum(deposit.potential_output_contribution for deposit in self.deposits)
        if self.extraction_sector_potential_output != expected:
            raise ValueError(
                "extraction_sector_potential_output="
                f"{self.extraction_sector_potential_output} does not equal the sum of "
                f"deposits[*].potential_output_contribution ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _extraction_sector_real_output_does_not_exceed_potential(
        self,
    ) -> ResourceExtractionReport:
        """Aggregate-level restatement of the same `actual <= potential` inequality each row
        already checks — belt-and-suspenders, mirroring the codebase's existing habit of checking
        both a per-row and an aggregate identity."""
        if self.extraction_sector_real_output > self.extraction_sector_potential_output:
            raise ValueError(
                f"extraction_sector_real_output={self.extraction_sector_real_output} exceeds "
                "extraction_sector_potential_output="
                f"{self.extraction_sector_potential_output}"
            )
        return self


class SectorOutputBasis(StrEnum):
    """Which formula a `SectorProductionReport` row's derived fields were computed by (Phase
    2C2). Determined entirely by category identity (`EXTRACTION` -> `RESOURCE_EXTRACTION`, every
    other category -> `STANDARD`) — never an authored or scenario choice; see
    `_output_basis_matches_category` below."""

    STANDARD = "standard"
    RESOURCE_EXTRACTION = "resource_extraction"


class SectorProductionConstraint(StrEnum):
    """The report-facing constraint classification for a `SectorProductionReport` row (Phase
    2C2, R9) — a superset of `production_accounting.SectorConstraint`'s four members (which
    `compute_sector_output` still produces, internally, for `STANDARD`-basis rows only — that
    function and module are unmodified) plus `PHYSICAL_RESOURCE_CONSTRAINED`, which only ever
    applies to the `RESOURCE_EXTRACTION` row. Defined here rather than added to
    `production_accounting.SectorConstraint` for the same reason `SectorOutputBasis` is: the pure
    engine module never produces this value and must stay untouched. The four shared members keep
    identical string values to `SectorConstraint`'s, so `STANDARD` rows' canonical JSON is
    byte-for-byte unaffected by this type change.
    """

    CAPACITY_CONSTRAINED = "capacity_constrained"
    LABOR_CONSTRAINED = "labor_constrained"
    EXACTLY_BALANCED = "exactly_balanced"
    INACTIVE = "inactive"
    PHYSICAL_RESOURCE_CONSTRAINED = "physical_resource_constrained"


def classify_extraction_constraint(
    *, potential_output: int, actual_output: int
) -> SectorProductionConstraint:
    """The Phase 2C2 classification for the extraction sector's `SectorProductionReport` row
    (R9), called identically from `phases.py` (to construct the row) and `TurnReport`'s
    cross-validator (to authoritatively check it) — the one deliberate exception to this
    codebase's usual "independently re-derive, don't share code" self-validation philosophy,
    because the classification itself has no freedom: given `(potential_output, actual_output)`
    exactly one outcome is possible, so re-deriving it a second time would only re-prove that the
    same deterministic function returns the same answer twice, not add any real defense. What
    genuinely needs independent re-derivation — whether `potential_output`/`actual_output`
    themselves agree with `ResourceExtractionReport`'s stored totals — is exactly what
    `TurnReport`'s cross-validators (report.py) already check, separately from this function.

    `actual_output > potential_output` is **REJECTED, never classified** (R9):
    `simulation.resource_output` proves, by construction, this can never happen via any
    legitimate code path (`extracted_i <= potential_quantity_i` for every category, hence summed).
    This function still raises defensively rather than silently assigning a business status to
    invalid data — belt-and-suspenders alongside `ResourceExtractionReport`'s own
    does-not-exceed-potential validators (row-level and aggregate-level, above).

    Valid-state table (R9):
        potential_output == 0                        -> INACTIVE   (implies actual_output == 0)
        potential_output >  0, actual_output <  potential -> LABOR_CONSTRAINED (includes the
            zero-employment case — 2B1 precedent: potential existing but unstaffed is a labor
            fact, not an inactivity fact)
        potential_output >  0, actual_output == potential -> PHYSICAL_RESOURCE_CONSTRAINED
            (deterministic tie semantics: this is the outcome whenever labor realized exactly
            what stock/capacity would allow, regardless of whether labor was scarce-but-exactly-
            sufficient or merely abundant with the resource itself the true ceiling — per-deposit
            distinctions of that kind remain `ResourceDepositReport.status`'s job, not this
            sector-aggregate field's)
    """
    if actual_output > potential_output:
        raise ValueError(
            f"actual_output={actual_output} exceeds potential_output={potential_output} for "
            "the extraction row — this state is invalid, not merely unreachable, and must "
            "never be assigned a business status"
        )
    if potential_output == 0:
        return SectorProductionConstraint.INACTIVE
    if actual_output < potential_output:
        return SectorProductionConstraint.LABOR_CONSTRAINED
    return SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED


class SectorProductionReport(BaseModel):
    """One sector's self-validated Phase 2B1 production outcome.

    Every derived field (`labor_limited_output`, `actual_output`,
    `capacity_utilization_bps`, `constraint`) is independently re-checked
    against the sector's own stored inputs on construction — see the
    validators below — mirroring `FinanceReport`'s self-validation pattern.
    There is no trusted boolean; a report that disagrees with its own
    formulas never finishes construction.

    As of Phase 2B3, `employed_workers` is no longer scenario-authored — it is this turn's
    labor allocation, cross-checked against `LaborMarketReport.sectors[*].allocated_workers` for
    the same category by `TurnReport` (see below), not re-derived by this row itself (mirroring
    how this row never re-derives the tax-base coefficients that used its own `actual_output`).

    Units: `capacity_output`/`output_per_worker`/`labor_limited_output`/
    `actual_output` are fixed-base-year output minor units (`StrictRealOutput`/
    `StrictRealOutputPerWorker`) — real production measures, never spendable
    money. `employed_workers` is a worker count (`StrictWorkerCount`), a
    distinct unit from output. See `app.core.quantity` and
    `docs/economy_methodology.md`.
    """

    model_config = _STRICT_CONFIG

    category: SectorCategory
    output_basis: SectorOutputBasis
    capacity_output: StrictRealOutput
    output_per_worker: StrictRealOutputPerWorker
    employed_workers: StrictWorkerCount
    labor_limited_output: StrictRealOutput
    actual_output: StrictRealOutput
    capacity_utilization_bps: StrictBps
    constraint: SectorProductionConstraint

    @model_validator(mode="after")
    def _output_basis_matches_category(self) -> SectorProductionReport:
        expected = (
            SectorOutputBasis.RESOURCE_EXTRACTION
            if self.category is SectorCategory.EXTRACTION
            else SectorOutputBasis.STANDARD
        )
        if self.output_basis != expected:
            raise ValueError(
                f"output_basis={self.output_basis!r} does not match category="
                f"{self.category.value!r} (expected {expected!r})"
            )
        return self

    @model_validator(mode="after")
    def _labor_limited_output_matches_formula(self) -> SectorProductionReport:
        if self.output_basis is SectorOutputBasis.STANDARD:
            expected = self.employed_workers * self.output_per_worker
            if self.labor_limited_output != expected:
                raise ValueError(
                    f"labor_limited_output={self.labor_limited_output} does not equal "
                    f"employed_workers * output_per_worker ({expected})"
                )
        else:
            # RESOURCE_EXTRACTION: labor_limited_output is defined to equal actual_output — the
            # physical bridge total (labor is already incorporated as one of three bounding terms
            # inside resource_extraction.py's own extraction formula, upstream of this report).
            if self.labor_limited_output != self.actual_output:
                raise ValueError(
                    f"labor_limited_output={self.labor_limited_output} does not equal "
                    f"actual_output={self.actual_output} for the RESOURCE_EXTRACTION basis "
                    "(the two fields are definitionally equal on this row)"
                )
        return self

    @model_validator(mode="after")
    def _actual_output_matches_formula(self) -> SectorProductionReport:
        if self.output_basis is SectorOutputBasis.STANDARD:
            expected = min(self.capacity_output, self.labor_limited_output)
            if self.actual_output != expected:
                raise ValueError(
                    f"actual_output={self.actual_output} does not equal "
                    f"min(capacity_output, labor_limited_output) ({expected})"
                )
        else:
            # RESOURCE_EXTRACTION: NOT independently re-derivable from this row's own fields —
            # the physical inputs (extracted quantities, coefficients) live in
            # ResourceExtractionReport, a sibling report. This row-level check is the
            # self-consistency half only (mirrored above in
            # _labor_limited_output_matches_formula); the AUTHORITATIVE check — that this value
            # actually equals ResourceExtractionReport.extraction_sector_real_output — is
            # TurnReport's cross-validator (below), which fires on every construction/parse path
            # exactly like every other TurnReport cross-check.
            if self.actual_output != self.labor_limited_output:
                raise ValueError(
                    f"actual_output={self.actual_output} does not equal "
                    f"labor_limited_output={self.labor_limited_output} for the "
                    "RESOURCE_EXTRACTION basis (the two fields are definitionally equal on this "
                    "row)"
                )
        return self

    @model_validator(mode="after")
    def _capacity_utilization_bps_matches_formula(self) -> SectorProductionReport:
        if self.output_basis is SectorOutputBasis.STANDARD:
            expected = (
                (self.actual_output * BPS_DENOMINATOR) // self.capacity_output
                if self.capacity_output > 0
                else 0
            )
            if self.capacity_utilization_bps != expected:
                raise ValueError(
                    f"capacity_utilization_bps={self.capacity_utilization_bps} does not match "
                    f"floor(actual_output * 10_000 / capacity_output) ({expected})"
                )
        # RESOURCE_EXTRACTION: not self-derivable from this row's own fields — the potential-
        # output total lives in ResourceExtractionReport, a sibling report. No row-level check is
        # performed; this field is authoritatively checked ONLY by TurnReport's cross-validator
        # (below). quarterly_capacity_output (this row's capacity_output field) is read NOWHERE
        # in this branch — it is not even used as a denominator for this basis (R6; see
        # docs/adr/0008-physical-extraction-derived-sector-output.md, "Legacy field semantics").
        return self

    @model_validator(mode="after")
    def _constraint_matches_classification_rule(self) -> SectorProductionReport:
        if self.output_basis is SectorOutputBasis.STANDARD:
            if self.capacity_output == 0:
                expected: SectorProductionConstraint = SectorProductionConstraint.INACTIVE
            elif self.labor_limited_output < self.capacity_output:
                expected = SectorProductionConstraint.LABOR_CONSTRAINED
            elif self.labor_limited_output > self.capacity_output:
                expected = SectorProductionConstraint.CAPACITY_CONSTRAINED
            else:
                expected = SectorProductionConstraint.EXACTLY_BALANCED
            if self.constraint != expected:
                raise ValueError(
                    f"constraint={self.constraint!r} does not match the classification rule "
                    f"applied to capacity_output/labor_limited_output (expected {expected!r})"
                )
        # RESOURCE_EXTRACTION: no row-level check — authoritatively checked by TurnReport's
        # cross-validator via classify_extraction_constraint (R9), which needs
        # ResourceExtractionReport's potential/actual totals, not available on this row alone.
        return self


class ProductionReport(BaseModel):
    """Structured, machine-readable Phase 2B1 sector production outcome for the player
    country, for one turn. Player-only this phase, mirroring `FinanceReport`'s scope — AI
    countries may have `economy=None` and get no production report.

    `sectors` must contain exactly one entry per `SectorCategory`, in the enum's declaration
    order — enforced (and, absent duplicates/missing categories, normalized) by the validator
    below, the same policy `EconomyState` applies to its own `sectors` tuple. This is what
    makes two logically-identical economies authored in different order serialize to
    byte-identical canonical JSON and `entry_hash`.

    This is "gross sector output at fixed base-year prices" — not GDP, not value added, not
    an inflation-adjusted or growth figure. No value-added accounting exists yet, so summing
    sector output can include intermediate production.
    """

    model_config = _STRICT_CONFIG

    sectors: tuple[SectorProductionReport, ...]
    total_employment: StrictWorkerCount
    total_gross_output: StrictRealOutput

    @model_validator(mode="after")
    def _sectors_cover_all_categories_exactly_once_in_canonical_order(self) -> ProductionReport:
        seen: set[SectorCategory] = set()
        for sector in self.sectors:
            if sector.category in seen:
                raise ValueError(f"duplicate sector category in report: {sector.category.value!r}")
            seen.add(sector.category)
        missing = [c for c in SectorCategory if c not in seen]
        if missing:
            raise ValueError(
                "production report is missing sector categories: "
                f"{[c.value for c in missing]!r} — all {len(SectorCategory)} are required"
            )
        by_category = {sector.category: sector for sector in self.sectors}
        canonical_order = tuple(by_category[category] for category in SectorCategory)
        if canonical_order != self.sectors:
            self.sectors = canonical_order
        return self

    @model_validator(mode="after")
    def _total_employment_matches_sum(self) -> ProductionReport:
        expected = sum(sector.employed_workers for sector in self.sectors)
        if self.total_employment != expected:
            raise ValueError(
                f"total_employment={self.total_employment} does not equal the sum of "
                f"sectors[*].employed_workers ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_gross_output_matches_sum(self) -> ProductionReport:
        expected = sum(sector.actual_output for sector in self.sectors)
        if self.total_gross_output != expected:
            raise ValueError(
                f"total_gross_output={self.total_gross_output} does not equal the sum of "
                f"sectors[*].actual_output ({expected})"
            )
        return self


class SectorTaxBaseReport(BaseModel):
    """One sector's self-validated Phase 2B2 tax-base contribution.

    `modeled_value_added`/`labor_income`/`operating_surplus` are independently re-checked here,
    from this row's own stored fields — see the validators below. The three tax-base
    contributions depend on the country-level `TaxBaseCoefficients`, which this row does not
    carry (avoiding redundant storage of the same coefficients on every row), so they are
    re-checked one level up, by `TaxBaseDerivationReport`'s own validator, which has both the
    rows and the coefficients.

    Units: `actual_output`/`modeled_value_added`/`labor_income`/`operating_surplus`/the three
    `*_contribution` fields are all fixed-base-year **real** output (`StrictRealOutput`) — none
    of them is `Money` yet; the real-to-nominal conversion happens exactly once, at
    `TaxBaseDerivationReport.derived_tax_bases`, via `base_year_real_output_to_money`.
    `modeled_value_added` is an explicitly-named decomposition proxy, not national-accounts value
    added, GDP, or growth — see `docs/economy_methodology.md`.
    """

    model_config = _STRICT_CONFIG

    category: SectorCategory
    actual_output: StrictRealOutput
    value_added_share_bps: StrictBps
    labor_income_share_bps: StrictBps
    modeled_value_added: StrictRealOutput
    labor_income: StrictRealOutput
    operating_surplus: StrictRealOutput
    personal_contribution: StrictRealOutput
    corporate_contribution: StrictRealOutput
    consumption_contribution: StrictRealOutput

    @model_validator(mode="after")
    def _modeled_value_added_matches_formula(self) -> SectorTaxBaseReport:
        expected = (self.actual_output * self.value_added_share_bps) // BPS_DENOMINATOR
        if self.modeled_value_added != expected:
            raise ValueError(
                f"modeled_value_added={self.modeled_value_added} does not equal "
                f"floor(actual_output * value_added_share_bps / 10_000) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _labor_income_matches_formula(self) -> SectorTaxBaseReport:
        expected = (self.modeled_value_added * self.labor_income_share_bps) // BPS_DENOMINATOR
        if self.labor_income != expected:
            raise ValueError(
                f"labor_income={self.labor_income} does not equal "
                f"floor(modeled_value_added * labor_income_share_bps / 10_000) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _operating_surplus_equals_value_added_minus_labor_income(self) -> SectorTaxBaseReport:
        expected = self.modeled_value_added - self.labor_income
        if self.operating_surplus != expected:
            raise ValueError(
                f"operating_surplus={self.operating_surplus} does not equal "
                f"modeled_value_added - labor_income ({expected})"
            )
        return self


class TaxBaseDerivationReport(BaseModel):
    """Structured, machine-readable Phase 2B2 production-derived tax-base outcome for the
    player country, for one turn. Player-only, mirroring `FinanceReport`/`ProductionReport`'s
    scope — AI countries may have `economy=None`/`finance=None` and get no derivation report.

    `sectors` must contain exactly one entry per `SectorCategory`, in canonical declaration
    order — enforced and (absent duplicates/missing categories) normalized by the same policy
    `EconomyState`/`ProductionReport` already apply to their own per-sector collections.
    """

    model_config = _STRICT_CONFIG

    coefficients: TaxBaseCoefficients
    sectors: tuple[SectorTaxBaseReport, ...]
    total_modeled_value_added: StrictRealOutput
    total_labor_income: StrictRealOutput
    total_operating_surplus: StrictRealOutput
    derived_tax_bases: TaxBaseState

    @model_validator(mode="after")
    def _sectors_cover_all_categories_exactly_once_in_canonical_order(
        self,
    ) -> TaxBaseDerivationReport:
        seen: set[SectorCategory] = set()
        for sector in self.sectors:
            if sector.category in seen:
                raise ValueError(
                    f"duplicate sector category in tax-base derivation report: "
                    f"{sector.category.value!r}"
                )
            seen.add(sector.category)
        missing = [c for c in SectorCategory if c not in seen]
        if missing:
            raise ValueError(
                "tax-base derivation report is missing sector categories: "
                f"{[c.value for c in missing]!r} — all {len(SectorCategory)} are required"
            )
        by_category = {sector.category: sector for sector in self.sectors}
        canonical_order = tuple(by_category[category] for category in SectorCategory)
        if canonical_order != self.sectors:
            self.sectors = canonical_order
        return self

    @model_validator(mode="after")
    def _each_sector_contribution_matches_coefficients(self) -> TaxBaseDerivationReport:
        for sector in self.sectors:
            expected_personal = (
                sector.labor_income * self.coefficients.personal_taxable_share_bps
            ) // BPS_DENOMINATOR
            if sector.personal_contribution != expected_personal:
                raise ValueError(
                    f"sector {sector.category.value!r}: personal_contribution="
                    f"{sector.personal_contribution} does not equal floor(labor_income * "
                    f"personal_taxable_share_bps / 10_000) ({expected_personal})"
                )
            expected_corporate = (
                sector.operating_surplus * self.coefficients.corporate_taxable_share_bps
            ) // BPS_DENOMINATOR
            if sector.corporate_contribution != expected_corporate:
                raise ValueError(
                    f"sector {sector.category.value!r}: corporate_contribution="
                    f"{sector.corporate_contribution} does not equal floor(operating_surplus * "
                    f"corporate_taxable_share_bps / 10_000) ({expected_corporate})"
                )
            expected_consumption = (
                sector.modeled_value_added * self.coefficients.effective_consumption_base_share_bps
            ) // BPS_DENOMINATOR
            if sector.consumption_contribution != expected_consumption:
                raise ValueError(
                    f"sector {sector.category.value!r}: consumption_contribution="
                    f"{sector.consumption_contribution} does not equal floor(modeled_value_added "
                    f"* effective_consumption_base_share_bps / 10_000) ({expected_consumption})"
                )
        return self

    @model_validator(mode="after")
    def _total_modeled_value_added_matches_sum(self) -> TaxBaseDerivationReport:
        expected = sum(sector.modeled_value_added for sector in self.sectors)
        if self.total_modeled_value_added != expected:
            raise ValueError(
                f"total_modeled_value_added={self.total_modeled_value_added} does not equal "
                f"the sum of sectors[*].modeled_value_added ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_labor_income_matches_sum(self) -> TaxBaseDerivationReport:
        expected = sum(sector.labor_income for sector in self.sectors)
        if self.total_labor_income != expected:
            raise ValueError(
                f"total_labor_income={self.total_labor_income} does not equal the sum of "
                f"sectors[*].labor_income ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_operating_surplus_matches_sum(self) -> TaxBaseDerivationReport:
        expected = sum(sector.operating_surplus for sector in self.sectors)
        if self.total_operating_surplus != expected:
            raise ValueError(
                f"total_operating_surplus={self.total_operating_surplus} does not equal the sum "
                f"of sectors[*].operating_surplus ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _derived_tax_bases_matches_summed_contributions(self) -> TaxBaseDerivationReport:
        expected_personal = base_year_real_output_to_money(
            sum(sector.personal_contribution for sector in self.sectors)
        )
        expected_corporate = base_year_real_output_to_money(
            sum(sector.corporate_contribution for sector in self.sectors)
        )
        expected_consumption = base_year_real_output_to_money(
            sum(sector.consumption_contribution for sector in self.sectors)
        )
        if self.derived_tax_bases.personal_income != expected_personal:
            raise ValueError(
                f"derived_tax_bases.personal_income={self.derived_tax_bases.personal_income} "
                f"does not equal base_year_real_output_to_money(sum of personal_contribution) "
                f"({expected_personal})"
            )
        if self.derived_tax_bases.corporate_profit != expected_corporate:
            raise ValueError(
                f"derived_tax_bases.corporate_profit={self.derived_tax_bases.corporate_profit} "
                f"does not equal base_year_real_output_to_money(sum of corporate_contribution) "
                f"({expected_corporate})"
            )
        if self.derived_tax_bases.taxable_consumption != expected_consumption:
            raise ValueError(
                "derived_tax_bases.taxable_consumption="
                f"{self.derived_tax_bases.taxable_consumption} does not equal "
                f"base_year_real_output_to_money(sum of consumption_contribution) "
                f"({expected_consumption})"
            )
        return self


class ConstitutionSummary(BaseModel):
    """A country's constitutional structure by value, for the report (Phase 3A, §9.1).

    Carries no legitimacy meaning — no anchor, no score, no weight. `constitution_digest` is
    re-derived from the other nine fields by `_constitution_digest_matches_axes` below, so a
    report can never claim a digest that disagrees with its own stored axes.
    """

    model_config = _STRICT_CONFIG

    executive_system: ExecutiveSystem
    executive_selection: ExecutiveSelection
    legislature: Legislature
    territorial_organization: TerritorialOrganization
    judicial_review: JudicialReview
    amendment_difficulty: AmendmentDifficulty
    decree_authority: DecreeAuthority
    executive_term_limit_terms: int | None
    national_election_interval_turns: int | None
    constitution_digest: str


class EconomicBaselineReport(BaseModel):
    """One resolved turn's economic observations, as published in a `PoliticalReport` (Phase 3A,
    §9.1). Structurally identical to `simulation.state.EconomicBaselineState` but kept as a
    separate type — state and report are different concerns even when their shape coincides, the
    same reasoning that keeps every other report type distinct from its state counterpart."""

    model_config = _STRICT_CONFIG

    source_turn: int = Field(ge=0)
    total_gross_output: StrictRealOutput
    unemployment_rate_bps: StrictBps


class PoliticalReport(BaseModel):
    """Structured, machine-readable Phase 3A political outcome for the player country, for one
    turn: full economic-baseline lifecycle (opening, observations, deltas, contribution, closing —
    §6.4), legitimacy resolution, and political-capital resolution.

    Self-validating like `FinanceReport`/`TaxBaseDerivationReport`: ten `@model_validator`s below
    each independently re-derive one equation from the report's own stored fields, using the same
    low-level helpers (`trunc_div_toward_zero`, `clamp_bps`) and calibration constants
    `simulation.legitimacy` uses — but **never by calling `simulation.legitimacy`'s functions**,
    so a bug in one code path is likely to be caught by the other.

    `opening_economic_baseline is None` *is* the "no prior baseline" signal — there is no
    redundant boolean to trust or re-derive alongside it, unlike the original draft's rejected
    `baseline_available: bool` field.
    """

    model_config = _STRICT_CONFIG

    constitution: ConstitutionSummary
    constitutional_order_support_bps: StrictLegitimacyBps
    """The authored value in force this turn. R1: never derived from `constitution`'s axes —
    `_order_support_contribution_matches_drift_formula` below only ever reads this field and
    `opening_legitimacy_bps`, by construction never `self.constitution`."""

    opening_legitimacy_bps: StrictLegitimacyBps
    opening_economic_baseline: EconomicBaselineReport | None = None
    """`None` only on the very first resolution of a fresh scenario (R2, §6.4)."""
    current_total_gross_output: StrictRealOutput
    current_unemployment_rate_bps: StrictBps
    output_change_bps: StrictSignedBps
    """(R5) Unbounded: a baseline of 1 rising to 3 is `+20,000 bps`, larger than the legitimacy
    scale itself. `0` both when `opening_economic_baseline is None` and when its
    `total_gross_output == 0` — two different reasons for the same value, never conflated."""
    output_contribution_bps: StrictSignedBps
    """(R5) Unbounded, inheriting `output_change_bps`'s range at a quarter scale."""
    unemployment_change_bps: StrictSignedLegitimacyBps
    unemployment_contribution_bps: StrictSignedLegitimacyBps
    performance_contribution_bps: StrictSignedLegitimacyBps
    """Capped to `+/-MAX_PERFORMANCE_CONTRIBUTION_BPS` — the first field in this chain the scale
    bound actually applies to."""
    order_support_contribution_bps: StrictSignedLegitimacyBps
    total_legitimacy_change_bps: StrictSignedLegitimacyBps
    """The *applied* change (`closing - opening`), not the requested one — see
    `_total_change_and_closing_legitimacy_match_clamped_formula`."""
    closing_legitimacy_bps: StrictLegitimacyBps
    closing_economic_baseline: EconomicBaselineReport
    """Never `None` after any resolved turn (R2, §6.4)."""

    opening_political_capital: StrictPoliticalCapital
    political_capital_regeneration: StrictPoliticalCapital
    political_capital_spent: StrictPoliticalCapital
    """Always `0` in Phase 3A — nothing spends political capital yet (§7). Carried so the
    reconciliation identity shipped now is already Phase 3B's final one."""
    political_capital_capacity: StrictPoliticalCapitalCapacity
    closing_political_capital: StrictPoliticalCapital

    @model_validator(mode="after")
    def _constitution_digest_matches_axes(self) -> PoliticalReport:
        """(R7) Digest equality alone is not a substitute for field equality — this re-derives the
        digest from the *other nine* stored fields, so a report whose digest and axes have been
        independently tampered can never both look consistent."""
        payload = {
            "executive_system": self.constitution.executive_system.value,
            "executive_selection": self.constitution.executive_selection.value,
            "legislature": self.constitution.legislature.value,
            "territorial_organization": self.constitution.territorial_organization.value,
            "judicial_review": self.constitution.judicial_review.value,
            "amendment_difficulty": self.constitution.amendment_difficulty.value,
            "decree_authority": self.constitution.decree_authority.value,
            "executive_term_limit_terms": self.constitution.executive_term_limit_terms,
            "national_election_interval_turns": self.constitution.national_election_interval_turns,
        }
        expected = canonical_digest(payload)
        if self.constitution.constitution_digest != expected:
            raise ValueError(
                f"constitution.constitution_digest={self.constitution.constitution_digest!r} "
                f"does not match canonical_digest of the other nine constitution fields "
                f"({expected!r})"
            )
        return self

    @model_validator(mode="after")
    def _output_change_matches_formula(self) -> PoliticalReport:
        if (
            self.opening_economic_baseline is None
            or self.opening_economic_baseline.total_gross_output == 0
        ):
            expected = 0
        else:
            expected = trunc_div_toward_zero(
                (
                    self.current_total_gross_output
                    - self.opening_economic_baseline.total_gross_output
                )
                * BPS_DENOMINATOR,
                self.opening_economic_baseline.total_gross_output,
            )
        if self.output_change_bps != expected:
            raise ValueError(
                f"output_change_bps={self.output_change_bps} does not match the formula "
                f"({expected})"
            )
        return self

    @model_validator(mode="after")
    def _output_contribution_matches_formula(self) -> PoliticalReport:
        expected = trunc_div_toward_zero(
            self.output_change_bps * OUTPUT_SENSITIVITY_BPS, BPS_DENOMINATOR
        )
        if self.output_contribution_bps != expected:
            raise ValueError(
                f"output_contribution_bps={self.output_contribution_bps} does not match "
                f"trunc_div_toward_zero(output_change_bps * OUTPUT_SENSITIVITY_BPS, 10_000) "
                f"({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unemployment_change_matches_difference(self) -> PoliticalReport:
        expected = (
            0
            if self.opening_economic_baseline is None
            else self.current_unemployment_rate_bps
            - self.opening_economic_baseline.unemployment_rate_bps
        )
        if self.unemployment_change_bps != expected:
            raise ValueError(
                f"unemployment_change_bps={self.unemployment_change_bps} does not match "
                f"current_unemployment_rate_bps - opening_economic_baseline.unemployment_rate_bps "
                f"({expected})"
            )
        return self

    @model_validator(mode="after")
    def _unemployment_contribution_matches_formula(self) -> PoliticalReport:
        expected = trunc_div_toward_zero(
            -self.unemployment_change_bps * UNEMPLOYMENT_SENSITIVITY_BPS, BPS_DENOMINATOR
        )
        if self.unemployment_contribution_bps != expected:
            raise ValueError(
                f"unemployment_contribution_bps={self.unemployment_contribution_bps} does not "
                f"match trunc_div_toward_zero(-unemployment_change_bps * "
                f"UNEMPLOYMENT_SENSITIVITY_BPS, 10_000) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _performance_contribution_matches_capped_sum(self) -> PoliticalReport:
        expected = clamp_bps(
            self.output_contribution_bps + self.unemployment_contribution_bps,
            low=-MAX_PERFORMANCE_CONTRIBUTION_BPS,
            high=MAX_PERFORMANCE_CONTRIBUTION_BPS,
        )
        if self.performance_contribution_bps != expected:
            raise ValueError(
                f"performance_contribution_bps={self.performance_contribution_bps} does not "
                f"match clamp(output_contribution_bps + unemployment_contribution_bps, "
                f"+/-{MAX_PERFORMANCE_CONTRIBUTION_BPS}) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _order_support_contribution_matches_drift_formula(self) -> PoliticalReport:
        """(R1) The derivation has exactly two inputs — `constitutional_order_support_bps` and
        `opening_legitimacy_bps` — and by construction cannot reference any constitutional axis;
        there is no `self.constitution` anywhere in this method."""
        expected = trunc_div_toward_zero(
            (self.constitutional_order_support_bps - self.opening_legitimacy_bps) * DRIFT_RATE_BPS,
            BPS_DENOMINATOR,
        )
        if self.order_support_contribution_bps != expected:
            raise ValueError(
                f"order_support_contribution_bps={self.order_support_contribution_bps} does not "
                f"match trunc_div_toward_zero((constitutional_order_support_bps - "
                f"opening_legitimacy_bps) * DRIFT_RATE_BPS, 10_000) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _total_change_and_closing_legitimacy_match_clamped_formula(self) -> PoliticalReport:
        requested = self.order_support_contribution_bps + self.performance_contribution_bps
        capped = clamp_bps(
            requested,
            low=-MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
            high=MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
        )
        expected_closing = clamp_bps(
            self.opening_legitimacy_bps + capped, low=0, high=BPS_DENOMINATOR
        )
        expected_applied = expected_closing - self.opening_legitimacy_bps
        if self.total_legitimacy_change_bps != expected_applied:
            raise ValueError(
                f"total_legitimacy_change_bps={self.total_legitimacy_change_bps} does not match "
                f"the applied (post-clamp) change ({expected_applied})"
            )
        if self.closing_legitimacy_bps != expected_closing:
            raise ValueError(
                f"closing_legitimacy_bps={self.closing_legitimacy_bps} does not match "
                f"clamp(opening_legitimacy_bps + clamp(requested, +/-"
                f"{MAX_TOTAL_LEGITIMACY_CHANGE_BPS}), 0, {BPS_DENOMINATOR}) ({expected_closing})"
            )
        return self

    @model_validator(mode="after")
    def _political_capital_reconciles(self) -> PoliticalReport:
        expected_regeneration = POLITICAL_CAPITAL_BASE_REGENERATION + trunc_div_toward_zero(
            self.closing_legitimacy_bps * LEGITIMACY_REGENERATION_COEFFICIENT, BPS_DENOMINATOR
        )
        if self.political_capital_regeneration != expected_regeneration:
            raise ValueError(
                f"political_capital_regeneration={self.political_capital_regeneration} does not "
                f"match POLITICAL_CAPITAL_BASE_REGENERATION + trunc_div_toward_zero("
                f"closing_legitimacy_bps * LEGITIMACY_REGENERATION_COEFFICIENT, 10_000) "
                f"({expected_regeneration})"
            )
        # (Phase 3B1) Against opening alone, not opening + regeneration: capital is committed at
        # the start of a turn, before regeneration is known, so a report claiming a government
        # spent more than it held would describe a turn that could not have happened. Mirrors the
        # identical guard in `legitimacy.resolve_political_capital`.
        if self.political_capital_spent > self.opening_political_capital:
            raise ValueError(
                f"political_capital_spent={self.political_capital_spent} exceeds "
                f"opening_political_capital={self.opening_political_capital}"
            )
        available = self.opening_political_capital + self.political_capital_regeneration
        expected_closing = min(
            self.political_capital_capacity, available - self.political_capital_spent
        )
        if self.closing_political_capital != expected_closing:
            raise ValueError(
                f"closing_political_capital={self.closing_political_capital} does not match "
                f"min(political_capital_capacity, opening_political_capital + "
                f"political_capital_regeneration - political_capital_spent) ({expected_closing})"
            )
        return self

    @model_validator(mode="after")
    def _baseline_lifecycle_is_coherent(self) -> PoliticalReport:
        """(R2) The four-stage lifecycle (§6.4), enforced end to end."""
        if self.opening_economic_baseline is None:
            for field_name in (
                "output_change_bps",
                "output_contribution_bps",
                "unemployment_change_bps",
                "unemployment_contribution_bps",
            ):
                if getattr(self, field_name) != 0:
                    raise ValueError(
                        f"opening_economic_baseline is None but {field_name}="
                        f"{getattr(self, field_name)} (expected 0 — no prior turn, no performance "
                        "to assess)"
                    )
        else:
            expected_source_turn = self.opening_economic_baseline.source_turn + 1
            if self.closing_economic_baseline.source_turn != expected_source_turn:
                raise ValueError(
                    "closing_economic_baseline.source_turn="
                    f"{self.closing_economic_baseline.source_turn} does not equal "
                    f"opening_economic_baseline.source_turn + 1 ({expected_source_turn})"
                )
        if self.closing_economic_baseline.total_gross_output != self.current_total_gross_output:
            raise ValueError(
                "closing_economic_baseline.total_gross_output="
                f"{self.closing_economic_baseline.total_gross_output} does not equal "
                f"current_total_gross_output ({self.current_total_gross_output})"
            )
        if (
            self.closing_economic_baseline.unemployment_rate_bps
            != self.current_unemployment_rate_bps
        ):
            raise ValueError(
                "closing_economic_baseline.unemployment_rate_bps="
                f"{self.closing_economic_baseline.unemployment_rate_bps} does not equal "
                f"current_unemployment_rate_bps ({self.current_unemployment_rate_bps})"
            )
        return self


def _legislative_axis_component_bps(
    *,
    preference_bps: int,
    direction: LegislativeChangeDirection,
    intensity_bps: int,
    weight_bps: int,
) -> int:
    """One policy axis's contribution to `policy_compatibility_bps`, reimplemented locally from the
    report's own stored fields — never by calling `legislative_voting._axis_component_bps` (R1: two
    independent code paths for the same formula, exactly like every other report validator in this
    module)."""
    if direction is LegislativeChangeDirection.UNCHANGED:
        return 0
    magnitude = trunc_div_toward_zero(preference_bps * intensity_bps, BPS_DENOMINATOR)
    weighted = trunc_div_toward_zero(magnitude * weight_bps, BPS_DENOMINATOR)
    return -weighted if direction is LegislativeChangeDirection.DECREASE else weighted


class BlocVoteReport(BaseModel):
    """One row per `(party_id, bloc_id, chamber)`: how one caucus voted in one chamber, carrying
    every field its validators (and `LegislativeReport`'s cross-row validators) need to replay the
    whole support chain independently, from role anchor to whipped final position (Phase 3B1, §7).

    A bloc seated in two chambers of a bicameral legislature produces **two** rows here — one per
    chamber, since seats, apportionment and vote outcome are per-chamber — but political-capital
    influence targets `(party_id, bloc_id)` alone, never a chamber. So `political_capital_allocated`
    and `influence_bps` are required to be identical across a repeated bloc identity's rows
    (`LegislativeReport._bicameral_allocation_is_consistent_per_bloc_identity`), while `seats`,
    `numerator`, `base_seats`, `remainder`, `bonus_seat` and `supporting_seats` are genuinely
    per-chamber and may differ.
    """

    model_config = _STRICT_CONFIG

    party_id: str
    bloc_id: str
    chamber: LegislativeChamber
    seats: StrictSeatCount
    government_role: GovernmentRole
    government_relationship_bps: StrictRelationshipBps
    discipline_bps: StrictBps
    tax_preference_bps: StrictPreferenceBps
    spending_preference_bps: StrictPreferenceBps
    baseline_support_bps: StrictBps
    policy_compatibility_bps: StrictSignedBps
    raw_support_bps: StrictBps
    political_capital_allocated: StrictPoliticalCapital
    influence_bps: StrictBps
    final_support_bps: StrictBps
    effective_support_bps: StrictBps
    numerator: StrictSeatNumerator
    base_seats: StrictSeatCount
    remainder: StrictBps
    bonus_seat: bool
    supporting_seats: StrictSeatCount

    @model_validator(mode="after")
    def _baseline_support_matches_role_and_relationship(self) -> BlocVoteReport:
        expected = clamp_bps(
            ROLE_ANCHOR_BPS[self.government_role]
            + trunc_div_toward_zero(
                self.government_relationship_bps * RELATIONSHIP_WEIGHT_BPS, BPS_DENOMINATOR
            )
        )
        if self.baseline_support_bps != expected:
            raise ValueError(
                f"baseline_support_bps={self.baseline_support_bps} does not match "
                f"clamp(ROLE_ANCHOR_BPS[{self.government_role.value!r}] + relationship "
                f"contribution) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _raw_support_is_clamped_sum(self) -> BlocVoteReport:
        expected = clamp_bps(self.baseline_support_bps + self.policy_compatibility_bps)
        if self.raw_support_bps != expected:
            raise ValueError(
                f"raw_support_bps={self.raw_support_bps} does not match "
                f"clamp(baseline_support_bps + policy_compatibility_bps) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _influence_matches_allocation(self) -> BlocVoteReport:
        expected = min(
            MAX_INFLUENCE_BPS, self.political_capital_allocated * INFLUENCE_BPS_PER_CAPITAL
        )
        if self.influence_bps != expected:
            raise ValueError(
                f"influence_bps={self.influence_bps} does not match "
                f"min(MAX_INFLUENCE_BPS, political_capital_allocated * "
                f"INFLUENCE_BPS_PER_CAPITAL) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _final_support_is_clamped_sum(self) -> BlocVoteReport:
        expected = clamp_bps(self.raw_support_bps + self.influence_bps)
        if self.final_support_bps != expected:
            raise ValueError(
                f"final_support_bps={self.final_support_bps} does not match "
                f"clamp(raw_support_bps + influence_bps) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _effective_support_matches_discipline_amplification(self) -> BlocVoteReport:
        midpoint = BPS_DENOMINATOR // 2
        expected = clamp_bps(
            self.final_support_bps
            + trunc_div_toward_zero(
                (self.final_support_bps - midpoint) * self.discipline_bps, BPS_DENOMINATOR
            )
        )
        if self.effective_support_bps != expected:
            raise ValueError(
                f"effective_support_bps={self.effective_support_bps} does not match "
                f"clamp(final_support_bps + discipline amplification) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _numerator_base_remainder_and_supporting_seats_are_consistent(self) -> BlocVoteReport:
        """(R4) Everything a single row can verify about its own apportionment inputs — the
        cross-row largest-remainder award itself is `LegislativeReport
        ._chamber_apportionment_is_correct`'s job, since it is comparative across every row in the
        same chamber and cannot be decided from one row alone."""
        expected_numerator = self.seats * self.effective_support_bps
        if self.numerator != expected_numerator:
            raise ValueError(
                f"numerator={self.numerator} does not match seats * effective_support_bps "
                f"({expected_numerator})"
            )
        expected_base = self.numerator // BPS_DENOMINATOR
        if self.base_seats != expected_base:
            raise ValueError(
                f"base_seats={self.base_seats} does not match numerator // 10_000 ({expected_base})"
            )
        expected_remainder = self.numerator % BPS_DENOMINATOR
        if self.remainder != expected_remainder:
            raise ValueError(
                f"remainder={self.remainder} does not match numerator % 10_000 "
                f"({expected_remainder})"
            )
        expected_supporting = self.base_seats + (1 if self.bonus_seat else 0)
        if self.supporting_seats != expected_supporting:
            raise ValueError(
                f"supporting_seats={self.supporting_seats} does not match base_seats + "
                f"int(bonus_seat) ({expected_supporting})"
            )
        if self.supporting_seats > self.seats:
            raise ValueError(
                f"supporting_seats={self.supporting_seats} exceeds seats={self.seats} (P2)"
            )
        return self


class ChamberVoteReport(BaseModel):
    """One chamber's vote: its size, how many seats support the proposal, the strict majority it
    needed, and the (R4) chamber-level largest-remainder apportionment totals."""

    model_config = _STRICT_CONFIG

    chamber: LegislativeChamber
    total_seats: StrictPositiveSeatCount
    supporting_seats: StrictSeatCount
    required_yes_seats: StrictPositiveSeatCount
    shortfall_seats: StrictSeatCount
    target_total: StrictSeatCount
    extras_awarded: StrictSeatCount
    passed: bool

    @model_validator(mode="after")
    def _required_yes_seats_is_strict_majority(self) -> ChamberVoteReport:
        expected = self.total_seats // 2 + 1
        if self.required_yes_seats != expected:
            raise ValueError(
                f"required_yes_seats={self.required_yes_seats} does not match "
                f"total_seats // 2 + 1 ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _passed_and_shortfall_match_strict_majority(self) -> ChamberVoteReport:
        if self.supporting_seats > self.total_seats:
            raise ValueError(
                f"supporting_seats={self.supporting_seats} exceeds total_seats={self.total_seats}"
            )
        expected_passed = self.supporting_seats >= self.required_yes_seats
        if self.passed != expected_passed:
            raise ValueError(
                f"passed={self.passed} does not match supporting_seats >= required_yes_seats "
                f"({expected_passed})"
            )
        expected_shortfall = max(0, self.required_yes_seats - self.supporting_seats)
        if self.shortfall_seats != expected_shortfall:
            raise ValueError(
                f"shortfall_seats={self.shortfall_seats} does not match "
                f"max(0, required_yes_seats - supporting_seats) ({expected_shortfall})"
            )
        return self

    @model_validator(mode="after")
    def _supporting_seats_equals_target_total(self) -> ChamberVoteReport:
        """(R4, P1) `target_total` is the chamber's true support mass; `supporting_seats` must
        equal it exactly, not merely bound it."""
        if self.supporting_seats != self.target_total:
            raise ValueError(
                f"supporting_seats={self.supporting_seats} does not match target_total="
                f"{self.target_total} (P1: sum(supporting_seats) == target_total)"
            )
        if self.extras_awarded < 0:
            raise ValueError(f"extras_awarded cannot be negative, got {self.extras_awarded}")
        return self


class LegislativeReport(BaseModel):
    """Structured, machine-readable Phase 3B1 legislative outcome for the player country's one
    budget proposal this turn: which route it took, how (if at all) each chamber voted, and how
    much political capital was committed.

    Self-validating like `PoliticalReport`: every validator below independently re-derives one
    equation from the report's own stored fields, using the same low-level helpers
    (`trunc_div_toward_zero`, `clamp_bps`) and calibration constants `simulation.legislative_voting`
    and `simulation.apportionment` use — but **never by calling either module's functions**, so a
    bug in one code path is likely to be caught by the other.

    `route is None` *is* the "no proposal was submitted" signal for `NO_PROPOSAL` — there is no
    redundant boolean alongside it. `legislature_present` is a recorded fact about the country's
    state, not derived from `route`/`outcome`: it is required `True` whenever the outcome is a
    legislative one (there is nothing to vote in otherwise), but for `NO_PROPOSAL`/
    `ENACTED_BY_DECREE` it simply records whether the state actually has a legislature.

    `budget_decision_digest` (Phase 3B1, R8) is `simulation.decisions.budget_decision_digest`'s
    output over the actually-submitted `BudgetDecision`, or `None` for `NO_PROPOSAL` — never the
    decision itself, so this report cannot grow into a second store of decision content that could
    drift from the real one. Only its *syntax* is checked here (a properly-shaped hex digest is
    present exactly when a proposal was submitted); whether it is the digest of the RIGHT decision
    is `simulation.reconciliation`'s job (group 18), which is the only place that ever recomputes
    it — mirroring exactly how `constitution.constitution_digest` is verified against a real
    `ConstitutionState` outside this class.
    """

    model_config = _STRICT_CONFIG

    outcome: LegislativeOutcome
    route: ProposalRoute | None
    legislature_present: bool
    tax_delta_bps: StrictSignedBps
    tax_direction: LegislativeChangeDirection
    tax_intensity_bps: StrictBps
    opening_total_program_spending: StrictMoney
    proposed_total_program_spending: StrictMoney
    spending_direction: LegislativeChangeDirection
    spending_intensity_bps: StrictBps
    chambers: tuple[ChamberVoteReport, ...] = Field(default_factory=tuple)
    blocs: tuple[BlocVoteReport, ...] = Field(default_factory=tuple)
    opening_political_capital: StrictPoliticalCapital
    political_capital_committed: StrictPoliticalCapital
    budget_decision_digest: str | None

    @model_validator(mode="after")
    def _budget_decision_digest_matches_proposal_presence(self) -> LegislativeReport:
        """(R8) Syntax only: `NO_PROPOSAL` carries no decision to digest, so it must be `None`;
        every other outcome describes a real submitted `BudgetDecision`, so it must carry a
        properly-shaped digest. Whether that digest is the RIGHT one is never checked here — see
        the class docstring."""
        if self.outcome is LegislativeOutcome.NO_PROPOSAL:
            if self.budget_decision_digest is not None:
                raise ValueError(
                    "NO_PROPOSAL must carry budget_decision_digest=None, got "
                    f"{self.budget_decision_digest!r}"
                )
            return self
        if self.budget_decision_digest is None:
            raise ValueError(
                f"outcome {self.outcome.value!r} must carry a budget_decision_digest, not None"
            )
        if not _HEX_DIGEST_PATTERN.fullmatch(self.budget_decision_digest):
            raise ValueError(
                f"budget_decision_digest={self.budget_decision_digest!r} is not a lowercase "
                "64-character hexadecimal digest"
            )
        return self

    @model_validator(mode="after")
    def _tax_change_representation_is_internally_consistent(self) -> LegislativeReport:
        if self.tax_delta_bps > 0:
            expected_direction = LegislativeChangeDirection.INCREASE
        elif self.tax_delta_bps < 0:
            expected_direction = LegislativeChangeDirection.DECREASE
        else:
            expected_direction = LegislativeChangeDirection.UNCHANGED
        if self.tax_direction != expected_direction:
            raise ValueError(
                f"tax_direction={self.tax_direction.value!r} does not match the sign of "
                f"tax_delta_bps={self.tax_delta_bps} (expected {expected_direction.value!r})"
            )
        expected_intensity = min(
            BPS_DENOMINATOR,
            trunc_div_toward_zero(
                abs(self.tax_delta_bps) * BPS_DENOMINATOR, TAX_FULL_INTENSITY_BPS
            ),
        )
        if self.tax_intensity_bps != expected_intensity:
            raise ValueError(
                f"tax_intensity_bps={self.tax_intensity_bps} does not match "
                f"min(10_000, trunc_div_toward_zero(abs(tax_delta_bps) * 10_000, "
                f"TAX_FULL_INTENSITY_BPS)) ({expected_intensity})"
            )
        return self

    @model_validator(mode="after")
    def _spending_change_representation_matches_totals(self) -> LegislativeReport:
        """(R7) The four exhaustive branches, reimplemented locally: the two `opening == 0`
        branches are decided before any division, exactly like `legislative_voting
        .spending_policy_change` and `legitimacy.py`'s own zero-baseline branch."""
        opening = self.opening_total_program_spending
        proposed = self.proposed_total_program_spending
        if opening == 0:
            if proposed == 0:
                expected_direction = LegislativeChangeDirection.UNCHANGED
                expected_intensity = 0
            else:
                expected_direction = LegislativeChangeDirection.INCREASE
                expected_intensity = BPS_DENOMINATOR
        elif proposed == 0:
            expected_direction = LegislativeChangeDirection.DECREASE
            expected_intensity = BPS_DENOMINATOR
        else:
            relative_change_bps = trunc_div_toward_zero(
                (proposed - opening) * BPS_DENOMINATOR, opening
            )
            expected_intensity = min(
                BPS_DENOMINATOR,
                trunc_div_toward_zero(
                    abs(relative_change_bps) * BPS_DENOMINATOR, SPENDING_FULL_INTENSITY_BPS
                ),
            )
            if proposed > opening:
                expected_direction = LegislativeChangeDirection.INCREASE
            elif proposed < opening:
                expected_direction = LegislativeChangeDirection.DECREASE
            else:
                expected_direction = LegislativeChangeDirection.UNCHANGED
        if self.spending_direction != expected_direction:
            raise ValueError(
                f"spending_direction={self.spending_direction.value!r} does not match the "
                f"formula over opening/proposed_total_program_spending (expected "
                f"{expected_direction.value!r})"
            )
        if self.spending_intensity_bps != expected_intensity:
            raise ValueError(
                f"spending_intensity_bps={self.spending_intensity_bps} does not match the "
                f"formula over opening/proposed_total_program_spending ({expected_intensity})"
            )
        return self

    @model_validator(mode="after")
    def _policy_compatibility_matches_preferences_direction_and_intensity(
        self,
    ) -> LegislativeReport:
        for bloc in self.blocs:
            tax_component = _legislative_axis_component_bps(
                preference_bps=bloc.tax_preference_bps,
                direction=self.tax_direction,
                intensity_bps=self.tax_intensity_bps,
                weight_bps=TAX_WEIGHT_BPS,
            )
            spending_component = _legislative_axis_component_bps(
                preference_bps=bloc.spending_preference_bps,
                direction=self.spending_direction,
                intensity_bps=self.spending_intensity_bps,
                weight_bps=SPENDING_WEIGHT_BPS,
            )
            expected = tax_component + spending_component
            if bloc.policy_compatibility_bps != expected:
                raise ValueError(
                    f"bloc ({bloc.party_id!r}, {bloc.bloc_id!r}) chamber "
                    f"{bloc.chamber.value!r}: policy_compatibility_bps="
                    f"{bloc.policy_compatibility_bps} does not match tax + spending axis "
                    f"components ({expected})"
                )
        return self

    @model_validator(mode="after")
    def _bicameral_allocation_is_consistent_per_bloc_identity(self) -> LegislativeReport:
        """Influence targets `(party_id, bloc_id)`, never a chamber (report corrections §3): a
        bloc seated in two chambers must show the identical allocated capital and influence on
        both rows, so the commitment validator below can safely count each identity once."""
        seen: dict[tuple[str, str], BlocVoteReport] = {}
        for bloc in self.blocs:
            key = (bloc.party_id, bloc.bloc_id)
            prior = seen.get(key)
            if prior is None:
                seen[key] = bloc
                continue
            if prior.political_capital_allocated != bloc.political_capital_allocated:
                raise ValueError(
                    f"bloc {key!r} has inconsistent political_capital_allocated across chamber "
                    f"rows: {prior.political_capital_allocated} vs "
                    f"{bloc.political_capital_allocated}"
                )
            if prior.influence_bps != bloc.influence_bps:
                raise ValueError(
                    f"bloc {key!r} has inconsistent influence_bps across chamber rows: "
                    f"{prior.influence_bps} vs {bloc.influence_bps}"
                )
        return self

    @model_validator(mode="after")
    def _chamber_apportionment_is_correct(self) -> LegislativeReport:
        """(R4) The chamber-level largest-remainder cross-row check: `target_total`,
        `extras_awarded`, and exactly which rows receive `bonus_seat`, replayed independently from
        every bloc row seated in that chamber. This is the one check a single `BlocVoteReport`
        cannot perform on itself — it is comparative across every row in the same chamber — and is
        the check that catches a bonus moved from a larger remainder to a smaller one even though
        every individual row stays internally consistent."""
        for chamber_report in self.chambers:
            rows = [bloc for bloc in self.blocs if bloc.chamber == chamber_report.chamber]
            target_total = sum(row.numerator for row in rows) // BPS_DENOMINATOR
            if chamber_report.target_total != target_total:
                raise ValueError(
                    f"chamber {chamber_report.chamber.value!r}: target_total="
                    f"{chamber_report.target_total} does not match "
                    f"sum(numerator) // 10_000 ({target_total})"
                )
            extras = target_total - sum(row.base_seats for row in rows)
            if chamber_report.extras_awarded != extras:
                raise ValueError(
                    f"chamber {chamber_report.chamber.value!r}: extras_awarded="
                    f"{chamber_report.extras_awarded} does not match target_total - "
                    f"sum(base_seats) ({extras})"
                )
            order = sorted(rows, key=lambda row: (-row.remainder, row.party_id, row.bloc_id))
            expected_bonus = {(row.party_id, row.bloc_id) for row in order[:extras]}
            actual_bonus = {(row.party_id, row.bloc_id) for row in rows if row.bonus_seat}
            if actual_bonus != expected_bonus:
                raise ValueError(
                    f"chamber {chamber_report.chamber.value!r}: bonus_seat is awarded to "
                    f"{sorted(actual_bonus)!r}, but the largest-remainder ordering (ties broken "
                    f"by (party_id, bloc_id)) awards it to {sorted(expected_bonus)!r}"
                )
            summed_supporting = sum(row.supporting_seats for row in rows)
            if summed_supporting != chamber_report.supporting_seats:
                raise ValueError(
                    f"chamber {chamber_report.chamber.value!r}: sum(bloc supporting_seats)="
                    f"{summed_supporting} does not match chamber supporting_seats="
                    f"{chamber_report.supporting_seats}"
                )
        return self

    @model_validator(mode="after")
    def _outcome_route_and_chamber_matrix_is_valid(self) -> LegislativeReport:
        """(Report corrections §1-2) The complete outcome/route/chamber matrix, with an explicit
        emptiness guard on every legislative branch — never `all([])` on a possibly-empty
        `chambers` tuple."""
        if self.outcome is LegislativeOutcome.NO_PROPOSAL:
            if self.route is not None:
                raise ValueError(f"NO_PROPOSAL must carry route=None, got {self.route!r}")
            if self.chambers or self.blocs:
                raise ValueError("NO_PROPOSAL must carry no chamber or bloc rows")
            if self.political_capital_committed != 0:
                raise ValueError(
                    "NO_PROPOSAL must commit zero political capital, got "
                    f"{self.political_capital_committed}"
                )
            if (
                self.tax_delta_bps != 0
                or self.tax_direction != LegislativeChangeDirection.UNCHANGED
            ):
                raise ValueError("NO_PROPOSAL must carry zero tax-change direction and intensity")
            if (
                self.spending_direction != LegislativeChangeDirection.UNCHANGED
                or self.spending_intensity_bps != 0
            ):
                raise ValueError(
                    "NO_PROPOSAL must carry zero spending-change direction and intensity"
                )
            if self.proposed_total_program_spending != self.opening_total_program_spending:
                raise ValueError(
                    "NO_PROPOSAL must leave proposed_total_program_spending equal to "
                    "opening_total_program_spending"
                )
            return self

        if self.route is None:
            raise ValueError(f"outcome {self.outcome.value!r} must carry a route, not None")

        if self.outcome is LegislativeOutcome.ENACTED_BY_DECREE:
            if self.route is not ProposalRoute.DECREE:
                raise ValueError("ENACTED_BY_DECREE must carry route=DECREE")
            if self.chambers or self.blocs:
                raise ValueError("ENACTED_BY_DECREE must carry no chamber or bloc rows")
            return self

        # PASSED_LEGISLATIVE / FAILED_LEGISLATIVE
        if self.route is not ProposalRoute.LEGISLATIVE:
            raise ValueError(f"outcome {self.outcome.value!r} must carry route=LEGISLATIVE")
        if not self.legislature_present:
            raise ValueError(f"outcome {self.outcome.value!r} requires legislature_present=True")
        if not self.chambers:
            raise ValueError(
                f"outcome {self.outcome.value!r} must carry at least one chamber row — a "
                "legislative outcome with zero chambers is never valid"
            )
        every_chamber_passed = all(chamber.passed for chamber in self.chambers)
        if self.outcome is LegislativeOutcome.PASSED_LEGISLATIVE and not every_chamber_passed:
            raise ValueError("PASSED_LEGISLATIVE requires every chamber row to have passed")
        if self.outcome is LegislativeOutcome.FAILED_LEGISLATIVE and every_chamber_passed:
            raise ValueError("FAILED_LEGISLATIVE requires at least one chamber row to have failed")
        return self

    @model_validator(mode="after")
    def _political_capital_committed_matches_route(self) -> LegislativeReport:
        """(Report corrections §2-3) Commitment is the sum of one allocation per unique
        `(party_id, bloc_id)` — never a sum over every chamber row, which would double-count a
        bicameral bloc."""
        if self.outcome is LegislativeOutcome.NO_PROPOSAL:
            expected = 0
        elif self.route is ProposalRoute.DECREE:
            expected = DECREE_POLITICAL_CAPITAL_COST
        else:
            unique_allocations: dict[tuple[str, str], int] = {}
            for bloc in self.blocs:
                unique_allocations[(bloc.party_id, bloc.bloc_id)] = bloc.political_capital_allocated
            expected = sum(unique_allocations.values())
        if self.political_capital_committed != expected:
            raise ValueError(
                f"political_capital_committed={self.political_capital_committed} does not match "
                f"the expected commitment for outcome={self.outcome.value!r}/"
                f"route={self.route!r} ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _committed_within_opening_capital(self) -> LegislativeReport:
        if self.political_capital_committed > self.opening_political_capital:
            raise ValueError(
                f"political_capital_committed={self.political_capital_committed} exceeds "
                f"opening_political_capital={self.opening_political_capital}"
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
    production: ProductionReport | None = None
    """`None` only when production did not run (never for a successful Phase 2B1+ turn on a
    valid player state — `simulation.invariants` requires player economy before resolution
    can even begin)."""
    tax_base_derivation: TaxBaseDerivationReport | None = None
    """`None` only when derivation did not run (never for a successful Phase 2B2+ turn on a
    valid player state). Named distinctly from `FinanceReport.tax_bases` to avoid confusion
    between "this turn's derivation detail" and "the bases finance actually applied.\""""
    labor_market: LaborMarketReport | None = None
    """`None` only when labor allocation did not run (never for a successful Phase 2B3+ turn on
    a valid player state). Runs before production in the same phase; see `phases.py`."""
    resources: ResourceExtractionReport | None = None
    """`None` only when resource extraction did not run (never for a successful Phase 2C1+ turn
    on a valid player state). Runs immediately after labor allocation and before resource
    depletion is written back to state, in the same phase; see `phases.py`."""
    political: PoliticalReport | None = None
    """`None` only when the political phase did not run (never for a successful Phase 3A+ turn
    on a valid player state — `simulation.invariants` requires player politics before resolution
    can even begin). Runs in slot 10, after every economic phase; see `phases.py`."""
    legislative: LegislativeReport | None = None
    """`None` only when the legislative phase did not run (never for a successful Phase 3B1+ turn
    on a valid player state — `simulation.invariants` requires player politics, and therefore a
    legislature-or-none decision, before resolution can even begin). Built for every resolved
    turn, including `NO_PROPOSAL` ones; the vote itself runs in slot 1, assembly in slot 15; see
    `phases.py`."""

    @model_validator(mode="after")
    def _labor_resources_production_derivation_finance_political_and_legislative_are_all_present_or_all_absent(
        self,
    ) -> TurnReport:
        """R1 (extended, Phase 2B3; extended again, Phase 2C1, Phase 3A and Phase 3B1): a partial
        combination of the seven player-economy/politics reports would represent a broken audit
        chain (e.g. production ran but derivation silently didn't) — reject it outright rather
        than accepting whatever subset happens to be present.
        """
        present = (
            self.labor_market is not None,
            self.resources is not None,
            self.production is not None,
            self.tax_base_derivation is not None,
            self.finance is not None,
            self.political is not None,
            self.legislative is not None,
        )
        if any(present) and not all(present):
            raise ValueError(
                "labor_market, resources, production, tax_base_derivation, finance, political, "
                "and legislative must be all present or all absent on a TurnReport — got "
                f"present={present} (labor_market, resources, production, tax_base_derivation, "
                "finance, political, legislative)"
            )
        return self

    @model_validator(mode="after")
    def _legislative_commitment_matches_political_report(self) -> TurnReport:
        if self.legislative is None or self.political is None:
            return self
        if self.legislative.political_capital_committed != self.political.political_capital_spent:
            raise ValueError(
                "legislative.political_capital_committed="
                f"{self.legislative.political_capital_committed} does not match "
                f"political.political_capital_spent ({self.political.political_capital_spent})"
            )
        return self

    @model_validator(mode="after")
    def _legislative_opening_capital_matches_political_report(self) -> TurnReport:
        if self.legislative is None or self.political is None:
            return self
        if self.legislative.opening_political_capital != self.political.opening_political_capital:
            raise ValueError(
                "legislative.opening_political_capital="
                f"{self.legislative.opening_political_capital} does not match "
                f"political.opening_political_capital ({self.political.opening_political_capital})"
            )
        return self

    @model_validator(mode="after")
    def _legislative_opening_spending_matches_finance(self) -> TurnReport:
        if self.legislative is None or self.finance is None:
            return self
        expected = self.finance.previous_spending_plan.total()
        if self.legislative.opening_total_program_spending != expected:
            raise ValueError(
                "legislative.opening_total_program_spending="
                f"{self.legislative.opening_total_program_spending} does not match "
                f"finance.previous_spending_plan.total() ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _political_current_output_matches_production(self) -> TurnReport:
        """Phase 3A: `PoliticalReport.current_total_gross_output` must equal
        `ProductionReport.total_gross_output` — the political phase must have assessed THIS
        turn's actual economy, not a stale or fabricated figure."""
        if self.political is None or self.production is None:
            return self
        if self.political.current_total_gross_output != self.production.total_gross_output:
            raise ValueError(
                "political.current_total_gross_output="
                f"{self.political.current_total_gross_output} does not match "
                f"production.total_gross_output ({self.production.total_gross_output})"
            )
        return self

    @model_validator(mode="after")
    def _political_current_unemployment_matches_labor_market(self) -> TurnReport:
        """Phase 3A: `PoliticalReport.current_unemployment_rate_bps` must equal
        `LaborMarketReport.unemployment_rate_bps` — same reasoning as the output check above."""
        if self.political is None or self.labor_market is None:
            return self
        if self.political.current_unemployment_rate_bps != self.labor_market.unemployment_rate_bps:
            raise ValueError(
                "political.current_unemployment_rate_bps="
                f"{self.political.current_unemployment_rate_bps} does not match "
                f"labor_market.unemployment_rate_bps ({self.labor_market.unemployment_rate_bps})"
            )
        return self

    @model_validator(mode="after")
    def _political_baseline_source_turns_match_resolved_turn(self) -> TurnReport:
        """Phase 3A: the closing baseline this turn writes is stamped with the turn it actually
        describes, and — when present — the opening baseline is stamped with the PREVIOUS turn,
        proving the baseline the political phase read really was the prior turn's, not a stale or
        substituted one.

        `resolved_turn` is `state.turn` *before* resolution (see that field's docstring), but
        `EconomicBaselineState.source_turn` is `state.turn` of the state that CARRIES the
        baseline — i.e. the state produced by this resolution, `resolved_turn + 1` (R6: "after
        resolving turn 0 the new state has turn == 1 and carries a baseline stamped
        source_turn == 1"). The opening baseline, read from the state going INTO this
        resolution, is therefore stamped with `resolved_turn` itself.
        """
        if self.political is None:
            return self
        expected_closing_turn = self.resolved_turn + 1
        if self.political.closing_economic_baseline.source_turn != expected_closing_turn:
            raise ValueError(
                "political.closing_economic_baseline.source_turn="
                f"{self.political.closing_economic_baseline.source_turn} does not match "
                f"resolved_turn + 1 ({expected_closing_turn})"
            )
        if self.political.opening_economic_baseline is not None:
            expected_opening_turn = self.resolved_turn
            if self.political.opening_economic_baseline.source_turn != expected_opening_turn:
                raise ValueError(
                    "political.opening_economic_baseline.source_turn="
                    f"{self.political.opening_economic_baseline.source_turn} does not match "
                    f"resolved_turn ({expected_opening_turn})"
                )
        return self

    @model_validator(mode="after")
    def _labor_market_extraction_sector_matches_resources_extraction_sector_workers(
        self,
    ) -> TurnReport:
        """Phase 2C1: `LaborMarketReport.sectors[EXTRACTION].allocated_workers` must equal
        `ResourceExtractionReport.extraction_sector_workers` — the worker budget resource
        sub-allocation actually used must be the exact number labor allocation gave the
        extraction sector, not merely a similar internally-valid number.
        """
        if self.labor_market is None or self.resources is None:
            return self
        extraction_row = next(
            (s for s in self.labor_market.sectors if s.category == SectorCategory.EXTRACTION), None
        )
        if extraction_row is None:
            raise ValueError("labor_market.sectors is missing the EXTRACTION category")
        if extraction_row.allocated_workers != self.resources.extraction_sector_workers:
            raise ValueError(
                "labor_market.sectors[EXTRACTION].allocated_workers="
                f"{extraction_row.allocated_workers} does not match "
                "resources.extraction_sector_workers="
                f"{self.resources.extraction_sector_workers}"
            )
        return self

    @model_validator(mode="after")
    def _labor_market_allocation_matches_production_employment(self) -> TurnReport:
        """Phase 2B3: per `SectorCategory` — matched by category identity, never tuple position
        — `LaborMarketReport.allocated_workers` must equal what `ProductionReport` used as
        `employed_workers` for that same sector. Two internally-valid reports could otherwise
        each be correct in isolation while silently describing different employment numbers.
        """
        if self.labor_market is None or self.production is None:
            return self
        allocated_by_category = {s.category: s.allocated_workers for s in self.labor_market.sectors}
        production_by_category = {s.category: s.employed_workers for s in self.production.sectors}
        for category, allocated in allocated_by_category.items():
            expected = production_by_category.get(category)
            if expected is None:
                raise ValueError(
                    f"labor_market references sector category {category.value!r} that does not "
                    "appear in production.sectors"
                )
            if allocated != expected:
                raise ValueError(
                    f"labor_market.sectors allocated_workers for category {category.value!r} "
                    f"({allocated}) does not match production.sectors employed_workers for the "
                    f"same category ({expected})"
                )
        return self

    @model_validator(mode="after")
    def _production_output_matches_tax_base_derivation_input(self) -> TurnReport:
        """R1: per `SectorCategory` — matched by category identity, never tuple position —
        `ProductionReport.actual_output` must equal what `TaxBaseDerivationReport` used as its
        input for that same sector. Two internally-valid reports could otherwise each be
        correct in isolation while silently describing different production numbers.
        """
        if self.production is None or self.tax_base_derivation is None:
            return self
        production_by_category = {s.category: s.actual_output for s in self.production.sectors}
        for row in self.tax_base_derivation.sectors:
            expected = production_by_category.get(row.category)
            if expected is None:
                raise ValueError(
                    f"tax_base_derivation references sector category {row.category.value!r} "
                    "that does not appear in production.sectors"
                )
            if row.actual_output != expected:
                raise ValueError(
                    f"tax_base_derivation.sectors actual_output for category "
                    f"{row.category.value!r} ({row.actual_output}) does not match "
                    f"production.sectors actual_output for the same category ({expected})"
                )
        return self

    @model_validator(mode="after")
    def _tax_base_derivation_output_matches_finance_applied_bases(self) -> TurnReport:
        """R1: `TaxBaseDerivationReport.derived_tax_bases` must exactly equal
        `FinanceReport.tax_bases` — the bases derivation computed must be the exact bases finance
        actually applied, not merely similar internally-valid numbers.
        """
        if self.tax_base_derivation is None or self.finance is None:
            return self
        if self.tax_base_derivation.derived_tax_bases != self.finance.tax_bases:
            raise ValueError(
                "tax_base_derivation.derived_tax_bases does not exactly equal "
                "finance.tax_bases — the derived bases and the bases finance applied have "
                "diverged"
            )
        return self

    @model_validator(mode="after")
    def _resources_extraction_output_matches_production_extraction_row(self) -> TurnReport:
        """Phase 2C2: `ResourceExtractionReport.extraction_sector_real_output` must equal
        `ProductionReport.sectors[EXTRACTION].actual_output` exactly — the extraction row's
        output IS the physical bridge total, not merely a similar internally-valid number. This
        is the AUTHORITATIVE check for that row's `actual_output` — `SectorProductionReport`
        cannot self-validate it in isolation (see `_actual_output_matches_formula`'s
        `RESOURCE_EXTRACTION` branch above)."""
        if self.resources is None or self.production is None:
            return self
        extraction_row = next(
            (s for s in self.production.sectors if s.category == SectorCategory.EXTRACTION), None
        )
        if extraction_row is None:
            raise ValueError("production.sectors is missing the EXTRACTION category")
        if extraction_row.actual_output != self.resources.extraction_sector_real_output:
            raise ValueError(
                "production.sectors[EXTRACTION].actual_output="
                f"{extraction_row.actual_output} does not match "
                "resources.extraction_sector_real_output="
                f"{self.resources.extraction_sector_real_output}"
            )
        return self

    @model_validator(mode="after")
    def _resources_extraction_utilization_matches_potential_output_formula(self) -> TurnReport:
        """Phase 2C2 (R6): `ProductionReport.sectors[EXTRACTION].capacity_utilization_bps` must
        equal `floor(extraction_sector_real_output * 10_000 / extraction_sector_potential_output)`,
        or `0` when the denominator is `0` — the AUTHORITATIVE check (the row's own validator
        cannot self-derive this; see `_capacity_utilization_bps_matches_formula` above)."""
        if self.resources is None or self.production is None:
            return self
        extraction_row = next(
            (s for s in self.production.sectors if s.category == SectorCategory.EXTRACTION), None
        )
        if extraction_row is None:
            raise ValueError("production.sectors is missing the EXTRACTION category")
        potential = self.resources.extraction_sector_potential_output
        actual = self.resources.extraction_sector_real_output
        expected = (actual * BPS_DENOMINATOR) // potential if potential > 0 else 0
        if extraction_row.capacity_utilization_bps != expected:
            raise ValueError(
                "production.sectors[EXTRACTION].capacity_utilization_bps="
                f"{extraction_row.capacity_utilization_bps} does not match "
                "floor(extraction_sector_real_output * 10_000 / "
                f"extraction_sector_potential_output), or 0 when potential is 0 ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _resources_extraction_constraint_matches_classification(self) -> TurnReport:
        """Phase 2C2 (R9): `ProductionReport.sectors[EXTRACTION].constraint` must equal
        `classify_extraction_constraint(potential, actual)` — the AUTHORITATIVE check. Calls the
        SAME shared classifier `phases.py` uses to construct the row (see
        `classify_extraction_constraint`'s own docstring for why this one classification is
        deliberately shared code, not independently re-derived)."""
        if self.resources is None or self.production is None:
            return self
        extraction_row = next(
            (s for s in self.production.sectors if s.category == SectorCategory.EXTRACTION), None
        )
        if extraction_row is None:
            raise ValueError("production.sectors is missing the EXTRACTION category")
        expected = classify_extraction_constraint(
            potential_output=self.resources.extraction_sector_potential_output,
            actual_output=self.resources.extraction_sector_real_output,
        )
        if extraction_row.constraint != expected:
            raise ValueError(
                f"production.sectors[EXTRACTION].constraint={extraction_row.constraint!r} does "
                f"not match classify_extraction_constraint(potential, actual) (expected "
                f"{expected!r})"
            )
        return self
