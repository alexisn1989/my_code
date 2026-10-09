# Gate 4A3 R1 diagnosis: the cold save listing

**Diagnosis and reporting only.** There is no code, test, threshold or cache change, and the approved
playtest build (the archive built from `a322484`, `f542cf28…`) and the protocol are unchanged. Any fix
proposed here needs a separate review.

**R1 is one of four open risks.** R2 is open as measured, and R3 and R4 are also open.

**What 6c recorded** (`gate-4a3-commit6c-saves.md` §3.2):
- a fresh server's first listing of 20 long saves took about **1,543 ms**;
- warm listings took about 21 ms;
- the first listing after one new 41-turn save took about 276 ms.

**Measurement conditions.** Every figure below was measured on this container. That means Python
3.11.15, pyyaml 6.0.3, pydantic 2.13.4 and pydantic-core 2.46.4, fastapi 0.141.1 and starlette 1.3.1.
The figures are conditional on it.

The raw data and the two harness scripts, copied verbatim, are in
[`gate-4a3-r1-diagnosis/`](gate-4a3-r1-diagnosis/).

## 1. Findings

1. **A playtester following the protocol meets small numbers.** With a fresh save root, five turns,
   save, five more and save again, all 20 runs gave the following:

   | step | median | max |
   |---|---:|---:|
   | listing after a save | 5–6 ms | under 8 ms |
   | save-as | 9–11 ms | under 16 ms |
   | **listing after a server restart** (the cold case a tester meets) | **67 ms** | **123 ms** |

   Every cold-start sample was under the 200 ms reference line. That is a measurement on the
   protocol's own path. **It is not a claim that no tester will notice anything.**
2. **The 6c worst case still holds on this build, and it is much larger.** A root holding 21 save files
   of one 40-turn campaign took **1,668 ms** (median) for a fresh server's first listing. The range
   across 10 cold starts was 1,582–1,838 ms. Warm listings took 27 ms.
3. **Validation cost is linear in a save's length.** One save's full listing verdict costs about
   **3.5 ms per stored turn** in-process. That is 18 ms at 5 turns and 144 ms at 40 (median). Parsing
   is a small part of it (under 5 ms at 40 turns); `validate_history` is the rest.
4. **A correction to what this repository says about validation.**
   - **The claim:** `validate_history` does **not** re-resolve turns. The profile contains no call to
     the resolver.
   - **What it actually does:** re-validates every stored payload with pydantic, re-serialises it to
     canonical JSON, recomputes the hashes, checks invariants, and runs the per-entry reconciliation.
   - **Which statements are wrong:**
     - `scripts/measure_budgets.py:15` says the load step "re-resolves every stored turn";
     - the 6c record's dialogue speaks of a "full replay";
     - my diagnosis plan repeated the claim.

   This record corrects them **here**. The script's docstring is not edited in this records-only
   commit, and a one-line fix can follow in a code commit if you want it.
5. **The same validation is also inside every turn.**
   - `/game/resolve` writes the campaign's save and then calls `list_saves()` within the same
     request (`app/api/routes.py:495–507`). Save-as does the same (`routes.py:237–238`).
   - Because the campaign file's bytes change every turn, **each resolve pays one full validation of
     the campaign so far**.
   - Resolve medians on the playtester path rise steadily: about 26 ms at turn 1, 53 ms at turn 5 and
     87 ms at turn 10.
   - The in-process per-length cost (finding 3) puts the validation share at roughly 18 ms of the
     turn-5 figure and 36 ms of the turn-10 one. **That is an estimate across two different
     harnesses, not a measured attribution.**
   - This was not in the approved plan's list of measurements. I added it because it is the same
     uncached validation, and it changes what fix (a) below would buy.

## 2. One save's validation cost, against its length (in-process, `a322484` export)

