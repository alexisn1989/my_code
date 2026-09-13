"""Report-vs-state reconciliation for the political and legislative domains.

`TurnReport` is constructed from reports only and has no `GameState` reference (the same
structural limit that produced Phase 2C2's late deviation — see F1) — so a check that needs
BOTH a report and the state it describes cannot live as a `TurnReport` validator. `resolve_turn`
already holds, in one scope, both the caller's untouched input `state` and the mutated `working`
copy (F15); this module's one function takes both, plus the report and the actual submitted
`DecisionSet`, and returns every disagreement it finds — never raising itself.

**Groups 1–11 (Phase 3A) are unchanged.** `FinanceReport.closing_cash` vs `TreasuryState
.cash_on_hand` remains a real, pre-existing, out-of-scope gap (F8, FIN-1).

**Groups 12–18 (Phase 3B1, R8) are new; groups 19–21 (Phase 3B2A) extend them further, and
group 12 is REWRITTEN in place (R12).** Group 16 is the one place this module reads
`finance.tax_policy`/`finance.spending_plan` — not balances, only policy — to prove the budget
gate actually gated against the real submitted command, not merely against report prose.

**R12 — why group 12 changed.** Its Phase 3B1 form gated groups 13–15 on whole-model
`opening_legislature == closing_legislature`. Phase 3B2A makes `government_relationship_bps`
genuinely mutable, so that condition is now false on the exact turns that most need structural
coverage — a corrupted chamber or seat count on an investment turn would have gone completely
unchecked. The fix drops that condition as a gate for groups 13–15 (which compare the REPORT's
chamber/bloc rows against state, and therefore still only run when the report carries such rows —
i.e. a turn with an actual vote) and additionally gives group 12 itself a direct STATE-TO-STATE
staticness proof that runs on every turn a legislature exists, independent of whether the report
carries any rows at all: the `==` comparison stays as a fast path on turns with no reported
relationship change (the O(1) common case), and a field-by-field slow path takes over the moment a
relationship change is reported, checking chambers, and every party/bloc's role, discipline and
both preferences, directly between the two states. This is what actually closes the coverage hole:
a NO_PROPOSAL or ENACTED_BY_DECREE turn carries ZERO chamber/bloc rows in its report by
construction (there was no vote to report), so groups 13–15 alone could never see a corruption on
such a turn no matter how the guard was written — only a check that reads state directly, with no
report row as an intermediary, can. `government_relationship_bps` is deliberately excluded from
both group 12's slow path and group 14's comparison, and is instead compared against the OPENING
state alone by group 14 (the value the vote was scored against) — its CLOSING value is group 20's
job, never group 12's or 14's.

**Composition, not re-derivation, for apportionment (group 15, user-directed).** State holds a
bloc's `seats` and a chamber's `total_seats` and nothing else — no `numerator`, `base_seats`,
`remainder`, `bonus_seat`, `supporting_seats` or `required_yes_seats` exists anywhere in
`GameState`. This module therefore compares only what state actually holds — seats — and proves
the rest **transitively**, by composition with `LegislativeReport`'s own self-validators (already
re-run on every parse, live or replayed):

```
validator #9  (report):  required_yes_seats == report_chamber.total_seats // 2 + 1
+ group 13    (here)  :  report_chamber.total_seats == state_chamber.total_seats
⇒                        required_yes_seats == state_chamber.total_seats // 2 + 1

validators #7/#8 (report): numerator/base_seats/remainder/bonus_seat/supporting_seats are all
                            correct given each row's own `seats`
+ group 14/15    (here) :  every report row's `seats` equals the real state bloc's seats in that
                            chamber, and no state row is missing or invented
⇒                          the whole apportionment describes the real legislature, without this
                            module ever importing `legislative_voting`/`apportionment` or
                            duplicating a single formula
```

A future reader who notices numerator/base/remainder/bonus/required-majority are never directly
compared against state here should read this docstring before "fixing" the apparent gap by
re-deriving voting formulas inside reconciliation — that would be a second, redundant formula
implementation, exactly the thing R1 forbids.

**No fixed total comparison count is claimed.** What is guaranteed is that every group, and every
individual field within a group, is independently corruptible and independently rejected (see
`tests/test_reconciliation.py`).
"""

from __future__ import annotations

from enum import StrEnum

from app.core.canonical_json import canonical_dumps
from app.core.money import BPS_DENOMINATOR
from app.core.politics import (
    RELATIONSHIP_DECAY_DENOMINATOR,
    RELATIONSHIP_DECAY_NUMERATOR,
    trunc_div_toward_zero,
)
from app.core.rng import derive_rng
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.cabinet import (
    appointment_cost_capital,
    effective_holder_id,
    holder_competence_bps,
)
from app.simulation.constitution import (
    DecreeAuthority,
    ExecutiveSelection,
    JudicialReview,
    Legislature,
    constitution_digest,
)
from app.simulation.decisions import (
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
    bloc_relationship_investment_digest,
    budget_decision_digest,
    cabinet_decision_digest,
    constitutional_amendment_decision_digest,
)

