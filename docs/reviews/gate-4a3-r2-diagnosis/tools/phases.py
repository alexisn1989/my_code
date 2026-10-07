"""R2 diagnosis: where one GET /api/scenarios spends its time, on ONE exported build (in-process).

    python -I phases.py --tree <export dir> --commit <sha> --iterations 200 --out <file.json>
                        --profile-out <file.txt> --gc-calls 300

1. Phase breakdown per scenario file: read, yaml.safe_load, ScenarioDefinition.model_validate,
   _to_game_state (state construction + invariants), check_invariants alone (a SUBSET of the
   previous phase, reported separately), build_dashboard, and the ScenarioSummary built and
   serialised. Each phase is timed over `--iterations` on already-produced inputs.
2. The C loader (diagnostic only): yaml.load(text, Loader=yaml.CSafeLoader) timed on the same texts,
   and its output compared with safe_load's (`==`). This proves agreement for THESE files only.
3. cProfile of one full request through TestClient(create_app(...)), top 25 by cumulative time.
4. GC, correlation only: a gc.callbacks hook records every collection (generation, duration) during
   `--gc-calls` timed requests; each request is marked with the collections that overlapped it.
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import importlib.metadata
import io
import json
import pstats
import statistics
import sys
import tempfile
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
    parser.add_argument("--gc-calls", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile-out", type=Path, required=True)
    args = parser.parse_args()

    tree = args.tree.resolve()
    backend = tree / "backend"
    sys.path.insert(0, str(backend))

    import yaml  # noqa: PLC0415
    import app  # noqa: PLC0415
    from app.api.main import ApiSettings, create_app  # noqa: PLC0415
    from app.api.projections import ScenarioSummary, build_dashboard  # noqa: PLC0415
    from app.simulation import scenario as scenario_module  # noqa: PLC0415
    from app.simulation.invariants import check_invariants  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app_file = Path(app.__file__).resolve()
    if not app_file.is_relative_to(backend):
        raise SystemExit(f"build identity: app imported from {app_file}, not from {backend}")

    scenario_root = tree / "data" / "scenarios"
    files = sorted(scenario_root.glob("*.yaml"))
    n = args.iterations
    per_file: dict[str, object] = {}
    loader_equal: dict[str, bool] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
        definition = scenario_module.ScenarioDefinition.model_validate(raw)
        state = scenario_module._to_game_state(str(path), definition)
        dashboard = build_dashboard(state, None)
        c_raw = yaml.load(text, Loader=yaml.CSafeLoader)  # noqa: S506 -- CSafeLoader is the safe loader
        loader_equal[path.stem] = c_raw == raw

        def summary() -> str:
            return ScenarioSummary(
                scenario_id=path.stem,
                display_name=dashboard.country_name,
                government_form=dashboard.government_form,
                election_interval_label="x",
                starting_legitimacy_text=dashboard.concerns.legitimacy.headline,
                is_showcase=False,
            ).model_dump_json()

        per_file[path.stem] = {
            "bytes": len(text.encode("utf-8")),
            "read": stats(timed(lambda: path.read_text(encoding="utf-8"), n)),
            "yaml_safe_load": stats(timed(lambda: yaml.safe_load(text), n)),
            "yaml_CSafeLoader": stats(timed(lambda: yaml.load(text, Loader=yaml.CSafeLoader), n)),  # noqa: S506
            "model_validate": stats(timed(lambda: scenario_module.ScenarioDefinition.model_validate(raw), n)),
            "to_game_state": stats(timed(lambda: scenario_module._to_game_state(str(path), definition), n)),
            "check_invariants_subset_of_to_game_state": stats(timed(lambda: check_invariants(state), n)),
            "build_dashboard": stats(timed(lambda: build_dashboard(state, None), n)),
            "summary_build_and_serialise": stats(timed(summary, n)),
        }

    with tempfile.TemporaryDirectory() as saves:
        port = 48998
        settings = ApiSettings(port=port, save_root=Path(saves), scenario_root=scenario_root, serve_spa=False)
        client = TestClient(create_app(settings), base_url=f"http://127.0.0.1:{port}")
        for _ in range(5):
            client.get("/api/scenarios")

        profiler = cProfile.Profile()
        profiler.enable()
        client.get("/api/scenarios")
        profiler.disable()
        buffer = io.StringIO()
        pstats.Stats(profiler, stream=buffer).sort_stats("cumulative").print_stats(25)
        args.profile_out.write_text(buffer.getvalue())

        events: list[dict[str, float]] = []
        open_starts: dict[int, float] = {}

        def hook(phase: str, info: dict[str, int]) -> None:
            now = time.perf_counter()
            if phase == "start":
                open_starts[info["generation"]] = now
            else:
                start = open_starts.pop(info["generation"], now)
                events.append({"generation": info["generation"], "start": start, "end": now})

        gc.callbacks.append(hook)
        calls = []
        try:
            for _ in range(args.gc_calls):
                start = time.perf_counter()
                client.get("/api/scenarios").content  # noqa: B018
                end = time.perf_counter()
                calls.append((start, end))
        finally:
            gc.callbacks.remove(hook)

    marked = []
    for start, end in calls:
        overlapping = [e for e in events if e["start"] < end and e["end"] > start]
        marked.append({
            "ms": round((end - start) * 1000, 3),
            "gen2": any(e["generation"] == 2 for e in overlapping),
            "gcMsInCall": round(sum(min(e["end"], end) - max(e["start"], start) for e in overlapping) * 1000, 3),
        })
    with_gen2 = [c["ms"] for c in marked if c["gen2"]]
    without_gen2 = [c["ms"] for c in marked if not c["gen2"]]
    slowest = sorted(marked, key=lambda c: c["ms"], reverse=True)[: max(1, len(marked) // 20)]

    record = {
        "commit": args.commit,
        "appFile": str(app_file),
        "python": sys.version,
        "dependencies": {d: importlib.metadata.version(d) for d in
                         ("pyyaml", "pydantic", "pydantic-core", "fastapi", "starlette", "httpx")},
        "libyaml": bool(yaml.__with_libyaml__),
        "iterationsPerPhase": n,
        "perFile": per_file,
        "cSafeLoaderEqualsSafeLoad": loader_equal,
        "gc": {
            "calls": len(marked),
            "collections": {g: sum(1 for e in events if e["generation"] == g) for g in (0, 1, 2)},
            "callsOverlappingGen2": len(with_gen2),
            "withGen2": stats(with_gen2) if with_gen2 else None,
            "withoutGen2": stats(without_gen2) if without_gen2 else None,
            "slowest5PercentWithGen2": sum(1 for c in slowest if c["gen2"]),
            "slowest5PercentCount": len(slowest),
            "calls_detail": marked,
        },
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
