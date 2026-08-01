"""Canonical JSON serialization for determinism checks and save files.

The single serialization path used to compare two independently-produced
`GameState`/`TurnReport` objects byte-for-byte, and later reused for save
files and API responses. "Canonical" here means:

- object keys sorted
- fixed, compact separators (no incidental whitespace differences)
- no floating-point NaN/Infinity (not valid JSON; `allow_nan=False` enforces it)
- datetimes, UUIDs, and sets are rejected outright rather than silently
  coerced — those are exactly the categories of "looks deterministic but
  isn't" values (wall-clock timestamps, random UUID4s, insertion-order-
  dependent sets) called out in `docs/architecture.md`. If the domain model
  ever needs a stable identifier or ordering, it should be a plain string ID
  or a sorted list, not one of these types.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any


class NonCanonicalValueError(TypeError):
    """Raised when a value that cannot be serialized deterministically is encountered."""


def _reject_non_canonical(obj: Any) -> Any:
    if isinstance(obj, set | frozenset):
        raise NonCanonicalValueError(
            f"unordered set {obj!r} is not canonically serializable; use a sorted list"
        )
    if isinstance(obj, datetime.date | datetime.datetime | datetime.time):
        raise NonCanonicalValueError(
            f"datetime-like value {obj!r} is not canonically serializable; "
            "use an explicit in-game turn/date field instead of wall-clock time"
        )
    if isinstance(obj, uuid.UUID):
        raise NonCanonicalValueError(
            f"UUID value {obj!r} is not canonically serializable; use a stable string content ID"
        )
    raise TypeError(f"object of type {type(obj).__name__} is not JSON serializable: {obj!r}")


def canonical_dumps(data: Any) -> str:
    """Serialize `data` (plain JSON-compatible structures) canonically.

    `data` should already be plain `dict`/`list`/`str`/`int`/`float`/`bool`/`None`
    (e.g. the output of a Pydantic model's `.model_dump(mode="json")`), not a
    live domain object.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_reject_non_canonical,
    )


def canonical_hash(data: Any) -> str:
    """Convenience: a short hash of `canonical_dumps(data)`, useful in test failure messages."""
    import hashlib

    return hashlib.sha256(canonical_dumps(data).encode()).hexdigest()[:16]
