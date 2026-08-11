"""Calibration tests for `tiny_valid.yaml`'s and `deficit_demo.yaml`'s authored legislatures
(Phase 3B1, T-P9-adjacent).

Every figure asserted below is **computed from the scenario files through the real
`legislative_voting`/`apportionment` modules**, not copied from a design document — if a scenario
author changes a bloc's seats, relationship or preference, this file recomputes the walkthrough
tally rather than silently going stale. That is the same discipline `test_scenario.py` already
applies to the economic figures; this file is its legislative counterpart.

The walkthrough proposal used throughout is the one the manual CLI walkthrough (plan §19) uses: a
+5 percentage-point rise in the personal income tax rate, spending unchanged.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.legislative_voting import (
    DECREE_POLITICAL_CAPITAL_COST,
    PolicyChange,
    chamber_carries,
    required_yes_seats,
    resolve_bloc_support,
    tax_policy_change,
)
from app.simulation.legislature import ChangeDirection, LegislativeChamber
from app.simulation.state import LegislatureState
from tests.conftest import SCENARIO_DIR

_NO_SPENDING_CHANGE = PolicyChange(direction=ChangeDirection.UNCHANGED, intensity_bps=0)


def _tax_rise_5pp(personal_income_rate_bps: int) -> PolicyChange:
    return tax_policy_change(
        rate_changes=((personal_income_rate_bps, personal_income_rate_bps + 500),)
    )


def _tally_chamber(
    *,
    legislature: LegislatureState,
    chamber: LegislativeChamber,
    tax_change: PolicyChange,
    allocations: dict[tuple[str, str], int],
) -> tuple[int, int]:
    """`(supporting_seats, total_seats)` for one chamber against one proposal, with optional
    per-bloc political-capital allocations. Every bloc actually seated in `chamber` is included,
    even at zero support, because apportionment needs the full chamber to compute the true total
    (see `apportionment`'s module docstring)."""
    total_seats = next(c.total_seats for c in legislature.chambers if c.chamber is chamber)
    rows = []
    for party in legislature.parties:
        for bloc in party.blocs:
            seats = next((s.seats for s in bloc.seats if s.chamber is chamber), 0)
            if not any(s.chamber is chamber for s in bloc.seats):
                continue
            support = resolve_bloc_support(
                role=party.government_role,
                relationship_bps=bloc.government_relationship_bps,
                tax_change=tax_change,
                tax_preference_bps=bloc.tax_preference_bps,
                spending_change=_NO_SPENDING_CHANGE,
                spending_preference_bps=bloc.spending_preference_bps,
                allocated_political_capital=allocations.get((party.id, bloc.id), 0),
                discipline_bps=bloc.discipline_bps,
            ).effective_support_bps
            rows.append(
                SeatSupport(
                    party_id=party.id, bloc_id=bloc.id, seats=seats, effective_support_bps=support
                )
            )
    result = apportion_supporting_seats(rows=tuple(rows))
    return result.supporting_seats, total_seats


def _cheapest_bargain(
    *,
    legislature: LegislatureState,
    chamber: LegislativeChamber,
    tax_change: PolicyChange,
    max_capital_per_bloc: int = 300,
) -> int | None:
    """The minimum total political capital, allocated one bloc at a time by exact bounded search
    over each bloc's own marginal-numerator curve, that reaches the chamber's required majority.
    `None` if no allocation within `max_capital_per_bloc` per bloc reaches it.

    Exact (not a heuristic): each bloc's contributed numerator is a nondecreasing function of its
    own allocation alone, so the chamber's summed numerator can be maximized independently per
    bloc for any total spend via a knapsack over per-bloc marginal-value steps.
    """
    total_seats = next(c.total_seats for c in legislature.chambers if c.chamber is chamber)
    required = required_yes_seats(total_seats=total_seats)
    need = required * 10_000

    per_bloc_options: list[list[tuple[int, int]]] = []
    for party in legislature.parties:
        for bloc in party.blocs:
            seats = next((s.seats for s in bloc.seats if s.chamber is chamber), 0)
            if not any(s.chamber is chamber for s in bloc.seats):
                continue
            options: list[tuple[int, int]] = []
            best = -1
            for capital in range(max_capital_per_bloc + 1):
                support = resolve_bloc_support(
                    role=party.government_role,
                    relationship_bps=bloc.government_relationship_bps,
                    tax_change=tax_change,
                    tax_preference_bps=bloc.tax_preference_bps,
                    spending_change=_NO_SPENDING_CHANGE,
                    spending_preference_bps=bloc.spending_preference_bps,
                    allocated_political_capital=capital,
                    discipline_bps=bloc.discipline_bps,
                ).effective_support_bps
                numerator = seats * support
                if numerator > best:
                    options.append((capital, numerator))
                    best = numerator
            per_bloc_options.append(options)

    budget = max_capital_per_bloc * len(per_bloc_options)
    unreachable = -1
    best_numerator_at_spend = [unreachable] * (budget + 1)
    best_numerator_at_spend[0] = 0
    for options in per_bloc_options:
        next_best = [unreachable] * (budget + 1)
        for spend, numerator in enumerate(best_numerator_at_spend):
            if numerator == unreachable:
                continue
            for extra_capital, added_numerator in options:
                new_spend = spend + extra_capital
                if new_spend > budget:
                    continue
                candidate = numerator + added_numerator
                if candidate > next_best[new_spend]:
                    next_best[new_spend] = candidate
        best_numerator_at_spend = next_best

    running_best = unreachable
    for spend, numerator in enumerate(best_numerator_at_spend):
        running_best = max(running_best, numerator)
        if running_best >= need:
            return spend
    return None


# --- tiny_valid: a majority coalition that does not need to bargain ----------


def test_tiny_valid_legislature_reconciles_every_chamber_seat() -> None:
    """Sanity precondition for everything below: every seat in every chamber is held by exactly
    one bloc, which `LegislatureState`'s own construction-time validator already enforces —
    re-asserted here directly so a future scenario edit that broke it would fail at the seat count,
    not several layers of arithmetic downstream."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    legislature = state.world.countries["arken"].politics.legislature
    assert legislature is not None
    for chamber_state in legislature.chambers:
        held = sum(
            entry.seats
            for party in legislature.parties
            for bloc in party.blocs
            for entry in bloc.seats
            if entry.chamber is chamber_state.chamber
        )
        assert held == chamber_state.total_seats


def test_tiny_valid_carries_the_walkthrough_budget_unaided_in_both_chambers() -> None:
    """The plan's §19 walkthrough claim, reproduced exactly through the shipped formulas: the
    governing coalition's own seats, with no political capital spent at all, are enough to pass a
    +5 pp personal-income rise in both the lower and upper chamber."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    country = state.world.countries["arken"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    lower_support, lower_total = _tally_chamber(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=tax_change,
        allocations={},
    )
    upper_support, upper_total = _tally_chamber(
        legislature=legislature,
        chamber=LegislativeChamber.UPPER,
        tax_change=tax_change,
        allocations={},
    )

    assert (lower_support, lower_total) == (58, 100)
    assert (upper_support, upper_total) == (33, 60)
    assert chamber_carries(supporting_seats=lower_support, total_seats=lower_total) is True
    assert chamber_carries(supporting_seats=upper_support, total_seats=upper_total) is True


