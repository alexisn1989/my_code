# Gate 4A3 R2 fix (release): the candidate build, measured

This commit adds records only: no code, test, threshold or cache change. It measures the **candidate**
release built from `a322484`, the R2 fix ([`gate-4a3-r2-fix.md`](gate-4a3-r2-fix.md)).

**R2 is reported per build:**

| build | R2 |
|---|---|
| **The approved playtest archive**, `058d779f…` built from `81f0648` | **Open and unchanged.** It still parses with the pure-Python loader. Its measurement stands as recorded in [`gate-4a3-r2-diagnosis.md`](gate-4a3-r2-diagnosis.md): 14 of 30 matched runs breached (95% CI 28.3–65.7%). Nothing here alters that archive or its approval. |
| **The candidate**, `f542cf28…` built from `a322484`, with libyaml | As measured below: **0 of 30** matched runs breached, with a 95% upper bound of **11.6%**. That bound is not zero risk. |
| **A supported Python-only install** (no libyaml) | The fallback keeps the slow path, so **R2 applies to it as to the approved archive**. `verify_release` refuses such an install as a release. |

**Whether the playtest moves to the candidate is your decision.** The roadmap's "approved playtest
build" line is not touched.

The dry run here is **internal**. It is not one of the five external playtesters.

## 1. The candidate archive

| step | result |
|---|---|
| `build_release.py --check-reproducible` from the clean tree at `a322484` (epoch `1791427147`) | exit 0. Two builds gave **identical bytes**: `f542cf281334a8f1aeb535864d63bb97e3b67bae617df820a2602f40cce7eae1` |
| **fresh clone** at `a322484` (checked equal to the pushed head), both dependency links, `--epoch 1791427147` | exit 0. The **same** sha256 |
| the SPA in the archive vs `frontend/dist` (`diff -r`) | **identical**: `index-BumrhHF5.js`, `index-DVVZ_8_3.css`, the same bundle as UX-4g's |

## 2. `verify_release`, once

```
python3 scripts/verify_release.py <archive f542cf28…> \
  --out gate-4a3-r2fix-release --budgets-out gate-4a3-r2fix-budgets --packaged-out gate-4a3-r2fix-packaged
```

**The only attempt exited 0.** Verdict `PASSED`, `breaches: []`, and the release and budget records
share the `runId` `fd3208fc…`.

**What it checked:**
- **The new loader requirement:** the installed app's provenance reports
  `yamlLoader: "yaml.cyaml.CSafeLoader"` and `yamlWithLibyaml: true`.
- **Install and provenance:** `app` comes from the new virtualenv.
- **Checksums:** every file. Hostile archives (absolute, traversal, symlink) are rejected.
- **Served:** `/` and `/api/scenarios` return 200, with the three scenarios.
- **Packaged turn:** passed, 13 requests, none off-origin.
- **F12:** a collision exits 1. SIGINT exits 0, and a restart serves 200.

| budget | median | worst | STOP |
|---|---:|---:|---:|
| new game | 15.30 ms | 51.53 ms | 300 ms |
| resolve, turns ≤ 20 | 127.62 ms | 242.37 ms | 500 ms |
| resolve, turns 21–40 | 290.52 ms | 391.68 ms | 800 ms |
| read projection | 8.47 ms | **95.86 ms** | 200 ms |
| load + validate a 40-turn save | 195.58 ms | 229.62 ms | 1000 ms |
| projection payload | 2,752 B | 68,113 B | 204,800 B |

**`/api/scenarios`:** median 32.35 ms, worst 95.86 ms.

**Other numbers moved, and I am not attributing them.**
- New game fell from UX-4h's median of 47.46 ms to 15.30 ms, which fits a game start no longer paying
  the Python parse.
- Several rows that do not touch YAML ran **slower** than in UX-4h's single run: resolve medians of
  127.62 and 290.52 ms against 103.69 and 243.13, `decision-options` 12.44 ms against 6.85, and load
  195.58 ms against 126.97.
- These are single runs in different container sessions. Nothing here attributes those differences
  to the build, and nothing on those paths changed.

## 3. The loader the application selected, measured

**The harness.** The new `phases_selected.py` ran on a `git archive` export of `a322484`, with its
build identity asserted. It **reads the app's own `_SAFE_LOADER`** rather than naming a loader. The
diagnosis's `phases.py`, which calls `yaml.safe_load` by name, is kept unchanged as evidence.

**Identity:**
- the selected loader is `yaml.cyaml.CSafeLoader`, with `libyaml: true`;
- `app` was imported from the export.

**Timings.** Each figure is the sum of the three files' medians, over 200 iterations per phase:

| phase | sum of medians |
|---|---:|
| **parse with the selected loader** | **14.79 ms** |
| control: pure-Python `SafeLoader` | 139.26 ms |
| control: `CSafeLoader` | 14.42 ms |
| the app's whole `load_scenario_text` (parse + validate + state + invariants) | 17.10 ms |

