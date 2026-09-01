"""Purpose-built projections: the only shapes this API ever returns.

Two rules govern this module.

**One.** Raw engine models never leave the process. `GameState`, `TurnReport`,
`HistoryEntry` and the save envelope are internal representation -- bps
encodings, digest strings, discriminator literals, scratch shapes -- and
exposing them would couple every screen to internal schema instead of a
versioned contract (ADR 0014, "Purpose-built projections, not raw engine
JSON"). Every response here is an explicit, independently typed model.

**Two.** `TurnResultProjection` is built in exactly ONE place:
`build_turn_result`. Live resolution and historical detail both call it, over
the same stored `TurnReport`, so the two views cannot drift apart. There is no
second path, and `test_api_projections.py` asserts the two are identical.

Nothing here recomputes a simulation result. Every number is read from state or
from a stored, already-validated report; the only arithmetic is presentation
(bps to a percentage string, minor units to a money string).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import BPS_DENOMINATOR, format_money
from app.core.politics import RELATIONSHIP_INVESTMENT_CAP
from app.simulation.constitution import DecreeAuthority, ExecutiveSelection, ExecutiveSystem
from app.simulation.decisions import BudgetDecision, ConstitutionalAmendmentDecision
from app.simulation.geography import outgoing_and_incoming
from app.simulation.legislative_voting import (
    CONSTITUTIONAL_AMENDMENT_DECREE_COST,
    DECREE_POLITICAL_CAPITAL_COST,
)
from app.simulation.legislature import LegislativeOutcome, ProposalRoute
from app.simulation.report import TurnReport
from app.simulation.state import (
    GameState,
    OutcomeBucket,
    PlayerCountryRef,
    PoliticalState,
    RouteState,
    SovereignRef,
    SpendingCategory,
    StrategicMapState,
)

Tone = Literal["positive", "negative", "caution", "neutral"]
Direction = Literal["up", "down", "unchanged"]
Severity = Literal["critical", "warning", "info"]

_STRICT = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------
# Reason-ID labels
# --------------------------------------------------------------------------
#
# Deliberately a table of this module's own, NOT an import of
# `app.cli.REASON_RENDERERS`. That table is CLI presentation, lives outside the
# mypy gate, and renders parameters into English sentences; binding API payloads
# to it would let a CLI wording change silently reshape an API response.
#
# `test_api_projections.py` asserts this table's KEY SET equals the CLI's key
# set exactly, so a newly emitted reason ID cannot reach a client unlabelled --
# the guarantee that matters, without the coupling.
REASON_LABELS: dict[str, str] = {
    "turn_resolved": "The turn was resolved.",
    "no_budget_changes_submitted": "No budget changes were submitted.",
    "tax_rate_changed": "A tax rate changed.",
    "spending_category_changed": "A spending category changed.",
    "deficit_financed_with_new_borrowing": "The deficit was financed with new borrowing.",
    "sector_inactive": "A sector was inactive this turn.",
    "labor_market_resolved": "The labour market was resolved.",
    "resource_extraction_resolved": "Resource extraction was resolved.",
    "production_summary": "Production was resolved.",
    "tax_bases_derived": "Tax bases were derived from production.",
    "legitimacy_resolved": "Legitimacy was resolved.",
    "political_capital_resolved": "Political capital was resolved.",
    "legislative_vote_resolved": "The legislature voted.",
    "budget_blocked_by_legislature": "The legislature blocked the budget.",
    "political_capital_ledger_resolved": "Political capital spending was recorded.",
    "relationship_decay_resolved": "Relationships decayed toward their authored baseline.",
    "enacted_policy_relationship_reaction": "Blocs reacted to the enacted policy.",
    "decree_bypass_relationship_reaction": "Blocs resented being bypassed by decree.",
    "bloc_relationship_resolved": "A bloc's relationship with the government changed.",
    "election_scheduled": "An election was scheduled.",
    "election_result": "The election was decided.",
    "game_concluded": "The campaign ended.",
    "coup_risk_assessed": "Coup risk was assessed.",
    "coup_attempt_occurred": "A coup was attempted.",
    "coup_succeeded": "The coup succeeded.",
    "popular_unrest_occurred": "Popular unrest broke out.",
    "impeachment_motion_brought": "An impeachment motion was brought.",
    "impeachment_succeeded": "The impeachment succeeded.",
    "constitutional_amendment_enacted": "The constitution was amended.",
    "peaceful_liberalization_completed": "Peaceful liberalization completed.",
    # External Wars W1. Labels only -- no endpoint, field, type or payload shape changes, and no
    # OpenAPI change. These six ids are already emitted by the engine; before they were labelled
    # here they reached clients as the `[reason_id]` placeholder `label_for` falls back to, which
    # this module's own key-set assertion exists to prevent. Each states what happened between
    # two FOREIGN actors and promises the player no action: W1 has no diplomacy, trade,
    # intervention or military mechanics.
    "foreign_conflict_outbreak": "A war broke out between two foreign countries.",
    "foreign_conflict_progressed": "A foreign war continued.",
    "foreign_conflict_ceasefire_entered": "A foreign war paused in a ceasefire.",
    "foreign_conflict_ceasefire_broke_down": "A foreign ceasefire broke down.",
    "foreign_conflict_terminated": "A foreign war ended.",
    "foreign_security_anxiety_applied": "Foreign wars raised security anxiety at home.",
}


def label_for(reason_id: str) -> str:
    """A stable label, with a visible placeholder rather than a crash if unmapped."""
    return REASON_LABELS.get(reason_id, f"[{reason_id}]")


# --------------------------------------------------------------------------
# Display helpers -- presentation only, never a simulation rule
# --------------------------------------------------------------------------


def format_bps_percent(value_bps: int) -> str:
    """10,000 bps == 100.00%. Integer arithmetic only; no float rounding."""
    sign = "-" if value_bps < 0 else ""
    whole, frac = divmod(abs(value_bps), 100)
    return f"{sign}{whole}.{frac:02d}%"


def format_signed_bps_points(value_bps: int) -> str:
    """A signed percentage-point delta, e.g. `+2.69pp`."""
    sign = "+" if value_bps >= 0 else "-"
    whole, frac = divmod(abs(value_bps), 100)
    return f"{sign}{whole}.{frac:02d}pp"


def revision_token(state: GameState) -> str:
    """The opaque token the contract defines as `"{turn}.{state_version}"`.

    Opaque **to the client**, which must echo it back verbatim. The server parses
    it on `/resolve` only to feed the engine's own staleness check the values the
    CLIENT claimed -- never to substitute its own (ADR 0014, revision tokens).
    """
    return f"{state.turn}.{state.state_version}"


def _politics(state: GameState) -> PoliticalState | None:
    country = state.world.countries.get(state.world.player_country_id)
    return None if country is None else country.politics


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


class ConcernCard(BaseModel):
    model_config = _STRICT

    label: str
    headline: str
    delta_text: str | None = None
    direction: Direction = "unchanged"
    tone: Tone = "neutral"
    detail_screen: str


class CapitalSummary(BaseModel):
    model_config = _STRICT

    current: int
    capacity: int
    committed_this_turn: int
    display: str


class Alert(BaseModel):
    model_config = _STRICT

    id: str
    severity: Severity
    headline: str
    detail: str | None = None
    screen: str | None = None


class GoalCard(BaseModel):
    model_config = _STRICT

    headline: str
    detail: str | None = None


class MapProjection(BaseModel):
    """The dashboard's national-tint summary card -- a single colour value, not a map of
    anything. No theater, border or geometry lives here.

    The real read-only strategic map (theaters, directed routes, authored political shapes) is a
    separate projection, `StrategicMapProjection` below, served at `GET /api/game/map/strategic`.
    Kept as a distinct type rather than folded together: this one is a dashboard summary widget,
    the other is a full spatial projection, and conflating them would make neither easy to reason
    about.
    """

    model_config = _STRICT

    presentation_only: Literal[True] = True
    tint_metric_label: str
    tint_value_bps: int
    note: str


class StrategicTheaterProjection(BaseModel):
    """One theater, fully resolved for display (Strategic Military Map, Gate M0). The client
    renders these fields and derives nothing: ownership, capital status and directed adjacency
    all arrive resolved."""

    model_config = _STRICT

    theater_id: str
    display_name: str
    kind: Literal["land", "coastal"]
    owner_id: str
    owner_namespace: Literal["player_country", "foreign_profile"]
    owner_display_name: str
    is_player_owned: bool
    is_capital: bool
    centroid_x: int
    centroid_y: int
    label_anchor: Literal["n", "s", "e", "w", "center"]
    outgoing_theater_ids: tuple[str, ...]
    """Theaters reachable FROM this one in one step. Sorted. Server-derived by
    `geography.outgoing_and_incoming`."""
    incoming_theater_ids: tuple[str, ...]
    """Theaters from which this one is reachable in one step. Sorted. Server-derived.

    Two fields, not one merged `connected_theater_ids`: with a single merged list the client
    cannot tell A->B from B->A from A<->B, and the whole point of storing directed routes is lost
    the moment the projection flattens them.
    """


class StrategicRouteProjection(BaseModel):
    """One DISPLAY edge (Strategic Military Map, Gate M0). Reciprocal directed pairs are
    collapsed into a single row so the map draws one line, never two overlapping ones."""

    model_config = _STRICT

    from_theater_id: str
    to_theater_id: str
    bidirectional: bool
    """True iff BOTH directed rows exist in authoritative state.

    When False, `from_theater_id` -> `to_theater_id` is the ONE authored direction, emitted as
    authored -- it is never reordered for determinism, because reordering it would destroy the
    only information the field carries.
    """


class StrategicShapeProjection(BaseModel):
    """One authored political outline (Strategic Military Map, Gate M0). Presentation only;
    never implies adjacency."""

    model_config = _STRICT

    shape_id: str
    owner_id: str
    owner_namespace: Literal["player_country", "foreign_profile"]
    owner_display_name: str
    polygon: tuple[tuple[int, int], ...]
    """Open ring, emitted in stored authored order. No rotation or winding normalization."""


class StrategicMapProjection(BaseModel):
    """The whole read-only strategic map (Strategic Military Map, Gate M0). Contains no order,
    no command, no pending action and no affordance for one."""

    model_config = _STRICT

    map_id: str
    capital_theater_id: str
    theaters: tuple[StrategicTheaterProjection, ...]
    routes: tuple[StrategicRouteProjection, ...]
    shapes: tuple[StrategicShapeProjection, ...]


class TerminalSummary(BaseModel):
    model_config = _STRICT

    bucket: Literal["victory", "defeat"]
    reason_label: str
    turn: int
    headline: str


class DashboardConcerns(BaseModel):
    model_config = _STRICT

    money: ConcernCard
    legitimacy: ConcernCard
    legislature: ConcernCard
    constitution: ConcernCard
    survival: ConcernCard


class DashboardProjection(BaseModel):
    model_config = _STRICT

    revision: str
    turn: int
    country_name: str
    government_form: str
    next_election_label: str
    concerns: DashboardConcerns
    political_capital: CapitalSummary
    alerts: tuple[Alert, ...] = ()
    goal: GoalCard
    map: MapProjection
    terminal: TerminalSummary | None = None


# --------------------------------------------------------------------------
# Turn result -- ONE type, ONE builder, used by live and history alike
# --------------------------------------------------------------------------


class DriverItem(BaseModel):
    model_config = _STRICT

    #: Gate 4A3A: `TurnReportEntry.category` already exists on the stored
    #: report and was already being read (`entry.category` below) -- it was
    #: simply never carried into the projection. Restoring it lets the
    #: consequences panel group real resolved drivers (policy / vote /
    #: relationships / economy / political events) without inventing any new
    #: data or duplicating a formula.
    category: str
    reason_id: str
    label: str
    params: dict[str, str | int] = Field(default_factory=dict)


class LedgerEntry(BaseModel):
    model_config = _STRICT

    label: str
    target: str | None = None
    amount_text: str
    effect_text: str | None = None


class TraceField(BaseModel):
    model_config = _STRICT

    label: str
    value_text: str
    source_field: str


class TurnResultProjection(BaseModel):
    model_config = _STRICT

    revision: str
    turn: int
    outcome_headline: str
    outcome_tone: Tone
    drivers: tuple[DriverItem, ...] = ()
    ledger: tuple[LedgerEntry, ...] = ()
    unchanged: tuple[str, ...] = ()
    trace: tuple[TraceField, ...] = ()
    terminal: TerminalSummary | None = None


# --------------------------------------------------------------------------
# Summaries and envelopes
# --------------------------------------------------------------------------


class ChamberPreview(BaseModel):
    """One chamber's projected tally. Chambers are never pooled."""

    model_config = _STRICT

    chamber: str
    total_seats: int
    supporting_seats: int
    required_seats: int
    carries: bool


