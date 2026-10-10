# Gate 4A3 W-1: decision reliability and finished-campaign wording (playtest feedback)

**Scope:** the two defects you hit in play, and nothing else:
- unreliable decision selection;
- contradictory victory text.

The other items stay separate and are not touched here: effect explanations (W-2), the pacing
diagnosis (W-3), and the chamber and negotiation ideas.

**No contract shape change:** `generate:api` is byte-identical. There is no engine, ruleset, scenario
or save-format change, and the frozen save fixtures are untouched (`git diff backend/tests/fixtures`
is empty).

## 1. What changed

1. **The selection comes from the draft.**
   - The chosen card id moved from the Decisions screen's own state into the draft store
     (`selectedCardId`). It is cleared by `clearDraft` and by a hand change of the proposal slot
     (`setPolicySlot`).
   - **It is displayed only while the draft still matches it.** `cardMatchesDraft`
     (`state/applyPolicyCard.ts`) compares the slot and the policy fields the card's template sets:
     the rates and spending, or the amendment targets. It ignores the route, which the same card
     offers both ways, and influence, which is never part of a card.
   - So a hand edit under "Customize policy" hides the card at once, and undoing the edit shows it
     again. Leaving Decisions and returning shows the same card, on its own tab.
2. **"Take no major action" clears the proposal, with an explicit scope.**
   - **The cause:** that card has no routes, so the select handler's no-available-route guard returned
     before applying anything, and the previous proposal stayed staged.
   - **Now it clears the policy proposal only.** Appointments, investments, promises, the assistance
     request and the movement order stay staged.
   - **A staged leader bargain is dropped with the proposal it endorsed,** because resolution refuses
     a bargain with no proposal. The player is told: "Your staged leader bargain was dropped too: it
     endorsed the proposal you cleared."
3. **Finished-campaign wording is outcome-specific** (`app/api/objective.py`). The qualifying-election
   win **consumes** the engine's marker, so a won campaign used to read "Qualifying transition: not
   recorded" beside its victory. The line now reports how the transition ended:
   - **victory:** "Qualifying transition: completed — the election on turn N was won.";
   - **electoral defeat:** "Qualifying transition: not completed — the campaign ended by electoral
     defeat on turn N.";
   - **term-limit exit, where the engine still stores the marker:** "… not completed — the campaign
     ended by term limit exit on turn N.";
   - **any other ending:** the same form, with the authored removal phrase from
     `outcome_labels.REMOVAL_REASON_TEXT`.

   Only a won election ever says "completed".

## 2. Tests

- **Backend (`test_campaign_objective.py`):** exact transition text for victory, electoral defeat with
  and without a marker, and term-limit exit. A victory's whole objective contains no "not recorded".
- **The pinned fixtures (`test_objective_fixtures.py`), regenerated:**
  - **The only changed existing field** is `concludedVictory.transition_text`, from "Qualifying
    transition: not recorded" to the completed line.
  - **Additions:** `concludedElectoralDefeat` and `concludedTermLimitExit` in
    `objective-stages.json`, and one new e2e fixture, `objective-concluded-electoral-defeat.json`.
  - The three existing e2e fixtures are unchanged.
- **Unit (`greybox/w1.test.tsx`, 10):**
  - the selection survives an unmount and remount;
  - it is cleared with the draft and by a hand slot change;
  - **drift:** a hand rate edit hides the card and undoing it shows it again, and an added amendment
    axis hides it;
  - `cardMatchesDraft` for "Take no major action";
  - "Take no major action" replaces a staged budget;
  - **its scope:** investments, cabinet orders, the promise, assistance and movement are equal before
    and after, the bargain is dropped, and the announcement is shown;
  - **the three finished-campaign lines,** where no non-victory card says "transition: completed" or
    "was won".
