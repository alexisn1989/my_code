"""Player (and, later, AI) decisions submitted for a turn.

`BudgetDecision` is the first concrete decision kind (product spec §15) —
Phase 1 had only a generic, unused `Decision(kind: str, payload: dict)`
placeholder. From Phase 2A through 3B1 it was the *only* kind, so
`DecisionSet.decisions` was a homogeneous `tuple[BudgetDecision, ...]` rather
than a discriminated union: a `Union` of one member is not a union.

**Phase 3B2A is that second kind.** `BlocRelationshipInvestmentDecision` gives
political capital a sink that competes with legislative influence and decrees,
and `Decision` is now the tagged union this docstring anticipated. `"budget"`
keeps its serialised tag value, so no already-written payload changes shape.

⚠ **The union made tuple position stop meaning identity.** Canonical kind order
sorts `"bloc_relationship_investment"` *before* `"budget"`, so on a turn
carrying both, `decisions[0]` is the investment. Four call sites in `phases.py`
and `reconciliation.py` read index 0 while the tuple was homogeneous; all four
now use `DecisionSet.budget_decision()`. **Never reintroduce positional
access** — it type-checks, it works on every single-kind set, and it silently
resolves the wrong decision on exactly the mixed sets this phase exists to
allow.

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
from app.core.politics import StrictRelationshipInvestment
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


class BlocInvestment(BaseModel):
    """Political capital committed to *improving* one bloc's relationship (Phase 3B2A).

    Deliberately shaped like `InfluenceAllocation`, and deliberately not the same thing. Influence
    buys a bloc's vote on **this** proposal and is gone when the vote resolves; an investment buys
    a lasting improvement to the relationship, which changes what **every future** proposal costs.
    Same target vocabulary, opposite time horizon — merging them into one model would make that
    difference unrepresentable.

    `political_capital` is bounded `1..RELATIONSHIP_INVESTMENT_CAP` by its type, so the cap the
    formula applies is the cap the schema enforces. Committing 500 where 200 is the maximum is a
    *rejected* decision, not a truncated one: silently accepting it would destroy 300 capital the
    player never agreed to lose.

    Like `InfluenceAllocation`, this model is dumb about anything needing `GameState`. Whether the
    bloc exists, whether the total is affordable, and whether the investment would have any effect
    at all are resolution-time questions (slot 1).
    """

    model_config = _STRICT_CONFIG

    party_id: _StrictNonemptyId
    bloc_id: _StrictNonemptyId
    political_capital: StrictRelationshipInvestment


class BlocRelationshipInvestmentDecision(BaseModel):
    """Invest political capital in one or more bloc relationships this turn (Phase 3B2A).

    **One action carrying many targets**, rather than many single-target actions: ordering and
    duplicate questions are then solved once, inside this model, instead of being re-opened at the
    `DecisionSet` level where two kinds already interleave.

    There is no cap on the *number* of targets. The bound is already finite and content-derived —
    at most one investment per `(party_id, bloc_id)` that actually exists — and squeezed further by
    affordability, so an arbitrary numeric limit would be a rule with no mechanism behind it.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["bloc_relationship_investment"] = "bloc_relationship_investment"
    investments: tuple[BlocInvestment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _investments_are_in_canonical_identity_order(self) -> BlocRelationshipInvestmentDecision:
        """Mirrors `BudgetDecision._influence_is_in_canonical_identity_order` field-for-field, and
        runs *before* the duplicate check so a noncanonical set is reported as an ordering problem
        rather than as an incidental duplicate."""
        targets = [(investment.party_id, investment.bloc_id) for investment in self.investments]
        if targets != sorted(targets):
            raise ValueError(
                f"investments must be sorted ascending by (party_id, bloc_id), got {targets!r}"
            )
        return self

    @model_validator(mode="after")
    def _no_duplicate_investment_targets(self) -> BlocRelationshipInvestmentDecision:
        targets = [(investment.party_id, investment.bloc_id) for investment in self.investments]
        if len(targets) != len(set(targets)):
            duplicates = sorted({target for target in targets if targets.count(target) > 1})
            raise ValueError(
                f"investments cannot target the same (party_id, bloc_id) twice: {duplicates}"
            )
        return self


Decision: TypeAlias = Annotated[
    BudgetDecision | BlocRelationshipInvestmentDecision, Field(discriminator="kind")
]
"""The tagged decision union this module's header anticipated (Phase 3B2A).

Discriminated by the explicit `kind` tag, never by shape. The two members do not structurally
overlap — `BudgetDecision` has no `investments`, the investment decision has no rate or spending
fields, and both are `extra="forbid"` — but tag discrimination means that stays true even if a
future member does overlap, and it produces an actionable `union_tag_invalid` for an unknown kind
instead of a pile of per-member errors.

`"budget"` keeps the value it has had since Phase 2A, so every already-serialised decision payload
parses identically under the union. Old saves are still refused, but by the *version policy* at
the envelope, not by the schema — those are different things and only one of them is a migration.
"""


class DecisionSet(BaseModel):
    """All decisions a player submits for a single turn resolution attempt."""

    model_config = _STRICT_CONFIG

    expected_turn: int = Field(ge=0)
    expected_state_version: int = Field(ge=0)
    decisions: tuple[Decision, ...] = Field(default_factory=tuple)

    def budget_decision(self) -> BudgetDecision | None:
        """The submitted `BudgetDecision`, or `None`.

        **Every caller must use this rather than `decisions[0]`.** Before Phase 3B2A the tuple held
        at most one member, so position and identity coincided and four call sites reasonably read
        index 0. Under the union they do not: canonical kind order sorts
        `"bloc_relationship_investment"` *before* `"budget"`, so on any turn carrying both, index 0
        is the investment. A positional read would have had slot 1 voting on the wrong object and
        reconciliation comparing policy against the wrong decision — silently, since both are valid
        `Decision`s.

        `_at_most_one_budget_decision` guarantees the match is unique, so returning the first is
        returning the only.
        """
        return next((d for d in self.decisions if isinstance(d, BudgetDecision)), None)

    def relationship_investment_decision(self) -> BlocRelationshipInvestmentDecision | None:
        """The submitted relationship-investment decision, or `None`. Unique by
        `_at_most_one_relationship_investment_decision`."""
        return next(
            (d for d in self.decisions if isinstance(d, BlocRelationshipInvestmentDecision)),
            None,
        )

    @model_validator(mode="after")
    def _at_most_one_budget_decision(self) -> DecisionSet:
        """(Phase 3B2A) Counts budget-kind members, not tuple length.

        The Phase 3B1 version counted `len(self.decisions)`, which was correct while the tuple was
        homogeneous and becomes a *false rejection* the moment a player submits a budget and an
        investment in the same turn — the central new combination this phase exists to allow.
        """
        budgets = sum(1 for d in self.decisions if isinstance(d, BudgetDecision))
        if budgets > 1:
            raise ValueError(
                f"at most one budget decision may appear in a DecisionSet, got {budgets}"
            )
        return self

    @model_validator(mode="after")
    def _at_most_one_relationship_investment_decision(self) -> DecisionSet:
        """One action carries every target (see `BlocRelationshipInvestmentDecision`), so a second
        one could only duplicate or contradict the first."""
        investments = sum(
            1 for d in self.decisions if isinstance(d, BlocRelationshipInvestmentDecision)
        )
        if investments > 1:
            raise ValueError(
                "at most one bloc-relationship-investment decision may appear in a DecisionSet, "
                f"got {investments}"
            )
        return self

    @model_validator(mode="after")
    def _decisions_are_in_canonical_kind_order(self) -> DecisionSet:
        """With two kinds, tuple order becomes free information — and this tuple is serialised into
        `decisions_json` and hash-covered. Two semantically identical decision sets listed in
        different orders would otherwise digest differently and produce different `entry_hash`es,
        which is exactly the kind of difference the hash chain is supposed to be able to ignore.

        Rejected, never reordered: the same reject-not-normalize rule as every other ordered
        collection here.
        """
        kinds = [d.kind for d in self.decisions]
        if kinds != sorted(kinds):
            raise ValueError(f"decisions must be sorted ascending by kind, got {kinds!r}")
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


def bloc_relationship_investment_digest(decision: BlocRelationshipInvestmentDecision) -> str:
    """A deterministic content fingerprint of a submitted relationship-investment decision.

    The exact shape of `budget_decision_digest`, for the exact same reason: every field covered by
    construction via `model_dump(mode="json")`, with no manual field selection to drift as the
    model grows. `investments` is already in construction-time-enforced canonical order, so two
    logically identical decisions cannot digest differently.

    `PoliticalCapitalReport`'s expenditure rows store the *result*; only `simulation.reconciliation`
    recomputes it and compares (group 21). The report never computes its own provenance — that is
    the two-code-paths rule, and a report that vouched for itself would prove nothing.
    """
    return canonical_digest(decision.model_dump(mode="json"))
