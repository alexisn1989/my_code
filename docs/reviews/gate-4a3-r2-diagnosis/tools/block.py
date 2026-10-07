"""R2 diagnosis: one timed block of GET /api/scenarios against ONE exported build, in a fresh process.

Run with `-I` from outside the export:
    python -I block.py --tree <export dir> --commit <sha> --warmup 5 --n 50 --out <file.json>

The export's `backend/` is put first on `sys.path`, and the run ASSERTS that `app` was imported from
inside that export before timing anything, so a block can never silently measure the wrong build.
The request goes through FastAPI's TestClient on `create_app`, so routing, the security middleware,
the handler and response-model serialisation are all included; the network socket is not.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

DEPENDENCIES = ("pyyaml", "pydantic", "pydantic-core", "fastapi", "starlette", "httpx")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    tree = args.tree.resolve()
    backend = tree / "backend"
    sys.path.insert(0, str(backend))

    import app  # noqa: PLC0415 -- deliberately imported after the path is set
    from app.api.main import ApiSettings, create_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app_file = Path(app.__file__).resolve()
    if not app_file.is_relative_to(backend):
        raise SystemExit(f"build identity: app imported from {app_file}, not from {backend}")

    port = 48999
    with tempfile.TemporaryDirectory() as saves:
        settings = ApiSettings(
            port=port,
            save_root=Path(saves),
            scenario_root=tree / "data" / "scenarios",
            serve_spa=False,
        )
        client = TestClient(create_app(settings), base_url=f"http://127.0.0.1:{port}")
        for _ in range(args.warmup):
            response = client.get("/api/scenarios")
            if response.status_code != 200 or len(response.json()) != 3:
                raise SystemExit(f"unexpected response: {response.status_code} {response.text[:200]}")
        samples = []
        for _ in range(args.n):
            start = time.perf_counter()
            response = client.get("/api/scenarios")
            _ = response.content
            samples.append(round((time.perf_counter() - start) * 1000, 3))
            if response.status_code != 200:
                raise SystemExit(f"status {response.status_code}")

    ordered = sorted(samples)
    record = {
        "commit": args.commit,
        "appFile": str(app_file),
        "python": sys.version,
        "dependencies": {name: importlib.metadata.version(name) for name in DEPENDENCIES},
        "warmupDiscarded": args.warmup,
        "samplesMs": samples,
        "median": statistics.median(samples),
        "p95": ordered[int(round(0.95 * (len(ordered) - 1)))],
        "max": ordered[-1],
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
