"""Phase 3B1 phase-wiring integration tests: the legislative vote (slot 1), the conditional
budget gate (slot 2), political-capital commitment (slot 10), and atomic rejection of invalid
decisions -- all exercised through the real `resolve_turn`, never by hand-building a report.

Two committed scenarios do most of the heavy lifting (calibration independently re-derived and
pinned in `test_scenario_legislature_calibration.py`):

- `tiny_valid.yaml`: a bicameral majority coalition that carries the walkthrough proposal
  (+5pp personal income tax) unaided in both chambers (58/100, 33/60).
- `deficit_demo.yaml`: a unicameral minority government that fails the same proposal unaided
  (47/100, required 51), and can carry it for 162 PC or more (cheapest bargain), with an opening
  political capital of exactly 300.

A handful of tests need a legislature this phase's two scenarios cannot express (an exact 50/50
tie, an unlimited-decree government, a bicameral split where only one chamber passes) -- those are
built directly via `tests.conftest`'s `make_politics`/`make_game_state` helpers, using saturating
role/relationship combinations (`relationship_bps=+/-10_000`, `tax_preference_bps=0`,
`discipline_bps=0`) so `effective_support_bps` is deterministically exactly 10,000 or exactly 0
regardless of the proposal's content -- no need to hand-compute the support formula for each test.
"""

from __future__ import annotations

import pytest

from app.content.scenarios import load_scenario_file
from app.core.canonical_json import canonical_dumps
from app.core.errors import TurnResolutionError
from app.simulation.constitution import DecreeAuthority, Legislature
from app.simulation.decisions import BudgetDecision, DecisionSet, InfluenceAllocation
from app.simulation.legislature import (
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)
from app.simulation.resolver import resolve_turn
from app.simulation.state import (
    BlocSeats,
    ChamberState,
    LegislativeBlocState,
    LegislatureState,
    PartyState,
)
from tests.conftest import SCENARIO_DIR, make_country, make_game_state, make_politics


def _bloc(
    *, bloc_id: str, name: str, relationship_bps: int, chambers: dict[LegislativeChamber, int]
) -> LegislativeBlocState:
    """A bloc whose `effective_support_bps` is deterministically 10,000 (`relationship_bps=
    +10_000`) or 0 (`relationship_bps=-10_000`), regardless of a proposal's content: role anchor
    plus a saturating relationship already clamps `baseline_support_bps` to the extreme,
    `tax_preference_bps=0`/`spending_preference_bps=0` keep `policy_compatibility_bps` at exactly
    0, and `discipline_bps=0` leaves `effective_support_bps == final_support_bps` untouched."""
    return LegislativeBlocState(
        id=bloc_id,
        name=name,
        seats=tuple(BlocSeats(chamber=c, seats=s) for c, s in chambers.items()),
        discipline_bps=0,
        government_relationship_bps=relationship_bps,
        tax_preference_bps=0,
        spending_preference_bps=0,
    )


def _tied_unicameral_legislature() -> LegislatureState:
    """100 lower seats, split exactly 50 saturating-supportive / 50 saturating-hostile: an exact
    50/100 tie against a required majority of 51 -- fails, and no tie-breaker is consulted."""
    return LegislatureState(
        chambers=(ChamberState(chamber=LegislativeChamber.LOWER, total_seats=100),),
        parties=(
            PartyState(
                id="gov",
                name="Government",
                government_role=GovernmentRole.COALITION,
                blocs=(
                    _bloc(
                        bloc_id="core",
                        name="Core",
                        relationship_bps=10_000,
                        chambers={LegislativeChamber.LOWER: 50},
                    ),
                ),
            ),
            PartyState(
                id="opp",
                name="Opposition",
                government_role=GovernmentRole.OPPOSITION,
                blocs=(
                    _bloc(
                        bloc_id="main",
                        name="Main",
                        relationship_bps=-10_000,
                        chambers={LegislativeChamber.LOWER: 50},
                    ),
                ),
            ),
        ),
    )


