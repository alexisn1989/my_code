# Gate 4A3 UX-4f: release re-verification, and the enforced internal dry run

This commit adds records only: no application, backend, scenario, contract or threshold change. It
re-verifies the release for the final build, `44fbd5a` (UX-4e). It then walks that build through the
interface, **installed from its own release archive**, with the dry run that UX-4e made enforcing.

It **supersedes UX-4d's release evidence** (`gate-4a3-ux4-*`, `gate-4a3-ux4d-release-and-dry-run.md`)
as the description of the final build. UX-4e changed the shipped bundle, so UX-4d's archive is no
longer the build that ships. UX-4d's files are preserved byte-identical.

**The dry run is INTERNAL. It is not one of the five external playtesters, and it does not count
toward them or toward the playtest's pass criterion.** That playtest, its protocol and its pass
criterion are unchanged, and they are yours.

## 1. The archive: rebuilt, reproducible, and the same from a fresh clone

| step | result |
|---|---|
| `build_release.py --check-reproducible` from the clean tree at `44fbd5a` (epoch = HEAD's commit time, `1791081047`) | exit 0. Two independent builds produced **identical bytes**: `09d21997e443cac10f9cb2d410d7d5964e86f88ea84d2713a85cf5a9e41a71ba` |
| **fresh clone** of the pushed branch at `44fbd5a`, `build_release.py --epoch 1791081047` | exit 0. The **same** sha256, `09d21997…a71ba` |
| the SPA inside the archive vs the gated `frontend/dist` (`diff -r`) | **identical** (exit 0). JS `index-CxgBPlll.js`, CSS `index-DVVZ_8_3.css` |

The archive lives outside the repository and is not committed. Its hash is the record.

## 2. `verify_release.py`: a STOP breach, diagnosed, then one re-run

### 2.1 The first run failed (stop-and-report)

```
python3 scripts/verify_release.py <archive 09d21997…> \
  --out gate-4a3-ux4f-release --budgets-out gate-4a3-ux4f-budgets --packaged-out gate-4a3-ux4f-packaged
```

**Exit 1:** "a budget passed its STOP threshold: ['read_projection_ms']". The verifier writes nothing
on failure, so none of the three names was written. It printed only the breach name, not the figure:
**that run's exact worst sample is not recorded.** The 206.47 ms below comes from the first
diagnostic run, made afterwards against the same archive.

Under frozen §18, I stopped and reported. I made no code change, added no caching and did not move
the threshold.

### 2.2 Diagnosis: R2 variance in `/api/scenarios`, not a UX-4e regression

I installed the UX-4e archive and the UX-4d archive (`d4a5459e…`), each under its own README commands,
on separate ports. Then I ran `scripts/measure_budgets.py` against them, alternating builds, writing
only to scratch. The JSONs are committed here, unchanged, in **`gate-4a3-ux4f-r2-ab/`**.

| run (file) | build | `/api/scenarios` median / worst (ms) | `/api/game/history` median / worst (ms) | breaches |
|---|---|---:|---:|---|
| `measure-ux4e-1` | UX-4e | 110.54 / **206.47** | 39.25 / 55.66 | `read_projection_ms` |
| `measure-ux4e-2` | UX-4e | 108.73 / 136.10 | 36.08 / 53.62 | none |
| `ab-ux4d-1` | UX-4d | 110.34 / 132.20 | 35.29 / 55.07 | none |
| `ab-ux4e-1` | UX-4e | 114.61 / 143.25 | 37.09 / 58.96 | none |
| `ab-ux4d-2` | UX-4d | 110.83 / 170.42 | 35.90 / 37.57 | none |
| `ab-ux4e-2` | UX-4e | 107.40 / 196.78 | 34.63 / 59.89 | none |
| `ab-ux4d-3` | UX-4d | 108.55 / 137.72 | 39.51 / 57.50 | none |
| `ab-ux4e-3` | UX-4e | 113.27 / 160.28 | 39.62 / 52.35 | none |

**Reading:**
- **The medians do not separate:** `/api/scenarios` is about 107–115 ms on both builds, and history
  is about 35–40 ms. UX-4e's history and turn-result changes did not make reads slower.
- **The worst sample varies from run to run on both builds:** UX-4d 132–170 ms, UX-4e 136–206 ms. In
  each A/B round UX-4e's worst was 11–26 ms higher. Three rounds cannot tell that apart from the spread
  within each build, and **it is not ruled out**.
- Every other read endpoint stays under 10 ms, apart from history.

**Conclusion:** this is **R2**, with less headroom than it was recorded with.

### 2.3 The re-run (one attempt, on your direction to continue)

The same command and the same unused names, on the same archive, re-hashed first. **Exactly one
attempt** was made; a second breach would have been reported again, not retried.

**Exit 0, verdict `PASSED`, `breaches: []`.** The release and budget records carry the same
`runId` (`2a97be06…`).
- **Checksums:** every file. Hostile archives (an absolute path, a parent traversal, a symlink) are
  all rejected.
- **Install:** the README's install line, verbatim, on a path stripped of the repository.
  - **Provenance:** `app` imports from the new virtualenv's site-packages.
  - `/` and `/api/scenarios` return 200, with exactly `decree_state`, `deficit_demo` and
    `tiny_valid`.
- **Packaged turn:** 1 passed; 13 requests, **none off-origin**.
- **F12:** a second launch on the bound port exits 1 and names the port. SIGINT stops the server (0),
  and a restart on the same port serves 200.

| budget | median | worst | STOP | |
|---|---:|---:|---:|---|
| new game | 46.55 ms | 106.48 ms | 300 ms | OK |
| resolve, turns ≤ 20 | 96.04 ms | 158.08 ms | 500 ms | OK |
| resolve, turns 21–40 | 235.69 ms | 303.19 ms | 800 ms | OK |
| read projection | 4.84 ms | **199.06 ms** | 200 ms | OK, **0.94 ms of headroom** |
| load + validate a 40-turn save | 144.22 ms | 162.35 ms | 1000 ms | OK |
| projection payload | 2,752 B | 68,113 B | 204,800 B | OK |

**Per endpoint (median / worst):**
- `/api/scenarios`: **128.24 / 199.06 ms**, the read row's worst;
- `/api/game/history`: 37.56 / 55.36 ms;
- `/api/game/decision-options`: 6.43 / 9.25 ms;
- `/api/saves`: 6.00 / 8.26 ms;
- every other endpoint is under 5 ms.

**This pass is narrow, and I am not presenting it as more than that.** The read row passed by under
1 ms, and an earlier run of the same archive breached it. The recorded verdict is `PASSED`, under the
established method and the unchanged threshold.

## 3. Carried risks

- **R2 (restated, worse than recorded):** `/api/scenarios`.
  - The median is about 107–128 ms.
  - The worst read here was 132–206 ms, across the nine runs with figures (eight diagnostic runs and
    the re-run), on two builds.
  - **Two observed breaches** of the 200 ms STOP: the first `verify_release`, and `measure-ux4e-1`.
  - UX-4d had recorded about 140 ms.
  - The 20-request worst-sample rule now sits at the edge, so a release check can fail on variance
    alone.
  - A fix, such as the cost of building the scenario listing on each request, would be a code change
    needing its own ruling. **None is made here.**
- **R1:** the cold `/api/saves` path, unchanged (`gate-4a3-commit6c-saves.md` §3.2).
- **R3:** narrowed by UX-4e's neutral "Turn outcome" heading. The History timeline's "Turn N — …"
  buttons are unchanged.
- **R4:** foreign-assistance amounts, unchanged.

## 4. The enforced internal dry run, through the interface of the installed build

**How it ran:**
- The archive was extracted fresh into a new scratch directory; `sha256sum -c SHA256SUMS` exited 0.
- The README's install commands ran on a path stripped of the repository (exit 0). `app` imported
  from that directory's own `.venv`.
- The README's run command started the server with `--port 48451` and a fresh save root.
- Then:
  ```
  MANDATE_DRYRUN_URL=http://127.0.0.1:48451 npm run dryrun:installed:ux4f
  ```
  This sets `MANDATE_DRYRUN_REQUIRED=1`, under which a missing address fails. It ran at 1440×900,
  exited **0**, and reported `1 passed (5.8s)`. It wrote `gate-4a3-ux4f-dryrun.json` and
  `gate-4a3-ux4f-dryrun-shots/`; the record's `gate` field reads `4A3 UX-4f (enforced)`.
- **What the run enforces:**
  - each turn's preview `would_pass` equals its resolved vote outcome;
  - the decree preview was affordable and enacted;
  - `consoleErrors` and `offOrigin` are both `[]`.

  The record is written only after all of these hold.
- **Stopping the server.** I sent SIGINT to process 747. Its log ends "Finished server process [747]",
  from the scratch install's command, and it exited 0.
  - **A recording gap:** my ownership check matched two PIDs, the server and my own shell. Its
    printout failed before the signal went out. The server's own log and exit status confirm it was
    the right process; the second PID was the checking shell itself.

| turn | route | preview `would_pass` | resolved outcome | agreed | confirmation | headline | visible / routine / Trace |
|---:|---|---|---|---|---|---|---|
| 1 | decree | true (affordable) | `enacted_by_decree` | yes | "Resolve turn 0 with 1 staged action?" | The budget was enacted by decree. The legislature was bypassed. | 14 / 5 / 19 |
| 2 | legislative | false | `failed_legislative` | yes | "Resolve turn 1 with 1 staged action?" | The budget was blocked. | 10 / 6 / 16 |
| 3 | legislative | false | `failed_legislative` | yes | "Resolve turn 2 with 1 staged action?" | The budget was blocked. | 10 / 6 / 16 |
| 4 | legislative | false | `failed_legislative` | yes | "Resolve turn 3 with 1 staged action?" | The budget was blocked. | 13 / 6 / 19 |
| 5 | legislative | false | `failed_legislative` | yes | "Resolve turn 4 with 1 staged action?" | The budget was blocked. | 12 / 6 / 18 |

**The UX-4e corrections, as installed:**
- **Turn 1 (decree):**
  - the first lines are "Personal income tax: 20.00% → 25.00%." and "Enacted by decree — no vote
    was held.";
  - no line says the legislature voted.
- **Turns 2–5 (legislative):**
  - the first lines are "The legislature voted the budget down: 0 of 1 chamber carried." and "Lower
    chamber blocked the budget: 45 of 51 seats, 6 short.";
  - the cause is now the **first** line. In UX-4d it was the eighth.
- **DR2 holds:** the third line is the extraction warning, kept visible.
- **Fewer visible lines:** 10–14 per turn, down from 12–15. Routine steps are 5–6, up from 4 (the
  capital ledger and baseline drift, ruled "Fold both").

**Every preview agreed with its resolution.** History re-read turn 1's headline exactly. There were
**0 console errors** and **0 off-origin requests**.

The screenshots are in `gate-4a3-ux4f-dryrun-shots/`:
- the Dashboard;
- each turn's result;
- History on turn 1;
- the Economy summary.

## 5. Gates

Each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `build_release.py --check-reproducible` (clean tree, `44fbd5a`) | 0 | `09d21997…a71ba` twice |
| `build_release.py --epoch 1791081047` (fresh clone at `44fbd5a`) | 0 | `09d21997…a71ba`: identical |
| `diff -r` archive SPA vs `frontend/dist` | 0 | identical |
| `verify_release.py … gate-4a3-ux4f-*` (first) | **1** | STOP: `read_projection_ms` (figure not printed); nothing written |
| `measure_budgets.py` × 8 (diagnosis, scratch) | 1 once, else 0 | §2.2; committed in `gate-4a3-ux4f-r2-ab/` |
| `verify_release.py … gate-4a3-ux4f-*` (the one re-run) | 0 | `PASSED`, `breaches: []`; read worst 199.06 ms |
| fresh extract `sha256sum -c`; README install (clean path) | 0 / 0 | `app` from the archive's `.venv` |
| `npm run dryrun:installed:ux4f` (enforcing) | 0 | `1 passed (5.8s)` |

**Not re-run, and why.** No application source, backend, scenario or contract changed in this
commit. The unit tests, the browser gates and the full suite therefore stand as recorded for UX-4e
(`44fbd5a`).

## 6. Scope

- **Added:**
  - this record;
  - `gate-4a3-ux4f-{release,budgets,packaged}.json`;
  - `gate-4a3-ux4f-dryrun.json` and `gate-4a3-ux4f-dryrun-shots/`;
  - `gate-4a3-ux4f-r2-ab/` (eight `measure_budgets` JSONs, unchanged from the runs).
- **Unchanged:** everything else, including UX-4d's release records and every earlier artifact.

The roadmap stays **"internally complete; externally pending"**. The five-person playtest is the
remaining external step, and it is yours.
