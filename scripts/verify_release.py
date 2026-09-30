#!/usr/bin/env python3
"""Verify the distributable archive on a CLEAN PATH (Gate 4A3 Commit 6).

A launch from the development tree proves nothing about a distributable, so this works only from the
archive, in an empty directory outside the repository, with the repository's virtualenv and import path
removed from the environment. In order:

1. SAFE INSPECTION BEFORE EXTRACTION (section 9.4 item 4). Every member must be a regular file or a
   directory, relative, under one `mandate-gui-<version>/` directory, with no `..` component -- no
   absolute path, no symlink, no hard link, no device. The checker is proved on three hostile tarballs
   (absolute path, `..` traversal, symlink) before it is trusted with the real one.
2. `SHA256SUMS` verified; the scenario set must be exactly the three shipped names.
3. The README's own commands executed as written: the install line verbatim, and the run line with
   only `--port` and `--save-root` appended, so the check neither collides with a real game on 8420 nor
   writes into the user's own save directory. Both additions are recorded.
4. PROVENANCE: the installed `app` must import from the new virtualenv's site-packages, never from the
   repository. Without this, everything below could be exercising the development tree.
5. `/` and `/api/scenarios` answer 200 from the installed server, with exactly the three scenarios.
6. One turn played through the interface against that instance (the `packaged` Playwright project),
   recording every request and requiring each to be same-origin.
7. F12 against the installed entry point: a second launch on the bound port exits 1 naming the port;
   SIGINT stops the first with status 0; a restart on the same port then succeeds.
8. The section 5 budgets, measured against this instance (`scripts/measure_budgets.py`).

Writes `docs/reviews/<name>.json` (default `gate-4a3-commit6-release`). Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SCENARIOS = {"decree_state", "deficit_demo", "tiny_valid"}
STARTUP_TIMEOUT_S = 60.0


BUDGETS_OUT = "gate-4a3-commit6-budgets"

#: The ONE budget breach the user ruled on (Gate 4A3 Commit 6, "Record breach, ship rest"):
#: `GET /api/saves` replays `validate_history` on every save file on every listing, so it passes the
#: 200 ms read-projection STOP. It is recorded verbatim, not fixed and not reclassified. The exception
#: is exactly that narrow: any OTHER breached budget, or any other endpoint over the read STOP, fails.
RULED_BREACH_ENDPOINT = "/api/saves"


class VerifyError(RuntimeError):
    pass


def ruled_breach_only(measured: dict[str, object]) -> bool:
    breaches = measured["breaches"]
    if breaches != ["read_projection_ms"]:
        return False
    stop = measured["budgets"]["read_projection_ms"]["stop"]  # type: ignore[index]
    per_endpoint = measured["results"]["read_projection_ms"]["perEndpoint"]  # type: ignore[index]
    over = sorted(path for path, row in per_endpoint.items() if row["worst"] > stop)
    return over == [RULED_BREACH_ENDPOINT]


# ------------------------------------------------------------------ 1. safe inspection


def unsafe_members(archive: Path) -> list[str]:
    """Every reason this archive is unsafe to extract. Empty means safe."""
    problems: list[str] = []
    tops: set[str] = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            path = PurePosixPath(name)
            if path.is_absolute() or name.startswith("/"):
                problems.append(f"absolute path: {name}")
            if ".." in path.parts:
                problems.append(f"parent traversal: {name}")
            if not (member.isfile() or member.isdir()):
                problems.append(f"not a regular file or directory: {name} (type {member.type!r})")
            if path.parts:
                tops.add(path.parts[0])
    if len(tops) != 1 or not next(iter(tops), "").startswith("mandate-gui-"):
        problems.append(
            f"expected one top-level mandate-gui-<version>/ directory, found {sorted(tops)}"
        )
    return problems


def _hostile(path: Path, kind: str) -> Path:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        body = b"x"
        if kind == "symlink":
            info = tarfile.TarInfo("mandate-gui-0/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        else:
            info = tarfile.TarInfo(
                "/etc/mandate-evil" if kind == "absolute" else "mandate-gui-0/../../evil"
            )
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    target = path / f"hostile-{kind}.tar.gz"
    target.write_bytes(buffer.getvalue())
    return target


def prove_the_checker(work: Path) -> dict[str, list[str]]:
    """Anti-vacuity: a checker that rejects nothing would pass the real archive for the wrong reason."""
    found: dict[str, list[str]] = {}
    for kind in ("absolute", "traversal", "symlink"):
        problems = unsafe_members(_hostile(work, kind))
        if not problems:
            raise VerifyError(f"the safety checker ACCEPTED a hostile {kind} archive")
        found[kind] = problems
    return found


# ------------------------------------------------------------------ 2. checksums


def verify_checksums(top: Path) -> int:
    lines = (top / "SHA256SUMS").read_text().splitlines()
    listed = set()
    for line in lines:
        digest, relative = line.split("  ", 1)
        listed.add(relative)
        actual = hashlib.sha256((top / relative).read_bytes()).hexdigest()
        if actual != digest:
            raise VerifyError(f"checksum mismatch: {relative}")
    present = {p.relative_to(top).as_posix() for p in top.rglob("*") if p.is_file()} - {
        "SHA256SUMS"
    }
    if present != listed:
        raise VerifyError(
            f"SHA256SUMS does not cover exactly the files present: {sorted(present ^ listed)}"
        )
    scenarios = {p.stem for p in (top / "scenarios").glob("*.yaml")}
    if scenarios != SHIPPED_SCENARIOS:
        raise VerifyError(
            f"scenario set is {sorted(scenarios)}, expected {sorted(SHIPPED_SCENARIOS)}"
        )
    return len(listed)


# ------------------------------------------------------------------ 3-5. install and launch


def readme_commands(top: Path) -> list[str]:
    text = (top / "README.md").read_text()
    blocks = re.findall(r"```\n(.*?)```", text, flags=re.DOTALL)
    commands = [line.strip() for line in blocks[0].splitlines() if line.strip()]
    if len(commands) != 2:
        raise VerifyError(f"expected two README commands, found {len(commands)}")
    return commands


def clean_env() -> dict[str, str]:
    """The parent environment minus anything that could make the repository importable."""
    env = {
        k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"}
    }
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if str(REPO_ROOT) not in p
    )
    env["PYTHONUNBUFFERED"] = "1"
    return env


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def http_get(port: int, path: str) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def launch(
    top: Path, run_line: str, port: int, save_root: Path, env: dict[str, str]
) -> subprocess.Popen[bytes]:
    command = f"{run_line} --port {port} --save-root {save_root}"
    return subprocess.Popen(
        ["bash", "-c", f"exec {command}"],
        cwd=top,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_ready(proc: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise VerifyError(f"the installed server exited early: {proc.stderr.read().decode()}")  # type: ignore[union-attr]
        try:
            if http_get(port, "/api/scenarios")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.25)
    raise VerifyError("the installed server never became ready")


def stop(proc: subprocess.Popen[bytes]) -> int:
    proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise VerifyError("the installed server did not stop within 15 s of SIGINT") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", default="gate-4a3-commit6-release")
    parser.add_argument(
        "--skip-browser", action="store_true", help="for drafting only; never for the gate"
    )
    args = parser.parse_args(argv)
    archive = args.archive.resolve()
    record: dict[str, object] = {
        "archive": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }

    with tempfile.TemporaryDirectory(prefix="mandate-verify-") as tmp:
        work = Path(tmp)
        if str(work).startswith(str(REPO_ROOT)):
            raise VerifyError("the verification directory must be outside the repository")
        record["hostileArchivesRejected"] = prove_the_checker(work)
        problems = unsafe_members(archive)
        if problems:
            raise VerifyError("unsafe archive:\n  " + "\n  ".join(problems))
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            record["members"] = len(members)
            tar.extractall(work / "x", filter="data")
        (top,) = [p for p in (work / "x").iterdir()]
        record["checksummedFiles"] = verify_checksums(top)

        env = clean_env()
        install_line, run_line = readme_commands(top)
        subprocess.run(
            ["bash", "-c", install_line], cwd=top, env=env, check=True, capture_output=True
        )
        record["readme"] = {
            "install": install_line,
            "run": run_line,
            "runAppended": "--port <free port> --save-root <temporary directory>",
        }

        python = top / ".venv" / "bin" / "python"
        origin = subprocess.run(
            [str(python), "-c", "import app, sys; print(app.__file__); print(sys.prefix)"],
            cwd=work,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\n")
        app_file, prefix = origin[0], origin[1]
        if str(REPO_ROOT) in app_file or not app_file.startswith(str(top / ".venv")):
            raise VerifyError(f"`app` imported from {app_file}, not from the new virtualenv")
        record["provenance"] = {
            "app.__file__": app_file.replace(str(work), "<work>"),
            "sys.prefix": prefix.replace(str(work), "<work>"),
        }

        port = free_port()
        server = launch(top, run_line, port, work / "saves", env)
        try:
            wait_ready(server, port)
            root_status, root_body = http_get(port, "/")
            scen_status, scen_body = http_get(port, "/api/scenarios")
            ids = {entry["scenario_id"] for entry in json.loads(scen_body)}
            if (
                root_status != 200
                or b'<div id="root"' not in root_body
                and b"id=root" not in root_body
            ):
                raise VerifyError(f"/ answered {root_status} without the SPA shell")
            if scen_status != 200 or ids != SHIPPED_SCENARIOS:
                raise VerifyError(f"/api/scenarios answered {scen_status} with {sorted(ids)}")
            record["served"] = {
                "/": root_status,
                "/api/scenarios": scen_status,
                "scenarios": sorted(ids),
            }

            if not args.skip_browser:
                browser = subprocess.run(
                    ["npx", "playwright", "test", "--project=packaged", "--reporter=line"],
                    cwd=REPO_ROOT / "frontend",
                    env={**os.environ, "MANDATE_PACKAGED_BASE_URL": f"http://127.0.0.1:{port}"},
                    capture_output=True,
                    text=True,
                )
                record["packagedTurn"] = {"exit": browser.returncode, "tail": browser.stdout[-600:]}
                if browser.returncode != 0:
                    raise VerifyError(
                        "the packaged Playwright turn failed:\n" + browser.stdout[-3000:]
                    )

                budgets = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts" / "measure_budgets.py"),
                        "--base-url",
                        f"http://127.0.0.1:{port}",
                        "--out",
                        BUDGETS_OUT,
                    ],
                    capture_output=True,
                    text=True,
                )
                measured = json.loads(
                    (REPO_ROOT / "docs" / "reviews" / f"{BUDGETS_OUT}.json").read_text()
                )
                record["budgets"] = {
                    "exit": budgets.returncode,
                    "report": budgets.stdout.strip().splitlines(),
                    "breaches": measured["breaches"],
                    "knownBreach": ruled_breach_only(measured),
                }
                if budgets.returncode != 0 and not ruled_breach_only(measured):
                    raise VerifyError(
                        "a budget passed its STOP threshold:\n" + budgets.stdout + budgets.stderr
                    )

            second = launch(top, run_line, port, work / "saves2", env)
            _, second_err = second.communicate(timeout=30)
            message = second_err.decode()
            if second.returncode != 1 or str(port) not in message or "--port" not in message:
                raise VerifyError(
                    f"a second launch on the bound port did not fail fast: {second.returncode} {message}"
                )
            record["f12Collision"] = {"exit": second.returncode, "message": message.strip()}
        finally:
            code = stop(server)
        if code != 0:
            raise VerifyError(f"SIGINT stopped the server with status {code}, not 0")
        restarted = launch(top, run_line, port, work / "saves", env)
        try:
            wait_ready(restarted, port)
        finally:
            restart_code = stop(restarted)
        record["f12Shutdown"] = {
            "sigintExit": code,
            "restartOnSamePort": "served 200",
            "restartSigintExit": restart_code,
        }

    out = REPO_ROOT / "docs" / "reviews" / f"{args.out}.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerifyError as error:
        print(f"verify_release: {error}", file=sys.stderr)
        raise SystemExit(1) from None