# (Group 58) CONSTANTS ONLY, deliberately. `assess_legislative_bargain`, `asking_price_capital` and
# `will_deal` are NOT imported: this module transcribes those formulas itself
# (`_transcribed_bargain_price`, `_transcribed_bargain_will_deal`) so that the arithmetic is really
# performed twice. `tests/test_legislative_bargain.py` enforces this with an AST scan written as an
# allowlist, so a newly added helper in that module is refused here by default rather than needing
# to be added to a denylist.
# (Group 59) CONSTANTS ONLY, on the same footing as the bargaining import below:
# `assess_foreign_assistance`, `assistance_share_bps` and `remaining_pool` are NOT imported,
# because this module transcribes those formulas itself.
from app.simulation.foreign_assistance import (
    FOREIGN_ASSISTANCE_BASE_SHARE_BPS,
    FOREIGN_ASSISTANCE_INDEPENDENCE_PENALTY_MAX_BPS,
    FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS,
    FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS,
    FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS,
    MINIMUM_ASSISTANCE_STANDING_BPS,
)
from app.simulation.foreign_conflict import (
    MAX_CONCURRENT_CONFLICTS,
    MIN_ACTIVE_INTENSITY_BPS,
    MIN_OUTBREAK_WEIGHT_BPS,
    PROGRESS_JITTER_BPS,
    ConflictStatus,
    WarAim,
    apply_active_intensity_floor,
    average_exhaustion_bps,
    ceasefire_closing_intensity_bps,
    ceasefire_closing_status,
    ceasefire_decayed_intensity_bps,
    ceasefire_gate_open,
    ceasefire_recovered_exhaustion_bps,
    closing_position_bps,
    closing_readiness_bps,
    dyad_weight_bps,
    exhaustion_gain_bps,
    initial_intensity_bps,
    is_decisive,
    outbreak_occurs,
    outbreak_probability_bps,
    passes_pressure_floor,
    raw_closing_intensity_bps,
    select_candidate_index,
    settles_rather_than_pauses,
)
from app.simulation.government_survival import (
    ASSASSINATION_SEVERITY_THRESHOLD_BPS,
    MAX_POLLING_UNCERTAINTY_SWING_BPS,
    coup_attempt_risk_bps,
    coup_success_probability_bps,
    election_baseline_support_bps,
    impeachment_attempt_risk_bps,
    impeachment_success_probability_bps,
    is_competitive_elected_constitution,
    is_noncompetitive_constitution,
    legislative_support_bps,
    population_weighted_mean_bps,
    resolve_transition_pressure_bps,
    structural_removal_exposure_bps,
    transition_pressure_added_bps,
    unrest_attempt_risk_bps,
    unrest_success_probability_bps,
)
from app.simulation.legislative_bargaining import (
    LEGISLATIVE_BARGAIN_AMBITION_PRICE_MAX,
    LEGISLATIVE_BARGAIN_BASE_PRICE,
    LEGISLATIVE_BARGAIN_INDEPENDENCE_PRICE_MAX,
    LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS,
    LEGISLATIVE_BARGAIN_TRUST_DISCOUNT_MAX,
    LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS,
    LEGISLATIVE_ENDORSEMENT_BPS,
)
from app.simulation.legislative_voting import (
    CONSTITUTIONAL_AMENDMENT_DECREE_COST,
    required_amendment_yes_seats,
    resolve_amendment_support,
)
from app.simulation.legislature import (
    AmendmentThreshold,
    CapitalExpenditureCategory,
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.legitimacy import (
    aggregate_security_contribution_bps,
    foreign_conflict_security_anxiety_bps,
)
from app.simulation.report import (
    CabinetChange,
    ConstitutionalAmendmentReport,
    ForeignAffairsReport,
    ForeignAssistanceReport,
    GovernanceReport,
    LegislativeBargainOutcome,
    LegislativeBargainReport,
    MovementReport,
    TurnReport,
    TurnReportEntry,
)
from app.simulation.state import (
    LEGISLATIVE_PROPOSAL_DISPLAY_NAMES,
    CabinetPost,
    FormationBranch,
    FormationState,
    GameState,
    LegislatureState,
    OutcomeBucket,
    PendingLiberalizationState,
    PoliticalState,
    RemovalReason,
    SpendingCategory,
    VictoryReason,
    leader_of_foreign_profile,
)

_COUP_UNREST_OWNED_REMOVAL_REASONS = frozenset(
    {
        RemovalReason.COUP,
        RemovalReason.FORCED_ABDICATION,
        RemovalReason.ASSASSINATION,
        RemovalReason.IMPEACHMENT,
    }
)
"""The only four `RemovalReason` values slot 12 (coup/unrest/impeachment) can ever produce --
`ELECTORAL_DEFEAT`/`TERM_LIMIT_EXIT` come exclusively from slot 13 (election). Group 33 uses this
to tell a legitimate election-caused conclusion (which `coup_unrest.removal_triggered` correctly
leaves `None` for) apart from a fabricated `None` hiding a real coup/unrest/impeachment removal."""

_CONSTITUTION_FIELDS = (
    "executive_system",
    "executive_selection",
    "legislature",
    "territorial_organization",
    "judicial_review",
    "amendment_difficulty",
    "decree_authority",
    "executive_term_limit_terms",
    "national_election_interval_turns",
)

_AMENDABLE_CONSTITUTION_AXES = (
    "decree_authority",
    "executive_selection",
    "executive_system",
    "executive_term_limit_terms",
    "national_election_interval_turns",
)
_NEVER_AMENDABLE_CONSTITUTION_AXES = (
    "territorial_organization",
    "judicial_review",
    "amendment_difficulty",
)

_TAX_RATE_FIELDS = ("personal_income_rate_bps", "corporate_rate_bps", "consumption_rate_bps")
"""The three targetable `TaxPolicyState` fields — deliberately excludes `compliance_rate_bps`,
which no `BudgetDecision` can ever target (group 16)."""

_StructuralRow = tuple[str, int, int, int, int]
"""(`government_role.value`, `discipline_bps`, `tax_preference_bps`, `spending_preference_bps`,
`seats`) for one `(party_id, bloc_id, chamber)` — everything group 12/14/15 require EXCEPT
relationship. Relationship is handled separately (R12): group 12's slow path allows it to differ
between the two states only for a bloc the report names; group 14 compares a vote row's copy
against the OPENING state alone (the value the vote was actually scored against)."""


def _structural_rows(
    legislature: LegislatureState,
) -> dict[tuple[str, str, LegislativeChamber], _StructuralRow]:
    """Every row `(party_id, bloc_id, chamber)` a bloc actually holds seats in, mirroring
    `LegislativeBlocState.seats`'s own "omit what you don't hold" convention. Used both for group
    12's direct state-to-state staticness proof and for groups 14/15's report-to-state proof."""
    rows: dict[tuple[str, str, LegislativeChamber], _StructuralRow] = {}
    for party in legislature.parties:
        for bloc in party.blocs:
            for seat_entry in bloc.seats:
                rows[(party.id, bloc.id, seat_entry.chamber)] = (
                    party.government_role.value,
                    bloc.discipline_bps,
                    bloc.tax_preference_bps,
                    bloc.spending_preference_bps,
                    seat_entry.seats,
                )
    return rows


def _opposition_seat_share_bps(legislature: LegislatureState | None) -> int | None:
    """Mirrors `phases._opposition_seat_share_bps` exactly (this module deliberately never
    imports `phases.py` -- see groups 35-40's own `legislative_support_bps` recompute for the
    same "independently re-derive, never call the phase handler" discipline): the share of
    LOWER-chamber seats held by OPPOSITION-role parties alone. `None` when no legislature
    exists."""
    if legislature is None:
        return None
    lower_chamber = next(
        chamber_state
        for chamber_state in legislature.chambers
        if chamber_state.chamber == LegislativeChamber.LOWER
    )
    opposition_seats = sum(
        seat_entry.seats
        for party in legislature.parties
        if party.government_role == GovernmentRole.OPPOSITION
        for bloc in party.blocs
        for seat_entry in bloc.seats
        if seat_entry.chamber == LegislativeChamber.LOWER
    )
    return trunc_div_toward_zero(opposition_seats * BPS_DENOMINATOR, lower_chamber.total_seats)


def _amendment_value_text(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def _reported_amendment_is_enacted(value: object) -> bool:
    return isinstance(value, ConstitutionalAmendmentReport) and value.outcome in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    )


def _expected_amendment_vote(
    opening_politics: PoliticalState,
    decision: ConstitutionalAmendmentDecision,
    endorsed_party_id: str | None = None,
) -> tuple[tuple[dict[str, object], ...], LegislativeOutcome, tuple[str, ...]]:
    if decision.route is ProposalRoute.DECREE:
        if (
            opening_politics.constitution.legislature is not Legislature.NONE
            or opening_politics.legislature is not None
            or opening_politics.constitution.decree_authority is not DecreeAuthority.UNLIMITED
        ):
            return (
                (),
                LegislativeOutcome.NO_PROPOSAL,
                (
                    "group 43 amendment route=decree is illegal for the opening constitution "
                    "or legislature state",
                ),
            )
        return (), LegislativeOutcome.ENACTED_BY_DECREE, ()
    legislature = opening_politics.legislature
    if opening_politics.constitution.legislature is Legislature.NONE or legislature is None:
        return (
            (),
            LegislativeOutcome.NO_PROPOSAL,
            ("group 43 amendment route=legislative requires an opening legislature",),
        )
    blocs_by_key = {
        (party.id, bloc.id): bloc for party in legislature.parties for bloc in party.blocs
    }
    influence_problems: list[str] = []
    for allocation in decision.influence:
        bloc = blocs_by_key.get((allocation.party_id, allocation.bloc_id))
        if bloc is None:
            influence_problems.append(
                "group 43 amendment influence targets unknown opening-legislature identity "
                f"({allocation.party_id!r}, {allocation.bloc_id!r})"
            )
        elif sum(row.seats for row in bloc.seats) == 0:
            influence_problems.append(
                "group 43 amendment influence targets zero-seat opening-legislature bloc "
                f"({allocation.party_id!r}, {allocation.bloc_id!r})"
            )
    if influence_problems:
        return (), LegislativeOutcome.NO_PROPOSAL, tuple(influence_problems)
    allocations = {(row.party_id, row.bloc_id): row.political_capital for row in decision.influence}
    threshold = AmendmentThreshold(opening_politics.constitution.amendment_difficulty.value)
    expected: list[dict[str, object]] = []
    for chamber_state in legislature.chambers:
        support_rows: list[SeatSupport] = []
        for party in legislature.parties:
            for bloc in party.blocs:
                seats = next(
                    (row.seats for row in bloc.seats if row.chamber is chamber_state.chamber),
                    0,
                )
                if seats == 0:
                    continue
                support = resolve_amendment_support(
                    role=party.government_role,
                    relationship_bps=bloc.government_relationship_bps,
                    discipline_bps=bloc.discipline_bps,
                    allocated_political_capital=allocations.get((party.id, bloc.id), 0),
                    endorsement_bps=(
                        LEGISLATIVE_ENDORSEMENT_BPS if party.id == endorsed_party_id else 0
                    ),
                )
                support_rows.append(
                    SeatSupport(
                        party_id=party.id,
                        bloc_id=bloc.id,
                        seats=seats,
                        effective_support_bps=support.effective_support_bps,
                    )
                )
        apportioned = apportion_supporting_seats(rows=tuple(support_rows))
        required = required_amendment_yes_seats(
            total_seats=chamber_state.total_seats, difficulty=threshold
        )
        passed = apportioned.supporting_seats >= required
        expected.append(
            {
                "chamber": chamber_state.chamber,
                "total_seats": chamber_state.total_seats,
                "supporting_seats": apportioned.supporting_seats,
                "required_yes_seats": required,
                "shortfall_seats": max(0, required - apportioned.supporting_seats),
                "target_total": apportioned.supporting_seats,
                "extras_awarded": apportioned.supporting_seats
                - sum(row.base for row in apportioned.rows),
                "passed": passed,
            }
        )
    outcome = (
        LegislativeOutcome.PASSED_LEGISLATIVE
        if all(bool(row["passed"]) for row in expected)
        else LegislativeOutcome.FAILED_LEGISLATIVE
    )
    return tuple(expected), outcome, ()


def _pending_after_amendment(
    *,
    opening_politics: PoliticalState,
    closing_politics: PoliticalState,
    closing_turn: int,
    amendment_decision: ConstitutionalAmendmentDecision | None,
    amendment_enacted: bool,
) -> PendingLiberalizationState | None:
    expected_pending = opening_politics.pending_liberalization
    if amendment_decision is not None and amendment_enacted:
        qualifies = is_noncompetitive_constitution(
            executive_selection=opening_politics.constitution.executive_selection,
            decree_authority=opening_politics.constitution.decree_authority,
        ) and is_competitive_elected_constitution(
            executive_selection=closing_politics.constitution.executive_selection,
            decree_authority=closing_politics.constitution.decree_authority,
            national_election_interval_turns=(
                closing_politics.constitution.national_election_interval_turns
            ),
        )
        if qualifies:
            return PendingLiberalizationState(
                set_at_turn=closing_turn,
                opening_constitution_digest=constitution_digest(opening_politics.constitution),
                closing_constitution_digest=constitution_digest(closing_politics.constitution),
            )
        if not is_competitive_elected_constitution(
            executive_selection=closing_politics.constitution.executive_selection,
            decree_authority=closing_politics.constitution.decree_authority,
            national_election_interval_turns=(
                closing_politics.constitution.national_election_interval_turns
            ),
        ):
            return None
    return expected_pending


def reconcile_political_legislative_and_survival_report(
    *,
    opening_state: GameState,
    closing_state: GameState,
    report: TurnReport,
    decisions: DecisionSet | None,
) -> list[str]:
    """Return every disagreement between what `report` claims and what `opening_state`/
    `closing_state`/`decisions` actually hold. Never raises; exact equality only, no formulas of
    its own beyond group 16's per-field targeting logic (which mirrors `BudgetDecision`'s own
    "targets, not deltas" semantics, not a voting/apportionment formula) — every report's own
    self-validators already proved its internal arithmetic is correct; this proves the report
    describes the REAL command and the REAL state, not merely a self-consistent one.

    `decisions` is `None` only when a caller (history replay) could not parse a stored
    `decisions_json` into a real `DecisionSet` at all — that failure is recorded as its own
    problem by the caller, so groups 16 and 18 (the two groups that need the real decision) are
    skipped here rather than raising on a `None` they cannot do anything useful with. Groups 1–15
    and 17 do not need `decisions` and always run.

    `report.political is None` (the political phase did not run) produces no problems here — that
    case is rejected earlier, by `TurnReport`'s own all-present-or-all-absent rule together with
    `simulation.invariants.check_invariants` requiring player politics. The same holds for
    `report.legislative is None`.
    """
    political = report.political
    if political is None:
        return []

    problems: list[str] = []

    opening_player = opening_state.world.countries[opening_state.world.player_country_id]
    closing_player = closing_state.world.countries[closing_state.world.player_country_id]
    opening_politics = opening_player.politics
    closing_politics = closing_player.politics
    if opening_politics is None or closing_politics is None:
        problems.append(
            "political report is present but the opening or closing state has no "
            "PoliticalState for the player"
        )
        return problems

    # Group 1: opening_legitimacy_bps vs opening state.
    if political.opening_legitimacy_bps != opening_politics.legitimacy_bps:
        problems.append(
            f"political.opening_legitimacy_bps={political.opening_legitimacy_bps} does not "
            f"match opening_state politics.legitimacy_bps={opening_politics.legitimacy_bps}"
        )

    # Group 2: opening_political_capital vs opening state.
    if political.opening_political_capital != opening_politics.political_capital:
        problems.append(
            f"political.opening_political_capital={political.opening_political_capital} does "
            "not match opening_state politics.political_capital="
            f"{opening_politics.political_capital}"
        )

    # Group 3: opening_economic_baseline vs opening state (both None, or all three fields equal).
    report_opening_baseline = political.opening_economic_baseline
    state_opening_baseline = opening_politics.economic_baseline
    if (report_opening_baseline is None) != (state_opening_baseline is None):
        problems.append(
            "political.opening_economic_baseline presence does not match opening_state "
            f"politics.economic_baseline presence (report={report_opening_baseline is not None}, "
            f"state={state_opening_baseline is not None})"
        )
    elif report_opening_baseline is not None and state_opening_baseline is not None:
        if report_opening_baseline.source_turn != state_opening_baseline.source_turn:
            problems.append(
                "political.opening_economic_baseline.source_turn="
                f"{report_opening_baseline.source_turn} does not match opening_state "
                f"politics.economic_baseline.source_turn={state_opening_baseline.source_turn}"
            )
        if report_opening_baseline.total_gross_output != state_opening_baseline.total_gross_output:
            problems.append(
                "political.opening_economic_baseline.total_gross_output="
                f"{report_opening_baseline.total_gross_output} does not match opening_state "
                "politics.economic_baseline.total_gross_output="
                f"{state_opening_baseline.total_gross_output}"
            )
        if (
            report_opening_baseline.unemployment_rate_bps
            != state_opening_baseline.unemployment_rate_bps
        ):
            problems.append(
                "political.opening_economic_baseline.unemployment_rate_bps="
                f"{report_opening_baseline.unemployment_rate_bps} does not match opening_state "
                "politics.economic_baseline.unemployment_rate_bps="
                f"{state_opening_baseline.unemployment_rate_bps}"
            )

    # Group 4: closing_legitimacy_bps vs closing state.
    if political.closing_legitimacy_bps != closing_politics.legitimacy_bps:
        problems.append(
            f"political.closing_legitimacy_bps={political.closing_legitimacy_bps} does not "
            f"match closing_state politics.legitimacy_bps={closing_politics.legitimacy_bps}"
        )

    # Group 5: closing_political_capital vs closing state.
    if political.closing_political_capital != closing_politics.political_capital:
        problems.append(
            f"political.closing_political_capital={political.closing_political_capital} does "
            "not match closing_state politics.political_capital="
            f"{closing_politics.political_capital}"
        )

    # Group 6: closing_economic_baseline vs closing state (never None on either side).
    state_closing_baseline = closing_politics.economic_baseline
    if state_closing_baseline is None:
        problems.append(
            "political.closing_economic_baseline is present but closing_state "
            "politics.economic_baseline is None"
        )
    else:
        if political.closing_economic_baseline.source_turn != state_closing_baseline.source_turn:
            problems.append(
                "political.closing_economic_baseline.source_turn="
                f"{political.closing_economic_baseline.source_turn} does not match closing_state "
                f"politics.economic_baseline.source_turn={state_closing_baseline.source_turn}"
            )
        if (
            political.closing_economic_baseline.total_gross_output
            != state_closing_baseline.total_gross_output
        ):
            problems.append(
                "political.closing_economic_baseline.total_gross_output="
                f"{political.closing_economic_baseline.total_gross_output} does not match "
                "closing_state politics.economic_baseline.total_gross_output="
                f"{state_closing_baseline.total_gross_output}"
            )
        if (
            political.closing_economic_baseline.unemployment_rate_bps
            != state_closing_baseline.unemployment_rate_bps
        ):
            problems.append(
                "political.closing_economic_baseline.unemployment_rate_bps="
                f"{political.closing_economic_baseline.unemployment_rate_bps} does not match "
                "closing_state politics.economic_baseline.unemployment_rate_bps="
                f"{state_closing_baseline.unemployment_rate_bps}"
            )

    # Groups 7-9: PoliticalReport is assembled after slot 2, so its constitution is the closing
    # constitution. Commit 22's group 44 owns state-to-state five-axis staticness/provenance.
    for field_name in _CONSTITUTION_FIELDS:
        report_value = getattr(political.constitution, field_name)
        closing_value = getattr(closing_politics.constitution, field_name)
        if report_value != closing_value:
            problems.append(
                f"political.constitution.{field_name}={report_value!r} does not match "
                f"closing_state constitution.{field_name}={closing_value!r}"
            )

    # Group 9: digest vs the same closing constitution.
    expected_closing_digest = constitution_digest(closing_politics.constitution)
    if political.constitution.constitution_digest != expected_closing_digest:
        problems.append(
            "political.constitution.constitution_digest="
            f"{political.constitution.constitution_digest!r} does not match "
            f"constitution_digest(closing_state.constitution)={expected_closing_digest!r}"
        )

    # Group 10 (R1): constitutional_order_support_bps vs opening and closing -- 3A never mutates
    # authored order support.
    if (
        political.constitutional_order_support_bps
        != opening_politics.constitutional_order_support_bps
    ):
        problems.append(
            "political.constitutional_order_support_bps="
            f"{political.constitutional_order_support_bps} does not match opening_state "
            "politics.constitutional_order_support_bps="
            f"{opening_politics.constitutional_order_support_bps}"
        )
    if (
        political.constitutional_order_support_bps
        != closing_politics.constitutional_order_support_bps
    ):
        problems.append(
            "political.constitutional_order_support_bps="
            f"{political.constitutional_order_support_bps} does not match closing_state "
            "politics.constitutional_order_support_bps="
            f"{closing_politics.constitutional_order_support_bps}"
        )

    # Group 11 (R7): political_capital_capacity vs opening and closing -- nothing changes
    # capacity in 3A.
    if political.political_capital_capacity != opening_politics.political_capital_capacity:
        problems.append(
            f"political.political_capital_capacity={political.political_capital_capacity} does "
            "not match opening_state politics.political_capital_capacity="
            f"{opening_politics.political_capital_capacity}"
        )
    if political.political_capital_capacity != closing_politics.political_capital_capacity:
        problems.append(
            f"political.political_capital_capacity={political.political_capital_capacity} does "
            "not match closing_state politics.political_capital_capacity="
            f"{closing_politics.political_capital_capacity}"
        )

    # -------------------------------------------------------------------------------------------
    # Phase 3B1 (R8): legislative reconciliation, groups 12-18.
    # -------------------------------------------------------------------------------------------
    legislative = report.legislative
    if legislative is None:
        return problems

    opening_legislature = opening_politics.legislature
    closing_legislature = closing_politics.legislature

    # Group 12 (Phase 3B2A, R12 REWRITE): legislature presence (report vs BOTH states), and
    # staticness -- now field-by-field rather than one whole-model `==`. The whole-model equality
    # is retained as a FAST PATH ONLY: every turn with no relationship change still takes the O(1)
    # `==` this replay loop needs, but the moment a legitimate relationship change is present, this
    # group no longer silently disables groups 13-15 the way whole-model inequality used to (that
    # was found to be a real defect, not a hypothetical one: it would have made a corrupted chamber
    # or seat count on exactly an investment turn undetectable). D7 static fields are still proved
    # exactly as strictly as before; only `government_relationship_bps` is now a genuinely mutable
    # field, and its own staticness-or-change is group 20's job, never this group's.
    if legislative.legislature_present != (opening_legislature is not None):
        problems.append(
            f"legislative.legislature_present={legislative.legislature_present} does not match "
            f"opening_state politics.legislature presence ({opening_legislature is not None})"
        )
    if legislative.legislature_present != (closing_legislature is not None):
        problems.append(
            f"legislative.legislature_present={legislative.legislature_present} does not match "
            f"closing_state politics.legislature presence ({closing_legislature is not None})"
        )

    # Group 12, continued (R12): structural staticness proved STATE TO STATE, directly --
    # independent of whether `legislative.chambers`/`legislative.blocs` happen to carry any rows.
    # This is the check that actually proves D7 (composition is static except relationship) on
    # EVERY turn a legislature exists, including a NO_PROPOSAL or ENACTED_BY_DECREE turn whose
    # report carries ZERO chamber/bloc rows by construction -- exactly the turns groups 13-15
    # below cannot see, because those groups compare the REPORT against state and there is no
    # report row to compare when no vote happened. Without this block, an investment made on a
    # turn with no legislative proposal would leave chamber/bloc/seat corruption completely
    # unchecked -- the same class of coverage hole R12 closed for report-bearing turns.
    political_capital_report = report.political_capital
    political_relationship_report = report.political_relationship
    if opening_legislature is not None and closing_legislature is not None:
        has_relationship_changes = bool(
            political_relationship_report is not None and political_relationship_report.blocs
        )
        if not has_relationship_changes:
            # Fast path: a turn with no reported relationship change must leave the legislature
            # byte-identical -- the O(1) whole-model `==` this replay loop needs on its common case.
            if opening_legislature != closing_legislature:
                problems.append(
                    "politics.legislature differs between opening_state and closing_state, but "
                    "no relationship change was reported to explain it"
                )
        else:
            # Slow path: every field except `government_relationship_bps` must be identical
            # between the two states; relationship handling is group 20's job, not this block's.
            opening_chamber_seats = {c.chamber: c.total_seats for c in opening_legislature.chambers}
            closing_chamber_seats = {c.chamber: c.total_seats for c in closing_legislature.chambers}
            if opening_chamber_seats != closing_chamber_seats:
                problems.append(
                    "politics.legislature chambers changed between opening_state "
                    f"({opening_chamber_seats}) and closing_state ({closing_chamber_seats})"
                )
            state_opening_rows = _structural_rows(opening_legislature)
            state_closing_rows = _structural_rows(closing_legislature)
            if set(state_opening_rows) != set(state_closing_rows):
                problems.append(
                    "politics.legislature party/bloc/chamber composition changed between "
                    "opening_state and closing_state"
                )
            for structural_key in set(state_opening_rows) & set(state_closing_rows):
                if state_opening_rows[structural_key] != state_closing_rows[structural_key]:
                    problems.append(
                        f"politics.legislature row {structural_key!r} changed a non-relationship "
                        f"field between opening_state {state_opening_rows[structural_key]} and "
                        f"closing_state {state_closing_rows[structural_key]}"
                    )

            # (Phase 3B2B) `baseline_government_relationship_bps` is authored, not a running
            # total -- unlike `government_relationship_bps` (group 20's job), it must NEVER move,
            # on ANY turn, whether or not that turn carries a reported relationship change. Keyed
            # by (party_id, bloc_id) alone, not chamber, since a bloc's baseline is a single fact
            # regardless of how many chambers it sits in.
            opening_baselines = {
                (party.id, bloc.id): bloc.baseline_government_relationship_bps
                for party in opening_legislature.parties
                for bloc in party.blocs
            }
            closing_baselines = {
                (party.id, bloc.id): bloc.baseline_government_relationship_bps
                for party in closing_legislature.parties
                for bloc in party.blocs
            }
            for bloc_key in set(opening_baselines) & set(closing_baselines):
                if opening_baselines[bloc_key] != closing_baselines[bloc_key]:
                    problems.append(
                        f"politics.legislature bloc {bloc_key!r}: "
                        f"baseline_government_relationship_bps changed from "
                        f"{opening_baselines[bloc_key]} to {closing_baselines[bloc_key]} -- the "
                        "authored baseline must never move"
                    )

    # Groups 13-15 need REPORT chamber/bloc rows to compare against state; NOTE (R12): unlike
    # Phase 3B1, this is no longer additionally gated on `opening_legislature == closing_legislature`
    # -- dropping that condition is part of the fix, and the state-to-state block just above closes
    # the remaining gap on turns whose report carries no rows at all.
    if legislative.chambers and opening_legislature is not None:
        opening_chambers_by_id = {
            chamber.chamber: chamber for chamber in opening_legislature.chambers
        }
        closing_chambers_by_id = (
            {chamber.chamber: chamber for chamber in closing_legislature.chambers}
            if closing_legislature is not None
            else {}
        )

        # Group 13: chamber identity, matched by `chamber`, never tuple position -- against BOTH
        # states independently, so a corruption on either side is caught even when the other is
        # fine.
        report_chamber_ids = [row.chamber for row in legislative.chambers]
        if len(report_chamber_ids) != len(set(report_chamber_ids)):
            problems.append("legislative.chambers contains a duplicate chamber identity")
        for state_label, chambers_by_id in (
            ("opening_state", opening_chambers_by_id),
            ("closing_state", closing_chambers_by_id),
        ):
            state_chamber_ids = set(chambers_by_id)
            for missing_chamber in sorted(state_chamber_ids - set(report_chamber_ids)):
                problems.append(
                    f"legislative.chambers is missing a row for chamber "
                    f"{missing_chamber.value!r}, which {state_label} legislature has"
                )
            for invented_chamber in sorted(set(report_chamber_ids) - state_chamber_ids):
                problems.append(
                    f"legislative.chambers reports a row for chamber {invented_chamber.value!r}, "
                    f"which {state_label} legislature does not have"
                )
            for chamber_row in legislative.chambers:
                state_chamber = chambers_by_id.get(chamber_row.chamber)
                if state_chamber is None:
                    continue  # already reported above as "invented" (or absent this state)
                if chamber_row.total_seats != state_chamber.total_seats:
                    problems.append(
                        f"legislative chamber {chamber_row.chamber.value!r}: total_seats="
                        f"{chamber_row.total_seats} does not match {state_label} total_seats="
                        f"{state_chamber.total_seats}"
                    )

        # Groups 14/15: party/bloc identity + structural fields + seats, matched by (party_id,
        # bloc_id, chamber) -- never row position. `_structural_rows` (module-level, shared with
        # group 12's state-to-state block above) only contains chambers a bloc actually holds
        # seats in (mirroring `LegislativeBlocState.seats`'s own "omit what you don't hold"
        # convention and slot 1's identical row-inclusion rule), so no legitimately-zero-seat
        # pairing is ever flagged as "missing".
        opening_structural_rows = _structural_rows(opening_legislature)
        closing_structural_rows = (
            _structural_rows(closing_legislature) if closing_legislature is not None else {}
        )
        opening_relationship_by_key = {
            (party.id, bloc.id): bloc.government_relationship_bps
            for party in opening_legislature.parties
            for bloc in party.blocs
        }

        report_row_keys = [(row.party_id, row.bloc_id, row.chamber) for row in legislative.blocs]
        if len(report_row_keys) != len(set(report_row_keys)):
            problems.append(
                "legislative.blocs contains a duplicate (party_id, bloc_id, chamber) row"
            )

        structural_field_names = (
            "government_role",
            "discipline_bps",
            "tax_preference_bps",
            "spending_preference_bps",
            "seats",
        )

        for row in legislative.blocs:
            key = (row.party_id, row.bloc_id, row.chamber)
            row_values = (
                row.government_role.value,
                row.discipline_bps,
                row.tax_preference_bps,
                row.spending_preference_bps,
                row.seats,
            )
            for state_label, structural_rows in (
                ("opening_state", opening_structural_rows),
                ("closing_state", closing_structural_rows),
            ):
                state_row = structural_rows.get(key)
                if state_row is None:
                    if structural_rows is closing_structural_rows and closing_legislature is None:
                        continue  # already reported as a presence mismatch above
                    problems.append(
                        f"legislative.blocs reports a row for ({row.party_id!r}, "
                        f"{row.bloc_id!r}) in chamber {row.chamber.value!r}, which "
                        f"{state_label} legislature does not seat there"
                    )
                    continue
                for field_name, reported_value, state_value in zip(
                    structural_field_names, row_values, state_row, strict=True
                ):
                    if reported_value != state_value:
                        problems.append(
                            f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                            f"{row.chamber.value!r}): {field_name}={reported_value!r} does not "
                            f"match {state_label} {field_name}={state_value!r}"
                        )

            # Group 14's namesake concern (R12): the vote row's relationship must equal the
            # OPENING relationship -- the value the vote was actually scored against at slot 1.
            # Comparing against the CLOSING relationship instead would make a retroactively
            # rescored vote (one whose report was built as if it already knew this turn's
            # improved relationship) undetectable; pinning to opening closes exactly that.
            opening_relationship = opening_relationship_by_key.get((row.party_id, row.bloc_id))
            if opening_relationship is not None and row.government_relationship_bps != (
                opening_relationship
            ):
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): government_relationship_bps="
                    f"{row.government_relationship_bps} does not match opening_state "
                    f"government_relationship_bps={opening_relationship} (the vote must be "
                    "scored against the OPENING relationship, never the closing one)"
                )

        for missing_party_id, missing_bloc_id, missing_chamber in sorted(
            set(opening_structural_rows) - set(report_row_keys),
            key=lambda k: (k[0], k[1], k[2].value),
        ):
            problems.append(
                f"legislative.blocs is missing a row for ({missing_party_id!r}, "
                f"{missing_bloc_id!r}) in chamber {missing_chamber.value!r}, which opening_state "
                "legislature seats there"
            )

    # Group 16: budget gating, against the ACTUAL submitted decision, never report prose.
    opening_finance = opening_player.finance
    closing_finance = closing_player.finance
    # (Phase 3B2A) Located by KIND, never by position: under the decision union a relationship
    # investment sorts ahead of the budget, so `decisions[0]` would have compared the closing
    # policy against a decision that never mentioned policy at all.
    decision = decisions.budget_decision() if decisions is not None else None
    if decisions is not None:
        if opening_finance is None or closing_finance is None:
            problems.append(
                "legislative report is present but the opening or closing state has no "
                "GovernmentFinanceState for the player"
            )
        else:
            applies = legislative.outcome in (
                LegislativeOutcome.PASSED_LEGISLATIVE,
                LegislativeOutcome.ENACTED_BY_DECREE,
            )
            for field_name in _TAX_RATE_FIELDS:
                target = getattr(decision, field_name) if decision is not None else None
                expected = (
                    target
                    if (target is not None and applies)
                    else getattr(opening_finance.tax_policy, field_name)
                )
                actual = getattr(closing_finance.tax_policy, field_name)
                if actual != expected:
                    problems.append(
                        f"finance.tax_policy.{field_name}={actual} does not match the expected "
                        f"closing value ({expected}) given the submitted decision and "
                        f"outcome={legislative.outcome.value!r}"
                    )
            if closing_finance.tax_policy.compliance_rate_bps != (
                opening_finance.tax_policy.compliance_rate_bps
            ):
                problems.append(
                    "finance.tax_policy.compliance_rate_bps changed, but no BudgetDecision can "
                    "ever target it"
                )

            decision_spending = (
                {update.category: update.amount for update in decision.spending_updates}
                if decision is not None
                else {}
            )
            for category in SpendingCategory:
                target = decision_spending.get(category)
                expected = (
                    target
                    if (target is not None and applies)
                    else opening_finance.spending_plan.get(category)
                )
                actual = closing_finance.spending_plan.get(category)
                if actual != expected:
                    problems.append(
                        f"finance.spending_plan.{category.value}={actual} does not match the "
                        f"expected closing value ({expected}) given the submitted decision and "
                        f"outcome={legislative.outcome.value!r}"
                    )

    # Group 17 (Phase 3B2A, GENERALIZED): political-capital ordering, against the LEDGER total --
    # never the legislative-only commitment, which is now only one of the ledger's sinks. Where
    # this used to duplicate `TurnReport`'s own legislative-vs-political cross-check, it now
    # duplicates the ledger-vs-political one instead -- the report-internal identity moved (§7.2),
    # so this comparison against the REAL state moves with it. (`political_capital_report` was
    # already bound above, at group 12, so group 20/21 below can also use it.)
    if legislative.opening_political_capital != opening_politics.political_capital:
        problems.append(
            f"legislative.opening_political_capital={legislative.opening_political_capital} does "
            f"not match opening_state politics.political_capital="
            f"{opening_politics.political_capital}"
        )
    if legislative.political_capital_committed > legislative.opening_political_capital:
        problems.append(
            f"legislative.political_capital_committed={legislative.political_capital_committed} "
            f"exceeds legislative.opening_political_capital="
            f"{legislative.opening_political_capital}"
        )
    if political_capital_report is not None:
        total_committed = political_capital_report.total_committed
        if total_committed != political.political_capital_spent:
            problems.append(
                f"political_capital.total_committed={total_committed} does not match "
                f"political.political_capital_spent={political.political_capital_spent}"
            )
        # Approved clamp order, unchanged: closing = min(capacity, opening - committed + regen).
        # CORRECTED to the ledger TOTAL: using `legislative.political_capital_committed` alone
        # (the Phase 3B1 formula) would under-count on any turn with a relationship investment.
        expected_closing_capital = min(
            political.political_capital_capacity,
            legislative.opening_political_capital
            - total_committed
            + political.political_capital_regeneration,
        )
        if closing_politics.political_capital != expected_closing_capital:
            problems.append(
                f"closing_state politics.political_capital={closing_politics.political_capital} "
                "does not match min(capacity, opening - total_committed + regeneration)="
                f"{expected_closing_capital}"
            )

    # Group 19 (Phase 3B2A): the capital ledger vs BOTH states.
    if political_capital_report is not None:
        if political_capital_report.opening_political_capital != opening_politics.political_capital:
            problems.append(
                "political_capital.opening_political_capital="
                f"{political_capital_report.opening_political_capital} does not match "
                f"opening_state politics.political_capital={opening_politics.political_capital}"
            )
        if political_capital_report.closing_political_capital != closing_politics.political_capital:
            problems.append(
                "political_capital.closing_political_capital="
                f"{political_capital_report.closing_political_capital} does not match "
                f"closing_state politics.political_capital={closing_politics.political_capital}"
            )
        if (
            political_capital_report.total_committed
            > political_capital_report.opening_political_capital
        ):
            problems.append(
                f"political_capital.total_committed={political_capital_report.total_committed} "
                "exceeds political_capital.opening_political_capital="
                f"{political_capital_report.opening_political_capital}"
            )
        legislative_share = sum(
            row.political_capital
            for row in political_capital_report.expenditures
            if row.category
            in (CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE, CapitalExpenditureCategory.DECREE)
        )
        if legislative.political_capital_committed != legislative_share:
            problems.append(
                "legislative.political_capital_committed="
                f"{legislative.political_capital_committed} does not match the "
                f"LEGISLATIVE_INFLUENCE/DECREE share of political_capital.expenditures "
                f"({legislative_share})"
            )

    # Group 20 (Phase 3B2A, REWRITTEN Phase 3B2B): relationship memory vs BOTH states, and
    # untargeted immutability. This is where "did the closing relationship the report claims
    # actually land in state" (as opposed to group 14's "was the vote scored against the real
    # opening relationship") is proved -- the two groups are deliberately disjoint, one per
    # endpoint, never merged. Re-keyed from `political_capital_report.relationship_changes`
    # (removed, §8) onto `political_relationship_report.blocs`, and extended to also prove each
    # row's `baseline_relationship_bps` against BOTH states (group 12 already proves the baseline
    # never MOVES between the two states; this proves the row didn't lie about what it is).
    if political_relationship_report is not None and opening_legislature is not None:
        opening_relationship_by_key = {
            (party.id, bloc.id): bloc.government_relationship_bps
            for party in opening_legislature.parties
            for bloc in party.blocs
        }
        opening_baseline_by_key = {
            (party.id, bloc.id): bloc.baseline_government_relationship_bps
            for party in opening_legislature.parties
            for bloc in party.blocs
        }
        closing_relationship_by_key = (
            {
                (party.id, bloc.id): bloc.government_relationship_bps
                for party in closing_legislature.parties
                for bloc in party.blocs
            }
            if closing_legislature is not None
            else {}
        )
        closing_baseline_by_key = (
            {
                (party.id, bloc.id): bloc.baseline_government_relationship_bps
                for party in closing_legislature.parties
                for bloc in party.blocs
            }
            if closing_legislature is not None
            else {}
        )
        changed_keys = {
            (memory_row.party_id, memory_row.bloc_id)
            for memory_row in political_relationship_report.blocs
        }
        for memory_row in political_relationship_report.blocs:
            memory_key = (memory_row.party_id, memory_row.bloc_id)
            real_opening_baseline = opening_baseline_by_key.get(memory_key)
            if (
                real_opening_baseline is not None
                and memory_row.baseline_relationship_bps != real_opening_baseline
            ):
                problems.append(
                    f"political_relationship.blocs row {memory_key!r}: "
                    f"baseline_relationship_bps={memory_row.baseline_relationship_bps} does not match "
                    f"opening_state baseline_government_relationship_bps={real_opening_baseline}"
                )
            real_closing_baseline = closing_baseline_by_key.get(memory_key)
            if (
                real_closing_baseline is not None
                and memory_row.baseline_relationship_bps != real_closing_baseline
            ):
                problems.append(
                    f"political_relationship.blocs row {memory_key!r}: "
                    f"baseline_relationship_bps={memory_row.baseline_relationship_bps} does not match "
                    f"closing_state baseline_government_relationship_bps={real_closing_baseline}"
                )
            real_opening = opening_relationship_by_key.get(memory_key)
            if real_opening is not None and memory_row.opening_relationship_bps != real_opening:
                problems.append(
                    f"political_relationship.blocs row {memory_key!r}: opening_relationship_bps="
                    f"{memory_row.opening_relationship_bps} does not match opening_state "
                    f"government_relationship_bps={real_opening}"
                )
            real_closing = closing_relationship_by_key.get(memory_key)
            if real_closing is not None and memory_row.closing_relationship_bps != real_closing:
                problems.append(
                    f"political_relationship.blocs row {memory_key!r}: closing_relationship_bps="
                    f"{memory_row.closing_relationship_bps} does not match closing_state "
                    f"government_relationship_bps={real_closing}"
                )
        # Untargeted immutability: every bloc NOT named by a memory row must have an identical
        # relationship in both states -- this is the check a naive "just drop the group-12 guard"
        # fix could still miss, and it is asserted independently of group 12's own structural
        # comparison.
        for bloc_key, real_closing_value in closing_relationship_by_key.items():
            if bloc_key in changed_keys:
                continue
            real_opening_value = opening_relationship_by_key.get(bloc_key)
            if real_opening_value is not None and real_opening_value != real_closing_value:
                problems.append(
                    f"bloc {bloc_key!r} government_relationship_bps changed from "
                    f"{real_opening_value} to {real_closing_value} but is not named by any "
                    "political_relationship.blocs row"
                )

    # Group 21 (Phase 3B2A, NARROWED Phase 3B2B): relationship-investment decision provenance --
    # located from the REAL DecisionSet, never inferred, mirroring group 18's discipline exactly.
    # Reads investment capital from the LEDGER rows only (`political_capital.expenditures`); the
    # report-side correspondence between the ledger and `political_relationship.blocs` moved to
    # `TurnReport` cross-validator 1 (§8), so it is not re-proved here.
    if decisions is not None and political_capital_report is not None:
        investment_decision = decisions.relationship_investment_decision()
        decision_investments: dict[tuple[str, str], int] = (
            {
                (investment.party_id, investment.bloc_id): investment.political_capital
                for investment in investment_decision.investments
            }
            if investment_decision is not None
            else {}
        )
        report_investment_rows: dict[tuple[str, str], int] = {
            (expenditure_row.party_id, expenditure_row.bloc_id): expenditure_row.political_capital
            for expenditure_row in political_capital_report.expenditures
            if expenditure_row.category is CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT
            and expenditure_row.party_id is not None
            and expenditure_row.bloc_id is not None
        }
        for investment_key, decision_amount in decision_investments.items():
            if report_investment_rows.get(investment_key) != decision_amount:
                problems.append(
                    f"the submitted decision invests {decision_amount} in {investment_key!r}, "
                    "but political_capital.expenditures does not show that investment"
                )
        for investment_key, report_amount in report_investment_rows.items():
            if decision_investments.get(investment_key) != report_amount:
                problems.append(
                    f"political_capital.expenditures shows {report_amount} invested in "
                    f"{investment_key!r}, but the submitted decision does not commit that"
                )

        # Provenance digest: every BLOC_RELATIONSHIP_INVESTMENT row's `decision_digest` must equal
        # `bloc_relationship_investment_digest` of the REAL submitted decision -- mirroring group
        # 18's `budget_decision_digest` check exactly, so editing the stored decision and leaving
        # a stale digest on the report row is caught the same way a stale budget digest is.
        investment_expenditure_rows = [
            expenditure_row
            for expenditure_row in political_capital_report.expenditures
            if expenditure_row.category is CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT
        ]
        if investment_decision is not None:
            expected_investment_digest = bloc_relationship_investment_digest(investment_decision)
            for expenditure_row in investment_expenditure_rows:
                if expenditure_row.decision_digest != expected_investment_digest:
                    problems.append(
                        "political_capital.expenditures row "
                        f"({expenditure_row.party_id!r}, {expenditure_row.bloc_id!r}): "
                        f"decision_digest={expenditure_row.decision_digest!r} does not match "
                        "bloc_relationship_investment_digest(the submitted decision)="
                        f"{expected_investment_digest!r}"
                    )

    # Group 22 (Phase 3B2B, new): decay is based on the OPENING deviation from the authored
    # baseline -- re-derived here from `opening_state` alone, independently of row validator 2's
    # own re-derivation from the row's OWN stored `opening_deviation_bps`, so a row that lies about
    # its own opening/baseline pair (consistent with itself, per row validator 1) but disagrees
    # with the real state is still caught.
    if political_relationship_report is not None and opening_legislature is not None:
        opening_bloc_by_key = {
            (party.id, bloc.id): bloc
            for party in opening_legislature.parties
            for bloc in party.blocs
        }
        for memory_row in political_relationship_report.blocs:
            bloc = opening_bloc_by_key.get((memory_row.party_id, memory_row.bloc_id))
            if bloc is None:
                continue  # already reported by group 23(a) below
            deviation = bloc.government_relationship_bps - bloc.baseline_government_relationship_bps
            if deviation == 0:
                expected_decay = 0
            else:
                magnitude = trunc_div_toward_zero(
                    abs(deviation) * RELATIONSHIP_DECAY_NUMERATOR, RELATIONSHIP_DECAY_DENOMINATOR
                )
                magnitude = max(1, min(magnitude, abs(deviation)))
                expected_decay = -magnitude if deviation > 0 else magnitude
            if memory_row.decay_component_bps != expected_decay:
                problems.append(
                    f"political_relationship.blocs row ({memory_row.party_id!r}, {memory_row.bloc_id!r}): "
                    f"decay_component_bps={memory_row.decay_component_bps} does not match the decay "
                    f"formula over opening_state's own deviation ({expected_decay})"
                )

    # Group 23 (Phase 3B2B, new; R4/R5-expanded, absorbs the first draft's separate group 24):
    # three state-dependent facts `PoliticalRelationshipReport` cannot prove about itself.

    # (c) Legislature presence: checked FIRST and unconditionally on `opening_legislature`, since
    # the one case this exists to catch -- a fabricated `True` on a `Legislature.NONE` country --
    # is exactly the case where `opening_legislature is None`. Gating this on
    # `opening_legislature is not None` (as (a)/(b) legitimately do, since both need a bloc to
    # exist at all) would make the check unreachable in its own target scenario.
    if (
        political_relationship_report is not None
        and political_relationship_report.legislature_present != (opening_legislature is not None)
    ):
        problems.append(
            "political_relationship.legislature_present="
            f"{political_relationship_report.legislature_present} does not match "
            f"opening_state politics.legislature presence ({opening_legislature is not None})"
        )

    if political_relationship_report is not None and opening_legislature is not None:
        opening_bloc_by_key = {
            (party.id, bloc.id): bloc
            for party in opening_legislature.parties
            for bloc in party.blocs
        }
        report_keys = {
            (memory_row.party_id, memory_row.bloc_id)
            for memory_row in political_relationship_report.blocs
        }

        # (a) Row coverage: every bloc meeting §8's row-coverage rule has exactly one row, and no
        # row names a bloc absent from the opening state.
        investment_keys = (
            {
                (expenditure_row.party_id, expenditure_row.bloc_id)
                for expenditure_row in political_capital_report.expenditures
                if expenditure_row.category
                is CapitalExpenditureCategory.BLOC_RELATIONSHIP_INVESTMENT
            }
            if political_capital_report is not None
            else set()
        )
        policy_enacted = report.legislative is not None and report.legislative.outcome in (
            LegislativeOutcome.PASSED_LEGISLATIVE,
            LegislativeOutcome.ENACTED_BY_DECREE,
        )
        for bloc_key, bloc in opening_bloc_by_key.items():
            deviation = bloc.government_relationship_bps - bloc.baseline_government_relationship_bps
            needs_row = deviation != 0 or bloc_key in investment_keys or policy_enacted
            has_row = bloc_key in report_keys
            if needs_row and not has_row:
                problems.append(
                    f"political_relationship.blocs is missing a row for {bloc_key!r}, which "
                    "opening_state's own deviation/investment/enacted-policy facts require one for"
                )
            elif has_row and not needs_row:
                problems.append(
                    f"political_relationship.blocs carries a row for {bloc_key!r}, which none of "
                    "opening_state's deviation/investment/enacted-policy facts require one for"
                )
        for row_key in report_keys - set(opening_bloc_by_key):
            problems.append(
                f"political_relationship.blocs names {row_key!r}, which opening_state's "
                "legislature does not contain"
            )

        # (b) Preference correspondence: each row's stored preferences must equal that bloc's own
        # AUTHORED preferences in opening_state -- a row cannot fabricate a preference to
        # manufacture a policy reaction that didn't happen.
        for memory_row in political_relationship_report.blocs:
            bloc = opening_bloc_by_key.get((memory_row.party_id, memory_row.bloc_id))
            if bloc is None:
                continue  # already reported above
            if memory_row.tax_preference_bps != bloc.tax_preference_bps:
                problems.append(
                    f"political_relationship.blocs row ({memory_row.party_id!r}, {memory_row.bloc_id!r}): "
                    f"tax_preference_bps={memory_row.tax_preference_bps} does not match opening_state "
                    f"tax_preference_bps={bloc.tax_preference_bps}"
                )
            if memory_row.spending_preference_bps != bloc.spending_preference_bps:
                problems.append(
                    f"political_relationship.blocs row ({memory_row.party_id!r}, {memory_row.bloc_id!r}): "
                    f"spending_preference_bps={memory_row.spending_preference_bps} does not match "
                    f"opening_state spending_preference_bps={bloc.spending_preference_bps}"
                )

        # Group 56 (characters slice): the chief-of-staff competence each row used, re-derived
        # from the OPENING cabinet and character registry rather than read off the report.
        #
        # This is what makes a forged competence fail. The row's own validator re-derives the gain
        # formula from its stored fields, so raising `chief_of_staff_competence_bps` and raising
        # `investment_component_bps` to match leaves the row perfectly self-consistent -- and buys
        # a larger relationship improvement out of nothing. Only a comparison against the state can
        # catch that, and it must use the OPENING cabinet for the same reason group 14 pins the
        # vote's relationship to the opening value: an appointment made this turn is not effective
        # until the next one, so a row scored against a mid-turn cabinet would be scored against a
        # holder who was not yet doing the job.
        expected_competence = holder_competence_bps(
            cabinet=opening_player.cabinet,
            characters=opening_state.world.characters,
            post=CabinetPost.CHIEF_OF_STAFF,
            resolving_turn=opening_state.turn,
        )
        for memory_row in political_relationship_report.blocs:
            if memory_row.chief_of_staff_competence_bps != expected_competence:
                problems.append(
                    f"political_relationship.blocs row ({memory_row.party_id!r}, "
                    f"{memory_row.bloc_id!r}): "
                    f"chief_of_staff_competence_bps={memory_row.chief_of_staff_competence_bps} "
                    "does not match the competence of the chief of staff serving in opening_state "
                    f"({expected_competence}) (group 56)"
                )

    # Group 57 (characters slice): the cabinet's three records of one turn agree -- the submitted
    # `DecisionSet`, the closing state, and the report (both its `governance` subtree and its
    # `government` entries). Group 54 makes the identical claim for movement, in the same shape and
    # for the same reason: a change that the report, the API projection and the CLI could each
    # describe differently is a change nobody can audit.
    problems.extend(
        _reconcile_cabinet(
            opening_state=opening_state,
            closing_state=closing_state,
            report=report,
            decisions=decisions,
        )
    )

    # Group 58 (characters slice): the legislative bargain's records agree -- and unlike most
    # groups this one re-derives the gate and the price by TRANSCRIBING the formulas rather than
    # calling `simulation.legislative_bargaining`. A check that called the function which produced
    # the report could not fail when that function is wrong.
    problems.extend(
        _reconcile_legislative_bargain(
            opening_state=opening_state,
            closing_state=closing_state,
            report=report,
            decisions=decisions,
        )
    )

    # Group 45 (plan §8, Gate 3C1's slice of the coup/unrest backstop): terminal-outcome
    # non-retroactivity. `opening_state.politics.terminal_outcome` must be `None` on every turn
    # reconciliation is asked to check at all -- the redundant, independently-checkable backstop
    # for the guarantee `resolve_turn`'s own top-of-function refusal already promises (`errors.
    # GameAlreadyConcludedError`), so a save whose history layer bypasses that guard (a
    # hand-assembled entry, never produced by a real `resolve_turn` call) is still caught here.
    if opening_politics.terminal_outcome is not None:
        problems.append(
            "opening_state politics.terminal_outcome is already set "
            f"({opening_politics.terminal_outcome!r}); no further turn should ever have been "
            "resolved against this state"
        )

    # Groups 24-34 (plan §8, Gate 3C2): the coup/unrest/impeachment report against real state and
    # real seeded RNG -- never merely against the report's own self-validated story. Computed
    # BEFORE the election groups below, both numerically (24-34 precede 35-40) and because the
    # election groups need `coup_unrest_concluded` to know whether slot 13 legitimately
    # short-circuited this turn.
    coup_unrest = report.coup_unrest
    coup_unrest_concluded = coup_unrest is not None and coup_unrest.removal_triggered is not None
    if coup_unrest is not None:
        military = next(row for row in closing_player.institutions if row.id == "military")
        opposition_seat_share_bps = _opposition_seat_share_bps(closing_politics.legislature)

        # Group 24: coup attempt-risk recompute, from closing_state's military row, legislature
        # (opposition seat share), legitimacy, and the report's own closing_transition_pressure_bps
        # (group 34 separately proves THAT value is itself correct).
        for field_name, report_value, state_value in (
            ("military_loyalty_bps", coup_unrest.coup.military_loyalty_bps, military.loyalty),
            ("military_power_bps", coup_unrest.coup.military_power_bps, military.power),
            (
                "military_competence_bps",
                coup_unrest.coup.military_competence_bps,
                military.competence,
            ),
            (
                "legitimacy_bps",
                coup_unrest.coup.legitimacy_bps,
                closing_politics.legitimacy_bps,
            ),
        ):
            if report_value != state_value:
                problems.append(
                    f"coup_unrest.coup.{field_name}={report_value} does not match closing_state "
                    f"({state_value})"
                )
        # Derived from the closing state's CONSTITUTION, never from either report row. This is
        # what makes a forged structural figure fail: a tamperer who raises the exposure and
        # rescales the contribution to match keeps both report self-validators happy, and still
        # disagrees with the constitution the save actually stores.
        expected_exposure = structural_removal_exposure_bps(
            executive_selection=closing_politics.constitution.executive_selection,
            decree_authority=closing_politics.constitution.decree_authority,
            legislature=closing_politics.constitution.legislature,
            judicial_review=closing_politics.constitution.judicial_review,
            national_election_interval_turns=(
                closing_politics.constitution.national_election_interval_turns
            ),
        )
        for channel_name, reported_exposure in (
            ("coup", coup_unrest.coup.structural_exposure_bps),
            ("popular_unrest", coup_unrest.popular_unrest.structural_exposure_bps),
        ):
            if reported_exposure != expected_exposure.exposure_bps:
                problems.append(
                    f"coup_unrest.{channel_name}.structural_exposure_bps={reported_exposure} does "
                    "not match the exposure recomputed from closing_state's constitution "
                    f"({expected_exposure.exposure_bps})"
                )

        expected_coup_risk = coup_attempt_risk_bps(
            military_loyalty_bps=military.loyalty,
            military_power_bps=military.power,
            legitimacy_bps=closing_politics.legitimacy_bps,
            opposition_seat_share_bps=opposition_seat_share_bps,
            transition_pressure_bps=coup_unrest.closing_transition_pressure_bps,
            structural_exposure_bps=expected_exposure.exposure_bps,
        )
        for field_name, report_value, expected_value in (
            (
                "loyalty_contribution_bps",
                coup_unrest.coup.loyalty_contribution_bps,
                expected_coup_risk.loyalty_contribution_bps,
            ),
            (
                "legitimacy_contribution_bps",
                coup_unrest.coup.legitimacy_contribution_bps,
                expected_coup_risk.legitimacy_contribution_bps,
            ),
            (
                "opposition_contribution_bps",
                coup_unrest.coup.opposition_contribution_bps,
                expected_coup_risk.opposition_contribution_bps,
            ),
            (
                "transition_pressure_contribution_bps",
                coup_unrest.coup.transition_pressure_contribution_bps,
                expected_coup_risk.transition_pressure_contribution_bps,
            ),
            (
                "structural_contribution_bps",
                coup_unrest.coup.structural_contribution_bps,
                expected_coup_risk.structural_contribution_bps,
            ),
            (
                "attempt_risk_bps",
                coup_unrest.coup.attempt_risk_bps,
                expected_coup_risk.attempt_risk_bps,
            ),
        ):
            if report_value != expected_value:
                problems.append(
                    f"coup_unrest.coup.{field_name}={report_value} does not match the recomputed "
                    f"figure from closing_state ({expected_value})"
                )

        # Group 25: coup success-probability recompute, independent of the RNG draw.
        if coup_unrest.coup.attempted:
            expected_coup_success = coup_success_probability_bps(
                military_power_bps=military.power,
                military_competence_bps=military.competence,
                legitimacy_bps=closing_politics.legitimacy_bps,
            )
            if coup_unrest.coup.success_probability_bps != expected_coup_success:
                problems.append(
                    "coup_unrest.coup.success_probability_bps="
                    f"{coup_unrest.coup.success_probability_bps} does not match the recomputed "
                    f"figure ({expected_coup_success})"
                )

        # Group 26: coup RNG-draw recompute -- the SAME seeded streams slot 12 actually drew
        # from, redrawn independently.
        expected_coup_attempted = (
            derive_rng(opening_state.seed, opening_state.turn, "coup_attempt").randint(
                1, BPS_DENOMINATOR
            )
            <= expected_coup_risk.attempt_risk_bps
        )
        if coup_unrest.coup.attempted != expected_coup_attempted:
            problems.append(
                f"coup_unrest.coup.attempted={coup_unrest.coup.attempted} does not match the "
                f"redrawn derive_rng(seed, turn, 'coup_attempt') outcome ({expected_coup_attempted})"
            )
        elif coup_unrest.coup.attempted:
            expected_coup_succeeded = derive_rng(
                opening_state.seed, opening_state.turn, "coup_outcome"
            ).randint(1, BPS_DENOMINATOR) <= (coup_unrest.coup.success_probability_bps or 0)
            if coup_unrest.coup.succeeded != expected_coup_succeeded:
                problems.append(
                    f"coup_unrest.coup.succeeded={coup_unrest.coup.succeeded} does not match the "
                    "redrawn derive_rng(seed, turn, 'coup_outcome') outcome "
                    f"({expected_coup_succeeded})"
                )

        # Group 27: popular-unrest attempt-risk recompute, from closing_state's population groups.
        radicalization_bps = population_weighted_mean_bps(
            shares_and_metrics=tuple(
                (round(group.population_share * BPS_DENOMINATOR), group.radicalization)
                for group in closing_player.population_groups
            )
        )
        organization_bps = population_weighted_mean_bps(
            shares_and_metrics=tuple(
                (round(group.population_share * BPS_DENOMINATOR), group.organization)
                for group in closing_player.population_groups
            )
        )
        disapproval_bps = population_weighted_mean_bps(
            shares_and_metrics=tuple(
                (
                    round(group.population_share * BPS_DENOMINATOR),
                    BPS_DENOMINATOR - group.approval,
                )
                for group in closing_player.population_groups
            )
        )
        for field_name, report_value, state_value in (
            (
                "radicalization_bps",
                coup_unrest.popular_unrest.radicalization_bps,
                radicalization_bps,
            ),
            ("organization_bps", coup_unrest.popular_unrest.organization_bps, organization_bps),
            ("disapproval_bps", coup_unrest.popular_unrest.disapproval_bps, disapproval_bps),
            (
                "legitimacy_bps",
                coup_unrest.popular_unrest.legitimacy_bps,
                closing_politics.legitimacy_bps,
            ),
        ):
            if report_value != state_value:
                problems.append(
                    f"coup_unrest.popular_unrest.{field_name}={report_value} does not match "
                    f"closing_state ({state_value})"
                )
        expected_unrest_risk = unrest_attempt_risk_bps(
            radicalization_bps=radicalization_bps,
            organization_bps=organization_bps,
            disapproval_bps=disapproval_bps,
            structural_exposure_bps=expected_exposure.exposure_bps,
        )
        for field_name, report_value, expected_value in (
            (
                "radicalization_contribution_bps",
                coup_unrest.popular_unrest.radicalization_contribution_bps,
                expected_unrest_risk.radicalization_contribution_bps,
            ),
            (
                "disapproval_contribution_bps",
                coup_unrest.popular_unrest.disapproval_contribution_bps,
                expected_unrest_risk.disapproval_contribution_bps,
            ),
            (
                "structural_contribution_bps",
                coup_unrest.popular_unrest.structural_contribution_bps,
                expected_unrest_risk.structural_contribution_bps,
            ),
            (
                "attempt_risk_bps",
                coup_unrest.popular_unrest.attempt_risk_bps,
                expected_unrest_risk.attempt_risk_bps,
            ),
        ):
            if report_value != expected_value:
                problems.append(
                    f"coup_unrest.popular_unrest.{field_name}={report_value} does not match the "
                    f"recomputed figure from closing_state ({expected_value})"
                )

        # Group 28: popular-unrest success-probability recompute, independent of the RNG draw.
        if coup_unrest.popular_unrest.attempted:
            expected_unrest_success = unrest_success_probability_bps(
                organization_bps=organization_bps, legitimacy_bps=closing_politics.legitimacy_bps
            )
            if coup_unrest.popular_unrest.success_probability_bps != expected_unrest_success:
                problems.append(
                    "coup_unrest.popular_unrest.success_probability_bps="
                    f"{coup_unrest.popular_unrest.success_probability_bps} does not match the "
                    f"recomputed figure ({expected_unrest_success})"
                )

        # Group 29: popular-unrest RNG-draw + severity recompute.
        expected_unrest_attempted = (
            derive_rng(opening_state.seed, opening_state.turn, "unrest_attempt").randint(
                1, BPS_DENOMINATOR
            )
            <= expected_unrest_risk.attempt_risk_bps
        )
        if coup_unrest.popular_unrest.attempted != expected_unrest_attempted:
            problems.append(
                f"coup_unrest.popular_unrest.attempted={coup_unrest.popular_unrest.attempted} "
                "does not match the redrawn derive_rng(seed, turn, 'unrest_attempt') outcome "
                f"({expected_unrest_attempted})"
            )
        elif coup_unrest.popular_unrest.attempted:
            expected_unrest_succeeded = derive_rng(
                opening_state.seed, opening_state.turn, "unrest_outcome"
            ).randint(1, BPS_DENOMINATOR) <= (
                coup_unrest.popular_unrest.success_probability_bps or 0
            )
            if coup_unrest.popular_unrest.succeeded != expected_unrest_succeeded:
                problems.append(
                    f"coup_unrest.popular_unrest.succeeded={coup_unrest.popular_unrest.succeeded} "
                    "does not match the redrawn derive_rng(seed, turn, 'unrest_outcome') outcome "
                    f"({expected_unrest_succeeded})"
                )
            elif coup_unrest.popular_unrest.succeeded:
                severity_draw = derive_rng(
                    opening_state.seed, opening_state.turn, "unrest_severity"
                ).randint(1, BPS_DENOMINATOR)
                expected_outcome = (
                    "assassination"
                    if severity_draw <= ASSASSINATION_SEVERITY_THRESHOLD_BPS
                    else "forced_abdication"
                )
                if coup_unrest.popular_unrest.outcome != expected_outcome:
                    problems.append(
                        f"coup_unrest.popular_unrest.outcome={coup_unrest.popular_unrest.outcome!r} "
                        "does not match the redrawn derive_rng(seed, turn, 'unrest_severity') "
                        f"outcome ({expected_outcome!r})"
                    )

        # Group 30: impeachment eligibility + attempt-risk recompute, from closing_state's
        # constitution (never checked against a report field, since ImpeachmentChannelReport
        # carries no constitution axes of its own).
        expected_eligible = (
            closing_politics.constitution.legislature is not Legislature.NONE
            and closing_politics.constitution.judicial_review is not JudicialReview.NONE
            and closing_politics.constitution.executive_selection
            is not ExecutiveSelection.HEREDITARY
        )
        if coup_unrest.impeachment.eligible != expected_eligible:
            problems.append(
                f"coup_unrest.impeachment.eligible={coup_unrest.impeachment.eligible} does not "
                f"match the recomputed eligibility from closing_state's constitution "
                f"({expected_eligible})"
            )
        expected_impeachment_risk = None
        if expected_eligible and coup_unrest.impeachment.eligible:
            if coup_unrest.impeachment.opposition_seat_share_bps != opposition_seat_share_bps:
                problems.append(
                    "coup_unrest.impeachment.opposition_seat_share_bps="
                    f"{coup_unrest.impeachment.opposition_seat_share_bps} does not match "
                    f"closing_state ({opposition_seat_share_bps})"
                )
            if coup_unrest.impeachment.legitimacy_bps != closing_politics.legitimacy_bps:
                problems.append(
                    f"coup_unrest.impeachment.legitimacy_bps={coup_unrest.impeachment.legitimacy_bps} "
                    f"does not match closing_state ({closing_politics.legitimacy_bps})"
                )
            assert opposition_seat_share_bps is not None
            expected_impeachment_risk = impeachment_attempt_risk_bps(
                opposition_seat_share_bps=opposition_seat_share_bps,
                legitimacy_bps=closing_politics.legitimacy_bps,
                judicial_review=closing_politics.constitution.judicial_review,
            )
            for field_name, report_value, expected_value in (
                (
                    "legitimacy_contribution_bps",
                    coup_unrest.impeachment.legitimacy_contribution_bps,
                    expected_impeachment_risk.legitimacy_contribution_bps,
                ),
                (
                    "opposition_contribution_bps",
                    coup_unrest.impeachment.opposition_contribution_bps,
                    expected_impeachment_risk.opposition_contribution_bps,
                ),
                (
                    "attempt_risk_bps",
                    coup_unrest.impeachment.attempt_risk_bps,
                    expected_impeachment_risk.attempt_risk_bps,
                ),
            ):
                if report_value != expected_value:
                    problems.append(
                        f"coup_unrest.impeachment.{field_name}={report_value} does not match the "
                        f"recomputed figure from closing_state ({expected_value})"
                    )

        # Group 31: impeachment success-probability recompute, independent of the RNG draw.
        if (
            expected_eligible
            and coup_unrest.impeachment.eligible
            and coup_unrest.impeachment.attempted
        ):
            assert opposition_seat_share_bps is not None
            expected_impeachment_success = impeachment_success_probability_bps(
                opposition_seat_share_bps=opposition_seat_share_bps,
                legitimacy_bps=closing_politics.legitimacy_bps,
            )
            if coup_unrest.impeachment.success_probability_bps != expected_impeachment_success:
                problems.append(
                    "coup_unrest.impeachment.success_probability_bps="
                    f"{coup_unrest.impeachment.success_probability_bps} does not match the "
                    f"recomputed figure ({expected_impeachment_success})"
                )

        # Group 32: impeachment RNG-draw recompute.
        if (
            expected_eligible
            and coup_unrest.impeachment.eligible
            and expected_impeachment_risk is not None
        ):
            expected_impeachment_attempted = (
                derive_rng(opening_state.seed, opening_state.turn, "impeachment_attempt").randint(
                    1, BPS_DENOMINATOR
                )
                <= expected_impeachment_risk.attempt_risk_bps
            )
            if coup_unrest.impeachment.attempted != expected_impeachment_attempted:
                problems.append(
                    f"coup_unrest.impeachment.attempted={coup_unrest.impeachment.attempted} does "
                    "not match the redrawn derive_rng(seed, turn, 'impeachment_attempt') outcome "
                    f"({expected_impeachment_attempted})"
                )
            elif coup_unrest.impeachment.attempted:
                expected_impeachment_succeeded = derive_rng(
                    opening_state.seed, opening_state.turn, "impeachment_outcome"
                ).randint(1, BPS_DENOMINATOR) <= (
                    coup_unrest.impeachment.success_probability_bps or 0
                )
                if coup_unrest.impeachment.succeeded != expected_impeachment_succeeded:
                    problems.append(
                        f"coup_unrest.impeachment.succeeded={coup_unrest.impeachment.succeeded} "
                        "does not match the redrawn derive_rng(seed, turn, "
                        f"'impeachment_outcome') outcome ({expected_impeachment_succeeded})"
                    )

        # Group 33: removal_triggered vs closing_state's own terminal_outcome. Slot 12 runs
        # before slot 13, so `removal_triggered is None` does not by itself mean anything is
        # wrong -- the election phase (slot 13, groups 35-40) may have concluded the game
        # instead, via ELECTORAL_DEFEAT/TERM_LIMIT_EXIT, a different and equally legitimate
        # source. But a coup/forced-abdication/assassination/impeachment removal reason can ONLY
        # ever come from THIS channel -- if closing_state carries one of those four and
        # `removal_triggered` is `None` or disagrees, that is unambiguously a fabrication
        # (tamper-matrix case 22).
        outcome = closing_politics.terminal_outcome
        state_removal_reason = outcome.removal_reason if outcome is not None else None
        if state_removal_reason in _COUP_UNREST_OWNED_REMOVAL_REASONS:
            if coup_unrest.removal_triggered != state_removal_reason:
                problems.append(
                    f"coup_unrest.removal_triggered={coup_unrest.removal_triggered!r} does not "
                    "match closing_state politics.terminal_outcome.removal_reason "
                    f"({state_removal_reason!r})"
                )
        elif coup_unrest.removal_triggered is not None:
            problems.append(
                f"coup_unrest.removal_triggered={coup_unrest.removal_triggered!r} does not "
                "match closing_state politics.terminal_outcome.removal_reason "
                f"({state_removal_reason!r})"
            )
        if coup_unrest.removal_triggered is not None and outcome is not None:
            if outcome.bucket.value != "defeat":
                problems.append(
                    "coup_unrest.removal_triggered is set, but closing_state politics."
                    f"terminal_outcome does not carry bucket='defeat' ({outcome!r})"
                )
            elif outcome.turn != closing_state.turn:
                problems.append(
                    f"closing_state terminal_outcome.turn={outcome.turn} does not match "
                    f"closing_state.turn={closing_state.turn}"
                )

        # Group 34 (R6): transition-pressure identity recompute -- the ONE combining formula,
        # applied once, reading the turn's OPENING pressure and (Gate 3C3 scope; always 0 here,
        # since ConstitutionalAmendmentDecision does not exist yet) the amendment-added amount.
        amendment_decision = (
            decisions.constitutional_amendment_decision() if decisions is not None else None
        )
        amendment_report = report.constitutional_amendment
        amendment_enacted = _reported_amendment_is_enacted(amendment_report)
        axes_changed = (
            len(amendment_decision.targets)
            if amendment_decision is not None and amendment_enacted
            else 0
        )
        expected_added = transition_pressure_added_bps(
            difficulty=opening_politics.constitution.amendment_difficulty,
            axes_changed=axes_changed,
        )
        expected_pressure = resolve_transition_pressure_bps(
            opening_pressure_bps=opening_politics.regime_transition_pressure_bps,
            amendment_added_bps=expected_added,
        )
        for field_name, report_value, expected_value in (
            (
                "opening_transition_pressure_bps",
                coup_unrest.opening_transition_pressure_bps,
                expected_pressure.opening_bps,
            ),
            (
                "decayed_transition_pressure_bps",
                coup_unrest.decayed_transition_pressure_bps,
                expected_pressure.decayed_bps,
            ),
            (
                "added_transition_pressure_bps",
                coup_unrest.added_transition_pressure_bps,
                expected_pressure.added_bps,
            ),
            (
                "closing_transition_pressure_bps",
                coup_unrest.closing_transition_pressure_bps,
                expected_pressure.closing_bps,
            ),
        ):
            if report_value != expected_value:
                problems.append(
                    f"coup_unrest.{field_name}={report_value} does not match the recomputed R6 "
                    f"identity ({expected_value})"
                )
        if closing_politics.regime_transition_pressure_bps != expected_pressure.closing_bps:
            problems.append(
                "closing_state politics.regime_transition_pressure_bps="
                f"{closing_politics.regime_transition_pressure_bps} does not match the "
                f"recomputed R6 identity ({expected_pressure.closing_bps})"
            )

    # Groups 35-40 (plan §8, Gate 3C1): the election report against real state, real seeded RNG,
    # and (§4.4) the exact next_election_turn scheduling table -- never merely against the
    # report's own self-validated story.
    election = report.election
    if election is not None:
        term_limit = closing_politics.constitution.executive_term_limit_terms
        term_limited = (
            term_limit is not None and opening_politics.consecutive_terms_held >= term_limit
        )

        # Gate 3C2: slot 12 (coup/unrest/impeachment) runs BEFORE slot 13 (election) and, if it
        # already concludes the game this turn, slot 13 always short-circuits to an inert
        # not_scheduled report regardless of whether this turn also happened to be a scheduled
        # election milestone (§4.2). Every group below that reasons about `election.scheduled`/
        # `.result` against the OPENING schedule needs to know that, or a coup landing on what
        # would otherwise have been an election turn reads as a reconciliation bug --
        # `coup_unrest_concluded` (computed once, above, alongside groups 24-34) carries that.

        # Group 35: scheduling recompute -- `scheduled` vs the OPENING schedule, and
        # `next_election_turn`'s new-or-unchanged value re-derived per §4.4's table (Gate 3C1's
        # four reachable rows: WIN reschedules by the closing constitution's own interval; a
        # LOSS/TERM_LIMIT_EXIT/non-scheduled turn leaves it frozen -- the two amendment-driven
        # rows are Gate 3C3 scope, unreachable while no amendment mechanism exists).
        amendment_decision = (
            decisions.constitutional_amendment_decision() if decisions is not None else None
        )
        amendment_report = report.constitutional_amendment
        amendment_enacted = _reported_amendment_is_enacted(amendment_report)
        interval_target = (
            next(
                (
                    target
                    for target in amendment_decision.targets
                    if target.axis == "national_election_interval_turns"
                ),
                None,
            )
            if amendment_decision is not None and amendment_enacted
            else None
        )
        post_slot_2_next = (
            (closing_state.turn + interval_target.value)
            if interval_target is not None and interval_target.value is not None
            else None
            if interval_target is not None
            else opening_politics.next_election_turn
        )
        expected_scheduled = not coup_unrest_concluded and post_slot_2_next == closing_state.turn
        if election.scheduled != expected_scheduled:
            problems.append(
                f"election.scheduled={election.scheduled} does not match "
                f"opening_state politics.next_election_turn == closing_state.turn "
                f"({expected_scheduled})"
            )
        if (
            election.scheduled
            and not term_limited
            and election.result == "won"
            and not election.liberalization_completed
        ):
            interval = closing_politics.constitution.national_election_interval_turns
            expected_next = (closing_state.turn + interval) if interval is not None else None
        else:
            expected_next = post_slot_2_next
        if election.next_election_turn != expected_next:
            problems.append(
                f"election.next_election_turn={election.next_election_turn} does not match the "
                f"§4.4 scheduling rule's expected value ({expected_next})"
            )
        if closing_politics.next_election_turn != election.next_election_turn:
            problems.append(
                f"closing_state politics.next_election_turn={closing_politics.next_election_turn} "
                f"does not match election.next_election_turn={election.next_election_turn}"
            )

        # Group 36: term-limit recompute -- `eligible_to_stand`/`result == "term_limit_exit"`
        # against opening terms-held and the post-slot-2 constitution's term limit.
        if election.scheduled:
            if election.executive_term_limit_terms != term_limit:
                problems.append(
                    f"election.executive_term_limit_terms={election.executive_term_limit_terms} "
                    f"does not match opening_state's executive_term_limit_terms={term_limit}"
                )
            if term_limited != (election.result == "term_limit_exit"):
                problems.append(
                    f"term_limited={term_limited} (opening consecutive_terms_held="
                    f"{opening_politics.consecutive_terms_held} >= term_limit={term_limit}) does "
                    f"not match election.result={election.result!r}"
                )
            if election.eligible_to_stand == term_limited:
                problems.append(
                    f"election.eligible_to_stand={election.eligible_to_stand} does not match "
                    f"term_limited={term_limited}"
                )

        # Group 37: support-score recompute -- legislative/population/legitimacy contributions
        # re-derived from CLOSING state (R7: nothing after slot 11 touches the legislature,
        # population approval, or legitimacy, so closing_state's values are provably what slot 13
        # actually read), matched field by field against the report -- never re-trusting the
        # report's own arithmetic.
        if election.scheduled and not term_limited:
            closing_legislature = closing_politics.legislature
            if closing_legislature is not None:
                lower_chamber = next(
                    (
                        chamber_state
                        for chamber_state in closing_legislature.chambers
                        if chamber_state.chamber == LegislativeChamber.LOWER
                    ),
                    None,
                )
                lower_pairs = tuple(
                    (seat_entry.seats, bloc.government_relationship_bps)
                    for party in closing_legislature.parties
                    for bloc in party.blocs
                    for seat_entry in bloc.seats
                    if seat_entry.chamber == LegislativeChamber.LOWER
                )
                expected_legislative_support = (
                    legislative_support_bps(
                        bloc_seats_and_relationships=lower_pairs,
                        total_seats=lower_chamber.total_seats,
                    )
                    if lower_chamber is not None and lower_pairs
                    else None
                )
            else:
                expected_legislative_support = None
            if election.legislative_support_contribution_bps != expected_legislative_support:
                problems.append(
                    "election.legislative_support_contribution_bps="
                    f"{election.legislative_support_contribution_bps} does not match the "
                    f"recomputed lower-chamber figure ({expected_legislative_support})"
                )
            expected_population_approval = population_weighted_mean_bps(
                shares_and_metrics=tuple(
                    (round(group.population_share * BPS_DENOMINATOR), group.approval)
                    for group in closing_player.population_groups
                )
            )
            if election.population_approval_contribution_bps != expected_population_approval:
                problems.append(
                    "election.population_approval_contribution_bps="
                    f"{election.population_approval_contribution_bps} does not match the "
                    f"recomputed figure ({expected_population_approval})"
                )
            if election.legitimacy_contribution_bps != closing_politics.legitimacy_bps:
                problems.append(
                    f"election.legitimacy_contribution_bps={election.legitimacy_contribution_bps} "
                    f"does not match closing_state politics.legitimacy_bps="
                    f"{closing_politics.legitimacy_bps}"
                )
            expected_assessment = election_baseline_support_bps(
                legislative_support_bps=election.legislative_support_contribution_bps,
                population_approval_bps=election.population_approval_contribution_bps,
                legitimacy_bps=election.legitimacy_contribution_bps,
            )
            if election.baseline_support_bps != expected_assessment.baseline_support_bps:
                problems.append(
                    f"election.baseline_support_bps={election.baseline_support_bps} does not "
                    f"match the recomputed figure ({expected_assessment.baseline_support_bps})"
                )

            # Group 38: RNG-draw recompute -- the SAME seeded stream slot 13 actually drew from,
            # redrawn independently and compared to the stored swing (only ever drawn on a real,
            # non-term-limited election evaluation).
            expected_swing = derive_rng(opening_state.seed, opening_state.turn, "election").randint(
                -MAX_POLLING_UNCERTAINTY_SWING_BPS, MAX_POLLING_UNCERTAINTY_SWING_BPS
            )
            if election.polling_uncertainty_bps != expected_swing:
                problems.append(
                    f"election.polling_uncertainty_bps={election.polling_uncertainty_bps} does "
                    f"not match the redrawn derive_rng(seed, turn, 'election') swing "
                    f"({expected_swing})"
                )

        # Group 39: result vs closing state -- `result == "won"` implies the incumbent's term
        # count actually incremented and (Gate 3C1: liberalization does not exist yet) no
        # terminal_outcome was set; `result in ("lost", "term_limit_exit")` implies the closing
        # state's terminal_outcome matches exactly.
        victory_amendment = (
            decisions.constitutional_amendment_decision() if decisions is not None else None
        )
        victory_amendment_outcome = LegislativeOutcome.NO_PROPOSAL
        if victory_amendment is not None:
            _, victory_amendment_outcome, _ = _expected_amendment_vote(
                opening_politics,
                victory_amendment,
                _endorsed_party_id_from_opening(opening_state, decisions),
            )
        pending_after_slot_2 = _pending_after_amendment(
            opening_politics=opening_politics,
            closing_politics=closing_politics,
            closing_turn=closing_state.turn,
            amendment_decision=victory_amendment,
            amendment_enacted=victory_amendment_outcome
            in (LegislativeOutcome.PASSED_LEGISLATIVE, LegislativeOutcome.ENACTED_BY_DECREE),
        )
        opening_pending = opening_politics.pending_liberalization
        should_complete_liberalization = bool(
            election.scheduled
            and election.result == "won"
            and opening_pending is not None
            and opening_pending.set_at_turn < closing_state.turn
            and pending_after_slot_2 is not None
        )
        if election.liberalization_completed != should_complete_liberalization:
            problems.append(
                "election.liberalization_completed does not match independently derived "
                f"should_complete={should_complete_liberalization}"
            )
        expected_terms_held = (
            opening_politics.consecutive_terms_held + 1
            if election.result == "won"
            else opening_politics.consecutive_terms_held
        )
        if closing_politics.consecutive_terms_held != expected_terms_held:
            problems.append(
                "closing_state politics.consecutive_terms_held="
                f"{closing_politics.consecutive_terms_held} does not match the election "
                f"result={election.result!r} applied to opening_state's "
                f"consecutive_terms_held={opening_politics.consecutive_terms_held}"
            )
        if election.result in ("term_limit_exit", "lost"):
            expected_reason = (
                "term_limit_exit" if election.result == "term_limit_exit" else "electoral_defeat"
            )
            outcome = closing_politics.terminal_outcome
            if outcome is None:
                problems.append(
                    f"election.result={election.result!r} requires closing_state to carry a "
                    "terminal_outcome, but it has none"
                )
            else:
                if outcome.bucket.value != "defeat":
                    problems.append(
                        f"election.result={election.result!r} requires terminal_outcome.bucket="
                        f"'defeat', but closing_state has {outcome.bucket.value!r}"
                    )
                if (
                    outcome.removal_reason is None
                    or outcome.removal_reason.value != expected_reason
                ):
                    problems.append(
                        f"election.result={election.result!r} requires terminal_outcome"
                        f".removal_reason={expected_reason!r}, but closing_state has "
                        f"{outcome.removal_reason.value if outcome.removal_reason else None!r}"
                    )
                if outcome.turn != closing_state.turn:
                    problems.append(
                        f"terminal_outcome.turn={outcome.turn} does not match "
                        f"closing_state.turn={closing_state.turn}"
                    )
        elif election.result == "won":
            outcome = closing_politics.terminal_outcome
            if should_complete_liberalization:
                if (
                    outcome is None
                    or outcome.bucket is not OutcomeBucket.VICTORY
                    or outcome.victory_reason is not VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED
                    or outcome.turn != closing_state.turn
                ):
                    problems.append(
                        "election.liberalization_completed=True requires the exact peaceful "
                        f"liberalization VICTORY terminal outcome, got {outcome!r}"
                    )
            elif outcome is not None and not coup_unrest_concluded:
                problems.append(
                    f"an ordinary won election must leave terminal_outcome=None, got {outcome!r}"
                )

        # Group 40: `election.parties` vs `closing_state.politics.legislature`, by `party_id`
        # identity -- exact seats/total_seats match, read from state DIRECTLY, never through
        # `LegislativeReport` (a bug an earlier draft's design would have introduced, since a
        # decree/no-proposal turn's `LegislativeReport` carries no chamber/bloc rows at all).
        if election.parties:
            closing_legislature = closing_politics.legislature
            assert closing_legislature is not None, (
                "election.parties is non-empty, which self-validation already requires a "
                "legislature to exist for"
            )
            lower_chamber = next(
                (
                    chamber_state
                    for chamber_state in closing_legislature.chambers
                    if chamber_state.chamber == LegislativeChamber.LOWER
                ),
                None,
            )
            expected_total_seats = lower_chamber.total_seats if lower_chamber is not None else 0
            expected_seats_by_party = {
                party.id: sum(
                    seat_entry.seats
                    for bloc in party.blocs
                    for seat_entry in bloc.seats
                    if seat_entry.chamber == LegislativeChamber.LOWER
                )
                for party in closing_legislature.parties
            }
            report_party_ids = {party_row.party_id for party_row in election.parties}
            for party_row in election.parties:
                if party_row.total_seats != expected_total_seats:
                    problems.append(
                        f"election.parties[{party_row.party_id!r}].total_seats="
                        f"{party_row.total_seats} does not match closing_state's lower-chamber "
                        f"total_seats ({expected_total_seats})"
                    )
                expected_seats = expected_seats_by_party.get(party_row.party_id)
                if expected_seats is None:
                    problems.append(
                        f"election.parties names {party_row.party_id!r}, which closing_state's "
                        "legislature does not contain"
                    )
                elif party_row.seats != expected_seats:
                    problems.append(
                        f"election.parties[{party_row.party_id!r}].seats={party_row.seats} does "
                        f"not match closing_state's lower-chamber seats ({expected_seats})"
                    )
            for party_id in expected_seats_by_party:
                if party_id not in report_party_ids:
                    problems.append(
                        f"election.parties is missing a row for {party_id!r}, which "
                        "closing_state's legislature holds lower-chamber seats for"
                    )

    # An election turn that was NOT scheduled must leave consecutive_terms_held exactly as it
    # opened (next_election_turn's own staticness is already proved by group 35 above) -- a
    # no-op election evaluation must be a genuine no-op, proved state-to-state. terminal_outcome
    # is the one exception: slot 12 (coup/unrest/impeachment) can legitimately set it on a turn
    # where the election never even ran (§4.2's short-circuit) -- that case is reconciled against
    # `report.coup_unrest` directly (Gate 3C2, groups 24-34), not here.
    if election is not None and not election.scheduled:
        if closing_politics.consecutive_terms_held != opening_politics.consecutive_terms_held:
            problems.append(
                "election.scheduled=False but closing_state politics.consecutive_terms_held="
                f"{closing_politics.consecutive_terms_held} differs from opening_state's "
                f"{opening_politics.consecutive_terms_held}"
            )
        if (
            not coup_unrest_concluded
            and closing_politics.terminal_outcome != opening_politics.terminal_outcome
        ):
            problems.append(
                "election.scheduled=False but closing_state politics.terminal_outcome differs "
                "from opening_state's"
            )

    raw_amendment_report: object = report.constitutional_amendment
    amendment_report = (
        raw_amendment_report
        if isinstance(raw_amendment_report, ConstitutionalAmendmentReport)
        else None
    )
    amendment_decision = (
        decisions.constitutional_amendment_decision() if decisions is not None else None
    )
    expected_amendment_chambers: tuple[dict[str, object], ...] = ()
    expected_amendment_outcome = LegislativeOutcome.NO_PROPOSAL
    amendment_validation_problems: tuple[str, ...] = ()
    if amendment_decision is not None:
        (
            expected_amendment_chambers,
            expected_amendment_outcome,
            amendment_validation_problems,
        ) = _expected_amendment_vote(
            opening_politics,
            amendment_decision,
            _endorsed_party_id_from_opening(opening_state, decisions),
        )
        problems.extend(amendment_validation_problems)
    amendment_enacted = expected_amendment_outcome in (
        LegislativeOutcome.PASSED_LEGISLATIVE,
        LegislativeOutcome.ENACTED_BY_DECREE,
    )

    # Group 41: pending-liberalization state-to-state, in the real slot-2 then slot-13 order.
    if decisions is not None:
        expected_pending = _pending_after_amendment(
            opening_politics=opening_politics,
            closing_politics=closing_politics,
            closing_turn=closing_state.turn,
            amendment_decision=amendment_decision,
            amendment_enacted=amendment_enacted,
        )
        opening_pending = opening_politics.pending_liberalization
        should_complete = bool(
            election is not None
            and election.scheduled
            and election.result == "won"
            and opening_pending is not None
            and opening_pending.set_at_turn < closing_state.turn
            and expected_pending is not None
        )
        if election is not None and election.liberalization_completed != should_complete:
            problems.append(
                "group 42 election.liberalization_completed does not match independently "
                f"derived should_complete={should_complete}"
            )
        if (
            election is not None
            and election.scheduled
            and (election.result == "lost" or should_complete)
        ):
            expected_pending = None
        if closing_politics.pending_liberalization != expected_pending:
            problems.append(
                "group 41 pending_liberalization does not match slot-2 then slot-13 state "
                f"transition: closing={closing_politics.pending_liberalization!r}, "
                f"expected={expected_pending!r}"
            )

    # Group 42: a liberalization victory consumes provenance that existed in persisted opening
    # state, never a marker fabricated by this turn's report or slot-2 amendment.
    if election is not None and election.liberalization_completed:
        opening_pending = opening_politics.pending_liberalization
        if opening_pending is None or opening_pending.set_at_turn >= closing_state.turn:
            problems.append(
                "group 42 election.liberalization_completed requires persisted "
                "opening_state pending_liberalization from an earlier turn"
            )

    # Group 43: amendment report provenance against the real submitted decision and opening vote.
    if decisions is not None:
        if political_capital_report is not None:
            reported_amendment_expenditures = tuple(
                (
                    row.party_id,
                    row.bloc_id,
                    row.political_capital,
                    row.decision_digest,
                )
                for row in political_capital_report.expenditures
                if row.category is CapitalExpenditureCategory.CONSTITUTIONAL_AMENDMENT
            )
            if amendment_decision is None:
                expected_amendment_expenditures: tuple[
                    tuple[str | None, str | None, int, str], ...
                ] = ()
            else:
                expected_digest = constitutional_amendment_decision_digest(amendment_decision)
                expected_amendment_expenditures = (
                    ((None, None, CONSTITUTIONAL_AMENDMENT_DECREE_COST, expected_digest),)
                    if amendment_decision.route is ProposalRoute.DECREE
                    else tuple(
                        (
                            row.party_id,
                            row.bloc_id,
                            row.political_capital,
                            expected_digest,
                        )
                        for row in amendment_decision.influence
                    )
                )
            if reported_amendment_expenditures != expected_amendment_expenditures:
                problems.append(
                    "group 43 constitutional-amendment capital ledger rows do not exactly "
                    "match the real decision identities, amounts, and digest: "
                    f"report={reported_amendment_expenditures!r}, "
                    f"expected={expected_amendment_expenditures!r}"
                )
        if amendment_report is None:
            problems.append(
                "group 43 constitutional_amendment report is missing or has an invalid runtime type"
            )
        elif amendment_decision is None:
            if (
                amendment_report.proposed
                or amendment_report.outcome is not LegislativeOutcome.NO_PROPOSAL
                or amendment_report.route is not None
                or amendment_report.targets
                or amendment_report.chambers
                or amendment_report.influence
                or amendment_report.political_capital_committed != 0
                or amendment_report.amendment_decision_digest is not None
            ):
                problems.append(
                    "group 43 no ConstitutionalAmendmentDecision was submitted but the report "
                    "does not describe exact NO_PROPOSAL"
                )
        else:
            if not amendment_report.proposed:
                problems.append("group 43 submitted amendment requires proposed=True")
            if amendment_report.route is not amendment_decision.route:
                problems.append("group 43 amendment route does not match the submitted decision")
            expected_digest = constitutional_amendment_decision_digest(amendment_decision)
            if amendment_report.amendment_decision_digest != expected_digest:
                problems.append(
                    "group 43 amendment_decision_digest does not match the submitted decision"
                )
            expected_targets = tuple(
                (
                    target.axis,
                    _amendment_value_text(getattr(opening_politics.constitution, target.axis)),
                    _amendment_value_text(target.value),
                )
                for target in amendment_decision.targets
            )
            reported_targets = tuple(
                (row.axis, row.opening_value, row.proposed_value)
                for row in amendment_report.targets
            )
            if reported_targets != expected_targets:
                problems.append(
                    "group 43 amendment targets do not match the submitted decision and real "
                    f"opening constitution: report={reported_targets!r}, expected={expected_targets!r}"
                )
            if amendment_report.influence != amendment_decision.influence:
                problems.append(
                    "group 43 amendment influence does not match the submitted decision"
                )
            expected_commitment = (
                CONSTITUTIONAL_AMENDMENT_DECREE_COST
                if amendment_decision.route is ProposalRoute.DECREE
                else sum(row.political_capital for row in amendment_decision.influence)
            )
            if amendment_report.political_capital_committed != expected_commitment:
                problems.append(
                    "group 43 amendment political-capital commitment does not match the real "
                    f"decision ({expected_commitment})"
                )
            if amendment_report.outcome is not expected_amendment_outcome:
                problems.append(
                    f"group 43 amendment outcome={amendment_report.outcome!r} does not match "
                    f"the recomputed outcome={expected_amendment_outcome!r}"
                )
            if len(amendment_report.chambers) != len(expected_amendment_chambers):
                problems.append(
                    "group 43 amendment chamber count does not match the opening legislature"
                )
            for index, expected_row in enumerate(expected_amendment_chambers):
                if index >= len(amendment_report.chambers):
                    break
                reported_row = amendment_report.chambers[index]
                for field_name, expected_chamber_value in expected_row.items():
                    if getattr(reported_row, field_name) != expected_chamber_value:
                        problems.append(
                            f"group 43 amendment chamber[{index}].{field_name}="
                            f"{getattr(reported_row, field_name)!r} does not match recomputed "
                            f"value {expected_chamber_value!r}"
                        )
        if amendment_report is not None:
            for axis in (*_AMENDABLE_CONSTITUTION_AXES, "amendment_difficulty"):
                if getattr(amendment_report.opening_constitution, axis) != getattr(
                    opening_politics.constitution, axis
                ):
                    problems.append(
                        f"group 43 amendment opening snapshot axis {axis!r} does not match "
                        "opening_state"
                    )
                if getattr(amendment_report.closing_constitution, axis) != getattr(
                    closing_politics.constitution, axis
                ):
                    problems.append(
                        f"group 43 amendment closing snapshot axis {axis!r} does not match "
                        "closing_state"
                    )
            if amendment_report.opening_constitution_digest != constitution_digest(
                opening_politics.constitution
            ):
                problems.append("group 43 opening_constitution_digest does not match opening_state")
            if amendment_report.closing_constitution_digest != constitution_digest(
                closing_politics.constitution
            ):
                problems.append("group 43 closing_constitution_digest does not match closing_state")

    # Group 44: only the five authored targets may change; three axes are never amendable.
    for axis in _NEVER_AMENDABLE_CONSTITUTION_AXES:
        if getattr(opening_politics.constitution, axis) != getattr(
            closing_politics.constitution, axis
        ):
            problems.append(f"group 44 never-amendable constitution axis {axis!r} changed")
    targets_by_axis: dict[str, object] = (
        {target.axis: target.value for target in amendment_decision.targets}
        if amendment_decision is not None and amendment_enacted
        else {}
    )
    for axis in _AMENDABLE_CONSTITUTION_AXES:
        opening_value = getattr(opening_politics.constitution, axis)
        closing_value = getattr(closing_politics.constitution, axis)
        expected_axis_value = targets_by_axis.get(axis, opening_value)
        if closing_value != expected_axis_value:
            problems.append(
                f"group 44 constitution axis {axis!r} closed at {closing_value!r}; "
                f"expected {expected_axis_value!r} from the real submitted amendment"
            )

    # Group 18: decision provenance -- located from the REAL DecisionSet, never inferred.
    if decisions is not None:
        budget_count = sum(1 for d in decisions.decisions if isinstance(d, BudgetDecision))
        if budget_count > 1:
            problems.append(
                f"the submitted DecisionSet carries {budget_count} BudgetDecisions; "
                "at most one is ever valid"
            )
        if decisions.expected_turn != opening_state.turn:
            problems.append(
                f"decisions.expected_turn={decisions.expected_turn} does not match "
                f"opening_state.turn={opening_state.turn}"
            )
        if decisions.expected_state_version != opening_state.state_version:
            problems.append(
                f"decisions.expected_state_version={decisions.expected_state_version} does not "
                f"match opening_state.state_version={opening_state.state_version}"
            )

        if decision is None:
            if legislative.outcome is not LegislativeOutcome.NO_PROPOSAL:
                problems.append(
                    "no BudgetDecision was submitted but legislative.outcome="
                    f"{legislative.outcome.value!r} (expected NO_PROPOSAL)"
                )
            if legislative.route is not None:
                problems.append(
                    f"no BudgetDecision was submitted but legislative.route={legislative.route!r} "
                    "(expected None)"
                )
            if legislative.political_capital_committed != 0:
                problems.append(
                    "no BudgetDecision was submitted but legislative.political_capital_committed="
                    f"{legislative.political_capital_committed} (expected 0)"
                )
            if legislative.budget_decision_digest is not None:
                problems.append(
                    "no BudgetDecision was submitted but legislative.budget_decision_digest="
                    f"{legislative.budget_decision_digest!r} (expected None)"
                )
        else:
            if legislative.outcome is LegislativeOutcome.NO_PROPOSAL:
                problems.append(
                    "a BudgetDecision was submitted but legislative.outcome=NO_PROPOSAL"
                )
            if legislative.route != decision.route:
                problems.append(
                    f"legislative.route={legislative.route!r} does not match the submitted "
                    f"decision's route={decision.route!r}"
                )
            expected_digest = budget_decision_digest(decision)
            if legislative.budget_decision_digest != expected_digest:
                problems.append(
                    "legislative.budget_decision_digest="
                    f"{legislative.budget_decision_digest!r} does not match "
                    f"budget_decision_digest(the submitted decision)={expected_digest!r}"
                )

            # Influence allocations agree by (party_id, bloc_id), both directions, never row
            # position -- `legislative.blocs` may repeat an identity across chambers (bicameral),
            # so the report side is folded to one allocation per identity first (its own
            # consistency across chamber rows is `LegislativeReport`'s job, not this module's).
            decision_allocations = {
                (allocation.party_id, allocation.bloc_id): allocation.political_capital
                for allocation in decision.influence
            }
            report_allocations = {
                (row.party_id, row.bloc_id): row.political_capital_allocated
                for row in legislative.blocs
            }
            for alloc_key, amount in decision_allocations.items():
                if report_allocations.get(alloc_key, 0) != amount:
                    problems.append(
                        f"the submitted decision commits {amount} to {alloc_key!r}, but "
                        "legislative.blocs does not show that allocation"
                    )
            for alloc_key, amount in report_allocations.items():
                if amount > 0 and decision_allocations.get(alloc_key, 0) != amount:
                    problems.append(
                        f"legislative.blocs shows {amount} allocated to {alloc_key!r}, but the "
                        "submitted decision does not commit that"
                    )

    return problems