**Method** (`tools/r1_lengths.py`, data in `lengths-a322484.json`):
- **Identity:** the export's `backend/` is first on `sys.path`, and `app` is asserted to come from it.
- **The campaign:** one `decree_state` campaign built through `TestClient(create_app(…))` with empty
  turns, and save-as at turns 1, 2, 5, 10, 20 and 40.
- **The timings:** for each save, 20 timed calls after one discarded warm-up, of:
  - **parse:** decode plus `load_save_json`;
  - **validate:** `validate_history`;
  - **verdict:** the repository's own `_compute_verdict`, exactly what one listing pays per unseen
    save.
- Every save validated with no problems.

| turns | entries | bytes | parse (median) | validate (median / max) | **verdict (median / p95 / max)** |
|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 56,536 | 0.16 ms | 4.0 / 4.6 ms | **5.0** / 5.6 / 5.7 ms |
| 2 | 3 | 97,365 | 0.26 ms | 6.8 / 7.5 ms | **7.8** / 8.1 / 8.1 ms |
| 5 | 6 | 223,879 | 0.63 ms | 15.8 / 41.6 ms | **18.0** / 19.8 / 46.0 ms |
| 10 | 11 | 437,069 | 1.24 ms | 31.6 / 59.2 ms | **35.7** / 47.4 / 67.8 ms |
| 20 | 21 | 858,068 | 2.82 ms | 67.1 / 107.3 ms | **68.6** / 96.5 / 105.4 ms |
| 40 | 41 | 1,711,696 | 4.91 ms | 136.7 / 185.0 ms | **143.6** / 177.5 / 180.8 ms |

A least-squares fit of the verdict medians gives **3.55 ms per turn**, with an intercept of 0.29 ms.

**Profile** (`profile-validate40-a322484.txt`): one 40-turn `validate_history` took 0.161 s under the
profiler, which adds its own overhead.

| work | cumulative time |
|---|---:|
| `_validate_entry_payload` (pydantic `model_validate` plus the canonical-form re-checks) | 0.104 s |
| of which pydantic validation | 0.055 s |
| of which canonical JSON re-serialisation | 0.038 s |
| digests | 0.018 s |
| per-entry reconciliation, for example `reconcile_political_legislative_and_survival_report` | 0.026 s |
| `check_invariants` | 0.008 s |

**No resolver frames appear** (finding 4).

## 3. The playtester's path, over HTTP, on the installed approved archive

**Method** (`tools/r1_http.py`, part A, data in `r1-http.json`):
- **The install:** a fresh, checksum-verified README install of `f542cf28…`. `app` is asserted to
  come from that install's `.venv`.
- **Repetitions:** **20 fixed repetitions, all retained.** Each used a fresh server process on a fresh
  port, with a **fresh, empty save root**: the protocol's one root per tester.
- **The steps:**
  1. Valdrun, with five empty turns resolved and timed;
  2. save-as, then a list (timed), then a list again (warm);
  3. five more turns, timed;
  4. save-as, then a list (timed);
  5. stop the server, restart it on the same root, then a list (timed, cold) and a list again (warm).
- **Stopping servers:** each server was stopped by the single PID the script launched, after a
  `/proc` check of its cmdline and cwd. All 40 exits were 0.
- **Listings:** they held 2 saves after the first save-as and 3 after the second. Those are the
  campaign's own save plus the checkpoints. All were loadable after restart.

| step (20 samples each) | median | p95 | max |
|---|---:|---:|---:|
| save-as after 5 turns | 9.03 ms | 10.46 | 10.65 |
| listing after the first save | 5.13 ms | 6.72 | 7.75 |
| listing, warm | 4.46 ms | 5.38 | 5.48 |
| save-as after 10 turns | 10.99 ms | 13.26 | 15.57 |
| listing after the second save | 6.34 ms | 7.45 | 7.69 |
| **listing after a restart (cold, 3 saves of up to 10 turns)** | **67.09 ms** | **95.19** | **122.64** |
| listing after a restart, warm | 6.44 ms | 8.19 | 10.23 |
| resolve, turns 1–5 (100 samples) | 39.73 ms | 56.67 | 71.25 |
| resolve, turns 6–10 (100 samples) | 82.74 ms | 108.36 | 116.31 |

