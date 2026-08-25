"""Gate 4A3A: the policy-card catalog, proven against real scenario content
and the same structural preflight `/preview` and `/resolve` share.

The load-bearing property this file exists to pin: **no selectable card or
available route ever contains a no-op, out-of-range, incoherent, noncanonical,
or otherwise invalid template.** That is proven mechanically, not asserted by
convention, by re-running `first_decision_problem` -- the exact function
`policy_cards.py` itself calls -- over every emitted available template and
checking it still says "no problem."
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.decision_preflight import first_decision_problem
from app.api.policy_card_calibration import TAX_STEP_BPS
from app.api.policy_cards import build_decision_options_with_policy_cards, build_policy_cards
from app.api.projections import revision_token
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.legislature import ProposalRoute
from app.simulation.state import (
    GameState,
    GovernmentFinanceState,
    OutcomeBucket,
    TerminalOutcomeState,
    VictoryReason,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
ALL_SCENARIOS = ("tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml")


def _state(scenario_filename: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / scenario_filename)


def _with_player_country_update(state: GameState, **country_updates: object) -> GameState:
    country = state.world.countries[state.world.player_country_id]
    new_country = country.model_copy(update=country_updates)
    new_countries = dict(state.world.countries)
    new_countries[state.world.player_country_id] = new_country
    return state.model_copy(
        update={"world": state.world.model_copy(update={"countries": new_countries})}
    )


def _terminal_state(state: GameState) -> GameState:
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    victory = TerminalOutcomeState(
        bucket=OutcomeBucket.VICTORY,
        victory_reason=VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED,
        turn=state.turn,
    )
    return _with_player_country_update(
        state, politics=politics.model_copy(update={"terminal_outcome": victory})
    )


# --------------------------------------------------------------------------
# Generation, for every shipped scenario
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_catalog_generates_for_every_shipped_scenario(scenario: str) -> None:
    cards = build_policy_cards(_state(scenario))
    assert cards, f"{scenario}: catalog must not be empty"
    assert any(card.available for card in cards), f"{scenario}: at least one card must be usable"


#: Gate 4A3A calibration -- (total cards, available cards), computed directly
#: from the real catalog generator against each shipped scenario's actual
#: authored content (never hand-derived or guessed). A change to any of these
#: numbers means the catalog's shape genuinely changed for that scenario --
#: either a deliberate content/calibration change (update the table) or a
#: real regression (do not).
_KNOWN_CARD_COUNTS: dict[str, tuple[int, int]] = {
    "tiny_valid.yaml": (44, 33),
    "deficit_demo.yaml": (45, 35),
    "decree_state.yaml": (44, 31),
}


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_catalog_size_matches_known_calibration(scenario: str) -> None:
    cards = build_policy_cards(_state(scenario))
    expected_total, expected_available = _KNOWN_CARD_COUNTS[scenario]
    actual_available = sum(1 for card in cards if card.available)
    assert (len(cards), actual_available) == (expected_total, expected_available), (
        f"{scenario}: catalog shape changed -- if this is a deliberate content or "
        "calibration change, update _KNOWN_CARD_COUNTS; otherwise this is a regression"
    )


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_card_ids_are_unique_and_generation_is_deterministic(scenario: str) -> None:
    state = _state(scenario)
    first = build_policy_cards(state)
    second = build_policy_cards(state)

    ids = [card.card_id for card in first]
    assert len(ids) == len(set(ids))
    assert [card.model_dump_json() for card in first] == [card.model_dump_json() for card in second]


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_canonical_order_is_taxation_then_spending_then_constitution_then_restraint(
    scenario: str,
) -> None:
    categories = [card.category for card in build_policy_cards(_state(scenario))]
    rank = {"taxation": 0, "spending": 1, "constitution": 2, "restraint": 3}
    ranks = [rank[category] for category in categories]
    assert ranks == sorted(ranks)
    assert categories[-1] == "restraint"
    assert categories.count("restraint") == 1


# --------------------------------------------------------------------------
# R3: every selectable card/route agrees with the shared preflight
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_no_available_route_contains_a_structurally_invalid_template(scenario: str) -> None:
    """Re-runs the SAME check `policy_cards.py` used to decide availability.

    This is not a duplicate of that internal logic -- it is calling the one
    real `first_decision_problem` function a second time, independently, and
    asserting agreement. If a future edit to `policy_cards.py` ever emitted a
    card whose template disagreed with the preflight, this fails.
    """
    state = _state(scenario)
    cards = build_policy_cards(state)
    checked = 0
    for card in cards:
        for route in card.routes:
            if not route.available:
                assert route.template is None
                continue
            assert route.template is not None
            decision_set = DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(route.template,),
            )
            problem = first_decision_problem(state, decision_set)
            assert problem is None, (
                f"{scenario}/{card.card_id}/{route.route}: preflight disagrees -- {problem}"
            )
            checked += 1
    assert checked > 0, f"{scenario}: no available route was found to check"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_no_available_amendment_route_targets_an_axis_already_at_its_current_value(
    scenario: str,
) -> None:
    """The specific no-op failure mode the preflight rejects, pinned directly:
    every axis a selectable amendment template targets must genuinely differ
    from that axis's CURRENT value in the opening constitution."""
    state = _state(scenario)
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    constitution = politics.constitution
    checked = 0
    for card in build_policy_cards(state):
        for route in card.routes:
            template = route.template
            invalid = (
                not route.available
                or template is None
                or template.kind != "constitutional_amendment"
            )
            if invalid:
                continue
            for target in template.targets:  # type: ignore[union-attr]
                assert target.value != getattr(constitution, target.axis)
                checked += 1
    assert checked > 0, f"{scenario}: no available amendment target was found to check"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_every_selectable_template_round_trips_through_decision_set(scenario: str) -> None:
    """A card's template is a real, submittable `Decision` -- not a shape that
    merely looks like one. Round-tripping it through `DecisionSet.model_validate`
    with the current revision, the same way a client would build a submission,
    must succeed for every available route."""
    state = _state(scenario)
    revision = revision_token(state)
    turn_str, version_str = revision.split(".")
    checked = 0
    for card in build_policy_cards(state):
        for route in card.routes:
            if not route.available:
                continue
            assert route.template is not None
            payload = {
                "expected_turn": int(turn_str),
                "expected_state_version": int(version_str),
                "decisions": (route.template.model_dump(mode="json"),),
            }
            rebuilt = DecisionSet.model_validate(payload)
            assert rebuilt.decisions[0] == route.template
            checked += 1
    assert checked > 0, f"{scenario}: no available route was found to round-trip"


