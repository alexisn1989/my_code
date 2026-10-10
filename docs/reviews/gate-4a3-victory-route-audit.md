# Gate 4A3 victory-route audit: can a player win, through the interface, in each shipped scenario?

**You asked for this before any victory-visibility plan.** The question was whether the problem is
visibility, inaccessible actions, or both.

**Short answer:**
- **Every shipped scenario has a legal route from a new campaign to victory, and the interface can
  carry it out.** All three routes were replayed through the installed playtest build and ended in
  victory.
- **The problem is mainly visibility**:
  - the objective, the current stage and the qualifying transition are not shown where a player
    looks;
  - the turn result understates the reform.
- **There is one interaction obstacle in Valdrun:** the obvious reform is refused, with a message that
  doesn't say what to change.

**This is an audit only.** No code, test, threshold or build changed. The playtest build is
`083c7a98…`, from `5236ddb`.

The evidence is in [`gate-4a3-victory-route-audit/`](gate-4a3-victory-route-audit/):
- `engine-search/` holds the routes;
- `interface-replay/` holds the replay records and screenshots;
- `tools/` holds the two search harnesses and the Playwright spec, copied verbatim.

## 1. The engine's victory rule (read from the code)

1. **The qualifying transition** (`app/simulation/phases.py:1010–1023`) is an **enacted**
   constitutional amendment that takes the constitution from non-competitive to competitive-elected.
   - **Non-competitive:** a hereditary or appointed executive, or any decree authority other than
     `none`.
   - **Competitive-elected:** an executive chosen by direct election or by the legislature, decree
     authority `none`, and a national election interval set.
2. When that happens, the engine sets `pending_liberalization` with `set_at_turn`
   (`phases.py:2559–2564`).
3. **Victory** (`phases.py:4740–4748`) comes from **winning a national election on a later turn than
   that marker**. The outcome is `VICTORY`, with reason `PEACEFUL_LIBERALIZATION_COMPLETED`.
4. **Losing that election is `ELECTORAL_DEFEAT`.** The checklist being met is therefore not victory,
   which matches your caution about a percentage bar.

## 2. What each scenario starts with

| scenario | executive | decree | election interval | amendment threshold | what must change |
|---|---|---|---|---|---|
| `deficit_demo` | direct election (presidential) | `emergency_only` | 20, election at turn 20 | simple majority, one chamber | decree authority only |
| `tiny_valid` | legislative selection (parliamentary) | `emergency_only` | 16, election at turn 16 | supermajority, two chambers | decree authority only |
| `decree_state` (Valdrun) | hereditary (monarchical) | `unlimited` | **none**, so no election | supermajority, one chamber | executive selection, decree authority **and** an interval, plus a companion change to the executive system (§4) |

**Amendments cannot be decreed while a legislature sits.** The reform cards say so: "A decree cannot
amend the constitution while a legislature sits; this reform must go to a vote." Every route is
therefore legislative.

## 3. The routes the engine accepts (default seed, from a new campaign)

**Method.** `tools/victory_search.py`, then `victory_search_v2.py` for Valdrun, plays each scenario
through `TestClient(create_app(…))`, choosing only from the served decision options and accepting
only what `/api/game/preview` says passes and is affordable.
- Before the transition, each turn it tries the reform with no influence, then influence on one bloc,
  then influence on two, then with each willing bargain.
- Otherwise it invests capital in relationships.
- After the transition it invests and waits for the election.
- It **reads** the engine state only to record the marker, the next election and the outcome.

| scenario | route | result |
|---|---|---|
| `deficit_demo` | **turn 0:** decree authority → `none`, legislative route, **300 influence on the Citizens' Bloc hardliners**, which carries **53 of 51 needed**. Turns 1–19: relationship investment | **victory, turn 20**: the election was won with 65.42% |
| `tiny_valid` | **turn 0:** decree authority → `none`, **395 influence on the National Front conservatives plus Maret Kuusk's bargain (105)**, which carries **69 of 67** (lower) and **40 of 40** (upper). Turns 1–15: relationship investment | **victory, turn 16**: 66.72% |
| Valdrun | **turns 0–1:** invest 200 each in Crown Party Core and Reform Opposition Main. **Turn 2:** the **four-axis** reform (decree `none`, direct election, **presidential** system, interval 4) with **468 influence on Reform Opposition Main**, which carries **72 of 67**. Turns 3–6: relationship investment | **victory, turn 7**: 64.38% |

**What these routes do not establish:**
- **They are one route each, at the authored seed.** They show that victory is reachable. They don't
  show it is likely, or forgiving.
- The existing interface campaign `T21` (`e2e/campaigns.spec.ts`) **loses** Valdrun's election on
  turn 11, with a different reform (interval 8, term limit 2) and less investment. **Reform does not
  guarantee a win.**
- **Reform raised coup risk**, to 10.72% for one turn in Valdrun, and 2.18% and 2.88% in the others.
  Liberalisation is a dangerous stretch, as you anticipated.
