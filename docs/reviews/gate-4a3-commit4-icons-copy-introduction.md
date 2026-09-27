# Gate 4A3 Commit 4 — an icon set, clearer copy and an introduction

**Hand-written, like `gate-4a3-commit3-fixes.md` and for the same reason.** The machine-readable
results it cites are generated; this is the record of what was done, what was measured, and what is
still owed.

| artifact | what it is | status |
|---|---|---|
| `gate-4a3-baseline.{json,md}` | Commit 1's browser baseline, `V1…V38` | **byte-identical, untouched** |
| `gate-4a3-stress.json` | Commit 1a's per-screen stress correction | **byte-identical, untouched** |
| `gate-4a3-accessibility.{json,md}` | Commit 2's axe baseline | **byte-identical, untouched** |
| `gate-4a3-accessibility-after-commit3.{json,md}` | Commit 3's post-fix sweep | **byte-identical, untouched** |
| `gate-4a3-stress-seated-cabinet.json` | Government's seated stress case | **byte-identical** (re-run, same result) |
| `gate-4a3-accessibility-after-commit4.{json,md}` | the sweep re-run after this commit | new |
| `gate-4a3-commit3-verification.json` | the regression measurements, now extended | regenerated |

**`gate-4a3-accessibility-after-commit3` was overwritten once during this commit and restored from
git.** `npm run audit:accessibility:verify` hard-codes Commit 3's artifact name, so running it here
wrote Commit 4's results over Commit 3's evidence — the same class of mistake as Commit 3 overwriting
Commit 2's baseline, one commit later, through the very mechanism (`MANDATE_A11Y_OUT`) introduced to
prevent it. A parameter only helps if the caller passes a new value. So there is now **one script per
commit**: `audit:accessibility:verify` stays pinned to Commit 3's name and
`audit:accessibility:verify:commit4` writes Commit 4's, each reproducing its own commit's evidence.

The two seated-cabinet screenshots under `gate-4a3-baseline/` are regenerated, because the screen
they photograph now renders icons. The claim they illustrate — both 64-character holder names
present, zero overflow — is unchanged, and `gate-4a3-stress-seated-cabinet.json` is byte-identical.

## Two corrections to Commit 3's record (documentation only)

**C1 — the landmark findings are `A2–A7` and `A10–A15`, not `A2–A15`.** The contiguous range wrongly
swept in **A8** (the `aria-valid-attr-value` tab defect) and **A9** (a `color-contrast` defect), two
different findings with two different fixes. Corrected in `gate-4a3-commit3-fixes.md`, in
`verify-commit3-fixes.spec.ts`'s docstring and test name, and in `GreyboxApp.tsx`'s comment.

**C2 — the coverage claim is "zero axe violations in the audited states".** Two things about the
terminal screen are **unmeasured rather than clean**, and both are Commit 5's:

| owed to Commit 5 | why it is unmeasured |
|---|---|
| N6 — terminal-screen contrast | the screen renders an outcome only in a *concluded* campaign; the sweep runs mid-campaign |
| terminal-state reflow at 320px | the same cause on the other axis: the sweep visits the screen and reflows a **placeholder** |

Neither correction establishes a code defect, and Commit 3 (`b9090327…`) is not amended.

## The icon set — ten marks, `src/greybox/icons.tsx`

Stroke-only inline SVG, `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`,
`stroke-width="2"`, `aria-hidden="true"`, sized by class. One `Icon` wrapper writes all of that, so
"stroke-only" and "never announced" are properties of the component rather than ten copies that could
drift — the same split `Portrait.tsx` uses to make "this is a face" structural.

**Two marks were doing two jobs each, and separating them is a gain in meaning rather than style:**

| was | meant | now |
|---|---|---|
| `▲` | caution **and** up | a warning triangle **and** an up chevron |
| `■` | neutral **and** unchanged | an open circle **and** a horizontal bar |

A reader could not previously tell "no valence" from "no movement", or a warning from a rise.

