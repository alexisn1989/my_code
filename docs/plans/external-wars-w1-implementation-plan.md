# MANDATE — External wars: master roadmap + calibrated Gate W1 plan

> **RECOVERY PROVENANCE.** The container reverted this plan file to a pre-revision draft
> (`d9e51fe9…`, explicitly rejected). This text was recovered by mechanically replaying the
> recorded `Write`/`Edit` operation log from the session transcript — not reconstructed from
> memory. The replay is deterministic and reproducible (380 ops applied, 3 inert failures whose
> target text a later complete `Write` had already replaced), yielding base SHA-256
> `4a2ef01d105abc20292210a79f72c9f3708af97dc20f0c65a44f62487ed64375`, which the product owner
> adopted as the authorized base text. That adoption is not a claim of proven byte-identity with
> the lost copy. The only changes applied on top of that base are the authorized §9.6 scenario
> authoring, this note, and the consistency corrections that authoring mechanically forces
> (explicit aggressor/defender fields in §6.2 and §6.3). A further authorized consistency
> revision then replaced foreign-actor ownership with a `foreign_profiles` namespace, removed
> two unused profile fields, repaired the ceasefire state machine against a declared 48-cell
> grid, and replaced every provisional calibration figure with measurements from the final
> authored content. A final authorized correction then removed the absorbing zero-intensity
> `ACTIVE` state via `MIN_ACTIVE_INTENSITY_BPS`, added `MIN_OUTBREAK_WEIGHT_BPS` so the
> low-pressure control is excluded structurally rather than by luck, and recalibrated against a
> declared 240-configuration grid.
>
> **PLAN ONLY.** No repository file was edited, no branch created, nothing committed, pushed or
> opened as a PR. The only authorized mutation was the R1 recovery
> (`git fetch` + `git merge --ff-only`). Calibration ran from a scratch driver outside the
> repository.

---

## 1. Recovered HEAD and baseline (R1)

Recovery performed exactly as authorized — no reset, amend, rebase or force-push:

```
git fetch origin claude/phase-4a-graphical-vertical-slice
git merge --ff-only origin/claude/phase-4a-graphical-vertical-slice
5915a6f → c47fc82   (fast-forward, 6 commits)
```

| Gate | Result |
|---|---|
| Local HEAD | **`c47fc82`** |
| Remote HEAD | **`c47fc82`** — equal |
| Working tree | clean |
| Backend | **6,348 passed**, 1 warning, 699.87s |
| Frontend | **133 passed**, 17.85s |
| Ruleset / content | 0.12.0 (`state.py:983`, all three scenarios) |
| Save format | 1 (`save_format.py:41`) |
| Frozen Phase 4A plan | unchanged |

Gate 4A3A files confirmed present. Baseline is authoritative.

## 2. The completeness rule — exact finding (R13, R15)

**It exists, it is exhaustive, and I measured it.**

- **Validator:** `TurnReport._all_twelve_domain_reports_are_all_present_or_all_absent`,
  `report.py:3385-3418`. Rejects any partial subset of the twelve domain reports.
- **Test:** `tests/test_tax_base_report.py:278-300`,
  `test_all_partial_combinations_of_twelve_reports_are_rejected`, parametrized over
  `itertools.combinations(_TWELVE_REPORT_FIELDS, r)` for `r` in 1..11 = **4,094 cases**.
- **Measured cost: 4,094 passed in 18.60 s** (~4.5 ms/case).

**Consequence, with the two proportions kept distinct — they are very different numbers:**

| Measure | Value |
|---|---|
| Share of **test cases** | **4,094 of 6,348 = 64.5%** |
| Share of **runtime** | **18.60 s of 699.87 s = 2.66%** |

The 64.5% figure is a **case count only**. It makes the suite's test *number* look dominated by one
parametrization, but each case is ~4.5 ms, so it costs **2.66% of wall time**. Any statement of the
form "this test is two thirds of the suite" is true of counts and false of cost.

**DECISION — APPROVED: keep exhaustive enumeration at 13 reports.** 8,190 cases ≈ 37 s inside a
~700 s backend suite (rising to roughly 5% of runtime, still small). **Convert to property-based
testing when report 14 arrives** (16,382 cases, ~75 s): all singletons, all all-but-one, plus a
seeded sample of the middle. ADR 0012's "1,022 at a tenth report" horizon note predates this
measurement; the measurement supersedes it.

## 3. Scope of this document (R2)

- **§5–§16: Gate W1 — fully specified and calibrated against the final authored content, and
  awaiting freeze authorization.** It is not authorized for implementation by this document.
- **§17: W2–W5 — nonbinding architectural outline only.**
- **Binding process rule:** each later gate gets **its own repository audit and its own detailed
  plan, written after its predecessor ships.** No W2–W5 formula, constant, state field or validator
  in §17 is approved by approving this document. Prerequisite state does not exist yet, so those
  designs cannot honestly be settled now.

## 4. Findings that gate the design (recap, all verified at `c47fc82`)

**Reusable:** three reserved noop phase slots — `resolve_diplomacy_and_sanctions` (7),
`resolve_military_movement_and_combat` (8), `apply_casualties_occupation_disruption_war_costs` (9)
(`phases.py:3126-3128`) — **no new slot needed**; `WorldState.countries` dict + `player_country_id`
(`state.py:974-981`); optional per-country `finance`/`economy`/`politics` (`state.py:963-972`);
`derive_rng(seed, turn, stream)` over blake2b (`core/rng.py:21-45`); eight existing streams
(`election`, `coup_*`, `unrest_*`, `impeachment_*`); preview provably RNG-free
(`api/preview.py:14-26`); alphabetical canonical decision-kind order (`decisions.py:479-491`);
45 reconciliation groups; 12 reports.

**Absent — the reason for the gate split:** `MilitaryState` and `DiplomaticRelationState` are named
in `state.py:6-8` as deliberately *not* stubbed. `InstitutionState(id="military")` feeds **only**
coup/unrest/impeachment (`government_survival.py:201-256`). No war-powers constitutional axis
(`constitution.py:44-119`). No trade model — `state.py:200-201` says exports are folded into one
coefficient *because* trade is not modelled. Non-player countries are inert (13+ sites read only
`player_country_id`). Invariants forbid non-player politics (`invariants.py:399,562`).
`deficit_demo` has one country. No war terminal outcome (`state.py:776-795`).

---

# GATE W1 — Foreign actors and persistent conflicts

Ruleset **0.12.0 → 0.13.0**. Save format stays **1**.

## 5. W1 scope, and the neutrality contradiction resolved (R3)

**W1 ships no player decision at all.** The player observes; the world moves.

**R3 resolved, one coherent rule applied everywhere:** in W1 the player is *uninvolved*, and that is
represented by the **absence of any engagement record**, not by an enum member. There is **no
`PlayerStance` enum, no `NEUTRAL` value, no neutrality decision and no engagement cost in W1.**
Explicit neutrality becomes a player choice with consequences in **W2**, where
`PlayerConflictEngagementState` is introduced (§17).

This removes the contradiction at the source rather than annotating around it: a stance enum whose
only reachable W1 value is `UNINVOLVED` would be exactly the decorative state this plan forbids.
Every table, state model, test and walkthrough below is written to that single rule.

## 6. W1 state model

### 6.1 Foreign actors: ownership, keying, and honest capability naming (R5, C2)

Foreign actors are **not** `CountryState` entries. `CountryState` requires `population` and
`treasury` with no defaults (`state.py`), so representing an abstract foreign actor that way would
force inventing demographic and fiscal data. They live in their own namespace instead:

```python
class ForeignProfileState(BaseModel):
    # An abstract foreign actor. `war_capability_bps` is an ABSTRACT AUTHORED CAPABILITY used
    # ONLY for non-player conflict progression. It is structurally separate from, and never read
    # by: the player's future `MilitaryState` (W4), `InstitutionState(id="military")`, and the
    # coup/unrest/impeachment formulas in `government_survival.py`.
    model_config = _STRICT_CONFIG
    display_name: str
    war_capability_bps: StrictBps

WorldState.foreign_profiles: dict[str, ForeignProfileState]
```

The **dictionary key is the stable foreign-country id**. The id is deliberately **not** duplicated
inside the value, so key and value can never disagree.

**Construction rules, each an invariant code:**

