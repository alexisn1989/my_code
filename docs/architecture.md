# MANDATE — Architecture

## System boundaries

```
mandate/
  backend/
    app/
      core/         pure infrastructure: RNG, money type, error types — no game rules
      simulation/    pure game engine: state, decisions, phases, resolver, invariants — NO I/O
      api/           FastAPI routes (Phase 4+) — thin, delegates to simulation + services
      db/            SQLAlchemy models, session management (Phase 4+)
      models/        ORM row models (Phase 4+, distinct from simulation/state.py domain models)
      schemas/       Pydantic request/response DTOs for the API (Phase 4+)
      services/      orchestration: load state → call simulation → persist (Phase 4+)
      content/       loaders/validators for data-driven content (policies, events, scenarios)
      cli.py         headless entry point: create games and resolve turns without a server
    migrations/      Alembic (Phase 4+)
    tests/
  frontend/
    src/{api,components,features,pages,stores,styles,types}   (Phase 5+ for behavior)
  data/
    scenarios/       validated scenario YAML (content, not code)
    events/          (Phase 8+)
    map/             (Phase 6+)
  docs/
  scripts/
  docker-compose.yml (Phase 4+: Postgres for local dev)
```

The load-bearing boundary is **`app/simulation` has zero dependencies on FastAPI, SQLAlchemy, or
any I/O**. It is a library: construct a `GameState`, submit a `DecisionSet`, call `resolve_turn`,
get back a new `GameState` and a `TurnReport`. Everything else in the backend (API routes, DB
persistence, the CLI) is a caller of that library, not part of it. This is what makes the engine
independently testable and keeps turn-resolution logic in one place instead of leaking into
request handlers.

`app/core` sits below `simulation`: infrastructure primitives (deterministic RNG, the `Money` type
alias, shared error types) that carry no game-specific rules and that `simulation` depends on.

## Deterministic simulation

Every `GameState` stores an integer `seed`. Any code that needs randomness during turn resolution
must request a `random.Random` instance from `core.rng.derive_rng(seed, turn, stream)`, which seeds
from a hash of `(seed, turn, stream_name)`. `stream_name` namespaces independent random draws (e.g.
`"events"` vs. `"combat"`) so that adding a new consumer of randomness in one system cannot shift
the sequence another system draws — a common source of "deterministic but fragile" bugs. Simulation
code must never read `random` module global state or wall-clock time directly; this is enforced by
an AST-based test (`tests/test_no_forbidden_imports.py`) that inspects every module under
`app/simulation` and fails if it imports `random` (only `app/core/rng.py` may) or `time`/`datetime`
`.now()`-style calls.

Determinism is verified by resolving the same scenario + seed + decisions twice, independently, and
comparing **canonical JSON** serializations of the resulting state and report byte-for-byte:
sorted object keys, fixed separators, no timestamps, no UUID4 values, no unordered-set
serialization, no environment-dependent fields (hostnames, PIDs, cwd). `core/canonical_json.py`
provides the single serialization path used by tests, save files, and (later) API responses, so
"deterministic" is actually machine-checked rather than asserted by eye.

## Turn resolution

`resolve_turn(state: GameState, decisions: DecisionSet) -> TurnResolution` is a pure function:

1. **Validate first, on the untouched input.** `validate_decision_set(state, decisions)` checks the
   decision set's `expected_turn`/`state_version` against `state.turn`/`state.version` and runs
   `check_invariants(state)` on the input. Any failure raises `TurnResolutionError` and returns
   before anything is copied — the caller's `state` object is provably untouched (checked with a
   pre/post equality assertion in tests, not just "we didn't call any mutators").
2. **Copy.** Only after validation passes, deep-copy `state` into a working copy.
3. **Run phases in the fixed order** from `simulation/phases.py::PHASE_ORDER`, mutating the copy.
   The 15-phase order from the product spec (§7) is encoded as data — a tuple of `(phase_id,
   handler)` — so the order is declared once, tested once (`test_resolver.py` asserts the exact
   sequence of phase IDs that ran), and cannot silently drift.
