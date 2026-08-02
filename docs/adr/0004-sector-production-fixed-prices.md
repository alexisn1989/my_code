# ADR 0004: Sector production at fixed prices and the Phase 2B1 ruleset bump

- Status: accepted
- Date: 2026-08-02

## Context

Phase 2A gave government accounting resolving against fixed, scenario-authored tax bases — nothing
produced anything real underneath the budget numbers. Phase 2B1 introduces the production layer
later phases will use to derive tax bases from real economic activity: aggregate sectors with
capacity, labor productivity, and employment, producing deterministic quarterly output at fixed
base-year prices. Full formulas live in `docs/economy_methodology.md`; this ADR covers the design
decisions and their tradeoffs.

## Decisions

### A new `StrictQuantity`-family type, not a reuse of `StrictMoney`

`app/core/quantity.py` defines `StrictWorkerCount` and `StrictRealOutput`/`StrictRealOutputPerWorker`
as distinct aliases, not one generic "quantity" type reused across both. `StrictMoney`'s underlying
`strict=True, ge=0` int constraint is structurally identical to what a worker count or an output
figure needs, but currency, worker headcount, and real (constant-price) output are three different
semantic domains that will keep diverging — money gets bps-based tax/interest operations; output
gets labor/productivity operations; a worker count is neither. Reusing `StrictMoney` for
`quarterly_capacity_output` would let a `SectorState` field silently read as spendable currency in a
future diff. This follows the codebase's existing convention of one alias per domain
(`StrictMoney`, `StrictBps`), not a shared one.

### `output_per_worker` is strictly positive; `employed_workers` is the only "idle" signal

`output_per_worker: StrictRealOutputPerWorker` uses `gt=0`, not `ge=0`. Without this, a scenario
author has two independent ways to express "this sector currently produces nothing"
(`employed_workers == 0` or `output_per_worker == 0`), which complicates future hiring/layoff
mechanics that presumably want to vary `employed_workers` against a fixed productivity figure.
Keeping `output_per_worker` strictly positive leaves `employed_workers == 0` as the sole
representation of an idle-but-staffable sector.

### Constraint classification: capacity checked first, floor-division utilization

```
if quarterly_capacity_output == 0:                        INACTIVE
elif labor_limited_output <  quarterly_capacity_output:    LABOR_CONSTRAINED
elif labor_limited_output >  quarterly_capacity_output:    CAPACITY_CONSTRAINED
else:                                                      EXACTLY_BALANCED
```

Capacity is checked before any labor comparison specifically to resolve
`quarterly_capacity_output == 0 and employed_workers == 0` as `INACTIVE` rather than the trivial
`0 == 0` reading of "exactly balanced." The converse edge case —
`quarterly_capacity_output > 0 and employed_workers == 0` — is `LABOR_CONSTRAINED`, not `INACTIVE`:
capacity exists and is simply unstaffed, a materially different fact from "no capacity at all,"
even though both cases produce zero output and zero utilization. `capacity_utilization_bps` floors
(`actual_output * 10_000 // quarterly_capacity_output`) rather than rounds, consistent with
`core.money.apply_bps`'s existing convention, and guarantees the bps value can only equal 10,000
when output has genuinely reached capacity exactly.

### `EconomyState`'s completeness/ordering invariant is enforced twice

`SectorState` is deliberately **not** frozen — a later economy phase is expected to make
`employed_workers` adjustable, so freezing it now to simplify this phase's validation story would
have to be undone almost immediately. Because it's mutable, `EconomyState`'s own
`@model_validator(mode="after")` (which checks "all 11 categories, exactly once" and normalizes
sector order) only runs at construction time: a later `sector.category = ...` assignment mutates a
*child* object's own field and does not re-trigger the *parent* `EconomyState`'s validator, so an
already-built `EconomyState` can desynchronize from its own invariant without ever raising.
`simulation.invariants` re-checks the identical rule independently, every turn (pre- and
post-resolution, like every other invariant) — this is the actual backstop, not the constructor
check alone. A dedicated regression test (`tests/test_invariants.py`) constructs a valid economy,
mutates a nested sector's category into a duplicate via plain attribute assignment, and confirms
both `check_invariants` reports it and `resolve_turn`/`advance_game` reject it without mutating
input state or appending history.

**A subtlety this surfaced**: a plain reassignment of the *whole* `sectors` tuple (as opposed to a
nested field) *does* re-trigger `EconomyState`'s validator, because Pydantic's
`validate_assignment=True` reruns "after" validators even when the assigned value is an
already-constructed instance — so it silently re-normalizes order back to canonical rather than
preserving a noncanonical order. Testing the noncanonical-order invariant case honestly required a
genuinely bypassed construction (`model_construct`/`model_copy(update=...)`), not a live attribute
assignment, since no live assignment path can actually produce that state.

### `ProductionReport` is self-validating and player-country-only, mirroring `FinanceReport`