**`aria-hidden`, which is the opposite of `Portrait`'s choice, deliberately.** A portrait *is* the
content, so it carries `role="img"` and the person's name. Each icon here sits beside an existing
`sr-only` word (`ToneValue` renders "positive", `DeltaText` renders "up") or, in the map legend, a
`<dt>` that names it. Labelling the icon too would make a screen reader announce the meaning twice.
The never-colour-alone triple is unchanged: mark, colour, hidden word.

### Contrast measured at the icons' OWN placements, not borrowed

A 2px stroke is a graphical object under WCAG 2.2 SC 1.4.11 and needs **3:1**. Commit 3's
6.24–8.86:1 figures are for the four **tone** tokens on the navy backgrounds tone *text* sits on, and
they say nothing about the other two groups: direction icons render inside `DeltaText`
(`text-parchment-200/70`) and the policy cards' effect chips, and the legend icons sit on the
strategic map's own surface.

| group | worst measured | bar |
|---|---|---|
| tone | **11.84:1** | 3:1 |
| direction | **9.76:1** | 3:1 |
| map legend | **9.76:1** | 3:1 |

21 icon placements across four surfaces, with the probe calibrated at **5.65:1** against a known
token before any of its figures were trusted.

**Seven of the ten icons were reached; the other three are recorded, not glossed.** A first run
measured only six and would have reported the tone group "clear" on the strength of the `neutral`
mark alone. `positive` was then reached by **opening the preview panel** rather than by arguing the
gap away — `ConsequencesPanel` exists only after a player presses Preview, so a sweep that merely
navigates never sees it. `negative`, `caution` and `unchanged` remain unreached, each with its reason
in `iconContrast.iconsNotReached`: a mark only appears when the projected value it describes occurs.
Their **tokens** were measured as text by Commit 3 against a stricter 4.5:1 bar, which is evidence
about the token and is recorded as such — not as a measurement of those placements.

## The copy pass

Five sites were identified by survey. **`check:copy` then found three more, because the survey had
grepped for three specific phrases rather than for the words:**

| file | was | now |
|---|---|---|
| `UnavailableScreen` | panel "Not available in this gate" | "Not in this version of the game" |
| `UnavailableScreen` | body opening with what was *not* built | opens with the Dashboard card that *does* exist |
| `CabinetScreen` | "not available in this gate. Only the cabinet is projected so far." | "The cabinet is the only part of the government you can see here…" |
| `MeetingScreen` | same two terms in one sentence | "The people you can deal with directly are the only part of the picture you can see here…" |
| `DecisionsScreen` | "occupy the same slot" | "one budget or one constitutional amendment each turn, never both" |
| **`ConsequencesPanel`** | caption "Chamber-by-chamber projection" | "Expected vote, chamber by chamber" — *projection* is the engine's word for a server-built view, and using it for a forecast invited the wrong reading |
| **`DecisionsScreen`** | panel "(separate slot)" | "(separate from your proposal)" — a `title` prop, invisible to a `textContent` scan |
| **`DecisionsScreen`** | "Not part of the policy slot." | "Separate from the budget or amendment above, so staging one does not use up the other." |

Straight quotes around *Take no major action* became `&ldquo;`/`&rdquo;`, matching the rest of the
interface.

### Three checks, each claiming only what it covers

The three are separated because a source scanner cannot speak about rendered text, and pretending
otherwise is how F4's premise went wrong — its "three animation sites" were all substring false
positives inside identifiers.

**1. `npm run check:copy` — SOURCE.** Names its inspected set rather than saying "the source": JSX
text nodes; the prose attributes `title`, `aria-label`, `aria-description`, `aria-valuetext`, `alt`,
`placeholder`, `label`, `caption`, `heading`, `summary` (**not** `aria-live` or `aria-hidden`, whose
values are keywords); and the prose properties `label`, `heading`, `title`, `caption`, `detail`,
`term`, `definition`. Whole-word anchored (`\bgate\b`), so *aggregate*, *delegate*, *mitigate*,
*investigate* and *navigate* do not match. Measured: **342 player-visible strings across 40 files,
15 forbidden words**. Comments, identifiers, import paths, `data-*` attributes and class names are
invisible to it by construction.

