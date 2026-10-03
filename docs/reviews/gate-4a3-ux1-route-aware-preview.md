# Gate 4A3 UX-1 — a route-aware preview, a visible route, and advice that says what to do

**Subject:** `Gate 4A3 (UX-1): make the preview route-aware and the decree choice visible`
**Parent:** `d1c0920153a50728f823b775951040d150257115` (Commit 6c), not amended.
**Plan:** the UX polish pass approved for UX-1 to UX-4 (U2 + U3 in this commit).
**Evidence:**
- `gate-4a3-ux1-verify-ux.json`
- `gate-4a3-ux1-{verification,icon-coverage,terminal,campaigns,stress-seated-cabinet}.json`
- `gate-4a3-ux1-stress-seated-cabinet-shots/`
- `gate-4a3-accessibility-after-ux1.{json,md}`

The external playtest watches whether a stranger discovers the **decree-versus-legislature**
trade-off without help. Walking the current build showed two problems in Kingdom of Valdrun:

- the decree route was hidden;
- once found, the preview mis-stated what a decree does.

This commit fixes both. The internal walkthrough was not a playtest, and nothing here claims a
playtest result.

---

## 1. A real defect, fixed first: the preview ignored the route (U2)

`preview_decisions` (`backend/app/api/preview.py`) scored the legislature for **every** proposal. The
resolver handles a decree differently. Its `ProposalRoute.DECREE` branch (`phases.py`) enacts a decree
budget as `ENACTED_BY_DECREE` with **no chamber vote**.

So in Valdrun a decree budget previewed as *lower 45 / 51 — Fails — Would not pass*, while resolving
the same draft reported *"The budget was enacted by decree. The legislature was bypassed."* This was
reproduced against the unmodified code before the fix:

| | preview (before) | real resolution |
|---|---|---|
| Valdrun, raise income tax, **decree** | `would_pass: false`, one failing `lower` chamber row | 200, *"The budget was enacted by decree…"* |

**The fix.** It lives in the API layer only; the engine is untouched.
- A decree proposal previews `chambers=()` and `would_pass=True`, because it is enacted without a
  vote.
- Whether resolution would accept it at all is `affordable`, together with the structural check,
  which rejects the request outright.
- The legislative path is unchanged.
- The `would_pass` docstring now states the decree meaning.
- `generate:api` is **byte-identical**: 62 / 13 / `0.23.0`.

**Parity tests** extend `tests/test_api_preview_parity.py`. Every case runs the preview **and** a real
resolve from the same opening save:

| case | preview | resolution |
|---|---|---|
| Valdrun budget by **decree** | `chambers=[]`, `would_pass=true`, route cost 250 | 200, "enacted by decree", no chamber rows in the trace |
| the same budget, **legislative** | per-chamber supporting/required | equal, chamber for chamber, to the resolved trace; "blocked" |
| decree **with influence** | 422 `decision_rejected` | 422 `decision_rejected` |
| **unaffordable decree** (250 + 200 + 200 = 650 > 500) | `affordable=false`, committed 650 | 422 `decision_rejected` |
| bicameral, failing in **one** chamber | lower carries, upper fails | equal row for row; "blocked" |
| bicameral amendment failing in **both** | both fail | equal |
| amendment by decree where a **legislature sits** (Valdrun) | 422, *"…while a legislature sits…"* | 422 |
| amendment by decree with **no legislature** | `chambers=[]`, `would_pass=true`, cost = `decree_amendment_capital_cost` (400) | 200 |

Rejections are compared by **status and type** (`422`, `decision_rejected`), not by message, because
the preview and resolve messages differ.

**Two cases were first written vacuously and are now anti-vacuous.** My first draft used a wrong axis
name (`term_limit`) and a non-existent bloc (`crown_party/core`). Two "both reject" tests then passed
for the wrong reason: a schema error, not the rule under test. Both now prove the rejection is about
the rule:
- the decree-with-influence case shows the **same** influence accepted on the legislative route;
- the legislature-sits case asserts the response names that rule.

