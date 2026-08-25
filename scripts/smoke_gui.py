#!/usr/bin/env python3
"""Gate 4A2 closeout -- mandate testing item 22: a real full-stack smoke path
through `mandate-gui`, permanent in CI, not a one-time manual verification.

Launches the REAL `mandate-gui` process (not a `TestClient`, not an in-process
FastAPI app) against the real built frontend, waits for it with a deterministic
bounded-interval readiness probe (never a blind `sleep`), confirms the SPA is
served, then drives all three shipped scenarios through decision-options,
preview, resolve, history, save-as, and load over real HTTP. Tears the process
down in `finally` and uses an isolated, temporary `--save-root` so it leaves no
orphan process and no leftover save on disk.

Python standard library only -- `urllib.request` for HTTP, `subprocess` for
the process, `socket` to pick a free port, `tempfile`/`shutil` for the
isolated save root -- no new dependency, backend or frontend.

Usage: `python scripts/smoke_gui.py` from the repository root (or anywhere;
paths are resolved relative to this file). Exits non-zero on any broken
contract, with the specific assertion that failed printed to stderr.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

READINESS_TIMEOUT_SECONDS = 30.0
READINESS_POLL_INTERVAL_SECONDS = 0.2
REQUEST_TIMEOUT_SECONDS = 10.0

ALL_SCENARIO_IDS = ("decree_state", "deficit_demo", "tiny_valid")


class SmokeFailure(Exception):
    """One assertion in the smoke path failed."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _request(
    base_url: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    url = f"{base_url}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    text = raw.decode("utf-8") if raw else ""
    parsed: Any = json.loads(text) if text else None
    return status, parsed