class PreviewProjection(BaseModel):
    """A deterministic ESTIMATE, explicitly not an authoritative outcome.

    `estimate` is always True and `excludes_stochastic_channels` names what the
    preview deliberately does not know, so no caller can mistake this for a
    resolved result.
    """

    model_config = _STRICT

    estimate: Literal[True] = True
    excludes_stochastic_channels: tuple[str, ...] = ()
    chambers: tuple[ChamberPreview, ...] = ()
    would_pass: bool = False
    has_proposal: bool = False
    route: str | None = None
    route_capital_cost: int = 0
    influence_capital: int = 0
    investment_capital: int = 0
    committed_capital: int = 0
    opening_capital: int = 0
    affordable: bool = True


class ScenarioSummary(BaseModel):
    model_config = _STRICT

    scenario_id: str
    display_name: str
    government_form: str
    election_interval_label: str
    starting_legitimacy_text: str
    is_showcase: bool


class SaveSummary(BaseModel):
    model_config = _STRICT

    save_id: str
    display_name: str
    scenario_id: str
    current_turn: int
    updated_at: str
    terminal_outcome_summary: str | None = None
    loadable: bool = True
    integrity_problem: str | None = None


class HistoryListEntry(BaseModel):
    model_config = _STRICT

    turn: int
    outcome_line: str
    tone: Tone


