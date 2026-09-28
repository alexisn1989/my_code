# Gate 4A3 (frozen-plan 4A5) Commit 5 — the concluded terminal screen

**Subject:** `Gate 4A3 (5/6): measure the concluded terminal screen`
**Parent:** `16f35cb671509181ec209b1fb2f18b827c0e1c98` (Commit 4a), not amended.
**Machine-readable evidence:** `gate-4a3-commit5-terminal.json`, `gate-4a3-commit5-verification.json`,
`gate-4a3-commit5-icon-coverage.json`, `gate-4a3-accessibility-after-commit5.{json,md}`.

Two measurements had been owed since Commit 3 and deferred twice with a reason. Both are now taken, in
the state where their subject exists. Along the way the widened scan and the concluded campaign each
exposed one real defect, and one further defect is reported unfixed with the reason.

---

## 1. What was owed, and why it could not be measured before

| | owed since | blocked by |
|---|---|---|
| **N6** — terminal-screen contrast, the last of Commit 2's six axe `incomplete` results | Commit 3 | the missing state **and** the contrast scan's candidate selector |
| **Terminal-state reflow** at the 320px conformance width | Commit 3 | the missing state alone |

**The two blockers were not the same, and treating them as one would have "resolved" N6 without
measuring anything.** Reflow's overflow measurement already walked every element, so only the state was
missing. N6's contrast measurement asked for
`main [aria-hidden="true"], main span, main text` — which matched **nothing** on a screen built from an
`<h2>`, two `Panel` headings, two `<p>` and two `<button>`. So the recorded *"no text-bearing element
was present"* was a statement about the selector, not about the DOM.

---

## 2. The route to a concluded campaign

`tiny_valid`, resolved with **empty decision sets** until it concluded. No decisions at all, which is
what makes it deterministic: a campaign is a function of (scenario, seed, decisions), and the seed is
the scenario's own authored `seed: 42`. The engine's stochastic channels read that seed rather than a
clock — `foreign_conflict.py` takes an `occurrence_draw` as a parameter and declares "No I/O, no
randomness, no state mutation, no clock, no floating point" — and the replay discipline depends on it.

**The ending is a game rule, not a draw:** a 2-term limit against a 16-turn election interval.

| measured | value |
|---|---|
| turns resolved | **32** |
| bucket | `defeat` |
| removal reason | `term_limit_exit` |
| projected headline | `Removed from office: term limit exit, turn 32.` |
| cap (stop condition) | 60 |

**The turn count was pinned from a direct measurement, not borrowed.** `backend/tests/test_soak.py`
records 32 for this scenario and calls it "the real, deterministic horizon under ordinary play" — but it
measures that figure with the scenario's **foreign dyad disabled**, so a live war's fluctuating
security-anxiety contribution cannot perturb its pinned legitimacy figures. The shipped scenario ships
that dyad **enabled** (`kessia`/`vetruska`), and legitimacy feeds election outcomes, so the soak's 32 was
not automatically this run's 32. Measured against the shipped configuration before the spec was written:
turn 32, `defeat`, `term_limit_exit`, 33 entries, `validate_history == []`. It agrees with the soak —
now for a checked reason rather than by assumption.

**Turns are driven through the API; every measurement is taken from the rendered DOM.** Thirty-two
click-and-confirm round trips would add brittleness without changing what is measured. Driving a campaign
*entirely* through the interface is the frozen plan's T21 walkthrough, which this commit's scope excludes
and which **remains owed**.

---

## 3. The scan, redefined — and why the filters mattered more than the selector

The candidate set is now **every element in `main`**, with two rejection rules deciding. A node is
measured iff it (1) **directly owns** a non-whitespace text node, and (2) **is painted**.

The two rules already existed and were already correct — own text rather than `textContent`, and a
visibility test covering `display:none`, `visibility:hidden`, `opacity:0`, `clip-path`, `.sr-only` and a
box of 1px or less. **Only the candidate set was wrong.** Three consequences fall out rather than needing
rules of their own:

- **Decorative marks need no exclusion.** An `svg[data-icon]` owns no text node, so rule 1 drops every
  icon. Icons keep their own 3:1 measurement under SC 1.4.11; this scan is text at 4.5:1 under SC 1.4.3.
- **Aria-hidden *text* stays in**, because it is painted and a sighted reader sees it.
- **SVG `<text>` stays in**, so the strategic map loses no coverage: on painted nodes the new set is a
  strict superset of the old.

**Both rules are proven to run, not assumed.** Each screen must reject at least one candidate for owning
no text, and the run as a whole must reject at least one painted-hidden node. A rule that excludes nothing
is a rule that is not running — and `.sr-only` nodes measuring 1.00:1 while looking like application
defects is one of the three failures this probe already survived.

### Coverage delta

| | Commit 4a | Commit 5, concluded | Commit 5, mid-campaign |
|---|---|---|---|
| screens measured | 4 | **8** | **5** |
| nodes measured | 74 | **203** | **195** |
| candidates examined | — | 703 | 611 |
| rejected: own no text | — | 490 | 402 |
| rejected: own text, never painted | — | 10 | 14 |
| worst ratio | 5.45:1 | **5.45:1** | **5.45:1** |

