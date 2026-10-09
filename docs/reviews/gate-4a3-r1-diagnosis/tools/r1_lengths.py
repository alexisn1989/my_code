"""R1 diagnosis: the cost of validating ONE save, against its length, on ONE exported build (in-process).

    python -I r1_lengths.py --tree <export dir> --commit <sha> --calls 20 --out <file.json>
                            --profile-out <file.txt>

Builds one `decree_state` campaign through FastAPI's TestClient on the export's own `create_app`,
resolving EMPTY turns (the budget script's own `resolve_empty` payload) and saving at turns
1, 2, 5, 10, 20 and 40. For each save it times, over `--calls` calls after one discarded warm-up:

* `parse`: `decode_save_bytes` + `load_save_json` on the file's exact bytes;
* `validate`: `validate_history(save)` on the parsed save -- the step the listing memo exists to skip;
* `verdict`: the repository's own `_compute_verdict` on the raw bytes, i.e. exactly what one cold
  listing pays per unseen save (parse + current state + validate + terminal summary).

It also writes a same-thread cProfile of one 40-turn `validate_history`, top 25 by cumulative time.
The export's `backend/` is put first on `sys.path` and `app` is ASSERTED to come from it.
"""

from __future__ import annotations

import argparse
import cProfile
import importlib.metadata
import io
import json
import pstats
import statistics
import sys
import tempfile
import time
from pathlib import Path

LENGTHS = (1, 2, 5, 10, 20, 40)


def stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": len(samples),
        "median": round(statistics.median(samples), 3),
        "p95": round(ordered[int(round(0.95 * (len(ordered) - 1)))], 3),
        "max": round(ordered[-1], 3),
    }


def timed(fn, calls: int) -> list[float]:  # type: ignore[no-untyped-def]
    fn()  # warm-up, discarded
    out = []
    for _ in range(calls):
        start = time.perf_counter()
        fn()
        out.append((time.perf_counter() - start) * 1000)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--calls", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile-out", type=Path, required=True)
    args = parser.parse_args()

    tree = args.tree.resolve()
    backend = tree / "backend"
    sys.path.insert(0, str(backend))

    import app  # noqa: PLC0415
    from app.api.main import ApiSettings, create_app  # noqa: PLC0415
    from app.api.save_registry import SaveRepository  # noqa: PLC0415
    from app.simulation.history import validate_history  # noqa: PLC0415
    from app.simulation.save_format import load_save_json  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app_file = Path(app.__file__).resolve()
    if not app_file.is_relative_to(backend):
        raise SystemExit(f"build identity: app imported from {app_file}, not from {backend}")
    from app.api import save_registry as registry_module  # noqa: PLC0415

    decode = registry_module.decode_save_bytes

    per_length: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as saves_dir:
        saves = Path(saves_dir)
        port = 48996
        client = TestClient(
            create_app(ApiSettings(port=port, save_root=saves, scenario_root=tree / "data" / "scenarios",
                                   serve_spa=False)),
            base_url=f"http://127.0.0.1:{port}",
        )
        assert client.post("/api/game/new", json={"scenario_id": "decree_state"}).status_code == 200
        saved: dict[int, str] = {}
        turn = 0
        for target in LENGTHS:
            while turn < target:
                state = client.get("/api/game/state").json()
                response = client.post(
                    "/api/game/resolve",
                    json={"revision": state["revision"], "campaign_id": state["campaign_id"], "decisions": []},
                )
                assert response.status_code == 200, response.text[:300]
                turn += 1
            response = client.post("/api/game/save-as", json={"display_name": f"R1 length {target}"})
            assert response.status_code == 200, response.text[:300]
            saved[target] = response.json()["save_id"]

        repository = SaveRepository(saves)
        for target, save_id in saved.items():
            path = saves / f"{save_id}.json"
            raw = path.read_bytes()
            parsed = load_save_json(decode(raw, path), source=f"save:{save_id}")
            problems = validate_history(parsed)
            if problems:
                raise SystemExit(f"save at turn {target} fails validation: {problems}")
            per_length[str(target)] = {
                "turn": parsed.current_state().turn,
                "entries": len(parsed.entries),
                "bytes": len(raw),
                "parse": stats(timed(lambda: load_save_json(decode(raw, path), source="s"), args.calls)),
                "validate": stats(timed(lambda: validate_history(parsed), args.calls)),
                "verdict": stats(timed(lambda: repository._compute_verdict(raw, path, save_id), args.calls)),
            }

        longest = load_save_json(decode((saves / f"{saved[40]}.json").read_bytes(), saves / "x"), source="s")
        validate_history(longest)  # warm-up
        profiler = cProfile.Profile()
        profiler.enable()
        validate_history(longest)
        profiler.disable()
        buffer = io.StringIO()
        buffer.write(f"app: {app_file}\none validate_history of a {len(longest.entries)}-entry save\n\n")
        pstats.Stats(profiler, stream=buffer).sort_stats("cumulative").print_stats(25)
        args.profile_out.write_text(buffer.getvalue())

    lengths = [int(k) for k in per_length]
    medians = [per_length[str(k)]["verdict"]["median"] for k in lengths]  # type: ignore[index]
    mean_x, mean_y = statistics.mean(lengths), statistics.mean(medians)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(lengths, medians)) / sum(
        (x - mean_x) ** 2 for x in lengths
    )
    record = {
        "commit": args.commit,
        "appFile": str(app_file),
        "python": sys.version,
        "dependencies": {d: importlib.metadata.version(d) for d in
                         ("pyyaml", "pydantic", "pydantic-core", "fastapi", "starlette", "httpx")},
        "callsPerMeasurement": args.calls,
        "perLength": per_length,
        "verdictMedianSlopeMsPerTurn": round(slope, 3),
        "verdictMedianInterceptMs": round(mean_y - slope * mean_x, 3),
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
