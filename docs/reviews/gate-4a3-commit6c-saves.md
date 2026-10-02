# Gate 4A3 Commit 6c — `GET /api/saves` fixed with a content-keyed validation memo; the waiver ended

**Subject:** `Gate 4A3 (6c/6): validate each save's bytes once, and end the /api/saves waiver`
**Parent:** `522bbfa4eb1a47b96729523ed912a8dd0600ba90` (Commit 6b), not amended.
**Evidence from this run:** `gate-4a3-commit6c-release.json`, `gate-4a3-commit6c-budgets.json`,
`gate-4a3-commit6c-packaged.json`.

`GET /api/saves` was the one budget that failed in Gate 4A3. At Commit 6 its worst was 245–314 ms
against a 200 ms STOP, and 283.68 ms at 6b. It shipped as **FAILED, waived by user ruling**
(`gate-4a3-commit6-budget-waiver.md`, left byte-identical). The waiver said it would end with *"a
follow-up decision on the fix, once it is implemented and measured under the 200 ms STOP"*. This
commit is that fix, measured. **The waiver is ended:** the verifier no longer accepts any budget
breach.

---

## 1. The ruling, and its provenance

The approach is caching, which frozen §18 forbids without the user's say-so. It was put to the user
through the question tool in this session. Both questions, all options, and the answer are below,
extracted programmatically from the session transcript (`95421f9a-dace-5133-a3f4-58c7d173c2c7.jsonl`),
not retyped.

The transcript is not in the repository, so this section is a **transcribed attestation**. That is the
same status as the browser exit codes recorded in 6a, which `gate-4a3-commit6b-verifier.md` §5
describes.

**Question 1** (header `Next item`):

> Gate 4A3 is internally complete at 522bbfa4. Which owed item should come next?

- **Fix /api/saves (Recommended)** — "The one failed budget (worst 245-314 ms vs 200 ms STOP). Fixing it removes the waiver so 'internally complete' needs no exception. Needs your ruling on the approach (next question)."
- **npm default-name hazard** — "Mechanical: make the remaining e2e specs/npm scripts require explicit artifact names with exclusive writes, like 6b did for the verifier. No design decision; frontend e2e + package.json only."
- **T2: reason_id beside drivers** — "Each Turn result driver line paints its engine reason_id in a <code> element (27/27). Copy decision: remove it, or keep it as a labelled trace aid."
- **Carried divergences** — "The three from the characters slice: shared *_REJECTION_CODES tuple for bargain/assistance, /preview returning the stable code, and a repo-wide emitted-reason registration check. Backend refactor of shipped code."

**Question 2** (header `Saves fix`):

> If /api/saves is next: list_saves fully replays validate_history on every save on every listing (and also rewrites the index on each GET). Frozen §18 forbids caching or weakened validation without your say-so. Which approach do you authorize?

- **Content-keyed memo (Recommended)** — "Cache each save's validation result keyed by SHA-256 of its exact bytes (in memory, per server). Same verdict as today since validation is a pure function of the bytes; any change re-validates. This is caching, so it needs your explicit authorization."
- **Validate on load only** — "Listing checks envelope, versions and hash chain but not a full replay; full validate_history still runs on load, so nothing unvalidated is played. 'loadable' becomes a weaker claim in the list."
- **Keep waiver, no fix yet** — "Leave /api/saves as FAILED-WAIVED and do something else next."
- **Not applicable** — "Choose this if you picked a different item above."

**Answer, verbatim:**

> Your questions have been answered: "Gate 4A3 is internally complete at 522bbfa4. Which owed item should come next?"="Fix /api/saves (Recommended)", "If /api/saves is next: list_saves fully replays validate_history on every save on every listing (and also rewrites the index on each GET). Frozen §18 forbids caching or weakened validation without your say-so. Which approach do you authorize?"="Content-keyed memo (Recommended)". You can now continue with these answers in mind.

Question at transcript line 555 (2026-10-02T02:08:31.092Z), answer at line 556 (2026-10-02T02:08:39.157Z); tool-use id `toolu_01MnrUudwmRNjYNiT2jLoLrK`.

A review of the plan required "exact bytes" to be honoured literally (§2.1), and required the design
points in §2.2–§2.4 before implementation.

---

## 2. The fix

### 2.1 The key is the exact on-disk bytes (`backend/app/saves.py`)

`read_save_file` used `Path.read_text`, which decodes UTF-8 **and translates `\r\n` and `\r` to
`\n`**. Hashing its result would have given a CRLF file and an LF file the same key, contradicting
"exact bytes". It is split, with no change in behaviour:

- `read_save_bytes(path)` returns the exact bytes, with the same `SaveFileError` on `OSError`.
- `decode_save_bytes(raw, path)` uses `io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")`. That is
  the same machinery `read_text` uses, so the newline translation and the decode-error message are
  identical.

**Parity is proved against the right oracle.** The 6b `read_save_file` is copied verbatim into
`tests/test_save_bytes.py`, because it wraps errors in `SaveFileError` and bare `read_text` does not.
Across LF, CRLF, lone CR, mixed, BOM, invalid UTF-8 (including a decode failure past the first 8 KiB
chunk), an empty file, a missing file and a directory, the new function returns the identical text or
raises the identical `SaveFileError` message. **11 tests.**

### 2.2 One captured buffer per file (`backend/app/api/save_registry.py`)

The listing reads each file **once**. The SHA-256 key, the decode, `load_save_json` and
`validate_history` all come from that one buffer. Nothing reopens the file, so a verdict can never be
stored under the key of bytes it was not computed from.

`read_save`'s path checks (ID validation, root containment, refusing symlinks and non-regular files)
moved into one shared `_checked_path`, used by both `read_save` and the listing. Loading a save
(`read_save` and the load endpoint) still validates in full every time; the memo serves only the
listing.

### 2.3 What is memoized, and for how long

**What is memoized.** Only a successful verdict: scenario, current turn, problems and the terminal
summary. The following are not:
- read, decode, parse and version failures, which are re-checked on every listing;
- `display_name` (from the index);
- `updated_at` (from `stat`).

**Admission, with no eviction.** A plain LRU over a sorted scan thrashes at `cap + 1`: each insert
evicts the file the next listing reads first, so every listing revalidates everything. Instead, a miss
is admitted only if a slot is free, and nothing is ever evicted to make room. With `cap + k` saves,
`k` revalidate per listing, never all of them. The cap is `VALIDATION_MEMO_MAX = 4096`.

**Atomic admission.** The decision is taken under the lock when a computation registers, counting
admitted computations still in flight. Concurrent misses on distinct keys therefore cannot overshoot
the cap.

**Retention follows the directory.** At the end of a listing, keys that no current file has are
dropped.

**Single-flight.** Concurrent misses on one key compute once. Waiters read the result from the
in-flight object they waited on, not from the memo. This keeps single-flight working for a key that
was deliberately not admitted because the memo is full. If the owner fails with a non-memoizable
error, waiters compute for themselves.

**Why it is sound.** `validate_history` does no I/O, reads no clock, no randomness and no scenario
file, and imports only engine modules. Decoding and parsing are deterministic, and the code and the
supported versions are fixed for a process's lifetime. So within one server process the verdict is a
pure function of the bytes. The memo is in memory and per server; a restart starts empty.

### 2.4 The verifier (`scripts/verify_release.py`)

**The waiver path is removed:** `RULED_BREACH_ENDPOINT`, `BUDGET_WAIVER` and `ruled_breach_only`.
- `budget_verdict` returns `"PASSED"` only for exit 0 with no breaches. Any breach raises,
  `/api/saves` included.
- The budget step is now `measure_budget_step`, so its wiring is testable.

**The two 6b cleanup holes are closed:**
- `reserve()` now releases its placeholders on **any** failure, not only `FileExistsError`. A
  `PermissionError` or a full disk on the second `open("x")` used to strand the first.
- The three final writes now sit inside the protected region, so a failure on any of them releases
  all three reservations.

---

## 3. Measured

### 3.1 The verifier, on the new archive

The archive was rebuilt at `SOURCE_DATE_EPOCH=1790730747`. `app/` changed, so the hash changed:
`1dafdc746eee165e5056f6177bfe95b2a314b263ede12f0eead12f8525546c90` (was `54290cca…`). Two independent
builds agree (`--check-reproducible`). `verify_release.py` exited **0**:

| budget | median | worst | STOP | |
|---|---:|---:|---:|---|
| new game | 41.37 ms | 68.58 ms | 300 ms | OK |
| resolve, turns ≤ 20 | 93.57 ms | 184.06 ms | 500 ms | OK |
| resolve, turns 21–40 | 246.01 ms | 331.72 ms | 800 ms | OK |
| **read projection** | 6.01 ms | **154.61 ms** | 200 ms | **OK** |
| load + validate 40-turn save | 132.76 ms | 184.74 ms | 1000 ms | OK |
| projection payload | 2,752 B | 68,113 B | 204,800 B | OK |

