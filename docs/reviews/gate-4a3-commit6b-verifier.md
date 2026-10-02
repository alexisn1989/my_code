# Gate 4A3 Commit 6b — the release verifier: a fresh report per run, and no overwritten evidence

**Subject:** `Gate 4A3 (6b/6): tie each budget report to its run, and stop the verifier overwriting evidence`
**Parent:** `fdad835900b1551740f52275fdb8878d7f8685e8` (Commit 6a), not amended.
**Evidence from this run:** `gate-4a3-commit6b-release.json`, `gate-4a3-commit6b-budgets.json`,
`gate-4a3-commit6b-packaged.json`.

An audit of 6a confirmed the waiver record, the artifact comparisons and the twelve recorded exit codes.
It found the verifier itself still untrustworthy in two ways, plus one contradiction in the roadmap. A
review of the plan for this commit added three more requirements. This commit fixes all of them. Commit
6 and 6a evidence is left byte-identical.

---

## 1. The defects, reproduced against the real 6a script

`read_fresh_budgets` does not exist in 6a, so a unit test of the new function cannot prove the old
failure. Both defects were instead reproduced by running **the 6a verifier itself, byte for byte**
(`git show fdad8359:scripts/verify_release.py`, confirmed with `cmp`), end to end against the real
archive (SHA-256 `54290cca…`).

### The harness (scratch directory outside the repository; not committed as a tool)

```sh
R=<scratch>/repro6a; mkdir -p $R/scripts $R/docs/reviews $R/frontend $R/shim
git show fdad8359:scripts/verify_release.py > $R/scripts/verify_release.py      # the real 6a verifier
cat > $R/scripts/measure_budgets.py <<'EOF'                                      # dies before writing
import sys
print("stub measure_budgets: dying before writing any report", file=sys.stderr)
raise SystemExit(1)
EOF
git show fdad8359:docs/reviews/gate-4a3-commit6a-budgets.json \
    > $R/docs/reviews/stale-budgets.json                                         # a REAL breach report
printf '#!/bin/sh\necho "npx shim: browser step stubbed"\nexit 0\n' > $R/shim/npx; chmod +x $R/shim/npx
cd $R && PATH=$R/shim:$PATH python scripts/verify_release.py <archive> \
    --out repro-release --budgets-out stale-budgets
```

The 6a verifier takes `REPO_ROOT` from its own location (`parents[1]`), so it treats the scratch
directory as the repository. Every step before the budgets runs for real:
- safe inspection;
- checksums;
- the README's install line, from PyPI into a fresh virtualenv;
- provenance;
- serving.

The F12 steps after the budgets also run for real. Only the browser turn (an `npx` shim) and the
measurement (the stub) are replaced.

### Results

| run | exit | what it recorded |
|---|---:|---|
| **6a**, stale report present, measurement writes nothing | **0** | `"budgets": {"exit": 1, "report": [], "breaches": ["read_projection_ms"], "verdict": "FAILED_WAIVED", "waivedEndpoint": "/api/saves", …}` — a waiver granted for a measurement that never ran |
| **6a**, `--skip-browser` | **0** | a release record with **no `budgets` and no `packagedTurn` key**, i.e. a passing exit for a run that skipped both |
| **6b**, same harness, fresh names, the same stale file beside them | **1** | `verify_release: the measurement wrote no report: exit 1`; no release, budget or packaged file left behind |
| **6b**, `--budgets-out stale-budgets` (an existing file) | **1** | `… stale-budgets.json already exists; pass new output names …`, refused at reservation before the archive was read |
| **6b**, `--skip-browser` | **2** | `error: unrecognized arguments: --skip-browser` |

For the 6b run, the `npx` shim also writes `{}` to `MANDATE_PACKAGED_OUT_PATH`, because 6b requires a
packaged report before it reaches the budget step. The stale file's SHA-256 is identical before and
after every run: `63ceb9ee…12a6be8a`.

---

## 2. The fixes

### 2.1 A fresh budget report, tied to the run

- `measure_budgets.py` gains two arguments:
  - `--out-path`, an absolute file, created exclusively;
  - `--run-id`, recorded in the report as `runId`.
- The verifier draws `secrets.token_hex(16)` per run and records it as `runId` in the release record.
  It points the measurement at `<its own temporary directory>/budgets.json`. No earlier file can exist
  there.
- New `read_fresh_budgets(returncode, path, run_id)` refuses:
  - a missing report ("the measurement wrote no report: exit N");
  - a report whose `runId` differs or is absent;
  - an exit status the report does not explain: exit 0 with breaches, exit 1 without, or any other
    exit.