**What shipped content cannot reach, measured rather than assumed.**
- No budget in `tiny_valid` fails in either chamber: rates from 500 to 5,000 bps and spending scaled
  ×0.3 to ×3 all carried.
- Every amendment there fails in **both** chambers, whatever influence is spent.
- No shipped scenario lacks a legislature.

The one-chamber and no-legislature cases therefore use **test-only variants**. These are copies of
`tiny_valid` and `decree_state` edited under `tmp_path` (six upper seats moved, or the legislature
removed). Both load through the production scenario loader. **No shipped scenario changed.**

**The guards bite.** With the fix reverted (`decreed = False`), the two decree tests fail and the rest
pass.

## 2. The route is visible, and the preview says what to do (U3)

- **The route control renders once, outside "Customize policy"**, for whichever proposal is drafted.
  It shows that proposal's own decree price: `decree_legislative_capital_cost` for a budget,
  `decree_amendment_capital_cost` for an amendment. Before, the decree option lived only inside the
  collapsed editor.
- **`decreeAllowed(kind, options)`** (`format.ts`) mirrors the resolver, using only existing option
  fields:
  - a budget may be decreed when `decree_available`;
  - an amendment needs `decree_available` **and** `chambers.length === 0`.

  So in Valdrun the amendment route offers Decree **disabled**, and its advice never mentions decree.
- **Pre-resolution decree wording**, built in `format.ts`:
  - when affordable: *"If resolved now: enacted by decree — the legislature is bypassed. Route cost
    250."*
  - when not affordable: *"Not affordable: 650 of 500 committed — resolving this draft would be
    refused."*

  A decree shows no vote table, no "Would pass", and no shortfall advice.
- **A legislative proposal that would fail** gets one line **per failing chamber**, from that
  chamber's own row (*"Upper chamber: 4 short of 31."*), never a pooled gap. A closing line follows:
  *"You can add influence capital for blocs above"*, plus *", or switch the route to decree (cost
  C)"* only when this proposal kind may be decreed.
- **Focus** moves to the "Known before resolution" heading after Preview.
- **Zero capital terms are hidden**, and the total is always shown.
- **Chamber and route names** come from authored maps ("Lower chamber", "Legislative vote"), never
  the raw `lower` / `legislative`.

## 3. Tests

**Frontend:** `DecisionsScreen.preview.test.tsx` has +9 tests, and the frontend total went **485 →
494**.
- Three existing expectations changed **by design**, each annotated in the test:
  - the chamber is named "Lower chamber", not `lower`;
  - a decree shows the decree sentence instead of the no-vote note and "Would pass".
- The new tests cover:
  - the unaffordable wording;
  - per-chamber lines with no pooled gap;
  - the decree clause only when allowed, at its own price;
  - a Valdrun amendment never offered a decree;
  - a no-legislature amendment offered one at 400;
  - the route control outside `<details>`, exactly once;
  - zero terms hidden;
  - focus after Preview;
  - no raw identifiers.
- `e2e/campaigns.spec.ts`: one expectation changed by design. A zero promise-release term is no
  longer rendered.

**Browser:** the new cumulative **`e2e/verify-ux.spec.ts`**, with its `@ux1` block run by
`verify:ux:1`, walks Valdrun at **1440×900, 390×844 and 320×800**:
- select a tax card;
- the route control is visible, outside Customize, once;
- the legislative preview fails, and the advice has one line per failing chamber plus the decree
  clause at 250;
- focus is on the result heading;
- no raw identifiers appear;
- Decree → preview shows no table and the pre-resolution sentence;
- a Valdrun amendment offers Decree disabled.

At 1440 the decree is resolved, and the turn result reads *"The budget was enacted by decree. The
legislature was bypassed."* The spec requires `MANDATE_UX_OUT` and writes with `wx`.

**Evidence protection:** `stress-seated-cabinet.spec.ts` wrote its committed JSON **and** two
committed screenshots in place, with no name parameter. It now takes `MANDATE_STRESS_SEATED_OUT` (the
default is unchanged), so this commit's re-run wrote beside the committed files. Both screenshots and
the JSON reproduced **byte-identical** to the committed ones.

