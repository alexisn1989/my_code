"""Player (and, later, AI) decisions submitted for a turn.

`BudgetDecision` is the first concrete decision kind (product spec §15) —
Phase 1 had only a generic, unused `Decision(kind: str, payload: dict)`
placeholder. As of Phase 2A it is the *only* kind, so `DecisionSet.decisions`
is a homogeneous `tuple[BudgetDecision, ...]` rather than a discriminated
union: a `Union` of one member is not a union. When a second decision kind
is added (Phase 3+), that is the point to introduce
`Annotated[BudgetDecision | ..., Field(discriminator="kind")]` — not before.

`DecisionSet.expected_turn` and `expected_state_version` are the
stale-submission guard described in the product spec (§30): a decision set
built against an out-of-date view of the game must be rejected, not silently
applied against whatever the state has since become.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import StrictBps, StrictMoney
from app.simulation.state import SpendingCategory

_STRICT_CONFIG = ConfigDict(extra="forbid")


class SpendingUpdate(BaseModel):
    """A player's target amount for one spending category."""

    model_config = _STRICT_CONFIG

    category: SpendingCategory
    amount: StrictMoney


class BudgetDecision(BaseModel):
    """Set target tax rates and/or spending amounts for the upcoming turn.

    Targets, not deltas: an omitted rate (`None`) leaves that rate at its
    current value; a rate that *is* included replaces it outright — even if
    the new value equals the old one, which is still an explicit, reportable
    player choice (`FinanceReport` labels it "unchanged" rather than treating
    it as if nothing was submitted; see `report.py`).

    Must set at least one target: an empty decision that changes nothing is
    rejected at construction rather than silently accepted as a no-op that
    happens to do nothing (a *missing* `BudgetDecision` in a `DecisionSet` is
    how "keep the current budget" is actually expressed).
    """

    model_config = _STRICT_CONFIG

    kind: Literal["budget"] = "budget"
    personal_income_rate_bps: StrictBps | None = None
    corporate_rate_bps: StrictBps | None = None
    consumption_rate_bps: StrictBps | None = None
    spending_updates: tuple[SpendingUpdate, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _require_at_least_one_target(self) -> BudgetDecision:
        no_rate_targets = (
            self.personal_income_rate_bps is None
            and self.corporate_rate_bps is None
            and self.consumption_rate_bps is None
        )
        if no_rate_targets and not self.spending_updates:
            raise ValueError(
                "a budget decision must set at least one tax-rate target or spending update; "
                "submit no BudgetDecision at all to keep the current budget unchanged"
            )
        return self

    @model_validator(mode="after")
    def _reject_duplicate_spending_categories(self) -> BudgetDecision:
        categories = [update.category for update in self.spending_updates]
        if len(categories) != len(set(categories)):
            duplicates = sorted({c for c in categories if categories.count(c) > 1})
            raise ValueError(
                f"a budget decision cannot target the same spending category twice: {duplicates}"
            )
        return self


class DecisionSet(BaseModel):
    """All decisions a player submits for a single turn resolution attempt."""

    model_config = _STRICT_CONFIG

    expected_turn: int = Field(ge=0)
    expected_state_version: int = Field(ge=0)
    decisions: tuple[BudgetDecision, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _at_most_one_budget_decision(self) -> DecisionSet:
        if len(self.decisions) > 1:
            raise ValueError(
                f"at most one budget decision may appear in a DecisionSet, got {len(self.decisions)}"
            )
        return self
