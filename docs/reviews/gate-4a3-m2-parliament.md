# Gate 4A3 M-2: Parliament and the shared preview

**Authorized by:** your instruction "Incorporate that retry-display rule and test, then implement M-2
only. Run the specified gates and return the record plus desktop/mobile Parliament screenshots.
Stop on failure."
- **Not authorized:** a commit, a push, M-3, a candidate build or a build switch. None was done.
- **The plan:** M-2 Revision 2, with your five state rules, marked [R2], and the retry-display rule.

**Scope:**
- **Frontend only:**
  - no backend application, data or contract change;
  - `generate:api` is byte-identical to `HEAD` (`506790e`);
  - one backend **test** is added: the role-label drift guard.
- **Not included:** no bloc panel, no negotiation and no staging from Parliament (M-3); no result
  restructure (M-4).

## 1. What changed

### 1.1 The shared preview (`src/state/previewStore.ts`, `src/state/useDraftPreview.ts`; new)
- **One store, read by Decisions and Parliament.** It replaces the `useMutation` that lived inside
  `DecisionsScreen`.
- **Every part carries the signature of the draft it was requested for:** the result (`entry`), the
  failure (`error`) and the loading state (`pending`).
  - **`previewView(state, signature)` derives, at render, what a screen may show for the current
    draft:**
    - `current`: the result, only for this draft;
    - `stale`: a result exists, but for another draft;
    - `pendingForDraft`;
    - `errorForDraft`: a failure, only for this draft.
  - **[R2]** A delayed failure for an edited-away draft never appears against the new draft. A
    request for an edited-away draft shows no "Previewing…", and Preview stays enabled.
- **Only the latest request of the current epoch may write.** `begin` issues a request id;
  `accept`/`fail` are dropped otherwise, so an older response landing after a newer one changes
  nothing.
- **The lifecycle token (`epoch`) [R2]:**
  - **always advanced on an explicit event:** a resolve (`useResolve`) and a new game or load
    (`clearCampaignScopedState`), even of the same campaign and revision;
  - **advanced in `SessionProvider.setCampaignView`** only when the revision or the campaign id
    actually changes, so re-adopting an unchanged view keeps a valid preview;
  - a response requested under an older epoch is dropped, whatever its timing.
- **The retry-display rule (the latest attempt for a draft decides):**
  - `begin` clears the stored error, so a retry hides the old error at once;
  - while a retry is pending, an earlier result for the **same** draft stays visible;
  - a retry that **fails** hides that earlier result (`current` is null when the draft's newest
    failure is newer than its result), so a verdict never sits beside an error for the same
    request.
- **Supporting changes:**
  - `src/format/counters.ts`: `nextCount`, because the format boundary forbids `+ 1` outside
    `src/format/`;
  - `src/test/setup.ts` resets the store after each test.

### 1.2 Decisions (`DecisionsScreen.tsx`)
- **Reads the shared preview:**
  - the result shows only when `current`;
  - "preview-outdated" shows when `stale`;
  - the error panel and "Previewing…" follow `errorForDraft` and `pendingForDraft`.
- **Focus [R2].** After Preview, focus moves to the result's heading only for a request **this
  mounted screen instance** issued. Its id is kept in local state, so a response landing after the
  player has left, or after a remount, moves no focus.
- **Its existing tests pass unchanged:** the preview presentation tests, W-1, W-2, and the API
  `usePreview` test. `usePreview` stays exported for that test.

### 1.3 Parliament (`greybox/screens/ParliamentScreen.tsx`, `greybox/parliament/Hemicycle.tsx`; new)
- **The registry's `legislature` entry renders it.** The id, the nav name and the heading
  "Legislature" are unchanged; it now requires a campaign. Legislature leaves the nav's
  "Summaries" group, as Constitution did.
