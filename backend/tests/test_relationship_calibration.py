"""Phase 3B2A (Revision 3, §15): sequential, one-based, engine-verified relationship-investment
calibration.

Every figure asserted below was produced by driving the REAL engine
(`app.simulation.resolver.resolve_turn`) turn by turn, reading `PoliticalCapitalReport` and
`LegislativeReport` back off the actual resolution -- never hand-computed and asserted as if it
were independent. What makes this a genuine regression test rather than a tautology is that the
expected numbers are literal constants pinned here, matching the plan's own pre-implementation
figures exactly (confirmed by a scratch run against this exact commit before this file was
written): if a future change to `RELATIONSHIP_HALF_GAP_CAPITAL`, `RELATIONSHIP_INVESTMENT_CAP`, the
apportionment formula, or the capital-ledger identity moves any one of these numbers, this file
fails.

**Turn numbering is ONE-BASED throughout**, matching `TurnReport.resolved_turn` and every table in
the plan: the first resolved turn is turn 1.

The "cheapest bargain" figure at each turn comes from `_exhaustive_cheapest_bargain`
(`test_decree_capital_calibration.py`) -- the same proven-optimal bounded-knapsack DP used to
confirm `DECREE_POLITICAL_CAPITAL_COST`, re-run here against each turn's CURRENT (possibly
investment-improved) legislature rather than a fixed one.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import DecisionSetError, TurnResolutionError
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
)
from app.simulation.legislative_voting import DECREE_POLITICAL_CAPITAL_COST
from app.simulation.legislature import ProposalRoute
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR
from tests.test_decree_capital_calibration import _exhaustive_cheapest_bargain, _tax_rise_5pp


def _bargain_for(state: GameState) -> tuple[int, dict[tuple[str, str], int]]:
    """This turn's cheapest passing bargain against the CURRENT (opening) legislature, using the
    canonical `+5pp` personal-income proposal (plan §15's stated modelling assumption)."""
    player = state.world.countries[state.world.player_country_id]
    legislature = player.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(player.finance.tax_policy.personal_income_rate_bps)
    chamber = legislature.chambers[0].chamber
    total_seats = legislature.chambers[0].total_seats
    minimum_spend, allocation, _supporting, _required = _exhaustive_cheapest_bargain(
        legislature=legislature,
        chamber=chamber,
        tax_change=tax_change,
        total_seats=total_seats,
    )
    return (minimum_spend or 0), {key: c for key, c in allocation.items() if c > 0}


def _budget_for(state: GameState, *, route: ProposalRoute, allocation: dict) -> BudgetDecision:
    player = state.world.countries[state.world.player_country_id]
    new_rate = player.finance.tax_policy.personal_income_rate_bps + 500
    influence = (
        tuple(
            InfluenceAllocation(party_id=p, bloc_id=b, political_capital=c)
            for (p, b), c in allocation.items()
        )
        if route is ProposalRoute.LEGISLATIVE
        else ()
    )
    return BudgetDecision(personal_income_rate_bps=new_rate, route=route, influence=influence)


def _decisions_for(
    state: GameState, *decision_objs: BudgetDecision | BlocRelationshipInvestmentDecision
) -> DecisionSet:
    # Canonical kind order: "bloc_relationship_investment" sorts before "budget".
    ordered = sorted(decision_objs, key=lambda d: d.kind)
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(ordered),
    )


# --- §15.1 deficit_demo: bargain-and-invest, first cheaper after resolved turn 8 ----------------

# (turn, opening_capital, opening_rel_bps, bargain, invest, total_committed, regen, closing_capital,
#  closing_rel_bps, cum_strategy, cum_baseline)
_DEFICIT_DEMO_TABLE = (
    (1, 300, -2_000, 162, 100, 262, 381, 419, 0, 262, 162),
    (2, 419, 0, 122, 100, 222, 382, 579, 1_666, 484, 324),
    (3, 579, 1_666, 89, 100, 189, 384, 774, 3_055, 673, 486),
    (4, 774, 3_055, 61, 100, 161, 385, 800, 4_212, 834, 648),
    (5, 800, 4_212, 38, 100, 138, 386, 800, 5_176, 972, 810),
    (6, 800, 5_176, 18, 100, 118, 386, 800, 5_980, 1_090, 972),
    (7, 800, 5_980, 2, 100, 102, 387, 800, 6_650, 1_192, 1_134),
    (8, 800, 6_650, 0, 0, 0, 388, 800, 6_650, 1_192, 1_296),
    (9, 800, 6_650, 0, 0, 0, 389, 800, 6_650, 1_192, 1_458),
)
"""Baseline is the FIXED 162 bargain repeated every turn (the target bloc's relationship never
moves without investment, so the cheapest bargain never moves either) -- `cum_baseline` is
therefore `162 * turn`, listed explicitly rather than computed, so a reader can check it by eye."""


