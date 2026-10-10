# Gate 4A3 victory path, V-2: the objective card, the Constitution screen, the links and the result line

**Plan:** Victory path, Revision 2a. This is commit V-2. V-1 (`746897d`) built the backend.

**What V-2 changes:**
- the frontend;
- the new `victory` browser project;
- one backend **test** file that pins every fixture the new tests render.

There is **no `app/` change and no contract change**: `generate:api` is byte-identical to V-1.

## 1. What a player now sees

- **Dashboard: "Your campaign objective"** (`greybox/ObjectivePanels.tsx`). It sits right after
  "Your current priority", which is unchanged and still shows the most urgent problem.
  - It shows the server's stage headline and detail.
  - It keeps two lines apart: "Constitutional conditions: K of 3 met" and "Qualifying transition:
    recorded on turn T" (or "not recorded").
  - It shows the election note, and each condition as **"Met" / "Not yet" in words**.
  - Its one action is **"Review reforms"**, which opens Constitution.
  - In the qualifying-election stage it also shows the **existing** Survival and Legitimacy
    headlines. There is no new estimate.
  - **No progress bar, no percentage**: a test asserts the summary contains no "%".
- **Constitution, a real screen** (`screens/ConstitutionScreen.tsx`), replacing the placeholder:
  - the Constitution concern card, in every state;
  - the objective;
  - **"Draft the qualifying reform"**;
  - the checklist: condition, current value, status;
  - **"Draft this change on its own"** for each unmet condition the server links;
  - a withheld link's reason, for example "Not on its own: …";
  - the server's ordering note, and "Meeting every condition is not victory: you must then win the
    election."

  Revision 1's unsafe sentence ("the reform that completes them is the one that counts") appears
  nowhere, and a test asserts that.
- **Links replace, never merge.**
  - A link sets `requestedCardId` and opens Decisions.
  - Decisions consumes it through **the same `handleSelectCard`** as the card's own Select button:
    `chooseCardRoute`, `mapPolicyCardToDraft` and `applyCard` are unchanged.
  - So the drafted proposal is replaced wholesale, and influence is cleared.
  - If a real proposal was drafted, it says "Replaced your drafted budget with: …" (or "…amendment
    with: …"), visibly and in the live region.
  - The grid opens on the card's tab, and focus moves to the selection summary.
  - An unavailable or unknown card stages nothing and says why.
- **The preview** (`ConsequencesPanel`) adds one sentence that always begins **"If enacted, …"**.
  When resolving would not enact the draft, a second sentence follows: "This draft would not pass as
  it stands, so nothing would change." or "This draft is not affordable, so resolving it would be
  refused."
- **The turn result** shows the server's `objective_line` directly under the headline, live and in
  History.
- **D-V1:** each enacted axis is now its own line, for example "Decree authority: unlimited → none."
  and "Election schedule: none → every 4 turns.", not "The constitution was amended." four times.
- **Nav:** Constitution left the "Summaries" group, because it is no longer a summary, and is gated
  on an active game like Government. "How to govern" gains one sentence about Dashboard and
  Constitution.

## 2. Deviations from the plan's text, made and itemised here

1. **The phone's first screen** (§5: "a fresh campaign shows the objective headline without
   scrolling").
   - **Measured** at 390×844: the national header was 233 px tall, and the objective headline ended
     at y = 907.
   - **The fix:** **on the Dashboard below `lg` only**, the header's five-item concern summary is
     hidden. It repeats the five concern cards on the same screen. Every other screen, and the
     Dashboard at `lg` and wider, keep it, and its text stays in the DOM.
   - **Result:** the headline now ends at y = 823. U12's goal, stakes and Build-a-decision checks
     move **up** by 88 px.
   - I did **not** weaken the check, move the stakes line, or touch the priority card.
2. **The checklist is a list, not a table.** Buttons inside a horizontally scrolled `DataTable` could
   sit outside the viewport at 320 px. A list reflows without a scroll container, so every control
   is fully in view, which the browser checks.
3. **Two existing assertions changed for the Summaries regrouping:**
   - `ux3.test.tsx` "groups the summary screens…";
   - `verify-ux.spec.ts` `@ux3`, which now expects `["Economy", "Legislature"]` and that the
     Constitution control is still in the nav.

   The `@ux3` change was found by the first `verify:ux:v2` run, which failed on exactly that
   assertion: 1 failed, 11 passed, 14 did not run. Its log is kept as `gate-4a3-v2-verify-ux-attempt1.log`. After the change, the gate was
   re-run once.
4. **Setup-only fixture completions,** needed because the contract makes `objective` required and
   `DraftState` gained three members:
   - `objective: OBJECTIVE_FIXTURE` was added to the dashboard fixtures in four test files;
   - `requestedCardId`, `requestCard` and `clearRequestedCard` were added to `buildDecisionSet.test.ts`'s
     full-draft fixture.

   No assertion changed in those files.

## 3. Tests

**Every fixture is backend output.** `backend/tests/test_objective_fixtures.py` (10 tests) fails if any
of these differs from what the backend now produces for states reached by real resolved turns:
- `frontend/src/test/objective-stages.json`: seven stages;
- `decision-options-valdrun.json`;
- `objective-results.json`: the Valdrun reform turn's result, and three real previews (passing,
  failing vote, unaffordable);
