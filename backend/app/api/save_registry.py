"""Server-owned save storage, addressed by UUID4 ID and nothing else.

The security posture here is *by construction*, not by blocklist. A save ID is
matched against a strict UUID4 pattern **before any `Path` is built**, and the
UUID grammar contains no path syntax at all -- no separator, no `..`, no drive
letter, no null byte -- so traversal is not "filtered out", it is unrepresentable.
Two redundant checks follow anyway (resolved parent must be the save root; the
target must be a regular file and not a symlink), because a defence that costs
nothing should not be skipped.

Authority hierarchy, per ADR 0014 and the frozen plan:

  * The UUID-named engine save files are **authoritative**. They are the only
    durable game data, and they are written with the engine's own
    `write_save_atomic` (same-directory temp -> fsync -> os.replace -> directory
    fsync), which this module reuses verbatim and never reimplements.
  * `index.json` is **convenience metadata** and is fully reconstructible from
    the save files. It is never required to read or validate a save, and it is
    written with the same atomic replacement so a torn index is impossible.

A valid save file missing from the index is therefore a recoverable orphan, not
lost data; reconciliation adopts it with conservative derived metadata. A file
that is not a regular UUID-named file, or that fails to parse or validate, is
never silently registered -- it is reported as unreadable so the UI can say so.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.errors import MandateError
from app.saves import read_save_file, write_save_atomic
from app.simulation.history import GameSave, validate_history
from app.simulation.save_format import dump_save_json, load_save_json

#: A save ID is exactly a lowercase UUID4. Nothing else is accepted, ever.
SAVE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

INDEX_FILENAME = "index.json"
MAX_DISPLAY_NAME_LENGTH = 80


class InvalidSaveIdError(MandateError):
    """The supplied save ID is not a UUID4. Raised before any filesystem access."""


class SaveNotFoundError(MandateError):
    """No save file exists for a well-formed save ID."""


class InvalidDisplayNameError(MandateError):
    """A display name was empty, too long, or contained control characters."""


def new_save_id() -> str:
    """A fresh server-generated save ID. Clients never choose one."""
    return str(uuid4())


def validate_save_id(save_id: str) -> str:
    """Return `save_id` if it is a UUID4, else raise -- before touching the disk.

    Traversal attempts (`../../etc/passwd`), absolute paths, embedded separators
    and null bytes all fail this single check on shape, so no later code has to
    remember to sanitise anything.
    """
    if not isinstance(save_id, str) or not SAVE_ID_PATTERN.fullmatch(save_id):
        raise InvalidSaveIdError("save id must be a UUID4")
    return save_id


def validate_display_name(display_name: str) -> str:
    """1-80 characters after stripping, no control characters.

    Stored only in `index.json`. It is **never** used to build a path, so this
    is a data-quality rule rather than a security boundary.
    """
    stripped = display_name.strip()
    if not stripped or len(stripped) > MAX_DISPLAY_NAME_LENGTH:
        raise InvalidDisplayNameError(
            f"display name must be 1-{MAX_DISPLAY_NAME_LENGTH} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
        raise InvalidDisplayNameError("display name must not contain control characters")
    return stripped


def _as_int(value: object) -> int:
    """Coerce an untrusted index value to an int, defaulting to 0."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


@dataclass(frozen=True)
class SaveRecord:
    """Listing metadata for one save. Never carries a filesystem path."""

    save_id: str
    display_name: str
    scenario_id: str
    current_turn: int
    updated_at: str
    terminal_outcome_summary: str | None = None
    loadable: bool = True
    integrity_problem: str | None = None


