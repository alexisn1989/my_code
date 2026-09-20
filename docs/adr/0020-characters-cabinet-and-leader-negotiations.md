# ADR 0020: Characters, cabinet appointments and leader negotiations

**Status:** accepted. Ruleset `0.17.0 -> 0.23.0` across the slice. Content `0.16.0 -> 0.19.0`.
**Supersedes, in part:** the repeated deferral of "characters, cabinet ministers, and any named-actor
layer" recorded in `docs/product_spec.md` and `docs/roadmap.md`. It supersedes nothing about
legitimacy neutrality (ADR 0009), government-form exposure (ADR 0019) or the expenditure-target
model (POL-4, which this slice leaves open with two further entries against it).

## The gap

MANDATE had no people in it. The player governed offices and institutions: a coup was a fact about
the military institution, a vote a fact about a bloc, a foreign actor a display name and a
war-capability number. Every Gate 3C removal reason "describes the office, never a person", by
design and by explicit deferral.

That is a defensible model of a state and a poor model of governing one. The decisions a head of
government actually makes are with people who have their own interests, who remember what was
promised, and who behave differently towards someone who has kept their word than towards someone
who has not. None of that was representable, and no amount of tuning the office-level formulas would
have made it so.

## Decision

`CharacterState` — scenario-authored, keyed by stable id — carries five bounded basis-point traits,
and **each one has a named, tested consumer**. A trait with no consumer is decoration, so the rule is
structural rather than aspirational:

| trait | consumer |
|---|---|
| `competence` | office performance — the chief-of-staff bonus to relationship investment, the foreign minister's share of an assistance grant |
| `loyalty` | willingness to accept an appointment, and the bargain gate |
| `independence` | the appointment surcharge and the bargain's asking price |
| `ambition` | which office a candidate will accept, and the asking price |
| `personal_trust` | the only value moved by kept and broken promises; read by both negotiation assessments |

