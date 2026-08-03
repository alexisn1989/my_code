# ADR 0006: Labor allocation and unemployment at fixed prices

- Status: accepted
- Date: 2026-08-03

## Context

Phase 2B2 connected sector production to government revenue, but one input in that chain was
still scenario-authored, not derived: `SectorState.employed_workers`. A scenario author picked a
worker count per sector by hand, and nothing tied it to the country's population. Phase 2B3
replaces that authored number with the smallest deterministic labor foundation that still
produces genuine employment and unemployment:

```
population -> effective labor force -> sector labor demand -> deterministic allocation
    -> employment and unemployment -> existing production -> existing tax-base and finance chain
```

Fixed prices throughout, exactly as every prior economy phase. No wages, hiring friction, tax
behavioral responses, or population approval — allocation is instantaneous each turn, deliberately
the smallest foundation; hiring friction becomes meaningful only once wages, policy effects, or
shocks can move labor demand, none of which exist yet.

This ADR also records two corrections (R1–R2) made during an independent review of the initial
design, before implementation — both real gaps the review caught, not stylistic preferences.

## Decisions

### `SectorState.employed_workers` is removed; employment becomes purely derived

Exactly the Phase 2B2 `GovernmentFinanceState.tax_bases` precedent: a value that is always
recomputed from other state should not also be stored, or it can drift from its own derivation.
Employment now exists only as a turn-local value on `LaborMarketReport`/`ProductionReport`,
never written back into `GameState`. The alternative — keep `employed_workers` in state, updated
each turn — was rejected for the same reason Phase 2B2 rejected keeping `tax_bases`: it creates a
redundant, driftable authored value with no "opening vs. closing" meaning to define.

### Labor supply is a reduced-form, country-level coefficient

`EconomyState.effective_labor_force_share_bps` (a new `StrictBps` field) temporarily combines
working-age share, labor-force participation, and any other structural availability limitation
into one number — the same kind of deliberate placeholder
`TaxBaseCoefficients.effective_consumption_base_share_bps` already is (ADR 0005 R4):

```
effective_labor_force = floor(population * effective_labor_force_share_bps / 10_000)
```

`population` is `CountryState.population` — the single authoritative population value;
`population_groups` merely partitions it and is not used here. Since `0 <= share_bps <= 10_000`
(`StrictBps`) and `population >= 0`, floor division gives `0 <= effective_labor_force <=
population` by construction, not by a runtime clamp. The coefficient lives on `EconomyState`
(grouped with the sectors it feeds) rather than on `CountryState` directly, so `population` stays
the one authoritative headcount and this field only ever says what *share* of it is economically
active.

### Sector labor demand is a full-capacity staffing requirement, not observed demand

```
required_workers = 0                                            if quarterly_capacity_output == 0
                 = ceil(quarterly_capacity_output / output_per_worker)  otherwise
```

Integer ceiling division only (`(capacity + opw - 1) // opw`), no floats — `output_per_worker` is
already strictly positive (`StrictRealOutputPerWorker`, Phase 2B1), so no division-by-zero path
exists. This is explicitly *not* observed vacancies, wage-based labor demand, or
profit-maximizing employment — those all require a wage/price system that does not exist yet.

### Deterministic allocation: largest-remainder method, canonical tie-breaking

```
total_labor_demand = sum(required_workers)

if total_labor_demand <= effective_labor_force:      # abundant or exactly equal
    allocated[i] = required[i]
else:                                                 # scarce
    floor_i     = (effective_labor_force * required_i) // total_labor_demand
    remainder_i = (effective_labor_force * required_i) %  total_labor_demand
    leftover    = effective_labor_force - sum(floor_i)
    distribute +1 to the `leftover` sectors with the largest remainder_i,
      ties broken by ascending canonical SectorCategory declaration order
```

