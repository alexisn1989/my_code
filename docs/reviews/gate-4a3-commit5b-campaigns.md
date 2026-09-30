# Gate 4A3 (frozen-plan 4A5) Commit 5b — both campaigns, through the interface

**Subject:** `Gate 4A3 (5b/6): play both campaigns through the interface`
**Parent:** `5e61b945878f960d083901373e76f74db483583a` (Commit 5), not amended.
**Machine-readable evidence:** `gate-4a3-commit5b-campaigns.json`, `gate-4a3-commit5b-terminal.json`,
`gate-4a3-commit5b-verification.json`, `gate-4a3-commit5b-icon-coverage.json`,
`gate-4a3-accessibility-after-commit5b.{json,md}`.

Every browser gate before this one reached its state at least partly through the API, so a break
between the interface and a live server could pass all of them — finding **F11**. The frozen plan's
Commit 5 owed two walkthroughs that close it, and Commit 5 as authorized did not include them. This
commit plays both, **resolving every turn through the interface and none through the API**, and fixes
**T1** in the same change because T21 ends on the screen T1 is about.

Playing the game through its own controls found **two further frontend defects** that no earlier gate
could reach. Both are fixed here, each guarded by a unit test proved to bite.

---

## 0. A correction to Commit 5's record

Commit 5 reported T1 unfixed because *"that is a backend change, and Commit 5's scope fence is explicit:
no engine change"*. **The reasoning was wrong.** The fence forbade *engine* changes
(`app/simulation/**`); the fix belongs in the API layer, which the fence never covered. T1 was fixable
in Commit 5 and should have been. Commit 5's artifacts are left byte-identical as the record of that run
— including its `reason_label: "term_limit_exit"` — and the correction lives here.

---

## 1. T1 — fixed with authored wording, in the API layer only

New `backend/app/api/outcome_labels.py`, following `POST_DISPLAY_NAMES`: every `RemovalReason` and
`VictoryReason` member has one authored entry carrying a **label** (`"Term limit exit"`,
`"Electoral defeat"`, …) and the **phrase** the headline uses. It lives in `app/api/`, not beside the
other display maps in `state.py`, because no resolution reads it; `app/simulation/**` is untouched.

- `TerminalSummary.reason_label` is now the label. The headline uses the authored phrase, and the
  phrases are exactly the words the old `replace("_", " ")` produced, so **every headline a player has
  already seen is byte-identical** — asserted per reason. Only the label stops being an identifier.
- `save_registry._terminal_summary_text` made the same transformation for the save list; it now reads
  the same map, and its persisted text is pinned unchanged.
- **No fallback for a missing entry.** Indexing fails, and a test pins each map's keys to its enum by
  set equality, so a new reason cannot ship without wording.
- The contract is **byte-identical, 62 / 13 / `0.23.0`**: `reason_label` is a bare `str`. The
  hand-written `docs/contracts/phase4a-api-contract.yaml` still shows `example: electoral_defeat`;
  it is a Gate 4A1 design document and is recorded as stale rather than edited.

**In the browser**, a new helper (`e2e/player-text.ts`) reads what a player can actually read —
rendered text plus the player-visible attributes — and both the terminal spec (every concluded screen)
and T21 assert the reason identifier appears in neither. `check:copy` cannot make that claim: the
string arrives from the server at runtime.

`backend/tests/test_api_outcome_labels.py` adds **30 tests**.

---

## 2. T21 — `decree_state`, authored seed 77, entirely through the interface

The seed field was left empty, so the server kept the authored seed. Every figure below is the one
`backend/tests/test_liberalization_campaign.py` pins for the same campaign driven through the engine
directly.

| turn | through the interface | observed | engine test |
|---|---|---|---|
| 1 | `Relationship investment for Reform Opposition Main` = 85 | capital **798** | 798 |
| 2 | the same input = 118 | capital **1,000** | 1,000 |
| 3 | **Customize policy** → Constitutional amendment → decree `none`, selection `direct_election`, system `presidential`, term limit 2, interval 8; route Legislative; influence 300 → Preview | **67 of 100, 67 required, would pass** | 67 / 100 / 67 |
| 4–11 | eight empty resolves | concluded at **turn 11**, `defeat`, **"Electoral defeat"** | `ELECTORAL_DEFEAT` |

**Eleven resolves, all through `Resolve turn` → `Confirm and resolve`.** The confirm sentence names how
many decisions the interface is about to submit, and each turn asserts that count, so a draft that
silently lost or gained a decision would fail.

The Customize amendment editor had **no unit test at all**; this is its first proof, in a real browser.

**Not directly visible:** the opposition bloc's relationship figures (−5,385, −2,774) are carried by no
projection, so they are proved by what they cause — the 67-of-100 tally and the turn-11 election.

---

## 3. The new-features campaign — `deficit_demo`, one decision set

Every screen the frozen plan predates, composed in one turn against 300 opening capital:

