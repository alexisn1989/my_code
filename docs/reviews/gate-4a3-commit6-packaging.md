# Gate 4A3 (frozen-plan 4A5) Commit 6 — package, secure and measure the slice, and close it internally

**Subject:** `Gate 4A3 (6/6): package, secure and measure the slice, and close it internally`
**Parent:** `abcc9a9b3c4c9a7ca8a0b4f49d4cbf8883aace5c` (Commit 5b), not amended.
**Machine-readable evidence:** `gate-4a3-commit6-release.json`, `gate-4a3-commit6-packaged.json`,
`gate-4a3-commit6-budgets.json`, `gate-4a3-commit6-dependencies.json`, and the browser re-runs
`gate-4a3-commit6-{verification,icon-coverage,terminal,campaigns}.json` and
`gate-4a3-accessibility-after-commit6.{json,md}`.

The last commit of the gate. It makes the slice **distributable**, re-verifies the security rules
against a **running** server, measures the budgets over real HTTP for the first time, and closes the
gate as **internally complete; externally pending** — with one budget breach recorded rather than
hidden, by the user's ruling.

---

## 1. Tailwind scans shipped source only

`src/styles/tokens.css` now reads `@import "tailwindcss" source(none)` followed by explicit
`@source` lines for the app's TypeScript and `index.html`, and `@source not` for every test file.
Automatic detection had been scanning e2e specs, tools, JSON and tests, so words in comments and test
assertions shipped as utilities — once at 1.20 kB, from the word "filter" in a spec comment.

**The stylesheet lost seven dead rules — 18.49 → 18.11 kB — and gained none.** Each was traced to a
non-shipping source and shown absent from shipped code:

| removed | came from |
|---|---|
| `.accent-red-600` | a `tokens.css` comment and `check-palette.mjs`; the app uses only `var(--color-accent-red-600)` |
| **`.bg-red-950`**, **`.text-emerald-300`** | `tokens.css` comments and `check-palette.mjs` — **default-palette colours `check:palette` forbids, shipping as dead rules** |
| `.collapse` | substrings and test mentions only |
| `.contents` | `tools/check-bundle.mjs` |
| `.w-1/2`, `.w-[63%]` | `StrategicMapScreen.test.tsx` assertions; the screen's real `min-[900px]:` variants are still emitted |

**The JS is byte-identical to Commit 5b's** (same SHA-256); only its filename hash moved, because
Vite's chunk name covers the imported stylesheet.

**Proved in a scratch copy, never committed:** the bare word `filter` added to an e2e comment and to a
test file leaves the CSS byte-identical (0 `.filter` rules); the same word in a real component's
`className` produces `.filter` — so the scan still reads shipped source, and step one did not pass by
scanning nothing.

**New permanent gate, `npm run check:css-sources`:** the import must carry `source(none)`, every
`@source` must resolve inside `src/` or be `index.html`, and tests must be excluded. Verified against
four planted violations. Writing it caught a bug in its own first draft: a naive comment-stripping
regex ate the middle of `"../**/*.{ts,tsx}"`, which contains a comment opener and closer.

`tailwind.config.ts`'s comment no longer claims its globs decide anything — the build never loads it.

---

## 2. The security boundary and the startup promises, against a running server

New `backend/tests/test_live_server.py` (**18 tests**) starts the real `mandate-gui` console script
and talks to it over raw sockets — the first backend test that does. Every earlier API test uses
`TestClient`, which never opens a socket.

| verified | how |
|---|---|
| loopback only | the kernel's own `/proc/net/tcp` shows the listener on `127.0.0.1` alone; a connect to this host's non-loopback address (`192.0.2.2`) is refused |
| Host | missing (HTTP/1.0), rebinding-style, other-port, no-port, suffix and trailing-dot spellings → 403; the two loopback spellings → 200 |
| Origin | `Origin: null` → 403 on GET **and** POST; a foreign origin → 403; the server's own → 200 |
| forwarded headers | for every header in `UNTRUSTED_FORWARDING_HEADERS`: a good Host with a hostile forwarded value is served, a hostile Host with a good forwarded value is refused |
| F12 collision | a second launch exits 1 within the timeout, names the port and `--port`, and nothing binds port+1 |
| F12 shutdown | SIGINT exits 0 and `mandate-gui` restarts on the same port at once |

