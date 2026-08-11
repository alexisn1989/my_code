# MANDATE — Roadmap

Phases match `product_spec.md` / the original brief §38. A phase is not started until the
previous one's acceptance criteria pass and are verified (not just implemented). Section
references (`§n`) point at the numbered sections of the original brief for full requirement detail.

## Phase 0 — Discovery and project foundation — **complete**

Scope: §1–§6, §39–§40 (process rules), monorepo layout, tooling, docs.

Acceptance criteria:
- [x] Repository inspected, current state documented before any edit.
- [x] `docs/product_spec.md`, `docs/architecture.md`, `docs/adr/0001-*.md` written.
- [x] Monorepo structure created (`backend/`, `frontend/`, `data/`, `docs/`, `scripts/`).
- [x] Backend formatting/lint/type/test tooling configured and runnable (`uv sync`, `ruff`,
      `mypy`, `pytest`).
- [x] `.env.example` present; no secrets committed.
- [x] CI workflow runs lint + type-check + tests on push.
- [x] Local development instructions in `README.md`.

## Phase 1 — Pure simulation foundation — **complete**

Scope: §7 (turn structure), §8 (core game state, minimal subset), §5.4 (immutable turn history).

Minimal-slice acceptance criteria (first pass):
- [x] Typed `GameState`, `DecisionSet`, `TurnReport` (+ minimal `WorldState`, `CountryState`,
      `PopulationGroupState`, `InstitutionState`, `TreasuryState`).
- [x] Deterministic seeded RNG (`core/rng.py`), namespaced by `(seed, turn, stream)`.
- [x] Scenario loader with validation (Pydantic, YAML).
- [x] Turn resolver with the explicit 15-phase order from §7, phases registered as data.
- [x] Invariant validation (population non-negative, group shares sum to 1 within tolerance,
      turn/version bounds) run before and after resolution.
- [x] Headless CLI: create a game, resolve turns, inspect state — no server required.
- [x] One valid scenario fixture (`data/scenarios/tiny_valid.yaml`).
- [x] Tests: determinism (canonical JSON diff), turn number advances exactly once, invalid
      decisions never mutate input state, group-share validation, fixture loads.

History/persistence completion (second pass — see `docs/adr/0002-snapshot-history-and-versioning.md`):
- [x] Immutable, hash-chained `GameSave`/`HistoryEntry` above the (unchanged, still pure) resolver.
- [x] `entry_hash` covers state, decisions, report, turn, and both version fields — not state alone.
- [x] Tail-truncation guard (`entry_count` + `head_entry_hash`) independent of the chain-link check.
- [x] Recursive immutability: canonical-text storage, fresh-parse accessors, no reachable mutable
      nested state — verified by explicit mutation-attempt tests, not just a `frozen=True` flag.
- [x] Version compatibility policy: save-format/ruleset/content versions checked independently;
      Phase-0's save format rejected outright (documented why a migration is impossible, not just
      undesirable).
- [x] Atomic save writes: unique same-directory temp file, `fsync`, `os.replace`, cleanup on failure.
- [x] CLI: `new`/`inspect`/`resolve`/`history`, all operating on the real save format.
- [x] Frontend scaffold installed and verified: `npm ci`, `tsc --noEmit`, `vite build`, `vitest run`
      all pass; one render smoke test.
- [x] 100-turn deterministic soak test, duration measured and reported (no invariant violations).

Deliberately still deferred, not missing: full domain-model coverage of the remaining ~29 state
classes in §8 (`GovernmentState`, `MilitaryState`, `DiplomaticRelationState`, parties, elections,
…). Each is added in the phase that gives it real behavior — see `docs/architecture.md`, "Why not
more, yet" — never as an empty placeholder ahead of that.

## Phase 2 — Economy, budget, and population

Scope: §11 (population simulation), §13 (economy), §14 (public services), §15 (policy system,
12–15 policies for the slice).

Acceptance criteria: revenue/spending/sector/price/employment/debt formulas implemented and
reconciled by tests; central bank with policy rate, inflation response, currency effects, and a
player-facing choice between political control and operational independence; population groups
update incrementally with tracked approval reasons; policies have delayed/ramped effects; property
tests for money reconciliation and bounded metrics.

### Phase 2A — Government accounting and budget gameplay — **complete**

Scope: the government-finance slice of §13 only — tax revenue, spending, quarterly debt interest,
and deficit financing. See `docs/economy_methodology.md` for every formula and
`docs/adr/0003-government-accounting.md` for the design decisions.

Acceptance criteria:
- [x] `TaxBaseState`/`TaxPolicyState`/`SpendingPlanState`/`GovernmentFinanceState` — fixed tax
      bases, player-adjustable rates (basis points) and spending, all strict-integer validated
      (rejects float/numeric-string/bool/NaN/inf, not just non-strict coercion).
- [x] Pure `simulation/accounting.py`: per-category tax revenue, quarterly interest on *opening*
      debt only, deficit-consumes-cash-then-borrows, no automatic debt repayment — both
      reconciliation equations verified exactly (representative cases + 2,000-trial random search).
- [x] `BudgetDecision`: explicit targets (not deltas), at least one target required, no duplicate
      spending categories, at most one per `DecisionSet`.
- [x] `FinanceReport` is self-validating on every construction path (fresh build, parsed from
      history JSON, loaded from a save, CLI inspection) — independently re-derives every total and
      both reconciliation equations from its own stored fields rather than trusting the phase that
      built it; `reconciliation_status` is a derived property, not a field that could disagree with
      the numbers.
- [x] `OpeningFinanceSnapshot` captured before any budget mutation, using real copies (not bare
      references) of the nested Pydantic sub-models — proven by tests that mutate a live field
      in place, not just by reassigning the parent object.
- [x] Player country requires `GovernmentFinanceState` (AI countries may omit it) — enforced
      through the existing invariant/resolver pre-copy path, so a missing budget produces no
      accounting, no history entry, and no output file, with no bespoke exception type needed.
