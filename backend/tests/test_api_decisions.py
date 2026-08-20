"""Gate 4A1: reject-not-normalize, preserved end to end through the real API.

The engine's own decision models already reject noncanonical order, duplicate
targets, and illegal combinations at construction (see
`test_budget_decisions.py`, `test_constitutional_amendment_decision.py`,
`test_relationship_investment_decision.py`). This file's job is narrower and
specific to the API layer: prove that `/game/resolve` and `/game/preview`
translate that SAME rejection through the SAME `pydantic.ValidationError` ->
`DecisionSetError` path, with no server-side sorting, deduplication, or
repair anywhere in between (frozen plan Sec 10.1, "canonical ordering --
client-constructed, never server-normalized"). Every malformed payload here
is deliberately submitted exactly as a bypass-the-UI attacker or a buggy
client would send it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        ApiSettings(save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, serve_spa=False)
    )
    with TestClient(app, base_url="http://127.0.0.1:8420") as test_client:
        yield test_client


def _new(client: TestClient, scenario_id: str = "decree_state") -> str:
    response = client.post("/api/game/new", json={"scenario_id": scenario_id})
    assert response.status_code == 200, response.text
    revision: str = response.json()["revision"]
    return revision


def _assert_both_reject(client: TestClient, revision: str, decisions: tuple[dict, ...]) -> None:
    """`/preview` and `/resolve` must reject the identical malformed payload
    with the identical error type -- proving the two cannot silently drift
    apart on what "invalid" means."""
    body = {"revision": revision, "decisions": list(decisions)}

    preview = client.post("/api/game/preview", json=body)
    resolve = client.post("/api/game/resolve", json=body)

    assert preview.status_code == 422, preview.text
    assert resolve.status_code == 422, resolve.text
    assert preview.json()["type"] == "decision_rejected"
    assert resolve.json()["type"] == "decision_rejected"


BLOC_A = {"party_id": "governing_party", "bloc_id": "core"}
BLOC_B = {"party_id": "opposition_party", "bloc_id": "main"}


def _budget(**overrides: Any) -> dict:
    payload: dict[str, Any] = {
        "kind": "budget",
        "spending_updates": [{"category": "health", "amount": 200_000_000}],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# Canonical kind order -- the DecisionSet level
# --------------------------------------------------------------------------


def test_noncanonical_kind_order_is_rejected_not_reordered(client: TestClient) -> None:
    """`bloc_relationship_investment` sorts before `budget`; submitting the
    reverse must be REJECTED, never silently swapped into canonical order."""
    revision = _new(client)
    investment = {
        "kind": "bloc_relationship_investment",
        "investments": [{**BLOC_A, "political_capital": 10}],
    }
    _assert_both_reject(client, revision, (_budget(), investment))


def test_canonical_kind_order_is_accepted(client: TestClient) -> None:
    revision = _new(client)
    investment = {
        "kind": "bloc_relationship_investment",
        "investments": [{**BLOC_A, "political_capital": 10}],
    }
    body = {"revision": revision, "decisions": [investment, _budget()]}

    assert client.post("/api/game/preview", json=body).status_code == 200
    assert client.post("/api/game/resolve", json=body).status_code == 200


# --------------------------------------------------------------------------
# Budget: targets, duplicates, influence order
# --------------------------------------------------------------------------


def test_an_empty_budget_decision_is_rejected(client: TestClient) -> None:
    revision = _new(client)
    _assert_both_reject(client, revision, (_budget(spending_updates=[]),))


def test_duplicate_spending_categories_are_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision = _budget(
        spending_updates=[
            {"category": "health", "amount": 200_000_000},
            {"category": "health", "amount": 210_000_000},
        ]
    )
    _assert_both_reject(client, revision, (decision,))


def test_noncanonical_influence_order_is_rejected_not_sorted(client: TestClient) -> None:
    """(opposition_party, main) sorts after (governing_party, core); reversed
    input must be rejected, never quietly re-sorted into place."""
    revision = _new(client)
    decision = _budget(
        influence=[
            {**BLOC_B, "political_capital": 5},
            {**BLOC_A, "political_capital": 5},
        ]
    )
    _assert_both_reject(client, revision, (decision,))


def test_duplicate_influence_targets_are_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision = _budget(
        influence=[
            {**BLOC_A, "political_capital": 5},
            {**BLOC_A, "political_capital": 7},
        ]
    )
    _assert_both_reject(client, revision, (decision,))


def test_canonical_influence_order_is_accepted(client: TestClient) -> None:
    revision = _new(client)
    decision = _budget(
        influence=[
            {**BLOC_A, "political_capital": 5},
            {**BLOC_B, "political_capital": 5},
        ]
    )
    body = {"revision": revision, "decisions": [decision]}

    assert client.post("/api/game/preview", json=body).status_code == 200
    assert client.post("/api/game/resolve", json=body).status_code == 200


def test_a_decree_route_with_influence_is_rejected(client: TestClient) -> None:
    """A decree is not voted on, so whipping a bloc's vote makes no sense."""
    revision = _new(client)  # decree_state grants unlimited decree authority
    decision = _budget(route="decree", influence=[{**BLOC_A, "political_capital": 5}])
    _assert_both_reject(client, revision, (decision,))


