"""Strategic Military Map Gate M0 commit 8 -- the sec.10.1 structural presentation-boundary proof.

Mirrors `test_legislative_neutrality.py`'s AST-based module scans: no module under
`app/simulation/` OTHER THAN `geography.py` and `state.py` may reference `TheaterPresentation`,
`CountryShapeState`, `centroid_x`, `centroid_y`, `label_anchor` or `polygon`. Those are the map's
presentation-only vocabulary (`TheaterPresentation`'s own docstring, `app/simulation/state.py`):
read by the map projection and by the renderer, by NO formula and by no validator that decides
legality.

Checked against the real parsed AST -- every `Name`/`Attribute` identifier and every import alias
-- so a reference added inside a function body, a decorator, an f-string interpolation
(`f"{centroid_x}"`, which IS an `ast.Name` node inside the f-string's AST) or under
`TYPE_CHECKING` is caught just the same. A plain-text mention inside a comment or a docstring
literal is deliberately NOT flagged: those are not a channel through which a formula could read
the value, only documentation, and `app/simulation/invariants.py` already mentions
`CountryShapeState` by name in exactly that harmless way (an error-message string and a docstring
cross-reference), which this file pins as legitimate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app.simulation as simulation_package

FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "TheaterPresentation",
        "CountryShapeState",
        "centroid_x",
        "centroid_y",
        "label_anchor",
        "polygon",
    }
)

EXEMPT_MODULE_NAMES = frozenset({"geography.py", "state.py"})


def _simulation_modules() -> list[Path]:
    package_dir = Path(simulation_package.__file__).parent
    return sorted(
        path
        for path in package_dir.glob("*.py")
        if path.name != "__init__.py" and path.name not in EXEMPT_MODULE_NAMES
    )


def _referenced_forbidden_identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_IDENTIFIERS:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_IDENTIFIERS:
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name in FORBIDDEN_IDENTIFIERS or name in FORBIDDEN_IDENTIFIERS:
                    found.add(alias.name)
        elif isinstance(node, ast.keyword) and node.arg in FORBIDDEN_IDENTIFIERS:
            found.add(node.arg)
    return found


def test_covers_a_real_nonempty_set_of_simulation_modules_other_than_geography_and_state() -> None:
    modules = _simulation_modules()
    names = {path.name for path in modules}
    assert len(modules) > 15
    assert "geography.py" not in names
    assert "state.py" not in names
    assert "reconciliation.py" in names
    assert "invariants.py" in names
    assert "history.py" in names


def test_no_module_other_than_geography_and_state_references_presentation_vocabulary() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _simulation_modules():
        found = _referenced_forbidden_identifiers(path)
        if found:
            offenders[path.name] = found
    assert offenders == {}, (
        "presentation-only identifiers leaked into simulation modules other than "
        f"geography.py/state.py: {offenders}"
    )


def test_invariants_module_mentions_countryshapestate_only_as_harmless_plain_text() -> None:
    """Positive confirmation that the scan above is real, not vacuously passing because it
    mis-parses `invariants.py`: the module's raw source DOES contain the literal text
    "CountryShapeState" (a docstring cross-reference and an f-string error message), and the AST
    scan correctly finds zero real identifier references there -- proving the distinction between
    "mentioned in text" and "referenced in code" is actually being drawn, not just assumed."""
    invariants_path = Path(simulation_package.__file__).parent / "invariants.py"
    assert "CountryShapeState" in invariants_path.read_text(encoding="utf-8")
    assert _referenced_forbidden_identifiers(invariants_path) == set()


def test_the_scan_actually_fires_on_a_real_reference_self_check() -> None:
    """Guards against the scan silently doing nothing: a probe module that genuinely imports and
    uses `TheaterPresentation` and reads `centroid_x` must be caught."""
    import tempfile

    probe_source = (
        "from app.simulation.state import TheaterPresentation\n\n"
        "def read(p: TheaterPresentation) -> int:\n"
        "    return p.centroid_x\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as handle:
        handle.write(probe_source)
        probe_path = Path(handle.name)
    try:
        found = _referenced_forbidden_identifiers(probe_path)
        assert found == {"TheaterPresentation", "centroid_x"}
    finally:
        probe_path.unlink()
