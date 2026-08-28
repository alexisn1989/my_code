"""Phase 3B2B closeout Part 2: restores the plan's full binding §12 calibration coverage.

`test_relationship_memory_calibration.py` pinned only the phase's central claims (the 4,856 fixed
point, the -1,600 decree-only band) and deferred the plan's full 16-strategy matrix (3
`deficit_demo` + 8 `decree_state` + 5 `tiny_valid`) to ADR 0012's "what is deferred" section. That
deferral was a real, undisclosed scope reduction from the approved plan, which made the matrix
binding. This file restores it.

Every literal table below was produced by a scratch driver (outside the repository) that imports
and calls this exact, unmodified backend package -- `resolve_turn`, `_exhaustive_cheapest_bargain`
(the same bounded-knapsack DP `test_decree_capital_calibration.py` proves optimal), and
`tax_policy_change` -- turn by turn, against the real, unmodified scenario content. No number here
was hand-derived or adjusted to fit the plan's own §12 tables. Every one of them reproduced the
plan's precomputed figures exactly on this pass (crossover turns, cumulative totals, fixed points,
chamber seat counts) -- "reality wins" did not require any correction this time, but the discipline
is the same either way: these are the real engine's own numbers, checked against the plan, not
assumed from it.

`_bargain_for` intentionally reuses `test_decree_capital_calibration._exhaustive_cheapest_bargain`
rather than a third reimplementation -- that DP is itself independently proven optimal elsewhere,
so re-deriving it a third time here would add no additional guarantee, only drift risk.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
)
from app.simulation.legislative_voting import tax_policy_change
from app.simulation.legislature import ProposalRoute
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState
from tests.conftest import SCENARIO_DIR
from tests.test_decree_capital_calibration import _exhaustive_cheapest_bargain

# --- shared driving helpers --------------------------------------------------------------------


def _decisions_for(state: GameState, *decision_objs: object) -> DecisionSet:  # type: ignore[no-untyped-def]
    ordered = sorted(decision_objs, key=lambda d: d.kind)  # type: ignore[attr-defined]
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=tuple(ordered),  # type: ignore[arg-type]
    )


def _bargain_for(state: GameState, target_rate: int) -> tuple[int, dict[tuple[str, str], int]]:
    """This turn's cheapest passing bargain (summed across every chamber) against the CURRENT
    (opening) legislature, for an absolute personal-income target."""
    player = state.world.countries[state.world.player_country_id]
    legislature = player.politics.legislature
    assert legislature is not None
    current_rate = player.finance.tax_policy.personal_income_rate_bps
    tax_change = tax_policy_change(rate_changes=((current_rate, target_rate),))
    total_cost = 0
    merged_allocation: dict[tuple[str, str], int] = {}
    for chamber_state in legislature.chambers:
        minimum_spend, allocation, _supporting, _required = _exhaustive_cheapest_bargain(
            legislature=legislature,
            chamber=chamber_state.chamber,
            tax_change=tax_change,
            total_seats=chamber_state.total_seats,
        )
        total_cost += minimum_spend or 0
        for key, capital in allocation.items():
            if capital > 0:
                merged_allocation[key] = max(merged_allocation.get(key, 0), capital)
    return total_cost, merged_allocation


def _influence_from(allocation: dict[tuple[str, str], int]) -> tuple[InfluenceAllocation, ...]:
    return tuple(
        InfluenceAllocation(party_id=p, bloc_id=b, political_capital=c)
        for (p, b), c in sorted(allocation.items())
    )


def _bloc(state: GameState, *, country_id: str, party_id: str, bloc_id: str):  # type: ignore[no-untyped-def]
    politics = state.world.countries[country_id].politics
    return next(
        b
        for p in politics.legislature.parties
        for b in p.blocs
        if p.id == party_id and b.id == bloc_id
    )


# --- deficit_demo: three strategies (A, B, and C, itself run direct and invest) -----------------
#
# (turn, target_bps, genuine, bargain_cost, invest, total_committed, opening_capital,
#  closing_capital, cumulative_committed, focus_closing_relationship_bps,
#  decay_component_bps, investment_component_bps, policy_reaction_component_bps,
#  decree_bypass_component_bps)
#
# Focus bloc throughout: citizens_bloc/moderates (baseline -2,000, tax_preference_bps -2,000).

_TABLE_DEFICIT_DEMO_A = (
    (1, 2000, True, 162, 0, 162, 300, 519, 162, -2050, 0, 0, -50, 0),
    (2, 2000, False, 149, 0, 149, 519, 752, 311, -2044, 6, 0, 0, 0),
    (3, 2000, False, 148, 0, 148, 752, 800, 459, -2039, 5, 0, 0, 0),
    (4, 2000, False, 148, 0, 148, 800, 800, 607, -2035, 4, 0, 0, 0),
    (5, 2000, False, 148, 0, 148, 800, 800, 755, -2031, 4, 0, 0, 0),
    (6, 2000, False, 148, 0, 148, 800, 800, 903, -2028, 3, 0, 0, 0),
    (7, 2000, False, 148, 0, 148, 800, 800, 1051, -2025, 3, 0, 0, 0),
    (8, 2000, False, 148, 0, 148, 800, 800, 1199, -2022, 3, 0, 0, 0),
    (9, 2000, False, 148, 0, 148, 800, 800, 1347, -2020, 2, 0, 0, 0),
    (10, 2000, False, 148, 0, 148, 800, 800, 1495, -2018, 2, 0, 0, 0),
    (11, 2000, False, 148, 0, 148, 800, 800, 1643, -2016, 2, 0, 0, 0),
    (12, 2000, False, 148, 0, 148, 800, 800, 1791, -2014, 2, 0, 0, 0),
    (13, 2000, False, 148, 0, 148, 800, 800, 1939, -2013, 1, 0, 0, 0),
    (14, 2000, False, 148, 0, 148, 800, 800, 2087, -2012, 1, 0, 0, 0),
    (15, 2000, False, 148, 0, 148, 800, 800, 2235, -2011, 1, 0, 0, 0),
    (16, 2000, False, 148, 0, 148, 800, 800, 2383, -2010, 1, 0, 0, 0),
    (17, 2000, False, 148, 0, 148, 800, 800, 2531, -2009, 1, 0, 0, 0),
    (18, 2000, False, 148, 0, 148, 800, 800, 2679, -2008, 1, 0, 0, 0),
    (19, 2000, False, 148, 0, 148, 800, 800, 2827, -2007, 1, 0, 0, 0),
    (20, 2000, False, 148, 0, 148, 800, 800, 2975, -2006, 1, 0, 0, 0),
)
"""Strategy A: direct bargaining every turn, one-time genuine rise to 2,000bps (turn 1), held
(resubmitted legislatively, unaided by further investment) every turn after."""

_TABLE_DEFICIT_DEMO_B = (
    (1, 2000, True, 162, 100, 262, 300, 419, 262, -50, 0, 2000, -50, 0),
    (2, 2000, False, 109, 100, 209, 419, 592, 471, 1382, -243, 1675, 0, 0),
    (3, 2000, False, 80, 100, 180, 592, 796, 651, 2396, -422, 1436, 0, 0),
    (4, 2000, False, 60, 100, 160, 796, 800, 811, 3114, -549, 1267, 0, 0),
    (5, 2000, False, 45, 100, 145, 800, 800, 956, 3622, -639, 1147, 0, 0),
    (6, 2000, False, 35, 100, 135, 800, 800, 1091, 3983, -702, 1063, 0, 0),
    (7, 2000, False, 28, 100, 128, 800, 800, 1219, 4238, -747, 1002, 0, 0),
    (8, 2000, False, 23, 100, 123, 800, 800, 1342, 4419, -779, 960, 0, 0),
    (9, 2000, False, 19, 100, 119, 800, 800, 1461, 4547, -802, 930, 0, 0),
    (10, 2000, False, 17, 100, 117, 800, 800, 1578, 4637, -818, 908, 0, 0),
    (11, 2000, False, 15, 100, 115, 800, 800, 1693, 4701, -829, 893, 0, 0),
    (12, 2000, False, 14, 100, 114, 800, 800, 1807, 4747, -837, 883, 0, 0),
    (13, 2000, False, 13, 100, 113, 800, 800, 1920, 4779, -843, 875, 0, 0),
    (14, 2000, False, 12, 100, 112, 800, 800, 2032, 4802, -847, 870, 0, 0),
    (15, 2000, False, 12, 100, 112, 800, 800, 2144, 4818, -850, 866, 0, 0),
    (16, 2000, False, 12, 100, 112, 800, 800, 2256, 4829, -852, 863, 0, 0),
    (17, 2000, False, 11, 100, 111, 800, 800, 2367, 4837, -853, 861, 0, 0),
    (18, 2000, False, 11, 100, 111, 800, 800, 2478, 4843, -854, 860, 0, 0),
    (19, 2000, False, 11, 100, 111, 800, 800, 2589, 4847, -855, 859, 0, 0),
    (20, 2000, False, 11, 100, 111, 800, 800, 2700, 4850, -855, 858, 0, 0),
)
"""Strategy B: Strategy A's identical targets, plus 100/turn invested in citizens_bloc/moderates.
Turn 20 has not yet reached the fixed point (4,850); test_deficit_demo_strategy_b_reaches_the_
controlled_4856_fixed_point below extends this same strategy to turn 30 to show it does."""

_TABLE_DEFICIT_DEMO_C_DIRECT = (
    (1, 2000, True, 162, 0, 162, 300, 519, 162, -2050, 0, 0, -50, 0),
    (2, 2500, True, 163, 0, 163, 519, 738, 325, -2094, 6, 0, -50, 0),
    (3, 3000, True, 163, 0, 163, 738, 800, 488, -2133, 11, 0, -50, 0),
    (4, 3500, True, 164, 0, 164, 800, 800, 652, -2167, 16, 0, -50, 0),
    (5, 4000, True, 164, 0, 164, 800, 800, 816, -2197, 20, 0, -50, 0),
    (6, 4500, True, 165, 0, 165, 800, 800, 981, -2223, 24, 0, -50, 0),
    (7, 5000, True, 165, 0, 165, 800, 800, 1146, -2246, 27, 0, -50, 0),
    (8, 5000, False, 151, 0, 151, 800, 800, 1297, -2216, 30, 0, 0, 0),
    (9, 5000, False, 151, 0, 151, 800, 800, 1448, -2189, 27, 0, 0, 0),
    (10, 5000, False, 150, 0, 150, 800, 800, 1598, -2166, 23, 0, 0, 0),
    (11, 5000, False, 150, 0, 150, 800, 800, 1748, -2146, 20, 0, 0, 0),
    (12, 5000, False, 150, 0, 150, 800, 800, 1898, -2128, 18, 0, 0, 0),
    (13, 5000, False, 150, 0, 150, 800, 800, 2048, -2112, 16, 0, 0, 0),
    (14, 5000, False, 149, 0, 149, 800, 800, 2197, -2098, 14, 0, 0, 0),
    (15, 5000, False, 149, 0, 149, 800, 800, 2346, -2086, 12, 0, 0, 0),
    (16, 5000, False, 149, 0, 149, 800, 800, 2495, -2076, 10, 0, 0, 0),
    (17, 5000, False, 149, 0, 149, 800, 800, 2644, -2067, 9, 0, 0, 0),
    (18, 5000, False, 149, 0, 149, 800, 800, 2793, -2059, 8, 0, 0, 0),
    (19, 5000, False, 149, 0, 149, 800, 800, 2942, -2052, 7, 0, 0, 0),
    (20, 5000, False, 149, 0, 149, 800, 800, 3091, -2046, 6, 0, 0, 0),
)
"""Strategy C-direct: a genuine seven-step staircase (2,000..5,000bps, turns 1-7), held after,
direct bargaining, no investment."""

_TABLE_DEFICIT_DEMO_C_INVEST = (
    (1, 2000, True, 162, 100, 262, 300, 419, 262, -50, 0, 2000, -50, 0),
    (2, 2500, True, 123, 100, 223, 419, 578, 485, 1332, -243, 1675, -50, 0),
    (3, 3000, True, 95, 100, 195, 578, 767, 680, 2310, -416, 1444, -50, 0),
    (4, 3500, True, 75, 100, 175, 767, 800, 855, 3003, -538, 1281, -50, 0),
    (5, 4000, True, 61, 100, 161, 800, 800, 1016, 3494, -625, 1166, -50, 0),
    (6, 4500, True, 51, 100, 151, 800, 800, 1167, 3842, -686, 1084, -50, 0),
    (7, 5000, True, 44, 100, 144, 800, 800, 1311, 4088, -730, 1026, -50, 0),
    (8, 5000, False, 25, 100, 125, 800, 800, 1436, 4312, -761, 985, 0, 0),
    (9, 5000, False, 20, 100, 120, 800, 800, 1556, 4471, -789, 948, 0, 0),
    (10, 5000, False, 17, 100, 117, 800, 800, 1673, 4584, -808, 921, 0, 0),
    (11, 5000, False, 15, 100, 115, 800, 800, 1788, 4663, -823, 902, 0, 0),
    (12, 5000, False, 14, 100, 114, 800, 800, 1902, 4720, -832, 889, 0, 0),
    (13, 5000, False, 13, 100, 113, 800, 800, 2015, 4760, -840, 880, 0, 0),
    (14, 5000, False, 12, 100, 112, 800, 800, 2127, 4788, -845, 873, 0, 0),
    (15, 5000, False, 12, 100, 112, 800, 800, 2239, 4808, -848, 868, 0, 0),
    (16, 5000, False, 11, 100, 111, 800, 800, 2350, 4822, -851, 865, 0, 0),
    (17, 5000, False, 11, 100, 111, 800, 800, 2461, 4833, -852, 863, 0, 0),
    (18, 5000, False, 11, 100, 111, 800, 800, 2572, 4840, -854, 861, 0, 0),
    (19, 5000, False, 11, 100, 111, 800, 800, 2683, 4845, -855, 860, 0, 0),
    (20, 5000, False, 11, 100, 111, 800, 800, 2794, 4849, -855, 859, 0, 0),
)
"""Strategy C-invest: Strategy C-direct's identical staircase, plus 100/turn invested."""


