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
  [`docs/adr/0005-production-derived-tax-bases.md`](docs/adr/0005-production-derived-tax-bases.md),
  [`docs/adr/0006-labor-allocation-at-fixed-prices.md`](docs/adr/0006-labor-allocation-at-fixed-prices.md),
  [`docs/adr/0007-resource-endowments-and-extraction.md`](docs/adr/0007-resource-endowments-and-extraction.md),
  [`docs/adr/0008-physical-extraction-derived-sector-output.md`](docs/adr/0008-physical-extraction-derived-sector-output.md),
  [`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`](docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md)
- **Economy formulas:** [`docs/economy_methodology.md`](docs/economy_methodology.md)

## Current status

**Phase 0, Phase 1 (pure simulation foundation), Phase 2A (government accounting and budget
gameplay), Phase 2B1 (sector production at fixed prices), Phase 2B2 (production-derived tax
bases), Phase 2B3 (labor allocation and unemployment at fixed prices), Phase 2C1 (resource
endowments and extraction), Phase 2C2 (physical extraction drives extraction-sector output), and
Phase 3A (constitutional foundation, legitimacy and political capital) are complete and
verified.** The player can change tax rates and spending; eleven aggregate economic sectors
resolve deterministic quarterly output at fixed base-year prices, staffed every turn by a
deterministic labor allocation **derived** from population (replacing the fixed,
scenario-authored `employed_workers` Phase 2B1 started with), which in turn **derives** the tax
bases revenue is computed against (replacing the fixed, scenario-authored bases Phase 2A started
with) — population, capacity, labor productivity, and employment genuinely drive government
revenue. Alongside that economic chain, eight physical natural resources (timber, iron ore, coal,
crude oil, natural gas, uranium, copper, critical minerals) hold finite, country-level,
exactly-conserved reserves; the extraction sector's already-allocated workers sub-allocate across
the eight deposits each turn, bounded by stock, capacity, and labor, with timber the only
renewable resource, regenerating (and clamped to a ceiling) before extraction each turn. As of
Phase 2C2, that physical extraction — converted through a single named unit-bridge, never
double-counted — **is** the extraction sector's output: depleting a reserve now costs real tax
revenue, closing the gap Phase 2C1 deliberately left open. As of Phase 3A, the player also has a
constitutional structure and a legitimacy score: legitimacy drifts toward a scenario-authored
acceptance level and responds to this same economy's output and unemployment — **never** to the
form of government, a compile-time-checked guarantee — and political capital regenerates from
legitimacy. The relationship is one-directional throughout: population/labor supply affects
allocation and production; resource endowments affect extraction, which affects the extraction
sector's production, which (like every sector) affects tax bases and revenue; economic performance
affects legitimacy; tax rates, spending, and politics still do not affect allocation, production,
or extraction, and politics cannot yet affect the economy at all. Revenue, spending, interest, and
debt resolve deterministically and reconcile exactly every turn, with a self-validating report
chain proving labor allocation, resource extraction, production, tax-base derivation, finance, and
politics agree with each other, not just internally. All of it is wrapped in the same hash-chained,
immutable history from Phase 1. There is no API and no database yet, no parties, legislature,
elections, or coups, and no prices, inflation, wages, hiring friction, resource trade, or
resource-to-industry linkage for the other ten sectors — see `docs/roadmap.md` for what's
implemented per phase and `docs/economy_methodology.md` for exactly what's simulated and what
isn't.

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
  It also shows the player's legitimacy and political capital by default; `--politics` adds the
  full constitutional axis table and the persisted economic-baseline record.
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

### Government accounting (Phase 2A, tax bases production-derived since Phase 2B2)

The player can change tax rates (personal income, corporate, consumption) and spending across
seven categories. Each turn: tax revenue is collected against tax bases derived from that turn's
sector production (see below — not fixed, scenario-authored numbers as in the original Phase 2A),
spending and quarterly debt interest are deducted, a deficit consumes cash before any new
borrowing, and the result is checked against two reconciliation equations that must hold exactly
in integer minor units. `FinanceReport` re-derives and checks those equations independently every
time it's constructed — including when read back out of history — so a report can never claim to
reconcile when the numbers don't actually add up.

### Sector production (Phase 2B1, employment derived since Phase 2B3)

