# Gate 4A3 M-3: the bloc panel and negotiation

**Authorized by:** your instruction "Implement M-3 with the default choices", on the M-3 plan
Revision 2, which includes your four corrections.
- **Not authorized:** a commit, a push, M-4, a candidate build or a build switch. None was done.

**The default choices, as approved:**
1. **No before-and-after figure for an endorsement.** The panel asks the player to preview after
   staging; the chamber cards then show the new support.
2. **Replacement in the browser is tested on a labelled altered response,** never previewed or
   resolved.
3. **Failure tracing is now permanent** for the `redesign` project.

**Scope:**
- **Frontend only:** no backend, data or contract change, and `generate:api` is byte-identical to
  `HEAD` (`a177c52`).
- **Every action uses the existing draft-store setters** (`setBargain`, `clearBargain`,
  `setBudgetInfluence` / `setAmendmentInfluence`, `setInvestment`).

## 1. What changed
- **`greybox/parliament/BlocPanel.tsx` (new): the panel.**
  - **Heading:** the bloc's name, its party and stance, and its seats in every chamber; a **Close**
    button.
  - **The bloc:** its relationship with your government, and its tax and spending preferences in
    words.
  - **The party leader:** portrait, name, party and traits. Then one of:
    - an offer: "Endorse your budget", the fixed asking price, "there is no haggling", a note to
      preview after staging, and **Stage this bargain · N**;
    - a refusal ("Will not deal at any price.", with no price);
    - "No leader of {party} offers a bargain." (the governing party).
  - **Bargain states:**
    - **staged here:** party-wide, with **Withdraw bargain**;
    - **another leader's bargain staged:** the replacement sentence, **Replace bargain with {name}
      · N**, **Keep {old}'s bargain**, and the announcement "Replaced your staged bargain with {old}
      by {new}.";
    - **blocked:** with the reason (no proposal, or the decree route).
  - **What you can do:**
    1. change the proposal (Open in Decisions);
    2. bargain (above);
    3. influence on this vote (the active slot; disabled without a proposal or on a decree);
    4. invest in the relationship (with the options' range; its effect is shown only from a
       **current** preview).
  - **Staged for this bloc:** the party's bargain, the influence summary and this bloc's investment.
- **Your corrections:**
  - **A concluded campaign:** the panel stays readable, but stage, replace, keep, withdraw,
    influence and investment are all disabled with "The campaign has ended.", even when the draft
    and options are populated.
  - **Lifecycle:**
    - the panel keeps only `{partyId, blocId, chamber}` and reads everything else from the current
      projection on every render;
    - it closes on any revision or campaign change;
    - a bloc gone from the options closes it safely, with focus falling back to its chamber's
      heading, else the screen's heading.
  - **The party-wide count is of distinct blocs across chambers:** "applies to all 2 blocs", or
    "{party}'s one bloc".
  - **The influence summary** is a line outside `stagedActions`, so the nav count, the resolve
    confirmation and the draft list are unchanged. In the panel, entering 0 or clearing the field
    removes the entry.
- **`ParliamentScreen.tsx`:**
  - each bloc's name in a chamber table is now a button (`aria-expanded`) that opens the panel;
  - **placement:** beside the chambers **from 1280 px** (`xl`), inline directly after the opening
    chamber below that;
  - the wrapper's structure never changes when the panel opens or closes, so the chamber cards are
    never remounted and focus can return to their buttons;
  - the chamber headings and the screen heading are focus targets for the fallbacks.
- **`format/parliament.ts`:** every panel sentence.
  - `bargainBlockedReason` moved here from `MeetingScreen.tsx`, **word for word**. Relationships
    imports it, and its 21 tests pass unchanged.
- **`playwright.config.ts`:** the `redesign` project keeps a trace and a screenshot on failure.
- **`package.json`:** the `:m3` scripts.

### 1.1 Departures from the plan, stated
- **Side placement starts at 1280 px, not 1024 px.** At 1024–1279 px a 24-rem panel would leave
  about 350 px for the chambers. Below 1280 the panel is inline, which `@m3` checks at 960, 820, 720,
  390 and 320.
- **The parity check (decree route) uses the influence reason.** Valdrun is the only scenario where
  a budget can be decreed, and its only leader refuses to deal, so that panel has no bargain to
  block. It shows the decree reason on the influence control instead.