def _run_deficit_demo_strategy(table, *, invest_capital, targets_by_turn):  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    cumulative = 0
    for (
        turn,
        target,
        genuine,
        bargain,
        invest,
        total,
        opening_capital,
        closing_capital,
        expected_cum,
        closing_rel,
        decay,
        investment,
        policy,
        decree_bypass,
    ) in table:
        assert target == targets_by_turn(turn), f"turn {turn}: expected target mismatch in table"
        player = state.world.countries[state.world.player_country_id]
        assert player.politics.political_capital == opening_capital, f"turn {turn}: opening capital"
        current_rate = player.finance.tax_policy.personal_income_rate_bps
        assert (current_rate != target) == genuine, f"turn {turn}: genuine flag vs rate delta"

        computed_bargain, allocation = _bargain_for(state, target)
        assert computed_bargain == bargain, f"turn {turn}: cheapest bargain"

        decisions_list: list[object] = [
            BudgetDecision(
                personal_income_rate_bps=target,
                route=ProposalRoute.LEGISLATIVE,
                influence=_influence_from(allocation),
            )
        ]
        if invest_capital and invest > 0:
            decisions_list.append(
                BlocRelationshipInvestmentDecision(
                    investments=(
                        BlocInvestment(
                            party_id="citizens_bloc",
                            bloc_id="moderates",
                            political_capital=invest_capital,
                        ),
                    )
                )
            )
        assert total <= opening_capital, f"turn {turn}: total commitment must not exceed opening"

        resolution = resolve_turn(state, _decisions_for(state, *decisions_list))
        report = resolution.report
        pcr = report.political_capital
        assert pcr is not None
        assert pcr.total_committed == total, f"turn {turn}: total_committed"
        assert pcr.closing_political_capital == closing_capital, f"turn {turn}: closing capital"

        prr = report.political_relationship
        row = None
        if prr is not None:
            row = next(
                (
                    r
                    for r in prr.blocs
                    if r.party_id == "citizens_bloc" and r.bloc_id == "moderates"
                ),
                None,
            )
        if decay or investment or policy or decree_bypass:
            assert row is not None, f"turn {turn}: expected a relationship-memory row"
            assert row.decay_component_bps == decay, f"turn {turn}: decay component"
            assert row.investment_component_bps == investment, f"turn {turn}: investment component"
            assert row.policy_reaction_component_bps == policy, f"turn {turn}: policy component"
            assert row.decree_bypass_component_bps == decree_bypass, f"turn {turn}: decree bypass"
            assert row.closing_relationship_bps == closing_rel, f"turn {turn}: row closing"

        state = resolution.state
        closing_bloc = _bloc(
            state, country_id="strapped", party_id="citizens_bloc", bloc_id="moderates"
        )
        assert closing_bloc.government_relationship_bps == closing_rel, (
            f"turn {turn}: state closing"
        )

        cumulative += total
        assert cumulative == expected_cum, f"turn {turn}: cumulative committed"
    return state