Verified against five planted cases, each restored afterwards: a JSX-text violation, an attribute
violation, a property violation, a whole-word non-match that must stay clean, and a renamed Glossary
term that must report the exception as stale.

**And one incidental proof that the stated scope is real.** `src/api/schema.d.ts` is in the scanned
set — 72 kB of generated types whose docstrings are *saturated* with build vocabulary ("slot 1",
"projection", "ruleset", "digest"). It contributes **zero** offences, because comments and type-level
string literals are invisible to the walk. A text grep over the same file would have produced
hundreds of matches, which is precisely the difference between this and the grep that gave F4 its
false premise.

**Two exceptions, each scoped as narrowly as the thing it excuses, and neither to a file:**

- *revision* in `GlossaryScreen.tsx`, scoped to **the one object whose `term` is "Revision"** — not
  the file, not its definition list. A `revision` in any other entry still fails, because a
  legitimate definition must not become cover for a leak beside it.
- *revision* in `ErrorPanel.tsx`, scoped to **the exact string "The game moved to revision"**. The
  Glossary entry describes this very situation in so many words ("the interface echoes it back when
  resolving, so a stale decision is refused"), so the word is taught and then used; rewording it
  would make that entry pointless.

An exception that matches nothing **fails**, so a stale or misspelled one cannot sit there looking
like a considered decision. The allowlist is printed on every successful run.

**The map legend's pairing needed its own assertions, and they were initially missing.** Unlike
`ToneValue` and `DeltaText`, the three legend marks carry no `sr-only` word — the `<dt>` *is* the name
and the `<dd>` describes the mark in words. So the pairing that can go wrong there is icon-to-`<dt>`,
and a star beside "One-way route" would have passed every presence check. Each is now asserted against
the definition it belongs to (verified by planting exactly that swap, which fails), each is asserted
`aria-hidden` with its `<dd>` still describing the mark in words, and the replaced arrow and star
characters are asserted absent from the legend.

**2. Rendered exact-string assertions** for every changed location — `copy.test.tsx` for
`UnavailableScreen`, and the existing suites for `CabinetScreen`, `MeetingScreen`, `DecisionsScreen`
and `ConsequencesPanel`. `CabinetScreen.test.tsx` previously asserted
`/not available in this gate/i`: **a pattern is what let that wording sit unexamined for two gates**,
so it is now the exact sentence, which fails on a half-applied edit.

**3. The rendered scan, in `verify:fixes`, whose claim is exactly as wide as its coverage.**
`document.body.textContent` alone would be wrong twice over: it misses every `aria-label`, `title`,
`placeholder` and `alt` — the strings a screen-reader user hears and a sighted user never sees, and
the panel title that said "(separate slot)" was exactly such a `title` — and it includes text that is
present but never painted. So the scan reads **text nodes and those five attributes**, on 11 screens
plus the Glossary, and claims *"no forbidden whole word reaches a player **in the audited states**"*.
The unqualified form is **withdrawn**: the concluded-campaign terminal screen is not entered here, for
the same reason N6 and terminal reflow are owed to Commit 5.

`revision` is deliberately **absent from the rendered scan's vocabulary**, and this is the one word
where the two checks must differ: it is expected in the rendered Glossary, and a DOM scan cannot tell
which source entry a rendered word came from. The source check is what keeps the allowance narrow.

## The introduction

**The existing sentence was wrong, not merely thin.** It read *"Read your country's condition, build
one decision, resolve the turn…"* — and a turn is not one decision: it combines a policy proposal with
appointments, bargains, assistance requests, promises and movement orders. A player told they build
*one* decision would not look for the rest. So this is a correctness fix:

> Review your country, prepare your actions, preview their consequences, resolve the turn, and read
> what happened.

plus a short sentence on where those things live.

**The one-budget-or-amendment limit is not stated here.** It governs the policy proposal alone, and
`DecisionsScreen`'s own panel states it. Putting it in a general introduction would imply it governs
the whole turn — the same misstatement relocated.

**It was dismissible and nothing else.** `dismissHelp` could only set the flag true, so once closed
the one place the game explains itself was gone for the session. A **"How to govern"** header toggle
now reopens it, reusing the `aria-expanded` pattern the Glossary control beside it already uses
(`aria-expanded` is the negation of the stored `dismissedHelp`, since the note being open *is* that
flag being false). It stays an `<aside>` — the `complementary` landmark Commit 3 restored — and never
a dialog.

**Dismissal is not persisted.** The store is in-memory, so the note returns on reload; `localStorage`
is per-viewer browser state and a scope expansion. Recorded as an observation, not fixed.

### The keyboard proof is a traversal, because a trap is a property of what Tab does

An operable Start button and an absent `aria-modal` establish nothing about focus. jsdom cannot answer
the question at all — it has no focus model for Tab — so this half runs in the real browser:

1. **Forward** — Tab from the top; focus enters the note and **leaves** it for the page.
2. **Backward** — Shift+Tab out again. A one-directional check misses a trap that only bites backwards.
3. **Dismissal while the Dismiss button holds focus** — the case most likely to break, because the
   focused element is removed. The next Tab must land on a real control; `<body>` with the tab
   position lost would be a regression a lenient check would pass.
4. **Reopening by keyboard**, with `aria-expanded` flipping and the loop sentence back.
5. **Start operable throughout**, with nothing `inert` behind the note.

**The new toggle joined the 320px conformance checks, and it immediately failed.** Two side-by-side
controls plus the title block need roughly 347px, so the page scrolled horizontally at 320px —
caught by `verify:fixes`'s V1–V3 assertion on the first run after the toggle was added. `flex-wrap`
on the header is the fix; shrinking the controls would have made them narrower than their own labels.
Both controls are now asserted present, non-zero-width and inside the viewport at 320px.

## One refactor, and why it was worth the diff

The calibrated colour probe moved out of `verify-commit3-fixes.spec.ts` into **`e2e/contrast-probe.ts`**.
Commit 4 needed the same machinery for the icons' strokes, and a second copy would have been a second
chance to regress independently into the three failures that probe already survived — an `rgba` regex
that missed Tailwind v4's OKLab output, a canvas round-trip this Chromium rejects, and `.sr-only`
nodes being measured although they are never painted.

**The move is proved faithful by measurement, not by inspection**: the N1–N6 worst-case ratios are
unchanged at **15.43 / 5.65 / 5.65 / 7.50**, and the calibration still reads **5.65:1**.

Two things the extraction had to get right, both recorded because both are easy to get wrong:

- the source uses **nullish coalescing, never a falsy-or**: a NaN channel must propagate so the caller
  reports the element UNMEASURED, where `|| 0` would substitute a real-looking zero — the same silent
  substitution that produced two rounds of false 1.00:1 results;
- the template literal contains **no backticks**. One did, inside a comment, and it closed the
  template early and turned the rest of the file into unparseable code on the first run.

## What the accessibility sweep now says

**0 findings across 89 surfaces** (11 screens plus the Glossary, 8 viewport cases) —
`gate-4a3-accessibility-after-commit4.json`.

**Needs-review fell from 6 to 4, and the reason is the icon set.** The two that disappeared were
axe's *"content contains only non-text characters"* on the Dashboard and Decisions — the `aria-hidden`
glyph **spans**. Those nodes no longer exist: a mark is now an `<svg>` with no text content, so there
is no text-only node left to question. The four that remain are the *"background could not be
determined because it is overlapped"* cases on Strategic map, Relationships, Decisions and
Victory / defeat.

**Careful: the `N…` ids are assigned per run and do NOT carry across.** This run's `N1` (Strategic
map) is not Commit 3's `N1` (Dashboard). Commit 3's record maps its own six by screen, and that
mapping is what to read them against.

