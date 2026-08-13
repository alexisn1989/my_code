"""Phase 3B2A: end-to-end relationship-investment resolution through the real engine.

Focused on the two properties the plan singled out as the highest-risk parts of this ticket:

- **R13** — a guaranteed zero-effect investment is refused atomically at slot 1, never charged.
- **R12** — group 12/14's rewrite proves a turn can carry a legitimate relationship change AND a
  legislative vote at once, with the vote scored against the OPENING relationship and the state
  landing on the CLOSING one, and that a report which scored the vote against the closing value
  instead is rejected.

The full one-based sequential calibration tables (T11/T11b) are `test_relationship_calibration.py`
(plan commit 9); this file is about resolution mechanics, not the multi-turn numbers.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import TurnResolutionError
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
)
from app.simulation.legislature import CapitalExpenditureCategory, LegislativeOutcome, ProposalRoute
from app.simulation.reconciliation import reconcile_political_and_legislative_report
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR


def _decisions_for(state, *decision_objs):  # type: ignore[no-untyped-def]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(decision_objs),
    )


# --- R13: guaranteed zero-effect investments are refused, not charged ---------


def test_investing_in_a_bloc_already_at_the_relationship_ceiling_is_refused() -> None:
    """gap == 0: relationship exactly +10,000. The clearest guaranteed no-op."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    player = state.world.countries[state.world.player_country_id]
    legislature = player.politics.legislature
    party = legislature.parties[0]
    bloc = party.blocs[0]
    maxed_bloc = bloc.model_copy(update={"government_relationship_bps": 10_000})
    maxed_party = party.model_copy(update={"blocs": (maxed_bloc, *party.blocs[1:])})
    maxed_legislature = legislature.model_copy(
        update={"parties": (maxed_party, *legislature.parties[1:])}
    )
    maxed_politics = player.politics.model_copy(update={"legislature": maxed_legislature})
    tampered_state = state.model_copy(
        update={
            "world": state.world.model_copy(
                update={
                    "countries": {
                        **state.world.countries,
                        state.world.player_country_id: player.model_copy(
                            update={"politics": maxed_politics}
                        ),
                    }
                }
            )
        }
    )

    decisions = _decisions_for(
        tampered_state,
        BlocRelationshipInvestmentDecision(
            investments=(BlocInvestment(party_id=party.id, bloc_id=bloc.id, political_capital=200),)
        ),
    )
    before = tampered_state.model_dump(mode="json")
    with pytest.raises(TurnResolutionError, match="no effect"):
        resolve_turn(tampered_state, decisions)
    assert tampered_state.model_dump(mode="json") == before  # untouched, no partial mutation


def test_a_truncation_zero_gain_is_also_refused() -> None:
    """A positive gap can still buy nothing: gap=1 at capital=200 truncates to a gain of 0. The
    rejection must be written against the COMPUTED gain, not a bare `gap == 0` check -- this is
    exactly the case a gap-only rule would miss."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    player = state.world.countries[state.world.player_country_id]
    legislature = player.politics.legislature
    party = legislature.parties[0]
    bloc = party.blocs[0]
    near_ceiling_bloc = bloc.model_copy(update={"government_relationship_bps": 9_999})
    near_ceiling_party = party.model_copy(update={"blocs": (near_ceiling_bloc, *party.blocs[1:])})
    near_ceiling_legislature = legislature.model_copy(
        update={"parties": (near_ceiling_party, *legislature.parties[1:])}
    )
    near_ceiling_politics = player.politics.model_copy(
        update={"legislature": near_ceiling_legislature}
    )
    tampered_state = state.model_copy(
        update={
            "world": state.world.model_copy(
                update={
                    "countries": {
                        **state.world.countries,
                        state.world.player_country_id: player.model_copy(
                            update={"politics": near_ceiling_politics}
                        ),
                    }
                }
            )
        }
    )

    decisions = _decisions_for(
        tampered_state,
        BlocRelationshipInvestmentDecision(
            investments=(BlocInvestment(party_id=party.id, bloc_id=bloc.id, political_capital=1),)
        ),
    )
    with pytest.raises(TurnResolutionError, match="no effect"):
        resolve_turn(tampered_state, decisions)


def test_a_real_investment_at_the_same_scenario_is_accepted() -> None:
    """Sanity: the refusal above is about the specific tampered relationship, not about
    `deficit_demo` generally -- the same target at its AUTHORED relationship accepts capital and
    produces a positive gain."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = _decisions_for(
        state,
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
    )
    resolution = resolve_turn(state, decisions)
    report = resolution.report.political_capital
    assert report is not None
    assert report.relationship_changes[0].applied_change_bps == 2_000