def _staircase_target(turn: int) -> int:
    stair = (2000, 2500, 3000, 3500, 4000, 4500, 5000)
    return stair[turn - 1] if turn <= 7 else stair[-1]


def test_deficit_demo_strategy_a_direct_bargaining_one_time_rise() -> None:
    """(§12.1 Strategy A) Direct bargaining every turn; the target genuinely rises once (turn 1)
    and is held (resubmitted legislatively) thereafter. Every field the plan requires is checked
    every turn: target, genuineness, cheapest bargain, total commitment, affordability,
    capital open/close, all four relationship components, and cumulative commitment."""
    _run_deficit_demo_strategy(
        _TABLE_DEFICIT_DEMO_A, invest_capital=0, targets_by_turn=lambda t: 2000
    )


def test_deficit_demo_strategy_b_bargain_plus_investment() -> None:
    """(§12.1 Strategy B) Strategy A's identical targets, plus 100/turn invested in
    citizens_bloc/moderates -- the crossover-vs-Strategy-A comparison test below reads both this
    table and Strategy A's."""
    _run_deficit_demo_strategy(
        _TABLE_DEFICIT_DEMO_B, invest_capital=100, targets_by_turn=lambda t: 2000
    )


def test_deficit_demo_strategy_c_direct_seven_step_staircase() -> None:
    """(§12.1 Strategy C-direct) A genuine seven-step staircase to 5,000bps, held after, no
    investment."""
    _run_deficit_demo_strategy(
        _TABLE_DEFICIT_DEMO_C_DIRECT, invest_capital=0, targets_by_turn=_staircase_target
    )


def test_deficit_demo_strategy_c_invest_seven_step_staircase_plus_investment() -> None:
    """(§12.1 Strategy C-invest) Strategy C-direct's identical staircase, plus 100/turn invested."""
    _run_deficit_demo_strategy(
        _TABLE_DEFICIT_DEMO_C_INVEST, invest_capital=100, targets_by_turn=_staircase_target
    )


def test_deficit_demo_strategy_b_crosses_strategy_a_at_resolved_turn_13_not_turn_8() -> None:
    """(§12.1, §21 decision 3; R13) Phase 3B2A's turn-8 break-even does NOT survive under 3B2B's
    decay: the cumulative cost of investing-and-bargaining (Strategy B) first drops below
    never-investing (Strategy A) at resolved turn 13, five turns later than the no-decay original,
    because decay now taxes the held relationship every turn. Both cumulative sequences are
    re-derived here from the tables above, not hand-copied, so a table edit that breaks the
    crossover breaks this test too."""
    cum_a = 0
    cum_b = 0
    for row_a, row_b in zip(_TABLE_DEFICIT_DEMO_A, _TABLE_DEFICIT_DEMO_B, strict=True):
        turn = row_a[0]
        cum_a += row_a[5]
        cum_b += row_b[5]
        if turn <= 12:
            assert cum_a <= cum_b, f"turn {turn}: strategy A must still be cheapest or tied"
        if turn == 13:
            assert cum_a == 1939 and cum_b == 1920
            assert cum_b < cum_a, "turn 13: strategy B must have just become cheaper"
        if turn == 20:
            assert cum_a - cum_b == 275, "turn 20: strategy B must be exactly 275 cheaper"


def test_deficit_demo_strategy_c_invest_crosses_c_direct_at_resolved_turn_13_too() -> None:
    """(§12.1; R13) The same turn-13 crossover, independently reproduced against a completely
    different absolute-target schedule (the seven-step staircase) -- strong evidence the crossover
    turn is a property of the investment mechanic against this scenario's decay-adjusted DP, not an
    artifact of one particular staircase shape."""
    cum_direct = 0
    cum_invest = 0
    for row_d, row_i in zip(
        _TABLE_DEFICIT_DEMO_C_DIRECT, _TABLE_DEFICIT_DEMO_C_INVEST, strict=True
    ):
        turn = row_d[0]
        cum_direct += row_d[5]
        cum_invest += row_i[5]
        if turn == 12:
            assert cum_direct == 1898 and cum_invest == 1902
            assert cum_direct < cum_invest, "turn 12: direct must still be favored"
        if turn == 13:
            assert cum_direct == 2048 and cum_invest == 2015
            assert cum_invest < cum_direct, "turn 13: invest must have just become cheaper"
        if turn == 20:
            assert cum_direct - cum_invest == 297, "turn 20: invest must be exactly 297 cheaper"