| Rule | Invariant code |
|---|---|
| Keys nonempty | `foreign_profile_id_empty` |
| Keys disjoint from every `WorldState.countries` id, including `neighbor` and the player | `foreign_profile_id_collides_with_country` |
| Both dyad members exist in `foreign_profiles` | `dyad_member_not_a_foreign_profile` |
| No dyad references `player_country_id` | `dyad_references_player_country` |
| Serialization/iteration is key-sorted, never insertion-ordered | `foreign_profiles_not_canonically_ordered` |

Key uniqueness is structurally guaranteed by the mapping type; the canonical-order rule is what
makes that guarantee observable in serialization.

**Order independence is explicit.** Every read of `foreign_profiles` — validation, outbreak
candidate assembly, weighted selection, report row emission, canonical JSON — iterates
`sorted(foreign_profiles)`. A test constructs the same world twice with the mapping built in two
different insertion orders and asserts byte-identical canonical JSON, identical outbreak draws and
identical reports.

**`neighbor` is untouched.** It remains an ordinary `CountryState`, is never a `foreign_profiles`
key, and is therefore never dyad-eligible. Nothing about it changes in W1.

**Removed from W1: `belligerence_bps` and `alignment_bps`.** Neither participates in any W1
formula — the outbreak weight is `trunc_div(tension + grievance, 2)` and reads neither, and no
other W1 formula references them. They were decorative future state. `alignment_bps` is a W2
diplomacy concern and is **not** prebuilt here.

**Mandatory test (R5): `test_foreign_capability_cannot_reach_domestic_coup_math`** — resolve a turn
twice with `war_capability_bps` at 0 and at 10,000 for every foreign profile, and assert the
`CoupUnrestReport` is byte-identical. Plus an AST/source scan asserting `government_survival.py`
never imports or references `ForeignProfileState` or `foreign_profiles`.

**Reconciliation ownership.** `foreign_profiles` is authored and static in W1: group 49 proves no
key and no value changed between opening and closing state. Tamper cases: mutated `display_name`;
mutated `war_capability_bps`; added profile; removed profile; profile id colliding with a country
id; dyad member absent from `foreign_profiles`.

### 6.2 Bilateral conflict dyads — wars need bilateral causes (R4)

A foreign actor's profile (§6.1) carries only `display_name` and `war_capability_bps` — nothing
about *why* A would attack B, and nothing about either actor's disposition toward the player. A
generic per-actor belligerence figure was deliberately rejected as a cause of war for the same
reason: it cannot express that a specific pair has a specific quarrel. The authored **bilateral
dyad** supplies that cause, and is the only thing that can.

```python
class ConflictDyadState(BaseModel):
    """An authored bilateral relationship between two FOREIGN countries. Only
    `eligible` dyads may ever generate a war — generic belligerence never causes
    an outbreak on its own."""
    model_config = _STRICT_CONFIG
    country_a: str          # canonical: country_a < country_b, lexicographic
    country_b: str
    tension_bps: StrictBps          # standing bilateral hostility
    grievance_bps: StrictBps        # accumulated specific casus belli
    eligible: bool                  # authored gate: may this pair ever fight?
    aggressor: str                  # authored; MUST equal country_a or country_b
    defender: str                   # authored; MUST be the other one
    aim_a: WarAim                   # each side's war aim IF war occurs — authored, never drawn
    aim_b: WarAim
    player_security_exposure_bps: StrictBps
    """AUTHORED security exposure of the player to THIS dyad's war. Explicit content, never
    inferred from a country id, name, adjacency heuristic, or any other derived signal (§9.2).
    Economic exposure is deliberately NOT modelled here and is zero in W1 — it arrives only when
    W3 builds a real trade channel."""
```

`WorldState.dyads: tuple[ConflictDyadState, ...]`, canonical by `(country_a, country_b)`,
**reject-not-normalize**.

**Aggressor and defender are separate explicit authored fields and are NEVER inferred from
canonical ordering.** Canonical order exists only to make the pair's identity and serialization
stable; it carries no role meaning. A validator enforces `{aggressor, defender} == {country_a,
country_b}` and `aggressor != defender`, and a dedicated test authors a dyad whose aggressor is
`country_b` — proving role and ordering are genuinely independent. Invariant codes
`dyad_roles_do_not_match_pair` and `dyad_aggressor_equals_defender`.

**R4's six required specifications, each answered:**

1. **Canonical pair ordering** — `country_a < country_b` lexicographically, enforced at construction
   and rejected (never reordered), matching every other ordered collection here. Invariant code
   `dyad_pair_not_canonical`.
2. **Active-conflict exclusion** — a dyad whose pair already has a conflict in `ACTIVE` or
   `CEASEFIRE` is removed from the candidate set. A pair cannot fight two wars at once.
3. **At most one outbreak per turn** — **yes**. One draw, one possible new war. Bounds the RNG,
   keeps the turn report legible, and makes the outbreak stream trivially auditable.
4. **Deterministic weighted candidate selection** —
   `weight(d) = clamp_bps(trunc_div(tension_bps + grievance_bps, 2))` for eligible, non-excluded
   dyads; a single cumulative-weight pick from the same `foreign_conflict_outbreak` RNG.
5. **Total pressure exceeding 10,000** — the occurrence probability is
   `min(10_000, trunc_div(total_weight * OUTBREAK_SCALE_BPS, 10_000))`, an **explicit clamp**: at
   saturation a war is certain among eligible dyads, and the weighted pick still decides which. The
   clamp is a named, tested boundary, not an accident of arithmetic.
6. **Reproducible ids and aims** — `conflict_id = f"{country_a}__{country_b}__t{opened_turn}"`,
   deterministic and unique (a pair cannot re-fight while active). **Aims are authored on the dyad,
   never drawn** — this removes an RNG draw and makes "why this war, with these aims" answerable
   from content rather than from a die roll.

### 6.3 Conflict state

```python
class ConflictStatus(StrEnum):
    ACTIVE = "active"          # reversible
    CEASEFIRE = "ceasefire"    # reversible
    SETTLED = "settled"        # TERMINAL
    DECIDED = "decided"        # TERMINAL

class WarAim(StrEnum):
    TERRITORIAL / REGIME_CHANGE / RESOURCE_ACCESS / DETERRENCE

class ForeignConflictState(BaseModel):
    model_config = _STRICT_CONFIG
    conflict_id: str
    country_a: str; country_b: str          # canonical, mirrors the dyad
    aggressor: str                          # COPIED at outbreak from the dyad, never re-derived
    defender: str
    war_capability_a_bps: StrictBps         # COPIED at outbreak — the conflict is self-contained
    war_capability_b_bps: StrictBps
    aim_a: WarAim; aim_b: WarAim
    opened_turn: int = Field(ge=0)
    intensity_bps: StrictBps
    position_bps: StrictRelationshipBps     # signed: >0 favours A
    exhaustion_a_bps: StrictBps
    exhaustion_b_bps: StrictBps
    negotiation_readiness_bps: StrictBps
    status: ConflictStatus
    ceasefire_run_turns: int = Field(ge=0, default=0)
    resolved_turn: int | None = None        # required iff status is terminal
```

**No player field of any kind in W1** (§5). **No `FROZEN` member** — see §8.4, where measurement
proves it unreachable.

`WorldState.conflicts: tuple[ForeignConflictState, ...]`, canonical by `conflict_id`,
reject-not-normalize.

**Invariants (new codes):** `dyad_pair_not_canonical`, `dyad_duplicate_pair`,
`dyad_country_unknown`, `dyad_country_is_player`, `conflict_ids_not_canonical`,
`conflict_duplicate_id`, `conflict_country_unknown`, `conflict_country_is_player`,
`conflict_resolved_turn_requires_terminal_status`, `conflict_terminal_status_requires_resolved_turn`,
`foreign_profile_required_for_dyad_member`.

**M8's two invariants are untouched** — a foreign *profile* is not politics and not a legislature.

## 7. Phase timing — exact opening/closing rules (C6)

Slot **7** `resolve_diplomacy_and_sanctions`: outbreak draw and initialization. Slot **8**
`resolve_military_movement_and_combat`: progression and termination. Slot **10**: the security
anxiety contribution. Slot **15**: report. **No new slot** (`phases.py:3126-3128`).

**Ten binding rules, used identically by the formulas, the report and reconciliation:**

1. A conflict created in slot 7 **is initialized in slot 7 and progresses in slot 8 of that same
   turn.** It is not skipped for one turn.
2. `closing_position` uses `opening_war_capability_a/b`, `opening_intensity`, `opening_position`
   and this turn's `position_jitter`.