Eleven aggregate sectors (agriculture, extraction, manufacturing, construction, energy,
transportation, consumer services, finance and professional services, technology, defense
industry, public services) each have a quarterly production capacity and output-per-worker
productivity. Every turn, each sector's labor-limited output (`allocated_workers *
output_per_worker`, using this same turn's labor allocation — see below, not a scenario-authored
employment count) is capped at capacity, classified
(capacity-constrained/labor-constrained/exactly-balanced/inactive), and reported at a fixed
base-year price — deliberately **not** GDP, value added, or an inflation-adjusted figure.
`ProductionReport` self-validates the same way `FinanceReport` does.

### Labor allocation and unemployment (Phase 2B3)

Sector employment is no longer scenario-authored. Each turn: an effective labor force is derived
from population and a reduced-form labor-force-share coefficient; each sector's labor demand is
the ceiling-division worker count needed to run at full capacity; a deterministic
largest-remainder allocation (with explicit canonical tie-breaking) distributes the labor force
across sectors, capped at each sector's own demand. The relationship is one-directional:
population/labor supply determines allocation and therefore production; tax rates and spending
still cannot affect allocation. `LaborMarketReport` self-validates the same way the other reports
do, and `TurnReport` cross-validates that labor allocation matches what production actually used,
per sector.

### Production-derived tax bases (Phase 2B2)

Each sector also has a value-added share and a labor-income share; the government has three
fiscal-reach coefficients (personal/corporate/consumption). Every turn, sector output is decomposed
into a `modeled_value_added` proxy (explicitly not national-accounts value added), split into
labor income and operating surplus, and converted into the three tax bases `FinanceReport` uses —
through exactly one named, explicit real-output-to-money conversion function. The relationship is
one-directional: production determines tax bases and revenue; tax rates and spending still cannot
affect production. `TurnReport` cross-validates that labor allocation, production, tax-base
derivation, and finance all agree with each other (matched by sector category, not just internally
self-consistent) — a partial or inconsistent combination is rejected outright. Full formulas, the
unit-bridge design, and what's explicitly not yet simulated (prices, inflation, wages, hiring
friction, tax-rate elasticity, …): [`docs/economy_methodology.md`](docs/economy_methodology.md).

### Resource endowments and extraction (Phase 2C1)

Each country holds finite, country-level reserves of eight physical resources (timber, iron ore,
coal, crude oil, natural gas, uranium, copper, critical minerals) — a distinct physical-quantity
type family from `Money`/`RealOutput`, with no conversion between them, so "resources feed nothing
else yet" is structurally true, not just documented. Timber is the only renewable resource:
each turn it regenerates by a fixed amount, clamped to a stock ceiling, before extraction is
computed. Every turn, the extraction sector's already-allocated workers (from labor allocation,
above) are sub-allocated across the eight deposits by the same deterministic largest-remainder
algorithm labor allocation uses, and each deposit's extraction is capped at
`min(available_stock, extraction_capacity_per_turn, allocated_workers * output_per_worker)` —
exact conservation by construction, with a five-way status classification
(inactive/depleted/stock-constrained/capacity-constrained/labor-constrained) explaining which
bound applied. `ResourceExtractionReport` self-validates the same way the other reports do, and
`TurnReport` cross-validates that labor allocation's extraction-sector worker count matches the
resource report's budget exactly. Originally (Phase 2C1) this relationship was conservation-only —
extraction changed no production, tax base, or revenue; **Phase 2C2 (below) deliberately reverses
that boundary.** Full formulas, the three-regime timber trajectory worked out against the
`deficit_demo` scenario, and what's explicitly not yet simulated (prices, trade,
resource-to-industry input-output chains, ownership, environmental effects, …):
[`docs/economy_methodology.md`](docs/economy_methodology.md) and
[`docs/adr/0007-resource-endowments-and-extraction.md`](docs/adr/0007-resource-endowments-and-extraction.md).

### Physical extraction drives extraction-sector output (Phase 2C2)

The extraction sector no longer computes its `RealOutput` the same way the other ten sectors do.
Each turn, every deposit's extracted quantity — and, separately, its stock/capacity-bounded
*potential* quantity — is converted through a single named bridge function
(`extracted_resource_to_real_output`, exact integer multiplication, no rounding) using a
scenario-authored, strictly-positive coefficient per resource category
(`EconomyState.resource_output_coefficients`). The summed actual and potential totals become the
extraction row's `actual_output` and the basis for its `capacity_utilization_bps`/`constraint` —
never the legacy `quarterly_capacity_output`/`output_per_worker` fields every other sector still
uses, which are now completely inert for this one row. Because `extracted <= potential` holds by
construction (the same `min()`-bounded formula extraction already used), the utilization ratio
never needs clamping and `actual_output > potential_output` is rejected by validation at three
independent layers rather than ever being assigned a business status. The extraction sector's
contribution now flows through `total_gross_output` exactly once, into tax bases and revenue,
exactly like every other sector — depleting a reserve costs real revenue. Both scenarios are
recalibrated so `tiny_valid.yaml` preserves its full 100-turn output exactly and `deficit_demo.yaml`
preserves turn 1 before diverging at the same turn-26/turn-41 boundaries its physical trajectory
already established. Full formulas and the R1–R10 review corrections:
[`docs/economy_methodology.md`](docs/economy_methodology.md) and
[`docs/adr/0008-physical-extraction-derived-sector-output.md`](docs/adr/0008-physical-extraction-derived-sector-output.md).

### Constitutional foundation, legitimacy and political capital (Phase 3A)

Each country now has a nine-axis `ConstitutionState` (executive system, executive selection,
legislature, territorial organization, judicial review, amendment difficulty, decree authority,
plus optional term-limit/election-interval scalars) checked against nine validity rules — which
reject internally *incoherent* arrangements (a hereditary presidency, a parliament with no
legislature) but say nothing about whether a valid arrangement is accepted, good, or stable. That
is the job of `constitutional_order_support_bps`, a scenario-authored acceptance level, and
`legitimacy_bps`, which drifts toward it every turn and additionally responds to this same
economy's output and unemployment — a resource-depletion shock that shrinks production now costs
the government real legitimacy, through the same extraction→production chain Phase 2C2 built, with
no new economic engineering. **Government form cannot influence legitimacy**: `simulation/
legitimacy.py`'s public functions accept no constitutional type in their signatures at all, a
`mypy`-checked guarantee, not merely a tested convention — proven by a dedicated test matrix
showing five differently-formed governments at matched authored-support levels produce identical
legitimacy trajectories turn by turn, while their constitutions and hashes genuinely differ.
Political capital regenerates each turn from legitimacy alone (200 at zero legitimacy, up to 500 at
full legitimacy); nothing spends it yet — that starts in Phase 3B. A new reconciliation step
(`simulation/reconciliation.py`) checks the political report against both the turn's opening and
closing state across eleven groups, and history replay re-runs it on every entry, so even a
tamperer who edits a value *and* recomputes the hash to match is still caught. Full formulas:
[`docs/economy_methodology.md`](docs/economy_methodology.md) and
[`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md`](docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md).

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
