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
                "decisions": [{"kind": "budget", "personal_income_rate_bps": 2_500}],
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
                "decisions": [{"kind": "budget", "personal_income_rate_bps": 2_500}],
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
                "decisions": [{"kind": "budget", "personal_income_rate_bps": 2_500}],
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


def test_resolve_stops_cleanly_at_a_mid_batch_conclusion_and_persists_what_ran(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Phase 3C (R10): `tiny_valid` concludes via `TERM_LIMIT_EXIT` at its real, natural turn 32
    -- requesting 40 turns must stop cleanly at 32, still write the save (every genuinely
    resolved turn persisted, not discarded because the batch as a whole didn't reach 40), exit
    successfully, and say so -- never a bare "error:" for turns that actually completed."""
    save0 = tmp_path / "save0.json"
    save1 = tmp_path / "save1.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    capsys.readouterr()

    exit_code = main(["resolve", "--state", str(save0), "--turns", "40", "--out", str(save1)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "game concluded" in out
    assert "fewer turns were resolved than requested" in out
    assert save1.exists()

    exit_code = main(["inspect", "--state", str(save1), "--politics"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "current_turn:        32" in out
    assert "integrity:           OK" in out
    assert "game concluded:      turn 32  defeat (term_limit_exit)" in out


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


# --- Phase 3A: politics in inspect/history (T-N2) -----------------------------


def test_inspect_shows_legitimacy_and_political_capital_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = tmp_path / "save0.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0)]) == 0
    out = capsys.readouterr().out
    assert "legitimacy:          70%" in out
    assert "political capital:   500 / 1,000" in out
    # The full axis table is --politics-gated, not shown by default.
    assert "constitution:" not in out
    assert "order support:" not in out


def test_inspect_politics_flag_shows_the_full_axis_table_and_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = tmp_path / "save0.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--politics"]) == 0
    out = capsys.readouterr().out
    assert "constitution:        parliamentary / legislative_selection / bicameral / unitary" in out
    assert "national_election=every 16 turns" in out
    assert "order support:       80%" in out
    assert "economic baseline:   (none yet — no turn resolved)" in out


def test_history_turn_shows_the_political_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = tmp_path / "save0.json"
    save1 = tmp_path / "save1.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    capsys.readouterr()
    assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
    capsys.readouterr()

    assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
    out = capsys.readouterr().out
    assert "political:" in out
    assert "legitimacy: opening=70% order_support=1% performance=0% -> closing=71%" in out
    assert "opening baseline: (none — first resolved turn, performance contribution 0)" in out
    assert "political capital: opening=500 regeneration=+413 spent=0 -> closing=913 / 1,000" in out


def test_resolve_output_also_shows_the_political_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_cmd_resolve` prints via `_print_report`, a separate code path from `_cmd_history`'s
    inline printing -- both must show the political block independently."""
    save0 = tmp_path / "save0.json"
    save1 = tmp_path / "save1.json"
    assert main(["new", "--scenario", SCENARIO_PATH, "--out", str(save0)]) == 0
    capsys.readouterr()

    assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
    out = capsys.readouterr().out
    assert "political:" in out
    assert "closing=71%" in out


# --- Phase 3B1 (§17 step 17): legislative presentation in inspect/resolve/history ------------
#
# Pins meaningful labels, identities and exact political numbers -- deliberately NOT full-output
# snapshots, which break on every unrelated formatting change and prove nothing about meaning.

DEFICIT_SCENARIO_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "deficit_demo.yaml"
)
DECREE_SCENARIO_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "decree_state.yaml"
)


def _new_save(tmp_path: Path, scenario: str, name: str = "save0.json") -> Path:
    save = tmp_path / name
    assert main(["new", "--scenario", scenario, "--out", str(save)]) == 0
    return save


