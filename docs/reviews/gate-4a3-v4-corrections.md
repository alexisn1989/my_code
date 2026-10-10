# Gate 4A3 victory path, V-4: two corrections (forward-only)

**This applies your review of `30d0b80` and `97a5dfd`.** Earlier records, artifacts and commit messages
are unchanged. This record corrects them going forward.

## 1. The failed-vote caveat is scoped to the amendment

**V-2's caveat was too broad.** Shown when the preview's `would_pass` is false, it said: "This draft
would not pass as it stands, so nothing would change." That was **wrong**: the turn's other actions,
and any election, still resolve.

**Now** (`frontend/src/format/format.ts`, `objectiveEffectCaveat`): **"This amendment would not pass
as it stands, so it would not change the constitution."**
- The unaffordable sentence is unchanged: "This draft is not affordable, so resolving it would be
  refused." That one is about the whole set, which resolve refuses.
- The two exact-string expectations moved to the new text: `src/format/objective.test.ts` and
  `src/greybox/victory.test.tsx`. No code still contains the old string.
- **This corrects** the caveat as quoted in
  [`gate-4a3-v2-objective-frontend.md`](gate-4a3-v2-objective-frontend.md) §1, which stays as it was.

## 2. The concluded Constitution screen: the V-2 claim is withdrawn

**The claim withdrawn.**
- V-2's record says the objective surfaces were checked "at the start, after the reform and at the
  end of each campaign" (§3, line 158), with "30 surface checks per scenario" (line 160).
- The `30d0b80` commit message says "…contrast decided on the new surfaces in every stage".
- **Both are too broad.** At the end of each campaign, only the **Dashboard card** was checked. The
  concluded **Constitution screen** was never checked in a winning replay.
- What V-2 did check per scenario was these five surfaces at six widths each (30): the Dashboard card
  at the start, after the reform and at the end, and Constitution at the start and after the reform.
  The fixture test's 36 checks are unaffected.

**What V-4 adds** (`e2e/victory.spec.ts`). After the concluded Dashboard check, each winning replay
now checks the concluded Constitution screen:
- the checklist is all **Met**;
- it has **no** buttons, and **no** "Draft the qualifying reform";
- the headline is "Objective complete: the qualifying election was won.";
- `checkSurface` passes at 1440, 960, 820, 720, 390 and 320: no page overflow, every control in view,
  axe with 0 violations, and `color-contrast` with 0 incomplete.

**The count is executable.** Each replay then asserts that:
- its surface log has **exactly 36** entries;
- the "Constitution (concluded)" entries are exactly those six widths, in order.

Result (`gate-4a3-v4-victory.json`): **36, 36 and 36** surface checks for `deficit_demo`,
`tiny_valid` and Valdrun. All three are still won, through the link, with no console errors. The
fixture test is unchanged, at 36.

## 3. The installed-archive walkthrough, added for V-5

V-4 adds the spec, its configuration and its script, so V-5 can stay records-only. **V-4 does not run
it against an archive.**
- **`e2e/installed-walkthrough.spec.ts`:**
  - **Walk A, Valdrun:** the card, Constitution's link by keyboard, then a failing preview with
    "If enacted, …" and the new caveat. It stops at the preview.
  - **Walk B, `deficit_demo`:**
    1. the link;
    2. influence;
    3. a passing preview;
    4. resolve;
    5. the objective line and the named amendment line;
    6. **History** showing the same line and headline;
    7. the card at the qualifying-election stage;
    8. the checklist all Met.

    Preview and resolution must agree here.
- **`playwright.walkthrough.config.ts`:** it has **no `webServer` and no `baseURL`**, so the spec can
  only reach the server it is given. The main config's `webServer` cannot be disabled per project.
- **`walkthrough:installed:v5`** sets `MANDATE_WALKTHROUGH_REQUIRED=1` and its gate label **itself**.
- **Under that flag, every one of these is required:**
  - the URL;
  - the archive path and its expected sha256;
  - the install directory;
  - the server's PID;
  - the output name.

  A missing one **fails**. Proven here: `npm run walkthrough:installed:v5` with nothing set exits
  **1** with "MANDATE_WALKTHROUGH_URL is required", and writes no record.
- **The binding:**
  - the spec recomputes the archive's **full outer sha256** and requires the expected one;
  - it requires the server PID's `/proc` cmdline to contain the **installed** `.venv/bin/mandate-gui`
    on the URL's port;
  - it requires the installed `app.__file__` to lie inside the install directory.

  All of this is recorded.
- **The record is written with `wx`,** only after every assertion holds.

## 4. Gates (each its own command; its own `$?`)

| gate | exit | result |
|---|---:|---|
| `npm test` | 0 | 43 files, 648 passed (the same count; two strings changed) |
| `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | byte-identical; no backend change |
| backend `ruff check` / `ruff format --check` / `mypy` | 0 / 0 / 0 | |
| backend full suite | 0 | 36,534 passed (unchanged: `format.ts` is read by drift tests), 33 min 49 s, run alongside the browser gates |
| **`verify:victory:v4`** | 0 | **9 passed**: 36 surface checks per replay, asserted |
| `verify:ux:v4` | 0 | 26 passed |
| `verify:fixes:v4` | 0 | 13 passed |
| `verify:icons:v4` | 0 | 7 passed |
| `verify:terminal:v4` | 0 | 6 passed |
| `verify:campaigns:v4` | 0 | 7 passed |
| `audit:stress:seated:v4` | 0 | 6 passed |
| `audit:accessibility:verify:v4` | 0 | 6 passed |

**A harness mistake, recorded.** The first launch of the eight browser gates ran `npm` from `backend/`,
because the background shell did not keep the `cd`.
- **Every one exited 254** ("Could not read package.json"), and **no test ran**. Their logs are kept
  in the session scratch as `not-run/`, and no artifact was written.
- The gates were then launched once more, with the directory pinned inside each command. Those runs
  are the ones in the table.

**The artifacts compared with V-2's:** only the bundle filenames (`campaigns`) and the output name
(`verify-ux`) differ. `icon-coverage`, `terminal`, `verification`, `stress-seated` (JSON and both
screenshots) and the accessibility JSON are identical.

**Mutation checks**, each restored and confirmed with `cmp`:

| mutation | result |
|---|---|
| the old caveat wording restored | `vitest` exit 1: 2 named failures, the caveat tests in `objective.test.ts` and `victory.test.tsx` |
| the concluded-Constitution block removed from `victory.spec.ts` | `playwright` exit 1 for **each** replay: "deficit_demo: surface checks", "tiny_valid: surface checks" and "decree_state: surface checks". Each expected length 36 and received 30. In the full project run, the serial mode stopped after the first; the other two were then run alone, and each failed |

**Not changed:**
- `app/`, the contract, the engine, the scenarios;
- the approved playtest build (`083c7a98…`) and the roadmap;
- every earlier record.
