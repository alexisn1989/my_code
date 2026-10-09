# Gate 4A3 R1 fix (release): the candidate build, measured

This commit adds records only: no code, test, threshold or cache change. It measures the **candidate**
release built from `5236ddb`, the R1 fix ([`gate-4a3-r1-fix.md`](gate-4a3-r1-fix.md)).

**R1 is reported per build:**

| build | R1 |
|---|---|
| **The approved playtest archive** (`f542cf28…`, built from `a322484`) | **Open and unchanged**, as measured in [`gate-4a3-r1-diagnosis.md`](gate-4a3-r1-diagnosis.md). Nothing here alters that archive or its approval |
| **The candidate** (`083c7a98…`, built from `5236ddb`) | **The warm path is improved, as measured below. The cold path is unchanged and still open.** A fresh process still validates every save once: 1.6–1.8 s for a root of 21 long saves |

**Whether the playtest moves to the candidate is your decision.** The roadmap's approved-build line is
not touched.

The dry run here is **internal**. It is not one of the five external playtesters.

## 1. The candidate archive

| step | result |
|---|---|
| `build_release.py --check-reproducible` at `5236ddb` (epoch `1791513998`) | exit 0. Two builds gave **identical bytes**: `083c7a984aedfa3823e128c2e160cd385135ac102ead60673fc3012268a8f490` |
| **fresh clone** at `5236ddb` (equal to the pushed head), both dependency links, the same epoch | exit 0. The **same** sha256 |
| the SPA vs `frontend/dist` (`diff -r`) | **identical**: `index-BumrhHF5.js`, `index-DVVZ_8_3.css`, the same bundle as the approved build's |

## 2. `verify_release`, once

```
python3 scripts/verify_release.py <archive 083c7a98…> \
  --out gate-4a3-r1fix-release --budgets-out gate-4a3-r1fix-budgets --packaged-out gate-4a3-r1fix-packaged
```

**The only attempt exited 0.** Verdict `PASSED`, `breaches: []`, and the release and budget records
share the run ID `5c5e355c…`.

**What it confirmed:**
- **Provenance:** the installed app selects `yaml.cyaml.CSafeLoader` with libyaml.
- **Checksums:** every file. Hostile archives are rejected.
- **Served:** `/` and `/api/scenarios` return 200, with the three scenarios.
- **Packaged turn:** passed, 13 requests, none off-origin.
- **F12:** a collision exits 1. SIGINT exits 0, and a restart serves 200.

| budget | median | worst | STOP |
|---|---:|---:|---:|
| new game | 14.88 ms | 54.80 ms | 300 ms |
| resolve, turns ≤ 20 | 63.99 ms | 120.67 ms | 500 ms |
| resolve, turns 21–40 | 143.14 ms | 181.74 ms | 800 ms |
| read projection | 5.44 ms | 67.90 ms | 200 ms |
| load + validate a 40-turn save | 146.88 ms | 173.34 ms | 1000 ms |
| projection payload | 2,752 B | 68,113 B | 204,800 B |

**The resolve rows are lower than in earlier single runs.** For comparison, the R2-fix candidate gave
127.62 and 290.52 ms, and UX-4h 103.69 and 243.13 ms. That is what removing the listing's validation
from each resolve would predict. **Each of those is a single run in a different session**, so the
matched comparison in §3 is the evidence, not this table.

## 3. The playtester's path and the worst case, against the approved build

**Method.** The diagnosis's harness (`gate-4a3-r1-diagnosis/tools/r1_http.py`) was run **unchanged**:
it is byte-identical to the committed copy, checked with `cmp`.
- **The install:** a fresh, checksum-verified README install of the candidate.
- **Repetitions:** 20 path repetitions and 10 worst-case repetitions, **all retained**.
- **Outcome:** every server exited 0, and every save listed as loadable.
- **Data:** `gate-4a3-r1fix-measurements/r1-http-candidate.json`.

**The comparison** is with the diagnosis's figures for the approved build. These are **two samples from
different sessions**, so a difference is called only where it is large against the run-to-run spread.

