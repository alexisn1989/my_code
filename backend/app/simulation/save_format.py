"""The on-disk save envelope: version compatibility policy and pure (de)serialization.

Three version concepts stay deliberately separate (see
`docs/adr/0002-snapshot-history-and-versioning.md`):

- `save_format_version` — the shape of the save *file* (this module's envelope).
- `ruleset_version` — the simulation rules a game was created under.
- `content_version` — the authored content (scenarios, later policies/events) a game uses.

A save's `save_format_version`/`ruleset_version`/`content_version` must each be individually
supported for the save to load at all; `check_compatibility` reports exactly which one is wrong
rather than a single generic "incompatible save" message.

`dump_save_json`/`load_save_json` are pure text<->`GameSave` functions with no disk I/O — reading
and writing files is `app.saves`, matching the same pure-core/I/O-boundary split used for scenarios
(`simulation.scenario` vs. `content.scenarios`).

Every `HistoryEntry` field is serialized as-is, including `state_json`/`decisions_json`/
`report_json` as literal JSON *string* values (escaped text), not re-embedded as nested objects.
This is what makes `simulation.history.validate_history`'s "is this payload still canonical JSON"
check meaningful after a load: JSON parsing preserves string values exactly, so a hand-edited,
no-longer-canonical payload string survives the round trip as a detectably-different string,
instead of being silently re-canonicalized by the act of loading it.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.canonical_json import canonical_dumps
from app.core.errors import (
    SaveFileError,
    UnsupportedContentVersionError,
    UnsupportedRulesetVersionError,
    UnsupportedSaveFormatVersionError,
)
from app.simulation.history import GameSave, HistoryEntry
from app.simulation.state import RULESET_VERSION

SAVE_FORMAT_VERSION = 1
"""The only save envelope shape this build writes or reads.