# ================================================================================================
# External Wars Gate W1, Commit 7 (R13, C8 sec.12): reconciliation groups 46-52.
#
# `ForeignAffairsReport` and `ForeignConflictProgressionRow` already self-validate their own
# internal arithmetic -- given a row's own stored opening_*/position_jitter_bps/termination_draw,
# `report.py`'s own validators re-derive every closing_* field via the exact same pure formulas
# `phases.py` uses, and reject a mismatch at construction. That is what makes the SAME
# "composition, not re-derivation" principle this module's docstring already documents for
# apportionment (group 15) apply here too: this function does not re-derive the position/
# exhaustion/readiness formula chain from opening to closing (the report's own validators already
# proved that, whenever the report was genuinely constructed) -- it proves the three things a
# self-validating report structurally CANNOT prove about itself: that its OPENING values are
# authentic (group 46), that its DRAWS are authentic redraws of the real seeded streams (group 48),
# and that its CLOSING claims match the REAL authoritative state (group 47's projection) rather
# than merely being self-consistent with its own opening values.
#
# A `model_copy(update=...)`-forged report bypasses every self-validator (Pydantic v2 never
# re-validates on `model_copy`), so groups 47/48/52 below DO recompute the position/exhaustion/
# readiness/termination-gate chain independently wherever that is the only way to know whether a
# draw should exist at all (the termination-draw guard) or whether a floor should have applied --
# not because the report's arithmetic can't be trusted when genuinely constructed, but because a
# bypassed construction is exactly what every tamper test here constructs.
#
# Never raises on tampered input: every state/mapping lookup is `.get()`, never `[...]`; the two
# pure functions that CAN raise on out-of-range input if fed report-derived data directly
# (`select_candidate_index` on empty/non-positive weights; `active_closing_status` on a
# termination_draw inconsistent with its own gate state) are never called with report-supplied
# values -- only with values this function itself derived from authoritative state and its own
# fresh redraws, which are safe by the same mathematical guarantees `phases.py`'s own comments
# document (e.g. zero passing candidates makes `occurred=True` unreachable for any draw).
#
# Two engine facts shape every guard below:
#   - The outbreak occurrence draw is UNCONDITIONAL (every turn, including zero-candidate and
#     at-capacity turns); the selection draw is conditional on occurrence, drawn from the SAME
#     generator immediately afterward -- never a second generator.
#   - A CEASEFIRE-opening row consumes NO randomness at all: no jitter draw, no termination draw
#     (`_progress_ceasefire_conflict`'s own docstring). Only an ACTIVE-opening row ever draws
#     jitter, and only when ITS OWN recomputed ceasefire gate opens does it draw a termination
#     value.
# ================================================================================================