| step (median / p95 / max) | approved (`f542cf28…`) | **candidate (`083c7a98…`)** | reading |
|---|---|---|---|
| resolve, turns 1–5 (100 samples) | 39.73 / 56.67 / 71.25 ms | **26.40 / 37.80 / 44.44 ms** | lower |
| resolve, turns 6–10 (100 samples) | 82.74 / 108.36 / 116.31 ms | **48.66 / 81.39 / 111.75 ms** | **lower, and large against the spread**: the 20 per-run medians span 43.0–54.7 ms on the candidate and 71.6–107.7 ms on the approved build, ranges that do not overlap |
| save-as after 5 turns | 9.03 / 10.46 / 10.65 ms | 10.49 / 13.20 / 14.94 ms | about 1.5 ms higher, which fits the added read-back. Not tested |
| save-as after 10 turns | 10.99 / 13.26 / 15.57 ms | 12.52 / 16.04 / 18.93 ms | as above |
| listing after the first save | 5.13 / 6.72 / 7.75 ms | 5.37 / 6.20 / 6.78 ms | no difference called |
| listing after the second save | 6.34 / 7.45 / 7.69 ms | 5.85 / 7.93 / 23.55 ms | no difference called. One sample of 23.55 ms is recorded |
| **listing after a restart (cold)** | 67.09 / 95.19 / 122.64 ms | 65.47 / 81.11 / 90.89 ms | **unchanged, as designed** |
| **worst case: 21 saves, first listing (10 runs)** | 1,668.49 ms median (max 1,837.73) | **1,623.68 ms median (max 1,817.25)** | **unchanged, as designed** |

**Resolve medians by turn:**

| turn | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| approved (ms) | 25.8 | 29.4 | 38.2 | 44.8 | 52.8 | 87.3 | 66.0 | 77.5 | 81.4 | 87.3 |
| **candidate (ms)** | **19.6** | **21.8** | **25.6** | **28.7** | **32.8** | **37.4** | **42.0** | 76.2 | **47.8** | **52.8** |

The candidate's turn-8 median, 76.2 ms, stands out. I record it, and do not attribute a cause.

**Reading:**
- Each resolve now pays one validation, the engine's own guard on its input, instead of two.
- Resolve latency still grows with campaign length, because that remaining validation is linear in
  turns. It grows about half as fast.
- **Nothing here measures turns beyond 10 on the playtester path.** The `verify_release` rows in §2 are
  the only longer-campaign figures, and they are a single run.

## 4. The enforced internal dry run of the candidate

**Setup:**
- a fresh extract (`sha256sum -c` exit 0), then the README install on a clean path (exit 0);
- the server ran on `--port 48481` with a fresh save root.

**The run:**
```
MANDATE_DRYRUN_URL=http://127.0.0.1:48481 npm run dryrun:installed:r1fix
```
- It exited **0** (`1 passed (6.1s)`), and the record's `gate` is `4A3 R1-fix (enforced)`.
- The server was stopped by its **one** verified PID, 5510 (`/proc` cmdline and cwd checked). Its log
  ends "Finished server process [5510]".

**Results:**
- **Every preview agreed with its resolution:** turn 1 was decree and enacted; turns 2–5 were
  legislative and failed.
- There were **0 console errors** and **0 off-origin requests**.
- **Every turn's headline, consequences and outcome, and the History headline, are identical** to the
  R2-fix candidate's dry run.

The record is `gate-4a3-r1fix-dryrun.json`, with eight screenshots in `gate-4a3-r1fix-dryrun-shots/`.

## 5. Gates

Each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `build_release.py --check-reproducible` (`5236ddb`) | 0 | `083c7a98…` twice |
| fresh-clone `build_release.py --epoch 1791513998` | 0 | identical |
| `diff -r` SPA vs `dist` | 0 | identical |
| `verify_release.py … gate-4a3-r1fix-*` (the only attempt) | 0 | `PASSED` |
| `r1_http.py` (unchanged), 20 path and 10 worst-case repetitions | 0 | §3 |
| fresh extract and README install; `npm run dryrun:installed:r1fix` | 0 / 0 | `1 passed (6.1s)` |

**Not re-run.** The code gates for `5236ddb` stand as recorded in `gate-4a3-r1-fix.md`, including the
suite at 36,460 with one warning.

## 6. Scope

- **Added:**
  - this record;
  - `gate-4a3-r1fix-{release,budgets,packaged}.json`;
  - `gate-4a3-r1fix-dryrun.json` and `gate-4a3-r1fix-dryrun-shots/`;
  - `gate-4a3-r1fix-measurements/r1-http-candidate.json`.
- **Changed (the named exception):** the roadmap's R1 entry gains one item for the candidate, with a
  link. "**Open.**" is qualified as applying to the approved playtest archive.
- **Unchanged:** the approved playtest build and its roadmap line, and every other file.