- **Your draft:**
  - the proposal (the card's title when the draft still matches it, otherwise the staged wording);
  - a status: current / not previewed / changed since / previewing;
  - **Change in Decisions** and **Preview**, which runs the same shared preview;
  - the decree sentence;
  - the unaffordable sentence;
  - signature-bound errors.
  - **A concluded campaign** shows "The campaign has ended." with no buttons.
- **One card per chamber, from `chamber_details`:**
  - **Thresholds:** "A budget needs N" and "An amendment needs N", the engine's values.
  - **The hemicycle has exactly two modes [R2]:**
    - **`current`:** only for a current preview, on the legislative route, in a running campaign.
      Filled seats are the preview's own bloc rows.
    - **`seats`:** everything else, with the reason in words.
  - **The tally:** "N supporting if resolved now · N needed · Would (not) carry", with a bar and a
    legend. Support is shown as filled against hollow plus numbers, never by colour alone.
  - **The bloc table:** bloc (with party and stance beneath), seats, supporting if resolved now,
    and relationship.
- **Last recorded vote:**
  - the stored proposal sentence;
  - one line per chamber, with the stored tallies;
  - for budgets, the stored per-bloc rows ("Seats then", "Supporting");
  - for amendments, "Per-bloc votes are not recorded for amendments.", with no rows.
  - **[R2]** This is the only place history appears; it is never drawn onto today's chamber.
- **[R2] A concluded campaign suppresses every live estimate,** even with a matching preview stored.
- **No legislature:** "No legislature sits in {country}."
- **The seat diagram** (`format/hemicycle.ts`):
  - the mockup's geometry;
  - the measured width decides whether arc labels fit (from 560 px) and whether seats would fall
    below 6 px, in which case bars are drawn instead (unit-tested with 400 seats; no shipped chamber
    needs them).
- **Wording** is in `format/parliament.ts`. It says "supporting if resolved now", because
  `check:copy` forbids "projected". The role labels are drift-guarded against `GovernmentRole`.

### 1.4 Changed after the first browser screenshots
**At 390 px the bloc table's numbers scrolled off the edge,** contained but out of view, beside a
separate "Party · stance" column. Party and stance now sit under the bloc's name. At 390 px, Seats
and "Supporting if resolved now" stay in view, and Relationship scrolls inside the table's
keyboard-reachable container.

## 2. Forward-only updates to existing tests
| file | change | why |
|---|---|---|
| `src/greybox/ux3.test.tsx` | the "Summaries" group is `["Economy"]`; Legislature is asserted present in the nav by name | Legislature is a full screen now |
| `src/greybox/GreyboxApp.accessibility.test.tsx` | its hand-built decision options gain `chamber_details: []` | M-0 made the field required, and Parliament reads it; the mock's own comment requires "empty rather than absent" |
| `e2e/verify-ux.spec.ts` | `@ux3`: the "Summaries" group is `["Economy"]`; Legislature is visible in the nav by name | same as ux3 |
| `src/test/setup.ts` | resets the preview store after each test | the store is module-level |
| `e2e/redesign.spec.ts` (`@m1`, from M-1) | the spec's own API calls (the server-ready poll, the stylesheet fetch, and M-2's two `decision-options` reads) go through `apiGet`, which sends `Connection: close` | `final5`'s "socket hang up" (§6, item 6). No assertion changed |

No assertion was removed or reversed in M-2.

## 3. New tests
- **`src/state/previewStore.test.ts`** (8 tests), checking the store directly:
  - out-of-order responses;
  - invalidation;
  - signature-bound loading and errors;
  - the retry-display cases (a), (b) and (c).
- **`src/greybox/m2.test.tsx`** (33 tests), through the real Decisions and Parliament screens with
  controlled preview responses:
  - **Parliament content:**
    - the engine's thresholds, with an upper-chamber budget threshold of 37, not
      floor(60 / 2) + 1 = 31;
    - before and after Preview;
    - bloc rows and filled seats that sum to each chamber's tally;
    - every seat drawn;
    - decree;
    - a failing chamber;
    - no recorded vote;
    - a recorded budget vote, shown only under "Last recorded vote";
    - an amendment vote with no invented rows;
    - a concluded campaign with a matching preview stored;
    - no legislature;
    - no "projected".
  - **Freshness:** an edit of each kind (the proposal, the route, influence, a bargain, an
    investment) hides the estimate on both screens; a late response; two requests in either order.
  - **Lifecycle:** a response held across a resolve, a load, a new game or a view-changing refresh
    (re-applying the same draft, so only the epoch stands in the way).
  - An unchanged view keeps a valid preview.
  - Errors and loading follow the draft, on both screens.
  - The retry-display rule (a), (b) and (c), on both screens.
  - **Focus:**
    - a Decisions preview landing after the player left moves no focus, now or on return;
    - Parliament never moves focus, and announces only its own requests;
    - the heading survives loading (§6, item 2).