- [x] `RULESET_VERSION` moved from scenario-authored content to an engine constant; Phase-1 saves
      rejected with an actionable error (frozen fixture committed *before* the bump, since there is
      no other way to produce one afterward).
- [x] Reason-ID/params reports (no prose in hash-protected history) with a CLI renderer table;
      every reason ID the engine can emit is proven to have one.
- [x] CLI `resolve --decisions-file` (requires `--turns 1`); `history` shows the financial report.
- [x] Two scenario fixtures: `tiny_valid.yaml` (sustainable — used by the soak test) and
      `deficit_demo.yaml` (deliberately borrows; every figure hand-checked against the resolver).
- [x] 236 backend tests: strict-int rejection, formula edge cases, decision validation, treasury/
      debt behavior, reconciliation, self-validation corruption (one test per equation), opening-
      snapshot immutability (including in-place mutation, which caught a real reference-sharing
      bug before it shipped), compatibility, CLI workflows, 8-turn and 100-turn integration runs.

Explicitly deferred to later Phase 2 work: production sectors, GDP/prices/inflation/employment,
tax bases responding to rates, wages, central bank, exchange rates, population approval effects —
none of it simulated yet, stated plainly in `docs/economy_methodology.md` rather than implied.

### Phase 2B1 — Sector production at fixed prices — **complete**

Scope: aggregate economic sectors (§13) with capacity, labor productivity, employment, and
deterministic quarterly output at fixed base-year prices — the production foundation later phases
use to derive tax bases from real economic activity. See `docs/economy_methodology.md` for every
formula and `docs/adr/0004-sector-production-fixed-prices.md` for the design decisions.

Acceptance criteria:
- [x] `SectorCategory` (11 fixed categories), `SectorState`, `EconomyState` — strict-integer
      validated (`StrictWorkerCount`/`StrictRealOutput`/`StrictRealOutputPerWorker`, distinct
      aliases from `Money`, never conflated with spendable treasury cash), all 11 categories
      required exactly once, canonical declaration order enforced and normalized.
- [x] Pure `simulation/production_accounting.py`: labor-limited output, actual output (capped at
      capacity), floor-division capacity utilization in bps, and a four-way constraint
      classification (`capacity_constrained`/`labor_constrained`/`exactly_balanced`/`inactive`)
      with an explicit, tested tie-break for the zero-capacity/zero-employment case.
- [x] `EconomyState`'s "all 11 categories, exactly once" invariant is checked twice — once at
      construction (Pydantic validator) and independently every turn
      (`simulation.invariants`) — because `SectorState` is deliberately kept mutable (a later
      phase needs adjustable employment), so a nested `sector.category` mutation after
      construction can desynchronize an already-built `EconomyState` without re-running the
      constructor's own check; proven by a dedicated nested-mutation regression test.
- [x] `resolve_production_and_trade` (an existing, previously no-op §7 phase slot) implements
      production only — trade stays explicitly out of scope; `PHASE_ORDER` unchanged.
- [x] `ProductionReport` is self-validating on every construction path (mirrors `FinanceReport`'s
      pattern exactly), player-country-only, with canonical per-sector ordering so
      logically-identical reports serialize byte-identically regardless of authored order.
- [x] Full isolation from Phase 2A accounting, in both directions, actively tested (not just
      documented): a `FinanceReport` is byte-identical across wildly different `EconomyState`
      fixtures, and a `ProductionReport` is byte-identical across different finance/budget states.
- [x] `RULESET_VERSION` bumped again (`0.2.0 -> 0.3.0`) — `CountryState.economy` becomes a new
      required player field with no data to backfill from an older save; a Phase-2A-ruleset save
      fixture was frozen *before* the bump, mirroring the Phase 1 → 2A precedent.
- [x] CLI `inspect`/`history` extended with a production summary and per-sector breakdown; new
      `reason_id`s (`production_summary`, `sector_inactive`) added to the renderer coverage test —
      concise summary entries only, not a full per-sector dump duplicated into history every turn.
- [x] Two scenario fixtures updated: `tiny_valid.yaml` (all 11 sectors, hand-checked, covering all
      four classifications) and `deficit_demo.yaml` (uniform, hand-checked).
- [x] 315 backend tests: strict-quantity rejection, formula/classification correctness (including
      both zero-capacity and zero-employment edge cases), report self-validation corruption,
      canonical-ordering byte-identical serialization, resolver/history tamper detection extended
      to the new `production`/`economy` fields, Phase-2A regression/isolation, compatibility
      fixture rejection, and the existing 8-turn/100-turn integration and soak runs re-verified
      with production resolving every turn.

Explicitly deferred: tax-base derivation from production, GDP/value-added/real-growth figures,
prices, inflation, wages, unemployment/labor-force dynamics, hiring/layoffs, population approval
effects, and any behavioral link between taxes/spending and sector output — none of it implied or
half-built, stated plainly in `docs/economy_methodology.md`.

### Phase 2B2 — Production-derived tax bases — **complete**

Scope: derive Phase 2A's tax bases from Phase 2B1's sector production, replacing the fixed
scenario-authored bases — the one connection Phase 2B1 deliberately left out. See
`docs/economy_methodology.md` for the full formulas and `docs/adr/0005-production-derived-tax-bases.md`
for the design decisions.

Acceptance criteria:
- [x] `GovernmentFinanceState.tax_bases` removed; replaced by a new `TaxBaseCoefficients` model
      (country-level fiscal-reach coefficients) plus new per-sector
      `value_added_share_bps`/`labor_income_share_bps` on `SectorState` — tax bases are now
      purely derived, turn-local, and never written back into `GameState`.
- [x] Pure `simulation/tax_base_derivation.py`: modeled-value-added/labor-income/operating-surplus
      decomposition and three tax-base contributions per sector, summed nationally (sum-of-parts,
      not a national recompute) and converted to `Money` through exactly one named function,
      `base_year_real_output_to_money` (`app.core.quantity`) — the sole real-output-to-nominal-money
      boundary, using an exact-integer-bps price index rather than a runtime float.
