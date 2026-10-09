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

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.api.outcome_labels import outcome_reason_text
from app.core.errors import MandateError
from app.saves import decode_save_bytes, read_save_bytes, read_save_file, write_save_atomic
from app.simulation.history import GameSave, validate_history
from app.simulation.save_format import dump_save_json, load_save_json

#: A save ID is exactly a lowercase UUID4. Nothing else is accepted, ever.
SAVE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

INDEX_FILENAME = "index.json"

#: Gate 4A3 Commit 6c: the most save verdicts the listing memo holds. A miss is admitted only while a
#: slot is free and nothing is ever evicted, so a directory larger than this keeps the first
#: `VALIDATION_MEMO_MAX` saves memoized and revalidates only the overflow -- never a full rescan.
VALIDATION_MEMO_MAX = 4096
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


@dataclass(frozen=True)
class _Verdict:
    """Everything a listing derives from one save's bytes -- and nothing it does not."""

    scenario_id: str
    current_turn: int
    problems: tuple[str, ...]
    terminal_summary: str | None


@dataclass
class _InFlight:
    """One verdict being computed. Waiters read the result from HERE, not from the memo, so
    single-flight holds even for a key that was not admitted because the memo is full."""

    admitted: bool
    done: threading.Event = field(default_factory=threading.Event)
    verdict: _Verdict | None = None
    waiters: int = 0


