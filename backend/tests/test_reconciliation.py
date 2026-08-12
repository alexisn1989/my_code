"""Tests for `simulation.reconciliation.reconcile_political_and_legislative_report`
(Phase 3A groups 1-11, T-R5/T-R6; Phase 3B1 groups 12-18, R8).

Every corruption below is built with `model_copy(update=...)`, which does NOT re-run
`PoliticalReport`'s own self-validators (Pydantic v2's `model_copy` never validates) — so each
test produces a report that is internally self-consistent per its own ten formula validators
(§9.1) but disagrees with the state it is compared against. That isolates the reconciliation
check specifically: a report can pass every formula check and still be caught here for describing
the wrong turn's political facts.

No fixed comparison count is asserted anywhere in this file (§9.3) — each test instead proves
one specific field is independently corruptible and independently rejected.

The original (groups 1-11) tests below pass `decisions=None` unchanged -- they corrupt only
`political`, never touch `legislative`, and `_resolve_twice()`'s scenario never submits a
`BudgetDecision`, so there is nothing group 16/18 could usefully check against a real
`DecisionSet` there; `None` is exactly what a caller passes when there is genuinely no decision
to reconcile against (see the function's own docstring), and groups 1-15/17 run identically
either way. The new (groups 12-18) tests below build real scenarios with real submitted
decisions specifically to exercise the checks that need one.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.simulation.constitution import ExecutiveSelection, ExecutiveSystem, JudicialReview
from app.simulation.decisions import BudgetDecision, DecisionSet, InfluenceAllocation
from app.simulation.legislature import LegislativeChamber
from app.simulation.reconciliation import reconcile_political_and_legislative_report
from app.simulation.report import EconomicBaselineReport, TurnReport
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR, make_game_state


def _empty_decisions_for(state) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=[]
    )


def _resolve_twice():  # type: ignore[no-untyped-def]
    """Resolve two turns from a fresh state so both an opening-baseline-`None` report (turn 1)
    and an opening-baseline-present report (turn 2) are available for corruption tests."""
    state = make_game_state(turn=0, state_version=0)
    first = resolve_turn(state, _empty_decisions_for(state))
    second = resolve_turn(first.state, _empty_decisions_for(first.state))
    return state, first, second


def test_a_clean_resolution_reconciles_with_no_problems() -> None:
    """Sanity check: the real resolver's own output never trips the reconciliation check —
    everything below corrupts a `model_copy`, never the resolver's real output."""
    state, first, second = _resolve_twice()
    assert (
        reconcile_political_and_legislative_report(
            opening_state=state, closing_state=first.state, report=first.report, decisions=None
        )
        == []
    )
    assert (
        reconcile_political_and_legislative_report(
            opening_state=first.state,
            closing_state=second.state,
            report=second.report,
            decisions=None,
        )
        == []
    )


def test_corrupted_opening_legitimacy_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"opening_legitimacy_bps": first.report.political.opening_legitimacy_bps + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("opening_legitimacy_bps" in p for p in problems)


def test_corrupted_closing_legitimacy_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"closing_legitimacy_bps": first.report.political.closing_legitimacy_bps + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("closing_legitimacy_bps" in p for p in problems)


def test_corrupted_opening_political_capital_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"opening_political_capital": first.report.political.opening_political_capital + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("opening_political_capital" in p for p in problems)


def test_corrupted_closing_political_capital_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"closing_political_capital": first.report.political.closing_political_capital + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("closing_political_capital" in p for p in problems)


