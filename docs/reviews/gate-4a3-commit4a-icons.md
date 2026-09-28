# Gate 4A3 Commit 4a — the three unreached icons, measured

Commit 4 measured **seven** of ten icons in the browser and recorded `negative`, `caution` and
`unchanged` as *not reached, with reasons*. That was an honest disposition and a real evidence gap.
This commit closes it: **all ten are measured at their own placements, and none is inferred.**

It also found and fixed a defect that made every contrast figure in Commits 3 and 4 wrong.

## All ten results

Bar: **3:1**, WCAG 2.2 SC 1.4.11 — a 2px stroke is a graphical object. Every icon inherits its stroke
from the element's own `color` via `stroke="currentColor"`, so the token column *is* the stroke colour.

| icon | group | placement(s) measured | token | backdrop | measured | offline | clears 3:1 |
|---|---|---|---|---|---|---|---|
| `positive` | tone | preview-panel | `success-400` | `navy-900` | **10.18:1** | 10.18:1 | yes |
| `negative` | tone | dashboard-concern, preview-panel, turn-result | `danger-400` | `navy-900` | **7.17:1** | 7.17:1 | yes |
| `caution` | tone | dashboard-concern | `warning-400` | `navy-900` | **9.93:1** | 9.93:1 | yes |
| `neutral` | tone | dashboard-concern | `parchment-200` | `navy-900` | **13.27:1** | 13.27:1 | yes |
| `up` | direction | policy-card | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |
| `down` | direction | policy-card | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |
| `unchanged` | direction | policy-card | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |
| `route-one-way` | map-legend | map-legend | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |
| `route-two-way` | map-legend | map-legend | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |
| `capital` | map-legend | map-legend | `parchment-200` @0.8 | `navy-900` | **8.78:1** | 8.78:1 | yes |

**31 measurements, 10 of 10 icons reached, `notReached: []`.** Every measured figure equals its
offline expectation exactly — computed from the authored `tokens.css` hex, the alpha, and the backdrop
the placement authors, never from anything the probe reported. Narrowest margin: `negative` at 7.17:1
against a 3:1 bar.

`negative` turned up at **three** placements rather than one, because the resolved turn also produced
`outcome_tone="negative"` on Turn result — the failing budget — alongside the Money concern card.

## How the three were reached — shipped content, no fixture

No fixture scenario was authored and no state was invented. Each was reachable already; Commit 4's
sweep simply never entered the state.

| icon | route | why it is deterministic |
|---|---|---|
| **`unchanged`** | Decisions → the **Constitutional reform** tab | All four amendment card families hard-code `direction="unchanged"` on their effects (`policy_cards.py:548,579,586,642,674`). Present at turn 0 in every scenario. Commit 4 only ever saw the default-open Taxation family, which is the one family always `up`/`down`. The run confirmed **24** cards carrying such an effect. |
| **`negative`** | Decisions → select the personal-income-increase card → **Preview** | In `deficit_demo` that card's own template raises 1500 bps to 2000, tallying **47 against a required 51**, so `carries` and `would_pass` both go false. Commit 4 previewed an *empty* draft, which yields no chamber rows and no "Would pass" line at all. |
| **`caution`** | one resolved turn → Dashboard **Survival** card | Caution iff `coup.attempt_risk_bps > 0` (`projections.py:1586`), and `BASE_COUP_ATTEMPT_RISK_BPS = 8` is added before the clamp (`government_survival.py:317`), so it is **always ≥ 8**. At turn 0 there is no report and the card reads "Not yet assessed" — which is exactly why Commit 4 never saw it. |

**A fixture route for `caution` was considered and rejected.** The other producer is the Legitimacy
card at `legitimacy_bps < 5_000`, and that is effectively unreachable in shipped play: legitimacy
drifts *up* toward `constitutional_order_support_bps`, and the capped downward channels put
`deficit_demo`'s fixed point at exactly 5000 against a strict `<`. Authoring a low-legitimacy fixture
would have depicted a state the game cannot produce. The survival card is the real one.

Observed after the resolve: `Money=negative, Legitimacy=neutral, Legislature=neutral,
Constitution=neutral, Survival=caution`.

## The defect this found: every recorded contrast figure was inflated

**The bug.** `numbers()` in `e2e/contrast-probe.ts` read alpha **only** from a slash-separated
component. But `getComputedStyle(el).backgroundColor` returns the **legacy comma form** for a
transparent background — `rgba(0, 0, 0, 0)` — where alpha is the fourth comma value. So it parsed as
`[0,0,0]` with **alpha 1**, the `rgb()` branch returned *opaque black*, and `effectiveBg` accepted the
**first transparent ancestor** as a painted black backdrop and stopped walking.

