# Military Movement Vertical Slice — Revision 3e implementation plan

**Supersedes Revision 3d**, SHA-256 `43dde2c8766db433009a1363a0d7b0831c3c6b71449e17f76538da541cc3189a`,
which superseded 3c (`079ce4cd…8c24`), 3b (`5d773126…9a2e`), 3a (`0043e5bf…bd05`), 3
(`ecc296fb…0014`) and 2 (`03dc36f0…fda7`). All withdrawn.

Revision 3e is a **micro-correction** (E1–E2, §13.6). D1–D5 are preserved exactly and no settled
decision is reopened. It stops the CLI printing an applied movement twice, and removes three stale
contract statements Revision 3d inherited from 3c.

Revision 3 incorporated corrections C1–C13 into its own prose but left **live remnants elsewhere in
the document that contradicted them** — chiefly in §12's test matrix, which was not re-read when the
corrections were applied. Revision 3a removes those remnants (F1–F8, §13.2) so the plan no longer
disagrees with itself.

**Status: PROPOSAL — NOT FROZEN, NOT IMPLEMENTED.** Lives outside the repository. Nothing in the
repository was changed to produce it.

Audit basis: `cf738ad7372f44181447f81a004ab79d136c48a1` on
`claude/phase-4a-graphical-vertical-slice`, ruleset `0.14.0`, save format `1`. Every claim below
was re-verified against that commit's working tree; citations are `path:line`.

---

## 0. What this slice is, honestly

It is **real**: real authored state, real turn orders, real resolution through the production
resolver, real persistence in the save chain, real reporting, real reconciliation, and a real
accessible UI.

It is **not** combat, and not strategically meaningful deployment. **A formation's location feeds
no other formula in this slice.** It does not touch combat, coup risk, economics, foreign
conflicts, occupation or territorial control. Moving a formation changes where an icon is drawn,
what the theater list says, and what the save records — and nothing else in the simulation.

### 0.1 Movement is free — decided, not open

Movement carries **no resource cost of any kind**. This is a closed decision, not an open question,
and nothing in this plan or the UI may present it as unresolved. Precisely, a confirmed movement:

- **Deducts no money.** No treasury field is read or written.
- **Deducts no political capital.** No political-capital field is read or written.
- **Changes no readiness or supply value.** No such field exists in this slice (§6).
- **Has no hidden opportunity cost.** No other decision becomes unavailable, more expensive or
  differently scored because a movement order was submitted.

The one real constraint is structural, not economic: the slice accepts a **maximum of one movement
order per turn** (product decision 13, enforced at §2.3). That is a cap on how much may be ordered,
not a price paid for ordering it, and it must never be described as a financial or political cost.

The order-review UI states exactly `Cost: None in this infrastructure slice`.

That limitation is deliberate and must stay prominent in the plan, the ADR, the roadmap and the
player-facing UI copy. Its purpose is to build a trustworthy end-to-end foundation — state,
orders, resolution, persistence, reporting, interaction — that a later authorized slice can make
strategically meaningful *before* Navy, Air Force or combat are added. It must not be described as
a military system.

---

## 1. Military state ownership

### 1.1 Recommendation: nest under `CountryState`

```
CountryState
└── military: MilitaryState | None = None
    └── formations: dict[StrictFormationId, FormationState]
```

This is the ruling's preferred shape, and the real models support it. Ownership is established by
the containing country; no `owner` field is duplicated inside a formation, matching the
established rule that a container's identity is not restated in its members.

### 1.2 Required explanations

**Are all player-controlled countries `CountryState`?** Yes. `WorldState.countries:
dict[str, CountryState]` (`app/simulation/state.py:1382`) and `player_country_id: str`
(`state.py:1383`); the player is resolved as `state.world.countries[state.world.player_country_id]`
(`app/simulation/invariants.py:1270`). `ForeignProfileState` is deliberately *not* a
`CountryState` (`state.py:993-1011`), so nesting under `CountryState` reaches exactly the countries
that can own formations and no others.

**Required or optional after the bump?** **Optional on the model, required for the player by
invariant** — the established pattern for every country sub-model. `finance`, `economy` and
`politics` are each `X | None = None` (`state.py:984-986`) with `player_finance_required`,
`player_economy_required`, `player_politics_required` (`invariants.py:1274`, `:1285`, `:1296`)
making them mandatory for the player only. A required-on-the-model `military` would force every
future AI country to author one.

New invariant code: **`player_military_state_required`**. Deliberately *not*
`player_military_required` — `player_military_institution_required` already exists
(`invariants.py:1307`) for the coup-risk institution row, and two codes a reader could confuse
would be worse than a longer name.

**How is the containing country proven to own the formation's location?** By a new invariant that
resolves the formation's `location_theater_id` in `world.strategic_map.theaters` and requires that
theater's owner to be a `PlayerCountryRef` whose `country_id` equals the containing country's key.
This composes with M0's existing rules rather than restating them: `map_player_ref_not_player`
already guarantees any `PlayerCountryRef` in the map equals `world.player_country_id`
(frozen plan §9.1), so the check reduces to "the theater is player-owned" plus "this country is the
player". Codes: `formation_location_unknown_theater`, `formation_location_not_owned_by_country`.

**How are empty military states represented?** `MilitaryState(formations={})` — a present state
with no formations. That is distinct from `military=None`, which means "this country has no
military dimension modelled at all". The player must have the former after the bump; an AI country
may have the latter. Making an empty dict the only representation would erase that distinction.

**Why keep formations out of `strategic_map`?** Because
`reconcile_strategic_map_staticness` (`app/simulation/reconciliation.py:3100`, Group 53) compares
`canonical_dumps` of the opening and closing map and fails on any byte difference: "no phase may
write it" (`reconciliation.py:3143-3145`). A formation position inside the map would break
reconciliation the first time anything moved. Keeping them separate preserves Group 53 intact as
the guarantee that *geography* never changes, while Group 54 (§7) separately guarantees that
*positions* change only through accepted orders. Two guarantees, neither weakened.

**How does this evolve without pretending `ForeignProfileState` is a country?** It does not touch
foreign profiles at all. When foreign forces eventually exist, the honest options are a separate
`ForeignProfileState.military` field of a *different* type carrying only what an abstract actor can
truthfully have, or a promotion of specific foreign actors to `CountryState` under their own
mandate. Nesting under `CountryState` today forecloses neither and fabricates neither.

### 1.3 One inconsistency to note, not to copy

`CountryState.id` (`state.py:978`) duplicates its own `WorldState.countries` key. That predates the
M0 rule and is not being changed here. `FormationState` follows the **newer** precedent —
`ForeignProfileState` (`state.py:1008-1010`) and `TheaterState` — and does not carry its own id.

---

## 2. Decision shape

### 2.1 Discriminator: `military_movement`

**Recommended over `formation_movement`**, on extension grounds rather than alphabetical ones.
The union member is the *player's military instruction for the turn*; later slices will add naval
transit and air sorties, which are also formation movements but are not interchangeable with land
redeployment. `military_movement` can grow order variants inside itself; `formation_movement`
would either become a lie (an air sortie is not the same operation) or force sibling kinds
`formation_naval_movement`, `formation_air_movement`, splitting one player intention across three
union members and three one-per-kind validators.

Canonical kind order is ascending by `kind` (`app/simulation/decisions.py:477`). Current kinds:
`bloc_relationship_investment`, `budget`, `constitutional_amendment`. `military_movement` sorts
last; no existing decision set's canonical order changes.

### 2.2 Models

```python
StrictFormationId: TypeAlias = Annotated[str, Field(strict=True, min_length=1, max_length=64)]
# A NEW identifier namespace, so it gets its own alias. Structurally identical to StrictMapId
# (app/simulation/geography.py:25) -- strict, 1..64, no charset constraint, so no separator may be
# assumed absent from an id.
#
# C5: theater ids reuse the EXISTING type. `StrictTheaterId` does not exist in production -- a
# repository-wide grep of app/ returns nothing. `StrictMapId` is the authoritative alias, verified
# at: theater dict keys (app/simulation/state.py:1315), route endpoints (state.py:1247-1248),
# capital_theater_id (state.py:1314), map_id (state.py:1313), shape_id (state.py:1271), and both
# owner refs (state.py:1176, :1189). Revision 2 invented a second, structurally identical alias;
# Revision 3 does not.

class FormationMovementOrder(BaseModel):
    model_config = _STRICT_CONFIG
    formation_id: StrictFormationId
    destination_theater_id: StrictMapId

class MilitaryMovementDecision(BaseModel):
    model_config = _STRICT_CONFIG
    kind: Literal["military_movement"] = "military_movement"
    orders: tuple[FormationMovementOrder, ...]
```

### 2.3 Shape-only validators (Pydantic, state-independent)

| Rule | Code |
|---|---|
| At least one order | `military_movement_orders_empty` |
| At most one order in ruleset 0.15.0 | `military_movement_too_many_orders` |
| Orders sorted ascending by `formation_id` | `military_movement_orders_not_canonical` |
| No duplicate `formation_id` | `military_movement_duplicate_formation` |

Canonical ordering is **rejected, not normalized**, matching `_decisions_are_in_canonical_kind_order`
(`decisions.py:477`) and its stated reason: the tuple is serialized into `decisions_json` and
hash-covered, so two semantically identical sets in different orders would digest differently.

"No duplicate or contradictory orders" reduces to the duplicate-`formation_id` rule: with one
destination per formation, two orders for the same formation *are* the contradiction, and two
orders for different formations cannot contradict each other in this slice.

The one-per-kind rule follows the existing pattern exactly — a new
`_at_most_one_military_movement_decision` validator counting members by type
(`decisions.py:423` is the model to copy), plus `DecisionSet.military_movement_decision()`
alongside the three existing accessors (`decisions.py:394-420`). **Never `decisions[0]`** — the
docstring at `decisions.py:394-406` explains why positional reads broke once the union grew.

### 2.4 Why the collection now, capped at one

The cap lives in a **validator**, not in the shape. Raising it in a later ruleset changes one
constant and one test matrix; it does not migrate a decision shape, re-issue a discriminator, or
invalidate saved `decisions_json`. Callers already iterate `orders`.

---

## 3. Reachability

A destination is valid **only when every condition holds**, and the conditions are evaluated in
**this exact order**, because the order is itself part of the contract (§3.4):

1. The formation resolves in the player country's `military.formations`.
2. The origin and destination theater ids both resolve in `strategic_map.theaters`.
3. Destination ≠ origin.
4. **Origin and destination are both owned by the formation's containing player country.**
5. A **directly authored outgoing** route row exists with `from_theater == origin` and
   `to_theater == destination`.
6. That route's `kind == RouteKind.LAND`.

Exactly one edge is traversed. **No BFS, no multi-hop, no undirected adjacency.** An
incoming-only route is not a valid outgoing route.

### 3.4 Ownership is checked before reachability, and that ordering is load-bearing