- [x] Self-validating `TaxBaseDerivationReport`/`SectorTaxBaseReport`, mirroring
      `FinanceReport`/`ProductionReport`'s pattern — plus new `TurnReport`-level cross-report
      validation proving the whole chain agrees: production's `actual_output` matches
      derivation's input per sector category (matched by category identity, not tuple position),
      derivation's output matches finance's applied bases exactly, and
      production/derivation/finance reports are all present or all absent together.
- [x] Derivation runs at the start of the existing revenue phase (no new `PHASE_ORDER` slot, no
      reordering) — production (phase 3) already precedes revenue (phase 4), so same-turn linkage
      is structural; proven across a real multi-turn run, not just turn 0.
- [x] The relationship is one-directional: sector production affects tax bases and therefore
      revenue; tax rates and spending still do not affect production or the bases derived from it
      — actively tested in both directions, including a deliberately-inverted replacement for a
      Phase 2B1 isolation test that had become vacuously true (not meaningfully true) under the
      new code.
- [x] Both scenario fixtures re-calibrated so derived tax bases reproduce the original Phase 2A
      authored bases **exactly** — verified by direct computation and by resolving turn 0 through
      the real engine — so every existing Phase 2A hand-checked revenue/interest/borrowing/
      reconciliation figure in both fixtures is unchanged.
- [x] `RULESET_VERSION` bumped again (`0.3.0 -> 0.4.0`); a Phase-2B1-ruleset save fixture was
      frozen *before* the bump, mirroring every prior ruleset-bump precedent.
- [x] CLI `inspect`/`history` extended with a tax-base derivation summary and per-sector
      breakdown; new `tax_bases_derived` reason ID added to the renderer coverage test.
- [x] 379 backend tests: strict coefficient validation, formula/rounding-boundary correctness
      (including a hand-picked case proving sum-of-parts genuinely differs from a national
      recompute), cross-report chain corruption in every direction, unit-bridge conversion
      function tests, coefficient-range invariant backstops, resolver/history tamper detection
      extended to the new report/state fields, compatibility fixture rejection, calibration
      exactness against both real scenarios, same-turn/no-lag verification, and the existing
      8-turn/100-turn integration and soak runs re-verified with derivation resolving every turn.

Explicitly deferred: tax-rate elasticity, tax avoidance/compliance behavior, Laffer-curve effects,
production responses to taxes, hiring/firing/labor movement, wage bargaining, unemployment,
capacity investment or depreciation, prices, inflation, GDP/value-added/real-growth figures, trade,
population approval effects — none of it implied or half-built, stated plainly in
`docs/economy_methodology.md`.

### Phase 2B3 — Labor allocation and unemployment at fixed prices — **complete**

Scope: replace the last remaining hand-authored input in the production chain —
`SectorState.employed_workers` — with a deterministic, instantaneous labor foundation: population
→ effective labor force → sector labor demand → deterministic worker allocation → employment and
unemployment → existing production → existing tax-base and finance chain. Still fixed prices; no
wages, hiring friction, tax behavioral responses, or population approval. See
`docs/economy_methodology.md` for every formula and
`docs/adr/0006-labor-allocation-at-fixed-prices.md` for the design decisions.

Acceptance criteria:
- [x] `SectorState.employed_workers` removed entirely — employment is fully turn-local and derived,
      never authored, mirroring why `GovernmentFinanceState.tax_bases` was removed in Phase 2B2.
      `EconomyState` gains a required `effective_labor_force_share_bps` — a deliberate reduced-form
      coefficient (working-age share, participation, and other structural availability, temporarily
      combined into one number) — feeding `effective_labor_force = floor(population *
      effective_labor_force_share_bps / 10_000)`, proved `0 <= effective_labor_force <= population`
      by construction.
- [x] Pure `simulation/labor_allocation.py`: ceiling-division sector labor demand
      (`required_workers = ceil(capacity / output_per_worker)`, `0` when capacity is `0`), and a
      largest-remainder allocation algorithm with an explicit, tested canonical-order tie-break —
      proven to conserve the total and never over-allocate a sector both by direct proof and by a
      committed Hypothesis property test (1,000 random cases per run: `0 <= allocated_i <=
      required_i`, `sum(allocated) == min(labor_force, sum(required))`, always).
- [x] Labor allocation runs at the very start of the existing production phase (no new
      `PHASE_ORDER` slot, no reordering) — production consumes this same turn's allocation with no
      lag, proven across a real multi-turn run.
- [x] Self-validating `LaborMarketReport`/`SectorLaborAllocationReport`, mirroring the existing
      report pattern — plus a fourth `TurnReport`-level cross-report check (allocation matches what
      production actually used, per category) extending the existing three-report completeness
      rule to four; every partial combination of the four reports is rejected.
- [x] The relationship stays one-directional: labor supply affects production, tax bases, and
      revenue; tax rates and spending still do not affect allocation or production — actively
      tested in both directions.
- [x] Both scenario fixtures recalibrated (`output_per_worker` retuned only — never population,
      capacity, or the labor-force share) to land at a plausible ~10% unemployment rate
      (`tiny_valid`: labor force 600,000 / employment 540,000 / unemployed 60,000; `deficit_demo`:
      labor force 200,000 / employment 180,000 / unemployed 20,000 — both exactly 10.00%) while
      every existing Phase 2B2 output/tax-base/revenue figure in both fixtures stays byte-for-byte
      identical.
- [x] `RULESET_VERSION` bumped again (`0.4.0 -> 0.5.0`); a Phase-2B2-ruleset save fixture was
      frozen *before* the bump, mirroring every prior ruleset-bump precedent.
- [x] CLI `inspect`/`history` extended with a labor-market summary and per-sector allocation
      breakdown; new `labor_market_resolved` reason ID added to the renderer coverage test.
