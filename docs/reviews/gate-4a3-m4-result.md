# Gate 4A3 M-4: the result restructure

**Authorized by:** your instruction "Implement M-4 with the approved defaults and clarifications", on
the M-4 plan with your three defaults and three clarifications.
- **Not authorized:** a commit, a push, M-5, a candidate build or a build switch. None was done.

**The defaults, as approved:**
1. **Portraits** are added in `app/api` from the state the recorded turn produced.
2. **The proposal card** is `navy-900` with a `gold-600` border; the verdict is a bordered word.
3. **Seat colours** are derived from the recorded rows, one palette per vote.

**Scope:**
- **Frontend, plus one `app/api` enrichment.** No engine, data or save change.
- **The contract shape is unchanged** (`params` stays `dict[str, str | int]`), and `generate:api` is
  byte-identical to `HEAD` (`a2c7663`).

## 1. What changed

**`greybox/TurnResultView.tsx`** is still the one component behind the live Result screen and
History, now laid out as the approved M-V `result` mockup:
1. **The proposal card**, headed "Turn outcome" (the heading tests hold):
   - the verdict in words: "Enacted", "Did not carry", "Enacted by decree" or "No proposal", read only
     from `recorded_vote.outcome` or `no_vote_reason`;
   - the headline with its tone, and the objective line;
   - "Your proposal": `recordedProposalSentence`, the sentence Parliament's "Last recorded vote"
     uses, or "No proposal was put to a vote this turn.";
   - the vote and enacted-change drivers;
   - **for a vote:** one block per chamber with `recordedChamberLine`.
     - **Budgets** add a seat diagram from the stored bloc rows (new `Hemicycle` mode `recorded`)
       and a collapsed "Votes by bloc (recorded)" table.
     - **Amendments** show totals and "Per-bloc votes are not recorded for amendments.", with no
       diagram and no rows.
2. **People and reactions:**
   - the bargain, cabinet, assistance and promise entries, each with its sentence (unchanged
     wording) and the portrait from that turn when the server attached one;
   - **"How the blocs took it":** one row per bloc ("▲ closer", "▼ cooler" or "• no change", the
     signed points, "relationship opening → closing"), with that bloc's reactions listed under it.
3. **What else happened:** every other non-routine driver, in `outcomeFirst` order
   (`data-testid="drivers-consequential"` kept).
4. **Collapsed:** Routine steps (still controlled, so a Trace link opens it), "What your decision
   committed (N)", "What did not change", and the Trace (unchanged).

**`format/result.ts` (new):**
- **`partitionDrivers`** places every driver exactly once and keeps its **original index**, so every
  anchor and Trace link is unchanged.
  - **Bloc reactions are matched by the pair `{party_id, bloc_id}`.**
  - **A reaction with no matching bloc row** is listed in `unmatched` **and** shown under "What else
    happened". The view carries `data-unmatched-components`.
- **`voteColours`:** one palette from the union of party ids across all chambers, chambers in stored
  order then rows in stored order.
- Also the verdict, the bloc move, the person beside an entry, and every new sentence.

**`app/api/projections.py`:**
- `build_turn_result` adds `character_portrait_ref`, `outgoing_character_portrait_ref` and
  `counterpart_portrait_ref` to the people entries.
- The refs come from `_portrait_refs(state)`, which reads **only** the `state` argument, i.e. the
  state the recorded turn produced.
- **A character absent from that state gets no key.** There is no fallback.
- The stored report is untouched, and live and History use this one builder.

**Also changed:**
- `Hemicycle.tsx`: the `recorded` mode, and an `arcLabels` option, off on the result's small diagrams
  as in the mockup.
- `package.json`: the `:m4` scripts.

### 1.1 Departures from the mockup and plan, stated
- **The card is navy, not parchment.** This was your default: the contrast probe accepts only the
  authored navy surfaces.
- **No card title** ("Lower the personal income tax"): it is not stored. "Your proposal" is the stored
  description instead.
