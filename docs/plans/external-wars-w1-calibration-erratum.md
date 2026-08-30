# External Wars W1 — calibration erratum for frozen-plan §10

**Status:** docs-only correction plus one adopted production constant change (§7). Does not edit
the frozen plan.
**Frozen plan:** `docs/plans/external-wars-w1-implementation-plan.md`,
SHA-256 `2ceb9a7b33512a45f6d756d3a1698c724495475d374f3d339814fef1040c82e0`.
**Applies to:** §10 ("W1 calibration — measured against the final content and remedies (R15)"),
subsections 10.1–10.8, and the derivation of the shipped constants in §10.1 and §10.7.

This erratum corrects the *measurement* that produced §10's figures, including a defect in one of
its nine grid acceptance criteria (§2). Correcting that defect changes which grid configuration the
frozen plan's own selection rule picks, so **the shipped constants are updated** (§7) to the
honestly-derived winner. No production formula, scenario content, schema, or the other calibrated
constants changed.

```
                                frozen §10.1        this erratum
MIN_ACTIVE_INTENSITY_BPS       500                  250
CEASEFIRE_RECOVERY_BPS         300                  200
CEASEFIRE_BREAKDOWN_BPS        4,000                4,500
CEASEFIRE_DURABILITY_TURNS     4                    3
MIN_OUTBREAK_WEIGHT_BPS        500                  500   (unchanged)
```

## 1. What was wrong with the original measurement

§10's own header states its figures came from "a scratch script outside the repository importing
the real engine's `derive_rng` unmodified and applying §7/§8's opening/closing discipline exactly."
That script has two defects, found by mechanically recovering it from the durable Claude operation
transcript that produced it and auditing it against production:

- Transcript: `/root/.claude/projects/-home-user-my-code/95421f9a-dace-5133-a3f4-58c7d173c2c7.jsonl`,
  the command at line 36653 (tool id `toolu_01RjHwaChb7wMSHdBayJM2Cz`), whose embedded model file
  hashes to SHA-256 `bb1710168023debc2be178b50fd586427f560850bd16788a71192c5a07b67921`; the command
  payload itself hashes to `b7b8d4119779f5809af5ecebc3f6ab4c05b52b41bfdac6497fe682d411e8eee0`. The
  calibration run that produced §10's printed figures is at line 36671
  (tool id `toolu_019tyR8cMhuaAYRjeGdG4ALp`). The 240-cell grid run is at line 36661
  (tool id `toolu_014QXy5AdDWTrDLCcHmxnv4B`, sha256 `8934fa0f7b0807e055bf0bb45e24d81a560bf61e2de5fac03437005064c0314e`).

### Defect 1 — 1-based turn indexing against a turn-keyed RNG

The recovered driver iterates `for t in range(1, H+1)`, i.e. turns 1..H. Production's
`PhaseContext.rng(stream)` calls `derive_rng(state.seed, self.resolving_turn, stream)`
(`app/simulation/phases.py`), and `derive_rng` hashes `f"{seed}:{turn}:{stream}"`
(`app/core/rng.py`) — every draw is keyed by the exact turn number. A freshly loaded scenario has
`state.turn == 0`, so a real campaign's first resolved turn is turn 0, not turn 1. The driver's
entire draw sequence was therefore shifted by one turn relative to production for every run.

### Defect 2 — a floor-run counter that does not reset across ceasefires

The driver's `step()` function only touches its `floor_run`/`floor_run_max` counters inside the
`ACTIVE`-continuing-below-floor branch's own `else` clause. The `CEASEFIRE` branch and every
terminal-status branch never touch the counter, so it silently persists across ceasefire
excursions instead of resetting. This inflated "longest continuous run at the floor" — it counted
turns at the floor with ceasefire interruptions in between as one unbroken run.

**Corrected definition:** the continuous-floor-run counter increments only while a conflict's
closing status is `ACTIVE` **and** its closing intensity equals `MIN_ACTIVE_INTENSITY_BPS` exactly;
it resets to zero on every other closing state, explicitly including `CEASEFIRE`, `SETTLED`,
`DECIDED`, and `ACTIVE` above the floor.

### Defect 3 — the `no_indefinite_ceasefire` grid criterion is a horizon status snapshot, not a
### duration measurement

The recovered grid driver's criterion (line 36661) is:

