"""Gate 4A3 M-2: the Parliament screen's role labels cover exactly the engine's government roles.

Each bloc row names its party's formal role through `GOVERNMENT_ROLE_LABEL` in
`frontend/src/format/parliament.ts`, and orders rows by `GOVERNMENT_ROLE_ORDER`. An unknown role
falls back to neutral words, so a role added to the engine without a label would silently lose its
name in play. This test reads both maps' keys from the source and pins them to the enum.
"""

from __future__ import annotations

import pathlib
import re

from app.simulation.legislature import GovernmentRole

PARLIAMENT_TS = (
    pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "format" / "parliament.ts"
)


def _keys(name: str) -> list[str]:
    source = PARLIAMENT_TS.read_text(encoding="utf-8")
    start = source.index(f"export const {name}")
    block = source[start : source.index("};", start)]
    return re.findall(r"^\s*([a-z_]+):\s*(?:\"[^\"]+\"|\d+),\s*$", block, flags=re.MULTILINE)


def test_role_labels_equal_the_engine_roles() -> None:
    keys = _keys("GOVERNMENT_ROLE_LABEL")
    assert len(keys) == len(set(keys)), "a role is labelled twice"
    assert set(keys) == {role.value for role in GovernmentRole}


def test_role_order_covers_the_engine_roles() -> None:
    assert set(_keys("GOVERNMENT_ROLE_ORDER")) == {role.value for role in GovernmentRole}


def test_the_blocks_are_actually_parsed() -> None:
    """Anti-vacuity: the regex must find every entry, not an empty or partial list."""
    assert len(_keys("GOVERNMENT_ROLE_LABEL")) == len(GovernmentRole) == 3
    assert len(_keys("GOVERNMENT_ROLE_ORDER")) == 3
