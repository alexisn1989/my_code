"""Disk I/O for save files: atomic writes and reads.

Deliberately outside `app.core` and `app.simulation` — the AST-based
determinism guard (`tests/test_no_forbidden_imports.py`) only scans those two
packages, and this module legitimately needs `tempfile`/`os`, which have
nothing to do with simulation randomness or wall-clock time. Nothing here
computes game state; it only moves already-canonical bytes to and from disk.
`app.simulation.save_format` does the pure (de)serialization; this module
never parses save content, only bytes.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.core.errors import SaveFileError


def write_save_atomic(path: str | Path, data: bytes) -> None:
    """Write `data` to `path` atomically: readers never observe a partial file.

    Sequence: create a unique temp file in the *same directory* as `path`
    (so the final replace is a same-filesystem rename, which POSIX
    guarantees is atomic), write and `fsync` it, close it, then
    `os.replace` the destination. On any failure the temp file is removed
    and `path` is left exactly as it was.

    The temp filename is intentionally unique and unpredictable
    (`tempfile.NamedTemporaryFile`, not a fixed `<path>.tmp`): filesystem
    naming has no bearing on game-state determinism — it is not part of any
    canonical payload, hash, or history — so there is nothing to gain by
    making it deterministic, and doing so would let two concurrent writes to
    the same destination collide on the same temp path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # delete=False is required: the file must survive past this `with` block so
    # os.replace() can rename it into place below, which is incompatible with
    # ruff's SIM115 "always use `with tempfile.X(...) as f`" idiom.
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    _fsync_directory_best_effort(path.parent)


def _fsync_directory_best_effort(directory: Path) -> None:
    """Persist the rename itself, not just the file's contents, where possible.

    Not supported on every platform — Windows has no directory file
    descriptor to `fsync` — so this is skipped there rather than failing the
    write. On POSIX filesystems that do support it, this closes the window
    where a crash immediately after `os.replace` could leave the directory
    entry unpersisted even though the file content was durably written.
    """
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def read_save_file(path: str | Path) -> str:
    """Read a save file's raw text. Raises `SaveFileError` if it can't be read."""
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SaveFileError(f"could not read save file {path}: {exc}") from exc