_LIVE_CONFLICT_STATUSES = (ConflictStatus.ACTIVE, ConflictStatus.CEASEFIRE)


def _is_live_conflict_status(status: ConflictStatus) -> bool:
    return status in _LIVE_CONFLICT_STATUSES


def _transcribed_assistance_share_bps(
    *,
    personal_trust_bps: int,
    standing_bps: int,
    foreign_minister_competence_bps: int,
    independence_bps: int,
) -> int:
    """Group 59's OWN copy of the share formula, deliberately not a call to
    `foreign_assistance.assistance_share_bps`.

    Same reasoning as `_transcribed_bargain_price`: a reconciliation check that calls the function
    which produced the report cannot fail when that function is wrong -- it computes the same wrong
    answer and certifies it. Transcribing means the arithmetic is genuinely performed twice, by two
    authors. Sharing the CONSTANTS is a different thing and is allowed, because a constant is one
    number both sides read and a transcription error in the formula still surfaces.

    `tests/test_foreign_assistance.py` enforces the boundary with an AST allowlist scan rather than
    trusting this docstring.
    """
    return max(
        1,
        FOREIGN_ASSISTANCE_BASE_SHARE_BPS
        + trunc_div_toward_zero(
            personal_trust_bps * FOREIGN_ASSISTANCE_TRUST_SHARE_MAX_BPS, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            standing_bps * FOREIGN_ASSISTANCE_STANDING_SHARE_MAX_BPS, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            foreign_minister_competence_bps * FOREIGN_MINISTER_ASSISTANCE_SHARE_MAX_BPS,
            BPS_DENOMINATOR,
        )
        - trunc_div_toward_zero(
            independence_bps * FOREIGN_ASSISTANCE_INDEPENDENCE_PENALTY_MAX_BPS, BPS_DENOMINATOR
        ),
    )