- the three `frontend/e2e/fixtures/objective-*.json` dashboards.

The same file also checks:
- that the frontend's `QUALIFYING_REFORM_CARD_ID` equals the backend's;
- **the D-V1 label drift guards:** `CONSTITUTION_AXIS_LABEL` keys equal the engine's five amendable
  axes, and `CONSTITUTION_VALUE_LABEL` keys equal every decree, system and selection value.

**Unit tests (+34):**
- `format/objective.test.ts` (9):
  - the D-V1 lines of the real Valdrun reform, and every axis form;
  - every effect × conditions combination begins "If enacted," and contains no "%" or "will be
    recorded";
  - the exact sentences for the real previews, the same-turn election and unknown elections;
  - the caveat for the real failing and unaffordable previews, and none for the passing one.
- `greybox/victory.test.tsx` (25):
  - **the card in all seven stages,** with exact server text, words not colour, "Review reforms"
    navigating to Constitution, none when concluded, and survival and legitimacy only in the
    election stage. jsdom axe passes in every stage;
  - **the screen:** the rows in words; each link requests its card and opens Decisions; a withheld
    link has no button and shows its note; no link in `cannot_qualify` (both), qualifying-election or
    concluded; an unavailable card shows its own reason; axe passes;
  - **Decisions:**
    - a link replaces a staged budget, announces it and focuses the selection;
    - **a link does not merge** into a staged amendment: the term-limit target and the influence are
      dropped, and the player is told;
    - nothing is announced when nothing was drafted;
    - an unknown card stages nothing;
  - **the preview:** the sentence and caveat for three real previews, and nothing without an
    amendment;
  - **the result:** the objective line and D-V1 lines, live and in History; no line when the server
    sends none.

**The `victory` browser project** (`e2e/victory.spec.ts`, its own server), **9 passed, 2.1 min:**
- **A winning campaign in every scenario, through the actual links,** promoted from the audit.
  - **Each reform** is made by opening Constitution and activating **Draft the qualifying reform by
    keyboard** (focus, then Enter), not by Customize. Then Decisions is current, the selection
    summary is focused and names the card, influence is entered, and Preview is pressed.
  - **Every turn,** the interface sent exactly the audit route's recorded decisions.
  - **The results:**

    | scenario | turns | reform turn's preview | reform turn's result line | final |
    |---|---:|---|---|---|
    | `deficit_demo` | 20 | "If enacted, this reform would record the qualifying transition; the election on turn 20 would decide." | "…Win the election on turn 20 to complete it." | Victory, turn 20 |
    | `tiny_valid` | 16 | "…turn 16 would decide." | "…turn 16…" | Victory, turn 16 |
    | Valdrun | 7 | "…turn 7 would decide." | "…turn 7…" | Victory, turn 7 |

  - **Also asserted:**
    - the stage goes `reform`, then `qualifying_election` ("Win the qualifying election: turn N."),
      then `concluded` ("Objective complete: the qualifying election was won.");
    - the checklist before (2, 2 and 0 met) and after (all met);
    - "Qualifying transition: recorded on turn N";
    - the last turn's line, "Objective complete: you won the qualifying election.";
    - **no console errors.**
