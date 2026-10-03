# Gate 4A3 UX-3: orientation, the next action, and no dead ends

This is the third of the four approved UX-pass commits. It implements U1, U5 and U10 from
`mandate-master-build-breezy-puppy.md`, including the three rulings approved with the UX-3
implementation plan. It changes no engine, `app/core`, scenario, contract, budget or playtest protocol,
and no backend production code at all. It is internal work and is not one of the five external
testers.

## 1. U1: the stakes and the first action (O1)

**What was wrong.** After Start, nothing said what winning or losing means. The goal card read
"Nothing is pressing.", the win condition lived only in the Glossary, and "Capital 500 / 1,000" was
unexplained.

**What changed.**
- **`GlossaryScreen.tsx`** is the one source of this copy.
  - It exports `GLOSSARY_ENTRIES` and `glossaryDefinition(term)`, which throws for an unknown term.
  - It exports `WIN_AND_LOSS_LINE`:
    > You win by turning this into a competitive constitution and then winning the first election
    > held under it. You lose if you are removed by coup, forced abdication, assassination,
    > impeachment, electoral defeat or term limit exit.
  - **Ruling (approved):** the line ends "term limit exit", not the earlier draft's "a term limit".
    Every removal is therefore named by the API's own authored phrase, which a test can check.
- **The line appears in two places.** It is in the "How to govern" note, and in Dashboard's "Your
  current priority" card under the server's goal.
- **"Build a decision"** moved from the bottom button row into that card, as its primary
  (gold-bordered) button. It still navigates to Decisions and still appears in every state, as
  before. "Review history" stays in the row.
- **The capital tooltip.** The header's `Capital {display}` carries the Glossary's "Political
  capital" definition as both `title` and `aria-description`. It quotes the Glossary; it does not
  restate it.

**What keeps the line true** (`backend/tests/test_orientation_copy.py`):
- **Every removal reason** in `RemovalReason` has its `REMOVAL_REASON_TEXT[...].phrase` in the line
  (6 parametrised cases). The test reads the line from the source and joins it exactly as the browser
  does.
- **Every shipped scenario starts noncompetitive** under `is_noncompetitive_constitution` (3 cases).
  That is the only condition under which "turning **this** into a competitive constitution"
  describes the player's country. Measured: `decree_state` is hereditary with unlimited decree, and
  `deficit_demo` and `tiny_valid` have `emergency_only` decree, which is not `NONE`. A future
  competitive scenario fails this test rather than shipping a false sentence.
- Two anti-vacuity checks: the parsed line is the whole sentence, and the scenario glob finds
  exactly the three shipped scenarios.
- **Mutation check:** I removed "impeachment, " from the line, and exactly
  `test_every_removal_reason_is_named_by_its_authored_phrase[impeachment]` failed. The file was then
  restored and verified with `cmp`.

## 2. U5: the next action (O7)

On a non-terminal turn, the result screen's primary action is now **"Plan turn {N}"**, which opens
Decisions. "Back to Dashboard" became secondary (navy border); "Review history" is unchanged; the
terminal branch is unchanged.

**N needs no arithmetic.** `TurnResultProjection.turn` is `state.turn` after resolution
(`projections.py`, "the turn this result PRODUCED"). The national header shows that same number as
"Turn {turn}". The browser asserts the two are equal.

**Ruling (approved), carried rather than fixed: R3.** The existing result heading "Turn {N} —
outcome" names the turn the result *produced*, which is one higher than the turn the player just
resolved. Relabelling it would need `resolved_turn` on the contract, and the contract is unchanged in
this pass. It is added to the UX risk list.

## 3. U10: no dead ends, and a tint that is really drawn (O8)

**Every Details link lands on what it was linked for.**
- **One card component.** `greybox/ConcernCards.tsx` holds `ConcernCardGrid`, which is the
  Dashboard's own card markup moved, not copied, with the same `concern-cards` test id. It also holds
  `concernsOf(dashboard)`.
- **`ConcernSummaries({ screen })`** renders every concern whose `detail_screen` names that screen,
  from the same revision-keyed dashboard query. It shows no Details button, which would link to the
  same page. With no campaign, or before the data loads, it renders nothing.
- **Economy, Legislature and Constitution** show it above their unchanged "Not in this version of the
  game" panel. `UnavailableScreen` takes the screen id from the registry.