class ResolveResponse(BaseModel):
    """Shape A -- live resolution. Envelope keys are camelCase per the contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    turn_result: TurnResultProjection = Field(serialization_alias="turnResult", alias="turnResult")
    dashboard: DashboardProjection


class HistoryDetailResponse(BaseModel):
    """Shape B -- historical detail. Same `TurnResultProjection` type as Shape A."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    turn_result: TurnResultProjection = Field(serialization_alias="turnResult", alias="turnResult")
    dashboard_as_of_turn: DashboardProjection = Field(
        serialization_alias="dashboardAsOfTurn", alias="dashboardAsOfTurn"
    )


# --------------------------------------------------------------------------
# Decision options -- the legal-move envelope (frozen plan Sec 4.6, Sec 10)
# --------------------------------------------------------------------------


class SpendingCategoryOption(BaseModel):
    model_config = _STRICT

    category: str
    current_amount: int


class BlocOption(BaseModel):
    model_config = _STRICT

    party_id: str
    party_name: str
    bloc_id: str
    bloc_name: str
    chamber: str
    seats: int


class ConstitutionalAxisOption(BaseModel):
    model_config = _STRICT

    axis: str
    current_value: str | int | None
    allowed_values: tuple[str, ...] | None = None
    #: Whether submitting `null` for this axis is a legal target (an abolished
    #: term limit or election requirement), distinct from an enum axis where
    #: every value is one of `allowed_values` and never null.
    nullable: bool = False


# --------------------------------------------------------------------------
# Policy cards (Gate 4A3A) -- server-authored, typed, self-validating.
#
# The browser must not calculate legal policy targets, costs, thresholds, or
# consequences. A card's `routes[].template`, when present, is a REAL,
# canonical, submit-ready `BudgetDecision` or `ConstitutionalAmendmentDecision`
# -- the same discriminated union `DecisionSet` itself accepts -- never a
# `dict[str, Any]`. React may wrap the chosen template with investments and
# revision metadata through the existing `buildDecisions` builder; it computes
# no proposal content.
#
# Affordability is deliberately NOT an availability concept here (see
# `decision_preflight.py`'s own docstring for why): a route the player cannot
# currently afford is still a legal, selectable choice, and `/preview`'s
# `committed_capital`/`opening_capital`/`affordable` fields are what explain
# the shortfall once a card is selected and previewed.
# --------------------------------------------------------------------------