- **`src/format/hemicycle.test.ts`** (7 tests):
  - one point per seat for 1 to 400 seats;
  - no two seats touching;
  - left-to-right order;
  - the shipped chambers at least 6 px at 320 px;
  - the bars fallback at 400 seats;
  - the bars and the tally maths.
- **`backend/tests/test_parliament_copy.py`** (3 tests): the role labels and order equal
  `GovernmentRole`, with an anti-vacuity count.
- **`e2e/redesign.spec.ts` `@m2`** (9 browser tests):
  - **at each of the six widths, on Arken (two chambers) and Valdrun:**
    - the thresholds equal `chamber_details`;
    - every seat is drawn, at least 6 px, with no overlap;
    - the stylesheet applies;
    - no page overflow and no clipped node;
    - axe is clean on `main` before and after Preview;
    - a preview **from Parliament** whose numbers equal the response, with rows that sum;
  - **journeys at 1440 and 390 (touch):**
    - an edit after Preview;
    - a held response edited away;
    - a response held across a resolve;
    - a Valdrun decree (no tallies);
    - a Valdrun failed vote, afterwards only under "Last recorded vote", with the chamber showing
      no support;
  - **keyboard:** a late response never steals focus, from Decisions or from Parliament.

## 4. Gates
**Final run `final6`, on the final tree.** Each command ran on its own, and its own `$?` is shown.
Logs: session scratch `m2/final6/`. The tracked diff and the untracked file hashes were the same before
and after the run (`tree-unchanged-during-run` exit 0). A read-only watcher sampled the server and
renderer processes throughout.

| gate | exit | result |
|---|---|---|
| `npm test` | 0 | 50 files, 729 tests passed (681 at M-1, plus 48 new) |
| `npm run typecheck` | 0 | |
| `npm run build` | 0 | |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0, 0, 0, 0 | |
| `generate:api` | 0 | byte-identical to `HEAD` |
| `verify:redesign:m2` (`@m1` and `@m2`) | 0 | 20 passed. Run through a scratch config that is the repository's Playwright config plus a trace and screenshot on failure; the same spec, filter and artifact name |
| `verify:victory:m2` | 0 | 10 passed |
| `verify:ux:m2` | 0 | 29 passed |
| `verify:fixes:m2` | 0 | 13 passed |
| `verify:icons:m2` | 0 | 7 passed |
| `verify:terminal:m2` | 0 | 6 passed |
| `verify:campaigns:m2` | 0 | 7 passed |
| `audit:stress:seated:m2` | 0 | 6 passed |
| `audit:accessibility:verify:m2` | 0 | 6 passed |
| backend `ruff check`, `ruff format --check`, `mypy` | 0, 0, 0 | |
| backend `pytest -q` | 0 | 36,581 passed, 1 skipped (the existing `decree_state` skip). The 3 new are the role-label drift guard |

**Artifacts (uncommitted):**
- `gate-4a3-m2-{redesign,victory,verify-ux,verification,icon-coverage,terminal,campaigns,stress-seated-cabinet}.json`;
- `gate-4a3-m2-redesign-shots/` (dashboard and Parliament screenshots per width, plus the journeys'
  recorded-vote views);
- `gate-4a3-m2-stress-seated-cabinet-shots/`;
- `gate-4a3-accessibility-after-m2.{json,md}`.

## 5. Mutation checks
Each mutation was applied from a scratch backup, run, restored, and checked with `cmp` (restored =
yes for all). Browser mutations were run on a rebuilt bundle, through the same spec with failure
tracing; the bundle was rebuilt again after each. Logs: `scratchpad/m2/mutations/`.