- **Per endpoint (median / worst):** `/api/saves` **6.93 / 10.8 ms**, down from 186.71 / 283.68 at
  6b. The read row's worst is now `/api/scenarios` at 116.72 / 154.61 ms, unchanged in kind and under
  its STOP.
- **Verdict:** `"PASSED"`, `breaches: []`, with `runId` equal in the release and budget records.
- **Packaged turn:** 13 requests, none off-origin; feedback worst 5.1 ms.

### 3.2 What the budget does not show

These figures are recorded, not asserted, and stated plainly. The budget method, unchanged since
Commit 6, discards one warm-up request per endpoint. The first listing that sees a file validates it
in full, once. Measured in-process over 20 saves of one `decree_state` campaign (turns 2–40):

- **A fresh server's first listing:** about **1,543 ms**, which is every save validated once.
- **Warm listings:** median about **21 ms**, worst about 33 ms.
- **The first listing after one new 41-turn save:** about **276 ms**, which is that one file
  validated once.

So the steady state is fixed. A newly written long save still costs one full validation on its first
listing, which is above the STOP. Taking that cost earlier, for example by validating at write time,
would be a separate design decision. It is not part of this commit.

### 3.3 The waiver is really gone: an end-to-end reproduction

The 6b harness (`gate-4a3-commit6b-verifier.md` §1) was reused on the new archive with these stubs:
- a `measure_budgets.py` that honours `--out-path` and `--run-id`, writes a **fresh** report for this
  run carrying the `/api/saves` breach, and exits 1;
- an `npx` shim that writes the packaged report.

| verifier | exit | outcome |
|---|---:|---|
| 6b (`522bbfa4`, byte for byte) | **0** | a release record with `verdict: "FAILED_WAIVED"` |
| 6c | **1** | `a budget passed its STOP threshold: ['read_projection_ms'] (exit 1)`, and `docs/reviews` left **empty** |

---

## 4. Tests

- **`tests/test_save_validation_memo.py` (14).** Every save is made through the production path.
  The tests cover:
  - a hit validates nothing and returns identical records;
  - a **same-length tamper with its original nanosecond mtime restored** is revalidated and listed
    unloadable;
  - **CRLF and LF** files that decode alike are two keys;
  - byte-identical files are validated once;
  - unreadable and unparseable files are **re-read, re-decoded and re-parsed** on every listing,
    counted at those functions, and never memoized;
  - the listing never calls `read_save`;
  - symlinks and directories are still refused;
  - display name and mtime are fresh;
  - **`cap + 1`** costs one validation per listing;
  - retention follows deletes and rewrites;
  - concurrent misses on one key validate once, both when admitted and **with the memo full (cap
    0)**;
  - a failed owner lets the waiter compute;
  - admission under the cap is atomic across three concurrent distinct keys, synchronised with a
    barrier.
- **`tests/test_save_bytes.py` (11).** The parity matrix in §2.1.
- **`tests/test_release_verifier.py` (33, +6).**
  - `budget_verdict` passes only a clean run.
  - **Wiring:** `main` reaches the real `measure_budget_step`, a fresh `/api/saves` breach fails the
    run, and none of the three outputs is left behind.
  - The real step passes a clean fresh report.
  - A `PermissionError` on the second reservation strands nothing.
  - A failed second or third final write releases all three reservations and leaves an unrelated file
    byte-identical.

**Every memo guard bites.** Ten mutations were applied in place, one at a time, then restored and
confirmed with `cmp`. Each turned `test_save_validation_memo.py` red:

| mutation | tests failing |
|---|---:|
| key = hash of the decoded text, not the raw bytes | 2 |
| key = mtime and size | 7 |
| key = `save_id` | 6 |
| parse errors memoized | 1 |
| LRU eviction instead of the admission rule | 2 |
| no single-flight | 3 |
| no retention pruning | 1 |
| waiters read the memo, not the in-flight result | 1 |
| admission ignores admitted computations in flight | 1 |
| the listing reopens the file via `read_save` | 2 |

---

## 5. Gates

Each gate was run separately. Every exit status was captured as `$?` from the command itself, never
through a pipeline. The result column is the command's own final line, verbatim.

