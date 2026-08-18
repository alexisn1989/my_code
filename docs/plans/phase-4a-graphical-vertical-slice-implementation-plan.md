# MANDATE — Phase 4A: Graphical Vertical Slice (Revision 2)

> **PLAN ONLY.** No branch created, no repository file edited, no dependency installed, no
> production code written, no PR opened. Phase 3C is merged (`origin/main` = `96317ba`); its design
> record lives in `docs/adr/0013-government-survival.md` and in git history and is not reproduced
> here. **This is Revision 2**, correcting fourteen binding issues (R1–R14) found in Revision 1's
> review. Corrections are integrated throughout, not appended — every section below reflects the
> corrected design, and a consistency sweep (§26) confirms no section still references a superseded
> assumption.

---

## Context — why this phase exists

Every phase through 3C built a simulation that is **provably correct and completely invisible**. The
engine resolves twelve self-validating reports per turn, hash-chains them, reconciles them against
state, and refuses to lie — but the only way to see any of it is `app/cli.py` (1,524 lines) printing
indented text, or reading canonical JSON by hand. `frontend/src/App.tsx` is an eleven-line
placeholder that says, in its own words, "no gameplay screens exist yet."

Phase 4A closes that gap with a **desktop-first graphical vertical slice**: a player starts a
scenario, reads their country's condition, constructs a legal decision, resolves a turn, understands
what changed and why, reviews prior turns, saves, reloads, and plays to victory or defeat — without
touching the CLI or reading raw JSON.

The phase is successful only if the simulation **feels like a game rather than a database
inspector**. That is the acceptance bar, and §22's external playtest is how it is measured.

**Scope discipline:** Phase 4A exposes existing mechanics. It adds no formula, no mechanic, and no
calibration. The graphical application calls the authoritative Python engine; it never reproduces a
simulation formula in TypeScript.

---

## 1. Merge-gate evidence — all ten gates PASS (verified read-only)

| # | Gate | Evidence | Result |
|---|---|---|---|
| 1 | PR #12 merged | `merged: true`, `merged_by: alexisn1989`, `merged_at 2026-08-18T00:44:30Z` | **PASS** |
| 2 | Both CI checks succeeded | Backend `success` (completed 00:50:40); Frontend `success` (completed 00:42:22); run 32085506968 | **PASS** ⚠ see note |
| 3 | `ae9b554` ancestor of `origin/main` | `git merge-base --is-ancestor` → exit 0 | **PASS** |
| 4 | New `origin/main` merge commit | **`96317ba91ec230fa59d93fbe7048b48bf0d984db`** | **RECORDED** |
| 5 | `origin/main` ruleset/content `0.12.0` | `state.py:983` `RULESET_VERSION = "0.12.0"`; all three scenarios `content_version: "0.12.0"` | **PASS** |
| 6 | `SAVE_FORMAT_VERSION` = 1 | `save_format.py:41` | **PASS** |
| 7 | Phase 3C plan + ADR 0013 present | `docs/plans/phase-3c-government-survival-implementation-plan.md`, `docs/adr/0013-government-survival.md` | **PASS** |
| 8 | Twelve reports + terminal outcomes | `report.py:3329-3381` (all twelve fields); `state.py:769-820` (`OutcomeBucket`, `RemovalReason`, `VictoryReason`, `TerminalOutcomeState`, `PendingLiberalizationState`) | **PASS** |
| 9 | Working tree clean | `git status --short` empty | **PASS** |
| 10 | No Phase 4A branch | No local branch; `git ls-remote --heads origin` name-filtered → none | **PASS** |

⚠ **Disclosed, non-blocking (gate 2).** The owner merged at `00:44:30`, **before** the backend check
finished at `00:50:40`. The backend check subsequently reported `success` against the exact merged
head SHA (`ae9b554`), so `main` is verified green — but the merge did not *wait* for it. Recorded as
a process observation, not a defect in the merged code.

**Additional verified fact:** `git diff ae9b554 origin/main` is empty — `origin/main`'s tree is
byte-identical to the Phase 3C head. Baseline measurements below were therefore taken in the
existing working tree without a checkout, and are exactly equivalent to measuring `main`.

---

## 2. Baseline results — measured, not asserted

### 2.1 Existing gates, unchanged

| Gate | Result |
|---|---|
| `uv sync --locked --group dev` | 45 resolved / 22 audited, no drift |
| `uv build` | sdist + wheel built |
| `uv run ruff format --check .` | **116 files already formatted** |
| `uv run ruff check .` | All checks passed |
| `uv run mypy` | Success, **36 source files** |
| `uv run pytest -q` | **6,061 passed** (confirmed twice, independently) |
| `npm ci` / `typecheck` / `build` / `test` | clean; 1/1 test; built in 620ms; bundle 190.87 kB (60.24 kB gzip) |
| `npm audit --audit-level=low` | 1 high, dev-only — the known **FE-1** `nanoid` advisory (GHSA-2v37-7h3g-55p8) via `vite → postcss`. **Not remediated during planning**, per mandate. |
| `docker compose config --quiet` | exit 0, **no container started** |

### 2.2 Interface-architecture measurements (the load-bearing evidence)

Scenario creation, median of 5:

| Scenario | `load_scenario_file` | `new_game` |
|---|---|---|
| `tiny_valid` | 31.90 ms | 0.46 ms |
| `deficit_demo` | 23.33 ms | 0.40 ms |
| `decree_state` | 24.61 ms | 0.41 ms |

Turn resolution against history depth (`decree_state`, no decisions) — **`advance_game` revalidates
the entire chain, so cost grows with depth**:

| Turn | `advance_game` |
|---|---|
| 1 | 6.12 ms |
| 2 | 7.32 ms |
| 5 | 25.10 ms |
| 10 | 23.79 ms |
| 20 | 51.03 ms |
| 30 | 67.99 ms |
| 40 | **91.08 ms** |

Save size and serialize/validate/load cost:

| Turns | Save size | `dump_save_json` | `load_save_json` | `validate_history` |
|---|---|---|---|---|
| 1 | 36.8 KiB | 0.17 ms | 0.16 ms | 2.69 ms |
| 10 | 298.1 KiB | 1.59 ms | 1.12 ms | 23.62 ms |
| 20 | 588.6 KiB | 3.17 ms | 2.29 ms | 46.87 ms |
| 40 | **1,169.4 KiB** | 5.48 ms | 4.38 ms | **84.39 ms** |

Single-entry payload — what one screen actually needs:

| Quantity | Size |
|---|---|
| Entries in a 40-turn save | 41 |
| One entry `state_json` | **6.8 KiB** |
| One entry `report_json` | **19.6 KiB** |
| Full 40-turn save | 1,169.4 KiB |

### 2.3 What these numbers decide (R14-corrected)

