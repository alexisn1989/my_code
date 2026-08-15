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

from app.core.money import BPS_DENOMINATOR
from app.core.politics import (
    RELATIONSHIP_DECAY_DENOMINATOR,
    RELATIONSHIP_DECAY_NUMERATOR,
    trunc_div_toward_zero,
)
from app.core.rng import derive_rng
from app.simulation.constitution import constitution_digest
from app.simulation.decisions import (
    BudgetDecision,
    DecisionSet,
    bloc_relationship_investment_digest,
    budget_decision_digest,
)
from app.simulation.government_survival import (
    MAX_POLLING_UNCERTAINTY_SWING_BPS,
    election_baseline_support_bps,
    legislative_support_bps,
    population_weighted_mean_bps,
)
from app.simulation.legislature import (
    CapitalExpenditureCategory,
    LegislativeChamber,
    LegislativeOutcome,
)
from app.simulation.report import TurnReport
from app.simulation.state import GameState, LegislatureState, SpendingCategory

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

    # Groups 35-40 (plan §8, Gate 3C1): the election report against real state, real seeded RNG,
    # and (§4.4) the exact next_election_turn scheduling table -- never merely against the
    # report's own self-validated story.
    election = report.election
    if election is not None:
        term_limit = opening_politics.constitution.executive_term_limit_terms
        term_limited = (
            term_limit is not None and opening_politics.consecutive_terms_held >= term_limit
        )

        # Group 35: scheduling recompute -- `scheduled` vs the OPENING schedule, and
        # `next_election_turn`'s new-or-unchanged value re-derived per §4.4's table (Gate 3C1's
        # four reachable rows: WIN reschedules by the closing constitution's own interval; a
        # LOSS/TERM_LIMIT_EXIT/non-scheduled turn leaves it frozen -- the two amendment-driven
        # rows are Gate 3C3 scope, unreachable while no amendment mechanism exists).
        expected_scheduled = opening_politics.next_election_turn == closing_state.turn
        if election.scheduled != expected_scheduled:
            problems.append(
                f"election.scheduled={election.scheduled} does not match "
                f"opening_state politics.next_election_turn == closing_state.turn "
                f"({expected_scheduled})"
            )
        if election.scheduled and not term_limited and election.result == "won":
            interval = closing_politics.constitution.national_election_interval_turns
            expected_next = (closing_state.turn + interval) if interval is not None else None
        else:
            expected_next = opening_politics.next_election_turn
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
        # against the OPENING `consecutive_terms_held`/`executive_term_limit_terms`, the values
        # the check was actually run against, never a post-election value.
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
        elif closing_politics.terminal_outcome is not None:
            problems.append(
                f"election.result={election.result!r} does not conclude the game, but "
                f"closing_state carries a terminal_outcome={closing_politics.terminal_outcome!r}"
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

    # An election turn that was NOT scheduled must leave consecutive_terms_held and
    # terminal_outcome exactly as they opened (next_election_turn's own staticness is already
    # proved by group 35 above) -- a no-op election evaluation must be a genuine no-op, proved
    # state-to-state.
    if election is not None and not election.scheduled:
        if closing_politics.consecutive_terms_held != opening_politics.consecutive_terms_held:
            problems.append(
                "election.scheduled=False but closing_state politics.consecutive_terms_held="
                f"{closing_politics.consecutive_terms_held} differs from opening_state's "
                f"{opening_politics.consecutive_terms_held}"
            )
        if closing_politics.terminal_outcome != opening_politics.terminal_outcome:
            problems.append(
                "election.scheduled=False but closing_state politics.terminal_outcome differs "
                "from opening_state's"
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