Black flatters light text on dark navy, so nothing looked broken: four separate tables of plausible
ratios came out, every one too high.

**It was caught by arithmetic, not by a test.** The probe's OKLab→sRGB conversion is exact — converting
the computed value its own docstring records reproduces authored `parchment-200` `#e8dcc0` to the
channel — which isolated the fault to the composite step. Every recorded figure then turned out to
match a **pure-black** backdrop to two decimals, and no real surface:

| node | recorded | navy-800 | navy-900 | navy-950 | **black** |
|---|---:|---:|---:|---:|---:|
| `parchment-200/60` (calibration) | 5.65 | 5.06 | 5.45 | 5.57 | **5.65** |
| `parchment-200/80` (direction icons) | 9.76 | 7.86 | 8.78 | 9.20 | **9.76** |
| `success-400` opaque (`positive`) | 11.84 | — | 10.18 | 10.80 | **11.84** |
| `parchment-200` opaque (Dashboard worst) | 15.43 | — | 13.27 | 14.08 | **15.43** |

### Corrected figures, old beside new

| figure | Commit 4 recorded | corrected | bar | still passes |
|---|---:|---:|---:|---|
| N1–N6 Dashboard worst | 15.43 | **13.27** | 4.5 | yes |
| N1–N6 Decisions worst | 5.65 | **5.45** | 4.5 | yes |
| N1–N6 Relationships worst | 5.65 | **5.45** | 4.5 | yes |
| N1–N6 Strategic map worst | 7.50 | **7.01** | 4.5 | yes |
| icon tone worst | 11.84 | **10.18** | 3 | yes |
| icon direction worst | 9.76 | **8.78** | 3 | yes |
| icon map-legend worst | 9.76 | **8.78** | 3 | yes |
| calibration node | 5.65 | **5.57** | — | matches offline 5.57 |

**No verdict changed**, and that was verified rather than assumed. The narrowest corrected figure is
5.45:1 against a 4.5:1 text bar.

### Why the calibration did not catch it

Its band was `5.2 < r < 5.7`, wide enough to contain navy-900 (5.45), navy-950 (5.57) **and** the
black-backdrop 5.65. **A tolerance that holds both the truth and the bug cannot detect the bug** — and
for two commits it did not. It is now a fixed tolerance around a single expected value.

## The rules, fixed before the run

A tolerance chosen after seeing a number is not a tolerance. All three were set in
`e2e/contrast-probe.ts` before any measurement.

- **Conversion: ±1 per 8-bit channel** against the authored hex. Deliberately *not* "exactly equal":
  CSS Color 4 does not require serialization to preserve component text, so an exact rule would be
  brittle by specification rather than by luck. Measured at delta 0 on every token.
- **Ratio: ±0.05 absolute**, applied twice — once against the probe's own recorded inputs (validates
  the arithmetic), and once against **authored values** (catches a wrong backdrop, because it never
  consults what the probe believed the backdrop was). The parser bug produced an ~11% error, so this
  would have failed on its first run.
- **Backdrop: asserted per placement against authored CSS.** "Some navy token" would not do — it
  catches pure black but still accepts `navy-800` where `navy-900` is authored, a walk that stops one
  ancestor early. So each placement's expectation is derived from the component's own `className`:

| placement | authored backdrop, and where |
|---|---|
| Dashboard concern cards | each concern is a `Panel` → `bg-navy-900` |
| `ConsequencesPanel` (preview) | inside a `Panel` → `bg-navy-900` |
| policy-card effect chips | the card's own `<button>` → `bg-navy-900` |
| map legend | the `<details>` wrapper → `bg-navy-900` |
| Turn result | inside a `Panel` → `bg-navy-900` |

An icon in no named container is tagged `unknown` and **fails the run** rather than being attributed
to a guess. A backdrop mismatch also fails, in either direction: the walk is wrong, or the table is
stale.

### One expectation of mine was wrong, and the measurement was right

The icon calibration first asserted a hard-coded `navy-900` and failed at **5.57**. That figure was
*correct*: the first `text-parchment-200/60` node on the page is the header's own connection line,
which sits on `bg-navy-950`, not inside a `Panel`. So the calibration now derives its expectation from
the backdrop the probe resolved — **after** asserting that backdrop is an authored surface — which
keeps the check independent without baking in an assumption about which node gets found.

