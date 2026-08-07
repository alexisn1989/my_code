"""Tests for `simulation.reconciliation.reconcile_political_report` (Phase 3A, T-R5/T-R6).

Every corruption below is built with `model_copy(update=...)`, which does NOT re-run
`PoliticalReport`'s own self-validators (Pydantic v2's `model_copy` never validates) — so each
test produces a report that is internally self-consistent per its own ten formula validators
(§9.1) but disagrees with the state it is compared against. That isolates the reconciliation
check specifically: a report can pass every formula check and still be caught here for describing
the wrong turn's political facts.

No fixed comparison count is asserted anywhere in this file (§9.3) — each test instead proves
one specific field is independently corruptible and independently rejected.
"""

from __future__ import annotations

from app.simulation.constitution import ExecutiveSelection, ExecutiveSystem, JudicialReview
from app.simulation.decisions import DecisionSet
from app.simulation.reconciliation import reconcile_political_report
from app.simulation.report import EconomicBaselineReport
from app.simulation.resolver import resolve_turn
from tests.conftest import make_game_state


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
        reconcile_political_report(
            opening_state=state, closing_state=first.state, report=first.report
        )
        == []
    )
    assert (
        reconcile_political_report(
            opening_state=first.state, closing_state=second.state, report=second.report
        )
        == []
    )


def test_corrupted_opening_legitimacy_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"opening_legitimacy_bps": first.report.political.opening_legitimacy_bps + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
    )
    assert any("opening_legitimacy_bps" in p for p in problems)


def test_corrupted_closing_legitimacy_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"closing_legitimacy_bps": first.report.political.closing_legitimacy_bps + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
    )
    assert any("closing_legitimacy_bps" in p for p in problems)


def test_corrupted_opening_political_capital_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"opening_political_capital": first.report.political.opening_political_capital + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
    )
    assert any("opening_political_capital" in p for p in problems)


def test_corrupted_closing_political_capital_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"closing_political_capital": first.report.political.closing_political_capital + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
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
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
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
        problems = reconcile_political_report(
            opening_state=first.state, closing_state=second.state, report=corrupted_report
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
        problems = reconcile_political_report(
            opening_state=state, closing_state=first.state, report=corrupted_report
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
        problems = reconcile_political_report(
            opening_state=state, closing_state=first.state, report=corrupted_report
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
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
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
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
    )
    assert any("constitutional_order_support_bps" in p for p in problems)


def test_corrupted_political_capital_capacity_is_rejected() -> None:
    state, first, _ = _resolve_twice()
    corrupted_political = first.report.political.model_copy(
        update={"political_capital_capacity": first.report.political.political_capital_capacity + 1}
    )
    corrupted_report = first.report.model_copy(update={"political": corrupted_political})
    problems = reconcile_political_report(
        opening_state=state, closing_state=first.state, report=corrupted_report
    )
    assert any("political_capital_capacity" in p for p in problems)


def test_no_political_report_produces_no_problems() -> None:
    """`report.political is None` is rejected earlier (TurnReport completeness +
    player_politics_required); reconciliation itself is a no-op for that case, not a crash."""
    state, first, _ = _resolve_twice()
    report_without_political = first.report.model_copy(update={"political": None})
    assert (
        reconcile_political_report(
            opening_state=state, closing_state=first.state, report=report_without_political
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
    problems = reconcile_political_report(
        opening_state=state, closing_state=mutated_state, report=first.report
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
    problems = reconcile_political_report(
        opening_state=state, closing_state=mutated_state, report=first.report
    )
    assert any("political_capital_capacity" in p for p in problems)