3. `exhaustion_gain` uses **`opening_intensity`** — never a closing value.
4. `closing_intensity` uses `opening_intensity` plus `INTENSITY_GROWTH_BPS` minus decay scaled by
   **`closing_avg_exhaustion`**, which is stored under that exact name in the report row.
5. `closing_readiness` uses **`closing_avg_exhaustion`** and **`closing_position`**, both named.
6. Slot-10 anxiety uses the **post-slot-8** conflict snapshot.
7. Only conflicts still **`ACTIVE` after slot 8** contribute anxiety.
8. A conflict opened this turn **does** contribute if it is still `ACTIVE` after slot 8.
9. A conflict that became `CEASEFIRE`, `SETTLED` or `DECIDED` in slot 8 contributes **zero** that
   turn.
10. Compute each qualifying conflict's **uncapped** anxiety, **sum them**, then apply
    `MAX_SECURITY_CONTRIBUTION_BPS` **once to the aggregate** — never per conflict.

**Reveal-before-respond remains structural.** Slot 1 seals turn *N*'s decisions; outbreak is drawn
in slot 7, six slots later, so a war born in turn *N* cannot be referenced by a turn-*N* decision
set. W1 has nothing to respond *with*, so this is proven now and inherited free by W2.

## 8. The complete conflict state machine (R6)

### 8.1 Initialization at outbreak

```
position_bps          = 0
intensity_bps         = clamp_bps(INITIAL_INTENSITY_BPS
                        + trunc_div(tension_bps * TENSION_INTENSITY_WEIGHT_BPS, 10_000))
exhaustion_a/b_bps    = 0
negotiation_readiness = 0
ceasefire_run_turns   = 0
status                = ACTIVE
war_capability_a/b    = copied from each country's ForeignProfileState
```

### 8.2 ACTIVE progression, per turn, with the minimum-active-intensity floor

Every input is the **opening** value except where a name says `closing`:

```
position_jitter_bps  = draw(foreign_conflict_progress:{cid}) in [-PROGRESS_JITTER_BPS, +PROGRESS_JITTER_BPS]
closing_position_bps = clamp_rel(opening_position_bps
                       + trunc_div((opening_war_capability_a_bps - opening_war_capability_b_bps)
                                   * opening_intensity_bps, 10_000)
                       + position_jitter_bps)

exhaustion_gain_bps        = trunc_div(opening_intensity_bps * EXHAUSTION_RATE_BPS, 10_000)
closing_exhaustion_a/b_bps = clamp_bps(opening_exhaustion_a/b_bps + exhaustion_gain_bps)
closing_avg_exhaustion_bps = trunc_div(closing_exhaustion_a_bps + closing_exhaustion_b_bps, 2)

raw_closing_intensity_bps  = clamp_bps(opening_intensity_bps
                             + INTENSITY_GROWTH_BPS
                             - trunc_div(closing_avg_exhaustion_bps * INTENSITY_DECAY_BPS, 10_000))

closing_readiness_bps      = clamp_bps(closing_avg_exhaustion_bps
                             - trunc_div(abs(closing_position_bps) * DECISIVENESS_PENALTY_BPS, 10_000))
```

The terminal gates of §8.3 are then evaluated. **Only after `closing_status` is known** is the
floor applied:

```
if closing_status is ACTIVE:
    closing_intensity_bps = max(MIN_ACTIVE_INTENSITY_BPS, raw_closing_intensity_bps)
else:
    closing_intensity_bps = raw_closing_intensity_bps
```

**Why the floor exists, and what it is not.** `ACTIVE` is a claim that fighting is still happening;
a conflict that closed a turn at zero intensity was making that claim while nothing occurred. Worse,
it was **absorbing**: `exhaustion_gain_bps` is computed from `opening_intensity_bps`, so at zero
intensity exhaustion stopped accruing, `raw_closing_intensity_bps` could never recover, position
random-walked on jitter alone, and no terminal gate was reachable. The floor is the smallest causal
correction — *if the conflict is still classified as active, some fighting must still be occurring* —
and it restores progress by keeping `exhaustion_gain_bps` strictly positive, which is what
eventually opens the ceasefire path.

The floor is **not** an arbitrary exhaustion gain while intensity is zero, **not** an automatic
settlement when intensity collapses, and **not** a recovery oscillation. Terminal states
(`SETTLED`, `DECIDED`) keep the formula-derived `raw_closing_intensity_bps` with **no** floor, so a
war can still end quiet; `CEASEFIRE` may likewise decay below the floor, because a ceasefire is
precisely the claim that fighting has stopped.

**Invariant `active_conflict_below_minimum_intensity`:**
`status is ACTIVE  ⇒  intensity_bps >= MIN_ACTIVE_INTENSITY_BPS`.

**Combining rule.** All components derive from the opening conflict state, are summed once and
clamped once; a permutation test asserts order independence.

### 8.3 Terminal gates — fixed deterministic priority

Evaluated in this exact order; the first that opens wins:

1. **DECIDED** — `abs(position_bps) >= DECISIVE_POSITION_BPS`. **Purely deterministic, no draw.**
   This is R6's explicit requirement: a conflict past the decisive threshold **cannot** continue
   because a draw failed. `resolved_turn` set.
2. **SETTLED / CEASEFIRE** — when `readiness >= CEASEFIRE_THRESHOLD_BPS`, **one** draw from
   `foreign_conflict_termination:{cid}` decides which: `SETTLED` (terminal, `resolved_turn` set)
   requires `readiness >= SETTLEMENT_THRESHOLD_BPS` **and** `draw < readiness`; otherwise
   `CEASEFIRE` (reversible, `ceasefire_run_turns = 0`).

### 8.4 ⚠ `FROZEN` removed — measured unreachable (reality wins)

The earlier draft specified a `FROZEN` prolonged-stalemate status. **Two calibration passes prove it
can never fire**, at any swept constant:

| Configuration | Terminal statuses over 15 runs × 80 turns |
|---|---|
| `INTENSITY_DECAY_BPS=900` | `SETTLED 12, DECIDED 27, ACTIVE 10` — **no FROZEN** |
| `INTENSITY_DECAY_BPS=1400` | `ACTIVE 19, DECIDED 12, SETTLED 9` — **no FROZEN** |
| `INTENSITY_DECAY_BPS=2000` | `ACTIVE 27, DECIDED 4` — **no FROZEN** |
| Redefined as a long stalemate (≥15 turns, `abs(pos)≤3000`, `intensity≤800`, readiness below the ceasefire gate) | `SETTLED 12, DECIDED 27, ACTIVE 10` — **byte-identical, still no FROZEN** |

**Structural reason, and it is not a tuning problem.** Exhaustion rises monotonically and readiness
tracks it; therefore *any* sufficiently long war eventually crosses `CEASEFIRE_THRESHOLD_BPS`, and
the ceasefire gate always fires before an intensity-burnout gate can. `FROZEN` is dominated by
construction.

**DECISION — APPROVED: `FROZEN` is not in W1.** Prolonged stalemate is represented by a
**long-running `ACTIVE` conflict**, which the measurements show is real and common — mean duration
**14.0 turns**, max **50**, and **40 of 49** conflicts run ≥10 turns. An unreachable status kept for
narrative variety is exactly the decorative state §4 forbids. If playtesting later wants a distinct
burnout terminal it requires a non-monotonic exhaustion model — a separate design change needing its
own evidence, not a W1 addition.

### 8.5 CEASEFIRE — entry, maintenance, breakdown, maturation (repaired)

- **Entry:** §8.3 rule 2. `closing_ceasefire_run_turns = 0`.
- **Maintenance (per ceasefire turn):**
  `ceasefire_decayed_intensity_bps = clamp_bps(opening_intensity_bps − trunc_div(opening_intensity_bps × CEASEFIRE_INTENSITY_DECAY_BPS, 10_000))`;
  `closing_exhaustion_a/b_bps = max(0, opening_exhaustion_a/b_bps − CEASEFIRE_RECOVERY_BPS)`;
  `closing_readiness_bps = clamp_bps(closing_avg_exhaustion_bps − trunc_div(|position| × DECISIVENESS_PENALTY_BPS, 10_000))`;
  `closing_ceasefire_run_turns = opening_ceasefire_run_turns + 1`. **Position is frozen** — no
  jitter, no progress draw, no exhaustion accrual.
- **Breakdown, evaluated BEFORE maturation:** `closing_readiness_bps < CEASEFIRE_BREAKDOWN_BPS` ⇒
  `ACTIVE`, `closing_ceasefire_run_turns = 0`, and the returning conflict **restarts at or above the
  floor**:
  ```
  closing_intensity_bps = max(MIN_ACTIVE_INTENSITY_BPS, ceasefire_decayed_intensity_bps)
  ```