| # | mutation | result |
|---|---|---|
| S1 | `accept` without the epoch check | exit 1: "drops a response requested before invalidate…", and all four "a response held across {a resolve, a load, a new game, a stale-view refresh} is never shown" |
| S2 | `accept` without the latest-request check | exit 1: "keeps B when an older A lands after it", "the latest of two requests wins…" |
| S3 | `previewView.current` ignoring the signature | exit 1: "an undo shows the same result again", the edit tests (proposal, route, influence, bargain, …) and others |
| S4 | `errorForDraft` returning any error | exit 1: the signature-bound error tests, on both screens, and retry (c) |
| S5 | `begin` not clearing the error | exit 1: retry (a), in the store and on both screens |
| S6 | `current` ignoring a newer failure | exit 1: retry (b), in the store and on both screens |
| S7 | `setCampaignView` invalidating unconditionally | exit 1: "re-adopting the unchanged view keeps a valid preview" |
| P1 | thresholds calculated as floor(n / 2) + 1 | exit 1: "…the engine's own thresholds…" |
| P2 | the chamber filled from `last_recorded_vote` | exit 1: "…never drawn onto today's chamber" |
| P3 | the per-bloc table rendered for an amendment, without the note | exit 1: "…and no invented bloc rows". The mutation produced an **empty** table, not invented rows; the test rejects any table there |
| **P4** | the terminal check removed from the chamber mode | **first run: SURVIVED (exit 0).** The test was vacuous: see §6, item 5. **After the test fix (P4b): exit 1**, "a concluded campaign shows no live estimate, even with a matching preview stored" |
| P5 | the hemicycle dropping a seat | exit 1: "draws every seat…", "…bloc rows that sum to it" |
| P6 | Decisions' focus effect keyed on any accepted entry | exit 1: "a Decisions preview landing after the player left moves no focus…" |
| H0 | the loading-state heading back in its old position | exit 1: "keeps the focused heading element when the data arrives" |
| B1 | (browser) `current` ignoring the signature | exit 1: `@m2` freshness journeys at 1440: expected "Your draft has changed since the last preview", received "Preview is current for this draft" |
| B2 | (browser) Decisions' focus effect keyed on any accepted entry | exit 1: `@m2` keyboard journey: focus landed on `preview-result-heading` on return |

**Not re-run after the P4 test fix or the `Connection: close` change:** S1–S7, P1–P3, P5, P6, B1 and
B2.
- The P4 fix changed only the one concluded-campaign test in `m2.test.tsx`.
- The spec change touches only how the spec makes its own API calls.
- Every mutated source file is byte-identical to the one they ran against.

## 6. Superseded attempts and failures
1. **`final1`: stopped, superseded.** It was stopped (TaskStop) during `npm test`, before any exit
   status was recorded, because `e2e/verify-ux.spec.ts:504` still expected Legislature in the
   "Summaries" group. It wrote no artifacts.
2. **`final2`: `verify:redesign:m2` exit 1. Every other gate exited 0** (728 unit tests, backend
   36,581 passed).
   - **The failure:** in M-1's place checks at 960 px, "pin and list land on the same heading:
     Parliament"; the focused element was `<body>`.
   - **The cause, a real defect:** a place focuses the destination's heading as soon as it renders.
     Parliament's loading state rendered its heading at a different tree position from the loaded
     state, so React replaced the element when the data arrived and focus fell to the page.
   - **The fix:** the heading sits at the same position in every state.
   - **The new test** "keeps the focused heading element when the data arrives" fails against the old
     markup (H0).
   - Artifacts: `scratchpad/m2/final2/artifacts-superseded/`.
3. **`final3`: `verify:redesign:m2` exit 1. Every other gate exited 0** (729 unit tests, backend
   36,581 passed).
   - **The failure:** in `@m1` at 1440, the first navigation to Parliament (pin, Enter) ran into the
     300-second test limit. The step was `toHaveAttribute("aria-current", "page")`; its 10-second
     expectation never returned.
   - The dashboard screenshot was written at 04:51 and the failure came at 04:56.
   - **Not reproduced afterwards:**
     - 6 isolated runs of that test and 3 full `redesign` runs, all passing;
     - the bounded investigation's 16 full runs with failure tracing and a CPU watcher: 10 plain,
       3 after build and `generate:api`, and 3 under CPU contention. All passed (20 of 20, 118–146
       seconds).
   - **The cause was not established.** It is recorded as an unexplained intermittent stall: 1 of 26
     executions before `final4`. Artifacts: `scratchpad/m2/final3/artifacts-superseded/`;
     investigation: `scratchpad/m2/investigate/`.
4. **`final4`: every gate exited 0.** `redesign` ran through the scratch config with failure tracing
   and passed 20 of 20. It was superseded only because a test file then changed (item 5). Artifacts:
   `scratchpad/m2/final4/artifacts-superseded/`.

