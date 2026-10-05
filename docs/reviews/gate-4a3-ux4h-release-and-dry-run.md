# Gate 4A3 UX-4h: release verification and the enforced internal dry run, for the UX-4g build

This commit adds records only: no application, backend, scenario, contract or threshold change. It
verifies the release built from `81f0648` (UX-4g). It then walks that build through the interface,
**installed from its own release archive**, with the enforcing dry run.

UX-4g changed the shipped bundle, so this record **supersedes UX-4f's release evidence**
(`gate-4a3-ux4f-*`) as the description of the final build. UX-4f's files, including its R2 diagnostic
runs and the correction of them in `gate-4a3-ux4g-corrections.md` §3, are unchanged.

**The dry run is INTERNAL. It is not one of the five external playtesters, and it does not count
toward them or toward the playtest's pass criterion.** That playtest, its protocol and its pass
criterion are yours.

## 1. The archive: rebuilt, reproducible, and the same from a fresh clone

| step | result |
|---|---|
| `build_release.py --check-reproducible` from the clean tree at `81f0648` (epoch = HEAD's commit time, `1791162475`) | exit 0. Two independent builds produced **identical bytes**: `058d779ff5a5d09b9a78999bd21055b17c519422b51a6e2f6ff49142e1747740` |
| **fresh clone** at `81f0648` (checked equal to the pushed branch head), `build_release.py --epoch 1791162475` | exit 0. The **same** sha256, `058d779f…7740` |
| the SPA inside the archive vs the gated `frontend/dist` (`diff -r`) | **identical** (exit 0). JS `index-BumrhHF5.js`, CSS `index-DVVZ_8_3.css`, the build every UX-4g browser gate ran against |

**A setup slip, recorded.** The first fresh-clone build exited 1: `tsc` could not find
`frontend/tools/openapi-gen/node_modules`. I had linked only `frontend/node_modules` into the clone.
UX-4f's clone had linked both, since dependencies are not sources and are not committed. Linking the
second directory too and re-running gave the result above. The failed attempt wrote no archive.

## 2. `verify_release.py`, once

```
python3 scripts/verify_release.py <archive 058d779f…> \
  --out gate-4a3-ux4h-release --budgets-out gate-4a3-ux4h-budgets --packaged-out gate-4a3-ux4h-packaged
```

**Exactly one attempt, as planned.** It exited **0**, with verdict `PASSED` and `breaches: []`. The
release and budget records carry the same `runId` (`d9590709…`).
- **Checksums:** every file. Hostile archives (an absolute path, a parent traversal, a symlink) are
  all rejected.
- **Install:** the README's install line, verbatim, on a path stripped of the repository.
  - **Provenance:** `app` imports from the new virtualenv's site-packages.
  - `/` and `/api/scenarios` return 200, with exactly `decree_state`, `deficit_demo` and
    `tiny_valid`.
- **Packaged turn:** 1 passed; 13 requests, **none off-origin**.
- **F12 (port handling):** a second launch on the bound port exits 1 and names the port. SIGINT stops
  the server (0), and a restart on the same port serves 200.

| budget | median | worst | STOP | |
|---|---:|---:|---:|---|
| new game | 47.46 ms | 65.52 ms | 300 ms | OK |
| resolve, turns ≤ 20 | 103.69 ms | 214.71 ms | 500 ms | OK |
| resolve, turns 21–40 | 243.13 ms | 328.10 ms | 800 ms | OK |
| read projection | 4.41 ms | 160.74 ms | 200 ms | OK |
| load + validate a 40-turn save | 126.97 ms | 180.79 ms | 1000 ms | OK |
| projection payload | 2,752 B | 68,113 B | 204,800 B | OK |

**Per endpoint (median / worst):**
- `/api/scenarios`: 131.73 / 160.74 ms, the read row's worst;
- `/api/game/history`: 41.42 / 47.80 ms;
- `/api/game/decision-options`: 6.85 / 9.56 ms;
- `/api/saves`: 6.17 / 7.98 ms;
- every other endpoint is under 4 ms.

**R2 stays open.**
- `/api/scenarios` medians in the two `verify_release` runs are 128.24 ms (UX-4f) and 131.73 ms
  (here). That is above the 107–115 ms seen in UX-4f's diagnostic runs.
- This one pass does not change the UX-4g correction: **run-to-run variation observed; cause
  unresolved; regression not ruled out.**
- No code, caching or threshold change was made, and unchanged code was not re-run for a better
  timing.

**R1, R3 and R4:** unchanged, as recorded in UX-4f §3.

## 3. The enforced internal dry run, through the interface of the installed build

**How it ran:**
- The archive was extracted fresh into a new scratch directory; `sha256sum -c SHA256SUMS` exited 0.
- The README's install commands ran on a path stripped of the repository (exit 0). `app` imported
  from that directory's own `.venv`.
- The README's run command started the server with `--port 48461` and a fresh save root.
- Then:
  ```
  MANDATE_DRYRUN_URL=http://127.0.0.1:48461 npm run dryrun:installed:ux4h
  ```
  This sets `MANDATE_DRYRUN_REQUIRED=1` and `MANDATE_DRYRUN_GATE="4A3 UX-4h (enforced)"`. It ran at
  1440×900, exited **0**, and reported `1 passed (5.4s)`. It wrote `gate-4a3-ux4h-dryrun.json`, whose
  `gate` field reads `4A3 UX-4h (enforced)`, and `gate-4a3-ux4h-dryrun-shots/`.
- **What the run enforces:**
  - each preview agrees with its resolution;
  - the decree preview was affordable and enacted;
  - there are no console errors and no off-origin requests.
- **Stopping the server, with the UX-4f gap closed.** Before any signal, I searched `/proc` for the
  server's exact command line, excluding shells. **Exactly one** process matched:
  - PID 6424;
  - cwd: the scratch install;
  - command: `.venv/bin/python3.11 .venv/bin/mandate-gui … --port 48461 --save-root ../saves`.

  SIGINT went to that PID alone. Its log ends "Finished server process [6424]", and it exited 0.

| turn | route | preview `would_pass` | resolved outcome | agreed | confirmation | headline | visible / routine / Trace |
|---:|---|---|---|---|---|---|---|
| 1 | decree | true (affordable) | `enacted_by_decree` | yes | "Resolve turn 0 with 1 staged action?" | The budget was enacted by decree. The legislature was bypassed. | 14 / 5 / 19 |
| 2 | legislative | false | `failed_legislative` | yes | "Resolve turn 1 with 1 staged action?" | The budget was blocked. | 10 / 6 / 16 |
| 3 | legislative | false | `failed_legislative` | yes | "Resolve turn 2 with 1 staged action?" | The budget was blocked. | 10 / 6 / 16 |
| 4 | legislative | false | `failed_legislative` | yes | "Resolve turn 3 with 1 staged action?" | The budget was blocked. | 13 / 6 / 19 |
| 5 | legislative | false | `failed_legislative` | yes | "Resolve turn 4 with 1 staged action?" | The budget was blocked. | 12 / 6 / 18 |

**The UX-4g corrections, as installed:**
- **Turns 2–5:** the second line is "Lower chamber blocked the budget: 45 supporting votes; 51
  required—6 short."
- **Negative relationships** keep their sign, for example "Reform Opposition Main: relationship
  -80.00% → -83.50% (-3.50 points)." on turn 1.
  - These values are below −1%, which displayed correctly before UX-4g too. **The walk did not reach
    the −99…−1 bps range the fix is for.** That range is proved by the UX-4g unit and view tests
    (`format/percent.test.ts`, `greybox/ux4g.test.tsx`), not by this walk.

**Every preview agreed with its resolution.** History re-read turn 1's headline exactly. There were
**0 console errors** and **0 off-origin requests**.

The screenshots are in `gate-4a3-ux4h-dryrun-shots/`:
- the Dashboard;
- each turn's result;
- History on turn 1;
- the Economy summary.

## 4. Gates

Each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `build_release.py --check-reproducible` (clean tree, `81f0648`) | 0 | `058d779f…7740` twice |
| `build_release.py --epoch 1791162475` (fresh clone; first attempt missing a dependency link) | 1, then 0 | §1; `058d779f…7740`: identical |
| `diff -r` archive SPA vs `frontend/dist` | 0 | identical |
| `verify_release.py … gate-4a3-ux4h-*` (the only attempt) | 0 | `PASSED`, `breaches: []`; read worst 160.74 ms |
| fresh extract `sha256sum -c`; README install (clean path) | 0 / 0 | `app` from the archive's `.venv` |
| `npm run dryrun:installed:ux4h` (enforcing) | 0 | `1 passed (5.4s)` |

**Not re-run, and why.** No source changed after `81f0648`, so UX-4g's unit tests, browser gates and
full suite (36,405) stand as recorded in `gate-4a3-ux4g-corrections.md`.

## 5. Scope

- **Added:**
  - this record;
  - `gate-4a3-ux4h-{release,budgets,packaged}.json`;
  - `gate-4a3-ux4h-dryrun.json` and `gate-4a3-ux4h-dryrun-shots/`.
- **Unchanged:** everything else, including every earlier artifact.

The roadmap stays **"internally complete; externally pending"**. The five-person playtest is the
remaining external step, and it is yours.