def test_opening_baseline_presence_mismatch_is_rejected() -> None:
    """Turn 1's report has `opening_economic_baseline is None`; fabricating one where state has
    none must be rejected on presence alone, before any field comparison."""
    state, first, _ = _resolve_twice()
    assert first.report.political.opening_economic_baseline is None
    fabricated_baseline = EconomicBaselineReport(
        source_turn=0, total_gross_output=1, unemployment_rate_bps=1000
    )
    corrupted_political = first.report.political.model_copy(
        update={"opening_economic_baseline": fabricated_baseline}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("opening_economic_baseline presence" in p for p in problems)


def test_each_opening_baseline_field_is_independently_rejected() -> None:
    """Turn 2's report has a real opening baseline (turn 1's closing) -- corrupt each of its
    three fields independently."""
    state, first, second = _resolve_twice()
    opening_baseline = second.report.political.opening_economic_baseline
    assert opening_baseline is not None

    for field_name, delta in (
        ("source_turn", 1),
        ("total_gross_output", 1),
        ("unemployment_rate_bps", 1),
    ):
        corrupted_baseline = opening_baseline.model_copy(
            update={field_name: getattr(opening_baseline, field_name) + delta}
        )
        corrupted_political = second.report.political.model_copy(
            update={"opening_economic_baseline": corrupted_baseline}
        )
        corrupted_report = second.report.model_copy(update={"political": corrupted_political})
        problems = reconcile_political_and_legislative_report(
            opening_state=first.state,
            closing_state=second.state,
            report=corrupted_report,
            decisions=None,
        )
        assert any(f"opening_economic_baseline.{field_name}" in p for p in problems), field_name


def test_each_closing_baseline_field_is_independently_rejected() -> None:
    state, first, _ = _resolve_twice()
    closing_baseline = first.report.political.closing_economic_baseline

    for field_name, delta in (
        ("source_turn", 1),
        ("total_gross_output", 1),
        ("unemployment_rate_bps", 1),
    ):
        corrupted_baseline = closing_baseline.model_copy(
            update={field_name: getattr(closing_baseline, field_name) + delta}
        )
        corrupted_political = first.report.political.model_copy(
            update={"closing_economic_baseline": corrupted_baseline}
        )
        corrupted_report = first.report.model_copy(update={"political": corrupted_political})
        problems = reconcile_political_and_legislative_report(
            opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
        )
        assert any(f"closing_economic_baseline.{field_name}" in p for p in problems), field_name


def test_each_of_the_nine_constitutional_fields_is_independently_rejected() -> None:
    """(R7) Field-by-field, not just the digest -- each of the nine `ConstitutionSummary` fields
    is corrupted alone, keeping the (now-inconsistent) digest untouched, and each must be caught
    against BOTH opening and closing state."""
    state, first, _ = _resolve_twice()
    corruptions = {
        "executive_system": ExecutiveSystem.PARLIAMENTARY
        if first.report.political.constitution.executive_system != ExecutiveSystem.PARLIAMENTARY
        else ExecutiveSystem.MONARCHICAL,
        "executive_selection": ExecutiveSelection.APPOINTED
        if first.report.political.constitution.executive_selection != ExecutiveSelection.APPOINTED
        else ExecutiveSelection.HEREDITARY,
    }
    for field_name, corrupt_value in corruptions.items():
        corrupted_constitution = first.report.political.constitution.model_copy(
            update={field_name: corrupt_value}
        )
        corrupted_political = first.report.political.model_copy(
            update={"constitution": corrupted_constitution}
        )
        corrupted_report = first.report.model_copy(update={"political": corrupted_political})
        problems = reconcile_political_and_legislative_report(
            opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
        )
        assert any(f"constitution.{field_name}" in p for p in problems), field_name
        # Both opening and closing comparisons fire -- two problems, not one.
        matching = [p for p in problems if f"constitution.{field_name}" in p]
        assert len(matching) == 2, field_name


def test_digest_alone_corrupted_with_fields_intact_is_rejected() -> None:
    """(R7) Digest equality alone is not a substitute for field equality: corrupt ONLY the
    digest string, leaving all nine fields correct, and it must still be caught."""
    state, first, _ = _resolve_twice()
    corrupted_constitution = first.report.political.constitution.model_copy(
        update={"constitution_digest": "0" * 64}
    )
    corrupted_political = first.report.political.model_copy(
        update={"constitution": corrupted_constitution}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("constitution_digest" in p for p in problems)


def test_corrupted_constitutional_order_support_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={
            "constitutional_order_support_bps": (
                first.report.political.constitutional_order_support_bps + 1
            )
        }
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("constitutional_order_support_bps" in p for p in problems)


def test_corrupted_political_capital_capacity_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"political_capital_capacity": first.report.political.political_capital_capacity + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=first.state, report=corrupted_report, decisions=None
    )
    assert any("political_capital_capacity" in p for p in problems)


def test_no_political_report_produces_no_problems() -> None:
    """`report.political is None` is rejected earlier (TurnReport completeness +
    player_politics_required); reconciliation itself is a no-op for that case, not a crash."""
    state, first, _ = _resolve_twice()
    report_without_political = first.report.model_copy(update={"political": None})
    assert (
        reconcile_political_and_legislative_report(
            opening_state=state,
            closing_state=first.state,
            report=report_without_political,
            decisions=None,
        )
        == []
    )


# --- T-R6: constitution/support/capacity are static -- a STATE-side mutation is caught too -----


def test_a_working_copy_mutation_of_a_constitutional_field_is_caught() -> None:
    """(R1/R7) If a hypothetical future bug mutated the working copy's constitution mid-turn, the
    report (built from the untouched opening snapshot) would now disagree with closing state --
    proving groups 7/8 catch STATE-side drift, not just report-side corruption."""
    state, first, _ = _resolve_twice()
    player_id = first.state.world.player_country_id
    player = first.state.world.countries[player_id]
    assert player.politics is not None
    mutated_constitution = player.politics.constitution.model_copy(
        update={
            "judicial_review": JudicialReview.STRONG
            if player.politics.constitution.judicial_review != JudicialReview.STRONG
            else JudicialReview.WEAK
        }
    )
    mutated_politics = player.politics.model_copy(update={"constitution": mutated_constitution})
    mutated_state = first.state.model_copy(
        update={
            "world": first.state.world.model_copy(
                update={
                    "countries": {
                        **first.state.world.countries,
                        player_id: player.model_copy(update={"politics": mutated_politics}),
                    }
                }
            )
        }
    )
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=mutated_state, report=first.report, decisions=None
    )
    assert any("judicial_review" in p for p in problems)