def test_deficit_demo_strategy_b_reaches_the_controlled_4856_fixed_point() -> None:
    """(§12.1, §21 decision 3; the phase's central claim) Strategy B's table above stops at turn
    20 (closing 4,850, still converging); driven ten turns further under the SAME strategy (bargain
    every turn + invest 100/turn), it reaches the identical +4,856 fixed point
    `test_relationship_memory_calibration.py` pins for the pure-investment case -- confirming the
    fixed point does not depend on whether a legislative bargain is also paid every turn, only on
    decay-plus-investment dynamics once the one-time turn-1 policy shock has decayed away."""
    state = _run_deficit_demo_strategy(
        _TABLE_DEFICIT_DEMO_B, invest_capital=100, targets_by_turn=lambda t: 2000
    )
    expected_from_turn_24 = 4856
    for _ in range(10):
        bargain, allocation = _bargain_for(state, 2000)
        budget = BudgetDecision(
            personal_income_rate_bps=2000,
            route=ProposalRoute.LEGISLATIVE,
            influence=_influence_from(allocation),
        )
        invest = BlocRelationshipInvestmentDecision(
            investments=(
                BlocInvestment(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=100
                ),
            )
        )
        resolution = resolve_turn(state, _decisions_for(state, budget, invest))
        state = resolution.state
    closing_bloc = _bloc(
        state, country_id="strapped", party_id="citizens_bloc", bloc_id="moderates"
    )
    assert closing_bloc.government_relationship_bps == expected_from_turn_24


# --- decree_state: eight strategies --------------------------------------------------------------
#
# (turn, target_bps, route, total_committed, opening_capital, closing_capital,
#  cumulative_committed, governing_party_core_closing_bps, opposition_party_main_closing_bps)

_TABLE_S1_LEGISLATIVE_EVERY_TURN = (
    (1, 2500, "legislative", 283, 500, 600, 283, 6050, -8150),
    (2, 2500, "legislative", 246, 600, 739, 529, 6044, -8132),
    (3, 2500, "legislative", 246, 739, 881, 775, 6039, -8116),
    (4, 2500, "legislative", 246, 881, 1000, 1021, 6035, -8102),
    (5, 2500, "legislative", 245, 1000, 1000, 1266, 6031, -8090),
    (6, 2500, "legislative", 245, 1000, 1000, 1511, 6028, -8079),
    (7, 2500, "legislative", 245, 1000, 1000, 1756, 6025, -8070),
    (8, 2500, "legislative", 245, 1000, 1000, 2001, 6022, -8062),
    (9, 2500, "legislative", 244, 1000, 1000, 2245, 6020, -8055),
    (10, 2500, "legislative", 244, 1000, 1000, 2489, 6018, -8049),
    (11, 2500, "legislative", 244, 1000, 1000, 2733, 6016, -8043),
    (12, 2500, "legislative", 244, 1000, 1000, 2977, 6014, -8038),
    (13, 2500, "legislative", 244, 1000, 1000, 3221, 6013, -8034),
    (14, 2500, "legislative", 244, 1000, 1000, 3465, 6012, -8030),
    (15, 2500, "legislative", 244, 1000, 1000, 3709, 6011, -8027),
    (16, 2500, "legislative", 244, 1000, 1000, 3953, 6010, -8024),
    (17, 2500, "legislative", 244, 1000, 1000, 4197, 6009, -8021),
    (18, 2500, "legislative", 244, 1000, 1000, 4441, 6008, -8019),
    (19, 2500, "legislative", 244, 1000, 1000, 4685, 6007, -8017),
    (20, 2500, "legislative", 244, 1000, 1000, 4929, 6006, -8015),
)

_TABLE_S2_UNCHANGED_DECREE = (
    (1, 2000, "decree", 250, 500, 633, 250, 5800, -8200),
    (2, 2000, "decree", 250, 633, 768, 500, 5625, -8375),
    (3, 2000, "decree", 250, 768, 906, 750, 5471, -8529),
    (4, 2000, "decree", 250, 906, 1000, 1000, 5337, -8663),
    (5, 2000, "decree", 250, 1000, 1000, 1250, 5219, -8781),
    (6, 2000, "decree", 250, 1000, 1000, 1500, 5116, -8884),
    (7, 2000, "decree", 250, 1000, 1000, 1750, 5026, -8974),
    (8, 2000, "decree", 250, 1000, 1000, 2000, 4947, -9053),
    (9, 2000, "decree", 250, 1000, 1000, 2250, 4878, -9122),
    (10, 2000, "decree", 250, 1000, 1000, 2500, 4818, -9182),
    (11, 2000, "decree", 250, 1000, 1000, 2750, 4765, -9235),
    (12, 2000, "decree", 250, 1000, 1000, 3000, 4719, -9281),
    (13, 2000, "decree", 250, 1000, 1000, 3250, 4679, -9321),
    (14, 2000, "decree", 250, 1000, 1000, 3500, 4644, -9356),
    (15, 2000, "decree", 250, 1000, 1000, 3750, 4613, -9387),
    (16, 2000, "decree", 250, 1000, 1000, 4000, 4586, -9414),
    (17, 2000, "decree", 250, 1000, 1000, 4250, 4562, -9438),
    (18, 2000, "decree", 250, 1000, 1000, 4500, 4541, -9459),
    (19, 2000, "decree", 250, 1000, 1000, 4750, 4523, -9477),
    (20, 2000, "decree", 250, 1000, 1000, 5000, 4507, -9493),
)

_TABLE_S3_ONE_GENUINE_THEN_UNCHANGED = (
    (1, 2500, "decree", 250, 500, 633, 250, 5850, -8350),
    (2, 2500, "decree", 250, 633, 768, 500, 5668, -8507),
    (3, 2500, "decree", 250, 768, 906, 750, 5509, -8644),
    (4, 2500, "decree", 250, 906, 1000, 1000, 5370, -8764),
    (5, 2500, "decree", 250, 1000, 1000, 1250, 5248, -8869),
    (6, 2500, "decree", 250, 1000, 1000, 1500, 5142, -8961),
    (7, 2500, "decree", 250, 1000, 1000, 1750, 5049, -9041),
    (8, 2500, "decree", 250, 1000, 1000, 2000, 4967, -9111),
    (9, 2500, "decree", 250, 1000, 1000, 2250, 4896, -9173),
    (10, 2500, "decree", 250, 1000, 1000, 2500, 4834, -9227),
    (11, 2500, "decree", 250, 1000, 1000, 2750, 4779, -9274),
    (12, 2500, "decree", 250, 1000, 1000, 3000, 4731, -9315),
    (13, 2500, "decree", 250, 1000, 1000, 3250, 4689, -9351),
    (14, 2500, "decree", 250, 1000, 1000, 3500, 4652, -9383),
    (15, 2500, "decree", 250, 1000, 1000, 3750, 4620, -9411),
    (16, 2500, "decree", 250, 1000, 1000, 4000, 4592, -9435),
    (17, 2500, "decree", 250, 1000, 1000, 4250, 4568, -9456),
    (18, 2500, "decree", 250, 1000, 1000, 4500, 4547, -9474),
    (19, 2500, "decree", 250, 1000, 1000, 4750, 4528, -9490),
    (20, 2500, "decree", 250, 1000, 1000, 5000, 4512, -9504),
)

