"""Gate 4A3 R1 fix: the listing memo is seeded by `SaveRepository.write_save` (option (a)).

Every resolve and save-as writes a save and then lists saves in the same request; before this fix
each turn paid one full `validate_history` of the campaign it had just written. `write_save` now
reads the file back and, when the bytes on disk are exactly the bytes it serialized, stores the
verdict for that key itself -- with `problems=()` asserted from provenance rather than computed.

What these tests pin:

1. EQUIVALENCE -- the seeded verdict equals `_compute_verdict` on the same bytes, field for field,
   for each shipped scenario at several lengths and for a CONCLUDED campaign. This is the guard on
   the asserted `problems=()`.
2. a listing after a write does not re-validate that save; an unseeded file still is;
3. changed or tampered bytes are a new key and are validated (and a tampered one is listed with its
   problem);
4. a read-back mismatch, or a failed read-back, seeds nothing -- and the write itself succeeded;
5. the memo bound and an existing entry are respected;
6. through the API: the LISTING validates nothing the server wrote, while the engine's own
   `advance_game` check still runs exactly once per resolve;
7. load still validates in full and refuses a tampered save;
8. a fresh repository (a restart) validates every save once, as before.

Every save is made through the production path (`new_game` / `advance_game` / `write_save`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import save_registry
from app.api.main import ApiSettings, create_app
from app.api.save_registry import VALIDATION_MEMO_MAX, SaveRepository, new_save_id
from app.content.scenarios import load_scenario_file
from app.core.errors import GameAlreadyConcludedError, SaveFileError
from app.simulation import history as history_module
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION
from tests.conftest import SCENARIO_DIR

SCENARIOS = ("decree_state", "deficit_demo", "tiny_valid")
LENGTHS = (0, 1, 5, 20)


def _empty(save: GameSave) -> DecisionSet:
    state = save.current_state()
    return DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)


def _campaign(scenario: str, turns: int, *, seed: int | None = None) -> GameSave:
    state = load_scenario_file(SCENARIO_DIR / f"{scenario}.yaml")
    if seed is not None:
        state = state.model_copy(update={"seed": seed})
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(turns):
        save = advance_game(save, _empty(save))
    return save


def _concluded_campaign() -> GameSave:
    """`tiny_valid` always concludes by turn 32 (an electoral defeat at its turn-16 election, or the
    term-limit exit at 32), so running it to the engine's refusal yields a concluded save."""
    save = _campaign("tiny_valid", 0, seed=0)
    for _ in range(40):
        try:
            save = advance_game(save, _empty(save))
        except GameAlreadyConcludedError:
            break
    assert (
        save.current_state()
        .world.countries[save.current_state().world.player_country_id]
        .politics.terminal_outcome
        is not None
    )  # type: ignore[union-attr]
    return save


