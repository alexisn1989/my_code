"""D4 calibration follow-up: `DECREE_POLITICAL_CAPITAL_COST` against exhaustively-derived
legislative-bargain minimums (Phase 3B1, follow-up to the atomic state/version/content commit).

## Why this file exists

The atomic commit that landed `PoliticalState.legislature` also authored `tiny_valid.yaml`'s and
`deficit_demo.yaml`'s legislatures and derived their walkthrough tallies for real
(`test_scenario_legislature_calibration.py`). What it could **not** do is confirm D4
(`DECREE_POLITICAL_CAPITAL_COST = 250`, `legislative_voting.py`) against a real
non-degenerate crossover, because both committed scenarios author `decree_authority:
emergency_only` — neither can decree at all, so there is nothing in either file to compare 250
against.

This file closes that gap with a four-regime matrix, computed **exhaustively** (not sampled) from
the real formulas:

| Regime | Source | Question | Answer |
|---|---|---|---|
| **A** | `tiny_valid`'s actual legislature | cheapest commitment to pass | **0** |
| **B** | `deficit_demo`'s actual legislature | cheapest commitment to pass | **162** |
| **C** | synthetic, `decree_authority: unlimited` | cheapest commitment, reachable-but-deep shortfall | **283** |
| **D** | synthetic, `decree_authority: unlimited`, hostile supermajority | cheapest commitment | **unreachable at any price** — a 250 PC decree enacts instead |

**The required relationship holds:** `0 < 162 < 250 < 283`, and Regime D is legislatively
unreachable while its 250 PC decree is affordable. `DECREE_POLITICAL_CAPITAL_COST` is therefore
**retained at 250** — nothing here disconfirms it, so it is not changed.

**What this file does NOT prove — and what now closes that gap.** Regimes C and D are synthetic
legislatures built directly from the state models, not new scenario content — real per the state
models' own validators (exact seat reconciliation, `PoliticalState`'s both-directions rule, all of
`constitution.py`'s C1-C10), but never loaded from a committed scenario a player could actually
start a game with. `data/scenarios/decree_state.yaml` (plan §0.8) closes that: it promotes Regime
C's exact bloc parameters (below) into a real, loadable monarchy with `decree_authority: unlimited`
**and** a real unicameral legislature — a genuine legislative-versus-decree *choice*, not a
decree-only dead end (a legislature-less government has no legislative route to choose between).
`tiny_valid`/`deficit_demo` remain `emergency_only` by design (see
`test_the_two_legislate_only_scenarios_still_cannot_decree` below); `decree_state.yaml` is the
scenario that offers the player the choice, with its own integration coverage in
`test_decree_state_scenario.py`.

## The exhaustive algorithm, and why it is exact

Every "cheapest bargain" figure below comes from `_exhaustive_cheapest_bargain`, a dynamic
program over each bloc's own **exhaustively enumerated** marginal-numerator curve
(`_marginal_curve`). It is provably optimal, not a heuristic search, for two reasons:

1. **Additive separability.** A chamber's apportionment numerator is
   `sum(seats_i * effective_support_i)` (`apportionment.py`), and bloc `i`'s own numerator is a
   function of bloc `i`'s own allocated capital *alone* — no cross-bloc interaction exists
   anywhere in `legislative_voting.resolve_bloc_support`. Minimizing total spend to reach a target
   sum, where each term depends on a disjoint variable, is an exact bounded-knapsack problem.
2. **Domain completeness.** Each bloc's curve is enumerated over every integer capital from 0 to
   `MAX_INFLUENCE_BPS // INFLUENCE_BPS_PER_CAPITAL` (300) — the point beyond which
   `legislative_voting.influence_bps`'s hard cap makes additional capital provably unable to buy
   any more effective support. Spending beyond 300 on one bloc is therefore always weakly
   dominated by capping at 300 (identical numerator, strictly higher cost), so restricting the
   per-bloc search domain to `[0, 300]` loses no reachable minimum — the search bound is complete
   for *any* amount of capital, not merely for what a government happens to hold.

The DP tracks, for every *exact* total spend `s` (not "at most `s`"), the best achievable summed
numerator using one capital choice per bloc. The reported minimum is the smallest `s` at which
`dp[s]` **itself** reaches the required numerator — read directly off the DP table, not inferred
from a running maximum, so the reported minimum is always a genuinely reachable allocation with an
exact backtrace.
"""

from __future__ import annotations

