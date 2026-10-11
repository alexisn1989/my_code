# Gate 4A3 M-0: backend data for the map-led redesign

**Authorized by:** your answer "Approve visuals, start M-0". That approves the M-V visual direction
and authorizes M-0 only. Nothing is committed without your instruction.

**Scope:** additive `app/api/` projections that the later screens (M-2 to M-4) will read. **No screen
changes.**
- **Untouched:** the engine, ruleset, scenarios and save format. `git diff -- backend/app/simulation
  backend/data backend/tests/fixtures data frontend/e2e/fixtures` is empty.
- **No new endpoint:** 13 paths before and after.

## 1. What changed

1. **`DecisionOptionsProjection.chamber_details`:** each chamber's seats and the engine's own
   thresholds.
   - `budget_required_seats` comes from `required_yes_seats`.
   - `amendment_required_seats` comes from `required_amendment_yes_seats`, at the constitution's
     current difficulty.
   - **This replaces the M-V mockup's calculated budget threshold** with the engine's value.
2. **`BlocOption` gains four fields, all read from state:**
   - `government_relationship_bps` (current, not baseline);
   - `government_role`;
   - `tax_preference_bps` and `spending_preference_bps`. Positive favours rises, negative favours
     cuts (`legislative_voting.py:407`).
3. **`ChamberPreview.blocs`:** the preview's own apportionment rows (`party_id`, `bloc_id`, `seats`,
   `supporting_seats`), for budgets and amendments. A decree preview has no chambers, and so no rows.
4. **`TurnResultProjection.recorded_vote` and `no_vote_reason`** (new module `app/api/votes.py`):
   - `recorded_vote` is the chamber vote the turn held, from the stored report.
     - **Budgets** carry per-bloc rows (`BlocVoteReport`), with bloc display names.
     - **Amendments** carry chamber totals only, with `blocs_recorded = false`, because their report
       stores no bloc rows. None are invented.
     - It also carries what was proposed: a budget's stored tax and spending directions and totals,
       or an amendment's stored axis targets.
   - `no_vote_reason` is `"no_proposal"` or `"enacted_by_decree"`, read only from the stored
     outcomes.
     - **"No legislature" is not offered:** a legislative-route proposal with no sitting legislature
       is refused before a turn exists (`phases.py:911`, `:2192`), and a test proves it.
     - Any other stored combination raises rather than guessing.
   - A model validator requires **exactly one** of the two.
5. **`DecisionOptionsProjection.last_recorded_vote`:** `{turn, vote}` for the newest turn that
   **held** a chamber vote.
   - The walk skips decree, no-proposal and appointment-only turns.
   - `turn` is the number History files that turn under.
   - The tallies are that turn's stored ones, never recomputed.
   - It is `null` when no vote has ever been held.
   - **Cost:**
     - The walk checks each stored report's raw JSON for chamber rows (`held_a_vote`), and fully
       parses only the turn that held a vote.
     - **Corrected.** This record first said "10.5 ms median, 11.8 ms max" as if that were the
       cost of the request. **It was not.** Those figures, and the 32.7 ms of the first version,
       are in-process timings of the `last_recorded_vote` function alone, on a 40-turn no-vote
       save. They exclude routing, the rest of the options projection, serialization and HTTP.
     - **The complete request is measured in §7:**
       - a 40-turn no-vote history: 26.92 ms median, 80.55 ms worst on M-0, against 14.61 ms and
         57.06 ms on W-2;
       - a recent-vote history: 21.70 ms median, 67.23 ms worst on M-0, against 13.67 ms and
         25.13 ms on W-2.
     - **Not measured:** a release-budget run (`verify_release`) on an M-0 build. That belongs to a
       separately approved candidate step.

## 2. Contract change, itemised

`generate:api` exited 0, and a second run was byte-identical. Schemas went from **66 to 74**; paths
stayed at 13.

| change | kind |
|---|---|
| `ChamberDetail`, `PreviewBlocSupport`, `RecordedVote`, `RecordedChamberVote`, `RecordedBlocVote`, `RecordedBudgetChange`, `RecordedAmendmentTarget`, `LastRecordedVote` | new schemas (8) |
| `BlocOption.government_relationship_bps`, `.government_role`, `.tax_preference_bps`, `.spending_preference_bps` | new **required** fields |
| `ChamberPreview.blocs` | new field, default `[]` |
| `DecisionOptionsProjection.chamber_details` (default `[]`), `.last_recorded_vote` (default `null`) | new fields |
| `TurnResultProjection.recorded_vote`, `.no_vote_reason` (exactly one set) | new fields |

**Nothing was renamed or removed.** The only `-` line in the OpenAPI diff is `"seats"`, which gained a
trailing comma.

**The pinned fixtures were regenerated, and the diff only adds lines:**
- `decision-options-valdrun.json`: the bloc fields, `chamber_details` and `last_recorded_vote`;
- `objective-results.json`: the preview bloc rows and the turn results' vote fields;
- every `-` line gained only a comma;
- `objective-stages.json` and the e2e fixtures are unchanged.