def test_a_working_copy_mutation_of_support_or_capacity_is_caught() -> None:
    state, first, _ = _resolve_twice()
    player_id = first.state.world.player_country_id
    player = first.state.world.countries[player_id]
    assert player.politics is not None
    mutated_politics = player.politics.model_copy(
        update={"political_capital_capacity": player.politics.political_capital_capacity + 1}
    )
    mutated_state = first.state.model_copy(
        update={
            "world": first.state.world.model_copy(
                update={
                    "countries": {
                        **first.state.world.countries,
                        player_id: player.model_copy(update={"politics": mutated_politics}),
                    }
                }
            )
        }
    )
    problems = reconcile_political_and_legislative_report(
        opening_state=state, closing_state=mutated_state, report=first.report, decisions=None
    )
    assert any("political_capital_capacity" in p for p in problems)


# =============================================================================
# Phase 3B1 (R8): groups 12-18
# =============================================================================


def _decisions_with(state, decision: BudgetDecision | None) -> DecisionSet:  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(decision,) if decision is not None else (),
    )


def _tiny_valid_passing_turn():  # type: ignore[no-untyped-def]
    """`tiny_valid.yaml`, a real +5pp personal-income proposal with 50 PC allocated to a
    bicameral bloc (`civic_union/mainstream`, seated in both chambers) -- passes unaided
    regardless (58/100, 33/60), giving a real `PASSED_LEGISLATIVE` report with nonzero committed
    capital and a real bicameral influence allocation to corrupt."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(party_id="civic_union", bloc_id="mainstream", political_capital=50),
        ),
    )
    decisions = _decisions_with(state, decision)
    resolution = resolve_turn(state, decisions)
    return state, resolution, decisions


def _deficit_demo_failed_turn():  # type: ignore[no-untyped-def]
    """`deficit_demo.yaml`, the same walkthrough proposal with NO influence -- fails unaided
    (47/100, required 51), giving a real `FAILED_LEGISLATIVE` report whose budget must NOT
    apply."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    decisions = _decisions_with(state, decision)
    resolution = resolve_turn(state, decisions)
    return state, resolution, decisions


def _with_player_politics(state, politics):  # type: ignore[no-untyped-def]
    player_id = state.world.player_country_id
    player = state.world.countries[player_id]
    return state.model_copy(
        update={
            "world": state.world.model_copy(
                update={
                    "countries": {
                        **state.world.countries,
                        player_id: player.model_copy(update={"politics": politics}),
                    }
                }
            )
        }
    )