# --------------------------------------------------------------------------
# Disabled-card coverage: every stable reason is genuinely reachable
# --------------------------------------------------------------------------


def test_every_unavailable_route_and_card_carries_a_stable_reason_and_detail() -> None:
    for scenario in ALL_SCENARIOS:
        for card in build_policy_cards(_state(scenario)):
            if not card.available:
                assert card.unavailable_reason is not None
                assert card.unavailable_detail is not None
            for route in card.routes:
                if not route.available:
                    assert route.unavailable_reason is not None
                    assert route.unavailable_detail is not None


def test_outside_legal_bounds_is_reachable_on_a_saturated_tax_rate() -> None:
    state = _state("decree_state.yaml")
    finance = state.world.countries[state.world.player_country_id].finance
    assert finance is not None
    saturated_policy = finance.tax_policy.model_copy(
        update={"personal_income_rate_bps": 10_000 - (TAX_STEP_BPS - 1)}
    )
    saturated_finance: GovernmentFinanceState = finance.model_copy(
        update={"tax_policy": saturated_policy}
    )
    saturated_state = _with_player_country_update(state, finance=saturated_finance)

    cards = build_policy_cards(saturated_state)
    increase_card = next(c for c in cards if c.card_id == "tax_personal_income_increase")
    assert increase_card.available is False
    assert increase_card.unavailable_reason == "outside_legal_bounds"
    assert increase_card.routes == ()