def _wait_until_ready(base_url: str, process: subprocess.Popen[bytes]) -> None:
    """Deterministic bounded-interval polling against a monotonic deadline --
    never a blind fixed `sleep`. Succeeds the instant /api/scenarios first
    returns 200; fails fast if the process exits before that happens."""
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeFailure(
                f"mandate-gui exited early with code {process.returncode} before becoming ready"
            )
        try:
            status, _ = _request(base_url, "/api/scenarios")
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(READINESS_POLL_INTERVAL_SECONDS)
    raise SmokeFailure(f"mandate-gui did not become ready within {READINESS_TIMEOUT_SECONDS}s")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _smoke_one_scenario(base_url: str, scenario_id: str) -> None:
    status, dashboard = _request(base_url, "/api/game/new", method="POST", body={"scenario_id": scenario_id})
    _assert(status == 200, f"[{scenario_id}] /api/game/new: expected 200, got {status}: {dashboard}")
    revision = dashboard["revision"]

    status, options = _request(base_url, "/api/game/decision-options")
    _assert(status == 200, f"[{scenario_id}] /api/game/decision-options: expected 200, got {status}")
    _assert("opening_capital" in options, f"[{scenario_id}] decision-options missing opening_capital")

    # Gate 4A3A: the server-authored policy-card catalog must round-trip through
    # a REAL running process and REAL HTTP JSON encoding, not just a TestClient
    # -- this is the one place that would catch a serialization bug a pytest
    # TestClient call could miss (e.g. an enum that doesn't survive real JSON).
    cards = options.get("policy_cards")
    _assert(isinstance(cards, list) and len(cards) > 0, f"[{scenario_id}] decision-options has no policy_cards")
    for card in cards:
        _assert("card_id" in card, f"[{scenario_id}] a policy card is missing card_id")
        _assert("category" in card, f"[{scenario_id}] card {card.get('card_id')} is missing category")
        _assert("available" in card, f"[{scenario_id}] card {card.get('card_id')} is missing available")
        # The "no proposal" card is the one legitimate exception: it has no
        # route concept at all (nothing is submitted through legislative or
        # decree), so an empty routes list is correct for it specifically.
        if card["card_id"] != "no_proposal":
            _assert(
                "routes" in card and len(card["routes"]) > 0,
                f"[{scenario_id}] card {card.get('card_id')} has no routes",
            )
        if not card["available"]:
            _assert(
                card.get("unavailable_reason") is not None,
                f"[{scenario_id}] unavailable card {card.get('card_id')} has no unavailable_reason",
            )

    status, preview = _request(
        base_url, "/api/game/preview", method="POST", body={"revision": revision, "decisions": []}
    )
    _assert(status == 200, f"[{scenario_id}] /api/game/preview: expected 200, got {status}: {preview}")
    _assert(preview["estimate"] is True, f"[{scenario_id}] preview did not label itself an estimate")

    status, resolved = _request(
        base_url, "/api/game/resolve", method="POST", body={"revision": revision, "decisions": []}
    )
    _assert(status == 200, f"[{scenario_id}] /api/game/resolve: expected 200, got {status}: {resolved}")
    _assert(set(resolved) == {"turnResult", "dashboard"}, f"[{scenario_id}] unexpected resolve envelope shape")

    status, history = _request(base_url, "/api/game/history")
    _assert(status == 200, f"[{scenario_id}] /api/game/history: expected 200, got {status}")
    _assert(len(history) == 1, f"[{scenario_id}] expected exactly one history entry after one resolve")

    status, detail = _request(base_url, "/api/game/history/1")
    _assert(status == 200, f"[{scenario_id}] /api/game/history/1: expected 200, got {status}")
    _assert(
        detail["turnResult"] == resolved["turnResult"],
        f"[{scenario_id}] historical turnResult disagrees with the live resolve response",
    )

    status, save = _request(
        base_url, "/api/game/save-as", method="POST", body={"display_name": f"smoke-{scenario_id}"}
    )
    _assert(status == 200, f"[{scenario_id}] /api/game/save-as: expected 200, got {status}: {save}")

    status, saves = _request(base_url, "/api/saves")
    _assert(status == 200, f"[{scenario_id}] /api/saves: expected 200, got {status}")
    _assert(
        any(row["save_id"] == save["save_id"] for row in saves),
        f"[{scenario_id}] the just-created save is not listed",
    )

    status, loaded = _request(base_url, "/api/game/load", method="POST", body={"save_id": save["save_id"]})
    _assert(status == 200, f"[{scenario_id}] /api/game/load: expected 200, got {status}: {loaded}")
    _assert(loaded["turn"] == dashboard["turn"] + 1, f"[{scenario_id}] loaded save is at the wrong turn")


def main() -> int:
    if not (FRONTEND_DIST / "index.html").is_file():
        print(
            f"smoke_gui: {FRONTEND_DIST}/index.html not found -- build the frontend first "
            "(`cd frontend && npm ci && npm run build`).",
            file=sys.stderr,
        )
        return 1

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    save_root = Path(tempfile.mkdtemp(prefix="mandate-smoke-saves-"))

    process = subprocess.Popen(
        [
            "uv",
            "run",
            "mandate-gui",
            "--port",
            str(port),
            "--save-root",
            str(save_root),
            "--scenario-root",
            str(REPO_ROOT / "data" / "scenarios"),
            "--frontend-dist",
            str(FRONTEND_DIST),
        ],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        _wait_until_ready(base_url, process)

        # "/" serves HTML, not JSON -- `_request`'s unconditional json.loads
        # would blow up on it, so fetch it directly here instead.
        raw_request = urllib.request.Request(base_url + "/", method="GET")
        with urllib.request.urlopen(raw_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8")
        _assert(response.status == 200, "SPA root did not return 200")
        _assert("<div id=" in html or "MANDATE" in html, "SPA root did not look like the built index.html")

        for scenario_id in ALL_SCENARIO_IDS:
            _smoke_one_scenario(base_url, scenario_id)
            print(f"smoke_gui: {scenario_id} OK")

        print("smoke_gui: all three scenarios OK -- new, options, preview, resolve, history, save-as, load")
        return 0

    except SmokeFailure as failure:
        print(f"smoke_gui: FAILED -- {failure}", file=sys.stderr)
        return 1

    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        shutil.rmtree(save_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
