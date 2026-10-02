"""The release verifier's evidence guards (Gate 4A3 Commits 6b and 6c).

`scripts/verify_release.py` is a standalone script, loaded here by path. These tests pin the guards
Commit 6b added after an audit of 6a, and Commit 6c's changes: the `/api/saves` waiver is ended (any
breach now fails, through the real budget step), and a failed reservation or a failed final write
leaves no placeholder behind.

* a budget report is accepted only if THIS run wrote it (its own path, its own `runId`) and it agrees
  with the measurement's exit status -- so a stale report carrying the waived `/api/saves` breach can
  never stand in for a measurement that died before writing;
* output names are required, safe, pairwise distinct, and their files are created exclusively, so
  neither committed evidence nor a concurrent run's output can be overwritten;
* there is no way to skip the browser turn or the budgets.

The 6a defect itself is reproduced end to end against the real 6a script in the Commit 6b record
(`docs/reviews/gate-4a3-commit6b-verifier.md`); `read_fresh_budgets` did not exist in 6a, so these unit
tests guard the fix rather than reproduce the old failure.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_release.py"
WAIVED = "/api/saves"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_release_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vr = _load()


def _report(
    run_id: str | None, breaches: list[str], saves_worst: float = 278.81
) -> dict[str, object]:
    report: dict[str, object] = {
        "budgets": {"read_projection_ms": {"target": 100, "stop": 200}},
        "results": {
            "read_projection_ms": {
                "perEndpoint": {
                    WAIVED: {"median": 232.0, "worst": saves_worst},
                    "/api/scenarios": {"median": 136.0, "worst": 174.7},
                }
            }
        },
        "breaches": breaches,
    }
    if run_id is not None:
        report["runId"] = run_id
    return report


def _write(path: Path, report: dict[str, object]) -> Path:
    path.write_text(json.dumps(report))
    return path


# ------------------------------------------------------------------ a fresh report, tied to the run


def test_a_stale_breach_report_cannot_stand_in_for_a_measurement_that_wrote_nothing(
    tmp_path: Path,
) -> None:
    """The audit's scenario: the measurement exits 1 before writing, while a real breach report from
    an earlier run sits where 6a used to look. 6a read it and recorded FAILED_WAIVED; now the run's
    own path is empty, and that is refused."""
    stale = _write(tmp_path / "stale-budgets.json", _report(None, ["read_projection_ms"]))
    assert json.loads(stale.read_text())["breaches"] == ["read_projection_ms"], "a tempting bait"
    with pytest.raises(vr.VerifyError, match="wrote no report: exit 1"):
        vr.read_fresh_budgets(1, tmp_path / "run" / "budgets.json", "this-run")


def test_a_report_from_another_run_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report("another-run", ["read_projection_ms"]))
    with pytest.raises(vr.VerifyError, match="belongs to run 'another-run'"):
        vr.read_fresh_budgets(1, path, "this-run")


def test_a_report_without_a_run_id_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report(None, ["read_projection_ms"]))
    with pytest.raises(vr.VerifyError, match="belongs to run None"):
        vr.read_fresh_budgets(1, path, "this-run")


def test_exit_one_without_a_breach_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report("r", []))
    with pytest.raises(vr.VerifyError, match="exited 1 but reports no breach"):
        vr.read_fresh_budgets(1, path, "r")


def test_exit_zero_with_a_breach_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report("r", ["read_projection_ms"]))
    with pytest.raises(vr.VerifyError, match="exited 0 but reports breaches"):
        vr.read_fresh_budgets(0, path, "r")


def test_any_other_exit_status_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report("r", ["read_projection_ms"]))
    with pytest.raises(vr.VerifyError, match="exited 2"):
        vr.read_fresh_budgets(2, path, "r")


def test_a_fresh_breach_report_is_read_but_never_passes(tmp_path: Path) -> None:
    """Commit 6c ended the waiver: the fresh /api/saves breach that 6a/6b recorded as FAILED_WAIVED
    is now a failed run."""
    path = _write(tmp_path / "budgets.json", _report("r", ["read_projection_ms"]))
    measured = vr.read_fresh_budgets(1, path, "r")
    with pytest.raises(vr.VerifyError, match="passed its STOP threshold"):
        vr.budget_verdict(1, measured)


def test_only_a_clean_measurement_passes() -> None:
    assert vr.budget_verdict(0, {"breaches": []}) == "PASSED"
    for breaches in (
        ["read_projection_ms"],
        ["new_game_ms"],
        ["new_game_ms", "read_projection_ms"],
    ):
        with pytest.raises(vr.VerifyError):
            vr.budget_verdict(1, {"breaches": breaches})
    assert not hasattr(vr, "ruled_breach_only"), "the waiver path is gone"


def test_a_fresh_clean_report_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path / "budgets.json", _report("r", [], saves_worst=150.0))
    measured = vr.read_fresh_budgets(0, path, "r")
    assert measured["breaches"] == []


# ------------------------------------------------------------------ arguments


def test_every_output_name_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        vr.main(["archive.tar.gz"])
    assert raised.value.code == 2
    err = capsys.readouterr().err
    for flag in ("--out", "--budgets-out", "--packaged-out"):
        assert flag in err


def test_skip_browser_no_longer_exists() -> None:
    """6a's --skip-browser skipped the browser turn AND the budgets, yet wrote a release record and
    exited 0. It is gone: there is no way to obtain a release record for an incomplete run."""
    with pytest.raises(SystemExit) as raised:
        vr.main(
            [
                "a.tar.gz",
                "--out",
                "r",
                "--budgets-out",
                "b",
                "--packaged-out",
                "p",
                "--skip-browser",
            ]
        )
    assert raised.value.code == 2


# ------------------------------------------------------------------ names


@pytest.mark.parametrize(
    "name", ["../x", "a/b", "/abs", "", "x.json", "X", "a..b", ".hidden", "a\\b"]
)
def test_unsafe_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(vr.VerifyError, match="unsafe artifact name"):
        vr.output_paths(
            {"--out": "release", "--budgets-out": name, "--packaged-out": "packaged"}, tmp_path
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [("--out", "--budgets-out"), ("--out", "--packaged-out"), ("--budgets-out", "--packaged-out")],
)
def test_two_outputs_may_not_share_a_name(tmp_path: Path, first: str, second: str) -> None:
    names = {"--out": "release", "--budgets-out": "budgets", "--packaged-out": "packaged"}
    names[second] = names[first]
    with pytest.raises(vr.VerifyError, match="outputs must be distinct"):
        vr.output_paths(names, tmp_path)


def test_safe_distinct_names_resolve_inside_the_reviews_directory(tmp_path: Path) -> None:
    paths = vr.output_paths(
        {"--out": "r-6b", "--budgets-out": "b.6b", "--packaged-out": "p"}, tmp_path
    )
    assert {p.parent for p in paths.values()} == {tmp_path.resolve()}
    assert sorted(p.name for p in paths.values()) == ["b.6b.json", "p.json", "r-6b.json"]


# ------------------------------------------------------------------ exclusive reservation


def test_an_existing_file_is_refused_and_left_byte_identical(tmp_path: Path) -> None:
    committed = tmp_path / "committed.json"
    committed.write_text('{"evidence": true}\n')
    first = tmp_path / "first.json"
    with pytest.raises(vr.VerifyError, match="already exists"):
        vr.reserve([first, committed, tmp_path / "never.json"])
    assert committed.read_text() == '{"evidence": true}\n'
    assert not first.exists(), "a placeholder this call created must be removed on refusal"
    assert not (tmp_path / "never.json").exists()


def test_a_second_run_cannot_reserve_names_the_first_holds(tmp_path: Path) -> None:
    """The check-then-write race: two runs with the same names. Creation is exclusive, so the second
    loses at reservation and never measures -- and it removes nothing the first created."""
    names = [tmp_path / "r.json", tmp_path / "b.json", tmp_path / "p.json"]
    held = vr.reserve(names)
    with pytest.raises(vr.VerifyError, match="already exists"):
        vr.reserve(names)
    assert all(path.exists() for path in held)
    vr.release(held)
    assert not any(path.exists() for path in names)


def test_main_refuses_an_existing_output_before_reading_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vr, "REVIEWS_DIR", tmp_path)
    (tmp_path / "budgets.json").write_text("committed\n")
    with pytest.raises(vr.VerifyError, match="already exists"):
        vr.main(
            [
                str(tmp_path / "does-not-exist.tar.gz"),
                "--out",
                "release",
                "--budgets-out",
                "budgets",
                "--packaged-out",
                "packaged",
            ]
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["budgets.json"]
    assert (tmp_path / "budgets.json").read_text() == "committed\n"


def test_a_failed_run_removes_exactly_its_own_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vr, "REVIEWS_DIR", tmp_path)
    (tmp_path / "unrelated.json").write_text("keep\n")

    def boom(archive: Path) -> None:
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "budgets.json",
            "packaged.json",
            "release.json",
            "unrelated.json",
        ], "all three outputs are reserved before anything is verified"
        raise vr.VerifyError("simulated failure")

    monkeypatch.setattr(vr, "verify", boom)
    with pytest.raises(vr.VerifyError, match="simulated failure"):
        vr.main(
            [
                "a.tar.gz",
                "--out",
                "release",
                "--budgets-out",
                "budgets",
                "--packaged-out",
                "packaged",
            ]
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["unrelated.json"]
    assert (tmp_path / "unrelated.json").read_text() == "keep\n"


# ------------------------------------------------------------------ Commit 6c: wiring and cleanup


def _fake_measurement(report: dict[str, object] | None, returncode: int) -> Any:
    """A stand-in for `subprocess.run` that writes `report` (with the run's own id) to --out-path."""

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        out_path = Path(command[command.index("--out-path") + 1])
        run_id = command[command.index("--run-id") + 1]
        if report is not None:
            out_path.write_text(json.dumps({**report, "runId": run_id}))
        return subprocess.CompletedProcess(command, returncode, stdout="STOP\n", stderr="")

    return runner


def test_a_fresh_saves_breach_through_the_real_budget_step_leaves_no_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wiring, not just `budget_verdict`: `main` runs, `verify` reaches the REAL
    `measure_budget_step`, the measurement writes a FRESH report with this run's id carrying the
    /api/saves breach and exits 1 -- and the run fails with none of its three outputs left."""
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    monkeypatch.setattr(vr, "REVIEWS_DIR", reviews)
    runner = _fake_measurement(_report(None, ["read_projection_ms"]), 1)

    def verify_through_the_budget_step(archive: Path) -> tuple[dict[str, object], str, str]:
        work = tmp_path / "work"
        work.mkdir()
        budgets, text = vr.measure_budget_step(8420, work, "run-6c", runner=runner)
        return {"budgets": budgets}, text, "{}"

    monkeypatch.setattr(vr, "verify", verify_through_the_budget_step)
    with pytest.raises(vr.VerifyError, match="passed its STOP threshold"):
        vr.main(["a.tar.gz", "--out", "release", "--budgets-out", "budgets", "--packaged-out", "p"])
    assert list(reviews.iterdir()) == []


def test_the_real_budget_step_passes_a_clean_fresh_report(tmp_path: Path) -> None:
    runner = _fake_measurement(_report(None, [], saves_worst=150.0), 0)
    record, text = vr.measure_budget_step(8420, tmp_path, "run-6c", runner=runner)
    assert record["verdict"] == "PASSED"
    assert json.loads(text)["runId"] == "run-6c"


def test_a_reservation_failing_for_another_reason_strands_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [tmp_path / "r.json", tmp_path / "b.json", tmp_path / "p.json"]
    real_open = Path.open

    def failing_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if self == names[1] and mode == "x":
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(vr.VerifyError, match=r"could not reserve .*b\.json"):
        vr.reserve(names)
    assert not names[0].exists(), "the first placeholder must be released"
    assert not names[2].exists(), "the third must never have been created"


@pytest.mark.parametrize("failing_write", [2, 3])
def test_a_failed_final_write_releases_all_three_reservations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_write: int
) -> None:
    monkeypatch.setattr(vr, "REVIEWS_DIR", tmp_path)
    (tmp_path / "unrelated.json").write_text("keep\n")
    monkeypatch.setattr(vr, "verify", lambda archive: ({"ok": True}, "{}", "{}"))
    writes = {"n": 0}
    real_write = Path.write_text

    def failing_write_text(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        writes["n"] += 1
        if writes["n"] == failing_write:
            raise OSError(28, "No space left on device")
        return real_write(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    with pytest.raises(OSError, match="No space left"):
        vr.main(["a.tar.gz", "--out", "release", "--budgets-out", "budgets", "--packaged-out", "p"])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["unrelated.json"]
    assert (tmp_path / "unrelated.json").read_bytes() == b"keep\n"
