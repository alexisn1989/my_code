# ADR 0016: External wars — foreign actors and persistent conflicts — Gate W1

- Status: accepted
- Date: 2026-08-30

## Context

Every phase through 4A3A modelled one country in isolation. The world outside the player's borders
existed only as `neighbor`, an ordinary `CountryState` no formula treated as foreign, and as
scenario prose. Nothing outside the player's own government could happen, persist, or matter.

Gate W1 makes foreign wars real: authored foreign actors, authored bilateral quarrels, and wars that
break out, escalate, exhaust themselves, pause in ceasefires and end — all on their own schedule,
driven by seeded randomness the player never touches.

W1 is deliberately **observe-only**. The player can see these wars and feel one domestic
consequence (security anxiety), and can do nothing else about them. That is not an unfinished
edge: player diplomacy, trade exposure and military intervention each need systems that do not
exist yet (a mutable relationship model, a trade channel, military capability and war powers), and
each is scoped to its own audited gate. Shipping a "Join war" button with no army, no legal
authority and no cost model would be a lie in the interface.

The frozen plan is `docs/plans/external-wars-w1-implementation-plan.md`
(SHA-256 `2ceb9a7b33512a45f6d756d3a1698c724495475d374f3d339814fef1040c82e0`), unchanged throughout.
Its §10 calibration measurements are **superseded** by
`docs/plans/external-wars-w1-calibration-erratum.md`; the erratum corrects measurement, never the
plan text.

## Decisions

### Foreign actors are their own namespace, not fabricated countries

`WorldState.foreign_profiles: dict[str, ForeignProfileState]` is a separate authoritative namespace.
`ForeignProfileState` carries exactly two fields: `display_name` and an abstract
`war_capability_bps`.

Foreign actors are deliberately **not** `CountryState` objects. `CountryState` requires `population`
and `treasury` with no defaults, so modelling Kessia that way would force inventing demographic and
fiscal data no scenario has any business authoring for a country the player never governs. A foreign
profile therefore has no population, treasury, economy, politics, institutions or military
simulation — none of it is needed to fight an abstract war, and all of it would be fiction presented
as fact.

Foreign-profile keys are disjoint from every `WorldState.countries` id, enforced by the
`foreign_profile_id_collides_with_country` invariant. `neighbor` remains an ordinary `CountryState`
and is never dyad-eligible: no dyad names it, and none can, because dyad members resolve only
through `foreign_profiles`.

`belligerence_bps` and `alignment_bps` were specified in an early draft and **excluded**: nothing
read them. Decorative state that no formula consumes is a promise the engine does not keep.

### `war_capability_bps` is foreign-conflict capability only

It feeds `simulation.foreign_conflict` and nothing else. It is structurally separate from the
player's future `MilitaryState` (W4), from `InstitutionState(id="military")`, and from every
coup, unrest, impeachment, election, legislative and constitutional formula. An AST/source scan
(`tests/test_foreign_conflict.py`, `tests/test_legislative_neutrality.py`) enforces this by naming
the module specifically, so a foreign country's army can never quietly become a domestic
coup input.

### Dyads are authored quarrels; ordering and roles are independent

`ConflictDyadState` is an explicitly authored bilateral relationship. Generic per-actor belligerence
never causes a war on its own — only a specific authored pair with a specific quarrel can fight.

`country_a`/`country_b` are canonical: `country_a < country_b` lexicographically. That ordering
exists solely to make the pair's identity and serialization stable and carries **no** role meaning.
`aggressor`/`defender` are separate explicit authored fields, validated to be distinct and to match
the pair, and are never inferred from canonical position. All three shipped dyads happen to store
`country_b` as aggressor — the code never relies on that pattern, and a dedicated test authors the
opposite arrangement to prove ordering and role are genuinely independent.

Non-canonical tuple ordering is **rejected, never silently normalized** — matching every other
ordered collection in `state.py`. Mapping insertion order, by contrast, is semantically irrelevant:
an earlier draft's dictionary-order invariant was removed because it asserted something that does
not matter, while canonical tuple ordering — which does — remains enforced.

### Outbreak: at most one war per turn, from authored candidates only

At most one outbreak may occur per turn. A dyad is a candidate only when it is authored, `eligible`,
has no `ACTIVE`/`CEASEFIRE` conflict already running for that pair, and capacity is available.

