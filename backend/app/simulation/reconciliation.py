"""Report-vs-state reconciliation for the political domain (Phase 3A, §9.3).

`TurnReport` is constructed from reports only and has no `GameState` reference (the same
structural limit that produced Phase 2C2's late deviation — see F1) — so a check that needs
BOTH the political report and the state it describes cannot live as a `TurnReport` validator.
`resolve_turn` already holds, in one scope, both the caller's untouched input `state` and the
mutated `working` copy (F15); this module's one function takes both plus the report and returns
every disagreement it finds, never raising itself.

**Political scope only (R3).** `FinanceReport.closing_cash` vs `TreasuryState.cash_on_hand` is a
real pre-existing gap (F8), but unrelated to Phase 3A's approved signals — see the Phase 3A plan's
FIN-1 ticket. Every check below references only `politics`.

**Eleven logical check groups** (§9.3). No fixed total comparison count is claimed: groups 3 and 6
compare an *optional* baseline (both `None`, or three fields each), so any headline number would
tempt tests to assert a count instead of asserting behavior. What is guaranteed is that every
group, and every individual field within a group, is independently corruptible and independently
rejected (see `tests/test_reconciliation.py`, T-R5/T-R6).
"""

from __future__ import annotations

from app.simulation.constitution import constitution_digest
from app.simulation.report import TurnReport
from app.simulation.state import GameState

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


def reconcile_political_report(
    *, opening_state: GameState, closing_state: GameState, report: TurnReport
) -> list[str]:
    """Return every disagreement between what `report.political` claims and what
    `opening_state`/`closing_state` actually hold. Never raises; exact equality only, no formulas
    of its own — `report.political`'s own ten self-validators already proved its internal
    arithmetic is correct (§9.1); this proves the report describes the REAL state, not merely a
    self-consistent one.

    `report.political is None` (the political phase did not run) produces no problems here —
    that case is rejected earlier, by `TurnReport`'s own all-present-or-all-absent rule together
    with `simulation.invariants.check_invariants` requiring player politics.
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

    return problems