- **A decree turn has no "Your proposal" line.** Its verdict and its own driver ("Enacted by decree —
  no vote was held.") already say it, and a third sentence would repeat them.
- **Bloc reactions are kept, under each bloc.** The mockup dropped them.
- **The Plan turn, Back to Dashboard and Review history buttons stay below the view** (on
  ResultScreen), not inside "What else happened".
- **Every disclosure summary and the Trace toggle are now at least 44 px tall** (§3).

## 2. Tests

**Backend:**
- **`tests/test_turn_result_portraits.py` (4 tests):**
  - the portrait comes from the turn's own state, and the stored report carries none;
  - **History after later turns** (the post dismissed, then refilled) equals turn N's live result
    byte for byte, with refs from turn N's stored state;
  - a character deleted from another state changes nothing, and deleted from the turn's own state,
    the key is absent, with no fallback;
  - the source guard: the helper's only state input is `state`.
- **`tests/test_result_fixtures.py` (2 tests):** pins `frontend/src/test/turn-results.json`, six turns
  resolved by `resolve_turn`:
  - Arken: a passed bicameral budget with Maret Kuusk's bargain and a cabinet replacement;
  - Valdrun: a failed budget, a decree budget, an amendment that failed, one that passed, and a turn
    with no proposal.

**Frontend:**
- **`format/result.test.ts` (18 tests):**
  - exactly-once placement on every real fixture, with nothing unmatched;
  - a property test over 300 random sequences, including the exact `unmatched` set;
  - the same bloc id under two parties stays two rows;
  - repeated reactions are kept in order, with their indices;
  - a synthetic unmatched reaction is reported and still shown;
  - the verdicts, the bloc moves, the people;
  - one palette across chambers that differ in membership and order.
- **`greybox/m4.test.tsx` (38 tests),** through the real Result and History screens (one of them,
  the view-level palette test, was added after `final1` was stopped, §4):
  - **every card state:**
    - recorded tallies, rows that sum, filled seats equal to the recorded support;
    - amendment totals and the note, with no diagram or rows;
    - decree;
    - no proposal;
  - **the stored numbers,** with different decision options in the cache;
  - **people:** the portrait from that turn, a refusal with no price, a name alone without a ref;
  - **bloc rows:** the moves in words, with their reactions under them;
  - **the collapsed sections** and their counts;
  - **Trace links** to a card line, a reaction under a bloc and a routine line;
  - **History renders the same DOM as live** for every fixture;
  - **one palette in the view,** including chambers reshaped to differ in membership and order;
  - **copy:** no "projected".
- **`redesign.spec.ts`:**
  - **journeys A and B (Revision 2a), at 1440 and 390:**
    - the proposal card against the resolve response;
    - Maret Kuusk with her sentence and portrait;
    - every bloc move in words;
    - History equal to live, for A **after a later turn**;
  - **new `@m4` (8 browser tests):**
    - every width: the card, one palette equal to Parliament's, no overflow or clipped node, 44 px
      controls, axe clean, a screenshot;
    - Valdrun: a decree turn and a no-proposal turn;
    - keyboard: Trace to a card line and to a reaction under a bloc.

**Forward-only updates to existing tests** (the same fact, at its new place):

| test | was | now |
|---|---|---|
| `ux4e.test.tsx` "puts the outcome first, and names the bloc" | the six lines in one list | the same six lines, in the same page order: the outcome in the card, the rest in "What else happened", the bloc move and its decree reaction under the bloc |
| `ux4g.test.tsx` (2 tests) | in `drivers-consequential` | the signed relationship on the bloc row; the blocking sentence in the card |
| `ResultScreen.test.tsx` repeated-reason test | "Why this happened" section | "What else happened" section (the two drivers carry no bloc ids) |
| `verify-ux.spec.ts` `driversText`, `@ux2` blocking sentence, `@ux4e` visible lines | the "Why this happened" section | every visible driver line in page order, Routine excluded; the blocking sentence in the card |
| `campaigns.spec.ts` `driversText`, the no-`<code>` check | the section; `li[data-reason-id] code` | the same lines in page order; `[data-reason-id] code` (a bloc row is a `div`) |
| **release spec** `packaged-instance.spec.ts` | "Why this happened" heading visible | the proposal card and "What else happened" visible |
| **release spec** `dry-run.spec.ts` | `drivers-consequential` lines recorded | every visible driver line recorded |

The release specs are not gates here; they parse (`playwright test --list`) and run at the next
candidate build.

## 3. Development failures found and fixed (before the gates)
1. **History differed from live by one trailing blank line** in the `@m3` journey's reading helper,
   after it removed the History note. The helper now normalises trailing whitespace. The view itself
   was identical.
2. **The new disclosure summaries were 20 px tall, and the Trace toggle 30 px,** found by the new
   `@m4` 44 px check. Fixed: `min-h-11` and padding.

## 4. Gates
**Run `final2`**, on this tree (`scratchpad/m4/final2/run.sh`). Each command was run on its own, and
its real `$?` was recorded in `exits.txt`.

| gate | exit | result |
|---|---|---|
| `npm test` | 0 | 53 files, 806 tests passed (750 before M-4, plus 18 and 38 new) |
| `typecheck` | 0 | |
| `build` | 0 | |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | schema and contract byte-identical to `HEAD` (`git diff --exit-code` 0) |
| `verify:redesign:m4` (`@m1` to `@m4`; trace and screenshot on failure) | 0 | 42 passed (34 before M-4, plus 8 `@m4`) |
| `verify:victory:m4` | 0 | 10 passed |
| `verify:ux:m4` | 0 | 29 passed |
| `verify:fixes:m4` | 0 | 13 passed |
| `verify:icons:m4` | 0 | 7 passed |
| `verify:terminal:m4` | 0 | 6 passed |
| `verify:campaigns:m4` | 0 | 7 passed |
| `audit:stress:seated:m4` | 0 | 6 passed |
| `audit:accessibility:verify:m4` | 0 | 6 passed |
| ruff check / ruff format --check / mypy | 0 / 0 / 0 | |
| backend suite | 0 | 36,587 passed (36,581 plus 6 new), 1 skipped (`decree_state has no leader who will deal`, as before) |
| tree unchanged during the run | 0 | the tracked diff and the untracked hashes are equal at the start and the end |

**Stopped, not failed: run `final1`.**
- **It passed its first nine steps:** the unit tests through `generate:api`.
- **I stopped it during `verify:redesign:m4`, before that gate gave any result.** I had found a test
  gap against clarification C. The palette was tested across differing chambers only at the
  function level; the view was tested only on Arken, whose two chambers list parties in the same
  order. A per-chamber palette in the view would have gone undetected (mutation X9 below).
- **How it was stopped:**
  - its process group (leader PID 5702, verified by `/proc` cmdline and cwd) with SIGTERM;
  - then the spec's leftover server, by its single PID 10851 (verified by cmdline and cwd), with
    SIGINT.
- **The stop is noted in `final1/exits.txt`.** The tree was unchanged since that run began.
- **Its partial artifact** `gate-4a3-m4-redesign.json` was **moved**, not deleted, to
  `scratchpad/m4/final1/artifacts-stopped/`.
- **The fix:** the view-level test "colours a party the same in both chambers when they differ in
  membership and order" was added (`m4.test.tsx`). Then `final2` ran once.

## 5. Mutation checks
Each mutation was applied from a scratch backup, run, restored, and checked with `cmp`. The bundle
was rebuilt for the browser cases and once more at the end. The raw results are in
`scratchpad/m4/mutations/results.txt`.

**All 16 failed their tests, as intended. There was no survivor and no invalid run.**

| # | mutation | failing test(s) |
|---|---|---|
| X1 | one driver (`turn_resolved`) dropped by the partition | exactly-once, on all six real turns |
| X2 | the card's tallies not the recorded ones | the passed-budget and amendment cards; "the stored numbers, never today's chamber" |
| X3 | a bloc table shown for an amendment | the amendment card (no rows invented) |
| X4 | a no-proposal turn shown as a decree | the verdict tests; the no-proposal card |
| X5 | a bloc's reaction dropped | exactly-once; pair matching; repeated reactions; the bloc rows in the view |
| X6 | the direction without its word (sign only) | "in words and a mark, never colour alone"; the bloc rows in the view |
| X7 | a card line without its anchor | "every Trace link lands on its line" |
| X8 | History orders the people differently | "History renders the same DOM as live" (Arken) |
| X9 | a palette per chamber in the view | the view-level palette test (chambers differing in membership and order) |
| X10 | an unmatched reaction reported but not shown | the unmatched test; the property test |
| X11 | an unmatched reaction shown but not reported | the unmatched test; the property test |
| X12 | reactions matched by `bloc_id` alone | the same bloc id under two parties; the unmatched test |
| X13 | a missing character given a placeholder portrait | the backend test: absent character, no fallback |
| X14 | the outgoing holder's portrait not added | the backend test: portraits from the turn's state; both fixture tests |
| B1 | (browser) History orders the bloc rows differently | `@m3` journey A: "History equals live, after a later turn" |
| B2 | (browser) the decree verdict reads "Enacted" | `@m4` Valdrun: the verdict word |

**After all mutations:** the tracked diff equalled `final2/tree-at-end.diff`, the untracked sources
matched their hashes, and no mutation or development artifact was left in `docs/reviews`.

## 6. Not done
- No commit or push. M-5, a candidate build and a build switch are not authorized.
- No new mechanic.