1. **Projections exist for contract safety and stability, not because a browser cannot handle
   1.17 MiB.** A 1.17 MiB payload is trivial for any modern browser to receive and hold — this is
   **not** a size argument. The real reasons the API serves purpose-built projections instead of raw
   `state_json`/`report_json` are: (a) raw engine JSON exposes internal representation — bps
   encodings, digest strings, discriminator literals, scratch-object shapes — that would leak
   implementation structure into the UI and couple screens to internal schema instead of a
   versioned API contract; (b) a projection is independently typed and testable (§14.3), so a schema
   change in the engine cannot silently reshape a screen; (c) the *server* cost of computing and
   revalidating a large save (§2.2's `advance_game`/`validate_history` figures) is real and belongs
   server-side regardless of client bandwidth. **Import/export, if and when it ships (§4.7,
   deferred), may legitimately transfer a complete raw save — that is a different purpose
   (portability) from a different endpoint (rendering), and the two are not in tension.**
2. **The save must live server-side.** `validate_history` at 84 ms and `advance_game` at 91 ms are
   trivial server costs and unnecessary client-side costs to repeat on every read — not because the
   client is incapable, but because the server already holds the authoritative, already-validated
   copy in memory (§4.4/§4.8).
3. **Synchronous request/response is sufficient.** Worst measured turn resolution (91 ms at turn 40)
   plus projection assembly is comfortably inside a 200 ms "click → see result" budget. **No
   WebSocket, streaming, or job queue is justified in 4A.**
4. **Turn cost grows linearly with history.** A 100-turn campaign would resolve at ~230 ms. Still
   acceptable, but §18 sets a budget and §23 records it as the first thing to revisit if campaigns
   lengthen.

---

## 3. Current frontend/backend findings (exact references)

| # | Finding | Location | Consequence for 4A |
|---|---|---|---|
| **F1** | **The React app is a placeholder, not a shell to extend.** `App.tsx` renders a heading and a paragraph saying no gameplay screens exist. Total source: 5 files. | `frontend/src/` | 4A builds the application essentially from zero. |
| **F2** | **The dependency set for a real app is already installed and unused.** `@tanstack/react-query ^5`, `zustand ^5`, `react ^19`, `tailwindcss ^4`, `vitest ^4`, `@testing-library/react ^16`. | `frontend/package.json` | Server-state (React Query) and client-state (Zustand) libraries are already chosen by the repo. **No new runtime dependency is required for the core app.** |
| **F3** | **A MANDATE palette already exists.** `--color-navy-950/900/800`, `--color-parchment-100/200`, `--color-gold-500/600`, `--color-charcoal-700/900`, `--color-accent-red-600`, `--font-display: Georgia serif`, `--font-body: system sans`. `color-scheme: dark`. | `frontend/src/styles/tokens.css` | The art bible (§13) extends this; it does not replace it. |
| **F4** | ⚠ **There is no web framework in the backend. Only a CLI.** No FastAPI/Flask/ASGI module exists anywhere in `app/`. | `backend/app/` | 4A must create the API layer. |
| **F5** | ⚠ **The existing `api` optional-dependency extra is NOT "FastAPI only" — corrected (R5).** It declares `fastapi`, `uvicorn[standard]`, **and** `sqlalchemy`, `alembic`, `psycopg[binary]` (Phase 4's future persistence stack). Installing `--extra api` would pull in three database packages 4A never uses. | `backend/pyproject.toml:12-19` | §4.6 defines a **new, minimal `gui` extra** containing only `fastapi`/`uvicorn`. The `api` extra is left completely untouched, for the real Phase-4-persistence work later. |
| **F6** | ⚠ **CI does not install any optional extra.** The backend job runs `uv sync --locked --group dev`. | `.github/workflows/ci.yml:30` | Gate 4A1 changes this to `uv sync --locked --group dev --extra gui` and regenerates `uv.lock` (F5). |
| **F7** | ⚠ **`app.cli` is outside the mypy gate; a new `app.api` would be too.** `packages = ["app.core", "app.simulation", "app.content"]`, `modules = ["app.saves"]`. | `backend/pyproject.toml` | 4A adds `app.api` to `[tool.mypy] packages`. |
| **F8** | **The engine's public surface is already exactly the operations the UI needs.** `load_scenario_file`, `new_game`, `advance_game`, `validate_history`, `dump_save_json`, `load_save_json`, plus `GameSave.current_state()/.current_turn()/.entry_at(turn)` and `HistoryEntry.state()/.decisions()/.report()`. | `history.py`, `save_format.py`, `scenarios.py` | The API is a thin adapter, not a new abstraction. |
| **F9** | **`resolve_turn`/`advance_game` are provably pure.** `resolver.py:94`: `working = state.model_copy(deep=True)`; docstring: "Never mutates `state`"; proven by a byte-identical canonical-JSON snapshot test. | `resolver.py:65-95` | Crash/failure recovery (§4.8) and preview (§4.7) both lean on this: a failed or speculative call cannot corrupt the authoritative save. |
| **F10** | **A structured error taxonomy already exists**, all deriving from `MandateError`: `DecisionSetError`, `TurnResolutionError`, `StateValidationError`, `ScenarioValidationError`, `SaveFileError`, three `SaveCompatibilityError` subtypes, `HistoryValidationError`, `GameAlreadyConcludedError` (carries `bucket`/`reason`/`turn`), `SnapshotNotFoundError` (carries `turn`/`available_turns`). | `core/errors.py` | Error→HTTP mapping is a table over existing types (§15). |
| **F11** | **30 stable reason IDs already exist** and are already rendered by a shared table. | `cli.py` `REASON_RENDERERS` | The explanation vocabulary (§11) is already complete and stable. |
| **F12** | **Atomic save writing already exists.** `write_save_atomic` — same-directory temp file, `fsync`, `os.replace`, directory `fsync`, temp cleanup on any exception. | `app/saves.py:22-63` | 4A reuses this verbatim for every write in §4.8's sequence. |
| **F13** | **Postgres compose file exists but nothing uses it.** | `docker-compose.yml:1-4` | Stays unused in 4A. |
| **F14** | **The roadmap sequences this differently than the mandate.** Roadmap Phase 4 = "Persistence and API"; Phase 5 = "Playable frontend". | `docs/roadmap.md` | Disclosed deliberate resequencing (§24); the roadmap must be updated as part of 4A's documentation gate. |
| **F15** *(new)* | **No single high-level pure vote-scoring function exists — confirmed by inspection, not assumed.** `phases.py:953-1040` composes `resolve_bloc_support` → `apportion_supporting_seats` → `required_yes_seats`/`chamber_carries` **inline** inside `_validate_and_reserve_actions`, mixed with `PhaseContext` scratch-object construction; `phases.py:620-670` does the identical thing for `resolve_amendment_support`/`required_amendment_yes_seats`. Neither is factored into a reusable function. | `phases.py:953-1040`, `620-670` | Drives §10.3's design (R6): preview composes the same primitives phases.py uses, with mandatory parity tests as the safety net — not a claimed-but-nonexistent shared function. |

---

## 4. Recommended application architecture

### 4.1 One sentence

**A local FastAPI process, bound to loopback only, holds one authoritative `GameSave` behind a
single mutation lock, serves purpose-built JSON projections identified by an opaque revision token
to a Vite/React SPA, and persists every mutation to a server-managed save store before ever
reporting success.**

### 4.2 The layers

```
┌──────────────────────────────────────────────────────────────┐
│  React SPA (Vite dev server / static build served by FastAPI)│
│  • React Query  → all server state, keyed by revision token  │
│  • Zustand      → decision-draft only (never game state)     │
│  • src/format/  → the ONLY place display arithmetic may live │
│  • Renders ONLY fields the API sent. No formulas.            │
└───────────────────────────┬──────────────────────────────────┘
                            │  JSON over 127.0.0.1 (same-origin via Vite proxy in dev;
                            │  single origin in playtest builds — see §4.9)
┌───────────────────────────▼──────────────────────────────────┐
│  app/api/  (NEW — the only new backend package)               │
│  • main.py          app factory, static SPA mount, Host/     │
│                      Origin validation middleware (§4.9)      │
│  • routes.py         thin HTTP verbs                          │
│  • session.py        the ONE in-memory GameSession: current  │
│                       GameSave + asyncio.Lock + revision      │
│                       comparison + write-then-swap (§4.8)     │
│  • save_registry.py  save_id validation, safe path resolution,│
│                       listing metadata index (§4.5)            │
│  • projections.py    DashboardProjection, TurnResultProjection │
│  • preview.py         pure vote-preview composition (§4.7)     │
│  • errors.py          MandateError → problem+json              │
│  NO simulation logic. Imports the engine; never reimplements. │
└───────────────────────────┬──────────────────────────────────┘
┌───────────────────────────▼──────────────────────────────────┐
│  FROZEN ENGINE (untouched by 4A)                              │
│  history.new_game / advance_game / validate_history            │
│  save_format.dump_save_json / load_save_json                   │
│  content.scenarios.load_scenario_file                          │
│  app.saves.write_save_atomic / read_save_file                  │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Why a local HTTP API is the smallest safe boundary

- **It reuses the engine literally** (F8). Any divergence between GUI and CLI behaviour becomes a
  test failure, not a silent fork.
- **It is already the repo's committed direction** (corrected per R5/F5: FastAPI/uvicorn, not the
  database stack, is the pre-committed piece — `pyproject.toml`'s own top-level description already
  says "simulation engine **and API**").
- **It preserves atomicity by construction** (F12, §4.8): the server owns the file and writes it
  atomically before ever swapping its in-memory pointer; a browser crash cannot corrupt anything,
  because the browser never held the file.
- **It is testable at both ends**: FastAPI's `TestClient` gives contract tests in the existing
  pytest gate; fixture-based component tests give the frontend gate confidence without needing a
  running server.

### 4.4 Session model — one authoritative session, explicitly

**v1 has exactly one active game session per running server process** — a module-level singleton
(`GameSession`), never per-browser-cookie, per-tab, or per-user. Multiple browser tabs against the
same running server share the *same* session and the *same* save; §4.8 defines exactly what happens
when two tabs act concurrently. Multiple **simultaneous, independent** games (two different save
files open for editing at once) are out of scope for 4A — the player loads one save at a time,
exactly like the CLI's `--state`/`--out` model. This is a named, deliberate simplification (§24), not
an oversight.

### 4.5 Save identity — IDs, never paths (R3)

**A fixed, server-managed save root**, e.g. `~/.mandate/saves/` (created on first run if absent;
overridable via `--save-root` on the launch command for testing — see §4.9). Nothing under `app/api/`
ever accepts a client-supplied filesystem path.

- **Save ID:** a server-generated UUID4 (`550e8400-e29b-41d4-a716-446655440000`). The on-disk file is
  always exactly `{save_root}/{save_id}.json` — an engine save, written and read verbatim by the
  existing `write_save_atomic`/`read_save_file`/`dump_save_json`/`load_save_json` (F12, F8), which
  are **completely untouched**.
- **Display name and listing metadata** (`display_name`, `scenario_id`, `created_at`, `updated_at`,
  `current_turn`, `terminal_outcome_summary`) live in a small **API-layer-only sidecar index**,
  `{save_root}/index.json`, maintained by `save_registry.py`. This index is convenience metadata,
  never part of the engine's save format, never hash-covered, never read by the engine.
- **Validation, before any filesystem call:** an incoming `save_id` is checked against a strict
  UUID4 regex. Anything else — `..`, an absolute path, a path separator, a null byte, a symlink name
  — **fails the regex and is rejected with 400 before `Path()` is ever constructed.** Because the ID
  space contains no path syntax at all, traversal is prevented by construction, not by a blocklist.
  The resolved path is additionally asserted to have `save_root` as its real, resolved parent
  (`Path.resolve()` compared by prefix) as a second, redundant layer, and the target is asserted to
  **not** be a symlink before it is opened. §17's T-security tests exercise all of these.
- **Display-name validation:** 1–80 characters after stripping, rejecting control characters. Stored
  only in `index.json`; **never** used to construct a filesystem path.

### 4.6 The endpoint set

| Operation | Endpoint | Engine call | Notes |
|---|---|---|---|
| List scenarios | `GET /api/scenarios` | scan `data/scenarios/*.yaml`, `load_scenario_file` for metadata | name, id, government form, election interval, one-line pitch |
| New game | `POST /api/game/new` `{scenario_id, seed?}` | `load_scenario_file` → `new_game` → allocate `save_id` → `dump_save_json` → `write_save_atomic` (under the session lock, §4.8) | returns `DashboardProjection` |
| Dashboard | `GET /api/game/state` | `session.current_save.current_state()` → projection | `DashboardProjection`, embeds `revision` |
| Legal-move envelope | `GET /api/game/decision-options` | reads current state + constitution | what the UI needs to build a legal decision (§10) |
| Preview a vote | `POST /api/game/preview` `{decisions}` | pure vote functions only (§4.7) — **never** the session lock, never a write | read-only; always reflects the *current* session state at call time |
| Resolve | `POST /api/game/resolve` `{revision, decisions}` | revision check → `DecisionSet(expected_turn, expected_state_version, decisions)` → `advance_game` → write → swap (§4.8) | returns `{turnResult: TurnResultProjection, dashboard: DashboardProjection}` (§4.10) |
| History list | `GET /api/game/history` | `save.entries` → turn index | tiny: turn numbers + one-line outcome each |
| History detail | `GET /api/game/history/{turn}` | `save.entry_at(turn).report()` → **the same projection functions `/resolve` uses** | returns `{turnResult: TurnResultProjection, dashboardAsOfTurn: DashboardProjection}` |
| List saves | `GET /api/saves` | `save_registry` index scan | safe metadata only, no paths (§4.5) |
| Save As | `POST /api/game/save-as` `{display_name}` | writes a **new**, separate `save_id` as a checkpoint of current state; the session's own autosave `save_id` is unchanged | a branch/checkpoint operation, not a rename — see §15.3 for the precise semantics |
| Load | `POST /api/game/load` `{save_id}` | `read_save_file` → `load_save_json` → `validate_history` → replace session (§4.8) | integrity result surfaced to the player |

### 4.7 Preview — composed from real primitives, proven by parity (R6)

Per F15, no single high-level "score this vote" function exists to call. `app/api/preview.py`
therefore **composes the same three engine primitives `phases.py` itself uses, in the same order**:
`resolve_bloc_support`/`resolve_amendment_support` per seated bloc → `apportion_supporting_seats` →
`required_yes_seats`/`required_amendment_yes_seats`. It is read-only over the current opening state
and:

- **Never calls `advance_game`/`resolve_turn`.**
- **Never touches an RNG stream** — enforced by a source scan (T-preview-rng, §17) asserting
  `preview.py` imports no symbol from `core.rng`, so the seeded channels (election swing,
  coup/unrest/impeachment) are never previewed. Their uncertainty is the game.
- **Never mutates session state, the on-disk save, or history** — enforced by a test that snapshots
  `session.current_save` (identity and byte-serialized content) before and after every preview call.
- **Is deterministic and byte-stable** — the same draft against the same opening state returns
  byte-identical output on repeated calls, proven directly (not merely implied by "it's pure").

**Because this composition is unavoidable rather than reused from a shared function (F15), it is
proven correct by an explicit, mandatory parity suite** (`test_api_preview_parity.py`, §17):
preview's projected tally is compared against the real `ConstitutionalAmendmentReport`/
`LegislativeReport` chamber rows produced by *actually resolving* the identical decision through
`resolve_turn`, across:

- all three scenarios,
- both proposal kinds (budget and constitutional amendment),
- both chamber shapes (`tiny_valid` bicameral, `deficit_demo`/`decree_state` unicameral),
- the exact passed/failed boundary from the real campaign (67/100-vs-67 passes, 66/100-vs-67 fails),
- and a spread of influence allocations, including zero.

**Considered and rejected:** extracting a new shared pure function in `simulation/legislative_voting.py`
that both `phases.py` and `preview.py` would call. This would remove the duplication, but it touches
`app/simulation/` — which §4 of the mandate explicitly forbids redesigning ("Legislative voting" is
named in the scope freeze) and which §20 pins as a scope-breach trigger for 4A. Rejected in favor of
the composition-plus-parity-tests approach R6 itself anticipates as the fallback.

### 4.8 Concurrency and crash recovery (R1 + R4)

**Revision token, not server-stamped values.** Every projection (`DashboardProjection`,
`TurnResultProjection`) embeds `revision: str`, an opaque token formatted `"{turn}.{state_version}"`
(documented to the client as *opaque — echo verbatim, never parse or construct one*). The client
carries the token it most recently received and sends it back as the `revision` field on
`POST /api/game/resolve`. **The server does not stamp `expected_turn`/`expected_state_version` from
its own current save.** It parses the *client's* echoed revision into the two integers and passes
those, unchanged, as `DecisionSet.expected_turn`/`.expected_state_version` — so the engine's own
staleness check (`resolver.py:50-62`, `DecisionSetError`) does real, load-bearing work instead of
being trivially satisfied by construction.

**The mutation lock.** `GameSession` holds one `asyncio.Lock`. Every session-mutating endpoint
(`/new`, `/load`, `/resolve`, `/save-as`) acquires it; a concurrent second request that cannot
acquire the lock **immediately** returns `409 {"type": "resolution_in_progress"}` — it is never
silently queued.

**The `/resolve` sequence, precisely:**

1. Acquire `session.lock` (else 409 `resolution_in_progress`).
2. Parse the client's `revision` into `(claimed_turn, claimed_version)`.
3. **Friendly fast-path check** (redundant with, never a substitute for, step 5): compare
   `(claimed_turn, claimed_version)` against `session.current_save.current_state()`'s live values,
   read fresh at this instant (not cached from request arrival). Mismatch → release lock, return
   `409 {"type": "stale_revision", extra: {expected: "...", actual: "..."}}`, draft preserved
   client-side.
4. Build `DecisionSet(expected_turn=claimed_turn, expected_state_version=claimed_version, decisions=...)`
   and call `advance_game(session.current_save, decision_set)` — pure; returns a *new* `GameSave`
   without mutating the old one (F9). Any `DecisionSetError`/`TurnResolutionError` here is the
   engine's own authoritative rejection (step 3 is only ever a friendlier, earlier version of the
   same fact) → release lock, map via §15's error table, `session.current_save` untouched.
5. `dump_save_json(new_save)` → `write_save_atomic(...)`. **If this raises, release the lock and
   return 500 — `session.current_save` is still the OLD save, both in memory and on disk.**
6. **Only after the write succeeds**, swap: `session.current_save = new_save`.
7. Release the lock, build `{turnResult, dashboard}` from `new_save`, respond 200.

**Two-tab stale-draft scenario** (the literal case §17's tests prove): Tab A and Tab B both load the
dashboard and both receive `revision="10.10"`. Tab B resolves first: lock free, claimed matches
actual, resolves, writes, swaps to turn 11, responds with `revision="11.11"`. Tab A, still showing
its stale draft, submits with `revision="10.10"`: lock is free again (B released it), step 3 reads
the *now-current* state (turn 11) and finds a mismatch → `409 stale_revision`. Tab A's draft is
preserved; the UI prompts a refresh. **No decision is ever silently applied against a turn the
player did not see.**

**Simultaneous-resolve scenario:** two requests race to acquire the lock at nearly the same instant.
Whichever wins runs the full sequence above; the loser blocks briefly then either (a) still fails to
acquire within its own request lifetime and gets `409 resolution_in_progress`, or (b) acquires after
the winner releases and then hits the *now-stale* revision check in step 3 — either way, **no
double-resolve, no lost update, no interleaved write** is possible, because step 6's swap is the only
place `session.current_save` changes and it happens strictly inside the held lock.

**Startup recovery.** Session state is process memory; a server restart loses it — **by design**,
because every successful mutation is already disk-durable *before* it is ever reflected in a
response (step 5 precedes step 6/7). There is no "torn" state to recover: the on-disk save is always
exactly consistent with the last response the client actually received. After a restart,
`GET /api/game/state` with no session loaded returns a distinct `404 {"type": "no_active_session"}`
rather than crashing; the client falls back to the Title/Load screen, and the player explicitly
`POST /api/game/load {save_id}`s to resume. The client may remember the last `save_id` in
`localStorage` and offer a one-click "Resume where you left off" — a client-side convenience, not a
server auto-behaviour.

### 4.9 Local security boundary (R10)

- **Bind loopback only.** `uvicorn` is started against `127.0.0.1`, never `0.0.0.0`.
- **Development:** the Vite dev server proxies `/api/*` to the FastAPI process, so browser requests
  are same-origin from the browser's own perspective. **No CORS middleware is enabled in this mode**
  — there is nothing cross-origin to allow.
- **Playtest/single-process mode:** FastAPI itself serves the built SPA — `app.mount("/", StaticFiles(
  directory="frontend/dist", html=True))` plus a catch-all fallback to `index.html` for client-side
  routes — so there is exactly **one origin, one port, one process** to run (this doubles as §4.11's
  one-command story).
- **Origin/Host validation.** A small middleware rejects any state-changing request (`POST`) whose
  `Origin` header (when present) does not match the server's own known local origin, and rejects any
  request whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` — a defence against
  DNS-rebinding-style attacks even though the server is loopback-only.
- **Mutations accept only `application/json`.** Any other `Content-Type` on a mutating endpoint is
  rejected with 415, before the body is parsed.
- **Wildcard CORS is forbidden.** No `allow_origins=["*"]` anywhere in `main.py`, enforced by a grep-
  based lint test.
- **No arbitrary filesystem access anywhere in the API**, by construction: §4.5's save-ID scheme is
  the *only* filesystem-touching input, and it never accepts a path.
- **T-security tests** (§17) exercise: `../../etc/passwd`-shaped `save_id`, an absolute-path
  `save_id`, a `save_id` containing `/` or `\`, a symlink placed inside `save_root` pointing outside
  it, a request bearing a hostile `Origin`, and a mutation sent as `text/plain`. Every case is
  rejected with a clear 4xx and produces **no** filesystem or session side effect.

### 4.10 Live/history parity — one shared projection type (R7)

**`TurnResultProjection` is defined exactly once** (`app/api/projections.py`) and is the *only*
type that ever describes "what happened on turn N and why." It carries: `revision`, `turn`,
`outcome_headline` (layer 1), `drivers: DriverItem[]` (layer 2 — each `{reason_id, label, params}`
from the 30-ID vocabulary), `ledger: LedgerEntry[]`, `unchanged: string[]`, `next_turn_pointers`
(`next_election_turn`, `pending_liberalization`, `transition_pressure_bps`), `trace: TraceField[]`
(layer 3), and `terminal: TerminalSummary | null`.

- `POST /api/game/resolve` returns `{"turnResult": TurnResultProjection, "dashboard": DashboardProjection}`
  for the turn just resolved.
- `GET /api/game/history/{turn}` returns `{"turnResult": TurnResultProjection, "dashboardAsOfTurn": DashboardProjection}`
  for that historical turn — **built by calling the identical projection function** over the
  identical stored `TurnReport` (via `HistoryEntry.report()`), never a second, parallel
  implementation.
- `GET /api/game/state` is **deliberately separate** — it returns a bare `DashboardProjection`
  (current country condition: treasury, legitimacy, legislature composition, survival risk, etc.),
  never a narrative about what changed. Conflating the two was Revision 1's defect; §17's T-parity
  test now compares the two `turnResult` objects directly (`resolve(turn=N).turnResult ==
  history(N).turnResult`), not two unrelated complete endpoint payloads.

### 4.11 One-command startup (R11)

**Operator (one-time, per playtest machine):** `npm run build` in `frontend/` (produces
`frontend/dist/`), then `uv sync --locked --group dev --extra gui` in `backend/`.

**Operator (each session):** `uv run mandate-gui` — a new `[project.scripts]` entry point
(`mandate-gui = "app.api.main:run"`) that starts `uvicorn` on `127.0.0.1:8420` by default, serving
the built SPA per §4.9. A `--port` flag overrides the default.

**The five external testers receive an already-open browser tab at `http://127.0.0.1:8420`** — they
never run a command themselves. This satisfies the mandate's "already-running app or one launch
command" without overstating automation: the *operator's* one-time build step and the *tester's*
zero-command experience are named separately and honestly.

- **Port collision:** if 8420 is already bound, startup **fails fast** with a clear error naming the
  port and suggesting `--port <n>`. No silent auto-incrementing port search — that could surprise an
  operator mid-setup and produce two undiscoverable, conflicting server instances.
- **Clean shutdown:** standard `SIGINT`/`SIGTERM` triggers `uvicorn`'s graceful shutdown. No
  background threads, no lock files. The in-memory session is intentionally lost (§4.8); only saves
  persist.
- **Desktop packaging** (installer, tray icon, auto-launching Node+Python together) remains deferred
  to 4B (§24) — the chosen architecture is compatible with it later, but nothing in 4A depends on it.

### 4.12 Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Pyodide / WASM — run the engine in the browser** | Would ship a Python runtime plus the whole engine to the client for a single-player desktop app, and makes "the frontend never computes simulation results" unverifiable by construction. Rejected on the mandate's own "must call the authoritative Python engine" rule. |
| **Reimplement projections/formulas in TypeScript** | Explicitly forbidden by §4 of the mandate. Rejected outright. |
| **Electron / Tauri desktop shell now** | Real packaging value, explicitly deferrable per the mandate. Adopting it in 4A adds a build toolchain and a signing story before a single screen exists. Deferred to 4B. |
| **CLI subprocess invoked per action (no HTTP)** | Every action would pay full process start + `load_save_json` + `validate_history`; CLI output is *formatted text*, not data, requiring fragile re-parsing; file paths would become the API, reintroducing exactly the path-safety problem §4.5 exists to avoid. Rejected. |
| **A long-lived stdio/JSON-RPC child process instead of HTTP** | Reinvents request framing, error propagation, and concurrency FastAPI already provides, for no compensating benefit at this scale. |
| **Static SPA reading save JSON directly (no server)** | Cannot execute the engine at all. Immediately disqualifying. |
| **WebSockets / streaming turn resolution** | Unjustified: worst measured resolution is 91 ms (§2.2). Adds reconnection/ordering complexity for no perceptible gain. |
| **A new shared pure vote-scoring function in `app/simulation/`** | Would remove preview's composition duplication, but touches the simulation package the phase's own scope freeze forbids redesigning (§4.7). Rejected in favor of composition + mandatory parity tests. |
| **Server-side stamping of `expected_turn`/`expected_state_version` from the current save** | Defeats the engine's staleness check by construction — any decision, however stale, would always "match" whatever the server currently holds. This was Revision 1's defect; corrected by the revision-token design (§4.8, R1). |
| **Filesystem paths as the save identifier** | A network-facing (even loopback) server accepting client-supplied paths is a path-traversal vulnerability waiting to happen. Corrected by the save-ID scheme (§4.5, R3). |

---

## 5. (merged into §4.12 above)

---

## 6. Vertical-slice scenario choice

### 6.1 Strategy — one polished, three loadable

**Adopt the mandate's default: one polished showcase scenario, smoke support for all three.**
Repository evidence supports rather than contradicts it — all three scenarios already load through
one code path (`load_scenario_file`) and already resolve through one resolver, so "smoke support"
costs a dropdown entry and a test, while polish (tutorial framing, tuned copy, map identity) is
genuinely per-scenario work.

### 6.2 Showcase: **`decree_state`**

| Criterion | `tiny_valid` | `deficit_demo` | **`decree_state`** |
|---|---|---|---|
| Budget passes unaided? | **Yes** (0 PC in both chambers) — no tension | No: 47/100, needs 162 PC | No: 45/100, needs 283 PC |
| Genuine route choice (legislate **vs** decree)? | No (`emergency_only`, unreachable) | No (`emergency_only`) | **Yes — unlimited decree authority.** The only scenario offering it |
| Constitutional amendment path? | Amendable, but no signature campaign | No | **Yes — the calibrated 85/118/300 campaign** |
| Reachable victory? | No — concludes `TERM_LIMIT_EXIT` (defeat) at turn 32 | No | **Yes — `peaceful_liberalization_completed`, the game's only VICTORY** |
| Coup/unrest visible? | Only when edited | Low | **Yes — coup risk 0.52% → 10.52% after the amendment** |
| Time to a decisive moment | 16 turns to first election | ~40 turns | **11 turns** |
| Chambers | Bicameral (100 + 60) | Unicameral | Unicameral (100) |
| Visual story | Stable democracy stays stable | Fiscal strain | **Monarchy → constitutional republic** |

**Chosen: `decree_state`.** Justification, tied to the acceptance bar ("feels like a game"):

1. **It is the only scenario with a real decision every single turn.** Legislate for 283 PC or
   decree for 250 PC is a genuine, priced trade-off with different political consequences.
2. **It contains the only victory in the game.** A vertical slice whose best outcome is *defeat*
   would be a poor advertisement for the whole project.
3. **Its signature campaign is short and knife-edged.** 85 → 118 → 300 PC across three turns,
   passing at exactly **67/100 against a required 67**, with 299 PC failing at 66/100.
4. **It has the strongest visual narrative**: a hereditary monarchy with unlimited decree power
   transforming into a presidential republic with scheduled elections.
5. **Danger is visible.** Transition pressure spikes to 100% and decays 8,334 → 2,792 across turns
   4–10 while coup risk sits at 10.52% — real, surfaceable tension.

**Honest caveat, deliberately kept:** at the scenario's authored seed 77 the turn-11 election is
**LOST** (baseline 5,091, swing −269, final 4,822 → `electoral_defeat`). This is not a flaw to
engineer around — losing a campaign you invested 503 PC in is exactly the "one more turn" pressure
§22's fun gate measures. **The new-game screen exposes the optional seed field** (the CLI already
supports `--seed`), so a player can replay the same campaign under different uncertainty. Seed 0
yields the victory path (swing +719, final 5,810). **No scenario file is recalibrated to simplify
the interface.**

### 6.3 Rejected scenario strategies

| Strategy | Why rejected |
|---|---|
| **All three polished equally** | Triples the per-scenario copy, tutorial, and map-identity work for a slice whose purpose is to prove the loop is fun once. |
| **One scenario only, other two hidden** | Loses a nearly-free correctness signal: "all three load and resolve through the GUI" costs one dropdown and one test. Also hides `tiny_valid`'s bicameral shape, the only place the two-chamber UI is exercised. |

---

## 7. User journey (the ten required capabilities)

| # | Capability | Where it happens | Proof it is met |
|---|---|---|---|
| 1 | Start a scenario | Title → **New Campaign** (scenario cards, optional seed) | `POST /api/game/new` |
| 2 | Understand immediate condition | **National Dashboard** — header + situation view + alerts + goal card | `GET /api/game/state` |
| 3 | Review government/economy/political constraints | Four panels: Government, Economy & Budget, Legislature, Constitution + Relationships | same projection, tabs |
| 4 | Construct a legal decision | **Decision Workspace** with live affordability + route availability + tooltips | `GET /api/game/decision-options`, `POST /api/game/preview` |
| 5 | Resolve a turn | **Resolve Turn** confirmation → result | `POST /api/game/resolve` |
| 6 | Understand what changed and why | **Turn Result** with three-layer disclosure | `TurnResultProjection` + 30 reason IDs |
| 7 | Review prior turns | **History timeline** → historical turn detail | `GET /api/game/history[/{turn}]`, same `TurnResultProjection` |
| 8 | Save and reload | Autosave every turn; explicit Save As / Load, save-ID based | `write_save_atomic`, `load_save_json` + `validate_history` |
| 9 | Continue to victory or defeat | Terminal screen; further resolution refused | `GameAlreadyConcludedError` → 409 |
| 10 | No CLI, no raw JSON | Every above path is graphical, with contextual onboarding | §21 manual walkthrough; §22 unassisted playtest |

---

## 8. Information architecture

**Design rule: the player must never need to inspect twelve raw reports.** Twelve reports collapse
into five player-facing concerns — *Money, Legitimacy, Legislature, Constitution, Survival* — and one
narrative surface (the turn result).

### 8.1 Disclosure tiers

**Always visible (persistent chrome):**
- Country name, government form
- Turn number, and next election (turn N, or "none scheduled")
- Treasury cash, and the turn's balance direction
- Political capital: `current / capacity`, and this turn's committed amount
- Legitimacy %
- **Survival banner** — only when a risk is non-trivial or a terminal outcome is pending
- Primary action: **Resolve Turn**

**One click away (main tabs):** Dashboard · Government · Economy · Legislature · Constitution ·
Relationships · Decisions · History

**Only when relevant (conditional):**
- Amendment panel — only where the constitution is amendable and a legislature or decree route exists
- Decree route control — only when `decree_authority` permits it (hidden, not disabled-with-mystery)
- Election panel — only when `next_election_turn` is set
- Pending-liberalization badge — only when set
- Coup/unrest/impeachment detail — only when eligible
- Second chamber column — only when bicameral (`tiny_valid`)

**Only in detailed inspection (third layer, R12/R9 — dev-build only for the raw viewer):**
- Per-sector production, labor allocation, resource depletion tables
- Tax-base derivation chain
- Per-bloc four-component relationship arithmetic
- Exact bps values, digests, `entry_hash`
- **Raw report JSON viewer** — a deliberate escape hatch, gated behind `import.meta.env.DEV`.
  **Never present in the built playtest artifact** — corrected per R12; a player-facing "read the
  raw report" capability would undercut the entire premise of purpose-built projections.

### 8.2 Onboarding surfaces (R8, new)

Kept deliberately minimal — **no forced tutorial campaign, no gated tutorial turns**:

- **Contextual tooltips** on key controls (capital meter, decree-vs-legislate toggle, seat threshold
  line, transition-pressure indicator) — hover/focus-triggered, dismissible, never blocking.
- **A plain-language goal card** on the dashboard, rendered from the *same* alert-ranking data §8.1
  already defines (terminal pending > survival risk > election due > amendment opportunity > fiscal
  deficit) as one current-priority sentence. **Not** a fabricated narrative — every word traces to a
  real projection field.
- **A static glossary panel** (political capital, legitimacy, decree authority, transition pressure,
  liberalization, etc.) — hand-written copy, not derived from simulation, cheap and safe.
- **An optional, dismissible "How to govern" intro** — 3–4 slides on first launch explaining the
  loop (read condition → decide → resolve → learn why → repeat). Skippable at any point, never
  reappears once dismissed (persisted in `localStorage`).

§22's playtest explicitly tests whether these are *sufficient* — testers get the app and these
surfaces, and nothing else. If they are not enough, gate 4A5 iterates copy and tooltip placement,
never adds new systems.

### 8.3 Screen inventory

| Screen | Purpose | Notes |
|---|---|---|
| Title / Load | Start or resume | Scenario cards; recent saves (by save ID, §4.5); integrity status shown on load |
| National Dashboard | The default view; condition at a glance + goal card | Map anchor + alerts + five concern cards |
| Government | Executive, institutions, survival risk | Loyalty/power/competence/corruption per institution |
| Economy & Budget | Treasury, revenue, spending, sectors | Tier-3 tables behind summary |
| Legislature | Chambers, parties, blocs, seats, relationships | Per chamber; seat bar is the hero element |
| Constitution | Nine axes, amendability, digest | Amendment entry point |
| Relationships | Per-bloc standing vs authored baseline | Deviation, not just level |
| Decision Workspace | Build and validate the turn's decisions | §10 |
| Turn Result | What happened and why | §11 |
| History | Timeline of turns; open any prior turn | Same `TurnResultProjection` as live (§4.10) |
| Victory / Defeat | Terminal outcome + campaign retrospective | Blocks further resolution |
| Glossary | Static reference | §8.2 |

---

## 9. Screen-by-screen specification (abbreviated to decisions, not pixels)

**Title / New Campaign.** Three scenario cards (showcase first, visually primary). Each shows
government form, starting legitimacy, election interval or "no election scheduled", and a one-line
pitch. Optional advanced disclosure: seed override (default = scenario's authored seed). Load panel
lists recent saves by `save_id`/`display_name` from `GET /api/saves`, with integrity state; a save
failing `validate_history` is listed but **not loadable**, with the specific problem shown. First
launch offers the dismissible "How to govern" intro (§8.2).

**National Dashboard.** Persistent header (§8.1). Goal card (§8.2). Centre: the national map (§12)
as visual anchor. Right rail: alerts, ranked. Below: five concern cards, each a headline number, a
turn-over-turn delta with direction, and a link to its tab.

**Legislature.** Per chamber: a seat bar segmented by party, sorted by seats; each bloc row shows
seats, discipline, current relationship, and its authored baseline as a ghost marker. Where a
proposal was voted, supporting seats vs required is drawn as a threshold line — the 67/100-against-67
moment must be legible at a glance.

**Constitution.** Nine axes as labelled rows with plain-language values. Amendable axes are marked.
Shows `amendment_difficulty` and the resulting seat threshold. Entry point to the amendment builder.

**Turn Result.** §11.

**Victory / Defeat.** Full-bleed terminal screen stating bucket and reason in plain language, the
turn it occurred, and a campaign retrospective. Offers New Campaign / Review History only — never
"resolve another turn."

**Glossary.** Static reference panel, reachable from the persistent chrome, not a modal that blocks
the game.

---

## 10. Decision-control mapping

Every currently supported decision, mapped to controls. **Every range below is the engine's real
constraint, cited.**

| Decision | Control | Real constraint | Source |
|---|---|---|---|
| **No action** | Default. "Resolve Turn" with an empty `DecisionSet` is always legal | `decisions: ()` | `decisions.py` |
| **Budget proposal** | Three tax sliders + seven spending fields | Rates `StrictBps` 0–10,000; must set ≥1 target; no duplicate category | `BudgetDecision._require_at_least_one_target`, `_reject_duplicate_spending_categories` |
| **Legislative influence** | Per-bloc capital steppers on the budget | `political_capital > 0`; no duplicate `(party_id, bloc_id)`; canonical identity order | `InfluenceAllocation`, `_reject_duplicate_influence_targets`, `_influence_is_in_canonical_identity_order` |
| **Decree route** | Segmented control: Legislative / Decree | Decree shown only where the constitution grants it; flat **250 PC** | `ProposalRoute`, `DECREE_POLITICAL_CAPITAL_COST = 250` |
| **Bloc relationship investment** | Per-bloc capital steppers (separate panel) | **1–200 PC per bloc per turn**; no duplicate targets; canonical order | `RELATIONSHIP_INVESTMENT_CAP = 200` |
| **Constitutional amendment** | Five axis pickers | Each target must *change* its value; canonical alphabetical axis order; final constitution must satisfy C1–C10 | `ConstitutionalAxisTarget` union; `_targets_are_in_canonical_axis_order`; `first_constitutional_violation` |
| **Amendment influence** | Per-bloc capital steppers on the amendment | Same as legislative influence; decree route costs flat **400 PC** | `CONSTITUTIONAL_AMENDMENT_DECREE_COST = 400` |

### 10.1 Cross-cutting UI rules

- **Affordability.** A persistent meter: `committed / opening capital`, shown as an error state
  before submission — but the backend still rejects it authoritatively.
- **Mutual exclusion.** Budget and amendment are one policy proposal per turn
  (`_at_most_one_policy_proposal`). The UI presents them as two tabs of one "Policy proposal" slot,
  so the exclusion is structural in the interface. Relationship investment is a separate,
  non-exclusive slot.
- **Canonical ordering — client-constructed, never server-normalized (R2, corrected).**
  **Revision 1's design was wrong and is withdrawn: the API layer does NOT sort decisions or
  allocations before validation.** The engine's own contract is *reject, not normalize*
  (`_decisions_are_in_canonical_kind_order`, `_influence_is_in_canonical_identity_order`,
  `_targets_are_in_canonical_axis_order` all raise on noncanonical order rather than reordering), and
  that contract is preserved end to end. Instead, **the graphical decision builder assembles its
  payload in canonical order by construction** — a single client-side `buildDecisionSet()` helper is
  the *only* place a `DecisionSet` payload is assembled, and it always emits kind-sorted decisions
  with identity-sorted allocations and axis-sorted amendment targets, because that is simply the
  order it iterates its own internal draft structure in. A malformed payload sent directly to the API
  (bypassing the UI entirely — the case T-reject-not-normalize exercises) still receives a clean
  `422` from the engine's own validators, exactly as today. **No server-side reordering exists
  anywhere in the stack.**
- **Turn / state-version — via the revision token, never server-authored.** Per §4.8/R1, the client
  echoes the exact `revision` it received; the server never substitutes its own current values.
- **Confirmation.** "Resolve Turn" opens a summary: every decision in plain language, total capital
  committed, opening capital, and route. Confirm is a distinct second action.
- **Validation errors.** §15's mapping. Field-level errors attach to the control that produced them;
  set-level errors (mutual exclusion, affordability, stale revision) attach to the workspace header.
- **Failed votes still cost.** Capital committed to a *failed* proposal is consumed. The result
  screen states it explicitly — "Budget blocked. 283 political capital was committed and is spent."
  — backed by `PoliticalCapitalReport`'s ledger rows.

### 10.2 The frontend may help; the backend decides

The UI constructs a canonically-ordered, plausibly valid decision and can pre-empt obvious errors
(range, duplicates, affordability). It is never the authority. Every submission is validated by
`DecisionSet.model_validate` and then by the resolver, and §17's T-reject-not-normalize pins a test
that a deliberately invalid/noncanonical decision constructed *outside* the UI is still rejected with
422, never silently reordered.

### 10.3 Preview — legible without leaking

`POST /api/game/preview` returns the projected chamber tally for the currently drafted proposal,
computed exactly as specified in §4.7 (composition of the same primitives `phases.py` uses, proven
correct by the mandatory parity suite, never touching an RNG stream). This is what makes the 67/100
moment *decidable* rather than a coin flip, without ever previewing the seeded channels whose
uncertainty is the game.

---

## 11. Explanation and progressive disclosure

Every important result answers five questions, all from **stored** report fields and the **30 stable
reason IDs** (F11), assembled into the single `TurnResultProjection` type (§4.10). Nothing is
re-derived client-side.

- **What happened?** → outcome enum, rendered in plain language
- **Why?** → the reason IDs emitted that turn, with their stored params
- **What did my decision contribute?** → the ledger: what was committed, to whom, and to what effect
- **What did *not* change?** → explicit "unchanged" statements
- **What next?** → forward-looking state: next election turn, pending liberalization, decaying pressure

### 11.1 Three layers

1. **Outcome** — one sentence, one colour state, one number.
2. **Drivers** — 2–5 bullets naming the causes, each from a reason ID.
3. **Trace** — exact bps/currency values, thresholds, digests, and the report fields they came from.

### 11.2 Worked examples

| Situation | Layer 1 | Layer 2 | Layer 3 |
|---|---|---|---|
| **Budget passed** | "Budget enacted. Personal income tax rises to 25%." | supporting vs required seats; which blocs were bought and for how much | per-bloc `BlocVoteReport` chain: baseline → compatibility → influence → final → effective |
| **Budget blocked** | "Budget blocked. Tax rates are unchanged." | seats short; which blocs refused; **capital was still spent** | `legislative_vote_resolved` + `budget_blocked_by_legislature` params; ledger rows |
| **Decree enacted** | "Enacted by decree. The legislature was bypassed." | 250 PC flat; every seated bloc's relationship took −2.00pp | `decree_bypass_relationship_reaction` per bloc, shown *separately* from `enacted_policy_relationship_reaction` |
| **Relationship investment** | "Opposition Main improved to −27.74%." | four components, signed and named | `bloc_relationship_resolved` + `relationship_decay_resolved` |
| **Election result** | "You lost the election with 48.22% (50% required)." | legislative 45.82% · population 53.30% · legitimacy 66.84% → baseline 50.91%; swing −2.69pp | `ElectionReport` fields verbatim |
| **Coup / unrest / impeachment risk** | "Coup risk 10.52% this turn." | named contributing factors | `CoupUnrestReport` assessment fields |
| **Constitutional amendment** | "Amendment passed, 67 of 100 seats (67 required)." | five axes changed, old → new; 300 PC committed | opening/closing digests; transition pressure added |
| **Victory** | "Peaceful liberalization completed." | the transition that qualified, and the election that confirmed it | `pending_liberalization` provenance; `game_concluded` params |
| **Defeat** | "Removed from office: electoral defeat, turn 11." | the margin and what drove it | `TerminalOutcomeState` + the terminal turn's full report |

---

## 12. Map design — honest by construction

**Fact: the engine is country-level. There is no province, region, or spatial state anywhere in
`GameState`.** The map is therefore a *national identity anchor*, not a simulation surface.

**Treatment.** A hand-authored **stylised SVG silhouette** of the fictional country, rendered inline
so its parts are addressable DOM nodes. It carries the country's name and government form, a single
national tint driven by one real, country-level metric (default: legitimacy) on a restrained 5-stop
ramp, a small capital marker, and a handful of decorative, non-semantic geographic features.

**Explicitly presentation-only in 4A** — labelled as such in-code and in a visible "About this map"
note: the silhouette shape, all internal features, the capital position, and every overlay-chip
position. **Only the national tint is data-driven, and only from a country-level value.**

**Additive path to real provinces.** The SVG is authored as one `<g id="nation">` containing one
`<path id="outline">`; a future province layer becomes a sibling `<g id="provinces">` keyed by id.
No 4A code assumes "exactly one region" beyond that single element.

**GIS leverage.** Author the silhouette as real GeoJSON, project it once (equal-area) to SVG path
data at build time. **No mapping library is added in 4A**: the projection happens offline, the
output is a static path string.

---

## 13. Visual art bible (compact)

**Direction: modern governmental operations room, restrained political-thriller tone.** Extends
`tokens.css` (F3) — it does not replace it.

| Element | Specification |
|---|---|
| **Palette (existing)** | `navy-950/900/800`, `parchment-100/200`, `gold-500/600`, `charcoal-700/900`, `accent-red-600` |
| **Palette (to add)** | One positive green, one caution amber (contrast parity with `accent-red-600`), one neutral-blue for "informational" |
| **Typography** | Display/serif (`--font-display`) for country name, titles, terminal outcomes. Body/sans (`--font-body`) for data and UI. Tabular numerals everywhere numbers align |
| **Panels** | Flat `navy-900` surfaces, 1px `navy-800` border, 4px corners. No drop shadows, no glassmorphism |
| **Icons** | One stroke-only 24px set, 1.5px stroke, geometric. No emoji |
| **Charts** | Horizontal seat/threshold bars, small-multiple turn-over-turn deltas, stacked budget bars. No pie charts. Every chart states its axis units and threshold |
| **State colours** | Positive green / negative red / caution amber / neutral parchment — never colour alone: always sign + glyph + label too |
| **Portrait** | A single presentation-only silhouette/emblem for "the office" — not a person. No name, no stats, no traits |
| **Accessibility** | ≥4.5:1 body text; colour-blind safe; 2px gold focus rings always visible; `prefers-reduced-motion` respected |

No final art is generated during planning.

---

## 14. State management and API contracts

### 14.1 Client state split

- **React Query** owns all server state (F2), keyed by `["state", revision]` /
  `["history", turn, revision]`. A successful resolve invalidates the affected queries.
- **Zustand** owns only the in-progress decision draft plus UI preferences. **Game state is never
  mirrored into Zustand.**
- **`src/format/` is the only place display arithmetic may occur** (R9, §17 T-format-boundary) —
  small, named, reviewed helpers (`formatBps`, `formatMoney`, `formatTurns`) that convert
  already-computed server values into display strings. No other file performs arithmetic on a
  domain value.

### 14.2 Contract shape

All responses are `application/json`. All errors are a single problem shape:

```
{ "type": "decision_rejected" | "game_concluded" | "save_incompatible" | "stale_revision" |
          "resolution_in_progress" | "no_active_session" | ...,
  "title":  "Budget rejected",
  "detail": "<engine message, verbatim>",
  "status": 422,
  "fields": [ { "path": "decisions[0].influence[1].political_capital", "message": "..." } ],
  "extra":  { ... }   // typed per error, e.g. {bucket, reason, turn} or {expected, actual}
}
```

### 14.3 Type generation (R13, named precisely)

**Tool: `openapi-typescript`** — a single new frontend **devDependency**, zero runtime footprint. It
reads FastAPI's own generated `/openapi.json` and emits a pure `.d.ts` type file
(`src/api/schema.d.ts`), checked in and regenerated by a script (`npm run generate:api-types`). This
adds exactly one new entry to `frontend/package.json`'s `devDependencies` and one generated file to
`src/api/`; it does **not** generate a runtime client, a fetch wrapper, or any executable code — thin,
hand-written `src/api/client.ts` functions call `fetch()` and are typed against the generated
`.d.ts`. §17's T-contract-drift test regenerates the schema in CI and fails if the checked-in file
differs, so the two sides cannot silently drift.

**No MSW (Mock Service Worker) is introduced.** Component tests (§17 T-components) use plain,
hand-written fixture JSON objects typed against the same generated schema, rendered directly into
components via React Testing Library — no service-worker-based request interception is needed at
this scale, and none is added.

---

## 15. Save, load, and error behaviour

### 15.1 Atomicity

**The browser never holds a save.** Every mutation follows §4.8's precise sequence: engine call →
`dump_save_json` → `write_save_atomic` → **only then** the in-memory swap → response. A request
failure or a mid-request browser close cannot corrupt anything: the disk write either completed
atomically (F12) or did not start, and the in-memory session is only ever updated *after* the write
succeeds.

### 15.2 The UI never mutates save JSON

There is no code path from the browser to `state_json`. The client sends *decisions* and *save IDs*;
it receives *projections*. Editing a save requires editing the file outside the app — at which point
`validate_history` catches it on load and the UI refuses to continue, showing the specific problem.

### 15.3 Save As — precise semantics (R12)

`POST /api/game/save-as {display_name}` creates a **new, separate `save_id`** as a checkpoint/branch
of the current state, and registers it in the save index under the given `display_name`. **It does
not rename or replace the session's own autosave `save_id`** — the running session keeps
autosaving under its original ID. This resolves Revision 1's ambiguity between "Save As" and
ordinary autosave, and gives the player a genuine "keep this moment" capability without inventing
save-management features (folders, deletion, renaming-after-creation) that §24 explicitly defers.

### 15.4 Save listing scope (R12)

**In 4A:** basic server-managed listing (`GET /api/saves`), autosave-on-every-mutation, explicit
load-by-ID, and the checkpoint-style Save As above. **Deferred to 4B:** folders/organization,
deletion, renaming an existing save, cloud sync, search/pagination beyond a simple list. A stray
save simply persists — acceptable for a vertical slice with a handful of playtesters.

### 15.5 Import/export (R3/R14 — decided: deferred, shape specified)

**Deferred to 4B, not implemented in 4A.** If and when authorized, the sanctioned shape is: a
bounded multipart upload (size-capped) that is immediately run through `load_save_json` +
`validate_history` *before* acceptance (never trusted on arrival), and a download endpoint that
streams the existing, already-validated save bytes for a given `save_id` with
`Content-Disposition: attachment`. **This is legitimately a full raw-save transfer** (§2.3) — a
different purpose (portability) from the dashboard's purpose-built projections, and not in tension
with them.

### 15.6 Error mapping

| Engine / API error | HTTP | UI treatment |
|---|---|---|
| `DecisionSetError`, `TurnResolutionError` (decision cause) | 422 | Field/workspace errors; draft preserved |
| `StateValidationError` | 500 | "The engine rejected the resulting state; nothing was changed." Save untouched |
| `GameAlreadyConcludedError` | **409** | Route to the terminal screen |
| `SnapshotNotFoundError` | 404 | History UI shows the available range |
| `ScenarioValidationError` | 400 | Scenario card marked unloadable |
| `SaveFileError` | 400 | "Could not read that save file." |
| Version-incompatibility errors (three subtypes) | **409** | "This save was made by an older version. This build supports 0.12.0." **No migration is offered** |
| `HistoryValidationError` / non-empty `validate_history` | **409** | The specific integrity problems; not loadable |
| **Stale revision (§4.8)** | **409** | "The game has moved on to turn N — refresh and reconsider." Draft preserved |
| **Resolution in progress (§4.8)** | **409** | Brief "already resolving…" state; auto-retry once, then surface |
| **Invalid `save_id` / traversal attempt (§4.5, §4.9)** | 400 | Generic "that save could not be found" — never echoes the attempted value |
| **Hostile Origin/Host (§4.9)** | 403 | N/A — never reachable from the legitimate UI |

---

## 16. Accessibility

- **Keyboard**: every interactive control reachable and operable; visible focus ring at all times;
  logical tab order per panel; `Esc` closes any overlay; the decision workspace is fully operable
  without a pointer.
- **Semantics**: landmark regions; one `h1` per screen; data tables are real `<table>` with scope;
  live regions announce turn resolution results.
- **Contrast**: ≥4.5:1 body, ≥3:1 large text.
- **Colour independence**: sign + glyph + label always accompany colour (§13).
- **Motion**: `prefers-reduced-motion` respected.
- **Targets**: ≥32×32 CSS px interactive targets.
- **Zoom**: usable at 200% browser zoom at the supported widths.

---

## 17. Testing matrix

Backend gate is preserved exactly: **6,061 passing tests must not regress**, and all new backend
tests are additive within the same `uv run pytest` gate.

| # | Requirement | Layer | Key assertions |
|---|---|---|---|
| T1 | Every endpoint's happy path | pytest + `TestClient` | status, schema, projection field presence |
| T2 | Decision-schema contract | pytest | every `Decision` union member round-trips API→`DecisionSet` |
| T-reject-not-normalize (R2, replaces old T3) | **Backend never sorts or reorders** | pytest | a payload with decisions/allocations/axes in non-canonical order, sent directly (bypassing the client builder), is rejected 422 with the engine's own message — never silently reordered and accepted |
| T3 | Invalid decisions rejected | pytest | over-cap investment (>200), duplicate targets, budget+amendment together, unaffordable total → 422 with field paths |
| T4 | **Backend is authoritative** | pytest | a hand-built invalid payload bypassing all UI help is still rejected |
| T-stale-revision (R1, new) | Two-tab stale draft | pytest | Tab-B-resolves-then-Tab-A-submits-stale scenario (§4.8) → 409 `stale_revision`, save unchanged, draft preserved |
| T-simultaneous-resolve (R1/R4, new) | Concurrent resolve race | pytest (two tasks against one `TestClient`/lock) | exactly one resolution succeeds; the other gets `resolution_in_progress` or `stale_revision`; no double-advance, no lost update |
| T5 | Stale submission (legacy single-request case) | pytest | a decision echoing an old revision after some other mutation → 409, save unchanged |
| T6 | Atomic rejection through the API | pytest | after a rejected resolve: in-memory save, on-disk bytes, and `current_turn()` all unchanged |
| T7 (R7-corrected) | **Live/history parity** | pytest | `resolve(turn=N).turnResult == history(N).turnResult`, field-by-field, comparing the shared `TurnResultProjection` directly — not two unrelated complete endpoints |
| T8 | Terminal refusal | pytest | resolve after conclusion → 409 with `{bucket, reason, turn}`; no new entry |
| T9 | Save/load round trip | pytest | new → resolve k → save → load (by `save_id`) → projections identical; `validate_history` empty |
| T10 | Tampered save refused | pytest | a byte-edited save fails load with the specific problem, not a generic 500 |
| T11 | Version-incompatible save | pytest | the frozen `phase3b2b_save_ruleset_0.11.0.json` → 409 naming both versions; no migration offered |
| T12 | All three scenarios | pytest | each loads, resolves 3 turns, and produces a complete projection |
| T-preview-rng (R6, replaces old T13) | **Preview touches no RNG** | pytest (source scan) | `app/api/preview.py` imports no symbol from `core.rng` |
| T-preview-no-mutation (R6, new) | **Preview mutates nothing** | pytest | `session.current_save` identity/bytes unchanged before vs. after any preview call |
| T-preview-parity (R6, new, mandatory) | **Preview matches real resolution** | pytest | across all 3 scenarios, both proposal kinds, bicameral/unicameral, the real 67-vs-66 boundary, and varied influence — preview's tally equals the tally from actually resolving the identical decision |
| T-format-boundary (R9, replaces old T14) | **No simulation arithmetic outside `src/format/`** | vitest + ESLint rule | a custom `no-restricted-syntax` rule forbids arithmetic `BinaryExpression`s outside `src/format/**` and test files; `src/format/**` contains only reviewed unit-conversion helpers |
| T-generated-types (part of R9) | **Frontend cannot read un-sent fields** | tsc | components only compile against the generated schema; a deliberately-added component reading a nonexistent field fails the build |
| T15 | Component rendering | vitest + RTL | each panel renders from a fixture projection; no crash on optional/absent reports |
| T16 | Loading / error / empty states | vitest | every query surface has all three |
| T17 | Keyboard navigation | vitest + RTL | decision workspace fully operable via keyboard; focus visible |
| T18 | Accessibility checks | vitest + `axe-core` | zero violations on each screen fixture |
| T19 | Responsive at supported sizes | vitest/CSS | 1280×800, 1440×900, 1920×1080 — no horizontal scroll |
| T20 | Explanation completeness | pytest + vitest | every one of the 30 reason IDs has a UI renderer |
| T-security (R10, new) | **Security boundary** | pytest | traversal-shaped `save_id`, absolute path, embedded separators, symlink-outside-root, hostile `Origin`, non-JSON mutation body — all rejected, no side effect |
| T-contract-drift (R13) | **Types match schema** | CI script | `npm run generate:api-types` against the running server produces no diff against the checked-in `schema.d.ts` |
| T21 | End-to-end campaign smoke | Playwright (gate 4A5) | new `decree_state` → 85/118/300 campaign → resolve to turn 11 → terminal screen, entirely through the GUI |
| T22 | Onboarding sufficiency (R8) | §22 playtest | tracked qualitatively, not a pass/fail unit test — see §22's fun gate |

**End-to-end tooling.** **Playwright is justified** — T21 is the only test proving the ten required
capabilities compose into a playable loop, and needs a real browser driving a real server. Deferred
to gate 4A5 so it is written against a stable UI. **No full-page snapshots** — assertions target
roles, labels, and specific numbers.

---

## 18. Performance budgets

Derived from §2.2, restated with corrected reasoning (R14: these are latency/UX budgets, not a claim
that any of these payloads would otherwise overwhelm a browser):

| Budget | Target | Basis |
|---|---|---|
| New game (API round trip) | < 150 ms | 24.6 ms load + 0.4 ms new_game + write + projection |
| Resolve turn, turn ≤ 20 | < 250 ms | measured 51 ms at turn 20 + save write + projection |
| Resolve turn, turn ≤ 40 | < 400 ms | measured 91 ms at turn 40 |
| Any read-only projection | < 100 ms | served from the in-memory session |
| Load + validate a 40-turn save | < 500 ms | measured 4.4 ms load + 84.4 ms validate |
| Projection payload, any screen | < 100 KiB | one entry is 26.4 KiB raw; projections are subsets, chosen for contract clarity (§2.3), not payload-size necessity |
| Initial JS bundle (gzip) | < 250 KiB | current placeholder is 60 KiB gzip |
| Interaction → visible feedback | < 100 ms | optimistic UI affordance only; never optimistic *results* |

**Stop-and-report rule**: if any measured budget is exceeded by more than 2×, stop and report exact
measurements rather than weakening validation or adding a caching layer that could serve stale state.

---

## 19. Gate-by-gate implementation sequence

Each gate is independently reviewable and must be green before the next begins. Every gate ends with
the **full existing backend gate** (`ruff format --check`, `ruff check`, `mypy`, `pytest`) plus the
frontend gate, both green.

### Gate 4A0 — Plan freeze, UX architecture, greybox, and API contract
- **Commit 0 (isolated, first commit of the phase — R13):** freeze this approved plan verbatim into
  `docs/plans/phase-4a-graphical-vertical-slice-implementation-plan.md`. No other change in that
  commit — mirrors the Phase 3C precedent (`docs/plans/phase-3c-...md`).
- **Outcome:** the contract and the shape of the app agreed before any real code.
- **Adds:** `docs/adr/0014-graphical-vertical-slice-architecture.md`; an OpenAPI sketch; unstyled
  greybox screens (static fixtures, no API); the screen inventory as routes.
- **Tests:** greybox renders; route table test.
- **Manual:** click through every screen with fixture data.
- **Stop if:** the contract cannot express a screen without a client-side calculation.

### Gate 4A1 — Engine-facing application/API layer
- **Outcome:** every endpoint in §4.6 works, fully tested, with no UI at all.
- **Adds:** `backend/app/api/{__init__,main,routes,session,save_registry,projections,preview,errors}.py`
  (8 files); `backend/tests/{test_api_contract,test_api_decisions,test_api_projections,
  test_api_saves,test_api_security,test_api_concurrency,test_api_preview_parity}.py` (7 files).
  **Modifies** `pyproject.toml` (R5: new minimal `gui` extra — `fastapi`, `uvicorn[standard]` only,
  leaving the DB-bearing `api` extra untouched; add `app.api` to `[tool.mypy] packages`; add
  `[project.scripts] mandate-gui`), `uv.lock` (regenerated for the new extra),
  `.github/workflows/ci.yml` (R5/F6: `uv sync --locked --group dev --extra gui`).
- **Tests:** T1, T2, T-reject-not-normalize, T3, T4, T-stale-revision, T-simultaneous-resolve, T5,
  T6, T7, T8, T9, T10, T11, T12, T-preview-rng, T-preview-no-mutation, T-preview-parity, T-security.
- **Manual:** drive the whole campaign with `curl` — new, resolve ×3, history, save, load, plus the
  two-tab and traversal scenarios by hand.
- **Perf:** §18 API budgets measured and recorded.
- **Commits:** (1) api package skeleton + `gui` extra + CI/mypy wiring; (2) `save_registry` +
  session + save/load; (3) projections (`DashboardProjection`, `TurnResultProjection`); (4) resolve
  + revision-token staleness + decision validation; (5) preview + parity tests; (6) security
  middleware (§4.9) + security tests; (7) error mapping; (8) `mandate-gui` entry point (§4.11) +
  startup docs.
- **Stop if:** any projection requires a value the reports do not already contain, or any parity
  test fails to reproduce the real resolver's tally.

### Gate 4A2 — Application shell, scenario start/load, national dashboard
- **Outcome:** a player can start `decree_state` and read their country's condition. No decisions yet.
- **Adds:** React Query + Zustand wiring, `openapi-typescript` devDependency + generated
  `src/api/schema.d.ts` + `src/api/client.ts`, app shell, persistent header, Title/New/Load, Dashboard,
  the SVG map, the five concern cards, the goal card, the glossary panel, first-launch tooltips.
- **Tests:** T15, T16, T19, T-generated-types.
- **Manual:** start each of the three scenarios; load a save; read the dashboard; open the glossary.
- **Perf:** bundle size; projection latency.
- **Stop if:** the dashboard needs a number no endpoint returns.

### Gate 4A3 — Decision workspace and turn resolution
- **Outcome:** a player constructs every supported decision and resolves a turn.
- **Adds:** the workspace, all controls in §10, affordability meter, preview, confirmation, error
  surfacing, per-control tooltips.
- **Tests:** T3, T4, T-reject-not-normalize, T-stale-revision (client-side handling), T17,
  T-format-boundary.
- **Manual:** the full 85/118/300 campaign through the GUI to the turn-3 amendment at 67/100; verify
  the client never sends noncanonical order.
- **Perf:** resolve-turn budget.
- **Stop if:** the UI must compute a projected tally itself (it must come from `/preview`).

### Gate 4A4 — Results, explanations, history, terminal screens
- **Outcome:** the player understands every outcome and can review the whole campaign.
- **Adds:** Turn Result with three-layer disclosure, all 30 reason-ID renderers, history timeline and
  detail (embedding the shared `TurnResultProjection`), Victory/Defeat screens.
- **Tests:** T7 (UI-level), T8, T20.
- **Manual:** resolve to turn 11 on seed 77 (defeat) and seed 0 (victory); review every prior turn;
  confirm history and the original live result render identically.
- **Perf:** history navigation latency.
- **Stop if:** live and historical renderings differ in any field.

### Gate 4A5 — Visual polish, accessibility, security review, external playtest
- **Outcome:** it looks and feels like a game; it is safe to hand to strangers; five strangers play it.
- **Adds:** the art bible applied, icon set, real copy, the "How to govern" intro overlay, `axe` pass,
  Playwright E2E (T21), `mandate-gui` packaging polish (§4.11), the playtest protocol run and its
  findings; dev-only raw-report viewer explicitly stripped from the built artifact (verified, not
  assumed).
- **Tests:** T18, T21; a build-artifact check that no `import.meta.env.DEV`-gated code ships.
- **Manual:** §21 in full, using the one-command startup (§4.11) on a clean machine.
- **Perf:** all §18 budgets re-measured.
- **Stop if:** fewer than three of five testers want another turn (§22) — fix the loop, do not add
  features.

---

## 20. File inventory (R13-corrected)

**New — backend (8, corrected count):** `app/api/__init__.py`, `main.py`, `routes.py`, `session.py`,
`save_registry.py`, `projections.py`, `preview.py`, `errors.py`.

**New — backend tests (7):** `test_api_contract.py`, `test_api_decisions.py`,
`test_api_projections.py`, `test_api_saves.py`, `test_api_security.py`, `test_api_concurrency.py`,
`test_api_preview_parity.py`.

**New — frontend (~32):** `src/api/schema.d.ts` (generated), `src/api/client.ts`; `src/state/`
(query hooks + draft store); `src/format/` (the arithmetic-boundary directory, §14.1/T-format-boundary);
`src/screens/` (Title, Dashboard, Government, Economy, Legislature, Constitution, Relationships,
Decisions, Result, History, Terminal, Glossary); `src/components/` (header, panel, seat bar, delta,
alert, goal card, tooltip, reason renderers, map); `src/assets/nation.svg`; plus co-located tests.

**Modified — backend (3):** `pyproject.toml` (new minimal `gui` extra per R5; mypy `packages` +=
`app.api`; new `[project.scripts] mandate-gui`), `uv.lock` (regenerated), `.github/workflows/ci.yml`
(`--extra gui`).

**Modified — frontend (4):** `package.json` (adds `openapi-typescript` devDependency now, in 4A2;
adds Playwright/axe devDependencies in 4A5), `src/App.tsx` (replaced), `src/main.tsx` (providers),
`src/styles/tokens.css` (extended, not replaced).

**Modified — docs (4):** new `docs/adr/0014-*.md`; `docs/roadmap.md` (record the 4/5 resequencing,
F14); `docs/architecture.md` (new API-layer section); `README.md`.

**Deliberately NOT modified:** every file under `app/core/`, `app/simulation/`, `app/content/`,
`app/saves.py`, `app/cli.py`, all three scenario YAMLs, every frozen fixture, `docker-compose.yml`,
and the existing `api` optional-dependency extra. **Any diff touching `app/simulation/` during 4A is
a scope breach.**

---

## 21. Manual walkthrough

Using `uv run mandate-gui` (§4.11) against a built frontend, in a browser, CLI closed:

1. Launch; see the optional "How to govern" intro; dismiss it. Three scenario cards. Start
   **`decree_state`** at its authored seed.
2. Dashboard: monarchy, unlimited decree, legitimacy 60%, capital 500/1,000, no election scheduled.
   Goal card names the amendment opportunity. Hover a tooltip; open the glossary; close it.
3. Legislature: 45 governing vs 55 opposition; opposition relationship −80%.
4. Decisions → invest **85 PC** in `opposition_party/main`. Affordability shows 85/500. Preview (not
   applicable to investment; applicable to the amendment step below). Confirm; resolve.
5. Result: relationship −80% → **−53.85%**, capital closes **798**. Four components shown separately.
   Note the `revision` token advanced.
6. Turn 2: invest **118 PC** → **−27.74%**, capital **1,000**.
7. Turn 3: switch the policy slot to **Constitutional amendment**; set all five axes; allocate
   **300 PC**. Preview shows **67 of 100, 67 required** (via `/preview`, proven byte-identical to the
   real vote by T-preview-parity). Confirm; resolve.
8. Result: **PASSED**; five axes listed old → new; next election **turn 11**; pending liberalization
   set; coup risk rises to **10.52%**.
9. **Open a second browser tab** on the same running server. Both show the same state. In Tab B,
   build the same 299-influence amendment draft and hold it without submitting. In Tab A, resolve a
   quiet turn 4 (no decisions). Now submit Tab B's stale draft → **409 "the game has moved on to
   turn 5"**, draft preserved, not silently misapplied.
10. Resolve turns 4–10 with no decisions; watch transition pressure decay 8,334 → 2,792.
11. Turn 11: election. At seed 77 → **LOST, 48.22% vs 50%** → Defeat screen. Resolve is refused (409).
12. Reload the pre-election save (by ID, from the save list); review turns 3 and 11 in History —
    **identical rendering to live** (same `TurnResultProjection`).
13. Start a new campaign at seed 0 → same campaign → **WON 58.10%** → Victory screen.
14. Load the frozen `phase3b2b_save_ruleset_0.11.0.json` (copied into the save root under a fresh ID
    for this test) → refused, naming 0.11.0 and 0.12.0, no migration offered.
15. Hand-edit a byte in a save file on disk; load it → refused with the specific integrity problem.
16. Attempt `POST /api/game/load {"save_id": "../../etc/passwd"}` directly (bypassing the UI) →
    clean 400, no filesystem access, no crash.
17. Repeat steps 1–2 for `tiny_valid` (bicameral: two chambers shown) and `deficit_demo`.
18. Restart the server process entirely. Reopen the browser tab → "no active game" → Title/Load
    screen → resume the seed-0 victory save by ID → dashboard shows the correct post-victory state.

---

## 22. External playtest protocol

- **Recruit five** people unfamiliar with the codebase; at least two who do not play strategy games.
- **Setup:** the app already running (§4.11) on `decree_state`, no explanation beyond "you govern
  this country." **The onboarding surfaces (§8.2) are the only help offered — no facilitator
  coaching once the session starts.**
- **Task:** play at least five turns. No CLI, no code, no help from the observer.
- **Observe and record, per tester:**
  1. Time to first confident decision.
  2. Every point of visible confusion, with the screen and the element, and whether a tooltip/goal
     card/glossary entry was available there and unused, or genuinely absent.
  3. After each resolution: *"What just happened, and why?"* — record whether the answer matches the
     engine's actual reason IDs.
  4. Whether they discover the decree/legislate trade-off unprompted.
  5. Whether they can say what their capital bought.
- **Fun gate (primary):** at the end of turn five, ask *"do you want to play another turn?"* — record
  the unprompted answer. **At least three of five must voluntarily want another turn.**
- **If fewer than three:** stop. Do not add systems, screens, or scenarios. Fix the
  decision→feedback loop and the onboarding surfaces (§8.2) — clarity of consequence, legibility of
  trade-off, weight of the result, tooltip placement, goal-card wording — and re-run with five new
  testers.

---

## 23. Risks, limitations, rollback

1. ⚠ **Turn cost grows linearly with history** (6 ms → 91 ms over 40 turns, §2.2). Fine for a
   vertical slice; §18 budgets it and measures it every gate. **Not** fixed by weakening
   `validate_history` in 4A.
2. ✅ **Resolved in this revision:** CI previously would not have installed any FastAPI dependency at
   all (F6) and the extra it would have installed pulled in an unused database stack (R5). Both fixed
   by the new minimal `gui` extra and the corresponding CI change in gate 4A1's first commit.
3. ✅ **Resolved in this revision:** `app.api` is added to the mypy gate in the same first commit
   that creates it (F7) — never shipped unchecked even transiently.
4. ⚠ **The frontend could silently start computing outcomes.** The single most important scope
   risk. **Mitigation:** T-format-boundary's structural ESLint rule (no arithmetic outside
   `src/format/**`) plus T-preview-parity proving even the one composed calculation (preview) is
   provably identical to real resolution.
5. ⚠ **Projection/type drift between API and UI.** **Mitigation:** T-contract-drift regenerates and
   diffs the TypeScript schema in CI.
6. **The showcase campaign loses at the authored seed.** Deliberate (§6.2). **Mitigation:** the
   defeat screen explains the margin and the seeded swing explicitly, and offers a new campaign; the
   seed override makes the victory path reachable on demand.
7. **Map honesty could erode over time.** **Mitigation:** §12's explicit presentation-only labelling
   in-code and the single `{regionId: value}` tint function.
8. ✅ **Resolved in this revision:** stale-decision detection (R1) and concurrent-mutation safety
   (R4) were previously undefined/broken (server-side stamping defeated the engine's own staleness
   check). Now fully specified in §4.8 with dedicated tests.
9. ✅ **Resolved in this revision:** save paths were previously client-supplied, a real
   path-traversal exposure even on loopback. Now save IDs only (§4.5), with dedicated security tests
   (§4.9, T-security).
10. **`decree_state` has no scheduled election at start**, which could read as "nothing to do."
    **Mitigation:** the goal card (§8.2) names the amendment opportunity as the primary objective.
11. **Rollback:** every gate is independently revertible; 4A is purely additive to a green `main`,
    and no engine file is touched. Reverting all of 4A restores Phase 3C exactly. There is no version
    bump, no save-format change, and therefore no one-way door.

---

## 24. Explicitly deferred

**Deferred to 4B or later:** desktop packaging (Electron/Tauri, installers, code signing), Postgres
persistence + Alembic (all of roadmap Phase 4's database work — the existing DB-bearing `api` extra
stays completely untouched), advanced multi-save management (folders, deletion, renaming, cloud
sync — R12), import/export (R3/R14 — deferred, sanctioned shape specified in §15.5 if later
authorized), multi-session/multiple-simultaneous-games (§4.4), undo/rewind, a full guided tutorial
campaign (R8 — only lightweight contextual onboarding ships in 4A), sound, animation beyond state
transitions, localisation, mobile/tablet layouts, and save migrations (**explicitly forbidden in
4A**).

**Unchanged from Phase 3C's deferred list:** characters and cabinet ministers, emergency system,
courts/judicial review, seat realignment, defections, confidence votes, coalition collapse,
AI-country politics, war, diplomacy, nuclear weapons, provincial simulation, multiplayer,
LLM-generated gameplay.

**Carried forward untouched:** `POL-4`, `FIN-1`, `FE-1` (the `nanoid` advisory — not remediated
during planning), `TEST-1`.

**Roadmap correction owed (F14):** `docs/roadmap.md` still describes Phase 4 as "Persistence and
API" and Phase 5 as "Playable frontend." Phase 4A deliberately resequences these. Recorded during
4A's documentation work as a disclosed deviation.

**A raw-report JSON viewer is dev-only, never player-facing (R12).** Gated by
`import.meta.env.DEV`; gate 4A5 includes a build-artifact check proving it does not ship.

---

## 25. Requirement-to-test matrix

| Mandate requirement | Gate | Tests |
|---|---|---|
| Start a scenario | 4A2 | T1, T12, T15 |
| Understand immediate condition | 4A2 | T15, T16, T19 |
| Review government/economy/political constraints | 4A2 | T15, T19 |
| Construct a legal decision | 4A3 | T2, T-reject-not-normalize, T3, T-format-boundary, T17 |
| Resolve a turn | 4A3 | T1, T5, T6, T-stale-revision, T-simultaneous-resolve |
| Understand what changed and why | 4A4 | T20, **T7** |
| Review prior turns | 4A4 | **T7** |
| Save and reload | 4A1, 4A4 | T9, T10, T11, T-security |
| Continue to victory or defeat | 4A4 | T8, T21 |
| No CLI, no raw JSON | 4A5 | T21, §21 |
| Backend authoritative | 4A1, 4A3 | **T4**, T3, T5, T-reject-not-normalize |
| Frontend computes nothing | 4A1–4A5 | **T-format-boundary**, T-preview-rng, T-preview-parity |
| Atomicity preserved | 4A1 | T6, T9 |
| Concurrency safety | 4A1 | **T-stale-revision, T-simultaneous-resolve** |
| Security boundary | 4A1, 4A5 | **T-security** |
| Live/history parity | 4A4 | **T7** |
| Preview is authoritative | 4A1 | **T-preview-parity, T-preview-no-mutation, T-preview-rng** |
| All three scenarios | 4A2 | T12 |
| Onboarding sufficiency | 4A5 | §22 |
| Accessibility | 4A5 | T17, T18 |
| Responsive desktop sizes | 4A2 | T19 |
| End-to-end campaign | 4A5 | **T21** |
| Contract stability | 4A1 | T-contract-drift, T-generated-types |
| Map implies no province mechanics | 4A2 | §12 assertion + review |
| Performance budgets | every | §18 measurements |
| External playtest fun gate | 4A5 | §22 |

---

## 26. Consistency sweep (this revision)

Performed across the whole document after integrating R1–R14:

- **Architecture (§4):** revision-token flow (R1), lock semantics (R4), save-ID scheme (R3),
  minimal `gui` extra (R5), preview composition + parity (R6), shared `TurnResultProjection` (R7),
  security boundary (R10), startup story (R11) — all defined once in §4, referenced (not redefined)
  everywhere else.
- **Endpoints (§4.6):** every endpoint name used later in §9, §10, §15, §17, §19, §21 matches this
  table exactly; `/save-as` and `/load` use `save_id`/`display_name`, never `path`.
- **File inventory (§20):** recounted (8 backend modules, 7 backend test files — R13); includes
  `save_registry.py` and the security/concurrency/parity test files added by R1/R3/R4/R6/R10;
  includes `src/format/` (R9) and `openapi-typescript`'s generated file (R13).
- **Gates (§19):** gate 4A1 now explicitly includes the `gui` extra + CI + mypy wiring, the
  save-registry/session/lock work, and all R1/R3/R4/R6/R10 tests; gate 4A0 explicitly names the
  isolated plan-freeze commit (R13); onboarding (R8) is spread across 4A2/4A3/4A5 rather than
  bolted on at the end.
- **Tests (§17, §25):** old T3 (server-side sorting) and old T13/T14 (RNG-only preview check,
  numeric deny-list) are withdrawn and replaced by name; every new R-derived test has a stable
  identifier used consistently in §17, §19, and §25's requirement matrix.
- **Manual walkthrough (§21):** rewritten to use `mandate-gui`, save IDs, the revision token, and
  includes the two-tab and traversal-attempt steps the new architecture specifically claims to
  handle.
- **Risks (§23):** four previously-open risks (CI/mypy wiring, stale-decision detection, save-path
  safety) are marked resolved-in-this-revision rather than left as open risks now that §4 specifies
  them.
- **Deferred scope (§24):** import/export and advanced save management are named as deferred with
  their sanctioned future shape (R3/R14), rather than silently absent; the dev-only JSON viewer is
  named explicitly (R12).
- **Performance reasoning (§2.3, §18):** every remaining reference to save/projection size is
  framed as a contract/latency argument, not a "the browser can't handle it" argument (R14) —
  checked section by section.

No section references a Revision-1 assumption this revision corrected.

---

## Final plan status

**Implementation-ready.** Every architectural recommendation is tied to a cited repository fact
(§3) or a measured number (§2.2), and every one of the fourteen binding corrections (R1–R14) is
integrated at its point of use, not appended as an addendum. Design choices are labelled as choices;
facts are labelled as facts. The two largest scope decisions remain: **no database in 4A**, and
**one authoritative server-held session with a save-ID-only filesystem boundary** — together these
make a graphical vertical slice reachable and safe to hand to external playtesters without first
building all of roadmap Phase 4.

Zero repository files were modified during planning. No branch, no dependency, no code, no PR.