- Only a report that passes is used for the verdict, and only that validated text is copied into
  `docs/reviews`.
- `FAILED_WAIVED` therefore needs, from this run:
  - a fresh report;
  - a real breach;
  - exactly the waived endpoint.

### 2.2 No default names; safe, distinct, exclusively created outputs

- `--out`, `--budgets-out` and `--packaged-out` are **required**. 6a's defaults named Commit 6's
  committed artifacts.
- **Name rule.** Each name must match `[a-z0-9][a-z0-9.-]*`, contain no `..`, and not end in `.json`.
  The resolved `docs/reviews/<name>.json` must have `docs/reviews` as its parent.
- **Distinct names.** All three names must be pairwise distinct.
- **Exclusive reservation.** All three files are created with `open(path, "x")` **before the archive
  is read**.
  - An existing file is refused, whether committed evidence or another run's output, so a concurrent
    run with the same names loses at reservation.
  - A refused reservation removes what that call created.
  - Any failure after reservation deletes exactly this run's placeholders and nothing else.
- **No child writes into `docs/reviews`.** Both child reports go to this run's temporary directory:
  - the packaged spec receives `MANDATE_PACKAGED_OUT_PATH` and writes with `flag: "wx"`;
  - the budget report goes there via `--out-path`.

  The verifier copies each child report into its reservation only after the run completes.
- **Standalone use of the children.**
  - `packaged-instance.spec.ts` requires `MANDATE_PACKAGED_OUT_PATH` or `MANDATE_PACKAGED_OUT`, with no
    fallback name. `MANDATE_PACKAGED_OUT` gets the same name rule, and every write is `wx`.
  - `measure_budgets.py --out` gets the same name rule and an exclusive write.

### 2.3 `--skip-browser` removed

In 6a it skipped the browser turn **and** the budgets, yet wrote a release record and exited 0 (§1).
Marking such output "incomplete" would still leave a record on disk that looks like a release record.
Removing the flag leaves no way to obtain a release record without both steps.

### 2.4 The roadmap's definition

"Internally complete" now reads: every automated gate is green **except one budget**, `GET /api/saves`
read latency, which FAILED and is waived by user ruling, and the playtest is prepared. The definition no
longer contradicts the waiver it sits beside.

---

## 3. Permanent tests — `backend/tests/test_release_verifier.py` (27)

The script is loaded by path with `importlib`, so there is no new dependency. The tests cover:

- **The stale-report scenario.** A real-shaped breach report is planted, and `ruled_breach_only` is
  asserted True on it, so the bait is tempting. The run's own path is empty → refused.
- **Run identity:** a foreign `runId` and an absent `runId` are each refused.
- **Exit/breach agreement:** exit 1 with no breach, exit 0 with a breach, and exit 2 are each refused.
- **Acceptance:** a fresh waived report and a fresh clean report are each accepted.
- **Arguments:** all three names are required, and `--skip-browser` is rejected.
- **Names:**
  - `../x`, `a/b`, `/abs`, `""`, `x.json`, `X`, `a..b`, `.hidden` and `a\b` are each rejected;
  - each of the three name pairs is rejected when equal;
  - safe names resolve inside the reviews directory.
- **Reservation:**
  - an existing file is refused and left byte-identical;
  - a second reservation of held names fails, which is the race, and removes nothing of the first;
  - `main` refuses an existing output before reading the archive;
  - a failed run removes exactly its own three placeholders and leaves an unrelated file intact.

**Each guard was proved to bite.** Seven mutations were applied in place, one at a time, then restored
and confirmed byte-identical with `cmp`. Every one turned the module red:

| mutation | tests failing |
|---|---:|
| the missing-report check falls back to a stale file | 1 |
| no `runId` check | 2 |
| no exit/breach agreement | 1 |
| no distinct-name check | 3 |
| no name rule | 9 |
| `open(path, "a")` instead of `"x"` | 3 |
| no cleanup on failure | 1 |

---

## 4. The run under Commit 6b's names

`verify_release.py dist/mandate-gui-0.1.0.tar.gz --out gate-4a3-commit6b-release --budgets-out
gate-4a3-commit6b-budgets --packaged-out gate-4a3-commit6b-packaged` exited **0**.

**The first attempt exited 1**, before the packaged turn: Playwright's shared web server could not start
because this container had been reset and the SPA was not yet built. That is an environment failure,
not a verifier failure. The run deleted its three reservations, exactly as §2.2 requires, and left
nothing behind. After `npm run build`, the built `dist/` is **byte-identical** (`diff -r`) to the SPA
inside the archive, and the second attempt is the result recorded here.