| command | exit | result |
|---|---:|---|
| `ruff format --check .` (backend) | 0 | `190 files already formatted` |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check` on `scripts/{verify_release,measure_budgets,build_release}.py` | 0 | `3 files already formatted` |
| `ruff check` on the same three scripts | 0 | `All checks passed!` |
| bare `mypy` | 0 | `Success: no issues found in 56 source files` |
| `pytest -q tests/test_save_validation_memo.py` | 0 | `14 passed in 1.93s` |
| `pytest -q tests/test_save_bytes.py` | 0 | `11 passed in 0.20s` |
| `pytest -q tests/test_release_verifier.py` | 0 | `33 passed in 0.32s` |
| `pytest -q tests/test_api_saves.py` | 0 | `53 passed, 1 warning in 1.44s` |
| `pytest -q tests/test_api_concurrency.py` | 0 | `27 passed, 1 warning in 2.95s` |
| `pytest -q tests/test_saves_atomic.py` | 0 | `10 passed in 0.19s` |
| `pytest -q tests/test_save_format.py` | 0 | `13 passed in 0.65s` |
| `pytest -q tests/test_api_outcome_labels.py` | 0 | `30 passed in 1.41s` |
| `pytest -q tests/test_live_server.py` | 0 | `18 passed in 9.52s` |
| `npm run generate:api` | 0 | `git status` shows no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical, 62 schemas / 13 paths / `0.23.0`** |
| `npm run build` | 0 | `dist/assets/index-CjkzPwt-.js 345.50 kB │ gzip: 99.65 kB`; `dist/` **byte-identical** (`diff -r`) to the SPA inside the 6c archive |
| `npm run check:bundle` | 0 | `check-bundle: OK -- no dev-raw-report sentinel in 1 built JS file(s); no sourcemap, no import.meta.env, index.html same-origin; initial JS 96.12 KiB gzip (level 9) of a 250 KiB budget, 153.88 KiB headroom.` |
| `build_release.py --epoch 1790730747 --check-reproducible` | 0 | two independent builds: `1dafdc746eee165e5056f6177bfe95b2a314b263ede12f0eead12f8525546c90` |
| `verify_release.py … --out gate-4a3-commit6c-release --budgets-out gate-4a3-commit6c-budgets --packaged-out gate-4a3-commit6c-packaged` | 0 | `verdict: "PASSED"`, `breaches: []` (§3.1) |
| full backend suite, `uv run pytest -q; echo "PYTEST_EXIT=$?"` | **0** | `36355 passed, 1 warning in 1404.76s (0:23:24)` — the 1 warning is the known `StarletteDeprecationWarning`; +31 from 36,324 = 14 + 11 + 6 |

### The tests in the three new or changed modules, by name (`pytest --collect-only -q`)

```
tests/test_save_validation_memo.py::test_a_second_listing_validates_nothing_and_returns_identical_records
tests/test_save_validation_memo.py::test_a_same_length_tamper_with_its_original_mtime_restored_is_revalidated
tests/test_save_validation_memo.py::test_crlf_and_lf_files_are_distinct_keys_although_they_decode_alike
tests/test_save_validation_memo.py::test_byte_identical_files_are_validated_once_and_listed_twice
tests/test_save_validation_memo.py::test_unreadable_and_unparseable_files_are_read_and_checked_on_every_listing
tests/test_save_validation_memo.py::test_the_listing_never_reopens_a_file_through_read_save
tests/test_save_validation_memo.py::test_symlinks_and_directories_named_like_saves_are_still_refused
tests/test_save_validation_memo.py::test_display_name_and_mtime_are_never_memoized
tests/test_save_validation_memo.py::test_one_file_over_the_cap_costs_one_validation_per_listing_not_a_rescan
tests/test_save_validation_memo.py::test_retention_follows_the_directory
tests/test_save_validation_memo.py::test_concurrent_misses_on_one_key_validate_once[admitted]
tests/test_save_validation_memo.py::test_concurrent_misses_on_one_key_validate_once[memo-full]
tests/test_save_validation_memo.py::test_when_the_owner_fails_a_waiter_computes_for_itself
tests/test_save_validation_memo.py::test_admission_under_the_cap_is_atomic_across_concurrent_distinct_keys
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[bom]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[crlf]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[empty]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[invalid-utf8]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[invalid-utf8-late]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[lf]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[lone-cr]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[missing]
tests/test_save_bytes.py::test_read_save_file_matches_the_6b_implementation[mixed]
tests/test_save_bytes.py::test_a_directory_path_fails_identically
tests/test_save_bytes.py::test_the_bytes_are_the_exact_on_disk_bytes
tests/test_release_verifier.py::test_a_stale_breach_report_cannot_stand_in_for_a_measurement_that_wrote_nothing
tests/test_release_verifier.py::test_a_report_from_another_run_is_refused
tests/test_release_verifier.py::test_a_report_without_a_run_id_is_refused
tests/test_release_verifier.py::test_exit_one_without_a_breach_is_refused
tests/test_release_verifier.py::test_exit_zero_with_a_breach_is_refused
tests/test_release_verifier.py::test_any_other_exit_status_is_refused
tests/test_release_verifier.py::test_a_fresh_breach_report_is_read_but_never_passes
tests/test_release_verifier.py::test_only_a_clean_measurement_passes
tests/test_release_verifier.py::test_a_fresh_clean_report_is_accepted
tests/test_release_verifier.py::test_every_output_name_is_required
tests/test_release_verifier.py::test_skip_browser_no_longer_exists
tests/test_release_verifier.py::test_unsafe_names_are_rejected[../x]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[a/b]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[/abs]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[x.json]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[X]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[a..b]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[.hidden]
tests/test_release_verifier.py::test_unsafe_names_are_rejected[a\\b]
tests/test_release_verifier.py::test_two_outputs_may_not_share_a_name[--out---budgets-out]
tests/test_release_verifier.py::test_two_outputs_may_not_share_a_name[--out---packaged-out]
tests/test_release_verifier.py::test_two_outputs_may_not_share_a_name[--budgets-out---packaged-out]
tests/test_release_verifier.py::test_safe_distinct_names_resolve_inside_the_reviews_directory
tests/test_release_verifier.py::test_an_existing_file_is_refused_and_left_byte_identical
tests/test_release_verifier.py::test_a_second_run_cannot_reserve_names_the_first_holds
tests/test_release_verifier.py::test_main_refuses_an_existing_output_before_reading_the_archive
tests/test_release_verifier.py::test_a_failed_run_removes_exactly_its_own_placeholders
tests/test_release_verifier.py::test_a_fresh_saves_breach_through_the_real_budget_step_leaves_no_artifacts
tests/test_release_verifier.py::test_the_real_budget_step_passes_a_clean_fresh_report
tests/test_release_verifier.py::test_a_reservation_failing_for_another_reason_strands_nothing
tests/test_release_verifier.py::test_a_failed_final_write_releases_all_three_reservations[2]
tests/test_release_verifier.py::test_a_failed_final_write_releases_all_three_reservations[3]
```

### The memo mutations, by exact text

| # | file | original | replaced with |
|---|---|---|---|
| 1 | `save_registry.py` | `key = hashlib.sha256(raw).hexdigest()` | `key = hashlib.sha256(decode_save_bytes(raw, path).encode()).hexdigest()` |
| 2 | `save_registry.py` | the same line | `key = f"{path.stat().st_mtime_ns}:{len(raw)}"` |
| 3 | `save_registry.py` | the same line | `key = save_id` |
| 4 | `save_registry.py` | the same line, and the `_compute_verdict` call | the key line followed by `errs = self.__dict__.setdefault("_errs", {})` / `if key in errs: raise errs[key]`; the call wrapped in `try: … except MandateError as exc: errs[key] = exc; raise` |
| 5 | `save_registry.py` | `admitted=len(self._memo) + admitted_in_flight < VALIDATION_MEMO_MAX`, and the store | `admitted=True`; before storing, `if len(self._memo) >= VALIDATION_MEMO_MAX: del self._memo[next(iter(self._memo))]` |
| 6 | `save_registry.py` | `flight = self._in_flight.get(key)` | `flight = None` |
| 7 | `save_registry.py` | `for stale in [key for key in self._memo if key not in seen_keys]:` | `for stale in []:` |
| 8 | `save_registry.py` | `if flight.verdict is not None: return key, flight.verdict` | `if key in self._memo: return key, self._memo[key]` |
| 9 | `save_registry.py` | `admitted=len(self._memo) + admitted_in_flight < VALIDATION_MEMO_MAX` | `admitted=len(self._memo) < VALIDATION_MEMO_MAX` |
| 10 | `save_registry.py` | `save = load_save_json(decode_save_bytes(raw, path), source=f"save:{save_id}")` | `save = self.read_save(save_id)` |

Each was applied alone to the working file, `pytest -q tests/test_save_validation_memo.py` was run, and
the file was restored and confirmed identical with `cmp`. The failing counts are in §4.

**Scope.** Changed: `backend/app/saves.py`, `backend/app/api/save_registry.py`, `scripts/verify_release.py`,
`backend/tests/test_release_verifier.py` and `docs/roadmap.md`. New: two test modules and this record with its three JSON
artifacts. No `app/simulation/` file, scenario, fixture, frozen plan, contract or earlier review artifact is in
the diff.