- **The server's 422 carries the rule's message, not its code name.** The test asserts the type
  `decision_rejected` and that exact message, which the preflight attaches to
  `legislative_bargain_requires_legislative_route`.
- **An investment of 0 is treated like an empty field** (no entry), as for influence.

## 2. Tests
- **`src/greybox/m3.test.tsx`** (21 tests), through the real Parliament screen with a fixture in
  which:
  - one party has a bloc in two chambers plus a second bloc;
  - two leaders are willing, one refuses, and the governing party has none.

  **The groups:**
  1. one party-wide bargain, counted as 2 distinct blocs, never 3 rows, including when the panel is
     opened from the upper chamber, where the party seats only one bloc (added after X7a, §5);
  2. replacement and its announcement; Keep changes nothing;
  3. each action leaves the rest of the draft deep-equal;
  4. no-proposal and decree reasons; a refusing leader shows no price; no counterpart;
  5. influence follows the active slot; 0 or empty removes it; the `stagedActions` count is
     unchanged; investment is not influence;
  6. focus: open; Close and Escape return to the invoker; staging moves focus to the staged line
     and withdrawing back to Stage; another bloc swaps; a vanished invoker falls back to the chamber
     heading;
  7. an investment effect only from a current preview;
  8. no "projected";
  9. a concluded campaign with a populated draft and options: everything disabled, the draft
     unchanged;
  10. lifecycle: closes on revision and campaign change; a vanished bloc closes safely (chamber
      heading, then screen heading); a changed price shows at once.
- **`e2e/redesign.spec.ts` `@m3`** (14 browser tests):
  - **the open panel at all six widths:** placement, no overflow or clipped node, 44 px controls,
    axe clean on `main`, a screenshot;
  - **journey A (Arken), at 1440 and 390 (touch):** stage Maret Kuusk's bargain (105) from the panel;
    the request carries it; preview with both chambers current and rows that sum; resolve (200) and
    the result headline; both chambers' stored tallies under "Last recorded vote";
  - **journey B (Valdrun), at 1440 and 390:** Draft the qualifying reform; Nadia Brekke refuses, with
    no price; 300 influence from the panel, with its summary; the preview is affordable; resolve and
    the headline; the amendment's last vote with its note;
  - **keyboard:** open with Enter (focus on the heading), stage with Enter, Escape (focus back on the
    row), and swap blocs;
  - **replacement on a labelled altered response,** at 1440 (keyboard) and 390 (`tap()`): keep, then
    replace, both announced. It is never previewed or resolved;
  - **parity:** the interface's own decree set plus a bargain is refused by the server (422,
    `decision_rejected`, the decree-route message), and the panel gives the decree reason.

## 3. Development failures found and fixed (before the gates)
1. **Focus fell to the page after staging by keyboard.** Staging swapped the focused Stage button for
   the staged line; the button was removed, so the next Escape could not close the panel. The
   `@m3` keyboard test caught it. **Fixed:** focus moves to the staged line after staging or
   replacing, and to Stage after withdrawing, with a new unit test (group 6).
2. **The parity test first expected the rule's code name in the 422 body.** The body carries its
   message, and the test now asserts that (§1.1).
3. **The bloc ids in the first draft of the spec were guesses** (`rural/…`). They were corrected to
   the scenario's real ids (`rural_alliance/farmers`, `national_front/conservatives`) before any run.

## 4. Gates
**Run `final2`**, on this tree (`scratchpad/m3/final2/run.sh`). Each command was run on its own, and
its real `$?` was recorded in `exits.txt`.

| gate | exit | result |
|---|---|---|
| `npm test` | 0 | 51 files, 750 tests passed |
| `typecheck` | 0 | |
| `build` | 0 | |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | schema and contract byte-identical to `HEAD` (`git diff --exit-code` 0) |
| `verify:redesign:m3` (`@m1\|@m2\|@m3`; trace and screenshot on failure) | 0 | 34 passed |
| `verify:victory:m3` | 0 | 10 passed |
| `verify:ux:m3` | 0 | 29 passed |
| `verify:fixes:m3` | 0 | 13 passed |
| `verify:icons:m3` | 0 | 7 passed |
| `verify:terminal:m3` | 0 | 6 passed |
| `verify:campaigns:m3` | 0 | 7 passed |
| `audit:stress:seated:m3` | 0 | 6 passed |
| `audit:accessibility:verify:m3` | 0 | 6 passed |
| ruff check / ruff format --check / mypy | 0 / 0 / 0 | |
| backend suite | 0 | 36,581 passed, 1 skipped (`decree_state has no leader who will deal`, as in M-2) |
| tree unchanged during the run | 0 | the tracked diff and the untracked hashes are equal at the start and the end |