Chosen over simpler alternatives (e.g. proportional-floor-only, which would silently under-allocate
by up to `n-1` workers with no defined rule for the remainder) specifically because it is exact,
deterministic, and provably conserves the total: `allocated_i <= required_i` always (in the
abundant branch trivially; in the scarce branch `effective_labor_force < total_labor_demand`
implies `floor_i <= required_i - 1` whenever `required_i > 0`, and `leftover` is always strictly
less than the number of positive-demand sectors, so no sector receives more than one extra unit).
Verified by direct proof, by a hand-picked all-equal-remainder fixture (eleven sectors, identical
demand, tie-breaking resolved entirely by canonical order), and by a committed Hypothesis
property test (1,000 random cases per run) proving `0 <= allocated_i <= required_i` and
`sum(allocated) == min(labor_force, sum(required))` hold for arbitrary nonnegative integer inputs.

### Allocation runs at the start of the existing production phase

No new `PHASE_ORDER` slot and no reordering: allocation is the first thing
`resolve_production_and_trade` does, immediately before per-sector output — same phase, same
turn, so same-turn linkage (population/labor-supply changes affect production the very turn they
apply) is structural, not incidental. `compute_sector_output` changes signature to accept an
explicit `allocated_workers` parameter instead of reading a state field, so the only employment
figure in play during production is the one allocation just produced this same call.
`production_accounting.aggregate_production` likewise sums employment from the caller-supplied
allocated-workers tuple rather than from `SectorState`.

### Cross-report validation extends from three reports to four

