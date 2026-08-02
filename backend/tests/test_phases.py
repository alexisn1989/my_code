"""Tests for `simulation.phases`, focused on the R3 opening-snapshot guarantee:
`OpeningFinanceSnapshot` is captured before any budget mutation and cannot be
changed by anything that happens to the working state afterward.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.simulation.decisions import DecisionSet
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.state import GameState
from tests.conftest import make_game_state


def _run_phases_for(state: GameState) -> PhaseContext:
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    ctx = PhaseContext(state=state, decisions=decisions, resolving_turn=state.turn)
    run_phases(ctx)
    return ctx


def test_opening_snapshot_matches_state_as_it_was_before_any_phase_ran() -> None:
    state = make_game_state(turn=0, state_version=0)
    player_id = state.world.player_country_id
    original_finance = state.world.countries[player_id].finance
    assert original_finance is not None
    original_cash = state.world.countries[player_id].treasury.cash_on_hand
    original_debt = state.world.countries[player_id].treasury.debt

    ctx = _run_phases_for(state)

    assert ctx.finance is not None
    opening = ctx.finance.opening
    assert opening.opening_cash == original_cash
    assert opening.opening_debt == original_debt
    assert opening.previous_tax_policy == original_finance.tax_policy
    assert opening.previous_spending_plan == original_finance.spending_plan
    assert opening.tax_bases == original_finance.tax_bases


def test_opening_snapshot_dataclass_itself_is_frozen() -> None:
    state = make_game_state(turn=0, state_version=0)
    ctx = _run_phases_for(state)
    assert ctx.finance is not None

    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.finance.opening.opening_cash = 999_999_999  # type: ignore[misc]


def test_reassigning_working_state_finance_does_not_affect_the_opening_snapshot() -> None:
    state = make_game_state(turn=0, state_version=0)
    ctx = _run_phases_for(state)
    assert ctx.finance is not None
    before_cash = ctx.finance.opening.opening_cash
    before_policy = ctx.finance.opening.previous_tax_policy

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    assert player.finance is not None
    player.treasury = player.treasury.model_copy(update={"cash_on_hand": 1, "debt": 2})
    player.finance = player.finance.model_copy(
        update={
            "tax_policy": player.finance.tax_policy.model_copy(
                update={"personal_income_rate_bps": 1}
            )
        }
    )

    assert ctx.finance.opening.opening_cash == before_cash
    assert ctx.finance.opening.previous_tax_policy == before_policy


def test_in_place_mutation_of_the_working_tax_policy_does_not_affect_the_opening_snapshot() -> None:
    """The stricter version of the test above: `TaxPolicyState` has
    `validate_assignment=True`, which permits mutating a field on a *live*
    instance (`obj.field = x`) rather than only replacing the whole object. If
    `OpeningFinanceSnapshot` stored a bare reference to the working state's
    `TaxPolicyState` instead of its own copy, this in-place mutation would
    silently corrupt what the turn's report calls "opening" — this is exactly
    what `phases._apply_legal_and_administrative_changes`'s `.model_copy()`
    calls (not bare references) at snapshot-capture time prevent."""
    state = make_game_state(turn=0, state_version=0)
    ctx = _run_phases_for(state)
    assert ctx.finance is not None
    before_rate = ctx.finance.opening.previous_tax_policy.personal_income_rate_bps

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    assert player.finance is not None
    # In-place field mutation on the *same* TaxPolicyState instance ctx.state
    # currently holds — not a reassignment to a new object.
    player.finance.tax_policy.personal_income_rate_bps = before_rate + 1234

    assert ctx.finance.opening.previous_tax_policy.personal_income_rate_bps == before_rate
    assert player.finance.tax_policy.personal_income_rate_bps == before_rate + 1234


def test_in_place_mutation_of_the_working_spending_plan_does_not_affect_the_opening_snapshot() -> (
    None
):
    state = make_game_state(turn=0, state_version=0)
    ctx = _run_phases_for(state)
    assert ctx.finance is not None
    before_health = ctx.finance.opening.previous_spending_plan.health

    player = ctx.state.world.countries[ctx.state.world.player_country_id]
    assert player.finance is not None
    player.finance.spending_plan.health = before_health + 5678

    assert ctx.finance.opening.previous_spending_plan.health == before_health
    assert player.finance.spending_plan.health == before_health + 5678
