"""Shared exception hierarchy for MANDATE.

Kept in `core` (rather than `simulation`) so both the simulation engine and,
later, the API/service layer can raise and catch the same error types without
`app.api` importing from `app.simulation` internals.
"""

from __future__ import annotations

from dataclasses import dataclass


class MandateError(Exception):
    """Base class for all MANDATE application errors."""


@dataclass(frozen=True)
class InvariantViolation:
    """A single invariant check failure.

    A plain value, not an exception — `simulation.invariants.check_invariants`
    returns a `list[InvariantViolation]` for the caller to inspect; only the
    aggregate `StateValidationError` below is ever actually raised. Carries a
    stable machine-readable `code` (e.g. "group_shares_not_normalized") in
    addition to a human-readable `message`, so callers (tests, API error
    responses) can key off the code rather than parsing message text.
    """

    code: str
    message: str


class StateValidationError(MandateError):
    """Aggregates one or more `InvariantViolation`s.

    Raised by `check_invariants` / `resolve_turn` when validation fails, so
    callers get every violation at once instead of only the first.
    """

    def __init__(self, violations: list[InvariantViolation]) -> None:
        if not violations:
            raise ValueError("StateValidationError requires at least one violation")
        self.violations = violations
        summary = "; ".join(f"{v.code}: {v.message}" for v in violations)
        super().__init__(f"{len(violations)} invariant violation(s): {summary}")


class DecisionSetError(MandateError):
    """A submitted `DecisionSet` is invalid or stale.

    Distinct from `StateValidationError`: this is about the *submission*
    (wrong turn, wrong state version, malformed decision) rather than the
    game state itself.
    """


class TurnResolutionError(MandateError):
    """Raised when a turn cannot be resolved.

    Wraps either a `DecisionSetError` or a `StateValidationError` as `__cause__`
    is set by the raiser. The caller's original `GameState` is guaranteed
    untouched whenever this is raised — see `simulation/resolver.py`.
    """


class ScenarioValidationError(MandateError):
    """A scenario file failed content validation."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        detail = "; ".join(problems)
        super().__init__(f"scenario {source!r} is invalid: {detail}")


class SaveFileError(MandateError):
    """A save/state file is missing, corrupt, or version-incompatible."""
