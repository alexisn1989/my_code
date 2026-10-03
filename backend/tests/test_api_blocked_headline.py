"""Gate 4A3 UX-2 (U6): a blocked budget's headline agrees with the turn's own ledger.

The headline used to read "The budget was blocked. Committed capital was still spent." even when
nothing was committed -- directly above a ledger saying "Nothing was committed this turn." The clause
is now stated only when capital was committed TOWARD THE VOTE (bloc influence or a leader's bargain).
Each case resolves a real Kingdom of Valdrun turn whose budget the legislature blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.test_api_preview_parity import _budget, _make_client, _new, _resolve

SPENT_CLAUSE = "Committed capital was still spent."


def _blocked_turn(tmp_path: Path, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    with _make_client(tmp_path) as client:
        resolved = _resolve(client, _new(client, "decree_state"), decisions)
    assert resolved.status_code == 200, resolved.text
    turn_result: dict[str, Any] = resolved.json()["turnResult"]
    assert turn_result["outcome_headline"].startswith("The budget was blocked."), (
        "the precondition: this budget really is blocked in Valdrun"
    )
    return turn_result


def test_a_blocked_budget_with_nothing_committed_does_not_claim_capital_was_spent(
    tmp_path: Path,
) -> None:
    result = _blocked_turn(tmp_path, [_budget()])
    assert result["ledger"] == []
    assert result["outcome_headline"] == "The budget was blocked."


def test_a_blocked_budget_with_influence_spent_says_so(tmp_path: Path) -> None:
    influence = [{"party_id": "opposition_party", "bloc_id": "main", "political_capital": 10}]
    result = _blocked_turn(tmp_path, [_budget(influence=influence)])
    assert result["ledger"], "the influence is in the ledger"
    assert result["outcome_headline"] == f"The budget was blocked. {SPENT_CLAUSE}"


def test_a_relationship_investment_alone_is_not_spending_on_the_vote(tmp_path: Path) -> None:
    investment = {
        "kind": "bloc_relationship_investment",
        "investments": [
            {"party_id": "opposition_party", "bloc_id": "main", "political_capital": 20}
        ],
    }
    result = _blocked_turn(tmp_path, [investment, _budget()])
    assert result["ledger"], "the investment is in the ledger"
    assert result["outcome_headline"] == "The budget was blocked."
