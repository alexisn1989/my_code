# Gate 4A3 UX-4g: negative percentages, the chamber wording, and a forward correction to UX-4f

This commit answers your review of `7254ee5` (UX-4f). You accepted that run's `PASSED` and kept R2
open. Before final sign-off you raised three issues:
1. a percentage-display bug in the new relationship sentences;
2. an overclaimed performance diagnosis;
3. a wording correction I had missed.

The first and third are code changes; the second is corrected here, forward-only. Every committed
record, including all of UX-4f's, is unchanged. The release evidence for this changed build follows
in UX-4h.

## 1. Negative percentages between −99 and −1 bps lost their sign

**Your reproduction:** −50 bps rendered "0.50%". **The cause:** `formatBpsPercent`
(`frontend/src/format/format.ts`) took the whole part as `Math.trunc(valueBps / 100)`. For −99…−1 that
is `-0`, which a template literal prints as `"0"`, and the fraction came from `Math.abs`. Values of
−100 and below kept their sign, which is why the existing −8,000 case had not caught it.

The frontend had diverged from the function it documents itself as mirroring: the backend's
`format_bps_percent` (`app/api/projections.py`) takes the sign first, then `divmod(abs(...), 100)`, and
was already correct.

**Where it reached the player.** Relationships run −10,000…10,000 (`app/simulation/invariants.py`), so
UX-4e's "{Bloc}: relationship {opening} → {closing}" could show a bloc just below zero as positive. The
same formatter is used at 28 call sites, including Meeting standing and the cabinet traits.

**The fix:** the sign comes first and the digits from the magnitude, exactly as on the backend. Output
changes only for −99…−1. The sign stays an ASCII `-`, matching the backend and `formatSignedPoints`.

**The tests:**
- **`format/percent.test.ts` (new):** an exact table covering −1, −50, −99, −100, −150, −8,000,
  −10,000, 0, 50, 4,822 and 10,000. A sweep checks that every value from −10,000 to −1 starts with
  `-`.
- **`backend/tests/test_api_projections.py`:** `test_bps_render_as_exact_percentages` gains the same
  negative cases plus 50, so both sides are pinned to one table. The backend passed them unchanged.
- **`format/consequences.test.ts`:** three relationship sentences that cross or stay below zero, for
  example "Crown Party Core: relationship 0.20% → -0.50% (-0.70 points)."
- **`greybox/ux4g.test.tsx` (new), live and History:** the rendered turn result shows "Reform Bloc:
  relationship 0.20% → -0.50% (-0.70 points)." and never "→ 0.50%".
- **Mutation:** with the sign dropped again, 13 tests fail across the three files. The backup was
  restored and checked with `cmp`.

## 2. The blocking chamber names votes, as you had asked

| before (UX-4e, UX-4f) | now |
|---|---|
| "Lower chamber blocked the budget: 45 of 51 seats, 6 short." | "Lower chamber blocked the budget: 45 supporting votes; 51 required—6 short." |

The figures come from the same stored params as before: `supporting_seats`, `required_yes_seats` and
`shortfall_seats`.

**Tests:**
- the exact sentence, for the lower and the upper chamber, with a check that the "of N seats" form is
  gone;
- the view test above, live and History;
- the `@ux2` and `@ux4e` browser assertions (`e2e/verify-ux.spec.ts`) now match the new wording, and
  `@ux4e` also asserts that no visible line says "of N seats".

**Mutation:** restoring the old wording fails 4 tests.

The UX-4e and UX-4f records quote the old sentence as what that build showed. That was accurate for
those builds, so they are left as written.

## 3. Forward correction to UX-4f's performance diagnosis

UX-4f (`gate-4a3-ux4f-release-and-dry-run.md`, blob `977ddbf7`, and the `7254ee5` commit message)
claimed more than its evidence supports.

| where | as written | corrected |
|---|---|---|
| record §2.2 heading (line 42) | "R2 variance in `/api/scenarios`, not a UX-4e regression" | **Run-to-run variation observed; cause unresolved; regression not ruled out.** |
| record §2.2 (line 61) | "UX-4e's history and turn-result changes did not make reads slower." | Withdrawn. The medians did not separate in eight runs. UX-4e's worst sample was 11–26 ms higher in every A/B round, and that is not explained. |
| record §2.2 (line 67) | "Conclusion: this is **R2** …" | Withdrawn as a conclusion. R2 is the open risk this is tracked under, not a diagnosed cause. |
| record §3 (lines 112–115) | "Two observed breaches of the 200 ms STOP …"; "a release check can fail on variance alone" | Only **one** breach is attributed to `/api/scenarios` (`measure-ux4e-1`, 206.47 ms). The first `verify_release` kept only the aggregate `read_projection_ms` breach, so its endpoint is unknown. "Variance alone" is withdrawn, because the cause is unresolved. |
| commit `7254ee5`, lines 7–10 | "exited 1 on read_projection_ms (/api/scenarios)"; "R2, not a UX-4e regression" | The first failure is the **aggregate** read budget only; `/api/scenarios` is named by the diagnostic runs alone. **Regression not ruled out.** |