**Every superseded run's evidence is kept in the session scratch:** logs, exit statuses, traces and
artifacts.
5. **Mutation P4 survived the tests that `final4` ran.**
   - **The cause, a vacuous test:** the concluded-campaign test stored the matching preview **before**
     rendering. When the harness adopted the campaign view, the view change correctly advanced the
     epoch and cleared the store, so there was never a preview to suppress.
   - **The fix, to that one test:** it now previews in a running campaign (and asserts the estimate is
     shown), leaves Parliament, ends the campaign, asserts that a matching preview is still stored, and
     returns. Then the original assertions.
   - P4 now fails it (P4b, exit 1). The gates were re-run once (`final5`).
6. **`final5`: `verify:redesign:m2` exit 1. Every other gate exited 0** (729 unit tests, backend
   36,581 passed).
   - **The failure:** in `@m2` at 1440, just after starting Valdrun, the spec's own
     `page.request.get("/api/game/decision-options")` failed with `socket hang up`. 11 passed and 8
     did not run.
   - **What the trace shows:**
     - every request the browser made succeeded;
     - the failing request was the spec's, sent 5.02 seconds after the previous request on the same
       API connection;
     - `mandate-gui` runs uvicorn 0.52.1 with its default `timeout_keep_alive` of 5 seconds;
     - the watcher showed both server processes alive and idle throughout.
   - **The hypothesis:** the test client reused a pooled keep-alive connection just as the server
     closed it.
   - **The attempt to prove it did not reproduce the race.** A scratch script, using Playwright's own
     `APIRequestContext` against a single-process scratch server, waited between two requests on one
     connection: 4 rounds, 163 trials per arm, across 4.900–5.095 seconds (finest step 1 ms). There
     were 0 connection failures with or without the header. **So the race is a well-supported
     hypothesis, not a demonstrated cause.**
   - **What was shown:** without the header the client keeps its connection open after a response,
     ready for reuse (0 open before, 1 after); with `Connection: close` it does not (0 after).
     - The first version of this socket probe was **invalid**: it relied on `ss`, which is not
       installed, so its counts meant nothing. It was redone by reading `/proc/net/tcp`.
   - **The change:** the spec's own calls send `Connection: close` (§2), so they never reuse a pooled
     connection. A development run passed 20 of 20, and `final6` passed.
   - **Also noted:** during `final5` I ran two unit-test files (15 tests, a few seconds, read-only),
     about a minute before this failure. It may have competed for CPU, though nothing ties it to the
     failure.
   - Artifacts: `scratchpad/m2/final5/artifacts-superseded/`; trace and logs:
     `scratchpad/m2/final5/`; race evidence: `scratchpad/m2/race/`. The scratch servers were stopped
     by single PIDs verified by cmdline and cwd.
7. **Development, before the gates:**
   - the 390 px bloc table (§1.4);
   - a pre-check that ran against a stale bundle was avoided by building before every browser run;
   - `--repeat-each` reproduction attempts failed on the spec's write-once output, not on any test,
     and were replaced by separate runs.

## 7. Screenshots compared with the approved mockups
Against the approved round-2 mockups (`parliament-tiny-preview`, `parliament-valdrun-draft`,
`parliament-tiny-recorded`):
- **The same structure:** the draft panel, then a card per chamber (the title with its seats, the
  thresholds, the hemicycle coloured by party with filled and hollow seats, the tally line with a
  verdict and bar, the legend, the bloc table), then "Last recorded vote".
- **Intended differences:**
  - thresholds are the engine's values, so the mockup's asterisk note is gone;
  - "projected" is worded "supporting if resolved now";
  - **a recorded vote is not drawn onto the chamber** (the mockup's `tiny-recorded` view did). It is
    shown only under "Last recorded vote", with its stored rows [R2];
  - party and stance sit under the bloc's name, rather than in their own column;
  - the Legislature summary card comes last.

## 8. Not done
- No commit or push. M-3 and later steps, a candidate build and a build switch are not authorized.
- **No bloc panel or staging from Parliament:** rows are plain text. That is M-3.
- **In the browser, a response held across a resolve can never match the new draft's signature**
  (the revision differs), so that journey proves only that nothing is shown. The epoch-specific
  cases, where the same signature returns after the event, are proved in the unit tests.