4. **Re-validate.** `check_invariants` runs again on the result. A violation discards the working
   copy and raises — the original `state` argument is still the untouched pre-turn state, giving
   the same "fully commits or leaves state unchanged" guarantee the database transaction will give
   at Phase 4, but provable in-process without a database.
5. **Return** `TurnResolution(state=new_state, report=TurnReport(...))`.

Phases this session (0/1) implement for real: decision validation, turn/version advance, and report
generation. The other named phases (production, budget, prices, diplomacy, combat, group welfare,
institutional updates, unrest, elections, narrative events) are registered in `PHASE_ORDER` as
explicit no-ops — each phase handler exists and runs, but does nothing yet and records that fact in
`TurnReport.dev.phase_statuses: dict[str, Literal["implemented", "not_implemented"]]`, structured
metadata for developers/tests. It is **not** surfaced as 12–15 repetitive entries in the
player-facing part of the report — the brief's "no placeholder feature claims" rule (§5.7) means
absent behavior is marked in dev metadata, not narrated to a hypothetical player as if it were
content.

## Money and bounded values

`Money` is declared as `Money: TypeAlias = int` in `core/money.py` (Python 3.11 target — no PEP 695
`type` statement). One unit = 1/100 of the in-fiction currency. All treasury, debt, revenue, and
expenditure fields use `Money`; arithmetic is plain integer arithmetic, so ledgers either reconcile
exactly or fail a test — no binary-float drift. Bounded political metrics (approval, loyalty,
trust, 0–100 scale) are `float` with a shared `clamp01_100` helper; they don't need to balance to
zero the way money does, only to stay in range, which `check_invariants` enforces.

## Persistence (design now, build at Phase 4)

Two storage shapes, kept deliberately separate:

- **Relational identity tables** (`games`, `countries`, `leaders`, …) for things queried by ID,
  joined, or listed (e.g. "list my saves"). Not built this session.
- **Immutable snapshot JSON** (`game_snapshots`, `turn_reports`) for full `GameState`/`TurnReport`
  objects at each turn, serialized via the same canonical JSON path used for determinism checks.
  Snapshots are never overwritten; a new turn is a new row. This gives the "immutable turn history"
  guarantee from the spec (§5.4) directly from the storage model rather than from application-level
  discipline.

This session's CLI approximates the snapshot half of that model without a database: `cli.py new`
writes a versioned JSON state file (schema version + `ruleset_version` stamped in), `cli.py inspect`
loads and validates a state file without mutating it, and `cli.py resolve` loads a state file,
resolves N turns, and writes the resulting state to a new output path — never overwriting the input
file, foreshadowing the "new row per turn" persistence model.

## Content and versioning

Scenarios are YAML. Parsing/validation is pure and lives in `app/simulation/scenario.py` (text in,
`GameState` out, no disk access); reading the file from `data/scenarios/` is the one line of I/O in
`app/content/scenarios.py`, which is otherwise where Phase 2+ content loaders (policies, events)
will live once those systems exist to validate against. Every
`GameState` carries `ruleset_version` and `content_version` strings (semver-ish, hand-bumped) so
that a balance change to policy/event data does not retroactively alter already-resolved turns
loaded from an older snapshot — enforced at Phase 2+ when content actually has numeric effects; the
fields exist from this session onward so nothing has to be retrofitted.

## Why not more, yet

FastAPI, SQLAlchemy, Alembic, and the frontend runtime are intentionally not exercised this
session. The brief's phase discipline (§38, §39) treats "playable and understandable game loop" and
"deterministic, correct simulation" as higher priority than API surface or UI, and explicitly warns
against generating a large amount of unverified code in one pass. `app/api`, `app/db`,
`app/models`, `app/schemas`, `app/services` are documented here as the target shape (git does not
track empty directories, so they are not created on disk until Phase 4 gives them contents).