**What stands.** Per your ruling:
- UX-4f's re-run `PASSED` is accepted for that run, at 199.06 ms against a 200 ms STOP;
- R2 stays **open**, with no code, caching or threshold change;
- unchanged code is not re-run for a better timing.

The eight diagnostic JSONs in `gate-4a3-ux4f-r2-ab/` are unchanged.

## 4. The dry-run record names its own gate

`e2e/dry-run.spec.ts` hard-coded the label "4A3 UX-4f (enforced)", so any later enforced run would
have called itself UX-4f. The label now comes from `MANDATE_DRYRUN_GATE`, and is required under
`MANDATE_DRYRUN_REQUIRED=1`.
- `dryrun:installed:ux4f` sets the same label as before, so a re-run of it is unchanged.
- The new `dryrun:installed:ux4h` sets "4A3 UX-4h (enforced)" and writes `gate-4a3-ux4h-dryrun`.

## 5. Gates

Each command was run on its own, and each exit status is its real `$?`.

| command | exit | result |
|---|---:|---|
| `npm test` | 0 | 41 files, **613** passed. UX-4e had 593; the +20 are 12 in `percent.test.ts`, 4 in `consequences.test.ts` and 4 in `ux4g.test.tsx` |
| `npm run typecheck` | 0 | |
| `npm run build` | 0 | JS `index-BumrhHF5.js`, CSS `index-DVVZ_8_3.css` (unchanged) |
| `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `npm run generate:api` | 0 | byte-identical: no tracked file changed |
| backend `ruff check .`, `ruff format --check .` | 0, 0 | |
| backend `mypy` (the project's configured packages) | 0 | 57 source files. A first call, `mypy app`, also swept `app/cli.py`, which is outside the configuration, and reported 2 errors there. `cli.py` is unchanged since `44fbd5a`. |
| backend full suite (`pytest -q`) | 0 | **36,405 passed**, 1 warning (a dependency's `StarletteDeprecationWarning` from `fastapi.testclient`), in 23:00. UX-4e had 36,398; the +7 are the new parametrised percent cases |
| mutation: sign dropped | 1 | 13 failed (wanted: fail) |
| mutation: old chamber wording | 1 | 4 failed (wanted: fail) |
| `verify:ux:4g` | 0 | 26 passed |
| `verify:fixes:ux4g` | 0 | 13 passed |
| `verify:icons:ux4g` | 0 | 7 passed |
| `verify:terminal:ux4g` | 0 | 6 passed |
| `verify:campaigns:ux4g` | 0 | 7 passed |
| `audit:stress:seated:ux4g` | 0 | 6 passed |
| `audit:accessibility:verify:ux4g` | 0 | 6 passed |

**Artifacts compared with UX-4e's.** Only expected differences:
- **byte-identical:** `accessibility-after-ux4g.json`, `icon-coverage`, `stress-seated-cabinet` (JSON
  and shots), `terminal` and `verification`;
- **`accessibility-after-ux4g.md`:** only the artifact name in its header;
- **`campaigns`:** only the bundle filename (`index-CxgBPlll.js` → `index-BumrhHF5.js`);
- **`verify-ux`:** only its output name and the three blocking-chamber lines, which now read "45
  supporting votes; 51 required—6 short.".

## 6. Scope

- **Changed:**
  - `frontend/src/format/format.ts`, in `formatBpsPercent` and the blocking-chamber sentence;
  - `frontend/e2e/verify-ux.spec.ts`, two wording assertions;
  - `frontend/e2e/dry-run.spec.ts`, the gate label;
  - `frontend/package.json`, the `:ux4g` gate scripts, `dryrun:installed:ux4h`, and the label on
    `dryrun:installed:ux4f`;
  - `frontend/src/format/consequences.test.ts`;
  - `backend/tests/test_api_projections.py`, test cases only.
- **Added:**
  - `frontend/src/format/percent.test.ts` and `frontend/src/greybox/ux4g.test.tsx`;
  - this record;
  - the `gate-4a3-ux4g-*` and `gate-4a3-accessibility-after-ux4g.*` artifacts.
- **Unchanged:** the engine, `app/**` (backend production code), the scenarios, the contract, the
  budgets, and every earlier artifact.