def _bicameral_split_legislature() -> LegislatureState:
    """Lower: 60 supportive / 40 hostile (passes, required 51). Upper: 20 supportive / 40 hostile
    (fails, required 31). The same two blocs sit in both chambers, at different seat counts, so
    this also exercises the bicameral non-duplication of political-capital commitment."""
    return LegislatureState(
        chambers=(
            ChamberState(chamber=LegislativeChamber.LOWER, total_seats=100),
            ChamberState(chamber=LegislativeChamber.UPPER, total_seats=60),
        ),
        parties=(
            PartyState(
                id="gov",
                name="Government",
                government_role=GovernmentRole.COALITION,
                blocs=(
                    _bloc(
                        bloc_id="core",
                        name="Core",
                        relationship_bps=10_000,
                        chambers={LegislativeChamber.LOWER: 60, LegislativeChamber.UPPER: 20},
                    ),
                ),
            ),
            PartyState(
                id="opp",
                name="Opposition",
                government_role=GovernmentRole.OPPOSITION,
                blocs=(
                    _bloc(
                        bloc_id="main",
                        name="Main",
                        relationship_bps=-10_000,
                        chambers={LegislativeChamber.LOWER: 40, LegislativeChamber.UPPER: 40},
                    ),
                ),
            ),
        ),
    )


def _zero_seat_bloc_legislature() -> LegislatureState:
    """One bloc holds every seat; a second bloc in the same party holds none anywhere -- legal
    per `LegislatureState` (seats are per-bloc-omittable), and exactly the shape T-required
    "zero-seat bloc rejection" needs a target for."""
    return LegislatureState(
        chambers=(ChamberState(chamber=LegislativeChamber.LOWER, total_seats=100),),
        parties=(
            PartyState(
                id="gov",
                name="Government",
                government_role=GovernmentRole.COALITION,
                blocs=(
                    _bloc(
                        bloc_id="core",
                        name="Core",
                        relationship_bps=10_000,
                        chambers={LegislativeChamber.LOWER: 100},
                    ),
                    LegislativeBlocState(
                        id="ghost",
                        name="Ghost",
                        seats=(),
                        discipline_bps=0,
                        government_relationship_bps=0,
                        tax_preference_bps=0,
                        spending_preference_bps=0,
                    ),
                ),
            ),
        ),
    )


def _decisions_for(state, decision: BudgetDecision | None) -> DecisionSet:
    return DecisionSet(
        expected_turn=state.turn,
        expected_state_version=state.state_version,
        decisions=(decision,) if decision is not None else (),
    )


def _empty_decisions(state) -> DecisionSet:
    return _decisions_for(state, None)


# --- NO_PROPOSAL -------------------------------------------------------------


def test_no_proposal_carries_route_none_and_zero_commitment() -> None:
    state = make_game_state(turn=0, state_version=0)
    resolution = resolve_turn(state, _empty_decisions(state))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.NO_PROPOSAL
    assert legislative.route is None
    assert legislative.political_capital_committed == 0
    assert legislative.chambers == ()
    assert legislative.blocs == ()


def test_no_proposal_leaves_budget_and_economic_state_unchanged() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    resolution = resolve_turn(state, _empty_decisions(state))
    player = resolution.state.world.countries[resolution.state.world.player_country_id]
    original_player = state.world.countries[state.world.player_country_id]
    assert player.finance is not None and original_player.finance is not None
    assert player.finance.tax_policy == original_player.finance.tax_policy
    assert player.finance.spending_plan == original_player.finance.spending_plan
    assert resolution.report.finance is not None
    assert resolution.report.finance.budget_changes == ()


# --- legislative passage / failure -------------------------------------------


def test_majority_legislative_passage() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert legislative.route is ProposalRoute.LEGISLATIVE
    assert {c.chamber for c in legislative.chambers} == {
        LegislativeChamber.LOWER,
        LegislativeChamber.UPPER,
    }
    lower = next(c for c in legislative.chambers if c.chamber is LegislativeChamber.LOWER)
    upper = next(c for c in legislative.chambers if c.chamber is LegislativeChamber.UPPER)
    assert (lower.supporting_seats, lower.total_seats, lower.passed) == (58, 100, True)
    assert (upper.supporting_seats, upper.total_seats, upper.passed) == (33, 60, True)


def test_minority_legislative_failure() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    lower = legislative.chambers[0]
    assert (lower.supporting_seats, lower.total_seats, lower.required_yes_seats) == (47, 100, 51)
    assert lower.passed is False
    assert lower.shortfall_seats == 4


