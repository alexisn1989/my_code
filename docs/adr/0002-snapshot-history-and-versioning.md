# ADR 0002: Snapshot history, hash chaining, and version compatibility

- Status: accepted
- Date: 2026-08-01

## Context

Phase 1's minimal slice gave a pure `resolve_turn(state, decisions) -> (state, report)` with no
notion of "the game so far": each call discarded the previous state. That's enough to prove the
engine works, but not enough to make a *game* — there was no way to inspect turn 3 after reaching
turn 8, no way to detect a corrupted or hand-edited save, and the Phase-0 save file
(`{state_file_schema_version, state}`) recorded a snapshot with no memory of how it was reached.

This ADR covers the design added to fix that: an immutable, hash-chained history layer above the
resolver (`app.simulation.history`), a version-compatibility policy (`app.simulation.save_format`),
and atomic save I/O (`app.saves`).

## Decision

### History is a separate layer above the resolver, not inside it

`resolve_turn` is unchanged. `simulation.history.advance_game(save, decisions) -> GameSave` calls
it and wraps the result in one more history entry. Turn-resolution correctness and history
integrity are genuinely separate concerns, and keeping them apart meant the resolver's own test
suite needed zero changes while adding this layer.

### `HistoryEntry` stores canonical text, not live models — this is what makes immutability real

A `frozen=True` wrapper around a mutable `GameState` does not make the `GameState` immutable —
callers can still reach through the wrapper and mutate the nested object. `HistoryEntry` instead
stores `state_json` / `decisions_json` / `report_json` as canonical JSON **strings**, plus plain
`str`/`int`/`None` fields. There is no mutable object anywhere inside a `HistoryEntry` or
`GameSave` to reach. `HistoryEntry.state()` / `.decisions()` / `.report()` and
`GameSave.current_state()` each parse a **fresh** Pydantic model on every call — two calls return
two independent objects, and `tests/test_history.py` proves mutating either has no effect on the
stored save (`test_mutating_retrieved_*_does_not_affect_history`,
`test_independent_retrievals_return_independent_objects`).

`current_state` is *derived* from the final entry rather than cached as a second mutable field.
This also means "the current state matches the final entry" holds by construction — there is
nothing to independently validate, because there is no second copy to drift from the first.

### The hash chain protects the complete path to a state — not just the state

Every entry's `entry_hash` is a BLAKE2b-256 digest (`core.canonical_json.canonical_digest`) over
the canonical JSON of:

```json
{
  "turn": <int>,
  "previous_entry_hash": <string|null>,
  "decisions": <object|null>,
  "report": <object|null>,
  "state": <object>,
  "ruleset_version": <string>,
  "content_version": <string>
}
```

Hashing the parsed *value* of state/decisions/report (not the raw stored string) means the chain
detects changes to what a turn actually was — including the decisions submitted and the report
produced — not just the resulting numbers. An earlier design considered hashing only `state`; that
would have let someone rewrite a turn's justification (its `DecisionSet`/`TurnReport`) without
detection as long as the resulting `GameState` matched, which defeats the point of keeping history
at all. The genesis entry (turn 0) has `previous_entry_hash`, `decisions`, and `report` all `null`.

### Tail truncation needs its own guard — a chain-link check alone cannot see it