```python
if c.status=="CEASEFIRE" and c.resolved is None: cfstuck+=1
...
ok = ... and cfstuck==0
```

This counts any conflict whose status at the **final traced turn** happens to read `CEASEFIRE` —
regardless of how long that ceasefire has actually run. A conflict that entered a fresh ceasefire
one turn before the 80-turn horizon closed is counted identically to one that has been stuck in
ceasefire indefinitely. That is a right-censoring artifact, not evidence of an unreachable exit.

Traced case (`decree_state`, seed 7, `marnil__sorrend__t33`, shipped constants at the time of the
original grid): two separate ceasefire episodes. Episode 1 runs turns 42–45 (`run_turns` 0→3,
readiness 5,043→4,143) and breaks down to `ACTIVE` at turn 46 when readiness (3,843) falls under the
breakdown line (4,000) — a complete, healthy cycle. Episode 2 opens at turn 76 and is still running
(`run_turns` 0→3, readiness 5,011→4,111) when the 80-turn horizon closes mid-episode. Extending the
same run 60 turns past the horizon, this conflict exits to `ACTIVE` at turn 80 — one turn after the
traced window ends. The original criterion counted this as "stuck"; it was never stuck, it was
merely still inside an episode when the horizon cut the trace off.

**Corrected definition:** a violation is one **uninterrupted** `CEASEFIRE` episode whose length
exceeds `CEASEFIRE_DURABILITY_TURNS`. Episodes are tracked per conflict and reset on any
non-`CEASEFIRE` closing status, so separate episodes are never concatenated. An episode still open
at the horizon is **right-censored** — reported separately from a genuine violation — and counts as
a violation only if its length has *already* exceeded `CEASEFIRE_DURABILITY_TURNS` at the point the
trace ends.

This criterion turns out to be **structurally non-binding**: `ceasefire_closing_status`
(`app/simulation/foreign_conflict.py`) evaluates breakdown before maturation and returns
`CEASEFIRE` only while `closing_ceasefire_run_turns < CEASEFIRE_DURABILITY_TURNS` — a continuous
run is bounded by construction, for every value the four swept constants take. Measured directly
across all 240 grid cells: the longest closed episode equals that cell's own durability exactly, the
longest right-censored episode never exceeds it, and **zero honest violations occur in any of the
240 cells** — confirmed both by direct trace inspection and by the `test_foreign_conflict_calibration.py::TestCalibrationGrid::test_no_continuous_ceasefire_episode_ever_exceeds_its_own_durability`
regression.

### Basis validation

Before trusting any corrected figure, the recovered driver's own (1-based, unreset-counter,
snapshot-criterion) logic was reproduced against a parity-proven isolated harness and checked
against §10.7's own numbers: it reproduced the frozen grid exactly — same 5 of 240 passing,
identical five tuples, identical per-row statistics, identical six failure counts
(155/125/125/79/68/60). This confirms the corrected-basis divergence below comes from the three
defects above, not from a difference in the new measurement code.

## 2. Corrected measurement basis

Production-native: turns 0..H-1 (40-turn horizon = turns 0–39; 80-turn horizon = turns 0–79),
using an isolated calibration harness that performs only turn iteration and per-conflict status
dispatch — every arithmetic step calls the real `app.simulation.foreign_conflict`,
`app.simulation.legitimacy`, and `app.core.rng` functions, never a reimplemented formula. The
harness was proven field-by-field parity-identical to `resolve_turn` on every turn reachable
before an unrelated campaign-terminal outcome, across all three shipped scenarios and the five
declared seeds (`42, 1337, 20260826, 7, 99991`).

## 3. The honest 240-configuration grid

