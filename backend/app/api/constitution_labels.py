"""Player-facing labels for the constitution's axes.

Moved here unchanged from `policy_cards.py` (Gate 4A3 victory path) so the policy-card catalog and
the campaign objective (`objective.py`) word every axis value identically. `policy_cards.py`
imports the projection models, and `projections.py` imports the objective, so these tables need a
home neither module depends on.
"""

from __future__ import annotations

from app.simulation.constitution import DecreeAuthority, ExecutiveSelection, ExecutiveSystem

EXECUTIVE_SYSTEM_LABELS: dict[ExecutiveSystem, str] = {
    ExecutiveSystem.PRESIDENTIAL: "Presidential",
    ExecutiveSystem.PARLIAMENTARY: "Parliamentary",
    ExecutiveSystem.SEMI_PRESIDENTIAL: "Semi-presidential",
    ExecutiveSystem.MONARCHICAL: "Monarchical",
}
EXECUTIVE_SELECTION_LABELS: dict[ExecutiveSelection, str] = {
    ExecutiveSelection.DIRECT_ELECTION: "Direct election",
    ExecutiveSelection.LEGISLATIVE_SELECTION: "Selected by the legislature",
    ExecutiveSelection.HEREDITARY: "Hereditary succession",
    ExecutiveSelection.APPOINTED: "Appointed",
}
DECREE_AUTHORITY_LABELS: dict[DecreeAuthority, str] = {
    DecreeAuthority.NONE: "No decree authority",
    DecreeAuthority.EMERGENCY_ONLY: "Emergency decree authority only",
    DecreeAuthority.UNLIMITED: "Unlimited decree authority",
}


def election_interval_label(turns: int | None) -> str:
    if turns is None:
        return "No scheduled national election"
    return f"Every {turns} turn" if turns == 1 else f"Every {turns} turns"