`SectorProductionReport`/`ProductionReport` (`app.simulation.report`) use the identical
self-validation pattern established for `FinanceReport` in Phase 2A: every derived field
(`labor_limited_output`, `actual_output`, `capacity_utilization_bps`, `constraint`,
`total_employment`, `total_gross_output`) is independently re-derived from the report's own stored
inputs on every construction path, with no trusted boolean. `ProductionReport.sectors` is
normalized to canonical `SectorCategory` order by the same validator that checks
completeness/uniqueness, so two logically-identical reports authored in different sector order
serialize to byte-identical canonical JSON and `entry_hash` — the same reasoning that already
motivates canonical-JSON storage in `simulation.history`.

`ProductionReport` is scoped to the player country only, exactly matching `FinanceReport`. AI
countries may have `economy=None` and receive no production report; computing sector output for AI
countries too was considered and rejected as expanding this phase's scope and testing surface ahead
of any system that would consume it.

### No `ProductionScratch` workspace

Phase 2A's `FinanceScratch` exists because government accounting genuinely spans multiple phases:
an opening snapshot is captured before mutation, a middle phase computes revenue/spending/interest,
a later phase applies the result to treasury. Production in Phase 2B1 has none of that shape — it
reads only the current turn's `state...economy` and writes directly to
`ctx.production_report` inside the single existing `resolve_production_and_trade` phase slot, never
touching treasury. Adding scratch machinery now would be speculative ahead of the trade
functionality that phase name implies but this phase does not implement.

### Full isolation from Phase 2A accounting, in both directions, actively tested

`resolve_production_and_trade` runs *before* the finance phases in the fixed `PHASE_ORDER`
(unchanged — no reordering), so `ctx.production_report` is already populated by the time the finance
phases execute. Nothing in the type system prevents a finance phase from reading it, or a future
production change from reading `ctx.finance`/treasury — this is a real risk, not a hypothetical one,
given how easy it would be for a later contributor to wire something like "higher output → higher
tax revenue" prematurely. `tests/test_phase_isolation.py` actively tests the isolation rather than
relying on code review: a `FinanceReport` produced against several wildly different `EconomyState`
fixtures is byte-identical, and a `ProductionReport` is byte-identical across different
finance/budget states.

### `RULESET_VERSION` bumps again; a pre-bump save fixture was frozen first

`CountryState.economy` becomes a new **required** field for the player country (enforced by a new
`player_economy_required` invariant, structurally parallel to `player_finance_required`). A
Phase-2A-era save has no sector data and none is invented or backfilled — the same "nothing to
migrate from" reasoning that justified the Phase 1 → 2A bump applies again, independent of whether
production logic itself affects Phase 2A's math (it doesn't). `RULESET_VERSION` moves
`"0.2.0" -> "0.3.0"`; `content_version` bumps alongside it since scenario YAML must now supply an
`economy:` block; `SAVE_FORMAT_VERSION` is unchanged since the envelope shape itself didn't change.

**Consequence for testing**: once bumped, no code path can produce a genuine Phase-2A-ruleset save
anymore. `backend/tests/fixtures/phase2a_save_ruleset_0.2.0.json` was generated with unmodified
Phase-2A code and committed *before* this bump landed, mirroring exactly how the Phase-1 fixture was
frozen before the 2A bump — the only way to produce one.

### Terminology: gross sector output, not GDP

Sector output is documented and coded as "gross sector output at fixed base-year prices,"
"production capacity," and "capacity utilization" — never GDP, value added, real GDP, inflation, or
economic growth. No value-added accounting exists yet, so `total_gross_output` (a plain sum across
sectors) can include intermediate production counted more than once, which is precisely what "GDP"
implies it doesn't. This is stated in `docs/economy_methodology.md`, in `ProductionReport`'s own
field documentation, and enforced by not introducing any of those terms anywhere in Phase 2B1 code.

## Consequences

- Every backend test that constructs a player country via `tests/conftest.make_country` now gets an
  `EconomyState` by default (`with_economy=True`), alongside the existing `with_finance=True`
  default — the same pattern Phase 2A established, so the new invariant doesn't silently break
  unrelated coverage. `tests/conftest.make_economy` provides a uniform, unremarkable default economy
  (every sector labor-constrained); tests wanting a specific classification or edge case build
  `SectorState`/`EconomyState` directly.
- Both scenario fixtures (`tiny_valid.yaml`, `deficit_demo.yaml`) now carry a required `economy:`
  block. `tiny_valid.yaml`'s is deliberately hand-checked to cover all four constraint
  classifications, so the 100-turn soak exercises every code path rather than one uniform case.
- CLI `inspect`/`history` gained a production summary and per-sector breakdown
  (`_print_production_report`, mirroring `_print_finance_report`); two new `reason_id`s
  (`production_summary`, `sector_inactive`) were added to the renderer table and its coverage test.