def _with_player_finance(state, finance):  # type: ignore[no-untyped-def]
    player_id = state.world.player_country_id
    player = state.world.countries[player_id]
    return state.model_copy(
        update={
            "world": state.world.model_copy(
                update={
                    "countries": {
                        **state.world.countries,
                        player_id: player.model_copy(update={"finance": finance}),
                    }
                }
            )
        }
    )


def _replace_bloc_rows(legislative, *, match_party_id: str, match_bloc_id: str, **updates):  # type: ignore[no-untyped-def]
    """Corrupt every row for `(match_party_id, match_bloc_id)` identically (both chamber rows, if
    bicameral) -- keeps the bicameral-consistency shape intact so the ONE thing under test is
    isolated. The match key is named separately from `**updates` so a test can corrupt `party_id`
    or `bloc_id` itself without a keyword collision."""
    new_blocs = tuple(
        row.model_copy(update=updates)
        if (row.party_id, row.bloc_id) == (match_party_id, match_bloc_id)
        else row
        for row in legislative.blocs
    )
    return legislative.model_copy(update={"blocs": new_blocs})


def _json_roundtrip(report: TurnReport) -> TurnReport:
    """Dump to plain JSON-able data and re-parse -- re-runs every self-validator on every nested
    report, exactly like history replay's `TurnReport.model_validate` (§9.4). Used to prove a
    corruption that reconciliation alone catches survives the round trip unchanged (it isn't
    accidentally "fixed" or masked by re-parsing), and, for genuinely report-internal
    corruptions, that the OTHER layer (self-validation) is what actually catches those."""
    return TurnReport.model_validate(report.model_dump(mode="json"))


_RECONCILE_PATHS = pytest.mark.parametrize(
    "load",
    [
        pytest.param(lambda r: r, id="direct_model"),
        pytest.param(_json_roundtrip, id="json_replay"),
    ],
)


def test_a_clean_legislative_resolution_reconciles_with_no_problems() -> None:
    state, resolution, decisions = _tiny_valid_passing_turn()
    assert (
        reconcile_political_and_legislative_report(
            opening_state=state,
            closing_state=resolution.state,
            report=resolution.report,
            decisions=decisions,
        )
        == []
    )


def test_chamber_identity_missing_row_is_rejected() -> None:
    """Group 13: the report drops its `upper` chamber row entirely -- caught by identity, not
    position (there is no "expected 2, got 1" count check to fool)."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    lower_only = tuple(c for c in legislative.chambers if c.chamber is LegislativeChamber.LOWER)
    corrupted_legislative = legislative.model_copy(update={"chambers": lower_only})
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("missing a row for chamber 'upper'" in p for p in problems)


def test_party_identity_mismatch_is_rejected() -> None:
    """Group 14: a bloc row relabeled under a party that does not exist in the state
    legislature."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = _replace_bloc_rows(
        legislative,
        match_party_id="civic_union",
        match_bloc_id="mainstream",
        party_id="not_a_real_party",
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("does not seat there" in p for p in problems)


def test_bloc_identity_mismatch_is_rejected() -> None:
    """Group 14: a bloc row relabeled with a bloc id that does not exist under its real party."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = _replace_bloc_rows(
        legislative,
        match_party_id="civic_union",
        match_bloc_id="mainstream",
        bloc_id="not_a_real_bloc",
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("does not seat there" in p for p in problems)


def test_seats_mismatch_is_rejected() -> None:
    """Group 15 (composition): the one apportionment input state actually holds."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = _replace_bloc_rows(
        legislative, match_party_id="civic_union", match_bloc_id="mainstream", seats=1
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any(
        "seats=1 does not match state seats=" in p
        for p in problems
        if "civic_union" in p and "mainstream" in p
    )