PolicyCardCategory = Literal["taxation", "spending", "constitution", "restraint"]

PolicyCardUnavailableReason = Literal[
    "route_constitutionally_unavailable",
    "no_legislature",
    "decree_cannot_amend_with_legislature",
    "requires_companion_constitutional_change",
    "outside_legal_bounds",
    "no_baseline_to_scale",
    "no_change_from_current",
    "game_concluded",
]


class PolicyCardEffect(BaseModel):
    """One "current -> proposed" fact about a card, in RAW typed form (R6).

    No value here is preformatted ("20.00%", "200,000,000"): `current_value`/
    `proposed_value` are the raw bps/money/turn/term integers, `unit` names
    which format function in `src/format/**` applies, and `current_label`/
    `proposed_label` carry ONLY server-authored enum display text (there is no
    numeric formatting to do for an enum). React formats the raw values; it
    never invents or reformats a number itself.
    """

    model_config = _STRICT

    label: str
    unit: Literal["bps", "money", "turns", "terms", "enum"]
    current_value: int | None = None
    proposed_value: int | None = None
    current_label: str | None = None
    proposed_label: str | None = None
    direction: Direction


class PolicyCardChamberRequirement(BaseModel):
    model_config = _STRICT

    chamber: str
    total_seats: int
    required_seats: int


class PolicyCardRoute(BaseModel):
    """One route (legislative or decree) a card could be submitted through.

    R11: no affordability field lives here. R2/R3: `template` is a real typed
    decision or `None` -- never a placeholder dict.
    """

    model_config = _STRICT

    route: ProposalRoute
    available: bool
    unavailable_reason: PolicyCardUnavailableReason | None = None
    unavailable_detail: str | None = None
    base_route_cost: int
    bargaining_available: bool
    chambers: tuple[PolicyCardChamberRequirement, ...] = ()
    template: (
        Annotated[BudgetDecision | ConstitutionalAmendmentDecision, Field(discriminator="kind")]
        | None
    ) = None

    @model_validator(mode="after")
    def _availability_matches_template(self) -> PolicyCardRoute:
        if self.available and self.template is None:
            raise ValueError("an available route must carry a template")
        if not self.available and self.template is not None:
            raise ValueError("an unavailable route must not carry a template")
        return self

    @model_validator(mode="after")
    def _available_route_has_no_reason(self) -> PolicyCardRoute:
        if self.available and (
            self.unavailable_reason is not None or self.unavailable_detail is not None
        ):
            raise ValueError("an available route must not carry an unavailable reason or detail")
        return self

    @model_validator(mode="after")
    def _unavailable_route_explains_itself(self) -> PolicyCardRoute:
        if not self.available and (
            self.unavailable_reason is None or self.unavailable_detail is None
        ):
            raise ValueError(
                "an unavailable route must carry both a stable reason and a player-facing detail"
            )
        return self

    # No `_no_diagnostic_leak_into_player_text` here: a route carries no
    # `diagnostic_code` field (only `PolicyCard` does -- constitutional
    # coherence is a property of the amendment TARGET, which is route-
    # independent), so there is nothing at this level to check a leak
    # against. See `PolicyCard`'s own version of this validator below.


class PolicyCard(BaseModel):
    model_config = _STRICT

    card_id: str
    category: PolicyCardCategory
    category_label: str
    title: str
    description: str
    available: bool
    unavailable_reason: PolicyCardUnavailableReason | None = None
    unavailable_detail: str | None = None
    #: The raw internal rule id (e.g. a C-rule name), kept SEPARATE from
    #: `unavailable_detail` so it can never leak into player-facing text.
    diagnostic_code: str | None = None
    #: True only for the single "take no major policy action" card -- it
    #: explicitly clears the proposal slot rather than carrying a template.
    clears_proposal_slot: bool = False
    effects: tuple[PolicyCardEffect, ...] = ()
    routes: tuple[PolicyCardRoute, ...] = ()

    @model_validator(mode="after")
    def _available_card_has_no_reason(self) -> PolicyCard:
        if self.available and (
            self.unavailable_reason is not None or self.unavailable_detail is not None
        ):
            raise ValueError("an available card must not carry an unavailable reason or detail")
        return self

    @model_validator(mode="after")
    def _unavailable_card_explains_itself(self) -> PolicyCard:
        if not self.available and (
            self.unavailable_reason is None or self.unavailable_detail is None
        ):
            raise ValueError(
                "an unavailable card must carry both a stable reason and a player-facing detail"
            )
        return self

    @model_validator(mode="after")
    def _no_diagnostic_leak_into_player_text(self) -> PolicyCard:
        """`diagnostic_code` holds the raw internal rule id `first_constitutional_violation`
        returns -- a snake_case identifier such as `hereditary_requires_monarchical_system`,
        never a "C7"-style code -- so the leak check compares against THIS card's own actual
        value, not a hardcoded placeholder prefix that would never match anything real."""
        if (
            self.diagnostic_code is not None
            and self.unavailable_detail is not None
            and self.diagnostic_code in self.unavailable_detail
        ):
            raise ValueError("a diagnostic code must never appear in player-facing text")
        return self

    @model_validator(mode="after")
    def _proposal_card_availability_matches_its_routes(self) -> PolicyCard:
        """Rule 4/6/7 (§3 invariants): for a PROPOSAL card, `available` is
        true iff at least one route is available; an unavailable proposal
        card has no available route and no template on any route. The
        no-proposal card is the explicit special case this rule skips."""
        if self.clears_proposal_slot:
            return self
        any_route_available = any(route.available for route in self.routes)
        if self.available != any_route_available:
            raise ValueError(
                "a proposal card's availability must match whether any route is available"
            )
        return self

    @model_validator(mode="after")
    def _no_proposal_card_has_no_routes(self) -> PolicyCard:
        if self.clears_proposal_slot and self.routes:
            raise ValueError("the no-proposal card clears the slot; it carries no routes")
        return self


