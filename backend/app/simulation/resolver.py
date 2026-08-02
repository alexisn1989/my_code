"""Turn resolution: the one place a `GameState` is advanced.

`resolve_turn` is a pure function — see `docs/architecture.md`, "Turn
resolution", for the full contract. In short:

1. Validate the `DecisionSet` against the *input* `state` (stale-submission
   check) and validate the input `state`'s own invariants. Both happen
   before anything is copied, so a failure here cannot have touched `state`.
2. Only then, deep-copy `state` into a working copy and advance its
   `turn`/`state_version`.
3. Run every phase in `phases.PHASE_ORDER`, in order, against the working copy.
4. Re-validate invariants on the result. A violation discards the working
   copy entirely; the caller's original `state` is still exactly what they
   passed in.
5. Return the new state and an explainable `TurnReport`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import DecisionSetError, StateValidationError, TurnResolutionError
from app.simulation.decisions import DecisionSet
from app.simulation.invariants import check_invariants
from app.simulation.phases import PhaseContext, run_phases
from app.simulation.report import TurnReport, TurnReportDevMeta
from app.simulation.state import GameState


@dataclass(frozen=True)
class TurnResolution:
    """The result of a successful `resolve_turn` call."""

    state: GameState
    report: TurnReport


def _validate_decision_set(state: GameState, decisions: DecisionSet) -> None:
    problems: list[str] = []
    if decisions.expected_turn != state.turn:
        problems.append(
            f"stale decision set: expected_turn={decisions.expected_turn} "
            f"but state.turn={state.turn}"
        )
    if decisions.expected_state_version != state.state_version:
        problems.append(
            f"stale decision set: expected_state_version={decisions.expected_state_version} "
            f"but state.state_version={state.state_version}"
        )
    if problems:
        raise DecisionSetError("; ".join(problems))


def resolve_turn(state: GameState, decisions: DecisionSet) -> TurnResolution:
    """Resolve one turn. Never mutates `state`; raises `TurnResolutionError` on failure.

    On any failure — a stale/invalid decision set, an already-invalid input
    state, or a resulting state that fails invariant checks — the exact
    object passed in as `state` is guaranteed untouched. This is proven, not
    just intended: `tests/test_resolver.py` snapshots the input state's
    canonical JSON before calling `resolve_turn` and asserts it is byte-
    identical afterward whenever an error is raised.
    """
    try:
        _validate_decision_set(state, decisions)
    except DecisionSetError as exc:
        raise TurnResolutionError(f"decision set rejected: {exc}") from exc

    input_violations = check_invariants(state)
    if input_violations:
        cause = StateValidationError(input_violations)
        raise TurnResolutionError(f"input state failed invariant checks: {cause}") from cause

    resolving_turn = state.turn
    working = state.model_copy(deep=True)
    working.turn = resolving_turn + 1
    working.state_version = state.state_version + 1

    ctx = PhaseContext(state=working, decisions=decisions, resolving_turn=resolving_turn)
    run_phases(ctx)

    output_violations = check_invariants(working)
    if output_violations:
        cause = StateValidationError(output_violations)
        raise TurnResolutionError(
            f"resolution produced an invalid state, discarded: {cause}"
        ) from cause

    report = TurnReport(
        game_seed=working.seed,
        resolved_turn=resolving_turn,
        entries=ctx.report_entries,
        dev=TurnReportDevMeta(phase_statuses=ctx.phase_statuses),
        finance=ctx.finance_report,
        production=ctx.production_report,
        tax_base_derivation=ctx.tax_base_derivation_report,
    )
    return TurnResolution(state=working, report=report)