_TABLE_S4_FOUR_STEP_STAIRCASE = (
    (1, 2500, "decree", 250, 500, 633, 250, 5850, -8350),
    (2, 3000, "decree", 250, 633, 768, 500, 5718, -8657),
    (3, 3500, "decree", 250, 768, 906, 750, 5603, -8925),
    (4, 4000, "decree", 250, 906, 1000, 1000, 5502, -9160),
    (5, 4000, "decree", 250, 1000, 1000, 1250, 5364, -9215),
    (6, 4000, "decree", 250, 1000, 1000, 1500, 5243, -9264),
    (7, 4000, "decree", 250, 1000, 1000, 1750, 5137, -9306),
    (8, 4000, "decree", 250, 1000, 1000, 2000, 5044, -9343),
    (9, 4000, "decree", 250, 1000, 1000, 2250, 4963, -9376),
    (10, 4000, "decree", 250, 1000, 1000, 2500, 4892, -9404),
    (11, 4000, "decree", 250, 1000, 1000, 2750, 4830, -9429),
    (12, 4000, "decree", 250, 1000, 1000, 3000, 4776, -9451),
    (13, 4000, "decree", 250, 1000, 1000, 3250, 4729, -9470),
    (14, 4000, "decree", 250, 1000, 1000, 3500, 4687, -9487),
    (15, 4000, "decree", 250, 1000, 1000, 3750, 4651, -9502),
    (16, 4000, "decree", 250, 1000, 1000, 4000, 4619, -9515),
    (17, 4000, "decree", 250, 1000, 1000, 4250, 4591, -9526),
    (18, 4000, "decree", 250, 1000, 1000, 4500, 4567, -9536),
    (19, 4000, "decree", 250, 1000, 1000, 4750, 4546, -9544),
    (20, 4000, "decree", 250, 1000, 1000, 5000, 4527, -9551),
)

_TABLE_S5_SEVEN_STEP_STAIRCASE = (
    (1, 2500, "decree", 250, 500, 633, 250, 5850, -8350),
    (2, 3000, "decree", 250, 633, 768, 500, 5718, -8657),
    (3, 3500, "decree", 250, 768, 906, 750, 5603, -8925),
    (4, 4000, "decree", 250, 906, 1000, 1000, 5502, -9160),
    (5, 4500, "decree", 250, 1000, 1000, 1250, 5414, -9365),
    (6, 5000, "decree", 250, 1000, 1000, 1500, 5337, -9545),
    (7, 5500, "decree", 250, 1000, 1000, 1750, 5269, -9702),
    (8, 5500, "decree", 250, 1000, 1000, 2000, 5160, -9690),
    (9, 5500, "decree", 250, 1000, 1000, 2250, 5065, -9679),
    (10, 5500, "decree", 250, 1000, 1000, 2500, 4981, -9670),
    (11, 5500, "decree", 250, 1000, 1000, 2750, 4908, -9662),
    (12, 5500, "decree", 250, 1000, 1000, 3000, 4844, -9655),
    (13, 5500, "decree", 250, 1000, 1000, 3250, 4788, -9649),
    (14, 5500, "decree", 250, 1000, 1000, 3500, 4739, -9643),
    (15, 5500, "decree", 250, 1000, 1000, 3750, 4696, -9638),
    (16, 5500, "decree", 250, 1000, 1000, 4000, 4659, -9634),
    (17, 5500, "decree", 250, 1000, 1000, 4250, 4626, -9630),
    (18, 5500, "decree", 250, 1000, 1000, 4500, 4597, -9627),
    (19, 5500, "decree", 250, 1000, 1000, 4750, 4572, -9624),
    (20, 5500, "decree", 250, 1000, 1000, 5000, 4550, -9621),
)

_TABLE_S6_INVEST_PLUS_DECREE = (
    # External Wars Gate W1: closing/opening capital re-measured against the real engine with
    # decree_state's eligible dyad (exposure 3,000) live -- the security-anxiety legitimacy
    # pressure (frozen plan sec.9.4/9.5) shaves a few bps off political capital regeneration from
    # turn 4 onward. total_committed, cumulative and both bloc relationship columns are byte-
    # identical to the pre-W1 figures, confirming the shift is isolated to legitimacy-derived
    # capital regen and nothing else.
    (1, 2500, "decree", 350, 500, 533, 350, 5850, -5350),
    (2, 2500, "decree", 350, 533, 568, 700, 5668, -3323),
    (3, 2500, "decree", 350, 568, 606, 1050, 5509, -1887),
    (4, 2500, "decree", 350, 606, 643, 1400, 5370, -870),
    (5, 2500, "decree", 350, 643, 679, 1750, 5248, -150),
    (6, 2500, "decree", 350, 679, 714, 2100, 5142, 360),
    (7, 2500, "decree", 350, 714, 748, 2450, 5049, 721),
    (8, 2500, "decree", 350, 748, 781, 2800, 4967, 977),
    (9, 2500, "decree", 350, 781, 813, 3150, 4896, 1158),
    (10, 2500, "decree", 350, 813, 845, 3500, 4834, 1287),
    (11, 2500, "decree", 350, 845, 877, 3850, 4779, 1379),
    (12, 2500, "decree", 350, 877, 909, 4200, 4731, 1443),
    (13, 2500, "decree", 350, 909, 941, 4550, 4689, 1489),
    (14, 2500, "decree", 350, 941, 973, 4900, 4652, 1521),
    (15, 2500, "decree", 350, 973, 1000, 5250, 4620, 1544),
    (16, 2500, "decree", 350, 1000, 1000, 5600, 4592, 1560),
    (17, 2500, "decree", 350, 1000, 1000, 5950, 4568, 1571),
    (18, 2500, "decree", 350, 1000, 1000, 6300, 4547, 1579),
    (19, 2500, "decree", 350, 1000, 1000, 6650, 4528, 1585),
    (20, 2500, "decree", 350, 1000, 1000, 7000, 4512, 1589),
)

_TABLE_S7_INVEST_THEN_TRANSITION = (
    # External Wars Gate W1: same re-measurement as S6 above -- only turn 4's closing capital (and
    # therefore turn 5's opening capital) shifts by -3; every other column, including both bloc
    # relationship figures at every turn, is byte-identical to the pre-W1 figures.
    (1, 2500, "decree", 350, 500, 533, 350, 5850, -5350),
    (2, 2500, "legislative", 290, 533, 628, 640, 5868, -3123),
    (3, 2500, "legislative", 246, 628, 770, 886, 5884, -1545),
    (4, 2500, "legislative", 214, 770, 943, 1100, 5898, -427),
    (5, 2500, "legislative", 192, 943, 1000, 1292, 5910, 364),
    (6, 2500, "legislative", 176, 1000, 1000, 1468, 5921, 925),
    (7, 2500, "legislative", 165, 1000, 1000, 1633, 5930, 1322),
    (8, 2500, "legislative", 157, 1000, 1000, 1790, 5938, 1603),
    (9, 2500, "legislative", 151, 1000, 1000, 1941, 5945, 1802),
    (10, 2500, "legislative", 147, 1000, 1000, 2088, 5951, 1943),
    (11, 2500, "legislative", 144, 1000, 1000, 2232, 5957, 2043),
    (12, 2500, "legislative", 142, 1000, 1000, 2374, 5962, 2114),
    (13, 2500, "legislative", 141, 1000, 1000, 2515, 5966, 2164),
    (14, 2500, "legislative", 140, 1000, 1000, 2655, 5970, 2200),
    (15, 2500, "legislative", 139, 1000, 1000, 2794, 5973, 2225),
    (16, 2500, "legislative", 139, 1000, 1000, 2933, 5976, 2242),
    (17, 2500, "legislative", 138, 1000, 1000, 3071, 5979, 2255),
    (18, 2500, "legislative", 138, 1000, 1000, 3209, 5981, 2264),
    (19, 2500, "legislative", 138, 1000, 1000, 3347, 5983, 2270),
    (20, 2500, "legislative", 138, 1000, 1000, 3485, 5985, 2275),
)

