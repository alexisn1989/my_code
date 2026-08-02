# MANDATE

A turn-based political survival and nation-management strategy game. The player governs a
fictional country — economy, political system, population groups, institutions, diplomacy, trade,
and war — and the central challenge is remaining in power while living with the consequences of
every decision.

- **Design and product spec:** [`docs/product_spec.md`](docs/product_spec.md)
- **Architecture:** [`docs/architecture.md`](docs/architecture.md)
- **Roadmap and phase status:** [`docs/roadmap.md`](docs/roadmap.md)
- **ADRs:** [`docs/adr/0001-stack-and-architecture.md`](docs/adr/0001-stack-and-architecture.md),
  [`docs/adr/0002-snapshot-history-and-versioning.md`](docs/adr/0002-snapshot-history-and-versioning.md)

## Current status

**Phase 0 (project foundation) and Phase 1 (pure simulation foundation) are complete and
verified.** There is a deterministic, hash-chained, immutable game-history engine reachable from a
headless CLI, and a verified (installed, type-checked, built, tested) but otherwise empty frontend
shell. There is no API and no database yet — see `docs/roadmap.md` for what's implemented per
phase.

## Repository layout

```
backend/    Python simulation engine, history/save layer, CLI, (Phase 4+) FastAPI app
frontend/   React/TypeScript/Vite app — verified shell, no gameplay screens yet
data/       Data-driven content: scenarios (YAML), later events/map
docs/       Product spec, architecture, roadmap, ADRs
```

## Backend: setup and verification

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.11.

```bash
cd backend
uv sync --group dev              # installs pinned, locked dependencies
uv run ruff format --check .     # formatting
uv run ruff check .              # lint
uv run mypy                      # strict type-check (app/core, app/simulation, app/content, app/saves)
uv run pytest -v                 # full test suite
```

### Headless CLI

The simulation and history engine work without a server or database:

```bash
uv run python -m app.cli new --scenario ../data/scenarios/tiny_valid.yaml --out save.json
uv run python -m app.cli inspect --state save.json
uv run python -m app.cli resolve --state save.json --turns 8 --out save.turn8.json
uv run python -m app.cli history --state save.turn8.json
uv run python -m app.cli history --state save.turn8.json --turn 3
```

- `new` creates a save containing only the genesis (turn-0) entry.
- `inspect` loads a save and reports its version envelope, current turn, entry count, and
  integrity status — even an invalid save can be inspected; that's the point of "integrity status."
- `resolve` appends N turns to history and writes the result atomically; it refuses to overwrite
  its input, and on any failure nothing is written and the input is untouched.
- `history` lists every turn, or with `--turn N` shows one historical entry, without mutating
  anything. Unlike `inspect`, it refuses to operate on a save that fails integrity validation.

Save files are hash-chained (see the history ADR below) — every entry records not just the
resulting state but the decisions submitted and the report produced, linked to the previous entry
by a BLAKE2b-256 hash. This detects accidental corruption and hand-editing; it is explicitly **not**
anti-cheat security (the hashes are unkeyed).

## Frontend

`frontend/` is a verified but intentionally empty shell (React 19 + TypeScript + Vite + Tailwind v4
+ Vitest) — one placeholder page, one render smoke test. Real gameplay screens start at Phase 5
once there is a backend API to talk to.

```bash
cd frontend
npm ci               # installs exactly what's locked in package-lock.json
npm run typecheck
npm run build
npm test              # noninteractive (vitest run)
```

## Local Postgres (Phase 4+)

`docker-compose.yml` defines a Postgres service for the relational identity tables (games,
countries, leaders, …) introduced in Phase 4. Nothing in the backend uses a database yet — the
immutable history/save layer is file-based (see the ADR) and works standalone. The compose file is
validated (`docker compose config --quiet`) but not started as part of this phase.

## Contributing / working method

See `docs/product_spec.md` §39 for how phased development proceeds: small, coherent changes;
tests added with every behavior change; database migrations for schema changes; no claims of
"working" without the commands above having actually been run.