- **What a win can't reach,** in the real browser:
  - **Replacement:** a budget card was staged, then the link was followed. The alert reads
    "Replaced your drafted budget with: Complete the constitutional conditions in one reform."
  - **The three backend-built dashboards** (after decree none, with a withheld link, and both
    `cannot_qualify` variants) were served in place of `/api/game/state`. The stage, the headline,
    the withheld executive link, the offered interval link, and no links in `cannot_qualify` were
    all checked.
- **Reflow and accessibility, explicit:**
  - Each of these surfaces is checked at 1440, 960, 820, 720, 390 and 320:
    - the Dashboard card and the Constitution screen at the start, after the reform and at the end
      of each campaign, and in each fixture state;
    - in total, 30 surface checks per scenario and 36 for the fixtures.
  - **Each check:** no page overflow; every button fully in view horizontally after scrolling; axe
    with **0 violations**; `color-contrast` with **0 incomplete**.
  - At **390×844** on a fresh campaign, the objective headline is inside the first screen.

## 4. Gates (each its own command; its own `$?`)

| gate | exit | result |
|---|---:|---|
| backend `ruff check` / `ruff format --check` / `mypy` | 0 / 0 / 0 | |
| backend full suite | 0 | **36,534 passed** (36,524 + 10 in `test_objective_fixtures.py`), 18 min 10 s |
| `generate:api` | 0 | byte-identical to V-1 |
| `npm test` | 0 | 43 files, **648** passed (614 + 34) |
| `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| **`verify:victory:v2`** | 0 | **9 passed** |
| `verify:ux:v2` | 1, then 0 | first run: the `@ux3` Summaries assertion (§2.3); after the change, 26 passed |
| `verify:fixes:v2` | 0 | 13 passed |
| `verify:icons:v2` | 0 | 7 passed |
| `verify:terminal:v2` | 0 | 6 passed |
| `verify:campaigns:v2` | 0 | 7 passed |
| `audit:stress:seated:v2` | 0 | 6 passed |
| `audit:accessibility:verify:v2` | 0 | 6 passed; the accessibility JSON is identical to V-1's |

**The artifacts compared with V-1's, structurally. Every difference is from a V-2 change:**
- **`campaigns`:** only the bundle filenames.
- **`terminal`:** the concluded Dashboard measures 4 more text-owning elements (209 → 213), the
  objective card's.
- **`verification`:** the Dashboard's needs-review disposition measures 12 more elements (198 → 210
  overall), all on `navy-900`, the card's surface.
- **`verify-ux`:**
  - at 1440 the first viewport's stakes and Build-a-decision bottoms move 20 px down (the new
    "How to govern" sentence) and stay inside it;
  - the tint calibration nodes go from 1 to 4;
  - at 390 the goal, stakes and Build-a-decision move **up** 88 px (§2.1).
- **`stress-seated` screenshots:** they differ because of the taller "How to govern" note. Both were
  inspected.
- **`icon-coverage` and accessibility:** identical.

**Mutation checks**, each restored and confirmed with `cmp`:

| mutation | failed |
|---|---|
| `applyCard` merges amendment targets instead of replacing | "does not merge into a staged amendment…" |
| the qualifying sentence without "If enacted" | 5 (2 format, 3 preview) |
| the caveat dropped | 3 (failing and unaffordable previews) |
| the replacement announcement dropped | 2 (Decisions link tests) |
| D-V1 back to the generic label | 3 (format, and the result live and in History) |
| **backend** `QUALIFYING_INTERVAL_TURNS` 4 → 8, run against the `victory` replay | Valdrun: "turn 2: the links sent the audited decisions" fails |

## 5. Not changed

- the engine, ruleset, scenarios and save format;
- the contract, since V-1;
- the playtest protocol;
- the approved playtest build `083c7a98…`.

**V-3 records a candidate release. Switching the playtest to it stays your decision.**
