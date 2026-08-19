"""The one process-wide game session, and the mutation boundary guarding it.

Phase 4A has exactly **one** authoritative `GameSave` per running process --
not per browser tab, per cookie, or per user. Two tabs against the same server
share the same game, which is the deliberate simplification the frozen plan
records (§4.4). It follows directly that **multiple Uvicorn workers are
unsupported and prohibited**: each worker would own a different `GameSession`
and a different idea of the current save, so `mandate-gui` pins one process and
one worker.

The mutation boundary is deliberately two layers, and both are load-bearing:

  1. A **synchronous admission flag**, tested and set with no `await` in
     between. Under asyncio's cooperative scheduling nothing can interleave
     between that test and that set, so a second mutation arriving while one is
     in flight is refused *immediately*. This is what makes refusal
     non-queueing.

  2. A **real process-wide `asyncio.Lock`**, acquired after admission. The flag
     alone would be an admission marker rather than a concurrency primitive; the
     lock is the actual mutual-exclusion boundary around the one authoritative
     transaction, and it stays correct if a future route ever hands work to
     another task.

Why not `if lock.locked(): raise` followed by `await lock.acquire()`: that
sequence is **not atomic**. The event loop may schedule another coroutine
between the test and the acquire, so two requests can both observe an unlocked
lock and both proceed. The admission flag exists precisely to close that window.

Both layers are released in `finally`, which runs for `BaseException` and so
covers `asyncio.CancelledError` from a disconnecting client. **No waiting queue
is ever formed**: a request is admitted or refused, never parked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.errors import MandateError
from app.simulation.history import GameSave

from .save_registry import SaveRepository


class SessionBusyError(MandateError):
    """A mutation is already in flight. Maps to 409 `resolution_in_progress`."""


class NoActiveSessionError(MandateError):
    """No game is loaded. Maps to 404 `no_active_session`."""


class MutationBoundary:
    """Non-waiting admission in front of a real process-wide lock."""

    def __init__(self) -> None:
        self._admitted = False
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        """True while a mutation holds admission. Read-only; never a gate on its own."""
        return self._admitted

    @asynccontextmanager
    async def admit(self, operation: str) -> AsyncIterator[None]:
        """Admit one mutation, or refuse immediately.

        The `if self._admitted: raise` / `self._admitted = True` pair below has
        no `await` between the test and the set, which is what makes admission
        atomic. Only after admission is the real lock awaited -- and because
        admission is exclusive, that await never actually waits, so no queue can
        form behind it.
        """
        if self._admitted:
            raise SessionBusyError(f"a {operation} is already being resolved")
        self._admitted = True
        try:
            async with self._lock:
                yield
        finally:
            # `finally` runs for BaseException too, so a cancelled request
            # cannot leave the session permanently busy.
            self._admitted = False


class GameSession:
    """The single authoritative session: one save, one save ID, one boundary."""

    def __init__(self, repository: SaveRepository) -> None:
        self._repository = repository
        self._current_save: GameSave | None = None
        self._save_id: str | None = None
        self.boundary = MutationBoundary()

    @property
    def repository(self) -> SaveRepository:
        return self._repository

    @property
    def is_active(self) -> bool:
        return self._current_save is not None

    @property
    def current_save(self) -> GameSave:
        if self._current_save is None:
            raise NoActiveSessionError("no active game session")
        return self._current_save

    @property
    def save_id(self) -> str:
        if self._save_id is None:
            raise NoActiveSessionError("no active game session")
        return self._save_id

    def adopt(self, save: GameSave, save_id: str) -> None:
        """Swap in a new authoritative save.

        Called **only after** the save has been durably persisted (on a new game
        or a resolve) or successfully read and validated (on a load), so the
        in-memory pointer never moves ahead of the disk.
        """
        self._current_save = save
        self._save_id = save_id

    def clear(self) -> None:
        """Drop the active session. Used by tests and by a failed load path."""
        self._current_save = None
        self._save_id = None