# --- R12: mixed investment + vote turns, and the retroactive-rescoring tamper -


def test_a_turn_with_both_a_legislative_vote_and_an_investment_reconciles_clean() -> None:
    """The regression T13b calls out explicitly: a legitimate investment alongside a real vote,
    where the vote row holds the OPENING relationship and closing state holds the IMPROVED one."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current_rate = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decisions = _decisions_for(
        state,
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
        BudgetDecision(
            personal_income_rate_bps=current_rate + 500,
            influence=(
                InfluenceAllocation(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=162
                ),
            ),
        ),
    )
    resolution = resolve_turn(state, decisions)
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE

    vote_row = next(
        row
        for row in resolution.report.legislative.blocs
        if row.party_id == "citizens_bloc" and row.bloc_id == "moderates"
    )
    assert vote_row.government_relationship_bps == -2_000  # the AUTHORED opening value

    closing_player = resolution.state.world.countries[resolution.state.world.player_country_id]
    closing_bloc = next(
        bloc
        for party in closing_player.politics.legislature.parties
        for bloc in party.blocs
        if party.id == "citizens_bloc" and bloc.id == "moderates"
    )
    assert closing_bloc.government_relationship_bps == 0  # -2000 + gain(2000)
    assert closing_bloc.government_relationship_bps != vote_row.government_relationship_bps

    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=resolution.report,
        decisions=decisions,
    )
    assert problems == []


def test_a_report_scoring_the_vote_against_the_closing_relationship_is_rejected() -> None:
    """The retroactive-rescoring tamper: a report whose vote row shows the IMPROVED (closing)
    relationship instead of the real opening one. This is precisely what pinning group 14 to the
    opening state exists to catch."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current_rate = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decisions = _decisions_for(
        state,
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
        BudgetDecision(
            personal_income_rate_bps=current_rate + 500,
            influence=(
                InfluenceAllocation(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=162
                ),
            ),
        ),
    )
    resolution = resolve_turn(state, decisions)
    legislative = resolution.report.legislative
    assert legislative is not None

    tampered_blocs = tuple(
        row.model_copy(update={"government_relationship_bps": 0})
        if row.party_id == "citizens_bloc" and row.bloc_id == "moderates"
        else row
        for row in legislative.blocs
    )
    tampered_legislative = legislative.model_copy(update={"blocs": tampered_blocs})
    tampered_report = resolution.report.model_copy(update={"legislative": tampered_legislative})

    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=tampered_report,
        decisions=decisions,
    )
    assert any(
        "government_relationship_bps" in p and "opening_state" in p
        for p in problems
        if "citizens_bloc" in p and "moderates" in p
    )


