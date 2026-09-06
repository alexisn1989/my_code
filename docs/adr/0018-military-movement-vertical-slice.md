# ADR 0018: Military movement — orders, application and reporting, with no consequence of location

- Status: accepted
- Date: 2026-09-06

## Context

Gate M0 gave the game territory: theaters, capitals, directed routes and sovereign shapes, all
read-only. Nothing occupied that territory and nothing moved across it. A player could look at the
map and issue no order against it.

This slice makes a formation's location a **real, ordered, persisted, reported fact** — and
deliberately nothing more. It is infrastructure, not the first slice of a war game. Shipping
movement costs, supply, readiness or combat resolution on top of a model that has none of them
would put affordances on screen the engine cannot honour, which is the same failure ADR 0016
refused for "Join war" and ADR 0017 refused for troop icons over a read-only map.

The frozen plan is `docs/plans/military-movement-vertical-slice-implementation-plan.md`
(SHA-256 `7826ecc5ae7057b8305bd2174d7f896ff24175643cf8eb89cf7d551be974f25f`), byte-identical
throughout the slice.

## Decisions

### One classifier, one source of legality

`app/simulation/military.classify_destinations` is the single implementation of movement legality.
The draft preview, the authoritative submission validator and the `/api/game/military` projection
all call it; none re-derives the rule. That is why the three cannot disagree about what is legal or
about why, and it is enforced rather than asserted: the projection's verdicts are compared row for
row against the classifier's across all three shipped scenarios.

**Ownership is checked before reachability, and the ordering is load-bearing.** A foreign-owned
theater reports an ownership failure whether or not a directed route reaches it. Reporting the
routed one as "no route" would imply that authoring a route would authorize entry — false, since
foreign entry is excluded by product decision, not by graph topology.

Exactly one edge is traversed. No BFS, no multi-hop, no undirected adjacency. An incoming-only
route is not an outgoing one, and the two-hop case gets the same honest single sentence as any
other unreachable player theater: producing a "reachable through another theater" message would
require the traversal this slice forbids.

### Acceptance and application land together

Commit 4 added the classifier and deliberately accepted **no new player action**. Commit 5 then
added decision acceptance, authoritative validation, slot-8 application, reporting, reconciliation
and both presentation surfaces **in one commit**.

That grouping is the point. An intermediate state where a player could submit a valid
`military_movement` decision, have it accepted, and have the turn resolve with the order silently
discarded is a defect no amount of focused validation testing makes safe, because the defect is the
externally observable behaviour rather than the tests. At the end of commit 5, every accepted legal
movement is applied exactly once and reported exactly once.

### State, decisions and ordering

`MilitaryState` nests under `CountryState`, keyed by formation id. Movement is a fourth decision
kind, `military_movement`, sorting last of the four; a collection of orders capped at one by a
**validator** rather than by the shape, so raising the cap later changes a constant rather than
migrating a decision shape or re-issuing a discriminator.

Every ordered collection is **rejected, never normalized** — noncanonical orders, duplicate
formations and out-of-order decision sets are refused rather than sorted, because these payloads
are serialized into `decisions_json` and hash-covered. Two semantically identical submissions in
different orders would otherwise digest differently.

Slot 8 gained a substep before the unchanged W1 progression. `PHASE_ORDER`'s fifteen ids, their
order and their contract are untouched, and slot 9 — whose name promises casualties, occupation and
war costs — was not borrowed for redeployment.

### Reporting and reconciliation

`MovementReport` is the fourteenth domain report, present on every resolved turn and empty on a
quiet one. Present-and-empty rather than absent: an absent report means the audit chain is broken,
which is a different statement from "nothing happened", and thirteen present alongside a missing
fourteenth is exactly the proper subset the completeness rule exists to reject. Adding it doubled
the exhaustive completeness run from 8,190 subsets to 16,382; the check was not weakened to avoid
the cost.

Rows are **self-contained**, carrying both theater display names alongside the ids. A historical
turn therefore renders from the report written when it happened, never by resolving names from
current state, and a raw id never becomes fallback player-facing text.

Reconciliation Group 54 proves the submitted decisions, the opening-to-closing transition and the
report agree — with ten negative controls and six single-field row tamper controls, one per field,
because a single combined control would let five of the six checks be absent without failing.

### API and frontend

`/api/game/military` is revision-keyed and separate from the strategic map, which is
campaign-static and cached with an infinite stale time. Positions change every turn; serving them
from the map's query would show stale positions with no refetch. The collection is
`destination_options` and carries the **ineligible** theaters with their reasons, because the
interface has to explain an unavailable destination and cannot explain what it was never given.

The map **stages** an order and never resolves the turn. Resolution stays on the Decisions screen;
a second way to end a turn would be a competing authority. Confirming on the map returns control to
the shared turn draft.

Formations render in a bounded fan: six per theater, then five icons and one `+N` control that
**occupies a slot** rather than being a seventh marker squeezed between six — which is what makes
the non-overlap provable. Six is a rendering ceiling and never a gameplay one; the state model caps
formations per theater at nothing, and the renderer must not become the reason a limit exists. Slot
0 opens away from the theater's own name, because a naive fan starting due north puts it through
the label of three of `tiny_valid`'s five theaters.

The **textual list is the accessible source of truth and never clusters.** No formation becomes
unreachable because its icon was clustered, and the whole interaction completes with the keyboard
alone, in the narrow layout where no SVG renders at all.

