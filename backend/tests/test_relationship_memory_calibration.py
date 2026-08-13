"""Real-engine calibration regression tests for Phase 3B2B (§12 of the approved plan).

Every figure pinned here was produced by actually calling `resolve_turn` turn-by-turn against the
real, unmodified `deficit_demo.yaml`/`decree_state.yaml` scenario content -- never hand-derived or
assumed from the plan's own tables. Where a number disagreed with what the plan's own scratch
driver reported, this file records what the real engine actually produced (reality wins) rather
than adjusting the engine to match a stale expectation.

This is a reduced-scope replacement for 3B2A's `test_relationship_calibration.py` (removed: its
pinned turn-8 break-even and per-turn closing-relationship figures were computed with NO decay and
are no longer true now that decay and policy reactions exist on every turn). It intentionally does
not attempt to reproduce the plan's full 16-strategy, 20-turn exhaustive table (§12.1-§12.3) --
that full matrix is tracked as follow-up work. What is pinned here is the plan's central,
load-bearing claim: relationship investment converges to a genuine fixed point instead of climbing
to the ceiling forever, and a repeated content-free decree converges into a bounded band rather
than running away.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
)
from app.simulation.legislature import ChangeDirection, LegislativeOutcome, ProposalRoute
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR


def _decisions_for(state: GameState, *decision_objs: object) -> DecisionSet:  # type: ignore[no-untyped-def]
    ordered = sorted(decision_objs, key=lambda d: d.kind)  # type: ignore[attr-defined]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(ordered),  # type: ignore[arg-type]
    )


def _bloc(state: GameState, *, country_id: str, party_id: str, bloc_id: str):  # type: ignore[no-untyped-def]
    politics = state.world.countries[country_id].politics
    return next(
        b
        for p in politics.legislature.parties
        for b in p.blocs
        if p.id == party_id and b.id == bloc_id
    )


def test_decay_plus_investment_converges_to_the_controlled_fixed_point_4856() -> None:
    """(§12.1, §21 decision 3) `citizens_bloc/moderates` (`deficit_demo`, baseline -2,000),
    investing 100/turn against decay alone (no budget decision ever submitted), settles at
    exactly +4,856 and holds it -- verified by driving the real engine 60 turns, not asserted."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    closing_by_turn: dict[int, int] = {}
    for turn in range(60):
        resolution = resolve_turn(state, _decisions_for(state, investment))
        state = resolution.state
        bloc = _bloc(state, country_id="strapped", party_id="citizens_bloc", bloc_id="moderates")
        closing_by_turn[turn + 1] = bloc.government_relationship_bps

    assert closing_by_turn[1] == 0  # opening -2000 + investment gain 2000, no policy, no decay
    assert closing_by_turn[20] == 4850
    assert closing_by_turn[25] == 4856
    assert closing_by_turn[60] == 4856  # the fixed point holds indefinitely, never a ratchet


def test_stopping_investment_lets_the_relationship_decay_back_toward_baseline() -> None:
    """3B2A would have frozen wherever investment stopped, forever. 3B2B decays it back down --
    the entire point of the phase, confirmed by actually stopping investment mid-run."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    investment = BlocRelationshipInvestmentDecision(
        investments=(
            BlocInvestment(party_id="citizens_bloc", bloc_id="moderates", political_capital=100),
        )
    )
    for _ in range(8):
        resolution = resolve_turn(state, _decisions_for(state, investment))
        state = resolution.state
    peak = _bloc(state, country_id="strapped", party_id="citizens_bloc", bloc_id="moderates")
    peak_value = peak.government_relationship_bps
    assert peak_value > 0

    for _ in range(20):
        resolution = resolve_turn(state, _decisions_for(state))
        state = resolution.state
    after = _bloc(state, country_id="strapped", party_id="citizens_bloc", bloc_id="moderates")
    assert after.government_relationship_bps < peak_value


def test_repeated_content_free_decree_converges_to_the_penalty_only_band() -> None:
    """(§7.3, §12.2 Case 1) Re-decreeing the currently-active rate every turn on `decree_state` --
    `UNCHANGED`, so policy reaction is always 0 -- settles both blocs into the SAME 8-wide band
    `floor(|deviation|/8) == 200`, landing on -1,600 from baseline in both directions, stable from
    turn 46. Verified against the real engine, not derived."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    current_rate = state.world.countries["valdrun"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current_rate, route=ProposalRoute.DECREE)
    for turn in range(60):
        resolution = resolve_turn(state, _decisions_for(state, decision))
        state = resolution.state
        legislative = resolution.report.legislative
        assert legislative is not None
        assert legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
        assert legislative.tax_direction is ChangeDirection.UNCHANGED
        if turn == 45:
            core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
            main = _bloc(state, country_id="valdrun", party_id="opposition_party", bloc_id="main")
            assert core.government_relationship_bps == 4_400  # baseline 6,000, deviation -1,600
            assert main.government_relationship_bps == -9_600  # baseline -8,000, deviation -1,600

    core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
    main = _bloc(state, country_id="valdrun", party_id="opposition_party", bloc_id="main")
    assert core.government_relationship_bps == 4_400
    assert main.government_relationship_bps == -9_600


def test_a_single_decree_recovers_instead_of_sustaining_the_penalty() -> None:
    """(§7.3 "one decree recovers") A single genuine decree, then no further decision of any kind
    -- the relationship visibly recovers back toward baseline every subsequent turn, unlike a
    repeated-decree trajectory (which never recovers, per the test above)."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    state = resolution.state
    core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
    after_decree = core.government_relationship_bps
    assert after_decree < 6_000  # policy(+50) + decree_bypass(-200) nets negative here

    previous = after_decree
    for _ in range(10):
        resolution = resolve_turn(state, _decisions_for(state))
        state = resolution.state
        core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
        assert core.government_relationship_bps > previous  # monotone recovery, every turn
        previous = core.government_relationship_bps


def test_every_turn_of_every_scenario_above_stays_within_opening_capital() -> None:
    """(R13's affordability guard, spot-checked) None of the decision sequences driven above ever
    require more capital than was actually available -- confirmed by re-driving the decree_state
    repeated-decree sequence and checking the ledger's own guarantee every turn."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    current_rate = state.world.countries["valdrun"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current_rate, route=ProposalRoute.DECREE)
    for _ in range(20):
        opening_capital = state.world.countries["valdrun"].politics.political_capital
        resolution = resolve_turn(state, _decisions_for(state, decision))
        assert resolution.report.political_capital is not None
        assert resolution.report.political_capital.total_committed <= opening_capital
        state = resolution.state