- **Maturation:** `closing_ceasefire_run_turns >= CEASEFIRE_DURABILITY_TURNS` ⇒ `SETTLED`,
  `resolved_turn` set, `closing_intensity_bps = ceasefire_decayed_intensity_bps` (no floor — a
  settled war is not fighting).
- **Staying in ceasefire:** `closing_intensity_bps = ceasefire_decayed_intensity_bps`, **no floor**.

**The previously specified constants made `CEASEFIRE → ACTIVE` unreachable by construction**, proven
by executing the plan's own loop: entry readiness is at least `CEASEFIRE_THRESHOLD_BPS` (5,000);
position is frozen, so readiness falls by exactly `CEASEFIRE_RECOVERY_BPS` per turn; with recovery
200 and durability 3 the lowest readiness reachable before maturation is 4,400, which never crosses
a 3,500 breakdown threshold. Position cancels out of the comparison entirely.

### 8.6 Terminal vs reversible, and `resolved_turn`

| Status | Kind | `resolved_turn` |
|---|---|---|
| `ACTIVE` | reversible | **must be `None`** |
| `CEASEFIRE` | reversible | **must be `None`** |
| `SETTLED` | **terminal** | **required** |
| `DECIDED` | **terminal** | **required** |

Enforced by a row self-validator **and** by two invariant codes, so neither a report nor a state can
carry the mismatch alone.

### 8.7 Exactly what each RNG draw decides

| Stream | Draws | Decides |
|---|---|---|
| `foreign_conflict_outbreak` | 2 per turn, max | (a) does a war start; (b) which eligible dyad |
| `foreign_conflict_progress:{cid}` | 1 per ACTIVE conflict per turn | the position jitter, nothing else |
| `foreign_conflict_termination:{cid}` | 1 only when the ceasefire gate is open | settlement vs. ceasefire, nothing else |

`DECIDED` consumes no randomness. `CEASEFIRE` maintenance, breakdown and maturation consume none.

## 9. Domestic effects — explicit authored security exposure only (R9)

### 9.1 The binding rule

**An external war produces zero effect on the player unless the authored
`player_security_exposure_bps` for that dyad is nonzero.** A distant war must not arbitrarily alter
legitimacy or approval. **W1's only permitted channel is security exposure. Economic exposure is
zero until W3 builds a real trade channel.**

### 9.2 Exposure is authored, never inferred

Exposure is read **only** from `ConflictDyadState.player_security_exposure_bps`. It is **never**
inferred from a country id (`"neighbor"`), display name, position in a list, or any adjacency
heuristic. Enforced three ways:

- **Content rule:** each shipped scenario authors exactly **one border-adjacent dyad** with nonzero
  exposure; every remote dyad is authored **0**.
- **Source-scan test** `test_exposure_is_never_derived_from_an_identifier`: `foreign_conflict.py`
  and the slot-10 handler contain no string literal matching any scenario country id, and no
  substring/prefix test against a country id anywhere on the exposure path.
- **Behavioural test** `test_renaming_an_exposed_actor_does_not_change_exposure` (C9): in a dedicated fixture, rename
  **`kessia`** — a genuinely exposed, dyad-eligible actor — throughout `foreign_profiles`, the dyad
  and the authored exposure, preserving the explicitly authored `player_security_exposure_bps`.
  Assert the security-anxiety trajectory is byte-identical. Renaming `neighbor` would be vacuous:
  it is neither exposed nor dyad-eligible.
- `test_changing_only_an_id_cannot_create_remove_or_alter_exposure` (C9): mutate only ids, never
  exposure values, in three directions — exposed→unexposed name, unexposed→exposed name, and a
  name never used — and assert exposure is unchanged in all three.
- `test_no_scenario_id_literal_appears_on_the_exposure_path` (C9): source scan over
  `foreign_conflict.py` and the slot-10 handler for any literal equal to a scenario country or
  profile id.

### 9.3 ⚠ Two engine findings that constrain the design

**Finding A — population approval is authored and never mutated by any phase.** Exhaustive search
of `app/simulation/` shows `approval` is only ever *read*, by `government_survival.py`'s coup and
unrest formulas (`:78, :107-137, :296-312`). No phase writes it. **Therefore W1 does not touch
approval at all** — doing so would require building an approval-mutation subsystem that does not
exist, which is precisely the invention this plan refuses. "Public concern" is expressed through
legitimacy, which *is* a live, moving quantity.

**Finding B — `resolve_legitimacy` today accepts exactly two contributions.**
`legitimacy.py:188-206`:

```
requested = order_support_contribution + performance_contribution
capped    = clamp(requested, ±MAX_TOTAL_LEGITIMACY_CHANGE_BPS)      # ±500
closing   = clamp(opening + capped, LEGITIMACY_MIN_BPS, LEGITIMACY_MAX_BPS)
return closing - opening, closing        # the APPLIED change is what gets reported
```

Adding a third contribution is therefore **a real change to a shipped, self-validated formula**, not
a bolt-on: it changes the function signature, `PoliticalReport`'s stored fields, that report's
self-validator, and the reconciliation group that re-derives legitimacy. That cost is accepted and
scheduled in commit 5 — it is the honest way in, and the alternative (a post-hoc legitimacy nudge
outside `resolve_legitimacy`) would bypass both the ±500 cap and the applied-vs-requested discipline
that makes legitimacy auditable.

### 9.4 The security-anxiety contribution

A third named contribution, symmetric with `performance_contribution` and carrying its own cap:

```
security_anxiety_bps = clamp(
    -trunc_div(player_security_exposure_bps * intensity_bps * SECURITY_ANXIETY_WEIGHT_BPS,
               10_000 * 10_000),
    low = -MAX_SECURITY_CONTRIBUTION_BPS,
    high = 0)
```

Summed over every `ACTIVE` conflict whose dyad has nonzero exposure, then passed to
`resolve_legitimacy` as `security_contribution`.

**Sign is negative-only, deliberately.** A nearby war creates anxiety; it never *raises* legitimacy.
A rally-round-the-flag effect is a real phenomenon but claiming it here would be an unevidenced
invention, so the minimal honest claim is one-directional pressure.

**Zero exposure ⇒ exactly zero**, by construction — the multiplication makes it arithmetically
impossible for a remote war to move legitimacy by even one bps.

### 9.5 Sizing — measured, and the first formula was badly wrong

The earlier draft's `trunc_div(exposure * intensity, 10_000)` yields **1,200 bps** at exposure 2,000
and intensity 6,000. Against `MAX_TOTAL_LEGITIMACY_CHANGE_BPS = 500` and
`MAX_PERFORMANCE_CONTRIBUTION_BPS = 300`, that would **saturate the total legitimacy cap downward
every single turn of every war**, swamping both economic performance and constitutional drift. It
was mis-scaled by roughly an order of magnitude.

Corrected by measuring **real** war intensities — 563 ACTIVE-turn samples across all three scenarios
× five declared seeds × 80 turns:

```
intensity:  min 0   p25 3,745   median 4,642   p75 5,277   p95 5,621   max 5,668
```

(Materially lower than the assumed 6,000–8,000, because intensity decays as exhaustion accumulates.)
Resulting anxiety, with `MAX_SECURITY_CONTRIBUTION_BPS = 150`:

| `SECURITY_ANXIETY_WEIGHT_BPS` | exposure 0 | exposure 2,000 | exposure 3,000 | cap binds? |
|---|---|---|---|---|
| 400 | 0 / 0 / 0 | median 37, p95 44 | median 55, p95 67 | never |
| **600** ✅ | **0 / 0 / 0** | **median 55, p95 67** | **median 83, p95 101** | **never** |
| 800 | 0 / 0 / 0 | median 74, p95 89 | median 111, p95 134 | never |

**Chosen: `SECURITY_ANXIETY_WEIGHT_BPS = 600`, `MAX_SECURITY_CONTRIBUTION_BPS = 150`.** At exposure
3,000 a war contributes a median **83 bps** — about 28% of the performance cap and 17% of the total
legitimacy cap: clearly felt, clearly secondary to the economy. 400 is too faint to notice; 800
starts rivalling performance. **The ±150 cap never binds at measured intensities** — a defence that
does not fire in practice, the same status the ceiling clamps elsewhere in this codebase hold.

### 9.6 Final authored scenario content — COMPLETE (C1, C3)

