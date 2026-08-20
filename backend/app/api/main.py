"""Application factory, settings, and the `mandate-gui` entry point.

Builds the ASGI app (routing, security middleware, exception handlers, and the
Gate 4A0 greybox static mount), and the `mandate-gui` console command that
serves it.

**One process, one worker, always.** The authoritative game session is process
memory (`app.api.session`), so two Uvicorn workers would own two different
`GameSession` objects, two different mutation boundaries, and two different
ideas of the current save -- silently invalidating every concurrency guarantee
`session.py` establishes. Multi-worker deployment is therefore unsupported and
prohibited: `run_server` hard-codes `workers=1` and no flag exists to change it.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .routes import router
from .save_registry import SaveRepository
from .security import LocalSecurityMiddleware
from .session import GameSession

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
    #: One EXPLICITLY configured development origin, e.g. a separately-running
    #: Vite dev server. Never inferred, never a pattern -- see `--dev-origin`.
    dev_origin: str | None = None

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Exactly the two loopback spellings at the configured port.

        Derived from `port` rather than hand-maintained, so a `--port` override
        cannot leave the old port authorised.
        """
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    @property
    def allowed_origins(self) -> frozenset[str]:
        origins = {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}
        if self.dev_origin is not None:
            origins.add(self.dev_origin)
        return frozenset(origins)


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
    # The ONE authoritative session for this process. Built per app instance so
    # tests get an isolated save root rather than sharing a process global.
    app.state.session = GameSession(SaveRepository(resolved.save_root))
    register_exception_handlers(app)
    # Installed on every app, no opt-out: this is a local desktop application,
    # not a service with an internal trusted network to exempt.
    app.add_middleware(
        LocalSecurityMiddleware,
        allowed_hosts=resolved.allowed_hosts,
        allowed_origins=resolved.allowed_origins,
    )
    app.include_router(router, prefix="/api")
    if resolved.serve_spa:
        _mount_spa(app, resolved)
    return app


def _mount_spa(app: FastAPI, settings: ApiSettings) -> None:
    """Serve the Gate 4A0 greybox build. Not API-wired -- that is Gate 4A2.

    `/api/*` is registered above and is therefore matched first; this only ever
    serves what `/api/*` did not claim. A missing build fails loudly at server
    start (`require_frontend_build`), never here with a 404 the operator has to
    puzzle out.
    """
    require_frontend_build(settings.frontend_dist)
    assets_dir = settings.frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_path = settings.frontend_dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str) -> FileResponse:
        candidate = (settings.frontend_dist / full_path).resolve()
        dist_root = settings.frontend_dist.resolve()
        if (
            full_path
            and candidate.is_relative_to(dist_root)
            and candidate.is_file()
            and not candidate.is_symlink()
        ):
            return FileResponse(candidate)
        return FileResponse(index_path)


class PortInUseError(RuntimeError):
    """A clear, catchable failure -- never a raw traceback at startup."""


class FrontendBuildMissingError(RuntimeError):
    """`frontend/dist/index.html` is absent. Names the exact fix."""


def require_frontend_build(frontend_dist: Path) -> None:
    if not (frontend_dist / "index.html").is_file():
        raise FrontendBuildMissingError(
            f"frontend/dist/index.html not found at {frontend_dist}. "
            "Build it first: cd frontend && npm ci && npm run build"
        )


def probe_port_available(host: str, port: int) -> None:
    """Bind-and-release, so a collision is reported clearly before uvicorn starts.

    A best-effort check, not a guarantee -- another process could bind between
    this call and uvicorn's own bind. It exists to turn the COMMON case (a
    previous `mandate-gui` still running) into a clear message instead of a
    traceback from deep inside uvicorn's startup.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        probe.bind((host, port))
    except OSError as error:
        raise PortInUseError(
            f"port {port} is already in use on {host}. "
            f"Stop the other process, or start with --port <a different port>."
        ) from error
    finally:
        probe.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mandate-gui")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--save-root", type=Path, default=None)
    parser.add_argument("--scenario-root", type=Path, default=None)
    parser.add_argument("--frontend-dist", type=Path, default=None)
    parser.add_argument(
        "--dev-origin",
        default=None,
        help=(
            "An additional allowed Origin for local development, e.g. "
            "http://localhost:5173 for a separately-running Vite dev server. "
            "Never inferred; must be passed explicitly."
        ),
    )
    return parser


def _settings_from_args(argv: list[str] | None) -> ApiSettings:
    args = build_argument_parser().parse_args(argv)
    base = settings_from_env()
    resolved = replace(base, port=args.port)
    if args.save_root is not None:
        resolved = replace(resolved, save_root=args.save_root)
    if args.scenario_root is not None:
        resolved = replace(resolved, scenario_root=args.scenario_root)
    if args.frontend_dist is not None:
        resolved = replace(resolved, frontend_dist=args.frontend_dist)
    if args.dev_origin is not None:
        resolved = replace(resolved, dev_origin=args.dev_origin)
    return resolved


def run(argv: list[str] | None = None) -> None:
    """The `mandate-gui` console entry point.

    Exactly one process, one Uvicorn worker, bound to loopback: `run_server`
    below hard-codes `workers=1` and never accepts a flag to change it, because
    the single process-wide `GameSession` (one save, one mutation boundary)
    is only correct under exactly that topology -- a second worker would be a
    second, divergent session.
    """
    settings = _settings_from_args(argv)
    try:
        require_frontend_build(settings.frontend_dist)
        probe_port_available(settings.bind_host, settings.port)
    except (FrontendBuildMissingError, PortInUseError) as error:
        print(f"mandate-gui: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    run_server(settings)


def run_server(settings: ApiSettings) -> None:
    """Actually start Uvicorn. Split from `run()` so tests can stub this call
    and inspect exactly what configuration would have been used."""
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.bind_host,
        port=settings.port,
        workers=1,
        log_level="info",
    )
