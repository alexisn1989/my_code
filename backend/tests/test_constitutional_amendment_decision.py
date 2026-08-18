"""Gate 3C3 commit 18: constitutional-amendment decision shape and provenance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.constitution import DecreeAuthority, ExecutiveSelection, ExecutiveSystem
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    ConstitutionalAmendmentDecision,
    DecisionSet,
    DecreeAuthorityTarget,
    ElectionIntervalTarget,
    ExecutiveSelectionTarget,
    ExecutiveSystemTarget,
    InfluenceAllocation,
    TermLimitTarget,
    constitutional_amendment_decision_digest,
)
from app.simulation.legislature import CapitalExpenditureCategory, ProposalRoute
from app.simulation.report import CapitalExpenditureReport


def _minimal_amendment(**updates: object) -> ConstitutionalAmendmentDecision:
    values: dict[str, object] = {
        "targets": (DecreeAuthorityTarget(value=DecreeAuthority.NONE),),
    }
    values.update(updates)
    return ConstitutionalAmendmentDecision(**values)  # type: ignore[arg-type]


def test_all_five_target_variants_round_trip_in_canonical_axis_order() -> None:
    decision = ConstitutionalAmendmentDecision(
        targets=(
            DecreeAuthorityTarget(value=DecreeAuthority.NONE),
            ExecutiveSelectionTarget(value=ExecutiveSelection.DIRECT_ELECTION),
            ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
            TermLimitTarget(value=None),
            ElectionIntervalTarget(value=8),
        )
    )

    reparsed = ConstitutionalAmendmentDecision.model_validate_json(decision.model_dump_json())
    assert reparsed == decision
    assert [target.axis for target in decision.targets] == sorted(
        target.axis for target in decision.targets
    )


def test_target_union_requires_a_known_explicit_axis_tag() -> None:
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        ConstitutionalAmendmentDecision.model_validate(
            {"targets": [{"axis": "judicial_review", "value": "strong"}]}
        )


def test_targets_must_be_nonempty_unique_and_canonically_ordered() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        ConstitutionalAmendmentDecision(targets=())
    with pytest.raises(ValidationError, match="same axis twice"):
        ConstitutionalAmendmentDecision(
            targets=(
                DecreeAuthorityTarget(value=DecreeAuthority.NONE),
                DecreeAuthorityTarget(value=DecreeAuthority.UNLIMITED),
            )
        )
    with pytest.raises(ValidationError, match="sorted ascending by axis name"):
        ConstitutionalAmendmentDecision(
            targets=(
                ExecutiveSystemTarget(value=ExecutiveSystem.PRESIDENTIAL),
                DecreeAuthorityTarget(value=DecreeAuthority.NONE),
            )
        )


@pytest.mark.parametrize("value", [0, -1, True, "8"])
def test_interval_target_requires_a_strict_positive_integer_or_none(value: object) -> None:
    with pytest.raises(ValidationError):
        ElectionIntervalTarget(value=value)  # type: ignore[arg-type]
    assert ElectionIntervalTarget(value=None).value is None


@pytest.mark.parametrize("value", [0, -1, True, "2"])
def test_term_limit_target_requires_a_strict_positive_integer_or_none(value: object) -> None:
    with pytest.raises(ValidationError):
        TermLimitTarget(value=value)  # type: ignore[arg-type]
    assert TermLimitTarget(value=None).value is None


def test_influence_rejects_duplicate_noncanonical_and_decree_allocations() -> None:
    alpha = InfluenceAllocation(party_id="alpha", bloc_id="main", political_capital=1)
    beta = InfluenceAllocation(party_id="beta", bloc_id="main", political_capital=2)
    with pytest.raises(ValidationError, match="same .* twice"):
        _minimal_amendment(influence=(alpha, alpha))
    with pytest.raises(ValidationError, match="sorted ascending"):
        _minimal_amendment(influence=(beta, alpha))
    with pytest.raises(ValidationError, match="decree route takes no influence"):
        _minimal_amendment(route=ProposalRoute.DECREE, influence=(alpha,))


def test_decision_set_accepts_investment_plus_amendment_and_finds_by_kind() -> None:
    investment = BlocRelationshipInvestmentDecision(
        investments=(BlocInvestment(party_id="alpha", bloc_id="main", political_capital=1),)
    )
    amendment = _minimal_amendment()
    decision_set = DecisionSet(
        expected_turn=0,
        expected_state_version=0,
        decisions=(investment, amendment),
    )
    assert decision_set.budget_decision() is None
    assert decision_set.relationship_investment_decision() is investment
    assert decision_set.constitutional_amendment_decision() is amendment


def test_decision_set_rejects_budget_plus_amendment_as_two_policy_proposals() -> None:
    with pytest.raises(ValidationError, match="at most one policy proposal"):
        DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(BudgetDecision(personal_income_rate_bps=2_000), _minimal_amendment()),
        )


def test_decision_set_rejects_multiple_amendments() -> None:
    with pytest.raises(ValidationError, match="at most one constitutional-amendment decision"):
        DecisionSet(
            expected_turn=0,
            expected_state_version=0,
            decisions=(_minimal_amendment(), _minimal_amendment()),
        )


def test_amendment_digest_is_stable_complete_and_lowercase_hex() -> None:
    original = _minimal_amendment()
    independently_built = _minimal_amendment()
    changed = _minimal_amendment(
        targets=(DecreeAuthorityTarget(value=DecreeAuthority.EMERGENCY_ONLY),)
    )
    digest = constitutional_amendment_decision_digest(original)
    assert digest == constitutional_amendment_decision_digest(independently_built)
    assert digest != constitutional_amendment_decision_digest(changed)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert set(digest) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    ("party_id", "bloc_id"),
    [(None, None), ("party", "bloc")],
)
def test_amendment_capital_row_allows_decree_or_legislative_target_shape(
    party_id: str | None, bloc_id: str | None
) -> None:
    row = CapitalExpenditureReport(
        category=CapitalExpenditureCategory.CONSTITUTIONAL_AMENDMENT,
        party_id=party_id,
        bloc_id=bloc_id,
        political_capital=1,
        decision_digest="a" * 64,
    )
    assert (row.party_id, row.bloc_id) == (party_id, bloc_id)


def test_amendment_capital_row_rejects_a_partial_target() -> None:
    with pytest.raises(ValidationError, match="either both .* or neither"):
        CapitalExpenditureReport(
            category=CapitalExpenditureCategory.CONSTITUTIONAL_AMENDMENT,
            party_id="party",
            bloc_id=None,
            political_capital=1,
            decision_digest="a" * 64,
        )
