# Gate 4A3 victory path, V-5: the candidate, verified and walked through as installed

**This commit is records only:** no code, test, threshold or cache change. It records the candidate built
from `6f610b9` (V-4) and the installed-archive walkthrough you asked for **before** any switch
decision.
- **The approved playtest build is unchanged:** `083c7a98…`, from `5236ddb`. The roadmap is not
  touched.
- **The candidate for your separate switch approval:**
  `8848c0e9ca64e452b8114e5f3f234e9843d36f98274d309dbc9ccf2c1b2f5122`.
- It supersedes V-3's `faeef811…` as the candidate, because V-4 changed the caveat wording. V-3's
  records are unchanged.

The walkthrough is **internal**. It is not one of the five external playtesters.

## 1. The candidate archive

| step | result |
|---|---|
| `build_release.py --check-reproducible` at `6f610b9` (epoch `1791655607`, the commit time) | exit 0. Two builds gave **identical bytes**: `8848c0e9…5122` |
| **fresh clone** at `6f610b9` (equal to the pushed head), both dependency links, the same epoch | exit 0. The **same** sha256 |
| the SPA vs `frontend/dist` (`diff -r`) | **identical**: `index-BZH-KFG-.js` and `index-DUcQTl77.css`, the bundle the V-4 browser gates ran against |

## 2. `verify_release`, once

```
python3 scripts/verify_release.py <archive 8848c0e9…> \
  --out gate-4a3-v5-release --budgets-out gate-4a3-v5-budgets --packaged-out gate-4a3-v5-packaged
```

**The only attempt exited 0.** Verdict `PASSED`, `breaches: []`, run `c9ff6c7c…`.

**What it confirmed:**
- **Provenance:** the installed app selects `yaml.cyaml.CSafeLoader`.
- **Checksums:** all 9 checksummed files. 3 hostile archives are rejected.
- **Served:** `/` and `/api/scenarios` return 200, with the three scenarios.
- **Packaged turn:** passed, 13 requests, none off-origin, and the worst feedback was 5.8 ms.
- **F12:** a collision exits 1. SIGINT exits 0, and a restart serves 200.

| budget | median | worst | STOP |
|---|---:|---:|---:|
| new game | 34.27 ms | 117.60 ms | 300 ms |
| resolve, turns ≤ 20 | 114.12 ms | 205.45 ms | 500 ms |
| resolve, turns 21–40 | 283.35 ms | 492.41 ms | 800 ms |
| read projection | 12.84 ms | **170.04 ms** (`/api/game/history`) | 200 ms |
| load + validate a 40-turn save | 320.04 ms | 430.37 ms | 1000 ms |
| projection payload | 2,995 B | 73,626 B | 204,800 B |

**This run is about twice as slow as V-3's on every row, and that is not attributable to code.**
- `git diff 97a5dfd 6f610b9 -- backend scripts data` is **empty**: V-4 changed only frontend strings
  and specs.
- V-3's single run on the same backend gave a history worst of 58.77 ms and a resolve median of
  62.03 ms.
- Both are single runs. This one came straight after a 34-minute suite in the same container.
- **Headroom on the read-projection STOP is 30 ms in this run.** It passed. As with R2, a single
  passing run does not exclude a breach on a slower machine.
- Per your earlier instruction, **no run was repeated for a better number.** R1 and R2 stay as
  recorded.

## 3. The installed-archive walkthrough (`npm run walkthrough:installed:v5`)

**The binding to the archive.** Each step is its own command, with its exit status:

| step | result |
|---|---|
| the archive's **full outer sha256**, before extraction, against `8848c0e9…5122` | equal (exit 0) |
| fresh extraction into a new directory | exit 0 |
| `sha256sum -c SHA256SUMS` (the internal manifest) | exit 0, every file OK |
| README install (`python3.11 -m venv` …, `--require-hashes`, the wheel) | exit 0 |
| installed `app.__file__` | `…/walk/mandate-gui-0.1.0/.venv/lib/python3.11/site-packages/app/__init__.py` |
| the server: `<install>/.venv/bin/mandate-gui --frontend-dist dist --scenario-root scenarios --port 38129 --save-root <fresh>` | serving 200 |
| server identity: **one** PID, found by an exact `/proc` cmdline match (interpreter, installed `mandate-gui`, port) | PID 12255; cwd is the install directory |