_TABLE_S8_ALTERNATING = (
    (1, 2500, "legislative", 283, 500, 600, 283, 6050, -8150),
    (2, 2500, "decree", 250, 600, 735, 533, 5844, -8332),
    (3, 2500, "legislative", 250, 735, 873, 783, 5863, -8291),
    (4, 2500, "decree", 250, 873, 1000, 1033, 5680, -8455),
    (5, 2500, "legislative", 252, 1000, 1000, 1285, 5720, -8399),
    (6, 2500, "decree", 250, 1000, 1000, 1535, 5555, -8550),
    (7, 2500, "legislative", 254, 1000, 1000, 1789, 5610, -8482),
    (8, 2500, "decree", 250, 1000, 1000, 2039, 5458, -8622),
    (9, 2500, "legislative", 256, 1000, 1000, 2295, 5525, -8545),
    (10, 2500, "decree", 250, 1000, 1000, 2545, 5384, -8677),
    (11, 2500, "legislative", 257, 1000, 1000, 2802, 5461, -8593),
    (12, 2500, "decree", 250, 1000, 1000, 3052, 5328, -8719),
    (13, 2500, "legislative", 258, 1000, 1000, 3310, 5412, -8630),
    (14, 2500, "decree", 250, 1000, 1000, 3560, 5285, -8752),
    (15, 2500, "legislative", 258, 1000, 1000, 3818, 5374, -8658),
    (16, 2500, "decree", 250, 1000, 1000, 4068, 5252, -8776),
    (17, 2500, "legislative", 259, 1000, 1000, 4327, 5345, -8679),
    (18, 2500, "decree", 250, 1000, 1000, 4577, 5226, -8795),
    (19, 2500, "legislative", 259, 1000, 1000, 4836, 5322, -8696),
    (20, 2500, "decree", 250, 1000, 1000, 5086, 5206, -8809),
)

_DECREE_STATE_STRATEGIES = {
    "s1_legislative_every_turn": _TABLE_S1_LEGISLATIVE_EVERY_TURN,
    "s2_unchanged_decree": _TABLE_S2_UNCHANGED_DECREE,
    "s3_one_genuine_then_unchanged": _TABLE_S3_ONE_GENUINE_THEN_UNCHANGED,
    "s4_four_step_staircase": _TABLE_S4_FOUR_STEP_STAIRCASE,
    "s5_seven_step_staircase": _TABLE_S5_SEVEN_STEP_STAIRCASE,
    "s6_invest_plus_decree": _TABLE_S6_INVEST_PLUS_DECREE,
    "s7_invest_then_transition": _TABLE_S7_INVEST_THEN_TRANSITION,
    "s8_alternating": _TABLE_S8_ALTERNATING,
}


def _run_decree_state_strategy(table):  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    cumulative = 0
    for (
        turn,
        target,
        route,
        total,
        opening_capital,
        closing_capital,
        expected_cum,
        core_closing,
        opp_closing,
    ) in table:
        player = state.world.countries[state.world.player_country_id]
        assert player.politics.political_capital == opening_capital, f"turn {turn}: opening capital"

        decisions_list: list[object] = []
        if route == "legislative":
            bargain, allocation = _bargain_for(state, target)
            decisions_list.append(
                BudgetDecision(
                    personal_income_rate_bps=target,
                    route=ProposalRoute.LEGISLATIVE,
                    influence=_influence_from(allocation),
                )
            )
        else:
            decisions_list.append(
                BudgetDecision(personal_income_rate_bps=target, route=ProposalRoute.DECREE)
            )

        assert total <= opening_capital, f"turn {turn}: total commitment must not exceed opening"
        resolution = resolve_turn(state, _decisions_for(state, *decisions_list))
        report = resolution.report
        pcr = report.political_capital
        assert pcr is not None
        assert pcr.total_committed == total, f"turn {turn}: total_committed"
        assert pcr.closing_political_capital == closing_capital, f"turn {turn}: closing capital"

        state = resolution.state
        core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
        opp = _bloc(state, country_id="valdrun", party_id="opposition_party", bloc_id="main")
        assert core.government_relationship_bps == core_closing, f"turn {turn}: core closing"
        assert opp.government_relationship_bps == opp_closing, f"turn {turn}: opposition closing"

        cumulative += total
        assert cumulative == expected_cum, f"turn {turn}: cumulative committed"
    return state, cumulative


def _run_decree_state_strategy_with_investment(table, *, invest_capital, invest_target):  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / "decree_state.yaml")
    cumulative = 0
    for (
        turn,
        target,
        route,
        total,
        opening_capital,
        closing_capital,
        expected_cum,
        core_closing,
        opp_closing,
    ) in table:
        player = state.world.countries[state.world.player_country_id]
        assert player.politics.political_capital == opening_capital, f"turn {turn}: opening capital"

        decisions_list: list[object] = []
        if route == "legislative":
            bargain, allocation = _bargain_for(state, target)
            decisions_list.append(
                BudgetDecision(
                    personal_income_rate_bps=target,
                    route=ProposalRoute.LEGISLATIVE,
                    influence=_influence_from(allocation),
                )
            )
        else:
            decisions_list.append(
                BudgetDecision(personal_income_rate_bps=target, route=ProposalRoute.DECREE)
            )
        decisions_list.append(
            BlocRelationshipInvestmentDecision(
                investments=(
                    BlocInvestment(
                        party_id=invest_target[0],
                        bloc_id=invest_target[1],
                        political_capital=invest_capital,
                    ),
                )
            )
        )

        assert total <= opening_capital, f"turn {turn}: total commitment must not exceed opening"
        resolution = resolve_turn(state, _decisions_for(state, *decisions_list))
        report = resolution.report
        pcr = report.political_capital
        assert pcr is not None
        assert pcr.total_committed == total, f"turn {turn}: total_committed"
        assert pcr.closing_political_capital == closing_capital, f"turn {turn}: closing capital"

        state = resolution.state
        core = _bloc(state, country_id="valdrun", party_id="governing_party", bloc_id="core")
        opp = _bloc(state, country_id="valdrun", party_id="opposition_party", bloc_id="main")
        assert core.government_relationship_bps == core_closing, f"turn {turn}: core closing"
        assert opp.government_relationship_bps == opp_closing, f"turn {turn}: opposition closing"

        cumulative += total
        assert cumulative == expected_cum, f"turn {turn}: cumulative committed"
    return state, cumulative