The frontend's source is unchanged, apart from the regenerated types (`schema.d.ts`) and the M-0
gate scripts in `package.json`.

## 3. Tests: `backend/tests/test_parliament_projection.py` (31 passed, 1 skipped)

- **Thresholds:** for each scenario, `chamber_details` equals the engine functions **and** every
  policy card's own `PolicyCardChamberRequirement`. The comparison is checked to be non-vacuous.
- **Bloc fields:** equal to state at turn 0, **and after a turn of relationship investment**, where
  current relationships differ from their baselines. The test asserts that at least one does.
- **Preview bloc rows:**
  - for legislative budgets in all three scenarios, with and without a dealing leader's bargain,
    each bloc's projected seats equal the **resolved** `BlocVoteReport.supporting_seats`, and the
    rows sum to the chamber total;
  - amendment rows sum to each chamber;
  - a decree preview has no chambers;
  - **The skip:** Valdrun with a bargain, because no Valdrun leader will deal.
- **Recorded votes on real resolved turns:**
  - a passed two-chamber budget, whose stored tallies, bloc rows and names match the report;
  - a failed budget (45 of 51);
  - an amendment vote, with totals equal to the stored ones and no bloc rows;
  - a decree budget gives `enacted_by_decree`;
  - no proposal, in each scenario, gives `no_proposal`;
  - an appointment-only turn gives `no_proposal`.
- **Every stored outcome is classified:**
  - each `LegislativeOutcome` goes through `no_vote_reason` on a real report;
  - a member set test fails if a new outcome is added;
  - a proposed amendment with no chambers and a non-decree outcome raises;
  - a missing legislative report raises.
- **No legislature:** both a budget and an amendment on the legislative route with no legislature are
  refused (`TurnResolutionError`).
- **Exactly one:** the turn-result validator rejects both-set and neither-set.
- **The last vote held** (history built with `advance_game`):
  - a fresh campaign gives `None`;
  - a vote, then decree and no-proposal turns, gives the vote's turn and its stored 45/51;
  - a later amendment vote becomes the last, with no bloc rows;
  - the JSON pre-check agrees with the full parse on every stored turn, both kinds included.
- **Through the API:**
  - `/decision-options` gives `null`, then the vote;
  - the vote's `turn` equals History's entry turn;
  - the decree turn's history detail gives `enacted_by_decree`;
  - after save-as and a load into a fresh app, `last_recorded_vote` is identical.

## 4. Gates (final runs; each its own command and its own `$?`)

| gate | exit | result |
|---|---:|---|
| `npm test` | 0 | 45 files, **665** passed, unchanged (no screen code changed) |
| `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | |
| `generate:api` | 0 | the contract itemised in §2; a second run was byte-identical |
| backend `ruff check` / `ruff format --check` / `mypy` | 0 / 0 / 0 | |
| backend full suite | 0 | **36,578 passed, 1 skipped** (+31 passed and +1 skipped from `test_parliament_projection.py`; W-2 ended at 36,547), 29 min 29 s |
| `verify:victory:m0` | 0 | 10 passed |
| `verify:ux:m0` | 0 | 29 passed |
| `verify:fixes:m0` | 0 | 13 passed |
| `verify:icons:m0` | 0 | 7 passed |
| `verify:terminal:m0` | 0 | 6 passed |
| `verify:campaigns:m0` | 0 | 7 passed |
| `audit:stress:seated:m0` | 0 | 6 passed |
| `audit:accessibility:verify:m0` | 0 | 6 passed |

**The artifacts compared with W-2's:**
- **identical:** `victory`, `icon-coverage`, `terminal`, `verification`, `stress-seated` (the JSON and
  both screenshots), and the accessibility JSON. The bundle filename is unchanged too;
- **`campaigns`:** 20 added values, none changed or removed. They are the new per-bloc rows inside the
  recorded preview responses;
- **`verify-ux`:** the output name only.

## 5. Mutation checks (each restored and checked with `cmp`; the tracked diff equal before and after)

| mutation | result |
|---|---|
| MA: preview bloc rows report each bloc's seats instead of the apportionment's supporting seats | pytest exit 1: 3 amendment-sum and 5 resolved-equality cases |
| MB: a recorded chamber tally reports total seats instead of the stored supporting seats | pytest exit 1: passed and failed budget, last-vote walk, API |
| MC: an amendment claims bloc rows | pytest exit 1: the amendment test and the last-vote walk |
| MD: the walk returns the latest turn, not the last that held a vote | pytest exit 1: the last-vote walk and the API test |
| ME: a decree budget is called "no proposal" | pytest exit 1: the decree test, the outcome walk and the API test |
| MF: the budget threshold computed as `seats // 2` | pytest exit 1: the 3 threshold cases and the API test |
| MG: the bloc option reports the baseline relationship instead of the current one | **first run: survived (exit 0).** At turn 0 every shipped bloc sits at its baseline. The test was strengthened to also check after an investment turn, asserting at least one relationship moved. Re-run: pytest exit 1, all 3 after-a-turn cases |