- [x] 437 backend tests: labor-supply/demand formula edge cases, allocation algorithm correctness
      including canonical tie-breaking and the Hypothesis property test, report self-validation
      corruption, the extended four-report cross-validation chain, resolver/history tamper
      detection extended to the new report/state fields, compatibility fixture rejection,
      calibration exactness against both real scenarios, same-turn/no-lag verification, and the
      existing 8-turn/100-turn integration and soak runs re-verified with allocation resolving
      every turn.

Explicitly deferred: wages/wage bargaining, minimum wage, hiring/firing delay or adjustment costs,
skills/education matching/occupations, worker mobility costs, labor unions/strikes, unemployment
benefits, demographic age structure, migration/population growth, tax-rate or spending effects on
labor supply/demand, production investment/depreciation, prices/inflation, GDP/growth figures,
trade, population approval effects — none of it implied or half-built, stated plainly in
`docs/economy_methodology.md`.

### Phase 2C1 — Resource endowments and extraction — **complete**

Scope: the shallow base-game resource foundation deferred (not designed) at the end of Phase 2B3
— a conservation layer distinct from Phase 2B's aggregate sector production: eight physical
natural resources (timber, iron ore, coal, crude oil, natural gas, uranium, copper, critical
minerals), country-level finite reserves, deterministic timber regeneration, and extraction
bounded by stock/capacity/labor/productivity. Deliberately **not** the future Resources and Energy
expansion — see "Explicitly deferred" below. See `docs/economy_methodology.md` for every formula
and `docs/adr/0007-resource-endowments-and-extraction.md` for the design decisions, including the
R1–R9 independent-review corrections applied during this phase.

Acceptance criteria:
- [x] `ResourceCategory` (8 fixed categories, canonical declaration order) and
      `EconomyState.resource_deposits: tuple[ResourceDepositState, ...]` — all 8 categories
      required exactly once, zero-stock/zero-capacity entries legal. **Unlike every other
      canonical-order validator in the codebase, noncanonical resource order is REJECTED, not
      silently normalized** (R3) — a deliberate divergence, justified in the ADR.
- [x] New physical-quantity type family in `core/quantity.py`
      (`StrictResourceQuantity`/`StrictResourceQuantityPerWorker`) — distinct from `Money` and
      `RealOutput`; no conversion function to either exists, so "resources feed nothing yet" is
      structurally true, not just documented. Heterogeneous resource quantities (tonnes, barrels,
      cubic metres) are never summed together — only worker counts and per-status counts are
      aggregated.
- [x] Pure `simulation/resource_extraction.py`: regeneration (renewable only, clamped to a stock
      ceiling, applied before extraction the same turn), ceiling-division labor demand, extraction
      bounded by `min(available_stock, extraction_capacity_per_turn, allocated_workers *
      output_per_worker)`, exact conservation by construction, and a five-way status
      classification (`inactive`/`depleted`/`stock_constrained`/`capacity_constrained`/
      `labor_constrained`) with an explicit boundary rule: when available stock exactly ties
      extraction capacity, the deposit reports `stock_constrained`, not `capacity_constrained` —
      the stock, not the capacity, determined the outcome (R8).
- [x] The shared largest-remainder allocation core (labor and resources both use it) moved to a
      new, category-agnostic `simulation/integer_allocation.py` — **explicitly order-sensitive by
      contract, not permutation-independent** (R7): `labor_allocation.allocate_workers` keeps its
      existing canonical-tuple signature byte-for-byte; the resource wrapper
      (`allocate_extraction_workers`) takes a category-keyed mapping and canonicalizes to
      `tuple(ResourceCategory)` order *before* calling the core, so permuting the mapping's
      insertion order provably cannot change the result.
- [x] Extraction runs at the very start of `resolve_production_and_trade` (phase 3), immediately
      after labor allocation, sub-allocating the extraction sector's already-allocated workers
      across the 8 deposits. No `PHASE_ORDER` change. **Depletion is applied in the same step**
      (R2) — a deliberate, narrow, explicitly-tested exception to phase 3's prior "never mutates
      state" contract, scoped to `economy.resource_deposits` alone; phase 5 needs no
      resource-related code at all.
- [x] Self-validating `ResourceExtractionReport`/`ResourceDepositReport` — the deposit report
      carries `regeneration_per_turn`/`stock_ceiling` (R1) specifically so regeneration is
      genuinely re-derivable from the report's own stored fields, not merely trusted. `TurnReport`
      gains a fifth report and a new cross-report check (labor's extraction-sector allocation
      matches the resource report's worker budget exactly); the completeness rule extends from
      four reports to five, rejecting all 30 proper nonempty partial combinations.
- [x] The relationship stays one-directional and conservation-only (D8): resource endowments
      determine extraction; extraction changes no production, tax base, revenue, price, trade,
      approval, or war outcome this phase — actively tested in both directions, including that
      phase 3's mutation is scoped to `resource_deposits` and nothing else in state.
- [x] Both scenario fixtures gain resource endowments — `tiny_valid.yaml` resource-rich (all 8
      categories active), `deficit_demo.yaml` resource-poor/import-dependent (only timber and iron
      ore endowed) — while every existing Phase 2B3 labor/production/tax-base/revenue/treasury
      figure in both stays byte-for-byte identical. `deficit_demo`'s timber trajectory is worked
      out exactly across three regimes: capacity-bound decline (resolutions 1–39), a
      `stock_constrained` boundary turn where available stock ties capacity exactly (resolution
      40), and a steady state extracting exactly the regenerated amount forever (resolutions 41+).
- [x] `RULESET_VERSION` bumped again (`0.5.0 -> 0.6.0`); a Phase-2B3-ruleset save fixture was
      frozen *before* the bump, mirroring every prior ruleset-bump precedent.
- [x] CLI `inspect`/`history` extended with a resource-extraction summary and per-deposit
      breakdown (each in its own physical unit); `inspect` also summarizes endowments at turn 0,
      directly from state, since (unlike production/labor figures) they exist before any turn is
      resolved. New `resource_extraction_resolved` reason ID added to the renderer coverage test.
- [x] 567 backend tests: strict physical-quantity validation, formula/classification correctness
      including the three-regime timber dynamic and the stock/capacity tie boundary, the neutral
      allocation core's order-sensitivity pinned directly (not just its wrappers' behavior),
      mapping-permutation resistance for the resource wrapper, report self-validation corruption
      (including the two new R1 fields), the extended five-report cross-validation chain (all 30
      partial combinations), resolver/history tamper detection extended to the new state/report
      fields, a CLI-level no-stray-temp-file assertion (R5), compatibility fixture rejection,
      calibration exactness against both real scenarios, same-turn/no-lag verification, phase-3
      mutation-scope isolation, and the existing 8-turn/100-turn integration and soak runs
      re-verified with extraction resolving every turn (plus a dedicated 100-turn `deficit_demo`
      soak exercising the full three-regime timber trajectory).

