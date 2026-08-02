"""Tests for atomic save-file writes (`app.saves`)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.errors import SaveFileError
from app.saves import read_save_file, write_save_atomic


def test_successful_write_produces_expected_bytes(tmp_path: Path) -> None:
    dest = tmp_path / "save.json"
    write_save_atomic(dest, b'{"hello":"world"}')
    assert dest.read_bytes() == b'{"hello":"world"}'


def test_existing_destination_is_atomically_replaced(tmp_path: Path) -> None:
    dest = tmp_path / "save.json"
    dest.write_bytes(b"old content")
    write_save_atomic(dest, b"new content")
    assert dest.read_bytes() == b"new content"


def test_no_temp_files_left_behind_on_success(tmp_path: Path) -> None:
    dest = tmp_path / "save.json"
    write_save_atomic(dest, b"data")
    leftovers = [p for p in tmp_path.iterdir() if p != dest]
    assert leftovers == []


def test_simulated_failure_leaves_original_destination_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "save.json"
    dest.write_bytes(b"original content")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="simulated failure"):
        write_save_atomic(dest, b"new content")

    assert dest.read_bytes() == b"original content"


def test_failed_write_cleans_up_its_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "save.json"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        write_save_atomic(dest, b"data")

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "dir" / "save.json"
    write_save_atomic(dest, b"data")
    assert dest.read_bytes() == b"data"


def test_temp_filename_pattern_does_not_leak_into_written_bytes(tmp_path: Path) -> None:
    dest = tmp_path / "save.json"
    payload = b'{"turn":0}'
    write_save_atomic(dest, payload)
    assert dest.read_bytes() == payload
    assert b".tmp" not in dest.read_bytes()


def test_read_save_file_round_trips_written_content(tmp_path: Path) -> None:
    dest = tmp_path / "save.json"
    write_save_atomic(dest, "héllo".encode())
    assert read_save_file(dest) == "héllo"


def test_read_save_file_missing_path_raises_save_file_error(tmp_path: Path) -> None:
    with pytest.raises(SaveFileError):
        read_save_file(tmp_path / "does-not-exist.json")
