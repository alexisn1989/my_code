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
      saves.py       disk I/O for save files: atomic writes/reads — outside core/simulation
      cli.py         headless entry point: create games, resolve turns, inspect history
    migrations/      Alembic (Phase 4+)
    tests/
  frontend/
    src/{App.tsx,main.tsx,styles/}   verified shell (Phase 0/1); gameplay screens start Phase 5
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
alias, canonical JSON/hashing, shared error types) that carry no game-specific rules and that
`simulation` depends on. `app/saves.py` sits on the *other* side of the boundary from `simulation`:
it is the one module allowed to touch the filesystem (`tempfile`, `os`) for save I/O, and it is
deliberately a sibling of `app/core`/`app/simulation`, not inside either — see "History, hash
chaining, and immutability" below for why atomic file writes don't belong inside the pure engine.

## Deterministic simulation

Every `GameState` stores an integer `seed`. Any code that needs randomness during turn resolution
must request a `random.Random` instance from `core.rng.derive_rng(seed, turn, stream)`, which seeds
from a hash of `(seed, turn, stream_name)`. `stream_name` namespaces independent random draws (e.g.
`"events"` vs. `"combat"`) so that adding a new consumer of randomness in one system cannot shift
the sequence another system draws — a common source of "deterministic but fragile" bugs. Simulation
code must never read `random` module global state or wall-clock time directly; this is enforced by
an AST-based test (`tests/test_no_forbidden_imports.py`) that inspects every module under
`app/core` and `app/simulation` and fails if it imports `random` (only `app/core/rng.py` may) or
`time`/`datetime` `.now()`-style calls. The one exemption is imports inside `if TYPE_CHECKING:`
blocks: those never execute at runtime (doubly so under this codebase's universal `from __future__
import annotations`), so they cannot introduce non-determinism — this is what lets
`simulation/phases.py` annotate a method as returning `random.Random` without actually importing
`random`. `app/saves.py` is deliberately *outside* both scanned packages: its `tempfile`/`os` usage
is real, necessary non-determinism (unique temp filenames, filesystem timing), but it lives at the
I/O boundary, never inside a function that computes game state — see "History, hash chaining, and
immutability" below.

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

## History, hash chaining, and immutability

`resolve_turn` has no notion of "the game so far" — it stays a pure function of one state and one
decision set. `app/simulation/history.py` adds that notion in a layer *above* the resolver rather
than inside it, because the two concerns are genuinely separate (correctly computing one
transition vs. durably and verifiably remembering the sequence that produced the current state) and
keeping them apart meant the resolver's existing test suite needed zero changes.

**Representation, not just a `frozen=True` flag, is what makes history immutable.** A frozen
wrapper around a mutable `GameState` does not make the `GameState` immutable — a caller can still
reach through it. `HistoryEntry` instead stores `state_json`/`decisions_json`/`report_json` as
canonical JSON **strings** plus plain `str`/`int`/`None` fields; there is no mutable object
anywhere inside a `HistoryEntry` or `GameSave` to reach. `.state()`/`.decisions()`/`.report()` and
`GameSave.current_state()` each parse a **fresh** model on every call, so two calls return two
independent objects and mutating either cannot touch what's stored
(`tests/test_history.py::test_mutating_retrieved_*`). `current_state` is derived from the final
entry rather than cached as a second mutable copy — "current state matches the final entry" holds
by construction, with nothing to independently drift.

**The hash chain protects the complete path to a state, not just the state.** Every entry's
`entry_hash` is a BLAKE2b-256 digest (`core.canonical_json.canonical_digest`) over the canonical
JSON of `{turn, previous_entry_hash, decisions, report, state, ruleset_version, content_version}`
— the submitted decisions and resulting report are covered, not only the resulting numbers.
Changing any of those seven fields on any entry breaks that entry's hash and every
`previous_entry_hash` link after it. A **chain-link check alone cannot catch tail truncation**
(deleting the last N entries leaves a shorter chain that is still internally consistent), so
`GameSave` also carries `entry_count` and `head_entry_hash`, each updated by exactly one
increment/replacement per successful `advance_game` call and untouched on failure.

**Two independent checks catch two different kinds of tampering.** `validate_history` checks both
(1) whether a stored payload's *parsed value* still matches its recomputed hash, and (2) whether
the *stored string itself* is still exactly its own canonical form
(`canonical_dumps(json.loads(s)) == s`). Editing a number breaks (1). Adding whitespace or
reordering keys inside a stored JSON string breaks (2) but not (1), since `json.loads` ignores
formatting — so (2) exists specifically to catch a class of tampering the hash chain alone would
miss. Neither check ever repairs what it finds; malformed stored data is reported as a problem, not
silently renormalized. Full details and the exact hash payload are in
`docs/adr/0002-snapshot-history-and-versioning.md`.

**What this is not.** The chain, `entry_count`, and `head_entry_hash` are unkeyed hashes over a
public algorithm — anyone editing a save file can recompute all of them. This is deterministic
*corruption and unsophisticated-tampering detection*, not anti-cheat security, and is never
described otherwise.

**Atomic writes use a unique temp file, not a deterministic one.** `app.saves.write_save_atomic`
creates a unique temp file in the destination's own directory (`tempfile.NamedTemporaryFile`),
writes and `fsync`s it, closes it, then `os.replace`s the destination, cleaning up on any failure.
Filesystem naming has no bearing on game-state determinism — it's not part of any canonical
payload, hash, or history — so there was nothing to gain by making it predictable, and a fixed name
would let concurrent writes to the same destination collide. Best-effort directory `fsync` after
the replace persists the rename itself where the platform supports it (skipped, not failed, on
platforms without a directory file descriptor to sync, e.g. Windows).

**Performance boundary.** `advance_game` runs `validate_history` (a full O(n) re-verification of
every entry's hash and chain link) before every single turn, so N sequential turns cost O(n²)
total. Measured at n=100 (`tests/test_soak.py`): ~0.7s total, ~7ms/turn. This build favors
correctness over optimization — validation strength is not weakened to make this faster. If a
later phase's soak testing shows this matters at realistic game lengths, the options are
incremental tail-only validation (trust everything before the last known-good entry) or a trusted
in-memory session wrapper that validates once on load; neither is implemented without a measured
reason to.

## Money and bounded values

`Money` is declared as `Money: TypeAlias = int` in `core/money.py` (Python 3.11 target — no PEP 695
`type` statement). One unit = 1/100 of the in-fiction currency. All treasury, debt, revenue, and
expenditure fields use `Money`; arithmetic is plain integer arithmetic, so ledgers either reconcile
exactly or fail a test — no binary-float drift. Bounded political metrics (approval, loyalty,
trust, 0–100 scale) are `float` with a shared `clamp01_100` helper; they don't need to balance to
zero the way money does, only to stay in range, which `check_invariants` enforces.

## Persistence: file-based now, database at Phase 4

Two storage shapes, kept deliberately separate — one built now, one designed for later:

- **Immutable snapshot history, built now, as files.** A `GameSave` (`simulation/history.py`) *is*
  the "new row per turn, never overwritten" model from the product spec (§5.4), just backed by a
  JSON file instead of a database table. `save_format.dump_save_json`/`load_save_json` are the pure
  (de)serialization; `app/saves.py` is the atomic disk I/O. `cli.py new` creates a save with one
  genesis entry; `cli.py resolve` appends N entries via `advance_game` and writes atomically,
  refusing to overwrite its input; `cli.py history` retrieves any past entry without mutating
  anything; `cli.py inspect` reports version/turn/entry-count/integrity status without requiring the
  save to be valid to inspect it.
- **Relational identity tables** (`games`, `countries`, `leaders`, …), for things queried by ID,
  joined, or listed (e.g. "list my saves" across many games at once) — genuinely deferred to Phase
  4, since nothing about listing/querying many games is needed to play one game end to end. At
  Phase 4, a `GameSave`'s entries become rows in a `game_snapshots` table (one immutable row per
  turn, same content, same hash chain) instead of array elements in a JSON file; the
  `history`/`save_format` modules do not need to change shape to make that move; the entries stay
  in this file-based form for local development and headless tooling regardless.

## Content and versioning

Scenarios are YAML. Parsing/validation is pure and lives in `app/simulation/scenario.py` (text in,
`GameState` out, no disk access); reading the file from `data/scenarios/` is the one line of I/O in
`app/content/scenarios.py`, which is otherwise where Phase 2+ content loaders (policies, events)
will live once those systems exist to validate against. Every
`GameState` carries `ruleset_version` and `content_version` strings (semver-ish, hand-bumped) so
that a balance change to policy/event data does not retroactively alter already-resolved turns
loaded from an older snapshot — enforced at Phase 2+ when content actually has numeric effects; the
fields exist from this session onward so nothing has to be retrofitted.

A third, independent version — `save_format_version` (`simulation/save_format.py`) — covers the
shape of the save *file* itself, separate from both `ruleset_version` and `content_version`.
`save_format.check_compatibility` checks all three independently and raises a distinct exception
naming exactly which one is unsupported, rather than one generic "incompatible save" error. See
`docs/adr/0002-snapshot-history-and-versioning.md` for the compatibility policy and why the Phase-0
save format is rejected outright rather than migrated.

## Why not more, yet

FastAPI, SQLAlchemy, and Alembic are intentionally not exercised yet. The brief's phase discipline
(§38, §39) treats "playable and understandable game loop" and "deterministic, correct simulation"
as higher priority than API surface or UI, and explicitly warns against generating a large amount
of unverified code in one pass. `app/api`, `app/db`, `app/models`, `app/schemas`, `app/services`
are documented here as the target shape (git does not track empty directories, so they are not
created on disk until Phase 4 gives them contents).

The frontend toolchain *is* now installed and verified (`npm ci`, `tsc --noEmit`, `vite build`,
`vitest run` all pass in CI) — see `README.md` for the commands — but it remains a placeholder
shell with one render smoke test. No gameplay screens, API calls, routing, or state management are
implemented; those start at Phase 5 once there is a backend API for them to talk to. Building them
sooner would mean building UI against a save-file CLI it will never talk to in production.

Future domain model classes from the product spec (§8) that have no behavior yet — full
`GovernmentState`, `MilitaryState`, `DiplomaticRelationState`, party/election models, and so on —
are added in the phase that gives them behavior (see `docs/roadmap.md`), not stubbed out empty now.
An empty placeholder model is worse than no model: it looks like progress, has no tests worth
writing against it, and has to be redesigned anyway once its actual behavior is known.