`security.py`'s comment claimed GET and HEAD were exempt from the Origin rule; the code never exempted
them. The comment now says what the code does, and the live test proves the stricter behaviour.
`UNTRUSTED_FORWARDING_HEADERS` was referenced nowhere; the live test now iterates it, so it cannot
drift from behaviour.

### A defect found while writing it, and fixed

**A clean Ctrl+C blocked a restart on the same port for up to a minute.** The startup probe bound with
`SO_REUSEADDR=0`; uvicorn's own bind uses 1. Any connection the server closed itself — the normal case
with a browser open — leaves TIME_WAIT on the server's port, which the probe counted as "in use", so a
restart said *"port N is already in use … Stop the other process"* when no other process existed. It
was reproduced before fixing (exit 1, that message), and the live test's own readiness polling is
enough to trigger it.

The probe now sets `SO_REUSEADDR=1` on POSIX, matching uvicorn; a live LISTEN socket still refuses the
bind, so real collisions are still reported (`test_probe_detects_a_bound_port` and the live collision
test). Windows keeps 0, because there `SO_REUSEADDR` would let the probe bind over a live listener.
Guarded by a unit test and two live tests, **all three proved to fail against the old probe**.

`require_frontend_build`'s message now names `--frontend-dist` first, because from a release archive
the build exists and only the path is wrong. Guarded by a unit test proved to bite.

---

## 3. Bundle hygiene and the bundle budget

`check:bundle` now also fails on a shipped sourcemap, a `sourceMappingURL` comment, `import.meta.env`
residue, or a non-same-origin URL in `dist/index.html`, and **enforces the bundle budget**: the initial
JS is **96.12 KiB gzipped (level 9) of 250 KiB, 153.88 KiB of headroom**. Each new check was proved
against a planted violation. The `DEV_RAW_REPORT_SENTINEL` literal is untouched.

---

## 4. The release archive — reproducible

`scripts/build_release.py` builds `dist/mandate-gui-0.1.0.tar.gz`: the wheel, the hashed runtime
requirements, the built SPA, the three shipped scenarios, a two-command README
(`packaging/README.release.md`) and `SHA256SUMS`, under one `mandate-gui-0.1.0/` directory.

- Inputs are staged from `git ls-files`, never the working tree, so no `.venv`, cache or save leaks in.
- The build backend is pinned (`hatchling==1.32.0`); the wheel holds only `app/` and its metadata,
  every entry timestamped at the epoch.
- `requirements.txt` is `uv export --frozen`: **20 pins, every one `==` with hashes (204 hash
  lines)**, asserted by the script. That is how "no unpinned ranges in what ships" is met.
- Tar members in sorted order, one mtime, modes 0644/0755, owner 0/0 with empty names, GNU format;
  gzip with `mtime=0` and no filename.