Same 240 cells (`MIN_ACTIVE_INTENSITY_BPS` × the 48-cell ceasefire grid), same declared seeds, same
nine acceptance criteria (with the corrected `no_indefinite_ceasefire` from §1's defect 3), turns
0–79. **27 of 240 pass** (frozen: 5 of 240; the earlier turn/floor-run-corrected-only pass, before
this criterion fix, found 7 of 240):

```
   (FLOOR, REC,  BRK, DUR)
   ( 250, 200, 4500, 3),
   ( 250, 300, 4000, 4),
   ( 250, 400, 3500, 4),
   ( 250, 400, 4000, 3),
   ( 500, 200, 4500, 3),
   ( 500, 200, 4500, 4),
   ( 500, 300, 4000, 4),
   ( 500, 400, 3500, 4),
   ( 500, 400, 4000, 3),
   ( 750, 200, 4500, 3),
   ( 750, 200, 4500, 4),
   ( 750, 300, 4000, 4),
   ( 750, 300, 4500, 3),
   ( 750, 400, 3500, 4),
   ( 750, 400, 4000, 3),
   (1000, 200, 4500, 4),
   (1000, 300, 4000, 4),
   (1000, 300, 4500, 3),
   (1000, 400, 3500, 4),
   (1000, 400, 4000, 3),
   (1000, 500, 4000, 3),
   (1250, 200, 4500, 4),
   (1250, 300, 4000, 4),
   (1250, 300, 4500, 3),
   (1250, 400, 3500, 4),
   (1250, 400, 4000, 3),
   (1250, 500, 3500, 4),
```

Honest violations across all 240 cells: **0**. Zero below-floor `ACTIVE` closes and zero stalled
conflicts across all 240 — unchanged from every prior measurement.

### Selection proof (frozen §10.7's own order, unchanged)

Per-floor passing counts: 250→4, 500→5, 750→6, 1000→6, 1250→6 (of 48 each; frozen's own proof had
recorded 250→0, the artifact this erratum corrects).

1. **Lowest `MIN_ACTIVE_INTENSITY_BPS`** — 250 has 4 passing configurations, the lowest floor with
   any. Floor 250 selected; four candidates remain at this floor:
   `(250,200,4500,3)`, `(250,300,4000,4)`, `(250,400,3500,4)`, `(250,400,4000,3)`.
2. **Fewest changed ceasefire constants** (vs. the pre-W1 baseline `REC=200, BRK=3500, DUR=3`):
   `(250,200,4500,3)` changes only breakdown (1 changed); the other three each change all three
   (3 changed). `(250,200,4500,3)` selected; it is now the sole remaining candidate, so rules 3–5
   are satisfied vacuously.

```
MIN_ACTIVE_INTENSITY_BPS      (new) = 250
CEASEFIRE_RECOVERY_BPS      300 -> 200
CEASEFIRE_BREAKDOWN_BPS    4000 -> 4500
CEASEFIRE_DURABILITY_TURNS    4 -> 3
```

## 4. Corrected §10.2–§10.4 figures, at the selected configuration `(250, 200, 4500, 3)`

These figures describe the newly-selected configuration directly (not the old shipped constants
under a corrected basis, since the shipped constants themselves are now different — see §7).

| §10.2 | Horizon | Runs | Conflicts | Quiet campaigns |
|---|---:|---:|---:|---:|
| 40t | 15 | 18 | 2 / 15 |
| 80t | 15 | 35 | 0 / 15 |

| §10.3 | Horizon | Completed n | min/med/max | Right-censored n | observed min/max |
|---|---:|---:|---|---:|---|
| 40t | 10 | 13/14/37 | 8 | 1/29 |
| 80t | 26 | 13/14/37 | 9 | 4/69 |

Opened-by-40 terminal-by-80: **15/18 (83.3%)** — clears the required ≥50% threshold.

| §10.4 | Horizon | DECIDED | SETTLED | ACTIVE | CEASEFIRE | CF breakdowns | CF maturations |
|---|---:|---:|---:|---:|---:|---:|---:|
| 40t | 1 | 9 | 8 | 0 | 6 | 9 |
| 80t | 1 | 25 | 8 | 1 | 15 | 25 |

| §10.4 intensity | Horizon | min/med/max | floor binds | honest longest continuous floor run |
|---|---:|---|---:|---:|
| 40t | 0/5,128/6,215 | 37 | 19 |
| 80t | 0/4,645/6,215 | 132 | 27 |

Zero closing-`ACTIVE`-below-floor at both horizons. Sub-floor `SETTLED`/`DECIDED`/`CEASEFIRE` closes
remain legal by design and are excluded from the floor-bind and floor-run counts.

## 5. Categories re-measured at the selected configuration

- **§10.5 concurrency:** shipped concurrency 1 at both horizons — unchanged. Synthetic multi-dyad
  fixture (3 dyads, 5 seeds, 80 turns): **38** conflicts, max concurrent **2**, cap
  (`MAX_CONCURRENT_CONFLICTS = 2`) never exceeded.
- **§10.5 security anxiety** (5 seeds × 80 turns, negative-only, capped once):
  `tiny_valid` (exp 2,000): nonzero 156, min −71, median −63, max −3, cap hits 0.
  `decree_state` (exp 3,000): nonzero 186, min −111, median −93, max −4, cap hits 0.
  `deficit_demo` (exp 2,000): nonzero 140, min −72, median −67, max −3, cap hits 0.
  The ±150 cap never binds. Zero-exposure control: every value exactly 0 (n=400).
- **§10.6 low-pressure floor:** shipped weights unchanged (8,000 / 9,000 / 8,000);
  `MIN_OUTBREAK_WEIGHT_BPS` unchanged at 500. Low-pressure control (tension 200, grievance 0 ⇒
  weight 100) yields **0 conflicts at both horizons, every seed** — unchanged, structural.
  `passes_pressure_floor(499) = False`, `passes_pressure_floor(500) = True` — unchanged.
- **Determinism / save-reload:** rerun byte-identical across all 15 (scenario × seed) runs.
  Split-run test (turns 0–39, save, reload at turn 40, continue 40 more) produces a trace identical
  to an uninterrupted 80-turn run — confirmed.
- **§10.8 disclosed floor grind:** exhaustion still accrues at the floor, at
  `trunc_div(250 × 1,200 / 10,000) = 30` bps/turn — half of the 60 bps/turn the old floor (500)
  produced, because the gain scales with the floor itself, but still strictly positive, which is
  the property that actually matters (not the removed absorbing state).
- **§9's deterministic liveness witness** (a synthetic worst-case: opening intensity 0, opening
  exhaustion 4,000, floor applied): reaches a non-`ACTIVE` status within **35** turns (was ≤30 under
  the old floor's 60 bps/turn gain) — same seed and fixture, only the timing moved, because halving
  the floor halves the at-floor exhaustion gain. Every anti-absorbing and eventual-progress property
  (readiness monotonic, every `ACTIVE` turn ≥ floor and > 0, terminates) is unchanged.

## 6. What is unchanged

- Every constant in §10.1 not listed in the table at the top of this document.
- Every scenario's authored content, every schema, the ruleset version (`0.13.0`, unreleased — see
  §8) and the save format (`1`).
