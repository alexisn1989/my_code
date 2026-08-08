"""Phase 3B1: the legislative vocabulary's values and ordering are part of the save format.

Every enum here is serialised into `state_json`/`report_json` and therefore into `entry_hash`.
Renaming a value is a save-breaking change, and reordering `LegislativeChamber` silently changes
what "canonical order" means for every seat tuple. Both are pinned.
"""

from __future__ import annotations

from app.simulation.legislature import (
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