def test_decree_state_strategy_1_legislative_bargain_every_turn() -> None:
    """(§12.2.1 #1) Genuine rise to 2,500bps turn 1, resubmitted legislatively every turn after."""
    _run_decree_state_strategy(_TABLE_S1_LEGISLATIVE_EVERY_TURN)


def test_decree_state_strategy_2_unchanged_decree_every_turn() -> None:
    """(§12.2.1 #2; §12.2 Case 1) The target never moves from the scenario's opening 2,000bps --
    every turn's decree is content-free, so the policy component is always exactly 0 and only the
    procedural -200bps decree-bypass penalty acts, converging both blocs toward the -1,600 band."""
    _run_decree_state_strategy(_TABLE_S2_UNCHANGED_DECREE)


def test_decree_state_strategy_3_one_genuine_decree_then_unchanged() -> None:
    """(§12.2.1 #3; §12.2 Case 2) One genuine rise (turn 1), then repeated UNCHANGED re-decrees --
    the bypass penalty continues every turn even once content stops moving."""
    _run_decree_state_strategy(_TABLE_S3_ONE_GENUINE_THEN_UNCHANGED)


def test_decree_state_strategy_4_four_step_decree_staircase() -> None:
    """(§12.2.1 #4; §12.2 Case 3) A four-step genuine staircase, then held."""
    _run_decree_state_strategy(_TABLE_S4_FOUR_STEP_STAIRCASE)


def test_decree_state_strategy_5_seven_step_decree_staircase() -> None:
    """(§12.2.1 #5; §12.2 Case 3) A seven-step genuine staircase, then held."""
    _run_decree_state_strategy(_TABLE_S5_SEVEN_STEP_STAIRCASE)


def test_decree_state_strategy_6_invest_plus_decree_every_turn() -> None:
    """(§12.2.1 #6) One genuine decree (turn 1), then unchanged decrees, PLUS 100/turn invested in
    opposition_party/main every turn -- the most expensive of all eight strategies, since the flat
    250 decree cost, the -200 relationship penalty, and the 100 investment are all paid every
    single turn with the decree route continuing to re-suppress the very relationship being
    invested in."""
    _run_decree_state_strategy_with_investment(
        _TABLE_S6_INVEST_PLUS_DECREE,
        invest_capital=100,
        invest_target=("opposition_party", "main"),
    )


def test_decree_state_strategy_7_invest_then_transition_to_legislative() -> None:
    """(§12.2.1 #7) Decree once (turn 1) while investing, then transition to the legislative route
    from turn 2 onward as investment makes bargaining cheaper -- ends as the cheapest of all eight
    strategies by turn 20 (3,485 total, versus the next-best strategy's 4,929, per
    test_decree_state_strategy_7_is_cheapest_from_turn_6_and_wins_by_turn_20 below)."""
    _run_decree_state_strategy_with_investment(
        _TABLE_S7_INVEST_THEN_TRANSITION,
        invest_capital=100,
        invest_target=("opposition_party", "main"),
    )


def test_decree_state_strategy_8_alternating_legislative_and_decree() -> None:
    """(§12.2.1 #8) Alternates legislative (odd turns) and decree (even turns) at the held 2,500bps
    target."""
    _run_decree_state_strategy(_TABLE_S8_ALTERNATING)


def test_decree_state_flat_decree_strategies_commit_exactly_250_every_turn() -> None:
    """(§12.2.1's required finding) Strategies 2-5 are capital-IDENTICAL at every one of 20 turns
    (250/turn flat, since DECREE_POLITICAL_CAPITAL_COST does not depend on content) despite
    carrying completely different enacted content and completely different relationship
    consequences -- choosing WHAT to decree costs nothing extra in capital; it only costs
    relationship."""
    for table in (
        _TABLE_S2_UNCHANGED_DECREE,
        _TABLE_S3_ONE_GENUINE_THEN_UNCHANGED,
        _TABLE_S4_FOUR_STEP_STAIRCASE,
        _TABLE_S5_SEVEN_STEP_STAIRCASE,
    ):
        for row in table:
            assert row[3] == 250, f"{table} turn {row[0]}: flat decree cost must be exactly 250"
    committed_sequences = {
        name: tuple(row[3] for row in table)
        for name, table in _DECREE_STATE_STRATEGIES.items()
        if name
        in (
            "s2_unchanged_decree",
            "s3_one_genuine_then_unchanged",
            "s4_four_step_staircase",
            "s5_seven_step_staircase",
        )
    }
    sequences = list(committed_sequences.values())
    assert all(seq == sequences[0] for seq in sequences), (
        "strategies 2-5 must have byte-for-byte identical total_committed sequences"
    )


def test_decree_state_strategy_7_is_cheapest_from_turn_6_and_wins_by_turn_20() -> None:
    """(§12.2.1's required finding) Strategy 7 (invest then transition) first becomes cheaper than
    the flat-decree group's running total at resolved turn 6 (t5: 1,292 vs 1,250, decree still
    cheaper; t6: 1,468 vs 1,500, strategy 7 now cheaper) and ends turn 20 as the cheapest of all
    eight strategies (3,485), versus the next-best strategy (#1, legislative-every-turn: 4,929)."""
    cum_s7 = 0
    cum_flat = 0
    for row in _TABLE_S7_INVEST_THEN_TRANSITION:
        turn = row[0]
        cum_s7 += row[3]
        cum_flat = 250 * turn
        if turn == 5:
            assert cum_s7 == 1292 and cum_flat == 1250
            assert cum_s7 > cum_flat, "turn 5: decree must still be cheaper"
        if turn == 6:
            assert cum_s7 == 1468 and cum_flat == 1500
            assert cum_s7 < cum_flat, "turn 6: strategy 7 must have just become cheaper"
    finals = {
        name: sum(row[3] for row in table) for name, table in _DECREE_STATE_STRATEGIES.items()
    }
    assert finals["s7_invest_then_transition"] == 3485
    others = {name: total for name, total in finals.items() if name != "s7_invest_then_transition"}
    next_best_name, next_best_total = min(others.items(), key=lambda kv: kv[1])
    assert next_best_name == "s1_legislative_every_turn"
    assert next_best_total == 4929
    assert finals["s7_invest_then_transition"] < next_best_total


def test_decree_state_all_eight_strategies_stay_within_opening_capital_every_turn() -> None:
    """(§12.2.1's required finding; §22's affordability guarantee) `total_committed <=
    opening_political_capital` held for all eight strategies at every one of their 20 turns during
    the real drive above -- re-verified here directly from the pinned tables so a future table
    edit that violates it fails loudly."""
    for name, table in _DECREE_STATE_STRATEGIES.items():
        for row in table:
            turn, _target, _route, total, opening_capital = row[0], row[1], row[2], row[3], row[4]
            assert total <= opening_capital, (
                f"{name} turn {turn}: total {total} > opening {opening_capital}"
            )


# --- tiny_valid: five cases, bicameral, reported per chamber ------------------------------------
#
# (turn, target_bps, outcome, lower_supporting, lower_required, upper_supporting, upper_required)

_TABLE_CASE1_NO_PROPOSAL = (
    (1, None, "no_proposal", None, None, None, None),
    (2, None, "no_proposal", None, None, None, None),
    (3, None, "no_proposal", None, None, None, None),
    (4, None, "no_proposal", None, None, None, None),
    (5, None, "no_proposal", None, None, None, None),
    (6, None, "no_proposal", None, None, None, None),
    (7, None, "no_proposal", None, None, None, None),
    (8, None, "no_proposal", None, None, None, None),
)