def test_deficit_demo_sequential_calibration_matches_the_plan_exactly() -> None:
    """(T11) Drives the REAL engine turn 1-9 on `deficit_demo`, investing 100/turn in
    `citizens_bloc/moderates` and taking the cheapest legislative bargain every turn, stopping
    investment once the bargain reaches 0. Asserts every field the plan requires, every turn:
    opening capital, vote cost, investment, total commitment, affordability, regeneration, closing
    capital, opening/closing relationship, next-turn bargain (next row's `bargain`), and both
    cumulative totals."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    cum_strategy = 0
    for (
        turn,
        opening,
        opening_rel,
        bargain,
        invest,
        total,
        regen,
        closing,
        closing_rel,
        exp_cum_s,
        exp_cum_b,
    ) in _DEFICIT_DEMO_TABLE:
        player = state.world.countries[state.world.player_country_id]
        assert player.politics.political_capital == opening, f"turn {turn}: opening capital"
        bloc = next(
            b
            for p in player.politics.legislature.parties
            for b in p.blocs
            if p.id == "citizens_bloc" and b.id == "moderates"
        )
        assert bloc.government_relationship_bps == opening_rel, f"turn {turn}: opening relationship"

        computed_bargain, allocation = _bargain_for(state)
        assert computed_bargain == bargain, f"turn {turn}: cheapest bargain"

        decision_objs: list[BudgetDecision | BlocRelationshipInvestmentDecision] = []
        if bargain > 0:
            decision_objs.append(
                _budget_for(state, route=ProposalRoute.LEGISLATIVE, allocation=allocation)
            )
        if invest > 0:
            decision_objs.append(
                BlocRelationshipInvestmentDecision(
                    investments=(
                        BlocInvestment(
                            party_id="citizens_bloc",
                            bloc_id="moderates",
                            political_capital=invest,
                        ),
                    )
                )
            )
        decisions = _decisions_for(state, *decision_objs)

        # Affordability: asserted BEFORE resolving, against the real opening capital -- the guard
        # this whole table is designed to exercise, never merely trusted.
        assert total <= opening, f"turn {turn}: total commitment must not exceed opening capital"

        resolution = resolve_turn(state, decisions)
        report = resolution.report
        pcr = report.political_capital
        assert pcr is not None
        assert pcr.total_committed == total, f"turn {turn}: total_committed"
        assert pcr.political_capital_regeneration == regen, f"turn {turn}: regeneration"
        assert pcr.closing_political_capital == closing, f"turn {turn}: closing capital"
        assert pcr.closing_political_capital == min(
            player.politics.political_capital_capacity,
            opening - total + regen,
        ), f"turn {turn}: closing capital clamp identity"

        if invest > 0:
            assert len(pcr.relationship_changes) == 1
            change = pcr.relationship_changes[0]
            assert change.opening_relationship_bps == opening_rel, f"turn {turn}: change row opens"
            assert change.closing_relationship_bps == closing_rel, f"turn {turn}: applied change"
            assert change.political_capital == invest
        else:
            assert pcr.relationship_changes == ()

        state = resolution.state
        closing_bloc = next(
            b
            for p in state.world.countries[
                state.world.player_country_id
            ].politics.legislature.parties
            for b in p.blocs
            if p.id == "citizens_bloc" and b.id == "moderates"
        )
        assert closing_bloc.government_relationship_bps == closing_rel, f"turn {turn}: closing rel"

        cum_strategy += total
        assert cum_strategy == exp_cum_s, f"turn {turn}: cumulative strategy cost"
        assert 162 * turn == exp_cum_b, f"turn {turn}: cumulative baseline cost (fixed bargain)"


def test_deficit_demo_break_even_is_after_resolved_turn_8_not_turn_7() -> None:
    """(T11) The relationship strategy is strictly more expensive than the never-invest baseline
    for seven consecutive resolved turns (net negative through turn 7) and first becomes cheaper
    on turn 8 -- pinned as its own assertion so this specific, easy-to-get-wrong claim (revision 2
    said "turn 7", using a zero-based index) cannot silently regress even if the table above is
    edited."""
    cum_s = 0
    cum_b = 0
    for turn, *_rest, total, _regen, _closing, _closing_rel, exp_cum_s, exp_cum_b in (
        (row[0], row[5], row[6], row[7], row[8], row[9], row[10]) for row in _DEFICIT_DEMO_TABLE
    ):
        cum_s += total
        cum_b = 162 * turn
        assert cum_s == exp_cum_s
        assert cum_b == exp_cum_b
        if turn <= 7:
            assert cum_s > cum_b, f"turn {turn}: strategy must still be behind"
        if turn == 8:
            assert cum_s < cum_b, "turn 8: strategy must be first cheaper here"


# --- §15.2 decree_state: adaptive decree/legislate + invest, first cheaper after turn 8 ---------

# (turn, opening_capital, opening_rel_bps, bargain, route_is_decree, route_cost, invest, total,
#  regen, closing_capital, closing_rel_bps, cum_strategy)
_DECREE_STATE_TABLE = (
    (1, 500, -8_000, 283, True, 250, 200, 450, 383, 433, -2_858, 450),
    (2, 433, -2_858, 200, False, 200, 200, 400, 385, 418, 815, 850),
    (3, 418, 815, 127, False, 127, 200, 327, 388, 479, 3_439, 1_177),
    (4, 479, 3_439, 75, False, 75, 200, 275, 390, 594, 5_313, 1_452),
    (5, 594, 5_313, 37, False, 37, 200, 237, 392, 749, 6_652, 1_689),
    (6, 749, 6_652, 10, False, 10, 200, 210, 394, 933, 7_608, 1_899),
    (7, 933, 7_608, 0, False, 0, 0, 0, 395, 1_000, 7_608, 1_899),
    (8, 1_000, 7_608, 0, False, 0, 0, 0, 397, 1_000, 7_608, 1_899),
    (9, 1_000, 7_608, 0, False, 0, 0, 0, 398, 1_000, 7_608, 1_899),
)
"""Strategy C (plan §15.2): decree on turn 1 only (250 < 283, the bargain), legislate from turn 2
on (the bargain is already cheaper than 250 by then), investing the smaller of the 200 cap and
whatever opening capital leaves after the route -- capped at 200 throughout here since the route
never gets expensive enough to eat the whole 200. `cum_baseline` (always-decree) is `250 * turn`,
computed inline rather than tabulated."""


def test_decree_state_sequential_calibration_matches_the_plan_exactly() -> None:
    """(T11, T11b context) Drives the REAL engine turn 1-9 on `decree_state`, taking the cheaper
    of decree (250) or the cheapest legislative bargain each turn, investing 100-200 in
    `opposition_party/main` from what capital remains after the route. Asserts every field the
    plan requires, every turn, exactly as the `deficit_demo` test does."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    cum_strategy = 0
    for (
        turn,
        opening,
        opening_rel,
        bargain,
        route_is_decree,
        route_cost,
        invest,
        total,
        regen,
        closing,
        closing_rel,
        exp_cum_s,
    ) in _DECREE_STATE_TABLE:
        player = state.world.countries[state.world.player_country_id]
        assert player.politics.political_capital == opening, f"turn {turn}: opening capital"
        bloc = next(
            b
            for p in player.politics.legislature.parties
            for b in p.blocs
            if p.id == "opposition_party" and b.id == "main"
        )
        assert bloc.government_relationship_bps == opening_rel, f"turn {turn}: opening relationship"

        computed_bargain, allocation = _bargain_for(state)
        assert computed_bargain == bargain, f"turn {turn}: cheapest bargain"
        # Route selection (plan §15.2, strategy C): decree only when a real bargain exists AND
        # costs more than the fixed decree price -- a free bargain (0) is always cheaper to
        # legislate than to decree.
        use_decree = bargain > 0 and bargain > DECREE_POLITICAL_CAPITAL_COST
        assert use_decree == route_is_decree, f"turn {turn}: route selection"
        computed_route_cost = DECREE_POLITICAL_CAPITAL_COST if use_decree else bargain
        assert computed_route_cost == route_cost, f"turn {turn}: route cost"

        route = ProposalRoute.DECREE if use_decree else ProposalRoute.LEGISLATIVE
        decision_objs: list[BudgetDecision | BlocRelationshipInvestmentDecision] = [
            _budget_for(state, route=route, allocation=allocation)
        ]
        if invest > 0:
            decision_objs.append(
                BlocRelationshipInvestmentDecision(
                    investments=(
                        BlocInvestment(
                            party_id="opposition_party", bloc_id="main", political_capital=invest
                        ),
                    )
                )
            )
        decisions = _decisions_for(state, *decision_objs)
        assert total <= opening, f"turn {turn}: total commitment must not exceed opening capital"

        resolution = resolve_turn(state, decisions)
        report = resolution.report
        pcr = report.political_capital
        assert pcr is not None
        assert pcr.total_committed == total, f"turn {turn}: total_committed"
        assert pcr.political_capital_regeneration == regen, f"turn {turn}: regeneration"
        assert pcr.closing_political_capital == closing, f"turn {turn}: closing capital"
        assert pcr.closing_political_capital == min(
            player.politics.political_capital_capacity, opening - total + regen
        ), f"turn {turn}: closing capital clamp identity"

        if invest > 0:
            change = pcr.relationship_changes[0]
            assert change.opening_relationship_bps == opening_rel
            assert change.closing_relationship_bps == closing_rel
            assert change.political_capital == invest

        state = resolution.state
        cum_strategy += total
        assert cum_strategy == exp_cum_s, f"turn {turn}: cumulative strategy cost"
        assert DECREE_POLITICAL_CAPITAL_COST * turn == 250 * turn