def _key(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Counter:
    """Wrap a module-level function and count calls."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> None:
        self.calls = 0
        real: Callable[..., Any] = getattr(module, name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, counted)


# ------------------------------------------------------------------ 1. equivalence


@pytest.mark.parametrize("turns", LENGTHS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_seeded_verdict_equals_the_computed_one(
    scenario: str, turns: int, tmp_path: Path
) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _campaign(scenario, turns))
    path = repository.path_for(save_id)
    seeded = repository._memo[_key(path)]
    computed = repository._compute_verdict(path.read_bytes(), path, save_id)
    assert seeded == computed
    assert seeded.problems == ()


def test_the_seeded_verdict_equals_the_computed_one_for_a_concluded_campaign(
    tmp_path: Path,
) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _concluded_campaign())
    path = repository.path_for(save_id)
    seeded = repository._memo[_key(path)]
    assert seeded == repository._compute_verdict(path.read_bytes(), path, save_id)
    assert seeded.terminal_summary is not None


# ------------------------------------------------------------------ 2. no re-validation after a write


def test_a_listing_after_a_write_does_not_revalidate_that_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = SaveRepository(tmp_path)
    # An UNSEEDED file in the same root: written by a different repository, so this one never saw it.
    other_id = new_save_id()
    SaveRepository(tmp_path).write_save(other_id, _campaign("decree_state", 1))
    written_id = new_save_id()
    writer.write_save(written_id, _campaign("decree_state", 2))

    validations = Counter(monkeypatch, save_registry, "validate_history")
    records = {record.save_id: record for record in writer.list_saves()}
    assert validations.calls == 1, "only the unseeded file is validated"
    assert records[written_id].loadable and records[other_id].loadable

    writer.list_saves()
    assert validations.calls == 1, "and neither is validated again"


# ------------------------------------------------------------------ 3. changed bytes are a new key


def test_bytes_changed_on_disk_after_a_write_are_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _campaign("decree_state", 1))
    path = repository.path_for(save_id)
    # Different, valid bytes written behind the repository's back.
    path.write_bytes(save_registry.dump_save_json(_campaign("decree_state", 2)).encode("utf-8"))

    validations = Counter(monkeypatch, save_registry, "validate_history")
    (record,) = repository.list_saves()
    assert validations.calls == 1
    assert record.loadable and record.current_turn == 2


def test_tampered_bytes_after_a_write_are_listed_with_their_problem(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _campaign("decree_state", 2))
    path = repository.path_for(save_id)
    text = path.read_text(encoding="utf-8")
    assert '"turn":1' in text
    path.write_text(text.replace('"turn":1', '"turn":7', 1), encoding="utf-8")

    (record,) = repository.list_saves()
    assert record.loadable is False
    assert record.integrity_problem


# ------------------------------------------------------------------ 4. read-back


def test_a_read_back_mismatch_seeds_nothing_and_the_write_still_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    real_read = save_registry.read_save_bytes
    monkeypatch.setattr(save_registry, "read_save_bytes", lambda path: real_read(path) + b" ")
    save_id = new_save_id()
    repository.write_save(save_id, _campaign("decree_state", 1))
    assert repository._memo == {}
    monkeypatch.setattr(save_registry, "read_save_bytes", real_read)

    assert repository.path_for(save_id).is_file()
    validations = Counter(monkeypatch, save_registry, "validate_history")
    (record,) = repository.list_saves()
    assert validations.calls == 1 and record.loadable


def test_a_failed_read_back_seeds_nothing_and_the_write_still_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)

    def failing(path: object) -> bytes:
        raise SaveFileError("simulated read failure")

    monkeypatch.setattr(save_registry, "read_save_bytes", failing)
    save_id = new_save_id()
    repository.write_save(save_id, _campaign("decree_state", 1))
    assert repository._memo == {}
    assert repository.path_for(save_id).is_file()


# ------------------------------------------------------------------ 5. bounds


def test_a_full_memo_is_not_grown_by_a_write(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    sentinel = save_registry._Verdict(
        scenario_id="x", current_turn=0, problems=(), terminal_summary=None
    )
    repository._memo.update({f"{i:064x}": sentinel for i in range(VALIDATION_MEMO_MAX)})
    repository.write_save(new_save_id(), _campaign("decree_state", 1))
    assert len(repository._memo) == VALIDATION_MEMO_MAX


def test_an_existing_entry_for_the_key_is_not_replaced(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    save = _campaign("decree_state", 1)
    key = hashlib.sha256(save_registry.dump_save_json(save).encode("utf-8")).hexdigest()
    existing = save_registry._Verdict(
        scenario_id="kept", current_turn=99, problems=(), terminal_summary=None
    )
    repository._memo[key] = existing
    repository.write_save(new_save_id(), save)
    assert repository._memo[key] is existing


# ------------------------------------------------------------------ 6. the API path


def test_the_listing_validates_nothing_the_server_wrote_while_the_engine_check_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = 48995
    client = TestClient(
        create_app(ApiSettings(port=port, save_root=tmp_path, serve_spa=False)),
        base_url=f"http://127.0.0.1:{port}",
    )
    listing = Counter(monkeypatch, save_registry, "validate_history")
    engine = Counter(monkeypatch, history_module, "validate_history")
    assert client.post("/api/game/new", json={"scenario_id": "decree_state"}).status_code == 200
    for _ in range(5):
        state = client.get("/api/game/state").json()
        response = client.post(
            "/api/game/resolve",
            json={
                "revision": state["revision"],
                "campaign_id": state["campaign_id"],
                "decisions": [],
            },
        )
        assert response.status_code == 200
    assert client.post("/api/game/save-as", json={"display_name": "R1"}).status_code == 200
    listed = client.get("/api/saves").json()

    assert listing.calls == 0, "the listing re-validated a save the server itself wrote"
    assert engine.calls == 5, "advance_game's own input check runs once per resolve"
    assert len(listed) == 2 and all(row["loadable"] for row in listed)


# ------------------------------------------------------------------ 7. load still validates


def test_load_refuses_a_save_tampered_after_it_was_seeded(tmp_path: Path) -> None:
    port = 48994
    client = TestClient(
        create_app(ApiSettings(port=port, save_root=tmp_path, serve_spa=False)),
        base_url=f"http://127.0.0.1:{port}",
    )
    client.post("/api/game/new", json={"scenario_id": "decree_state"})
    state = client.get("/api/game/state").json()
    client.post(
        "/api/game/resolve",
        json={"revision": state["revision"], "campaign_id": state["campaign_id"], "decisions": []},
    )
    save_id = client.post("/api/game/save-as", json={"display_name": "R1"}).json()["save_id"]
    path = tmp_path / f"{save_id}.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"turn":1', '"turn":7', 1), encoding="utf-8")

    response = client.post("/api/game/load", json={"save_id": save_id})
    assert 400 <= response.status_code < 500, response.text[:300]
    assert "turn" in response.text


# ------------------------------------------------------------------ 8. a restart validates once


def test_a_fresh_repository_validates_every_save_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = SaveRepository(tmp_path)
    for turns in (1, 2, 3):
        writer.write_save(new_save_id(), _campaign("decree_state", turns))

    validations = Counter(monkeypatch, save_registry, "validate_history")
    restarted = SaveRepository(tmp_path)
    restarted.list_saves()
    assert validations.calls == 3
    restarted.list_saves()
    assert validations.calls == 3