A consequence worth naming: the N1–N6 probe counts a node per measurable element, and the
Dashboard's dropped from 11 to 6, Decisions' from 29 to 23 and the Strategic map's from 12 to 9,
because the glyph spans it was measuring are gone. The **worst-case ratios are unchanged**, which is
what the refactor-faithfulness claim rests on; the counts moved because the DOM did.

## Deliberately not done

- **D1 — `Portrait`'s missing backdrop colour.** Commit 3's record dated it to "Commit 4's art pass".
  Commit 4 as authorized is three named items — icon set, copy pass, introduction — and choosing a
  frame colour is a separate visual-design decision, so it is **still open** rather than quietly
  absorbed here. Said plainly so a reader does not find a dangling promise.
- **N6's contrast and terminal-state reflow** stay with Commit 5.
- **Tailwind's source scanning** stays with Commit 6. It did not bite this time, and that was
  measured rather than assumed: a build of `HEAD` in a scratch checkout reproduced Commit 3's exact
  18.30 kB CSS, and a rule-level diff against this commit's build shows **exactly five added rules
  and none removed** — `inline-block`, `h-4`, `w-4`, `align-[-0.15em]` (the icon `<svg>`) and
  `justify-end` (the header group). No utility leaked from a comment.

## Gates

| gate | result |
|---|---|
| `ruff format --check .` | 184 files already formatted |
| `ruff check .` | all checks passed |
| bare `mypy` | 55 source files, no issues |
| `npm test` | **480 passed, 29 files** (+61 from 419) |
| `npm run typecheck` | clean |
| `npm run build` | clean, 100 modules |
| `npm run check:bundle` | OK |
| `npm run check:palette` | OK — 40 files, 16 tokens |
| **`npm run check:copy`** | OK — 342 strings, 40 files, 15 words, 2 scoped exceptions |
| `npm run verify:fixes` | **13 passed**, exit 0 |
| `npm run audit:stress:seated` | 6 passed, exit 0 |
| `npm run audit:accessibility:verify:commit4` | **0 findings / 89 surfaces**, exit 0 |
| `npm run generate:api` | **byte-identical, 62 / 13 / 0.23.0** |
| full backend suite | **36,247 passed, 0 failed, 1 known warning**, `PYTEST_EXIT=0`, 24:46 — unchanged, which is what confirms no backend file moved |

