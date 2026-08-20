"""Gate 4A1: the mutation boundary, revision protection, and atomicity.

The load-bearing test is `test_a_second_resolve_is_refused_while_the_first_is_in
_flight`, which proves refusal with a **real overlap**: request A is genuinely
in flight, paused at a test-controlled barrier *after* it gained admission, and
request B is submitted while A is provably still holding the boundary.

There are no sleeps and no timing guesses anywhere in this file. Concurrency is
driven through `httpx.AsyncClient` over `ASGITransport` in a single event loop
started by `asyncio.run`, so no `pytest-asyncio` plugin is needed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.main import ApiSettings, create_app
from app.api.session import GameSession, MutationBarrier, SessionBusyError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"


def _build_app(tmp_path: Path) -> FastAPI:
    return create_app(
        ApiSettings(save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, serve_spa=False)
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(_build_app(tmp_path), base_url="http://127.0.0.1:8420") as test_client:
        yield test_client


def _new_game(client: TestClient) -> str:
    response = client.post("/api/game/new", json={"scenario_id": "decree_state"})
    assert response.status_code == 200, response.text
    revision: str = response.json()["revision"]
    return revision


def _session_of(app: FastAPI) -> GameSession:
    session: GameSession = app.state.session
    return session


def _run(coroutine: Callable[[], Awaitable[Any]]) -> Any:
    return asyncio.run(coroutine())


# --------------------------------------------------------------------------
# The boundary itself
# --------------------------------------------------------------------------


def test_admission_is_exclusive_and_never_queues() -> None:
    async def scenario() -> None:
        from app.api.session import MutationBoundary

        boundary = MutationBoundary()
        entered = asyncio.Event()
        release = asyncio.Event()
        refusals: list[str] = []

        async def holder() -> None:
            async with boundary.admit("resolution"):
                entered.set()
                await release.wait()

        task = asyncio.create_task(holder())
        await entered.wait()

        assert boundary.busy is True
        with pytest.raises(SessionBusyError):
            async with boundary.admit("resolution"):
                refusals.append("should never run")

        release.set()
        await task
        assert refusals == []
        assert boundary.busy is False

        # And the boundary is reusable immediately afterwards.
        async with boundary.admit("resolution"):
            pass

    _run(scenario)


@pytest.mark.parametrize("failure", [ValueError("boom"), asyncio.CancelledError()])
def test_the_boundary_is_released_on_every_failure_including_cancellation(
    failure: BaseException,
) -> None:
    """`finally` runs for BaseException, so a cancelled request cannot wedge it."""

    async def scenario() -> None:
        from app.api.session import MutationBoundary

        boundary = MutationBoundary()
        with pytest.raises(type(failure)):
            async with boundary.admit("resolution"):
                raise failure

        assert boundary.busy is False
        async with boundary.admit("resolution"):
            pass

    _run(scenario)


# --------------------------------------------------------------------------
# Real overlap through the ASGI app
# --------------------------------------------------------------------------


def test_a_second_resolve_is_refused_while_the_first_is_in_flight(tmp_path: Path) -> None:
    """Two genuine concurrent requests, deterministically overlapped.

    A is held at a barrier reached only after it has gained admission, so when B
    is submitted the boundary is provably occupied. B must be refused
    immediately -- not queued behind A -- and A must then complete exactly once.
    """
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            assert created.status_code == 200
            revision = created.json()["revision"]

            session = _session_of(app)
            before = session.current_save
            barrier = MutationBarrier.create()
            session.barrier = barrier

            first = asyncio.create_task(
                client.post("/api/game/resolve", json={"revision": revision, "decisions": []})
            )
            await barrier.reached.wait()  # A is admitted and paused -- no sleep involved.

            second = await client.post(
                "/api/game/resolve", json={"revision": revision, "decisions": []}
            )
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False, "the winner must still be in flight"

            barrier.release.set()
            session.barrier = None
            first_response = await first

            assert first_response.status_code == 200
            after = session.current_save
            assert len(after.entries) == len(before.entries) + 1, "exactly one history entry"
            assert after.current_turn() == before.current_turn() + 1, "exactly one turn"
            assert session.boundary.busy is False, "the boundary is clear afterwards"

            # Exactly one authoritative save on disk, carrying the new head.
            saves = sorted((tmp_path / "saves").glob("*.json"))
            assert [path.name for path in saves if path.name != "index.json"] == [
                f"{session.save_id}.json"
            ]
            stored = json.loads((tmp_path / "saves" / f"{session.save_id}.json").read_text())
            assert stored["head_entry_hash"] == after.head_entry_hash

            # The loser's ORIGINAL revision is now stale -- a different 409.
            late = await client.post(
                "/api/game/resolve", json={"revision": revision, "decisions": []}
            )
            assert late.status_code == 409
            assert late.json()["type"] == "stale_revision"

    _run(scenario)


# --------------------------------------------------------------------------
# Cross-operation overlap: one boundary guards new/load/save-as/resolve
# together, not just resolve-vs-resolve. Each pair below overlaps a REAL
# in-flight request (paused at the barrier after admission) against a second
# request of a different kind, proving the second is refused immediately,
# that the winner completes exactly once, and that a retry afterward
# succeeds. `create_game` and `load_game` call `session.wait_at_barrier()` in
# the same position `resolve` does, which is what makes the load-vs-resolve
# and new-vs-resolve directions provable the same deterministic way.
# --------------------------------------------------------------------------


def test_a_new_game_is_refused_while_a_resolve_is_in_flight(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]

            session = _session_of(app)
            active_id_before = session.save_id
            history_len_before = len(session.current_save.entries)

            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/resolve", json={"revision": revision, "decisions": []})
            )
            await barrier.reached.wait()

            second = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False, "the winner must still be in flight"

            # No partial save from the refused /new: still exactly one file, the
            # original active save, untouched.
            saves = sorted(
                path.name
                for path in (tmp_path / "saves").glob("*.json")
                if path.name != "index.json"
            )
            assert saves == [f"{active_id_before}.json"]
            assert session.save_id == active_id_before, "not swapped mid-flight"

            barrier.release.set()
            session.barrier = None
            first_response = await first

            assert first_response.status_code == 200
            assert session.save_id == active_id_before, "resolve keeps the same save id"
            assert len(session.current_save.entries) == history_len_before + 1, (
                "exactly one history entry -- no lost update, no double-advance"
            )

            # The previously refused /new now succeeds.
            retry = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            assert retry.status_code == 200
            assert session.save_id != active_id_before, "new game swapped in a fresh save id"
            saves_after = sorted(
                path.name
                for path in (tmp_path / "saves").glob("*.json")
                if path.name != "index.json"
            )
            assert f"{session.save_id}.json" in saves_after

    _run(scenario)


def test_a_load_is_refused_while_a_resolve_is_in_flight(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]
            checkpoint = await client.post("/api/game/save-as", json={"display_name": "checkpoint"})
            checkpoint_id = checkpoint.json()["save_id"]

            session = _session_of(app)
            active_id_before = session.save_id
            save_obj_before = session.current_save

            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/resolve", json={"revision": revision, "decisions": []})
            )
            await barrier.reached.wait()

            second = await client.post("/api/game/load", json={"save_id": checkpoint_id})
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False
            assert session.current_save is save_obj_before, "the paused resolve has not swapped yet"
            assert session.save_id == active_id_before

            barrier.release.set()
            session.barrier = None
            first_response = await first

            assert first_response.status_code == 200
            assert session.save_id == active_id_before, "resolve completed under the original id"
            assert session.current_save is not save_obj_before, "exactly one swap -- the resolve's"

            # The previously refused load now succeeds and correctly replaces the session.
            retry = await client.post("/api/game/load", json={"save_id": checkpoint_id})
            assert retry.status_code == 200
            assert session.save_id == checkpoint_id
            stored = json.loads((tmp_path / "saves" / f"{checkpoint_id}.json").read_bytes())
            assert stored["head_entry_hash"] == session.current_save.head_entry_hash

    _run(scenario)


def test_a_save_as_is_refused_while_a_resolve_is_in_flight(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]

            session = _session_of(app)
            active_id_before = session.save_id

            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/resolve", json={"revision": revision, "decisions": []})
            )
            await barrier.reached.wait()

            second = await client.post("/api/game/save-as", json={"display_name": "mid-flight"})
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False

            # No checkpoint file leaked from the refused Save As.
            saves = sorted(
                path.name
                for path in (tmp_path / "saves").glob("*.json")
                if path.name != "index.json"
            )
            assert saves == [f"{active_id_before}.json"]

            barrier.release.set()
            session.barrier = None
            first_response = await first
            assert first_response.status_code == 200
            assert session.save_id == active_id_before

            retry = await client.post("/api/game/save-as", json={"display_name": "after resolve"})
            assert retry.status_code == 200
            checkpoint_id = retry.json()["save_id"]
            assert checkpoint_id != active_id_before
            saves_after = sorted(
                path.name
                for path in (tmp_path / "saves").glob("*.json")
                if path.name != "index.json"
            )
            assert set(saves_after) == {f"{active_id_before}.json", f"{checkpoint_id}.json"}

    _run(scenario)


def test_a_resolve_is_refused_while_a_load_is_in_flight(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]
            checkpoint = await client.post("/api/game/save-as", json={"display_name": "checkpoint"})
            checkpoint_id = checkpoint.json()["save_id"]

            session = _session_of(app)
            active_id_before = session.save_id
            save_obj_before = session.current_save

            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/load", json={"save_id": checkpoint_id})
            )
            await barrier.reached.wait()

            second = await client.post(
                "/api/game/resolve", json={"revision": revision, "decisions": []}
            )
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False
            assert session.current_save is save_obj_before, "still the pre-load save"
            assert session.save_id == active_id_before

            barrier.release.set()
            session.barrier = None
            first_response = await first

            assert first_response.status_code == 200
            assert session.save_id == checkpoint_id, "the load completed and swapped the id"
            loaded_save_obj = session.current_save
            assert loaded_save_obj is not save_obj_before

            # The checkpoint carries the same opening revision the refused resolve
            # was submitted against, so the retry can now succeed against it.
            retry = await client.post(
                "/api/game/resolve", json={"revision": revision, "decisions": []}
            )
            assert retry.status_code == 200
            assert session.save_id == checkpoint_id, "resolve advanced the now-active loaded save"
            assert session.current_save is not loaded_save_obj

    _run(scenario)


def test_a_resolve_is_refused_while_a_new_game_is_in_flight(tmp_path: Path) -> None:
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]

            session = _session_of(app)
            active_id_before = session.save_id
            save_obj_before = session.current_save

            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/new", json={"scenario_id": "decree_state"})
            )
            await barrier.reached.wait()

            second = await client.post(
                "/api/game/resolve", json={"revision": revision, "decisions": []}
            )
            assert second.status_code == 409
            assert second.json()["type"] == "resolution_in_progress"
            assert first.done() is False
            assert session.save_id == active_id_before
            assert session.current_save is save_obj_before, "the paused /new has not swapped yet"

            barrier.release.set()
            session.barrier = None
            first_response = await first

            assert first_response.status_code == 200
            assert session.save_id != active_id_before, "the second new game swapped in a fresh id"
            new_revision = first_response.json()["revision"]
            assert new_revision == "0.0"

            retry = await client.post(
                "/api/game/resolve", json={"revision": new_revision, "decisions": []}
            )
            assert retry.status_code == 200

    _run(scenario)


def test_read_only_and_preview_requests_stay_coherent_during_a_paused_resolve(
    tmp_path: Path,
) -> None:
    """A capture, never a mixture, of pre- vs. post-resolve state.

    Reads issued while a resolve is admitted but still paused before persistence
    must see the complete PRE-resolve revision -- proving `/state` and
    `/preview` each capture `session.current_save` once, the same discipline the
    mutation boundary enforces for the mutating endpoints.
    """
    app = _build_app(tmp_path)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8420"
        ) as client:
            created = await client.post("/api/game/new", json={"scenario_id": "decree_state"})
            revision = created.json()["revision"]

            session = _session_of(app)
            barrier = MutationBarrier.create()
            session.barrier = barrier
            first = asyncio.create_task(
                client.post("/api/game/resolve", json={"revision": revision, "decisions": []})
            )
            await barrier.reached.wait()

            mid_state = await client.get("/api/game/state")
            assert mid_state.status_code == 200
            assert mid_state.json()["revision"] == revision

            mid_preview = await client.post(
                "/api/game/preview", json={"revision": revision, "decisions": []}
            )
            assert mid_preview.status_code == 200

            barrier.release.set()
            session.barrier = None
            first_response = await first
            assert first_response.status_code == 200

            after_state = await client.get("/api/game/state")
            assert after_state.json()["revision"] != revision, "the resolve has now advanced it"

    _run(scenario)


# --------------------------------------------------------------------------
# Release-on-failure for /new, /load, /save-as specifically
# --------------------------------------------------------------------------


def test_the_boundary_is_released_after_a_rejected_new_game(client: TestClient) -> None:
    response = client.post("/api/game/new", json={"scenario_id": "not_a_real_scenario"})
    assert response.status_code in (400, 404)

    retry = client.post("/api/game/new", json={"scenario_id": "decree_state"})
    assert retry.status_code == 200


def test_the_boundary_is_released_after_a_rejected_load(client: TestClient) -> None:
    _new_game(client)

    response = client.post(
        "/api/game/load", json={"save_id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    assert response.status_code == 404

    save_id = client.get("/api/saves").json()[0]["save_id"]
    retry = client.post("/api/game/load", json={"save_id": save_id})
    assert retry.status_code == 200


def test_the_boundary_is_released_after_a_rejected_save_as(client: TestClient) -> None:
    _new_game(client)

    response = client.post("/api/game/save-as", json={"display_name": ""})
    assert response.status_code == 422

    retry = client.post("/api/game/save-as", json={"display_name": "valid name"})
    assert retry.status_code == 200


def test_a_failed_load_never_replaces_the_active_save(client: TestClient) -> None:
    _new_game(client)
    save_id_before = client.get("/api/saves").json()[0]["save_id"]

    response = client.post(
        "/api/game/load", json={"save_id": "550e8400-e29b-41d4-a716-446655440000"}
    )
    assert response.status_code == 404

    assert client.get("/api/game/state").json()["revision"] == "0.0"
    assert client.get("/api/saves").json()[0]["save_id"] == save_id_before


def test_a_failed_save_as_never_changes_the_active_save_id(client: TestClient) -> None:
    _new_game(client)
    active_id = client.get("/api/saves").json()[0]["save_id"]

    response = client.post("/api/game/save-as", json={"display_name": ""})
    assert response.status_code == 422

    saves_after = client.get("/api/saves").json()
    assert len(saves_after) == 1, "no checkpoint file was created by the rejected attempt"
    assert saves_after[0]["save_id"] == active_id


# --------------------------------------------------------------------------
# Revision protection
# --------------------------------------------------------------------------


def test_a_stale_revision_resolves_nothing_and_writes_nothing(
    client: TestClient, tmp_path: Path
) -> None:
    revision = _new_game(client)
    assert client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).is_success
    save_id = client.get("/api/saves").json()[0]["save_id"]
    on_disk = (tmp_path / "saves" / f"{save_id}.json").read_bytes()
    turn_before = client.get("/api/game/state").json()["turn"]

    response = client.post("/api/game/resolve", json={"revision": revision, "decisions": []})

    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "stale_revision"
    assert body["extra"]["actual"] == revision
    assert client.get("/api/game/state").json()["turn"] == turn_before
    assert (tmp_path / "saves" / f"{save_id}.json").read_bytes() == on_disk
    assert not list((tmp_path / "saves").glob("*.tmp"))


@pytest.mark.parametrize("revision", ["", "abc", "1", "1.2.3", "-1.0", "1.0extra"])
def test_a_malformed_revision_token_is_rejected(client: TestClient, revision: str) -> None:
    _new_game(client)

    response = client.post("/api/game/resolve", json={"revision": revision, "decisions": []})

    assert response.status_code == 422
    assert response.json()["type"] == "decision_rejected"


def test_the_revision_advances_by_exactly_one_turn(client: TestClient) -> None:
    revision = _new_game(client)
    assert revision == "0.0"

    body = client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).json()

    assert body["turnResult"]["revision"] == "1.1"
    assert body["dashboard"]["revision"] == "1.1"
    assert body["turnResult"]["turn"] == 1


def test_resolve_returns_both_shapes_and_they_agree_with_history(client: TestClient) -> None:
    revision = _new_game(client)

    body = client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).json()

    assert set(body) == {"turnResult", "dashboard"}
    historical = client.get("/api/game/history/1").json()
    assert set(historical) == {"turnResult", "dashboardAsOfTurn"}
    # The same projection type from the same builder over the same stored report.
    assert historical["turnResult"] == body["turnResult"]


# --------------------------------------------------------------------------
# Persistence atomicity
# --------------------------------------------------------------------------


def test_a_persistence_failure_leaves_disk_and_memory_unchanged(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injected failure, not a mocked assertion that a writer was called."""
    revision = _new_game(client)
    save_id = client.get("/api/saves").json()[0]["save_id"]
    path = tmp_path / "saves" / f"{save_id}.json"
    before_bytes = path.read_bytes()
    before_state = client.get("/api/game/state").json()

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.api.save_registry.write_save_atomic", explode)
    response = client.post("/api/game/resolve", json={"revision": revision, "decisions": []})

    assert response.status_code == 500
    monkeypatch.undo()
    assert path.read_bytes() == before_bytes, "the on-disk save is untouched"
    assert client.get("/api/game/state").json() == before_state, "memory is untouched"
    assert not list((tmp_path / "saves").glob("*.tmp")), "no temporary file survives"

    # And the boundary was released, so a later valid request still succeeds.
    assert client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).is_success


def test_the_boundary_is_released_after_a_rejected_decision(client: TestClient) -> None:
    revision = _new_game(client)

    rejected = client.post(
        "/api/game/resolve",
        json={"revision": revision, "decisions": [{"kind": "not_a_real_decision"}]},
    )
    assert rejected.status_code == 422

    assert client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).is_success


def test_the_boundary_is_released_after_a_stale_rejection(client: TestClient) -> None:
    revision = _new_game(client)
    client.post("/api/game/resolve", json={"revision": revision, "decisions": []})

    assert (
        client.post("/api/game/resolve", json={"revision": revision, "decisions": []}).status_code
        == 409
    )

    current = client.get("/api/game/state").json()["revision"]
    assert client.post("/api/game/resolve", json={"revision": current, "decisions": []}).is_success