`MIN_OUTBREAK_WEIGHT_BPS` is 500, giving three distinct authored meanings: `eligible: false` (the
pair cannot fight at all), eligible below 500 (they could fight, but present tension is too low),
and eligible at or above 500 (they participate in selection). Weight 499 is excluded and weight 500
included, both measured at the exact boundary.

Candidate weights may legitimately sum above 10,000. Only the outbreak *probability* is clamped;
weighted selection uses the full uncapped total, so a third eligible dyad cannot silently dilute
away because the sum saturated.

`MAX_CONCURRENT_CONFLICTS` is 2. `ACTIVE` and `CEASEFIRE` consume capacity; `SETTLED` and `DECIDED`
are permanent history and consume none, so a terminal war never blocks a future one.

### Randomness is namespaced, and observation cannot reroll it

Three new streams, declared in `ForeignAffairsReport.excluded_stochastic_channels`:
`foreign_conflict_outbreak`, `foreign_conflict_progress:{cid}`, and
`foreign_conflict_termination:{cid}`. Each is derived through `derive_rng(seed, turn, stream)`, so
a conflict's draws are independent of every other conflict's and of the eight pre-existing streams.

Saving, loading, previewing and inspecting a save cannot change any outcome. Preview stays RNG-free
and gained no behaviour; `inspect --conflicts` resolves nothing and consumes nothing.

### The player is uninvolved by absence, not by an enum

There is no `PlayerStance` enum and no foreign-policy decision in W1. The player's non-involvement
is represented by the absence of any engagement record — the honest encoding of "this is not your
war", and the one that does not have to be migrated when W2's neutrality and W4's intervention each
need their own targeted, coexisting records rather than one overloaded mode field.

### Security anxiety is the only domestic consequence

`player_security_exposure_bps` is authored per dyad. **No adjacency is inferred** from a country id,
a display name or any derived signal — exposure is content, and adjacency remains authoring
rationale only. Economic exposure is deliberately not modelled and is zero in W1; it arrives when
W3 builds a real trade channel.

Raw per-conflict contributions are summed first and the ±`MAX_SECURITY_CONTRIBUTION_BPS` cap is
applied **once** to the aggregate, not per conflict. The contribution is negative-only. A
zero-exposure dyad produces exactly zero effect, structurally.

### The thirteenth domain report, and what validates it

`ForeignAffairsReport` completes the thirteen-report set. The all-present-or-all-absent completeness
rule now rejects all **8,190** proper nonempty subsets; the all-thirteen-absent case remains valid,
which is why the `-k thirteen` selection reports 8,191 passing cases.

Reconciliation groups **46–52** connect the report to opening state, closing state, authored
content, capabilities, RNG streams, security exposure, and both floors. The tamper matrix —
historically named "16-case" in the frozen plan, which then enumerates 21 — implements all **21**
cases, each proving a green hash chain after consistent downstream rehashing *and* a specific,
correctly-attributed semantic problem.

### CLI observation

`inspect --state <save-path> --conflicts` is read-only and deterministic: it loads through the
authoritative save loader, runs the existing version and history validation, resolves no turn,
consumes no RNG, and writes nothing. It shows live (`ACTIVE`/`CEASEFIRE`) and concluded
(`SETTLED`/`DECIDED`) conflicts separately, with explicit stored roles, authored aims, current
values and the originating dyad's authored exposure. It offers no player action, because none
exists. The turn-report block is wired into both `_print_report` and `_cmd_history` from one shared
helper.

## Final selected constants

| Constant | Final value |
|---|---:|
| `MIN_OUTBREAK_WEIGHT_BPS` | 500 |
| `MIN_ACTIVE_INTENSITY_BPS` | 250 |
| `CEASEFIRE_RECOVERY_BPS` | 200 |
| `CEASEFIRE_BREAKDOWN_BPS` | 4,500 |
| `CEASEFIRE_DURABILITY_TURNS` | 3 |
| `MAX_CONCURRENT_CONFLICTS` | 2 |

Complete tables live in `docs/plans/external-wars-w1-calibration-erratum.md`. In summary:

- Production-native horizons are turns **0–39** and **0–79** (the original driver measured 1–H
  against a turn-keyed RNG, shifting every draw).
- A continuous floor run resets on **every** non-`ACTIVE`-at-floor closing state, ceasefires
  included; the original counter concatenated episodes across them.
- A `CEASEFIRE` still open at the final horizon turn is **right-censored**, not automatically
  indefinite; the original criterion counted the horizon snapshot and misclassified it.
- Honest grid result: **27 of 240** configurations pass, and the frozen plan's own unmodified
  selection rules choose **`(250, 200, 4,500, 3)`**.
