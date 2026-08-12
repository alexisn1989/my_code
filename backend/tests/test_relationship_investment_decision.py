"""Phase 3B2A T1-T4, T8b: the discriminated decision union and its five validators.

Two things are proven here that a shape-based union would not give:

- **Tag discrimination.** An unknown `kind` fails with `union_tag_invalid` and a missing one with
  `union_tag_not_found`, rather than a pile of per-member field errors that never say what was
  actually wrong.
- **Position is not identity.** Canonical kind order sorts `"bloc_relationship_investment"` ahead
  of `"budget"`, so on a mixed set the budget is at index 1. Every accessor test below exists
  because four production call sites used to read index 0.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.politics import RELATIONSHIP_INVESTMENT_CAP
from app.simulation.decisions import (
    BlocInvestment,
    BlocRelationshipInvestmentDecision,
    BudgetDecision,
    DecisionSet,
    bloc_relationship_investment_digest,
)


def _investment(*targets: tuple[str, str, int]) -> BlocRelationshipInvestmentDecision:
    return BlocRelationshipInvestmentDecision(
        investments=tuple(
            BlocInvestment(party_id=p, bloc_id=b, political_capital=c) for p, b, c in targets
        )
    )


def _budget() -> BudgetDecision:
    return BudgetDecision(personal_income_rate_bps=2_500)


def _set(*decisions: object) -> DecisionSet:
    return DecisionSet(decisions=tuple(decisions), expected_turn=0, expected_state_version=0)  # type: ignore[arg-type]


# --- T1: strict discriminated parsing ----------------------------------------


def test_both_kinds_round_trip_through_the_union() -> None:
    original = _set(_investment(("p", "b", 100)), _budget())
    reparsed = DecisionSet.model_validate_json(original.model_dump_json())
    assert reparsed == original
    assert [d.kind for d in reparsed.decisions] == ["bloc_relationship_investment", "budget"]


def test_an_unknown_kind_is_rejected_by_the_discriminator() -> None:
    """Asserted on the error *type*, not merely that something failed: `union_tag_invalid` is what
    tells a caller their `kind` is not a kind, rather than that some field of some member is
    missing."""
    with pytest.raises(ValidationError) as exc_info:
        DecisionSet.model_validate(
            {
                "decisions": [{"kind": "repression", "target": "x"}],
                "expected_turn": 0,
                "expected_state_version": 0,
            }
        )
    assert {e["type"] for e in exc_info.value.errors()} == {"union_tag_invalid"}


def test_a_missing_kind_is_rejected_by_the_discriminator() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DecisionSet.model_validate(
            {
                "decisions": [{"personal_income_rate_bps": 2500}],
                "expected_turn": 0,
                "expected_state_version": 0,
            }
        )
    assert {e["type"] for e in exc_info.value.errors()} == {"union_tag_not_found"}


def test_the_two_variants_do_not_structurally_overlap() -> None:
    """A budget payload carrying `investments`, or an investment payload carrying a rate, is
    rejected by `extra="forbid"` — so even setting the tag aside, no payload validates as both."""
    with pytest.raises(ValidationError):
        BudgetDecision.model_validate(
            {"kind": "budget", "personal_income_rate_bps": 2500, "investments": []}
        )
    with pytest.raises(ValidationError):
        BlocRelationshipInvestmentDecision.model_validate(
            {
                "kind": "bloc_relationship_investment",
                "investments": [{"party_id": "p", "bloc_id": "b", "political_capital": 10}],
                "personal_income_rate_bps": 2500,
            }
        )


def test_the_budget_tag_value_is_unchanged_from_phase_2a() -> None:
    """Every already-serialised decision payload parses identically under the union. Old saves are
    still refused — by the version policy at the envelope, not by the schema."""
    assert _budget().kind == "budget"


# --- T2: canonical ordering, both levels -------------------------------------


def test_investment_targets_must_be_in_canonical_order() -> None:
    with pytest.raises(ValidationError, match="sorted ascending by"):
        _investment(("z_party", "b", 10), ("a_party", "b", 10))


def test_decisions_must_be_in_canonical_kind_order() -> None:
    """Tuple order is serialised into `decisions_json` and hash-covered, so two semantically
    identical sets in different orders would digest differently."""
    with pytest.raises(ValidationError, match="sorted ascending by kind"):
        _set(_budget(), _investment(("p", "b", 100)))


def test_canonical_kind_order_puts_the_investment_first() -> None:
    """The fact that makes positional access wrong. Stated as its own assertion so the reason the
    accessors exist is visible without reading the production code."""
    assert "bloc_relationship_investment" < "budget"
    mixed = _set(_investment(("p", "b", 100)), _budget())
    assert mixed.decisions[0].kind == "bloc_relationship_investment"
    assert mixed.decisions[1].kind == "budget"


# --- T3: duplicate rejection, and validator ordering -------------------------


def test_duplicate_investment_targets_are_rejected() -> None:
    with pytest.raises(ValidationError, match="same \\(party_id, bloc_id\\) twice"):
        _investment(("p", "b", 10), ("p", "b", 20))


def test_a_noncanonical_duplicate_is_reported_as_ordering_not_duplication() -> None:
    """Proves the ordering validator runs first. Both faults are present; the message names the
    one a caller can act on without guessing which check tripped."""
    with pytest.raises(ValidationError, match="sorted ascending by"):
        _investment(("p", "z", 10), ("p", "a", 10), ("p", "z", 20))


# --- T4: the ten-case cardinality table --------------------------------------


def test_one_budget_only_is_accepted() -> None:
    decisions = _set(_budget())
    assert decisions.budget_decision() is not None
    assert decisions.relationship_investment_decision() is None


def test_one_investment_only_is_accepted() -> None:
    decisions = _set(_investment(("p", "b", 100)))
    assert decisions.budget_decision() is None
    assert decisions.relationship_investment_decision() is not None


def test_one_of_each_is_accepted() -> None:
    """The regression the Phase 3B1 `len(self.decisions) > 1` count would have caused: it would
    have rejected the central new combination this phase exists to allow."""
    decisions = _set(_investment(("p", "b", 100)), _budget())
    assert decisions.budget_decision() is not None
    assert decisions.relationship_investment_decision() is not None


def test_two_budgets_are_rejected() -> None:
    with pytest.raises(ValidationError, match="at most one budget decision"):
        _set(_budget(), _budget())


def test_two_investment_actions_are_rejected() -> None:
    with pytest.raises(ValidationError, match="at most one bloc-relationship-investment"):
        _set(_investment(("p", "b", 100)), _investment(("q", "b", 100)))


def test_an_empty_decision_set_remains_valid() -> None:
    """ "Do nothing this turn" is still expressed by submitting nothing, exactly as before."""
    decisions = _set()
    assert decisions.decisions == ()
    assert decisions.budget_decision() is None
    assert decisions.relationship_investment_decision() is None


# --- the accessors themselves ------------------------------------------------


def test_the_accessors_locate_by_kind_not_by_position() -> None:
    """The proof that matters: on a mixed set, `budget_decision()` returns the budget even though
    the budget is *not* first."""
    budget = _budget()
    investment = _investment(("p", "b", 100))
    decisions = _set(investment, budget)

    assert decisions.decisions[0] is investment
    assert decisions.budget_decision() is budget
    assert decisions.relationship_investment_decision() is investment


# --- T8b: the investment bound -----------------------------------------------


@pytest.mark.parametrize(
    ("capital", "accepted"),
    [
        pytest.param(0, False, id="zero-rejected"),
        pytest.param(1, True, id="one-accepted"),
        pytest.param(RELATIONSHIP_INVESTMENT_CAP, True, id="cap-accepted"),
        pytest.param(RELATIONSHIP_INVESTMENT_CAP + 1, False, id="over-cap-rejected"),
        pytest.param(500, False, id="far-over-cap-rejected"),
    ],
)
def test_investment_capital_boundaries(capital: int, accepted: bool) -> None:
    if accepted:
        assert _investment(("p", "b", capital)).investments[0].political_capital == capital
    else:
        with pytest.raises(ValidationError):
            _investment(("p", "b", capital))


def test_an_investment_action_must_carry_at_least_one_target() -> None:
    """An action that invests in nobody is malformed, not a smaller action — the same rule
    `BudgetDecision._require_at_least_one_target` applies to an empty budget."""
    with pytest.raises(ValidationError):
        BlocRelationshipInvestmentDecision(investments=())


# --- provenance ---------------------------------------------------------------


def test_the_investment_digest_covers_every_field() -> None:
    base = _investment(("p", "b", 100))
    assert bloc_relationship_investment_digest(base) == bloc_relationship_investment_digest(
        _investment(("p", "b", 100))
    )
    assert bloc_relationship_investment_digest(base) != bloc_relationship_investment_digest(
        _investment(("p", "b", 101))
    )
    assert bloc_relationship_investment_digest(base) != bloc_relationship_investment_digest(
        _investment(("p", "c", 100))
    )
    assert bloc_relationship_investment_digest(base) != bloc_relationship_investment_digest(
        _investment(("q", "b", 100))
    )
    assert bloc_relationship_investment_digest(base) != bloc_relationship_investment_digest(
        _investment(("p", "b", 100), ("p", "c", 50))
    )


def test_the_investment_digest_is_a_lowercase_hex_sha() -> None:
    digest = bloc_relationship_investment_digest(_investment(("p", "b", 100)))
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)