**Resolve medians by turn:**

| turn | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| median (ms) | 25.8 | 29.4 | 38.2 | 44.8 | 52.8 | 87.3 | 66.0 | 77.5 | 81.4 | 87.3 |

Turn 6 is the first resolve after a save-as. I note that it is higher than turn 7, but I don't
attribute a cause.

**Why the listing right after a save is fast:** save-as already ran `list_saves()` inside its own
request (finding 5), so the listing that follows finds the new file memoised.

## 4. The 6c worst case, repeated on this build

**Method** (`tools/r1_http.py`, part B):
- **The save root:** one campaign of 40 empty Valdrun turns, with save-as at every second turn. That
  gives 20 checkpoints plus the campaign's own save: **21 files**.
- **Repetitions:** **10 fixed repetitions.** Each started a fresh server on that root and took the
  first listing (cold), then a second (warm).
- **Outcome:** all 21 saves were listed as loadable every time, and every server exited 0.

| | median | max | every sample |
|---|---:|---:|---|
| **first listing, cold** | **1,668.49 ms** | 1,837.73 ms | 1,595.0, 1,634.1, 1,708.4, 1,766.1, 1,654.3, 1,581.7, 1,682.7, 1,705.4, 1,837.7, 1,602.9 |
| second listing, warm | 26.91 ms | 34.93 ms | |

The 200 ms `/api/saves` STOP applies only as a reference line here, because the budget method
deliberately discards the first request. This is not a budget breach in the method's terms. **It is a
1.6–1.8 s wait a user would see** on the Title screen's load panel after starting the game with a
root this full.

## 5. Fix options, for a separate review (none implemented)

Each needs your ruling and its own gated commit.

| option | expected effect, on this evidence | limits and risks |
|---|---|---|
| **(a) Seed the memo when the server writes a save**, from the save it just built | It would remove the per-resolve validation of the campaign file (finding 5; an **estimated** 18 ms at turn 5, about 36 ms at turn 10 and about 144 ms at turn 40), and save-as's own listing cost | It does nothing for a cold start. **It trusts the writer:** a write that silently corrupted bytes on disk would be listed as loadable until a restart. The full validation on **load** is unchanged, so nothing unvalidated is ever played. It is memo population, so it needs a §18 ruling |
| **(b) A persistent on-disk memo** in the save root, keyed by each file's SHA-256 | A cold start would pay hashing and a lookup instead of validation (finding 2's 1.6–1.8 s); the gain is estimated, not measured | Caching across restarts (§18). The memo file itself becomes something to validate, or else a forged entry could mark a tampered save loadable. Invalidation by key is sound |
| **(c) List from the index first, and validate in the background** | Listing would be about index-read time | "Listed as loadable" would become provisional until validation finishes, which changes a promise the UI makes |
| **(d) Validate at write time** | **Nothing new for resolve**, which effectively does this already (finding 5) | Listed for completeness, because 6c named it. The evidence here shows it is not a distinct option |

**R1's status for the playtest:**
- On the protocol's path (one fresh root per tester, a handful of saves), the cold listing measured
  67 ms median and at most 123 ms.
- The 1.6–1.8 s case needs a root holding many long saves.

**R1 stays open** until a fix is chosen, or the risk is otherwise ruled on.

## 6. Scope

- **Added:**
  - this record;
  - `gate-4a3-r1-diagnosis/`, holding `tools/` (`r1_lengths.py`, `r1_http.py`),
    `lengths-a322484.json`, `profile-validate40-a322484.txt` and `r1-http.json`.
- **Changed (the named exception):** the roadmap's R1 line now states these measured figures and links
  here.
- **Unchanged:**
  - `app/**`, `scripts/**` (including the inaccurate docstring of finding 4), tests and thresholds;
  - the playtest build and protocol;
  - every earlier record.
