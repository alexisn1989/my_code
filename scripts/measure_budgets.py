#!/usr/bin/env python3
"""Measure the section 5 budgets over real HTTP (Gate 4A3 Commit 6).

No test in the repository asserted an API latency or a payload size before this. Each budget has
exactly ONE stop number (Gate 4A3 plan, section 5): the WORST observed sample is compared with the STOP
threshold and fails the run; the MEDIAN is reported against the target and never fails it.

Method, stated so a second person gets the same kind of number:
* latency is client-side wall clock over loopback (`time.perf_counter`), request sent to body read;
* one warm-up request per endpoint is made and DISCARDED before any sample;
* resolve latency comes from one fresh `decree_state` campaign resolved with empty decision sets to
  turn 40 -- the scenario the frozen plan's own section 2.2 baseline used, and one measured to reach
  turn 45 without concluding, so turn 40 is an ordinary turn and not a conclusion;
* the save/load row saves the 40-turn campaign and loads it back ten times; loading runs
  `validate_history`, which re-validates, re-serialises and re-hashes every stored turn and reconciles
  it (it does not re-resolve turns), so it is the expensive path by design;
* the bundle row is enforced by `npm run check:bundle`, and the interaction row by the packaged
  Playwright spec; neither is measured here.

`--base-url` attaches to a running instance (the packaged one, in `verify_release.py`); otherwise this
starts `mandate-gui` from the active environment against the repository's scenarios. Standard library
only. Writes `docs/reviews/<name>.json` when `--out` is given, or exactly `--out-path` when that is
given; either file is created exclusively, so an existing report is never overwritten. `--run-id` is
written into the record so a caller can prove the report it reads came from the run it started.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = REPO_ROOT / "docs" / "reviews"
#: An artifact name: lowercase, digits, dots and dashes, no path separator, no `..`, no `.json`.
SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*")
KIB = 1024

# (target, STOP) in milliseconds or bytes. STOP is the only number that fails the run.
BUDGETS = {
    "new_game_ms": (150, 300),
    "resolve_turn_le_20_ms": (250, 500),
    "resolve_turn_21_to_40_ms": (400, 800),
    "read_projection_ms": (100, 200),
    "load_validate_40_turn_save_ms": (500, 1000),
    "projection_payload_bytes": (100 * KIB, 200 * KIB),
}

READ_ONLY = (
    "/api/game/state",
    "/api/game/map/strategic",
    "/api/game/decision-options",
    "/api/game/military",
    "/api/game/history",
    "/api/game/history/40",
    "/api/saves",
    "/api/scenarios",
)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(base: str, method: str, path: str, body: object | None = None) -> tuple[float, bytes]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base}{path}", data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    started = time.perf_counter()
    try:
        with _OPENER.open(request, timeout=60) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} -> {error.code}: {error.read()[:300]!r}") from None
    return (time.perf_counter() - started) * 1000, payload


def summary(samples: list[float]) -> dict[str, float]:
    return {
        "n": len(samples),
        "median": round(statistics.median(samples), 2),
        "worst": round(max(samples), 2),
    }


def resolve_empty(base: str) -> float:
    _, state_body = call(base, "GET", "/api/game/state")
    state = json.loads(state_body)
    ms, _ = call(
        base,
        "POST",
        "/api/game/resolve",
        {"revision": state["revision"], "campaign_id": state["campaign_id"], "decisions": []},
    )
    return ms


def measure(base: str) -> dict[str, object]:
    results: dict[str, object] = {}

    call(base, "POST", "/api/game/new", {"scenario_id": "decree_state"})  # warm-up, discarded
    new_game = [
        call(base, "POST", "/api/game/new", {"scenario_id": "decree_state"})[0] for _ in range(20)
    ]
    results["new_game_ms"] = summary(new_game)

    payloads: dict[str, int] = {}
    for path in READ_ONLY:
        if path.endswith("/40"):
            continue
        payloads[f"turn 0 {path}"] = len(call(base, "GET", path)[1])

    resolve_early = [resolve_empty(base) for _ in range(20)]
    resolve_late = [resolve_empty(base) for _ in range(20)]
    results["resolve_turn_le_20_ms"] = summary(resolve_early)
    results["resolve_turn_21_to_40_ms"] = summary(resolve_late)

    state = json.loads(call(base, "GET", "/api/game/state")[1])
    if state["turn"] != 40 or state.get("terminal") is not None:
        raise SystemExit(
            f"expected an ordinary turn 40, got turn {state['turn']} terminal={state.get('terminal')}"
        )

    reads: list[float] = []
    per_endpoint: dict[str, dict[str, float]] = {}
    for path in READ_ONLY:
        call(base, "GET", path)  # warm-up, discarded
        samples = []
        for _ in range(20):
            ms, body = call(base, "GET", path)
            samples.append(ms)
            payloads[f"turn 40 {path}"] = len(body)
        per_endpoint[path] = summary(samples)
        reads.extend(samples)
    results["read_projection_ms"] = {**summary(reads), "perEndpoint": per_endpoint}

    _, saved = call(base, "POST", "/api/game/save-as", {"display_name": "Budget run turn 40"})
    save_id = json.loads(saved)["save_id"]
    call(base, "POST", "/api/game/load", {"save_id": save_id})  # warm-up, discarded
    loads = [call(base, "POST", "/api/game/load", {"save_id": save_id})[0] for _ in range(10)]
    results["load_validate_40_turn_save_ms"] = summary(loads)

    largest = max(payloads, key=payloads.__getitem__)
    results["projection_payload_bytes"] = {
        "worst": payloads[largest],
        "median": statistics.median(payloads.values()),
        "largest": largest,
        "perResponse": payloads,
    }
    return results


def verdicts(results: dict[str, object]) -> tuple[list[str], list[str]]:
    report, breaches = [], []
    for key, (target, stop) in BUDGETS.items():
        row = results[key]
        assert isinstance(row, dict)
        worst, median = row["worst"], row["median"]
        state = "OK" if worst <= stop else "STOP"
        report.append(
            f"{key:34} median {median:>10} (target {target:>7})   worst {worst:>10} (STOP {stop:>7})  {state}"
        )
        if worst > stop:
            breaches.append(key)
    return report, breaches


def start_local(tmp: Path) -> tuple[subprocess.Popen[bytes], str]:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    dist = tmp / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>\n")
    proc = subprocess.Popen(
        [
            str(Path(sys.executable).parent / "mandate-gui"),
            "--port",
            str(port),
            "--frontend-dist",
            str(dist),
            "--scenario-root",
            str(REPO_ROOT / "data" / "scenarios"),
            "--save-root",
            str(tmp / "saves"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            call(base, "GET", "/api/scenarios")
            return proc, base
        except (OSError, SystemExit):
            time.sleep(0.25)
    proc.kill()
    raise SystemExit("the local server never became ready")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--out", default=None, help="write docs/reviews/<out>.json")
    parser.add_argument("--out-path", type=Path, default=None, help="write exactly this file")
    parser.add_argument("--run-id", default=None, help="recorded as runId")
    args = parser.parse_args(argv)
    if args.out is not None and args.out_path is not None:
        parser.error("pass --out or --out-path, not both")
    target: Path | None = None
    if args.out is not None:
        if not SAFE_NAME.fullmatch(args.out) or args.out.endswith(".json") or ".." in args.out:
            parser.error(f"unsafe --out name: {args.out!r}")
        target = REVIEWS_DIR / f"{args.out}.json"
    elif args.out_path is not None:
        if not args.out_path.is_absolute():
            parser.error("--out-path must be absolute")
        target = args.out_path
    proc = None
    with tempfile.TemporaryDirectory(prefix="mandate-budgets-") as tmp:
        if args.base_url:
            base = args.base_url.rstrip("/")
        else:
            proc, base = start_local(Path(tmp))
        try:
            results = measure(base)
        finally:
            if proc is not None:
                proc.terminate()
                proc.wait(timeout=15)
    report, breaches = verdicts(results)
    print("\n".join(report))
    record = {
        "method": __doc__.split("Method, stated", 1)[1].split("`--base-url`", 1)[0].strip(),
        "budgets": {k: {"target": t, "stop": s} for k, (t, s) in BUDGETS.items()},
        "results": results,
        "breaches": breaches,
    }
    if args.run_id is not None:
        record["runId"] = args.run_id
    if target is not None:
        # "x": exclusive creation. An existing report -- committed evidence, or another run's -- is
        # never overwritten; the run fails instead.
        with target.open("x") as handle:
            handle.write(json.dumps(record, indent=2) + "\n")
    if breaches:
        print(f"STOP: {', '.join(breaches)} past threshold", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
