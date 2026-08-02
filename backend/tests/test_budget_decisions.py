from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import BudgetDecision, DecisionSet, SpendingUpdate
from app.simulation.state import SpendingCategory


class TestBudgetDecisionValidation:
    def test_a_single_rate_target_is_valid(self) -> None:
        decision = BudgetDecision(personal_income_rate_bps=2_500)
        assert decision.personal_income_rate_bps == 2_500
        assert decision.corporate_rate_bps is None
        assert decision.consumption_rate_bps is None
        assert decision.spending_updates == ()

    def test_omitted_fields_default_to_none_meaning_unchanged(self) -> None:
        decision = BudgetDecision(corporate_rate_bps=3_000)
        assert decision.personal_income_rate_bps is None
        assert decision.consumption_rate_bps is None

    def test_a_single_spending_update_is_valid(self) -> None:
        decision = BudgetDecision(
            spending_updates=(SpendingUpdate(category=SpendingCategory.HEALTH, amount=1_000_00),)
        )
        assert decision.spending_updates[0].category == SpendingCategory.HEALTH
        assert decision.spending_updates[0].amount == 1_000_00

    def test_multiple_distinct_spending_updates_are_valid(self) -> None:
        decision = BudgetDecision(
            spending_updates=(
                SpendingUpdate(category=SpendingCategory.HEALTH, amount=1),
                SpendingUpdate(category=SpendingCategory.DEFENSE, amount=2),
            )
        )
        assert len(decision.spending_updates) == 2

    def test_empty_decision_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            BudgetDecision()

    def test_target_equal_to_hypothetical_current_value_is_still_valid(self) -> None:
        # BudgetDecision has no notion of "current" value — any explicit target
        # is a valid submission; whether it changes anything is determined
        # later by FinanceReport, which labels it unchanged rather than the
        # decision itself refusing to accept it.
        decision = BudgetDecision(personal_income_rate_bps=2_000)
        assert decision.personal_income_rate_bps == 2_000

    def test_duplicate_spending_categories_rejected(self) -> None:
        with pytest.raises(ValidationError, match="same spending category twice"):
            BudgetDecision(
                spending_updates=(
                    SpendingUpdate(category=SpendingCategory.HEALTH, amount=1),
                    SpendingUpdate(category=SpendingCategory.HEALTH, amount=2),
                )
            )

    def test_unknown_spending_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpendingUpdate.model_validate({"category": "not_a_real_category", "amount": 100})

    def test_negative_spending_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SpendingUpdate(category=SpendingCategory.HEALTH, amount=-1)

    @pytest.mark.parametrize("bad_bps", [-1, 10_001])
    def test_rate_out_of_bps_range_rejected(self, bad_bps: int) -> None:
        with pytest.raises(ValidationError):
            BudgetDecision(personal_income_rate_bps=bad_bps)

    def test_unknown_top_level_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BudgetDecision.model_validate(
                {"personal_income_rate_bps": 2_000, "unknown_field": True}
            )


class TestDecisionSetValidation:
    def test_zero_or_one_budget_decisions_are_valid(self) -> None:
        DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
        DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(BudgetDecision(personal_income_rate_bps=2_000),),
        )

    def test_multiple_budget_decisions_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most one budget decision"):
            DecisionSet(
                expected_turn=0,
                expected_state_version=0,
                decisions=(
                    BudgetDecision(personal_income_rate_bps=2_000),
                    BudgetDecision(corporate_rate_bps=2_500),
                ),
            )

    def test_a_list_of_decisions_is_accepted_and_stored_as_a_tuple(self) -> None:
        decision_set = DecisionSet.model_validate(
            {
                "expected_turn": 0,
                "expected_state_version": 0,
                "decisions": [{"personal_income_rate_bps": 2_000}],
            }
        )
        assert isinstance(decision_set.decisions, tuple)
        assert len(decision_set.decisions) == 1
