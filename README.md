# MANDATE

A turn-based political survival and nation-management strategy game. The player governs a
fictional country — economy, political system, population groups, institutions, diplomacy, trade,
and war — and the central challenge is remaining in power while living with the consequences of
every decision.

- **Design and product spec:** [`docs/product_spec.md`](docs/product_spec.md)
- **Architecture:** [`docs/architecture.md`](docs/architecture.md)
- **Roadmap and phase status:** [`docs/roadmap.md`](docs/roadmap.md)
- **Stack rationale:** [`docs/adr/0001-stack-and-architecture.md`](docs/adr/0001-stack-and-architecture.md)

## Current status

**Phase 0 (project foundation) and the minimal slice of Phase 1 (pure simulation foundation) are
implemented and verified.** There is a deterministic, testable turn-resolution engine reachable
from a headless CLI. There is no API, no database, and no working frontend yet — see
`docs/roadmap.md` for what's implemented per phase.

## Repository layout

```
backend/    Python simulation engine, CLI, (Phase 4+) FastAPI app
frontend/   React/TypeScript/Vite app — config scaffold only, not yet installed or built
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
uv run mypy app/core app/simulation   # strict type-check of the deterministic engine
uv run pytest -v                 # full test suite
```

### Headless CLI

The simulation engine works without a server or database:

```bash
uv run python -m app.cli new --scenario ../data/scenarios/tiny_valid.yaml --out save.json
uv run python -m app.cli inspect --state save.json
uv run python -m app.cli resolve --state save.json --turns 8 --out save.turn8.json
```

`new` creates a game from a scenario file. `inspect` loads and validates a state file without
mutating it. `resolve` resolves N turns and writes the result to a new file — it refuses to
overwrite its input.

## Frontend

`frontend/` currently contains configuration and a minimal shell page only (React + TypeScript +
Vite + Tailwind v4 + Vitest). **`npm install` has not been run or verified in this repository** —
that, and real gameplay screens, start at Phase 5 once there is a backend API to talk to.

```bash
cd frontend
npm install
npm run build
npm run test
```

## Local Postgres (Phase 4+)

`docker-compose.yml` defines a Postgres service for the persistence layer introduced in Phase 4.
Nothing in the backend uses a database yet; the compose file is validated
(`docker compose config --quiet`) but not started as part of this phase.

## Contributing / working method

See `docs/product_spec.md` §39 for how phased development proceeds: small, coherent changes;
tests added with every behavior change; database migrations for schema changes; no claims of
"working" without the commands above having actually been run.