def _reconcile_foreign_assistance(
    *,
    opening_state: GameState,
    closing_state: GameState,
    foreign_affairs: ForeignAffairsReport,
    report: TurnReport,
    decisions: DecisionSet | None,
) -> list[str]:
    """Group 59 (characters slice) -- foreign assistance, checked against an INDEPENDENT
    re-derivation rather than against the engine's own answer.

    Five things, as approved:

    1. **The decision** -- the row names the counterpart the submitted request named, that
       counterpart exists, and the snapshotted names match `opening_state`.
    2. **Opening and closing capacity** -- `assistance_drawn` in `closing_state` equals
       `opening_state`'s plus exactly the granted amount, never exceeds the authored capacity, and
       no OTHER counterpart's draw moved.
    3. **The finance term** -- `FinanceReport.external_assistance` equals the granted sum, and
       `pre_financing_balance` still satisfies the UNCHANGED three-term identity, so a grant that
       leaked into revenue fails here.
    4. **The report** -- the share and the grant re-derived by transcription from `opening_state`,
       and the entry matching the row param-for-param including snapshotted names.
    5. **The resulting state** -- no request means no row, no entry, no transfer and no capacity
       movement anywhere; and `world.characters` is byte-identical, since a later slice is the only
       writer of `personal_trust`.
    """
    problems: list[str] = []
    rows = foreign_affairs.assistance
    opening_world = opening_state.world
    closing_world = closing_state.world
    decision = decisions.foreign_assistance_decision() if decisions is not None else None

    # (5) Trust is read, never written by this slice.
    if opening_world.characters != closing_world.characters:
        problems.append(
            "world.characters changed during a turn, but no mechanic in this ruleset writes to it "
            "(group 59)"
        )

    granted_total = sum(row.granted for row in rows)
    finance = report.finance
    if finance is not None:
        # (3) The finance term, both directions.
        if finance.external_assistance != granted_total:
            problems.append(
                f"finance.external_assistance={finance.external_assistance} does not equal the "
                f"assistance rows' granted total ({granted_total}) (group 59)"
            )
        expected_balance = (
            finance.revenue.total_revenue
            - finance.total_program_spending
            - finance.quarterly_interest_expense
        )
        if finance.pre_financing_balance != expected_balance:
            problems.append(
                "finance.pre_financing_balance no longer equals revenue - spending - interest; a "
                "grant must never enter the country's own fiscal position (group 59)"
            )

    # (2) No counterpart's draw may move except the one that was granted.
    granted_by_profile = {row.profile_id: row.granted for row in rows}
    for profile_id in sorted(
        set(opening_world.foreign_relationships) | set(closing_world.foreign_relationships)
    ):
        opening_rel = opening_world.foreign_relationships.get(profile_id)
        closing_rel = closing_world.foreign_relationships.get(profile_id)
        if opening_rel is None or closing_rel is None:
            problems.append(
                f"foreign relationship {profile_id!r} appeared or vanished during a turn (group 59)"
            )
            continue
        expected_drawn = opening_rel.assistance_drawn + granted_by_profile.get(profile_id, 0)
        if closing_rel.assistance_drawn != expected_drawn:
            problems.append(
                f"{profile_id!r} assistance_drawn moved from {opening_rel.assistance_drawn} to "
                f"{closing_rel.assistance_drawn}, expected {expected_drawn} (group 59)"
            )
        if opening_rel.standing_bps != closing_rel.standing_bps:
            problems.append(
                f"{profile_id!r} standing_bps changed during a turn, but no mechanic in this "
                "ruleset writes it (group 59)"
            )

    if decisions is not None and decision is None:
        # (5) Nothing submitted, so nothing may be reported.
        if rows:
            problems.append(
                f"the turn reports {len(rows)} assistance row(s) but submitted no request "
                "(group 59)"
            )
        if finance is not None and finance.external_assistance != 0:
            problems.append(
                "the turn transferred external assistance but submitted no request (group 59)"
            )
        return problems

    if decision is None:
        return problems

    if len(rows) != 1:
        problems.append(
            f"the turn submitted an assistance request but reports {len(rows)} row(s) (group 59)"
        )
        return problems
    row = rows[0]

    # (1) The decision.
    if row.profile_id != decision.profile_id:
        problems.append(
            f"assistance row names {row.profile_id!r} but the submitted decision named "
            f"{decision.profile_id!r} (group 59)"
        )
        return problems
    profile = opening_world.foreign_profiles.get(row.profile_id)
    relationship = opening_world.foreign_relationships.get(row.profile_id)
    if profile is None or relationship is None:
        problems.append(
            f"the submitted request names {row.profile_id!r}, which opening_state has no profile "
            "or relationship for (group 59)"
        )
        return problems
    if row.profile_display_name != profile.display_name:
        problems.append(
            f"assistance row profile_display_name={row.profile_display_name!r} does not match "
            f"opening_state ({profile.display_name!r}) (group 59)"
        )
    if row.opening_capacity != profile.assistance_capacity:
        problems.append(
            f"assistance row opening_capacity={row.opening_capacity} does not match the authored "
            f"capacity ({profile.assistance_capacity}) (group 59)"
        )
    if row.opening_drawn != relationship.assistance_drawn:
        problems.append(
            f"assistance row opening_drawn={row.opening_drawn} does not match opening_state "
            f"({relationship.assistance_drawn}) (group 59)"
        )
    if row.standing_bps != relationship.standing_bps:
        problems.append(
            f"assistance row standing_bps={row.standing_bps} does not match opening_state "
            f"({relationship.standing_bps}) (group 59)"
        )

    # (4) The share and the grant, transcribed.
    found = leader_of_foreign_profile(opening_world.characters, row.profile_id)
    leader_id, leader = (None, None) if found is None else found
    if row.counterpart_character_id != leader_id:
        problems.append(
            f"assistance row names counterpart {row.counterpart_character_id!r} but "
            f"{row.profile_id!r}'s leader in opening_state is {leader_id!r} (group 59)"
        )

    expected_competence = holder_competence_bps(
        cabinet=opening_state.world.countries[opening_state.world.player_country_id].cabinet,
        characters=opening_world.characters,
        post=CabinetPost.FOREIGN_MINISTER,
        resolving_turn=opening_state.turn,
    )
    if row.foreign_minister_competence_bps != expected_competence:
        problems.append(
            f"assistance row foreign_minister_competence_bps="
            f"{row.foreign_minister_competence_bps} does not match the minister serving in "
            f"opening_state ({expected_competence}) (group 59)"
        )

    pool = max(0, profile.assistance_capacity - relationship.assistance_drawn)
    if relationship.standing_bps < MINIMUM_ASSISTANCE_STANDING_BPS:
        expected_share, expected_granted = 0, 0
        expected_refusal: str | None = "foreign_assistance_counterpart_is_hostile"
    elif pool <= 0:
        expected_share, expected_granted = 0, 0
        expected_refusal = "foreign_assistance_pool_exhausted"
    else:
        share = _transcribed_assistance_share_bps(
            personal_trust_bps=0 if leader is None else leader.personal_trust,
            standing_bps=relationship.standing_bps,
            foreign_minister_competence_bps=expected_competence,
            independence_bps=0 if leader is None else leader.independence,
        )
        # Transcribed, not called: the grant is floored at 1 INSIDE the `min`, so a willing
        # counterpart with a positive pool always transfers between 1 and the whole remainder.
        # `foreign_assistance_pool_exhausted` is therefore reachable from exactly one place --
        # the `pool <= 0` branch above -- which is what makes a row claiming exhaustion against a
        # pool that still has money in it fail here.
        expected_share = share
        expected_granted = min(pool, max(1, trunc_div_toward_zero(pool * share, BPS_DENOMINATOR)))
        expected_refusal = None

    if row.share_bps != expected_share:
        problems.append(
            f"assistance row share_bps={row.share_bps} does not match the re-derived share "
            f"({expected_share}) (group 59)"
        )
    if row.granted != expected_granted:
        problems.append(
            f"assistance row granted={row.granted} does not match the re-derived grant "
            f"({expected_granted}) (group 59)"
        )
    if row.refusal_code != expected_refusal:
        problems.append(
            f"assistance row refusal_code={row.refusal_code!r} does not match the re-derived "
            f"outcome ({expected_refusal!r}) (group 59)"
        )

    problems.extend(_reconcile_foreign_assistance_entry(row, report))
    return problems


