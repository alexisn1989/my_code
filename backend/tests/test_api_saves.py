"""Gate 4A1: save-ID security, atomic storage, and index reconciliation.

The security assertions here are about *shape*: a save ID is a UUID4 or it is
rejected before any `Path` is constructed, so traversal, absolute paths and
embedded separators are unrepresentable rather than filtered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.save_registry import (
    InvalidDisplayNameError,
    InvalidSaveIdError,
    SaveNotFoundError,
    SaveRepository,
    new_save_id,
    validate_display_name,
    validate_save_id,
)
from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

TRAVERSAL_ATTEMPTS = (
    "../../etc/passwd",
    "/etc/passwd",
    "..",
    ".",
    "a/b",
    "a\\b",
    "not-a-uuid",
    "",
    "550e8400-e29b-41d4-a716-44665544000",  # one character short
    "550e8400-e29b-11d4-a716-446655440000",  # version 1, not 4
    "550e8400e29b41d4a716446655440000",  # unhyphenated
    "550E8400-E29B-41D4-A716-446655440000",  # uppercase
    "550e8400-e29b-41d4-a716-446655440000\x00",
    "550e8400-e29b-41d4-a716-446655440000.json",
)


def _fresh_save(scenario: str = "decree_state.yaml") -> GameSave:
    return new_game(
        load_scenario_file(SCENARIO_DIR / scenario), save_format_version=SAVE_FORMAT_VERSION
    )


def _advance(save: GameSave) -> GameSave:
    state = save.current_state()
    return advance_game(
        save, DecisionSet(expected_turn=state.turn, expected_state_version=state.state_version)
    )


# --------------------------------------------------------------------------
# Save-ID validation happens before any filesystem access
# --------------------------------------------------------------------------


@pytest.mark.parametrize("attempt", TRAVERSAL_ATTEMPTS)
def test_non_uuid_save_ids_are_rejected(attempt: str) -> None:
    with pytest.raises(InvalidSaveIdError):
        validate_save_id(attempt)


@pytest.mark.parametrize("attempt", TRAVERSAL_ATTEMPTS)
def test_repository_refuses_to_build_a_path_for_a_non_uuid(attempt: str, tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)

    with pytest.raises(InvalidSaveIdError):
        repository.path_for(attempt)


def test_generated_save_ids_validate(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()

    assert validate_save_id(save_id) == save_id
    assert repository.path_for(save_id) == tmp_path / f"{save_id}.json"


def test_a_symlink_inside_the_root_is_not_readable_as_a_save(tmp_path: Path) -> None:
    """A symlink named like a save must not be followed out of the root."""
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    root = tmp_path / "saves"
    root.mkdir()
    save_id = new_save_id()
    (root / f"{save_id}.json").symlink_to(outside)
    repository = SaveRepository(root)

    # The resolved-parent check fires first: following the link lands outside
    # the save root, so the path is refused before it is ever opened.
    with pytest.raises(InvalidSaveIdError):
        repository.read_save(save_id)


def test_missing_save_raises_not_found(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)

    with pytest.raises(SaveNotFoundError):
        repository.read_save(new_save_id())


# --------------------------------------------------------------------------
# Display names are data, never a path component
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "bad\x00name", "line\nbreak"])
def test_invalid_display_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidDisplayNameError):
        validate_display_name(name)


def test_valid_display_name_is_stripped() -> None:
    assert validate_display_name("  Before the amendment  ") == "Before the amendment"


# --------------------------------------------------------------------------
# Round trip and atomicity
# --------------------------------------------------------------------------


def test_write_then_read_round_trips_a_save(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    save = _advance(_fresh_save())
    save_id = new_save_id()

    repository.write_save(save_id, save)
    reloaded = repository.read_save(save_id)

    assert reloaded.head_entry_hash == save.head_entry_hash
    assert reloaded.current_turn() == save.current_turn()


def test_a_failed_write_leaves_no_temporary_file_behind(tmp_path: Path, monkeypatch) -> None:
    repository = SaveRepository(tmp_path)
    save = _fresh_save()
    save_id = new_save_id()
    repository.write_save(save_id, save)
    original = (tmp_path / f"{save_id}.json").read_bytes()

    def explode(path: object, data: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.api.save_registry.write_save_atomic", explode)
    with pytest.raises(OSError):
        repository.write_save(save_id, _advance(save))

    assert (tmp_path / f"{save_id}.json").read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


# --------------------------------------------------------------------------
# Index reconciliation: files are authoritative, the index is convenience
# --------------------------------------------------------------------------


def test_listing_adopts_an_orphan_save_with_a_conservative_fallback_name(tmp_path: Path) -> None:
    """A valid save file absent from the index is recoverable, not lost data."""
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _fresh_save())
    assert not (tmp_path / "index.json").exists()

    records = repository.list_saves()

    assert [record.save_id for record in records] == [save_id]
    assert records[0].display_name.startswith("Recovered campaign - ")
    assert records[0].loadable is True
    assert (tmp_path / "index.json").is_file()


def test_listing_drops_an_index_entry_whose_file_does_not_exist(tmp_path: Path) -> None:
    """The index must never advertise a save that is not there."""
    repository = SaveRepository(tmp_path)
    ghost = new_save_id()
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.json").write_text(
        json.dumps({"saves": [{"save_id": ghost, "display_name": "Ghost"}]}), encoding="utf-8"
    )

    records = repository.list_saves()

    assert records == ()
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["saves"] == []


def test_listing_preserves_a_stored_display_name(tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _fresh_save())
    repository.list_saves()
    stored = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    stored["saves"][0]["display_name"] = "Before the amendment"
    (tmp_path / "index.json").write_text(json.dumps(stored), encoding="utf-8")

    records = repository.list_saves()

    assert records[0].display_name == "Before the amendment"


@pytest.mark.parametrize("filename", ["not-a-uuid.json", "README.md", "index.json"])
def test_non_uuid_files_in_the_root_are_never_registered(filename: str, tmp_path: Path) -> None:
    repository = SaveRepository(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / filename).write_text("{}", encoding="utf-8")

    assert repository.list_saves() == ()


def test_a_symlinked_save_file_is_not_registered(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    root = tmp_path / "saves"
    root.mkdir()
    (root / f"{new_save_id()}.json").symlink_to(outside)
    repository = SaveRepository(root)

    assert repository.list_saves() == ()


def test_a_tampered_save_is_listed_as_unloadable_with_its_problem(tmp_path: Path) -> None:
    """Never hidden, never silently trusted -- listed with the specific reason."""
    repository = SaveRepository(tmp_path)
    save_id = new_save_id()
    repository.write_save(save_id, _advance(_fresh_save()))
    path = tmp_path / f"{save_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Break the hash chain rather than the payload text: entry_hash is a
    # top-level field, so this is a tamper `validate_history` must catch.
    raw["entries"][-1]["entry_hash"] = "0" * len(raw["entries"][-1]["entry_hash"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    records = repository.list_saves()

    assert len(records) == 1
    assert records[0].loadable is False
    assert records[0].integrity_problem