class DecisionOptionsProjection(BaseModel):
    """Every REAL fact and constant needed to construct a legal decision.

    Nothing here is invented: the bps and capital bounds are the engine's own
    strict types and constants (`StrictBps`, `RELATIONSHIP_INVESTMENT_CAP`,
    `DECREE_POLITICAL_CAPITAL_COST`, `CONSTITUTIONAL_AMENDMENT_DECREE_COST`),
    and the spending, bloc and constitutional-axis listings are read straight
    from state. This endpoint answers "what exists to choose from" -- it never
    scores a draft (`/preview` does that) and never decides legality on
    submission (`/resolve`'s own validators still do, authoritatively).

    `policy_cards` is the Gate 4A3A game-loop projection: named, understood
    choices generated from this SAME state. It shares this envelope's
    `revision`, so a card catalog and the legal-move facts it was generated
    from are always the same age.
    """

    model_config = _STRICT

    revision: str
    opening_capital: int
    tax_rate_bps_minimum: int
    tax_rate_bps_maximum: int
    spending_categories: tuple[SpendingCategoryOption, ...]
    relationship_investment_minimum: int
    relationship_investment_maximum: int
    decree_available: bool
    decree_legislative_capital_cost: int
    decree_amendment_capital_cost: int
    policy_cards: tuple[PolicyCard, ...] = ()
    chambers: tuple[str, ...]
    blocs: tuple[BlocOption, ...]
    constitutional_axes: tuple[ConstitutionalAxisOption, ...]


def build_decision_options(state: GameState) -> DecisionOptionsProjection:
    country = state.world.countries[state.world.player_country_id]
    politics = country.politics
    if politics is None:  # pragma: no cover - every shipped scenario has politics
        raise ValueError("player country has no political state")
    constitution = politics.constitution
    finance = country.finance

    spending_categories = (
        ()
        if finance is None
        else tuple(
            SpendingCategoryOption(
                category=category.value, current_amount=finance.spending_plan.get(category)
            )
            for category in SpendingCategory
        )
    )

    legislature = politics.legislature
    chambers: tuple[str, ...] = ()
    blocs: list[BlocOption] = []
    if legislature is not None:
        chambers = tuple(chamber.chamber.value for chamber in legislature.chambers)
        for party in legislature.parties:
            for bloc in party.blocs:
                for seat_entry in bloc.seats:
                    blocs.append(
                        BlocOption(
                            party_id=party.id,
                            party_name=party.name,
                            bloc_id=bloc.id,
                            bloc_name=bloc.name,
                            chamber=seat_entry.chamber.value,
                            seats=seat_entry.seats,
                        )
                    )

    constitutional_axes = (
        ConstitutionalAxisOption(
            axis="decree_authority",
            current_value=constitution.decree_authority.value,
            allowed_values=tuple(member.value for member in DecreeAuthority),
        ),
        ConstitutionalAxisOption(
            axis="executive_system",
            current_value=constitution.executive_system.value,
            allowed_values=tuple(member.value for member in ExecutiveSystem),
        ),
        ConstitutionalAxisOption(
            axis="executive_selection",
            current_value=constitution.executive_selection.value,
            allowed_values=tuple(member.value for member in ExecutiveSelection),
        ),
        ConstitutionalAxisOption(
            axis="national_election_interval_turns",
            current_value=constitution.national_election_interval_turns,
            nullable=True,
        ),
        ConstitutionalAxisOption(
            axis="executive_term_limit_terms",
            current_value=constitution.executive_term_limit_terms,
            nullable=True,
        ),
    )

    return DecisionOptionsProjection(
        revision=revision_token(state),
        opening_capital=politics.political_capital,
        tax_rate_bps_minimum=0,
        tax_rate_bps_maximum=BPS_DENOMINATOR,
        spending_categories=spending_categories,
        relationship_investment_minimum=1,
        relationship_investment_maximum=RELATIONSHIP_INVESTMENT_CAP,
        decree_available=constitution.decree_authority is DecreeAuthority.UNLIMITED,
        decree_legislative_capital_cost=DECREE_POLITICAL_CAPITAL_COST,
        decree_amendment_capital_cost=CONSTITUTIONAL_AMENDMENT_DECREE_COST,
        chambers=chambers,
        blocs=tuple(blocs),
        constitutional_axes=constitutional_axes,
    )


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------

_GOVERNMENT_FORM_LABELS: dict[str, str] = {
    "monarchy": "Monarchy",
    "presidential": "Presidential republic",
    "parliamentary": "Parliamentary republic",
    "semi_presidential": "Semi-presidential republic",
    "directorial": "Directorial republic",
}

_DECREE_LABELS: dict[DecreeAuthority, str] = {
    DecreeAuthority.NONE: "no decree authority",
    DecreeAuthority.EMERGENCY_ONLY: "emergency decree authority",
    DecreeAuthority.UNLIMITED: "unlimited decree authority",
}


