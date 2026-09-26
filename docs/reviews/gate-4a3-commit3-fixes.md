# Gate 4A3 Commit 3 — the fix list, executed

**Hand-written, and deliberately so.** Unlike `gate-4a3-baseline.md` and `gate-4a3-accessibility.md`,
which are generated from their runs and must not be edited, this is the triage record: every finding
from Commits 1 and 2, what was done about it, and the evidence. The machine-readable results it cites
are generated:

| artifact | what it is | status |
|---|---|---|
| `gate-4a3-baseline.json` / `.md` | Commit 1's browser baseline, `V1…V38` | **byte-identical, untouched** |
| `gate-4a3-stress.json` | Commit 1a's per-screen stress correction | **byte-identical, untouched** |
| `gate-4a3-accessibility.json` / `.md` | Commit 2's axe baseline, `A1…A15`, `N1…N6` | **byte-identical, untouched** |
| `gate-4a3-accessibility-after-commit3.json` / `.md` | the same sweep re-run after the fixes | new |
| `gate-4a3-commit3-verification.json` | the regression measurements | new |
| `gate-4a3-stress-seated-cabinet.json` | Government's owed stress case | new |

A baseline is a historical record. Re-running the sweep after fixing must not overwrite the evidence
the fixes are measured against — it nearly did, and the file had to be restored from git, which is why
the artifact name is now a parameter (`MANDATE_A11Y_OUT`) rather than a constant.

## The headline

| | before | after |
|---|---|---|
| WCAG 2.2 AA axe violations | **3** | **0** |
| axe best-practice violations | **12** | **0** |
| Overflow findings at the 320px conformance width | **3** | **0** |
| Component-supplement findings open | **1** | **0** |
| axe `incomplete` (needs review) | 6 | 6 — **5 resolved by measurement, 1 deferred with a reason** |
| Observations at 195px (below the WCAG floor) | 35 | 33 — recorded, never asserted |

89 surfaces audited, all 11 screens plus the Glossary, at 8 viewport cases.

## What was fixed

### A8 — `aria-controls` referenced ids that did not exist (critical)

`PolicyCardGrid` built tab ids from the human label: `policy-tab-${ariaLabel}-${tab.id}` with
`ariaLabel = "Budget policy"` produced `id="policy-tab-Budget policy-taxation"`. **`aria-controls` is a
space-separated IDREF list**, so the browser read one reference as two — `policy-panel-Budget` and
`policy-taxation` — and neither existed.

Fixed by building ids from the stable slug ids (`budget`, `taxation`, …), which are closed unions of
lowercase identifiers and cannot contain spaces. The one rendered panel now has one fixed id that every
tab points at, and `aria-labelledby` carries the part that actually varies. An id per tab cannot work
here: only the active panel is in the DOM, so every inactive tab's `aria-controls` would dangle — the
same defect in a different guise.

**A second half, found while fixing the first.** The level-1 tablist was hand-rolled: its tabs had no
`id`, no `aria-controls`, no roving tabindex and no arrow-key handling — a `role="tablist"` whose tabs
controlled nothing and could not be operated as a tablist. Both levels now go through one `TabList`
component, so neither can drift from the other.

### A1 and A9 — contrast below 4.5:1 (serious), and F3's palette gap

Both were opacity-composited parchment text. Measured against the three navy backgrounds text actually
sits on:

| alpha | composited | navy-950 | navy-900 | navy-800 | verdict |
|---|---|---|---|---|---|
| 40% | `#63615c` | 3.10:1 | 3.10:1 | 3.02:1 | **fails** — this was A1 (axe: 3.09:1) |
| 50% | `#79766d` | 4.22:1 | 4.16:1 | 3.96:1 | **fails** — this was A9 (axe: 4.16:1) |
| **60%** | `#8f8a7e` | **5.57:1** | **5.45:1** | **5.06:1** | passes everywhere |
| 70% | `#a59e8e` | 7.19:1 | 7.01:1 | 6.34:1 | passes |

The offline figures match axe's own to two decimals, which is why 60% is a *measured* floor and not a
preference. All nine sub-60 sites were raised to 60%.

**F3** required one green, one amber and one neutral-blue token; `tokens.css` had none, and nine
component sites used Tailwind's stock palette instead. Added with their measured worst-case ratios:
`success-400 #86d3a0` (8.86:1), `warning-400 #e8b962` (8.64:1), `info-400 #8fb8dc` (7.53:1), plus a
fourth — `danger-400 #e58a8a` (6.24:1) — because the existing `accent-red-600` measures **1.92:1** as
text and cannot carry the negative tone. The fourth token is an extension beyond §13's three and is
recorded as such rather than slipped in.

Note what replacing the stock colours did *not* do: `emerald-300`, `red-300` and `amber-300` all
measured 10–13:1 already. This was a palette-consistency fix, not a contrast fix, and saying otherwise
would overstate it.

