# External Wars W1 — calibration erratum for frozen-plan §10

**Status:** docs-only correction. Does not edit the frozen plan.
**Frozen plan:** `docs/plans/external-wars-w1-implementation-plan.md`,
SHA-256 `2ceb9a7b33512a45f6d756d3a1698c724495475d374f3d339814fef1040c82e0`.
**Applies to:** §10 ("W1 calibration — measured against the final content and remedies (R15)"),
subsections 10.1–10.8, and the derivation of the shipped constants in §10.1 and §10.7.

This erratum corrects the *measurement* that produced §10's figures. It changes no production
code, no formula, no scenario content, no schema, and no calibrated constant. The shipped
constants remain exactly as recorded in §10.1:

```
MIN_ACTIVE_INTENSITY_BPS      = 500
CEASEFIRE_RECOVERY_BPS        = 300
CEASEFIRE_BREAKDOWN_BPS       = 4,000
CEASEFIRE_DURABILITY_TURNS    = 4
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
  (tool id `toolu_019tyR8cMhuaAYRjeGdG4ALp`).

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

**Corrected definition (this erratum):** the continuous-floor-run counter increments only while a
conflict's closing status is `ACTIVE` **and** its closing intensity equals
`MIN_ACTIVE_INTENSITY_BPS` exactly; it resets to zero on every other closing state, explicitly
including `CEASEFIRE`, `SETTLED`, `DECIDED`, and `ACTIVE` above the floor.

### Basis validation

Before trusting any corrected figure, the recovered driver's own (1-based, unreset-counter) logic
was reproduced against a parity-proven isolated harness and checked against §10.7's own numbers:
it reproduced the frozen grid exactly — same 5 of 240 passing, identical five tuples, identical
per-row statistics, identical six failure counts (155/125/125/79/68/60). This confirms the
corrected-basis divergence below comes from the two defects above, not from a difference in the
new measurement code.

## 2. Corrected measurement basis

Production-native: turns 0..H-1 (40-turn horizon = turns 0–39; 80-turn horizon = turns 0–79),
using an isolated calibration harness that performs only turn iteration and per-conflict status
dispatch — every arithmetic step calls the real `app.simulation.foreign_conflict`,
`app.simulation.legitimacy`, and `app.core.rng` functions, never a reimplemented formula. The
harness was proven field-by-field parity-identical to `resolve_turn` on every turn reachable
before an unrelated campaign-terminal outcome, across all three shipped scenarios and the five
declared seeds (`42, 1337, 20260826, 7, 99991`).

## 3. Corrected §10.2–§10.4 figures (shipped constants, both approved floors)

| §10.2 | Horizon | Runs | Conflicts | Quiet campaigns |
|---|---:|---:|---:|---:|
| frozen | 40t | 15 | 15 | 2 / 15 |
| **corrected** | 40t | 15 | **16** | 2 / 15 |
| frozen | 80t | 15 | 25 | 0 / 15 |
| **corrected** | 80t | 15 | **26** | 0 / 15 |

| §10.3 | Horizon | Completed n | min/med/max | Right-censored n | observed min/max |
|---|---:|---:|---|---:|---|
| frozen | 40t | 4 | 14/15/15 | 11 | 2/38 |
| **corrected** | 40t | **5** | **14/15/37** | 11 | **1/40** |
| frozen | 80t | 14 | 14/15/68 | 11 | 5/78 |
| **corrected** | 80t | **15** | 14/15/68 | 11 | **4/80** |

Opened-by-40 terminal-by-80: frozen 10/15 (66.7%); **corrected 11/16 (68.8%)** — both clear the
required ≥50% threshold.

| §10.4 | Horizon | DECIDED | SETTLED | ACTIVE | CEASEFIRE | CF breakdowns | CF maturations |
|---|---:|---:|---:|---:|---:|---:|---:|
| frozen | 40t | 0 | 4 | 10 | 1 | 7 | 4 |
| **corrected** | 40t | **1** | 4 | 10 | 1 | **8** | 4 |
| frozen | 80t | 3 | 11 | 11 | 0 | 20 | 11 |
| **corrected** | 80t | **4** | 11 | **10** | **1** | **21** | 11 |

| §10.4 intensity | Horizon | min/med/max | floor binds | longest continuous floor run |
|---|---:|---|---:|---:|
| frozen | 40t | 58/4,645/6,215 | 57 | 16 |
| **corrected** | 40t | **58/2,895/6,215** | **93** | **23** |
| frozen | 80t | 7/698/6,215 | 309 | 51 |
| **corrected** | 80t | **7/547/6,215** | **337** | **31** |

Zero closing-`ACTIVE`-below-floor at both horizons, both bases — unchanged. Sub-floor
`SETTLED`/`DECIDED`/`CEASEFIRE` closes remain legal by design and are excluded from the floor-bind
and floor-run counts, exactly as in the frozen definition.

## 4. Categories confirmed unchanged (production-native basis, re-measured)

- **§10.5 concurrency:** shipped concurrency 1 at both horizons — unchanged. Synthetic multi-dyad
  fixture (3 dyads, 5 seeds, 80 turns): **29** conflicts (frozen fixture reported 20, from a
  different synthetic run), max concurrent **2**, cap (`MAX_CONCURRENT_CONFLICTS = 2`) never
  exceeded — unchanged conclusion.
- **§10.5 security anxiety** (5 seeds × 80 turns, negative-only, capped once):
  `tiny_valid` (exp 2,000): nonzero 159, min −71, median −63, max −6, cap hits 0.
  `decree_state` (exp 3,000): nonzero 227, min −111, median −9, max −9, cap hits 0.
  `deficit_demo` (exp 2,000): nonzero 229, min −72, median −6, max −6, cap hits 0.
  All min/median/max values match frozen exactly; only the nonzero-turn counts shift with the
  corrected turn base. The ±150 cap never binds — unchanged. Zero-exposure control: every value
  exactly 0 (n=400) — unchanged.
- **§10.6 low-pressure floor:** shipped weights unchanged (8,000 / 9,000 / 8,000). Low-pressure
  control (tension 200, grievance 0 ⇒ weight 100) yields **0 conflicts at both horizons, every
  seed** — unchanged, structural. `passes_pressure_floor(499) = False`,
  `passes_pressure_floor(500) = True` — unchanged.
- **Determinism / save-reload:** rerun byte-identical across all 15 (scenario × seed) runs — 400
  distinct traced turns. Split-run test (turns 0–39, save, reload at turn 40, continue 40 more)
  produces a trace identical to an uninterrupted 80-turn run — confirmed.
- **§10.8:** the disclosed long floor run remains intentional, not the removed absorbing state —
  exhaustion still accrues at the floor at `trunc_div(500 × 1200 / 10_000) = 60` bps/turn.
- **Performance:** full 15-run 80-turn calibration in 0.30s (frozen: 0.2s); 240-cell grid in ~74s
  (frozen: 11s) — both well inside any operating budget. Not asserted as a regression equality.

## 5. The 240-configuration grid, corrected basis

Same 240 cells (`MIN_ACTIVE_INTENSITY_BPS` × the 48-cell ceasefire grid), same declared seeds, same
nine acceptance criteria, turns 0–79, corrected floor-run definition. **7 of 240 pass** (frozen: 5
of 240):

| FLOOR | REC | BRK | DUR | CF→ACT | CF→SET | DEC | SET | ACT | ≥10t | %term | rate/40 | dur min/med/max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 250 | 300 | 4000 | 4 | 18 | 11 | 1 | 11 | 13 | 23 | 50.0 | 0.83 | 14/15/39 |
| 250 | 400 | 3500 | 4 | 9 | 21 | 1 | 21 | 10 | 28 | 76.5 | 1.07 | 14/15/39 |
| 500 | 400 | 3500 | 4 | 9 | 23 | 2 | 23 | 8 | 29 | 88.2 | 1.10 | 14/15/64 |
| 750 | 400 | 3500 | 4 | 13 | 22 | 1 | 22 | 10 | 29 | 82.4 | 1.10 | 14/15/49 |
| 1000 | 400 | 3500 | 4 | 13 | 23 | 3 | 23 | 7 | 29 | 94.4 | 1.10 | 14/15/69 |
| 1250 | 300 | 4000 | 4 | 31 | 12 | 6 | 12 | 9 | 25 | 87.5 | 0.90 | 14/16/76 |
| 1250 | 400 | 4000 | 3 | 32 | 12 | 6 | 12 | 10 | 26 | 87.5 | 0.93 | 13/15/63 |

Failure counts across all 240: `cf_to_settled_witness` 148, `settled_reachable` 148,
`no_indefinite_ceasefire` 135, `terminal_ge_50pct` 73, `decided_reachable` 62,
`cf_to_active_witness` 60. Zero below-floor `ACTIVE` closes and zero stalled conflicts across all
240 — unchanged.

### The selection-rule finding

**`(500, 300, 4000, 4)` — the shipped configuration — is not in the corrected passing set.** It
fails exactly one of the nine criteria, `no_indefinite_ceasefire` (one `CEASEFIRE` conflict remains
open at the turn-79 horizon); it passes all eight others, including `zero_below_floor` and
`zero_stalled`. Applying §10.7's own selection rule to the corrected grid, floor 250 now has two
passing configurations where it previously had none, so `(500, 300, 4000, 4)` is no longer even
the selection rule's candidate floor, let alone its winner.

### Decision: ship `(500, 300, 4000, 4)` as a documented exception

This erratum does **not** redefine `no_indefinite_ceasefire` or any other acceptance criterion, and
does **not** change `MIN_ACTIVE_INTENSITY_BPS`, `CEASEFIRE_RECOVERY_BPS`,
`CEASEFIRE_BREAKDOWN_BPS`, or `CEASEFIRE_DURABILITY_TURNS`. The shipped configuration is retained
exactly as frozen in §10.1, with the fact of its corrected-basis selection-rule failure disclosed
here rather than silently absorbed or worked around. Rationale: both alternatives inspected during
this correction — redefining what "passing" means for the whole grid, or retuning a calibrated
constant — are substantive behavior/acceptance changes that were explicitly out of scope for a
measurement correction and were not separately authorized; the shipped configuration's failure is a
single, narrow, well-understood criterion (one lingering ceasefire at the 80-turn horizon, out of
26 conflicts across 15 runs) alongside a clean pass on every floor-safety and progress criterion,
so shipping it as a disclosed exception was judged preferable to an undiscussed behavior change.

## 6. Summary

- Constants, formulas, scenario content, schemas, and the ruleset/save-format versions are
  unchanged by this erratum.
- §10's originally reported figures are superseded by §3–§5 above for any future reference to W1
  calibration; the frozen plan document itself is not edited.
- The shipped configuration `(500, 300, 4000, 4)` remains in force, disclosed here as failing
  `no_indefinite_ceasefire` under corrected, production-native measurement and no longer the
  240-cell grid's selection-rule winner — a deliberate, documented exception rather than an
  oversight.
