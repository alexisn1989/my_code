# Gate 4A3 R1 fix (code): the listing memo is seeded when the server writes a save

This is option (a) from [`gate-4a3-r1-diagnosis.md`](gate-4a3-r1-diagnosis.md) §5, chosen by you ("go
with a"). That choice is also the §18 ruling this memo population needs, for this fix only.

**This commit holds the code, tests and command. No timing is claimed here.** The candidate build is
measured in the release record that follows.

**The approved playtest archive (`f542cf28…`) is unchanged**, and R1 stays open on it. Whether the
playtest moves to the candidate is your decision.

## 1. The change (`backend/app/api/save_registry.py`)

`SaveRepository.write_save` serialises the save, writes it atomically (unchanged), and then calls a new
`_seed_verdict(path, data, save)`, which does three things:
1. **Reads the file back** with `read_save_bytes`, the listing's own reader. It seeds **only when the
   bytes on disk equal the bytes it serialised.** A mismatch, or a failed read, seeds nothing and is
   not a write failure, because the write already succeeded atomically.
2. **Builds the verdict exactly as `_compute_verdict` does:**
   - `scenario_id` and `current_turn` come from `save.current_state()`;
   - `terminal_summary` comes from `_terminal_summary_text(save)`;
   - **`problems=()` is asserted from provenance, not computed.**
3. **Stores it under the memo lock**, keyed by `sha256(data)`. It never replaces an existing entry or
   one in flight, and it never exceeds `VALIDATION_MEMO_MAX`.

**The trust, stated plainly** (and in the class docstring):
- **Why the bytes are trusted:** they are this server's own serialisation of a save the engine built.
  `advance_game` validates its input; `new_game` builds a genesis; save-as writes the session's save,
  which was either loaded with full validation or built by the engine.
- **What it would cost if that trust were wrong:** an engine defect that produced an invalid history
  would be **listed** as loadable until the process restarts.
- **Why it would still not be played:**
  - **load never consults the memo**, and validates in full every time (`routes.py:205–223`);
  - the session already plays from that same in-memory save without re-validating it today.

**What it does not change:**
- The engine's own `validate_history` of the **input** save in `advance_game`
  (`history.py:261`) still runs once per resolve. Only the listing's second validation goes.
- **A cold start:** the memo stays in memory, so a fresh process validates every save once, as before.
  That is R1's open remainder.
- The engine, the save format, the ruleset, the contract, the scenarios and the frontend source.

**The candidate's dry-run command.** `frontend/package.json` gains `dryrun:installed:r1fix`, with gate
label "4A3 R1-fix (enforced)", writing `gate-4a3-r1fix-dryrun`. It is added here so the release commit
can stay records-only.

## 2. Tests

**New: `backend/tests/test_save_memo_seeding.py`, 23 tests.**

| # | what |
|---|---|
| 1 | **Equivalence.** The seeded verdict equals `_compute_verdict` on the same bytes, **field for field**, for each shipped scenario at turns 0, 1, 5 and 20 (12 cases), and for a **concluded** campaign: `tiny_valid` run to the engine's own refusal. This is the guard on the asserted `problems=()` |
| 2 | after a write, a listing makes **no** validation call for that save, while an unseeded file in the same root is validated once. A second listing validates nothing |
| 3 | different valid bytes written behind the repository's back get a new key and are validated. Tampered bytes are listed as not loadable, with their problem |
| 4 | a read-back mismatch seeds nothing, the file still exists, and the next listing validates. A failed read-back seeds nothing |
| 5 | a memo at `VALIDATION_MEMO_MAX` is not grown by a write, and an existing entry for the key is not replaced |
| 6 | **the API path.** `/game/new`, then five `/game/resolve` calls, then save-as, then `GET /api/saves`. The **listing's** `validate_history` is called **0** times, while the engine's own (`advance_game`) is called exactly **5** times, once per resolve |
| 7 | a save seeded and then tampered on disk is **refused by `/game/load`** with a 4xx |
| 8 | a fresh repository on the same root, which is what a restart is, validates every save once, as before |

**Existing tests: a setup-only change, by your rulings ("Fix setup only", then the two below).** Five
tests in
`backend/tests/test_save_validation_memo.py` wrote their saves through the same `SaveRepository` they
then listed:
- `test_a_second_listing_validates_nothing_and_returns_identical_records`;
- `test_byte_identical_files_are_validated_once_and_listed_twice`;
- `test_one_file_over_the_cap_costs_one_validation_per_listing_not_a_rescan`;
- `test_concurrent_misses_on_one_key_validate_once`;
- `test_when_the_owner_fails_a_waiter_computes_for_itself`.

Under seeding, their precondition, "the repository under test has never seen these bytes", no longer
held:
- three of them measured 0, 0 and 1 validations where they expected 2, 1 and 4;
- the two concurrency tests timed out waiting for a validation that never started.

**The fix, in those five functions, and later in the two tests below:** the saves are written through a **second**
`SaveRepository` on the same root (`writer`), as a restarted server would find them.
- **The whole diff, across all seven tests:** eight `_write(repository, …)` calls became
  `_write(writer, …)`, plus one three-line comment and `writer = SaveRepository(tmp_path)` per test.
  The seventh test also gains one assertion, described below.
- **No existing assertion changed.**
- I reported this as a deviation from the plan, which said those tests "must pass unchanged", before
  changing anything.

**Two more tests, found after the first full-suite run, and fixed the same way by your two further
rulings.** Neither one failed, which is why I missed them at first.

1. **`test_admission_under_the_cap_is_atomic_across_concurrent_distinct_keys` was passing
   vacuously.**
   - Seeding filled its cap-2 memo during setup, so only one of its three concurrent threads reached
     validation.
   - Its three-way barrier then timed out in that thread (`BrokenBarrierError`). Pytest surfaced this
     only as a `PytestUnhandledThreadExceptionWarning`: the suite's warning count went from 1 to 2.
   - Its final asserts still held, so the concurrency it exists to prove was not being exercised.
2. **`test_the_listing_never_reopens_a_file_through_read_save` was weakened.** Its listing became a
   memo hit, so the compute path it guards no longer ran.

**Both now write through the second repository.** The second also gains one assertion: the listing's
`validate_history` count is 1. That turns "the compute path ran" into an asserted property.

**Every other test that writes through the repository under test was read and assessed:**
- in the memo suite, the same-length tamper, display-name and mtime, CRLF and LF, symlink, and
  retention tests still exercise their properties;
- in `test_api_saves.py`, the tests assert results, not validation counts.

**Thread exceptions are now checked as errors.** The save suites were re-run with
`-W error::pytest.PytestUnhandledThreadExceptionWarning` and pass with no thread exception, so no
barrier is broken anywhere.

**Mutation checks.** Each was restored afterwards and checked with `cmp`.

| mutation | failed |
|---|---|
| seed without the read-back comparison | test 4, "read-back mismatch" |
| seed `problems=("x",)` | all 13 equivalence cases, plus tests 2 and 6, because the saves list as not loadable |
| ignore `VALIDATION_MEMO_MAX` | test 5, "full memo" |
| remove the seeding call | all 13 equivalence cases, plus tests 2 and 6 |

## 3. Gates

Each command was run on its own, and each exit status is its real `$?`.

| command | exit | result |
|---|---:|---|
| `pytest -W error::pytest.PytestUnhandledThreadExceptionWarning` on the seeding, memo, concurrency, saves, save-bytes and atomic-save suites | 0 | 138 passed, no thread exception |
| backend full suite (`pytest -q`), first run | 0 | 36,460 passed, **2 warnings**. The second warning was the vacuous sixth test, which led to the fixes above. Not accepted as a gate result |
| backend full suite (`pytest -q`), after the sixth and seventh fixes | 0 | **36,460 passed**, **1 warning** (the known `StarletteDeprecationWarning`; no thread exception), in 16:58. That is 36,437 + 23 new |
| `ruff check .`, `ruff format --check .` | 0, 0 | |
| `mypy` (project config) | 0 | 57 source files |
| `npm run generate:api` | 0 | byte-identical: no tracked file changed |
| `npm test`, `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | 613 passed. **The bundle is byte-identical** |
| the 22 save fixtures | | unchanged |

## 4. Scope

- **Changed:**
  - `backend/app/api/save_registry.py` (`write_save`, a new `_seed_verdict`, and the class docstring);
  - `backend/tests/test_save_validation_memo.py` (setup only in seven tests, plus one added assertion
    in the seventh, as above);
  - `frontend/package.json`.
- **Added:**
  - `backend/tests/test_save_memo_seeding.py`;
  - this record.
- **Unchanged:**
  - the approved playtest archive and its roadmap line;
  - the engine, the save format, the ruleset, the contract, the fixtures, the scenarios and the
    frontend source.