Condition 4 precedes conditions 5 and 6 deliberately. A foreign-owned destination therefore emits
the **ownership** error even when it also happens to lack a direct LAND route.

The reason is not tidiness. If a foreign theater that lacks a route were reported as "no route
from your territory", the explanation would imply that **authoring a route would authorize entry**
— which is false, and which would misrepresent a forbidden capability as a missing one. Foreign
entry is excluded by product decision, not by graph topology (§14). The player must never be able
to infer otherwise from an error message.

Concretely, in `tiny_valid`: `kessia_south` has an authored LAND route from `arken_north`, and
`vetruska_frontier` does not have one from any player theater. Both are nevertheless reported
identically as **foreign-owned**, never as unreachable.

### 3.1 Where this lives

A new pure helper in `app/simulation/geography.py`, beside `outgoing_and_incoming`
(`geography.py:136`), which is documented as "the SINGLE derivation of directed adjacency". That
function returns ids only and drops `kind`, so it cannot answer this question; the new helper is a
kind-aware sibling in the same module rather than a second adjacency derivation elsewhere:

```python
class KindedDirectedEdge(DirectedEdge, Protocol):
    """`DirectedEdge` plus the route kind. Extends the existing protocol rather than replacing it."""

    @property
    def kind(self) -> RouteKind: ...


def land_destinations_from(
    theater_id: StrictMapId,
    routes: Sequence[KindedDirectedEdge],
) -> tuple[StrictMapId, ...]:
    """Sorted destinations reachable by exactly ONE authored outgoing LAND route."""
    return tuple(sorted({
        r.to_theater for r in routes
        if r.from_theater == theater_id and r.kind == RouteKind.LAND
    }))
```

Three details of that signature are dictated by production, not chosen (F5):

- **`Sequence[...]`** matches the established precedent exactly: `outgoing_and_incoming` is declared
  `(theater_id: str, routes: Sequence[DirectedEdge])` (`geography.py:136-137`), with
  `from collections.abc import Sequence` already imported at `geography.py:11`.
- **A Protocol, never `RouteState`.** Revision 3 wrote `routes: tuple[RouteState, ...]`, which
  **cannot compile in this module**: `geography.py` is imported *by* `state.py`, and the
  `DirectedEdge` docstring says so outright — "it can never import `RouteState` back — not at
  runtime, and not under `TYPE_CHECKING` without inviting a cycle the next refactor trips over"
  (`geography.py:118-125`). `KindedDirectedEdge` extends that protocol; `RouteState` satisfies it
  structurally, and `RouteKind` is defined in this same module (`geography.py:82`), so no new import
  is needed.
- **`StrictMapId`, not raw `str`.** The existing helper predates the alias and uses bare `str`.
  `StrictMapId` is `Annotated[str, Field(...)]` (`geography.py:25`), so at a plain function boundary
  it is type-identical to `str` with no runtime behaviour change — it is strictly better
  documentation, and it keeps the new public helper consistent with every theater-id field in
  `state.py`. The older signature is left alone; this is not a licence to churn it.

### 3.2 Projection collapse is presentation only

`build_strategic_map` collapses a reciprocal pair into one `bidirectional=True` display row
(`app/api/projections.py:1071-1094`). **Legality is never decided from display rows.** The
projection's own per-theater `outgoing_theater_ids` / `incoming_theater_ids` keep both directions,
and the movement validator reads authored `RouteState` rows, never the collapsed display list. A
test asserts that a hypothetical one-way scenario yields different valid destinations from each
endpoint, so the two can never be conflated.

### 3.3 Consequence on shipped data

Every scenario's three player theaters form a star with the capital central, all edges reciprocal
`land`. One-edge movement therefore permits: capital ↔ either flank, and **not** flank → flank
(two hops). That is a real, explainable constraint, not a defect, and the UI must explain it
(§9.4).

---

## 4. Validation versus reporting — five distinct layers

| Layer | Question | Where | On failure |
|---|---|---|---|
| 1. Military facts | "Where is this formation, and which destinations are eligible?" | `GET /api/game/military`, built from the shared `classify_destinations` (§8.0) | none — it returns classified facts and stable reason codes |
| 2. Draft preview | "What would this order look like?" | `POST /api/game/preview` (`app/api/routes.py:470`) | returns explanation, changes nothing |
| 3. Submission validation | "Is this order legal against live state?" | `_validate_decision_set` (`app/simulation/resolver.py:48`) | **`DecisionSetError` → `TurnResolutionError`; the turn does not advance** |
| 4. Applied movement | "Move it." | resolver phase (§5) | cannot fail — layer 3 already proved legality |
| 5. Result reporting | "What moved?" | `MovementReport` | records applied transitions only |

Layer 1 answers what exists; layer 3 decides legality authoritatively. That division is not new
here — `DecisionOptionsProjection` already states it for its own (non-military) facts: "never
decides legality on submission — `/resolve`'s own validators still do, authoritatively"
(`projections.py:700-703`). It is cited as **precedent for the shape of the split only**;
`DecisionOptionsProjection` carries no military data and is not extended (§8.0).

**Invalid orders never reach a report.** I looked for a production precedent for reports carrying
rejected items and found none: the only "rejected" in `report.py` (`report.py:1471`) refers to a
rejected *design draft*, not a rejected input. A successfully resolved turn means every submitted
order was legal, so a `MovementReport` describing "accepted/rejected" rows would describe a state
that cannot occur.

### 4.1 Stable error codes

Shape errors (§2.3) are raised by Pydantic at `DecisionSet` construction. State-dependent errors are
raised by layer 3:

| Code | Condition |
|---|---|
| `formation_unknown` | no such formation in the player country's military state |
| `destination_theater_unknown` | destination is not a theater key |
| `destination_is_origin` | destination == the formation's current location |
| `destination_not_player_owned` | destination theater's owner is not the player country |
| `destination_not_directly_reachable` | destination **is** player-owned, and no authored outgoing **LAND** row origin → destination |

**Four codes Revision 2 listed are removed as unreachable (C4).** A stable player-facing error code
that no valid production state can produce is not a contract, it is decoration:

- `formation_origin_unresolved` and `origin_not_player_owned` — the two new invariants (§1.2)
  already guarantee that every formation's `location_theater_id` resolves and is owned by its
  containing player country. In a valid state these cannot arise from player input; they are
  **state-integrity failures**, and they remain as invariant problem codes
  (`formation_location_unknown_theater`, `formation_location_not_owned_by_country`), never as
  decision-validation codes.
- `route_kind_not_land` — `RouteKind` has exactly one member, `LAND`
  (`app/simulation/geography.py:82-85`), so a valid production `RouteState` cannot carry another
  value. A test forcing one through `model_construct` would prove the validator runs, not that a
  player can reach it. The LAND requirement is therefore folded into
  `destination_not_directly_reachable`, whose condition reads "no authored outgoing **LAND** row".
  When a future ruleset adds SEA or AIR kinds, a wrong-kind result becomes genuinely reachable and
  may be split out then.

**Rule for this slice: every stable player-facing error code must have a test that reaches it from a
valid production state** — never from `model_construct`, a hand-corrupted model, or a malformed
save.

The table is ordered by evaluation precedence (§3, §3.4). `destination_not_player_owned` is emitted
**before** reachability is examined, so `destination_not_directly_reachable` can only ever describe
a **player-owned** theater. A foreign-owned destination never produces it, whether or not a route to
it exists.

Layer 2 returns the same codes without raising, so the preview and the submission gate can never
disagree about *why* — both call the same classifier (§C3/§8.0), so there is only one legality
implementation to disagree with itself.

---

## 5. Resolver placement

### 5.1 Recommendation: extend `resolve_military_movement_and_combat`, movement first

Add a deterministic player-movement substep to the existing slot-8 phase, **before** W1
foreign-conflict progression. Rejected alternatives:

- **Slot 9 (`apply_casualties_occupation_disruption_war_costs`)** — rejected, as the ruling
  requires. It is `_noop` today, but its name promises casualties, occupation, disruption and war
  costs. Putting redeployment there would make the phase contract dishonest.
- **A newly named phase** — rejected for this slice. `PHASE_ORDER` is a fifteen-step contract whose
  ids are asserted verbatim (`tests/test_resolver.py:132` compares
  `report.dev.phase_statuses.keys()` to `PHASE_IDS`). A sixteenth id changes that contract and every
  save's dev metadata for a step that belongs, by name, in slot 8 already.
- **Splitting slot 8 into named substeps** — a reasonable future refactor, but it changes the same
  public `PHASE_IDS` contract. Deferred until there is a second reason to do it.

### 5.2 The five proofs the ruling requires

1. **Pre-existing behaviour unchanged when no movement is submitted.** The substep returns
   immediately when `DecisionSet.military_movement_decision()` is `None`, before reading or writing
   anything.

   Revision 2 claimed full `TurnReport` and full closing-state byte identity against pre-feature
   `0.14.0`. **That claim is impossible and is withdrawn (C7):** the ruleset adds required military
   state and a fourteenth report, so neither the whole state nor the whole report can be identical
   across the schema change. The honest, and still strong, baseline is:

   | Compared | Requirement |
   |---|---|
   | The thirteen pre-existing report subtrees | byte-identical |
   | Closing state **excluding** `countries[*].military` | byte-identical |
   | `countries[*].military` on a quiet turn | unchanged from opening |
   | `report.movement` on a quiet turn | present, `movements=()` |
   | Every pre-existing RNG stream | identical draws |
   | W1 foreign-conflict rows and outcomes | byte-identical |
   | `PHASE_IDS` and phase ordering | unchanged |

   **How the comparison is performed**, precisely, so "excluding" is a mechanism and not a promise:
   the `0.14.0` baseline is generated once by the unmodified engine and frozen as a fixture; the
   `0.15.0` run is dumped with `model_dump(mode="json")` and the new field removed by the same
   `exclude={"world": {"countries": ...}}`-style projection the existing presentation-neutrality
   test already uses (`backend/tests/test_map_presentation_neutrality.py` excludes
   `{"world": {"strategic_map"}}` for exactly this reason), plus `report.pop("movement")` before
   comparison. The removal is done by an explicit named helper with its own test proving it removes
   **only** those two paths, so a bug in the exclusion cannot quietly hide a real regression.
2. **RNG streams identical.** Strongest available evidence: **slot 8 consumes no RNG at all today**
   — I grepped `ctx.rng(` across the whole of `_resolve_foreign_conflict_progression`
   (`app/simulation/phases.py:2208-2265`) and the count is **0**. Movement is deterministic
   arithmetic and also draws nothing. Two non-drawing substeps cannot reorder any stream. And
   `derive_rng` namespaces on `(seed, turn, stream)` (`app/core/rng.py:36`), so even a future
   drawing substep with a fresh stream name cannot perturb an existing one. A test asserts every
   existing stream's first N draws are unchanged.