## The assertions were proved to bite

Green runs prove nothing on their own, so three failures were planted and each was caught:

| planted | result |
|---|---|
| `EXPECTED_BACKDROP["policy-card"]` changed to `navy-800` | **fails**, naming each icon, the resolved `rgb(15,22,38)` (navy-900) and the authored expectation |
| the Constitutional reform tab made unmatchable | **fails** — `unchanged` unreachable |
| an eleventh declared icon nothing renders | **fails** on `notReached`, naming it |

Plus the parser regression guard: the probe is asserted in-page against `rgba(0, 0, 0, 0)`,
`rgba(r, g, b, a)`, `rgb(r, g, b)`, `rgb(0 0 0 / 0)`, `oklab(… / 0.6)`, `#rrggbb`, and a nonsense
value that must stay non-finite so the caller reports UNMEASURED.

## I1 — `DeltaText` renders nowhere

Commit 4's record and `icons.tsx` both described direction icons as rendering "inside `DeltaText`
(`text-parchment-200/70`) and inside the policy cards' effect chips". The second half is right; the
first names a component **nothing renders**. `DeltaText` is exported from `components.tsx` with no call
site anywhere in `src/` — the Dashboard concern card renders `concern.delta_text` as plain text and
discards `concern.direction`. So the effect chips are the **only** direction-icon placement, at
`text-parchment-200/80`, and the `/70` figure described a context that never paints.

This makes `DeltaText` the second exported-but-unrendered component after `RatioBar` (finding S1).
`a11y.components.test.tsx` now asserts the absence of a call site, mirroring the existing `RatioBar`
check, so the claim is enforced rather than left as prose — and if a screen ever renders it, the test
says what to do: add its backdrop to `EXPECTED_BACKDROP` and measure it.

## Artifacts

| artifact | status |
|---|---|
| `gate-4a3-commit3-verification.json` | **byte-identical to `b1b12f6e`** — Commit 4's record, preserved |
| `gate-4a3-baseline.*`, `gate-4a3-stress.json`, `gate-4a3-accessibility*.{json,md}`, `gate-4a3-stress-seated-cabinet.json` | **byte-identical** |
| `gate-4a3-commit4a-verification.json` | new — the corrected re-run of the 13 Commit 3/4 checks |
| `gate-4a3-commit4a-icon-coverage.json` | new — all ten icons, with every measurement's inputs |
| `gate-4a3-commit4-icons-copy-introduction.md` | corrected **in place and annotated**, the way C1/C2 were: its contrast figures are marked inflated with the corrected values, and its `DeltaText` claims are fixed |

`verify-commit3-fixes.spec.ts`'s output name is now `MANDATE_VERIFY_OUT`, defaulting to the existing
name, and `verify:fixes:commit4a` writes the new one. That is what preserved the committed artifact —
Commit 4 overwrote Commit 3's accessibility evidence through exactly this mechanism, because a
parameter only helps if the caller passes a new value.

**Stated plainly: no command reproduces the committed Commit 4 artifact any more.** The code that
produced it read every transparent backdrop as painted pure black. It stands as history, not as
something regenerable, and pretending otherwise would be worse than saying so.

## Gates

| gate | result |
|---|---|
| `ruff format --check .` | 184 files already formatted |
| `ruff check .` | all checks passed |
| bare `mypy` | 55 source files, no issues |
| `npm test` | **481 passed, 29 files** (+1 from 480: the `DeltaText` call-site assertion) |
| `typecheck` / `build` | clean |
| `check:bundle` / `check:palette` / `check:copy` | OK |
| `verify:fixes:commit4a` | **13 passed**, exit 0 — corrected figures |
| **`verify:icons`** | **7 passed**, exit 0 — all ten icons, `notReached: []` |
| `audit:stress:seated` | 6 passed, exit 0 |
| `npm run generate:api` | **byte-identical, 62 / 13 / 0.23.0** |
| full backend suite | **36,247 passed, 0 failed, 1 known warning**, `PYTEST_EXIT=0`, 26:59 — unchanged, confirming no backend file moved |

The axe sweep was **not** re-run and needs no new artifact: the only DOM change is a `data-testid` on
`ConsequencesPanel`, which adds no rendered content and no accessible name.

## Scope

Frontend, tests and documentation. No engine change, no scenario change, no new fixture scenario, no
contract change. Nine frozen plans and 22 fixtures byte-identical.