def _government_form_label(politics: PoliticalState) -> str:
    system = politics.constitution.executive_system.value
    base = _GOVERNMENT_FORM_LABELS.get(system, system.replace("_", " ").capitalize())
    return f"{base}, {_DECREE_LABELS[politics.constitution.decree_authority]}"


def _terminal_summary(politics: PoliticalState) -> TerminalSummary | None:
    outcome = politics.terminal_outcome
    if outcome is None:
        return None
    victory = outcome.bucket is OutcomeBucket.VICTORY
    reason = outcome.victory_reason if victory else outcome.removal_reason
    reason_label = reason.value if reason is not None else "unknown"
    spoken = reason_label.replace("_", " ")
    return TerminalSummary(
        bucket="victory" if victory else "defeat",
        reason_label=reason_label,
        turn=outcome.turn,
        headline=(
            f"Victory: {spoken}, turn {outcome.turn}."
            if victory
            else f"Removed from office: {spoken}, turn {outcome.turn}."
        ),
    )


def build_dashboard(state: GameState, report: TurnReport | None) -> DashboardProjection:
    """The country's CURRENT condition.

    `report` is the stored report for the turn this state was reached by, or
    `None` at turn 0 where the genesis entry legitimately has none. Risk figures
    live in `CoupUnrestReport`, not in `GameState`, so when there is no report
    they are reported as not yet assessed rather than recomputed -- recomputing
    would invent a forward-looking number and present it as a resolved fact.
    """
    country = state.world.countries[state.world.player_country_id]
    politics = country.politics
    if politics is None:  # pragma: no cover - every shipped scenario has politics
        raise ValueError("player country has no political state")

    finance = report.finance if report is not None else None
    balance = None if finance is None else finance.pre_financing_balance

    money = ConcernCard(
        label="Money",
        headline=format_money(country.treasury.cash_on_hand),
        delta_text=None if balance is None else format_money(balance),
        direction="unchanged" if balance is None else ("down" if balance < 0 else "up"),
        tone="neutral" if balance is None else ("negative" if balance < 0 else "positive"),
        detail_screen="economy",
    )
    legitimacy = ConcernCard(
        label="Legitimacy",
        headline=format_bps_percent(politics.legitimacy_bps),
        tone="caution" if politics.legitimacy_bps < 5_000 else "neutral",
        detail_screen="government",
    )

    legislature = politics.legislature
    if legislature is None:
        seats_headline = "No legislature"
    else:
        total = sum(chamber.total_seats for chamber in legislature.chambers)
        seats_headline = f"{len(legislature.parties)} parties, {total} seats"

    coup = report.coup_unrest if report is not None else None
    if coup is None:
        survival_headline = "Not yet assessed"
        survival_tone: Tone = "neutral"
    else:
        survival_headline = f"Coup risk {format_bps_percent(coup.coup.attempt_risk_bps)}"
        survival_tone = "caution" if coup.coup.attempt_risk_bps > 0 else "neutral"

    difficulty = politics.constitution.amendment_difficulty.value.replace("_", " ").capitalize()
    return DashboardProjection(
        revision=revision_token(state),
        turn=state.turn,
        country_name=country.name,
        government_form=_government_form_label(politics),
        next_election_label=(
            "None scheduled"
            if politics.next_election_turn is None
            else f"Turn {politics.next_election_turn}"
        ),
        concerns=DashboardConcerns(
            money=money,
            legitimacy=legitimacy,
            legislature=ConcernCard(
                label="Legislature", headline=seats_headline, detail_screen="legislature"
            ),
            constitution=ConcernCard(
                label="Constitution", headline=difficulty, detail_screen="constitution"
            ),
            survival=ConcernCard(
                label="Survival",
                headline=survival_headline,
                tone=survival_tone,
                detail_screen="government",
            ),
        ),
        political_capital=CapitalSummary(
            current=politics.political_capital,
            capacity=politics.political_capital_capacity,
            committed_this_turn=(
                0
                if report is None or report.political_capital is None
                else report.political_capital.total_committed
            ),
            display=f"{politics.political_capital} / {politics.political_capital_capacity}",
        ),
        alerts=_build_alerts(politics, report),
        goal=_build_goal(politics, report),
        map=MapProjection(
            tint_metric_label="Legitimacy",
            tint_value_bps=politics.legitimacy_bps,
            note=(
                "This is a national identity tint, not a geographic map. No province-level "
                "mechanics exist."
            ),
        ),
        terminal=_terminal_summary(politics),
    )


def _build_alerts(politics: PoliticalState, report: TurnReport | None) -> tuple[Alert, ...]:
    """Ranked server-side: terminal > survival > election > liberalization > fiscal."""
    alerts: list[Alert] = []
    terminal = _terminal_summary(politics)
    if terminal is not None:
        alerts.append(
            Alert(id="terminal", severity="critical", headline=terminal.headline, screen="terminal")
        )
    coup = report.coup_unrest if report is not None else None
    if coup is not None and coup.coup.attempt_risk_bps > 0:
        alerts.append(
            Alert(
                id="coup-risk",
                severity="warning" if coup.coup.attempt_risk_bps >= 1_000 else "info",
                headline=f"Coup risk {format_bps_percent(coup.coup.attempt_risk_bps)}.",
                screen="government",
            )
        )
    if politics.next_election_turn is not None:
        alerts.append(
            Alert(
                id="election-scheduled",
                severity="info",
                headline=f"An election is scheduled for turn {politics.next_election_turn}.",
                screen="government",
            )
        )
    if politics.pending_liberalization is not None:
        alerts.append(
            Alert(
                id="pending-liberalization",
                severity="info",
                headline="A liberalizing transition is pending confirmation at the next election.",
                screen="constitution",
            )
        )
    finance = report.finance if report is not None else None
    if finance is not None and finance.pre_financing_balance < 0:
        alerts.append(
            Alert(
                id="fiscal-deficit",
                severity="warning",
                headline="The budget is running a deficit.",
                screen="economy",
            )
        )
    return tuple(alerts)


