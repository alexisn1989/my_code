"""Gate 4A3 UX-4c (U11): the portrait frame's edge is visible, computed from the palette itself.

The ruled design gives every portrait a `navy-950` tile with a 1px `gold-600` ring. The ring is what
must be seen (WCAG 2.2 SC 1.4.11, 3:1 for a graphical object) against the `navy-900` panel every
portrait sits on. This reads the hexes from `frontend/src/styles/tokens.css`, the classes from
`Portrait.tsx`, and the skin tones from `format/portrait.ts`, so a palette or class change that breaks
the claim fails here.

It also records the measurement behind the ruling: no tile token reaches 3:1 against all six skin
tones, so the frame does not claim to separate the face from its tile. The portrait is decorative;
the name is always text.

(A backend test because the frontend's test runner processes CSS imports as stylesheets and cannot
read `tokens.css` as text -- the same reason the other frontend drift guards live here.)
"""

from __future__ import annotations

import pathlib
import re

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
TOKENS = (FRONTEND / "styles" / "tokens.css").read_text(encoding="utf-8")


def _token(name: str) -> str:
    match = re.search(rf"--color-{name}:\s*(#[0-9a-fA-F]{{6}})", TOKENS)
    assert match is not None, name
    return match.group(1)


def _luminance(hex_colour: str) -> float:
    def channel(index: int) -> float:
        value = int(hex_colour[1 + 2 * index : 3 + 2 * index], 16) / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)


def _ratio(a: str, b: str) -> float:
    x, y = _luminance(a), _luminance(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _skins() -> list[str]:
    source = (FRONTEND / "format" / "portrait.ts").read_text(encoding="utf-8")
    block = source[
        source.index("export const PORTRAIT_SKIN = [") : source.index(
            "] as const;", source.index("PORTRAIT_SKIN")
        )
    ]
    return re.findall(r'"(#[0-9a-fA-F]{6})"', block)


def test_the_portrait_has_the_ruled_frame() -> None:
    source = (FRONTEND / "greybox" / "Portrait.tsx").read_text(encoding="utf-8")
    classes = re.search(r'className="([^"]*rounded-md[^"]*)"', source)
    assert classes is not None
    assert {"bg-navy-950", "ring-1", "ring-gold-600"} <= set(classes.group(1).split())


def test_the_ring_is_at_least_3_to_1_against_the_panel() -> None:
    measured = _ratio(_token("gold-600"), _token("navy-900"))
    assert measured >= 3
    assert round(measured, 2) == 4.16


def test_no_tile_token_reaches_3_to_1_on_every_skin() -> None:
    skins = _skins()
    assert len(skins) == 6, "anti-vacuity: all six skin tones were read"
    for name in ("navy-800", "navy-950", "charcoal-700"):
        assert min(_ratio(_token(name), skin) for skin in skins) < 3, name
    assert round(min(_ratio(_token("navy-950"), skin) for skin in skins), 2) == 1.77