def _resolve_with(
    tmp_path: Path,
    save0: Path,
    decision: dict | None,
    out_name: str = "save1.json",
) -> Path:
    """Resolve exactly one turn, optionally with a `BudgetDecision`, and return the new save.

    `decision` is a bare budget payload (no `"kind"`) — added here rather than at every call site,
    since a discriminated union needs the tag present in the input even though `kind` itself
    defaults to `"budget"` for direct model construction.
    """
    save1 = tmp_path / out_name
    argv = ["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]
    if decision is not None:
        tagged_decision = {"kind": "budget", **decision}
        decisions_file = tmp_path / f"decisions_{out_name}"
        decisions_file.write_text(
            json.dumps(
                {"expected_turn": 0, "expected_state_version": 0, "decisions": [tagged_decision]}
            ),
            encoding="utf-8",
        )
        argv += ["--decisions-file", str(decisions_file)]
    assert main(argv) == 0
    return save1


# --- 1/2. inspect --legislature on all three scenarios ---------------------------------------


def test_inspect_legislature_shows_tiny_valid_bicameral_composition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--legislature"]) == 0
    out = capsys.readouterr().out

    assert "legislature:         bicameral" in out
    assert "decree authority:    emergency_only" in out
    assert "lower chamber: 100 seats (strict majority 51)" in out
    assert "upper chamber: 60 seats (strict majority 31)" in out
    # Authored composition by role, summed from state's own bloc seat entries.
    assert "authored seats: coalition 52  confidence-and-supply 10  opposition 38" in out
    assert "authored seats: coalition 30  confidence-and-supply 6  opposition 24" in out
    # Party/bloc identity, role, and every authored preference.
    assert "civic_union (Civic Union) — coalition, 2 bloc(s)" in out
    assert "rural_alliance (Rural Alliance) — confidence-and-supply, 1 bloc(s)" in out
    assert "mainstream (Civic Union Mainstream): lower 40  upper 24" in out
    assert "discipline=50% relationship=60% tax_pref=20% spending_pref=20%" in out


def test_inspect_legislature_shows_deficit_demo_unicameral_composition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, DEFICIT_SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--legislature"]) == 0
    out = capsys.readouterr().out

    assert "legislature:         unicameral" in out
    assert "decree authority:    emergency_only" in out
    assert "lower chamber: 100 seats (strict majority 51)" in out
    assert "authored seats: coalition 40  confidence-and-supply 10  opposition 50" in out
    assert "upper chamber" not in out  # unicameral: exactly one chamber, never a phantom second


def test_inspect_legislature_shows_decree_state_monarchy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The §14 requirement in full: monarchical/hereditary executive, a unicameral 100-seat
    legislature, unlimited decree authority, and 45 coalition against 55 opposition seats."""
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--politics", "--legislature"]) == 0
    out = capsys.readouterr().out

    assert "constitution:        monarchical / hereditary / unicameral / unitary" in out
    assert "legislature:         unicameral" in out
    assert "decree authority:    unlimited" in out
    assert "lower chamber: 100 seats (strict majority 51)" in out
    assert "authored seats: coalition 45  confidence-and-supply 0  opposition 55" in out
    assert "governing_party (Crown Party) — coalition, 1 bloc(s)" in out
    assert "opposition_party (Reform Opposition) — opposition, 1 bloc(s)" in out
    assert "core (Crown Party Core): lower 45" in out
    assert "main (Reform Opposition Main): lower 55" in out


def test_inspect_legislature_never_shows_a_proposal_support_tally(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Authored composition is NOT proposal support. `tiny_valid` carries the walkthrough budget
    58/100 in its lower chamber, but that figure depends on a proposal nobody has submitted at
    inspection time -- printing it here would invent one. The authored coalition total (52) is
    shown instead, and it is deliberately a different number."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--legislature"]) == 0
    out = capsys.readouterr().out

    assert "58/100" not in out
    assert "33/60" not in out
    assert "supporting" not in out
    assert "PASSED" not in out and "FAILED" not in out
    assert "authored seats: coalition 52" in out


def test_inspect_legislature_is_opt_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    assert main(["inspect", "--state", str(save0)]) == 0
    out = capsys.readouterr().out
    assert "authored seats" not in out
    assert "strict majority" not in out


# --- Phase 3B2A (§16): `inspect --capital` -----------------------------------------------------


def test_inspect_capital_shows_bloc_relationships(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--capital"]) == 0
    out = capsys.readouterr().out

    assert "political capital:   500 / 1,000" in out
    assert "bloc relationships:" in out
    assert "rural_alliance/farmers" in out
    # No fabricated ledger or vote tally -- inspection is turn-0 state, not a resolved turn.
    assert "expenditures:" not in out
    assert "committed" not in out


def test_inspect_capital_is_opt_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    assert main(["inspect", "--state", str(save0)]) == 0
    out = capsys.readouterr().out
    assert "bloc relationships:" not in out


# --- Phase 3B2B (§13): `inspect --relationships` -----------------------------------------------


def test_inspect_relationships_shows_current_and_authored_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()

    assert main(["inspect", "--state", str(save0), "--relationships"]) == 0
    out = capsys.readouterr().out

    assert "bloc relationships (current / authored baseline):" in out
    assert "rural_alliance/farmers" in out
    assert "base " in out
    # A fresh scenario opens every bloc exactly at its authored baseline (§9): zero deviation.
    assert "at baseline" in out


def test_inspect_relationships_is_opt_in(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    assert main(["inspect", "--state", str(save0)]) == 0
    out = capsys.readouterr().out
    assert "bloc relationships (current / authored baseline):" not in out


def _resolve_with_decisions(
    tmp_path: Path,
    save0: Path,
    decisions: list[dict],
    out_name: str = "save1.json",
) -> Path:
    """Like `_resolve_with`, but accepts a full raw `decisions` list (any kind, already tagged)
    rather than a single bare budget payload -- needed for a mixed budget + relationship
    investment `DecisionSet`."""
    save1 = tmp_path / out_name
    decisions_file = tmp_path / f"decisions_{out_name}"
    decisions_file.write_text(
        json.dumps({"expected_turn": 0, "expected_state_version": 0, "decisions": decisions}),
        encoding="utf-8",
    )
    argv = [
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
    assert main(argv) == 0
    return save1


def test_resolve_and_history_render_the_same_capital_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(§16) The capital-ledger block follows the SAME shared-renderer discipline as the
    legislative block: `resolve` and `history --turn N` must print identical figures. Submits a
    mixed budget + relationship-investment `DecisionSet` on `tiny_valid`, whose `rural_alliance/
    farmers` bloc opens at a +20.00% relationship (gap 8,000 bps, no truncation ties in this
    range)."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    save1 = _resolve_with_decisions(
        tmp_path,
        save0,
        [
            # Canonical DecisionSet kind order: "bloc_relationship_investment" sorts before
            # "budget" -- reject-not-normalize, so the file must already be in that order.
            {
                "kind": "bloc_relationship_investment",
                "investments": [
                    {
                        "party_id": "rural_alliance",
                        "bloc_id": "farmers",
                        "political_capital": 100,
                    }
                ],
            },
            {"kind": "budget", "personal_income_rate_bps": 2_500},
        ],
    )
    resolve_out = capsys.readouterr().out

    assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
    history_out = capsys.readouterr().out

    for fragment in (
        "political capital:",
        "opening 500  committed 100  regeneration",
        "expenditures:",
        "bloc_relationship_investment",
        "rural_alliance/farmers",
        # (Phase 3B2B) Relationship detail moved off the capital-ledger block entirely, onto its
        # own shared leaf renderer -- `_print_political_relationship_memory`, following the SAME
        # "resolve and history must agree" discipline.
        "bloc relationships:",
        "baseline",
    ):
        assert fragment in resolve_out, fragment
        assert fragment in history_out, fragment


# --- 3/4/16. resolve and history render the same block through the shared helper --------------


def test_resolve_and_history_render_the_same_legislative_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(§14) `_cmd_resolve` and `_cmd_history` must agree, because they call ONE shared renderer.
    Phase 3A shipped a bug where `_cmd_history` had its own inline path and silently omitted a
    whole report section; this test is what makes that class of drift visible."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    save1 = _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500})
    resolve_out = capsys.readouterr().out

    assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
    history_out = capsys.readouterr().out

    for fragment in (
        "legislative:",
        "proposal: budget  route=legislative  outcome=passed_legislative",
        "lower chamber: 58/100 supporting, majority 51 -> PASSED (margin +7)",
        "upper chamber: 33/60 supporting, majority 31 -> PASSED (margin +2)",
        "apportionment: target 58, 1 extra seat(s) awarded on remainders",
        "political capital: committed 0 of 500 opening",
    ):
        assert fragment in resolve_out, fragment
        assert fragment in history_out, fragment


def test_resolve_and_history_render_the_same_election_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(Gate 3C1) `_cmd_resolve` and `_cmd_history` must agree on the election block too, the
    same M10 discipline `_print_election_report` follows for every other shared renderer --
    `tiny_valid`'s real turn-16 election (WON, unaided, real party rows) is the natural real-data
    case, not a synthetic one."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    save1 = tmp_path / "save1.json"
    capsys.readouterr()
    assert main(["resolve", "--state", str(save0), "--turns", "16", "--out", str(save1)]) == 0
    resolve_out = capsys.readouterr().out

    assert main(["history", "--state", str(save1), "--turn", "16"]) == 0
    history_out = capsys.readouterr().out

    for fragment in (
        "election: WON",
        "required 50%",
        "civic_union (coalition):",
        "national_front (opposition):",
        "rural_alliance (confidence_and_supply):",
    ):
        assert fragment in resolve_out, fragment
        assert fragment in history_out, fragment


def test_resolve_and_history_render_the_same_survival_risk_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(Gate 3C2) `_cmd_resolve` and `_cmd_history` must agree on the coup/unrest/impeachment
    block too, the same M10 discipline `_print_coup_unrest_report` follows -- a quiet turn-1
    resolution against `tiny_valid`'s real genesis data (no decisions), read from the real,
    unmodified engine."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    save1 = tmp_path / "save1.json"
    capsys.readouterr()
    assert main(["resolve", "--state", str(save0), "--turns", "1", "--out", str(save1)]) == 0
    resolve_out = capsys.readouterr().out

    assert main(["history", "--state", str(save1), "--turn", "1"]) == 0
    history_out = capsys.readouterr().out

    for fragment in ("survival risk: coup", "unrest", "impeachment"):
        assert fragment in resolve_out, fragment
        assert fragment in history_out, fragment


def test_resolve_and_history_render_the_same_amendment_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(Gate 3C3) `_cmd_resolve` and `_cmd_history` must agree on the constitutional-amendment
    block too, the same M10 discipline `_print_constitutional_amendment_report` follows. Drives
    `decree_state`'s real turn-3 amendment through the CLI's own `--decisions-file` path (two
    relationship-investment turns, then the five-axis amendment) -- the same real campaign the
    calibration suite pins numerically, exercised here through the CLI surface specifically."""
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)

    def _investment_file(pc: int, name: str, expected_turn: int) -> Path:
        path = tmp_path / name
        path.write_text(
            json.dumps(
                {
                    "expected_turn": expected_turn,
                    "expected_state_version": expected_turn,
                    "decisions": [
                        {
                            "kind": "bloc_relationship_investment",
                            "investments": [
                                {
                                    "party_id": "opposition_party",
                                    "bloc_id": "main",
                                    "political_capital": pc,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    save1 = tmp_path / "save1.json"
    assert (
        main(
            [
                "resolve",
                "--state",
                str(save0),
                "--turns",
                "1",
                "--decisions-file",
                str(_investment_file(85, "invest1.json", expected_turn=0)),
                "--out",
                str(save1),
            ]
        )
        == 0
    )
    save2 = tmp_path / "save2.json"
    assert (
        main(
            [
                "resolve",
                "--state",
                str(save1),
                "--turns",
                "1",
                "--decisions-file",
                str(_investment_file(118, "invest2.json", expected_turn=1)),
                "--out",
                str(save2),
            ]
        )
        == 0
    )

    amend_file = tmp_path / "amend.json"
    amend_file.write_text(
        json.dumps(
            {
                "expected_turn": 2,
                "expected_state_version": 2,
                "decisions": [
                    {
                        "kind": "constitutional_amendment",
                        "targets": [
                            {"axis": "decree_authority", "value": "none"},
                            {"axis": "executive_selection", "value": "direct_election"},
                            {"axis": "executive_system", "value": "presidential"},
                            {"axis": "executive_term_limit_terms", "value": 2},
                            {"axis": "national_election_interval_turns", "value": 8},
                        ],
                        "route": "legislative",
                        "influence": [
                            {
                                "party_id": "opposition_party",
                                "bloc_id": "main",
                                "political_capital": 300,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    save3 = tmp_path / "save3.json"
    capsys.readouterr()
    assert (
        main(
            [
                "resolve",
                "--state",
                str(save2),
                "--turns",
                "1",
                "--decisions-file",
                str(amend_file),
                "--out",
                str(save3),
            ]
        )
        == 0
    )
    resolve_out = capsys.readouterr().out

    assert main(["history", "--state", str(save3), "--turn", "3"]) == 0
    history_out = capsys.readouterr().out

    for fragment in (
        "constitutional amendment: route=legislative",
        "decree_authority: unlimited -> none",
        "67/100 seats",
        "outcome: PASSED",
        "qualifies as a liberalization transition",
    ):
        assert fragment in resolve_out, fragment
        assert fragment in history_out, fragment


def test_inspect_institutions_shows_real_bps_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(Gate 3C2) `inspect --institutions` reads the coup formula's own inputs directly from
    state, in strict bps."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    assert main(["inspect", "--state", str(save0), "--institutions"]) == 0
    out = capsys.readouterr().out
    assert "institutions:" in out
    assert "military (Military): loyalty=75% power=65% competence=60% corruption=10%" in out


# --- 5. no proposal ---------------------------------------------------------------------------


def test_no_proposal_renders_without_fake_chambers_or_route(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    _resolve_with(tmp_path, save0, None)
    out = capsys.readouterr().out

    assert "legislative:" in out
    assert "no budget proposal submitted" in out
    assert "political capital committed: 0" in out
    # No invented route, no invented chamber table.
    assert "route=" not in out
    assert "chamber:" not in out
    assert "apportionment:" not in out


# --- 6. passed bicameral ----------------------------------------------------------------------


def test_passed_bicameral_shows_each_chamber_passing_independently(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    capsys.readouterr()
    _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500})
    out = capsys.readouterr().out

    assert "lower chamber: 58/100 supporting, majority 51 -> PASSED (margin +7)" in out
    assert "upper chamber: 33/60 supporting, majority 31 -> PASSED (margin +2)" in out
    # Bloc rows carry identity, role, seats and the full apportionment audit trail.
    assert "civic_union/mainstream" in out
    assert "rural_alliance/farmers" in out
    assert "confidence_and_supply" in out
    assert "bonus +1" in out
    # Never a pooled 91/160 line implying passage came from a combined tally.
    assert "91/160" not in out
    assert "budget NOT applied" not in out


# --- 7. failed unicameral + explicit warning ---------------------------------------------------


def test_failed_unicameral_shows_shortfall_and_budget_not_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, DEFICIT_SCENARIO_PATH)
    capsys.readouterr()
    # deficit_demo opens at 15%; +5pp is 20%.
    _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_000})
    out = capsys.readouterr().out

    assert "outcome=failed_legislative" in out
    assert "lower chamber: 47/100 supporting, majority 51 -> FAILED (short 4)" in out
    assert "budget NOT applied — existing tax policy and spending plan remain in force" in out


# --- 8. the exact 282/283 boundary --------------------------------------------------------------


def _influence(amount: int) -> dict:
    return {
        "personal_income_rate_bps": 2_500,
        "influence": [
            {"party_id": "opposition_party", "bloc_id": "main", "political_capital": amount}
        ],
    }


def test_decree_state_283_passes_by_exactly_one_seat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)
    capsys.readouterr()
    _resolve_with(tmp_path, save0, _influence(283))
    out = capsys.readouterr().out

    assert "outcome=passed_legislative" in out
    assert "lower chamber: 51/100 supporting, majority 51 -> PASSED (margin +0)" in out
    assert "political capital: committed 283 of 500 opening" in out
    assert "budget NOT applied" not in out


def test_decree_state_282_fails_by_exactly_one_seat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)
    capsys.readouterr()
    _resolve_with(tmp_path, save0, _influence(282))
    out = capsys.readouterr().out

    assert "outcome=failed_legislative" in out
    assert "lower chamber: 50/100 supporting, majority 51 -> FAILED (short 1)" in out
    # A failed vote still consumes the capital it committed (D2).
    assert "political capital: committed 282 of 500 opening" in out
    assert "budget NOT applied — existing tax policy and spending plan remain in force" in out


# --- 9. decree: no chamber or bloc rows --------------------------------------------------------


def test_decree_renders_without_any_chamber_or_bloc_vote_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)
    capsys.readouterr()
    _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500, "route": "decree"})
    out = capsys.readouterr().out

    assert "proposal: budget  route=decree  outcome=enacted_by_decree" in out
    assert "political capital: committed 250 of 500 opening" in out
    assert "enacted through executive decree authority — no chamber vote" in out
    # A decree is not voted on: nothing to tabulate, so nothing is printed.
    assert "chamber:" not in out
    assert "apportionment:" not in out
    # (Phase 3B2B) `governing_party/core` now legitimately appears in the bloc-relationships
    # block -- a genuine policy reaction plus decree-bypass penalty, never a vote table -- so the
    # absence check narrows to what it always meant: no vote/apportionment tabulation exists.
    assert "bloc relationships:" in out
    assert "PASSED" not in out and "FAILED" not in out


# --- 10. unavailable decree stays an atomic, output-free failure ------------------------------


def test_unavailable_decree_writes_no_output_or_temp_file(tmp_path: Path) -> None:
    """`tiny_valid` is `emergency_only`, so a decree is constitutionally unavailable there and
    the whole turn aborts before a report exists (which is also why it gets no reason ID)."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    before = save0.read_bytes()
    out_path = tmp_path / "never_written.json"
    decisions_file = tmp_path / "decree.json"
    decisions_file.write_text(
        json.dumps(
            {
                "expected_turn": 0,
                "expected_state_version": 0,
                "decisions": [
                    {"kind": "budget", "personal_income_rate_bps": 2_500, "route": "decree"}
                ],
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
            str(decisions_file),
            "--out",
            str(out_path),
        ]
    )

    assert exit_code == 1
    assert not out_path.exists()
    assert save0.read_bytes() == before
    # No partial or temporary file left behind anywhere in the directory.
    assert {p.name for p in tmp_path.iterdir()} == {save0.name, decisions_file.name}


# --- 11. inspect on an invalid save: concise error, nonzero exit, never a raw traceback -------
#
# `_cmd_inspect` deliberately still reports what it can on an invalid save (its own docstring:
# "even an invalid save can be inspected"), but that tolerance had a real gap: reading the latest
# entry's report for the "production (latest)"/"tax bases (latest)" convenience lines used to call
# `.report()` unguarded, ahead of the final integrity check -- so a save whose latest entry's
# report failed schema or semantic validation crashed with a raw `pydantic.ValidationError`
# traceback instead of the documented "reported via a nonzero exit rather than a stack trace"
# behavior. These three tests reproduce the tamper classes Part 3 requires and confirm the fix:
# a concise, actionable error; exit 1; no traceback (an uncaught exception here would fail the
# test itself, since `main()` only catches `MandateError`); no output file (inspect takes none);
# and the input file byte-identical after the call.


def _load_envelope(save_path: Path) -> dict:
    return json.loads(save_path.read_text(encoding="utf-8"))


def _write_envelope(save_path: Path, envelope: dict) -> None:
    from app.core.canonical_json import canonical_dumps

    save_path.write_text(canonical_dumps(envelope), encoding="utf-8")


def _rehash_last_entry(envelope: dict) -> None:
    """Recompute the last entry's `entry_hash` (and the envelope's `head_entry_hash`) from its
    current, possibly-just-tampered content -- simulating a knowledgeable tamperer who does the
    hash arithmetic themselves, per `test_history.py`'s `_retamper_entry_with_consistent_hash`."""
    from app.core.canonical_json import canonical_digest, canonical_dumps
    from app.simulation.history import _entry_hash_payload

    entry = envelope["entries"][-1]
    entry["report_json"] = canonical_dumps(json.loads(entry["report_json"]))
    new_hash = canonical_digest(
        _entry_hash_payload(
            turn=entry["turn"],
            previous_entry_hash=entry["previous_entry_hash"],
            state=json.loads(entry["state_json"]),
            decisions=(
                json.loads(entry["decisions_json"]) if entry["decisions_json"] is not None else None
            ),
            report=json.loads(entry["report_json"]),
            ruleset_version=entry["ruleset_version"],
            content_version=entry["content_version"],
        )
    )
    entry["entry_hash"] = new_hash
    envelope["head_entry_hash"] = new_hash


def test_inspect_on_a_stale_hash_tamper_reports_cleanly_not_a_traceback(tmp_path: Path) -> None:
    """A traditional tamper: the report is edited but `entry_hash` is left stale (the tamperer
    forgot to update it). Caught purely by the hash-chain check, well before any report content
    is even schema-validated -- confirming the ordinary case never regressed."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    save1 = _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500})
    before = save1.read_bytes()

    envelope = _load_envelope(save1)
    entry = envelope["entries"][-1]
    report = json.loads(entry["report_json"])
    report["legislative"]["political_capital_committed"] += 1
    entry["report_json"] = json.dumps(report)  # deliberately NOT re-canonicalized or re-hashed
    _write_envelope(save1, envelope)

    exit_code = main(["inspect", "--state", str(save1)])

    assert exit_code == 1
    assert save1.read_bytes() != before  # this test's own setup wrote the tamper; expected


def test_inspect_on_a_consistently_rehashed_schema_tamper_reports_cleanly(
    tmp_path: Path,
) -> None:
    """A knowledgeable tamperer edits a report field out of its strict schema range (a negative
    `political_capital_committed`) and recomputes `entry_hash` to match -- the hash chain passes,
    so only `TurnReport.model_validate` (schema validation, at replay parse) can catch it. This
    is exactly the call `_cmd_inspect` used to make unguarded."""
    save0 = _new_save(tmp_path, SCENARIO_PATH)
    save1 = _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500})
    before = save1.read_bytes()

    envelope = _load_envelope(save1)

    def _tamper(report: dict) -> None:
        report["legislative"]["political_capital_committed"] = -1

    entry = envelope["entries"][-1]
    report = json.loads(entry["report_json"])
    _tamper(report)
    entry["report_json"] = json.dumps(report)
    _rehash_last_entry(envelope)
    _write_envelope(save1, envelope)

    capsys_exit = main(["inspect", "--state", str(save1)])

    assert capsys_exit == 1
    assert save1.read_bytes() != before  # this test's own setup wrote the tamper; expected


def test_inspect_on_a_consistently_rehashed_relationship_validator_tamper_reports_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuine decree on `decree_state` produces real `political_relationship.blocs` rows; one
    row's `closing_relationship_bps` is edited to violate its OWN row validator
    (`_closing_and_applied_change_match_the_single_clamp`), then the hash is recomputed to match.
    This is the specific case Part 3 calls out: a semantic tamper that fails a
    relationship-report validator, not just a bare schema range. Confirms `inspect` reports it
    concisely (a validation error naming the row) rather than crashing, and that `integrity:
    INVALID` still appears -- the same fact `validate_history` records, printed once, not
    duplicated by a raw traceback."""
    save0 = _new_save(tmp_path, DECREE_SCENARIO_PATH)
    save1 = _resolve_with(tmp_path, save0, {"personal_income_rate_bps": 2_500, "route": "decree"})
    before = save1.read_bytes()

    envelope = _load_envelope(save1)
    entry = envelope["entries"][-1]
    report = json.loads(entry["report_json"])
    blocs = report["political_relationship"]["blocs"]
    assert blocs, "a genuine decree must produce at least one relationship-memory row"
    blocs[0]["closing_relationship_bps"] += 1  # breaks the single-clamp identity
    entry["report_json"] = json.dumps(report)
    _rehash_last_entry(envelope)
    _write_envelope(save1, envelope)

    exit_code = main(["inspect", "--state", str(save1)])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "integrity:           INVALID" in out
    assert "closing_relationship_bps" in out
    assert save1.read_bytes() != before  # this test's own setup wrote the tamper; expected
