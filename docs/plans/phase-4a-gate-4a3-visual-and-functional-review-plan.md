# Phase 4A Gate 4A3 — visual and functional review, art, polish and packaging

**Status: frozen. Implementation not started.**

Ninth plan in `docs/plans/`. Audited against `HEAD` `26b8157e0b0855e181f6d56f26774f427282f888`
(`Characters (8/8): meet the people who decide, and close the slice`) on branch
`claude/phase-4a-graphical-vertical-slice`.

Amended five times before freezing, in two review rounds. Round one added the browser-first
ordering, the dual end-to-end campaigns, the concrete packaging target, one enforceable threshold
per budget, and the internal-versus-external completion split. Round two added §9's execution
details. Both rounds are recorded as written rather than folded silently into the prose.

---

## Context

The characters slice closed at `26b8157e`. The game is mechanically complete for this vertical
slice and **has never been reviewed in a real browser**.

All 404 frontend tests run in jsdom against a mocked `fetch`, so nothing automated exercises
rendered CSS, contrast, focus behaviour, zoom, overflow, or live integration with the API. Two
screens went live in the last two commits — Government and Relationships — and neither has been
seen by a human at any viewport.

Gate 4A3 exists to close that: look at the application first, fix what looking finds, then make it
distributable. The intended outcome is software that is safe and comprehensible to hand to five
strangers, and the evidence that it is.

---

## 0. The gate-label collision, resolved before anything else

The frozen Phase 4A plan's **§19 Gate 4A3 is "Decision workspace and turn resolution"**, which
shipped, folded into Gate 4A2. The work below is that plan's **§19 Gate 4A5**,
`docs/plans/phase-4a-graphical-vertical-slice-implementation-plan.md:1041`. The roadmap calls it
"Gate 4A3" because the MANDATE numbers it that way (`docs/roadmap.md:755`).

Two documents, two numbers, one body of work. This plan says **"Gate 4A3 (frozen-plan 4A5)"**
throughout: a plan that silently picked one label would strand a reader holding the other.

---

## 1. Rulings carried in

**F2 (user ruling): ADR 0020's per-character portraits SUPERSEDE the art bible's office-only
silhouette row.**

Frozen plan §13 specifies "a single presentation-only silhouette/emblem for *the office* — not a
person. No name, no stats, no traits" (`:777`). Commit 8 shipped per-character portraits carrying
names and traits, at the user's explicit request, with ADR 0020 as the architecture record.

**The frozen plan is left byte-identical.** The supersession is recorded here, exactly as Commit 6
§9's content-bump sentence and Commit 7's R8 were recorded rather than edited.

Everything else in §13 stands and is still owed: the palette additions, typography, flat panels,
the stroke-only icon set, the chart rules, the never-colour-alone rule, and the accessibility
floor.

---

## 2. Preconditions — measured, not recalled

- `HEAD` `26b8157e`, tree clean, local == remote. Backend 36,247 passed; frontend 404 passed;
  contract 62 schemas / 13 paths / `0.23.0`.
- **One-command startup works.** `uv run mandate-gui --port 8431` served `/` → 200 and
  `/api/scenarios` → 200. A live `POST /api/game/new` on `deficit_demo` followed by
  `GET /api/game/decision-options` returned 2 bargain counterparties, 2 foreign counterparts,
  8 promise options and 0 active promises, with `portrait_ref` populated.
