"""Report-vs-state reconciliation for the political and legislative domains.

`TurnReport` is constructed from reports only and has no `GameState` reference (the same
structural limit that produced Phase 2C2's late deviation — see F1) — so a check that needs
BOTH a report and the state it describes cannot live as a `TurnReport` validator. `resolve_turn`
already holds, in one scope, both the caller's untouched input `state` and the mutated `working`
copy (F15); this module's one function takes both, plus the report and the actual submitted
`DecisionSet`, and returns every disagreement it finds — never raising itself.

**Groups 1–11 (Phase 3A) are unchanged.** `FinanceReport.closing_cash` vs `TreasuryState
.cash_on_hand` remains a real, pre-existing, out-of-scope gap (F8, FIN-1).

**Groups 12–18 (Phase 3B1, R8) are new.** Group 16 is the one place this module reads
`finance.tax_policy`/`finance.spending_plan` — not balances, only policy — to prove the budget
gate actually gated against the real submitted command, not merely against report prose.

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

from app.simulation.constitution import constitution_digest
from app.simulation.decisions import BudgetDecision, DecisionSet, budget_decision_digest
from app.simulation.legislature import LegislativeChamber, LegislativeOutcome
from app.simulation.report import TurnReport
from app.simulation.state import GameState, SpendingCategory

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

_TAX_RATE_FIELDS = ("personal_income_rate_bps", "corporate_rate_bps", "consumption_rate_bps")
"""The three targetable `TaxPolicyState` fields — deliberately excludes `compliance_rate_bps`,
which no `BudgetDecision` can ever target (group 16)."""


def reconcile_political_and_legislative_report(
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

    # Groups 7/8: each of the nine ConstitutionSummary fields vs opening AND closing
    # ConstitutionState, independently -- (R7) not just the digest.
    for field_name in _CONSTITUTION_FIELDS:
        report_value = getattr(political.constitution, field_name)
        opening_value = getattr(opening_politics.constitution, field_name)
        closing_value = getattr(closing_politics.constitution, field_name)
        if report_value != opening_value:
            problems.append(
                f"political.constitution.{field_name}={report_value!r} does not match "
                f"opening_state constitution.{field_name}={opening_value!r}"
            )
        if report_value != closing_value:
            problems.append(
                f"political.constitution.{field_name}={report_value!r} does not match "
                f"closing_state constitution.{field_name}={closing_value!r}"
            )

    # Group 9: constitution_digest vs constitution_digest(opening) and (closing) -- (R7) digest
    # equality is checked IN ADDITION TO, never instead of, groups 7/8's field-by-field checks.
    expected_opening_digest = constitution_digest(opening_politics.constitution)
    if political.constitution.constitution_digest != expected_opening_digest:
        problems.append(
            "political.constitution.constitution_digest="
            f"{political.constitution.constitution_digest!r} does not match "
            f"constitution_digest(opening_state.constitution)={expected_opening_digest!r}"
        )
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

    # Group 12: legislature presence (report vs BOTH states) and D7 staticness. Whether a state's
    # OWN legislature matches its OWN constitution is Pydantic's job at parse time
    # (`PoliticalState._legislature_presence_matches_the_constitution`) and `check_invariants`'
    # backstop against a `model_construct` bypass -- reconciliation's job is only ever "does the
    # REPORT describe the REAL state", so this group compares the report against both states,
    # never a state against itself.
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
    if opening_legislature != closing_legislature:
        problems.append(
            "politics.legislature was mutated during resolution (D7: legislature composition is "
            "static in Phase 3B1) -- opening and closing legislatures differ"
        )

    # Groups 13-15 need a real, static legislature to compare rows against; if either is absent
    # (a NO_PROPOSAL/decree turn for a legislature-less country) or was just found to differ,
    # group 12 has already said everything there is to say about it.
    if (
        legislative.chambers
        and opening_legislature is not None
        and opening_legislature == closing_legislature
    ):
        chambers_by_id = {chamber.chamber: chamber for chamber in opening_legislature.chambers}

        # Group 13: chamber identity, matched by `chamber`, never tuple position.
        report_chamber_ids = [row.chamber for row in legislative.chambers]
        if len(report_chamber_ids) != len(set(report_chamber_ids)):
            problems.append("legislative.chambers contains a duplicate chamber identity")
        state_chamber_ids = set(chambers_by_id)
        for missing_chamber in sorted(state_chamber_ids - set(report_chamber_ids)):
            problems.append(
                f"legislative.chambers is missing a row for chamber {missing_chamber.value!r}, "
                "which the state legislature has"
            )
        for invented_chamber in sorted(set(report_chamber_ids) - state_chamber_ids):
            problems.append(
                f"legislative.chambers reports a row for chamber {invented_chamber.value!r}, "
                "which the state legislature does not have"
            )
        for chamber_row in legislative.chambers:
            state_chamber = chambers_by_id.get(chamber_row.chamber)
            if state_chamber is None:
                continue  # already reported above as "invented"
            if chamber_row.total_seats != state_chamber.total_seats:
                problems.append(
                    f"legislative chamber {chamber_row.chamber.value!r}: total_seats="
                    f"{chamber_row.total_seats} does not match state total_seats="
                    f"{state_chamber.total_seats}"
                )

        # Groups 14/15: party/bloc identity + seats, matched by (party_id, bloc_id, chamber) --
        # never row position. `state_rows` only contains chambers a bloc actually holds seats in
        # (mirroring `LegislativeBlocState.seats`'s own "omit what you don't hold" convention and
        # slot 1's identical row-inclusion rule), so no legitimately-zero-seat pairing is ever
        # flagged as "missing".
        state_rows: dict[
            tuple[str, str, LegislativeChamber], tuple[str, int, int, int, int, int]
        ] = {}
        for party in opening_legislature.parties:
            for bloc in party.blocs:
                for seat_entry in bloc.seats:
                    state_rows[(party.id, bloc.id, seat_entry.chamber)] = (
                        party.government_role.value,
                        bloc.government_relationship_bps,
                        bloc.discipline_bps,
                        bloc.tax_preference_bps,
                        bloc.spending_preference_bps,
                        seat_entry.seats,
                    )

        report_row_keys = [(row.party_id, row.bloc_id, row.chamber) for row in legislative.blocs]
        if len(report_row_keys) != len(set(report_row_keys)):
            problems.append(
                "legislative.blocs contains a duplicate (party_id, bloc_id, chamber) row"
            )

        for row in legislative.blocs:
            key = (row.party_id, row.bloc_id, row.chamber)
            state_row = state_rows.get(key)
            if state_row is None:
                problems.append(
                    f"legislative.blocs reports a row for ({row.party_id!r}, {row.bloc_id!r}) in "
                    f"chamber {row.chamber.value!r}, which the state legislature does not seat "
                    "there"
                )
                continue
            role_value, relationship_bps, discipline_bps, tax_pref, spending_pref, seats = state_row
            if row.government_role.value != role_value:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): government_role={row.government_role.value!r} does "
                    f"not match state government_role={role_value!r}"
                )
            if row.government_relationship_bps != relationship_bps:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): government_relationship_bps="
                    f"{row.government_relationship_bps} does not match state "
                    f"government_relationship_bps={relationship_bps}"
                )
            if row.discipline_bps != discipline_bps:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): discipline_bps={row.discipline_bps} does not match "
                    f"state discipline_bps={discipline_bps}"
                )
            if row.tax_preference_bps != tax_pref:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): tax_preference_bps={row.tax_preference_bps} does "
                    f"not match state tax_preference_bps={tax_pref}"
                )
            if row.spending_preference_bps != spending_pref:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): spending_preference_bps="
                    f"{row.spending_preference_bps} does not match state "
                    f"spending_preference_bps={spending_pref}"
                )
            # Group 15 (seats): the one state-held apportionment input. required_yes_seats/
            # numerator/base_seats/remainder/bonus_seat/supporting_seats are proven by
            # composition -- see the module docstring.
            if row.seats != seats:
                problems.append(
                    f"legislative.blocs row ({row.party_id!r}, {row.bloc_id!r}, "
                    f"{row.chamber.value!r}): seats={row.seats} does not match state seats={seats}"
                )

        for missing_party_id, missing_bloc_id, missing_chamber in sorted(
            set(state_rows) - set(report_row_keys), key=lambda k: (k[0], k[1], k[2].value)
        ):
            problems.append(
                f"legislative.blocs is missing a row for ({missing_party_id!r}, "
                f"{missing_bloc_id!r}) in chamber {missing_chamber.value!r}, which the state "
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

    # Group 17: political-capital ordering. Duplicates some of what `LegislativeReport`'s own
    # validators and `TurnReport`'s legislative cross-validators already prove report-internally
    # -- kept here too, explicitly, because reconciliation's unique value is comparing against the
    # REAL state, which those validators structurally cannot reach.
    if legislative.opening_political_capital != opening_politics.political_capital:
        problems.append(
            f"legislative.opening_political_capital={legislative.opening_political_capital} does "
            f"not match opening_state politics.political_capital="
            f"{opening_politics.political_capital}"
        )
    if legislative.political_capital_committed != political.political_capital_spent:
        problems.append(
            f"legislative.political_capital_committed={legislative.political_capital_committed} "
            f"does not match political.political_capital_spent="
            f"{political.political_capital_spent}"
        )
    if legislative.political_capital_committed > legislative.opening_political_capital:
        problems.append(
            f"legislative.political_capital_committed={legislative.political_capital_committed} "
            f"exceeds legislative.opening_political_capital="
            f"{legislative.opening_political_capital}"
        )
    # Approved clamp order, unchanged: closing = min(capacity, opening - committed + regeneration).
    expected_closing_capital = min(
        political.political_capital_capacity,
        legislative.opening_political_capital
        - legislative.political_capital_committed
        + political.political_capital_regeneration,
    )
    if closing_politics.political_capital != expected_closing_capital:
        problems.append(
            f"closing_state politics.political_capital={closing_politics.political_capital} does "
            "not match min(capacity, opening - committed + regeneration)="
            f"{expected_closing_capital}"
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