def test_political_capital_assisted_passage() -> None:
    """162 PC on `citizens_bloc/moderates` is the cheapest bargain that flips `deficit_demo`'s
    47/100 into a passing 51/100 (see `test_scenario_legislature_calibration.py`)."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=162
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert legislative.political_capital_committed == 162
    lower = legislative.chambers[0]
    assert (lower.supporting_seats, lower.total_seats) == (51, 100)


def test_strict_50_100_tie_fails() -> None:
    politics = make_politics(
        legislature=Legislature.UNICAMERAL, legislature_state=_tied_unicameral_legislature()
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decision = BudgetDecision(personal_income_rate_bps=2_500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    lower = legislative.chambers[0]
    assert (lower.supporting_seats, lower.required_yes_seats, lower.passed) == (50, 51, False)


# --- bicameral -----------------------------------------------------------------


def test_bicameral_lower_pass_upper_fail_yields_failed_outcome() -> None:
    politics = make_politics(
        legislature=Legislature.BICAMERAL, legislature_state=_bicameral_split_legislature()
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decision = BudgetDecision(personal_income_rate_bps=2_500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    lower = next(c for c in legislative.chambers if c.chamber is LegislativeChamber.LOWER)
    upper = next(c for c in legislative.chambers if c.chamber is LegislativeChamber.UPPER)
    assert lower.passed is True
    assert upper.passed is False


def test_bicameral_passage_only_when_both_chambers_pass() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert all(chamber.passed for chamber in legislative.chambers)
    assert legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE


def test_bicameral_influence_is_counted_exactly_once() -> None:
    """Report corrections §3: a bloc seated in two chambers that receives 100 PC commits 100, not
    200 -- `political_capital_committed` must never sum every chamber row directly."""
    politics = make_politics(
        legislature=Legislature.BICAMERAL,
        legislature_state=_bicameral_split_legislature(),
        political_capital=500,
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decision = BudgetDecision(
        personal_income_rate_bps=2_500,
        influence=(InfluenceAllocation(party_id="gov", bloc_id="core", political_capital=100),),
    )
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.political_capital_committed == 100
    core_rows = [b for b in legislative.blocs if (b.party_id, b.bloc_id) == ("gov", "core")]
    assert len(core_rows) == 2
    assert {row.political_capital_allocated for row in core_rows} == {100}


# --- decree --------------------------------------------------------------------


def test_valid_unlimited_decree_enacts_and_commits_the_fixed_cost() -> None:
    politics = make_politics(
        legislature=Legislature.NONE,
        decree_authority=DecreeAuthority.UNLIMITED,
        political_capital=500,
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    assert legislative is not None
    assert legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE
    assert legislative.route is ProposalRoute.DECREE
    assert legislative.political_capital_committed == 250
    assert legislative.chambers == ()
    assert legislative.blocs == ()
    player = resolution.state.world.countries["testland"]
    assert player.finance is not None
    assert player.finance.tax_policy.personal_income_rate_bps == 2_500


# --- atomic rejection ------------------------------------------------------------


def test_unavailable_decree_is_rejected_atomically() -> None:
    state = make_game_state(turn=0, state_version=0)  # default decree_authority=emergency_only
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, decision))
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_legislative_route_without_a_legislature_is_rejected_atomically() -> None:
    politics = make_politics(
        legislature=Legislature.NONE, decree_authority=DecreeAuthority.UNLIMITED
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.LEGISLATIVE)
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, decision))
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_unknown_party_influence_target_is_rejected_atomically() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = BudgetDecision(
        personal_income_rate_bps=2_500,
        influence=(
            InfluenceAllocation(party_id="no_such_party", bloc_id="whatever", political_capital=10),
        ),
    )
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, decision))
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_unknown_bloc_influence_target_is_rejected_atomically() -> None:
    state = make_game_state(turn=0, state_version=0)
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = BudgetDecision(
        personal_income_rate_bps=2_500,
        influence=(
            InfluenceAllocation(
                party_id="governing_party", bloc_id="no_such_bloc", political_capital=10
            ),
        ),
    )
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, decision))
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_zero_seat_bloc_influence_target_is_rejected_atomically() -> None:
    politics = make_politics(
        legislature=Legislature.UNICAMERAL, legislature_state=_zero_seat_bloc_legislature()
    )
    country = make_country("testland", politics=politics)
    state = make_game_state(countries={"testland": country}, player_country_id="testland")
    before = canonical_dumps(state.model_dump(mode="json"))
    decision = BudgetDecision(
        personal_income_rate_bps=2_500,
        influence=(InfluenceAllocation(party_id="gov", bloc_id="ghost", political_capital=10),),
    )
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, decision))
    assert canonical_dumps(state.model_dump(mode="json")) == before


def test_commitment_of_exactly_opening_capital_is_accepted_and_one_more_is_rejected() -> None:
    """`deficit_demo` opens at exactly 300 political capital: 300 committed is affordable to the
    last point, and 301 is rejected -- even though opening + regeneration comfortably exceeds
    both (R2: capital is committed against opening alone)."""
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    accepted = BudgetDecision(
        personal_income_rate_bps=2_000,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=300
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, accepted))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.political_capital_committed == 300

    before = canonical_dumps(state.model_dump(mode="json"))
    rejected = BudgetDecision(
        personal_income_rate_bps=2_000,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=301
            ),
        ),
    )
    with pytest.raises(TurnResolutionError):
        resolve_turn(state, _decisions_for(state, rejected))
    assert canonical_dumps(state.model_dump(mode="json")) == before


# --- failed vote still consumes commitment; downstream effects -----------------


def test_failed_vote_still_consumes_committed_capital() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    opening_capital = state.world.countries["strapped"].politics.political_capital
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(
        personal_income_rate_bps=current + 500,
        influence=(
            InfluenceAllocation(
                party_id="citizens_bloc", bloc_id="moderates", political_capital=50
            ),
        ),
    )
    resolution = resolve_turn(state, _decisions_for(state, decision))
    legislative = resolution.report.legislative
    political = resolution.report.political
    assert legislative is not None and political is not None
    assert legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    assert legislative.political_capital_committed == 50
    assert political.political_capital_spent == 50
    assert political.closing_political_capital == min(
        political.political_capital_capacity,
        opening_capital - 50 + political.political_capital_regeneration,
    )


def test_passed_budget_changes_downstream_revenue() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    current = state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps
    baseline = resolve_turn(state, _empty_decisions(state))
    raised = resolve_turn(
        state, _decisions_for(state, BudgetDecision(personal_income_rate_bps=current + 500))
    )
    assert raised.report.legislative is not None
    assert raised.report.legislative.outcome is LegislativeOutcome.PASSED_LEGISLATIVE
    assert raised.report.finance is not None and baseline.report.finance is not None
    assert (
        raised.report.finance.revenue.total_revenue != baseline.report.finance.revenue.total_revenue
    )
    assert raised.state.world.countries["arken"].finance.tax_policy.personal_income_rate_bps == (
        current + 500
    )


def test_failed_budget_leaves_downstream_policy_unchanged() -> None:
    state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
    current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
    decision = BudgetDecision(personal_income_rate_bps=current + 500)  # no influence -> fails
    resolution = resolve_turn(state, _decisions_for(state, decision))
    assert resolution.report.legislative is not None
    assert resolution.report.legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE
    player = resolution.state.world.countries["strapped"]
    original_player = state.world.countries["strapped"]
    assert player.finance.tax_policy == original_player.finance.tax_policy
    assert player.finance.spending_plan == original_player.finance.spending_plan


# --- determinism -----------------------------------------------------------------


def test_identical_legislative_games_are_byte_identical() -> None:
    def _play() -> tuple[str, str]:
        state = load_scenario_file(SCENARIO_DIR / "deficit_demo.yaml")
        current = state.world.countries["strapped"].finance.tax_policy.personal_income_rate_bps
        decision = BudgetDecision(
            personal_income_rate_bps=current + 500,
            influence=(
                InfluenceAllocation(
                    party_id="citizens_bloc", bloc_id="moderates", political_capital=162
                ),
            ),
        )
        resolution = resolve_turn(state, _decisions_for(state, decision))
        return (
            canonical_dumps(resolution.state.model_dump(mode="json")),
            canonical_dumps(resolution.report.model_dump(mode="json")),
        )

    state_a, report_a = _play()
    state_b, report_b = _play()
    assert state_a == state_b
    assert report_a == report_b