The two Commit 5 columns are two different runs: `verify:terminal` on a concluded campaign (8 screens,
all reachable) and `verify:fixes:commit5` on the mid-campaign session the earlier commits audited
(5 screens, the ones the six needs-review results named).

No new contrast defect surfaced. The worst figure is unchanged at 5.45:1 against a 4.5:1 bar, now over
nearly three times as many nodes.

---

## 4. N6 — RESOLVED BY MEASUREMENT

The concluded outcome panel renders exactly three text owners, and all three are **required** to appear
in the measured set. They are identified by strings the **server** projected, never by layout position,
so the assertion proves the measured text *is* the outcome rather than something resembling it.

| node | colour, on `bg-navy-900` | predicted | **measured** |
|---|---|---|---|
| the `Panel` heading, `Defeat` | `text-parchment-100` | 13.27:1 | **15.31:1** |
| the `ToneValue` span owning the headline | `text-danger-400` | 7.17:1 | **7.17:1** |
| the `<p>` owning `term_limit_exit, turn 32` | `text-parchment-200/70` | ≈7:1 | **7.01:1** |

**One prediction was wrong and is corrected rather than quietly dropped.** The plan predicted 13.27:1
for the panel heading, which is the figure for `parchment-200` on `navy-900`; the heading is
`parchment-100`, a lighter token, and measures 15.31:1. The measurement was right and the prediction
used the wrong token. The other two were exact.

Their backdrop is asserted against **what the component authors** — `Panel`'s own `className` carries
`bg-navy-900` — not against what the probe resolved. This is the strong form of the rule, the one
`EXPECTED_BACKDROP` applies to the ten icons. A walk that stopped one ancestor early, at `navy-800`,
would be a different defect wearing a less obvious value than Commit 4a's pure black, and the
sweep-wide token-membership test would have accepted it.

**The outer `<p className="text-lg">` is correctly skipped**: its only child is the `ToneValue` span, so
it owns no text of its own. That is the duplicate-ancestor rule doing visible work.

### N6 is not resolved by the mid-campaign run, and the record says so

The widened set means the terminal screen now yields **7 nodes mid-campaign** where it previously yielded
zero — but what it measures there is the *placeholder*, not the outcome. A screen-presence test would
therefore have marked N6 "resolved by measurement" on the strength of text that is not what axe flagged,
**and the coverage improvement itself would have introduced that false pass.** So in
`verify-commit3-fixes.spec.ts` N6 is deferred unconditionally, and its deferral no longer rides on an
empty-measurement list that is now empty for a different reason.

---

## 5. Terminal-state reflow

| | viewport | asserted? | result |
|---|---|---|---|
| **Conformance** | 320 × 512 | **yes** — WCAG 2.2 SC 1.4.10 | **8 of 8 screens clean**: no horizontal page scroll, no overflowing node |
| Below the floor | 195 × 422 | **no**, recorded only | 3 screens scroll (Dashboard, Relationships, Victory / defeat), 14 overflow observations |

195px is narrower than the 320px the standard requires, so treating it as conformance would invent a bar.

**A concluded campaign changes three screens**, which is why the sweep is not limited to the named one:
the terminal outcome itself; the Dashboard's "campaign has ended" panel; and **Decisions**, which takes
an early return replacing the entire composer — so its 320px layout in this state is a different layout
that had never been measured.

---

## 6. axe on the concluded screens — and a REAL VIOLATION, fixed

axe is included because N6 *is* an axe `incomplete`: resolving it means answering the question axe
declined to answer, on the screen in the state where it exists.

**Found: `heading-order` (moderate) on Decisions.** The terminal early return rendered
`<Panel title="The campaign has ended">` alone, and a `Panel` is an `<h3>` by default. With no `<h2>`
above it the document went from the site banner's `<h1>` straight to an `<h3>`. `DashboardScreen`'s
terminal panel already did it correctly, keeping its own `<h2>` and placing the panel beneath;
`DecisionsScreen` now matches, so the two ended-campaign panels have one structure rather than two.

It survived two gates because **this branch renders only in a concluded campaign**, and every sweep
before Commit 5 ran mid-campaign. It was found the first time a campaign was driven to its end.

Guarded at two levels, and the unit guard was proved to bite by planting the defect back (exactly one
test failed, naming the missing heading):

- `e2e/terminal-coverage.spec.ts` asserts zero axe violations on the concluded screens — the primary
  guard, since heading order is a whole-document property;
- `DecisionsScreen.test.tsx` pins the screen heading's level and its position before the panel — three
  orders of magnitude faster, and red long before anyone runs Playwright.

**After the fix: 0 violations across 8 screens**, 89–90 rules evaluated on each. `rulesEvaluated` is
asserted non-zero, so an empty violation list can never be read as clean when no rule ran.