- **Setup only:** `buildDecisionSet.test.ts`'s full-draft fixture gains the two new store members.
- **Browser (`victory` project):**
  - **The winning replays** now assert, on the concluded Dashboard and Constitution, "Qualifying
    transition: completed — the election on turn N was won.", and no "not recorded".
  - **A new "decision reliability" test:**
    - the card survives leaving Decisions;
    - a hand rate edit hides it, and undoing it shows it again;
    - "Take no major action" is shown selected, and the preview reports **no proposal**.
  - **The fixture test** renders the new electoral-defeat dashboard: the "not completed — … electoral
    defeat …" line, no "was won", and the six-width reflow and axe checks.

## 3. Gates (final runs; each its own command and its own `$?`)

| gate | exit | result |
|---|---:|---|
| `npm test` | 0 | 44 files, **660** passed (648 + 2 in `objective.test.ts`/`victory.test.tsx` via the new stages, + 10 in `w1.test.tsx`) |
| `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | byte-identical |
| backend `ruff check` / `ruff format --check` / `mypy` | 0 / 0 / 0 | |
| backend full suite | 0 | **36,535 passed** (+1: the new e2e fixture case), 32 min 22 s |
| **`verify:victory:w1`** | 0 | **10 passed**: 36 surface checks per replay, 48 in the fixture test (4 fixtures), plus decision reliability |
| `verify:ux:w1` | 0 | 26 passed |
| `verify:fixes:w1` | 0 | 13 passed |
| `verify:icons:w1` | 0 | 7 passed |
| `verify:terminal:w1` | 0 | 6 passed |
| `verify:campaigns:w1` | 0 | 7 passed |
| `audit:stress:seated:w1` | 0 | 6 passed |
| `audit:accessibility:verify:w1` | 0 | 6 passed |

**The artifacts compared with V-4's:** only the bundle filename (`campaigns`) and the output name
(`verify-ux`) differ. `icon-coverage`, `terminal`, `verification`, `stress-seated` (the JSON and both
screenshots) and the accessibility JSON are identical.

## 4. Superseded attempts, recorded and not omitted

1. **A `package.json` edit broke the file.** The new script lost its closing quote, so the first W-1
   frontend gate batch failed **on parsing**: every command exited 1, and none tested anything. The
   logs are kept in the session scratch (`w1/broken-json-run/`). The quote was fixed, and the batch
   then passed: 651 unit tests, before the later additions.
2. **`ruff format --check` exited 1** on one long line in `objective.py`. The suite-and-browser run
   that had just started (`b…mn3`) was **stopped before producing any result**; its log reached 0%.
   After `ruff format`, the only diff to that file was whitespace in the new code.
3. **The run restarted after formatting** (`b…hj0l`) was **stopped at 3%,** with no exit status,
   because your review asked for two further code changes: outcome-specific wording, and a
   selection derived from the draft. Its log is kept (`w1/superseded-2/`).
4. **The frontend results from attempt 1's repair are not reused.** Every gate in §3 was re-run on the
   final source.

## 5. Mutation checks (final code; each restored and checked with `cmp`)

| mutation | result |
|---|---|
| M1: the "Take no major action" branch disabled | vitest exit 1 (2 named: replace-budget, scope) · `victory` "decision reliability" exit 1 |
| M2: the selection back in screen-local state | vitest exit 1 (5 named: survives remount, the link test, no-major, both drift tests) · e2e exit 1 |
| M4: the displayed selection not checked against the draft | vitest exit 1 (both drift tests) · e2e exit 1 |
| M5: "Take no major action" clears the whole draft | vitest exit 1 (the scope test) |
| M3: the finished-campaign line reverted to the marker | pytest exit 1 (3 in `test_campaign_objective.py`, 2 fixture tests) |
| M6: every ending reads "completed" | pytest exit 1 (defeat, term-limit, and 2 fixture tests) |

All sources were byte-identical to the final versions afterwards, and `dist` was rebuilt from them.

**Not committed.** This awaits your review.
