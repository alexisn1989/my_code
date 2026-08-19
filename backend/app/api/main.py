"""Application factory, settings, and the `mandate-gui` entry point.

Gate 4A1 skeleton: this module currently builds a bare application and resolves
the settings every later commit depends on (bind address, port, save root,
scenario root). Routing, security middleware, SPA serving and the real startup
command arrive in this gate's later commits.

**One process, one worker, always.** The authoritative game session is process
memory (`app.api.session`), so two Uvicorn workers would own two different
`GameSession` objects and two different ideas of the current save. Multi-worker
deployment is therefore unsupported and prohibited, and `run()` pins
`workers=1`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

DEFAULT_PORT = 8420
DEFAULT_BIND_HOST = "127.0.0.1"


def _default_repo_root() -> Path:
    """The repository root, derived from this file's location.

    `app/api/main.py` -> `app/api` -> `app` -> `backend` -> repo root. Used only
    to locate `data/scenarios` and a default save root during development; both
    are overridable, and neither is ever taken from a client request.
    """
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ApiSettings:
    """Resolved once at startup. Never influenced by request content."""

    bind_host: str = DEFAULT_BIND_HOST
    port: int = DEFAULT_PORT
    save_root: Path = Path.home() / ".mandate" / "saves"
    scenario_root: Path = _default_repo_root() / "data" / "scenarios"
    frontend_dist: Path = _default_repo_root() / "frontend" / "dist"
    serve_spa: bool = True

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Exactly the two loopback spellings at the configured port.

        Derived from `port` rather than hand-maintained, so a `--port` override
        cannot leave the old port authorised.
        """
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset({f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"})


def settings_from_env() -> ApiSettings:
    """Build settings from the environment, falling back to the defaults.

    Environment is used rather than request data on purpose: nothing a browser
    sends may influence where saves are read from or written to.
    """
    save_root = os.environ.get("MANDATE_SAVE_ROOT")
    scenario_root = os.environ.get("MANDATE_SCENARIO_ROOT")
    port = os.environ.get("MANDATE_PORT")
    return ApiSettings(
        port=int(port) if port else DEFAULT_PORT,
        save_root=Path(save_root) if save_root else ApiSettings.save_root,
        scenario_root=Path(scenario_root) if scenario_root else ApiSettings.scenario_root,
    )


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the ASGI application.

    Kept as a factory rather than a module-level singleton so tests can build an
    isolated app per test with its own save root, instead of sharing one
    process-global instance across the suite.
    """
    resolved = settings if settings is not None else settings_from_env()
    app = FastAPI(
        title="MANDATE local game API",
        version="0.12.0",
        summary="Local, loopback-only interface to the MANDATE simulation engine.",
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = resolved
    return app


def run() -> None:
    """The `mandate-gui` console entry point. Fleshed out later in Gate 4A1."""
    raise NotImplementedError(
        "mandate-gui is implemented in a later Gate 4A1 commit (startup and SPA serving)"
    )
