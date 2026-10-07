"""R2 diagnosis: a same-thread cProfile of what `list_scenarios` does per request, on ONE exported build.

The TestClient profile (phases.py) cannot see the handler: FastAPI runs this sync route on a worker
thread, so that profile shows only the client waiting. This profiles the handler's own per-file work
-- load_scenario_file then build_dashboard(state, None), for every scenario file -- in the calling
thread, 20 times, top 25 by cumulative time.

    python -I profile_handler.py --tree <export dir> --out <file.txt>
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    tree = args.tree.resolve()
    backend = tree / "backend"
    sys.path.insert(0, str(backend))

    import app  # noqa: PLC0415
    from app.api.projections import build_dashboard  # noqa: PLC0415
    from app.content.scenarios import load_scenario_file  # noqa: PLC0415

    if not Path(app.__file__).resolve().is_relative_to(backend):
        raise SystemExit(f"build identity: app imported from {app.__file__}")
    files = sorted((tree / "data" / "scenarios").glob("*.yaml"))

    def handler_work() -> None:
        for path in files:
            build_dashboard(load_scenario_file(path), None)

    handler_work()  # warm-up
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(20):
        handler_work()
    profiler.disable()
    buffer = io.StringIO()
    buffer.write(f"app: {app.__file__}\n20 x handler work over {[p.name for p in files]}\n\n")
    pstats.Stats(profiler, stream=buffer).sort_stats("cumulative").print_stats(25)
    args.out.write_text(buffer.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main())
