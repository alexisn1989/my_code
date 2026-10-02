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

OUTPUTS (Gate 4A3 Commit 6b). `--out`, `--budgets-out` and `--packaged-out` are required and have no
default, because the defaults once named committed evidence. Each must be a safe, distinct artifact
name, and all three `docs/reviews/<name>.json` files are created EXCLUSIVELY before anything is
measured, so neither committed evidence nor a concurrent run's output can be overwritten. A failed run
deletes exactly the placeholders it created. Child processes never write into `docs/reviews`: the
budget report and the packaged-turn report go to this run's own temporary directory, and only a report
proven to belong to this run (its `runId`) and consistent with its exit status is copied in. There is
no way to skip the browser turn or the budgets: a release record exists only for a complete run.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
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


#: The ONE budget FAILURE the user WAIVED (Gate 4A3 Commit 6, ruling "Record breach, ship rest"):
#: `GET /api/saves` replays `validate_history` on every save file on every listing, so it passes the
#: 200 ms read-projection STOP. That budget FAILED; the ruling waives the failure, it does not pass
#: the budget. It is recorded as FAILED_WAIVED, not fixed and not reclassified. The waiver is exactly
#: that narrow: any OTHER breached budget, or any other endpoint over the read STOP, fails the run.
RULED_BREACH_ENDPOINT = "/api/saves"
BUDGET_WAIVER = "docs/reviews/gate-4a3-commit6-budget-waiver.md"
REVIEWS_DIR = REPO_ROOT / "docs" / "reviews"
#: An artifact name: lowercase, digits, dots and dashes, no path separator, no `..`, no `.json`.
SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*")


class VerifyError(RuntimeError):
    pass


# ------------------------------------------------------------------ 0. outputs and the budget report


def output_paths(names: dict[str, str], reviews_dir: Path | None = None) -> dict[str, Path]:
    """Map each `--flag` to its `docs/reviews/<name>.json`, refusing unsafe or repeated names."""
    directory = (reviews_dir or REVIEWS_DIR).resolve()
    paths: dict[str, Path] = {}
    owner: dict[str, str] = {}
    for flag, name in names.items():
        if not SAFE_NAME.fullmatch(name) or name.endswith(".json") or ".." in name:
            raise VerifyError(
                f"{flag}: unsafe artifact name {name!r} (lowercase letters, digits, '.' and '-'; "
                "no path, no '..', no .json suffix)"
            )
        if name in owner:
            raise VerifyError(
                f"{owner[name]} and {flag} both name {name!r}; outputs must be distinct"
            )
        owner[name] = flag
        path = directory / f"{name}.json"
        if path.resolve().parent != directory:
            raise VerifyError(f"{flag}: {name!r} escapes {directory}")
        paths[flag] = path
    return paths


def reserve(paths: list[Path]) -> list[Path]:
    """Create every path exclusively; on any collision remove what this call created and refuse."""
    created: list[Path] = []
    for path in paths:
        try:
            with path.open("x"):
                pass
        except FileExistsError:
            release(created)
            raise VerifyError(
                f"{path} already exists; pass new output names (committed evidence and another "
                "run's output are never overwritten)"
            ) from None
        created.append(path)
    return created


def release(created: list[Path]) -> None:
    """Delete exactly the placeholders this run created, and nothing else."""
    for path in created:
        path.unlink(missing_ok=True)


