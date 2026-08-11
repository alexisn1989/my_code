"""Integration tests for `data/scenarios/decree_state.yaml` (Phase 3B1, plan §0.8).

Every other shipped scenario is `decree_authority: emergency_only` (`tiny_valid.yaml`,
`deficit_demo.yaml`), so neither can ever decree — the decree route has, until this file,
only ever been proven against a *synthetic* legislature built directly from the state models
(`test_decree_capital_calibration.py`'s Regime C). `decree_state.yaml` promotes that exact,
already-exhaustively-proven Regime C into real, loadable scenario content: a monarchy with
`decree_authority: unlimited` **and** a real unicameral legislature, so a player genuinely
chooses a route every turn rather than being funnelled into one.

Every test here drives the real `load_scenario_file` → `resolve_turn` / `advance_game` →
`validate_history` path, never a hand-built report — the same discipline
`test_legislative_gating.py` and `test_scenario_legislature_calibration.py` already use for
`tiny_valid`/`deficit_demo`. The 283/282 legislative boundary and the 250 decree cost are not
re-derived here: they are Regime C's own DP-proven minimum
(`test_decree_capital_calibration.py::test_regime_c_reachable_deep_shortfall_minimum_is_exactly_283`),
transcribed field-for-field into the scenario file and merely *exercised* here through the real
resolver — that file keeps the exhaustive proof; this one proves the promotion was faithful.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.simulation.decisions import BudgetDecision, DecisionSet, InfluenceAllocation
from app.simulation.history import advance_game, new_game, validate_history
from app.simulation.invariants import check_invariants
from app.simulation.legislature import (
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.resolver import resolve_turn
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR

_SCENARIO_PATH = SCENARIO_DIR / "decree_state.yaml"
_COUNTRY_ID = "valdrun"

# The walkthrough proposal, matching the scenario's own header/comment claims and Regime C's
# `_tax_rise_5pp(2_000)` exactly (decree_state's authored opening rate is 20%, same as tiny_valid).
_TAX_RISE_5PP = 2_500
_LEGISLATIVE_283 = BudgetDecision(
    personal_income_rate_bps=_TAX_RISE_5PP,
    influence=(
        InfluenceAllocation(party_id="opposition_party", bloc_id="main", political_capital=283),
    ),
)
_LEGISLATIVE_282 = BudgetDecision(
    personal_income_rate_bps=_TAX_RISE_5PP,
    influence=(
        InfluenceAllocation(party_id="opposition_party", bloc_id="main", political_capital=282),
    ),
)
_DECREE_250 = BudgetDecision(personal_income_rate_bps=_TAX_RISE_5PP, route=ProposalRoute.DECREE)


def _decisions_for(state: GameState, decision: BudgetDecision | None) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(decision,) if decision is not None else (),
    )


def _load() -> GameState:
    return load_scenario_file(_SCENARIO_PATH)


# --- 1. loads through the real loader, invariants clean --------------------------------------


def test_decree_state_loads_and_passes_every_invariant() -> None:
    state = _load()
    assert state.world.player_country_id == _COUNTRY_ID
    assert check_invariants(state) == []


# --- 2. constitutional structure ---------------------------------------------------------------


def test_decree_state_is_monarchical_hereditary_unicameral_unlimited() -> None:
    con = _load().world.countries[_COUNTRY_ID].politics.constitution
    assert con.executive_system.value == "monarchical"
    assert con.executive_selection.value == "hereditary"
    assert con.legislature.value == "unicameral"
    assert con.decree_authority.value == "unlimited"
    assert con.executive_term_limit_terms is None
    assert con.national_election_interval_turns is None


# --- 3. legislature present and exactly seat-reconciled ----------------------------------------


def test_decree_state_legislature_is_present_and_exactly_seat_reconciled() -> None:
    politics = _load().world.countries[_COUNTRY_ID].politics
    legislature = politics.legislature
    assert legislature is not None
    assert len(legislature.chambers) == 1
    chamber = legislature.chambers[0]
    assert chamber.chamber is LegislativeChamber.LOWER
    assert chamber.total_seats == 100

    governing = next(p for p in legislature.parties if p.id == "governing_party")
    opposition = next(p for p in legislature.parties if p.id == "opposition_party")
    assert governing.government_role is GovernmentRole.COALITION
    assert opposition.government_role is GovernmentRole.OPPOSITION

    core = next(b for b in governing.blocs if b.id == "core")
    main = next(b for b in opposition.blocs if b.id == "main")
    assert core.seats[0].seats == 45
    assert main.seats[0].seats == 55
    assert core.seats[0].seats + main.seats[0].seats == chamber.total_seats

    # Regime C's exact bloc parameters, transcribed field-for-field
    # (test_decree_capital_calibration.py::_two_bloc_legislature).
    assert (core.discipline_bps, core.government_relationship_bps) == (5_000, 6_000)
    assert (core.tax_preference_bps, core.spending_preference_bps) == (2_000, 0)
    assert (main.discipline_bps, main.government_relationship_bps) == (8_000, -8_000)
    assert (main.tax_preference_bps, main.spending_preference_bps) == (-6_000, 0)


# --- 4. opening capital affords both routes -----------------------------------------------------


def test_opening_political_capital_affords_both_routes_and_capacity_covers_opening() -> None:
    politics = _load().world.countries[_COUNTRY_ID].politics
    assert politics.political_capital == 500
    assert politics.political_capital_capacity == 1_000
    assert politics.political_capital >= 283  # the legislative bargain
    assert politics.political_capital >= 250  # the decree
    assert politics.political_capital_capacity >= politics.political_capital


# --- 5. no-decision resolution ------------------------------------------------------------------


def test_no_decision_turn_is_no_proposal_zero_commitment_and_deterministic() -> None:
    state = _load()
    opening_finance = state.world.countries[_COUNTRY_ID].finance
    resolution_a = resolve_turn(state, _decisions_for(state, None))
    resolution_b = resolve_turn(state, _decisions_for(state, None))

    legislative = resolution_a.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    assert legislative.route is None
    assert legislative.political_capital_committed == 0
    assert legislative.budget_decision_digest is None
    assert legislative.chambers == ()
    assert legislative.blocs == ()

    closing_finance = resolution_a.state.world.countries[_COUNTRY_ID].finance
    assert closing_finance.tax_policy == opening_finance.tax_policy
    assert closing_finance.spending_plan == opening_finance.spending_plan

    assert canonical_dumps(resolution_a.state.model_dump(mode="json")) == canonical_dumps(
        resolution_b.state.model_dump(mode="json")
    )


# --- 6. legislative route at 283: passes, applies, commits exactly 283 -------------------------


def test_legislative_route_at_283_passes_applies_and_commits_exactly_283() -> None:
    state = _load()
    opening_rate = state.world.countries[_COUNTRY_ID].finance.tax_policy.personal_income_rate_bps
    resolution = resolve_turn(state, _decisions_for(state, _LEGISLATIVE_283))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert legislative.route is ProposalRoute.LEGISLATIVE
    assert legislative.political_capital_committed == 283

    assert len(legislative.chambers) == 1
    chamber = legislative.chambers[0]
    assert (chamber.supporting_seats, chamber.required_yes_seats, chamber.passed) == (
        51,
        51,
        True,
    )
    assert len(legislative.blocs) == 2

    closing = resolution.state.world.countries[_COUNTRY_ID].finance
    assert closing.tax_policy.personal_income_rate_bps == _TAX_RISE_5PP
    assert closing.tax_policy.personal_income_rate_bps != opening_rate


# --- 7. legislative route at 282: fails, does not apply, still consumes capital -----------------


def test_legislative_route_at_282_fails_but_still_consumes_committed_capital() -> None:
    state = _load()
    opening_finance = state.world.countries[_COUNTRY_ID].finance
    resolution = resolve_turn(state, _decisions_for(state, _LEGISLATIVE_282))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    assert legislative.political_capital_committed == 282

    chamber = legislative.chambers[0]
    assert (chamber.supporting_seats, chamber.required_yes_seats, chamber.passed) == (
        50,
        51,
        False,
    )

    closing_finance = resolution.state.world.countries[_COUNTRY_ID].finance
    assert closing_finance.tax_policy == opening_finance.tax_policy
    assert closing_finance.spending_plan == opening_finance.spending_plan

    assert resolution.state.turn == state.turn + 1


# --- 8. decree route: enacts, applies, commits exactly 250, zero vote rows ----------------------


def test_decree_route_enacts_applies_and_commits_exactly_250_with_no_vote_rows() -> None:
    state = _load()
    resolution = resolve_turn(state, _decisions_for(state, _DECREE_250))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    assert legislative.route is ProposalRoute.DECREE
    assert legislative.political_capital_committed == 250
    assert legislative.chambers == ()
    assert legislative.blocs == ()

    closing = resolution.state.world.countries[_COUNTRY_ID].finance
    assert closing.tax_policy.personal_income_rate_bps == _TAX_RISE_5PP


# --- 9. route equivalence: same budget, different capital/route/structure ----------------------


def test_passed_legislative_and_decree_reach_identical_policy_from_identical_opening() -> None:
    state = _load()
    legislative_resolution = resolve_turn(state, _decisions_for(state, _LEGISLATIVE_283))
    decree_resolution = resolve_turn(state, _decisions_for(state, _DECREE_250))

    legislative_finance = legislative_resolution.state.world.countries[_COUNTRY_ID].finance
    decree_finance = decree_resolution.state.world.countries[_COUNTRY_ID].finance
    assert legislative_finance.tax_policy == decree_finance.tax_policy
    assert legislative_finance.spending_plan == decree_finance.spending_plan

    legislative_report = legislative_resolution.report.legislative
    decree_report = decree_resolution.report.legislative
    assert legislative_report is not None and decree_report is not None
    assert legislative_report.route != decree_report.route
    assert legislative_report.outcome != decree_report.outcome
    assert legislative_report.political_capital_committed == 283
    assert decree_report.political_capital_committed == 250
    assert len(legislative_report.chambers) == 1 and legislative_report.chambers != ()
    assert decree_report.chambers == ()

    legislative_closing = legislative_resolution.state.world.countries[
        _COUNTRY_ID
    ].politics.political_capital
    decree_closing = decree_resolution.state.world.countries[_COUNTRY_ID].politics.political_capital
    assert legislative_closing != decree_closing  # different commitments regenerate differently


# --- 10. influence attached to a decree is still rejected --------------------------------------


def test_influence_attached_to_a_decree_is_rejected_by_construction() -> None:
    with pytest.raises(ValidationError, match="decree route takes no influence"):
        BudgetDecision(
            personal_income_rate_bps=_TAX_RISE_5PP,
            route=ProposalRoute.DECREE,
            influence=(
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=250
                ),
            ),
        )


# --- 11. legislature composition is byte-identical after both routes (D7) ----------------------


def test_legislature_is_byte_identical_after_both_routes() -> None:
    state = _load()
    opening_legislature = state.world.countries[_COUNTRY_ID].politics.legislature
    assert opening_legislature is not None
    opening_json = canonical_dumps(opening_legislature.model_dump(mode="json"))

    legislative_resolution = resolve_turn(state, _decisions_for(state, _LEGISLATIVE_283))
    decree_resolution = resolve_turn(state, _decisions_for(state, _DECREE_250))

    for resolution in (legislative_resolution, decree_resolution):
        closing_legislature = resolution.state.world.countries[_COUNTRY_ID].politics.legislature
        assert closing_legislature is not None
        assert canonical_dumps(closing_legislature.model_dump(mode="json")) == opening_json


# --- 12. all three shipped scenarios have at least one affordable successful route -------------


def test_all_three_shipped_scenarios_have_an_affordable_successful_route() -> None:
    # tiny_valid: unaided legislative passage.
    tiny_valid = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = tiny_valid.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    resolution = resolve_turn(
        tiny_valid,
        _decisions_for(tiny_valid, BudgetDecision(personal_income_rate_bps=current + 500)),
    )
    legislative = resolution.report.legislative
    assert legislative is not None and legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert legislative.political_capital_committed == 0

    # deficit_demo: legislative bargain costing exactly 162, affordable against its opening 300.
    deficit_demo = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = deficit_demo.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    opening_capital = deficit_demo.world.countries["strapped"].politics.political_capital
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=162
            ),
        ),
    )
    assert opening_capital >= 162
    resolution = resolve_turn(deficit_demo, _decisions_for(deficit_demo, decision))
    legislative = resolution.report.legislative
    assert legislative is not None and legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert legislative.political_capital_committed == 162

    # decree_state: BOTH a decree at 250 and a legislative bargain at 283, affordable against its
    # opening 500.
    decree_state = _load()
    opening_capital = decree_state.world.countries[_COUNTRY_ID].politics.political_capital
    assert opening_capital >= 283 and opening_capital >= 250
    legislative_resolution = resolve_turn(
        decree_state, _decisions_for(decree_state, _LEGISLATIVE_283)
    )
    decree_resolution = resolve_turn(decree_state, _decisions_for(decree_state, _DECREE_250))
    assert (
        legislative_resolution.report.legislative is not None
        and legislative_resolution.report.legislative.outcome
        is LegislativeOutcome.PASSED_LEGISLATIVE
    )
    assert (
        decree_resolution.report.legislative is not None
        and decree_resolution.report.legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    )


# --- 13. determinism through the history layer --------------------------------------------------


def test_two_independent_decree_state_games_with_identical_decisions_are_byte_identical() -> None:
    def play() -> str:
        save = new_game(_load(), save_format_version=SAVE_FORMAT_VERSION)
        state = save.current_state()
        save = advance_game(save, _decisions_for(state, None))
        state = save.current_state()
        save = advance_game(save, _decisions_for(state, _LEGISLATIVE_283))
        assert validate_history(save) == []
        return dump_save_json(save)

    first = play()
    second = play()
    assert first == second
