"""Version compatibility policy tests (product spec §30, ADR 0002/0003).

The centerpiece is `phase1_save_ruleset_0.1.0.json` — a save frozen with
unmodified Phase-1 code, committed to `tests/fixtures/` *before*
`RULESET_VERSION` was bumped to `0.2.0` for Phase 2A. There is no other way
to produce a genuine pre-2A save to test rejection against: once the bump
landed, `mandate.simulation.state.RULESET_VERSION` only ever stamps `0.2.0`
onto new games.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import (
    UnsupportedContentVersionError,
    UnsupportedRulesetVersionError,
    UnsupportedSaveFormatVersionError,
)
from app.saves import read_save_file
from app.simulation.save_format import load_save_json
from app.simulation.state import RULESET_VERSION

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PHASE1_SAVE_PATH = FIXTURES_DIR / "phase1_save_ruleset_0.1.0.json"
PHASE2A_SAVE_PATH = FIXTURES_DIR / "phase2a_save_ruleset_0.2.0.json"
PHASE2B1_SAVE_PATH = FIXTURES_DIR / "phase2b1_save_ruleset_0.3.0.json"
PHASE2B2_SAVE_PATH = FIXTURES_DIR / "phase2b2_save_ruleset_0.4.0.json"
PHASE2B3_SAVE_PATH = FIXTURES_DIR / "phase2b3_save_ruleset_0.5.0.json"


def test_frozen_phase1_save_fixture_declares_the_old_ruleset_version() -> None:
    # Sanity check on the fixture itself, so a future accidental regeneration
    # with the *current* code (which would make every test below vacuous)
    # fails loudly right here instead of silently.
    raw = json.loads(PHASE1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.1.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    raw_text = read_save_file(PHASE1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.1.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message  # "nothing was modified" framing


def test_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """A save with both an unsupported ruleset_version *and* completely garbage
    entry state must fail with the ruleset error, not a state-parsing error —
    proving `check_compatibility` runs before any entry's state/decisions/report
    JSON is ever touched."""
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible")


def test_unsupported_future_ruleset_version_is_rejected() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["ruleset_version"] = "99.0.0"
    for entry in raw["entries"]:
        entry["ruleset_version"] = "99.0.0"

    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="future")
    assert "99.0.0" in str(exc_info.value)


def test_unsupported_content_version_is_rejected_specifically_not_ruleset() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    # Give it a supported ruleset so the *content* check is what's exercised.
    raw["ruleset_version"] = RULESET_VERSION
    for entry in raw["entries"]:
        entry["ruleset_version"] = RULESET_VERSION

    with pytest.raises(UnsupportedContentVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="bad-content-version")
    assert "0.1.0" in str(exc_info.value)


def test_unsupported_save_format_version_is_rejected_specifically() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["save_format_version"] = 999

    with pytest.raises(UnsupportedSaveFormatVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="bad-envelope")
    assert "999" in str(exc_info.value)


def test_all_three_version_errors_are_distinct_types() -> None:
    assert UnsupportedSaveFormatVersionError is not UnsupportedRulesetVersionError
    assert UnsupportedRulesetVersionError is not UnsupportedContentVersionError
    assert UnsupportedSaveFormatVersionError is not UnsupportedContentVersionError


# --- Phase 2A -> Phase 2B1 ruleset bump (mirrors the Phase 1 -> 2A fixture) --
#
# `phase2a_save_ruleset_0.2.0.json` was frozen with unmodified Phase-2A code
# (no sector production, no EconomyState) *before* RULESET_VERSION was bumped
# to 0.3.0 for Phase 2B1 — the same one-shot-only sequencing as the Phase-1
# fixture above.


def test_frozen_phase2a_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2A_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.2.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2a_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via
    `player_economy_required` — proving the fixture was frozen *before* the
    bump (R1 sequencing risk): compatibility is checked before any entry
    payload is parsed at all, so the missing-economy invariant is never even
    reached for this save.
    """
    raw_text = read_save_file(PHASE2A_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2A_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.2.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2a_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2A_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2a")


# --- Phase 2B1 -> Phase 2B2 ruleset bump -------------------------------------
#
# `phase2b1_save_ruleset_0.3.0.json` was frozen with unmodified Phase-2B1 code (production
# sectors exist, but tax bases are still authored, not derived) *before* RULESET_VERSION was
# bumped to 0.4.0 for Phase 2B2 — mirroring the Phase 1 -> 2A and Phase 2A -> 2B1 fixtures.


def test_frozen_phase2b1_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.3.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `tax_base_coefficients` field or `player_economy_required` — proving compatibility is
    checked before any entry payload is parsed, and that the fixture was frozen before the
    bump (sequencing risk, same as every prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.3.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b1_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b1")


# --- Phase 2B2 -> Phase 2B3 ruleset bump -------------------------------------
#
# `phase2b2_save_ruleset_0.4.0.json` was frozen with unmodified Phase-2B2 code (tax bases are
# production-derived, but employment is still scenario-authored) *before* RULESET_VERSION was
# bumped to 0.5.0 for Phase 2B3 — mirroring every prior fixture above.


def test_frozen_phase2b2_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B2_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.4.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b2_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `effective_labor_force_share_bps` field — proving compatibility is checked before any entry
    payload is parsed, and that the fixture was frozen before the bump (sequencing risk, same
    as every prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B2_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B2_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.4.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b2_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B2_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b2")


# --- Phase 2B3 -> Phase 2C1 ruleset bump (T19) --------------------------------
#
# `phase2b3_save_ruleset_0.5.0.json` was frozen with unmodified Phase-2B3 code (labor allocation
# derives employment, but there are no resource endowments at all) *before* RULESET_VERSION was
# bumped to 0.6.0 for Phase 2C1 — mirroring every prior fixture above.


def test_frozen_phase2b3_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B3_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.5.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b3_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `resource_deposits` field — proving compatibility is checked before any entry payload is
    parsed, and that the fixture was frozen before the bump (sequencing risk, same as every
    prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B3_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B3_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.5.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b3_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B3_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b3")
