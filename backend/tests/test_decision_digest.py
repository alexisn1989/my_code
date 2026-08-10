"""Tests for `simulation.decisions.budget_decision_digest` (Phase 3B1, R8) and the syntax-only
`LegislativeReport.budget_decision_digest` validator that consumes its shape.

Two different things are under test, deliberately kept apart:

- **The pure digest function itself** (`TestBudgetDecisionDigest`): a deterministic content
  fingerprint over a `BudgetDecision`'s own `model_dump(mode="json")`, covering every field by
  construction. `test_budget_decisions.py` already proves canonically-identical decisions
  serialize byte-identically (`test_two_canonically_identical_decisions_serialize_byte_identically`)
  and that influence must already be in canonical order or is rejected outright
  (`test_noncanonical_influence_order_is_rejected_not_normalized`) -- this file builds directly on
  both of those to show the digest itself is what a caller actually uses: stable across
  independent, logically-identical constructions, and sensitive to every individual field.
- **`LegislativeReport`'s syntax-only validator** (`TestLegislativeReportDigestSyntax`): checks
  only that a stored digest is *shaped* like one of this function's outputs -- lowercase 64-hex,
  present iff the outcome is not `NO_PROPOSAL` -- never that it is the RIGHT one. Semantic equality
  against a real submitted decision is `simulation.reconciliation`'s job alone (group 18), covered
  in `test_reconciliation.py`, not here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import (
    BudgetDecision,
    InfluenceAllocation,
    SpendingUpdate,
    budget_decision_digest,
)
from app.simulation.legislature import LegislativeOutcome, ProposalRoute
from app.simulation.report import LegislativeReport
from app.simulation.state import SpendingCategory
from tests.test_legislative_report import _minimal_legislative_report


def _full_decision(**overrides: object) -> BudgetDecision:
    """A decision touching every field the digest must cover: all three rate targets, two
    spending targets, a non-default route... except `route` and `influence` are mutually
    exclusive (a decree takes no influence), so callers of this helper get the LEGISLATIVE/
    influence combination by default and pass `route=ProposalRoute.DECREE, influence=()`
    explicitly to exercise the other one.
    """
    fields: dict[str, object] = dict(
        personal_income_rate_bps=2_500,
        corporate_rate_bps=3_000,
        consumption_rate_bps=1_200,
        spending_updates=(
            SpendingUpdate(category=SpendingCategory.HEALTH, amount=31_000_00),
            SpendingUpdate(category=SpendingCategory.EDUCATION, amount=23_000_00),
        ),
        route=ProposalRoute.LEGISLATIVE,
        influence=(
            InfluenceAllocation(party_id="governing_party", bloc_id="core", political_capital=10),
            InfluenceAllocation(party_id="opposition_party", bloc_id="main", political_capital=5),
        ),
    )
    fields.update(overrides)
    return BudgetDecision(**fields)  # type: ignore[arg-type]


class TestBudgetDecisionDigest:
    def test_same_logical_decision_built_independently_twice_has_the_same_digest(self) -> None:
        first = _full_decision()
        second = _full_decision()
        assert first is not second
        assert first == second
        assert budget_decision_digest(first) == budget_decision_digest(second)

    def test_digest_is_a_lowercase_64_character_hex_string(self) -> None:
        digest = budget_decision_digest(_full_decision())
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)  # raises ValueError if not valid hex

    def test_a_minimal_decision_digests_differently_from_the_full_one(self) -> None:
        minimal = BudgetDecision(personal_income_rate_bps=2_500)
        full = _full_decision()
        assert budget_decision_digest(minimal) != budget_decision_digest(full)

    @pytest.mark.parametrize(
        "field_name,new_value",
        [
            ("personal_income_rate_bps", 2_600),
            ("corporate_rate_bps", 3_100),
            ("consumption_rate_bps", 1_300),
        ],
    )
    def test_changing_a_single_rate_target_changes_the_digest(
        self, field_name: str, new_value: int
    ) -> None:
        baseline = _full_decision()
        changed = _full_decision(**{field_name: new_value})
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_changing_a_spending_target_amount_changes_the_digest(self) -> None:
        baseline = _full_decision()
        changed = _full_decision(
            spending_updates=(
                SpendingUpdate(category=SpendingCategory.HEALTH, amount=31_000_01),
                SpendingUpdate(category=SpendingCategory.EDUCATION, amount=23_000_00),
            )
        )
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_changing_which_spending_category_is_targeted_changes_the_digest(self) -> None:
        baseline = _full_decision()
        changed = _full_decision(
            spending_updates=(
                SpendingUpdate(category=SpendingCategory.HEALTH, amount=31_000_00),
                SpendingUpdate(category=SpendingCategory.WELFARE, amount=23_000_00),
            )
        )
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_changing_route_changes_the_digest(self) -> None:
        legislative = _full_decision(route=ProposalRoute.LEGISLATIVE)
        decree = _full_decision(route=ProposalRoute.DECREE, influence=())
        assert budget_decision_digest(legislative) != budget_decision_digest(decree)

    def test_changing_an_influence_allocation_amount_changes_the_digest(self) -> None:
        baseline = _full_decision()
        changed = _full_decision(
            influence=(
                InfluenceAllocation(
                    party_id="governing_party", bloc_id="core", political_capital=11
                ),
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=5
                ),
            )
        )
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_changing_an_influence_target_identity_changes_the_digest(self) -> None:
        baseline = _full_decision()
        changed = _full_decision(
            influence=(
                InfluenceAllocation(
                    party_id="governing_party", bloc_id="core", political_capital=10
                ),
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="rebels", political_capital=5
                ),
            )
        )
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_dropping_an_influence_allocation_changes_the_digest(self) -> None:
        baseline = _full_decision()
        changed = _full_decision(
            influence=(
                InfluenceAllocation(
                    party_id="governing_party", bloc_id="core", political_capital=10
                ),
            )
        )
        assert budget_decision_digest(baseline) != budget_decision_digest(changed)

    def test_canonical_influence_order_is_the_only_representation_so_the_digest_is_unambiguous(
        self,
    ) -> None:
        """`influence` must already be in ascending `(party_id, bloc_id)` order or construction
        itself is rejected (`test_budget_decisions.py::
        test_noncanonical_influence_order_is_rejected_not_normalized`) -- there is no alternate,
        differently-ordered representation of the "same" decision for the digest to (correctly or
        incorrectly) normalize. This test pins that guarantee from the digest's side: the only
        legal way to build this decision digests identically every time."""
        allocations = (
            InfluenceAllocation(party_id="governing_party", bloc_id="core", political_capital=10),
            InfluenceAllocation(party_id="opposition_party", bloc_id="main", political_capital=5),
        )
        first = BudgetDecision(personal_income_rate_bps=2_500, influence=allocations)
        second = BudgetDecision(
            personal_income_rate_bps=2_500,
            influence=(
                InfluenceAllocation(
                    party_id="governing_party", bloc_id="core", political_capital=10
                ),
                InfluenceAllocation(
                    party_id="opposition_party", bloc_id="main", political_capital=5
                ),
            ),
        )
        assert budget_decision_digest(first) == budget_decision_digest(second)
        with pytest.raises(ValidationError, match="sorted ascending"):
            BudgetDecision(personal_income_rate_bps=2_500, influence=tuple(reversed(allocations)))


class TestLegislativeReportDigestSyntax:
    """The syntax-only validator on `LegislativeReport.budget_decision_digest` -- shape, not
    semantic correctness (that is `simulation.reconciliation`'s job; see `test_reconciliation.py`,
    group 18)."""

    def test_no_proposal_requires_none(self) -> None:
        report = _minimal_legislative_report(
            outcome=LegislativeOutcome.NO_PROPOSAL,
            route=None,
            allocated=0,
            chambers=(),
            blocs=(),
            budget_decision_digest=None,
        )
        assert report.budget_decision_digest is None

    def test_no_proposal_rejects_a_present_digest(self) -> None:
        with pytest.raises(ValidationError, match="NO_PROPOSAL must carry budget_decision_digest"):
            _minimal_legislative_report(
                outcome=LegislativeOutcome.NO_PROPOSAL,
                route=None,
                allocated=0,
                chambers=(),
                blocs=(),
                budget_decision_digest="a" * 64,
            )

    def test_a_real_outcome_requires_a_digest(self) -> None:
        with pytest.raises(ValidationError, match="must carry a budget_decision_digest"):
            LegislativeReport.model_validate(
                _minimal_legislative_report().model_dump(mode="json")
                | {"budget_decision_digest": None}
            )

    @pytest.mark.parametrize(
        "bad_digest",
        [
            "A" * 64,  # uppercase
            "a" * 63,  # too short
            "a" * 65,  # too long
            "g" * 64,  # non-hex character
            "",  # empty
        ],
    )
    def test_a_real_outcome_rejects_malformed_digests(self, bad_digest: str) -> None:
        with pytest.raises(ValidationError, match="not a lowercase 64-character hexadecimal"):
            _minimal_legislative_report(budget_decision_digest=bad_digest)

    def test_a_real_outcome_accepts_a_well_shaped_digest(self) -> None:
        digest = budget_decision_digest(BudgetDecision(personal_income_rate_bps=2_500))
        report = _minimal_legislative_report(budget_decision_digest=digest)
        assert report.budget_decision_digest == digest
