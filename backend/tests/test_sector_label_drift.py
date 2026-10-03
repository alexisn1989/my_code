"""Gate 4A3 UX-2: the browser's sector display names cover exactly the engine's sectors.

`sector_inactive` drivers carry only the raw `SectorCategory` value, and the turn result names the
sector through `SECTOR_LABEL` in `frontend/src/format/format.ts`. An unknown value falls back to the
generic driver label, so a sector added to the engine without a label would silently lose its name
in play. This test reads the map's keys from the source and pins them to the enum.
"""

from __future__ import annotations

import pathlib
import re

from app.simulation.state import SectorCategory

FORMAT_TS = (
    pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "format" / "format.ts"
)


def _label_keys() -> list[str]:
    source = FORMAT_TS.read_text(encoding="utf-8")
    start = source.index("export const SECTOR_LABEL")
    block = source[start : source.index("};", start)]
    return re.findall(r"^\s*([a-z_]+):\s*\"[^\"]+\",\s*$", block, flags=re.MULTILINE)


def test_sector_labels_equal_the_engine_sectors() -> None:
    keys = _label_keys()
    assert len(keys) == len(set(keys)), "a sector is labelled twice"
    assert set(keys) == {category.value for category in SectorCategory}


def test_the_block_is_actually_parsed() -> None:
    """Anti-vacuity: the regex must find every entry, not an empty or partial list."""
    assert len(_label_keys()) == len(SectorCategory) == 11