def test_group_12_state_to_state_check_catches_corruption_on_a_no_proposal_investment_turn() -> (
    None
):
    """The coverage regression the dropped `opening == closing` guard exists to fix, in its
    sharpest form: a NO_PROPOSAL turn carrying a legitimate relationship investment produces a
    report with ZERO chamber/bloc rows (there was no vote to report), so groups 13-15 -- which
    compare REPORT rows against state -- have nothing to compare and cannot see a corruption here
    no matter how their guard is written. Only group 12's direct state-to-state staticness check
    (added specifically to close this hole) can catch a corrupted chamber `total_seats` on a turn
    like this one."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = _decisions_for(
        state,
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
    )
    resolution = resolve_turn(state, decisions)
    legislative = resolution.report.legislative
    assert legislative is not None

    # NO_PROPOSAL carries no chamber rows to corrupt directly on the report; instead corrupt the
    # STATE's chamber size, proving the check runs against real state even on an investment turn.
    player = resolution.state.world.countries[resolution.state.world.player_country_id]
    legislature = player.politics.legislature
    chamber = legislature.chambers[0]
    corrupted_chamber = chamber.model_copy(update={"total_seats": chamber.total_seats + 1})
    corrupted_legislature = legislature.model_copy(
        update={"chambers": (corrupted_chamber, *legislature.chambers[1:])}
    )
    corrupted_politics = player.politics.model_copy(update={"legislature": corrupted_legislature})
    corrupted_state = resolution.state.model_copy(
        update={
            "world": resolution.state.world.model_copy(
                update={
                    "countries": {
                        **resolution.state.world.countries,
                        resolution.state.world.player_country_id: player.model_copy(
                            update={"politics": corrupted_politics}
                        ),
                    }
                }
            )
        }
    )

    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=corrupted_state,
        report=resolution.report,
        decisions=decisions,
    )
    # A NO_PROPOSAL turn carries ZERO chamber/bloc rows in its report by construction -- there was
    # no vote to report -- so groups 13-15 (which compare REPORT rows against state) have nothing
    # to compare here and cannot see this corruption no matter how their guard is written. What
    # must catch it is group 12's direct STATE-TO-STATE staticness check, which runs whenever a
    # legislature exists in both states, independent of report content. Confirm both halves: the
    # legislature is still reported present, and the corrupted `total_seats` is actually caught.
    assert legislative.legislature_present is True
    assert any("total_seats" in p or "chambers changed" in p for p in problems)


# --- route/category consistency and relationship-only turns -------------------


def test_decree_route_produces_exactly_one_decree_row_and_no_influence_rows() -> None:
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    decisions = _decisions_for(
        state, BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    )
    resolution = resolve_turn(state, decisions)
    ledger = resolution.report.political_capital
    assert ledger is not None
    categories = [row.category for row in ledger.expenditures]
    assert categories.count(CapitalExpenditureCategory.DECREE) == 1
    assert CapitalExpenditureCategory.LEGISLATIVE_INFLUENCE not in categories


def test_a_relationship_only_turn_is_a_valid_no_proposal_with_a_nonempty_ledger() -> None:
    """The simplest new thing this phase adds: no budget decision at all, just an investment."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    decisions = _decisions_for(
        state,
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
    )
    resolution = resolve_turn(state, decisions)
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 100
    assert len(ledger.relationship_changes) == 1

    problems = reconcile_political_and_legislative_report(
        opening_state=state,
        closing_state=resolution.state,
        report=resolution.report,
        decisions=decisions,
    )
    assert problems == []


def test_no_decisions_at_all_leaves_the_ledger_empty_and_politics_unchanged() -> None:
    """T-C1 preserved under 3B2A: with nothing submitted, the ledger is empty and
    `politics.legislature` is byte-identical -- Phase 3B1's no-decision guarantee, extended."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    decisions = _decisions_for(state)
    resolution = resolve_turn(state, decisions)
    ledger = resolution.report.political_capital
    assert ledger is not None
    assert ledger.total_committed == 0
    assert ledger.expenditures == ()
    assert ledger.relationship_changes == ()

    opening_player = state.world.countries[state.world.player_country_id]
    closing_player = resolution.state.world.countries[resolution.state.world.player_country_id]
    assert closing_player.politics.legislature == opening_player.politics.legislature