**Superseded: run `final1`.** It also exited 0 on every gate, with the same counts. It is
superseded because mutation X7a survived it and test 1 then changed (§5).
- Its logs stay in `scratchpad/m3/final1/`.
- Its `docs/reviews` artifacts were **moved**, not deleted, to
  `scratchpad/m3/final1/artifacts-superseded/`.
- The artifacts committed here are `final2`'s.

## 5. Mutation checks
Each mutation was applied from a scratch backup, run, restored, and checked with `cmp`. The bundle
was rebuilt for the browser cases. The raw results are in `scratchpad/m3/mutations/results.txt`.

**Valid, failing as intended (16):**

| # | mutation | failing test(s) |
|---|---|---|
| X1 | staging without the proposal and route check | group 4: no-proposal and decree reasons |
| X2 | replacement without its announcement | group 2: "names the bargain it replaces, replaces it, and announces the replacement" |
| X3 | `setBargain` also clearing influence | group 3: the bargain's draft isolation |
| X4 | influence always written to the budget slot | group 5: "writes and summarises the active slot only" |
| X5 | investment written as influence | group 3 (investment) and group 5 ("never to influence") |
| X6 | focus not returned on Close or Escape | group 6: both focus-return tests |
| X7b | the count taken over rows, not distinct blocs | group 1 |
| X8 | investment effect shown from a stale preview | group 7 |
| X9 | the terminal check removed from the panel | group 9 |
| X10 | the panel kept across a revision change | group 10 |
| X12a | the influence summary read from the budget slot | group 5 |
| X12b | 0 kept as an influence entry | group 5: "clearing to zero, or emptying the field…" |
| X13 | no focus move after staging | group 6: "staging moves focus to the staged line…" |
| B1 | (browser) focus not returned on Escape | `@m3` keyboard test |
| B2b | (browser) the count taken over rows | `@m3` journey A ("Rural Alliance's one bloc" expected; "all 2 blocs" received) |
| **X7a-b** | the count taken from the opening chamber only (X7a, re-run after the test fix) | group 1: vitest exit 1 |

**X7a survived first, and the test was fixed:**
- **The first X7a run passed (vitest exit 0).** Test 1 checked the count only from the lower chamber,
  where Reform Opposition seats both its blocs, so the answer is 2 either way. Opened from the upper
  chamber (one bloc there), it only checked that the staged line existed.
- **The fix (`m3.test.tsx`, test 1 only):** the upper-chamber panel must now read "applies to all 2
  blocs of Reform Opposition." Under X7a it reads "Reform Opposition's one bloc."
- **X7a-b**, the same mutation re-run after the fix, failed test 1 (exit 1). It was restored, and
  `cmp` confirmed the restore.
- **The other mutations were not re-run.** Only that test changed, and every source they mutate is
  byte-identical to what they ran against.

**Invalid (1):** B2, the first browser attempt at the row count. The mutated source did not compile
(TS6133, an unused import), so nothing ran. It is superseded by B2b, which mutated
`distinctPartyBlocCount` itself.

**Summary: 18 executions.**
- 16 valid runs failed their tests;
- 1 valid run survived (X7a), with the gap closed by the test fix and X7a-b;
- 1 run was invalid (B2).

**After all mutations:** the tree equalled the gated tree (the tracked diff and the untracked hashes),
and no `mut-` artifact was left in `docs/reviews`.

## 6. Not done
- No commit or push. M-4 (the result restructure), a candidate build and a build switch are not
  authorized.
- No new mechanic: no counter-offers, no haggling, no before-and-after estimate.

## 7. An observation, not changed in M-3
- **At 390 and 320 px, each chamber table's Relationship column sits past the right edge of the
  card,** inside the table's own horizontal scroll container (`DataTable`).
- **It predates M-3:** the committed M-2 screenshot `gate-4a3-m2-redesign-shots/parliament-arken-390.png`
  shows the same thing.
- **It is not page overflow** (`@m2` and `@m3` check `scrollWidth ≤ clientWidth` at every width).
- **At those widths, the bloc panel now shows each bloc's relationship in full.**
- **A different narrow layout for the table** (for example, stacking the relationship under the
  bloc name) would be a separate change, for your decision.
