# ADR 0014: Graphical vertical slice — local API process, server-held session, projected UI

- Status: accepted
- Date: 2026-08-18

## Context

Every phase through 3C built a simulation that is provably correct and completely invisible. The
engine resolves twelve self-validating reports per turn, hash-chains them, reconciles them against
state, and refuses to lie — but the only way to see any of it is `app/cli.py` printing indented
text, or reading canonical JSON by hand. `frontend/src/App.tsx` was an eleven-line placeholder that
said, in its own words, that no gameplay screens exist yet.

Phase 4A closes that gap with a desktop-first **graphical vertical slice**: start a scenario, read
the country's condition, construct a legal decision, resolve a turn, understand what changed and
why, review prior turns, save, reload, and play to victory or defeat — without touching the CLI or
reading raw JSON.

Phase 4A **exposes existing mechanics**. It adds no formula, no mechanic, and no calibration.
Ruleset/content stays `0.12.0`; `SAVE_FORMAT_VERSION` stays `1`.

This ADR records the architecture decided in the frozen plan
(`docs/plans/phase-4a-graphical-vertical-slice-implementation-plan.md`, Revision 2) and implemented
across gates 4A0–4A5. **Gate 4A0 — this commit's scope — implements none of it.** It freezes the
plan, records these decisions, sketches the API contract, and builds a static greybox. No API code,
no dependency, and no `backend/app/api/` package exists yet.

## Decisions

### One local FastAPI process and one React SPA; the Python engine is the only simulation authority

A local FastAPI application, bound to loopback only, holds the authoritative `GameSave` and serves
JSON to a Vite/React SPA. The API is a **thin adapter over the existing engine** — `new_game`,
`advance_game`, `validate_history`, `dump_save_json`, `load_save_json`, `load_scenario_file`,
`GameSave.current_state()/.current_turn()/.entry_at(turn)` are already exactly the operations the UI
needs. Any divergence between GUI and CLI behaviour becomes a test failure rather than a silent
fork.

**No simulation arithmetic exists in TypeScript.** Vote support, required seats, balances,
legitimacy, relationships, political-capital costs, risk percentages, election outcomes and terminal
conditions all arrive as explicit projection fields. Display conversions — basis points to
percentage text, integer currency to localized text, turn labels — are isolated to `src/format/`.

