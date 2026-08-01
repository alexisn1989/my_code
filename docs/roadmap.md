# MANDATE — Roadmap

Phases match `product_spec.md` / the original brief §38. A phase is not started until the
previous one's acceptance criteria pass and are verified (not just implemented). Section
references (`§n`) point at the numbered sections of the original brief for full requirement detail.

## Phase 0 — Discovery and project foundation — **in progress**

Scope: §1–§6, §39–§40 (process rules), monorepo layout, tooling, docs.

Acceptance criteria:
- [x] Repository inspected, current state documented before any edit.
- [x] `docs/product_spec.md`, `docs/architecture.md`, `docs/adr/0001-*.md` written.
- [ ] Monorepo structure created (`backend/`, `frontend/`, `data/`, `docs/`, `scripts/`).
- [ ] Backend formatting/lint/type/test tooling configured and runnable (`uv sync`, `ruff`,
      `mypy`, `pytest`).
- [ ] `.env.example` present; no secrets committed.
- [ ] CI workflow runs lint + type-check + tests on push.
- [ ] Local development instructions in `README.md`.

## Phase 1 — Pure simulation foundation — **this session, minimal slice**

Scope: §7 (turn structure), §8 (core game state, minimal subset).

Acceptance criteria (this session's cut — see `architecture.md` for what's deferred within Phase 1):
- [ ] Typed `GameState`, `DecisionSet`, `TurnReport` (+ minimal `WorldState`, `CountryState`,
      `PopulationGroupState`, `InstitutionState`, `TreasuryState`).
- [ ] Deterministic seeded RNG (`core/rng.py`), namespaced by `(seed, turn, stream)`.
- [ ] Scenario loader with validation (Pydantic, YAML).
- [ ] Turn resolver with the explicit 15-phase order from §7, phases registered as data.
- [ ] Invariant validation (population non-negative, group shares sum to 1 within tolerance,
      turn/version bounds) run before and after resolution.
- [ ] Headless CLI: create a game, resolve turns, inspect state — no server required.
- [ ] One valid scenario fixture (`data/scenarios/tiny_valid.yaml`).
- [ ] Tests: determinism (canonical JSON diff), turn number advances exactly once, invalid
      decisions never mutate input state, group-share validation, fixture loads.

Remainder of Phase 1 (full domain model coverage of all ~29 state classes in §8, richer invariant
set, immutable snapshot history in-process) is **not** in this session's scope; tracked as follow-up.

## Phase 2 — Economy, budget, and population

Scope: §11 (population simulation), §13 (economy), §14 (public services), §15 (policy system,
12–15 policies for the slice).

Acceptance criteria: revenue/spending/sector/price/employment/debt formulas implemented and
reconciled by tests; central bank with policy rate, inflation response, currency effects, and a
player-facing choice between political control and operational independence; population groups
update incrementally with tracked approval reasons; policies have delayed/ramped effects; property
tests for money reconciliation and bounded metrics.

## Phase 3 — Government and political survival

Scope: §9 (constitutional system), §10 (political capital/action capacity), §12 (parties/
legislature), §19 (coups/revolutions — risk surfacing), §20 (elections — scheduling/polling), §21
(leaders/cabinet).

Acceptance criteria: parliamentary-republic government type fully modeled per §9's composable
dimensions; political capital and administrative capacity constrain actions; legislative
support-score model; institution loyalty/power/competence tracked; coup/unrest risk indicators
visible with named contributing factors; election scheduling and polling with uncertainty; ~20–40
cabinet-relevant characters for the first scenario.

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