MA to MF ran before MG's test was strengthened. That change only added cases.

## 6. Superseded attempts, recorded and not omitted

1. **`last_recorded_vote`'s first version** fully validated every stored report (32.7 ms worst case).
   It was replaced by the JSON pre-check before any gate ran, and a test pins that the two agree.
2. **The first M-0 test run hit three test defects,** not code defects:
   - the four-axis amendment is illegal outside Valdrun, so the other scenarios now use their own
     legal decree target;
   - a refusal surfaces as `TurnResolutionError`, not `DecisionSetError`;
   - the no-legislature amendment first used an incoherent target.
3. **The strengthened bloc test first used a budget turn to move relationships.** In Valdrun and
   `deficit_demo` that moved none, so the test's own non-vacuity assertion failed it. It now uses a
   relationship investment.

4. **The cost wording in §1 was corrected** after your review. "10.5 ms" was an in-process
   function timing, not the request. The complete request is now measured in §7.

## 7. The complete `/game/decision-options` request, measured (a targeted check, not a release run)

**Method** (raw samples and scripts in `gate-4a3-m0-backend-data/`: `decision-options-timing.json`,
`measure_options.py`, `serve.py`, `drive.sh`):
- **Servers:** one fresh process per build and history.
  - It runs `app.api.main.run_server` on loopback with one worker.
  - It has a fresh port and a fresh save root, with SPA serving off; the measured endpoint does not
    use it.
  - The build is asserted from `app.__file__`.
- **Builds:**
  - **M-0:** the final, uncommitted M-0 working tree;
  - **W-2:** a `git archive` of `a9e006b`, without M-0, as the reference.
- **Histories, built through the API:**
  - **no vote:** Valdrun with 40 resolved no-proposal turns, so no chamber vote is ever held;
  - **recent vote:** Valdrun with 39 no-proposal turns, then turn 40 a legislative budget. On M-0
    the response was checked: `last_recorded_vote` is turn 40, at 45 of 51.
- **Timing:** client wall clock over loopback, as `scripts/measure_budgets.py` measures. The clock
  runs from sending the request to reading the whole body. Every response was asserted to be 200.
- **Sample:** per run, 5 warm-up requests discarded, then **50 timed**, all retained.
- **Order:** sequential, in one session on one machine: M-0 no-vote, M-0 recent, W-2 no-vote, W-2
  recent.

| build | history | n | median | p95 | worst | harness exit |
|---|---|---:|---:|---:|---:|---:|
| M-0 | 40 turns, no vote | 50 | **26.92 ms** | 36.84 ms | **80.55 ms** | 0 |
| M-0 | recent vote (turn 40) | 50 | **21.70 ms** | 24.99 ms | **67.23 ms** | 0 |
| W-2 (`a9e006b`) | 40 turns, no vote | 50 | 14.61 ms | 19.72 ms | 57.06 ms | 0 |
| W-2 (`a9e006b`) | recent vote (turn 40) | 50 | 13.67 ms | 20.57 ms | 25.13 ms | 0 |

The driver exited 0.

**What these show, and no more:**
- **What M-0 added to the median in this session:** about 12.3 ms with no vote ever held, and about
  8.0 ms with a recent vote.
- **The recent-vote path is not free.** It still parses that turn's stored report and state for
  bloc names, and it builds the other new fields. **Where those 8 ms go was not profiled.**
- **Against the release read thresholds:** every M-0 median is below the 100 ms threshold, and every
  M-0 worst is below the 200 ms STOP.
- **The limits:**
  - each worst value is a single request, and the no-vote M-0 run is the highest at 80.55 ms;
  - this is one run per build, in a fixed order, on one machine: no repetitions, no randomized order
    and no interval. **The later runs also had earlier servers still alive** (see the driver defect
    below);
  - so the differences are observations, not a measured regression bound;
  - it is not the release check's workload or method in full, and `verify_release` was not run.

**A defect in the measurement driver, recorded:**
- The driver saved the PID of a wrapper shell, not of the server. Its verification step therefore
  refused to signal it, and all four servers were left running.
- Each was then found by its command line and port, and checked individually: exactly one process
  per port, with its `/proc` cmdline and cwd. Each was stopped by that single PID with SIGTERM, and
  confirmed gone. No port answered afterwards.
- **Corrected:** an earlier draft of this record said the timings were unaffected. **That was not
  established.** Because no server was stopped, each later run executed while every earlier run's
  server was still alive and idle:
  - M-0 recent: 1 extra server;
  - W-2 no-vote: 2;
  - W-2 recent: 3.

  Whether those idle processes changed any timing was **not measured**. So the run order is a
  confound, on top of the single-run limits listed above.

**Not committed.** This awaits your review.