from app.content.scenarios import load_scenario_file
from app.simulation.apportionment import SeatSupport, apportion_supporting_seats
from app.simulation.constitution import (
    AmendmentDifficulty,
    ConstitutionState,
    DecreeAuthority,
    ExecutiveSelection,
    ExecutiveSystem,
    JudicialReview,
    Legislature,
    TerritorialOrganization,
)
from app.simulation.legislative_voting import (
    DECREE_POLITICAL_CAPITAL_COST,
    INFLUENCE_BPS_PER_CAPITAL,
    MAX_INFLUENCE_BPS,
    PolicyChange,
    chamber_carries,
    required_yes_seats,
    resolve_bloc_support,
    tax_policy_change,
)
from app.simulation.legislature import ChangeDirection, GovernmentRole, LegislativeChamber
from app.simulation.legitimacy import resolve_political_capital
from app.simulation.state import (
    BlocSeats,
    ChamberState,
    LegislativeBlocState,
    LegislatureState,
    PartyState,
    PoliticalState,
)
from tests.conftest import SCENARIO_DIR

_NO_SPENDING_CHANGE = PolicyChange(direction=ChangeDirection.UNCHANGED, intensity_bps=0)

_MAX_USEFUL_CAPITAL_PER_BLOC = MAX_INFLUENCE_BPS // INFLUENCE_BPS_PER_CAPITAL
"""300. Proven complete in the module docstring: capital beyond this point cannot buy any more
effective support from any single bloc, so it bounds the search without losing any reachable
minimum."""


def _tax_rise_5pp(personal_income_rate_bps: int) -> PolicyChange:
    """The walkthrough proposal used throughout: +5 percentage points on the personal income
    rate, spending unchanged — matching `test_scenario_legislature_calibration.py`."""
    return tax_policy_change(
        rate_changes=((personal_income_rate_bps, personal_income_rate_bps + 500),)
    )


def _effective_support(
    bloc: LegislativeBlocState, role: GovernmentRole, tax_change: PolicyChange, capital: int
) -> int:
    return resolve_bloc_support(
        role=role,
        relationship_bps=bloc.government_relationship_bps,
        tax_change=tax_change,
        tax_preference_bps=bloc.tax_preference_bps,
        spending_change=_NO_SPENDING_CHANGE,
        spending_preference_bps=bloc.spending_preference_bps,
        allocated_political_capital=capital,
        discipline_bps=bloc.discipline_bps,
    ).effective_support_bps


def _marginal_curve(
    *,
    bloc: LegislativeBlocState,
    role: GovernmentRole,
    tax_change: PolicyChange,
    seats: int,
    cap: int = _MAX_USEFUL_CAPITAL_PER_BLOC,
) -> list[tuple[int, int]]:
    """This bloc's `(capital, numerator)` staircase over `[0, cap]`, keeping only the points where
    the numerator strictly improves — an exhaustive enumeration of the bloc's own contribution,
    not a sample of it."""
    best = -1
    curve: list[tuple[int, int]] = []
    for capital in range(cap + 1):
        numerator = seats * _effective_support(bloc, role, tax_change, capital)
        if numerator > best:
            curve.append((capital, numerator))
            best = numerator
    return curve


def _blocs_in_chamber(
    legislature: LegislatureState, chamber: LegislativeChamber
) -> list[tuple[str, str, GovernmentRole, LegislativeBlocState, int]]:
    """`(party_id, bloc_id, role, bloc, seats)` for every bloc actually seated in `chamber`."""
    rows = []
    for party in legislature.parties:
        for bloc in party.blocs:
            if not any(entry.chamber is chamber for entry in bloc.seats):
                continue
            seats = next(entry.seats for entry in bloc.seats if entry.chamber is chamber)
            rows.append((party.id, bloc.id, party.government_role, bloc, seats))
    return rows


