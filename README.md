# MANDATE

A turn-based political survival and nation-management strategy game. The player governs a
fictional country — economy, political system, population groups, institutions, diplomacy, trade,
and war — and the central challenge is remaining in power while living with the consequences of
every decision.

- **Design and product spec:** [`docs/product_spec.md`](docs/product_spec.md)
- **Architecture:** [`docs/architecture.md`](docs/architecture.md)
- **Roadmap and phase status:** [`docs/roadmap.md`](docs/roadmap.md)
- **ADRs:** [`docs/adr/0001-stack-and-architecture.md`](docs/adr/0001-stack-and-architecture.md),
  [`docs/adr/0002-snapshot-history-and-versioning.md`](docs/adr/0002-snapshot-history-and-versioning.md),
  [`docs/adr/0003-government-accounting.md`](docs/adr/0003-government-accounting.md),
  [`docs/adr/0004-sector-production-fixed-prices.md`](docs/adr/0004-sector-production-fixed-prices.md),
  [`docs/adr/0005-production-derived-tax-bases.md`](docs/adr/0005-production-derived-tax-bases.md)
- **Economy formulas:** [`docs/economy_methodology.md`](docs/economy_methodology.md)

## Current status

**Phase 0, Phase 1 (pure simulation foundation), Phase 2A (government accounting and budget
gameplay), Phase 2B1 (sector production at fixed prices), and Phase 2B2 (production-derived tax
bases) are complete and verified.** The player can change tax rates and spending; eleven aggregate
economic sectors resolve deterministic quarterly output at fixed base-year prices, which now
**derives** the tax bases revenue is computed against (replacing the fixed, scenario-authored bases
Phase 2A started with) — capacity, labor productivity, and employment genuinely drive government
revenue. The relationship is one-directional: production affects tax bases and revenue; tax rates
and spending still do not affect production. Revenue, spending, interest, and debt resolve
deterministically and reconcile exactly every turn, with a self-validating report chain proving
production, tax-base derivation, and finance agree with each other, not just internally. All of it
is wrapped in the same hash-chained, immutable history from Phase 1. There is no API and no
database yet, and no prices, inflation, wages, or population effects — see `docs/roadmap.md` for
what's implemented per phase and `docs/economy_methodology.md` for exactly what's simulated and
what isn't.

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

# Submit a budget decision (raise the personal-income tax rate to 25%):
echo '{"expected_turn": 0, "expected_state_version": 0,
       "decisions": [{"personal_income_rate_bps": 2500}]}' > budget.json
uv run python -m app.cli resolve --state save.json --turns 1 \
    --decisions-file budget.json --out save1.json
```

- `new` creates a save containing only the genesis (turn-0) entry.
- `inspect` loads a save and reports its version envelope, current turn, entry count, and
  integrity status — even an invalid save can be inspected; that's the point of "integrity status."
- `resolve` appends N turns to history and writes the result atomically; it refuses to overwrite
  its input, and on any failure nothing is written and the input is untouched. `--decisions-file`
  applies a JSON `DecisionSet` (requires `--turns 1`) instead of the default "no decision, continue
  the current budget."
- `history` lists every turn, or with `--turn N` shows one historical entry — including the
  financial report, rendered as English via `app.cli.REASON_RENDERERS` — without mutating anything.
  Unlike `inspect`, it refuses to operate on a save that fails integrity validation.

Save files are hash-chained (see the history ADR below) — every entry records not just the
resulting state but the decisions submitted and the report produced, linked to the previous entry
by a BLAKE2b-256 hash. This detects accidental corruption and hand-editing; it is explicitly **not**
anti-cheat security (the hashes are unkeyed).

### Government accounting (Phase 2A, tax bases now production-derived as of Phase 2B2)

The player can change tax rates (personal income, corporate, consumption) and spending across
seven categories. Each turn: tax revenue is collected against tax bases derived from that turn's
sector production (see below — not fixed, scenario-authored numbers as in the original Phase 2A),
spending and quarterly debt interest are deducted, a deficit consumes cash before any new
borrowing, and the result is checked against two reconciliation equations that must hold exactly
in integer minor units. `FinanceReport` re-derives and checks those equations independently every
time it's constructed — including when read back out of history — so a report can never claim to
reconcile when the numbers don't actually add up.

### Sector production (Phase 2B1)

Eleven aggregate sectors (agriculture, extraction, manufacturing, construction, energy,
transportation, consumer services, finance and professional services, technology, defense
industry, public services) each have a quarterly production capacity, output-per-worker
productivity, and an employed-worker count. Every turn, each sector's labor-limited output
(`employed_workers * output_per_worker`) is capped at capacity, classified
(capacity-constrained/labor-constrained/exactly-balanced/inactive), and reported at a fixed
base-year price — deliberately **not** GDP, value added, or an inflation-adjusted figure.
`ProductionReport` self-validates the same way `FinanceReport` does.

### Production-derived tax bases (Phase 2B2)

Each sector also has a value-added share and a labor-income share; the government has three
fiscal-reach coefficients (personal/corporate/consumption). Every turn, sector output is decomposed
into a `modeled_value_added` proxy (explicitly not national-accounts value added), split into
labor income and operating surplus, and converted into the three tax bases `FinanceReport` uses —
through exactly one named, explicit real-output-to-money conversion function. The relationship is
one-directional: production determines tax bases and revenue; tax rates and spending still cannot
affect production. `TurnReport` cross-validates that production, tax-base derivation, and finance
all agree with each other (matched by sector category, not just internally self-consistent) — a
partial or inconsistent combination is rejected outright. Full formulas, the unit-bridge design,
and what's explicitly not yet simulated (prices, inflation, employment dynamics, wages, tax-rate
elasticity, …): [`docs/economy_methodology.md`](docs/economy_methodology.md).

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
