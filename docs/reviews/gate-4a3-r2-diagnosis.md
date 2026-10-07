# Gate 4A3 R2 diagnosis: where `/api/scenarios` spends its time

**Diagnosis and reporting only.** Nothing changes in this commit except these records and one line in
the roadmap (§7). There is no change to code, tests, thresholds or caching, and the approved playtest
build (the archive built from `81f0648`, `058d779f…7740`) is unchanged. Any fix proposed here needs a
separate review.

R2 is **one of** the open risks on that build; R1, R3 and R4 also remain.

**Before this diagnosis:**
- `/api/scenarios`: median about 108–132 ms, worst 132–206 ms, against the read budget's 200 ms STOP;
- the cause was unresolved;
- a regression had not been ruled out (`gate-4a3-ux4g-corrections.md` §3).

**Every measurement below** was made on this container (4 CPUs, Python 3.11.15) and used the
dependency versions the lockfile pins:
- pyyaml 6.0.3, built with libyaml;
- pydantic 2.13.4, pydantic-core 2.46.4;
- fastapi 0.141.1, starlette 1.3.1;
- httpx 0.28.1.

The raw data and the harness scripts are in [`gate-4a3-r2-diagnosis/`](gate-4a3-r2-diagnosis/). The
scripts are copied verbatim from the runs. They are evidence, imported by nothing.

## 1. Findings, worded no more strongly than the data allows

1. **Most of a request's time is spent parsing YAML.** On the final build, per request:
   - PyYAML's pure-Python `yaml.safe_load` of the three scenario files takes **124.6 ms**, the sum of
     the per-file medians;
   - every other phase together takes about **1.2 ms**;
   - this harness's whole request has a median of about **141 ms**.

   A same-thread profile of the handler's own work agrees: `safe_load` accounts for 9.81 s of 9.89 s
   cumulative (under profiler overhead).
2. **The C parser agrees on the three shipped scenarios, and is about 9× faster on them.**
   - libyaml is installed but unused.
   - `yaml.load(…, Loader=yaml.CSafeLoader)` produced output **equal** (`==`) to `safe_load`'s for
     `decree_state`, `deficit_demo` and `tiny_valid`, in **13.3 ms** in total.
   - This proves agreement for **those three files only**. It does not show compatibility for any
     other YAML, nor anything about replay safety.
3. **No difference between builds was detected in median or p95.**
   - Each newer build was compared with 6c, as newer minus baseline.
   - The final build's interval is **−5.0 to +2.0 ms** for the median and −23.0 to +8.9 ms for p95.
     The UX-4d and UX-4e intervals are similar.
   - A slowdown smaller than those bounds is not excluded.
   - The max showed a detected *improvement*, but that comes from three outlier blocks on the 6c
     baseline (§3). **It is not credited to any code change.**
4. **The release check failed on this endpoint in 14 of 30 matched runs.**
   - That is 46.7%, with a 95% Clopper–Pearson interval of **28.3%–65.7%**.
   - All 14 breaches were `read_projection_ms`, and in every one of the 30 runs the read row's worst
     sample came from `/api/scenarios`.
   - This is **conditional on this machine and this workload** (§4). It is not a general failure rate.
5. **The tail's cause is not established.**
   - In one instrumented run, calls that overlapped a generation-2 garbage collection were slower:
     median 170.5 ms against 139.4 ms.
   - But only 6 of the 15 slowest calls overlapped one.
   - That is **correlation within that run only**. It is not shown to cause slow HTTP requests
     elsewhere.

## 2. What one request does, and where the time goes (final build, in-process)

`list_scenarios` (`app/api/routes.py:145`) reloads every scenario file on every request. Per file, it
runs:
1. `load_scenario_file`;
2. `yaml.safe_load`;
3. `ScenarioDefinition.model_validate`;
4. `_to_game_state` (state construction plus `check_invariants`);
5. `build_dashboard(state, None)`;
6. `ScenarioSummary`.

The three files total 97,645 bytes. Since 6c, only UX-4a changed code on this path: a money-display
line in `build_dashboard`.

**Method** (`tools/phases.py`, data in `phases-81f0648.json`): each phase was timed 200 times per file,
on inputs produced beforehand. Medians in ms:

| phase | decree_state | deficit_demo | tiny_valid | sum |
|---|---:|---:|---:|---:|
| read the file | 0.021 | 0.024 | 0.023 | 0.07 |
| **`yaml.safe_load`** | **41.05** | **38.94** | **44.62** | **124.6** |
| `yaml.load(…, CSafeLoader)` (diagnostic, not used by the app) | 4.26 | 4.25 | 4.79 | 13.3 |
| `ScenarioDefinition.model_validate` | 0.230 | 0.246 | 0.247 | 0.72 |
| `_to_game_state` | 0.104 | 0.091 | 0.098 | 0.29 |
| of which `check_invariants` | 0.075 | 0.066 | 0.073 | 0.21 |
| `build_dashboard` | 0.025 | 0.024 | 0.023 | 0.07 |
| summary built and serialised | 0.004 | 0.004 | 0.004 | 0.01 |

