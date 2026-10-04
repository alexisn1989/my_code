# Gate 4A3 UX-4d: release verification, and the internal dry run

This is the last of the split UX-4 commits. It adds records and the dry-run harness only: no
application, backend, scenario or contract change. It verifies the build at `5a1b2eb` (UX-4c). It
then walks that build through the interface, **installed from its own release archive**.

**The dry run is INTERNAL. It is not one of the five external playtesters, and it does not count
toward them or toward the playtest's pass criterion.** That playtest, its protocol and its pass
criterion are unchanged, and they are yours.

## 1. The archive: rebuilt, reproducible, and the same from a fresh clone

| step | result |
|---|---|
| `build_release.py --check-reproducible` from the clean tree at `5a1b2eb` (epoch = HEAD's commit time, `1791075701`) | exit 0. Two independent builds produced **identical bytes**: `d4a5459e6eb7646889b37e5505921f0d71b241d2bef20f89d61df174adf0a875` |
| **fresh clone** of the pushed branch, checked out at `5a1b2eb`, `build_release.py --epoch 1791075701` | exit 0. The **same** sha256, `d4a5459e…f0a875`, rebuilt from the pushed history alone. `node_modules` were linked from the working tree, since dependencies are not sources. |
| the SPA inside the archive vs the gated `frontend/dist` (`diff -r`) | **identical**. JS `index-DJNo2ETb.js`, CSS `index-DVVZ_8_3.css`: the build every UX-4c gate ran against |

The archive itself lives outside the repository (in a scratch directory) and is not committed. Its
hash is the record.

## 2. `verify_release.py`, under new names

```
python3 scripts/verify_release.py <archive> \
  --out gate-4a3-ux4-release --budgets-out gate-4a3-ux4-budgets --packaged-out gate-4a3-ux4-packaged
```

**Exit 0, verdict `PASSED`, `breaches: []`.** The release and budget records carry the same
`runId` (`c9a1e105…`).
- **Checksums:** every file. Hostile archives (an absolute path, a parent traversal, a symlink) are
  all rejected.
- **Install:** the README's own install line, verbatim, on a path stripped of the repository.
  - **Provenance:** `app` imports from the new virtualenv's site-packages.
  - `/` and `/api/scenarios` return 200, with exactly `decree_state`, `deficit_demo` and `tiny_valid`.
- **Packaged turn:** 1 passed; 13 requests, **none off-origin**.
- **F12 (port handling):** a second launch on the bound port exits 1 and names the port. SIGINT stops
  the server (0), and a restart on the same port serves 200.

**Budgets, measured against the installed server:**

| budget | median | worst | STOP | |
|---|---:|---:|---:|---|
| new game | 41.63 ms | 61.73 ms | 300 ms | OK |
| resolve, turns ≤ 20 | 85.10 ms | 151.14 ms | 500 ms | OK |
| resolve, turns 21–40 | 219.40 ms | 301.97 ms | 800 ms | OK |
| read projection | 4.08 ms | 139.46 ms | 200 ms | OK |
| load + validate a 40-turn save | 139.22 ms | 167.28 ms | 1000 ms | OK |
| projection payload | 2,752 B | 68,113 B | 204,800 B | OK |

**Per endpoint (median / worst):**
- `/api/saves`: 6.00 / 7.42 ms;
- `/api/scenarios`: 116.58 / 139.46 ms, the read row's worst and under its STOP;
- `/api/game/history`: 43.27 / 80.05 ms;
- every other endpoint is under 10 ms.

**Carried risks, unchanged in kind:**
- **R1:** the cold `/api/saves` path, about 1.5 s for a fresh server's first listing of 20 long
  saves, is not what this warm-request method measures. It is recorded in `gate-4a3-commit6c-saves.md`
  §3.2.
- **R2:** `/api/scenarios` runs at about 140 ms worst against its 200 ms STOP.

## 3. The internal dry run, through the interface of the installed build

**How it ran:**
- The archive was extracted fresh; `sha256sum -c SHA256SUMS` passed.
- The README's install commands were run on a path stripped of the repository, and `app` imported
  from the archive's own `.venv`.
- The README's run command started the server with `--port 48431` and a fresh save root.
- The new **`e2e/dry-run.spec.ts`** (project `dry-run`; `npm run dryrun:installed:ux4` with
  `MANDATE_DRYRUN_URL` pointing at that server) drove it at 1440×900. It writes
  `gate-4a3-ux4-dryrun.json` and `gate-4a3-ux4-dryrun-shots/`, and refuses to overwrite either.
- The server was then stopped with SIGINT. I first confirmed the process was the one started from the
  scratch install, by its command line and working directory.

**The walk, all through the interface:**
1. Start Kingdom of Valdrun. On the Dashboard the stakes line is visible. "Build a decision" opens
   Decisions.
2. Each turn: select a tax card, choose the route, Preview, then Resolve and Confirm. Then read the
   result: its headline, the consequences, the folded Routine steps and the Trace. Then **"Plan turn
   N"** leads to the next turn.
3. History re-reads turn 1. Dashboard → **Details: Money** lands on the Economy summary card.

| turn | route | preview | confirmation | headline | visible / routine / Trace |
|---:|---|---|---|---|---|
| 1 | decree | "If resolved now: enacted by decree — the legislature is bypassed. Route cost 250." (`would_pass` true, affordable) | "Resolve turn 0 with 1 staged action?" | The budget was enacted by decree. The legislature was bypassed. | 15 / 4 / 19 |
| 2 | legislative | would not pass | "Resolve turn 1 with 1 staged action?" | The budget was blocked. | 12 / 4 / 16 |
| 3 | legislative | would not pass | "Resolve turn 2 with 1 staged action?" | The budget was blocked. | 12 / 4 / 16 |
| 4 | legislative | would not pass | "Resolve turn 3 with 1 staged action?" | The budget was blocked. | 15 / 4 / 19 |
| 5 | legislative | would not pass | "Resolve turn 4 with 1 staged action?" | The budget was blocked. | 14 / 4 / 18 |

**Every preview agreed with its resolution.** History re-read turn 1's headline exactly. There were
**0 console errors** and **0 off-origin requests**. The screenshots are in `gate-4a3-ux4-dryrun-shots/`:
the Dashboard, each turn's result, History on turn 1, and the Economy summary.

## 4. What the dry run showed, for your ruling (not changed here)

These are observations from walking the build. They are **not fixed in this pass**, because each
needs a ruling beyond the approved scope.

- **DR1 — the turn result is still long.** 12–15 lines stay visible under "Why this happened" every
  turn. UX-2 folds only the four approved bookkeeping reasons. Several remaining lines are generic and
  carry no figure or name:
  - "Legitimacy was resolved."
  - "Political capital was resolved."
  - "Survival risk was assessed, …"
  - "The legislature voted."
  - "Political capital spending was recorded."
  - "A tax rate changed."

  The per-bloc lines repeat without naming the bloc: "A bloc's relationship with the government
  changed." appears twice, and "Relationships decayed toward their authored baseline." twice.
  - The cause, "The legislature blocked the budget.", is the **eighth** line on turn 2.
  - Candidate fixes: word these reasons from their stored params, as UX-2 did for the economy (for
    example, `tax_rate_changed` carries the old and new rates, which the CLI already prints), or
    extend the routine rule.
- **DR2 — a recurring consequence.** "Resource extraction: 6,000 resource workers had no deposit to
  work." appears on every turn. Under the approved rule it stays visible (unplaced workers are
  consequential), but a player sees the same line five times.