### A2–A15 — content outside landmarks (12 findings, one cause)

Two nodes per screen, on all twelve surfaces, from **one** shell-level cause:

1. The title bar was a plain `<div>`, so the product title and connection line sat outside every
   landmark. It is now a `<header>` — the `banner` landmark it always was.
2. `<aside role="note">`: `<aside>` maps to `complementary` on its own, but `role="note"` **overrode**
   that, and `note` is not a landmark. An explicit role meant to describe the content silently removed
   it from the landmark structure. Dropping the role restores `complementary`.

**The trap this fix had to avoid:** `NationalHeader` was also a top-level `<header>`, so making the
title bar one too would have produced two banners and traded one violation for another. It became a
named `<section>` (a `region` landmark) in the same change. The verification asserts *exactly one*
banner per screen, because `region` passing is not the same claim — a page with no banner would also
pass `region`.

### V1–V3 — overflow at the 320px conformance width

- **V1**, Dashboard: a fixed `w-64` (256px) input inside panel padding. Now `w-full max-w-64` —
  identical wherever it fits, shrinking where it does not.
- **V2, V3**, Decisions: a multi-column `DataTable` cannot reflow below its minimum content width, so
  it pushed the column and its panel wider than the viewport. The table now scrolls **within its own
  box**. SC 1.4.10 exempts "content which requires two-dimensional layout for usage or meaning", and a
  data table is the canonical case: the page no longer scrolls, every cell stays reachable, and nothing
  is truncated. The scroll container is keyboard-operable and labelled by the table's own caption — a
  scrollable region only a pointer could reach would trade a reflow failure for a keyboard one.

### F4 — reduced motion, with its premise corrected

F4 recorded "only 3 transition/animate usages exist, so compliance is nearly free". The first half was
right; **the second half was wrong**, and all three were substring false positives in a text search:

- `ease-capital` is inside `data-testid="promise-release-capital"` (rel**ease-capital**)
- `ease-blocked` is inside `data-release-blocked` (rel**ease-blocked**)
- `transition` is the English word in a Glossary definition

Measured: the application has **no** CSS transition or animation declaration, no `@keyframes`, no SVG
`<animate>`, and no Tailwind motion utility in any class string. A guard written as "disable these three
animations" would have been a rule matching nothing.

What shipped instead is the standard global `prefers-reduced-motion` block, which is honest about being
*preventive*: it costs three rules and covers any future motion automatically. It is verified in the
real browser under `reducedMotion: "reduce"` — the media query is active, a deliberately injected 5s
inline transition is clamped to `1e-05s` (proving the guard **matches** rather than merely existing),
and 0 elements report non-zero duration across four screens.

### S1 — `RatioBar`'s meter had no `aria-valuenow` (critical)

Fixed rather than deleted: `aria-valuenow` now carries the raw basis-point value, with the range
declared from new `RATIO_BPS_MIN`/`RATIO_BPS_MAX` constants in `src/format/format.ts` — they live there
because computing them in a component would be arithmetic outside `src/format/**`, which
`format-boundary.test.ts` refuses. `aria-valuetext` keeps the human-readable form.

S1 stays on the record under `fixed` rather than being deleted, because it is standing evidence that a
component-level audit reaches what a screen-level one cannot: **nothing renders `RatioBar`**, so no
screen could ever have exhibited it.

## N1–N6 — the six needs-review results, measured

axe declined to judge these for two stated reasons: "content contains only non-text characters" (N1,
N2 — the `aria-hidden` tone glyphs) and "background could not be determined because it is overlapped"
(N3–N6). Neither is a verdict, so neither could be dispositioned by inspection.

The verification does what axe could not: for every text-bearing element on each flagged screen it
reads the computed foreground, converts Tailwind v4's **OKLab** output to sRGB, composites the alpha,
walks ancestors for the first non-transparent background, and computes the WCAG ratio in the page.

| finding | screen | measured | worst ratio | disposition |
|---|---|---|---|---|
| N1 | Dashboard | 11 nodes | 15.43:1 | resolved — above the bar |
| N2, N5 | Decisions | 29 nodes | 5.65:1 | resolved — above the bar |
| N4 | Relationships | 36 nodes | 5.65:1 | resolved — above the bar |
| N3 | Strategic map | 12 nodes | 7.50:1 | resolved — above the bar |
| **N6** | Victory / defeat | **0 nodes** | — | **deferred, not resolved** |

**N6 is explicitly not claimed.** The terminal screen renders its outcome only in a *concluded*
campaign, and this verification runs mid-campaign, so the node does not exist to be measured. Commit 5
drives a scenario to its terminal screen, which is where the measurement belongs. It is recorded as
owed rather than folded into the passing count — a first run of this test did exactly that, until a
"screens that yielded nothing" list was added to stop it.