- **Government** shows Legitimacy **and** Survival above the cabinet.
  - `CabinetScreen` now renders the `<h2>Government</h2>`, then the summaries, then `CabinetBody`, so
    the heading leads every state.
  - Before this change, the loading and error states had no heading at all. The body's two copies of
    the heading were removed, so there is still exactly one.
- **The nav** groups Economy, Legislature and Constitution in a nested list labelled by a visible
  "Summaries" caption. The registry's order and every control's accessible name are unchanged.

**The map box draws what it claims.**
- **Before:** a dashed empty box reading "map placeholder"; an `aria-label` describing a "stylised
  outline" that was never drawn; and the server's `map.note` ("…No province-level mechanics exist.")
  shown as a caption.
- **Now** (`data-testid="national-tint"`):
  - The box has an **opaque** fill, `color-mix(in oklab, var(--color-gold-600) P%, var(--color-navy-950))`.
  - P is `tintMixPercent(tint_value_bps)` in `format.ts`: linear from 15 at 0 bps to 60 at 10,000
    bps, clamped.
  - The country name is centred on it in `parchment-100`, **on its own `navy-950` label** (see
    "Deviation" below).
  - `aria-label` = "{Country}: national tint by {label}, {value}.", with the value formatted from
    `tint_value_bps` itself.
  - The caption is `tintCaption(label)`: "The colour shows national legitimacy: the stronger it is,
    the deeper the tint."
- **`map.note` is no longer rendered.** The server field, its text and `test_api_projections.py:127`
  are unchanged.
- **Contrast.** The country name measures **16.25:1** on its `navy-950` label in the browser, with
  the probe calibrated.

**Deviation from the approved detail, and why.** The approved plan put the country name directly on
the tint, to be measured there at ≥ 4.5:1. I first built it that way, and it measured 9.95:1. But two
existing sweeps then failed:
- `verify-commit3-fixes` (N1–N6);
- `terminal-coverage` (N6).

Both assert that **every measured text backdrop is one of the palette's authored surfaces**. Each
reported exactly one foreign backdrop, the gold mix (`rgb(63,55,41)` and `rgb(75,63,43)`, at two
legitimacy values).

