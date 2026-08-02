"""Tests for the save envelope: version compatibility and pure (de)serialization."""

from __future__ import annotations

import json

import pytest

from app.core.errors import (
    SaveFileError,
    UnsupportedContentVersionError,
    UnsupportedRulesetVersionError,
    UnsupportedSaveFormatVersionError,
)
from app.simulation.decisions import DecisionSet
from app.simulation.history import advance_game, new_game
from app.simulation.save_format import (
    SAVE_FORMAT_VERSION,
    check_compatibility,
    dump_save_json,
    load_save_json,
)
from app.simulation.state import RULESET_VERSION
from tests.conftest import make_game_state


def _fresh_save():
    return new_game(
        make_game_state(turn=0, state_version=0), save_format_version=SAVE_FORMAT_VERSION
    )


def test_current_versions_load_normally() -> None:
    save = _fresh_save()
    text = dump_save_json(save)
    loaded = load_save_json(text, source="test")
    assert loaded.save_format_version == SAVE_FORMAT_VERSION
    assert loaded.ruleset_version == save.ruleset_version
    assert loaded.content_version == save.content_version


def test_check_compatibility_accepts_current_versions() -> None:
    check_compatibility(
        save_format_version=SAVE_FORMAT_VERSION,
        ruleset_version=RULESET_VERSION,
        content_version="0.3.0",
    )  # must not raise


def test_unsupported_save_format_version_is_rejected_specifically() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    raw["save_format_version"] = SAVE_FORMAT_VERSION + 1
    with pytest.raises(UnsupportedSaveFormatVersionError):
        load_save_json(json.dumps(raw), source="test")


def test_unsupported_ruleset_version_is_rejected_specifically() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    raw["ruleset_version"] = "99.0.0"
    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="test")


def test_unsupported_content_version_is_rejected_specifically() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    raw["content_version"] = "99.0.0"
    with pytest.raises(UnsupportedContentVersionError):
        load_save_json(json.dumps(raw), source="test")


def test_future_save_format_version_is_rejected_not_reinterpreted() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    raw["save_format_version"] = 999
    with pytest.raises(UnsupportedSaveFormatVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="test")
    assert "999" in str(exc_info.value)
    assert str(SAVE_FORMAT_VERSION) in str(exc_info.value)


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(SaveFileError):
        load_save_json("{not valid json", source="test")


def test_missing_envelope_field_is_rejected() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    del raw["entry_count"]
    with pytest.raises(SaveFileError):
        load_save_json(json.dumps(raw), source="test")


def test_missing_entry_field_is_rejected() -> None:
    save = _fresh_save()
    raw = json.loads(dump_save_json(save))
    del raw["entries"][0]["state_json"]
    with pytest.raises(SaveFileError):
        load_save_json(json.dumps(raw), source="test")


def test_export_import_export_is_byte_identical() -> None:
    state = make_game_state(turn=0, state_version=0)
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    for _ in range(3):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn, expected_state_version=current.state_version, decisions=[]
        )
        save = advance_game(save, decisions)

    first_export = dump_save_json(save)
    reloaded = load_save_json(first_export, source="test")
    second_export = dump_save_json(reloaded)

    assert first_export == second_export


def test_export_import_export_preserves_entry_count_and_head_hash() -> None:
    save = _fresh_save()
    for _ in range(4):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn, expected_state_version=current.state_version, decisions=[]
        )
        save = advance_game(save, decisions)

    reloaded = load_save_json(dump_save_json(save), source="test")
    assert reloaded.entry_count == save.entry_count
    assert reloaded.head_entry_hash == save.head_entry_hash
    assert reloaded.entry_count == len(reloaded.entries)
    assert reloaded.head_entry_hash == reloaded.entries[-1].entry_hash