**Frontend delta +61, itemised by module and measured against `HEAD`:**

| module | was | now | delta |
|---|---:|---:|---:|
| `icons.test.tsx` (new) | — | 41 | **+41** |
| `copy.test.tsx` (new) | — | 4 | **+4** |
| `GreyboxApp.accessibility.test.tsx` | 15 | 21 | **+6** |
| `StrategicMapScreen.test.tsx` | 85 | 90 | **+5** |
| `DecisionsScreen.test.tsx` | 2 | 6 | **+4** |
| `MeetingScreen.test.tsx` | 20 | 21 | **+1** |
| `CabinetScreen.test.tsx` | 24 | 24 | 0 — one assertion replaced inside an existing test |
| `DecisionsScreen.preview.test.tsx` | 12 | 12 | 0 — one assertion added inside an existing test |

**Bundle 345.27 kB / 99.62 kB gzip** (was 342.98 / 98.88), **CSS 18.49 kB** (was 18.30). The frozen
plan's own line that there would be "nothing for `check:bundle` to weigh" was false and is withdrawn:
inline SVG is shipped bytes, and ten icons' path data plus the new copy is what the +0.74 kB gzip is.
**40% of the 250 KiB gzip ceiling.**

No backend file, no scenario, no engine version and no contract change. Nine frozen plans and 22
fixtures byte-identical.
