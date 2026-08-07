"""Phase 3A slot-10 phase-level tests not owned by a more specific file:
`test_political_report.py` corrupts report fields in isolation, `test_baseline_lifecycle.py`
proves the baseline lifecycle end to end, `test_legitimacy_neutrality.py` proves form/support
independence (T-R1a-c), and `test_phase_isolation.py` proves the one-way economy->politics
dependency (T-I1..I3). What remains here is T-P5: nothing spends political capital in Phase 3A.

T-D1 (determinism including every political field) and T-R1e (same-input byte identity) are
already covered by `test_determinism.py`'s whole-state/whole-report canonical-JSON comparisons —
`politics`/`political` are ordinary fields of `GameState`/`TurnReport` now, so those existing
byte-identity checks already include them with no dedicated test needed.
"""

from __future__ import annotations

from pathlib import Path

from app.content.scenarios import load_scenario_file
from app.simulation.decisions import DecisionSet
from app.simulation.resolver import resolve_turn
from tests.conftest import SCENARIO_DIR


def _resolve_n(scenario_path: Path, n: int) -> list:  # type: ignore[type-arg]
    state = load_scenario_file(scenario_path)
    reports = []
    for _ in range(n):
        decisions = DecisionSet(
            expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
        )
        resolution = resolve_turn(state, decisions)
        reports.append(resolution.report)
        state = resolution.state
    return reports


def test_political_capital_spent_is_always_zero_in_phase_3a() -> None:
    """(T-P5, §7) `political_capital_spent` is carried in the report so the reconciliation
    identity `closing == min(capacity, opening + regeneration - spent)` is already the final one
    3B will use, but nothing in Phase 3A decreases political capital -- spending needs a
    legislature, factions and a reform system, none of which exist yet. Checked across both
    scenarios for 20 turns each, including the turns where `tiny_valid` clamps at capacity and
    where `deficit_demo` takes its two performance hits, so the invariant is proven under every
    regime the fixtures exercise."""
    for name in ("tiny_valid", "deficit_demo"):
        reports = _resolve_n(SCENARIO_DIR / f"{name}.yaml", 20)
        for turn, report in enumerate(reports, start=1):
            assert report.political is not None
            assert report.political.political_capital_spent == 0, f"{name} turn {turn}"