**Profiles:**
- **`profile-81f0648.txt`** is the TestClient profile. It is **uninformative**, and is kept to show
  why. FastAPI runs this synchronous route on a worker thread, so cProfile saw only the client thread
  waiting on a lock (0.187 s of 0.189 s in `_thread.lock.acquire`).
- **`profile-handler-81f0648.txt`** (`tools/profile_handler.py`) profiles the handler's own work in
  the calling thread, 20 times. `safe_load` accounts for 9.810 s of the 9.894 s cumulative, and the
  composer and parser frames sit under it.

## 3. Build comparison: 6c, UX-4d, UX-4e and the final build

**Builds:** `d1c09201` (6c, which is also `bf66b8e6^`, the last commit before the UX pass), `5a1b2eb`
(UX-4d), `44fbd5a` (UX-4e) and `81f0648` (final).
- Each was exported with `git archive`; the tarball hashes are in `exports.txt`.
- `data/scenarios` is identical across all four (`git diff` is empty).

**Identity, proven per block** (`tools/block.py`). The harness runs with `python -I` from outside the
export and puts the export's `backend/` first on `sys.path`. It **asserts** that `app.__file__` lies
inside that export before timing anything, and records the Python and dependency versions.
`tools/analyse.py` re-asserts that all 80 blocks name their own export, and that all of them ran one
Python version and one dependency set.

**Design** (`tools/rounds.py`, recorded in `rounds-design.json`):
- **Size:** 20 rounds × 4 builds, fixed in advance.
- **Blocks:** each build in each round ran as **one fresh process**: 5 warm-up calls discarded, then
  **50 timed** `GET /api/scenarios` calls through FastAPI's `TestClient(create_app(...))`. That
  includes routing, the security middleware, the handler and serialisation, but no socket.
- **Order:** randomised but balanced. Seed 4242 drove five shuffles of the four Latin-square rotations,
  so each build ran in each position exactly 5 times.
- **Retention:** all 80 blocks were kept.
- **Position:** mean block medians by position were 140.9, 142.0, 145.5 and 140.2 ms. No position is
  consistently slow.

**Analysis** (`tools/analyse.py`, output in `rounds-analysis.json`):
- For each round and build, the block's own median, p95 and max are computed.
- **Difference = newer minus 6c, within the same round:** above 0 is a slowdown, below 0 an
  improvement.
- 95% intervals come from a bootstrap of 10,000 resamples (seed 7) **over rounds**. Each round's four
  builds stay together, so calls are never treated as independent.

| newer − 6c | median: mean [95% CI] ms | p95: mean [95% CI] ms | max: mean [95% CI] ms |
|---|---|---|---|
| UX-4d `5a1b2eb` | +1.5 [−1.6, +4.5]: not detected | −5.4 [−22.9, +9.0]: not detected | −24.5 [−56.2, −0.01]: improvement detected* |
| UX-4e `44fbd5a` | −1.4 [−4.8, +2.1]: not detected | −7.4 [−24.7, +8.6]: not detected | −29.8 [−57.1, −7.2]: improvement detected* |
| final `81f0648` | −1.3 [−5.0, +2.0]: not detected | −6.1 [−23.0, +8.9]: not detected | −30.1 [−60.7, −4.8]: improvement detected* |

\* **The max "improvement" is not credited to code.**
- 6c's five largest block maxima were 255.2, 255.5, **333.5, 357.6 and 463.6** ms. Every other
  build's largest block maximum was 274.5 ms.
- The detected difference rests on those three baseline outliers.
- No code on this path changed between the builds except UX-4a's display line. The max is the
  statistic most exposed to a single slow call.

**Pooled across 1,000 samples per build** (descriptive, not inferential):
- medians: 141.8 (6c), 143.2, 141.0 and 141.1 ms;
- p99: 269.6, 232.4, 224.9 and 229.3 ms;
- blocks with a max over 200 ms: 20, 20, 19 and 17 of 20.

This in-process harness reads about 10 ms higher than the HTTP medians in §4, because the TestClient
crosses a thread portal. Its absolute numbers are not interchangeable with the HTTP ones.

**Reading:**
- **No median or p95 slowdown was detected** in any newer build.
- The intervals bound a median change on the final build to between −5.0 and +2.0 ms in this harness.
- A smaller slowdown, or one confined to rarer tail events than 50-call blocks resolve, is not ruled
  out.

## 4. How often the release check fails on this, in its own workload

