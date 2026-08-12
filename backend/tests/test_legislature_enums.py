"""Phase 3B1: the legislative vocabulary's values and ordering are part of the save format.

Every enum here is serialised into `state_json`/`report_json` and therefore into `entry_hash`.
Renaming a value is a save-breaking change, and reordering `LegislativeChamber` silently changes
what "canonical order" means for every seat tuple. Both are pinned.
"""

from __future__ import annotations

from app.simulation.legislature import (
    CapitalExpenditureCategory,
    ChangeDirection,
    GovernmentRole,
    LegislativeChamber,
    LegislativeOutcome,
    ProposalRoute,
)


def test_chamber_values_and_declaration_order_are_stable() -> None:
    assert [c.value for c in LegislativeChamber] == ["lower", "upper"]


def test_government_role_values_are_stable() -> None:
    assert [r.value for r in GovernmentRole] == [
        "coalition",
        "confidence_and_supply",
        "opposition",
    ]


def test_proposal_route_values_are_stable() -> None:
    assert [r.value for r in ProposalRoute] == ["legislative", "decree"]


def test_change_direction_values_are_stable() -> None:
    assert [d.value for d in ChangeDirection] == ["decrease", "unchanged", "increase"]


def test_legislative_outcome_values_are_stable() -> None:
    assert [o.value for o in LegislativeOutcome] == [
        "no_proposal",
        "passed_legislative",
        "failed_legislative",
        "enacted_by_decree",
    ]


def test_there_is_no_route_unavailable_outcome() -> None:
    """(R5) An unavailable decree route aborts the turn; it is never a reported outcome.

    Pinned as its own test because re-adding the member is exactly the regression that would turn
    an invalid command back into a silently completed turn.
    """
    values = {o.value for o in LegislativeOutcome}
    assert "route_unavailable" not in values
    assert not hasattr(LegislativeOutcome, "ROUTE_UNAVAILABLE")


def test_every_outcome_describes_a_completed_turn() -> None:
    assert len(LegislativeOutcome) == 4


# --- Phase 3B2A: the capital-expenditure ledger's category -------------------


def test_capital_expenditure_category_values_and_declaration_order_are_stable() -> None:
    """Serialised into `report_json` and therefore hash-covered: renaming a value or reordering the
    members changes every entry hash in every save that carries a ledger."""
    assert [category.value for category in CapitalExpenditureCategory] == [
        "bloc_relationship_investment",
        "decree",
        "legislative_influence",
    ]


def test_capital_expenditure_category_values_are_alphabetical() -> None:
    """Why this matters rather than being a tidiness preference: the ledger's canonical sort key is
    `(category, party_id, bloc_id)`. Because the values are already alphabetical, "declaration
    order" and "sorted by value" are the same order, so there is no second convention a reader (or
    a future validator) can get wrong."""
    values = [category.value for category in CapitalExpenditureCategory]
    assert values == sorted(values)


def test_only_one_category_is_untargeted() -> None:
    """A decree is an act of the executive with no bloc on the other side of it; every other
    category names the bloc whose support or relationship was bought. `report`'s target-shape
    validator encodes exactly this split, and it is pinned here so the two cannot drift."""
    assert CapitalExpenditureCategory.DECREE.value == "decree"
    targeted = set(CapitalExpenditureCategory) - {CapitalExpenditureCategory.DECREE}
    assert {category.value for category in targeted} == {
        "bloc_relationship_investment",
        "legislative_influence",
    }
