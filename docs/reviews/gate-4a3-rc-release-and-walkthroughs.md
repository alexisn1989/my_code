# Gate 4A3 map-led redesign candidate (`rc`): release verification and installed runs

**Internal, and not one of the five external playtesters.**
- **The playtest build switch was pending review when this pass ran.** It was approved afterwards (§7).
- **Authorized by:** your instruction to commit the two reviewed files, build the candidate from that
  commit, run `verify_release` once, then both walkthroughs and the enforced dry run against a fresh
  installation.

## 1. The commit
- **`8ba9ff7`** "Installed redesign walk for the map-led redesign candidate".
- **Scope:** exactly `frontend/e2e/installed-walkthrough.spec.ts` and `frontend/package.json`, staged by
  name.
- **Checks:** the 81 mockups stay untracked, nothing is unstaged, and nothing was staged under
  `backend`, `data` or `frontend/src`.
- **Pushed.** After `git fetch`, local `HEAD` equals `origin/claude/phase-4a-graphical-vertical-slice`
  (`8ba9ff738c9b…`).

## 2. The candidate archive

| check | result |
|---|---|
| `npm run build` from the committed tree | exit 0; bundle `index-6r-ZG1t2.js`, `index-C8-vGaIO.css`, the same names as before |
| `build_release.py --check-reproducible` at `8ba9ff7` (epoch `1791945066`, the commit time) | exit 0; two builds gave **identical bytes** |
| **fresh clone** at `8ba9ff7`, both dependency links, the same epoch | exit 0; the **same** sha256 |
| packaged SPA vs `frontend/dist` (`diff -r`) | **identical** |

**Archive sha256: `b3ac1a946daaacac5bfbb635ee679aebb5e39608722626089d76160566d7a2b0`**

## 3. `verify_release`, once
- **The command:**
  ```
  python3 scripts/verify_release.py <archive b3ac1a94…> --out gate-4a3-rc-release --budgets-out gate-4a3-rc-budgets --packaged-out gate-4a3-rc-packaged
  ```
- **Result:** exit 0, run `c0e5d8fe7f29ccb085812e3eb20b8fc6`. The YAML loader is
  `yaml.cyaml.CSafeLoader`. Budgets `PASSED`, with no breaches:

| budget | median | worst | STOP |
|---|---|---|---|
| new_game_ms | 12.61 | 35.63 | 300 |
| resolve_turn_le_20_ms | 62.88 | 102.25 | 500 |
| resolve_turn_21_to_40_ms | 146.71 | 193.72 | 800 |
| read_projection_ms | 6.29 | 71.56 | 200 |
| load_validate_40_turn_save_ms | 161.91 | 194.82 | 1000 |
| projection_payload_bytes | 2,995 | 75,266 | 204,800 |

- **F12:** the port collision is refused with the stated message, and shutdown and restart on the
  same port are clean.

## 4. The fresh installation
- **Checks before running:**
  - the outer sha256 was checked before extraction;
  - `sha256sum -c SHA256SUMS` exits 0;
  - the README install exits 0.
- **The server:** the installed `<install>/.venv/bin/mandate-gui --frontend-dist dist --scenario-root
  scenarios --port 46509 --save-root <fresh>`, with PID 1265. Its `/proc` cmdline and cwd were checked,
  and it served `200`.
- **Shutdown:** stopped afterwards by SIGINT to that single verified PID.

## 5. The three enforced runs, in order (each against the server above)

| command | exit | result |
|---|---|---|
| `walkthrough:installed:rc` | 0 | **Walk A** (Valdrun): the qualifying-reform link; preview `would_pass` false with its caveat; not resolved. **Walk B** (`deficit_demo`): "Amendment passed, 53 of 100 seats (51 required).", the objective line, and History equal to live. 0 console errors, 0 off-origin requests |
| `walkthrough:installed:rc:redesign` | 0 | Arken: draft → map → Parliament → bloc panel → Maret Kuusk at 105 → Preview → resolve → card → History. Preview Lower 61/51 and Upper 35/31, both carried, `would_pass` true. The **recorded** vote is the same, `passed_legislative`, and History equals live. 0 console errors, 0 off-origin requests |
| `dryrun:installed:rc` | 0 | five turns through the interface: one decree turn (`enacted_by_decree`, as previewed), then four legislative turns previewed "Fails" at 45 of 51 and resolved `failed_legislative`. 0 console errors, 0 off-origin requests |

**Each walk bound itself to the archive:** the outer sha256, the server's PID, cmdline and port, and
the installed `app.__file__` inside the install. Each record was written with `wx`.

## 6. Evidence (uncommitted)
- `gate-4a3-rc-{release,budgets,packaged}.json`;
- `gate-4a3-rc-walkthrough.json` and `-shots/`;
- `gate-4a3-rc-redesign-walk.json` and `-shots/`;
- `gate-4a3-rc-dryrun.json` and `-shots/`;
- this record.

**Committing them needs your instruction.**

## 7. Not done
- **No build switch was made in this pass.** It was left pending review. The user then approved the
  switch to this archive, which is recorded in `docs/roadmap.md` in the same commit as this record.
- **The external playtest** was not run, and is not claimed.