def _build_goal(politics: PoliticalState, report: TurnReport | None) -> GoalCard:
    """One current-priority sentence, from the SAME ranking the alerts use.

    Never a fabricated narrative: every branch traces to a real state or report
    field, and the fallback says plainly that nothing is pressing.
    """
    ranked = _build_alerts(politics, report)
    if ranked:
        return GoalCard(headline=f"Your priority: {ranked[0].headline}", detail=ranked[0].detail)
    return GoalCard(headline="Nothing is pressing. Consider how to use your political capital.")


# --------------------------------------------------------------------------
# Strategic map -- read-only, Strategic Military Map Gate M0
# --------------------------------------------------------------------------


def _resolve_owner(
    owner: SovereignRef, state: GameState
) -> tuple[str, Literal["player_country", "foreign_profile"], str, bool]:
    """`(owner_id, owner_namespace, owner_display_name, is_player_owned)` for one `SovereignRef`.

    The one shared resolution used for both theater owners and shape owners (mirrors the shared
    invariant rule in `simulation.invariants._sovereign_ref_violation`) -- state invariants
    already guarantee the reference resolves, so there is no defensive fallback text here.
    """
    if isinstance(owner, PlayerCountryRef):
        country = state.world.countries[owner.country_id]
        return owner.country_id, "player_country", country.name, True
    profile = state.world.foreign_profiles[owner.foreign_profile_id]
    return owner.foreign_profile_id, "foreign_profile", profile.display_name, False


def _build_strategic_theaters(
    strategic_map: StrategicMapState, state: GameState
) -> tuple[StrategicTheaterProjection, ...]:
    theaters = []
    for theater_id, theater in strategic_map.theaters.items():
        owner_id, owner_namespace, owner_display_name, is_player_owned = _resolve_owner(
            theater.owner, state
        )
        outgoing, incoming = outgoing_and_incoming(theater_id, strategic_map.routes)
        theaters.append(
            StrategicTheaterProjection(
                theater_id=theater_id,
                display_name=theater.display_name,
                kind=theater.kind.value,
                owner_id=owner_id,
                owner_namespace=owner_namespace,
                owner_display_name=owner_display_name,
                is_player_owned=is_player_owned,
                is_capital=(theater_id == strategic_map.capital_theater_id),
                centroid_x=theater.presentation.centroid_x,
                centroid_y=theater.presentation.centroid_y,
                label_anchor=theater.presentation.label_anchor.value,
                outgoing_theater_ids=outgoing,
                incoming_theater_ids=incoming,
            )
        )
    return tuple(sorted(theaters, key=lambda t: t.theater_id))


def _build_strategic_routes(
    routes: tuple[RouteState, ...],
) -> tuple[StrategicRouteProjection, ...]:
    """Collapse directed rows into display rows (frozen plan sec.11.1).

    A pair with both directed rows collapses to one row `from=min(a,b), to=max(a,b),
    bidirectional=True`; a pair with exactly one directed row is emitted EXACTLY as authored,
    `bidirectional=False`, never flipped -- reordering a one-way row would destroy the only
    information it carries.
    """
    directed_pairs = {(r.from_theater, r.to_theater) for r in routes}
    seen_unordered: set[frozenset[str]] = set()
    projections = []
    for from_theater, to_theater in directed_pairs:
        pair_key = frozenset((from_theater, to_theater))
        if pair_key in seen_unordered:
            continue
        seen_unordered.add(pair_key)
        reverse_exists = (to_theater, from_theater) in directed_pairs
        if reverse_exists:
            low, high = sorted((from_theater, to_theater))
            projections.append(
                StrategicRouteProjection(
                    from_theater_id=low, to_theater_id=high, bidirectional=True
                )
            )
        else:
            projections.append(
                StrategicRouteProjection(
                    from_theater_id=from_theater, to_theater_id=to_theater, bidirectional=False
                )
            )
    return tuple(sorted(projections, key=lambda r: (r.from_theater_id, r.to_theater_id)))


def _build_strategic_shapes(
    strategic_map: StrategicMapState, state: GameState
) -> tuple[StrategicShapeProjection, ...]:
    shapes = []
    for shape in strategic_map.shapes:
        owner_id, owner_namespace, owner_display_name, _is_player_owned = _resolve_owner(
            shape.owner, state
        )
        shapes.append(
            StrategicShapeProjection(
                shape_id=shape.shape_id,
                owner_id=owner_id,
                owner_namespace=owner_namespace,
                owner_display_name=owner_display_name,
                polygon=shape.polygon,
            )
        )
    return tuple(sorted(shapes, key=lambda s: s.shape_id))


