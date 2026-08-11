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

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.canonical_json import canonical_digest
from app.core.money import StrictBps, StrictMoney
from app.simulation.legislature import ProposalRoute
from app.simulation.state import SpendingCategory

_STRICT_CONFIG = ConfigDict(extra="forbid")

_StrictNonemptyId: TypeAlias = Annotated[str, Field(strict=True, min_length=1)]
"""A party or bloc identity, addressed the same way `simulation.state`'s own models do: a
nonempty string, never coerced from another type. Empty is rejected rather than treated as "no
target" — an allocation with nothing to name is not a smaller allocation, it is a malformed one."""


class SpendingUpdate(BaseModel):
    """A player's target amount for one spending category."""

    model_config = _STRICT_CONFIG

    category: SpendingCategory
    amount: StrictMoney


class InfluenceAllocation(BaseModel):
    """Political capital committed to one bloc, to move its vote (Phase 3B1).

    Targets a bloc by `(party_id, bloc_id)` — the same pair `simulation.state` already uses to
    address a bloc globally (`LegislativeBlocState`'s docstring). Deliberately dumb about anything
    that needs `GameState` to answer: whether that bloc exists, whether the route even calls for
    whipping votes, and whether the government can afford the sum of every allocation are all
    resolution-time questions (slot 1), not construction-time ones.
    """

    model_config = _STRICT_CONFIG

    party_id: _StrictNonemptyId
    bloc_id: _StrictNonemptyId
    political_capital: Annotated[int, Field(strict=True, gt=0)]


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

    (Phase 3B1) `route` and `influence` extend this same decision rather than introducing a
    discriminated decision union yet (D5): the budget IS the one proposal 3B1 routes through a
    legislative vote or a decree, so there is no second decision kind yet for a union to
    discriminate. `route` defaults to `LEGISLATIVE` — a government must explicitly ask to bypass
    its chamber, never fall into doing so by omission. `influence` carries no stored total: the
    amount committed is always the exact sum of its allocations, so there is no second field that
    could ever disagree with the first.

    None of the validators below can see `GameState`: whether a targeted bloc exists, whether the
    constitution actually permits the chosen route, and whether the government can afford the sum
    of every allocation are all resolution-time questions (slot 1) — an invalid decision aborts
    the whole turn atomically rather than partially applying (`simulation.legislature.
    LegislativeOutcome`'s docstring).
    """

    model_config = _STRICT_CONFIG

    kind: Literal["budget"] = "budget"
    personal_income_rate_bps: StrictBps | None = None
    corporate_rate_bps: StrictBps | None = None
    consumption_rate_bps: StrictBps | None = None
    spending_updates: tuple[SpendingUpdate, ...] = Field(default_factory=tuple)
    route: ProposalRoute = ProposalRoute.LEGISLATIVE
    influence: tuple[InfluenceAllocation, ...] = Field(default_factory=tuple)

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

    @model_validator(mode="after")
    def _reject_duplicate_influence_targets(self) -> BudgetDecision:
        targets = [(allocation.party_id, allocation.bloc_id) for allocation in self.influence]
        if len(targets) != len(set(targets)):
            duplicates = sorted({target for target in targets if targets.count(target) > 1})
            raise ValueError(
                f"influence cannot target the same (party_id, bloc_id) twice: {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def _influence_is_in_canonical_identity_order(self) -> BudgetDecision:
        """Influence is logically a set keyed by `(party_id, bloc_id)`, so it is required to
        appear in ascending order of that key and **rejected**, never silently reordered, if it
        does not — the same reject-not-normalize rule `EconomyState.resource_deposits` follows
        (R3), for the same reason: two decisions that commit identical capital to identical blocs
        must produce byte-identical canonical JSON regardless of which order the caller happened
        to list them in, and silently normalizing the order would hide a caller bug that built
        the tuple wrong instead of surfacing it.
        """
        targets = [(allocation.party_id, allocation.bloc_id) for allocation in self.influence]
        if targets != sorted(targets):
            raise ValueError(
                f"influence must be sorted ascending by (party_id, bloc_id), got {targets!r}"
            )
        return self

    @model_validator(mode="after")
    def _decree_route_takes_no_influence(self) -> BudgetDecision:
        if self.route is ProposalRoute.DECREE and self.influence:
            raise ValueError(
                "a decree route takes no influence allocations; a decree is not voted on, so "
                "there is nobody to whip"
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


def budget_decision_digest(decision: BudgetDecision) -> str:
    """A deterministic content fingerprint of a submitted `BudgetDecision` (Phase 3B1, R8).

    Mirrors `constitution.constitution_digest` exactly: the same `canonical_digest` mechanism,
    over the model's own `model_dump(mode="json")`, so every field is covered by construction —
    `kind`, every tax target, every spending target, `route`, and the influence allocations in
    their (already construction-time-enforced, reject-not-normalize) canonical `(party_id,
    bloc_id)` order — with no manual field selection or duplicated serialization logic to drift
    out of sync as the model grows.

    `LegislativeReport.budget_decision_digest` stores the *result* of this function, never the
    decision itself; `simulation.reconciliation` is the only place that recomputes it and compares
    — see that module's group 18 — so a report can be checked for provenance without ever growing
    a `GameState`- or `DecisionSet`-shaped field of its own.
    """
    return canonical_digest(decision.model_dump(mode="json"))