`previous_entry_hash` links let validation catch a modified, reordered, or internally-removed
entry (its neighbor's link breaks). But **deleting the last N entries** leaves a shorter chain that
is still perfectly self-consistent — the truncated history has no way to know it used to be longer.
`GameSave` carries two small envelope fields precisely to close this: `entry_count` (must equal
`len(entries)`) and `head_entry_hash` (must equal `entries[-1].entry_hash`). Both are updated by
exactly one increment/hash-replacement per successful `advance_game` call and are untouched on
failure (`test_successful_turn_updates_count_and_head_hash_exactly_once`,
`test_failed_turn_changes_neither_count_nor_head_hash`).

### Two independent kinds of tamper detection, deliberately

`validate_history` checks two different things about every stored payload string:

1. **Value integrity** (hash recompute): does the *parsed* content still match what was hashed?
2. **Representation integrity** (canonical-form check): is the *stored string itself* still exactly
   `canonical_dumps(json.loads(stored_string))`?

These catch different tamper classes. Changing a number changes the parsed value, so (1) catches
it. Adding whitespace or reordering keys inside a stored JSON string changes nothing about the
parsed value — `json.loads` ignores formatting — so (1) alone would miss it silently; (2) exists
specifically to catch that (`test_noncanonical_stored_payload_is_rejected_without_normalization`).
Validation never repairs a non-canonical payload it finds; it only reports the problem.
Construction-time normalization (turning a fresh model into canonical text) happens exactly once,
in `history._make_entry`, when an entry is legitimately built — never during validation of an
existing one.

### Honesty about what this is, and isn't

The hash chain, `entry_count`, and `head_entry_hash` are **unkeyed**. Anyone who can edit a save
file can recompute the entire chain — including a truncated envelope — by running the same public
algorithm this codebase ships. What this reliably catches is **accidental corruption and
unsophisticated hand-editing**: a bit flip, a manually "fixed" JSON value where the editor didn't
also fix every downstream hash, a naive line deletion. It is not anti-cheat security and is not
described as such anywhere in the code or docs.

### Atomic writes use a unique temp file, not a deterministic one

`app.saves.write_save_atomic` creates a unique temp file (`tempfile.NamedTemporaryFile(dir=...,
delete=False)`) in the destination's own directory, writes and `fsync`s it, closes it, then
`os.replace`s the destination — cleaning up the temp file on any failure and leaving the
destination untouched. An earlier draft of this design used a fixed `<dest>.tmp` name for a
"deterministic everything" story; that was wrong. Filesystem naming is outside the simulation's
determinism boundary entirely — it never appears in any canonical payload, hash, or history — so
there was nothing to gain by making it predictable, and a fixed name would let two concurrent
writes to the same destination collide on the same temp path. `app.saves` lives outside
`app.core`/`app.simulation` specifically so this doesn't need to negotiate with the
`random`/wall-clock restrictions those packages enforce (see `tests/test_no_forbidden_imports.py`,
which only scans those two packages).

### Three version concepts, checked independently, Phase-0 saves rejected outright

`save_format_version` (the save file's shape), `ruleset_version` (simulation rules), and
`content_version` (authored content) are checked independently by
`save_format.check_compatibility`, each raising a distinct exception
(`UnsupportedSaveFormatVersionError` / `UnsupportedRulesetVersionError` /
`UnsupportedContentVersionError`) naming the unsupported value and what is supported.

The Phase-0 save format (`{state_file_schema_version, state}`) is **not** migrated — it is simply
not read by `load_save_json` at all (different top-level shape entirely, so it fails the envelope
key check with a `SaveFileError`). A migration is not just extra work here, it is impossible in
principle: Phase 0 recorded a bare `GameState` and never recorded the turns that produced it, so a
Phase-0 save sitting at turn 8 cannot be given a valid 9-entry history — there is no history to
migrate *from*, only a final answer with its work erased. The format existed for one commit, was
never part of a release, and has no save files anyone depends on. Rejecting it cleanly costs
nothing real and avoids fabricating a fake history that would look legitimate.

### Performance: correctness over optimization, for now

`advance_game` calls `validate_history` (full O(n) chain/hash re-verification) on every turn, so N
sequential turns cost O(n²) total. Measured at n=100: ~0.7s total, ~7ms/turn — see
`tests/test_soak.py`, which prints the measured duration. This is judged acceptable for Phase 1's
scale (tens to low hundreds of turns). If a later phase's soak testing shows this matters at
realistic game lengths, the documented options are incremental tail-only validation (trust
everything before the last known-good entry) or a trusted in-memory session wrapper that validates
once on load and tracks its own invariant afterward — neither is implemented now, since validation
strength should not be traded away without a measured reason.

## Consequences

- Every historical turn's justification (decisions + report), not just its outcome, is tamper-
  evident. This is strictly more than "protect the final state," at the cost of the hash payload
  being larger to recompute (still cheap at this scale).
- `GameSave`/`HistoryEntry` being plain frozen dataclasses over primitive fields (no live domain
  objects) means the whole history layer has no dependency on Pydantic's mutability model at all;
  Pydantic only appears at the parse/dump boundary (`.state()`, `_make_entry`).
- Save files are less human-eyeball-readable than Phase 0's `indent=2` format (canonical JSON is
  compact, and `state_json`/`decisions_json`/`report_json` are escaped strings-within-strings) —
  traded deliberately for byte-identical export/import and a meaningful canonical-form check. The
  `inspect`/`history` CLI commands exist so a human never needs to read the raw file.
- Anyone loading an old Phase-0 save gets a clear rejection, not a crash or silent misinterpretation
  — but also cannot continue that specific game; they must start a new one.