def build_strategic_map(state: GameState) -> StrategicMapProjection:
    """The whole read-only strategic map, resolved for display. Pure: reads `state` only, never
    mutates it, never draws RNG. Every collection is emitted in server-sorted (and therefore
    insertion-order-independent) order except `polygon`, which stays in stored authored order."""
    strategic_map = state.world.strategic_map
    return StrategicMapProjection(
        map_id=strategic_map.map_id,
        capital_theater_id=strategic_map.capital_theater_id,
        theaters=_build_strategic_theaters(strategic_map, state),
        routes=_build_strategic_routes(strategic_map.routes),
        shapes=_build_strategic_shapes(strategic_map, state),
    )


def build_turn_result(state: GameState, report: TurnReport) -> TurnResultProjection:
    """THE turn-result builder. Live resolution and history detail both call this.

    `state` is the state the turn produced; `report` is that turn's stored,
    already-validated `TurnReport`. Nothing is recomputed from current state --
    a historical turn renders from the report written when it happened.
    """
    politics = _politics(state)
    drivers = tuple(
        DriverItem(
            category=entry.category,
            reason_id=entry.reason_id,
            label=label_for(entry.reason_id),
            params=entry.params,
        )
        for entry in report.entries
    )

    ledger: list[LedgerEntry] = []
    capital = report.political_capital
    if capital is not None:
        for row in capital.expenditures:
            target = (
                f"{row.party_id}/{row.bloc_id}"
                if row.party_id is not None and row.bloc_id is not None
                else None
            )
            ledger.append(
                LedgerEntry(
                    label=row.category.value.replace("_", " ").capitalize(),
                    target=target,
                    amount_text=str(row.political_capital),
                )
            )

    trace: list[TraceField] = []
    legislative = report.legislative
    if legislative is not None:
        for chamber in legislative.chambers:
            trace.append(
                TraceField(
                    label=f"{chamber.chamber.value}: supporting seats",
                    value_text=str(chamber.supporting_seats),
                    source_field="LegislativeReport.chambers[].supporting_seats",
                )
            )
            trace.append(
                TraceField(
                    label=f"{chamber.chamber.value}: required seats",
                    value_text=str(chamber.required_yes_seats),
                    source_field="LegislativeReport.chambers[].required_yes_seats",
                )
            )
    amendment = report.constitutional_amendment
    if amendment is not None:
        for tally in amendment.chambers:
            trace.append(
                TraceField(
                    label=f"Amendment {tally.chamber.value}: supporting of required",
                    value_text=f"{tally.supporting_seats} of {tally.required_yes_seats}",
                    source_field="ConstitutionalAmendmentReport.chambers[].supporting_seats",
                )
            )
    election = report.election
    if election is not None:
        trace.append(
            TraceField(
                label="Final election support",
                value_text=format_bps_percent(election.final_support_bps),
                source_field="ElectionReport.final_support_bps",
            )
        )
    if capital is not None:
        trace.append(
            TraceField(
                label="Political capital committed",
                value_text=str(capital.total_committed),
                source_field="PoliticalCapitalReport.total_committed",
            )
        )

    headline, tone = _outcome_headline(report)
    return TurnResultProjection(
        revision=revision_token(state),
        # The turn this result PRODUCED, i.e. the history index it is filed
        # under -- not `report.resolved_turn`, which is the opening turn the
        # resolution ran against and is one lower.
        turn=state.turn,
        outcome_headline=headline,
        outcome_tone=tone,
        drivers=drivers,
        ledger=tuple(ledger),
        unchanged=_unchanged_statements(report),
        trace=tuple(trace),
        terminal=None if politics is None else _terminal_summary(politics),
    )


_ENACTED = (LegislativeOutcome.PASSED_LEGISLATIVE, LegislativeOutcome.ENACTED_BY_DECREE)


def _outcome_headline(report: TurnReport) -> tuple[str, Tone]:
    """Layer 1: one sentence, chosen from what the report actually records."""
    amendment = report.constitutional_amendment
    if amendment is not None and amendment.proposed:
        passed = amendment.outcome in _ENACTED
        first = amendment.chambers[0] if amendment.chambers else None
        detail = (
            f", {first.supporting_seats} of {first.total_seats} seats "
            f"({first.required_yes_seats} required)"
            if first is not None
            else ""
        )
        return (
            (f"Amendment passed{detail}." if passed else f"Amendment failed{detail}."),
            "positive" if passed else "negative",
        )
    election = report.election
    if election is not None and election.result in ("won", "lost"):
        won = election.result == "won"
        return (
            f"The election was {'won' if won else 'lost'} with "
            f"{format_bps_percent(election.final_support_bps)}.",
            "positive" if won else "negative",
        )
    legislative = report.legislative
    if legislative is not None:
        if legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE:
            return ("The budget was enacted by the legislature.", "positive")
        if legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE:
            return ("The budget was enacted by decree. The legislature was bypassed.", "caution")
        if legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE:
            return ("The budget was blocked. Committed capital was still spent.", "negative")
    return ("The turn was resolved.", "neutral")


def _unchanged_statements(report: TurnReport) -> tuple[str, ...]:
    """Explicit 'what did NOT change' lines, from stored report fields only."""
    lines: list[str] = []
    legislative = report.legislative
    if legislative is not None and legislative.outcome is LegislativeOutcome.NO_PROPOSAL:
        lines.append("No policy proposal was submitted.")
    if legislative is not None and legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE:
        lines.append("Tax rates and spending are unchanged.")
    if report.election is None:
        lines.append("No election was held this turn.")
    if report.constitutional_amendment is None:
        lines.append("The constitution is unchanged.")
    return tuple(lines)