**Three measurement failures preceded this working result**, and all three looked like application
defects rather than probe defects — every element came back at exactly 1.00:1:

1. An `rgba(...)` regex matched nothing, because Tailwind v4 emits `oklab(...)`.
2. A canvas `fillStyle` round-trip — normally the reliable way to make the browser parse any colour —
   also failed: this Chromium's canvas rejects `oklab()` and yields `rgba(0,0,0,0)`, which composited
   to exactly the background and produced 1.00:1 again.
3. `.sr-only` nodes were being measured at all. They are never painted, so contrast does not apply.

The probe is therefore **calibrated before it is trusted**: it must reproduce a known token's
independently computed ratio, and an unparseable colour now fails the run rather than scoring 1.00:1.
Precision is stated rather than implied — the OKLab round trip can shift a channel by a unit, so a
figure here may differ from an offline calculation by 1–2% (the calibration node read 5.65:1 against
5.45–5.57:1 offline). Immaterial at a 5.65:1-versus-4.5:1 margin, but stated.

## Government's owed stress coverage, paid

Commit 1a recorded Government as `not-stress-applicable` because the stress fixture derives from
`deficit_demo`, which opens with **both cabinet posts vacant** — no holder name exists to stretch. A
seated case was left owed.

`stress_long_names_seated_cabinet.yaml` seats both posts with authored 64-character names
(`StrictDisplayName`'s maximum). The result is non-vacuous by construction: the **server's own
projection** is checked to confirm both posts are seated, then both exact authored names must be proven
present in the Government DOM, and only then is overflow measured.

**Result: both names rendered at 1440×900 and 390×844, zero overflow, zero horizontal scroll.** Commit
1a's artifact is untouched; this is a separate file.

## What is retained, and why

| retained | rationale | scope of the allowance |
|---|---|---|
| **33 observations at 195px** | Halving a 390px phone for 200% zoom lands at 195 CSS px, **below** the 320px floor WCAG 2.2 SC 1.4.10 sets. These are real user observations, not conformance failures. | Measured and recorded every run; deliberately **not** asserted. Asserting them would quietly redefine the standard. |
| **`color-contrast` disabled in the jsdom supplement** | Not a deferral: A1/A9 are fixed. jsdom has no layout engine and cannot evaluate contrast **at all**, so a pass there would be meaningless. | One named rule in one file, with the reason; the browser sweep is the contrast evidence. |
| **N6 unmeasured** | Needs a concluded campaign. | Named, dated to Commit 5, excluded from the passing count. |
| **`danger-800` / `danger-950` border at 1.84:1** | A decorative panel border, essentially matching the 1.91:1 of the `red-900` it replaces. The error panel's meaning is carried by `role="alert"` and its title text, never by hue. | Pre-existing property, neither improved nor worsened; surfaces, not information. |
| **D1: `Portrait`'s intended backdrop never rendered** | `bg-parchment-900/40` referenced an **undefined** token, so Tailwind emitted nothing and the frame has always been transparent. Removing the dead reference is an exact visual no-op. | Recorded as D1. Choosing a real colour is a visual design decision and belongs with Commit 4's art pass. |
| **Tailwind scanning test/e2e files** | A bare utility name in a *comment* emits that rule into the production stylesheet — hit three times here at 27 bytes each, once by the very note warning about it. | Worked around by wording; constraining the scanned sources is a build-config change **parked for Commit 6** as instructed. |

## The new gates

- **`npm run check:palette`** — the F3 boundary check, and two rules the findings earned: no
  default-palette colour, no text alpha below the measured 60% floor, and **every referenced colour
  token must exist**. It parses the real AST and inspects only string literals, because a text scan
  also matches prose — the first draft failed on a comment explaining a removed class.
  Verified against three planted violations, each caught.

  It is a Node script rather than a vitest file for a measured reason: Vite's CSS plugin **empties
  `.css` in the test transform**, so a vitest file cannot read `tokens.css` at all (confirmed via both
  `?raw` import and `import.meta.glob`). `tools/check-bundle.mjs` records the same conclusion for
  `dist/`.

  It found a false claim in my own comment before it ever guarded a regression: `accent-red-600` and
  `charcoal-700` are **not** unused, as an earlier draft asserted — they are consumed as
  `var(--color-…)` SVG fills by the strategic map.

- **`npm run verify:fixes`** — the regression checks. This one **asserts**, which is the deliberate
  difference from Commits 1 and 2: a baseline must not be made to fail by finding defects, but a fix
  without a failing-on-regression check is a claim rather than a guarantee. Coverage is asserted
  explicitly — a missing screen, a missing viewport, or an axe run that failed to execute fails the
  spec.

- **`npm run audit:stress:seated`** — Government's seated-cabinet stress pass.

- **Unit-speed A8 guards** in `PolicyCardGrid.test.tsx` (6 new tests), so a reintroduced label-derived
  id fails in `npm test` rather than waiting for an audit.
