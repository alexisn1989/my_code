"""`read_save_file`, split into bytes and decode for Gate 4A3 Commit 6c, behaves exactly as before.

The listing memo hashes a save's exact on-disk bytes, so `read_save_file` was split into
`read_save_bytes` and `decode_save_bytes`. The oracle is the 6b implementation, copied verbatim below:
it wraps read and decode errors in `SaveFileError` (which `Path.read_text` does not), so it is the
behaviour to preserve -- same text on success, same exception type and message on failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import SaveFileError
from app.saves import decode_save_bytes, read_save_bytes, read_save_file


def _read_save_file_6b(path: str | Path) -> str:
    """Verbatim body of `app.saves.read_save_file` at 522bbfa4 (Commit 6b)."""
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SaveFileError(f"could not read save file {path}: {exc}") from exc


CASES: dict[str, bytes | None] = {
    "lf": b'{\n"a": 1\n}\n',
    "crlf": b'{\r\n"a": 1\r\n}\r\n',
    "lone-cr": b'{\r"a": 1\r}\r',
    "mixed": b'{\r\n"a":\r1\n}',
    "bom": b'\xef\xbb\xbf{"a": 1}',
    "invalid-utf8": b"\xff\xfe\x00 not utf-8",
    "invalid-utf8-late": b"x" * 9000 + b"\xff tail",
    "empty": b"",
    "missing": None,
}


def _outcome(reader: object, path: Path) -> tuple[str, str]:
    try:
        return ("text", reader(path))  # type: ignore[operator]
    except SaveFileError as error:
        return ("SaveFileError", str(error))


@pytest.mark.parametrize("name", sorted(CASES))
def test_read_save_file_matches_the_6b_implementation(tmp_path: Path, name: str) -> None:
    path = tmp_path / f"{name}.json"
    content = CASES[name]
    if content is not None:
        path.write_bytes(content)
    assert _outcome(read_save_file, path) == _outcome(_read_save_file_6b, path)


def test_a_directory_path_fails_identically(tmp_path: Path) -> None:
    path = tmp_path / "a-directory.json"
    path.mkdir()
    new, old = _outcome(read_save_file, path), _outcome(_read_save_file_6b, path)
    assert new == old
    assert new[0] == "SaveFileError"


def test_the_bytes_are_the_exact_on_disk_bytes(tmp_path: Path) -> None:
    path = tmp_path / "crlf.json"
    path.write_bytes(b'{\r\n"a": 1\r\n}')
    raw = read_save_bytes(path)
    assert raw == b'{\r\n"a": 1\r\n}', "no newline translation before hashing"
    assert decode_save_bytes(raw, path) == '{\n"a": 1\n}'
