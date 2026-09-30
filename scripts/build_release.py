#!/usr/bin/env python3
"""Build the distributable archive: `dist/mandate-gui-<version>.tar.gz` (Gate 4A3 Commit 6).

A reproducible archive, not an installer. It carries the backend wheel, the pinned and hashed runtime
requirements, the built SPA, the three shipped scenarios, a two-command README, and `SHA256SUMS`, all
under one top-level directory `mandate-gui-<version>/`.

WHAT "REPRODUCIBLE" MEANS HERE, AND HOW IT IS MADE TRUE (frozen plan section 9.5). The same committed
inputs and the same `SOURCE_DATE_EPOCH` produce the same bytes. Every source of nondeterminism is pinned
rather than hoped away:

* inputs are staged from what git tracks or would track (`git ls-files --cached --others
  --exclude-standard`), never from the developer's tree, so an ignored `.venv`, build output, cache or
  save cannot leak in;
* the wheel's build backend is pinned in `backend/pyproject.toml` (`hatchling==1.32.0`), and hatchling
  honours `SOURCE_DATE_EPOCH` for the wheel's own zip timestamps;
* tar members are added in sorted path order with one mtime, fixed modes (0644 / 0755), uid and gid 0,
  empty owner names, and the GNU format, which writes no PAX timestamps;
* gzip is written with `mtime=0`, no embedded filename, and a fixed compression level.

`--check-reproducible` builds twice in two independent temporary directories and fails, printing both
member tables' differences, unless the two SHA-256 hashes are equal.

Standard library only; run with the repository's own interpreter.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SCENARIOS = ("decree_state.yaml", "deficit_demo.yaml", "tiny_valid.yaml")
GZIP_LEVEL = 9
FILE_MODE = 0o644
DIR_MODE = 0o755


class ReleaseError(RuntimeError):
    pass


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def agreed_version() -> str:
    """The backend and frontend must declare the SAME version. A mismatch fails the build rather than
    silently picking one, because the archive name would then describe only half of what it holds."""
    backend = tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text())["project"][
        "version"
    ]
    frontend = json.loads((REPO_ROOT / "frontend" / "package.json").read_text())["version"]
    if backend != frontend:
        raise ReleaseError(f"version mismatch: backend {backend} != frontend {frontend}")
    return str(backend)


def head_commit_epoch() -> int:
    return int(run(["git", "log", "-1", "--format=%ct"], cwd=REPO_ROOT).strip())


def stage_sources(staging: Path) -> None:
    """Copy exactly the tracked-or-trackable files under the three trees the build needs."""
    listed = run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "backend",
            "frontend",
            "data/scenarios",
        ],
        cwd=REPO_ROOT,
    )
    for relative in sorted(filter(None, listed.split("\0"))):
        source = REPO_ROOT / relative
        if not source.is_file():  # a tracked path deleted in the working tree
            continue
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Dependencies are not sources: link them rather than copy them. Both are ignored by git, so the
    # listing above can never have staged them.
    for modules in ("frontend/node_modules", "frontend/tools/openapi-gen/node_modules"):
        if (REPO_ROOT / modules).is_dir():
            (staging / modules).symlink_to(REPO_ROOT / modules, target_is_directory=True)


def build_frontend(staging: Path) -> Path:
    run(["npm", "run", "build"], cwd=staging / "frontend")
    dist = staging / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        raise ReleaseError("the frontend build produced no index.html")
    return dist


def build_wheel(staging: Path, epoch: int, version: str) -> Path:
    out = staging / "wheel-out"
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch)}
    run(["uv", "build", "--wheel", "--out-dir", str(out)], cwd=staging / "backend", env=env)
    wheels = sorted(out.glob("*.whl"))
    expected = f"mandate_backend-{version}-py3-none-any.whl"
    if [w.name for w in wheels] != [expected]:
        raise ReleaseError(f"expected exactly {expected}, got {[w.name for w in wheels]}")
    return wheels[0]


def export_requirements(staging: Path) -> str:
    """The runtime closure (`gui` extra, no dev group), every package `==` with hashes.

    This is how "no unpinned ranges in what ships" is met. The wheel's own `Requires-Dist` keeps its
    ranges -- that is metadata about compatibility -- and the install path the README gives uses these
    hashed pins with `--require-hashes`."""
    text = run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--extra",
            "gui",
            "--no-emit-project",
            "--no-header",
            "--format",
            "requirements-txt",
        ],
        cwd=staging / "backend",
    )
    check_requirements_are_pinned(text)
    return text


def check_requirements_are_pinned(text: str) -> None:
    """Every requirement line must be `name==version` and carry at least one `--hash`."""
    requirement: str | None = None
    hashes = 0
    problems: list[str] = []

    def finish() -> None:
        if requirement is None:
            return
        spec = requirement.split(";")[0].strip().rstrip("\\").strip()
        if "==" not in spec or any(op in spec for op in (">", "<", "~", "!=")):
            problems.append(f"not pinned: {spec}")
        if hashes == 0:
            problems.append(f"no hash: {spec}")

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash"):
            hashes += 1
            continue
        finish()
        requirement, hashes = line, 0
        if "--hash" in line:
            hashes += line.count("--hash")
    finish()
    if requirement is None:
        problems.append("the requirements export is empty")
    if problems:
        raise ReleaseError("runtime requirements are not fully pinned:\n  " + "\n  ".join(problems))


def render_readme(version: str, wheel_name: str) -> str:
    template = (REPO_ROOT / "packaging" / "README.release.md").read_text()
    return template.replace("{version}", version).replace("{wheel}", wheel_name)


def layout(root: Path, *, version: str, wheel: Path, requirements: str, dist: Path) -> Path:
    """Assemble `mandate-gui-<version>/` with every member except SHA256SUMS, then write SHA256SUMS
    over all of them in sorted order."""
    top = root / f"mandate-gui-{version}"
    top.mkdir(parents=True)
    shutil.copy2(wheel, top / wheel.name)
    (top / "requirements.txt").write_text(requirements)
    (top / "README.md").write_text(render_readme(version, wheel.name))
    shutil.copytree(dist, top / "dist")
    (top / "scenarios").mkdir()
    for name in SHIPPED_SCENARIOS:
        shutil.copy2(REPO_ROOT / "data" / "scenarios" / name, top / "scenarios" / name)
    lines = []
    for path in sorted(p for p in top.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(top).as_posix()}")
    (top / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return top


def write_archive(top: Path, out: Path, epoch: int) -> None:
    members = sorted([top, *top.rglob("*")], key=lambda p: p.relative_to(top.parent).as_posix())
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path in members:
            name = path.relative_to(top.parent).as_posix()
            if path.is_symlink():
                raise ReleaseError(f"refusing to archive a symlink: {name}")
            info = tarfile.TarInfo(name)
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = DIR_MODE
                tar.addfile(info)
            else:
                data = path.read_bytes()
                info.mode = FILE_MODE
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    out.parent.mkdir(parents=True, exist_ok=True)
    with (
        open(out, "wb") as handle,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=handle, mtime=0, compresslevel=GZIP_LEVEL
        ) as gz,
    ):
        gz.write(buffer.getvalue())


def member_table(archive: Path) -> list[tuple[str, int, str, int, str]]:
    rows = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            digest = ""
            if member.isfile():
                extracted = tar.extractfile(member)
                assert extracted is not None
                digest = hashlib.sha256(extracted.read()).hexdigest()
            rows.append((member.name, member.size, oct(member.mode), member.mtime, digest))
    return rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_once(out: Path, epoch: int) -> dict[str, object]:
    version = agreed_version()
    with tempfile.TemporaryDirectory(prefix="mandate-release-") as tmp:
        work = Path(tmp)
        staging = work / "src"
        staging.mkdir()
        stage_sources(staging)
        dist = build_frontend(staging)
        wheel = build_wheel(staging, epoch, version)
        requirements = export_requirements(staging)
        top = layout(
            work / "layout", version=version, wheel=wheel, requirements=requirements, dist=dist
        )
        write_archive(top, out, epoch)
    return {"version": version, "archive": str(out), "sha256": sha256(out), "epoch": epoch}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--epoch", type=int, default=None, help="SOURCE_DATE_EPOCH (default: HEAD's commit time)"
    )
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--check-reproducible", action="store_true")
    args = parser.parse_args(argv)
    epoch = (
        args.epoch
        if args.epoch is not None
        else int(os.environ.get("SOURCE_DATE_EPOCH") or head_commit_epoch())
    )
    version = agreed_version()
    target = args.out_dir / f"mandate-gui-{version}.tar.gz"
    try:
        first = build_once(target, epoch)
        print(json.dumps(first, indent=2))
        if args.check_reproducible:
            with tempfile.TemporaryDirectory(prefix="mandate-release-second-") as tmp:
                second_path = Path(tmp) / target.name
                second = build_once(second_path, epoch)
                print(f"first  sha256 {first['sha256']}")
                print(f"second sha256 {second['sha256']}")
                if first["sha256"] != second["sha256"]:
                    a, b = member_table(target), member_table(second_path)
                    for row in sorted(set(a) ^ set(b)):
                        print(("first " if row in a else "second"), row)
                    raise ReleaseError("the two builds differ: NOT reproducible")
                print("reproducible: two independent builds produced identical bytes")
    except ReleaseError as error:
        print(f"build_release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