def _reconcile_foreign_assistance_entry(
    row: ForeignAssistanceReport, report: TurnReport
) -> list[str]:
    """Group 59, check 4's second half: the entry IS the row, restated.

    The entry is the only surface a REFUSAL reaches -- it moves no money, so it leaves no trace in
    the finance report, and `build_turn_result` derives its drivers from entries. Without this a
    player who asked a hostile counterpart for help would see a turn in which nothing happened.

    Params are pinned by EQUALITY, so a refused row's set cannot silently acquire a monetary key.
    """
    entries = [
        entry for entry in report.entries if entry.reason_id.startswith("foreign_assistance_")
    ]
    if len(entries) != 1:
        return [
            f"a submitted assistance request must produce exactly one report entry, got "
            f"{len(entries)} (group 59)"
        ]
    entry = entries[0]
    expected_reason = row.refusal_code or "foreign_assistance_granted"
    if entry.reason_id != expected_reason:
        return [
            f"assistance entry reason_id={entry.reason_id!r} does not match the row's outcome "
            f"({expected_reason!r}) (group 59)"
        ]
    expected_params: dict[str, str | int] = {
        "profile_id": row.profile_id,
        "profile_display_name": row.profile_display_name,
    }
    if row.counterpart_character_id is not None and row.counterpart_display_name is not None:
        expected_params["counterpart_character_id"] = row.counterpart_character_id
        expected_params["counterpart_display_name"] = row.counterpart_display_name
    if row.refusal_code is None:
        expected_params["granted"] = row.granted
        expected_params["remaining_capacity"] = row.opening_capacity - row.closing_drawn
    if dict(entry.params) != expected_params:
        return [
            f"assistance entry params {dict(entry.params)!r} do not match the row "
            f"({expected_params!r}) (group 59)"
        ]
    return []


def reconcile_foreign_affairs_report(
    *,
    opening_state: GameState,
    closing_state: GameState,
    report: TurnReport,
    decisions: DecisionSet | None = None,
) -> list[str]:
    """Return every disagreement between `report.foreign_affairs` and the REAL opening/closing
    `WorldState` and the REAL seeded RNG streams (External Wars Gate W1, frozen plan sec.12,
    groups 46-52). Never raises; returns `[]` when `report.foreign_affairs is None` (the 13-report
    all-present/all-absent rule is `TurnReport`'s own job, unaffected by this function).

    A separate, independently testable entrypoint from
    `reconcile_political_legislative_and_survival_report` -- not an extension of that ~1,950-line
    function -- mirroring the "one module, two owners" split this module already keeps for
    political/legislative concerns versus everything else. Group 51's own closing-legitimacy
    half stays that function's job (see group 51 below): this function proves the SECURITY
    CONTRIBUTION reaching the political report is correctly derived; the existing political
    reconciliation proves that contribution reaching CLOSING LEGITIMACY.
    """
    foreign_affairs = report.foreign_affairs
    if foreign_affairs is None:
        return []

    problems: list[str] = []
    opening_world = opening_state.world
    closing_world = closing_state.world
    outbreak = foreign_affairs.outbreak

    # ---- Group 59 (characters slice): foreign assistance -----------------------------------
    problems.extend(
        _reconcile_foreign_assistance(
            opening_state=opening_state,
            closing_state=closing_state,
            foreign_affairs=foreign_affairs,
            report=report,
            decisions=decisions,
        )
    )

    # ---- Group 49: authored staticness ---------------------------------------------------
    # Plain `==` on the `foreign_profiles` dict is already insertion-order-independent (Python
    # dict equality compares key/value pairs, never iteration order), so this is simultaneously
    # the staticness proof and half of group 52's order-independence guarantee.
    if opening_world.foreign_profiles != closing_world.foreign_profiles:
        problems.append(
            "world.foreign_profiles changed between opening_state and closing_state -- must be "
            "authored and static in W1 (group 49)"
        )
    if opening_world.dyads != closing_world.dyads:
        problems.append(
            "world.dyads changed between opening_state and closing_state -- must be authored "
            "and static in W1 (group 49)"
        )

    opening_conflicts_by_id = {c.conflict_id: c for c in opening_world.conflicts}
    closing_conflicts_by_id = {c.conflict_id: c for c in closing_world.conflicts}
    opening_live_ids = {
        cid for cid, c in opening_conflicts_by_id.items() if _is_live_conflict_status(c.status)
    }
    closing_live_ids = {
        cid for cid, c in closing_conflicts_by_id.items() if _is_live_conflict_status(c.status)
    }

    # ---- Group 47a: the global concurrency cap, both states -----------------------------
    if len(opening_live_ids) > MAX_CONCURRENT_CONFLICTS:
        problems.append(
            f"opening_state has {len(opening_live_ids)} live (ACTIVE/CEASEFIRE) conflicts, "
            f"exceeding MAX_CONCURRENT_CONFLICTS={MAX_CONCURRENT_CONFLICTS} (group 47)"
        )
    if len(closing_live_ids) > MAX_CONCURRENT_CONFLICTS:
        problems.append(
            f"closing_state has {len(closing_live_ids)} live (ACTIVE/CEASEFIRE) conflicts, "
            f"exceeding MAX_CONCURRENT_CONFLICTS={MAX_CONCURRENT_CONFLICTS} (group 47)"
        )

    # ---- Group 47b/52: exact outbreak candidate reconstruction --------------------------
    at_capacity = len(opening_live_ids) >= MAX_CONCURRENT_CONFLICTS
    excluded_pairs = {
        (c.country_a, c.country_b)
        for c in opening_world.conflicts
        if _is_live_conflict_status(c.status)
    }
    dyad_by_pair = {(d.country_a, d.country_b): d for d in opening_world.dyads}

    expected_pairs: list[tuple[str, str]] = []
    expected_passing_pairs: list[tuple[str, str]] = []
    if not at_capacity:
        for dyad in opening_world.dyads:  # world.dyads is itself always canonically ordered
            pair = (dyad.country_a, dyad.country_b)
            if not dyad.eligible or pair in excluded_pairs:
                continue
            expected_pairs.append(pair)
            weight = dyad_weight_bps(tension_bps=dyad.tension_bps, grievance_bps=dyad.grievance_bps)
            if passes_pressure_floor(raw_weight_bps=weight):  # group 52: floor filters selection
                expected_passing_pairs.append(pair)  # ... never candidacy -- sub-floor rows stay

    reported_pairs = [(row.country_a, row.country_b) for row in outbreak.candidates]
    if reported_pairs != expected_pairs:
        problems.append(
            f"foreign_affairs.outbreak.candidates pairs {reported_pairs!r} do not match the "
            f"reconstructed candidate set {expected_pairs!r} (at_capacity={at_capacity}) "
            "(group 47)"
        )

    # ---- Group 52: an at-or-above-floor dyad may never be silently excluded from candidacy -
    # Fix-forward 7c: group 52's own definition names both floor DIRECTIONS -- 7b closed "no
    # outbreak from a sub-floor dyad" (an occurred=True forgery), but a report that simply omits
    # a real, eligible, non-excluded, capacity-available dyad whose weight clears
    # MIN_OUTBREAK_WEIGHT_BPS from `candidates` altogether was previously only ever flagged by
    # the generic group-47 set-mismatch check above -- never attributed to the floor boundary
    # itself. This is a distinct, explicit signal for exactly that omission, independent of
    # whatever the general membership check separately concludes.
    reported_pair_set = set(reported_pairs)
    missing_passing_pairs = [
        pair for pair in expected_passing_pairs if pair not in reported_pair_set
    ]
    if missing_passing_pairs:
        problems.append(
            f"foreign_affairs.outbreak.candidates omits {missing_passing_pairs!r}, each an "
            "eligible, non-excluded, capacity-available dyad whose raw weight clears "
            f"MIN_OUTBREAK_WEIGHT_BPS ({MIN_OUTBREAK_WEIGHT_BPS}) -- an at-or-above-floor dyad "
            "may never be silently excluded from candidacy (group 52)"
        )

    expected_total_weight = 0
    for row in outbreak.candidates:
        candidate_dyad = dyad_by_pair.get((row.country_a, row.country_b))
        if candidate_dyad is None:
            problems.append(
                f"foreign_affairs.outbreak.candidates references pair "
                f"{(row.country_a, row.country_b)!r}, which is not an opening_state dyad "
                "(group 47)"
            )
            continue
        expected_weight = dyad_weight_bps(
            tension_bps=candidate_dyad.tension_bps, grievance_bps=candidate_dyad.grievance_bps
        )
        expected_passed = passes_pressure_floor(raw_weight_bps=expected_weight)
        if (
            row.tension_bps != candidate_dyad.tension_bps
            or row.grievance_bps != candidate_dyad.grievance_bps
            or row.raw_dyad_weight_bps != expected_weight
            or row.passed_pressure_floor != expected_passed
            or row.aggressor != candidate_dyad.aggressor
            or row.defender != candidate_dyad.defender
        ):
            problems.append(
                f"candidate {(row.country_a, row.country_b)!r} disagrees with the authored dyad "
                "on tension/grievance/weight/pressure-floor-flag/aggressor/defender (group 47/52)"
            )
        if expected_passed:
            expected_total_weight += expected_weight

    if outbreak.total_weight_bps != expected_total_weight:
        problems.append(
            f"foreign_affairs.outbreak.total_weight_bps={outbreak.total_weight_bps} does not "
            f"match the recomputed sum of passing candidate weights ({expected_total_weight}) "
            "(group 47)"
        )
    expected_probability = outbreak_probability_bps(total_weight_bps=expected_total_weight)
    if outbreak.clamped_probability_bps != expected_probability:
        problems.append(
            "foreign_affairs.outbreak.clamped_probability_bps="
            f"{outbreak.clamped_probability_bps} does not match the recomputed probability "
            f"({expected_probability}) (group 47)"
        )

    # ---- Group 48a: the outbreak RNG redraw, one generator, correct order ---------------
    outbreak_rng = derive_rng(opening_state.seed, opening_state.turn, "foreign_conflict_outbreak")
    expected_occurrence_draw = outbreak_rng.randrange(BPS_DENOMINATOR)
    if outbreak.occurrence_draw != expected_occurrence_draw:
        problems.append(
            f"foreign_affairs.outbreak.occurrence_draw={outbreak.occurrence_draw} does not "
            f"match the redrawn foreign_conflict_outbreak stream ({expected_occurrence_draw}) "
            "(group 48)"
        )
    expected_occurred = outbreak_occurs(
        occurrence_draw=expected_occurrence_draw, probability_bps=expected_probability
    )
    if outbreak.occurred != expected_occurred:
        problems.append(
            f"foreign_affairs.outbreak.occurred={outbreak.occurred} does not match the "
            f"recomputed occurrence ({expected_occurred}) (group 48)"
        )

    expected_selected_pair: tuple[str, str] | None = None
    expected_selection_draw: int | None = None
    # Mathematically guaranteed exactly as `phases.py` documents: expected_occurred is True only
    # when expected_total_weight > 0 (zero weight forces probability 0, forcing occurred False
    # for any draw), so this branch can never call `randrange(0)`.
    if expected_occurred and expected_total_weight > 0:
        passing_weights = tuple(
            dyad_weight_bps(
                tension_bps=dyad_by_pair[p].tension_bps, grievance_bps=dyad_by_pair[p].grievance_bps
            )
            for p in expected_passing_pairs
        )
        expected_selection_draw = outbreak_rng.randrange(expected_total_weight)
        try:
            selected_index = select_candidate_index(
                selection_draw=expected_selection_draw, weights_bps=passing_weights
            )
            expected_selected_pair = expected_passing_pairs[selected_index]
        except (ValueError, IndexError):
            expected_selected_pair = None

    if outbreak.selection_draw != expected_selection_draw:
        problems.append(
            f"foreign_affairs.outbreak.selection_draw={outbreak.selection_draw} does not match "
            f"the redrawn value ({expected_selection_draw}) (group 48)"
        )
    reported_selected_pair = (
        (outbreak.selected_country_a, outbreak.selected_country_b)
        if outbreak.selected_country_a is not None
        else None
    )
    if reported_selected_pair != expected_selected_pair:
        problems.append(
            f"foreign_affairs.outbreak selected pair {reported_selected_pair!r} does not match "
            f"the recomputed selection {expected_selected_pair!r} (group 48)"
        )

    # ---- Group 52: an outbreak may never be attributed to a sub-floor dyad ---------------
    # Fix-forward 7b: the frozen plan's group 52 ("both floors") names this clause explicitly --
    # "no outbreak occurred from a dyad whose raw_dyad_weight_bps was below
    # MIN_OUTBREAK_WEIGHT_BPS" -- as a check distinct from group 48's RNG-redraw comparison
    # above. That comparison already catches this case indirectly (a sub-floor dyad forces
    # total_weight_bps to exclude it, so expected_occurred is False and every downstream field
    # mismatches), but only ever as a "(group 48)" disagreement; this direct check on the
    # REPORT's own claimed pair gives the boundary its own explicit, attributable signal,
    # independent of whether the RNG-derived expectation happens to agree.
    if (
        outbreak.occurred
        and outbreak.selected_country_a is not None
        and outbreak.selected_country_b is not None
    ):
        reported_selected_pair_for_floor_check = (
            outbreak.selected_country_a,
            outbreak.selected_country_b,
        )
        selected_pair_dyad = dyad_by_pair.get(reported_selected_pair_for_floor_check)
        if selected_pair_dyad is not None:
            reported_pair_weight = dyad_weight_bps(
                tension_bps=selected_pair_dyad.tension_bps,
                grievance_bps=selected_pair_dyad.grievance_bps,
            )
            if not passes_pressure_floor(raw_weight_bps=reported_pair_weight):
                problems.append(
                    "foreign_affairs.outbreak selected pair "
                    f"{reported_selected_pair_for_floor_check!r} has raw weight "
                    f"{reported_pair_weight}, below MIN_OUTBREAK_WEIGHT_BPS "
                    f"({MIN_OUTBREAK_WEIGHT_BPS}) -- no outbreak may be attributed to a "
                    "sub-floor dyad (group 52)"
                )

    expected_new_conflict_id: str | None = None
    if expected_selected_pair is not None:
        expected_new_conflict_id = (
            f"{expected_selected_pair[0]}__{expected_selected_pair[1]}__t{opening_state.turn}"
        )
    if outbreak.conflict_id != expected_new_conflict_id:
        problems.append(
            f"foreign_affairs.outbreak.conflict_id={outbreak.conflict_id!r} does not match the "
            f"recomputed conflict id ({expected_new_conflict_id!r}) (group 46/48)"
        )
    expected_opened_turn = opening_state.turn if expected_new_conflict_id is not None else None
    if outbreak.opened_turn != expected_opened_turn:
        problems.append(
            f"foreign_affairs.outbreak.opened_turn={outbreak.opened_turn!r} does not match "
            f"the recomputed value ({expected_opened_turn!r}) (group 46)"
        )

    # Group 46, new-conflict initialization: re-derived from the AUTHORED dyad, independent of
    # whatever the outbreak row itself claims -- so a self-consistent-but-fabricated outbreak row
    # (matching its own initial_* fields to each other but not to the real dyad) is still caught.
    if expected_selected_pair is not None:
        selected_dyad = dyad_by_pair.get(expected_selected_pair)
        if selected_dyad is None:
            problems.append(
                f"foreign_affairs.outbreak selected pair {expected_selected_pair!r} is not an "
                "opening_state dyad (group 46)"
            )
        else:
            expected_initial_intensity = initial_intensity_bps(
                tension_bps=selected_dyad.tension_bps
            )
            if (
                outbreak.initial_intensity_bps != expected_initial_intensity
                or outbreak.initial_position_bps != 0
                or outbreak.initial_exhaustion_a_bps != 0
                or outbreak.initial_exhaustion_b_bps != 0
                or outbreak.initial_readiness_bps != 0
            ):
                problems.append(
                    "foreign_affairs.outbreak's initial_* fields do not match the recomputed "
                    f"outbreak initialization (expected intensity {expected_initial_intensity}, "
                    "position/exhaustion_a/exhaustion_b/readiness all 0) (group 46)"
                )

    # ---- Group 47: exact progression-row membership --------------------------------------
    expected_row_ids = set(opening_live_ids)
    if expected_new_conflict_id is not None:
        expected_row_ids.add(expected_new_conflict_id)

    reported_ids = [row.conflict_id for row in foreign_affairs.progressions]
    reported_id_set = set(reported_ids)
    if len(reported_ids) != len(reported_id_set):
        problems.append(
            f"foreign_affairs.progressions has duplicate conflict_id(s): {reported_ids!r} "
            "(group 47)"
        )
    if reported_id_set != expected_row_ids:
        problems.append(
            f"foreign_affairs.progressions ids {sorted(reported_id_set)!r} do not match the "
            f"expected id set {sorted(expected_row_ids)!r} (missing="
            f"{sorted(expected_row_ids - reported_id_set)!r}, extra="
            f"{sorted(reported_id_set - expected_row_ids)!r}) (group 47)"
        )

    # ---- Groups 46/47/48/50/52, per progression row --------------------------------------
    for progression_row in foreign_affairs.progressions:
        existing_conflict = opening_conflicts_by_id.get(progression_row.conflict_id)
        existing_is_live = existing_conflict is not None and _is_live_conflict_status(
            existing_conflict.status
        )
        new_via_outbreak = (
            expected_new_conflict_id is not None
            and expected_new_conflict_id == progression_row.conflict_id
        )

        source_count = int(existing_is_live) + int(new_via_outbreak)
        if source_count == 0:
            problems.append(
                f"conflict {progression_row.conflict_id!r}: matches neither an existing opening conflict "
                "nor a validated outbreak initialization (group 46)"
            )
            continue
        if source_count == 2:
            problems.append(
                f"conflict {progression_row.conflict_id!r}: matches BOTH an existing opening conflict and "
                "a validated outbreak initialization -- ambiguous provenance (group 46)"
            )
            continue

        # ---- group 46: the one matched source's opening values, and immutable fields ----
        aggressor: str | None
        defender: str | None
        aim_a: WarAim | None
        aim_b: WarAim | None
        if existing_is_live:
            assert existing_conflict is not None
            country_a, country_b = existing_conflict.country_a, existing_conflict.country_b
            aggressor, defender = existing_conflict.aggressor, existing_conflict.defender
            aim_a, aim_b = existing_conflict.aim_a, existing_conflict.aim_b
            opened_turn = existing_conflict.opened_turn

            opening_status = existing_conflict.status
            opening_intensity = existing_conflict.intensity_bps
            opening_position = existing_conflict.position_bps
            opening_exhaustion_a = existing_conflict.exhaustion_a_bps
            opening_exhaustion_b = existing_conflict.exhaustion_b_bps
            opening_readiness = existing_conflict.negotiation_readiness_bps
            opening_ceasefire_run_turns = existing_conflict.ceasefire_run_turns

            if progression_row.opening_status != opening_status:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: opening_status={progression_row.opening_status!r} does "
                    f"not match opening_state's real status ({opening_status!r}) (group 46)"
                )
            if (
                progression_row.opening_intensity_bps != opening_intensity
                or progression_row.opening_position_bps != opening_position
                or progression_row.opening_exhaustion_a_bps != opening_exhaustion_a
                or progression_row.opening_exhaustion_b_bps != opening_exhaustion_b
                or progression_row.opening_readiness_bps != opening_readiness
                or progression_row.opening_ceasefire_run_turns != opening_ceasefire_run_turns
                or progression_row.opened_turn != opened_turn
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: opening_* fields do not match "
                    "opening_state's real conflict (group 46)"
                )
        else:
            assert expected_selected_pair is not None  # new_via_outbreak implies this
            country_a, country_b = expected_selected_pair
            selected_dyad = dyad_by_pair.get(expected_selected_pair)
            aggressor = selected_dyad.aggressor if selected_dyad is not None else None
            defender = selected_dyad.defender if selected_dyad is not None else None
            aim_a = selected_dyad.aim_a if selected_dyad is not None else None
            aim_b = selected_dyad.aim_b if selected_dyad is not None else None
            opened_turn = opening_state.turn

            opening_status = ConflictStatus.ACTIVE
            opening_intensity = outbreak.initial_intensity_bps or 0
            opening_position = outbreak.initial_position_bps or 0
            opening_exhaustion_a = outbreak.initial_exhaustion_a_bps or 0
            opening_exhaustion_b = outbreak.initial_exhaustion_b_bps or 0
            opening_readiness = outbreak.initial_readiness_bps or 0
            opening_ceasefire_run_turns = 0

            if progression_row.opening_status is not ConflictStatus.ACTIVE:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: a conflict opened this turn must have "
                    f"opening_status=ACTIVE, not {progression_row.opening_status!r} (group 46)"
                )
            if (
                progression_row.opening_intensity_bps != opening_intensity
                or progression_row.opening_position_bps != opening_position
                or progression_row.opening_exhaustion_a_bps != opening_exhaustion_a
                or progression_row.opening_exhaustion_b_bps != opening_exhaustion_b
                or progression_row.opening_readiness_bps != opening_readiness
                or progression_row.opening_ceasefire_run_turns != 0
                or progression_row.opened_turn != opened_turn
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: opening_* fields do not match the validated "
                    "outbreak initialization (group 46)"
                )

        # ---- group 50: capability provenance, both sources alike -------------------------
        profile_a = opening_world.foreign_profiles.get(country_a)
        profile_b = opening_world.foreign_profiles.get(country_b)
        expected_capability_a = profile_a.war_capability_bps if profile_a is not None else None
        expected_capability_b = profile_b.war_capability_bps if profile_b is not None else None
        if profile_a is None or profile_b is None:
            problems.append(
                f"conflict {progression_row.conflict_id!r}: references a country pair "
                f"{(country_a, country_b)!r} not fully present in opening_state.foreign_profiles "
                "(group 50)"
            )
        if (
            progression_row.opening_war_capability_a_bps != expected_capability_a
            or progression_row.opening_war_capability_b_bps != expected_capability_b
        ):
            problems.append(
                f"conflict {progression_row.conflict_id!r}: opening_war_capability_a/b_bps do not match "
                "opening_state.world.foreign_profiles (group 50)"
            )

        # ---- group 47: exact closing projection + immutable-field stability --------------
        closing_conflict = closing_conflicts_by_id.get(progression_row.conflict_id)
        if closing_conflict is None:
            problems.append(
                f"conflict {progression_row.conflict_id!r}: progression progression_row describes a conflict absent "
                "from closing_state (group 47)"
            )
            continue

        if (
            closing_conflict.country_a != country_a
            or closing_conflict.country_b != country_b
            or closing_conflict.aggressor != aggressor
            or closing_conflict.defender != defender
            or closing_conflict.aim_a != aim_a
            or closing_conflict.aim_b != aim_b
            or closing_conflict.war_capability_a_bps != expected_capability_a
            or closing_conflict.war_capability_b_bps != expected_capability_b
            or closing_conflict.opened_turn != opened_turn
        ):
            problems.append(
                f"conflict {progression_row.conflict_id!r}: an immutable field (country pair, aggressor, "
                "defender, authored aim, authored capability, or opened_turn) changed between "
                "opening and closing state (group 47)"
            )

        if (
            progression_row.closing_status != closing_conflict.status
            or progression_row.closing_intensity_bps != closing_conflict.intensity_bps
            or progression_row.closing_position_bps != closing_conflict.position_bps
            or progression_row.closing_exhaustion_a_bps != closing_conflict.exhaustion_a_bps
            or progression_row.closing_exhaustion_b_bps != closing_conflict.exhaustion_b_bps
            or progression_row.closing_readiness_bps != closing_conflict.negotiation_readiness_bps
            or progression_row.closing_ceasefire_run_turns != closing_conflict.ceasefire_run_turns
            or progression_row.resolved_turn != closing_conflict.resolved_turn
        ):
            problems.append(
                f"conflict {progression_row.conflict_id!r}: a closing_* field does not match "
                "closing_state's real conflict (group 47)"
            )

        # ---- group 48/52: redraw + recompute, branching on the AUTHORITATIVE opening status
        # (never the progression_row's own, possibly-tampered, opening_status claim -- already checked above)
        if opening_status is ConflictStatus.ACTIVE:
            jitter_rng = derive_rng(
                opening_state.seed,
                opening_state.turn,
                f"foreign_conflict_progress:{progression_row.conflict_id}",
            )
            expected_jitter = jitter_rng.randint(-PROGRESS_JITTER_BPS, PROGRESS_JITTER_BPS)
            if progression_row.position_jitter_bps != expected_jitter:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: position_jitter_bps={progression_row.position_jitter_bps} "
                    f"does not match the redrawn foreign_conflict_progress stream "
                    f"({expected_jitter}) (group 48)"
                )
            expected_position = closing_position_bps(
                opening_position_bps=opening_position,
                opening_war_capability_a_bps=expected_capability_a or 0,
                opening_war_capability_b_bps=expected_capability_b or 0,
                opening_intensity_bps=opening_intensity,
                position_jitter_bps=expected_jitter,
            )
            expected_gain = exhaustion_gain_bps(opening_intensity_bps=opening_intensity)
            expected_exhaustion_a = min(
                BPS_DENOMINATOR, max(0, opening_exhaustion_a + expected_gain)
            )
            expected_exhaustion_b = min(
                BPS_DENOMINATOR, max(0, opening_exhaustion_b + expected_gain)
            )
            expected_avg = average_exhaustion_bps(
                exhaustion_a_bps=expected_exhaustion_a, exhaustion_b_bps=expected_exhaustion_b
            )
            expected_raw_intensity = raw_closing_intensity_bps(
                opening_intensity_bps=opening_intensity, closing_average_exhaustion_bps=expected_avg
            )
            expected_readiness = closing_readiness_bps(
                closing_average_exhaustion_bps=expected_avg,
                closing_position_bps_value=expected_position,
            )

            gate_open = not is_decisive(
                closing_position_bps_value=expected_position
            ) and ceasefire_gate_open(closing_readiness_bps_value=expected_readiness)
            expected_termination_draw: int | None = None
            if gate_open:
                expected_termination_draw = derive_rng(
                    opening_state.seed,
                    opening_state.turn,
                    f"foreign_conflict_termination:{progression_row.conflict_id}",
                ).randrange(BPS_DENOMINATOR)
            if progression_row.termination_draw != expected_termination_draw:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: termination_draw={progression_row.termination_draw} "
                    f"does not match the guard-correct redraw ({expected_termination_draw}) "
                    "(group 48)"
                )

            if is_decisive(closing_position_bps_value=expected_position):
                expected_status = ConflictStatus.DECIDED
            elif gate_open:
                assert expected_termination_draw is not None
                if settles_rather_than_pauses(
                    closing_readiness_bps_value=expected_readiness,
                    termination_draw=expected_termination_draw,
                ):
                    expected_status = ConflictStatus.SETTLED
                else:
                    expected_status = ConflictStatus.CEASEFIRE
            else:
                expected_status = ConflictStatus.ACTIVE

            expected_closing_intensity = apply_active_intensity_floor(
                raw_intensity_bps=expected_raw_intensity, closing_status=expected_status
            )
            # group 52: the active-intensity floor -- every closing ACTIVE conflict's intensity
            # must be >= MIN_ACTIVE_INTENSITY_BPS; terminal/ceasefire closes may legitimately sit
            # below it (never confuse the two).
            if (
                expected_status is ConflictStatus.ACTIVE
                and expected_closing_intensity < MIN_ACTIVE_INTENSITY_BPS
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: recomputed closing ACTIVE intensity "
                    f"{expected_closing_intensity} is below MIN_ACTIVE_INTENSITY_BPS "
                    f"({MIN_ACTIVE_INTENSITY_BPS}) (group 52)"
                )
            if (
                closing_conflict.status is ConflictStatus.ACTIVE
                and closing_conflict.intensity_bps < MIN_ACTIVE_INTENSITY_BPS
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: closing_state's real ACTIVE intensity "
                    f"{closing_conflict.intensity_bps} is below MIN_ACTIVE_INTENSITY_BPS "
                    f"({MIN_ACTIVE_INTENSITY_BPS}) (group 52)"
                )

            if (
                progression_row.closing_status != expected_status
                or progression_row.closing_position_bps != expected_position
                or progression_row.closing_exhaustion_a_bps != expected_exhaustion_a
                or progression_row.closing_exhaustion_b_bps != expected_exhaustion_b
                or progression_row.closing_readiness_bps != expected_readiness
                or progression_row.closing_intensity_bps != expected_closing_intensity
                or progression_row.closing_ceasefire_run_turns != 0
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: closing_* fields do not match the "
                    "recomputed ACTIVE-branch progression formulas (group 48/52)"
                )

        else:  # opening_status is ConflictStatus.CEASEFIRE -- consumes no randomness at all
            if progression_row.position_jitter_bps != 0:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: a CEASEFIRE-opening progression_row consumes no jitter "
                    f"draw and must store position_jitter_bps=0, got {progression_row.position_jitter_bps} "
                    "(group 48)"
                )
            if progression_row.termination_draw is not None:
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: CEASEFIRE maintenance consumes no "
                    f"termination draw, but termination_draw={progression_row.termination_draw} is stored "
                    "(group 48)"
                )

            decayed_intensity = ceasefire_decayed_intensity_bps(
                opening_intensity_bps=opening_intensity
            )
            expected_exhaustion_a = ceasefire_recovered_exhaustion_bps(
                opening_exhaustion_bps=opening_exhaustion_a
            )
            expected_exhaustion_b = ceasefire_recovered_exhaustion_bps(
                opening_exhaustion_bps=opening_exhaustion_b
            )
            expected_avg = average_exhaustion_bps(
                exhaustion_a_bps=expected_exhaustion_a, exhaustion_b_bps=expected_exhaustion_b
            )
            expected_readiness = closing_readiness_bps(
                closing_average_exhaustion_bps=expected_avg,
                closing_position_bps_value=opening_position,  # frozen during a ceasefire
            )
            provisional_run_turns = opening_ceasefire_run_turns + 1
            expected_status = ceasefire_closing_status(
                closing_readiness_bps_value=expected_readiness,
                closing_ceasefire_run_turns=provisional_run_turns,
            )
            expected_run_turns = (
                0 if expected_status is ConflictStatus.ACTIVE else provisional_run_turns
            )
            expected_closing_intensity = ceasefire_closing_intensity_bps(
                decayed_intensity_bps=decayed_intensity, closing_status=expected_status
            )
            # group 52: a CEASEFIRE -> ACTIVE breakdown must restart at or above the floor.
            if (
                expected_status is ConflictStatus.ACTIVE
                and expected_closing_intensity < MIN_ACTIVE_INTENSITY_BPS
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: a recomputed ceasefire breakdown restarts "
                    f"at intensity {expected_closing_intensity}, below MIN_ACTIVE_INTENSITY_BPS "
                    f"({MIN_ACTIVE_INTENSITY_BPS}) (group 52)"
                )
            if (
                closing_conflict.status is ConflictStatus.ACTIVE
                and closing_conflict.intensity_bps < MIN_ACTIVE_INTENSITY_BPS
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: closing_state's real breakdown intensity "
                    f"{closing_conflict.intensity_bps} is below MIN_ACTIVE_INTENSITY_BPS "
                    f"({MIN_ACTIVE_INTENSITY_BPS}) (group 52)"
                )

            if (
                progression_row.closing_status != expected_status
                or progression_row.closing_position_bps != opening_position
                or progression_row.closing_exhaustion_a_bps != expected_exhaustion_a
                or progression_row.closing_exhaustion_b_bps != expected_exhaustion_b
                or progression_row.closing_readiness_bps != expected_readiness
                or progression_row.closing_intensity_bps != expected_closing_intensity
                or progression_row.closing_ceasefire_run_turns != expected_run_turns
            ):
                problems.append(
                    f"conflict {progression_row.conflict_id!r}: closing_* fields do not match the "
                    "recomputed CEASEFIRE-maintenance formulas (group 48/52)"
                )

    # ---- Group 51: the security-anxiety causal chain, across BOTH reports ---------------
    # Recomputed purely from authoritative state (closing conflicts + opening dyad exposure),
    # never from either report -- so a self-consistent foreign-affairs report and a
    # self-consistent political report that disagree with EACH OTHER both disagree with this
    # independent recomputation, and both are caught.
    exposure_by_pair = {
        (d.country_a, d.country_b): d.player_security_exposure_bps for d in opening_world.dyads
    }
    uncapped_total = 0
    for conflict in closing_world.conflicts:
        if conflict.status is not ConflictStatus.ACTIVE:
            continue
        exposure = exposure_by_pair.get((conflict.country_a, conflict.country_b), 0)
        if exposure == 0:
            continue
        uncapped_total += foreign_conflict_security_anxiety_bps(
            exposure_bps=exposure, intensity_bps=conflict.intensity_bps
        )
    expected_security_contribution = aggregate_security_contribution_bps(
        uncapped_total_bps=uncapped_total
    )
    if expected_security_contribution > 0:
        problems.append(
            "internal: recomputed security contribution "
            f"{expected_security_contribution} is positive -- aggregate_security_contribution_bps "
            "is expected to be negative-only by construction (group 51)"
        )
    political = report.political
    if (
        political is not None
        and political.security_contribution_bps != expected_security_contribution
    ):
        problems.append(
            f"political.security_contribution_bps={political.security_contribution_bps} does "
            "not match the recomputed aggregate security contribution from closing_state's "
            f"ACTIVE conflicts and opening_state's authored exposure ({expected_security_contribution}) "
            "(group 51)"
        )

    return problems