def test_discipline_mismatch_is_rejected() -> None:
    """Group 14: `discipline_bps` is compared against state directly (never re-amplified)."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    row = next(
        r for r in legislative.blocs if r.party_id == "civic_union" and r.bloc_id == "mainstream"
    )
    corrupted_legislative = _replace_bloc_rows(
        legislative,
        match_party_id="civic_union",
        match_bloc_id="mainstream",
        discipline_bps=row.discipline_bps ^ 1,
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("discipline_bps" in p for p in problems)


def test_baseline_support_input_relationship_mismatch_is_rejected() -> None:
    """Group 14 (composition, not re-derivation): `baseline_support_bps` is never re-derived
    inside reconciliation -- `government_relationship_bps` (one of its two real inputs) is
    checked against state directly, and `LegislativeReport`'s own validator #1 re-derives
    `baseline_support_bps` from it on every parse (proven separately below), so the two together
    still catch a bad baseline without this module duplicating the formula."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    row = next(
        r for r in legislative.blocs if r.party_id == "civic_union" and r.bloc_id == "mainstream"
    )
    corrupted_legislative = _replace_bloc_rows(
        legislative,
        match_party_id="civic_union",
        match_bloc_id="mainstream",
        government_relationship_bps=row.government_relationship_bps - 1000,
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("government_relationship_bps" in p for p in problems)


def test_baseline_support_field_alone_is_caught_by_report_validation_not_reconciliation() -> None:
    """The other half of the composition proof: corrupting `baseline_support_bps` ALONE (leaving
    `government_relationship_bps` untouched) produces a report reconciliation cannot see anything
    wrong with -- because there is nothing wrong with it from reconciliation's point of view; the
    row simply lies about its own arithmetic, which is `LegislativeReport` validator #1's job,
    proven here by the same corrupted row failing to even construct through real validation."""
    _, resolution, _ = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    row = next(
        r for r in legislative.blocs if r.party_id == "civic_union" and r.bloc_id == "mainstream"
    )
    data = row.model_dump(mode="json")
    data["baseline_support_bps"] += 1
    with pytest.raises(Exception, match="baseline_support_bps"):
        type(row).model_validate(data)


def test_bonus_seat_assignment_is_caught_by_report_validation_not_reconciliation() -> None:
    """Group 15 (composition): moving a bonus seat between rows is `LegislativeReport` validator
    #8's job (`_chamber_apportionment_is_correct`), which reconciliation deliberately never
    re-derives -- see the module docstring. Proven the same way: the tampered pair of rows
    (bonus moved from the larger remainder to a smaller one, mirroring
    `test_legislative_report.py::test_8_corrupted_bonus_seat_ordering_is_rejected`) fails to
    construct through real validation, i.e. is caught before reconciliation would ever run."""
    _, resolution, _ = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    chamber_report = next(c for c in legislative.chambers if c.extras_awarded >= 1)
    rows = [r for r in legislative.blocs if r.chamber == chamber_report.chamber]
    bonus_row = next(r for r in rows if r.bonus_seat)
    eligible = sorted(
        (r for r in rows if not r.bonus_seat and r.base_seats < r.seats), key=lambda r: r.remainder
    )
    assert eligible
    target_row = eligible[0]
    data = legislative.model_dump(mode="json")
    bonus_idx = next(
        i
        for i, r in enumerate(data["blocs"])
        if r["party_id"] == bonus_row.party_id
        and r["bloc_id"] == bonus_row.bloc_id
        and r["chamber"] == bonus_row.chamber.value
    )
    target_idx = next(
        i
        for i, r in enumerate(data["blocs"])
        if r["party_id"] == target_row.party_id
        and r["bloc_id"] == target_row.bloc_id
        and r["chamber"] == target_row.chamber.value
    )
    data["blocs"][bonus_idx]["bonus_seat"] = False
    data["blocs"][bonus_idx]["supporting_seats"] = data["blocs"][bonus_idx]["base_seats"]
    data["blocs"][target_idx]["bonus_seat"] = True
    data["blocs"][target_idx]["supporting_seats"] = data["blocs"][target_idx]["base_seats"] + 1
    with pytest.raises(Exception, match="largest-remainder ordering"):
        type(legislative).model_validate(data)


def test_legislature_mutation_is_rejected() -> None:
    """Group 12 (D7 staticness): closing state's legislature differs from opening's."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert player.politics is not None and player.politics.legislature is not None
    party = player.politics.legislature.parties[0]
    bloc = party.blocs[0]
    mutated_bloc = bloc.model_copy(update={"discipline_bps": bloc.discipline_bps ^ 1})
    mutated_party = party.model_copy(update={"blocs": (mutated_bloc, *party.blocs[1:])})
    mutated_legislature = player.politics.legislature.model_copy(
        update={"parties": (mutated_party, *player.politics.legislature.parties[1:])}
    )
    mutated_politics = player.politics.model_copy(update={"legislature": mutated_legislature})
    mutated_state = _with_player_politics(resolution.state, mutated_politics)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=mutated_state,
        report=resolution.report,
        decisions=decisions,
    )
    assert any("legislature was mutated" in p for p in problems)


def test_opening_capital_mismatch_is_rejected() -> None:
    """Group 17."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = legislative.model_copy(
        update={"opening_political_capital": legislative.opening_political_capital + 1}
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("legislative.opening_political_capital" in p for p in problems)


def test_committed_capital_mismatch_is_rejected_directly() -> None:
    """Group 17: committed capital compared against `political.political_capital_spent`."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = legislative.model_copy(
        update={"political_capital_committed": legislative.political_capital_committed + 1}
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("political_capital_committed" in p for p in problems)


def test_committed_capital_mismatch_also_fails_report_validation_on_json_replay() -> None:
    """The same corruption, replayed: `political_capital_committed` is not just compared against
    `political.political_capital_spent` by reconciliation -- it is independently reconstructible
    from the unique-target allocations in `legislative.blocs` alone (`LegislativeReport` validator
    #12), and the bloc rows here still sum to the ORIGINAL, uncorrupted total. So a JSON round
    trip catches this one turn earlier than a direct in-memory reconciliation call would -- at
    report-parse time, before reconciliation ever runs -- which is a stronger guarantee, not a
    weaker one; this test exists to make that guarantee explicit rather than assume it."""
    _, resolution, _ = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = legislative.model_copy(
        update={"political_capital_committed": legislative.political_capital_committed + 1}
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    with pytest.raises(Exception, match="political_capital_committed"):
        _json_roundtrip(corrupted_report)


def test_closing_capital_mismatch_is_rejected() -> None:
    """Group 17: the approved clamp order, `min(capacity, opening - committed + regeneration)`,
    checked against the REAL closing state -- a state-side mutation, not a report corruption."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert player.politics is not None
    mutated_politics = player.politics.model_copy(
        update={"political_capital": player.politics.political_capital + 1}
    )
    mutated_state = _with_player_politics(resolution.state, mutated_politics)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=mutated_state,
        report=resolution.report,
        decisions=decisions,
    )
    assert any("does not match min(capacity" in p for p in problems)


def test_route_mismatch_with_submitted_decision_is_rejected_directly() -> None:
    """Group 18: `legislative.route` compared against the submitted decision's `route`. Corrupted
    to a route that still keeps `outcome`/`route` internally paired (`FAILED_LEGISLATIVE` still
    implies `route=LEGISLATIVE`, so swapping outcomes -- not fabricating a `DECREE` outcome that
    would trip the report's own matrix validator first -- is what isolates reconciliation's own
    check; see the sibling JSON-replay test for the `DECREE` case, which the matrix validator
    catches earlier)."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    from app.simulation.legislature import ProposalRoute

    corrupted_legislative = legislative.model_copy(update={"route": ProposalRoute.DECREE})
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any("does not match the submitted decision's route" in p for p in problems)


def test_route_decree_mismatch_also_fails_report_validation_on_json_replay() -> None:
    """The same `DECREE`-while-`PASSED_LEGISLATIVE` corruption, replayed: this ALSO violates the
    report's own outcome/route matrix (validator #11: `PASSED_LEGISLATIVE` requires
    `route=LEGISLATIVE`), so a JSON round trip catches it a layer earlier than reconciliation
    would -- proven explicitly rather than assumed."""
    _, resolution, _ = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    from app.simulation.legislature import ProposalRoute

    corrupted_legislative = legislative.model_copy(update={"route": ProposalRoute.DECREE})
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    with pytest.raises(Exception, match="route=LEGISLATIVE"):
        _json_roundtrip(corrupted_report)


def test_influence_allocation_mismatch_with_submitted_decision_is_rejected() -> None:
    """Group 18: the report shows a different allocation than the decision actually committed."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_legislative = _replace_bloc_rows(
        legislative,
        match_party_id="civic_union",
        match_bloc_id="mainstream",
        political_capital_allocated=60,
        influence_bps=600,
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=corrupted_report,
        decisions=decisions,
    )
    assert any(
        "civic_union" in p and "mainstream" in p and "does not" in p and "allocation" in p
        for p in problems
    )


