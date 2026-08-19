"""Engine errors to HTTP, through one problem shape.

The engine already has a structured error taxonomy (`app.core.errors`), so this
module is a **mapping table over existing types**, not a new set of exceptions.
Every response body has the same shape, so a client never has to guess whether
`detail` is a string or an object.

Two mapping choices worth stating, because they are judgement calls rather than
mechanics:

  * `GameAlreadyConcludedError`, version incompatibility, failed history
    validation, a stale revision and a busy session are all **409**. They share
    a meaning -- "the request is well-formed but conflicts with the current
    state of the resource" -- and each carries a distinct stable `type` so the
    UI can tell them apart without parsing prose.
  * `StateValidationError` is **500**, not 4xx. If the engine rejects the state
    it just produced, the client did nothing wrong; something in the engine is
    inconsistent, and the save is deliberately left untouched.

`detail` carries the engine's own message verbatim. That is a deliberate
trade: the messages are written for a developer-operator on loopback, and
paraphrasing them here would put a second, driftable description of every
failure in the codebase.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.core.errors import (
    DecisionSetError,
    GameAlreadyConcludedError,
    HistoryValidationError,
    MandateError,
    SaveCompatibilityError,
    SaveFileError,
    ScenarioValidationError,
    SnapshotNotFoundError,
    StateValidationError,
    TurnResolutionError,
)

from .save_registry import InvalidDisplayNameError, InvalidSaveIdError, SaveNotFoundError
from .session import NoActiveSessionError, SessionBusyError

PROBLEM_MEDIA_TYPE = "application/problem+json"


class FieldProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    message: str


class Problem(BaseModel):
    """The single error shape every failure uses."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str | None = None
    fields: tuple[FieldProblem, ...] = ()
    extra: dict[str, Any] = {}


def problem_response(
    *,
    type_: str,
    title: str,
    status: int,
    detail: str | None = None,
    fields: tuple[FieldProblem, ...] = (),
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body = Problem(
        type=type_, title=title, status=status, detail=detail, fields=fields, extra=extra or {}
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json"), media_type=PROBLEM_MEDIA_TYPE
    )


#: (exception type) -> (status, stable type slug, human title).
#: Ordered most specific first: `SaveCompatibilityError`'s three subclasses and
#: `SaveNotFoundError` must be matched before their bases.
_MAPPING: tuple[tuple[type[Exception], int, str, str], ...] = (
    (SessionBusyError, 409, "resolution_in_progress", "Another action is being resolved"),
    (NoActiveSessionError, 404, "no_active_session", "No active game"),
    (InvalidSaveIdError, 400, "save_not_found", "That save could not be found"),
    (SaveNotFoundError, 404, "save_not_found", "That save could not be found"),
    (InvalidDisplayNameError, 422, "invalid_display_name", "That name cannot be used"),
    (SaveCompatibilityError, 409, "save_incompatible", "That save was made by another version"),
    (HistoryValidationError, 409, "history_invalid", "That save failed its integrity check"),
    (GameAlreadyConcludedError, 409, "game_concluded", "The campaign has already ended"),
    (SnapshotNotFoundError, 404, "snapshot_not_found", "No such turn"),
    (ScenarioValidationError, 400, "scenario_invalid", "That scenario could not be loaded"),
    (SaveFileError, 400, "save_unreadable", "That save could not be read"),
    (DecisionSetError, 422, "decision_rejected", "Those decisions were rejected"),
    (TurnResolutionError, 422, "decision_rejected", "The turn could not be resolved"),
    (StateValidationError, 500, "internal_error", "The engine rejected the resulting state"),
)


def _describe(error: Exception) -> tuple[int, str, str]:
    for candidate, status, slug, title in _MAPPING:
        if isinstance(error, candidate):
            return status, slug, title
    return 500, "internal_error", "Unexpected error"


def register_exception_handlers(app: FastAPI) -> None:
    """Install the handlers that turn engine errors into the problem shape."""

    @app.exception_handler(MandateError)
    async def _mandate_error(request: Request, error: Exception) -> JSONResponse:
        status, slug, title = _describe(error)
        extra: dict[str, Any] = {}
        if isinstance(error, GameAlreadyConcludedError):
            # Enough for the client to route straight to the terminal screen
            # without a second request.
            extra = {
                "bucket": getattr(error.bucket, "value", str(error.bucket)),
                "reason": getattr(error.reason, "value", str(error.reason)),
                "turn": error.turn,
            }
        elif isinstance(error, SnapshotNotFoundError):
            extra = {"turn": error.turn, "available_turns": list(error.available_turns)}
        return problem_response(
            type_=slug, title=title, status=status, detail=str(error), extra=extra
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, error: Exception) -> JSONResponse:
        """Schema rejection -- the payload never reached the engine.

        Field paths are preserved so the decision workspace can attach each
        message to the control that produced it.
        """
        raw = error.errors() if isinstance(error, RequestValidationError) else []
        fields = tuple(
            FieldProblem(
                path=".".join(str(part) for part in entry.get("loc", ())),
                message=str(entry.get("msg", "invalid")),
            )
            for entry in raw
        )
        return problem_response(
            type_="decision_rejected",
            title="That request was rejected",
            status=422,
            detail="the submitted payload did not match the expected schema",
            fields=fields,
        )