**Reproducibility, falsifiably:** two builds in independent temporary directories with
`SOURCE_DATE_EPOCH=1790730747` (Commit 5b's commit time) produced the **identical SHA-256
`54290ccaebc66f3146b75e2869921972008570b7d9807977c83f4ed9eba7379b`**. After the push, the archive is rebuilt from the pushed tree with the same epoch and
must reproduce that hash.

---

## 5. Verified on a clean path

`scripts/verify_release.py` works only from the archive, in an empty directory outside the
repository, with the repository's virtualenv and import path stripped from the environment:

1. **Safe inspection before extraction** — every member relative, under one directory, no `..`, no
   symlink or device. The checker first rejects three hostile archives (absolute path, traversal,
   symlink) so it cannot pass the real one by rejecting nothing.
2. `SHA256SUMS` verified over all 9 files; the scenario set is exactly the three names.
3. The README's install command run **verbatim**; its run command with only `--port` and
   `--save-root` appended, recorded as such.
4. **Provenance:** `app` imports from the new virtualenv's site-packages, never the repository.
5. `/` and `/api/scenarios` → 200, with the three scenarios.
6. **One turn played through the interface against the installed server** (`packaged` project):
   13 requests, **none off-origin**; interaction feedback worst **2.8 ms** against a 200 ms STOP.
7. **F12 against the installed entry point:** a second launch exits 1 naming the port; SIGINT exits
   0; a restart on the same port serves.
8. The budgets, measured against this instance.

---

## 6. Budgets — measured over real HTTP for the first time

`scripts/measure_budgets.py`: client-side wall clock over loopback, one warm-up discarded per
endpoint, one fresh `decree_state` campaign resolved with empty turns to an ordinary turn 40. Median
against the target, worst against the STOP.

| budget | median | target | worst | STOP | verdict |
|---|---:|---:|---:|---:|---|
| New game | 87.03 ms | 150 ms | 120.29 ms | 300 ms | OK |
| Resolve, turns 1-20 | 160.93 ms | 250 ms | 245.44 ms | 500 ms | OK |
| Resolve, turns 21-40 | 345.18 ms | 400 ms | 525.29 ms | 800 ms | OK |
| Any read-only projection | 6.94 ms | 100 ms | 245.25 ms | 200 ms | **STOP — recorded by ruling** |
| Load + validate a 40-turn save | 155.62 ms | 500 ms | 228.7 ms | 1000 ms | OK |
| Projection payload | 2752 B | 102400 B | 68113 B | 204800 B | OK |
| Initial JS bundle (gzip, level 9) | — | 250 KiB | 96.12 KiB | 250 KiB | OK (`check:bundle`) |
| Interaction → visible feedback | — | 100 ms | 2.8 ms | 200 ms | OK (packaged spec) |

Read projections per endpoint (median / worst, ms): `/api/game/state` 3.15 / 4.02; `/api/game/map/strategic` 2.5 / 2.99; `/api/game/decision-options` 8.72 / 12.27; `/api/game/military` 2.31 / 3.66; `/api/game/history` 46.81 / 59.25; `/api/game/history/40` 3.2 / 34.33; `/api/saves` 196.39 / 245.25; `/api/scenarios` 133.15 / 177.34.

These are the final verification run's figures. Across every measurement taken while building this
commit, `/api/saves`'s worst ranged 245-314 ms and was always over its STOP; no other budget ever
passed its STOP.

### One breach, recorded by the user's ruling

**`GET /api/saves` passes its 200 ms STOP.** `SaveRepository.list_saves()` parses every save file and
runs `validate_history` — a full replay — on each one, on every listing, and rewrites the index while
doing so. Its cost is linear in the total turns across all saves, and every new game writes one, so
it grows with ordinary play. Frozen section 18 forbids fixing a breach with caching or weakened
validation, so the choice went to the user, who ruled **"Record breach, ship rest"**: recorded here
and in `gate-4a3-commit6-budgets.json` verbatim, not fixed, not reclassified. `verify_release.py`
accepts exactly that breach and nothing else — any other budget, or any other endpoint over the read
STOP, still fails it. **`GET /api/scenarios` is close behind**: worst 177 ms in the final run, and 198.9 ms — 1.1 ms under
the STOP — in the run before it, because it loads and projects every scenario file per call. The fix for both is its own follow-up decision.

---

## 7. Dependencies

`uv lock --check`, `npm ls --all` and `npm ci --dry-run` are clean. **Advisories: none** —
`npm audit --omit=dev` and the full `npm audit` report 0 of any severity (9 production packages), and
`pip-audit 2.10.1` over the shipped requirements reports 0 across 19 packages (the 20th, `colorama`,
installs only on Windows). **FE-1 is resolved**: the frozen plan's one high, dev-only `nanoid`
advisory via vite → postcss is gone — the lockfile now resolves `nanoid` 3.3.18 — and it was never in
the shipped closure. The `^` ranges in `package.json` do not ship: `npm ci` installs the lockfile and
the SPA ships bundled. Inventory: `gate-4a3-commit6-dependencies.json`.

---

## 8. The external playtest — prepared, not run

`docs/playtest/gate-4a3-external-playtest-protocol.md` makes frozen section 22 operational: install
from the archive by its own README, say only "you govern this country", no coaching, five turns, and
the fun gate — at least three of five voluntarily want another turn. One
`gate-4a3-observation-sheet.md` per tester, with the tally. Both say plainly that they are prepared
and not run; the result is the user's to obtain.

---

## 9. Closeout

**Gate 4A3 is internally complete; externally pending.** The roadmap entry says exactly that and
nothing stronger, and corrects the two places that still said the gate "has not started".

Owed, each with a named disposition:
- **The five-stranger playtest** (frozen section 22) — the user's to run.
- **`/api/saves`** past its budget — recorded by ruling; its fix is a follow-up decision.
- **T2** — each driver line renders its `reason_id`, 27 of 27 painted. Whether that is a trace aid
  or a leak is a copy decision, not a defect fix; it becomes an owned follow-up ticket rather than a
  change here.
- **D1** — `Portrait`'s frame colour, a visual-design decision.
- The three divergences carried from the characters slice (the unbuilt shared `*_REJECTION_CODES`
  tuple, `/preview` raising a message rather than a code, no repository-wide emitted-reason check).

---

## 10. Gates

| gate | result |
|---|---|
| `ruff format --check .` | 187 files formatted |
| `ruff check .` | passed |
| bare `mypy` | 56 source files, no issues |
| `uv lock --check` | clean (hatchling pin is a build requirement, not a locked dependency) |
| `npm test` | 485 passed, 30 files (unchanged) |
| `typecheck` / `build` | clean; CSS 18.11 kB, JS byte-identical to 5b |
| **`check:bundle`** (extended) | OK — 96.12 KiB gzip of 250 KiB |
| **`check:css-sources`** (new) | OK |
| `check:palette` / `check:copy` | clean |
| scratch CSS proofs | hole closed (CSS byte-identical), anti-vacuity (`.filter` emitted) |
| `verify:campaigns:commit6` | 7 passed |
| `verify:terminal:commit6` | 6 passed |
| `verify:fixes:commit6` | 13 passed |
| `verify:icons:commit6` | 7 passed |
| `audit:stress:seated` | 6 passed; its committed artifact reproduced byte-for-byte |
| `audit:accessibility:verify:commit6` | 0 findings across 89 surfaces, 4 needs-review — byte-identical to 5b's |
| **`build_release.py --check-reproducible`** | two builds, identical SHA-256 |
| **`verify_release.py`** | exit 0, including the packaged turn, F12 and the budgets with the one ruled breach |
| advisories | npm audit (prod and all) 0; pip-audit 0 |
| `generate:api` | byte-identical, **62 / 13 / `0.23.0`** |
| full backend suite | **36,297 passed**, 0 failed, 1 known warning, `PYTEST_EXIT=0`, 26:24 — +20: 18 in `test_live_server.py`, 2 in `test_api_security.py` |

**Re-measured browser evidence:** `gate-4a3-commit6-{verification,icon-coverage,terminal}.json` and
`gate-4a3-accessibility-after-commit6.{json,md}` are byte-identical to Commit 5b's; the campaigns
evidence differs only in the renamed asset paths. Removing the seven dead rules moved no measured
figure.

**Scope:** no `app/simulation/**` file, scenario, fixture, frozen plan, contract or earlier review
artifact is in the diff.
