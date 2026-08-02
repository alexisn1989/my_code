"""AST-based check that the deterministic engine stays deterministic.

Product spec §5.1: "Do not call the system clock or a global random generator
from simulation functions." This is checked structurally, not by convention:
every module under `app/core` and `app/simulation` is parsed and walked, and
the test fails if any module other than `app/core/rng.py` imports `random`,
or if any of them import `time` or call a wall-clock accessor
(`datetime.now`/`utcnow`, `date.today`).

Imports inside an `if TYPE_CHECKING:` block are exempt: they are erased by
the time the interpreter runs (doubly so under `from __future__ import
annotations`, PEP 563, which this codebase uses throughout) and so can never
introduce runtime non-determinism — they exist purely for mypy. This lets
`simulation/phases.py` annotate `PhaseContext.rng()` as returning
`random.Random` without actually importing `random` at runtime.

`app/cli.py` is intentionally out of scope — it is the I/O entry point, not
part of the pure engine, and may reasonably use wall-clock time for logging.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
RNG_MODULE_PATH = (APP_DIR / "core" / "rng.py").resolve()
DETERMINISTIC_PACKAGE_DIRS = (APP_DIR / "core", APP_DIR / "simulation")

_TIME_MODULES = {"time"}
_TIME_ATTR_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today")}


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for package_dir in DETERMINISTIC_PACKAGE_DIRS:
        files.extend(sorted(package_dir.rglob("*.py")))
    return files


def _is_type_checking_guard(test: ast.expr) -> bool:
    """True for `if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:`."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _walk_excluding_type_checking(node: ast.AST) -> list[ast.AST]:
    """Like `ast.walk`, but does not descend into `if TYPE_CHECKING:` bodies."""
    collected: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.If) and _is_type_checking_guard(child.test):
            continue
        collected.append(child)
        collected.extend(_walk_excluding_type_checking(child))
    return collected


def _find_problems(path: Path) -> tuple[list[str], list[str]]:
    """Return `(random_problems, time_problems)` found in one file."""
    random_problems: list[str] = []
    time_problems: list[str] = []
    is_rng_module = path.resolve() == RNG_MODULE_PATH
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in _walk_excluding_type_checking(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "random" and not is_rng_module:
                    random_problems.append(f"{path}:{node.lineno}: `import random`")
                if alias.name in _TIME_MODULES:
                    time_problems.append(f"{path}:{node.lineno}: `import {alias.name}`")
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "random" and not is_rng_module:
                random_problems.append(f"{path}:{node.lineno}: `from random import ...`")
            if node.module in _TIME_MODULES:
                time_problems.append(f"{path}:{node.lineno}: `from {node.module} import ...`")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name) and (value.id, node.func.attr) in _TIME_ATTR_CALLS:
                time_problems.append(f"{path}:{node.lineno}: `{value.id}.{node.func.attr}()`")

    return random_problems, time_problems


def test_random_module_is_only_imported_by_core_rng() -> None:
    problems: list[str] = []
    for path in _iter_py_files():
        random_problems, _ = _find_problems(path)
        problems.extend(random_problems)
    assert problems == [], (
        "only app/core/rng.py may import `random`; all randomness in the "
        "deterministic engine must go through app.core.rng.derive_rng. "
        "Violations:\n" + "\n".join(problems)
    )


def test_deterministic_packages_do_not_touch_wall_clock_time() -> None:
    problems: list[str] = []
    for path in _iter_py_files():
        _, time_problems = _find_problems(path)
        problems.extend(time_problems)
    assert problems == [], (
        "app/core and app/simulation must not read wall-clock time; turn "
        "resolution must be a pure function of (state, decisions). "
        "Violations:\n" + "\n".join(problems)
    )


def test_the_check_itself_detects_a_planted_violation(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import random\nimport time\n", encoding="utf-8")

    random_problems, time_problems = _find_problems(bad_file)

    assert random_problems, "the AST check failed to catch a planted `import random`"
    assert time_problems, "the AST check failed to catch a planted `import time`"


def test_the_check_permits_random_inside_core_rng() -> None:
    random_problems, _ = _find_problems(RNG_MODULE_PATH)
    assert random_problems == [], "core/rng.py is the one module allowed to import random"


def test_type_checking_guarded_random_import_is_exempt(tmp_path: Path) -> None:
    guarded_file = tmp_path / "type_only.py"
    guarded_file.write_text(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import random\n",
        encoding="utf-8",
    )

    random_problems, _ = _find_problems(guarded_file)

    assert random_problems == [], (
        "an import that only executes for the type checker can never run at "
        "runtime and so cannot introduce non-determinism"
    )