**Reading.** Both controls were measured in the same process and container. The selected loader
matches the C control and is about 9× faster than the Python one. The per-file figures are in
`gate-4a3-r2fix-measurements/phases-selected-a322484.json`.

## 4. The release check's own workload, on the candidate: 30 fixed runs

**Method.** The diagnosis's `tools/budgets30.py` (byte-identical to its committed copy) ran the real
`scripts/measure_budgets.py`, unmodified, **a fixed 30 times**.
- Each run used a fresh server from a fresh, checksum-verified README install of the candidate, with
  a fresh port and an empty save root.
- **Order within each run:** new games, turn-0 reads, 40 resolves, the read block (`/api/scenarios`
  last), then save and load.
- **All 30 runs are retained.** Every run and every server exited 0. Each server was stopped by the
  one PID the driver launched, after a `/proc` check.
- Runs took 12.1–14.5 s each, with a 1-minute load of 0.89–1.06.

**Result: 0 of 30 runs breached any budget.**
- **`/api/scenarios`:** medians per run 18.88–24.23 ms (median of medians 20.91). Its worst per run
  ranged from 45.10 to 80.91 ms.
- **The read row's worst per run** ranged from 52.14 to 86.09 ms. It came from `/api/scenarios` in 15
  runs and from `/api/game/history` in the other 15.
- **Breach rate:** 0 of 30, with a 95% Clopper–Pearson interval of **0–11.6%**. That is an upper bound,
  not zero risk, and it is conditional on this machine and this workload.

**Comparison with the approved archive, fixed in advance as a two-sided Fisher exact test at α = 0.05.**
- The approved archive breached in 14 of 30 runs, from the diagnosis; the candidate in 0 of 30.
- **p = 1.7 × 10⁻⁵, so fewer breaches is supported.**
- **The limit on that comparison:** the two samples ran in **different container sessions**, so the
  test alone does not separate build from environment.
- What does speak to the mechanism is §3: the C and Python loaders measured side by side in this one
  container, about 9× apart. The parse is the step the diagnosis attributed the time to.

## 5. The enforced internal dry run of the candidate

**Setup:**
- a fresh extract (`sha256sum -c` exit 0), then the README install on a clean path (exit 0);
- `app` and the C loader came from that directory's `.venv`;
- the server ran on `--port 48471` with a fresh save root.

**The run:**
```
MANDATE_DRYRUN_URL=http://127.0.0.1:48471 npm run dryrun:installed:r2fix
```
- It exited **0**, and the record's `gate` is `4A3 R2-fix (enforced)`.
- The server was stopped by its **one** verified PID, 3370 (`/proc` cmdline and cwd checked). Its log
  ends "Finished server process [3370]".

**Results:**
- **Every preview agreed with its resolution:** turn 1 was decree and `enacted_by_decree`; turns 2–5
  were legislative and `failed_legislative`.
- There were **0 console errors** and **0 off-origin requests**.
- **All five turns' headlines, consequences and outcomes are identical** to UX-4h's dry run of the
  approved build. That is consistent with the byte-identical new-campaign test.

The record is `gate-4a3-r2fix-dryrun.json`, with eight screenshots in `gate-4a3-r2fix-dryrun-shots/`.

## 6. Gates

Each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `build_release.py --check-reproducible` (`a322484`) | 0 | `f542cf28…` twice |
| fresh-clone `build_release.py --epoch 1791427147` | 0 | identical |
| `diff -r` SPA vs `dist` | 0 | identical |
| `verify_release.py … gate-4a3-r2fix-*` (the only attempt) | 0 | `PASSED`; loader `yaml.cyaml.CSafeLoader` |
| `phases_selected.py` (export of `a322484`) | 0 | §3 |
| `budgets30.py`, 30 fixed runs | 0 | 0 of 30 breached |
| fresh extract and README install; `npm run dryrun:installed:r2fix` | 0 / 0 | `1 passed (7.8s)` |

**Not re-run.** The code gates for `a322484` stand as recorded in `gate-4a3-r2-fix.md`, including the
suite at 36,437.

## 7. Scope

- **Added:**
  - this record;
  - `gate-4a3-r2fix-{release,budgets,packaged}.json`;
  - `gate-4a3-r2fix-dryrun.json` and `gate-4a3-r2fix-dryrun-shots/`;
  - `gate-4a3-r2fix-measurements/`, holding `tools/phases_selected.py`, `exports-a322484.txt`,
    `phases-selected-a322484.json` and `budgets30/` (30 runs plus the log).
- **Changed (the named exception):** the roadmap's R2 entry, and nothing else in it.
  - "**Open.**" now reads "**Open on the approved playtest archive.**".
  - The stale "Fix options: these await a separate review" item is replaced by one item for the
    candidate, with a link.
  - The "approved playtest build" line and the approved archive's R2 status are unchanged.
- **Unchanged:** every other file.