| check | result |
|---|---|
| archive SHA-256 | `54290ccaebc66f3146b75e2869921972008570b7d9807977c83f4ed9eba7379b` — unchanged, and rebuilt twice from this container (`--check-reproducible`) both before and after the edits |
| `runId` | `3c80edf9ea685021ded089f38a2a1dd6`, identical in the release record and the budget report |
| provenance | `app` imported from the new virtualenv's `site-packages` |
| packaged turn | 13 requests, **0 off-origin**; feedback worst 5.9 ms against a 200 ms STOP |
| F12 | second launch exit 1; SIGINT exit 0; restart on the same port served 200 |
| budgets | `verdict: "FAILED_WAIVED"`, `waivedEndpoint: "/api/saves"` |

| budget | median | worst | STOP |
|---|---:|---:|---:|
| new game | 69.39 ms | 131.0 ms | 300 ms |
| resolve, turns ≤ 20 | 125.98 ms | 229.01 ms | 500 ms |
| resolve, turns 21–40 | 300.83 ms | 434.75 ms | 800 ms |
| read projection | 5.52 ms | **283.68 ms** | 200 ms — **FAILED, waived** (`/api/saves` only) |
| load + validate 40-turn save | 142.1 ms | 185.15 ms | 1000 ms |
| projection payload | 2,752 B | 68,113 B | 204,800 B |

Per endpoint, read projections (median / worst, ms):
- `/api/saves` 186.71 / 283.68, the one waived endpoint;
- `/api/scenarios` 115.81 / 154.68, under its STOP and **not** waived;
- every other endpoint has a worst ≤ 81.6.

**The refusals, against real files:**
- A second invocation with the **same three names** exited 1 at reservation: "…gate-4a3-commit6b-
  release.json already exists…". It ran before anything was installed or measured, and all three 6b
  files are byte-identical afterwards (`sha256sum -c`).
- An invocation naming **committed Commit 6 evidence** (`--out gate-4a3-commit6-release`) was refused
  the same way, and nothing in `docs/reviews` changed.

---

## 5. Recorded, not changed

**The browser exit codes in `gate-4a3-commit6-browser-reruns.json` are transcribed attestations.**
- The twelve exit codes were transcribed from harness outputs: the `/tmp/pw*_*.log` files, the task
  `.output` files, and, for the 5b accessibility run, the session transcript.
- The original harness files were lost when the container was reset after 6a.
- They cannot be regenerated. Re-running the browser gates now would produce new evidence for the
  current tree, not the original runs.
- The record stands as transcription, and this document says so rather than upgrading it.

**The same default-name hazard remains elsewhere, and is owed.**
- Several npm scripts and e2e specs still default their artifact env vars to earlier commits' names.
  For example, `verify:fixes` → `MANDATE_VERIFY_OUT` → Commit 3's artifact.
- They are guarded today only by the one-script-per-commit rule.
- Out of scope for this verifier-only correction.

**Other items still owed:**
- the five-stranger playtest;
- the `/api/saves` fix;
- T2;
- D1;
- the three divergences carried from the characters slice.

---

## 6. Gates

Each gate was run separately. Every exit status was captured as `$?` from the command itself, never
from a pipeline.

| gate | result |
|---|---|
| `ruff format --check .` (backend) | 188 files formatted |
| `ruff check .` (backend) | passed |
| `ruff format --check` / `ruff check` on `scripts/{verify_release,measure_budgets,build_release}.py` | passed |
| bare `mypy` | 56 source files, no issues |
| focused: `test_release_verifier.py` + `test_live_server.py` | 45 passed |
| `build_release.py --epoch 1790730747 --check-reproducible`, before and after the edits | `54290cca…` both times, two independent builds each |
| `npm run build` / `check:bundle` | clean; 96.12 KiB gzip of 250; `dist/` byte-identical to the archive's SPA |
| `verify_release.py` under 6b names | exit 0, `FAILED_WAIVED` (§4) |
| §1 reproductions | 6a: stale report → exit 0 `FAILED_WAIVED`; `--skip-browser` → exit 0 with no budgets. 6b: exit 1, exit 1, exit 2 |
| guard mutations | 7 of 7 caught (§3) |
| **full backend suite** | **36,324 passed**, 0 failed, 1 known warning, `PYTEST_EXIT=0`, 23:47. The +27 is exactly `test_release_verifier.py` |

**Scope:**
- no `app/` file, scenario, fixture, contract, frozen plan, or Commit 6/6a artifact is in the diff;
- the e2e change touches no shipped source.

`ruff check` over **all** of `scripts/` reports one pre-existing issue, `N818` on `SmokeFailure` in
`scripts/smoke_gui.py`. It predates this commit, and that file is untouched.