**The walkthrough itself:**
- The spec runs under `playwright.walkthrough.config.ts`, which has **no** `webServer`. Its script
  set `MANDATE_WALKTHROUGH_REQUIRED=1`.
- **Inside the spec,** the archive's sha256 was recomputed, the PID's `/proc` cmdline and the port
  were checked, and `app.__file__` was checked against the install directory. All are recorded in
  [`gate-4a3-v5-walkthrough.json`](gate-4a3-v5-walkthrough.json).
- **Result: exit 0, `1 passed (4.7s)`.**
- The server was then stopped by that one PID, after its cmdline and cwd were re-checked: SIGINT,
  then confirmed gone.

**Walk A, Valdrun. It stops at the preview, by design.**
1. **Dashboard:** the objective card shows `reform`, "Reform the constitution: 0 of 3 conditions
   met."
2. **Constitution:** **Draft the qualifying reform**, by keyboard (focus, then Enter).
3. **Decisions:** "Complete the constitutional conditions in one reform" is selected, and the
   selection summary is focused.
4. **Preview, with no influence:**
   - `would_pass` false and `affordable` true; the effect is `qualifies`;
   - "If enacted, this reform would record the qualifying transition; the election on turn 5 would
     decide.";
   - the caveat: **"This amendment would not pass as it stands, so it would not change the
     constitution."**
5. **Nothing resolved.**

**Walk B, `deficit_demo`, through the link. Preview and resolution agree here.**
1. **Dashboard:** `reform`, "2 of 3 conditions met".
2. **The Constitution link:** "Set decree authority to no decree authority" is selected and
   focused.
3. **300 influence on the Hardliners, then Preview:**
   - `would_pass` true, `affordable` true;
   - "If enacted, this reform would record the qualifying transition; the election on turn 20 would
     decide.";
   - no caveat.
4. **Resolve:** "Amendment passed, 53 of 100 seats (51 required)." The amendment was **enacted**,
   matching the preview's pass.
   - The objective line: "The constitution now qualifies, and the transition is recorded. Win the
     election on turn 20 to complete it."
   - The named line: "Decree authority: emergency only → none."
5. **History, turn 1:** the `history` context shows **the same objective line, headline and named
   line** as the live result.
6. **Dashboard:** `qualifying_election`, "Win the qualifying election: turn 20."
7. **Constitution:** all three conditions are **Met**, and "Qualifying transition: recorded on turn
   1".

**Across both walks: 0 console errors, and 0 off-origin requests.**

**The screenshots** are in `gate-4a3-v5-walkthrough-shots/`:
- `a1`: the Valdrun dashboard;
- `a2`: the failing preview;
- `b1` to `b6`: the dashboard, the passing preview, the result, History, the dashboard after, and
  Constitution after.

**`a2` is viewport-only.** It shows the selected card and the draft, but not the preview panel below.
The preview sentence and caveat are asserted, and recorded verbatim in the JSON. The run was not
repeated for a better picture, since records are never overwritten.

## 4. For your separate decision

| | |
|---|---|
| candidate archive | `mandate-gui-0.1.0.tar.gz`, sha256 **`8848c0e9ca64e452b8114e5f3f234e9843d36f98274d309dbc9ccf2c1b2f5122`** |
| built from | `6f610b9`, epoch `1791655607`; reproducible; the fresh clone matches |
| `verify_release` | `PASSED` once, run `c9ff6c7c…`. Read-projection worst 170.04 ms against a 200 ms STOP, in a slow run (§2) |
| installed walkthrough | passed. Bound to this hash and to the installed server's identity |
| approved build now | `083c7a98…` (unchanged) |

**The switch is not made here.**