def test_amendment_by_decree_is_unavailable_on_every_shipped_scenario() -> None:
    """No shipped scenario satisfies BOTH `decree_authority == unlimited` AND
    `legislature == none` simultaneously -- `decree_state` has unlimited
    decree but a sitting legislature; the other two lack unlimited decree
    entirely. Checked on cards whose TARGET is itself coherent (`available`),
    since an incoherent target fails identically on both routes before the
    route-specific rule is ever reached -- that shared failure is already
    covered by `test_no_available_route_contains_a_structurally_invalid_
    template`'s and the disabled-card coverage test's assertions."""
    for scenario in ALL_SCENARIOS:
        cards = build_policy_cards(_state(scenario))
        available_amendment_cards = [
            card for card in cards if card.category == "constitution" and card.available
        ]
        assert available_amendment_cards
        for card in available_amendment_cards:
            decree_routes = [r for r in card.routes if r.route is ProposalRoute.DECREE]
            assert decree_routes, f"{scenario}/{card.card_id}: no decree route emitted"
            for route in decree_routes:
                assert not route.available
                assert route.unavailable_reason in (
                    "route_constitutionally_unavailable",
                    "decree_cannot_amend_with_legislature",
                )


def test_decree_state_reports_the_specific_legislature_present_reason() -> None:
    """The route-level detail R3 specifically requires: on `decree_state` the
    amendment CARD is legal (legislative route works) while its DECREE route
    is illegal for a reason budget decrees on the same scenario do not hit."""
    cards = build_policy_cards(_state("decree_state.yaml"))
    amendment_card = next(c for c in cards if c.card_id == "constitution_decree_authority_to_none")
    decree_route = next(r for r in amendment_card.routes if r.route is ProposalRoute.DECREE)
    assert decree_route.unavailable_reason == "decree_cannot_amend_with_legislature"

    budget_card = next(c for c in cards if c.card_id == "tax_personal_income_increase")
    budget_decree_route = next(r for r in budget_card.routes if r.route is ProposalRoute.DECREE)
    assert budget_decree_route.available


def test_no_baseline_to_scale_is_reachable_on_a_zeroed_spending_category() -> None:
    state = _state("tiny_valid.yaml")
    finance = state.world.countries[state.world.player_country_id].finance
    assert finance is not None
    zeroed_plan = finance.spending_plan.model_copy(update={"administration": 0})
    zeroed_state = _with_player_country_update(
        state, finance=finance.model_copy(update={"spending_plan": zeroed_plan})
    )

    cards = build_policy_cards(zeroed_state)
    increase = next(c for c in cards if c.card_id == "spending_administration_increase")
    decrease = next(c for c in cards if c.card_id == "spending_administration_decrease")
    for card in (increase, decrease):
        assert card.available is False
        assert card.unavailable_reason == "no_baseline_to_scale"
        assert card.routes == ()


def test_term_limit_presets_are_all_blocked_on_decree_state_by_its_hereditary_executive() -> None:
    cards = build_policy_cards(_state("decree_state.yaml"))
    term_limit_cards = [c for c in cards if c.card_id.startswith("constitution_term_limit_to_")]
    assert len(term_limit_cards) == 3
    for card in term_limit_cards:
        assert card.available is False
        assert card.unavailable_reason == "requires_companion_constitutional_change"
        assert card.diagnostic_code == "term_limit_requires_non_hereditary_executive"
        assert card.diagnostic_code not in card.unavailable_detail  # type: ignore[operator]


# --------------------------------------------------------------------------
# Terminal state disables everything
# --------------------------------------------------------------------------


def test_terminal_state_disables_every_card_including_no_proposal() -> None:
    state = _terminal_state(_state("decree_state.yaml"))
    cards = build_policy_cards(state)
    assert cards, "the catalog itself is still built, just entirely disabled"
    for card in cards:
        assert card.available is False
        assert card.unavailable_reason == "game_concluded"
        assert card.unavailable_detail is not None
        assert card.diagnostic_code is None
        assert card.routes == ()

    no_proposal = next(c for c in cards if c.clears_proposal_slot)
    assert no_proposal.available is False
    assert no_proposal.unavailable_reason == "game_concluded"


# --------------------------------------------------------------------------
# Wiring: build_decision_options_with_policy_cards
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_decision_options_wrapper_carries_the_same_revision_and_cards(scenario: str) -> None:
    state = _state(scenario)
    options = build_decision_options_with_policy_cards(state)
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    assert options.revision == revision_token(state)
    assert options.policy_cards == build_policy_cards(state)
    assert options.opening_capital == politics.political_capital


def test_decision_options_wrapper_does_not_mutate_state() -> None:
    state = _state("tiny_valid.yaml")
    before = state.model_dump_json()
    build_decision_options_with_policy_cards(state)
    assert state.model_dump_json() == before
