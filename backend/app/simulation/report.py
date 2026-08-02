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

from app.core.money import BPS_DENOMINATOR, StrictBps, StrictMoney, StrictSignedMoney
from app.core.quantity import (
    StrictRealOutput,
    StrictRealOutputPerWorker,
    StrictWorkerCount,
    base_year_real_output_to_money,
)
from app.simulation.accounting import compute_quarterly_interest, compute_tax_revenue
from app.simulation.production_accounting import SectorConstraint
from app.simulation.state import (
    SectorCategory,
    SpendingPlanState,
    TaxBaseCoefficients,
    TaxBaseState,
    TaxPolicyState,
)

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


class SectorProductionReport(BaseModel):
    """One sector's self-validated Phase 2B1 production outcome.

    Every derived field (`labor_limited_output`, `actual_output`,
    `capacity_utilization_bps`, `constraint`) is independently re-checked
    against the sector's own stored inputs on construction — see the
    validators below — mirroring `FinanceReport`'s self-validation pattern.
    There is no trusted boolean; a report that disagrees with its own
    formulas never finishes construction.

    Units: `capacity_output`/`output_per_worker`/`labor_limited_output`/
    `actual_output` are fixed-base-year output minor units (`StrictRealOutput`/
    `StrictRealOutputPerWorker`) — real production measures, never spendable
    money. `employed_workers` is a worker count (`StrictWorkerCount`), a
    distinct unit from output. See `app.core.quantity` and
    `docs/economy_methodology.md`.
    """

    model_config = _STRICT_CONFIG

    category: SectorCategory
    capacity_output: StrictRealOutput
    output_per_worker: StrictRealOutputPerWorker
    employed_workers: StrictWorkerCount
    labor_limited_output: StrictRealOutput
    actual_output: StrictRealOutput
    capacity_utilization_bps: StrictBps
    constraint: SectorConstraint

    @model_validator(mode="after")
    def _labor_limited_output_matches_formula(self) -> SectorProductionReport:
        expected = self.employed_workers * self.output_per_worker
        if self.labor_limited_output != expected:
            raise ValueError(
                f"labor_limited_output={self.labor_limited_output} does not equal "
                f"employed_workers * output_per_worker ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _actual_output_matches_formula(self) -> SectorProductionReport:
        expected = min(self.capacity_output, self.labor_limited_output)
        if self.actual_output != expected:
            raise ValueError(
                f"actual_output={self.actual_output} does not equal "
                f"min(capacity_output, labor_limited_output) ({expected})"
            )
        return self

    @model_validator(mode="after")
    def _capacity_utilization_bps_matches_formula(self) -> SectorProductionReport:
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
        return self

    @model_validator(mode="after")
    def _constraint_matches_classification_rule(self) -> SectorProductionReport:
        if self.capacity_output == 0:
            expected = SectorConstraint.INACTIVE
        elif self.labor_limited_output < self.capacity_output:
            expected = SectorConstraint.LABOR_CONSTRAINED
        elif self.labor_limited_output > self.capacity_output:
            expected = SectorConstraint.CAPACITY_CONSTRAINED
        else:
            expected = SectorConstraint.EXACTLY_BALANCED
        if self.constraint != expected:
            raise ValueError(
                f"constraint={self.constraint!r} does not match the classification rule "
                f"applied to capacity_output/labor_limited_output (expected {expected!r})"
            )
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

    @model_validator(mode="after")
    def _production_finance_and_derivation_are_all_present_or_all_absent(self) -> TurnReport:
        """R1: a partial combination of the three player-economy reports would represent a
        broken audit chain (e.g. production ran but derivation silently didn't) — reject it
        outright rather than accepting whatever subset happens to be present.
        """
        present = (
            self.production is not None,
            self.tax_base_derivation is not None,
            self.finance is not None,
        )
        if any(present) and not all(present):
            raise ValueError(
                "production, tax_base_derivation, and finance must be all present or all "
                f"absent on a TurnReport — got present={present} "
                "(production, tax_base_derivation, finance)"
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
