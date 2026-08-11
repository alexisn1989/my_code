from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.canonical_json import canonical_dumps
from app.simulation.decisions import (
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
    SpendingUpdate,
)
from app.simulation.legislature import ProposalRoute
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

    def test_multiple_budget_decisions_rejected_even_with_influence_set(self) -> None:
        """The at-most-one rule is unchanged by Phase 3B1's new fields — it counts
        `BudgetDecision`s, not anything about their content."""
        with pytest.raises(ValidationError, match="at most one budget decision"):
            DecisionSet(
                expected_turn=0,
                expected_state_version=0,
                decisions=(
                    BudgetDecision(
                        personal_income_rate_bps=2_000,
                        influence=(
                            InfluenceAllocation(
                                party_id="alpha", bloc_id="core", political_capital=1
                            ),
                        ),
                    ),
                    BudgetDecision(corporate_rate_bps=2_500),
                ),
            )


class TestProposalRouteAndInfluence:
    """Phase 3B1: `BudgetDecision.route`/`.influence`, and `InfluenceAllocation`'s own rules.

    None of these validators can see `GameState` — whether a targeted bloc exists, whether the
    constitution permits the chosen route, and affordability are all resolution-time checks
    (slot 1), not construction-time ones; nothing here tests for them because nothing here could.
    """

    # --- Defaults, and pre-3B1 JSON still parsing to them -----------------------

    def test_default_route_is_legislative(self) -> None:
        decision = BudgetDecision(personal_income_rate_bps=2_500)
        assert decision.route is ProposalRoute.LEGISLATIVE

    def test_default_influence_is_empty(self) -> None:
        decision = BudgetDecision(personal_income_rate_bps=2_500)
        assert decision.influence == ()

    def test_pre_3b1_budget_json_without_the_new_fields_parses_to_the_defaults(self) -> None:
        """A `BudgetDecision` serialized before `route`/`influence` existed — no trace of either
        key — must still parse, and parse to exactly the defaults above. This is the save-
        compatibility half of adding two fields with defaults rather than making them required."""
        pre_3b1_json = (
            '{"kind":"budget","personal_income_rate_bps":2000,"corporate_rate_bps":null,'
            '"consumption_rate_bps":null,"spending_updates":[]}'
        )
        decision = BudgetDecision.model_validate_json(pre_3b1_json)
        assert decision.route is ProposalRoute.LEGISLATIVE
        assert decision.influence == ()

    # --- Valid multiple allocations, round-tripped through canonical JSON -------

    def test_multiple_allocations_in_canonical_order_are_valid_and_round_trip(self) -> None:
        decision = BudgetDecision(
            personal_income_rate_bps=2_500,
            influence=(
                InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=150),
                InfluenceAllocation(party_id="bravo", bloc_id="main", political_capital=75),
            ),
        )
        assert len(decision.influence) == 2

        dumped = canonical_dumps(decision.model_dump(mode="json"))
        reparsed = BudgetDecision.model_validate_json(dumped)
        assert reparsed == decision
        assert canonical_dumps(reparsed.model_dump(mode="json")) == dumped

    def test_two_canonically_identical_decisions_serialize_byte_identically(self) -> None:
        first = BudgetDecision(
            personal_income_rate_bps=2_500,
            influence=(
                InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=150),
                InfluenceAllocation(party_id="bravo", bloc_id="main", political_capital=75),
            ),
        )
        second = BudgetDecision(
            personal_income_rate_bps=2_500,
            influence=(
                InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=150),
                InfluenceAllocation(party_id="bravo", bloc_id="main", political_capital=75),
            ),
        )
        assert canonical_dumps(first.model_dump(mode="json")) == canonical_dumps(
            second.model_dump(mode="json")
        )

    # --- Duplicate and noncanonical targets --------------------------------------

    def test_duplicate_influence_targets_rejected(self) -> None:
        with pytest.raises(ValidationError, match="same \\(party_id, bloc_id\\) twice"):
            BudgetDecision(
                personal_income_rate_bps=2_500,
                influence=(
                    InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=100),
                    InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=50),
                ),
            )

    def test_same_bloc_id_under_different_parties_is_not_a_duplicate(self) -> None:
        """Bloc ids are only unique within their own party (`simulation.state`'s own rule) — two
        different parties may each have a bloc called `"core"`, and targeting both is legal."""
        decision = BudgetDecision(
            personal_income_rate_bps=2_500,
            influence=(
                InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=100),
                InfluenceAllocation(party_id="bravo", bloc_id="core", political_capital=50),
            ),
        )
        assert len(decision.influence) == 2

    def test_noncanonical_influence_order_is_rejected_not_normalized(self) -> None:
        with pytest.raises(ValidationError, match="sorted ascending"):
            BudgetDecision(
                personal_income_rate_bps=2_500,
                influence=(
                    InfluenceAllocation(party_id="bravo", bloc_id="main", political_capital=75),
                    InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=150),
                ),
            )

    def test_noncanonical_order_within_the_same_party_is_also_rejected(self) -> None:
        """Ordering is by the full `(party_id, bloc_id)` pair, not by `party_id` alone."""
        with pytest.raises(ValidationError, match="sorted ascending"):
            BudgetDecision(
                personal_income_rate_bps=2_500,
                influence=(
                    InfluenceAllocation(party_id="alpha", bloc_id="reform", political_capital=10),
                    InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=10),
                ),
            )

    # --- Decree route takes no influence -----------------------------------------

    def test_decree_route_with_influence_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nobody to whip"):
            BudgetDecision(
                personal_income_rate_bps=2_500,
                route=ProposalRoute.DECREE,
                influence=(
                    InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=100),
                ),
            )

    def test_decree_route_with_no_influence_is_valid(self) -> None:
        decision = BudgetDecision(personal_income_rate_bps=2_500, route=ProposalRoute.DECREE)
        assert decision.route is ProposalRoute.DECREE
        assert decision.influence == ()

    def test_legislative_route_with_influence_is_valid(self) -> None:
        decision = BudgetDecision(
            personal_income_rate_bps=2_500,
            route=ProposalRoute.LEGISLATIVE,
            influence=(
                InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=100),
            ),
        )
        assert decision.route is ProposalRoute.LEGISLATIVE
        assert len(decision.influence) == 1


class TestInfluenceAllocationValidation:
    def test_a_valid_allocation_round_trips(self) -> None:
        allocation = InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=100)
        assert allocation.party_id == "alpha"
        assert allocation.bloc_id == "core"
        assert allocation.political_capital == 100

    def test_empty_party_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InfluenceAllocation(party_id="", bloc_id="core", political_capital=100)

    def test_empty_bloc_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InfluenceAllocation(party_id="alpha", bloc_id="", political_capital=100)

    def test_zero_political_capital_is_rejected(self) -> None:
        """`gt=0`, not `ge=0` — an allocation of nothing is not a smaller allocation, it is not
        an allocation at all, and omitting the target entirely is how "nothing committed" is
        actually expressed."""
        with pytest.raises(ValidationError):
            InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=0)

    def test_negative_political_capital_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=-1)

    @pytest.mark.parametrize(
        "bad_value",
        [
            pytest.param(True, id="bool-true"),
            pytest.param(False, id="bool-false"),
            pytest.param(100.0, id="whole-number-float"),
            pytest.param(100.5, id="fractional-float"),
            pytest.param("100", id="numeric-string"),
        ],
    )
    def test_political_capital_rejects_non_strict_int_representations(
        self, bad_value: object
    ) -> None:
        with pytest.raises(ValidationError):
            InfluenceAllocation(party_id="alpha", bloc_id="core", political_capital=bad_value)
