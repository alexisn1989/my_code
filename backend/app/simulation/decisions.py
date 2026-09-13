"""Player (and, later, AI) decisions submitted for a turn.

`BudgetDecision` is the first concrete decision kind (product spec §15) —
Phase 1 had only a generic, unused `Decision(kind: str, payload: dict)`
placeholder. From Phase 2A through 3B1 it was the *only* kind, so
`DecisionSet.decisions` was a homogeneous `tuple[BudgetDecision, ...]` rather
than a discriminated union: a `Union` of one member is not a union.

**Phase 3B2A added that second kind.** `BlocRelationshipInvestmentDecision` gives
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
from app.simulation.constitution import (
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    StrictTermCount,
    StrictTurnInterval,
)
from app.simulation.geography import StrictMapId
from app.simulation.legislature import ProposalRoute
from app.simulation.state import (
    CabinetPost,
    SpendingCategory,
    StrictCharacterId,
    StrictFormationId,
)

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


class DecreeAuthorityTarget(BaseModel):
    """Replace the constitution's decree-authority axis."""

    model_config = _STRICT_CONFIG

    axis: Literal["decree_authority"] = "decree_authority"
    value: DecreeAuthority


class ExecutiveSystemTarget(BaseModel):
    """Replace the constitution's executive-system axis."""

    model_config = _STRICT_CONFIG

    axis: Literal["executive_system"] = "executive_system"
    value: ExecutiveSystem


class ExecutiveSelectionTarget(BaseModel):
    """Replace the constitution's executive-selection axis."""

    model_config = _STRICT_CONFIG

    axis: Literal["executive_selection"] = "executive_selection"
    value: ExecutiveSelection


class ElectionIntervalTarget(BaseModel):
    """Replace or abolish the scheduled national-election interval."""

    model_config = _STRICT_CONFIG

    axis: Literal["national_election_interval_turns"] = "national_election_interval_turns"
    value: StrictTurnInterval | None


class TermLimitTarget(BaseModel):
    """Replace or abolish the executive term limit."""

    model_config = _STRICT_CONFIG

    axis: Literal["executive_term_limit_terms"] = "executive_term_limit_terms"
    value: StrictTermCount | None


ConstitutionalAxisTarget: TypeAlias = Annotated[
    DecreeAuthorityTarget
    | ExecutiveSystemTarget
    | ExecutiveSelectionTarget
    | ElectionIntervalTarget
    | TermLimitTarget,
    Field(discriminator="axis"),
]


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