`LaborMarketReport`, `ProductionReport`, `TaxBaseDerivationReport`, and `FinanceReport` each
self-validate their own internals (mirroring the existing pattern), but — following exactly ADR
0005 R1's reasoning — nothing previously proved `LaborMarketReport.allocated_workers` for a given
sector was the same figure `ProductionReport.employed_workers` used for that same sector.
`TurnReport` gains a new `@model_validator(mode="after")` checking this per `SectorCategory`,
matched by category identity (never tuple position, for the same reason ADR 0005 R1 gave), plus
extending the existing "all present or all absent" completeness rule from three reports to four —
a partial combination (e.g. allocation ran but production silently didn't) is rejected outright.

### Invariants: defense-in-depth backstops, not an "acceptable unemployment" rule

Two new every-turn invariant codes mirror `tax_base_coefficient_out_of_range`'s role:
`effective_labor_force_share_out_of_range` (bps outside `[0, 10_000]` via bypassed construction —
`StrictBps` already blocks every legitimate path) and `effective_labor_force_exceeds_population`
(recomputed from state, catching malformed constructed state — mathematically unreachable through
ordinary construction given a valid share, and genuinely only reachable via a bypassed negative
`population`). The Phase 2B1 invariant `sector_employment_exceeds_population` is removed — it
checked an authored field that no longer exists; its role is entirely taken over by the two checks
above plus the report-level identities.

Deliberately absent: any invariant enforcing an "acceptable" unemployment range. Unemployment
level is a scenario-calibration concern (see R1 below), not an engine-level constraint — a future
crisis, war, or shock must be free to produce extreme unemployment without tripping an invariant
that was never meant to be an economic-plausibility gate.

## R1 — Recalibrate scenario unemployment to a plausible level

The first calibration pass (retuning only the two capacity realignments needed to keep
Phase 2B2's exact output/base/revenue figures — extraction and energy in `tiny_valid.yaml`, both
realigned from their old authored capacity down to their prior `actual_output`, i.e. `capacity :=
previous actual_output`) technically worked, but produced ~91% unemployment in `tiny_valid` and
~94.5% in `deficit_demo`. An independent review rejected this as implausible for developer
fixtures that appear in CLI output, documentation, and future political-effect tests — and
dangerous once unemployment feeds approval/stability mechanics in a later phase, since a fixture
everyone treats as "the normal case" would already be showing a depression-level figure.

Fixed by retuning `output_per_worker` per sector — never population, capacity, or the
labor-force share — so labor demand rises to a plausible level while every sector's
`actual_output` (and therefore every Phase 2B2 output/tax-base/revenue figure) stays byte-for-byte
identical: raising `output_per_worker` lowers `required_workers = ceil(capacity /
output_per_worker)` without touching `capacity` or `actual_output` at all. Verified exactly:
`tiny_valid` — labor force 600,000, demand 540,000, employment 540,000, unemployed 60,000
(exactly 10.00%), output 20,000,000,000, bases 4,000,000,000/2,000,000,000/3,000,000,000, all
unchanged. `deficit_demo` — labor force 200,000, demand 180,000, employment 180,000, unemployed
20,000 (exactly 10.00%), output 4,000,000,000, bases 1,000,000,000/500,000,000/800,000,000, all
unchanged. Labor stays abundant in both scenarios — no scenario relies on scarcity, since that
remains the dedicated in-test fixture's job (an eleven-sector, all-equal-remainder economy used
only to exercise the scarce-allocation and tie-breaking code paths, not committed as a playable
scenario, per the brief's warning against building a content library prematurely).

One disclosed consequence of the *original* D1-only calibration carries forward unchanged: since
`allocated == required` under abundant labor implies `labor_limited >= capacity`, `actual =
min(capacity, labor_limited) = capacity` always — `labor_constrained` becomes unreachable in
`tiny_valid` specifically (it now genuinely means "the economy ran short of workers," which is
only possible under scarcity). This is a real structural consequence of deriving employment
rather than authoring it, not a bug; it is covered by the dedicated labor-scarce in-test fixture
instead.

## R2 — Preserve the natural-resource roadmap

An independent review noted that a previously-discussed future direction — natural-resource
endowments and extraction (timber, ores, fossil fuels, uranium, etc.) — was at risk of being
silently dropped rather than explicitly deferred. `docs/roadmap.md` now records
**Phase 2C1 — Resource endowments and extraction** as an explicit, not-yet-started, deferred
entry: country-level (later province-level) deposits, finite nonrenewable reserves with exact
conservation, deterministic renewable regeneration for timber, extraction bounded by
reserves/capacity/labor/productivity, physical resource quantities kept as a distinct type family
from `Money` and `RealOutput`, and future connections to energy, industry, trade, sanctions,
nationalization, corruption, environmental damage, alliances, war, and nuclear programs. This is
**documentation only** — Phase 2B3 adds no resource code, fields, formulas, scenarios, or tests;
the entry exists so a previously-agreed future direction has a durable, honest record instead of
disappearing between planning rounds.

## Consequences

- `tests/conftest.make_economy`'s `employed_workers` parameter is removed and replaced with
  `effective_labor_force_share_bps` (default `10_000` — the full default population of `100` is
  treated as economically active, so the factory's uniform "one worker per sector" shape from
  Phase 2B1/2B2 is preserved exactly under abundant labor).
- `production_accounting.compute_sector_output` and `aggregate_production` change signature to
  accept allocated-workers explicitly rather than reading `SectorState.employed_workers`, which no
  longer exists — every call site (`phases.py`, tests) updated accordingly.
- Two new invariant codes (`effective_labor_force_share_out_of_range`,
  `effective_labor_force_exceeds_population`) replace the removed
  `sector_employment_exceeds_population`, mirroring `tax_base_coefficient_out_of_range`'s
  defense-in-depth role from ADR 0005.
- `RULESET_VERSION` bumps again: `0.4.0 -> 0.5.0`. `CountryState`'s reachable economy shape
  changes in both directions (a new required `EconomyState.effective_labor_force_share_bps` field,
  and the removal of the previously-required `SectorState.employed_workers` field), so — the same
  "nothing to migrate from" reasoning as every prior bump — old-ruleset saves are rejected
  outright. `backend/tests/fixtures/phase2b2_save_ruleset_0.4.0.json` was generated with
  unmodified Phase-2B2 code and committed *before* this bump landed, mirroring exactly how the
  Phase-1/2A/2B1 fixtures were frozen before their respective bumps. `SAVE_FORMAT_VERSION` is
  unchanged; only the ruleset/content-governed inner schema changed.