class SaveRepository:
    """All filesystem access in the API goes through this one object."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    # -- paths ----------------------------------------------------------

    def path_for(self, save_id: str) -> Path:
        """Resolve a validated save ID to its file, with two redundant checks."""
        validate_save_id(save_id)
        candidate = self._root / f"{save_id}.json"
        resolved_root = self._root.resolve()
        # `strict=False`: the file legitimately may not exist yet on a write.
        if resolved_root not in candidate.resolve(strict=False).parents:
            raise InvalidSaveIdError("resolved save path escapes the save root")
        return candidate

    def _index_path(self) -> Path:
        return self._root / INDEX_FILENAME

    # -- reads ----------------------------------------------------------

    def read_save(self, save_id: str) -> GameSave:
        """Read, parse and version-check one save. Raises rather than guessing."""
        path = self.path_for(save_id)
        if path.is_symlink() or not path.is_file():
            raise SaveNotFoundError(f"no save {save_id}")
        return load_save_json(read_save_file(path), source=f"save:{save_id}")

    # -- writes ---------------------------------------------------------

    def write_save(self, save_id: str, save: GameSave) -> None:
        """Serialize and atomically replace one save file.

        Reuses `app.saves.write_save_atomic` exactly as the CLI does: readers
        never observe a partial file, and a failure leaves the previous bytes in
        place rather than a truncated one.
        """
        path = self.path_for(save_id)
        self._root.mkdir(parents=True, exist_ok=True)
        write_save_atomic(path, dump_save_json(save).encode("utf-8"))

    def write_index(self, records: tuple[SaveRecord, ...]) -> None:
        """Atomically replace the whole convenience index."""
        self._root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"saves": [record.__dict__ for record in records]}, indent=2, sort_keys=True
        )
        write_save_atomic(self._index_path(), payload.encode("utf-8"))

    def read_index(self) -> dict[str, dict[str, object]]:
        """Best-effort read. A missing or unreadable index is not an error.

        It is reconstructible metadata: losing it costs display names, never
        game data, so the caller reconciles instead of failing.
        """
        path = self._index_path()
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        saves = raw.get("saves")
        if not isinstance(saves, list):
            return {}
        by_id: dict[str, dict[str, object]] = {}
        for row in saves:
            if isinstance(row, dict) and isinstance(row.get("save_id"), str):
                by_id[str(row["save_id"])] = row
        return by_id

    # -- reconciliation -------------------------------------------------

    def _candidate_files(self) -> list[tuple[str, os.stat_result]]:
        """UUID-named regular files directly in the save root. No links, no recursion."""
        if not self._root.is_dir():
            return []
        found: list[tuple[str, os.stat_result]] = []
        with os.scandir(self._root) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if not entry.name.endswith(".json"):
                    continue
                stem = entry.name[: -len(".json")]
                if not SAVE_ID_PATTERN.fullmatch(stem):
                    continue
                found.append((stem, entry.stat(follow_symlinks=False)))
        return sorted(found, key=lambda pair: pair[0])

    def list_saves(self) -> tuple[SaveRecord, ...]:
        """List saves, reconciling the index against the authoritative files.

        Files are the source of truth: an index entry naming a file that does not
        exist is dropped, and a valid file missing from the index is adopted with
        conservative derived metadata and a fallback display name. Every save is
        parsed and `validate_history`-checked before it is described as loadable,
        so a tampered save is listed with its specific problem rather than being
        hidden or silently trusted.
        """
        stored = self.read_index()
        records: list[SaveRecord] = []
        for save_id, stat_result in self._candidate_files():
            updated_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
            row = stored.get(save_id, {})
            try:
                save = self.read_save(save_id)
                state = save.current_state()
                scenario_id = state.world.player_country_id
                current_turn = state.turn
                problems = validate_history(save)
            except MandateError as error:
                records.append(
                    SaveRecord(
                        save_id=save_id,
                        display_name=str(row.get("display_name") or f"Unreadable save {save_id}"),
                        scenario_id=str(row.get("scenario_id") or "unknown"),
                        current_turn=_as_int(row.get("current_turn")),
                        updated_at=updated_at,
                        loadable=False,
                        integrity_problem=str(error),
                    )
                )
                continue

            stored_name = row.get("display_name")
            display_name = (
                str(stored_name)
                if isinstance(stored_name, str) and stored_name.strip()
                # Conservative fallback: derived from what the save itself proves,
                # never invented to look like an authored name.
                else f"Recovered campaign - {scenario_id} turn {current_turn}"
            )
            terminal = self._terminal_summary_text(save)
            records.append(
                SaveRecord(
                    save_id=save_id,
                    display_name=display_name,
                    scenario_id=scenario_id,
                    current_turn=current_turn,
                    updated_at=updated_at,
                    terminal_outcome_summary=terminal,
                    loadable=not problems,
                    integrity_problem="; ".join(problems) if problems else None,
                )
            )

        self.write_index(tuple(records))
        return tuple(records)

    @staticmethod
    def _terminal_summary_text(save: GameSave) -> str | None:
        state = save.current_state()
        country = state.world.countries.get(state.world.player_country_id)
        politics = None if country is None else country.politics
        outcome = None if politics is None else politics.terminal_outcome
        if outcome is None:
            return None
        reason = outcome.victory_reason or outcome.removal_reason
        label = reason.value.replace("_", " ") if reason is not None else "unknown"
        return f"{outcome.bucket.value.capitalize()} - {label}, turn {outcome.turn}"