def test_a_decree_route_unavailable_to_the_constitution_is_rejected_the_same_way(
    client: TestClient,
) -> None:
    """`deficit_demo` grants only `emergency_only` -- decree must be refused
    identically by both endpoints, not merely by one of them."""
    revision = _new(client, "deficit_demo")
    decision = _budget(route="decree")
    _assert_both_reject(client, revision, (decision,))


# --------------------------------------------------------------------------
# Constitutional amendment: axis order, duplicates, empty targets
# --------------------------------------------------------------------------


def test_noncanonical_amendment_axis_order_is_rejected(client: TestClient) -> None:
    """`executive_system` sorts before `national_election_interval_turns`."""
    revision = _new(client)
    decision = {
        "kind": "constitutional_amendment",
        "targets": [
            {"axis": "national_election_interval_turns", "value": 4},
            {"axis": "executive_system", "value": "parliamentary"},
        ],
    }
    _assert_both_reject(client, revision, (decision,))


def test_duplicate_amendment_axes_are_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision = {
        "kind": "constitutional_amendment",
        "targets": [
            {"axis": "decree_authority", "value": "none"},
            {"axis": "decree_authority", "value": "emergency_only"},
        ],
    }
    _assert_both_reject(client, revision, (decision,))


def test_an_amendment_with_no_targets_is_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision: dict[str, Any] = {"kind": "constitutional_amendment", "targets": []}
    _assert_both_reject(client, revision, (decision,))


def test_a_budget_and_an_amendment_together_are_rejected(client: TestClient) -> None:
    """Mutual exclusion: budget and amendment are one policy-proposal slot."""
    revision = _new(client)
    amendment = {
        "kind": "constitutional_amendment",
        "targets": [{"axis": "executive_system", "value": "parliamentary"}],
    }
    _assert_both_reject(client, revision, (_budget(), amendment))


# --------------------------------------------------------------------------
# Relationship investment: order, duplicates, the real capital cap
# --------------------------------------------------------------------------


def test_noncanonical_investment_order_is_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision = {
        "kind": "bloc_relationship_investment",
        "investments": [
            {**BLOC_B, "political_capital": 5},
            {**BLOC_A, "political_capital": 5},
        ],
    }
    _assert_both_reject(client, revision, (decision,))


def test_duplicate_investment_targets_are_rejected(client: TestClient) -> None:
    revision = _new(client)
    decision = {
        "kind": "bloc_relationship_investment",
        "investments": [
            {**BLOC_A, "political_capital": 5},
            {**BLOC_A, "political_capital": 6},
        ],
    }
    _assert_both_reject(client, revision, (decision,))


@pytest.mark.parametrize("political_capital", [0, 201])
def test_investment_outside_the_real_1_to_200_cap_is_rejected(
    client: TestClient, political_capital: int
) -> None:
    """201 is not truncated to 200 -- it is rejected, so a player never loses
    capital they did not agree to commit."""
    revision = _new(client)
    decision = {
        "kind": "bloc_relationship_investment",
        "investments": [{**BLOC_A, "political_capital": political_capital}],
    }
    _assert_both_reject(client, revision, (decision,))


def test_investment_at_exactly_the_cap_is_accepted(client: TestClient) -> None:
    revision = _new(client)
    decision = {
        "kind": "bloc_relationship_investment",
        "investments": [{**BLOC_A, "political_capital": 200}],
    }
    body = {"revision": revision, "decisions": [decision]}

    assert client.post("/api/game/preview", json=body).status_code == 200
    assert client.post("/api/game/resolve", json=body).status_code == 200


def test_two_budget_decisions_in_one_set_are_rejected(client: TestClient) -> None:
    revision = _new(client)
    _assert_both_reject(client, revision, (_budget(), _budget()))


def test_an_unknown_decision_kind_is_rejected(client: TestClient) -> None:
    revision = _new(client)
    _assert_both_reject(client, revision, ({"kind": "not_a_real_decision_kind"},))


def test_extra_fields_on_a_decision_are_rejected(client: TestClient) -> None:
    """`extra="forbid"` end to end -- a client cannot smuggle an unmodelled field."""
    revision = _new(client)
    decision = _budget()
    decision["not_a_real_field"] = 1
    _assert_both_reject(client, revision, (decision,))


# --------------------------------------------------------------------------
# Failed votes still cost -- capital committed to a losing proposal is spent
# --------------------------------------------------------------------------


def test_a_failed_legislative_vote_still_consumes_committed_capital(client: TestClient) -> None:
    """`deficit_demo`'s opposition-controlled chamber blocks this budget, but
    the capital allocated to the losing whip attempt is still spent -- checked
    against the stored ledger, not a state diff, since capital also regenerates
    every turn and a diff would conflate the two effects."""
    revision = _new(client, "deficit_demo")
    decision = _budget(influence=[{**BLOC_A, "political_capital": 20}])

    body = client.post(
        "/api/game/resolve", json={"revision": revision, "decisions": [decision]}
    ).json()

    assert body["turnResult"]["outcome_tone"] == "negative"
    assert "still spent" in body["turnResult"]["outcome_headline"]
    ledger = next(
        row
        for row in body["turnResult"]["drivers"]
        if row["reason_id"] == "political_capital_resolved"
    )
    assert ledger["params"]["spent"] == 20
