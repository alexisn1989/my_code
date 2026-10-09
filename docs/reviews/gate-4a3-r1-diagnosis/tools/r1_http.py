"""R1 diagnosis: what a playtester meets, over HTTP, on the INSTALLED approved archive.

    python3 -I r1_http.py --install <installed archive dir> --path-reps 20 --worst-reps 10 --out <dir>

Every server is a fresh process of the archive's own `.venv/bin/mandate-gui` (the README run command)
on a fresh port; each is stopped by the ONE pid this script launched, after checking that pid's
/proc cmdline and cwd. Every repetition is retained; the counts are fixed in advance.

Part A -- the playtester path (`--path-reps`, each with a fresh, empty save root = the protocol's one
root per tester): start Valdrun, resolve 5 empty turns (each timed), save-as, list (timed), list
again (timed, warm), resolve 5 more (timed), save-as, list (timed); stop; restart on the SAME root
and list (timed: the cold start after a crash or restart), list again (warm); stop.

Part B -- 6c's worst case (`--worst-reps`): one save root holding 20 save-as checkpoints of one
Valdrun campaign at turns 2..40 (every second turn), built once; then, per repetition, a fresh server
on that root and its first listing (timed), then a second (warm).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def call(base: str, method: str, path: str, body: object | None = None) -> tuple[float, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with OPENER.open(request, timeout=120) as response:
        payload = response.read()
        status = response.status
    ms = round((time.perf_counter() - start) * 1000, 3)
    if status != 200:
        raise SystemExit(f"{method} {path} -> {status}")
    return ms, json.loads(payload)


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = ":".join(p for p in env.get("PATH", "").split(":") if "/home/user/my_code" not in p)
    return env


class Server:
    def __init__(self, install: Path, saves: Path) -> None:
        self.install = install
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [".venv/bin/mandate-gui", "--frontend-dist", "dist", "--scenario-root", "scenarios",
             "--port", str(self.port), "--save-root", str(saves)],
            cwd=install, env=clean_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(240):
            try:
                with OPENER.open(f"{self.base}/api/scenarios", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.25)
        self.stop()
        raise SystemExit("server never became ready")

    def stop(self) -> int:
        pid = self.proc.pid
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        cwd = os.readlink(f"/proc/{pid}/cwd")
        if Path(cwd).resolve() != self.install or f"--port {self.port}" not in cmdline:
            raise SystemExit(f"refusing to signal pid {pid}: cwd={cwd} cmd={cmdline}")
        os.kill(pid, signal.SIGINT)
        return self.proc.wait(timeout=30)


def resolve_empty(base: str) -> float:
    _, state = call(base, "GET", "/api/game/state")
    ms, _ = call(base, "POST", "/api/game/resolve",
                 {"revision": state["revision"], "campaign_id": state["campaign_id"], "decisions": []})
    return ms


def part_a(install: Path, root: Path, reps: int) -> list[dict[str, object]]:
    out = []
    for rep in range(reps):
        saves = root / f"a-saves-{rep:02d}"
        saves.mkdir()
        row: dict[str, object] = {"rep": rep}
        server = Server(install, saves)
        call(server.base, "POST", "/api/game/new", {"scenario_id": "decree_state"})
        row["resolve_turns_1_to_5_ms"] = [resolve_empty(server.base) for _ in range(5)]
        row["save_as_after_5_ms"], _ = call(server.base, "POST", "/api/game/save-as", {"display_name": "after 5"})
        row["list_after_first_save_ms"], listed = call(server.base, "GET", "/api/saves")
        row["saves_listed_after_first_save"] = len(listed)  # type: ignore[arg-type]
        row["list_warm_ms"], _ = call(server.base, "GET", "/api/saves")
        row["resolve_turns_6_to_10_ms"] = [resolve_empty(server.base) for _ in range(5)]
        row["save_as_after_10_ms"], _ = call(server.base, "POST", "/api/game/save-as", {"display_name": "after 10"})
        row["list_after_second_save_ms"], listed = call(server.base, "GET", "/api/saves")
        row["saves_listed_after_second_save"] = len(listed)  # type: ignore[arg-type]
        row["server_exit_first"] = server.stop()
        server = Server(install, saves)
        row["list_cold_after_restart_ms"], listed = call(server.base, "GET", "/api/saves")
        row["saves_listed_after_restart"] = len(listed)  # type: ignore[arg-type]
        row["all_loadable_after_restart"] = all(s["loadable"] for s in listed)  # type: ignore[union-attr,index]
        row["list_warm_after_restart_ms"], _ = call(server.base, "GET", "/api/saves")
        row["server_exit_second"] = server.stop()
        out.append(row)
        print(json.dumps({k: row[k] for k in ("rep", "list_after_first_save_ms", "list_cold_after_restart_ms")}),
              flush=True)
    return out


def part_b(install: Path, root: Path, reps: int) -> dict[str, object]:
    saves = root / "b-saves"
    saves.mkdir()
    server = Server(install, saves)
    call(server.base, "POST", "/api/game/new", {"scenario_id": "decree_state"})
    for turn in range(1, 41):
        resolve_empty(server.base)
        if turn % 2 == 0:
            call(server.base, "POST", "/api/game/save-as", {"display_name": f"turn {turn}"})
    build_exit = server.stop()
    files = sorted(p.name for p in saves.glob("*.json") if p.name != "index.json")
    runs = []
    for rep in range(reps):
        server = Server(install, saves)
        cold, listed = call(server.base, "GET", "/api/saves")
        warm, _ = call(server.base, "GET", "/api/saves")
        runs.append({"rep": rep, "cold_ms": cold, "warm_ms": warm, "saves_listed": len(listed),  # type: ignore[arg-type]
                     "all_loadable": all(s["loadable"] for s in listed),  # type: ignore[union-attr,index]
                     "server_exit": server.stop()})
        print(json.dumps(runs[-1]), flush=True)
    return {"save_files": len(files), "note": "20 save-as checkpoints at turns 2..40 plus the campaign's own autosave file",
            "build_server_exit": build_exit, "runs": runs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", type=Path, required=True)
    parser.add_argument("--path-reps", type=int, required=True)
    parser.add_argument("--worst-reps", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    install = args.install.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    probe = subprocess.run([str(install / ".venv/bin/python"), "-I", "-c",
                            "import app,sys,importlib.metadata as m;print(app.__file__);print(sys.version);"
                            "print({d:m.version(d) for d in ('pyyaml','pydantic','pydantic-core','fastapi','starlette')})"],
                           capture_output=True, text=True, check=True, env=clean_env()).stdout.splitlines()
    if not Path(probe[0]).resolve().is_relative_to(install / ".venv"):
        raise SystemExit(f"build identity: app imported from {probe[0]}")
    record = {"install": str(install), "appFile": probe[0], "python": probe[1], "dependencies": probe[2],
              "pathReps": args.path_reps, "worstReps": args.worst_reps}
    record["partA"] = part_a(install, args.out, args.path_reps)
    record["partB"] = part_b(install, args.out, args.worst_reps)
    (args.out / "r1-http.json").write_text(json.dumps(record, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