def read_fresh_budgets(returncode: int, path: Path, run_id: str) -> dict[str, object]:
    """The budget report THIS run produced, or a VerifyError.

    The report must exist at the path this run chose, inside its own temporary directory; carry this
    run's id; and agree with the measurement's exit status (0 with no breach, 1 with at least one).
    Anything else -- a measurement that died before writing, a report from another run, an exit status
    the report does not explain -- is refused, so a stale breach can never be read as a waiver.
    """
    if not path.is_file():
        raise VerifyError(f"the measurement wrote no report: exit {returncode}")
    measured: dict[str, object] = json.loads(path.read_text())
    if measured.get("runId") != run_id:
        raise VerifyError(
            f"the budget report belongs to run {measured.get('runId')!r}, not this one"
        )
    breaches = measured.get("breaches")
    if not isinstance(breaches, list):
        raise VerifyError("the budget report carries no breaches list")
    if returncode == 0 and breaches:
        raise VerifyError(f"the measurement exited 0 but reports breaches {breaches}")
    if returncode == 1 and not breaches:
        raise VerifyError("the measurement exited 1 but reports no breach")
    if returncode not in (0, 1):
        raise VerifyError(f"the measurement exited {returncode}")
    return measured


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
    # Required, with no default: a default once named committed evidence.
    parser.add_argument("--out", required=True)
    parser.add_argument("--budgets-out", required=True)
    parser.add_argument("--packaged-out", required=True)
    args = parser.parse_args(argv)
    archive = args.archive.resolve()
    paths = output_paths(
        {"--out": args.out, "--budgets-out": args.budgets_out, "--packaged-out": args.packaged_out}
    )
    reserved = reserve(list(paths.values()))
    try:
        record, budgets_text, packaged_text = verify(archive)
    except BaseException:
        release(reserved)
        raise
    paths["--budgets-out"].write_text(budgets_text)
    paths["--packaged-out"].write_text(packaged_text)
    paths["--out"].write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


def verify(archive: Path) -> tuple[dict[str, object], str, str]:
    """Every check, in order: the release record, then the budget and packaged reports' text."""
    run_id = secrets.token_hex(16)
    record: dict[str, object] = {
        "archive": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "runId": run_id,
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

            packaged_path = work / "packaged.json"
            browser = subprocess.run(
                ["npx", "playwright", "test", "--project=packaged", "--reporter=line"],
                cwd=REPO_ROOT / "frontend",
                env={
                    **os.environ,
                    "MANDATE_PACKAGED_BASE_URL": f"http://127.0.0.1:{port}",
                    "MANDATE_PACKAGED_OUT_PATH": str(packaged_path),
                },
                capture_output=True,
                text=True,
            )
            record["packagedTurn"] = {"exit": browser.returncode, "tail": browser.stdout[-600:]}
            if browser.returncode != 0:
                raise VerifyError("the packaged Playwright turn failed:\n" + browser.stdout[-3000:])
            if not packaged_path.is_file():
                raise VerifyError("the packaged Playwright turn passed but wrote no report")
            packaged_text = packaged_path.read_text()
            json.loads(packaged_text)

            budgets_path = work / "budgets.json"
            budgets = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "measure_budgets.py"),
                    "--base-url",
                    f"http://127.0.0.1:{port}",
                    "--out-path",
                    str(budgets_path),
                    "--run-id",
                    run_id,
                ],
                capture_output=True,
                text=True,
            )
            measured = read_fresh_budgets(budgets.returncode, budgets_path, run_id)
            waived = budgets.returncode == 1 and ruled_breach_only(measured)
            record["budgets"] = {
                "exit": budgets.returncode,
                "report": budgets.stdout.strip().splitlines(),
                "breaches": measured["breaches"],
                # PASSED only when no budget breached. A waived failure is still a failure.
                "verdict": "FAILED_WAIVED" if waived else "PASSED",
                "waivedEndpoint": RULED_BREACH_ENDPOINT if waived else None,
                "waiver": BUDGET_WAIVER if waived else None,
            }
            if budgets.returncode != 0 and not waived:
                raise VerifyError(
                    "a budget passed its STOP threshold:\n" + budgets.stdout + budgets.stderr
                )
            budgets_text = budgets_path.read_text()

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

    return record, budgets_text, packaged_text


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerifyError as error:
        print(f"verify_release: {error}", file=sys.stderr)
        raise SystemExit(1) from None