**Foreign profiles** (`WorldState.foreign_profiles`, key → value):

| Key (id) | `display_name` | `war_capability_bps` | Present in |
|---|---|---:|---|
| `kessia` | Kessia | 5,000 | `tiny_valid` |
| `vetruska` | Vetruska | 5,600 | `tiny_valid` |
| `marnil` | Marnil | 5,800 | `decree_state`, `deficit_demo` |
| `sorrend` | Sorrend | 6,400 | `decree_state` |
| `tolvane` | Tolvane | 6,400 | `deficit_demo` |

**Conflict dyads — the complete authored record. Exactly ONE eligible dyad per shipped scenario;
three across the whole catalog.**

| Scenario | `country_a` | `country_b` | `aggressor` | `defender` | `war_capability_a_bps` | `war_capability_b_bps` | `tension_bps` | `grievance_bps` | `aim_a` | `aim_b` | `eligible` | `player_security_exposure_bps` | Player-adjacent (rationale) |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|---:|---|
| `tiny_valid` | `kessia` | `vetruska` | `vetruska` | `kessia` | 5,000 | 5,600 | 8,500 | 7,500 | `DETERRENCE` | `TERRITORIAL` | `true` | **2,000** | `kessia` |
| `decree_state` | `marnil` | `sorrend` | `sorrend` | `marnil` | 5,800 | 6,400 | 9,500 | 8,500 | `DETERRENCE` | `REGIME_CHANGE` | `true` | **3,000** | `marnil` |
| `deficit_demo` | `marnil` | `tolvane` | `tolvane` | `marnil` | 5,800 | 6,400 | 9,000 | 7,000 | `DETERRENCE` | `RESOURCE_ACCESS` | `true` | **2,000** | `marnil` |