- **DR3 — R3, seen in play.** The confirmation says "Resolve turn 0…", the result is headed
  "Turn 1 — outcome", and the next action is "Plan turn 1". The confirmation, the national header
  and "Plan turn N" agree with each other. The result heading names the turn the result produced
  (R3, carried).

## 5. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `build_release.py --check-reproducible` (clean tree) | 0 | `d4a5459e…f0a875` twice: reproducible |
| `build_release.py --epoch 1791075701` (fresh clone at `5a1b2eb`) | 0 | `d4a5459e…f0a875`: identical |
| `diff -r` archive SPA vs `frontend/dist` | 0 | identical |
| `verify_release.py … --out gate-4a3-ux4-release --budgets-out gate-4a3-ux4-budgets --packaged-out gate-4a3-ux4-packaged` | 0 | `verdict: "PASSED"`, `breaches: []` |
| README install (clean path), checksums, provenance | 0 | `app` from the archive's `.venv` |
| `npm run dryrun:installed:ux4` (against the installed server) | 0 | `1 passed (5.3s)` |

**Superseded and removed.** A debug run of the dry-run spec under a scratch name passed. Its
untracked output was removed before the recorded run, after confirming it was not tracked.

**Not re-run, and why.** No application source, backend, scenario or contract changed in this
commit, so the unit tests, the browser gates and the full suite stand as recorded for UX-4c
(`5a1b2eb`). This commit adds only the dry-run spec, its Playwright project, its npm script and these
records.

## 6. Scope

- **Added:**
  - `frontend/e2e/dry-run.spec.ts`;
  - the `dry-run` project in `frontend/playwright.config.ts`;
  - the `dryrun:installed:ux4` script in `frontend/package.json`;
  - this record;
  - `gate-4a3-ux4-{release,budgets,packaged}.json`;
  - `gate-4a3-ux4-dryrun.json` and `gate-4a3-ux4-dryrun-shots/`.
- **Unchanged:** everything else, including every earlier artifact.

The roadmap stays **"internally complete; externally pending"**. The five-person playtest is the
remaining external step, and it is yours.