That invariant is an existing baseline check, and widening it to admit the mix would be broadening an
exclusion to get a pass, so I did not. **The design changed instead:** the name sits on a
`bg-navy-950` label inside the tint. The tint is still a real, opaque fill around the label (the
browser checks that it differs from the label's `navy-950`). The text backdrop is an authored
surface again. Both sweeps pass **unchanged**.

**Ruling (approved): one adjacent defect fixed.** A disabled nav control's tooltip said "Load or start
a game to view the strategic map." on Government and Relationships too. It now names each screen
("…view the government.", "…view the relationships."). The Strategic map's text is unchanged, and an
existing test pins it.

## 4. Tests

**Frontend: new, 21 (520 → 541)**
- `src/format/orientation.test.ts` (6):
  - `tintMixPercent` bounds and midpoint;
  - clamping;
  - strictly increasing in 100-bps steps;
  - the exact `tintFill`;
  - the exact caption;
  - the accessible name, with none of "outline", "placeholder", "province" or "mechanics".
- `src/greybox/ux3.test.tsx` (15):
  - glossary quoting;
  - the exact stakes line;
  - the stakes line and "Build a decision" inside the priority card, with exactly one such button;
  - the How-to-govern line and the capital `title` and `aria-description`, via the real
    `GreyboxApp`;
  - **5 generated cases, one per concern:** the screen its `detail_screen` names, rendered through the
    real registry, shows a "Summary" heading followed by exactly the concerns that link there, and no
    Details button;
  - Government shows both its cards, under a single h2 that comes before "Summary";
  - nothing renders without a campaign;
  - the nav's Summaries group and the corrected tooltips;
  - the tint box: its bps, fill, accessible name, country name and caption, with no developer copy
    in any text or attribute and no `map.note`;
  - "Plan turn 3" is ordered first and opens Decisions;
  - no Plan button on a terminal turn.

**Frontend: existing tests adjusted, with the reason for each.**
- `copy.test.tsx`: the screen now reads the session and dashboard, so it renders inside the same
  providers as in the app, and passes `screen`. Its assertions are unchanged.
- `CabinetScreen.test.tsx`: its fetch mock answered every URL with decision options. The new
  dashboard request is now answered with a 404, so the summary renders nothing and the 23 cabinet
  tests keep testing the cabinet. Their assertions are unchanged.
- `DashboardScreen.test.tsx`: the map fixture gains the `tint_value_bps` that the real projection
  always carries.

**Backend: new, 11.** These are in `tests/test_orientation_copy.py`, as in §1.

**Browser: `@ux3` in `e2e/verify-ux.spec.ts`, Valdrun at 1440, 390 and 320.**
- **At 1440×900:** the stakes line's bottom is at y=551 and "Build a decision"'s at y=593, so both
  are inside the first viewport.
- **The capital tooltip** text.
- **The tint:**
  - its computed fill is not transparent;
  - the probe is calibrated on the caption: `parchment-200` at 70% on `navy-900` agrees with the
    offline model within tolerance;
  - the only text on the tint is the country name;
  - that name's backdrop is the `navy-950` label, an authored surface, at ≥ 4.5:1 (16.25:1);
  - the tint's own fill differs from that label, so the tint really is drawn around it.
- **No developer-facing map copy anywhere:** "placeholder", "province", "mechanics" and "Stylised
  outline" are all absent.
- **Each of the five Details links** lands on a page showing that concern's card and headline, taken
  from the API.
- **The nav's Summaries group.**
- **Resolve once, then "Plan turn N":** N equals the header's whole-word "Turn N", and the link lands
  on Decisions.

## 5. Gates

Each gate was run separately, and each exit status is the command's own `$?`.

**The first browser run failed, and was superseded.** It was run once on the first build, with the
name on the mix. Three gates failed:
- `verify:ux:3` — my own test bug. The header's text runs together as "Turn 1Election", and a `\b`
  word boundary does not exist between "1" and "E". The match is now "Turn N, not followed by a
  digit".
- `verify:fixes:ux3` and `verify:terminal:ux3` — the palette-backdrop invariant above.

After the fixes, every artifact from that run was confirmed **untracked** (`git ls-files
--error-unmatch`) and moved out of the repository. Every frontend and browser gate below was then
re-run on the final build under the same names. No committed artifact was touched.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | `Tests  541 passed (541)`: 520 → 541, +21 (6 in `format/orientation.test.ts`, 15 in `greybox/ux3.test.tsx`) |
| `npm run typecheck` | 0 | clean |
| `npm run build` | 0 | JS `index-s42Jmb-m.js` 353.41 kB / 102.19 kB gzip; CSS `index-ClnHb-Eg.css` 18.22 kB |
| `npm run check:bundle` | 0 | `check-bundle: OK -- … initial JS 98.52 KiB gzip (level 9) of a 250 KiB budget …` |
| `npm run check:palette` | 0 | `check-palette: OK -- 41 source file(s), 16 colour token(s) defined, no default-palette colour, no sub-60 text alpha, every referenced token defined.` |
| `npm run check:copy` | 0 | `check-copy OK: 344 player-visible strings across 41 files, 15 forbidden words, whole-word matched.` |
| `npm run check:css-sources` | 0 | `check-css-sources: OK -- source(none), 2 shipped source pattern(s), 1 exclusion(s): …` |
| `npm run verify:ux:3` | 0 | `14 passed (18.1s)`: 5 preflight, then `@ux1`, `@ux2` and `@ux3` at three viewports each |
| `npm run verify:campaigns:ux3` | 0 | `7 passed (23.0s)` |
| `npm run verify:terminal:ux3` | 0 | `6 passed (30.3s)` |
| `npm run verify:fixes:ux3` | 0 | `13 passed (35.6s)` |
| `npm run verify:icons:ux3` | 0 | `7 passed (10.4s)` |
| `npm run audit:stress:seated:ux3` | 0 | `6 passed (5.8s)` |
| `npm run audit:accessibility:verify:ux3` | 0 | `6 passed (1.3m)`; `accessibility report written: 0 findings (0 WCAG AA, 0 best-practice), 4 needs-review, 89 surfaces` |
| `ruff check .` (backend) | 0 | `All checks passed!` |
| `ruff format --check .` (backend) | 0 | `193 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 56 source files` |
| `npm run generate:api` | 0 | no change to `docs/contracts/` or `frontend/src/api/`: **byte-identical** |
| full backend suite `uv run pytest -q; echo PYTEST_EXIT=$?` | **0** | `36380 passed, 1 warning in 1390.16s (0:23:10)`: 36,369 + 11, exactly the new orientation tests |
| backend tests that read frontend source, **re-run on the final tree** | 0 | `43 passed`: `test_orientation_copy.py`, `test_portraits.py`, `test_sector_label_drift.py` |

**Why the last row exists.** The full suite ran before the label change. That change touched only
frontend files. The only backend tests that read frontend source are the three listed, and all
three were re-run on the final tree.

**Artifacts compared with UX-2's.** Each difference is itemised.

| artifact | disposition |
|---|---|
| `gate-4a3-ux3-icon-coverage.json` | **byte-identical** to UX-2's. Its sweep does not visit the summary screens, and `verify:fixes` measures those icons (below). |
| `gate-4a3-ux3-stress-seated-cabinet.json` | **byte-identical**: the cabinet measurements are unchanged. |
| both seated-cabinet **screenshots** | **differ**, as the plan expected. Government now shows "Summary" with Legitimacy and Survival above the cabinet, the nav shows its "Summaries" group, and the How-to-govern note shows the stakes line. Inspected. |
| `gate-4a3-ux3-verification.json` | 12 differences, all from the new content. Icon contrast: 21 → 26 placements, across 4 → 8 surfaces, as the summary cards add icons to four screens. Text owners: candidates 611 → 612 and no-own-text 402 → 403. The worst-on node moved from the removed `map.note` caption to "Nothing needs your attention this turn.". Surface distribution: navy-900 187 → 188, navy-950 8 → 7. Calibration groups 2 → 1, because the removed caption was the second calibration node. Calibration still passes on the remaining group. Below-floor observations at 195 px (recorded, not asserted) 26 → 34, from the new cards. **At 320 px all 11 screens are still clean, and that is asserted.** |
| `gate-4a3-ux3-terminal.json` | 11 differences of the same kind. N6 measured 203 → 209. Government 11 → 17 measured, because of its summary cards. Calibration groups 2 → 1, for the same reason. Below-floor overflow at 195 px 14 → 13. **The 8 screens at 320 px are still clean, and that is asserted.** |
| `gate-4a3-accessibility-after-ux3.{json,md}` | **0 violations on all 89 surfaces, and the same 4 needs-review items.** The passed-rule counts rose: +1 on every gameplay surface, which is consistent with the header's new `aria-description` making one more ARIA rule applicable, and +2 on Government, Economy, Legislature and Constitution, which gain cards. One needs-review item, N4 (Victory / defeat, `color-contrast`, 1 node), keeps its rule, impact and count. Only axe's auto-generated selector string changed, from `.gap-3.flex > .py-1:nth-child(2)` to `.gap-3 > .py-1:nth-child(2)`. |
| `gate-4a3-ux3-campaigns.json` | The asset names changed. `sameOrigin.requests` went 78 → 80, matching the Government summary's dashboard read on the spec's two Government visits. `offOrigin` is still `[]`, and the distinct paths are unchanged apart from the asset names. |
| `gate-4a3-ux3-verify-ux.json` | new: the `@ux1`, `@ux2` and `@ux3` entries |

## 6. Scope

- **Frontend:** `GlossaryScreen.tsx`, `GreyboxApp.tsx`, `DashboardScreen.tsx`, `ResultScreen.tsx`,
  `UnavailableScreen.tsx`, `CabinetScreen.tsx`, `registry.tsx`, `format.ts`, the new
  `ConcernCards.tsx`, the new tests, and three adjusted tests (§4).
- **e2e:** `verify-ux.spec.ts` (`@ux3`) and the `:ux3` scripts.
- **Backend:** one new test file. There is **no backend production change**.
- **Records:** this file and the `gate-4a3-ux3-*` and `gate-4a3-accessibility-after-ux3.*`
  artifacts.
- **Untouched:** `app/`, every scenario, fixture and frozen plan, the contract, every earlier review
  artifact, and both contrast sweeps' assertions.

## 7. Risk list addition

- **R3 — the result heading's turn number** (ruling approved, carried rather than fixed). "Turn N —
  outcome" names the turn the result produced, one higher than the turn just resolved. A fix needs
  `resolved_turn` on the contract.