## 4. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  494 passed (494)` (485 → 494, +9 in `DecisionsScreen.preview.test.tsx`) |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-BM4phN3N.js` 346.93 kB / 100.25 kB gzip; CSS `index-DjFAPDAb.css` 18.11 kB, **byte-identical by hash** to 6c (no new utility class) |
| `npm run check:bundle` | 0 | `check-bundle: OK -- no dev-raw-report sentinel in 1 built JS file(s); no sourcemap, no import.meta.env, index.html same-origin; initial JS 96.64 KiB gzip (level 9) of a 250 KiB budget, 153.36 KiB headroom.` |
| `npm run check:palette` | 0 | `check-palette: OK -- 40 source file(s), 16 colour token(s) defined, no default-palette colour, no sub-60 text alpha, every referenced token defined.` |
| `npm run check:copy` | 0 | clean (allowlist printed, unchanged) |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- source(none), 2 shipped source pattern(s), 1 exclusion(s): ../**/*.{ts,tsx}, ../../index.html, not ../**/*.test.{ts,tsx}` |
| `npm run verify:ux:1` | 0 | `8 passed (10.8s)` — the `@ux1` block at 1440, 390 and 320 |
| `npm run verify:campaigns:ux1` | 0 | `7 passed (24.7s)` |
| `npm run verify:terminal:ux1` | 0 | `6 passed (37.2s)` |
| `npm run verify:fixes:ux1` | 0 | `13 passed (40.3s)` |
| `npm run verify:icons:ux1` | 0 | `7 passed (11.8s)` |
| `npm run audit:stress:seated:ux1` | 0 | `6 passed (7.0s)` |
| `npm run audit:accessibility:verify:ux1` | 0 | `6 passed (1.6m)`; `accessibility report written: 0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |
| `ruff format --check .` (backend) | 0 | `190 files already formatted` |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| bare `mypy` | 0 | `Success: no issues found in 56 source files` |
| `npm run generate:api` | 0 | no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical, 62 / 13 / `0.23.0`** |
| `pytest -q tests/test_api_preview_parity.py` | 0 | `40 passed` (+8) |
| full backend suite `uv run pytest -q; echo PYTEST_EXIT=$?` | **0** | `36363 passed, 1 warning in 1443.69s (0:24:03)` — +8 from 36,355, exactly the new parity tests; the 1 warning is the known `StarletteDeprecationWarning`. (A first run was lost to a container restart; this is the re-run.) |

**Artifacts compared with Commit 6's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux1-verification.json` | byte-identical to `gate-4a3-commit6-verification.json` |
| `gate-4a3-ux1-icon-coverage.json` | byte-identical to `gate-4a3-commit6-icon-coverage.json` |
| `gate-4a3-ux1-terminal.json` | byte-identical to `gate-4a3-commit6-terminal.json` |
| `gate-4a3-accessibility-after-ux1.{json,md}` | byte-identical to `…-after-commit6.{json,md}` |
| `gate-4a3-ux1-stress-seated-cabinet.json` + both screenshots | byte-identical to the committed `gate-4a3-stress-seated-cabinet.json` and `gate-4a3-baseline/stress-*__Government-seated.png` |
| `gate-4a3-ux1-campaigns.json` | measurements unchanged; bytes differ in exactly one field, `sameOrigin.distinctPaths[10]`, the built JS filename (`index-CjkzPwt-.js` → `index-BM4phN3N.js`) |

**Scope:**
- Backend: `app/api/preview.py`, one docstring in `app/api/projections.py`, and the parity tests.
- Frontend: `format.ts`, `components.tsx` (the `Panel` `headingId`), `ConsequencesPanel.tsx`,
  `DecisionsScreen.tsx` and its preview tests.
- e2e: the new `verify-ux.spec.ts`, the stress-seated output parameter, one campaigns expectation, and
  the `ux` Playwright project and scripts.
- Out of scope, and not in the diff: `app/simulation/`, `app/core/`, any scenario, fixture, frozen
  plan, the contract, and any earlier review artifact.