3. **Foreign-conflict progression keeps its ordering.** It stays the same call, in the same slot,
   after the movement substep. `PHASE_ORDER` and `PHASE_IDS` are unchanged — no id added, removed
   or reordered.
4. **No unrelated phase observes a partially applied movement.** The substep computes all
   destinations first, then applies them in one replacement of the player's `military.formations`
   mapping. No phase runs between computation and application, because both happen inside one
   handler call. Slots 1–7 ran before the phase and saw opening positions; slots 9–15 see final
   positions.
5. **The report is built at a semantically correct point.** Movement rows go into a
   `PhaseContext` scratch field, exactly as W1 does (`ctx.foreign_progression_rows`,
   `phases.py:519-521`); the `MovementReport` is assembled in slot 15 `generate_turn_report`
   alongside every other report. No phase builds its own final report object.

---

## 6. Formation state

```python
class FormationBranch(StrEnum):
    ARMY = "army"
    # No NAVY/AIR_FORCE. RouteKind has only LAND (geography.py:82-85) and TheaterKind only
    # LAND/COASTAL (geography.py:71-79), so an inert branch value would advertise reachability
    # the map cannot express -- the same reason M0 declined to declare SEA/AIR_REGION early.

class FormationState(BaseModel):
    model_config = _STRICT_CONFIG
    display_name: str
    branch: FormationBranch
    location_theater_id: StrictMapId
```