**Canonical rules.** `country_a < country_b` lexicographically. `aim_a` belongs to the canonical A
actor and `aim_b` to the canonical B actor — **aims follow canonical ordering, not roles**. In all
three initial dyads `country_b` happens to be the aggressor and the defender's aim is `DETERRENCE`,
but that is authored coincidence: roles are stored explicitly and **never** inferred from ordering
or from this pattern (§6.2's independence validator and test).

**Derived outbreak inputs, verified against the implementation:**

| Scenario | weight = `trunc_div(tension + grievance, 2)` | probability = `min(10000, trunc_div(weight x 700, 10000))` |
|---|---:|---:|
| `tiny_valid` | **8,000** | **560 bps** |
| `decree_state` | **9,000** | **630 bps** |
| `deficit_demo` | **8,000** | **560 bps** |

These are per-eligible-turn formula inputs before active-conflict exclusion, **not** guaranteed
campaign frequencies. Measured frequencies are §10.

**Scenario actor counts (C3).**

| Scenario | Retains | Adds as foreign profiles | Eligible dyads |
|---|---|---|---:|
| `tiny_valid` | `neighbor` (unchanged `CountryState`) | Kessia, Vetruska | 1 |
| `decree_state` | `neighbor` (unchanged `CountryState`) | Marnil, Sorrend | 1 |
| `deficit_demo` | — | Marnil, Tolvane | 1 |

**No `neighbor` dyad is eligible, and none is constructed.** A test asserts each scenario's
eligible dyad set has exactly one member and that `neighbor` appears in no dyad.

**W1 foreign actors stay abstract.** Only `display_name` and `war_capability_bps` are authored.
**No** population, treasury, institutions, economy, finance, politics, trade value or army is
invented. Should implementation require player-style country state for a foreign actor, that is a
schema defect to stop and report — not a licence to fabricate data.

### 9.7 Tests

- `test_zero_exposure_war_leaves_the_player_byte_identical` — a war fought to termination beside a
  player whose dyads are all 0-exposure produces a player-country state **byte-identical** to a
  no-war control run, including legitimacy, approval and political capital.
- `test_security_contribution_is_exactly_the_anxiety_formula` — re-derived from the report's own
  stored exposure, intensity, weight and cap.
- `test_security_contribution_is_never_positive`.
- `test_security_cap_does_not_bind_at_measured_intensities` — pins §9.5's "never binds" finding so a
  future intensity change that starts saturating the cap fails loudly instead of silently.
- `test_approval_is_untouched_by_any_foreign_war` — Finding A, pinned.
- The two §9.2 anti-inference tests.

**Bloc reactions remain out of W1.** Blocs carry only tax and spending preferences
(`legislative_voting.py`), so W1 cannot claim a bloc "favours a side". Authored foreign-policy
preferences (humanitarianism / interventionism / multilateralism) are a **W2** question, decided in
W2's own plan against W2's own evidence, and derived from neither government role nor constitution.

## 10. W1 calibration — measured against the final content and remedies (R15)

Every figure below comes from the selected configuration running the **final** authored content
(§9.6) with **both approved floors** in force. Nothing measured before those remedies survives.

**Driver:** a scratch script outside the repository importing the real engine's `derive_rng`
unmodified and applying §7/§8's opening/closing discipline exactly. **Seeds, declared before the
first run: 42, 1337, 20260826, 7, 99991.** Three shipped scenarios × five seeds = 15 runs/horizon.

### 10.1 Constants

| Constant | Value | Basis |
|---|---:|---|
| `MIN_ACTIVE_INTENSITY_BPS` | **500** | 240-cell grid §10.7 — lowest passing floor |
| `MIN_OUTBREAK_WEIGHT_BPS` | **500** | approved low-pressure floor §10.6 |
| `CEASEFIRE_RECOVERY_BPS` | **300** | grid — from 200 |
| `CEASEFIRE_BREAKDOWN_BPS` | **4,000** | grid — from 3,500 |
| `CEASEFIRE_DURABILITY_TURNS` | **4** | grid — from 3 |
| `OUTBREAK_SCALE_BPS` | 700 | approved, unchanged |
| `INITIAL_INTENSITY_BPS` / `TENSION_INTENSITY_WEIGHT_BPS` | 3,000 / 3,000 | unchanged |
| `PROGRESS_JITTER_BPS` / `EXHAUSTION_RATE_BPS` | 300 / 1,200 | unchanged |
| `INTENSITY_GROWTH_BPS` / `INTENSITY_DECAY_BPS` | 250 / 900 | unchanged |
| `DECISIVENESS_PENALTY_BPS` / `DECISIVE_POSITION_BPS` | 6,000 / 6,000 | unchanged |
| `CEASEFIRE_THRESHOLD_BPS` / `SETTLEMENT_THRESHOLD_BPS` | 5,000 / 7,500 | unchanged |
| `CEASEFIRE_INTENSITY_DECAY_BPS` | 2,500 | unchanged |
| `SECURITY_ANXIETY_WEIGHT_BPS` / `MAX_SECURITY_CONTRIBUTION_BPS` | 600 / 150 | unchanged; cap applied once to the aggregate |
| `MAX_CONCURRENT_CONFLICTS` | 2 | global cap |

### 10.2 Outbreak frequency and campaign shape

| Horizon | Runs | Conflicts | Per run | Quiet campaigns |
|---:|---:|---:|---:|---:|
| 40 turns | 15 | 15 | **1.00** | **2 / 15** |
| 80 turns | 15 | 25 | **1.67** | **0 / 15** |

Both inside the required 0.5–2.5 band.

### 10.3 Durations — completed and right-censored reported separately

Unresolved conflicts are **never** treated as completed.

| Horizon | Completed | min / median / max | Right-censored (still `ACTIVE`/`CEASEFIRE`) | observed-so-far min / max |
|---:|---:|---|---:|---|
| 40 turns | **4** | 14 / 15 / 15 | **11** | 2 / 38 |
| 80 turns | **14** | 14 / 15 / 68 | **11** | 5 / 78 |

**Conflicts opened by turn 40 that are terminal by turn 80: 10 / 15 = 66.7%** (requirement ≥50%).

### 10.4 Status, ceasefire behaviour, intensity and the floor

| Horizon | DECIDED | SETTLED | ACTIVE | CEASEFIRE | CF breakdowns | CF maturations |
|---:|---:|---:|---:|---:|---:|---:|
| 40 turns | 0 | 4 | 10 | 1 | **7** | **4** |
| 80 turns | **3** | **11** | 11 | 0 | **20** | **11** |

Both ceasefire paths have natural witnesses at both horizons, and both terminal outcomes are
naturally reachable at 80 turns.

| Horizon | intensity min / median / max | floor binds | longest continuous run at the floor |
|---:|---|---:|---:|
| 40 turns | 58 / 4,645 / 6,215 | 57 | 16 turns |
| 80 turns | 7 / 698 / 6,215 | 309 | 51 turns |

**Minima below 500 are correct and expected:** they are the closing intensities of `SETTLED`,
`DECIDED` and `CEASEFIRE` conflicts, which by design carry no floor. **No `ACTIVE` conflict closes a
turn below 500** — zero violations across all 240 grid configurations, verified explicitly.

### 10.5 Concurrency, determinism, RNG, security anxiety, performance

| Case | Result |
|---|---|
| Shipped-scenario concurrency | **1** at both horizons — each scenario has exactly one eligible dyad |
| Synthetic multi-dyad fixture | 20 conflicts across five seeds; **max concurrent = 2**, cap never exceeded |
| Determinism / save-reload | byte-identical across all scenarios and seeds |
| RNG-stream independence | the eight existing streams byte-identical before and after all conflict draws |
| Performance | full final calibration in **0.2 s**; the 240-configuration grid in **11 s** — well inside budget |

Security anxiety (negative-only, summed across qualifying conflicts then capped **once**), nonzero
turns across five seeds × 80 turns:

| Scenario | exposure | nonzero turns | min | median | max | cap hits |
|---|---:|---:|---:|---:|---:|---:|
| `tiny_valid` | 2,000 | 151 | −71 | −63 | −6 | **0** |
| `decree_state` | 3,000 | 229 | −111 | −9 | −9 | **0** |
| `deficit_demo` | 2,000 | 197 | −72 | −6 | −6 | **0** |

The ±150 aggregate cap **never binds** — it is not the ordinary result. Zero-exposure control: every
anxiety value exactly 0.

### 10.6 The low-pressure outbreak floor

```
weight_bps = clamp_bps(trunc_div(tension_bps + grievance_bps, 2))

candidate  ⇔  eligible
              and weight_bps >= MIN_OUTBREAK_WEIGHT_BPS
              and no ACTIVE or CEASEFIRE conflict already exists for the pair
```

Three distinct authored meanings: `eligible = false` — the pair cannot fight at all;
`eligible = true` with weight below 500 — the pair could fight, but present tension is too low;
`eligible = true` with weight ≥ 500 — the pair participates in outbreak selection.

**Boundary tests, both measured:** weight **499 ⇒ not a candidate**; weight **500 ⇒ candidate**.

Shipped weights are unchanged and all far above the floor: `tiny_valid` 8,000, `decree_state` 9,000,
`deficit_demo` 8,000. The low-risk control (tension 200, grievance 0 ⇒ **weight 100**) is now
excluded **structurally**: **0 conflicts at 40 turns and 0 at 80 turns across every declared seed**,
by threshold rather than by luck.

### 10.7 The 240-configuration grid

Declared before running: `MIN_ACTIVE_INTENSITY_BPS` ∈ {250, 500, 750, 1000, 1250} crossed with the
full 48-cell ceasefire grid (`CEASEFIRE_RECOVERY_BPS` ∈ {200, 300, 400, 500} ×
`CEASEFIRE_BREAKDOWN_BPS` ∈ {3500, 4000, 4500, 5000} × `CEASEFIRE_DURABILITY_TURNS` ∈ {3, 4, 5}) =
**240 configurations**. Authored capabilities, tension, grievance, aims, exposure,
`OUTBREAK_SCALE_BPS`, drift, jitter, exhaustion rate and the decisive threshold were **not** changed.

**5 of 240 pass.** Across all 240: **zero** below-floor `ACTIVE` closes and **zero** stalled
(non-progressing) active conflicts — the absorbing state is eliminated by the floor at every setting.

| floor | passing / 48 | below-floor violations | stalled |
|---:|---:|---:|---:|
| 250 | 0 | 0 | 0 |
| **500** | **1** | 0 | 0 |
| 750 | 1 | 0 | 0 |
| 1,000 | 2 | 0 | 0 |
| 1,250 | 1 | 0 | 0 |

| FLOOR | REC | BRK | DUR | CF→ACT | CF→SET | DECIDED | SETTLED | ACTIVE | ≥10t | % terminal | rate/40 | completed dur min/med/max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **500** | **300** | **4000** | **4** | **20** | **11** | **3** | **11** | 11 | 22 | **66.7** | **1.00** | 14 / 15 / 68 |
| 750 | 400 | 3500 | 4 | 14 | 19 | 1 | 19 | 10 | 26 | 75.0 | 1.07 | 14 / 15 / 51 |
| 1,000 | 400 | 3500 | 4 | 14 | 20 | 3 | 20 | 7 | 26 | 88.2 | 1.13 | 14 / 15 / 69 |
| 1,000 | 500 | 3500 | 4 | 31 | 1 | 9 | 1 | 11 | 20 | 69.2 | 0.87 | 15 / 47 / 78 |
| 1,250 | 300 | 4000 | 4 | 28 | 13 | 5 | 13 | 9 | 25 | 87.5 | 1.07 | 14 / 16 / 76 |

**Why the other 235 fail** (a configuration may fail several criteria at once):

| Failure | Configurations |
|---|---:|
| indefinite ceasefire | 155 |
| no `CEASEFIRE → SETTLED` witness | 125 |
| `SETTLED` unreachable | 125 |
| fewer than 50% terminal by turn 80 | 79 |
| `DECIDED` unreachable | 68 |
| no `CEASEFIRE → ACTIVE` witness | 60 |

**Selection proof, in the mandated order:**

1. **Lowest `MIN_ACTIVE_INTENSITY_BPS`** — 250 has **0** passing configurations; **500** has 1. Floor
   500 selected; only one candidate remains, so rules 2–5 are satisfied vacuously by that row.
2. Changed ceasefire constants: 3 (recovery, breakdown, durability all move).
3. Durability 4. 4. Recovery change |300 − 200| = 100. 5. Breakdown change |4000 − 3500| = 500.

```
MIN_ACTIVE_INTENSITY_BPS      (new) = 500
CEASEFIRE_RECOVERY_BPS      200 -> 300
CEASEFIRE_BREAKDOWN_BPS    3500 -> 4000
CEASEFIRE_DURABILITY_TURNS    3 -> 4
```

### 10.8 Disclosed characteristic — long low-intensity grinds

At 80 turns the longest continuous period a conflict spends pinned at the floor is **51 turns**.
This is **not** the former absorbing state: exhaustion still accrues at
`trunc_div(500 × 1200 / 10_000) = 60` bps per turn, so readiness rises monotonically and the
ceasefire path always eventually opens — which is why 66.7% of conflicts opened by turn 40 are
terminal by turn 80, against 0% terminal progress under the old formula. It does mean a long war can
settle into a protracted low-intensity phase before ending. That is disclosed as a property of the
selected calibration, not a defect.

## 11. Report model and validator ownership (R13, C7)

**Thirteenth report: `foreign_affairs: ForeignAffairsReport`.** Completeness becomes 8,190 cases
(§2) — exhaustive enumeration retained.

### 11.1 Outbreak row — complete schema

Emitted on any turn the outbreak draw runs, whether or not a war starts.

```
turn
candidates: tuple[OutbreakCandidateRow, ...]     # canonical by (country_a, country_b)
    country_a, country_b, aggressor, defender
    tension_bps, grievance_bps, candidate_weight_bps
raw_dyad_weight_bps                              # per candidate, before the pressure floor
passed_pressure_floor: bool                      # per candidate
minimum_outbreak_weight_bps                      # the threshold constant, stored
total_weight_bps                                 # sum over candidates that passed the floor
outbreak_scale_bps                               # the constant, stored
clamped_probability_bps                          # min(10000, trunc_div(total*scale,10000))
occurrence_draw                                  # the raw draw
occurred: bool
selection_draw: int | None                       # present iff occurred
selected_country_a, selected_country_b: str|None
conflict_id: str | None
opened_turn: int | None
initial_intensity_bps, initial_position_bps: int|None
initial_exhaustion_a_bps, initial_exhaustion_b_bps: int|None
initial_readiness_bps: int | None
initial_intensity_constant_bps, tension_intensity_weight_bps  # the constants used
```

Self-validators: each `raw_dyad_weight_bps` equals `trunc_div(tension+grievance, 2)`;
`passed_pressure_floor` equals `raw_dyad_weight_bps >= minimum_outbreak_weight_bps`, checked at the
exact 499/500 boundary; `total_weight_bps` equals the sum over **passing** candidates only; `clamped_probability_bps` equals the clamped formula; `occurred` agrees with
`occurrence_draw < clamped_probability_bps`; selection fields present iff `occurred`; the selected
pair is one of the candidates and is the one the cumulative-weight walk over `selection_draw`
lands on; the initialization values equal the §8.1 formulas from the stored constants.

**Candidate *eligibility* — which dyads were legal to list — is state-dependent and remains
reconciliation-owned** (group 47).

### 11.2 Progression row — every rederived input is stored

```
conflict_id, opened_turn, resolved_turn
opening_status, closing_status
opening_war_capability_a_bps, opening_war_capability_b_bps
opening_intensity_bps, raw_closing_intensity_bps, closing_intensity_bps
minimum_active_intensity_bps, active_intensity_floor_applied: bool
opening_position_bps, closing_position_bps, position_jitter_bps
opening_exhaustion_a_bps, opening_exhaustion_b_bps
closing_exhaustion_a_bps, closing_exhaustion_b_bps
closing_avg_exhaustion_bps
exhaustion_rate_bps, exhaustion_gain_bps
intensity_growth_bps, intensity_decay_bps
opening_readiness_bps, closing_readiness_bps, decisiveness_penalty_bps
decisive_position_threshold_bps, ceasefire_threshold_bps, settlement_threshold_bps
ceasefire_intensity_decay_bps, ceasefire_recovery_bps
ceasefire_breakdown_bps, ceasefire_durability_turns
opening_ceasefire_run_turns, closing_ceasefire_run_turns
termination_draw: int | None                     # present iff the ceasefire gate opened
```

**Every gameplay constant a self-validator uses is stored in the row.** That is the point of listing
`exhaustion_rate_bps`, `intensity_growth_bps`, `intensity_decay_bps`, `decisiveness_penalty_bps`,
the four ceasefire constants and all three thresholds: without them the claim "every input is
visible in the row" would be false and the checks would silently depend on the running build's
constants. **If a future validator needs a constant not listed here, it must either be added to the
row or the check must move to reconciliation — no third option.**

Row self-validators (7), each rederiving only from the row's own stored fields, using §7's
opening/closing names exactly: position identity; exhaustion-gain identity from `opening_intensity`;
closing-exhaustion identity; `raw_closing_intensity_bps` identity from `opening_intensity_bps` and `closing_avg_exhaustion`;
**the floor clamp** — `active_intensity_floor_applied` equals
`closing_status is ACTIVE and raw_closing_intensity_bps < minimum_active_intensity_bps`, and
`closing_intensity_bps` equals `max(minimum_active_intensity_bps, raw_closing_intensity_bps)` when
`ACTIVE` and `raw_closing_intensity_bps` otherwise — both clamps rederived at their exact
boundaries;
closing-readiness identity from `closing_avg_exhaustion` and `closing_position`; terminal-gate
correctness against the stored thresholds and `termination_draw`; `resolved_turn` present iff
`closing_status` is terminal.

Report self-validators (3): canonical `conflict_id` ordering; duplicate rejection; the outbreak
row, when it reports `occurred`, names a conflict whose `opened_turn` equals this turn.

**`TurnReport` cross-validators: ZERO.** A `TurnReport` validator cannot see `WorldState`, so the
membership question belongs to reconciliation (group 47). W1 has no genuinely cross-*report*
question and therefore adds no `TurnReport` validator.

## 12. Reconciliation groups (R13, C8)

| # | Group | Proves |
|---|---|---|
| **46** | Conflict state vs both states, **two exclusive sources** | See below |
| **47** | Membership and eligibility | Report conflict ids ⊆ world conflicts; **candidate eligibility** matches the opening state's authored dyads (state-dependent, cannot be self-validated); nothing appeared without a validated outbreak; nothing vanished |
| **48** | **RNG redraw** | Each stream redrawn from `(opening_state.seed, opening_state.turn, stream)` and compared: **occurrence**, **weighted candidate selection**, **progress jitter**, **settlement/ceasefire draw**. This is what makes save/reload-rerolling a detected tamper |
| **49** | Authored staticness | `foreign_profiles` (every key and value) **and** every `ConflictDyadState` unchanged between opening and closing state |
| **50** | Capability provenance | Each row's `opening_war_capability_a/b_bps` equals `opening_state.foreign_profiles[...]`, so a row cannot fabricate capability to justify a position it did not earn |
| **52** | **Both floors** | Every closing `ACTIVE` conflict has `intensity_bps >= MIN_ACTIVE_INTENSITY_BPS`; every `CEASEFIRE → ACTIVE` breakdown restarts at or above the floor; **no outbreak occurred from a dyad whose `raw_dyad_weight_bps` was below `MIN_OUTBREAK_WEIGHT_BPS`**; and the candidate set is unchanged under a re-ordered `foreign_profiles` mapping (order independence, §6.1) |
| **51** | Security-exposure effect, **post-slot-8** | The legitimacy security contribution is rederived from `opening_state`'s authored `player_security_exposure_bps` and the **closing (post-slot-8)** intensity of each conflict **still `ACTIVE`**, summed and capped **once**; it is never positive; it is exactly zero where exposure is zero |

**Group 46 — the two exclusive sources (C8).** A conflict created by a slot-7 outbreak did **not**
exist in the turn-opening state, so a blanket "row opening values equal `opening_state`" rule is
wrong. Every progression row must match **exactly one** of:

1. **Existing conflict** — the row's opening values equal that conflict in the **turn-opening
   state**.
2. **New conflict** — the row's opening values equal the **validated outbreak-row initialization**
   for this same turn and `conflict_id`.

Neither source, or both, is a reconciliation failure. No conflict may appear, disappear or mutate
without exactly one validated path. Every conflict not named by a row must be byte-identical across
the two states.

**Tamper matrix — 16 cases**, each asserting a green hash chain **and** a specific semantic problem:
tampered opening/closing position; tampered component; tampered stored constant; tampered status
transition; deleted row; fabricated conflict; fabricated outbreak occurrence; **tampered occurrence
draw**; **tampered selection draw**; **tampered progress jitter**; **tampered termination draw**
(all four via group 48); tampered capability (group 50); tampered `foreign_profiles` entry and
tampered dyad (group 49); non-canonical ordering; fabricated exposure effect (group 51); **removing
the active-intensity floor from a closing `ACTIVE` row**; **fabricating a larger
`minimum_active_intensity_bps` to justify an intensity the formula did not produce**; **returning
from ceasefire below the floor**; **allowing a weight-499 dyad to generate a war**; **excluding a
weight-500 dyad from the candidate set** (all five via group 52).

## 13. Reason IDs

`foreign_conflict_outbreak`, `foreign_conflict_progressed`, `foreign_conflict_ceasefire_entered`,
`foreign_conflict_ceasefire_broke_down`, `foreign_conflict_terminated`,
`foreign_security_anxiety_applied`. Each needs `_SAMPLE_PARAMS`, a renderer, a missing-params
fallback test and a real-resolver emission test (`cli.py:456-463`). Params are ids, enums and
integers — never prose. A zero component emits nothing.

## 14. Backend contract surface — no frontend work in W1 (C10)

**W1 contains:** state, conflict resolution, reports, reconciliation, history, tamper detection,
ruleset compatibility, CLI observation, and backend stochastic-channel exclusion metadata where the
existing contract requires new RNG channels to be declared.

`ForeignAffairsReport.excluded_stochastic_channels` names the three new streams
(`foreign_conflict_outbreak`, `foreign_conflict_progress:{cid}`,
`foreign_conflict_termination:{cid}`). Preview remains RNG-free and gains no new behaviour.

CLI observation only: `inspect --conflicts`, plus the turn-report block wired into **both**
`_print_report` (`cli.py:894-921`) **and** `_cmd_history`'s inline list (`cli.py:997-1026`) — the
Phase 3A dual-wiring trap — each with its own independent test.

**Moved entirely to W5 — not built, not stubbed, not previewed in W1:** React work of any kind;
Dashboard conflict alerts; conflict cards; `ConsequencesPanel` rendering changes; world-map
presentation; server-authored frontend labels and any visual treatment.

**The existing frontend verification runs unchanged and must stay green.** W1 adds no frontend file,
no projection field consumed by React, and no OpenAPI change driven by presentation.

## 15. Save/ruleset and scenarios

Ruleset **0.13.0**; save format **1**. **No migration** — a 0.12.0 save has no dyads; synthesising a
peaceful world would assert a fact the save does not contain. Commit 1 freezes
`phase4a_save_ruleset_0.12.0.json` from the unmodified build, and
`UnsupportedRulesetVersionError` is proven to raise *before* payload parsing.

**Scenarios — final counts (C3).** `tiny_valid` retains `neighbor` unchanged and adds **two**
foreign profiles (Kessia, Vetruska); `decree_state` retains `neighbor` unchanged and adds **two**
(Marnil, Sorrend); `deficit_demo` adds **two** (Marnil, Tolvane). Each scenario carries **exactly
one eligible dyad** — three across the whole catalog, never three per scenario. No `neighbor` dyad
exists or is eligible. A test proves each scenario's diff is the
foreign blocks plus `content_version` and nothing else. **No Phase 2 economic value is touched.**

## 16. W1 commit sequence (C11) — not executed

**The frozen-plan commit comes first. No schema, scenario, fixture or production-code change may
precede it.**

1. **Freeze this finally approved plan** as an isolated repository commit; push immediately; verify
   local HEAD equals the remote branch HEAD.
2. **Freeze the authentic `0.12.0` save fixture**, generated by the unmodified current build,
   isolated commit.
3. `simulation/foreign_conflict.py` + `test_foreign_conflict.py` **+ the neutrality-scan extension
   naming the module specifically**, same commit.
4. Core strict types and the §10.1 constants.
5. **Atomic:** state models (`foreign_profiles`, dyads, conflicts) + invariants + all three
   scenarios' authored content + ruleset bump `0.12.0 → 0.13.0` + exclusion ledger + conftest
   defaults.
6. **Report + phase wiring together by necessity** (slots 7/8/10/15). Completeness test extends to
   8,190 cases. Soaks measured before and after.
7. Reconciliation groups 46–51.
8. The 16-case tamper matrix.
9. Calibration tests transcribing §10's measured literals, declared seeds.
10. CLI `inspect --conflicts` and the dual-wired report block.
11. Docs + **ADR 0016** + roadmap.

Each commit individually gated (`ruff format`, `ruff check`, `mypy`, affected tests); full suite
green from 5 onward; pushed immediately on green.

---

# 17. W2–W5 — nonbinding architectural outline (R2)

**Nothing here is approved by approving this document.** Each gate gets its own repository audit and
its own detailed, calibrated plan, written only after its predecessor ships. Formulas, constants,
state fields and validators below are direction, not design.

### W2 — Explicit neutrality, mediation, humanitarian aid
Introduces `PlayerConflictEngagementState` (R7): a **structured** record replacing any single stance
enum, able to represent simultaneously — declared neutrality; mediation status; humanitarian
commitment; **sanctions with an explicit target**; **military aid with an explicit target**; **the
side joined**; withdrawal status; accumulated partiality; recurring commitments. **No engagement is
ever stored without identifying the affected side.** Coexistence rules (aid alongside mediation;
persistent sanctions alongside another action) are W2's to specify.
Decisions: `ForeignEngagementDecision` with a **discriminated `ConflictEngagement` union** (stable
action kinds, canonical ordering, transition rules) in its **own** at-most-one slot — never the
policy-proposal slot.
Requires the R9 comparison of a **minimal** authored foreign-policy preference set
(humanitarianism / interventionism / multilateralism), derived from neither government role nor
constitution.
Requires the R10 decision: authored baseline + mutable current relationship **with an explicit decay
rule**, or a separate canonical `DiplomaticRelationState` — **must not reproduce the Phase 3B2A
ratchet**. W2's plan states which gate introduces mutation and which report/reconciliation layer
explains every change.
Requires R11: money flows through the **real accounting architecture** — ledger category, report
ownership, reconciliation identity, recurring-commitment timing, affordability, cancellation, debt
and cash consequences, and **what happens when an affordable recurring commitment becomes
unaffordable**. **No direct `model_copy` treasury subtraction.**
Effort cost: **political capital** (resolved recommendation #5); diplomatic standing and
relationships determine **effectiveness**. **No second spendable currency.**

### W3 — Trade exposure and sanctions
Builds the channel `state.py:200-201` explicitly deferred. Sanctions must hurt **both** target and
imposer through that real channel. Precedes W4 (resolved recommendation #4).

### W4 — Military capability, war powers, joining, withdrawal
`MilitaryState`, structurally separate from `InstitutionState(id="military")`, with a test proving
coup inputs unchanged. A `war_powers` constitutional axis requiring (R12) **constitutional coherence
rules**: `LEGISLATIVE_APPROVAL` and `LEGISLATIVE_SUPERMAJORITY` are **invalid when no legislature
exists**; amendment targeting and canonical ordering; Gate 4A3A constitutional policy-card updates;
OpenAPI and frontend contract changes. **No hidden relationship between government form and war
authority.**
**R12 binding:** apportionment and majority-threshold primitives may be reused; **amendment support
scoring may not.** A dedicated war-authorization support formula is required, using authored
foreign-policy preferences, government relationship, discipline and influence.
**R8 binding:** W4 must resolve whether joining is one decision or a two-turn
authorize-then-join sequence; specify failed-vote capital consumption and atomic rejection; and give
joining a **dedicated `WarAuthorizationDecision`** if it occupies the policy-proposal slot — placing
`join` inside the ordinary engagement decision would not enforce the existing budget/amendment
mutual exclusion. Withdrawal requiring approval follows the same slot logic; it cannot be both
"per axis" and always in its own unrestricted slot.
**R14 binding — no universal terminal outcomes.** Brokering one settlement does **not** win the
campaign; losing one intervention does **not** remove the government. Mediation success becomes an
achievement / score contribution / scenario-authored objective. Military defeat damages capability,
money, legitimacy and political survival **through existing channels**. Terminal war defeat stays
deferred until invasion, occupation or sovereign collapse is genuinely modelled. A future scenario
may define peacemaking as its own victory condition; it is not a universal `VictoryReason`.

### W5 — Frontend and world map
Foreign Affairs screen; conflict cards reusing `PolicyCardView`'s accessible structure; selection
never auto-previews or spends; map tinting only after W1–W4 give it something true to show.

### Expansion scope, unchanged
Tactical units, cities, occupation, supply lines, refugees, borders, alliance organizations and
nuclear war remain expansion scope (resolved recommendation #7). Hooks stay additive-only; nothing
is stubbed empty.

---

## 18. Decision status

### 18.1 Resolved — all four W1 decisions are now closed

| # | Decision | Outcome |
|---|---|---|
| 1 | `FROZEN` status | **APPROVED: removed** (§8.4). Stalemate = long-running `ACTIVE`. No unreachable status kept for narrative variety |
| 2 | `OUTBREAK_SCALE_BPS` | **APPROVED: 700**, unchanged. Measured against the final authored content (§10.2): **0.87** conflicts per 40-turn run with **2 of 15** quiet runs; **1.07** per 80-turn run with **0 of 15** quiet |
| 3 | Completeness at 13 reports | **APPROVED: keep exhaustive**, convert at report 14 (§2). Clarified: 64.5% is a **case-count** share; the **runtime** share is **2.66%** |
| 4 | Player exposure | **APPROVED: explicit authored security exposure** (§9). One border-adjacent dyad per scenario nonzero, remote dyads 0, never inferred from an id, security channel only, economic exposure zero until W3 |

Decision 4 additionally forced two design corrections found while implementing it faithfully:
**approval is authored-and-static so W1 does not touch it** (§9.3 Finding A), and **the draft
anxiety formula was mis-scaled by ~10×** and is now measured-and-sized (§9.5).

### 18.2 Genuinely open

**None blocking W1.** Two items are scheduled rather than open:

1. **The `resolve_legitimacy` signature change** (§9.3 Finding B) touches a shipped, self-validated
   formula — its report field, self-validator and reconciliation group all change in commit 5. Not a
   decision, but the largest single piece of W1 risk, and called out so it is not discovered late.
2. **W2–W5 remain nonbinding** (§17). Each gets its own repository audit and calibrated plan after
   its predecessor ships. Approving this document approves **W1 only**.

## 19. Confirmation

The only repository mutation was the authorized R1 recovery (`git fetch`, `git merge --ff-only`),
which fast-forwarded `5915a6f → c47fc82`. **No repository file was edited; nothing was committed,
pushed, merged or opened as a PR; no dependency was installed.** Working tree clean at `c47fc82`.
Calibration ran from `scratchpad/w1_calibration_driver.py`, outside the repository, which only
imports and calls existing backend code. No Docker container was started. Every figure in §10 is
measured output from that driver against the real engine, with seeds declared before the first run.
