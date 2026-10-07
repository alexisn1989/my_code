"""R2 diagnosis: the release check's own measurement, run a FIXED 30 times against the installed archive.

    python3 -I budgets30.py --install <extracted, installed archive dir> --repo <repo root>
                            --runs 30 --out-dir <dir>

Each run: a fresh server process (the archive's own .venv/bin/mandate-gui, the README's run command)
on a fresh port with a fresh, empty save root; then the repository's real `scripts/measure_budgets.py
--base-url ...`, unmodified, whose own order is: warm-up + 20 new games, turn-0 payload reads, 40
empty-turn resolves, the read block (warm-up + 20 samples per endpoint, /api/scenarios last), THEN
save-as and 10 loads. Every run is retained whatever its exit status; the count is fixed in advance and
never extended. The server is stopped by the one PID this script launched, after checking that PID's
/proc cmdline and cwd.
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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_ready(base: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        try:
            with opener.open(f"{base}/api/scenarios", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"server at {base} never became ready")


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")}
    env["PATH"] = ":".join(p for p in env.get("PATH", "").split(":") if "/home/user/my_code" not in p)
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    install = args.install.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    log = []
    for index in range(args.runs):
        port = free_port()
        saves = args.out_dir / f"saves-{index:02d}"
        saves.mkdir()
        command = [".venv/bin/mandate-gui", "--frontend-dist", "dist", "--scenario-root", "scenarios",
                   "--port", str(port), "--save-root", str(saves)]
        server = subprocess.Popen(command, cwd=install, env=clean_env(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        entry: dict[str, object] = {"run": index, "port": port}
        log.append(entry)
        try:
            wait_ready(base)
            out = args.out_dir / f"run-{index:02d}.json"
            started = time.time()
            completed = subprocess.run(
                [sys.executable, str(args.repo / "scripts" / "measure_budgets.py"), "--base-url", base,
                 "--out-path", str(out), "--run-id", f"r2-{index:02d}"],
                capture_output=True, text=True, check=False,
            )
            entry.update({"exit": completed.returncode,
                          "seconds": round(time.time() - started, 1), "loadavg": os.getloadavg(),
                          "stderrTail": completed.stderr[-300:]})
            if out.exists():
                data = json.loads(out.read_text())
                read = data["results"]["read_projection_ms"]
                worst_endpoint = max(read["perEndpoint"], key=lambda p: read["perEndpoint"][p]["worst"])
                entry.update({"breaches": data["breaches"], "readWorst": read["worst"],
                              "readWorstEndpoint": worst_endpoint,
                              "scenarios": read["perEndpoint"]["/api/scenarios"]})
            print(json.dumps({k: entry.get(k) for k in ("run", "exit", "breaches", "readWorst", "readWorstEndpoint")}), flush=True)
        finally:
            pid = server.pid
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
            cwd = os.readlink(f"/proc/{pid}/cwd")
            if Path(cwd).resolve() != install or f"--port {port}" not in cmdline:
                raise SystemExit(f"refusing to signal pid {pid}: cwd={cwd} cmd={cmdline}")
            os.kill(pid, signal.SIGINT)
            server.wait(timeout=30)
            entry["serverExit"] = server.returncode
    (args.out_dir / "budgets30-log.json").write_text(json.dumps({"runs": args.runs, "log": log}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
