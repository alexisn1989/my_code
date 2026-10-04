# Gate 4A3 UX-4c: 320 px reflow (U7), the portrait frame (U11), and the phone's first screen (U12)

This is the third of the split UX-4 commits, following the UX-4 plan, your rulings on U11 and U12, and
the addendum's Clarification 1. The changes are frontend only, plus one new backend test. The engine,
backend production code, scenarios, contract and budgets are unchanged.

## 1. U7: no page-level horizontal scroll at 320 px (O4)

**Measured first, with a scratch probe outside the repository.** Valdrun's Decisions screen at 320 px:

| state | before: `scrollWidth` / viewport |
|---|---|
| nothing selected | 320 / 320 |
| a card selected | 320 / 320 |
| **legislative preview (fails)** | **380 / 320** |
| decree preview | 320 / 320 |

**The cause was not a visible element.**
- The failing preview's vote table is already a contained `DataTable`: its wrapper is 204 px wide and
  scrolls a 372 px table.
- Counting only elements with no clipping ancestor, **nothing** sat past the edge.
- The page was being widened by the `.sr-only` word inside the "Fails" cell's `ToneValue`, at
  `right = 380`. That word is `position: absolute`.
- An absolutely positioned box is clipped by an `overflow` ancestor **only if that ancestor is also
  its containing block**. The wrapper was not positioned, so the word's containing block was the
  page. Scrolled past the table's edge, it stretched the document.

**The fix, in `DataTable` (`greybox/components.tsx`):**
- The scroll wrapper is `relative`, so everything inside it is scrolled and clipped there.
- Every header and cell gets `last:pr-0`. The last column's right padding separated it from nothing,
  and it was what pushed the influence and investment tables 2 px past their panel, clipping the last
  header: the "clipped relationship-investment header" in the plan.

**After the fix:** 320 / 320 in all four states. A legislative vote table still scrolls *inside* its
own wrapper, which SC 1.4.10 permits for a data table.

## 2. U11: the portrait frame (D1), as ruled

**Measured first.** No palette token reaches 3:1 against all six skin tones. The best tile, `navy-950`,
is 1.77:1, because the darkest skin (`#5c3317`) sits close to navy. The approved rule therefore
stopped, and you ruled for a tile with a gold ring.

**The change.** `Portrait.tsx`'s `<svg>` gets `bg-navy-950 ring-1 ring-gold-600`.
- The ring is the frame's visible edge: `gold-600` on the `navy-900` panel is **4.16:1**, above the
  3:1 non-text bar.
- The frame makes no claim to separate the face from its tile. The portrait is decorative, and the
  name is always text.

**Tests: `backend/tests/test_portrait_frame.py` (3).** It reads the hexes from `tokens.css`, the
classes from `Portrait.tsx`, and the skin tones from `format/portrait.ts`:
- the ruled classes are on the portrait;
- the ring measures 4.16:1 against the panel (≥ 3);
- no tile token among `navy-800`, `navy-950` and `charcoal-700` reaches 3:1 on every skin. The best is
  1.77:1, and all six skins are read, as an anti-vacuity check.

It is a backend test because the frontend test runner processes even a `?raw` CSS import as a
stylesheet, so it arrives empty. My first draft was a vitest file and failed for exactly that reason;
it was deleted. This follows the repo's existing pattern for frontend drift guards.

## 3. U12: the phone's first screen, as ruled

**What was wrong (O10).** At 390 px the introduction was about 420 px tall, with UX-3's stakes line
in it. Beneath it were six wrapped rows of nav buttons, so Dashboard's priority card began near
y = 1,500.

**The change (`GreyboxApp.tsx`).**
- **The note starts closed when the app first loads below `lg`.** This is a `matchMedia("(min-width:
  1024px)")` check in a mount-only layout effect, so there is no flash.
  - Without `matchMedia` (jsdom) the screen is treated as wide.
  - The header's "How to govern" toggle reopens the note, and the choice is not persisted.
  - The priority card already carries the stakes line, so nothing is lost.
  - Resizing later never re-closes a note the player opened. Every baseline spec loads at the
    default 1280 px and resizes afterwards, so for them the note is open as before.