1. **Decisions** — Customize → Budget: personal income 1225 bps, health 220,000,000 (the known-good
   budget from `test_legislative_bargain.py`; a bargain needs a proposal staged first).
2. **Government** — chief of staff → Bela Ronsard → confirm; the staged summary names the post.
3. **Relationships** — Sofia Renn's bargain (asking price 113), assistance from Marnil, and a
   legislative-support promise at the server's earliest deadline; all three appear in the staged summary.
4. **Decisions → Preview** — cabinet **147**, leader bargain **113**, promise release **0**, assistance
   estimate **26,250,000** (labelled as money received), **51 of 51 required, would pass**,
   **260 of 300 committed — affordable**.
5. **Resolve** — five decisions confirmed; Turn result carries a driver for each of
   `cabinet_appointed`, `legislative_bargain_accepted`, `foreign_assistance_granted` and `promise_made`,
   and reads "…backed the budget, for 113 political capital."
6. **History** — the same turn re-opened; its "Why this happened" list is **identical, text for text**,
   to the live one.
7. **Afterwards** — Relationships lists the promise as outstanding; Government shows the new chief of
   staff.

**F11 is closed**: this is the first automated test that plays Government and Relationships against a
live server.

**Same-origin, across both campaigns:** 78 requests, 12 distinct paths, **none off-origin**.

---

## 4. Two defects the walkthrough found, both fixed

**D5b-1 — the concluding turn's result said "This turn ended the campaign" twice.** `TurnResultView`
renders that panel with the headline, and `ResultScreen` wrapped its *Review the outcome* button in a
second `Panel` with the identical title, so the page carried two adjacent headings saying the same
thing. It renders only on the turn a campaign concludes — which is why no earlier gate reached it, and
why the T21 spec's first run failed on it (a strict-mode locator matched both). The action is now a
plain button row, exactly like the non-terminal branch beside it.

**D5b-2 — duplicate React keys in the drivers list.** `TurnResultView` keyed each driver by
`reason_id`, but one turn routinely emits the same reason several times — the real budget turn above
produced **five** `enacted_policy_relationship_reaction` and five `bloc_relationship_resolved`. Duplicate
keys can drop or repeat rows when a list re-renders. Keyed by position and reason now; the list is
static per render, so the position is a stable identity.

Both are guarded in the new `ResultScreen.test.tsx`, and **both guards were proved to bite** by running
them against the unfixed component.

**Consequence for the evidence:** the shipped JS changed, so every browser gate was re-run under
Commit 5b's own artifact names (one script per commit). The CSS is **byte-identical** to Commit 5's by
content hash.

---

## 5. Recorded, not fixed

**T2 — each driver line renders its `reason_id`.** Beside every driver sentence, `TurnResultView`
renders `<code>{reason_id}</code>`: an engine identifier shown to the player, T1's class. Measured on
the real turn: **27 of 27 painted**. No document settles whether it is intended — the frozen plan
§4.10 gives each driver a `reason_id` but says nothing about showing it — so whether to keep it as a
trace aid or remove it is a copy decision, not a bug fix. It is recorded with an owner to be assigned in
the Commit 6 closeout rather than absorbed here.

---

## 6. Gates

Each run separately, with its real exit status:

| gate | result |
|---|---|
| `ruff format --check .` | 186 files formatted |
| `ruff check .` | passed |
| bare `mypy` | 56 source files, no issues |
| `npm test` | **485 passed, 30 files** — +3, all in the new `ResultScreen.test.tsx` |
| `typecheck` / `build` | clean; JS 345.50 kB / 99.65 kB gzip; **CSS 18.49 kB, byte-identical to Commit 5 by hash** |
| `check:bundle` / `check:palette` / `check:copy` | clean |
| **`verify:campaigns`** | **7 passed** — both campaigns, every turn through the interface |
| **`verify:terminal:commit5b`** | 6 passed |
| `verify:fixes:commit5b` | 13 passed |
| `verify:icons:commit5b` | 7 passed |
| `audit:stress:seated` | 6 passed |
| `audit:accessibility:verify:commit5b` | **0 findings across 89 surfaces**, 4 needs-review |
| `generate:api` | byte-identical, **62 / 13 / `0.23.0`** |
| full backend suite | **36,277 passed**, 0 failed, 1 known warning, `PYTEST_EXIT=0`, 26:16 — +30, all in `test_api_outcome_labels.py` |

**The re-measured evidence is identical in content to Commit 5's.** `gate-4a3-commit5b-verification`,
`-icon-coverage` and `gate-4a3-accessibility-after-commit5b.{json,md}` are **byte-identical** to their
Commit 5 counterparts (checked with `cmp`); `gate-4a3-commit5b-terminal` differs in exactly one fact, the
`reason_label` — which is T1. So the two frontend fixes moved no measured figure, and that is shown
rather than assumed.

**Scope:** no `app/simulation/**` file, no scenario, no fixture, no frozen plan and no committed review
artifact appears in the diff; every earlier artifact is untouched.