**Method** (`tools/budgets30.py`, results in `budgets30/`):
- **The real `scripts/measure_budgets.py`, unmodified, was run a fixed 30 times.** All 30 runs are
  retained, and the count was not extended.
- Each run used a **fresh server process** from one fresh, checksum-verified README install of the
  final archive, on a fresh port with an empty save root.
- **`measure_budgets.py`'s own order:**
  1. a warm-up and 20 `POST /api/game/new`;
  2. the turn-0 payload reads;
  3. 40 empty-turn resolves;
  4. the read block: a warm-up and 20 samples per endpoint, with `/api/scenarios` last;
  5. **then** save-as and 10 loads.
- The comparison is that script's: the worst of the 20 samples against the 200 ms STOP.
- Each server was stopped by the one PID the driver had launched, after checking that PID's `/proc`
  command line and working directory. All 30 servers exited 0.
- A run took 14.8–16.9 s, and the 1-minute load average was 0.84–1.06.

**Result:**
- **14 of 30 runs breached `read_projection_ms`**, every one at `/api/scenarios`. No other budget
  breached in any run.
- `/api/scenarios` worst per run, sorted: 148.96, 152.72, 163.79, 165.90, 167.46, 168.49, 168.69,
  169.49, 169.57, 169.98, 177.00, 180.13, 181.45, 188.90, 193.64, 194.74, **200.74, 206.10, 207.46,
  208.23, 210.23, 211.40, 211.79, 214.48, 215.81, 226.85, 228.37, 235.52, 237.07, 245.62** ms.
- `/api/scenarios` medians per run ranged from 124.64 to 159.85 ms (median of medians 131.72).

**The estimate:** a breach rate of **46.7%**, with a 95% Clopper–Pearson interval of **28.3%–65.7%**.
It is **conditional on this container, its load, and this workload.** It is not a rate for a
tester's machine, and it is not a property of the build alone.

It is consistent with the release history:
- UX-4f: one breach (aggregate), then one pass;
- UX-4h: one pass;
- UX-4f's diagnosis: one breach in eight runs.

## 5. Garbage collection: correlation within one run only

`tools/phases.py` hooked `gc.callbacks` during 300 timed TestClient requests on the final build:
- **collections:** 5,501 in generation 0, 500 in generation 1, 45 in generation 2;
- **45 calls overlapped a generation-2 collection:** median 170.5 ms, p95 226.5, max 253.3;
- **the other 255 calls:** median 139.4 ms, p95 197.9, max 248.9;
- **of the 15 slowest calls (5%),** 6 overlapped a generation-2 collection and 9 did not.

This shows an association **inside that instrumented run**, and nothing more. It does not show that
GC causes the slow HTTP samples in §4, nor that GC is the main source of the tail.

## 6. Fix options, for a separate review (none implemented)

**Every one of these needs your ruling and its own gated commit.**

| option | expected effect | limits and risks |
|---|---|---|
| **(a) Use libyaml's `CSafeLoader` in `_parse`** (`app/simulation/scenario.py`) | The parse would drop from about 124.6 ms to about 13.3 ms per request, an **estimate** from §2's phase medians, not an end-to-end measurement | Engine boundary: it also changes `POST /api/game/new` (`routes.py:192`) and the CLI (`cli.py:777`), so **every campaign's starting state** passes through it. Agreement is shown for the three shipped files only; replay and save compatibility is **not assessed**. `ScenarioValidationError`'s "invalid YAML: …" text would come from a different parser. The behaviour when libyaml is absent must be decided: fall back, or refuse. |
| **(b) A memo of the summaries, keyed by the SHA-256 of each file's exact bytes** (the 6c saves pattern) | A repeat request would cost one read and one hash per file. The first request after start, or after an edit, still pays the full parse | Caching, so a §18 ruling. It keeps the property that each card comes from the file as it is now, because a changed byte reloads it. It does nothing for `new game` or the CLI. |
| **(c) Build the summaries once at startup** | Every request would be about a list lookup | A scenario file edited while the server runs would not be reflected until restart. Startup pays the parse once. |

**R2 stays open** until one is chosen and verified, or the risk is otherwise ruled on.

## 7. Scope

- **Added:**
  - this record;
  - `gate-4a3-r2-diagnosis/`:
    - `tools/` (six scripts);
    - `blocks/` (80 JSON);
    - `budgets30/` (30 run JSON plus the driver log);
    - `exports.txt`, `rounds-design.json`, `rounds-analysis.json`, `phases-81f0648.json`, and two
      profiles.
- **Changed (the one named exception):** the roadmap's R2 line in the Gate 4A3 entry, rewritten to
  state the measured cause of the median, the conditional breach estimate, and a link here.
- **Unchanged:**
  - `app/**`, tests, thresholds and budgets;
  - the playtest build, protocol and observation sheet;
  - every earlier record.