class ConstitutionalAmendmentDecision(BaseModel):
    """Propose one atomic amendment across one or more constitutional axes (Phase 3C).

    This model validates only state-independent shape. Whether the selected route is legal,
    whether every target changes the opening constitution, whether the final combination remains
    coherent under C1-C10, and whether the political-capital commitment is affordable are all
    resolution-time checks in slot 1.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["constitutional_amendment"] = "constitutional_amendment"
    targets: tuple[ConstitutionalAxisTarget, ...] = Field(min_length=1)
    route: ProposalRoute = ProposalRoute.LEGISLATIVE
    influence: tuple[InfluenceAllocation, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _targets_are_in_canonical_axis_order(self) -> ConstitutionalAmendmentDecision:
        axes = [target.axis for target in self.targets]
        if axes != sorted(axes):
            raise ValueError(f"targets must be sorted ascending by axis name, got {axes!r}")
        return self

    @model_validator(mode="after")
    def _no_duplicate_axes(self) -> ConstitutionalAmendmentDecision:
        axes = [target.axis for target in self.targets]
        if len(axes) != len(set(axes)):
            duplicates = sorted({axis for axis in axes if axes.count(axis) > 1})
            raise ValueError(f"targets cannot name the same axis twice: {duplicates}")
        return self

    @model_validator(mode="after")
    def _influence_is_in_canonical_identity_order(
        self,
    ) -> ConstitutionalAmendmentDecision:
        targets = [(allocation.party_id, allocation.bloc_id) for allocation in self.influence]
        if targets != sorted(targets):
            raise ValueError(
                f"influence must be sorted ascending by (party_id, bloc_id), got {targets!r}"
            )
        return self

    @model_validator(mode="after")
    def _reject_duplicate_influence_targets(self) -> ConstitutionalAmendmentDecision:
        targets = [(allocation.party_id, allocation.bloc_id) for allocation in self.influence]
        if len(targets) != len(set(targets)):
            duplicates = sorted({target for target in targets if targets.count(target) > 1})
            raise ValueError(
                f"influence cannot target the same (party_id, bloc_id) twice: {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def _decree_route_takes_no_influence(self) -> ConstitutionalAmendmentDecision:
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


# --- Military movement (Military Movement vertical slice, commit 5) ---------
#
# STABLE, ASSERTABLE shape codes, following `geography.MAP_CONSTRUCTION_CODES` exactly: every
# custom construction `ValueError` below begins with its code followed by ": ", so a test asserts
# the code that actually reaches the caller rather than a docstring or a validator's own name.
# Pydantic wraps the message but preserves it verbatim, so `code in str(exc)` is a true statement
# about emitted behaviour -- and the same property is what lets `/preview` and `/resolve` surface
# the code at their public boundaries without a new response field.

MOVEMENT_ORDERS_EMPTY = "military_movement_orders_empty"
MOVEMENT_DUPLICATE_FORMATION = "military_movement_duplicate_formation"
MOVEMENT_ORDERS_NOT_CANONICAL = "military_movement_orders_not_canonical"
MOVEMENT_TOO_MANY_ORDERS = "military_movement_too_many_orders"

MOVEMENT_SHAPE_CODES: frozenset[str] = frozenset(
    {
        MOVEMENT_ORDERS_EMPTY,
        MOVEMENT_DUPLICATE_FORMATION,
        MOVEMENT_ORDERS_NOT_CANONICAL,
        MOVEMENT_TOO_MANY_ORDERS,
    }
)
"""Every shape-only code `MilitaryMovementDecision` can emit. Each is proven independently
reachable by a real constructor call in `tests/test_military_movement.py`, so a code that stops
firing fails the suite instead of lingering as dead documentation."""

MOVEMENT_ORDERS_PER_DECISION = 1
"""Ruleset 0.15.0 accepts one order per turn. The cap lives in a VALIDATOR, never in the shape:
raising it in a later ruleset changes this constant and one test matrix, and does not migrate a
decision shape, re-issue a discriminator or invalidate any saved `decisions_json`. Callers already
iterate `orders`, so none of them changes either."""


class FormationMovementOrder(BaseModel):
    """One formation's destination for this turn.

    Reuses `StrictFormationId` (`state.py`) and `StrictMapId` (`geography.py`) rather than minting
    a second, structurally identical theater alias -- `StrictMapId` is the authoritative alias for
    every theater id in `state.py`, and a parallel one would be two names for one concept.

    State-independent by construction: whether the formation exists, whether the theater exists,
    and whether the move is legal are all resolution-time questions answered once, by
    `military.movement_order_problems`.
    """

    model_config = _STRICT_CONFIG

    formation_id: StrictFormationId
    destination_theater_id: StrictMapId


class MilitaryMovementDecision(BaseModel):
    """The player's military instruction for the turn (Military Movement, commit 5).

    Discriminated `"military_movement"` rather than `"formation_movement"` on extension grounds:
    later slices add naval transit and air sorties, which are also formation movements but are not
    interchangeable with land redeployment. This kind can grow order variants inside itself;
    `formation_movement` would force sibling kinds and split one player intention across three
    union members and three one-per-kind validators.

    Four shape-only codes, in a deliberate precedence -- empty, duplicate, noncanonical, cap --
    because Pydantic runs `mode="after"` validators in definition order and an overlapping payload
    must report the same code every time:

    - duplicate precedes noncanonical because `[a, a]` IS sorted, so reporting it as an ordering
      problem would be wrong;
    - the cap is last so a two-order payload that is *also* malformed reports the malformation
      rather than the ruleset limit, which is the more actionable of the two.

    Canonical order is REJECTED, never normalized -- the same rule as
    `_decisions_are_in_canonical_kind_order` below, and for its reason: this tuple is serialized
    into `decisions_json` and hash-covered, so two semantically identical sets listed in different
    orders would digest differently.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["military_movement"] = "military_movement"
    orders: tuple[FormationMovementOrder, ...]

    @model_validator(mode="after")
    def _orders_are_not_empty(self) -> MilitaryMovementDecision:
        """An empty decision is rejected rather than accepted as a quiet turn.

        A quiet turn submits NO `MilitaryMovementDecision` at all; an empty one is a client bug,
        and accepting it would make two different payloads mean the same thing. Deliberately a
        validator rather than `Field(min_length=1)`: the field constraint emits Pydantic's generic
        `too_short` message, which carries no stable code for `/preview` and `/resolve` to surface.
        """
        if not self.orders:
            raise ValueError(
                f"{MOVEMENT_ORDERS_EMPTY}: a military movement decision must carry at least one "
                "order; submit no decision at all for a turn with no movement"
            )
        return self

    @model_validator(mode="after")
    def _no_duplicate_formation_ids(self) -> MilitaryMovementDecision:
        """Two orders for one formation ARE the contradiction, with one destination per formation.

        Runs BEFORE the ordering check, unlike `BlocRelationshipInvestmentDecision`'s pair, because
        a duplicated id is already in sorted order and would otherwise be misreported as an
        ordering problem.
        """
        ids = [order.formation_id for order in self.orders]
        if len(set(ids)) != len(ids):
            duplicates = sorted(
                {formation_id for formation_id in ids if ids.count(formation_id) > 1}
            )
            raise ValueError(
                f"{MOVEMENT_DUPLICATE_FORMATION}: a formation may be ordered to exactly one "
                f"destination per turn, got repeated {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def _orders_are_in_canonical_formation_order(self) -> MilitaryMovementDecision:
        ids = [order.formation_id for order in self.orders]
        if ids != sorted(ids):
            raise ValueError(
                f"{MOVEMENT_ORDERS_NOT_CANONICAL}: orders must be sorted ascending by "
                f"formation_id, got {ids!r}"
            )
        return self

    @model_validator(mode="after")
    def _at_most_one_order_in_this_ruleset(self) -> MilitaryMovementDecision:
        if len(self.orders) > MOVEMENT_ORDERS_PER_DECISION:
            raise ValueError(
                f"{MOVEMENT_TOO_MANY_ORDERS}: ruleset 0.15.0 accepts at most "
                f"{MOVEMENT_ORDERS_PER_DECISION} movement order per turn, got {len(self.orders)}"
            )
        return self


CABINET_ORDERS_EMPTY = "cabinet_orders_empty"
CABINET_DUPLICATE_POST = "cabinet_duplicate_post"
CABINET_ORDERS_NOT_CANONICAL = "cabinet_orders_not_canonical"

CABINET_SHAPE_CODES: frozenset[str] = frozenset(
    {CABINET_ORDERS_EMPTY, CABINET_DUPLICATE_POST, CABINET_ORDERS_NOT_CANONICAL}
)
"""Every stable code `CabinetDecision`'s own validators can raise, mirroring
`MOVEMENT_SHAPE_CODES`. SHAPE problems only -- whether the payload is a well-formed decision at
all. Whether the people named in it exist, are appointable and are affordable is a resolution-time
question that `phases.py` slot 1 and `app.api.decision_preflight` answer against `GameState`,
exactly as this module's other decisions already split those concerns."""


class CabinetOrder(BaseModel):
    """One post's staffing order: who takes it, or that it is being vacated.

    `character_id is None` IS the dismissal. A separate `dismiss: bool` flag would allow the
    contradictory `(character_id="x", dismiss=True)`, and a separate decision kind would make
    "replace" -- which is a dismissal and an appointment in one breath -- impossible to express as
    a single atomic order. One optional field makes every verb representable and every
    contradiction unconstructible.

    The VERB is never authored. Appoint, replace and dismiss are read off the OPENING cabinet at
    resolution: an order on a vacant post appoints, on an occupied post replaces, and a `None`
    dismisses. A client that mislabelled its own intent could not make the engine agree with it.
    """

    model_config = _STRICT_CONFIG

    post: CabinetPost
    character_id: StrictCharacterId | None = None


class CabinetDecision(BaseModel):
    """Staff the cabinet this turn (characters slice).

    **One action carrying every post**, the shape `BlocRelationshipInvestmentDecision` and
    `MilitaryMovementDecision` already use, and for the same reason: ordering and duplicate
    questions are settled once inside this model rather than re-opened at `DecisionSet` level.

    It is also what makes a same-turn TRANSFER expressible. Moving somebody from one post to
    another is two orders that must be judged together -- the destination, and whatever happens to
    the origin -- and slot 1 validates the RESULTING cabinet rather than the orders pairwise, so
    the transfer is legal precisely when nobody ends up holding two posts. Split across two
    decisions, or two turns, that judgement could not be made.

    There is no cap on the number of orders: the bound is already `len(CabinetPost)`, which is
    content-derived and finite, so an arbitrary numeric limit would be a rule with no mechanism
    behind it. `MovementDecision`'s per-ruleset cap exists because its bound is the formation
    roster, which is not.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["cabinet"] = "cabinet"
    orders: tuple[CabinetOrder, ...]

    @model_validator(mode="after")
    def _orders_are_not_empty(self) -> CabinetDecision:
        """A quiet turn submits NO `CabinetDecision`; an empty one is a client bug. A validator
        rather than `Field(min_length=1)` so the failure carries a stable code, matching
        `MilitaryMovementDecision._orders_are_not_empty`."""
        if not self.orders:
            raise ValueError(
                f"{CABINET_ORDERS_EMPTY}: a cabinet decision must carry at least one order; "
                "submit no decision at all for a turn with no cabinet change"
            )
        return self

    @model_validator(mode="after")
    def _no_duplicate_posts(self) -> CabinetDecision:
        """Two orders for one post ARE the contradiction. Runs BEFORE the ordering check because a
        duplicated post is already in sorted order and would otherwise be misreported as an
        ordering problem -- the same trap `MilitaryMovementDecision` documents."""
        posts = [order.post for order in self.orders]
        if len(set(posts)) != len(posts):
            duplicates = sorted({p.value for p in posts if posts.count(p) > 1})
            raise ValueError(
                f"{CABINET_DUPLICATE_POST}: a post may be ordered at most once per turn, got "
                f"repeated {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def _orders_are_in_canonical_post_order(self) -> CabinetDecision:
        """Canonical by `post.value`, REJECTED rather than sorted: this tuple is serialized into
        `decisions_json` and hash-covered, so two semantically identical sets listed in different
        orders would digest differently."""
        values = [order.post.value for order in self.orders]
        if values != sorted(values):
            raise ValueError(
                f"{CABINET_ORDERS_NOT_CANONICAL}: orders must be sorted ascending by post, got "
                f"{values!r}"
            )
        return self


LegislativeProposalKind: TypeAlias = Literal["budget", "constitutional_amendment"]
"""Which of the two policy proposals a legislative bargain is about.

Declared once and shared by `LegislativeBargainDecision.proposal_kind` and
`report.LegislativeBargainReport.proposal_kind`. Typing the report field as a bare `str` would let a
stored row name a proposal kind no decision could ever have carried, so the two are the same type by
construction rather than by agreement between two authors.

The values are exactly the `kind` tags of `BudgetDecision` and `ConstitutionalAmendmentDecision`,
which is what lets `_bargain_names_a_present_proposal`'s check be a comparison rather than a mapping.
"""


class LegislativeBargainDecision(BaseModel):
    """Buy one party leader's endorsement for the one proposal this turn carries.

    **Three fields, and none of them is money.** The price is a fact about the counterparty in the
    opening state, derived by `simulation.legislative_bargaining` and by nothing else, so there is
    nothing for a client to state and nothing it could get wrong. Two earlier designs carried an
    `offered_capital`; both were removed because the price is projected on
    `DecisionOptionsProjection.legislative_bargain_counterparties`, which left the offer a free
    variable with exactly one rational value -- first "offer the cap, pay the price", then "offer the
    price". A field whose only correct value is displayed elsewhere is a transcription task, not a
    decision.

    `proposal_kind` is an ASSERTION OF INTENT, never a selector. `_at_most_one_policy_proposal`
    already guarantees a `DecisionSet` carries at most one budget-or-amendment, so "the proposal in
    this set" is a unique referent and there is never a choice to disambiguate. What the field buys
    is the ability to catch a client that bargained for a budget while the set carries an amendment
    -- a real composition bug that would otherwise silently purchase an endorsement for the wrong
    vote.

    Deliberately NOT a digest of the target. The bargain and its proposal arrive atomically in one
    `DecisionSet` already guarded by `expected_turn`/`expected_state_version`, so a digest would add
    no integrity that is missing -- and it would force the frontend to reproduce this package's
    canonical-JSON encoding byte for byte, which is precisely the duplicated canonicalization
    `buildDecisionSet.ts` exists to prevent.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["legislative_bargain"] = "legislative_bargain"
    character_id: StrictCharacterId
    proposal_kind: LegislativeProposalKind


class ForeignAssistanceDecision(BaseModel):
    """Ask one foreign counterpart for a bounded assistance grant (characters slice).

    **Two fields, and neither is an amount.** What a counterpart gives is a fact about them -- their
    remaining pool, their leader's trust in the player, the bilateral standing, and how good the
    player's foreign minister is -- derived by `simulation.foreign_assistance` and by nothing else.
    A requested figure would be a number the player could only get wrong, and the engine would
    ignore it. This is the same conclusion the legislative bargain reached after two attempts at an
    offer field, applied from the start rather than discovered again.

    `profile_id` names the counterpart, not their leader. The leader's traits are read from
    `world.characters` by affiliation, so a scenario cannot end up with a request that names a
    person and a pool belonging to different actors.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["foreign_assistance"] = "foreign_assistance"
    profile_id: _StrictNonemptyId


Decision: TypeAlias = Annotated[
    BudgetDecision
    | BlocRelationshipInvestmentDecision
    | ConstitutionalAmendmentDecision
    | MilitaryMovementDecision
    | CabinetDecision
    | LegislativeBargainDecision
    | ForeignAssistanceDecision,
    Field(discriminator="kind"),
]
"""The tagged decision union this module's header anticipated (Phase 3B2A).

Discriminated by the explicit `kind` tag, never by shape. The members do not structurally
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

    def constitutional_amendment_decision(self) -> ConstitutionalAmendmentDecision | None:
        """The submitted constitutional-amendment decision, or `None`."""
        return next(
            (d for d in self.decisions if isinstance(d, ConstitutionalAmendmentDecision)),
            None,
        )

    def military_movement_decision(self) -> MilitaryMovementDecision | None:
        """The submitted movement decision, or `None`. Unique by
        `_at_most_one_military_movement_decision`.

        Identity-based like every accessor above, never `decisions[0]`: `"military_movement"` sorts
        LAST of the four kinds, so on a turn carrying a budget and a movement the movement is at
        index 1, and on a turn carrying only a movement it is at index 0. A positional read would
        be right by accident in one case and wrong in the other.
        """
        return next((d for d in self.decisions if isinstance(d, MilitaryMovementDecision)), None)

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
    def _at_most_one_constitutional_amendment_decision(self) -> DecisionSet:
        amendments = sum(
            1 for d in self.decisions if isinstance(d, ConstitutionalAmendmentDecision)
        )
        if amendments > 1:
            raise ValueError(
                "at most one constitutional-amendment decision may appear in a DecisionSet, "
                f"got {amendments}"
            )
        return self

    @model_validator(mode="after")
    def _at_most_one_military_movement_decision(self) -> DecisionSet:
        """One decision carries every order (see `MilitaryMovementDecision`), so a second one could
        only duplicate or contradict the first -- and the per-decision duplicate-formation rule
        could not see across two decisions to detect it."""
        movements = sum(1 for d in self.decisions if isinstance(d, MilitaryMovementDecision))
        if movements > 1:
            raise ValueError(
                f"at most one military-movement decision may appear in a DecisionSet, "
                f"got {movements}"
            )
        return self

    def cabinet_decision(self) -> CabinetDecision | None:
        """The submitted cabinet decision, or `None`. Unique by `_at_most_one_cabinet_decision`.

        Identity-based like every accessor above, never `decisions[0]`: `"cabinet"` sorts THIRD of
        the five kinds, after `"budget"` and before `"constitutional_amendment"`, so its index
        depends entirely on what else the turn carries -- index 0 on a cabinet-only turn, index 2
        behind an investment and a budget.
        """
        return next((d for d in self.decisions if isinstance(d, CabinetDecision)), None)

    @model_validator(mode="after")
    def _at_most_one_cabinet_decision(self) -> DecisionSet:
        """One decision carries every post (see `CabinetDecision`), so a second could only
        duplicate or contradict the first -- and the per-decision duplicate-post rule could not see
        across two decisions to detect it."""
        cabinets = sum(1 for d in self.decisions if isinstance(d, CabinetDecision))
        if cabinets > 1:
            raise ValueError(
                f"at most one cabinet decision may appear in a DecisionSet, got {cabinets}"
            )
        return self

    def legislative_bargain_decision(self) -> LegislativeBargainDecision | None:
        """The submitted legislative bargain, or `None`. Unique by
        `_at_most_one_legislative_bargain_decision`.

        Identity-based like every accessor above, never `decisions[0]`: `"legislative_bargain"`
        sorts FIFTH of the six kinds, between `"constitutional_amendment"` and
        `"military_movement"`, so its index depends entirely on what else the turn carries.
        """
        return next((d for d in self.decisions if isinstance(d, LegislativeBargainDecision)), None)

    @model_validator(mode="after")
    def _at_most_one_legislative_bargain_decision(self) -> DecisionSet:
        """One bargain per turn, so at most one party is endorsed.

        This is not merely the "one decision carries every target" pattern the accessors above
        follow -- there is no tuple of orders here to carry. It is a substantive rule: two accepted
        bargains would put two endorsements onto one vote, and there is no defensible answer yet for
        how they compose. Refusing the second at construction is better than inventing one.

        A future ruleset that does allow several would carry them as an `orders`-style tuple inside
        ONE decision, canonical ascending by `character_id` -- stated here so the ordering question
        is answered before it is asked, exactly as `CabinetDecision` answered it for posts.
        """
        bargains = sum(1 for d in self.decisions if isinstance(d, LegislativeBargainDecision))
        if bargains > 1:
            raise ValueError(
                "at most one legislative-bargain decision may appear in a DecisionSet, "
                f"got {bargains}"
            )
        return self

    def foreign_assistance_decision(self) -> ForeignAssistanceDecision | None:
        """The submitted assistance request, or `None`. Unique by
        `_at_most_one_foreign_assistance_decision`.

        Identity-based like every accessor above, never `decisions[0]`: `"foreign_assistance"`
        sorts FIFTH of the seven kinds, between `"constitutional_amendment"` and
        `"legislative_bargain"`.
        """
        return next((d for d in self.decisions if isinstance(d, ForeignAssistanceDecision)), None)

    @model_validator(mode="after")
    def _at_most_one_foreign_assistance_decision(self) -> DecisionSet:
        """One request per turn, so at most one pool is drawn against.

        Substantive rather than the usual "one decision carries every target": two requests would
        need a rule for how two draws against two independent pools compose with a single
        `external_assistance` term and a single foreign minister's attention. Refusing the second
        at construction is better than inventing one.
        """
        requests = sum(1 for d in self.decisions if isinstance(d, ForeignAssistanceDecision))
        if requests > 1:
            raise ValueError(
                "at most one foreign-assistance decision may appear in a DecisionSet, "
                f"got {requests}"
            )
        return self

    @model_validator(mode="after")
    def _at_most_one_policy_proposal(self) -> DecisionSet:
        proposals = sum(
            1
            for decision in self.decisions
            if isinstance(decision, (BudgetDecision, ConstitutionalAmendmentDecision))
        )
        if proposals > 1:
            raise ValueError(
                "at most one policy proposal (budget or constitutional amendment) may appear "
                f"in a DecisionSet, got {proposals}"
            )
        return self

    @model_validator(mode="after")
    def _decisions_are_in_canonical_kind_order(self) -> DecisionSet:
        """With multiple kinds, tuple order becomes free information — and this tuple is serialised into
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


def cabinet_decision_digest(decision: CabinetDecision) -> str:
    """A deterministic content fingerprint of a submitted cabinet decision.

    The exact shape of the three digest functions beside it, for the exact same reason: every field
    covered by construction via `model_dump(mode="json")`, with no manual field selection to drift
    as the model grows. `orders` is already in construction-time-enforced canonical post order, so
    two semantically identical decisions cannot digest differently.

    `GovernanceReport` and the `CABINET_APPOINTMENT` expenditure row store the RESULT of this
    function, never the decision itself; `simulation.reconciliation` group 57 is the only place
    that recomputes it and compares.
    """
    return canonical_digest(decision.model_dump(mode="json"))


def legislative_bargain_decision_digest(decision: LegislativeBargainDecision) -> str:
    """A deterministic content fingerprint of a submitted legislative bargain.

    The exact shape of the digest functions beside it, and it exists for the same reason they do:
    `CapitalExpenditureReport.decision_digest` is required on every ledger row, so the
    `LEGISLATIVE_BARGAIN` row needs one that ties the spend to one exact decision.

    Note what this is NOT. It is not a binding of the bargain to its target proposal -- that job
    belongs to `proposal_kind`, deliberately, because a target digest would force the frontend to
    reproduce this package's canonical-JSON encoding byte for byte. This digest covers the bargain's
    own three fields and nothing else, which is precisely what a provenance field on an expenditure
    row should be.
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


def constitutional_amendment_decision_digest(decision: ConstitutionalAmendmentDecision) -> str:
    """A deterministic fingerprint over every field of a constitutional amendment decision."""
    return canonical_digest(decision.model_dump(mode="json"))