def test_decree_state_break_even_is_after_resolved_turn_8_not_turn_7() -> None:
    """(T11) Strategy C is behind the always-decree baseline for seven consecutive resolved turns
    and first becomes cheaper on turn 8 -- the `decree_state` counterpart of the `deficit_demo`
    break-even test above, pinned independently so an edit to one table cannot silently move the
    other's headline claim."""
    cum_s = 0
    for turn, *_rest, total, _regen, _closing, _closing_rel, exp_cum_s in (
        (row[0], row[7], row[8], row[9], row[10], row[11]) for row in _DECREE_STATE_TABLE
    ):
        cum_s += total
        cum_decree_baseline = DECREE_POLITICAL_CAPITAL_COST * turn
        assert cum_s == exp_cum_s
        if turn <= 7:
            assert cum_s > cum_decree_baseline, f"turn {turn}: strategy must still be behind"
        if turn == 8:
            assert cum_s < cum_decree_baseline, "turn 8: strategy must be first cheaper here"


def test_repeated_450_commitment_is_affordable_turn_1_but_not_turn_2() -> None:
    """(T11b) The revision-1 "decree 250 + invest 200 every turn" strategy is arithmetically
    impossible past its first turn: 450 fits inside `decree_state`'s opening 500 (turn 1), but
    turn 2 opens at 433 (per `_DECREE_STATE_TABLE` row 2) and `250 + 200 = 450` does not fit
    there. Both halves are asserted against the REAL engine, not merely arithmetic: turn 1 is
    submitted and resolves; turn 2's identical decision is submitted and rejected atomically, with
    the input state left byte-identical."""
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    opening_turn1 = state.world.countries[state.world.player_country_id].politics.political_capital
    assert opening_turn1 == 500
    assert opening_turn1 >= 250 + 200, "turn 1: 450 must be affordable"

    decisions_turn1 = _decisions_for(
        state,
        BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE),
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=200),
            )
        ),
    )
    resolution = resolve_turn(state, decisions_turn1)
    state_after_turn1 = resolution.state
    opening_turn2 = state_after_turn1.world.countries[
        state_after_turn1.world.player_country_id
    ].politics.political_capital
    assert opening_turn2 == 433
    assert opening_turn2 < 250 + 200, "turn 2: 450 must now be UNaffordable"

    decisions_turn2 = _decisions_for(
        state_after_turn1,
        BudgetDecision(personal_income_rate_bps=3_000, route=ProposalRoute.DECREE),
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(party_id="opposition_party", bloc_id="main", political_capital=200),
            )
        ),
    )
    with pytest.raises(TurnResolutionError) as excinfo:
        resolve_turn(state_after_turn1, decisions_turn2)
    assert isinstance(excinfo.value.__cause__, DecisionSetError)

    # Atomicity: nothing about the passed-in state was mutated by the rejected attempt.
    unchanged_capital = state_after_turn1.world.countries[
        state_after_turn1.world.player_country_id
    ].politics.political_capital
    assert unchanged_capital == 433


