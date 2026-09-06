"""A revision token belongs to a campaign, and must not be honoured against a different one.

Freshness was validated on `(turn, state_version)` alone, which says WHEN a client's view was
taken but not WHAT it was a view of. Two campaigns at the same turn produce the same token, so a
tab left open on campaign A could advance campaign B -- returning 200, and corrupting the wrong
game.

The identity is `GameSession.save_id`, which already existed with exactly the right lifecycle. The
first class below proves that lifecycle rather than assuming it, because everything else here
rests on it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app
from app.api.session import GameSession

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(
        ApiSettings(save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, serve_spa=False)
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8420") as test_client:
        yield test_client


def _session_of(app: FastAPI) -> GameSession:
    session: GameSession = app.state.session
    return session


def _new_game(client: TestClient, scenario_id: str = "decree_state") -> dict:
    response = client.post("/api/game/new", json={"scenario_id": scenario_id})
    assert response.status_code == 200, response.text
    return response.json()


class TestSaveIdIsAValidCampaignIdentity:
    """`GameSession.save_id` must be stable for the life of one campaign and different across
    campaigns. If either half failed, it would be the wrong thing to identify a campaign with."""

    def test_it_survives_a_resolve(self, app: FastAPI, client: TestClient) -> None:
        dashboard = _new_game(client)
        before = _session_of(app).save_id

        response = _submit(client, dashboard, "resolve")
        assert response.status_code == 200, response.text

        assert _session_of(app).save_id == before

    def test_it_survives_a_save_as(self, app: FastAPI, client: TestClient) -> None:
        """Checkpointing under a new name writes a new FILE; it does not start a new campaign, and
        `save_as` deliberately never calls `adopt`."""
        _new_game(client)
        before = _session_of(app).save_id

        response = client.post("/api/game/save-as", json={"display_name": "A checkpoint"})
        assert response.status_code == 200, response.text

        assert _session_of(app).save_id == before

    def test_a_second_new_game_gets_a_different_identity(
        self, app: FastAPI, client: TestClient
    ) -> None:
        _new_game(client)
        first = _session_of(app).save_id

        _new_game(client)

        assert _session_of(app).save_id != first

    def test_loading_a_different_save_changes_the_identity(
        self, app: FastAPI, client: TestClient
    ) -> None:
        _new_game(client)
        first = _session_of(app).save_id
        saved = client.post("/api/game/save-as", json={"display_name": "Keep me"})
        assert saved.status_code == 200, saved.text
        checkpoint_id = saved.json()["save_id"]
        _new_game(client)
        assert _session_of(app).save_id != first

        response = client.post("/api/game/load", json={"save_id": checkpoint_id})
        assert response.status_code == 200, response.text

        assert _session_of(app).save_id == checkpoint_id


def _submit(client: TestClient, view: dict, endpoint: str) -> object:
    """Post to `/resolve` or `/preview` echoing back exactly what `view` carried.

    `campaign_id` is included only when the view actually has one, so this same helper reproduces
    the defect against the pre-fix server (which issued no campaign id and accepted the request)
    and exercises the fix afterwards.
    """
    body: dict[str, object] = {"revision": view["revision"], "decisions": []}
    if "campaign_id" in view:
        body["campaign_id"] = view["campaign_id"]
    return client.post(f"/api/game/{endpoint}", json=body)


class TestARevisionFromAnotherCampaignIsRejected:
    """The defect: `(turn, state_version)` says WHEN a view was taken, never WHAT of.

    Both campaigns below sit at turn 0 with state version 0, so their revision tokens are
    identical strings. Only the campaign identity can tell them apart.
    """

    @pytest.mark.parametrize("endpoint", ["resolve", "preview"])
    def test_a_stale_tab_cannot_act_on_the_replacement_campaign(
        self, client: TestClient, endpoint: str
    ) -> None:
        campaign_a = _new_game(client)
        campaign_b = _new_game(client)
        assert campaign_a["revision"] == campaign_b["revision"], (
            "both campaigns must sit at the same turn for this to test identity, not counters"
        )

        response = _submit(client, campaign_a, endpoint)

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["type"] == "stale_revision"
        # The two causes of this status stay distinguishable: the message names what did not
        # match, and `extra` carries the two campaign ids rather than two revision tokens.
        assert "campaign" in body["detail"]
        assert body["extra"]["actual"] == campaign_a["campaign_id"]
        assert body["extra"]["expected"] == campaign_b["campaign_id"]

    @pytest.mark.parametrize("endpoint", ["resolve", "preview"])
    def test_the_live_campaign_is_still_accepted(self, client: TestClient, endpoint: str) -> None:
        """The other half of the statement: the check must reject a foreign campaign without
        rejecting the real one."""
        _new_game(client)
        campaign_b = _new_game(client)

        response = _submit(client, campaign_b, endpoint)

        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("endpoint", ["resolve", "preview"])
    def test_a_request_without_a_campaign_is_refused_rather_than_waved_through(
        self, client: TestClient, endpoint: str
    ) -> None:
        """Fail closed. An omitted campaign that defaulted to "skip the check" would reintroduce
        the defect in a form that passes every other test in this file."""
        dashboard = _new_game(client)

        response = client.post(
            f"/api/game/{endpoint}", json={"revision": dashboard["revision"], "decisions": []}
        )

        assert response.status_code == 422, response.text

    def test_the_counter_check_still_runs_alongside_the_campaign_check(
        self, client: TestClient
    ) -> None:
        """The campaign check is added to the freshness comparison, never substituted for it: a
        stale revision within the RIGHT campaign must still be refused (ADR 0014)."""
        dashboard = _new_game(client)
        first = _submit(client, dashboard, "resolve")
        assert first.status_code == 200, first.text

        replayed = _submit(client, dashboard, "resolve")

        assert replayed.status_code == 409, replayed.text
        assert replayed.json()["type"] == "stale_revision"
