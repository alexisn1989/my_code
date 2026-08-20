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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import format_money
from app.simulation.constitution import DecreeAuthority
from app.simulation.legislature import LegislativeOutcome
from app.simulation.report import TurnReport
from app.simulation.state import GameState, OutcomeBucket, PoliticalState

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
    """Presentation only. The engine has no province, region, or spatial state."""

    model_config = _STRICT

    presentation_only: Literal[True] = True
    tint_metric_label: str
    tint_value_bps: int
    note: str


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
            note="This map shows national identity only. No province-level mechanics exist.",
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


def build_turn_result(state: GameState, report: TurnReport) -> TurnResultProjection:
    """THE turn-result builder. Live resolution and history detail both call this.

    `state` is the state the turn produced; `report` is that turn's stored,
    already-validated `TurnReport`. Nothing is recomputed from current state --
    a historical turn renders from the report written when it happened.
    """
    politics = _politics(state)
    drivers = tuple(
        DriverItem(reason_id=entry.reason_id, label=label_for(entry.reason_id), params=entry.params)
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