- **The nav is one horizontally scrollable row below `lg`,** instead of six wrapped rows.
  - Every button stays rendered, visible and Tab-reachable, so **no baseline spec's navigation
    changes**.
  - The Summaries group sits inline in that row.
  - Buttons don't wrap their labels.
- **Focus scrolls a nav button fully into view** (`scrollIntoView({inline: "nearest"})`, guarded for
  jsdom). The first `@ux4c` run found Tab landing on "Constitution" half off the edge (359–470 of
  390): Chrome scrolls a focused control into view only when it is wholly hidden.

## 4. Tests

**Browser: `@ux4c` in `e2e/verify-ux.spec.ts`, Valdrun at 1440, 390 and 320.**
- **The phone's first screen (Clarification 1), at 390×844 on a fresh campaign:**
  - the note is in its default state: closed, with `aria-expanded="false"`;
  - the page is unscrolled;
  - the server's **goal headline**, the **stakes line** and **"Build a decision"** are each visible and
    **fully inside the viewport**;
  - a trial click does not scroll, and the real click lands on Decisions.

  Measured: goal 547–595, stakes 603–723, button 735–765, all ≤ 844.
- **Nav, keyboard only, at every viewport:** Tab from the first button reaches **all 12** nav
  buttons in order, each fully on screen when focused.
- **Reflow at every viewport:** `scrollWidth ≤ clientWidth` with a card selected, after a failing
  legislative preview, and after a decree preview. Measured: equal at 1440, 390 and 320.
- **Portrait frame at every viewport:**
  - the tile's computed background is `rgb(10, 15, 26)` (navy-950);
  - its ring shadow includes `rgb(150, 116, 47)` (gold-600);
  - the portrait's panel resolves to `navy-900`;
  - ring against panel is **4.16:1**.

**`@ux3` updated for U12.** Below 1024 px it now asserts that the note starts **closed** on a fresh
load, then opens it with the header toggle, as a player would, before reading the stakes line.

**Mutation checks**, each restored afterwards (`cmp`) and rebuilt to the same bundle hashes:

| mutation | result |
|---|---|
| the note never closes on a narrow load | `@ux4c` fails: "default: closed" |
| the same, **with the two "closed" assertions removed from the test** | `@ux4c` still fails, on position: "goal ends on screen, unscrolled, at 390x844 — Received: 1015". The position checks are meaningful on their own. |
| the `DataTable` wrapper not positioned | `@ux4c` fails: "no page overflow, legislative, at 320px" |

**Nav contrast, measured in view (added after the first browser run, §5).** Below 1024 px, `@ux4c`
focuses each nav button, which scrolls it fully into view, and runs axe's `color-contrast` on that
button **alone** (`button[data-nav-screen=…]`). It requires 0 violations, 0 undecided results and at
least one rule evaluated, for **all 12** buttons at 390 and at 320.

**Frontend unit tests:** unchanged at 569. The vitest frame test was replaced by the backend one, as
above.

## 5. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

**The first browser run was superseded.** It had every gate at exit 0, but its accessibility sweep
reported **56 needs-review items, up from 4**, with 0 findings. I stopped and itemised them before
committing:
- **55 of the 56** are axe `color-contrast` results on **nav buttons**, at the six viewports below
  `lg`. Every one gives the same reason: "background color could not be determined because it's
  partially obscured". These are the buttons scrolled under the edge of the new one-row nav. Axe
  declines to judge an element it cannot fully see.
- The remaining item is the long-standing N1 (Strategic map theater labels).
- Of the earlier four, N1 and N4 are still present. N4 is now keyed together with a nav button.
  N2 (Relationships leader buttons at 195 px) is **no longer reported**. Findings stayed at 0, so axe
  now decides those nodes as passes. The likely cause is the shorter nav changing the 195 px layout;
  I did not investigate it separately. N3 merged into an item that also includes nav buttons.