def _exhaustive_cheapest_bargain(
    *,
    legislature: LegislatureState,
    chamber: LegislativeChamber,
    tax_change: PolicyChange,
    total_seats: int,
    cap: int = _MAX_USEFUL_CAPITAL_PER_BLOC,
) -> tuple[int | None, dict[tuple[str, str], int], int, int]:
    """Returns `(minimum_spend, allocation, supporting_seats_at_minimum, required_yes_seats)`.

    `allocation` is `{(party_id, bloc_id): capital}`, read off the DP's own backtrace — never
    hand-constructed. `minimum_spend is None` (with an empty `allocation`) means no allocation
    within the exhaustively-complete search space reaches the majority; see the module docstring
    for why that domain is complete, not merely large.
    """
    required = required_yes_seats(total_seats=total_seats)
    need = required * 10_000

    entries = [
        (
            party_id,
            bloc_id,
            _marginal_curve(bloc=bloc, role=role, tax_change=tax_change, seats=seats, cap=cap),
        )
        for party_id, bloc_id, role, bloc, seats in _blocs_in_chamber(legislature, chamber)
    ]

    budget = cap * len(entries)
    unreachable = -1
    dp = [unreachable] * (budget + 1)
    dp[0] = 0
    parents: list[list[tuple[int, int] | None]] = []
    for _party_id, _bloc_id, curve in entries:
        choice: list[tuple[int, int] | None] = [None] * (budget + 1)
        next_dp = [unreachable] * (budget + 1)
        for spend, numerator in enumerate(dp):
            if numerator == unreachable:
                continue
            for capital, added in curve:
                new_spend = spend + capital
                if new_spend > budget:
                    continue
                candidate = numerator + added
                if candidate > next_dp[new_spend]:
                    next_dp[new_spend] = candidate
                    choice[new_spend] = (spend, capital)
        parents.append(choice)
        dp = next_dp

    minimum_spend = None
    for spend, numerator in enumerate(dp):
        if numerator != unreachable and numerator >= need:
            minimum_spend = spend
            break

    if minimum_spend is None:
        return None, {}, 0, required

    allocation: dict[tuple[str, str], int] = {}
    spend = minimum_spend
    for i in range(len(entries) - 1, -1, -1):
        party_id, bloc_id, _curve = entries[i]
        prev_spend, capital = parents[i][spend]  # type: ignore[misc]
        allocation[(party_id, bloc_id)] = capital
        spend = prev_spend
    assert spend == 0

    supporting_seats = _tally_with_allocation(
        legislature=legislature, chamber=chamber, tax_change=tax_change, allocation=allocation
    )
    return minimum_spend, allocation, supporting_seats, required


