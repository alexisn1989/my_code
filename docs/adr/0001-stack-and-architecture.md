# ADR 0001: Stack and architecture for MANDATE

- Status: accepted
- Date: 2026-08-01

## Context

`alexisn1989/my_code` was empty at project start (one commit, a one-line README). The product
brief recommends a specific stack (React/TS/Vite frontend, FastAPI/SQLAlchemy/PostgreSQL backend)
"unless the existing repository already has a sensible, compatible stack." Since nothing existing
constrains the choice, the recommended stack is adopted as-is, with a few concrete tool decisions
the brief left open.

## Decision

- **Backend**: Python 3.11, FastAPI (from Phase 4), Pydantic v2, SQLAlchemy 2.x + Alembic (from
  Phase 4), PostgreSQL in production / SQLite only for isolated unit tests where behavior matches.
  Package/dependency management via **uv** with a `pyproject.toml` (PEP 621) and a committed
  `uv.lock`, rather than Poetry or bare pip+requirements.txt: uv was already on `PATH` in the
  target environment, resolves and installs fast, and produces a standard, pip-compatible layout
  that doesn't lock the project into a specific tool if that changes later. Ruff for lint+format,
  mypy for the simulation package (typed domain logic benefits most from strict checking; API glue
  code can be looser).
- **Frontend**: React + TypeScript + Vite, Tailwind, per the brief. This session scaffolds
  configuration and a minimal shell only — **no `npm install` and no build** — because there is no
  API yet for it to talk to and the session's disk allowance is finite. It becomes a real,
  installed, tested app starting at Phase 5.
- **Monorepo layout**: `backend/`, `frontend/`, `data/`, `docs/`, `scripts/` as siblings, matching
  the brief's proposed tree exactly (see `architecture.md`).
- **Simulation engine isolation**: `backend/app/simulation` (plus its `app/core` dependencies) has
  no import of FastAPI, SQLAlchemy, or any I/O library. It is called by the CLI today and will be
  called by API route handlers/services starting at Phase 4, but never the reverse. This is the
  single most load-bearing structural decision in the codebase: it's what makes "construct a
  GameState, submit decisions, resolve a turn, get a new GameState + TurnReport" testable without a
  server, and it's what the brief's "keep the simulation engine independent from FastAPI"
  requirement (§4) directly asks for.
- **Determinism enforcement is automated, not just documented**: an AST-based test walks every
  module under `app/simulation` and fails the build if it imports `random` outside `core/rng.py` or
  calls wall-clock time APIs. A canonical-JSON serializer (sorted keys, fixed separators, no
  timestamps/UUIDs/unordered sets) is the single path used to compare two independent resolutions
  of the same seed+decisions for byte-identical output.
- **Money**: `Money: TypeAlias = int` (Python 3.11 syntax — the newer `type Money = int` statement
  is 3.12+ and would break on the pinned interpreter). One unit = 1/100 of the fictional currency.
  No floats in financial state.
- **Persistence**, deferred to Phase 4, will mix normalized identity tables with immutable JSON
  snapshots per turn (see `architecture.md`) rather than either fully-normalized rows or a single
  opaque blob — chosen to keep "list my saves" queryable while keeping turn history provably
  immutable.

## Consequences

- Nothing here blocks Phase 4 from introducing FastAPI/SQLAlchemy/Alembic; the simulation package
  is a plain Python library they can import.
- The frontend toolchain is unverified this session (config only). This is called out explicitly in
  the Phase 0 report rather than assumed to work; `npm install && npm run build` is the first
  action of Phase 5 (or earlier, if a future session wants to verify the shell in isolation).
- Postgres is not run this session (no server available in the sandbox at inspection time; Docker
  daemon is reachable, so `docker-compose.yml` can be added and validated with
  `docker compose config --quiet` without starting a container, or deferred entirely to Phase 4).
- Choosing uv over Poetry means contributors need uv installed locally; this trades a small
  onboarding cost for faster CI and local iteration, judged worthwhile since dependency resolution
  speed compounds over many phases of a long-lived project.