**The mid-campaign sweep was re-run too, because the fix changed the DOM.**
`audit:accessibility:verify:commit5` reports **0 conformance findings and 0 best-practice findings
across 89 surfaces, with 4 needs-review** — identical to Commit 4's result, which is what confirms the
`heading-order` fix disturbed nothing outside the concluded state it applies to. It writes its own
artifact rather than touching Commit 3's or Commit 4's.

**Every `incomplete` is dispositioned**, because leaving one unmentioned is how N6 survived two commits.
One remains — `color-contrast`, 6 nodes, Strategic map — and it is answered by this run's own measurement
of that screen: 41 nodes, worst 5.45:1 on `navy-900`, with the background resolved by ancestor walk,
which is the step axe skips when elements overlap. An `incomplete` on a screen this run did not measure
would be a gap and is asserted against.

---

## 7. A defect REPORTED AND NOT FIXED, with the reason

**T1 — the terminal screen shows the player a raw identifier.** `TerminalSummary.reason_label` is the
engine's own `term_limit_exit`, and `TerminalScreen` renders it verbatim, so a concluded campaign reads:

> **Defeat** — Removed from office: term limit exit, turn 32.
> `term_limit_exit, turn 32`

The headline above it already says "term limit exit" in prose, so the line is both raw and redundant.

**Why it is not fixed here.** The project's own rule is that an identifier is never transformed into
prose on the client — `replace("_", " ")` is forbidden, and `check:copy` cannot see this string at all
because it arrives from the server at runtime. The correct fix is an **authored label map on the
server**, the pattern `POST_DISPLAY_NAMES` and `LEGISLATIVE_PROPOSAL_DISPLAY_NAMES` already establish.
That is a backend change, and Commit 5's scope fence is explicit: no engine change. Hacking it
client-side would break a standing rule to avoid crossing a fence, which is the wrong trade.

Recorded as owed, with the shape of the fix named. It is invisible to every gate that exists, and could
only be found by looking at a concluded campaign — which is what this commit did.

---

## 8. Artifact protection

Widening the candidate set **changes the figures**, so re-running the earlier scripts would not merely
rewrite a committed artifact — it would rewrite it with different numbers. All three would have:

| script | writes | status |
|---|---|---|
| `verify:fixes` | `gate-4a3-commit3-verification.json` | committed; Commit 4a preserved it byte-identical **on purpose** |
| `verify:fixes:commit4a` | `gate-4a3-commit4a-verification.json` | committed at `16f35cb6` |
| `verify:icons` | `gate-4a3-commit4a-icon-coverage.json` | committed at `16f35cb6` — **hard-coded, no parameter at all** |

So before anything ran once: the icon spec's output name became `MANDATE_ICONS_OUT` (defaulting to the
name it has always written), and three `:commit5` scripts were added. **The pre-Commit-5 scripts were not
run at all** — a parameter protects a file only when the caller passes a new value, which is exactly how
Commit 3's evidence was overwritten during Commit 4.

---

## 9. One more finding, for Commit 6

**The Tailwind source-scanning hazard fired again, and the mechanism is sharper than the record had it.**
Writing the word *filter* in a code comment added `.filter` to the **production stylesheet**, pulling in
13 `@property` declarations with it: **CSS 18.49 → 19.69 kB (+1.20 kB, +0.19 kB gzip)** — roughly 44× the
27-byte hits of Commits 2 and 3.

Two things were learned:

1. **`e2e/` is scanned.** The configured `content` glob is only `./index.html` and `./src/**`, so it is
   Tailwind v4's *automatic source detection* that reaches the e2e specs.
2. **`.filter(` is immune; the English word is not.** At `HEAD` every one of the 33 occurrences of
   `filter` across the e2e specs is a method call followed by a paren, and no `.filter` rule is emitted.
   Only a standalone word is extracted as a utility candidate.

**`check:bundle` cannot catch this**: it greps the shipped JS for a dev-viewer sentinel and says nothing
about CSS. The leak would have shipped past every gate.

Handled as Commits 2 and 3 handled it — by rewording, to *rejection rule* — because the structural fix
(constraining the scanned sources) is assigned to Commit 6. Verified by building `HEAD` in a scratch
checkout and diffing rule by rule: **zero rules added, zero removed**, and `dist` byte-identical to a
`HEAD` build by content hash. The later JS growth (345.31 → 345.50 kB, gzip unchanged) is the real
`DecisionsScreen` fix and nothing else.

---

## 10. Scope

**No engine change, no scenario change, no new fixture scenario, no contract change.** Contract stays
**62 schemas / 13 paths / `0.23.0`**. Frozen plans (9) and fixtures (22) byte-identical. Every review
artifact from Commits 1 → 4a byte-identical, verified blob-by-blob after the push.

**Still owed, and explicitly recorded:** the frozen plan's Commit 5 *new-features campaign* walkthrough
(Government appoint/dismiss, a Relationships bargain, an assistance request, a promise, then preview →
resolve → turn result → history), which would also close finding **F11**; the Commit 6 Tailwind
source-scanning cleanup; **T1** above; and **D1**, `Portrait`'s missing backdrop colour.