- **Zero** honest indefinite-ceasefire violations occur across all 240 cells — the mechanic bounds
  a continuous run by `CEASEFIRE_DURABILITY_TURNS` by construction.
- At-floor exhaustion gain moved from 60 to **30** bps/turn (it scales with the floor), and the
  deterministic liveness witness from ≤30 to **≤35** turns, with every anti-absorbing and
  eventual-progress property intact.

## Scenario content

| Scenario | Dyad | Capabilities A/B | Tension | Grievance | Aims A/B | Exposure |
|---|---|---:|---:|---:|---|---:|
| `tiny_valid` | `kessia` / `vetruska` | 5,000 / 5,600 | 8,500 | 7,500 | `DETERRENCE` / `TERRITORIAL` | 2,000 |
| `decree_state` | `marnil` / `sorrend` | 5,800 / 6,400 | 9,500 | 8,500 | `DETERRENCE` / `REGIME_CHANGE` | 3,000 |
| `deficit_demo` | `marnil` / `tolvane` | 5,800 / 6,400 | 9,000 | 7,000 | `DETERRENCE` / `RESOURCE_ACCESS` | 2,000 |

Each scenario carries exactly one eligible dyad — three across the whole catalog, never three per
scenario. All three store `country_b` as aggressor and `country_a` as defender; as above, no code
infers roles from that content pattern.

## Consequences

Advantages:

- The world does something on its own, deterministically, whether or not the player acts.
- Save/reload is stable: reloading mid-campaign cannot reroll an outbreak, a progression or a
  termination.
- Every conflict figure in a report is validated against state and re-derivable from stored inputs.
- Tampering is caught even after a knowledgeable edit re-links and re-hashes the whole downstream
  chain.
- Causal links are authored and explicit — exposure, eligibility and roles are content, not
  inference.
- CLI inspection is stable and honest about what it does not model.
- The architecture is additive: W2–W5 attach to it without rewriting it.

Limitations, stated plainly:

- The player cannot respond to a foreign war in any way.
- No diplomacy and no mutable foreign relationships — tension and grievance are authored constants
  that no formula changes.
- No trade exposure, sanctions, humanitarian aid or military aid.
- No war authorization, no player armed forces, no troop movement, no tactical battles.
- No occupation, annexation, colonies, insurgency, alliances, proxy wars or separatist recognition.
- No world map and no React presentation of any of this.
- No universal victory or defeat follows from one foreign war.

## Alternatives rejected

- **Foreign actors as full `CountryState` entries.** Would have forced fabricated population,
  treasury and economy for countries the player never governs, and invited domestic formulas to
  read them.
- **Inferring adjacency or roles from ids or names.** Exposure and aggressor/defender are authored
  precisely so a rename cannot silently change the simulation.
- **Player alignment as a cause of bilateral foreign war.** Two foreign countries fight over their
  own quarrel; making the player's disposition the cause would be a self-centred world model.
- **A one-turn random event instead of persistent state.** Gives no war to observe, no duration, no
  ceasefire, and nothing to reconcile.
- **A "Join war" button without military capability or legal authority.** An interface promise the
  engine cannot keep.
- **One `PlayerStance` enum reused for every future action.** Neutrality, mediation, sanctions and
  intervention are targeted and can coexist; a single mode field would have to be migrated apart
  again in W2 and W4.
- **Direct treasury subtraction outside finance accounting.** Any future cost must route through the
  existing accounting path, not poke the treasury.
- **Treating a horizon-ending ceasefire as proof of an indefinite loop.** This was the actual
  measurement defect; the honest criterion measures one uninterrupted episode against durability.
- **Retaining an unreachable `FROZEN` status.** Measurement proved it unreachable under every swept
  constant; a stalemate is a long-running `ACTIVE` conflict.
- **Making one settlement a universal campaign victory, or one foreign defeat an automatic loss.**
  Neither is the player's war.

## Expansion boundary

Each remains **nonbinding** and requires a fresh repository audit and its own implementation-ready
plan after its predecessor ships:

- **W2** — explicit neutrality and mediation.
- **W3** — trade exposure and sanctions.
- **W4** — military capability, war authorization, joining and withdrawal.
- **W5** — frontend and world-map presentation.

The larger military design — troop movement, army/navy/air force, military industry, arms markets,
proxy wars, alliances, occupation, annexation, colonies, insurgency and separatist recognition —
remains later design scope. Nothing in W1's state implies it is planned, scheduled or approved.