## Measured facts

- Ruleset `0.15.0`, content `0.15.0`, save format `1` (unchanged).
- Contract: `0.15.0`, **55** schemas and **13** paths. Commit 5 added no schema at all — the
  `Decision` union never reaches the contract, because `ResolveRequest.decisions` is declared
  `tuple[dict[str, Any], ...]`, and `TurnReport` is not in the schema. Commit 6 added exactly
  `MilitaryProjection`, `FormationProjection`, `DestinationOption` and `/api/game/military`.
- Backend suite grew from 10,873 (commit 3) to 19,316; frontend from 189 to 277. The great
  majority of the backend growth is the completeness run's doubling — 8,190 subsets to 16,382 —
  rather than new behaviour.

## Gate evidence

A real-browser walkthrough drove Chromium against a production build served by the real backend in
its single-process shape — one Uvicorn worker, because a second would be a second divergent
`GameSession`. Six steps at 1440×900 plus one narrow pass at 820×900, each with a SHA-256 over
its screenshot, and each screenshot checked against its own metadata rather than trusted.

It showed a formation drawn at its authored theater; two eligible and three ineligible destinations
each with its reason in words; exactly one arrowhead at the destination end of the planned route;
the order staged with the map returning to idle; resolution performed on the Decisions screen; the
formation at its new theater afterwards with the staged order cleared; and the same order staged at
a narrow viewport where the picture does not render at all.

The evidence is delivered with the gate report and is not committed, matching M0.

**One harness defect is recorded rather than hidden.** The first walkthrough script's narrow pass
failed: it opened a fresh browser context and tried to reach the map, but a new context holds no
client session, so the application correctly disables map navigation until a game is started. That
was a wrong test against right behaviour. The failing record was preserved and a corrected narrow
pass run separately.

### Deviations from the frozen plan, recorded

- **The scoped `0.14.0` regression comparison.** The plan states that the closing state excluding
  `countries[*].military` is byte-identical to the frozen baseline. Measured, it also differs in
  `ruleset_version` and `content_version` — which *are* the bump the fixture exists to record, and
  cannot not differ. Rather than widen the exclusion helper and weaken every other comparison, the
  helper removes exactly the two documented paths and the test pins the entire remaining difference
  as an exact set, so a third differing field fails rather than disappearing.
- **`destinationSelected` and `orderReview`** are implemented as one rendered state. The plan's
  diagram shows two boxes but describes the transition between them as automatic; splitting them
  would have required inventing an intermediate click the plan never describes.
- **The "focusable overflow control"** is served by the textual list rather than by the picture,
  because M0's SVG is `aria-hidden` and carries no keyboard stops by design. The marker still takes
  the selected styling when it hides the selection, so a clustered selection is never invisible.
- **Route insertion order** cannot be tested for independence: `StrategicMapState` rejects a
  noncanonical route sequence at construction, so the reordered map does not exist. The stronger
  guarantee is asserted instead.

## Consequences

A formation's location is now authoritative, ordered by the player, applied by the engine,
persisted in the save, covered by the hash chain, reconciled against its own report, and rendered
from that report on every surface. Later military systems have something real to stand on.

The cost is a required field: `CountryState.military` is mandatory for the player country from
ruleset `0.15.0`, every scenario authors a roster, and pre-`0.15.0` saves are unloadable. That is
the intended trade, and the same one M0 made for `strategic_map`.

## Limitations

**Location has no gameplay consequence.** This is the single most important thing to know about
this slice, and it is deliberate rather than unfinished. A formation is in a different theater
after a movement turn, and nothing in the engine reads that fact.

Specifically, and each is something a player might reasonably expect and will not find:

- Movement is **free**: no political capital, money, time or opportunity cost.
- There is **no combat, no casualties, no occupation and no war-cost mechanic**.
- There is **no supply, readiness, morale, fatigue or reinforcement model**.
- There is **no transit**: movement completes at turn close, and there is no in-transit state to
  model or to interrupt.
- **Foreign entry is impossible**, by product decision rather than by topology.
- Formations have **no strength, composition or equipment** — a formation is an identity, a branch
  and a location.
- `FormationBranch` has a **single member**, `army`. Naval and air branches are not modelled.
- **One order per turn**, per ruleset `0.15.0`.
- A formation's location affects **no existing mechanic**: not legitimacy, not the foreign-conflict
  progression it shares a phase slot with, not coup risk, not the economy.

### M0's prerequisite for interactive movement, and how it was met

ADR 0017 required, before troop icons or movement orders, a larger interaction-focused map surface
**or** deterministic zoom/pan, with larger effective labels and appropriate hit targets.

This slice took the first branch: an enlarged map mode giving the picture roughly 63% of the row
rather than half, with the same authored `0 0 10000 10000` viewBox and the same geometry — more
pixels, nothing rescaled or recentred. **Zoom and pan were not added**, and remain available as the
answer if a future gate finds the enlarged mode insufficient. The browser walkthrough is the
evidence that the interaction is operable at the shipped size; it is not a claim that no larger
surface will ever be needed.

## Expansion boundary

Nothing here designs cost, combat, supply, readiness, transit or a naval or air branch. The
one-order cap, the single branch and the absence of consequence are current facts of ruleset
`0.15.0`, not architectural commitments — but each becomes a decision only when a mandate audits
and plans it. In particular, the honest next question is not "what else can move" but **what
movement should cost**, since a free action with no consequence is not yet a strategic choice.