- The reconciliation and tamper-detection machinery: re-verified against the selected configuration
  (`test_foreign_affairs_reconciliation.py`, `test_foreign_conflict_tamper_matrix.py`,
  `test_reconciliation.py`, all green).
- RNG-stream independence, concurrency behaviour, and every unrelated political/economic/election/
  coup outcome.

## 7. Adopted constant change

Per the binding calibration ruling, the honestly-derived grid winner is adopted directly rather than
kept as a documented exception to an invalid criterion:

```
MIN_ACTIVE_INTENSITY_BPS      500 -> 250
CEASEFIRE_RECOVERY_BPS        300 -> 200
CEASEFIRE_BREAKDOWN_BPS     4,000 -> 4,500
CEASEFIRE_DURABILITY_TURNS      4 -> 3
```

`MIN_OUTBREAK_WEIGHT_BPS` (the separate outbreak-candidacy floor, 500) is unrelated and unchanged.

## 8. Ruleset/save-format compatibility

`RULESET_VERSION = "0.13.0"` had no durable save fixture at the time of this change (frozen
fixtures under `backend/tests/fixtures/` stop at `phase4a_save_ruleset_0.12.0.json`) and no git
release tag existed for it. It is therefore unreleased, and this erratum's constant change ships
under the same `0.13.0` / save format `1` rather than requiring a version bump.

## 9. Summary

- Three defects in the original scratch driver are documented: 1-based turn indexing (defect 1), a
  floor-run counter that never reset across ceasefires (defect 2), and a `no_indefinite_ceasefire`
  grid criterion that counted horizon-censored ceasefires as indefinite (defect 3).
- Correcting all three and re-running the 240-cell grid honestly yields 27 of 240 passing (vs. the
  frozen plan's 5 of 240), with `(250, 200, 4500, 3)` as the selection-rule winner under the frozen
  plan's own unmodified selection order.
- That configuration is adopted as the shipped constants (§7); every other formula, scenario,
  schema, and constant is unchanged.
- §10's originally reported figures are superseded by §3–§6 above for any future reference to W1
  calibration; the frozen plan document itself is not edited.