def reconcile_strategic_map_staticness(
    *, opening_state: GameState, closing_state: GameState
) -> list[str]:
    """Group 53 -- the strategic map is authoritative authored content and is IMMUTABLE during a
    campaign (Strategic Military Map, Gate M0).

    No phase writes it, so ANY difference between a history entry's opening and closing map is
    either an engine bug or a tampered save. Never raises: every failure is a returned problem
    string, matching both existing reconcilers.

    Takes no `report` argument. M0 adds no report, and a staticness check has nothing to compare
    a report against -- inventing a parameter to look symmetrical would be dishonest signature
    design.
    """
    opening_map = opening_state.world.strategic_map
    closing_map = closing_state.world.strategic_map

    # Unreachable in a valid 0.14.0 state -- `WorldState.strategic_map` is required, with no
    # default and no `| None`. Guarded anyway: every comparison in this module is on
    # already-parsed models, and a `model_construct`-bypassed or hand-corrupted instance could
    # still smuggle `None` through. A problem string, not an AttributeError, is what "never
    # raises" means here.
    if closing_map is None:
        return [
            "strategic map missing from the closing state (the field is required; a state "
            "that reached reconciliation without one is malformed)"
        ]
    if opening_map is None:
        return [
            "strategic map missing from the opening state (the field is required; a state "
            "that reached reconciliation without one is malformed)"
        ]

    if opening_map.map_id != closing_map.map_id:
        return [
            "strategic map changed during turn resolution: opening map_id "
            f"{opening_map.map_id!r} != closing map_id {closing_map.map_id!r}"
        ]

    opening_bytes = canonical_dumps(opening_map.model_dump(mode="json"))
    closing_bytes = canonical_dumps(closing_map.model_dump(mode="json"))
    if opening_bytes != closing_bytes:
        return [
            "strategic map changed during turn resolution: canonical map bytes differ (the "
            "strategic map is authored, immutable content and no phase may write it)"
        ]

    return []


# ---- Group 54: formation movement, state <-> decisions <-> report -------------------------

_MOVEMENT_ENTRY_PARAMS_TO_ROW_FIELDS: dict[str, str] = {
    "formation_id": "formation_id",
    "formation_display_name": "display_name",
    "branch": "branch",
    "origin_theater_id": "origin_theater_id",
    "origin_theater_display_name": "origin_theater_display_name",
    "destination_theater_id": "destination_theater_id",
    "destination_theater_display_name": "destination_theater_display_name",
}
"""The canonical `formation_moved` params, mapped to the `FormationMovementRow` field each must
equal. Declared once, as data, so group 54's agreement check cannot silently omit a field: adding
a param without adding it here fails the key-set test in `tests/test_military_movement.py`, and
omitting a field from this table would let a tamper test pass, which is exactly why each of the
seven has its own single-field tamper control."""


def _player_formations(state: GameState) -> dict[str, FormationState] | None:
    """The player country's formations, or `None` when the country or its military is missing.

    `None` is unreachable in a valid 0.15.0 state -- `player_military_state_required` (invariants)
    runs before and after every resolution. Guarded anyway, for the same reason
    `reconcile_strategic_map_staticness` guards a missing map: this module compares already-parsed
    models, and a tampered save must produce a problem string, not an AttributeError.
    """
    country = state.world.countries.get(state.world.player_country_id)
    if country is None or country.military is None:
        return None
    return dict(country.military.formations)


def reconcile_formation_movement(
    *,
    opening_state: GameState,
    closing_state: GameState,
    decisions: DecisionSet | None,
    report: TurnReport,
) -> list[str]:
    """Group 54 -- every formation transition is ordered, applied once and reported once.

    Proves the three records of one turn's movement agree: the submitted `DecisionSet`, the
    opening->closing state transition, and the `MovementReport` with its paired `formation_moved`
    entries. A movement can therefore never be reported differently by the report, the API
    projection and the CLI, because all three derive from one row and its paired entry and those
    two are proven identical here.

    Returns problem strings, never raises, matching every existing reconciler.

    `decisions` may legitimately be `None` (a malformed `decisions_json` already recorded its own
    problem upstream). Only the checks that genuinely need a submitted order are skipped then;
    every state-to-state and report-to-state check still runs, so a tampered movement paired with
    an unparseable decision payload is still caught.
    """
    problems: list[str] = []

    movement = report.movement
    if movement is None:
        return [
            "movement report missing from a resolved turn (every resolved turn emits one, empty "
            "on a quiet turn; a report that reached reconciliation without one is malformed) "
            "(group 54)"
        ]

    opening_formations = _player_formations(opening_state)
    closing_formations = _player_formations(closing_state)
    if opening_formations is None or closing_formations is None:
        return [
            "player military state missing from the opening or closing state (the field is "
            "required from ruleset 0.15.0; a state that reached reconciliation without one is "
            "malformed) (group 54)"
        ]

    # ---- 4. the formation roster is closed: none appeared, disappeared or was renamed away ----
    if set(opening_formations) != set(closing_formations):
        appeared = sorted(set(closing_formations) - set(opening_formations))
        disappeared = sorted(set(opening_formations) - set(closing_formations))
        problems.append(
            "the set of formation ids changed during turn resolution: appeared="
            f"{appeared!r}, disappeared={disappeared!r} (movement relocates formations and "
            "creates or destroys none) (group 54)"
        )

    ordered_destinations: dict[str, str] = {}
    if decisions is not None:
        decision = decisions.military_movement_decision()
        if decision is not None:
            ordered_destinations = {
                order.formation_id: order.destination_theater_id for order in decision.orders
            }

    shared_ids = sorted(set(opening_formations) & set(closing_formations))
    transitions: dict[str, tuple[str, str]] = {}
    for formation_id in shared_ids:
        opening = opening_formations[formation_id]
        closing = closing_formations[formation_id]

        # ---- 5. identity never changes during movement resolution -------------------------
        if opening.display_name != closing.display_name:
            problems.append(
                f"formation {formation_id!r} display_name changed during turn resolution: "
                f"{opening.display_name!r} -> {closing.display_name!r} (movement relocates a "
                "formation and never renames it) (group 54)"
            )
        if opening.branch != closing.branch:
            # `getattr(..., "value", ...)`, not `.value`: a tampered save can carry a branch that
            # is not a `FormationBranch` member at all -- `FormationBranch` has exactly one
            # member, so that is the ONLY form a mutated branch can take -- and this reconciler's
            # contract is to return a problem string, never to raise.
            problems.append(
                f"formation {formation_id!r} branch changed during turn resolution: "
                f"{getattr(opening.branch, 'value', opening.branch)!r} -> "
                f"{getattr(closing.branch, 'value', closing.branch)!r} (movement relocates a "
                "formation and never re-roles it) (group 54)"
            )

        if opening.location_theater_id == closing.location_theater_id:
            # ---- 1. an unordered formation stays put; an ordered one must actually move ----
            if formation_id in ordered_destinations:
                problems.append(
                    f"formation {formation_id!r} was ordered to "
                    f"{ordered_destinations[formation_id]!r} but did not move (it is still in "
                    f"{opening.location_theater_id!r}); an accepted order is always applied "
                    "(group 54)"
                )
            continue

        transitions[formation_id] = (
            opening.location_theater_id,
            closing.location_theater_id,
        )

        # ---- 2. a moved formation was ordered to move ------------------------------------
        if decisions is None:
            continue
        if formation_id not in ordered_destinations:
            problems.append(
                f"formation {formation_id!r} moved from {opening.location_theater_id!r} to "
                f"{closing.location_theater_id!r} with no submitted order naming it (a formation "
                "never relocates on its own) (group 54)"
            )
            continue
        # ---- 3. it moved to exactly where it was ordered ---------------------------------
        if closing.location_theater_id != ordered_destinations[formation_id]:
            problems.append(
                f"formation {formation_id!r} was ordered to "
                f"{ordered_destinations[formation_id]!r} but ended in "
                f"{closing.location_theater_id!r} (group 54)"
            )

    problems.extend(_movement_row_problems(opening_state, movement, transitions))
    problems.extend(_movement_entry_problems(report, movement))

    # ---- 8. the map is authored, immutable content -------------------------------------
    # Group 53 proves this independently and in far more detail; asserted here too so a bug that
    # disabled one group is not masked by the other. Deliberately a cheap identity/bytes check
    # rather than a second copy of group 53's reasoning.
    problems.extend(
        f"{problem} (also reported by group 54)"
        for problem in reconcile_strategic_map_staticness(
            opening_state=opening_state, closing_state=closing_state
        )
    )

    return problems


def _movement_row_problems(
    opening_state: GameState,
    movement: MovementReport,
    transitions: dict[str, tuple[str, str]],
) -> list[str]:
    """Checks 6, 7 and row-level faithfulness: rows and real transitions are in bijection, and
    every field of every row matches the authoritative state it claims to describe.

    Names are resolved from the OPENING map. The choice is immaterial -- check 8 proves the two
    maps are byte-identical -- and it is the map the resolver snapshotted from.
    """
    problems: list[str] = []
    rows_by_id = {row.formation_id: row for row in movement.movements}
    opening_formations = _player_formations(opening_state) or {}
    theaters = opening_state.world.strategic_map.theaters

    # ---- 7. every row describes a real transition ------------------------------------
    for formation_id in sorted(set(rows_by_id) - set(transitions)):
        problems.append(
            f"movement report contains a row for formation {formation_id!r}, which did not "
            "change theater during this turn (group 54)"
        )
    # ---- 6. every real transition is reported ----------------------------------------
    for formation_id in sorted(set(transitions) - set(rows_by_id)):
        origin, destination = transitions[formation_id]
        problems.append(
            f"formation {formation_id!r} moved from {origin!r} to {destination!r} but the "
            "movement report contains no row for it (an applied movement is always reported) "
            "(group 54)"
        )

    for formation_id in sorted(set(rows_by_id) & set(transitions)):
        row = rows_by_id[formation_id]
        origin, destination = transitions[formation_id]
        formation = opening_formations[formation_id]

        expected: dict[str, object] = {
            "origin_theater_id": origin,
            "destination_theater_id": destination,
            "display_name": formation.display_name,
            "branch": formation.branch,
            "origin_theater_display_name": (
                theaters[origin].display_name if origin in theaters else None
            ),
            "destination_theater_display_name": (
                theaters[destination].display_name if destination in theaters else None
            ),
        }
        for field_name, expected_value in expected.items():
            actual = getattr(row, field_name)
            if actual != expected_value:
                problems.append(
                    f"movement row for formation {formation_id!r} reports {field_name}="
                    f"{actual!r} but the authoritative value is {expected_value!r} (group 54)"
                )
    return problems


def _movement_entry_problems(report: TurnReport, movement: MovementReport) -> list[str]:
    """Checks 9, 10 and 11: the `formation_moved` entries and the movement rows are one record
    written twice, so no surface can report a movement the others do not.

    A quiet turn needs no special case: zero rows and zero entries satisfy every check below,
    which is exactly the statement that a quiet turn has neither.
    """
    problems: list[str] = []
    entries = [entry for entry in report.entries if entry.reason_id == "formation_moved"]

    # ---- 9. equal cardinality -- no duplicate entry, no missing one -------------------
    if len(entries) != len(movement.movements):
        problems.append(
            f"the turn report carries {len(entries)} 'formation_moved' entr(ies) but the movement "
            f"report carries {len(movement.movements)} row(s); an applied movement is recorded "
            "exactly once in each (group 54)"
        )
        return problems

    rows_by_id = {row.formation_id: row for row in movement.movements}
    for entry in entries:
        if entry.category != "military":
            problems.append(
                f"'formation_moved' entry carries category {entry.category!r}, expected 'military'"
                " (group 54)"
            )
        formation_id = entry.params.get("formation_id")
        row = rows_by_id.get(str(formation_id))
        if row is None:
            problems.append(
                f"'formation_moved' entry names formation {formation_id!r}, which has no row in "
                "the movement report (group 54)"
            )
            continue
        # ---- 10. every entry's seven params equal its row's seven fields --------------
        if set(entry.params) != set(_MOVEMENT_ENTRY_PARAMS_TO_ROW_FIELDS):
            problems.append(
                f"'formation_moved' entry for {formation_id!r} carries params "
                f"{sorted(entry.params)!r}, expected exactly "
                f"{sorted(_MOVEMENT_ENTRY_PARAMS_TO_ROW_FIELDS)!r} (group 54)"
            )
            continue
        for param, field_name in _MOVEMENT_ENTRY_PARAMS_TO_ROW_FIELDS.items():
            row_value = getattr(row, field_name)
            expected = row_value.value if isinstance(row_value, FormationBranch) else row_value
            if entry.params[param] != expected:
                problems.append(
                    f"'formation_moved' entry for {formation_id!r} reports {param}="
                    f"{entry.params[param]!r} but its movement row carries {expected!r} "
                    "(group 54)"
                )
    return problems


def _player_deposits(state: GameState) -> dict[str, str] | None:
    """category value -> `theater_id` for the player's deposits, or `None` when the country or
    its economy is missing.

    `None` is unreachable in a valid state (`player_economy_required`, invariants), and guarded
    anyway for the reason every helper in this module is: a tampered save must produce a problem
    string, never an AttributeError.
    """
    country = state.world.countries.get(state.world.player_country_id)
    if country is None or country.economy is None:
        return None
    return {
        deposit.category.value: deposit.theater_id for deposit in country.economy.resource_deposits
    }