class SaveRepository:
    """All filesystem access in the API goes through this one object.

    THE LISTING MEMO (Gate 4A3 Commit 6c, authorized by the user's ruling "Content-keyed memo").
    `list_saves` used to re-parse and fully replay `validate_history` for every save on every
    listing, which failed the 200 ms read budget. A listing now remembers each save's verdict keyed by
    the SHA-256 of the file's EXACT on-disk bytes. That is sound because the verdict is a pure
    function of those bytes for the life of a process: `validate_history` does no I/O, reads no
    clock, no randomness and no scenario file, and decoding and parsing are deterministic. Any
    changed byte is a new key and a full re-validation. Only successful verdicts are memoized; a
    read, decode, parse or version failure is re-checked on every listing. Loading a save
    (`read_save`, and the load endpoint) still validates in full, every time.

    SEEDING ON WRITE (Gate 4A3 R1 fix, authorized by the user's ruling "go with a"). Every resolve
    and save-as writes a save and then lists saves in the same request, so without seeding each
    turn paid one full `validate_history` of the campaign it had just written. `write_save` now
    reads the file back and, if the bytes on disk are EXACTLY the bytes it serialized, stores the
    verdict for that key itself. Its `problems=()` is asserted from provenance, not computed: the
    bytes are this server's own serialization of a save the engine built (`advance_game` validates
    its input; `new_game` builds a genesis; save-as writes the session's save, which was either
    loaded with full validation or built by the engine). The cost of that trust is stated rather
    than hidden: an engine defect producing an invalid history would be LISTED as loadable until
    the process restarts. It would still be refused by load, which never consults this memo, and
    the session already plays from that same in-memory save without re-validating it. A read-back
    mismatch or read failure seeds nothing, so the next listing validates in full as before. The
    memo stays in memory: a fresh process validates every save once, exactly as it did.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._memo_lock = threading.Lock()
        self._memo: dict[str, _Verdict] = {}
        self._in_flight: dict[str, _InFlight] = {}

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

    def _checked_path(self, save_id: str) -> Path:
        """The save's file, refusing a symlink or anything but a regular file. Shared by `read_save`
        and the listing so the two can never apply different checks."""
        path = self.path_for(save_id)
        if path.is_symlink() or not path.is_file():
            raise SaveNotFoundError(f"no save {save_id}")
        return path

    def read_save(self, save_id: str) -> GameSave:
        """Read, parse and version-check one save. Raises rather than guessing."""
        path = self._checked_path(save_id)
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
        data = dump_save_json(save).encode("utf-8")
        write_save_atomic(path, data)
        self._seed_verdict(path, data, save)

    def _seed_verdict(self, path: Path, data: bytes, save: GameSave) -> None:
        """Remember the verdict for bytes this server just wrote (see the class docstring).

        Seeds only when the file reads back byte-identical to `data`; derives `scenario_id`,
        `current_turn` and `terminal_summary` exactly as `_compute_verdict` does; never replaces an
        existing entry and never exceeds `VALIDATION_MEMO_MAX`. A read failure seeds nothing and is
        not a write failure: the write has already succeeded atomically.
        """
        try:
            on_disk = read_save_bytes(path)
        except (OSError, MandateError):
            return
        if on_disk != data:
            return
        state = save.current_state()
        verdict = _Verdict(
            scenario_id=state.world.player_country_id,
            current_turn=state.turn,
            problems=(),
            terminal_summary=self._terminal_summary_text(save),
        )
        key = hashlib.sha256(data).hexdigest()
        with self._memo_lock:
            if key in self._memo or key in self._in_flight:
                return
            admitted_in_flight = sum(1 for f in self._in_flight.values() if f.admitted)
            if len(self._memo) + admitted_in_flight >= VALIDATION_MEMO_MAX:
                return
            self._memo[key] = verdict

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
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # `UnicodeDecodeError` is listed explicitly: it subclasses `ValueError`, not
            # `json.JSONDecodeError`, so undecodable index bytes were escaping this handler and
            # failing every caller. Named rather than widened to `ValueError`, so a genuine bug in
            # the parsing below is still raised instead of silently returning an empty index.
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
        seen_keys: set[str] = set()
        for save_id, stat_result in self._candidate_files():
            updated_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
            row = stored.get(save_id, {})
            try:
                key, verdict = self._verdict_for(save_id)
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
            seen_keys.add(key)
            scenario_id = verdict.scenario_id
            current_turn = verdict.current_turn
            problems = verdict.problems

            stored_name = row.get("display_name")
            display_name = (
                str(stored_name)
                if isinstance(stored_name, str) and stored_name.strip()
                # Conservative fallback: derived from what the save itself proves,
                # never invented to look like an authored name.
                else f"Recovered campaign - {scenario_id} turn {current_turn}"
            )
            terminal = verdict.terminal_summary
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

        # Retention follows the directory: a key no current file has is dropped, so deleted or
        # rewritten saves free their slots. In-flight keys are untouched.
        with self._memo_lock:
            for stale in [key for key in self._memo if key not in seen_keys]:
                del self._memo[stale]
        self.write_index(tuple(records))
        return tuple(records)

    # -- the listing memo (Gate 4A3 Commit 6c) --------------------------

    def _verdict_for(self, save_id: str) -> tuple[str, _Verdict]:
        """The verdict for this save's bytes, computed at most once per key across threads.

        The file is read ONCE; the key, the decode, the parse and the validation all come from that
        one buffer, so a verdict can never be stored under the key of bytes it was not computed from.
        """
        path = self._checked_path(save_id)
        raw = read_save_bytes(path)
        key = hashlib.sha256(raw).hexdigest()
        while True:
            with self._memo_lock:
                cached = self._memo.get(key)
                if cached is not None:
                    return key, cached
                flight = self._in_flight.get(key)
                if flight is None:
                    # Admission is decided HERE, under the lock, counting admitted computations
                    # still in flight -- so concurrent misses on distinct keys cannot overshoot.
                    admitted_in_flight = sum(1 for f in self._in_flight.values() if f.admitted)
                    flight = _InFlight(
                        admitted=len(self._memo) + admitted_in_flight < VALIDATION_MEMO_MAX
                    )
                    self._in_flight[key] = flight
                    owner = True
                else:
                    flight.waiters += 1
                    owner = False
            if not owner:
                flight.done.wait()
                if flight.verdict is not None:
                    return key, flight.verdict
                continue  # the owner failed; failures are never memoized, so compute ourselves
            try:
                verdict = self._compute_verdict(raw, path, save_id)
                flight.verdict = verdict
                with self._memo_lock:
                    if flight.admitted:
                        self._memo[key] = verdict
            finally:
                with self._memo_lock:
                    del self._in_flight[key]
                flight.done.set()
            return key, verdict

    def _compute_verdict(self, raw: bytes, path: Path, save_id: str) -> _Verdict:
        save = load_save_json(decode_save_bytes(raw, path), source=f"save:{save_id}")
        state = save.current_state()
        return _Verdict(
            scenario_id=state.world.player_country_id,
            current_turn=state.turn,
            problems=tuple(validate_history(save)),
            terminal_summary=self._terminal_summary_text(save),
        )

    def _waiting_for(self, key: str) -> int:
        """Test hook: how many threads are waiting on an in-flight verdict for `key`."""
        with self._memo_lock:
            flight = self._in_flight.get(key)
            return 0 if flight is None else flight.waiters

    def _in_flight_count(self) -> int:
        """Test hook: how many verdicts are being computed right now."""
        with self._memo_lock:
            return len(self._in_flight)

    @staticmethod
    def _terminal_summary_text(save: GameSave) -> str | None:
        state = save.current_state()
        country = state.world.countries.get(state.world.player_country_id)
        politics = None if country is None else country.politics
        outcome = None if politics is None else politics.terminal_outcome
        if outcome is None:
            return None
        reason = outcome.victory_reason or outcome.removal_reason
        label = outcome_reason_text(reason).phrase
        return f"{outcome.bucket.value.capitalize()} - {label}, turn {outcome.turn}"