def test_tiny_valid_opposition_blocs_never_supply_a_seat_to_this_proposal() -> None:
    """Both `national_front` blocs sit at 0 effective support against a tax rise they oppose from
    a hostile relationship — confirming the 58/33 tallies come entirely from the coalition and its
    confidence-and-supply partner, not from an accidental opposition contribution."""
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    country = state.world.countries["arken"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)
    opposition = next(p for p in legislature.parties if p.id == "national_front")
    for bloc in opposition.blocs:
        support = resolve_bloc_support(
            role=opposition.government_role,
            relationship_bps=bloc.government_relationship_bps,
            tax_change=tax_change,
            tax_preference_bps=bloc.tax_preference_bps,
            spending_change=_NO_SPENDING_CHANGE,
            spending_preference_bps=bloc.spending_preference_bps,
            allocated_political_capital=0,
            discipline_bps=bloc.discipline_bps,
        ).effective_support_bps
        assert support == 0


# --- deficit_demo: a minority government that must bargain -------------------


def test_deficit_demo_legislature_reconciles_every_chamber_seat() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    legislature = state.world.countries["strapped"].politics.legislature
    assert legislature is not None
    for chamber_state in legislature.chambers:
        held = sum(
            entry.seats
            for party in legislature.parties
            for bloc in party.blocs
            for entry in bloc.seats
            if entry.chamber is chamber_state.chamber
        )
        assert held == chamber_state.total_seats