Explicitly deferred — this is the shallow base-game foundation, not the future **Resources and
Energy expansion**: market prices/inflation/exchange-rate valuation for resources; imports,
exports, trade routes, tariffs, embargoes, stockpiles separate from deposits; resource-to-industry
input-output chains and energy conversion (the extraction sector's `RealOutput` and physical
tonnage remain two descriptions of the same labor, not two connected activities — see the ADR);
pipelines, refineries, individual mines/fields, construction, maintenance; ownership, private
firms, state enterprises, royalties, concessions, foreign investment; nationalization,
privatization, cartels, lobbying, corruption, sanctions, smuggling; pollution, climate effects,
reclamation, accidents, environmental politics; military consumption, strategic reserves, resource
wars, nuclear-weapons inputs; exploration, discovery, technological substitution, reserve
reclassification; province/field/mine-level geography (waits for Phase 6's map); any new API
route, database table, migration, or gameplay frontend. None of it implied or half-built, stated
plainly in `docs/economy_methodology.md`.

### Phase 2C2 — Physical extraction drives extraction-sector output — **complete**

Scope: replace (never add to) the extraction sector's `RealOutput` derivation with one computed
from that turn's physical extraction, through a single named unit-bridge function mirroring
`base_year_real_output_to_money`. Resolves ADR 0007's limitation 2 ("two descriptions of the same
labor, not two connected activities"). See `docs/economy_methodology.md` for every formula and
`docs/adr/0008-physical-extraction-derived-sector-output.md` for the design decisions, including
the R1–R10 independent-review corrections applied before implementation.

Acceptance criteria:
- [x] `EconomyState.resource_output_coefficients: tuple[ResourceOutputCoefficient, ...]` — one
      strictly-positive (`gt=0`) `real_output_per_unit` per `ResourceCategory`, all 8 required
      exactly once, canonical order **rejected, not normalized** (mirroring the resource-deposit
      precedent, not the sector-order normalize-on-reorder one). A single named bridge function
      (`core/quantity.extracted_resource_to_real_output`) performs exact integer multiplication,
      no division anywhere, mirroring `base_year_real_output_to_money`'s shape.
- [x] The extraction sector stops calling `production_accounting.compute_sector_output` entirely
      — that module stays completely unmodified. A new pure `simulation/resource_output.py`
      converts both the actual extracted quantity and the potential (stock/capacity-bounded)
      quantity per deposit, then aggregates both totals in canonical order.
- [x] `capacity_utilization_bps`/`constraint` for the extraction row are computed from the
      potential-output total, never from the legacy `quarterly_capacity_output` — proven to need
      no saturating clamp, since `actual <= potential` holds by construction (a property test
      confirms this for arbitrary valid inputs). Both legacy sector-level fields
      (`quarterly_capacity_output`/`output_per_worker`) are completely inert for every derived
      field on the extraction row, contrasted against a STANDARD sibling sector where the
      identical mutation does change output.
- [x] A dedicated `SectorProductionConstraint.PHYSICAL_RESOURCE_CONSTRAINED` value (report.py-local,
      not added to the engine's own `SectorConstraint`); `actual_output > potential_output` is
      **rejected by validation, never classified**, at three independent layers (row-level,
      aggregate-level, and the shared classification function's own `raise`). Zero employment
      with positive potential stays `LABOR_CONSTRAINED`, matching the 2B1 precedent.
- [x] `TurnReport` gains three new cross-validators authoritatively checking the extraction row's
      `actual_output`/`capacity_utilization_bps`/`constraint` against `ResourceExtractionReport`'s
      totals — `TurnReport` stays at five reports, the 30-subset completeness rule unchanged.
- [x] The accounting identity — extraction contributes to `total_gross_output` exactly once —
      proven end to end through the real resolver, not merely asserted structurally.
- [x] Both scenarios recalibrated with honest round-integer coefficients: `tiny_valid.yaml`
      preserves every pre-2C2 figure exactly for its full 100-turn tested horizon;
      `deficit_demo.yaml` preserves turn 1 only, then diverges exactly at the same turn-26
      (iron_ore depletion) and turn-41 (timber steady state) boundaries ADR 0007 already
      established for the physical trajectory — pinned by dedicated boundary tests, not
      spot-checked.
- [x] `RULESET_VERSION` bumped again (`0.6.0 -> 0.7.0`) in the same lockstep every prior phase has
      used, justified by schema-shape compatibility alone — the corrected content-version policy
      explicitly documents that same-ruleset scenarios routinely carry different coefficient
      values, retracting an earlier drafted claim to the contrary. A Phase-2C1-ruleset save
      fixture was frozen with the genuinely unmodified engine before the bump.
- [x] CLI `inspect --coefficients` shows the full coefficient table read directly from state;
      `resolve`/`history` extended with per-resource output/potential contributions and the
      sector-aggregate totals/utilization/constraint.
- [x] 660 backend tests: bridge exactness and no-rounding (including a Hypothesis property test),
      `output_basis` structural design, the no-clamp-needed proof, reject-not-classify behavior
      and its zero-employment/deterministic-tie corollaries, the direct accounting identity,
      strengthened legacy-field inertness, the reversed resource-endowment isolation boundary
      (ADR 0007's own test rewritten, not deleted), exact turn-26/turn-41 boundaries extended
      through the 100-turn soak, tamper detection extended to the new state/report fields, and
      frozen-fixture compatibility rejection.
- [x] Only 4 of the originally-proposed 14 invariant codes were implemented, deliberately: 10
      would have checked report-vs-formula correctness, which `check_invariants` cannot see
      (it runs on `GameState` alone, before `TurnReport` is even constructed). That intent is
      covered more thoroughly by report.py's self-validators and `TurnReport`'s cross-validators
      instead — see the ADR's "Known limitations" for the full reasoning.

Explicitly deferred, unchanged from ADR 0007: market prices/inflation/exchange-rate valuation;
imports, exports, trade routes, tariffs, embargoes, stockpiles separate from deposits; ownership,
private firms, royalties, concessions, nationalization; environmental effects; military
consumption or strategic reserves; exploration/discovery/reserve reclassification;
province/field-level geography; education/productivity policy; approval/politics; diplomacy/
military/war; any new API route, database table, or gameplay frontend.

## Phase 3 — Government and political survival

Scope: §9 (constitutional system), §10 (political capital/action capacity), §12 (parties/
legislature), §19 (coups/revolutions — risk surfacing), §20 (elections — scheduling/polling), §21
(leaders/cabinet). Split into three sub-phases: **3A** lays the constitutional and metric
foundation (this is the smallest slice that later sub-phases can build onto without reshaping the
state model); **3B** spends political capital through legislative/faction bargaining, itself split
into **3B1** (legislature, parties, blocs and budget bargaining) and **3B2** (relationship
evolution, competing capital uses, non-budget laws); **3C** adds government survival (elections,
coups, removal).

### Phase 3A — Constitutional foundation, legitimacy and political capital — **complete**

Scope: the nine-axis `ConstitutionState` and its C1–C9 validity rules (§9's composable dimensions,
structural validity only — never a legitimacy judgment); scenario-authored
`constitutional_order_support_bps` and a form-blind legitimacy formula that drifts toward it;
economic performance (`total_gross_output`, `unemployment_rate_bps`) as the only other legitimacy
input; political capital that regenerates from legitimacy alone. No parties, legislature, elections,
coups, or removal from power — those are 3B/3C. See `docs/economy_methodology.md` for every formula
and `docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md` for the R1–R8
independent-review corrections applied before implementation.

Acceptance criteria:
- [x] `simulation/constitution.py`: seven `StrEnum` axes (`ExecutiveSystem` incl. `MONARCHICAL`,
      `ExecutiveSelection`, `Legislature`, `TerritorialOrganization`, `JudicialReview`,
      `AmendmentDifficulty`, `DecreeAuthority`) plus two optional scalars
      (`executive_term_limit_terms`, `national_election_interval_turns`); C1–C9 validity rules
      rejecting incoherent combinations only, exporting no legitimacy scoring of any kind; full
      10,368-configuration coverage computed and pinned (2,862 valid, 7,506 rejected, every rule
      independently reachable).
- [x] `simulation/legitimacy.py`: a pure module whose public functions accept no constitutional
      type at all — a compile-time, `mypy`-checked neutrality guarantee. Legitimacy drifts toward
      the scenario-authored `constitutional_order_support_bps` at a uniform, form-independent rate;
      economic performance (output change + unemployment change, each independently sensitivity-
      weighted and capped) is the only other input. Five authored orders spanning
      accepted/illegitimate monarchy and accepted/unpopular democracy proven to agree on an
      explicitly enumerated six-field numeric projection turn by turn, while their constitution
      digests genuinely differ.
- [x] `PoliticalState`/`EconomicBaselineState` on `CountryState.politics` (optional, player-required
      like `finance`/`economy`); the baseline is a turn-scoped observation record with a four-stage
      lifecycle (read/assess/write/report), `None` only on the first resolved turn, never a
      fabricated zero.
- [x] `PoliticalReport` (ten self-validators, each independently re-deriving one equation from the
      report's own stored fields) and `TurnReport.political` (three cross-validators against the
      production/labor-market observations and the resolved turn number); the all-present-or-all-
      absent completeness rule extends from five reports (30 rejected subsets) to six (62).
- [x] `simulation/reconciliation.py`: `reconcile_political_report` compares the political report
      against both the opening and closing `GameState` across eleven check groups (every field of
      every group independently corruptible and independently rejected), called from
      `resolver.py` immediately after `TurnReport` construction — the same architectural seam
      `TurnReport`'s own lack of state access forced onto its own module, not a validator.
- [x] `validate_history` parses each entry's `report_json` and re-runs `reconcile_political_report`
      against the neighbouring entry's state, catching consistently re-hashed tampers a stale-hash
      check alone would miss; the one change in this phase with a measurable performance cost,
      measured immediately before and after (soaks stayed at roughly 1.5–1.6x their pre-change
      duration, safely under the plan's ~2x stop threshold).
- [x] Slot 10 (`update_group_welfare_approval_trust_radicalization`) implements the political phase
      — no sixteenth `PHASE_ORDER` slot, following the precedent four consecutive prior phases
      established. `OpeningPoliticalSnapshot` (mirroring `OpeningFinanceSnapshot`) captures opening
      values by value before any mutation.
- [x] Twelve state-structural invariant codes (`_check_politics`), each decidable from a
      `GameState` alone; report-formula and report-vs-state checks are deliberately not
      duplicated here, guarded by a static source-scan test.
- [x] Both scenarios recalibrated with a `politics:` block on their player country only: `tiny_
      valid.yaml` (well-accepted parliamentary order, support 8,000, monotone legitimacy to 7,991
      over 100 turns) and `deficit_demo.yaml` (less-accepted presidential order, support 6,500,
      legitimacy dipping exactly at the existing turn-26/turn-41 resource-depletion boundaries).
- [x] CLI `inspect --politics` shows the full axis table, authored order support, legitimacy,
      political capital and the persisted baseline; `resolve`/`history` show the political block
      on both display code paths independently.
- [x] `RULESET_VERSION` bumped again (`0.7.0 -> 0.8.0`) in the same lockstep every prior phase has
      used, justified by schema-shape compatibility — `CountryState.politics` becomes required for
      the player. A Phase-2C2-ruleset save fixture was frozen with the genuinely unmodified engine
      before the bump.
- [x] 944 backend tests: constitutional validity and full configuration coverage, legitimacy/
      political-capital unit and Hypothesis-property tests, the form/support-independence
      projection matrix, the baseline lifecycle end to end through the real resolver, report self-
      validation and cross-checks, reconciliation, history-replay revalidation (both consistently
      re-hashed and traditional stale-hash tampers), phase isolation in both directions, resolver
      atomicity for stale decisions and invalid political state, the resource-depletion shock
      reproduced exactly, soak bounds and trajectories, and CLI display coverage.

Explicitly deferred to 3B/3C or later at the time 3A shipped: political-capital expenditure
(nothing spent it yet — it regenerated and pinned to capacity); parties, legislators, law passage;
elections, coups, removal from power; characters, appointments, institutional
loyalty/power/competence; courts deciding cases; repression, protests, uprisings, civil war;
AI-country politics (rejected outright, not silently unmodeled);
`PopulationGroupState`/`InstitutionState`'s float approval/trust/loyalty fields (unconverted, read
by no formula); `FinanceReport`/`TreasuryState` reconciliation (a pre-existing, unrelated gap,
tracked separately). **Phase 3B1 below has since closed the first two of these.**

### Phase 3B1 — Legislature, parties, blocs and political-capital bargaining — **complete**

Scope: §10 (political capital spent on a concrete action), §12 (parties/legislature, bloc support
model). Builds on 3A's `PoliticalState.political_capital`, which first becomes genuinely spendable
here. Full rationale and calibration:
[`docs/adr/0010-legislature-parties-and-political-capital-bargaining.md`](adr/0010-legislature-parties-and-political-capital-bargaining.md).

- [x] `LegislatureState`: one or two chambers, parties with a government role
      (coalition / confidence-and-supply / opposition), and internal blocs owning the seats and
      carrying discipline, government relationship and tax/spending preferences. Canonical identity
      ordering is **rejected, never silently normalised**, and per-chamber seat totals must
      reconcile **exactly** — unheld seats would be permanent abstentions nobody can bargain with.
- [x] Pure `apportionment.py` (chamber-level largest-remainder, five proved properties, fixing a
      per-bloc truncation that gave 100 one-seat blocs at 60% support **zero** seats where one
      100-seat bloc got 60) and pure `legislative_voting.py` (role anchor → relationship →
      policy compatibility → influence → discipline). **Neither module accepts a
      `ConstitutionState` or any constitutional enum** — the same `mypy`-checked neutrality
      guarantee 3A established for legitimacy, now covering seats and votes.
- [x] Strict majority `total_seats // 2 + 1`: a 50/50 tie **fails** and no tie-breaker exists.
      Bicameral passage is **AND across independently decided chambers**; pooled totals never
      decide passage.
- [x] The budget is gated on the vote: slot 1 resolves it, slot 2 commits the proposed policy only
      on `PASSED_LEGISLATIVE`/`ENACTED_BY_DECREE`, slot 10 commits the capital, slot 15 assembles
      the report. No new phase-order slot. With **no** decision the path is byte-identical to
      pre-3B1, preserving every committed Phase 2 figure.
- [x] A failed vote **consumes the committed capital** (refunding would let a player
      binary-search the passage threshold for free), and commitment is bounded by **opening**
      capital, not opening + regeneration.
- [x] Decree route at a fixed 250 political capital for `decree_authority: unlimited`, with no
      chamber or bloc rows. An unavailable or invalid decree is an **invalid decision, not an
      outcome**: the turn aborts atomically — no advancement, no capital, no history entry, input
      byte-identical, no output or temp file.
- [x] **C10** as a real constitutional rule: with no legislature the executive must hold unlimited
      decree authority, or no organ can make law at all. Enforced on every path; makes
      `decree_authority` validity-affecting for the first time (valid configurations
      2,862 → 2,538, C10 first on exactly 324 of 10,368).
- [x] Seventh report member `LegislativeReport` (13 self-validators), reconciliation groups 12–18
      (legislature identity, per-field budget gating against the actually-submitted decision,
      capital ordering, and a canonical BLAKE2b decision digest), and **history replay running the
      identical check** — closing a gap where a consistently re-hashed decision tamper passed every
      integrity check.
- [x] `RULESET_VERSION` bumped `0.8.0 -> 0.9.0` with a genuine 0.8.0 fixture frozen beforehand and
      rejected specifically by `UnsupportedRulesetVersionError`. **No migration is fabricated** —
      composition is authored content an engine cannot guess.
- [x] Three scenarios spanning the meaningful cases, every figure derived by tests from the files
      themselves: `tiny_valid` passes unaided (**58/100** and **33/60**); `deficit_demo` **fails**
      47/100 and needs a **162**-point bargain; new `decree_state.yaml` (monarchical / hereditary /
      unicameral / **unlimited**) fails at **282** (50/100), passes at **283** (51/100), and can
      decree for **250**. The ordering `0 < 162 < 250 < 283` is established by an exhaustive
      dynamic program, not sampling.
- [x] CLI: `inspect --legislature` (authored composition only — **never** a proposal support
      tally), one shared legislative renderer used by **both** `resolve` and `history --turn N`,
      and two reason IDs (`legislative_vote_resolved`, `budget_blocked_by_legislature`).
- [x] 1,463 backend tests, including a 100-turn soak submitting a proposal **every** turn.

Known limitations, all recorded in ADR 0010 rather than left implicit: `EMERGENCY_ONLY` confers no
decree power (no emergency system exists to read); at capacity with unlimited decree authority a
decree may weakly dominate legislating, so the claim that every route always carries a lasting
opportunity cost is **explicitly retracted**; legislature composition is **static**; and the budget
is the only proposal kind.

### Phase 3B2 — Relationship evolution, competing capital uses and non-budget laws

Scope: §12 (faction bargaining, dynamic), the rest of §10. Builds directly on 3B1's static
legislature.

Acceptance criteria: bloc relationships **evolve** in response to how the government treats them
(bargained with, bypassed by decree, repeatedly ignored), with realignment and defections; a
second proposal kind, which is also the point at which `DecisionSet` gains a genuine discriminated
union; **competing political-capital expenditures within a single turn** (`POL-3` below), which is
what makes the commitment opportunity cost strategically binding rather than notional; confidence
votes and coalition collapse; conference committees or override procedures for bicameral
disagreement; per-proposal supermajorities keyed to `amendment_difficulty`; AI-country politics
once AI economies exist.

### Phase 3C — Government survival

Scope: §19 (coups/revolutions — risk surfacing), §20 (elections — scheduling/polling), §21
(leaders/cabinet). The first sub-phase that can remove the player from power — by construction,
not by omission, in 3A/3B.

Acceptance criteria: institution loyalty/power/competence tracked; coup/unrest risk indicators
visible with named contributing factors; election scheduling and polling with uncertainty; ~20–40
cabinet-relevant characters for the first scenario. Also the named unblockers for two Phase 3B1
limitations: an **emergency system** (which is what would give `decree_authority: emergency_only`
any meaning), and **courts / judicial review / constitutional-crisis mechanics** (which is what
illegal or extra-constitutional decrees would need — `judicial_review` already exists as a
constitutional axis read by nothing), plus a **non-stock cost for decree use**.

### Named follow-up tickets

Small, independently attributable items deliberately kept out of the phase they were noticed in,
so each lands as its own reviewable change rather than riding along inside an unrelated one.

| Ticket | Scope | Status |
|---|---|---|
| `POL-2` | Resolve the `InstitutionState` / `LegislatureState` overlap. Both shipped scenarios author an inert institution whose id is literally `legislature`, with float approval/trust/loyalty metrics no formula reads. **Re-scoped** from "convert the floats to strict bps" to "resolve the overlap" — converting eight floats would not address the duplication. Migrating the remaining inert float fields to strict bps rides along with it. | open |
| `POL-3` | Competing political-capital expenditures within a turn, plus relationship consequences for how blocs are treated. The specific unblocker for ADR 0010's retracted opportunity-cost claim: today capital has exactly one sink, so per-turn bandwidth at capacity is effectively free. Lands in Phase 3B2. | open |
| `FIN-1` | Reconcile `FinanceReport` closing balances against `TreasuryState`. Deliberately **not** absorbed into 3B1: it would not have caught a gating bug, since a failed vote produces perfectly self-consistent finance numbers for the *wrong* budget — reconciliation group 16 is what catches that. | open |
| `FE-1` | Clear the dev-only transitive `nanoid` advisory by regenerating the frontend lockfile so `postcss` resolves `nanoid >= 3.3.17`. Dev-only, transitive, fix available, not a regression (the advisory database changed). Kept separate from every gameplay phase. | open |
| `HIST-1` | An unreachable duplicate `return` in `history.py`. **Closed** — its removal was forced during Phase 3B1 when `_validate_entry_payload`'s return type changed from a 3-tuple to a 4-tuple. | closed |

## Phase 4 — Persistence and API

Scope: §29 (persistence), §30 (API design), §31 (security/integrity, non-auth items).

Acceptance criteria: PostgreSQL schema + Alembic migrations apply cleanly to an empty database;
`POST /games`, decision validation, atomic turn resolution in one transaction, `GET` state/
briefing/history/report endpoints; export/import round-trips; idempotency/state-version protection
on turn resolution; structured validation errors.

## Phase 5 — Playable frontend

Scope: §26 (UI), §28 (accessibility, initial pass).

Acceptance criteria: new-game flow, overview, budget, policies, population, politics, and turn
report screens against the real API; effect previews with reason breakdowns; a complete
browser-based domestic gameplay loop (no diplomacy/war UI yet).

## Phase 6 — Map, diplomacy, and trade

Scope: §6 (map/province validation), §16 (diplomacy), §17 (trade), §24 (AI countries, initial).

Acceptance criteria: validated fictional GeoJSON for one continent / six countries; interactive map;
bilateral diplomatic actions and treaties with AI evaluation; trade routes in ≥3 aggregated goods;
five simplified AI countries acting on legally available information.

## Phase 7 — Military and war

Scope: §18 (military and war), AI war-rationality tests from §24.

Acceptance criteria: province-based unit movement/posture/mobilization; explainable combat
resolution; casualties/occupation/war-support tracking by group and institution; negotiated peace;
AI rationality tests (e.g. a nearly bankrupt country avoids optional wars) pass.

## Phase 8 — Events, tutorial, and content

Scope: §22 (events/crisis system), §35 (tutorial), §36 (The Arken Crisis scenario).

Acceptance criteria: data-driven event engine with eligibility/cooldowns/chains; ≥20 events
including two multi-step chains for the vertical slice (→100 at content-complete alpha); tutorial
scenario teaching the order in §35; The Arken Crisis authored per §36 with five distinct AI
countries.

## Phase 9 — Balance, accessibility, and alpha polish

Scope: §32 (testing strategy, full), §33 (balance/observability), §34 (difficulty), §28
(accessibility, full audit).

Acceptance criteria: headless simulation runner over hundreds of seeded AI-only games with
aggregate stats (game duration, removal causes, war/coup/debt-crisis frequency, regime survival
rates); no dominant strategy across regime types; accessibility audit passed; difficulty settings
(story/standard/hard/custom) implemented without simply scaling AI resources; save-compatibility
tests across a ruleset bump.

## Vertical slice definition of done

Tracked against §37: playable across Phases 1–3 (partial) through 8, not achieved until Phase 8
completes. See `product_spec.md` §38 for the full checklist.
