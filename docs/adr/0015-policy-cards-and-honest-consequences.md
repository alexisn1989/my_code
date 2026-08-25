# ADR 0015: Policy cards and honest consequences — Gate 4A3A

- Status: accepted
- Date: 2026-08-25

## Context

Gate 4A2 shipped a playable vertical slice, but the Decisions screen was a single raw editor: a
radiogroup choosing "Budget" or "Constitutional amendment," then bare number inputs and `<select>`s
keyed directly off server enum identifiers. It never showed the player *what a decision would
change* before they built it by hand, never explained *why* an option was unavailable beyond a
disabled control, and blended a preview's honest uncertainty together with a resolved turn's actual
outcome inside the same presentational vocabulary.

Gate 4A3A replaces that with a political-strategy-game card-based loop: see options → understand
effects → select → route → bargain → preview → resolve → see outcome. This ADR records the
architecture, built entirely on top of ADR 0014's existing rules (no simulation arithmetic in
TypeScript, the Python engine as sole authority) — Gate 4A3A adds no formula, mechanic, or
calibration of its own.

## Decisions

### The server authors the policy-card catalog; the browser never calculates legality

`backend/app/api/policy_cards.py` builds every card (`PolicyCard`/`PolicyCardRoute`/
`PolicyCardEffect`, `backend/app/api/projections.py`) by constructing a throwaway `DecisionSet` per
candidate template and re-running `first_decision_problem` — the exact same structural preflight
`/preview` already used — never a second, independently-derived legality check. This is what makes
the guarantee mechanical rather than conventional: a card can only claim "available" if the shared
preflight agrees, so the catalog and `/preview` cannot silently disagree about what is legal.

Every unavailable card or route carries a stable `PolicyCardUnavailableReason` enum value plus a
player-facing detail string — never a raw internal exception, never a bare diagnostic code leaked
into prose (enforced by a self-validator comparing the stored detail against the actual
`diagnostic_code`, not a guessed prefix).

Rejected: computing availability client-side from `DecisionOptionsProjection`'s raw bounds (would
require re-deriving `first_decision_problem`'s logic in TypeScript — exactly the forbidden
"simulation arithmetic outside the engine" ADR 0014 already rules out); silently omitting
unavailable cards (the mandate requires every option to be visible with a reason, never hidden).

### Two-level progressive disclosure, never 33–45 cards flat on one screen

A shipped scenario's catalog runs 44–45 cards. `frontend/src/greybox/policy/groupPolicyCards.ts`
groups them into three fixed majors (Budget, Constitutional reform, Take no major action) and, for
Constitutional reform, four families derived from stable `card_id` prefixes
(`constitution_decree_authority_`, `constitution_government_form_`, `constitution_term_limit_`,
`constitution_election_interval_`) — never from card order or a hand-maintained list.
`PolicyCardGrid.tsx` renders this as an accessible `role="tablist"` at each level, with roving
tabindex arrow-key navigation and a result count on every tab.

### Selecting a card never auto-previews, auto-resolves, or spends capital

`applyCard` (`frontend/src/state/draft.ts`) only replaces the relevant draft slot from the card's
template; `chooseCardRoute` (`frontend/src/state/applyPolicyCard.ts`) decides which route to apply —
preserving the player's prior route when the new card still offers it (R5), otherwise falling back
to the card's first available route and reporting the change via a `role="status"`/`role="alert"`
announcement. Preview and Resolve remain separate, explicit player actions, exactly as before.

### The existing detailed editor is preserved, not replaced

The full original radiogroup-plus-inputs editor still exists verbatim, under a collapsed
`<details><summary>Customize policy</summary>` section beneath the card grid. Power users lose no
functionality; the card grid is the new *default* path, not the only path.

### Consequences are three honest groups, never blended

`ConsequencesPanel.tsx` renders exactly two of the three: **known before resolution** (from
`PreviewProjection`, itself explicitly labelled an estimate) and **uncertain / excluded** (the
server's own list of stochastic channels a preview cannot claim). The third — **actual after
resolution** — is deliberately not this component at all: it is the pre-existing, separate
`TurnResultView.tsx` on a different screen, reading only stored `TurnResultProjection` fields. A
"what we expected" table and a "what happened" table can therefore never share a row or a heading by
construction, not by convention.

### The format-boundary and raw-data-boundary AST tests extend to every new file

`frontend/src/format/format-boundary.test.ts` (arithmetic outside `src/format/**`) and
`frontend/src/raw-data-boundary.test.ts` (no raw JSON dumps in the rendering layer) already parse
every non-test source file with the real TypeScript compiler API; Gate 4A3A's new files
(`groupPolicyCards.ts`, `applyPolicyCard.ts`, `PolicyCardGrid.tsx`, `PolicyCardView.tsx`,
`ConsequencesPanel.tsx`) are covered by the same structural scan, not a new, parallel check. Two real
violations were caught this way during development (roving-tabindex modulo arithmetic; a
route-change announcement built with string concatenation) and fixed by moving the computation into
`format.ts` or rewriting the expression, not by weakening the guard.

### Presentation gaps are fixed with label maps, not new client logic

A pass over the shipped UI found several real presentation defects, unrelated to card legality:
raw server enum values shown verbatim (`alert.severity`, spending-category and constitutional-axis
identifiers), a nullable axis rendering the literal string `"null"`, several visually identical
"Details" buttons sharing one accessible name, and `ToneValue`'s own docstring promising a glyph plus
a visually-hidden word that the implementation never provided. Each is a pure string-to-string
display map (`SEVERITY_LABEL`, `AXIS_LABEL`, `AXIS_VALUE_LABEL`, `SPENDING_CATEGORY_LABEL`) or a
static glyph/label table — never arithmetic, never a legality decision, so none of it belongs behind
the format-boundary guard; all of it is covered by ordinary component tests.

## Consequences

- The card catalog duplicates some information already present in `DecisionOptionsProjection`
  (raw bounds, seats) in a friendlier shape. This is deliberate: the catalog is the presentation
  layer's contract, and `DecisionOptionsProjection`'s raw fields remain available for the preserved
  "Customize policy" editor.
- `policy_cards.py` re-running `first_decision_problem` once per candidate template (up to ~45 per
  request) is more work per `/api/game/decision-options` call than the old single structural check.
  Measured against all three shipped scenarios via `scripts/smoke_gui.py` over real HTTP: no
  observable latency problem at this scenario size.
- Two real backend defects were found and fixed while building the catalog, before any test could
  encode them: government-form cards submitting no-op targets alongside real changes, and spurious
  diagnostic codes attached to cards whose real rejection reason was not a coherence violation.
  Neither is a Gate 4A3A feature; both are corrections to existing `policy_cards.py` logic written
  in this same gate.