def _reconcile_cabinet(
    *,
    opening_state: GameState,
    closing_state: GameState,
    report: TurnReport,
    decisions: DecisionSet | None,
) -> list[str]:
    """Group 57 -- the cabinet's records of one turn agree, and none of them can be forged alone.

    `CabinetPostReport` already re-derives its own arithmetic from its own stored fields, so a row
    can be internally perfect and still lie about the world: raise a competence, raise the cost to
    match, and the row validates. Only a comparison against the STATE catches that, which is what
    this group is.

    Six checks, each closing a different channel:

    1. **Opening holder and competence, re-derived from `opening_state`** through
       `simulation.cabinet` -- never read off the report. The competence here is the same number
       the chief-of-staff bonus used, so a forged one fails both this group and group 56.
    2. **Closing holder and effectivity, against `closing_state`'s real cabinet**, with every newly
       seated holder at exactly `opening_state.turn + 1`. An appointment that claimed to be
       effective sooner would be one that paid for the turn that hired it.
    3. **`change` re-derived from the holder pair**, so a replacement cannot be filed as an
       appointment, or a dismissal as unchanged.
    4. **Cost re-derived from the OPENING character registry** via `appointment_cost_capital`, and
       **`decision_digest` recomputed from the real submitted decision**. Together these are what
       make a forged price fail: the digest ties the row to one exact decision, and the cost ties
       it to that appointee's authored independence.
    5. **Report ENTRIES correspond one-for-one with the changed rows**, params included, display
       names included. This is what stops the API's `drivers` and the CLI -- which read entries,
       not the subtree -- from describing a cabinet change differently from the report that
       authorised it.
    6. **No decision means no change.** A turn that submitted no `CabinetDecision` must report
       every post `unchanged`, committing nothing: the non-retroactivity backstop.

    `decisions=None` skips only the checks that need the submitted set (the digest half of 4, and
    6); every state-to-report check still runs, so a tampered save with its decisions stripped is
    still caught.
    """
    problems: list[str] = []
    governance = report.governance
    if governance is None:
        return ["governance report missing from a resolved turn (group 57)"]

    opening_player = opening_state.world.countries[opening_state.world.player_country_id]
    closing_player = closing_state.world.countries[closing_state.world.player_country_id]
    opening_characters = opening_state.world.characters
    cabinet_decision = None if decisions is None else decisions.cabinet_decision()
    expected_digest = (
        None if cabinet_decision is None else cabinet_decision_digest(cabinet_decision)
    )

    for row in governance.posts:
        expected_opening = effective_holder_id(
            cabinet=opening_player.cabinet,
            post=row.post,
            resolving_turn=opening_state.turn,
        )
        if row.opening_holder_id != expected_opening:
            problems.append(
                f"governance.posts[{row.post.value!r}]: opening_holder_id="
                f"{row.opening_holder_id!r} does not match opening_state's serving holder "
                f"({expected_opening!r}) (group 57)"
            )
        expected_competence = holder_competence_bps(
            cabinet=opening_player.cabinet,
            characters=opening_characters,
            post=row.post,
            resolving_turn=opening_state.turn,
        )
        if row.opening_holder_competence_bps != expected_competence:
            problems.append(
                f"governance.posts[{row.post.value!r}]: opening_holder_competence_bps="
                f"{row.opening_holder_competence_bps} does not match opening_state "
                f"({expected_competence}) (group 57)"
            )

        closing_cabinet = closing_player.cabinet
        closing_appointment = (
            None if closing_cabinet is None else closing_cabinet.offices.get(row.post)
        )
        actual_closing = None if closing_appointment is None else closing_appointment.character_id
        if row.closing_holder_id != actual_closing:
            problems.append(
                f"governance.posts[{row.post.value!r}]: closing_holder_id="
                f"{row.closing_holder_id!r} does not match closing_state ({actual_closing!r}) "
                "(group 57)"
            )
        actual_effective = (
            None if closing_appointment is None else closing_appointment.effective_from_turn
        )
        if row.closing_effective_from_turn != actual_effective:
            problems.append(
                f"governance.posts[{row.post.value!r}]: closing_effective_from_turn="
                f"{row.closing_effective_from_turn!r} does not match closing_state "
                f"({actual_effective!r}) (group 57)"
            )

        expected_change = _expected_cabinet_change(row.opening_holder_id, row.closing_holder_id)
        if row.change is not expected_change:
            problems.append(
                f"governance.posts[{row.post.value!r}]: change={row.change.value!r} does not "
                f"follow from the holder pair (expected {expected_change.value!r}) (group 57)"
            )

        expected_cost = 0
        if expected_change in (CabinetChange.APPOINTED, CabinetChange.REPLACED):
            appointee = (
                None
                if row.closing_holder_id is None
                else opening_characters.get(row.closing_holder_id)
            )
            if appointee is None:
                problems.append(
                    f"governance.posts[{row.post.value!r}]: closing_holder_id="
                    f"{row.closing_holder_id!r} is not a character of opening_state (group 57)"
                )
                expected_cost = row.capital_committed
            else:
                expected_cost = appointment_cost_capital(independence_bps=appointee.independence)
        if row.capital_committed != expected_cost:
            problems.append(
                f"governance.posts[{row.post.value!r}]: capital_committed="
                f"{row.capital_committed} does not match the appointment cost of "
                f"{row.closing_holder_id!r} ({expected_cost}) (group 57)"
            )

        if (
            decisions is not None
            and row.change is not CabinetChange.UNCHANGED
            and row.decision_digest != expected_digest
        ):
            problems.append(
                f"governance.posts[{row.post.value!r}]: decision_digest="
                f"{row.decision_digest!r} does not match the submitted cabinet decision "
                f"({expected_digest!r}) (group 57)"
            )

    if decisions is not None and cabinet_decision is None:
        for row in governance.posts:
            if row.change is not CabinetChange.UNCHANGED or row.capital_committed != 0:
                problems.append(
                    f"governance.posts[{row.post.value!r}]: reports change={row.change.value!r} "
                    f"committing {row.capital_committed}, but no cabinet decision was submitted "
                    "this turn (group 57)"
                )

    problems.extend(_reconcile_cabinet_entries(governance, report))
    return problems


def _expected_cabinet_change(opening_id: str | None, closing_id: str | None) -> CabinetChange:
    """The truth table, in one place, so slot 1 and reconciliation cannot each have their own."""
    if opening_id == closing_id:
        return CabinetChange.UNCHANGED
    if opening_id is None:
        return CabinetChange.APPOINTED
    if closing_id is None:
        return CabinetChange.DISMISSED
    return CabinetChange.REPLACED


def _reconcile_cabinet_entries(governance: GovernanceReport, report: TurnReport) -> list[str]:
    """Group 57, check 5: the `government` report entries ARE the changed rows, restated.

    Entries matter more here than they do for most reports, because they are the only surface some
    changes reach. `api.projections.build_turn_result` derives its `drivers` from `report.entries`
    and its `ledger` from the expenditure rows, and a dismissal costs nothing, so it has no
    expenditure row at all -- without an entry it would be invisible on the API turn-result and
    history views entirely. Pinning the params here is what keeps that entry honest, including its
    snapshotted display names, which is what lets a ten-turn-old turn render the names it was
    resolved under.
    """
    problems: list[str] = []
    entries = [entry for entry in report.entries if entry.category == "government"]
    changed = [row for row in governance.posts if row.change is not CabinetChange.UNCHANGED]

    if len(entries) != len(changed):
        return [
            f"governance reports {len(changed)} changed post(s) but the turn carries "
            f"{len(entries)} 'government' report entry/entries (group 57)"
        ]

    for row, entry in zip(changed, entries, strict=True):
        expected_reason = f"cabinet_{row.change.value}"
        if entry.reason_id != expected_reason:
            problems.append(
                f"government entry reason_id={entry.reason_id!r} does not match the "
                f"{row.post.value!r} row's change ({expected_reason!r}) (group 57)"
            )
        expected_params: dict[str, str | int] = {
            "post": row.post.value,
            "post_display_name": row.post_display_name,
            "capital_committed": row.capital_committed,
        }
        if row.closing_holder_id is not None:
            expected_params["character_id"] = row.closing_holder_id
            expected_params["character_display_name"] = row.closing_holder_display_name or ""
        if row.opening_holder_id is not None:
            expected_params["outgoing_character_id"] = row.opening_holder_id
            expected_params["outgoing_character_display_name"] = (
                row.opening_holder_display_name or ""
            )
        if dict(entry.params) != expected_params:
            problems.append(
                f"government entry params {dict(entry.params)!r} do not match the "
                f"{row.post.value!r} row ({expected_params!r}) (group 57)"
            )
    return problems


def _transcribed_bargain_will_deal(*, loyalty_bps: int, personal_trust_bps: int) -> bool:
    """Group 58's OWN copy of the gate, deliberately not a call to
    `legislative_bargaining.will_deal`.

    A reconciliation check that calls the function which produced the report cannot fail when that
    function is wrong: it agrees with the defect and certifies it. Transcribing the rule means the
    arithmetic is genuinely performed twice, by two authors, so a mistake in either surfaces as a
    disagreement.

    Sharing the CONSTANTS is a different thing and is allowed: a constant is one number both sides
    read, so a transcription error in the formula still shows up, while duplicating the numbers
    would create a second calibration that could drift from the real one without anything noticing.
    `tests/test_legislative_bargain.py` enforces the boundary with an AST scan rather than trusting
    this docstring.
    """
    return not (
        loyalty_bps < LEGISLATIVE_BARGAIN_LOYALTY_REFUSAL_CEILING_BPS
        and personal_trust_bps < LEGISLATIVE_BARGAIN_TRUST_OVERRIDE_BPS
    )


def _transcribed_bargain_price(
    *, independence_bps: int, ambition_bps: int, personal_trust_bps: int
) -> int:
    """Group 58's own copy of the price formula. See `_transcribed_bargain_will_deal`."""
    return max(
        1,
        LEGISLATIVE_BARGAIN_BASE_PRICE
        + trunc_div_toward_zero(
            independence_bps * LEGISLATIVE_BARGAIN_INDEPENDENCE_PRICE_MAX, BPS_DENOMINATOR
        )
        + trunc_div_toward_zero(
            ambition_bps * LEGISLATIVE_BARGAIN_AMBITION_PRICE_MAX, BPS_DENOMINATOR
        )
        - trunc_div_toward_zero(
            personal_trust_bps * LEGISLATIVE_BARGAIN_TRUST_DISCOUNT_MAX, BPS_DENOMINATOR
        ),
    )


def _endorsed_party_id_from_opening(
    opening_state: GameState, decisions: DecisionSet | None
) -> str | None:
    """Which party the submitted bargain endorsed, re-derived from opening state by transcription.

    Used both by group 58 and by the amendment-vote re-derivation, so reconciliation's independent
    view of the vote includes the endorsement rather than expecting an un-endorsed tally and
    reporting every endorsed row as wrong.
    """
    if decisions is None:
        return None
    decision = decisions.legislative_bargain_decision()
    if decision is None:
        return None
    character = opening_state.world.characters.get(decision.character_id)
    if character is None or character.party_id is None:
        return None
    if not _transcribed_bargain_will_deal(
        loyalty_bps=character.loyalty, personal_trust_bps=character.personal_trust
    ):
        return None
    return character.party_id


def _reconcile_legislative_bargain(
    *,
    opening_state: GameState,
    closing_state: GameState,
    report: TurnReport,
    decisions: DecisionSet | None,
) -> list[str]:
    """Group 58 (characters slice) -- the legislative bargain's records all agree, checked against
    an INDEPENDENT re-derivation rather than against the engine's own answer.

    1. **Counterparty and price re-derived from `opening_state`'s character registry** by
       transcribing the formulas (see `_transcribed_bargain_price`), never by calling
       `legislative_bargaining`. This is the check that can actually catch a wrong price.
    2. **`proposal_kind` names a decision really present** in the submitted set, and
       `proposal_display_name` is the authored label for it -- so a forged row cannot rename a
       proposal in the historical record.
    3. **Outcome re-derived from the gate**, with `asking_price` present exactly when accepted,
       `capital_committed` equal to that price, and `endorsement_bps` following the outcome.
    4. **Every bloc's `endorsement_bps` is the constant for the endorsed party's blocs and `0`
       everywhere else, in every chamber** -- and equals it EXACTLY ONCE. Comparing against
       `LEGISLATIVE_ENDORSEMENT_BPS` itself rather than against a tally is what makes a double
       application detectable: `2 x 2,000` would often vanish into the `final` clamp on an
       already-supportive bloc, so a check that only replayed the clamped sum could not see it.
    5. **The `LEGISLATIVE_BARGAIN` ledger row is present iff accepted**, unique, untargeted, and
       equal to the re-derived price.
    6. **The report ENTRY corresponds one-for-one with the row**, params and snapshotted names
       included -- and a refusal's params carry NO monetary keys, which is what stops the deleted
       counteroffer from reappearing as display text.
    7. **No decision means no bargain anywhere**: no row, no entry, no ledger row, no non-zero
       endorsement. The non-retroactivity backstop.
    8. **The character registry is untouched.** This slice reads `personal_trust` and never writes
       it; a later slice is the only writer.
    """
    problems: list[str] = []
    legislative = report.legislative
    if legislative is None:
        return problems

    rows = legislative.bargains
    decision = decisions.legislative_bargain_decision() if decisions is not None else None

    # (8) Trust is read, never written by this slice.
    if opening_state.world.characters != closing_state.world.characters:
        problems.append(
            "the character registry changed during a turn, but no mechanic in this ruleset writes "
            "to it (group 58)"
        )

    ledger_rows = (
        [
            row
            for row in report.political_capital.expenditures
            if row.category is CapitalExpenditureCategory.LEGISLATIVE_BARGAIN
        ]
        if report.political_capital is not None
        else []
    )
    entries = [
        entry for entry in report.entries if entry.reason_id.startswith("legislative_bargain_")
    ]

    if decisions is not None and decision is None:
        # (7) Nothing was submitted, so nothing may be reported.
        if rows:
            problems.append(
                f"the turn reports {len(rows)} legislative bargain(s) but submitted none (group 58)"
            )
        if entries:
            problems.append(
                f"the turn carries {len(entries)} legislative-bargain entry/entries but submitted "
                "no bargain (group 58)"
            )
        if ledger_rows:
            problems.append(
                "the turn carries a LEGISLATIVE_BARGAIN expenditure row but submitted no bargain "
                "(group 58)"
            )
        for bloc in legislative.blocs:
            if bloc.endorsement_bps != 0:
                problems.append(
                    f"bloc ({bloc.party_id!r}, {bloc.bloc_id!r}) carries "
                    f"endorsement_bps={bloc.endorsement_bps} on a turn with no bargain (group 58)"
                )
        return problems

    if decision is None:
        # `decisions=None`: the submitted set is unavailable, so only state-to-report checks run.
        return problems

    if len(rows) != 1:
        problems.append(
            f"the turn submitted a legislative bargain but reports {len(rows)} row(s) (group 58)"
        )
        return problems
    row = rows[0]

    character = opening_state.world.characters.get(decision.character_id)
    if character is None:
        problems.append(
            f"the submitted bargain names {decision.character_id!r}, who is not in opening_state's "
            "character registry (group 58)"
        )
        return problems

    if row.character_id != decision.character_id:
        problems.append(
            f"bargain row names {row.character_id!r} but the submitted decision named "
            f"{decision.character_id!r} (group 58)"
        )
    if row.character_display_name != character.display_name:
        problems.append(
            f"bargain row character_display_name={row.character_display_name!r} does not match "
            f"opening_state ({character.display_name!r}) (group 58)"
        )
    if row.party_id != character.party_id:
        problems.append(
            f"bargain row party_id={row.party_id!r} does not match the counterparty's opening "
            f"party ({character.party_id!r}) (group 58)"
        )

    # (2) The named proposal was really submitted, and the label is the authored one.
    submitted_kinds = {d.kind for d in decisions.decisions} if decisions is not None else set()
    if decision.proposal_kind not in submitted_kinds:
        problems.append(
            f"the bargain names a {decision.proposal_kind!r} proposal that the submitted set does "
            "not carry (group 58)"
        )
    if row.proposal_kind != decision.proposal_kind:
        problems.append(
            f"bargain row proposal_kind={row.proposal_kind!r} does not match the submitted "
            f"{decision.proposal_kind!r} (group 58)"
        )
    expected_label = LEGISLATIVE_PROPOSAL_DISPLAY_NAMES.get(row.proposal_kind)
    if row.proposal_display_name != expected_label:
        problems.append(
            f"bargain row proposal_display_name={row.proposal_display_name!r} is not the authored "
            f"label for {row.proposal_kind!r} ({expected_label!r}) (group 58)"
        )

    # (1) and (3): the gate and the price, transcribed.
    expected_deal = _transcribed_bargain_will_deal(
        loyalty_bps=character.loyalty, personal_trust_bps=character.personal_trust
    )
    expected_outcome = (
        LegislativeBargainOutcome.ACCEPTED
        if expected_deal
        else LegislativeBargainOutcome.REFUSED_WILL_NOT_DEAL
    )
    if row.outcome is not expected_outcome:
        problems.append(
            f"bargain row outcome={row.outcome.value!r} does not match the re-derived gate "
            f"({expected_outcome.value!r}) (group 58)"
        )
    expected_price = (
        _transcribed_bargain_price(
            independence_bps=character.independence,
            ambition_bps=character.ambition,
            personal_trust_bps=character.personal_trust,
        )
        if expected_deal
        else None
    )
    if row.asking_price != expected_price:
        problems.append(
            f"bargain row asking_price={row.asking_price!r} does not match the re-derived price "
            f"({expected_price!r}) (group 58)"
        )
    expected_committed = expected_price if expected_deal and expected_price is not None else 0
    if row.capital_committed != expected_committed:
        problems.append(
            f"bargain row capital_committed={row.capital_committed} does not match the re-derived "
            f"commitment ({expected_committed}) (group 58)"
        )
    expected_endorsement = LEGISLATIVE_ENDORSEMENT_BPS if expected_deal else 0
    if row.endorsement_bps != expected_endorsement:
        problems.append(
            f"bargain row endorsement_bps={row.endorsement_bps} does not match the re-derived "
            f"outcome ({expected_endorsement}) (group 58)"
        )

    # (4) Every bloc, every chamber, exactly once.
    endorsed_party = character.party_id if expected_deal else None
    for bloc in legislative.blocs:
        expected_bloc = LEGISLATIVE_ENDORSEMENT_BPS if bloc.party_id == endorsed_party else 0
        if bloc.endorsement_bps != expected_bloc:
            problems.append(
                f"bloc ({bloc.party_id!r}, {bloc.bloc_id!r}) in chamber {bloc.chamber.value!r} "
                f"carries endorsement_bps={bloc.endorsement_bps}, expected {expected_bloc} "
                "(group 58)"
            )

    # (5) The ledger row.
    if expected_committed > 0:
        if len(ledger_rows) != 1:
            problems.append(
                f"an accepted bargain must produce exactly one LEGISLATIVE_BARGAIN expenditure "
                f"row, got {len(ledger_rows)} (group 58)"
            )
        elif ledger_rows[0].political_capital != expected_committed:
            problems.append(
                f"the LEGISLATIVE_BARGAIN expenditure row carries "
                f"{ledger_rows[0].political_capital} but the re-derived price is "
                f"{expected_committed} (group 58)"
            )
        elif ledger_rows[0].party_id is not None or ledger_rows[0].bloc_id is not None:
            problems.append(
                "the LEGISLATIVE_BARGAIN expenditure row must be untargeted -- identity lives on "
                "the bargain report, not the ledger (group 58)"
            )
    elif ledger_rows:
        problems.append(
            "a refused bargain must produce no LEGISLATIVE_BARGAIN expenditure row (group 58)"
        )

    # (6) The entry, params pinned exactly.
    problems.extend(_reconcile_legislative_bargain_entry(row, entries))
    return problems


def _reconcile_legislative_bargain_entry(
    row: LegislativeBargainReport, entries: list[TurnReportEntry]
) -> list[str]:
    """Group 58, check 6: the bargain's report entry IS its row, restated.

    The entry is the only surface a REFUSAL reaches: it commits no capital, so it has no expenditure
    row, and `api.projections.build_turn_result` builds `drivers` from entries and `ledger` from
    expenditure rows. Without this entry a player who approached a leader and was turned down would
    see a turn in which nothing happened.

    The refused param set is a strict subset of the accepted one, omitting `asking_price` and
    `endorsement_bps`. Pinning it by EQUALITY rather than checking for the absence of particular
    keys is what makes that robust: a refusal has no field in which a price could travel at all, so
    no renderer can state one, and any newly added monetary key fails here rather than leaking.
    """
    if len(entries) != 1:
        return [
            f"a submitted bargain must produce exactly one report entry, got {len(entries)} "
            "(group 58)"
        ]
    entry = entries[0]
    expected_reason = f"legislative_bargain_{row.outcome.value}"
    if entry.reason_id != expected_reason:
        return [
            f"legislative-bargain entry reason_id={entry.reason_id!r} does not match the row's "
            f"outcome ({expected_reason!r}) (group 58)"
        ]
    expected_params: dict[str, str | int] = {
        "character_id": row.character_id,
        "character_display_name": row.character_display_name,
        "party_id": row.party_id,
        "party_display_name": row.party_display_name,
        "proposal_kind": row.proposal_kind,
        "proposal_display_name": row.proposal_display_name,
    }
    if row.outcome is LegislativeBargainOutcome.ACCEPTED and row.asking_price is not None:
        expected_params["asking_price"] = row.asking_price
        expected_params["endorsement_bps"] = row.endorsement_bps
    if dict(entry.params) != expected_params:
        return [
            f"legislative-bargain entry params {dict(entry.params)!r} do not match the row "
            f"({expected_params!r}) (group 58)"
        ]
    return []


def reconcile_deposit_locations(
    *, opening_state: GameState, closing_state: GameState, report: TurnReport
) -> list[str]:
    """Group 55 -- a deposit's location is fixed, and the report says where it really is.

    Three records of the same fact are compared: the opening state, the closing state, and the
    resource report's rows. Deposits are IMMOBILE -- nothing in this ruleset can move one -- so
    the three must agree exactly, and a turn that appeared to relocate a country's gold would be
    caught here rather than showing up later as a report that disagrees with the map.

    Deliberately narrow. Whether the named theater exists and is owned by the country is
    `simulation.invariants`' job (`resource_deposit_theater_unknown`,
    `resource_deposit_theater_not_owned_by_country`), which runs before and after every
    resolution; this reconciler does not re-implement that judgement. It does look the theater up,
    because the display-name comparison needs it -- and reports a problem rather than raising when
    the lookup fails, so a tampered pair of (state, report) is still a problem string.

    Returns problem strings, never raises, matching every existing reconciler.
    """
    problems: list[str] = []

    if report.resources is None:
        return ["turn report has no resources report to reconcile deposits against (group 55)"]

    opening = _player_deposits(opening_state)
    closing = _player_deposits(closing_state)
    if opening is None or closing is None:
        return [
            "player country or its economy is missing, so deposit locations cannot be "
            "reconciled (group 55)"
        ]

    if opening != closing:
        moved = sorted(
            category
            for category in set(opening) | set(closing)
            if opening.get(category) != closing.get(category)
        )
        problems.append(
            f"deposit location(s) changed during the turn for {moved!r}; deposits are immobile "
            "in this ruleset (group 55)"
        )

    reported = {row.category.value: row for row in report.resources.deposits}
    if set(reported) != set(closing):
        problems.append(
            f"the resource report covers {sorted(reported)!r} but the closing state holds "
            f"{sorted(closing)!r} (group 55)"
        )

    theaters = closing_state.world.strategic_map.theaters
    for category in sorted(set(reported) & set(closing)):
        row = reported[category]
        expected_theater = closing[category]
        if row.theater_id != expected_theater:
            problems.append(
                f"the resource report places {category} at {row.theater_id!r} but the closing "
                f"state holds it at {expected_theater!r} (group 55)"
            )
            continue
        theater = theaters.get(expected_theater)
        if theater is None:
            problems.append(
                f"{category} is held at {expected_theater!r}, which the closing state's map does "
                "not contain (group 55)"
            )
            continue
        if row.theater_display_name != theater.display_name:
            problems.append(
                f"the resource report names {category}'s theater {row.theater_display_name!r} "
                f"but the map calls it {theater.display_name!r} (group 55)"
            )

    return problems