_TABLE_CASE2_ONE_TIME_RISE = (
    (1, 2500, "passed_legislative", 58, 51, 33, 31),
    (2, None, "no_proposal", None, None, None, None),
    (3, None, "no_proposal", None, None, None, None),
    (4, None, "no_proposal", None, None, None, None),
    (5, None, "no_proposal", None, None, None, None),
    (6, None, "no_proposal", None, None, None, None),
    (7, None, "no_proposal", None, None, None, None),
    (8, None, "no_proposal", None, None, None, None),
)

_TABLE_CASE3_REPEATED_UNCHANGED = (
    (1, 2500, "passed_legislative", 58, 51, 33, 31),
    (2, 2500, "passed_legislative", 58, 51, 33, 31),
    (3, 2500, "passed_legislative", 58, 51, 33, 31),
    (4, 2500, "passed_legislative", 58, 51, 33, 31),
    (5, 2500, "passed_legislative", 58, 51, 33, 31),
    (6, 2500, "passed_legislative", 58, 51, 33, 31),
    (7, 2500, "passed_legislative", 58, 51, 33, 31),
    (8, 2500, "passed_legislative", 58, 51, 33, 31),
)

_TABLE_CASE4_COALITION_INSURANCE = (
    (1, 2500, "passed_legislative", 58, 51, 33, 31),
    (2, 2500, "passed_legislative", 58, 51, 34, 31),
    (3, 2500, "passed_legislative", 59, 51, 34, 31),
    (4, 2500, "passed_legislative", 59, 51, 34, 31),
    (5, 2500, "passed_legislative", 59, 51, 34, 31),
    (6, 2500, "passed_legislative", 59, 51, 34, 31),
    (7, 2500, "passed_legislative", 59, 51, 34, 31),
    (8, 2500, "passed_legislative", 59, 51, 34, 31),
)
"""Case 4: coalition-insurance investment, 100/turn in rural_alliance/farmers, target held at
2,500bps every turn. The upper chamber gains its extra seat at turn 2; the lower chamber not until
turn 3 -- the identical asymmetric finding 3B2A's own calibration test established, reproduced
under 3B2B's decay-adjusted (smaller) investment gain and still landing on the same two turns."""

_TABLE_CASE5_STAIRCASE = (
    (1, 2500, "passed_legislative", 58, 51, 33, 31),
    (2, 3000, "passed_legislative", 58, 51, 33, 31),
    (3, 3500, "passed_legislative", 58, 51, 33, 31),
    (4, 4000, "passed_legislative", 58, 51, 33, 31),
    (5, 4500, "passed_legislative", 58, 51, 34, 31),
    (6, 5000, "passed_legislative", 58, 51, 34, 31),
    (7, 5500, "passed_legislative", 58, 51, 34, 31),
    (8, 6000, "passed_legislative", 58, 51, 34, 31),
)
"""Case 5: an eight-step genuine staircase, no investment. The upper chamber gains a seat at turn
5 from POLICY REACTION ALONE, zero capital spent -- a real, DP-independent consequence of sustained
coalition-liked policy."""


def _run_tiny_valid_case(table, *, invest):  # type: ignore[no-untyped-def]
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    for turn, target, outcome, lower_s, lower_r, upper_s, upper_r in table:
        decisions_list: list[object] = []
        if target is not None:
            decisions_list.append(
                BudgetDecision(personal_income_rate_bps=target, route=ProposalRoute.LEGISLATIVE)
            )
        if invest:
            decisions_list.append(
                BlocRelationshipInvestmentDecision(
                    investments=(
                        BlocInvestment(
                            party_id="rural_alliance", bloc_id="farmers", political_capital=100
                        ),
                    )
                )
            )
        resolution = resolve_turn(
            state,
            _decisions_for(state, *decisions_list)
            if decisions_list
            else DecisionSet(
                expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
            ),
        )
        report = resolution.report
        leg = report.legislative
        assert leg is not None
        assert leg.outcome.value == outcome, f"turn {turn}: outcome"
        if lower_s is None:
            assert leg.chambers == (), f"turn {turn}: expected no chamber reports"
        else:
            lower = next(c for c in leg.chambers if c.chamber.value == "lower")
            upper = next(c for c in leg.chambers if c.chamber.value == "upper")
            assert lower.supporting_seats == lower_s, f"turn {turn}: lower supporting"
            assert lower.required_yes_seats == lower_r, f"turn {turn}: lower required"
            assert upper.supporting_seats == upper_s, f"turn {turn}: upper supporting"
            assert upper.required_yes_seats == upper_r, f"turn {turn}: upper required"
        state = resolution.state


def test_tiny_valid_case1_no_proposal_no_investment() -> None:
    """(§12.3 Case 1) Every turn is NO_PROPOSAL -- no chamber report, no vote, no capital spent."""
    _run_tiny_valid_case(_TABLE_CASE1_NO_PROPOSAL, invest=False)


def test_tiny_valid_case2_one_time_enacted_tax_rise() -> None:
    """(§12.3 Case 2) Turn 1 passes unaided; turns 2-8 submit nothing at all."""
    _run_tiny_valid_case(_TABLE_CASE2_ONE_TIME_RISE, invest=False)


def test_tiny_valid_case3_repeated_unchanged_legislative_budgets() -> None:
    """(§12.3 Case 3) Every turn resubmits the held 2,500bps target and passes unaided, unchanged
    across all 8 turns -- a zero-compatibility resubmission changes nothing about passage in a
    majority government this comfortable."""
    _run_tiny_valid_case(_TABLE_CASE3_REPEATED_UNCHANGED, invest=False)


def test_tiny_valid_case4_coalition_insurance_investment() -> None:
    """(§12.3 Case 4) 100/turn invested in rural_alliance/farmers; passage is never in doubt in
    either chamber -- this strategy buys margin, not survival."""
    _run_tiny_valid_case(_TABLE_CASE4_COALITION_INSURANCE, invest=True)


def test_tiny_valid_case5_finite_staircase_upper_chamber_gains_a_seat_from_policy_alone() -> None:
    """(§12.3 Case 5) An eight-step genuine staircase with zero investment still moves the upper
    chamber's apportionment by turn 5 -- proof that policy reaction alone, not just purchased
    influence, can move a chamber's composition."""
    _run_tiny_valid_case(_TABLE_CASE5_STAIRCASE, invest=False)


def test_tiny_valid_unchanged_resubmission_never_changes_chamber_composition() -> None:
    """(required finding: unchanged absolute targets produce zero policy reaction) Case 3 holds an
    already-enacted target every turn; both chambers' supporting-seat counts are byte-identical
    from turn 1 through turn 8, because a held target scores ChangeDirection.UNCHANGED and a
    provably zero policy reaction -- confirmed directly from the pinned table, not merely assumed
    from the formula."""
    first = _TABLE_CASE3_REPEATED_UNCHANGED[0][3:]
    for row in _TABLE_CASE3_REPEATED_UNCHANGED:
        assert row[3:] == first, f"turn {row[0]}: chamber composition must stay unchanged"