def _nonzero(allocation: dict[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    """The backtrace records every bloc's chosen capital, including the many that are optimally
    left at 0 — this strips those so an assertion reads as 'these are the target blocs', which is
    the claim that actually matters."""
    return {key: capital for key, capital in allocation.items() if capital > 0}


def _tally_with_allocation(
    *,
    legislature: LegislatureState,
    chamber: LegislativeChamber,
    tax_change: PolicyChange,
    allocation: dict[tuple[str, str], int],
) -> int:
    rows = tuple(
        SeatSupport(
            party_id=party_id,
            bloc_id=bloc_id,
            seats=seats,
            effective_support_bps=_effective_support(
                bloc, role, tax_change, allocation.get((party_id, bloc_id), 0)
            ),
        )
        for party_id, bloc_id, role, bloc, seats in _blocs_in_chamber(legislature, chamber)
    )
    return apportion_supporting_seats(rows=rows).supporting_seats


def _synthetic_political_state(
    *, chambers: tuple[ChamberState, ...], parties: tuple[PartyState, ...], political_capital: int
) -> PoliticalState:
    """A real, valid `PoliticalState` for a synthetic regime: `decree_authority: unlimited`, a
    genuine unicameral legislature (never `Legislature.NONE`), satisfying every constitutional and
    state-model validator — including `LegislatureState`'s exact seat reconciliation and
    `PoliticalState`'s both-directions presence rule."""
    return PoliticalState(
        constitution=ConstitutionState(
            executive_system=ExecutiveSystem.PRESIDENTIAL,
            executive_selection=ExecutiveSelection.DIRECT_ELECTION,
            legislature=Legislature.UNICAMERAL,
            territorial_organization=TerritorialOrganization.UNITARY,
            judicial_review=JudicialReview.WEAK,
            amendment_difficulty=AmendmentDifficulty.SUPERMAJORITY,
            decree_authority=DecreeAuthority.UNLIMITED,
        ),
        constitutional_order_support_bps=7_000,
        legitimacy_bps=6_000,
        political_capital=political_capital,
        political_capital_capacity=1_000,
        legislature=LegislatureState(chambers=chambers, parties=parties),
    )


def _two_bloc_legislature(*, governing_seats: int, opposition_seats: int) -> LegislatureState:
    """A minimal, exactly-reconciled unicameral legislature: one coalition bloc, one opposition
    bloc, parameters matching the plan's own disclosed §7.9 compatibility figures exactly (a
    government bloc at relationship +6,000/preference +2,000 nets +200 compatibility on the
    walkthrough proposal; an opposition bloc at -8,000/-6,000 nets -600 — both reproduced and
    pinned by `test_the_disclosed_compatibility_figures_reproduce_exactly` below)."""
    return LegislatureState(
        chambers=(ChamberState(chamber=LegislativeChamber.LOWER, total_seats=100),),
        parties=(
            PartyState(
                id="governing_party",
                name="Governing Party",
                government_role=GovernmentRole.COALITION,
                blocs=(
                    LegislativeBlocState(
                        id="core",
                        name="Governing Party Core",
                        seats=(BlocSeats(chamber=LegislativeChamber.LOWER, seats=governing_seats),),
                        discipline_bps=5_000,
                        government_relationship_bps=6_000,
                        baseline_government_relationship_bps=6_000,
                        tax_preference_bps=2_000,
                        spending_preference_bps=0,
                    ),
                ),
            ),
            PartyState(
                id="opposition_party",
                name="Opposition Party",
                government_role=GovernmentRole.OPPOSITION,
                blocs=(
                    LegislativeBlocState(
                        id="main",
                        name="Opposition Party Main",
                        seats=(
                            BlocSeats(chamber=LegislativeChamber.LOWER, seats=opposition_seats),
                        ),
                        discipline_bps=8_000,
                        government_relationship_bps=-8_000,
                        baseline_government_relationship_bps=-8_000,
                        tax_preference_bps=-6_000,
                        spending_preference_bps=0,
                    ),
                ),
            ),
        ),
    )


_WALKTHROUGH_TAX_CHANGE = _tax_rise_5pp(2_000)


def test_the_disclosed_compatibility_figures_reproduce_exactly() -> None:
    """Sanity precondition for Regimes C and D: the plan's §7.9 worked example discloses exactly
    two compatibility figures for its illustrative government/opposition blocs — government +200,
    opposition -600. Reproduced here from the exact preference values `_two_bloc_legislature` uses
    (+2,000 government / -6,000 opposition) and the real formula chain, independent of any
    legislature construction, before anything downstream is trusted."""
    from app.simulation.legislative_voting import policy_compatibility_bps

    gov_compat = policy_compatibility_bps(
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        tax_preference_bps=2_000,
        spending_change=_NO_SPENDING_CHANGE,
        spending_preference_bps=0,
    )
    opp_compat = policy_compatibility_bps(
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        tax_preference_bps=-6_000,
        spending_change=_NO_SPENDING_CHANGE,
        spending_preference_bps=0,
    )
    assert gov_compat == 200
    assert opp_compat == -600


# --- Regime A: tiny_valid — cheapest commitment is 0 --------------------------


def test_regime_a_tiny_valid_cheapest_commitment_is_zero_in_both_chambers() -> None:
    """Search bounds: the full exhaustive DP over both chambers' actual blocs (same algorithm as
    B/C/D, applied uniformly). Target blocs: none — the minimum is found at spend 0 before any
    bloc is examined at all, because `dp[0] = 0` already needs no bloc contribution: both
    chambers' unaided 0-capital tallies (58/100, 33/60) already meet their required majorities
    (51, 31), so the DP's own threshold search terminates at spend 0.
    """
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    country = state.world.countries["arken"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    for chamber, total_seats in ((LegislativeChamber.LOWER, 100), (LegislativeChamber.UPPER, 60)):
        minimum, allocation, supporting_seats, required = _exhaustive_cheapest_bargain(
            legislature=legislature, chamber=chamber, tax_change=tax_change, total_seats=total_seats
        )
        assert minimum == 0
        assert _nonzero(allocation) == {}
        assert chamber_carries(supporting_seats=supporting_seats, total_seats=total_seats) is True
        assert required in (51, 31)


# --- Regime B: deficit_demo — cheapest commitment is exactly 162 --------------


def test_regime_b_deficit_demo_cheapest_commitment_is_exactly_162() -> None:
    """Search bounds: 5 blocs (`citizens_bloc/hardliners`, `citizens_bloc/moderates`,
    `governing_party/core`, `governing_party/left`, `independents/regional`), each over capital
    `[0, 300]` — a budget of 1,500 exact-spend DP states. Target bloc: the DP's own backtrace
    spends the entire minimum on a single bloc. Exact minimum: 162. Resulting supporting seats:
    51. Required majority: 51 (of 100).
    """
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    country = state.world.countries["strapped"]
    legislature = country.politics.legislature
    assert legislature is not None
    tax_change = _tax_rise_5pp(country.finance.tax_policy.personal_income_rate_bps)

    minimum, allocation, supporting_seats, required = _exhaustive_cheapest_bargain(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=tax_change,
        total_seats=100,
    )

    assert required == 51
    assert minimum == 162
    assert _nonzero(allocation) == {("citizens_bloc", "moderates"): 162}
    assert supporting_seats == 51
    assert chamber_carries(supporting_seats=supporting_seats, total_seats=100) is True

    # The zero-capital unaided tally this bargain improves on, re-derived rather than assumed.
    unaided, _empty, _unaided_seats, _required = _exhaustive_cheapest_bargain(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=tax_change,
        total_seats=100,
        cap=0,
    )
    assert unaided is None  # 0-capital-only search cannot reach 51; confirms the shortfall is real


def test_regime_b_minimum_is_strictly_below_the_decree_cost() -> None:
    """The concrete, real-content half of the required relationship: `0 < 162 < 250`."""
    assert 0 < 162 < DECREE_POLITICAL_CAPITAL_COST


# --- Regime C: synthetic, reachable deep shortfall, minimum > 250 -------------


def test_regime_c_reachable_deep_shortfall_minimum_is_exactly_283() -> None:
    """A 45/55 seated unicameral legislature — the governing bloc alone falls 6 seats short of
    the 51 required, and the opposition bloc (relationship -8,000, discipline 8,000) is the same
    disclosed archetype as the plan's own worked example.

    Search bounds: 2 blocs, capital `[0, 300]` each — a budget of 600 exact-spend DP states,
    small enough that this figure was independently cross-checked against a full joint 2-D
    brute force over the entire 301x301 grid (301 * 301 = 90,601 combinations) during
    development; both agree exactly. Target bloc: the DP spends everything on the opposition
    bloc — the governing bloc is already at maximum effective support (10,000 bps) with zero
    capital, so spending on it can never help. Exact minimum: 283. Resulting supporting seats:
    51 (exactly the required majority, not more). Required majority: 51 (of 100).
    """
    legislature = _two_bloc_legislature(governing_seats=45, opposition_seats=55)
    political_state = _synthetic_political_state(
        chambers=legislature.chambers, parties=legislature.parties, political_capital=500
    )
    assert political_state.constitution.decree_authority is DecreeAuthority.UNLIMITED
    assert political_state.constitution.legislature is Legislature.UNICAMERAL

    minimum, allocation, supporting_seats, required = _exhaustive_cheapest_bargain(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        total_seats=100,
    )

    assert required == 51
    assert minimum == 283
    assert _nonzero(allocation) == {("opposition_party", "main"): 283}
    assert supporting_seats == 51
    assert chamber_carries(supporting_seats=supporting_seats, total_seats=100) is True

    # One unit less genuinely fails — the reported minimum is tight, not merely sufficient.
    just_short = _tally_with_allocation(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        allocation={("opposition_party", "main"): 282},
    )
    assert chamber_carries(supporting_seats=just_short, total_seats=100) is False


def test_regime_c_minimum_exceeds_the_decree_cost() -> None:
    """The other real half of the required relationship: `250 < 283`. For this regime, legislating
    is the MORE expensive nominal route — a rational government here would decree instead, at a
    strictly lower committed cost."""
    assert DECREE_POLITICAL_CAPITAL_COST < 283


# --- Regime D: synthetic, hostile supermajority, legislatively unreachable ---


def test_regime_d_hostile_supermajority_is_legislatively_unreachable_at_any_price() -> None:
    """A 30/70 seated unicameral legislature — the same bloc archetypes as Regime C, at a seat
    split hostile enough that even fully saturating the opposition bloc's bought support
    (effective support capped at 1,400 bps under `MAX_INFLUENCE_BPS`, the exact figure the plan's
    own §7.10 discloses for its regime 4) cannot reach the 51-seat majority.

    Search bounds: the same 2-bloc, `[0, 300]`-each domain as Regime C — proven complete in the
    module docstring, so 'unreachable within this domain' means unreachable at *any* capital, not
    merely within an arbitrary cutoff. The DP's threshold search never finds a `dp[s]` reaching
    the required numerator anywhere in its full budget of 600 exact-spend states.
    """
    legislature = _two_bloc_legislature(governing_seats=30, opposition_seats=70)

    minimum, allocation, _supporting_seats, required = _exhaustive_cheapest_bargain(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        total_seats=100,
    )

    assert required == 51
    assert minimum is None
    assert allocation == {}

    # Direct confirmation of the capped-support figure the docstring cites, independent of the
    # search above.
    opposition_bloc = legislature.parties[1].blocs[0]
    saturated_support = _effective_support(
        opposition_bloc,
        GovernmentRole.OPPOSITION,
        _WALKTHROUGH_TAX_CHANGE,
        _MAX_USEFUL_CAPITAL_PER_BLOC,
    )
    assert saturated_support == 1_400

    # Even fully saturating BOTH blocs' capital never carries the chamber.
    fully_saturated_tally = _tally_with_allocation(
        legislature=legislature,
        chamber=LegislativeChamber.LOWER,
        tax_change=_WALKTHROUGH_TAX_CHANGE,
        allocation={
            ("governing_party", "core"): _MAX_USEFUL_CAPITAL_PER_BLOC,
            ("opposition_party", "main"): _MAX_USEFUL_CAPITAL_PER_BLOC,
        },
    )
    assert chamber_carries(supporting_seats=fully_saturated_tally, total_seats=100) is False


def test_regime_d_decree_at_250_is_affordable_where_legislation_is_not() -> None:
    """The other half of Regime D's claim: a government here is not simply stuck. With
    `decree_authority: unlimited` (asserted on the constructed state) and opening capital of 500,
    committing `DECREE_POLITICAL_CAPITAL_COST` (250) satisfies the R2 capital guard
    (`spent <= opening`) that `legitimacy.resolve_political_capital` and `PoliticalReport` both
    enforce — the same guard tightened in the R2 commit earlier in this phase. Phase wiring
    (plan §17 step 13) has not landed yet, so this is the guard-level affordability proof
    available today, not a full resolved-turn proof; that arrives once slot 1 routing exists.
    """
    legislature = _two_bloc_legislature(governing_seats=30, opposition_seats=70)
    political_state = _synthetic_political_state(
        chambers=legislature.chambers, parties=legislature.parties, political_capital=500
    )
    assert political_state.constitution.decree_authority is DecreeAuthority.UNLIMITED
    assert DECREE_POLITICAL_CAPITAL_COST == 250

    regeneration, closing = resolve_political_capital(
        opening=political_state.political_capital,
        capacity=political_state.political_capital_capacity,
        legitimacy_bps=political_state.legitimacy_bps,
        spent=DECREE_POLITICAL_CAPITAL_COST,
    )
    assert closing >= 0
    assert political_state.political_capital >= DECREE_POLITICAL_CAPITAL_COST


# --- The required relationship, asserted as one statement --------------------


def test_the_required_crossover_relationship_holds() -> None:
    """`0 < 162 < 250 < 283`, with the hostile regime unreachable and its decree affordable — the
    single statement this whole file exists to establish. `DECREE_POLITICAL_CAPITAL_COST` is
    retained at 250: nothing measured here disconfirms it, so nothing about it is changed."""
    regime_a = 0
    regime_b = 162
    regime_c = 283
    assert regime_a < regime_b < DECREE_POLITICAL_CAPITAL_COST < regime_c


# --- The two legislate-only scenarios, restated so their scope stays honest -------------------


def test_the_two_legislate_only_scenarios_still_cannot_decree() -> None:
    """`tiny_valid` and `deficit_demo` remain `decree_authority: emergency_only` BY DESIGN
    (plan §13): they exist to exercise the vote engine on every turn, and giving either of them
    a decree escape hatch would undercut that. Regimes C and D above prove the engine's
    legislative-versus-decree balance is sound in the abstract; these two scenarios simply never
    exercise the decree half of it, on purpose. The gap that leaves — no *player* could reach the
    decree route at all — is now closed by `data/scenarios/decree_state.yaml` (plan §0.8), whose
    integration coverage lives in `test_decree_state_scenario.py`, not here: this file keeps the
    exhaustive DP proof; that one proves the promoted Regime C numbers hold through the real
    resolver."""
    for scenario_file, country_id in (
        ("tiny_valid.yaml", "arken"),
        ("deficit_demo.yaml", "strapped"),
    ):
        state = load_scenario_file(SCENARIO_DIR / scenario_file)
        decree_authority = state.world.countries[country_id].politics.constitution.decree_authority
        assert decree_authority is DecreeAuthority.EMERGENCY_ONLY