Rejected: Pyodide/WASM (ships a Python runtime to the client and makes "the frontend computes
nothing" unverifiable), reimplementing formulas in TypeScript (forbidden outright), a CLI subprocess
per action (re-parsing formatted text, and file paths would become the API), and a static SPA
reading save JSON directly (cannot execute the engine at all).

### No database in Phase 4A

Saves are engine save files on disk. The existing database-bearing `api` optional-dependency extra —
which declares `sqlalchemy`, `alembic` and `psycopg` alongside `fastapi`/`uvicorn` — is **left
completely untouched** for the real Phase-4 persistence work later. Gate 4A1 will add a separate,
minimal `gui` extra containing only `fastapi` and `uvicorn`. `docker-compose.yml`'s Postgres service
stays unused.

### One process-wide `GameSession`: one mutation lock, one active save

The server holds a single module-level `GameSession` containing **one** mutation lock and **one**
authoritative in-memory `GameSave`. This is not per-browser-cookie, per-tab, or per-user state:
multiple tabs against the same running server share the same session and the same save. Multiple
simultaneous independent games are out of scope for 4A — the player loads one save at a time,
exactly like the CLI's `--state`/`--out` model. A deliberate simplification, named as one.

### The authoritative mutation order: persist, then swap, then unlock, then respond

Every session-mutating operation (`/api/game/new`, `/api/game/load`, `/api/game/resolve`,
`/api/game/save-as`) follows this order:

1. **Acquire the mutation lock immediately, or reject** with `409 {"type": "resolution_in_progress"}`.
   A mutation is never silently queued behind another.
2. **Parse the client-echoed revision token.**
3. **Compare it with the live state**, and reject a stale revision with
   `409 {"type": "stale_revision"}`.
4. **Construct `DecisionSet` without normalization** and call the authoritative engine.
5. **Serialize and atomically persist** the newly returned save.
6. **Swap `session.current_save` only after persistence succeeds.**
7. **Release the mutation lock.**
8. **Construct and return the projections from the successfully persisted new save.**

The result is returned *after* the lock is released, not before, and always from the save that was
actually persisted.

**Failure behaviour:** every error path releases the lock. A failed resolution or a failed
persistence leaves **both** the authoritative in-memory save and the existing on-disk save
unchanged. This is what makes a browser crash or a mid-request disconnect harmless: the browser
never held the file, and the in-memory pointer only ever moves after the disk write succeeded.

Atomic writing already exists and is reused verbatim: `app/saves.py`'s `write_save_atomic` creates a
same-directory temp file, `fsync`s it, `os.replace`s the destination, `fsync`s the directory, and
removes the temp file on any exception. **`app/saves.py` is not modified by Phase 4A.**

### Server-managed UUID4 save IDs; never client-supplied paths

A fixed, server-managed save root holds engine saves at exactly `{save_root}/{save_id}.json`, where
`save_id` is a server-generated UUID4. Nothing in the API layer ever accepts a filesystem path from
a client.

An incoming `save_id` is checked against a strict UUID4 regex **before any `Path` is constructed**,
so `..`, absolute paths, path separators and null bytes fail on shape rather than on a blocklist —
traversal is prevented by construction. As redundant layers, the resolved path is asserted to have
the save root as its real resolved parent, and the target is asserted not to be a symlink before it
is opened.

Display names and listing metadata live in an API-layer-only sidecar index, never in the engine save
format, never hash-covered, never read by the engine, and never used to construct a path.

### Purpose-built projections, not raw engine JSON

The API serves `DashboardProjection` and `TurnResultProjection` rather than `state_json` /
`report_json`. The reason is **contract stability, not payload size**: raw engine JSON exposes
internal representation (bps encodings, digest strings, discriminator literals) that would couple
screens to internal schema instead of a versioned API contract, and a projection is independently
typed and testable, so an engine schema change cannot silently reshape a screen.

Import/export, if it ships later, may legitimately transfer a complete raw save — a different
purpose (portability) from a different endpoint (rendering). It is deferred.

### Client-echoed opaque revision tokens

Every projection embeds `revision`, an opaque token documented to the client as *echo verbatim,
never parse or construct one*. The client sends back the token it most recently received, and the
server passes those values **unchanged** into `DecisionSet.expected_turn` /
`.expected_state_version`.

The server deliberately does **not** stamp those fields from its own current save. Stamping them
would satisfy the engine's staleness check by construction, silently disarming a real guarantee; the
echo makes `resolver.py`'s own `DecisionSetError` do load-bearing work. A stale draft submitted
after another tab resolved is refused, never applied against a turn the player did not see.

### Reject, never normalize, decision ordering

The engine's contract is to *reject* noncanonical order, not to reorder it — canonical kind order,
canonical influence identity order and canonical amendment axis order each raise rather than sort.
**The API layer performs no sorting whatsoever.** Instead the graphical decision builder assembles
its payload in canonical order by construction, because that is the order it iterates its own draft
structure in. A payload sent directly to the API bypassing the UI still receives a clean 422 from
the engine's own validators.

### One shared `TurnResultProjection` for live and historical results

`TurnResultProjection` is defined exactly once and is the only type that ever describes "what
happened on turn N and why." `POST /api/game/resolve` returns it for the turn just resolved;
`GET /api/game/history/{turn}` returns it for a historical turn, **built by calling the identical
projection function over the identical stored `TurnReport`** — never a second, parallel
implementation. In the UI, the live Turn Result screen and the History detail view render the **same
component**; their presentation logic is not duplicated.

`GET /api/game/state` is deliberately separate and returns a bare `DashboardProjection` — the
country's current condition, never a narrative about what changed.

### Preview composed from existing voting primitives, protected by parity tests

No single high-level pure vote-scoring function exists in the engine: `phases.py` composes
`resolve_bloc_support` → `apportion_supporting_seats` → `required_yes_seats`/`chamber_carries`
inline. Preview therefore **composes the same primitives in the same order**, read-only over the
current opening state.

Preview never calls `advance_game`, never touches an RNG stream (so the seeded channels — election
swing, coup, unrest, impeachment — are never previewed; their uncertainty is the game), and never
mutates session state, the save, or history. Because the composition is unavoidable rather than
reused from a shared function, it is protected by a **mandatory parity suite** comparing preview's
tally against actually resolving the identical decision, across all three scenarios, both proposal
kinds, both chamber shapes, and the real passed/failed boundary.

Rejected: extracting a new shared function into `app/simulation/`. That package is inside the
phase's scope freeze, and touching it is a scope breach.

### Loopback-only, same-origin security; no wildcard CORS; JSON-only mutations

`uvicorn` binds `127.0.0.1`, never `0.0.0.0`. In development, Vite proxies `/api/*` so browser
requests are same-origin and no CORS middleware is needed. In playtest mode FastAPI serves the built
SPA itself — one origin, one port, one process. A middleware validates `Origin` and `Host` as a
DNS-rebinding defence. Mutations accept only `application/json`, rejected with 415 otherwise.
`allow_origins=["*"]` is forbidden anywhere.

### React Query for server state; Zustand for drafts and preferences only

React Query owns all server state. Zustand owns only the in-progress decision draft and UI
preferences — **game state is never mirrored into Zustand**. Both libraries are already declared in
`frontend/package.json` and were unused before this phase; no new runtime dependency is required for
the core application.

### `decree_state` is the polished showcase; all three scenarios load

One scenario is polished, all three are smoke-supported. `decree_state` is chosen because it is the
only scenario with a real decision every turn (legislate for 283 political capital versus decree for
250), the only one containing a victory rather than only defeat, and the one with the shortest path
to a decisive moment — the 85/118/300 amendment campaign passing at exactly 67 of 100 against a
required 67, with 299 failing at 66.

At the authored seed 77 the turn-11 election is **lost** (48.22% against 50% required). This is kept
deliberately: losing a campaign you invested 503 political capital in is the tension the slice is
meant to produce. The new-game screen exposes the optional seed field; seed 0 reaches the victory
path at 58.10%. **No scenario file is recalibrated to simplify the interface.**

### The country map is presentation-only

The engine is country-level: there is no province, region, or spatial state anywhere in `GameState`.
The map is therefore a national identity anchor, not a simulation surface, and is labelled as such
in-code and in a visible note. Only a single national tint driven by one country-level metric is
data-driven; the silhouette, internal features, capital position and overlay positions are all
decorative. A future province layer becomes a sibling SVG group without any 4A code assuming "one
region."

### Minimal contextual onboarding, not a tutorial campaign

Contextual tooltips, a plain-language goal card rendered from the same alert-ranking data the
dashboard already computes server-side, a static glossary, and an optional dismissible intro. No
forced tutorial, no gated tutorial turns.

### A raw-report JSON viewer is developer-only

Gated behind `import.meta.env.DEV` and verified absent from the built playtest artifact. A
player-facing "read the raw report" escape hatch would undercut the entire premise of purpose-built
projections.

### Deferred

Desktop packaging (Electron/Tauri, installers, signing), Postgres persistence and Alembic, advanced
save management (folders, deletion, renaming, cloud sync), import/export, multiple simultaneous
games, undo/rewind, a full guided tutorial, sound, localisation, mobile layouts, and save migrations
(explicitly forbidden in 4A).

## Gate 4A0 scope — what this commit does and does not do

**Does:** freeze the approved plan verbatim; record these decisions; sketch the API contract as a
non-running OpenAPI document; build a static, fixture-driven greybox covering the twelve planned
screens with navigation, tests, and no network access.

**Does not:** create `backend/app/api/`; add FastAPI, uvicorn, `openapi-typescript`, Playwright, axe,
or any other dependency; implement endpoints, session state, the save registry, preview logic,
security middleware, concurrency locking, persistence, or any engine call from the frontend.

The greybox exists to answer one question before any API is written: **can the planned contract
express every screen without a client-side calculation?** Every value it displays is a literal in a
static fixture. No arithmetic derives one displayed value from another — not even to make the
fixture internally consistent.

## Known limitations

- **Turn cost grows with history.** `advance_game` revalidates the entire chain, measured at 6.12 ms
  at turn 1 and 91.08 ms at turn 40 on this machine. Comfortable for a vertical slice; the first
  thing to revisit if campaigns lengthen. Not addressed by weakening `validate_history`.
- **One session per process.** Two tabs share one game. Concurrent mutation is refused, not queued.
- **The frontend could in principle start computing outcomes.** The mitigation is layered — generated
  contract types, forbidden imports, a narrow forbidden-constant rule, contract tests proving
  displayed values are server-provided, and review of the small `src/format/` directory — and it is
  not claimed that any lint rule proves the semantic absence of client-side simulation.
- **The roadmap is resequenced.** `docs/roadmap.md` describes Phase 4 as "Persistence and API" and
  Phase 5 as "Playable frontend"; Phase 4A deliberately does the graphical slice first, without the
  database. Recorded as a disclosed deviation, to be reflected in the roadmap during 4A's
  documentation work.
- **FE-1 carried forward.** The dev-only `nanoid` advisory (GHSA-2v37-7h3g-55p8, via
  `vite → postcss`) is unchanged and deliberately not remediated in this gate.

## Consequences

The engine becomes visible without becoming duplicated. The API layer is additive to a green `main`:
no engine file is touched, there is no version bump and no save-format change, so there is no one-way
door — reverting Phase 4A restores Phase 3C exactly.

The cost is a real client/server contract to maintain, and a standing discipline that every semantic
value a screen shows must exist as a field some projection actually sends. That discipline is the
point: it is what keeps the Python engine the single authority over what is true in the game.