@_RECONCILE_PATHS
def test_decision_digest_mismatch_is_rejected(load) -> None:  # type: ignore[no-untyped-def]
    """Group 18, exercised both directly and via JSON replay."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    legislative = resolution.report.legislative
    assert legislative is not None
    corrupted_digest = ("0" if legislative.budget_decision_digest != "0" * 64 else "1") * 64
    corrupted_legislative = legislative.model_copy(
        update={"budget_decision_digest": corrupted_digest}
    )
    corrupted_report = resolution.report.model_copy(update={"legislative": corrupted_legislative})
    reloaded_report = load(corrupted_report)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=reloaded_report,
        decisions=decisions,
    )
    assert any("budget_decision_digest" in p for p in problems)


def test_applied_policy_after_a_failed_vote_is_rejected() -> None:
    """Group 16: `deficit_demo`'s proposal FAILS unaided (no influence submitted) -- if the
    closing state shows the proposal's target anyway, that is exactly the "budget applied despite
    a failed vote" bug group 16 exists to catch."""
    state, resolution, decisions = _deficit_demo_failed_turn()
    assert resolution.report.legislative is not None
    from app.simulation.legislature import LegislativeOutcome

    assert resolution.report.legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert player.finance is not None
    decision = decisions.budget_decision()
    assert decision is not None
    assert decision.personal_income_rate_bps is not None
    mutated_finance = player.finance.model_copy(
        update={
            "tax_policy": player.finance.tax_policy.model_copy(
                update={"personal_income_rate_bps": decision.personal_income_rate_bps}
            )
        }
    )
    mutated_state = _with_player_finance(resolution.state, mutated_finance)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=mutated_state,
        report=resolution.report,
        decisions=decisions,
    )
    assert any("finance.tax_policy.personal_income_rate_bps" in p for p in problems)