`personal_trust` is trust in *the player*, and is deliberately distinct from `InstitutionState.loyalty`
(an institution's loyalty to the office) and from a bloc's government relationship (a caucus's
standing). One source of truth each; no character score is ever copied into a bloc or an institution.

Four mechanics read those traits, and each is a separate pure module over metrics, importing no state
models: `cabinet.py` (appointment cost and refusal), `legislative_bargaining.py` (gate, price and
endorsement), `foreign_assistance.py` (bilateral standing, the finite pool and the granted share) and
`promises.py` (the vocabulary of what may be promised and what it is worth).

**Trust moves on events only** — a kept promise is `+1,000` bps, a broken one `-2,000` — with no
per-turn drift. That keeps it discrete, auditable, and free of a new per-turn state write. The
asymmetry is the design: trust is slow to build and quick to lose.

**The constants are measurements, not preferences, wherever a mechanic could otherwise be inert.**
`LEGISLATIVE_ENDORSEMENT_BPS = 2,000` was set by sweeping every reachable proposal shape against all
three scenarios: at 1,200 bps the endorsement could not change a single vote outcome through any
counterparty who would accept it, and shipping it would have sold the player something that did
nothing. `PROMISE_KEPT_TRUST_GAIN_BPS = 1,000` was chosen because two kept promises flip no shipped
leader from refusal to agreement and three flip all three — a discriminating demonstration rather
than an approximate one.

## One writer, and one definition per rule

`phases._commit_promise_settlements` is the **only** writer of `personal_trust` anywhere in the
repository, enforced by an AST sweep that fails any assignment or `model_copy(update=...)` naming it
elsewhere. The three negotiation modules keep reading trust and gain no write path.

The same discipline is applied to rules that two surfaces must agree on. Preflight and the resolver
draw every promise rule from the same production helpers; `release_block_reason` is one function
whose four cases are total over the resolver's whole rejection domain; the decree-route rule is one
predicate, `bargain_route_is_legislative`, used by both. That is not tidiness: **forcing two surfaces
onto one definition found real defects three times in this slice** — a qualification hole that let a
forged `qualifying_turn` reconcile clean, a release that could be paid for twice, and a release that
could duck an imminent breach.

## Reconciliation as an independent oracle

Groups 56–60 reconcile the five new subtrees, and each **transcribes** the formulas it checks rather
than calling the production function that produced the report. A check that calls the same function
cannot fail when that function is wrong — it agrees with the defect and certifies it. The boundary is
enforced by AST allowlists that permit calibration constants and refuse function calls, with
anti-vacuity plants so a scan that matches nothing cannot pass silently.

The line is **calibration versus behaviour**, not constant versus function. Group 60 may import the
four trust numbers, because a number both sides read still surfaces a transcription error; it may
**not** import `MAINTENANCE_TERMS`, `LIVE_PROMISE_STATUSES` or the status-to-reason mapping, because
those are behavioural classifications and sharing one would make reconciliation repeat any
misclassification and then certify it. Paired agreement sweeps then assert each transcription equals
its production counterpart over the full domain, so independence does not silently become divergence.

Two defect classes this found are worth naming, because neither is reachable by the usual
single-surface tamper:

- **Coordinated tampers** — state, report, entries and trust all agreeing while the RULE is wrong.
  Group 60's re-derivation of qualification is what catches them.
- **Vacuous proofs** — a check whose loop body never executes. A decree turn carries zero bloc vote
  rows, so group 58's per-bloc endorsement check passed *without running* on precisely the turn where
  an endorsement bought nothing. That was measured, not theorised: a decree budget plus a bargain
  resolved ACCEPTED, charged the asking price, reported `endorsement_bps = 2,000`, produced no votes
  at all, and reconciled clean. The fix is a route check **before** the loop, plus a submission
  refusal so the state is unreachable in the first place.

## The decree-route refusal

A bargain buys support in a chamber vote. A decree is the act of not asking the chamber. Buying
support for a vote that will not happen is therefore refused at submission —
`legislative_bargain_requires_legislative_route`, the seventh rejection code, evaluated after the
proposal-absent check because a route is only meaningful once the proposal has been found.

The alternative — hiding decree bargains client-side — was rejected explicitly: it would have created
frontend-only legality, where the same set submitted by any other route still resolved. The backend
is authoritative, and the panel merely declines to stage a draft it has been told cannot resolve,
with visible copy saying why.

This is the ruleset bump to `0.23.0`, and it is an honest one: a decision set the `0.22.0` engine
accepted is now refused, so replaying `0.22.0` decisions under `0.23.0` rules does not reproduce the
`0.22.0` turn.

## Portraits, and what they are not

Every authored character carries a `portrait_ref`, projected verbatim onto the four row types the
Relationships panel renders. The client draws a face from that reference and **never** from a
character id: deriving a likeness from an identifier would invent an appearance the content never
described. There is no fallback — a missing or unknown reference is a test failure, because a
fallback would let an unauthored character ship silently.

The shipped depiction is a greybox SVG: structure is constant (head, ears, brows, eyes, nose, mouth,
shoulders, collar, each tagged `data-portrait-part`) and appearance varies by a hash of the reference.
That split makes "this is a face" a property of the component, provable from the DOM, rather than a
claim about one hash landing well. An initials badge or a coloured disc was explicitly refused: a
badge is a label wearing a portrait's shape. **Real illustrated assets are future art production, not
deferred engineering** — this repository is an explicit greybox with no asset pipeline and a bundle
gate that binary assets would immediately make a live question.

This is the content bump to `0.19.0`, and it is unrelated to the ruleset one: a portrait changes no
resolution, and scenario shape is exactly what `content_version` exists to track.

## The counterpart's voice

Every counterparty row carries a first-person line composed from already-projected outcomes. The
lines carry **no figures at all**, and that is a mechanical constraint rather than a style: an earlier
design had the player name an offer, which left the field with exactly one rational value because the
price is projected, and the offer, the counteroffer and the price band were all removed. A line like
"would a hundred and fifty change your mind?" would smuggle that mechanic back through prose. Prices,
grants and deadlines are rendered separately, in their own labelled elements, and tests assert both
halves — no digit in a question, and the price still on screen — so the rule cannot be satisfied by
hiding the number instead.

## What this slice does NOT do

Recorded as limitations rather than left to be discovered:

- **No counteroffers, no price bands, no offer field.** Removed, not deferred. Reintroducing one
  needs a separate product decision, not an implementation.
- **No resignation.** The appointment gate is evaluated when an appointment is made and never
  re-assesses a sitting holder, so a legitimacy collapse does not empty the cabinet.
- **No character mortality, succession, scandal or ageing.** Rosters are static within a campaign;
  the only thing about a person that moves is their trust in the player.
- **No AI-country politics.** Foreign counterparts have a leader, a standing and a finite pool, and
  nothing more.
- **POL-4 stays open**, now with three expenditure categories against it — an appointment, a bargain
  and a promise release are all untargeted ledger rows because their real subject is a *person*, and
  `CapitalExpenditureReport` addresses a bloc.

## Compatibility

Every bump in the series rejects the older save rather than reinterpreting it, and each was preceded
by its own freeze commit capturing an authentic pre-change save from the unmodified engine, because
such a save becomes impossible to produce afterwards. `SAVE_FORMAT_VERSION` stays `1` throughout.

The two gates this commit moves are proved separately, because `check_compatibility` reports the
ruleset first and the pre-portrait fixture is old on both axes: the ruleset gate is proved on the
fixture as frozen, and the content gate on a copy whose ruleset stamp is moved forward, which is the
only shape that reaches it. A third test establishes what the usual "rejected before any payload is
parsed" wording actually proves here — `load_save_json` keeps every `state_json` as an opaque string
and parses none of them — so the falsifiable claim is that the same corrupted file with current
stamps loads cleanly and fails only when the state is read.
