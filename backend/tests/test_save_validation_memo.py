"""The save listing's content-keyed validation memo (Gate 4A3 Commit 6c).

`SaveRepository.list_saves` used to re-parse and fully replay `validate_history` for every save on
every listing, which failed the 200 ms read budget. The user authorized a memo keyed by the SHA-256
of each file's EXACT bytes. These tests pin what makes that safe:

* the key is the raw on-disk bytes -- not the decoded text, not mtime/size, not the save id -- and
  one captured buffer feeds the key, the decode, the parse and the validation;
* failures are never memoized;
* a directory one file larger than the cap revalidates one file per listing, not all of them;
* retention follows the directory;
* concurrent misses on one key validate once, even when the memo is full, and admission under the
  cap is atomic across concurrent distinct keys.

Every save here is made through the production path (`new_game` / `advance_game` /
`SaveRepository.write_save`); nothing is hand-assembled.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.api import save_registry
from app.api.save_registry import SaveNotFoundError, SaveRecord, SaveRepository, new_save_id
from app.content.scenarios import load_scenario_file
from app.core.errors import SaveFileError
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
UNDECODABLE = b"\xff\xfe\x00 not utf-8"
WAIT_S = 10.0


def _fresh(scenario: str = "decree_state.yaml") -> GameSave:
    return new_game(
        load_scenario_file(SCENARIO_DIR / scenario), save_format_version=SAVE_FORMAT_VERSION
    )


def _advance(save: GameSave) -> GameSave:
    state = save.current_state()
    return advance_game(
        save, DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)
    )


def _write(repository: SaveRepository, save: GameSave) -> str:
    save_id = new_save_id()
    repository.write_save(save_id, save)
    return save_id


def _key(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(records: tuple[SaveRecord, ...]) -> list[tuple[object, ...]]:
    return [
        (r.save_id, r.scenario_id, r.current_turn, r.loadable, r.integrity_problem) for r in records
    ]


class Counter:
    """Wrap a module-level function in `save_registry` and count calls."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        self.calls = 0
        real: Callable[..., Any] = getattr(save_registry, name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(save_registry, name, counted)


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_S
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the concurrency precondition")
        time.sleep(0.005)


# ------------------------------------------------------------------ hits, and what keys a verdict


def test_a_second_listing_validates_nothing_and_returns_identical_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    _write(writer, _advance(_fresh()))
    _write(writer, _fresh("tiny_valid.yaml"))
    validations = Counter(monkeypatch, "validate_history")
    first = repository.list_saves()
    assert validations.calls == 2
    second = repository.list_saves()
    assert validations.calls == 2, "a hit must not replay validate_history"
    assert second == first


def test_a_same_length_tamper_with_its_original_mtime_restored_is_revalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Size and nanosecond mtime are both unchanged, so a key built from them would serve the
    stale `loadable=True`. Only a key over the bytes catches it."""
    repository = SaveRepository(tmp_path)
    save_id = _write(repository, _advance(_fresh()))
    path = tmp_path / f"{save_id}.json"
    assert repository.list_saves()[0].loadable is True
    before = os.stat(path)

    raw = path.read_bytes()
    marker = b'"entry_hash":"'
    at = raw.rindex(marker) + len(marker)
    flipped = b"0" if raw[at : at + 1] != b"0" else b"1"
    path.write_bytes(raw[:at] + flipped + raw[at + 1 :])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(path)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)

    validations = Counter(monkeypatch, "validate_history")
    record = repository.list_saves()[0]
    assert validations.calls == 1
    assert record.loadable is False
    assert record.integrity_problem


def test_crlf_and_lf_files_are_distinct_keys_although_they_decode_alike(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    save_id = _write(repository, _fresh())
    canonical = (tmp_path / f"{save_id}.json").read_bytes()
    (tmp_path / f"{save_id}.json").unlink()
    lf, crlf = new_save_id(), new_save_id()
    (tmp_path / f"{lf}.json").write_bytes(b"{\n" + canonical[1:])
    (tmp_path / f"{crlf}.json").write_bytes(b"{\r\n" + canonical[1:])
    assert (tmp_path / f"{lf}.json").read_text(encoding="utf-8") == (
        tmp_path / f"{crlf}.json"
    ).read_text(encoding="utf-8"), "the two files must decode to identical text"

    validations = Counter(monkeypatch, "validate_history")
    records = repository.list_saves()
    assert validations.calls == 2, "exact bytes differ, so the keys differ"
    assert all(record.loadable for record in records)
    assert len(repository._memo) == 2


def test_byte_identical_files_are_validated_once_and_listed_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    original = _write(writer, _advance(_fresh()))
    copy = new_save_id()
    (tmp_path / f"{copy}.json").write_bytes((tmp_path / f"{original}.json").read_bytes())
    validations = Counter(monkeypatch, "validate_history")
    records = repository.list_saves()
    assert validations.calls == 1
    assert sorted(r.save_id for r in records) == sorted([original, copy])


# ------------------------------------------------------------------ failures are never memoized


def test_unreadable_and_unparseable_files_are_read_and_checked_on_every_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    (tmp_path / f"{new_save_id()}.json").write_bytes(UNDECODABLE)
    (tmp_path / f"{new_save_id()}.json").write_bytes(b'{"not": "a save"}')
    reads = Counter(monkeypatch, "read_save_bytes")
    decodes = Counter(monkeypatch, "decode_save_bytes")
    parses = Counter(monkeypatch, "load_save_json")

    for listing in (1, 2):
        records = repository.list_saves()
        assert [r.loadable for r in records] == [False, False]
        assert reads.calls == 2 * listing, "both files are re-read on every listing"
        assert decodes.calls == 2 * listing, "both are re-decoded on every listing"
        assert parses.calls == 1 * listing, "the decodable one is re-parsed on every listing"
    assert repository._memo == {}


def test_the_listing_never_reopens_a_file_through_read_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    _write(writer, _advance(_fresh()))

    def refuse(self: SaveRepository, save_id: str) -> GameSave:
        raise AssertionError("the listing must work from its one captured buffer")

    monkeypatch.setattr(SaveRepository, "read_save", refuse)
    validations = Counter(monkeypatch, "validate_history")
    records = repository.list_saves()
    assert [r.loadable for r in records] == [True]
    # (Gate 4A3 R1 fix) The compute path this test guards actually ran, rather than a memo hit.
    assert validations.calls == 1


def test_symlinks_and_directories_named_like_saves_are_still_refused(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    real = _write(repository, _fresh())
    linked, directory = new_save_id(), new_save_id()
    (tmp_path / f"{linked}.json").symlink_to(tmp_path / f"{real}.json")
    (tmp_path / f"{directory}.json").mkdir()
    assert [r.save_id for r in repository.list_saves()] == [real]
    for save_id in (linked, directory):
        with pytest.raises(SaveNotFoundError):
            repository._verdict_for(save_id)


def test_display_name_and_mtime_are_never_memoized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    save_id = _write(repository, _fresh())
    first = repository.list_saves()[0]
    index = tmp_path / "index.json"
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["saves"][0]["display_name"] = "Renamed campaign"
    index.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(tmp_path / f"{save_id}.json", (1_700_000_000, 1_700_000_000))

    validations = Counter(monkeypatch, "validate_history")
    second = repository.list_saves()[0]
    assert validations.calls == 0
    assert second.display_name == "Renamed campaign"
    assert second.updated_at != first.updated_at


# ------------------------------------------------------------------ capacity and retention


def test_one_file_over_the_cap_costs_one_validation_per_listing_not_a_rescan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The thrash case: an LRU over a sorted scan would evict, at cap + 1, exactly the file the
    next listing reads first, so every listing would revalidate everything."""
    monkeypatch.setattr(save_registry, "VALIDATION_MEMO_MAX", 3)
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    save = _fresh("tiny_valid.yaml")
    for _ in range(4):
        save = _advance(save)
        _write(writer, save)
    validations = Counter(monkeypatch, "validate_history")
    repository.list_saves()
    assert validations.calls == 4
    for listing in (2, 3):
        repository.list_saves()
        assert validations.calls == 4 + (listing - 1), "exactly the overflow file is revalidated"
    assert len(repository._memo) == 3


def test_retention_follows_the_directory(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    kept = _write(repository, _fresh())
    gone = _write(repository, _fresh("tiny_valid.yaml"))
    rewritten = _write(repository, _fresh("deficit_demo.yaml"))
    old_key = _key(tmp_path / f"{rewritten}.json")
    gone_key = _key(tmp_path / f"{gone}.json")
    repository.list_saves()
    assert {old_key, gone_key} <= set(repository._memo)

    (tmp_path / f"{gone}.json").unlink()
    repository.write_save(rewritten, _advance(_fresh("deficit_demo.yaml")))
    repository.list_saves()
    assert gone_key not in repository._memo
    assert old_key not in repository._memo
    assert set(repository._memo) == {
        _key(tmp_path / f"{kept}.json"),
        _key(tmp_path / f"{rewritten}.json"),
    }


# ------------------------------------------------------------------ concurrency


def _blocking_validate(monkeypatch: pytest.MonkeyPatch, release: threading.Event) -> list[int]:
    calls: list[int] = []
    real = save_registry.validate_history

    def blocking(save: GameSave) -> list[str]:
        calls.append(1)
        assert release.wait(WAIT_S), "test never released the validation"
        return real(save)

    monkeypatch.setattr(save_registry, "validate_history", blocking)
    return calls


def _list_in_thread(
    repository: SaveRepository, results: dict[str, tuple[SaveRecord, ...]], name: str
) -> threading.Thread:
    thread = threading.Thread(target=lambda: results.__setitem__(name, repository.list_saves()))
    thread.start()
    return thread


@pytest.mark.parametrize("cap", [4096, 0], ids=["admitted", "memo-full"])
def test_concurrent_misses_on_one_key_validate_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: int
) -> None:
    """With cap 0 nothing is ever admitted, so the waiter can only get its verdict from the
    in-flight object -- the case an Event alone would leave without an answer."""
    monkeypatch.setattr(save_registry, "VALIDATION_MEMO_MAX", cap)
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    save_id = _write(writer, _advance(_fresh()))
    key = _key(tmp_path / f"{save_id}.json")
    release = threading.Event()
    calls = _blocking_validate(monkeypatch, release)
    results: dict[str, tuple[SaveRecord, ...]] = {}

    first = _list_in_thread(repository, results, "a")
    _wait_until(lambda: repository._in_flight_count() == 1)
    second = _list_in_thread(repository, results, "b")
    _wait_until(lambda: repository._waiting_for(key) == 1)
    release.set()
    first.join(WAIT_S)
    second.join(WAIT_S)

    assert len(calls) == 1, "one key, one validation, across both listings"
    assert _rows(results["a"]) == _rows(results["b"])
    assert results["a"][0].loadable is True
    assert len(repository._memo) == (1 if cap else 0)


def test_when_the_owner_fails_a_waiter_computes_for_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    save_id = _write(writer, _advance(_fresh()))
    key = _key(tmp_path / f"{save_id}.json")
    release = threading.Event()
    parses: list[int] = []
    real = save_registry.load_save_json

    def flaky(text: str, *, source: str) -> GameSave:
        parses.append(1)
        if len(parses) == 1:
            assert release.wait(WAIT_S)
            raise SaveFileError("injected failure in the owner")
        return real(text, source=source)

    monkeypatch.setattr(save_registry, "load_save_json", flaky)
    results: dict[str, tuple[SaveRecord, ...]] = {}
    first = _list_in_thread(repository, results, "a")
    _wait_until(lambda: repository._in_flight_count() == 1)
    second = _list_in_thread(repository, results, "b")
    _wait_until(lambda: repository._waiting_for(key) == 1)
    release.set()
    first.join(WAIT_S)
    second.join(WAIT_S)

    assert len(parses) == 2, "the failure is not memoized, so the waiter parses for itself"
    assert results["a"][0].loadable is False
    assert results["b"][0].loadable is True


def test_admission_under_the_cap_is_atomic_across_concurrent_distinct_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(save_registry, "VALIDATION_MEMO_MAX", 2)
    repository = SaveRepository(tmp_path)
    # (Gate 4A3 R1 fix) Written through a SECOND repository on the same root, so the one under
    # test has never seen these bytes -- as after a restart. `write_save` now seeds the memo of
    # the repository that writes, which would otherwise pre-empt the listing this test measures.
    writer = SaveRepository(tmp_path)
    ids = [
        _write(writer, save)
        for save in (_fresh(), _fresh("tiny_valid.yaml"), _fresh("deficit_demo.yaml"))
    ]
    real = save_registry.validate_history

    # A barrier, not polling: every one of the three reaches validation only after it has been
    # registered (and admitted or refused) under the lock, so all three are in flight together.
    barrier = threading.Barrier(3, timeout=WAIT_S)

    def gated(save: GameSave) -> list[str]:
        assert repository._in_flight_count() >= 1
        barrier.wait()
        return real(save)

    monkeypatch.setattr(save_registry, "validate_history", gated)
    threads = [threading.Thread(target=repository._verdict_for, args=(sid,)) for sid in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_S)
    assert len(repository._memo) == 2, "three concurrent misses must not overshoot a cap of 2"

    monkeypatch.setattr(save_registry, "validate_history", real)
    validations = Counter(monkeypatch, "validate_history")
    repository.list_saves()
    assert validations.calls == 1