The new items are a measurement gap, not a known defect: those buttons' text and background are the
same as the visible ones'. **I closed the gap rather than accept it.** Nav buttons now carry
`data-nav-screen`, and `@ux4c` measures each one in view (§4): 0 violations and 0 undecided for all
12, at 390 and 320. Because that attribute changed the build, every artifact of the first run was
confirmed **untracked** and moved out of the repository. Every frontend and browser gate below was
then re-run on the final build. The sweep still **records** the 55 clipped-button items: its
behaviour is unchanged, and they are explained here.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  569 passed (569)`: unchanged (the frame test is backend, §2) |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-DJNo2ETb.js` 358.13 kB / 103.48 kB gzip; CSS `index-DVVZ_8_3.css` 18.52 kB |
| `npm run check:bundle` | 0 | `check-bundle: OK -- …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 43 source file(s), 16 colour token(s) defined, …` |
| `npm run check:copy` | 0 | `check-copy OK: 343 player-visible strings across 43 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- …` |
| `npm run verify:ux:4c` | 0 | `23 passed (29.9s)`: preflight, then all six blocks (`@ux1` to `@ux4c`) at three viewports each |
| `npm run verify:campaigns:ux4c` | 0 | `7 passed (22.8s)` |
| `npm run verify:terminal:ux4c` | 0 | `6 passed (29.2s)` |
| `npm run verify:fixes:ux4c` | 0 | `13 passed (34.9s)` |
| `npm run verify:icons:ux4c` | 0 | `7 passed (10.2s)` |
| `npm run audit:stress:seated:ux4c` | 0 | `6 passed (5.7s)` |
| `npm run audit:accessibility:verify:ux4c` | 0 | `6 passed (1.2m)`; `0 findings (0 WCAG AA, 0 best-practice), 56 needs-review, 89 surfaces`: the 55 clipped nav buttons and N1, as above |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check .` (backend) | 0 | `196 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 57 source files` |
| full backend suite `uv run pytest -q; echo PYTEST_EXIT=$?` | **0** | `36394 passed, 1 warning in 1327.01s (0:22:07)`: 36,391 + 3, exactly the frame tests |
| backend tests that read frontend source, **re-run on the final tree** | 0 | `57 passed` (the frame, money, orientation, portrait and sector guards) |

**Why the last row exists.** The full suite ran before `data-nav-screen` was added. That change
touched only `GreyboxApp.tsx`, and the backend tests that read frontend source were re-run on the
final tree.

**Artifacts compared with UX-4b's:**

| artifact | disposition |
|---|---|
| `gate-4a3-ux4c-verification.json`, `-icon-coverage.json`, `-terminal.json`, `-stress-seated-cabinet.json` | **byte-identical** |
| the 1440×900 seated screenshot | **byte-identical** |
| the 390×844 seated screenshot | differs: the nav is **one row** ("Title · Dashboard · Government · SUMMA…", scrolling at the edge) instead of wrapped rows. The note is open, because that spec loads at desktop width and then resizes. Inspected. |
| `gate-4a3-ux4c-campaigns.json` | differs only in `sameOrigin.distinctPaths[10..11]`, the new asset names |
| `gate-4a3-accessibility-after-ux4c.{json,md}` | 0 findings; needs-review 4 → 56, itemised above |
| `gate-4a3-ux4c-verify-ux.json` | new |

## 6. Scope

- **Frontend:** `greybox/components.tsx` (`DataTable`: `relative`, `last:pr-0`); `greybox/Portrait.tsx`
  (frame); `greybox/GreyboxApp.tsx` (the note's mount default, the one-row nav, focus scrolling,
  `data-nav-screen`).
- **Backend:** the new `tests/test_portrait_frame.py` only.
- **e2e:** `verify-ux.spec.ts` (`@ux4c`, and `@ux3` opening the note below 1024 px) and the `:ux4c`
  scripts.
- **Unchanged:** backend production code, the contract, every scenario and fixture, every baseline
  spec, and every committed artifact.