- Chromium is pre-installed. `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` (a cache root, see §9.2),
  `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. **`playwright install` must never be run.**
- Backend builds with hatchling (`packages = ["app"]`); `[project.scripts]
  mandate-gui = "app.api.main:run"`; the `gui` extra is fastapi + uvicorn[standard].
- `mandate-gui` already accepts `--port`, `--frontend-dist` and `--scenario-root`
  (`app/api/main.py::_settings_from_args`).

---

## 3. Audit findings

| # | Finding | Evidence |
|---|---|---|
| **F1** | Gate-label collision | frozen `:1020` vs `:1041`; roadmap `:755` |
| **F2** | Art bible's Portrait row superseded (§1) | frozen `:777`; ADR 0020 |
| **F3** | Palette gap: §13 requires one green, one amber, one neutral-blue; `tokens.css` has **none**, and 7 component sites use Tailwind defaults instead | `tokens.css`, grep |
| **F4** | **No `prefers-reduced-motion` anywhere** (0 occurrences), though only 3 transition/animate usages exist — compliance is nearly free | grep |
| **F5** | No icon set. `TONE_GLYPH` uses ✓ ✗ ▲ ■. The never-colour-alone rule is ALREADY satisfied (`aria-hidden` glyph beside an `sr-only` label) | `components.tsx:26,82` |
| **F6** | No `axe`, no Playwright. T18 and T21 unwritten | `package.json` |
| **F7** | **Already done**: dev-only raw-report stripping is verified, not assumed | `tools/check-bundle.mjs` |
| **F8** | **Already done**: one-command startup (§4.11) | §2 |
| **F9** | Bundle **98.80 KiB gzip of a 250 KiB ceiling** — 40% used | `npm run build` |
| **F10** | 11 screens + Glossary; three remain `UnavailableScreen` (Economy `:106`, Legislature `:113`, Constitution `:120`) | `registry.tsx` |
| **F11** | **404 tests, none in a real browser.** Every screen test is jsdom + mocked fetch | 26 test files |
| **F12** | §4.11 promises port-collision fail-fast and graceful shutdown. **Never tested** | frozen `:432` |

---

## 4. Order of work — look first, fix second

Six commits. The ordering is the point: **nothing is fixed before it has been seen**, and the
browser is what does the seeing.

### Commit 1 — Playwright infrastructure and the browser BASELINE (no fixes)

Playwright lands **first**, because jsdom cannot assess rendered CSS, contrast, focus behaviour or
browser integration, and an accessibility fix list derived from jsdom would be derived from the
wrong renderer.

- `@playwright/test` as a devDependency, resolved per §9.2.
- A fixture that builds the SPA, starts `mandate-gui` on a free port, and tears it down.
- **The baseline sweep**, committed as `docs/reviews/gate-4a3-baseline.md` plus screenshots:
  - **Viewports**: `1920x1080` desktop, `1440x900` laptop (the repo's own precedent,
    `docs/roadmap.md:991`), `390x844` mobile, plus `820x900` where a screen carries a map or grid.
  - **Every available screen**: Title, Dashboard, Government, Strategic map, Relationships,
    Decisions, Turn result, History, Terminal, Glossary, and one `UnavailableScreen`.
  - **Keyboard-only traversal**: tab order recorded, focus visible at every stop, Escape ladders,
    no keyboard trap.
  - **200% zoom**, by the two methods of §9.3.
  - **Overflow and truncation**, sourced per §9.3.
  - **Live regions**: each announcement fires once and says something true.
  - **Console**: every error and warning, verbatim.
- **No fixes.** The findings are the deliverable, numbered `V1…Vn`.

### Commit 2 — accessibility baseline, from the real browser (no fixes)

- `@axe-core/playwright` against the running application, every screen, every viewport.
- Violations recorded **verbatim and numbered `A1…An`**, with impact, selector and rule id.
- Supplementary jsdom `axe-core` unit tests for per-component regressions — explicitly a
  supplement, never the primary evidence.
- **No fixes.** A baseline edited while it is taken is not a baseline.

### Commit 3 — the fix list, derived and executed

The union of `V*` and `A*`, triaged, each fix traceable to its finding number. Known members from
§3:

- **F3** — add the three missing palette tokens with **measured** contrast ratios against
  `navy-900`; replace the 7 ad-hoc Tailwind-default sites; add a boundary test asserting no
  component names a raw default-palette colour.
- **F4** — a `prefers-reduced-motion` guard covering the 3 animated sites.
- Every `V*`/`A*` that is a real defect. A finding judged not worth fixing is recorded with its
  reason and an allowlist entry naming it, never silently dropped.

### Commit 4 — the icon set, real copy, and the intro overlay

- One stroke-only 24px geometric set, **inline SVG** (no asset pipeline, no new bundle risk),
  replacing the text glyphs while preserving sign + glyph + label.
- A real-copy pass over whatever the baseline flagged as unclear.
- The "How to govern" intro overlay (§8.2): dismissible, keyboard-reachable, never blocking.

### Commit 5 — two end-to-end campaigns

**T21, the legacy campaign**: new `decree_state` → the 85/118/300 campaign → resolve to turn 11 →
terminal screen, entirely through the GUI.

**The new-features campaign, which T21 does not cover.** Government and Relationships shipped after
the frozen plan was written, so the legacy walkthrough exercises neither:

1. Government: appoint or dismiss a minister, and see it staged.
2. Relationships: bargain with a party leader whose price is projected.
3. Relationships: request foreign assistance.
4. Relationships: make a promise at the server's earliest legal deadline.
5. Decisions: preview, and read the Leader bargain / Promise release / assistance terms.
6. Resolve.
7. Turn result: read each as a driver.
8. History: re-read the same turn and confirm it renders identically.

This also closes **F11**: it is the first automated test that would catch a live-integration break.

### Commit 6 — packaging, security, budgets, internal closeout

**Packaging target — a reproducible distributable archive, not an installer:**

- **Artifact**: `dist/mandate-gui-<version>.tar.gz` containing the hatchling-built backend wheel,
  the built SPA, `data/scenarios/`, a two-command `README` and `SHA256SUMS`.
- **Verification on a clean path, never the dev tree**: unpack into an empty directory, create a
  fresh virtualenv, install the wheel with its `gui` extra, launch with **explicit**
  `--frontend-dist` and `--scenario-root` (§9.5), assert `/` → 200 and `/api/scenarios` → 200, then
  drive one Playwright turn against that instance.
- **Reproducibility**, made falsifiable per §9.5.
- **F12**: assert the promised port-collision behaviour — a second launch on a bound port fails
  fast, names the port, suggests `--port`, and does not auto-increment; and that SIGINT shuts down
  cleanly.
- **Security review** per §9.4.
- **Explicitly out of scope**, per frozen §4.11/§24: Electron/Tauri, OS installers, code signing,
  tray icons, auto-launch. Those are 4B.

**Budgets** re-measured per §5. **Closeout**: a review record, and a roadmap entry worded per §6.

---

## 5. Budgets — one enforceable threshold per budget

Frozen §18 pairs per-row targets with a blanket *"exceeded by more than 2×"* stop rule, which
contradicts the row already written as a ceiling. **Narrowed here, and recorded as a narrowing
rather than a contradiction**: every budget gets exactly one stop number.

| Budget | Target (report) | **STOP at** |
|---|---|---|
| New game, API round trip | < 150 ms | > 300 ms |
| Resolve turn, ≤ 20 | < 250 ms | > 500 ms |
| Resolve turn, ≤ 40 | < 400 ms | > 800 ms |
| Any read-only projection | < 100 ms | > 200 ms |
| Load + validate a 40-turn save | < 500 ms | > 1000 ms |
| Projection payload, any screen | < 100 KiB | > 200 KiB |
| **Initial JS bundle (gzip)** | **< 250 KiB** | **> 250 KiB** |
| Interaction → visible feedback | < 100 ms | > 200 ms |

The latency rows keep §18's 2× intent, written as absolutes so nobody computes a threshold at
review time. **The bundle row is different in kind**: 250 KiB was authored as a ceiling with a ship
consequence, so its threshold equals its target and there is no 2× headroom. Currently measured at
**98.80 KiB gzip**, 40% of the ceiling.

---

## 6. Internal completion is NOT external acceptance

Gate 4A3 has **two distinct states**, never to be conflated in any record:

- **Internally complete** — commits 1–6 landed, every automated gate green, the playtest protocol
  and observation sheet prepared, the app running per §4.11.
- **Externally accepted** — frozen §22 run by the user: five recruited strangers, at least two who
  do not play strategy games, five turns each, no facilitator coaching, and the primary fun gate,
  **at least three of five voluntarily want another turn**. The stop condition is explicit: fewer
  than three means fix the loop, do not add features.

**The roadmap entry reads "internally complete; externally pending" and nothing stronger until that
result exists.** Claiming the gate complete without the playtest would be claiming an outcome
nobody observed — the same failure as the vacuous group-58 check Commit 8 removed.

---

## 7. Scope fence

No engine change. No new mechanic. No new screen. Economy, Legislature and Constitution stay
`UnavailableScreen` — making them live needs projections that do not exist, which is a different
mandate. No contract change: **62 / 13 / `0.23.0`** moving is a stop condition.

---

## 8. Stop and report

Any budget past its §5 threshold; a screen needing a value no endpoint returns; arithmetic wanting
to live outside `src/format/**`; an axe violation unfixable without an engine change; a contract
count that moves; `playwright install` appearing necessary; or any frozen artifact needing an edit.

Standing constraints unchanged: never reset, rebase, amend, cherry-pick or force-push; push only
`claude/phase-4a-graphical-vertical-slice`; no pull request; no staging or committing while a gate
is running or failing; `docs/plans/**` (nine files, this one included, once frozen) and all 22
fixtures stay byte-identical.

---

## 9. Execution details

### 9.1 The baseline commits must be GREEN while recording defects

Commits 1–2 exist to find defects, so they must not be made to fail by finding them.

- The sweep is a **reporting script**, `npm run audit:baseline`, which writes findings and
  screenshots and **exits 0 whenever it completes**, whatever it found. A non-zero exit means the
  harness broke, never that the application has a defect.
- The only assertions in Commits 1–2 are that the sweep **ran**: the report file exists, every
  expected screen × viewport artifact is present, and the run reached the end. Coverage, not
  quality.
- **No zero-violation regression test is added until Commit 3**, and then only for findings
  actually accepted and fixed. A won't-fix gets a recorded reason and an explicit allowlist entry
  naming it, never a silently-passing scan.
- Consequence, stated because it is the point: **Commit 2 lands with known violations recorded and
  the suite green.** Committing a deliberately red suite would break the standing rule that nothing
  is committed while a gate is failing.

### 9.2 Playwright browser resolution

`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` is the browser **cache root**, not an executable path.
The binaries are `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` and
`/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell`.

- **Primary**: let Playwright resolve its own pinned revision through that environment variable —
  its normal mechanism. Nothing is passed as `executablePath`.
- **Pin**: `@playwright/test` pinned to a version whose expected Chromium revision is **1194**. A
  version expecting a different revision would try to fetch it, which
  `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` blocks, surfacing as a launch failure rather than a silent
  download.
- **Fallback, only if resolution fails**: discover the exact binary under the cache root and pass
  that one path explicitly.
- **Preflight smoke test**, the first thing Commit 1 adds and a prerequisite for everything after:
  launch Chromium, assert `browser.version()` is non-empty, assert the resolved executable path is
  **under `/opt/pw-browsers`**, and assert no browser was downloaded (the cache directory listing
  is unchanged across the run).
- **Stop condition**: if no `@playwright/test` version pins revision 1194 and the fallback also
  fails, stop and report. `playwright install` is never run.

### 9.3 Audit methods, defined so a second person gets the same result

**200% zoom — two distinct measurements, labelled, never conflated.**

- **Reflow (layout) at 200%**: emulated the WCAG way, by halving the CSS viewport at
  `deviceScaleFactor: 1` — `1440x900` → `720x450`, `1920x1080` → `960x540`, `390x844` → `195x422`.
  This is the recognised reflow method and is what catches clipping and lost content. Recorded as
  **emulating reflow**, not as byte-identical to Chrome's Ctrl+`+`.
- **Rendering at 2× device scale**: a separate pass launched with `--force-device-scale-factor=2`,
  which catches raster and focus-ring artifacts.
- Neither is described as "browser zoom" without its qualifier.

**Long names and large values — the source is recorded per case.**

- **Live server, shipped content** is the default and covers every functional case: both E2E
  campaigns, keyboard traversal, live regions, console.
- **Controlled stress fixture** covers overflow and truncation only. The fixture is a save
  **produced by the engine through production entry points** with long authored display names and
  large figures, written into the save root the server was started with, then loaded through the
  real `POST /api/game/load` — so it is still the live server and the real projection path, with
  only the content stressed.
- **Mocked `fetch` is never used for a visual or integration claim.** It stays where it already is:
  the jsdom unit tests.
- The baseline report tags every finding `live` or `stress-fixture`.

### 9.4 Security review — the frozen gate's third pillar

§19's gate is "visual polish, **accessibility, security review**, external playtest". Each item is
recorded as **verified** or **found**, never assumed.

1. **Loopback binding** — assert the listener is on `127.0.0.1` only and is not reachable on a
   non-loopback address of this host.
2. **Host / Origin enforcement** — `LocalSecurityMiddleware` exists and has 27 tests
   (`backend/tests/test_api_security.py`), but those run through `TestClient`. Re-verify the same
   rules **against the running server**: missing, malformed and non-loopback `Host`; a
   rebinding-style hostname; `Origin: null`; and an `X-Forwarded-Host` that must not be preferred
   over the real `Host`.
3. **No unexpected external requests** — Playwright request interception across both campaigns:
   every request URL must be same-origin. A font CDN, analytics or third-party asset is a finding.
4. **Archive path handling** — before extraction, assert the tarball contains no absolute paths, no
   `..` traversal and no symlinks.
5. **No development data in the shipped artifact** — `check:bundle` already proves the dev
   raw-report sentinel is absent; extend it to assert no sourcemaps ship and no
   `import.meta.env.DEV`-gated residue survives.
6. **Dependencies, the offline-checkable parts** — lockfile integrity, a pinned-version inventory
   for both `uv.lock` and `package-lock.json`, and the absence of unpinned ranges in what ships. An
   online advisory scan runs **only if** the proxy permits it; if it cannot run it is recorded as
   not-run, never reported as clean.

### 9.5 "Reproducible archive", made falsifiable

Reproducible means a second build produces the same bytes, which is only checkable if every source
of nondeterminism is pinned:

- **Entry order**: members added in sorted path order.
- **Timestamps**: every member's `mtime` set to one constant (`SOURCE_DATE_EPOCH`, defaulting to
  the commit timestamp of `HEAD`).
- **Permissions**: `0644` for files, `0755` for directories; no other modes.
- **Ownership**: `uid`/`gid` `0`, `uname`/`gname` empty.
- **Gzip metadata**: written with `mtime=0` and no embedded original filename.
- **The test**: build **twice, in two independent clean directories**, and require **identical
  SHA-256**. Both hashes are printed; a mismatch is a stop-and-report, and the diff of the two
  member tables is the evidence.
- **Unpacked verification uses explicit paths** — `mandate-gui --frontend-dist <unpacked>/dist
  --scenario-root <unpacked>/scenarios --port N`. Both flags already exist
  (`_settings_from_args`), so this needs no new implementation, and passing them explicitly is what
  proves the archive self-contained rather than quietly reading the development tree.