- **The card-by-card Valdrun route is not tested.** Three separate supermajority votes (interval, then
  government form, then decree), with only the last one qualifying, look possible from the cards'
  availability. I did not play it.

## 4. The one interaction obstacle (Valdrun)

**The natural three-axis reform is refused before any vote:** decree `none`, direct election, and an
interval. The refusal is HTTP 422, which the interface shows:

> "This change would leave the constitution internally inconsistent; it needs a companion change to
> another part of the constitution."

**What the message leaves out:**
- It **does not say which part.** The missing companion is the executive system: a monarchical
  executive cannot be directly elected.
- The first search did not know this, so it **never found a valid reform in 60 turns**. A player would
  meet the same wall.
- With `executive_system: presidential` added, the reform is valid and goes to a vote.

**The cards hide the same coupling.** The government-form cards bundle system and selection together,
for example "Reform to presidential, direct election". But a player who builds the reform in
"Customize policy" (which is collapsed by default) has to discover the coupling themselves.

## 5. Replay through the interface (installed playtest build)

**Method.** `tools/victory-routes.spec.ts`, run with Playwright against a fresh server from the
installed archive `083c7a98…` (fresh save root, 1440×900).
- **The actions a player takes:**
  - **Decisions:** "Customize policy", then "Constitutional amendment", then the axis dropdowns and
    the election-interval number;
  - the "Route" radios, which stay on "Legislative vote";
  - the "Influence capital for {bloc}" and "Relationship investment for {bloc}" inputs;
  - for `tiny_valid`, the **Relationships** screen's leader row, then "Add to this turn's draft";
  - "Preview", then "Resolve turn", then "Confirm and resolve", then "Plan turn N".
- **Asserted every turn:** the decisions the interface sent to `/api/game/resolve` **equal** the
  engine route's recorded decisions. On each reform turn, the interface's own preview says it passes.
- **At the end:** the campaign is `VICTORY`, read back on the "Victory / defeat" screen, with **no
  console errors**.

**Result: `3 passed (19.0s)`.**

| scenario | turns played through the interface | outcome on the Victory / defeat screen |
|---|---:|---|
| `deficit_demo` | 20 | "Victory: peaceful liberalization completed, turn 20." |
| `tiny_valid` | 16 | "Victory: peaceful liberalization completed, turn 16." |
| Valdrun | 7 | "Victory: peaceful liberalization completed, turn 7." |

**The actions are all reachable.** The problem is not missing controls.

## 6. What the player could see along the way (screenshots in `interface-replay/*-shots/`)

| moment | what is shown | what is missing |
|---|---|---|
| **start**, Dashboard goal card | "Your priority: An election is scheduled for turn 20." (or turn 16); in Valdrun, "**Nothing is pressing.** Consider how to use your political capital." Then the static win/loss sentence | the **objective's stage** (reform not yet done); **which conditions are already met** (two of three in `deficit_demo` and `tiny_valid`); **what to do next** |
| **reform preview** | the vote tally, and "Would pass" | any statement that **this reform is the qualifying step** |
| **reform turn result** | headline "Amendment passed, 72 of 100 seats (67 required)." and **"The constitution was amended." repeated once per changed axis**, with no axis named (three times in Valdrun) | which condition changed, and that the campaign is now **one election from victory** |
| **after reform**, Dashboard | goal card: "**Your priority: Coup risk 10.72%.**". The header now says "Presidential republic, no decree authority · Election: Turn 7". The **only** progress signal is the third Alerts item: "A liberalizing transition is pending confirmation at the next election." | the new objective ("win the election at turn 7"), on the card the player reads first |
| **Constitution screen** (all along) | one summary card ("Supermajority"), then "**Not in this version of the game**" | the checklist |

## 7. Defects found on the same screens (recorded, not fixed)

- **D-V1:** the reform's turn result gives one generic "The constitution was amended." line **per
  changed axis**, unnamed. This is the same class as the generic driver lines UX-4e fixed for other
  reasons.
- **D-V2:** "What your decision committed" shows the influence target as a **raw identifier**, for
  example `opposition_party/main` or `national_front/conservatives`. That is the class T1/T2 closed
  elsewhere.
- **D-V3:** "What did not change" says "**No policy proposal was submitted.**" on a turn whose
  constitutional amendment passed. The line evidently means "no budget", and contradicts the turn.
- **D-V4 (§4):** the incoherent-amendment refusal doesn't name the companion change it needs.

## 8. Conclusion, for the plan you asked to see next

**The actions exist and work, so the gap is visibility,** together with one unhelpful refusal (D-V4)
and three result-wording defects (D-V1 to D-V3) on exactly the screens your proposal touches.

**Everything your proposal needs is already in the engine state:**
- the constitution's three conditions;
- `pending_liberalization` and its `set_at_turn`;
- `next_election_turn`;
- the existing survival and election information.

**The stage can therefore be derived from the engine's own eligibility and marker,** not from how
the constitution looks, as you asked. The bounded plan follows separately, for your approval.
