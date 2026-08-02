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
    """A save file is missing, unreadable, or not valid JSON.

    Distinct from `HistoryValidationError` (the file parses fine but its
    *content* fails history/integrity checks) and `SaveCompatibilityError`
    (the file parses fine but declares an unsupported version).
    """


class SaveCompatibilityError(MandateError):
    """Base class for version-incompatible saves. Never raised directly.

    Save-format version, ruleset version, and content version are distinct
    concepts (see `docs/adr/0002-snapshot-history-and-versioning.md`) and
    each gets its own subclass so callers can tell which one is wrong.
    """

    def __init__(self, kind: str, found: str, supported: str) -> None:
        self.kind = kind
        self.found = found
        self.supported = supported
        super().__init__(
            f"unsupported {kind} {found!r}; this build supports: {supported}. "
            "The save was not loaded; nothing was modified."
        )


class UnsupportedSaveFormatVersionError(SaveCompatibilityError):
    def __init__(self, found: str, supported: str) -> None:
        super().__init__("save_format_version", found, supported)


class UnsupportedRulesetVersionError(SaveCompatibilityError):
    def __init__(self, found: str, supported: str) -> None:
        super().__init__("ruleset_version", found, supported)


class UnsupportedContentVersionError(SaveCompatibilityError):
    def __init__(self, found: str, supported: str) -> None:
        super().__init__("content_version", found, supported)


class HistoryValidationError(MandateError):
    """A save's history failed structural or cryptographic integrity checks.

    Carries every problem found (see `simulation.history.validate_history`),
    not just the first — tampering often breaks several checks at once
    (e.g. a truncated tail breaks both `entry_count` and `head_entry_hash`),
    and an actionable error should say so.
    """

    def __init__(self, problems: list[str]) -> None:
        if not problems:
            raise ValueError("HistoryValidationError requires at least one problem")
        self.problems = problems
        super().__init__(f"{len(problems)} history integrity problem(s): " + "; ".join(problems))


class SnapshotNotFoundError(MandateError):
    """A requested turn number has no corresponding history entry."""

    def __init__(self, turn: int, available_turns: list[int]) -> None:
        self.turn = turn
        self.available_turns = available_turns
        span = f"{available_turns[0]}-{available_turns[-1]}" if available_turns else "none"
        super().__init__(f"no history entry for turn {turn}; available turns: {span}")