# --- §15.3 tiny_valid: relationship investment widens margin, does not change passage -----------

# (turn, lower_supporting, lower_total, lower_margin, upper_supporting, upper_total, upper_margin)
_TINY_VALID_MARGIN_TABLE = (
    (1, 58, 100, 7, 33, 60, 2),
    (2, 58, 100, 7, 34, 60, 3),
    (3, 59, 100, 8, 34, 60, 3),
    (7, 60, 100, 9, 34, 60, 3),
)
"""Investing 100/turn in `rural_alliance/farmers` (opening relationship +2,000, gap 8,000).
Passage is never in doubt at any point (`tiny_valid` is a majority government); the honest finding
is that a majority government buys MARGIN with relationship investment, not passage. Corrected
against the plan's own revision-1 draft, which claimed both chambers moved after a single
investment: the upper chamber gains its seat at turn 2, the lower not until turn 3, and the second
lower seat not until turn 7."""


def test_tiny_valid_relationship_investment_widens_margin_not_passage() -> None:
    """(T7) Drives the REAL engine on `tiny_valid`, investing 100/turn, and confirms passage is
    unaffected (both chambers PASS from turn 1) while the margin widens on the pinned turns above
    -- the asymmetry (upper moves first, at turn 2; lower not until turn 3) is the corrected
    finding revision 1 got wrong."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    pinned = {row[0]: row for row in _TINY_VALID_MARGIN_TABLE}
    for turn in range(1, 8):
        new_rate = (
            state.world.countries[
                state.world.player_country_id
            ].finance.tax_policy.personal_income_rate_bps
            + 500
        )
        decisions = _decisions_for(
            state,
            BlocRelationshipInvestmentDecision(
                investments=(
                    BlocInvestment(
                        party_id="rural_alliance", bloc_id="farmers", political_capital=100
                    ),
                )
            ),
            BudgetDecision(personal_income_rate_bps=new_rate, route=ProposalRoute.LEGISLATIVE),
        )
        resolution = resolve_turn(state, decisions)
        legislative = resolution.report.legislative
        assert legislative is not None
        lower = next(c for c in legislative.chambers if c.chamber.value == "lower")
        upper = next(c for c in legislative.chambers if c.chamber.value == "upper")
        assert lower.passed and upper.passed, f"turn {turn}: passage must never be in doubt"

        if turn in pinned:
            (
                _,
                lower_supporting,
                lower_total,
                lower_margin,
                upper_supporting,
                upper_total,
                upper_margin,
            ) = pinned[turn]
            assert lower.supporting_seats == lower_supporting, f"turn {turn}: lower supporting"
            assert lower.total_seats == lower_total
            assert lower.supporting_seats - lower.required_yes_seats == lower_margin
            assert upper.supporting_seats == upper_supporting, f"turn {turn}: upper supporting"
            assert upper.total_seats == upper_total
            assert upper.supporting_seats - upper.required_yes_seats == upper_margin

        state = resolution.state


# --- T7: the one-turn delay, in isolation ---------------------------------------------------


def test_relationship_investment_never_changes_the_vote_held_earlier_that_same_turn() -> None:
    """(T7) The structural proof, isolated from the calibration tables above: submitting a
    relationship investment ALONGSIDE a budget proposal in the SAME turn produces the exact same
    vote tally as submitting the budget proposal ALONE that turn -- the investment can only ever
    affect a LATER vote, never the one it was submitted with, because slot 1 (the vote) runs
    entirely before slot 11 (the relationship application)."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")

    budget_only = _decisions_for(
        state, BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.LEGISLATIVE)
    )
    budget_only_resolution = resolve_turn(state, budget_only)
    budget_only_legislative = budget_only_resolution.report.legislative
    assert budget_only_legislative is not None

    mixed = _decisions_for(
        state,
        BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.LEGISLATIVE),
        BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        ),
    )
    mixed_resolution = resolve_turn(state, mixed)
    mixed_legislative = mixed_resolution.report.legislative
    assert mixed_legislative is not None

    # Every chamber/bloc vote figure is identical between the two runs -- the investment changed
    # NOTHING about this turn's vote, only recorded a change that applies afterward (slot 11).
    assert budget_only_legislative.chambers == mixed_legislative.chambers
    assert budget_only_legislative.blocs == mixed_legislative.blocs
    assert budget_only_legislative.outcome == mixed_legislative.outcome

    # And the relationship DID move in the mixed run's resulting state, proving the investment was
    # not simply ignored -- it was deferred, not dropped.
    mixed_bloc = next(
        b
        for p in mixed_resolution.state.world.countries[
            mixed_resolution.state.world.player_country_id
        ].politics.legislature.parties
        for b in p.blocs
        if p.id == "citizens_bloc" and b.id == "moderates"
    )
    budget_only_bloc = next(
        b
        for p in budget_only_resolution.state.world.countries[
            budget_only_resolution.state.world.player_country_id
        ].politics.legislature.parties
        for b in p.blocs
        if p.id == "citizens_bloc" and b.id == "moderates"
    )
    assert mixed_bloc.government_relationship_bps != budget_only_bloc.government_relationship_bps