**Three fields, no more.** No readiness, strength, manpower, supply, commander, experience or
equipment: no mechanic in this slice reads any of them, and unread state is a promise the engine
does not keep (ADR 0016's own reason for excluding `belligerence_bps`).

**No status field.** A formation is either where it is or where its accepted order sent it;
movement completes at turn close (product decision 5), so there is no in-transit state to name.
Adding `status` now would mean a single-valued enum, which is not information.

**Canonical ordering:** `formations` is a `dict` keyed by `StrictFormationId`. Canonical JSON
already sorts mapping keys (`app/core/canonical_json`), so construction order is byte-irrelevant —
the same argument `WorldState.foreign_profiles` records (`state.py:1385-1388`). Every iteration
that can affect output uses `sorted(formations)`, and an insertion-order-independence test proves
it, mirroring `tests/test_map_insertion_order_independence.py`.

---

## 7. Report and reconciliation

### 7.1 `MovementReport` — applied transitions only

```python
class FormationMovementRow(BaseModel):
    model_config = _STRICT_CONFIG
    formation_id: StrictFormationId
    display_name: str
    branch: FormationBranch
    origin_theater_id: StrictMapId
    origin_theater_display_name: str
    destination_theater_id: StrictMapId
    destination_theater_display_name: str

class MovementReport(BaseModel):
    model_config = _STRICT_CONFIG
    movements: tuple[FormationMovementRow, ...] = ()   # canonical by formation_id
```

**Both theater display names are stored (D1).** Revision 3c carried only the two theater **ids**,
which contradicted its own promise to render "First Army of Arken moved from Arken Capital Region to
Northern March." — the row simply did not contain "Arken Capital Region" or "Northern March", so no
renderer could produce that sentence without resolving names from **current** state. That is exactly
what `display_name` was carried to avoid, and what `build_turn_result`'s own docstring forbids:
"Nothing is recomputed from current state — a historical turn renders from the report written when
it happened" (`app/api/projections.py:1138-1140`).

**The resolver snapshots both names** from the authoritative strategic map at the moment it applies
the order, alongside the ids.

The redundancy is deliberate:

- **ids** support reconciliation and machine-readable auditing;
- **display names** support stable standalone history rendering;
- **neither the frontend nor the CLI re-resolves a name from current state**;
- **raw ids never become fallback player-facing text.**

No status field: every row in this report is, by construction, an applied movement.

**Every successfully resolved turn emits a `MovementReport`.** A quiet turn emits
`MovementReport(movements=())`; a movement turn emits exactly one row in ruleset `0.15.0`.

Revision 2 said a quiet turn emits `movement=None` "exactly as `election` and `coup_unrest` do".
**That was wrong on both counts**, and the production code says so plainly.
`_all_thirteen_domain_reports_are_all_present_or_all_absent`
(`app/simulation/report.py:3964-3997`) rejects any report where `any(present) and not all(present)`,
and `election` and `coup_unrest` are *inside* that thirteen-field set — their outer fields are
**present** on quiet turns, and only their contents are empty. A resolved turn carrying the
thirteen existing reports plus `movement=None` would therefore be exactly the forbidden proper
subset the validator exists to reject.

So `movement` joins that set as the **fourteenth** field, and `movement=None` is legal only in the
existing all-fourteen-absent construction case. The distinction the design relies on is between an
absent report (the audit chain is broken) and a present-but-empty one (the chain ran and nothing
happened) — the same distinction `ForeignAffairsReport` already documents for a turn with no
candidates and no live conflicts (`report.py:3958-3961`).

### 7.2 Reconciliation Group 54

`reconcile_formation_movement(opening_state, closing_state, decisions, report)` proves, for every
formation:

1. Unchanged formation ⇒ closing location equals opening location.
2. Moved formation ⇒ exactly one submitted order named it.
3. Closing location equals that order's `destination_theater_id`.
4. The set of formation ids is identical opening to closing — none appeared, disappeared or
   duplicated.
5. `branch` and `display_name` are unchanged for every formation.
6. Every `MovementReport` row corresponds to a real opening→closing transition, and every
   transition has a row — neither direction may be silently empty.
6a. **Each row is internally faithful (D1)**, field by field:
   - `origin_theater_id` equals the formation's **opening** location;
   - `destination_theater_id` equals the formation's **closing** location;
   - `origin_theater_display_name` equals the authored display name of that opening theater in the
     strategic map;
   - `destination_theater_display_name` equals the authored display name of that destination
     theater;
   - `display_name` and `branch` equal the authoritative formation's own values.

   **Six independent tamper controls**, one per field, each mutated alone: origin display name,
   destination display name, origin id, destination id, formation display name, formation branch.
   Group 54 must detect every one. A single combined control would let five of the six checks be
   absent without failing.
7. The strategic map is unchanged (Group 53 continues to prove this independently; Group 54 asserts
   it too, so a bug that disabled one is not masked by the other).

Returns problem strings, never raises — matching every existing reconciler
(`reconciliation.py:3105-3107`). Group 54 is the next free number (53 is map staticness,
`reconciliation.py:3104`).

### 7.3 Exhaustive completeness growth — measured

`_THIRTEEN_REPORT_FIELDS` (`tests/test_tax_base_report.py:194`) drives an exhaustive test over every
proper nonempty subset: **2¹³ − 2 = 8,190** cases. Adding `movement` to that set — which C1 requires,
since the report is present on every resolved turn — makes it **2¹⁴ − 2 = 16,382**, an increase of
**8,192**. The tuple is renamed `_FOURTEEN_REPORT_FIELDS` and the validator's own name and message
are updated from "thirteen" to "fourteen".

Measured, not extrapolated:

| | Subsets | Validation work | Full pytest test |
|---|---|---|---|
| 13 fields (today) | 8,190 | **1.30s** | **27.50s** |
| 14 fields (projected) | 16,382 | **2.56s** | ~55s |

The validation itself is 0.16 ms/case and doubles to 2.56s. The remaining ~26s is pytest's
per-parametrized-case overhead, which is what actually doubles. Net effect on a ~21-minute suite:
**about +27s, ~2%.**

**Completeness testing is not weakened to avoid this.** But the ceiling is now visible and should be
recorded: a fifteenth report is ~110s and a sixteenth ~220s. The exhaustive strategy remains
practical for this slice and probably one more; it is not a strategy that survives indefinitely, and
the successor question (property-based subset sampling with the exhaustive run kept as a nightly
job) should be answered before report sixteen, not at it.

---

## 7.4 Report-presentation surfaces — audited, not assumed (C2)

Revision 3b asserted that "the existing Turn Result / History surfaces report what moved" without
identifying the code that would make it true. Audited mechanically at `cf738ad`:

| # | Surface | Path | Does it handle a new report automatically? |
|---|---|---|---|
| 1 | Frontend Turn Result | `frontend/src/greybox/TurnResultView.tsx` | **Partly.** It renders `TurnResultProjection` — `drivers`, `ledger`, `unchanged`, `trace` — never a raw `TurnReport`. It is generic over *projected rows*, so it needs no per-report code, but it shows nothing unless the backend projection emits rows. |
| 2 | Frontend History | `frontend/src/greybox/screens/HistoryScreen.tsx` | **Yes, structurally.** Its own docstring records that both call sites render the *same* `TurnResultView` over the same generated type, so "there is no second, parallel presentation path that could drift from this one" (`TurnResultView.tsx:1-8`). |
| 3 | Backend CLI current turn | `app/cli.py:550` `render_entry` | **No.** It dispatches on `REASON_RENDERERS` (`cli.py:507`) and falls back to `[unrendered reason_id=…]`. |
| 4 | Backend CLI history | same `render_entry`, via `mandate inspect` | **No.** Same table. |
| 5 | Report → API projection | `app/api/projections.py:1134` `build_turn_result` | **No.** Drivers come from report entries via `label_for` (`projections.py:115`); ledger rows are appended explicitly. |
| 6 | Human-readable labels | `REASON_LABELS` (`projections.py:84`) and `REASON_RENDERERS` (`cli.py:507`) | **No.** `label_for` falls back to the visible placeholder `[reason_id]` (`projections.py:117`). |
| 7 | Exhaustive registry | `tests/test_api_projections.py:76` — `assert set(REASON_LABELS) == set(REASON_RENDERERS)` | **This is the hard gate.** A new reason id must be added to **both** tables in the same commit or this assertion fails. |

**Consequence.** `MovementReport` is *not* rendered automatically anywhere. What is genuinely generic
is `TurnResultView` (#1, #2) — it needs no new frontend component, only backend rows — and that is
covered by a focused regression test rather than duplicated logic, exactly as C2 directs.

The movement reason id (proposed `formation_moved`) must land with **both** registry entries, and
the W1 precedent shows this is the established practice: its six ids were added to `REASON_LABELS`
with a comment noting that "before they were labelled here they reached clients as the `[reason_id]`
placeholder `label_for` falls back to, which this module's own key-set assertion exists to prevent"
(`projections.py:100-105`).

**Display names, never ids.** The rendered sentence is built from `MovementReport`'s own
`display_name` plus the theaters' display names:

> First Army of Arken moved from Arken Capital Region to Northern March.

No raw formation or theater identifier may appear in player-facing prose — the same rule R2 already
enforces for headings.

**Quiet-turn behaviour: render the sentence, do not omit the section.** Chosen after inspecting
precedent: `TurnResultView` renders `EmptyNote` components for empty collections rather than hiding
panels ("No drivers were recorded for this turn.", "Nothing was committed this turn."), and
`ForeignAffairsReport` documents that "an outbreak row with zero candidates and an empty
`progressions` tuple is still a valid, complete report" (`report.py:3958-3961`). A quiet turn
therefore renders **"No formations moved."** Omitting the section would make "nothing happened"
indistinguishable from "this surface does not know about movement". **The serialized
`MovementReport` is present regardless** (§7.1) — this choice concerns the visible section only.

**Tests — end-to-end across all four surfaces (D4).**

*Applied movement:*
1. `MovementReport` contains both ids **and** both theater display names.
2. API Turn Result renders the exact sentence.
3. API History renders the **same** sentence.
4. CLI current-turn output renders the same sentence.
5. CLI `inspect`/history output renders the same sentence.
6. Save/reload preserves every report field **and** the rendered sentence.
7. **No raw formation or theater id appears** in any of the four rendered outputs.

*Quiet movement:*
1. Serialized `MovementReport(movements=())` is present.
2. API Turn Result shows `No formations moved.`
3. API History shows the same.
4. CLI current and historical output show the same.
5. **No fabricated movement driver or ledger row appears.**

*Tampering:* six independent mutations — origin display name, destination display name, origin id,
destination id, formation display name, formation branch — each altered **alone**, each detected by
Group 54 (§7.2 item 6a).

*Cross-surface consistency:* for **one** resolved movement, assert that the API Turn Result, the API
History and both CLI paths derive their values from the **same authoritative report row** — the same
`formation_id`, both ids and both display names — so no surface can drift.

*Registries:* the existing `set(REASON_LABELS) == set(REASON_RENDERERS)` equality
(`tests/test_api_projections.py:76`) covers `formation_moved` in both tables, and no unknown code
falls through to `[reason_id]` or `[unrendered reason_id=…]`.

**Scheduling.** Backend CLI renderers, `REASON_LABELS`/`REASON_RENDERERS` entries and the
`build_turn_result` rows land in **commit 5** (they are backend presentation, and the key-set
assertion fails otherwise). Frontend Turn Result / History assertions and any reason-label UI work
land in **commit 8**. No earlier frontend contract commit is required, because `TurnResultView`
consumes only the existing generic projection types (§7.5).

## 7.4.1 The exact report-to-presentation mapping (D2, D3)

### Which design, and why the evidence forces it

**Design 2: the resolver emits a canonical reason entry, reconciled byte-for-byte against
`MovementReport`.** Not chosen for convenience — design 1 was tested against the real projection
models first and does not fit:

| Candidate collection | Shape | Verdict |
|---|---|---|
| `drivers: tuple[DriverItem, ...]` | `category`, `reason_id`, `label`, `params` (`projections.py:338-341`) | The only "something happened this turn" channel — but it is built **exclusively** from `report.entries` (`projections.py:1142-1150`), so a report sub-object alone can never reach it |
| `ledger: tuple[LedgerEntry, ...]` | `label`, `target`, **`amount_text` (required)**, `effect_text` (`projections.py:344-350`) | A movement has no amount; filling `amount_text` with a placeholder would be a fabricated field |
| `trace: tuple[TraceField, ...]` | `label`, `value_text`, `source_field` | The disclosure layer that is **collapsed by default** (`TurnResultView.tsx:9-10`) — wrong altitude for a turn event |
| `unchanged: tuple[str, ...]` | plain sentences, "from stored report fields only" (`projections.py:1270-1271`) | Right home for the **quiet** case, wrong for an applied one |

`build_turn_result` does read report sub-objects directly for `ledger` and `trace`
(`report.political_capital`, `report.legislative`, `report.constitutional_amendment`,
`report.election`), so design 1 is architecturally available — it simply cannot reach `drivers`,
which is where a turn event belongs. W1 resolves the same tension the same way: its conflict events
are reason ids in `REASON_LABELS` (`projections.py:106-111`), not projected report sub-objects.

**`MovementReport` remains the authoritative record.** The reason entry is a presentation channel
derived from the same application step, never a second source of truth (D3).

### Applied movement — field by field

| Stage | Exact mapping |
|---|---|
| Resolver (slot 8) | For each applied order, appends **one** `TurnReportEntry(category="military", reason_id="formation_moved", params={…})` **and** one `FormationMovementRow`, from the same snapshot in the same step |
| `params` schema | `dict[str, str \| int]` with exactly seven keys: `formation_id`, `formation_display_name`, `branch`, `origin_theater_id`, `origin_theater_display_name`, `destination_theater_id`, `destination_theater_display_name` |
| API projection | `build_turn_result` → `drivers`, as `DriverItem(category="military", reason_id="formation_moved", label=label_for("formation_moved"), params=entry.params)` — no new projection model, no new field |
| `REASON_LABELS["formation_moved"]` | `"A formation moved."` — a **static** label, matching every existing entry |
| Frontend Turn Result | `TurnResultView` renders `driver.label` today. The **parameterised** sentence is composed from `driver.params` for this `reason_id`. Composing it is string arithmetic, so **it lives in `src/format/`** — `src/format/format-boundary.test.ts` fails on any arithmetic `BinaryExpression` outside `src/format/**` |
| Frontend History | Identical, because both call sites render the *same* `TurnResultView` over the same generated type (`TurnResultView.tsx:1-8`) |
| CLI current turn | `render_entry` → `REASON_RENDERERS["formation_moved"]` → `_render_formation_moved(params)` |
| CLI history | The same `render_entry`, via `_cmd_history`'s entry loop (`cli.py:1645-1646`) |
| CLI report block | `_print_movement_report(report.movement)` — **quiet state only** (see §7.4.2), wired into **both** `_print_report` and `_cmd_history` from **one shared helper**, the `_print_foreign_affairs_report` pattern whose docstring names the alternative as "a second inline copy, the Phase 3A dual-wiring trap the frozen plan names explicitly" (`cli.py:1478-1483`) |
| Output sentence, all surfaces | `First Army of Arken moved from Arken Capital Region to Northern March.` |

### 7.4.2 The CLI prints an applied movement exactly once (E1)

**The call graph, traced mechanically.** Both CLI paths render `report.entries` **first**, then the
per-report blocks:

| Command | Path | Order of execution |
|---|---|---|
| Current resolved turn | `_print_report` (`cli.py:1515`), called at `cli.py:1596` | 1. `for entry in report.entries: render_entry(entry)` (`:1517-1518`) → 2. every `_print_*_report` block (`:1519-1544`) |
| `mandate inspect` / history | `_cmd_history`'s inline block | 1. `for report_entry in report.entries: render_entry(report_entry)` (`:1645-1646`) → 2. the same shared `_print_*_report` helpers (`:1647-1685`) |

So scheduling **both** a `REASON_RENDERERS["formation_moved"]` sentence **and** a
`_print_movement_report` that also prints applied movements would print the identical sentence
**twice in each path**. Revision 3d scheduled exactly that.

**Division of labour, corrected:**

- The canonical `formation_moved` entry, through `REASON_RENDERERS`, prints **every applied
  movement**. This is the entry loop, and it runs in both paths already.
- `_print_movement_report` prints **only the quiet sentence**, and only when
  `movements == ()`. For a nonempty report it emits **nothing** — no applied-movement sentence, no
  header, no blank section.
- Both command paths reuse that one helper for the quiet case, so the quiet sentence is also written
  once and in one place.

**Why not a summary/detail split.** The `_print_foreign_affairs_report` precedent does print a block
alongside its reason entries, but the two carry **genuinely different content**: the entries say "A
war broke out between two foreign countries." while the block prints the outbreak draw, probability,
candidate count and per-conflict intensity and position numbers (`cli.py:1487-1510`). Movement has
no such numeric detail — the sentence *is* the whole content — so a second block would be the
identical string, not a different purpose.

**Binding output guarantees**, per complete CLI output, for both commands:

| Property | Requirement |
|---|---|
| Applied movement sentence | appears **exactly once** |
| `No formations moved.` on a quiet turn | appears **exactly once** |
| `[unrendered reason_id=…]` fallback | **never** appears |
| `[reason_id]` label placeholder | **never** appears |
| Raw formation or theater id in player-facing text | **never** appears |

**Tests count occurrences, not presence.** Substring assertions cannot catch a double print, so each
test captures the **complete** output of the command and asserts an exact count: applied sentence
count `== 1`; quiet sentence count `== 1`; both asserted independently for the current-turn command
and the history command, since the two paths are separately wired and the repository's own comments
record that dual wiring is where this class of bug has appeared before.

### Quiet turn — field by field

| Stage | Exact mapping |
|---|---|
| Resolver | Emits **no** `formation_moved` entry and sets `MovementReport(movements=())` |
| Serialized report | `report.movement` is **present** with an empty tuple (§7.1) — never `None` on a resolved turn |
| API projection | `_unchanged_statements(report)` appends `"No formations moved."` when `report.movement.movements == ()` — that helper exists for exactly this, "Explicit 'what did NOT change' lines, from stored report fields only" (`projections.py:1270-1271`) |
| Frontend | Renders the string from `unchanged`; no component change |
| CLI | `_print_movement_report` prints `No formations moved.` |
| Fabrication | **No** `formation_moved` driver and **no** ledger row is invented on a quiet turn |

### Two namespaces, never conflated

- **Submission/classification codes** — `destination_not_player_owned`,
  `destination_not_directly_reachable`, `formation_unknown`, `destination_theater_unknown`,
  `destination_is_origin` — describe a **rejected** order. They never enter a report, never appear
  in `REASON_LABELS` or `REASON_RENDERERS`, and never reach a resolved turn (§4).
- **Historical report reason ids** — `formation_moved` — describe a **succeeded** action on a
  resolved turn, and live in both registries.

A test asserts the two sets are disjoint, so a future contributor cannot register a rejection code
as a turn event because both eventually need human-readable text.

### Agreement, duplication and omission

Reconciliation Group 54 additionally proves, for every resolved turn:

- the multiset of `formation_moved` entries and the tuple of `MovementReport.movements` have
  **equal length** — no duplicate entry, no missing one;
- each entry's seven `params` equal the corresponding row's seven fields **exactly**;
- a quiet turn has **zero** `formation_moved` entries and an empty `movements` tuple.

A movement can therefore never be reported differently by the report, the API projection and the
CLI: all three derive from one row and its paired entry, which are proven identical.

## 7.5 Contract regeneration — measured, not assumed (C3)

Revision 3b regenerated contracts only in commit 6, which would have left commit 5 with stale
artifacts if a new `Decision` union member or a fourteenth `TurnReport` field changed any reachable
schema. **This was tested rather than reasoned about.**

**Method.** The exact commit-5 delta — `FormationMovementOrder`, `MilitaryMovementDecision`, union
membership, `FormationMovementRow`, `MovementReport`, and `TurnReport.movement` — was applied to a
**scratch copy of `backend/` outside the repository**, and the real generator
(`scripts/dump_openapi.py`) was run against it with the project's own interpreter.

**Result: zero drift.** The generated document is **byte-identical** to the committed
`docs/contracts/phase4a-openapi.json`; both carry **52** schemas, with none added or removed.

**Why**, so the result is explainable and not a coincidence:

- `ResolveRequest.decisions` and `PreviewRequest.decisions` are declared
  `tuple[dict[str, Any], ...]` (`app/api/routes.py:367`), which serializes as an array of untyped
  objects. **The `Decision` union never reaches the schema**, so adding a member cannot change it.
- `TurnReport` is not in the schema at all; the API exposes `TurnResultProjection`. A fourteenth
  report field is therefore invisible to the contract.
- `BudgetDecision` and `ConstitutionalAmendmentDecision` *are* present, but only because
  `PolicyCardRoute` references them. Movement is not a policy card, so nothing pulls
  `MilitaryMovementDecision` in.
- An applied movement surfaces through the existing generic **`DriverItem`** shape, and a quiet turn
  through the existing **`unchanged: tuple[str, ...]`** sentences (§7.4.1). **`LedgerEntry` is
  explicitly rejected** — its `amount_text` is required and a movement has no amount. Either way no
  new projected type is introduced.

**Therefore commit 5 stages no generated-file change (D5).** Zero drift means there is nothing to
commit, and manufacturing a no-op artifact edit would be dishonest. Precisely:

- the real generator **is run during commit 5's verification**;
- both `docs/contracts/phase4a-openapi.json` and `frontend/src/api/schema.d.ts` are **required to
  remain byte-identical**;
- **no generated artifact is staged or manufactured** in commit 5;
- the zero-drift result is **recorded in commit 5's verification report**, so the check is visible
  even though the diff is empty.

**Commit 6 regenerates and commits the genuine `/api/game/military` delta**, accepting **only** the
endpoint/projection change attributable to it; any unrelated drift stops the commit. Since the
TypeScript types are generated from the JSON, an identical JSON yields an identical
`schema.d.ts`.

No commit leaves generated artifacts stale, and none commits a file that did not change.
"Regenerate later" is never an intermediate state.

## 8. API and cache behaviour

**Formation data must not go on the strategic-map endpoint.** `useStrategicMap`
(`frontend/src/api/queries.ts:127`) is keyed on a **generation counter** with `staleTime: Infinity`
because the map "never changes after a game is started or loaded" (`queries.ts:119-122`). Positions
change every turn; putting them there would show stale positions with no refetch.

### 8.1 New revision-keyed projection

`GET /api/game/military` → `MilitaryProjection`, keyed on `revision` like `useDecisionOptions`
(`queries.ts:78`):

```
MilitaryProjection
  revision: str
  formations: tuple[FormationProjection, ...]     # canonical by formation_id
      formation_id, display_name, branch,
      location_theater_id, location_display_name,
      destination_options: tuple[DestinationOption, ...]
          theater_id, display_name, eligible: bool, ineligible_reason_code: str | None
```

**`destination_options`, not `valid_destinations` (C3).** The collection deliberately carries both
eligible and ineligible theaters, because the UI must *explain* the ineligible ones (§9.4) rather
than hide them. A field named `valid_destinations` that contains invalid destinations would be a
lie in the schema.

**`last_resolved_movements` is removed (C9).** Revision 2 put it here without establishing where a
*state* projection would obtain history, and it duplicated the turn report. The division is:

- this revision-keyed projection reports **current positions and destination options**;
- the resolve response and the Turn Result / History surfaces report **what moved** — not
  automatically: §7.4 audits those seven surfaces, and the rows, labels and CLI renderers they need
  are scheduled work, not inherited behaviour;
- after a resolve, the new current position is visible through the refreshed projection.

No history-derived field remains in a state projection.

- **Destination options** are computed server-side from authored routes (§3), so the client never
  derives legality — the same rule that keeps the frontend from recomputing adjacency
  (`geography.py:141-142`).
- **Ineligible destinations are included with a reason code**, not omitted, so the UI can explain
  rather than silently hide (§9.4).
- **Pending drafts are absent from this projection.** A staged order lives in `useDraftStore`
  (§9.1.1) until the existing Resolve action sends it; the server has no draft to report.
- **No applied-movement history field.** What moved is reported by the resolve response and the
  existing Turn Result / History surfaces; this projection reports only the **current** position,
  which the post-resolve refetch already updates (C9).

### 8.0 One classifier, one source of legality (C3)

`/api/game/military` is the **single** endpoint carrying formation positions and destination
options. `DecisionOptionsProjection` is **not** extended with military legality data: it answers
"what constants and rows exist to choose from", and the decision composer needs no military
legality to assemble a `DecisionSet` — it carries the chosen order through verbatim, and layer 3
(§4) decides legality authoritatively. If a future composer genuinely cannot function without a
military reference, the minimal admissible addition is a **count of movable formations** for
enabling a control, defined in that gate and still derived from the same classifier below — never a
second legality implementation.

All three consumers call **one production classifier**:

```python
def classify_destinations(
    *, formation: FormationState, player_country_id: str, map_state: StrategicMapState,
) -> tuple[DestinationClassification, ...]:
    """Every theater, each marked eligible or carrying exactly one §4.1 reason code.
    The SINGLE implementation of movement legality."""
```

- the **military projection** converts its results into displayable options;
- the **draft preview** (layer 2) returns its reason codes without raising;
- the **submission validator** (layer 3) raises on any non-eligible result.

All three consumers arrive no earlier than the classifier itself: the classifier lands alone in
commit 4, and preview and submission validation land with application in commit 5 (§13, C1).

The projection may present, but must never re-derive. A test asserts that the projection's
eligibility for every theater in all three shipped scenarios equals the classifier's directly, so a
divergent second implementation cannot be introduced without failing.

### 8.2 Invalidation

| Event | Action |
|---|---|
| `useResolve` success | invalidate the military query (revision changed) |
| `useNewGame` / `useLoadGame` success | bump the generation counter **and** invalidate military |
| A formation moves | **no** strategic-map refetch — geography did not change |

The client composes immutable geography from `useStrategicMap` with revision-keyed positions from
`useMilitary`. Two queries, two lifetimes, one render.

---

## 9. Frontend state and accessibility

### 9.1 State machine — the map stages an order; it never resolves the turn (C2)

Revision 2's machine ran `confirmedDraft → resolving` automatically, which would have made the map
screen a second, competing way to end the turn. **Corrected: confirming on the map returns control
to the existing shared composer**, and only the existing Resolve action advances anything.

```
  idle ──select formation──▶ formationSelected ──select destination──▶ destinationSelected
             ▲                       ▲                                          │
             │                       │                                    (review shown)
             │                       └──────── Escape ──────────┐               ▼
             └──────── Escape ───────────────────────────┐      └──────── orderReview
                                                         │                      │
                                                         │        "Add movement order"
                                                         │                      ▼
                                                         └──── orderStaged ─────┘
                                                                    │
                              (control returns to the shared turn draft; the map is now idle
                               with a visible staged order, and the player may add a budget,
                               an amendment, or relationship investments as usual)
                                                                    │
                                                                    ▼
                                        existing Decisions screen ── Resolve turn ──▶ /resolve
```

There is **no `resolving` state on the map screen**. Resolution stays exactly where it already is:
`DecisionsScreen`'s Resolve → Confirm flow.

### 9.1.1 Where the shared draft lives, mechanically

| Question | Answer, verified in the repository |
|---|---|
| Which store owns the shared draft? | `useDraftStore`, a zustand store at `frontend/src/state/draft.ts:132`, shape `DraftState` (`draft.ts:62`) |
| How is the decision array built? | `buildDecisions(draft)` at `frontend/src/state/buildDecisionSet.ts:116`, which appends in canonical kind order and comments each position |
| When is it cleared? | `clearDraft()` — its own docstring says "Called ONLY after a successful resolve" (`draft.ts:95-96`), invoked at `DecisionsScreen.tsx:251` inside `onSuccess` |

**Additions to `DraftState`** — one nullable slot plus two actions, matching the existing
`investments`/`setInvestment` idiom rather than inventing a new pattern:

```ts
movement: { formationId: string; destinationTheaterId: string } | null;  // null = no order staged
setMovementOrder: (formationId: string, destinationTheaterId: string) => void;  // insert or REPLACE
clearMovementOrder: () => void;                                                 // remove
```

- **Insert / replace / remove.** `setMovementOrder` replaces wholesale, mirroring `applyCard`'s
  documented "replaces the relevant slot WHOLESALE — no stale field survives a card switch"
  (`draft.ts:76-80`). Staging a second order for a different formation *replaces* the first, which
  is what makes the one-order cap unreachable from the UI rather than merely rejected by the server.
- **Canonical order** is maintained in `buildDecisions`: the movement decision is appended **last**,
  after `bloc_relationship_investment`, `budget` and `constitutional_amendment`, because
  `military_movement` sorts last ascending (§2.1). Every insertion point in that function already
  carries a comment naming its sort position; the new one follows suit.
- **Returning to the map** reconstructs the pending display from `draft.movement` alone. The map
  holds no order state of its own, so navigating away and back cannot lose or duplicate a staged
  order.
- **New Game / Load** already bump the generation counter and reset session state; `clearDraft()`
  is called on both paths so a staged order from a previous campaign can never survive into a new
  one. This is the one behavioural addition to the existing clear points, and it is required —
  a stale `formationId` from another scenario would otherwise be submitted.
- **Successful resolve** clears it via the existing `clearDraft()` at `DecisionsScreen.tsx:251`;
  no new clear site is introduced.
- **Failed resolve preserves it**, by existing precedent: `clearDraft()` lives inside `onSuccess`
  only, so a rejected or errored resolve leaves the whole draft — movement included — intact for
  the player to correct and retry.

### 9.1.2 Combination with every existing decision kind

Each row lists **exactly** what is staged and **exactly** the resulting array — no optional or
elided member appears inside a result (B3):

| Staged together | Resulting `decisions` array |
|---|---|
| movement only | `[military_movement]` |
| movement + relationship investment | `[bloc_relationship_investment, military_movement]` |
| movement + budget | `[budget, military_movement]` |
| movement + constitutional amendment | `[constitutional_amendment, military_movement]` |
| movement + relationship investment + budget | `[bloc_relationship_investment, budget, military_movement]` |
| movement + relationship investment + amendment | `[bloc_relationship_investment, constitutional_amendment, military_movement]` |

Budget and constitutional amendment remain mutually exclusive under the existing `policySlot` rule,
so no row can contain both.

Movement never interacts with that exclusivity — it is a separate, non-exclusive slot, like
relationship investment. **Mixed-decision tests** are required: a budget and
a movement staged in one turn must produce a canonically ordered `DecisionSet`, resolve
deterministically, and yield both a `FinanceReport` change and a `MovementReport` row — plus the
reverse staging order producing a byte-identical `DecisionSet`, proving the array is built from the
draft's content and not from the order the player happened to click.

### 9.2 Focus and Escape

| Transition | Focus lands on | Escape |
|---|---|---|
| → formationSelected, **≥1 eligible destination** | the destination list's first eligible option | back to idle, focus the formation |
| → formationSelected, **zero eligible destinations** | the destination-section heading (see §9.2.1) | back to idle, focus the formation |
| → destinationSelected | the review panel heading (`tabIndex={-1}`, the M0 pattern) | back to formationSelected |
| → orderReview | "Add movement order" | back to destinationSelected |
| → orderStaged | the staged-order summary, which is focusable and offers "Change" and "Remove" | removes the staged order and returns to idle |
There is no map-side `resolving` or `error` row: resolution and its failures belong to the existing
Decisions screen, whose focus and error behaviour is unchanged by this slice (§9.1).

**After a resolve that happened on another screen (F7).** Revision 3 said focus lands on "the
refreshed map's staged-order region". That is impossible: Resolve happens on `DecisionsScreen`, so
the Strategic Map is **not mounted** and cannot receive focus. Corrected behaviour:

- The existing Decisions / Turn Result focus behaviour remains **authoritative** immediately after
  Resolve. This slice changes none of it.
- The map receives **no focus while unmounted**, and **no cross-screen focus transfer is attempted**.
- When the player later navigates back to Strategic Map, the revision-keyed military query supplies
  the formation's **new** location, and ordinary screen-entry focus behaviour applies — the same
  heading focus M0 already implements.
- A polite live-region message may state the new location, but **only once the map screen is
  mounted**, as an ordinary mount-time announcement.

**Frontend integration test required:** stage a movement on the map, navigate to Decisions, resolve
there, assert focus follows the existing Decisions/Turn Result behaviour and that nothing attempts
to focus an unmounted map node, then navigate back to Strategic Map and assert the formation renders
at its new location with the staged order cleared.

### 9.2.1 Zero eligible destinations (B4)

Nothing guarantees a player-owned theater has an outgoing LAND route, so this state must be
designed rather than assumed away.

**It is reachable from a valid state, and the invariants say so.**
`player_land_component_disconnected` (`app/simulation/invariants.py:1226-1245`) walks **directed**
edges *forward from the capital*: `player_edges[route.from_theater].add(route.to_theater)`, then a
frontier expansion from `capital_theater_id`. A theater reached by an authored `capital → X` row
therefore satisfies the invariant **even with no outgoing row of its own** — at which point a
formation in X has zero eligible destinations. No invariant is violated, and **none is added to
make the UI simpler**: a map-connectivity requirement invented for the convenience of a panel would
constrain scenario authorship for a presentation reason.

Behaviour:

- **Focus** the destination-section heading, or the explanatory message if the section has no
  heading — never a control the player cannot use.
- **Announce**, politely: that this formation has no eligible movement destination this turn.
- **List every theater with its ineligibility reason**, using the §9.4 wording — the player learns
  *why*, not merely that nothing is possible.
- **Render no order-review and no confirmation control.** There is nothing to review, and a
  disabled Confirm would imply an order is one step away.
- **Escape** returns focus to the selected formation, as in every other state.

**Tests (pointer and keyboard).** No shipped scenario exhibits this — I checked all three, and every
player theater has between one and two eligible destinations, because their routes are reciprocal.
The case therefore uses an **authored test scenario** that is fully valid: a player-owned theater
with an authored incoming route from the capital and no outgoing row. The test asserts the state
passes `check_invariants` first, so the case can never quietly become one that only "works" because
validation was skipped.

### 9.3 Live-region announcements

Reuse M0's existing polite `role="status"` region. Announcements: formation selected with its
location and eligible-destination **count**; destination selected with the planned route in words;
order confirmed as a draft with an explicit "nothing has moved yet"; after resolution, the applied
origin → destination.

### 9.4 Explaining invalid destinations

Every ineligible destination is **listed**, greyed, with its reason in words — never omitted, and
never conveyed by colour alone:

- "Not eligible — owned by Kessia; foreign entry is unavailable." (`destination_not_player_owned`)
- "Not eligible — owned by Vetruska; foreign entry is unavailable."
  (`destination_not_player_owned`)
- "Not eligible — no direct outgoing LAND route from this theater."
  (`destination_not_directly_reachable`, which per §3.4 can only ever name a **player-owned**
  theater)

**One rule, no traversal (C8).** Revision 2 also offered "reachable only through another theater"
for the flank→flank case. Producing that sentence requires graph traversal this one-edge slice
otherwise never performs, and running a BFS purely to improve an error message would smuggle
multi-hop reachability into a slice that forbids it. Every player-owned but unreachable destination
gets the single honest sentence above. The map still *shows* the wider route network, so a player
can see for themselves that a second move next turn would reach further — but the legality result
for the current order stays direct-edge-only.

Both foreign theaters read as ownership failures, and neither is ever described as merely
unreachable, so no wording can suggest that adding a route would authorize foreign entry (§3.4).

### 9.5 Styling and redundancy

Selected formation: dashed gold ring **and** the detail panel naming it **and** the live region.
Eligible destination: dashed gold ring **and** an "eligible" list row. Ineligible: dimmed **and** a
reason string. Planned route: gold dashed line **with a destination arrowhead** (§9.5.1) **and**
"Planned route: A → B" in text. **Nothing depends on colour, SVG position, pointer input or
animation alone**, and the whole interaction is operable in the narrow list-only layout where no
SVG renders at all.

#### 9.5.1 The planned route is visibly directed

The planned route is drawn in three parts, in this order:

1. A high-contrast **casing stroke** in the background colour, wider than the route, so nothing
   underneath shows through.
2. The **gold dashed foreground route**.
3. A **solid arrowhead at the destination end** of the foreground route.

Requirements:

- **Exactly one arrowhead**, attached to the destination end. A movement has one direction; two
  arrowheads would state a reciprocal relationship that the order does not have.
- The arrowhead is **solid, not dashed**, and carries the same casing treatment, so it stays
  legible where it overlaps or approaches the destination's reachability ring.
- The whole route group, arrowhead included, is drawn **above** the reachability rings and node
  discs in layer order — the rings cannot obscure it.
- **The arrowhead is never the sole carrier of direction.** The review panel's From and To fields
  and the live-region announcement both state the direction in words, and both remain present.
- The arrow's origin and destination come from the **authored directed route**, never from screen
  geometry, node ordering or the order in which the player clicked.
- The SVG remains **presentation-only**. It renders a decision already validated server-side
  (§3, §4); it never determines legality, and reversing the drawing would not reverse the order.

### 9.5.2 "In position" is derived copy, not state (C10)

The formation-selected mockup shows `Status: In position`. **No `status` field exists in
`FormationState`, and none is added** (§6). That phrase is **derived presentation copy** computed in
the component from two things it already knows:

- the formation has **no staged movement order** in the shared turn draft (§C2), and
- its authoritative location is the theater currently being displayed.

When an order is staged, the same line reads `Order staged: → <destination>` — again derived, from
the draft. This string must never become stored state, a report field, a projection field, or the
seed of an inferred in-transit system. Movement completes at turn close; there is no transit to
model (§6).

### 9.6 Deterministic icon placement

Formations are sorted **canonically by formation id**, then placed at fixed 60° steps around the
theater centroid, with the fan's **starting angle derived from the theater's authored
`label_anchor`** so slot 0 never lands under the name.

**Six is the ceiling, and it is a rendering ceiling, not a gameplay one (C6).** Revision 2 claimed
60° steps mean "N icons never overlap"; that is simply false above six, where the seventh icon
lands on the first. The corrected rule:

- **1–6 formations:** every formation renders as an individual icon, one per angular slot.
- **7 or more:** the first **five** formations in canonical id order render as individual icons, and
  the **sixth angular slot carries one `+N` overflow control**, where **N = total − 5**.

  Revision 3a said six icons *plus* an overflow control. That is seven markers for six slots, and it
  never said where the seventh went — so it could not guarantee the non-overlap it claimed. The
  overflow control is not an extra marker; it **occupies a slot**, which is what makes the geometry
  provable.

  | Formations | Individual icons | Overflow |
  |---|---|---|
  | 6 | 6 | none |
  | 7 | 5 | `+2` |
  | 20 | 5 | `+15` |

- The overflow control is **focusable and labelled with the exact hidden count**.
- Activating the overflow control **opens or focuses the textual formation list**, where every
  formation in that theater remains individually selectable and orderable.
- **If a formation inside the overflow is selected from the list**, the overflow control takes the
  selected styling and its accessible name states that it contains the current selection — so a
  clustered selection is never invisible on the map or unannounced to a screen reader.
- **Keyboard and screen-reader users always receive the complete list**, clustered or not: the
  textual list is the accessible source of truth and never clusters. Clustering is a property of
  the picture alone.
- **No formation becomes unreachable because its icon was clustered.** Selection, destination
  choice, review and confirmation are all available for a clustered formation through the list.

The state model imposes **no cap on formations per theater** (product decision 3). The renderer
must never be the reason a gameplay limit exists. Drawing the
mockups is what found this: a naive fan starting at −90° puts slot 0 straight through the label of
every `anchor: n` theater — three of five in `tiny_valid`.

All of this is arithmetic, so **all of it lives in `src/format/`**:
`src/format/format-boundary.test.ts` walks the real TypeScript AST and fails on any arithmetic
`BinaryExpression` outside `src/format/**`.

### 9.7 Enlarged map mode

A dedicated enlarged interaction map (product decision 17): same authored `0 0 10000 10000`
viewBox, same geometry, more pixels — roughly 63% of the row rather than 48%, with the information
column beside it. **No zoom/pan in this slice.** If a browser walkthrough shows the enlarged mode is
insufficient for hit targets or label legibility, that evidence — not a preference — reopens the
question.

---

## 10. Compatibility

These compatibility operations begin only after this implementation plan has been approved and
frozen in the preceding documentation-only commit (§13 commit 1). Within implementation, their
relative order is unchanged: the authentic `0.14.0` fixture still precedes every state-model or
ruleset change.

1. **Freeze an authentic, map-enabled `0.14.0` fixture first**, produced by the still-unmodified
   engine. It becomes impossible to generate after the bump.
2. **Prove it round-trips byte-identically** under the unmodified `0.14.0` engine, before any state
   model changes.
3. Add required military state.
4. Bump ruleset **`0.14.0` → `0.15.0`**.
5. Keep save format **`1`**.
6. Reject `0.14.0` at the **ruleset-version gate, before payload parsing** — the pattern
   `tests/test_compatibility.py:569` proves for the `0.13.0` fixture, which fails with an actionable
   error naming both versions rather than crashing inside `WorldState` validation.
7. **No synthesis.** A `0.14.0` save has no formations; inventing a roster would assert a fact the
   save does not contain.

Evidence for the ordering: the repository holds **13 fixtures, `0.1.0` through `0.13.0`**, one per
bump, and M0 froze the authentic `0.13.0` fixture in commit `129fb2c3` **before** bumping to
`0.14.0` in `a4c3be11`. **There is no `0.14.0` fixture** — verified against the current tree.

---

## 11. Scenario-authorship proposal — REQUIRES APPROVAL

One player Army formation per scenario. **These are proposals and are not authored until approved.**

| Scenario | Formation id | Display name | Branch | Starting theater | Theater display name | Why suitable |
|---|---|---|---|---|---|---|
| `tiny_valid` | `arken_first_army` | First Army of Arken | `army` | `arken_capital` | Arken Capital Region | The capital is the star's centre, so both other player theaters are exactly one authored LAND route away — the slice is exercisable from turn 1 without multi-hop. |
| `decree_state` | `valdrun_first_army` | First Army of Valdrun | `army` | `valdrun_capital` | Valdrun Capital Region | Same star topology; capital is central and player-owned, one LAND route from Eastern Valdrun and Valdrun Highlands. |
| `deficit_demo` | `strapped_first_army` | First Army of the Republic | `army` | `home_capital` | Capital Region | Same star topology; the one coastal player theater, Port District, is one LAND route away — exercising a coastal *destination* without implying any naval capability. |

Each scenario authors exactly one abstract Army formation for this slice. No manpower, strength,
equipment, or troop quantity is stated or implied.

"First Army" is a **proper formation name**, in the way a real order of battle names a formation.
It does not define manpower or formation strength. The roster nevertheless does state a count:
**exactly one formation in each current scenario** — that is authored, visible in state, and not
something the plan may claim to leave unstated. What remains genuinely unstated is how large that
formation is.

Every theater id and display name above was read back from the shipped scenario YAML at
`cf738ad` and matches exactly. The player-owned theaters are, per scenario: Arken Capital Region /
Arken Coast / Northern March; Valdrun Capital Region / Eastern Valdrun / Valdrun Highlands;
Capital Region / Lowlands / Port District.

---

## 12. Test matrix

**Backend.** Model construction and rejection for every §2.3 shape code; every §4.1 state code with
an **independently reachable case from a valid production state**; directed reachability including a
synthetic one-way scenario proving an incoming-only route is not outgoing, and a player-owned
destination with no outgoing LAND row; foreign-ownership precedence (below); both new invariants;
Group 54 negative controls (below); insertion-order independence; determinism across N turns × 3
scenarios; save/reload byte-identity; the `0.14.0` rejection; and the 16,382-subset completeness run.

No non-LAND route test appears anywhere (F2). `RouteKind` has one member
(`app/simulation/geography.py:82-85`), so such a route cannot exist in a valid production state, and
`route_kind_not_land` was removed in C4. Forcing one through `model_construct` would prove the
validator executes, not that a player can reach it — which is exactly the kind of decorative
coverage §4.1's reachability rule forbids.

**Backend — Group 54 negative controls (F6).** Each must be independently reachable:

| Control | Detected as |
|---|---|
| A formation moved with no submitted order (teleport) | closing location ≠ opening location, no order names it |
| **A formation id present in closing state but absent from opening** | the id sets differ |
| **A formation id present in opening state but absent from closing** | the id sets differ |
| A mutated `branch` | branch changed during movement resolution |
| A mutated `display_name` | display name changed during movement resolution |
| A `MovementReport` row with no corresponding transition | extra row |
| A transition with no `MovementReport` row | missing row |
| A row whose destination ≠ the closing location | wrong reported destination |

Revision 3 listed "a duplicated formation". **That control is deleted**: `formations` is a
`dict[StrictFormationId, FormationState]`, and a mapping cannot hold a duplicate key — there is no
valid or invalid state to construct. Group 54 detects **appearance and disappearance**, which are
reachable; it does not and cannot detect duplicate dictionary keys, and this plan does not claim it
does.

**Backend — no-movement regression scope (F4).** Revision 3's shorthand "proving W1 output is
byte-identical" was overbroad, because the complete report gains an empty `MovementReport` and the
complete state gains military state. The asserted scope is exactly C7's seven comparisons (§5.2
item 1), each checked separately:

1. All thirteen pre-existing report subtrees byte-identical.
2. W1 foreign-affairs rows and outcomes byte-identical.
3. Closing state **excluding** `countries[*].military` byte-identical.
4. Military state unchanged from opening on a quiet turn.
5. `report.movement` present with `movements=()`.
6. Every pre-existing RNG stream produces identical draws.
7. `PHASE_IDS` and phase ordering unchanged.

**Nothing in this plan claims the complete `TurnReport` or the complete closing state is
byte-identical across `0.14.0` and `0.15.0`.** Both grew; the claim would be false.

**Backend — report completeness (C1).** Five focused cases, exactly as the ruling requires:

1. A **quiet** resolved turn includes `MovementReport(movements=())` — present, not `None`.
2. A **movement** turn includes exactly one row.
3. **Thirteen present + `movement=None` is rejected** by
   `_all_thirteen_domain_reports_are_all_present_or_all_absent`, extended to fourteen.
4. **All fourteen present is accepted.**
5. **All fourteen absent** retains the existing valid special case.

Plus the exhaustive subset run, now over fourteen fields: **2¹⁴ − 2 = 16,382** proper nonempty
subsets, all rejected (§7.3).

**Backend — regression baseline (C7).** The seven comparisons in §5.2 item 1, each asserted
separately, plus a test of the exclusion helper itself proving it removes only
`countries[*].military` and `report.movement` and nothing else.

**Backend — ownership-before-reachability precedence (§3.4).** Four focused cases, because a
precedence rule that is only documented is not enforced:

1. A foreign-owned destination **with** an authored LAND route from the origin emits
   `destination_not_player_owned`, **not** `destination_not_directly_reachable`. Uses
   `tiny_valid`'s real `arken_north → kessia_south` route, so the case is not synthetic.
2. A foreign-owned destination **without** any route emits the same
   `destination_not_player_owned` — `vetruska_frontier`, again real shipped data.
3. `destination_not_directly_reachable` is emitted **only** for player-owned destinations; a test
   asserts no foreign-owned theater can produce it, across all three shipped scenarios.
4. **Origin ownership is an invariant concern, not a submission code (F3).** Revision 3 required a
   case where "a foreign-owned origin emits `origin_not_player_owned`"; that code was removed in C4
   as unreachable, so the case is deleted rather than kept against a code that no longer exists.
   Replaced by three assertions:
   - `formation_location_not_owned_by_country` is emitted when a **candidate state** carrying a
     foreign-owned formation origin is validated, before any gameplay begins.
   - **No successfully created or loaded valid game** can reach decision submission with a
     foreign-owned formation origin — asserted across all three shipped scenarios by running the
     invariant check on the state each `new_game` and `load` produces.
   - Submission validation **never emits `origin_not_player_owned`**, asserted by scanning the
     validator's own reachable code set for the removed identifier.

**Frontend.** State-machine transitions including Escape from each state; keyboard-only completion
of the whole interaction; live-region text at each transition; every ineligible reason rendered as
text; both foreign destinations rendering an **ownership** reason and neither rendering an
unreachability reason; label non-collision at each `label_anchor`; narrow-layout parity; and the
existing format-arithmetic and raw-data boundaries.

**Frontend — icon placement and overflow (C6, B1).** Five counts in one theater:

| Formations | Expected individual icons | Expected overflow |
|---|---|---|
| 1 | 1 | none |
| 2 | 2 | none |
| 6 | 6 | none |
| 7 | **5** | **`+2`** |
| 20 | **5** | **`+15`** |

Plus, for every count: **no two rendered markers share coordinates** — icons and the overflow
control alike, asserted on the actual rendered positions rather than on the placement function in
isolation; the overflow control focusable and labelled with the exact hidden count; **every hidden
formation selectable and orderable through the textual list**, with the complete list in the
accessibility tree regardless of clustering; and **selecting a hidden formation gives the overflow
control selected styling and an accessible name stating it contains the selection**.

**Frontend — shared composer (C2).** Staging an order writes `draft.movement` and does **not**
resolve; navigating away and back reconstructs the staged display from the store; a budget and a
movement staged in either click order produce byte-identical canonical `DecisionSet`s; a failed
resolve preserves the staged order; a successful one clears it; New Game and Load clear it.

**Frontend — planned-route direction (§9.5.1).** Five focused cases:

1. **Exactly one** planned-route arrowhead is rendered.
2. The arrowhead is attached to the **destination** end, not the origin end.
3. **Reversing an authored test route reverses the displayed direction** — the arrowhead follows
   the authored row, not screen geometry or click order.
4. The review panel's textual **From** and **To** fields are present whenever a route is drawn, so
   direction never rests on the arrowhead alone.
5. **No route and no arrowhead render before a destination is selected** — neither in `idle` nor in
   `formationSelected`.

**Calibration/soak.** None. There is no probabilistic behaviour and no balance surface in this
slice — a soak would measure nothing. Say so rather than running one for appearances.

**Generated contracts.** `MilitaryProjection` regenerates both
`docs/contracts/phase4a-openapi.json` and `frontend/src/api/schema.d.ts` via `npm run generate:api`;
zero drift required afterwards.

---

## 13. Proposed atomic commit sequence — DO NOT EXECUTE

1. **Freeze this implementation plan — documentation only.** Nothing else lands first, and a
   docs-only commit cannot change engine behaviour, so the engine that generates commit 2's fixture
   is still the unmodified `0.14.0` engine (C11).
2. Freeze the authentic map-enabled `0.14.0` save fixture; prove byte-identical round-trip under
   that unmodified engine.
3. `MilitaryState` / `FormationState` / `FormationBranch`, scenario rosters, the two new invariants,
   ruleset `0.15.0`, and the `0.14.0` rejection test.
4. **Pure reachability and classification machinery only.** The directed one-edge LAND helper, the
   shared `classify_destinations`, its stable internal classification result, and exhaustive
   classifier tests including ownership-before-reachability precedence and the one-way cases.

   Commit 4 must **not**: add `MilitaryMovementDecision` to the production `Decision` union; add a
   production accessor that makes it accepted input; accept movement during resolve; expose a
   movement decision through production preview or submission; mutate state; or emit a movement
   report. It is a pure internal foundation that **adds no newly accepted player action** (C1).

5. **The complete backend movement atom**, landing together because they are not separable without
   a dishonest intermediate state: `FormationMovementOrder`, `MilitaryMovementDecision`, its
   `Decision` union membership and accessor, the shape-only validators, preview integration,
   authoritative submission validation, slot-8 application, the always-present `MovementReport`,
   TurnReport completeness thirteen → fourteen, history support, reconciliation Group 54, and the
   backend presentation surfaces identified in §7.4. Explicitly included: **self-contained movement
   rows** carrying both theater display names (§7.1, D1); the **exact API projection mapping** and
   **exact CLI current/history rendering** (§7.4.1); the **cross-surface consistency tests** (§12);
   and **generator verification with zero artifact drift** — run, required byte-identical, nothing
   staged (§7.5, D5).

   **At the end of commit 5, every accepted legal movement is applied exactly once and reported
   exactly once. An accepted movement is never silently ignored.**

6. The `/api/game/military` projection and endpoint, **reusing the classifier landed in commit 4**
   — this commit adds no legality logic of its own — plus its own contract regeneration (§7.5).
7. Enlarged military-map mode, including bounded icon placement and the sixth-slot `+N` overflow
   control.
8. Accessible selection, destination, review and **staging into the shared turn draft** — plus the
   `DraftState.movement` slot, its `buildDecisions` insertion point, and the mixed-decision tests.
9. Determinism, insertion-order, save/reload, compatibility and real-browser walkthrough evidence.
10. ADR and roadmap closeout, recording the infrastructure-only limitation prominently.

**Every commit must compile, pass its own focused tests without depending on later code, and leave
no dishonest externally observable state.**

Two distinct failures have been corrected here. Revision 3a scheduled the classifier *after* its
consumers, so commits 4 and 5 could not have been green (B2). Revision 3b fixed that but introduced
a worse one: it put decision-union membership, preview and submission validation in commit 4 while
application and reporting waited for commit 5 — so at commit 4 **a player could submit a valid
`military_movement` decision, have it accepted, and have the turn resolve with the order silently
discarded** (C1). No amount of focused validation testing makes that safe, because the defect is the
externally observable behaviour, not the tests. Acceptance and application must land together.

| Commit | Depends on | Introduces | Newly accepted player action |
|---|---|---|---|
| 3 | — | state, rosters, invariants, `0.15.0`, compatibility rejection | none |
| 4 | 3 | reachability helper, **`classify_destinations`**, classifier tests | **none** — pure internal foundation |
| 5 | 3, 4 | decision models + union membership, preview, submission validation, slot-8 application, `MovementReport`, fourteen-field completeness, history, Group 54, backend presentation, contract generator verification; generated artifacts remain byte-identical and are not staged | movement, **accepted and applied in the same commit** |
| 6 | 4, 5 | `/api/game/military` (reuse only) + its contract delta | none |
| 7 | 6 | enlarged map, bounded overflow | none |
| 8 | 6, 7 | selection, staging, the `src/format/` sentence composer, and frontend tests that the already-generic Turn Result / History component renders the projected movement output correctly | none |
| 9 | 3–8 | determinism, ordering, compatibility, save/reload, browser evidence | none |
| 10 | 3–9 | ADR + roadmap closeout | none |

Commit 4 stands independently: `classify_destinations` is a pure function over
`FormationState` (commit 3) and `StrategicMapState` (M0), and its tests construct both directly. No
repository evidence suggests it cannot, so it is **not** merged into commit 5.

---

## 13.1 Claims withdrawn from Revision 2

Recorded so a reviewer can diff intent, not just text. Each was wrong about the production code or
about its own consequences:

| Revision 2 claim | Why withdrawn |
|---|---|
| "A turn with no movement decision emits `movement=None`, exactly as `election` and `coup_unrest` do" | Both halves false; the completeness validator rejects proper subsets and those two fields are inside it (C1) |
| `confirmedDraft → resolving` on the map screen | Would make the map a second way to end a turn (C2) |
| Destination options on both `DecisionOptionsProjection` and `/api/game/military` | Two sources invite two legality implementations (C3) |
| `formation_origin_unresolved`, `origin_not_player_owned`, `route_kind_not_land` as player-facing codes | Unreachable from any valid production state (C4) |
| `StrictTheaterId` | Does not exist in production; `StrictMapId` is the real type (C5) |
| "N icons never overlap" at 60° steps | False above six (C6) |
| Full `TurnReport` / full closing-state byte identity across the bump | Impossible once state and reports grow (C7) |
| "Reachable only through another theater" | Requires traversal this slice forbids (C8) |
| `last_resolved_movements` in a state projection | History in a state projection, duplicating the report (C9) |
| Fixture frozen before the plan | Plan freeze must come first (C11) |

## 13.2 Revision 3 remnants removed in Revision 3a

Revision 3 applied C1–C13 to the prose that discussed them, but §12's test matrix and three other
passages were not re-read and kept contradicting the corrections. Recorded so the diff is auditable:

| | Live remnant in Revision 3 | Resolution |
|---|---|---|
| F1 | §4 layer 1 named `DecisionOptionsProjection` as the military-facts source | Replaced with `GET /api/game/military` built from `classify_destinations`; that projection stays unextended |
| F2 | §12 required "a synthetic non-LAND route proving `route_kind_not_land` is reachable" | Deleted; contradicts C4, and no `model_construct` substitute added |
| F3 | §12 required "a foreign-owned origin emits `origin_not_player_owned`" | Deleted; replaced with invariant-level coverage plus a proof the code is never emitted |
| F4 | §12 said "a no-movement-decision turn proving W1 output is byte-identical" | Replaced with C7's seven explicit comparisons |
| F5 | §3.1 declared `theater_id: str` and `routes: tuple[RouteState, ...]` | `StrictMapId` + `Sequence[KindedDirectedEdge]`; the `RouteState` form would also have been an import cycle |
| F6 | §12 listed "a duplicated formation" as a Group 54 control | Deleted as impossible in a dict; replaced with appearance and disappearance |
| F7 | §9.2 focused the map after a resolve on another screen | Impossible while unmounted; corrected to no cross-screen transfer plus a return-navigation test |
| F8 | §10 began with the fixture freeze, reading as if it preceded the plan freeze | One clarifying sentence added; operation order itself unchanged |

## 13.3 Revision 3a gaps closed in Revision 3b

| | Gap | Resolution |
|---|---|---|
| B1 | Six icons **plus** an overflow control — seven markers for six angular slots, with the seventh's position undefined | The overflow **occupies** the sixth slot: 1–6 → that many icons; ≥7 → five icons + `+N`, N = total − 5. 7 → `+2`; 20 → `+15` |
| B2 | Commits 4 and 5 depended on `classify_destinations`, which arrived in commit 6 | Classifier moves to commit 4 with its first consumers; commit 6 reuses and adds no legality logic; forward-only dependency table added |
| B3 | "movement + budget" showed an optional relationship decision inside the result array | Six exact rows; no elided or optional member appears in any result |
| B4 | Zero eligible destinations undefined | Defined focus, announcement, full reason list, no confirmation control, Escape; shown reachable from a valid state via the directed-edge invariant; authored test scenario, no new invariant |

## 13.4 Revision 3b defects corrected in Revision 3c

| | Defect | Correction |
|---|---|---|
| C1 | Commit 4 added `MilitaryMovementDecision` to the production union with preview and submission validation, while application and reporting waited for commit 5 — so an accepted order could resolve and be silently discarded | Commit 4 is now classifier-only and adds **no newly accepted player action**; commit 5 is the complete backend atom where acceptance and application land together |
| C2 | "Existing Turn Result and History surfaces report what moved" was asserted without identifying the code | Seven surfaces audited with paths; `TurnResultView` is generic over projected rows (regression test, not duplication), the two reason registries are not and are gated by `test_api_projections.py:76`; display-name rendering and the quiet-turn sentence chosen from precedent and scheduled |
| C3 | Contracts regenerated only in commit 6, risking stale artifacts at commit 5 | Delta modelled in a scratch copy and the **real generator run**: byte-identical output, 52 schemas, zero drift — explained by untyped `decisions` arrays and `TurnReport`'s absence from the schema. Commit 5 runs regeneration and verifies zero drift without staging generated files; commit 6 commits the genuine endpoint delta |

## 13.5 Revision 3c defects corrected in Revision 3d

| | Defect | Correction |
|---|---|---|
| D1 | `FormationMovementRow` carried neither theater display name, so the promised sentence could not be produced from the row — contradicting the plan's own reason for storing `display_name` and `build_turn_result`'s "nothing is recomputed from current state" | Both `origin_theater_display_name` and `destination_theater_display_name` added and snapshotted by the resolver; Group 54 item 6a verifies all six fields with six independent tamper controls |
| D2 | The report→projection→CLI path was described only in outline | §7.4.1 maps it field by field for the applied and quiet cases: collection, projected model, `reason_id`, seven `params` keys, CLI renderer input, and the exact output sentence |
| D3 | One authoritative source was asserted but the mechanism was unspecified | Design 2 chosen **from evidence** — `drivers` is built only from `report.entries`, `LedgerEntry` requires an amount a movement lacks, `trace` is collapsed by default — with `MovementReport` still authoritative and Group 54 proving entry↔row agreement, plus a disjointness test separating rejection codes from report reason ids |
| D4 | Rendering tests were surface-level | Seven applied-movement assertions, five quiet-turn assertions, six independent tamper controls, and a cross-surface consistency assertion |
| D5 | "Commit 5 regenerates the contracts and commits the measured zero-drift result" — zero drift means nothing to commit | Generator run during verification, both files required byte-identical, **nothing staged or manufactured**, result recorded in the verification report; commit 6 commits the genuine delta |

## 13.6 Revision 3d issues corrected in Revision 3e

| | Issue | Correction |
|---|---|---|
| E1 | Both `REASON_RENDERERS["formation_moved"]` **and** `_print_movement_report` were scheduled to print applied movements; the traced call graph shows both CLI paths run the entry loop *then* the report blocks, so the identical sentence would print **twice** in each | §7.4.2: entries print applied movements; the helper prints **only** the quiet sentence and emits nothing for a nonempty report. Summary/detail split rejected because, unlike W1, movement has no distinct numeric detail. Occurrence-**count** tests on complete output, for both commands |
| E2.1 | §7.5 said movement surfaces through `DriverItem` / `LedgerEntry`, which D2/D3 had already rejected | Applied → `DriverItem`; quiet → `unchanged`; `LedgerEntry` explicitly rejected for its required `amount_text` |
| E2.2 | The dependency table said commit 5 carried "contracts if any" | Replaced with the measured outcome: generator verification, artifacts byte-identical and not staged |
| E2.3 | §13.4's C3 row still said commit 5 "regenerates and commits the measured result" | Replaced with the D5 wording: verifies zero drift without staging; commit 6 commits the genuine endpoint delta |

**Preserved unchanged (E3):** both theater display-name fields, the seven canonical `formation_moved`
parameters, entry-to-row reconciliation, the quiet `unchanged` API sentence, the two disjoint
reason-code namespaces, commit 4's classifier-only boundary, commit 5's atomic
acceptance/application/reporting boundary, contract timing, the roster, movement cost, reachability,
scenario authorship, frontend behaviour and the mockups.

## 14. Explicit exclusions

Navy, Air Force, combat, interception, casualties, occupation, annexation, control transfer,
foreign entry, military access agreements, insurgency, arms industries, alliances, sanctions and
proxy wars are all **out of scope**, and none is designed for or prepared here. Sea and air
movement additionally **cannot** be built on shipped data: `RouteKind` has only `LAND` and
`TheaterKind` only `LAND`/`COASTAL`, so they require authored sea/air geography under their own
mandate.
