"""R2 fix: time the YAML loader THE APPLICATION SELECTED, on ONE exported build (in-process).

Unlike the diagnosis's `phases.py` (kept unchanged as evidence), which calls `yaml.safe_load` by name,
this harness reads `app.simulation.scenario._SAFE_LOADER` -- the loader the build actually chose at
import -- records its identity, and times parsing with it. The pure-Python `SafeLoader` and libyaml's
`CSafeLoader` are timed alongside as controls, and the application's whole `load_scenario_text` is
timed too.

    python -I phases_selected.py --tree <export dir> --commit <sha> --iterations 200 --out <file.json>
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import statistics
import sys
import time
from pathlib import Path


def stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": len(samples),
        "median": round(statistics.median(samples), 4),
        "p95": round(ordered[int(round(0.95 * (len(ordered) - 1)))], 4),
        "max": round(ordered[-1], 4),
    }


def timed(fn, iterations: int) -> list[float]:  # type: ignore[no-untyped-def]
    out = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        out.append((time.perf_counter() - start) * 1000)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    tree = args.tree.resolve()
    backend = tree / "backend"
    sys.path.insert(0, str(backend))

    import yaml  # noqa: PLC0415
    import app  # noqa: PLC0415
    from app.simulation import scenario as scenario_module  # noqa: PLC0415

    app_file = Path(app.__file__).resolve()
    if not app_file.is_relative_to(backend):
        raise SystemExit(f"build identity: app imported from {app_file}, not from {backend}")
    selected = scenario_module._SAFE_LOADER
    selected_name = f"{selected.__module__}.{selected.__qualname__}"

    n = args.iterations
    per_file: dict[str, object] = {}
    for path in sorted((tree / "data" / "scenarios").glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        per_file[path.stem] = {
            "bytes": len(text.encode("utf-8")),
            "selected_loader_parse": stats(timed(lambda: yaml.load(text, Loader=selected), n)),  # noqa: S506
            "control_python_SafeLoader": stats(timed(lambda: yaml.load(text, Loader=yaml.SafeLoader), n)),
            "control_CSafeLoader": stats(timed(lambda: yaml.load(text, Loader=yaml.CSafeLoader), n)),  # noqa: S506
            "app_load_scenario_text": stats(
                timed(lambda: scenario_module.load_scenario_text(text, source=path.name), n)
            ),
        }

    record = {
        "commit": args.commit,
        "appFile": str(app_file),
        "selectedLoader": selected_name,
        "libyaml": bool(yaml.__with_libyaml__),
        "python": sys.version,
        "dependencies": {d: importlib.metadata.version(d) for d in
                         ("pyyaml", "pydantic", "pydantic-core", "fastapi", "starlette", "httpx")},
        "iterationsPerPhase": n,
        "perFile": per_file,
        "sumOfMedians": {
            key: round(sum(f[key]["median"] for f in per_file.values()), 3)  # type: ignore[index]
            for key in ("selected_loader_parse", "control_python_SafeLoader", "control_CSafeLoader",
                        "app_load_scenario_text")
        },
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
