"""The fixed, documented turn resolution order (product spec §7).

`PHASE_ORDER` is the fifteen-step resolution order from the brief, encoded as
data — a tuple of `(phase_id, handler)` pairs — rather than as a sequence of
separate calls buried in `resolver.py`. That makes the order declared exactly
once, testable exactly once (`tests/test_resolver.py` asserts the literal
sequence of phase IDs that ran), and impossible to silently reorder by
editing call sites.

Every phase handler has the same signature, `(ctx: PhaseContext) -> None`,
and is expected to mutate `ctx.state` in place and call
`ctx.mark_implemented()` if it does real work. This session implements real
logic only for `generate_turn_report`; every other phase is a registered,
honest no-op (see `docs/architecture.md`, "Turn resolution", and
`simulation.report` for why that's tracked as dev metadata rather than
player-facing report noise).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.rng import derive_rng
from app.simulation.decisions import DecisionSet
from app.simulation.report import PhaseStatus, TurnReportEntry
from app.simulation.state import GameState

if TYPE_CHECKING:
    # Only needed for the `random.Random` annotation below. A real (unguarded)
    # `import random` here would defeat the purpose of `core.rng.derive_rng` —
    # see `tests/test_no_forbidden_imports.py`, which allows TYPE_CHECKING-only
    # imports precisely because they can never execute and so can never
    # introduce non-determinism.
    import random


@dataclass
class PhaseContext:
    """Mutable working state threaded through phase handlers during one resolution."""

    state: GameState
    """The working copy being mutated. Never the caller's original object."""
    decisions: DecisionSet
    resolving_turn: int
    """The turn number being resolved (i.e. `state.turn` as it was *before* this resolution)."""
    report_entries: list[TurnReportEntry] = field(default_factory=list)
    phase_statuses: dict[str, PhaseStatus] = field(default_factory=dict)
    _current_phase_id: str | None = field(default=None, repr=False)

    def rng(self, stream: str) -> random.Random:
        """A deterministic RNG for `stream`, namespaced to this game/turn/stream triple."""
        return derive_rng(self.state.seed, self.resolving_turn, stream)

    def mark_implemented(self) -> None:
        """Call from within a phase handler to record that it did real work."""
        if self._current_phase_id is None:
            raise RuntimeError("mark_implemented() called outside of phase execution")
        self.phase_statuses[self._current_phase_id] = PhaseStatus.IMPLEMENTED


PhaseHandler = Callable[[PhaseContext], None]


def _noop(_ctx: PhaseContext) -> None:
    """Placeholder for a resolution step not yet implemented (tracked in dev metadata)."""


def _generate_turn_report(ctx: PhaseContext) -> None:
    ctx.report_entries.append(
        TurnReportEntry(
            category="administration",
            summary=f"Turn {ctx.resolving_turn} resolved.",
            detail=(
                "This build implements turn advancement, invariant checking, and report "
                "generation only; gameplay systems (economy, population, diplomacy, military, "
                "events) are not yet active — see dev.phase_statuses for exactly which "
                "resolution steps ran real logic."
            ),
        )
    )
    ctx.mark_implemented()


# The fifteen-step resolution order from product spec §7. Order matters and is tested.
PHASE_ORDER: tuple[tuple[str, PhaseHandler], ...] = (
    ("validate_and_reserve_actions", _noop),
    ("apply_legal_and_administrative_changes", _noop),
    ("resolve_production_and_trade", _noop),
    ("resolve_government_revenue_and_expenditure", _noop),
    ("update_prices_inflation_employment_debt_reserves", _noop),
    ("resolve_public_services_and_infrastructure", _noop),
    ("resolve_diplomacy_and_sanctions", _noop),
    ("resolve_military_movement_and_combat", _noop),
    ("apply_casualties_occupation_disruption_war_costs", _noop),
    ("update_group_welfare_approval_trust_radicalization", _noop),
    ("update_institutional_loyalty_competence_corruption_power", _noop),
    ("evaluate_protests_strikes_insurgency_coups_revolutions", _noop),
    ("evaluate_elections_and_constitutional_events", _noop),
    ("trigger_narrative_events", _noop),
    ("generate_turn_report", _generate_turn_report),
)

PHASE_IDS: tuple[str, ...] = tuple(phase_id for phase_id, _ in PHASE_ORDER)


def run_phases(ctx: PhaseContext) -> None:
    """Run every phase in `PHASE_ORDER`, in order, recording a status for each."""
    for phase_id, handler in PHASE_ORDER:
        ctx._current_phase_id = phase_id  # same-module access to the phase-execution protocol
        ctx.phase_statuses.setdefault(phase_id, PhaseStatus.NOT_IMPLEMENTED)
        handler(ctx)
        ctx._current_phase_id = None
