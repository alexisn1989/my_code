"""End-to-end CLI tests: new -> resolve (with a decisions file) -> history,
plus the specific failure-mode guarantees the ticket calls out — invalid
decisions produce no output file and leave the input save byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli import main

SCENARIO_PATH = str(Path(__file__).resolve().parents[2] / "data" / "scenarios" / "tiny_valid.yaml")


def test_new_creates_a_save_at_turn_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_path = tmp_path / "save.json"
    exit_code = main(["new", "--scenario", SCENARIO_PATH, "--out", str(save_path)])
    assert exit_code == 0
    assert save_path.exists()

    exit_code = main(["inspect", "--state", str(save_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "current_turn:        0" in out
    assert "integrity:           OK" in out


def test_full_workflow_new_resolve_with_decisions_file_then_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = tmp_path / "save0.json"
    save1 = tmp_path / "save1.json"
    decisions_file = tmp_path / "budget.json"

    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0

    decisions_file.write_text(
        json.dumps(
            {
                "expected_turn": 0,
                "expected_state_version": 0,
                "decisions": [{"personal_income_rate_bps": 2_500}],
            }
        ),
        encoding="utf-8",
    )
    capsys.readouterr()  # discard "new" output
    exit_code = main(
        [
            "resolve",
            "--state",
            str(save0),
            "--turns",
            "1",
            "--decisions-file",
            str(decisions_file),
            "--out",
            str(save1),
        ]
    )
    assert exit_code == 0
    resolve_out = capsys.readouterr().out
    assert "Personal-income tax rate changed from 20% to 25%." in resolve_out
    assert "reconciliation: reconciled" in resolve_out
    assert save1.exists()

    exit_code = main(["history", "--state", str(save1), "--turn", "1"])
    assert exit_code == 0
    history_out = capsys.readouterr().out
    assert "Personal-income tax rate changed from 20% to 25%." in history_out


def test_decisions_file_requires_turns_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = tmp_path / "save0.json"
    decisions_file = tmp_path / "budget.json"
    bad_out = tmp_path / "bad.json"

    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    decisions_file.write_text(
        json.dumps(
            {
                "expected_turn": 0,
                "expected_state_version": 0,
                "decisions": [{"personal_income_rate_bps": 2_500}],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "resolve",
            "--state",
            str(save0),
            "--turns",
            "2",
            "--decisions-file",
            str(decisions_file),
            "--out",
            str(bad_out),
        ]
    )
    assert exit_code == 2
    assert not bad_out.exists()


def test_invalid_decisions_file_produces_no_output_and_leaves_input_untouched(
    tmp_path: Path,
) -> None:
    save0 = tmp_path / "save0.json"
    bad_out = tmp_path / "bad.json"
    bad_decisions_file = tmp_path / "empty_budget.json"

    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    before_bytes = save0.read_bytes()

    bad_decisions_file.write_text(
        json.dumps({"expected_turn": 0, "expected_state_version": 0, "decisions": [{}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "resolve",
            "--state",
            str(save0),
            "--turns",
            "1",
            "--decisions-file",
            str(bad_decisions_file),
            "--out",
            str(bad_out),
        ]
    )
    assert exit_code == 1
    assert not bad_out.exists()
    assert save0.read_bytes() == before_bytes
    # T18/R5: no stray write_save_atomic temp file left behind either — a general-purpose CLI
    # safety property (not resource-specific), extended here rather than duplicated into a new
    # resource-triggered failure test, since it protects any future failure path for free.
    assert {p.name for p in tmp_path.iterdir()} == {save0.name, bad_decisions_file.name}


def test_stale_decisions_file_expected_turn_is_rejected(tmp_path: Path) -> None:
    save0 = tmp_path / "save0.json"
    bad_out = tmp_path / "bad.json"
    stale_decisions_file = tmp_path / "stale_budget.json"

    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    before_bytes = save0.read_bytes()

    stale_decisions_file.write_text(
        json.dumps(
            {
                "expected_turn": 5,  # save is actually at turn 0
                "expected_state_version": 0,
                "decisions": [{"personal_income_rate_bps": 2_500}],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "resolve",
            "--state",
            str(save0),
            "--turns",
            "1",
            "--decisions-file",
            str(stale_decisions_file),
            "--out",
            str(bad_out),
        ]
    )
    assert exit_code == 1
    assert not bad_out.exists()
    assert save0.read_bytes() == before_bytes


def test_resolve_refuses_to_overwrite_its_input(tmp_path: Path) -> None:
    save0 = tmp_path / "save0.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0

    exit_code = main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save0)])
    assert exit_code == 2


def test_history_shows_a_deficit_scenarios_borrowing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deficit_scenario = str(
        Path(__file__).resolve().parents[2] / "data" / "scenarios" / "deficit_demo.yaml"
    )
    save0 = tmp_path / "save0.json"
    save1 = tmp_path / "save1.json"

    assert main(["new", "--scenario", deficit_scenario, "--out", str(save0)]) == 0
    capsys.readouterr()
    assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
    resolve_out = capsys.readouterr().out
    assert "issued" in resolve_out and "denars of new debt" in resolve_out