def test_deficit_demo_fails_the_walkthrough_budget_unaided() -> None:
    """The scenario the phase exists to exercise: a minority government's own seats are not
    enough. Tallied at 47 of a required 51 — four short, not zero, so the shortfall is a real
    bargaining gap rather than an unreachable wall."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    country = state.world.countries["strapped"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    support, total = _tally_chamber(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=tax_change,
        allocations={},
    )
    required = required_yes_seats(total_seats=total)

    assert (support, total) == (47, 100)
    assert required == 51
    assert chamber_carries(supporting_seats=support, total_seats=total) is False


def test_deficit_demo_can_be_carried_by_a_bargain_cheaper_than_a_decree_would_cost() -> None:
    """The cheapest allocation that reaches 51/100 costs strictly less than
    `DECREE_POLITICAL_CAPITAL_COST`, and comfortably less than the government's own opening
    capital — so legislating is both affordable and the rational choice here, which matters
    because this government's `decree_authority` is `emergency_only` and it has no route to decree
    at all (plan §8.1). If this bargain were unaffordable, the scenario would describe a
    government that simply cannot govern, which is not what `deficit_demo` is for."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    country = state.world.countries["strapped"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    cheapest = _cheapest_bargain(
        legislature=legislature, chamber=LegislativeChamber.LOWER, tax_change=tax_change
    )

    assert cheapest is not None
    assert cheapest == 162
    assert cheapest < DECREE_POLITICAL_CAPITAL_COST
    assert cheapest < country.politics.political_capital


def test_deficit_demo_bargain_actually_carries_when_spent() -> None:
    """Closes the loop: the capital the search above reports is spent for real, and the chamber
    genuinely carries — not merely a number that satisfies the search's own internal accounting.

    The full search finds the entire 162 is best spent on a single bloc: `citizens_bloc/moderates`
    is the cheapest seat-per-capital target (mild hostility, low discipline, so its effective
    support climbs fastest per unit of influence), and no split with `independents/regional`
    beats spending on `moderates` alone.
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    country = state.world.countries["strapped"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    allocations = {("citizens_bloc", "moderates"): 162}

    support, total = _tally_chamber(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=tax_change,
        allocations=allocations,
    )
    assert support == 51
    assert chamber_carries(supporting_seats=support, total_seats=total) is True


def test_deficit_demo_governing_blocs_alone_are_the_bulk_of_the_forty_seven() -> None:
    """`governing_party`'s two blocs plus `independents` already reach 45 of the 47 unaided seats,
    confirming the coalition itself — not a fluke of apportionment's remainder rule — carries the
    government's own weight; the remaining 2 seats are `citizens_bloc/moderates`'s base-plus-bonus
    contribution from a nonzero-but-small effective support, which only appears once
    `citizens_bloc` is back in the tally to compete for (and win) the chamber's one remainder
    seat."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    country = state.world.countries["strapped"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    friendly = {p.id for p in legislature.parties if p.id != "citizens_bloc"}
    rows = []
    for party in legislature.parties:
        if party.id not in friendly:
            continue
        for bloc in party.blocs:
            seats = next((s.seats for s in bloc.seats if s.chamber is LegislativeChamber.LOWER), 0)
            support = resolve_bloc_support(
                role=party.government_role,
                relationship_bps=bloc.government_relationship_bps,
                tax_change=tax_change,
                tax_preference_bps=bloc.tax_preference_bps,
                spending_change=_NO_SPENDING_CHANGE,
                spending_preference_bps=bloc.spending_preference_bps,
                allocated_political_capital=0,
                discipline_bps=bloc.discipline_bps,
            ).effective_support_bps
            rows.append(
                SeatSupport(
                    party_id=party.id, bloc_id=bloc.id, seats=seats, effective_support_bps=support
                )
            )
    friendly_total = apportion_supporting_seats(rows=tuple(rows)).supporting_seats
    assert friendly_total == 45


# --- D4 (§7.10): tiny_valid/deficit_demo stay legislate-only, by design --------------------


def test_tiny_valid_and_deficit_demo_remain_legislate_only_by_design() -> None:
    """Both scenarios author `decree_authority: emergency_only` deliberately: they exist to
    exercise the vote engine on every turn, and a decree escape hatch would undercut that
    (see each file's own comments). `DECREE_POLITICAL_CAPITAL_COST`'s placement relative to a
    real, nondegenerate cheapest-legislative-bargain band was never validatable against these
    two — there is no decree here to compare it against — which is exactly why
    `test_decree_capital_calibration.py` proved it exhaustively against synthetic Regime C/D
    legislatures instead. `data/scenarios/decree_state.yaml` (plan §0.8) has since promoted
    Regime C into real, loadable content that DOES hold `unlimited` decree authority, closing
    the "no player can reach this" gap those regimes always had (own coverage in
    `test_decree_state_scenario.py`) — but that is a new, third scenario, not a change to
    either of these two, which remain legislate-only on purpose.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    assert state.world.countries["arken"].politics.constitution.decree_authority.value == (
        "emergency_only"
    )
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    assert state.world.countries["strapped"].politics.constitution.decree_authority.value == (
        "emergency_only"
    )