Phase 0 wrote a different, simpler `{state_file_schema_version, state}` shape with no history at
all. That format is not migrated: it recorded only a bare state, never the turns that produced it,
so a Phase-0 save at turn 8 cannot be given a valid 9-entry history — there is no data to migrate
*from*. It is rejected with an actionable message (see `app.cli`), not silently reinterpreted.
"""

SUPPORTED_RULESET_VERSIONS: frozenset[str] = frozenset({RULESET_VERSION})
"""Just the current engine ruleset. Phase 1 (`"0.1.0"`, no government accounting), Phase 2A
(`"0.2.0"`, no sector production), Phase 2B1 (`"0.3.0"`, no production-derived tax bases), Phase
2B2 (`"0.4.0"`, no derived labor allocation), Phase 2B3 (`"0.5.0"`, no resource endowments or
extraction), Phase 2C1 (`"0.6.0"`, extraction sector output still abstract, not derived from
physical extraction), Phase 2C2 (`"0.7.0"`, no constitution, legitimacy or political capital), and
Phase 3A (`"0.8.0"`, no legislature, and political capital that regenerates but cannot be spent),
and Phase 3B1 (`"0.9.0"`, one budget decision at a time, static bloc relationships, no expenditure
ledger) saves are intentionally excluded: each ruleset bump changes what turn resolution actually
*does* and/or what `GameState` must contain (Phase 2A added required player finance; Phase 2B1
added required player economy; Phase 2B2 removes authored `tax_bases` in favor of required
`tax_base_coefficients` and per-sector shares; Phase 2B3 removes authored
`SectorState.employed_workers` in favor of a required
`EconomyState.effective_labor_force_share_bps`; Phase 2C1 adds a new required
`EconomyState.resource_deposits`; Phase 2C2 adds a new required
`EconomyState.resource_output_coefficients`; Phase 3A adds a new required
`CountryState.politics`; Phase 3B1 adds a required `PoliticalState.legislature` wherever the
constitution declares one, and routes the budget through a legislative vote that can reject it;
Phase 3B2A makes `DecisionSet.decisions` a tagged union and `TurnReport` carry an eighth report
with no 0.9.0 data to reconstruct it from), and an older save has no recorded data to run the new
behavior against, so there is nothing to migrate — rejected with an actionable message, same as the
save-format-version case above. See `docs/adr/0003-government-accounting.md`,
`docs/adr/0004-sector-production-fixed-prices.md`, `docs/adr/0005-production-derived-tax-bases.md`,
`docs/adr/0006-labor-allocation-at-fixed-prices.md`,
`docs/adr/0007-resource-endowments-and-extraction.md`,
`docs/adr/0008-physical-extraction-derived-sector-output.md`,
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`,
`docs/adr/0010-legislature-parties-and-political-capital-bargaining.md`, and
`docs/adr/0011-competing-political-capital-uses-and-bloc-relationships.md`.
"""

SUPPORTED_CONTENT_VERSIONS: frozenset[str] = frozenset({"0.10.0"})
"""Tracks content-*schema* compatibility (what shape scenario-authored data must have), not a
fingerprint of any scenario's actual parameter values — two scenarios sharing a content_version
routinely carry different `resource_output_coefficients`/`resource_deposits`/`sectors` values
(`tiny_valid.yaml` and `deficit_demo.yaml` always have), and now different `constitution`/
`constitutional_order_support_bps` and `legislature` values too — `tiny_valid` seats a bicameral
majority coalition and `deficit_demo` a unicameral minority government, at the same content
version, because they share a *shape* and not a set of numbers. Bumped `"0.9.0" -> "0.10.0"` for
Phase 3B2A: no scenario field changes shape (every calibration value in every scenario is
unchanged — see `test_compatibility.py`'s bump-is-version-line-only proof), but the bump still
applies because scenario content is loaded into a `GameState` whose overall shape changed
(the mutable-relationship reconciliation groups and the eighth report), and content-version
gating exists precisely to keep "what shape a scenario must have" honest about that. See
`docs/adr/0008-physical-extraction-derived-sector-output.md`, "Content-version policy", and
`docs/adr/0011-competing-political-capital-uses-and-bloc-relationships.md`."""

_REQUIRED_ENVELOPE_KEYS = {
    "save_format_version",
    "ruleset_version",
    "content_version",
    "entry_count",
    "head_entry_hash",
    "entries",
}
_REQUIRED_ENTRY_KEYS = {
    "turn",
    "previous_entry_hash",
    "state_json",
    "decisions_json",
    "report_json",
    "ruleset_version",
    "content_version",
    "entry_hash",
}


def check_compatibility(
    *, save_format_version: int, ruleset_version: str, content_version: str
) -> None:
    """Raise a specific `SaveCompatibilityError` subclass for the first unsupported version found."""
    if save_format_version != SAVE_FORMAT_VERSION:
        raise UnsupportedSaveFormatVersionError(str(save_format_version), str(SAVE_FORMAT_VERSION))
    if ruleset_version not in SUPPORTED_RULESET_VERSIONS:
        raise UnsupportedRulesetVersionError(
            ruleset_version, ", ".join(sorted(SUPPORTED_RULESET_VERSIONS))
        )
    if content_version not in SUPPORTED_CONTENT_VERSIONS:
        raise UnsupportedContentVersionError(
            content_version, ", ".join(sorted(SUPPORTED_CONTENT_VERSIONS))
        )


def _entry_to_dict(entry: HistoryEntry) -> dict[str, Any]:
    return {
        "turn": entry.turn,
        "previous_entry_hash": entry.previous_entry_hash,
        "state_json": entry.state_json,
        "decisions_json": entry.decisions_json,
        "report_json": entry.report_json,
        "ruleset_version": entry.ruleset_version,
        "content_version": entry.content_version,
        "entry_hash": entry.entry_hash,
    }


def dump_save_json(save: GameSave) -> str:
    """Serialize a `GameSave` to canonical JSON text. Pure — no disk access."""
    payload = {
        "save_format_version": save.save_format_version,
        "ruleset_version": save.ruleset_version,
        "content_version": save.content_version,
        "entry_count": save.entry_count,
        "head_entry_hash": save.head_entry_hash,
        "entries": [_entry_to_dict(entry) for entry in save.entries],
    }
    return canonical_dumps(payload)


def _require_keys(raw: Any, required: set[str], *, source: str, what: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SaveFileError(f"{source}: {what} must be a JSON object")
    missing = required - raw.keys()
    if missing:
        raise SaveFileError(f"{source}: {what} is missing field(s): {sorted(missing)}")
    return raw


def _entry_from_dict(raw: Any, *, source: str, position: int) -> HistoryEntry:
    entry = _require_keys(
        raw, _REQUIRED_ENTRY_KEYS, source=source, what=f"entry at position {position}"
    )
    turn = entry["turn"]
    if not isinstance(turn, int) or isinstance(turn, bool):
        raise SaveFileError(f"{source}: entry at position {position} has a non-integer turn")
    return HistoryEntry(
        turn=turn,
        previous_entry_hash=entry["previous_entry_hash"],
        state_json=entry["state_json"],
        decisions_json=entry["decisions_json"],
        report_json=entry["report_json"],
        ruleset_version=entry["ruleset_version"],
        content_version=entry["content_version"],
        entry_hash=entry["entry_hash"],
    )


def load_save_json(raw_text: str, *, source: str = "<string>") -> GameSave:
    """Parse and version-check canonical save JSON text into a `GameSave`.

    Pure — no disk access, and raises before touching entries at all if the
    version envelope itself is unsupported. Does **not** run
    `simulation.history.validate_history` — that is a separate, explicit
    step callers take (see `app.saves`/`app.cli`), so "this file parses and
    has a supported version" stays distinguishable from "this file's history
    is internally consistent."
    """
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SaveFileError(f"{source} is not valid JSON: {exc}") from exc

    envelope = _require_keys(raw, _REQUIRED_ENVELOPE_KEYS, source=source, what="save file")

    save_format_version = envelope["save_format_version"]
    ruleset_version = envelope["ruleset_version"]
    content_version = envelope["content_version"]
    if not isinstance(save_format_version, int) or isinstance(save_format_version, bool):
        raise SaveFileError(f"{source}: save_format_version must be an integer")
    if not isinstance(ruleset_version, str) or not isinstance(content_version, str):
        raise SaveFileError(f"{source}: ruleset_version/content_version must be strings")

    check_compatibility(
        save_format_version=save_format_version,
        ruleset_version=ruleset_version,
        content_version=content_version,
    )

    entries_raw = envelope["entries"]
    if not isinstance(entries_raw, list):
        raise SaveFileError(f"{source}: entries must be a JSON array")

    entry_count = envelope["entry_count"]
    head_entry_hash = envelope["head_entry_hash"]
    if not isinstance(entry_count, int) or isinstance(entry_count, bool):
        raise SaveFileError(f"{source}: entry_count must be an integer")
    if not isinstance(head_entry_hash, str):
        raise SaveFileError(f"{source}: head_entry_hash must be a string")

    entries = tuple(
        _entry_from_dict(raw_entry, source=source, position=i)
        for i, raw_entry in enumerate(entries_raw)
    )

    return GameSave(
        save_format_version=save_format_version,
        ruleset_version=ruleset_version,
        content_version=content_version,
        entry_count=entry_count,
        head_entry_hash=head_entry_hash,
        entries=entries,
    )