def test_missing_policy_application_after_a_passed_vote_is_rejected() -> None:
    """Group 16: `tiny_valid`'s proposal PASSES -- if the closing state still shows the OPENING
    rate, that is the "budget silently failed to apply despite passing" bug."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    assert resolution.report.legislative is not None
    from app.simulation.legislature import LegislativeOutcome

    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    opening_player = state.world.countries[state.world.player_country_id]
    closing_player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert closing_player.finance is not None
    mutated_finance = closing_player.finance.model_copy(
        update={
            "tax_policy": closing_player.finance.tax_policy.model_copy(
                update={
                    "personal_income_rate_bps": opening_player.finance.tax_policy.personal_income_rate_bps
                }
            )
        }
    )
    mutated_state = _with_player_finance(resolution.state, mutated_finance)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=mutated_state,
        report=resolution.report,
        decisions=decisions,
    )
    assert any("finance.tax_policy.personal_income_rate_bps" in p for p in problems)


def test_mutation_of_an_untargeted_spending_category_is_rejected() -> None:
    """Group 16: `tiny_valid`'s proposal targets only `personal_income_rate_bps` -- every
    spending category is untargeted and must equal opening exactly, whatever the outcome."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    closing_player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert closing_player.finance is not None
    mutated_finance = closing_player.finance.model_copy(
        update={
            "spending_plan": closing_player.finance.spending_plan.model_copy(
                update={"health": closing_player.finance.spending_plan.health + 1}
            )
        }
    )
    mutated_state = _with_player_finance(resolution.state, mutated_finance)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=mutated_state,
        report=resolution.report,
        decisions=decisions,
    )
    assert any("finance.spending_plan.health" in p for p in problems)


def test_no_legislative_report_produces_no_new_problems() -> None:
    """`report.legislative is None` is rejected earlier by TurnReport's completeness rule;
    reconciliation is a no-op for the legislative groups in that case, not a crash."""
    state, resolution, decisions = _tiny_valid_passing_turn()
    report_without_legislative = resolution.report.model_copy(update={"legislative": None})
    # (report_without_legislative is not itself a valid TurnReport -- completeness is a
    # construction-time rule -- but reconciliation takes an already-built Python object and must
    # not crash on this shape either way.)
    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=report_without_legislative,
        decisions=decisions,
    )
    assert not any("legislative" in p for p in problems)
