# Gate 4A3 victory path, V-3: the candidate release, recorded

**This commit is records only:** no code, test, threshold or cache change. It records the **candidate**
release built from `30d0b80`, which is V-2 on top of V-1 `746897d`:
- the campaign objective card;
- the Constitution screen and its links;
- the "If enacted" preview sentence;
- the result's objective line;
- D-V1 to D-V4.

**The approved playtest build is unchanged:** `083c7a98…`, built from `5236ddb`, as named in the
roadmap. This commit does not touch the roadmap. **Whether the playtest moves to this candidate is
your decision.**

## 1. The candidate archive

| step | result |
|---|---|
| `build_release.py --check-reproducible` at `30d0b80` (epoch `1791609744`, the commit time) | exit 0. Two builds gave **identical bytes**: `faeef811f084c7d0825650d043f325b5cb5c9d4f2748644deca6a18bbca5fece` |
| **fresh clone** at `30d0b80` (equal to the pushed head), both dependency links, the same epoch | exit 0. The **same** sha256 |
| the SPA vs `frontend/dist` (`diff -r`) | **identical**: `index-Dsx_9vFP.js` and `index-DUcQTl77.css`, the bundle every V-2 browser gate ran against |

## 2. `verify_release`, once

```
python3 scripts/verify_release.py <archive faeef811…> \
  --out gate-4a3-v3-release --budgets-out gate-4a3-v3-budgets --packaged-out gate-4a3-v3-packaged
```

**The only attempt exited 0.** Verdict `PASSED`, `breaches: []`, and the release and budget records
share the run ID `31ff3ad0…`.

**What it confirmed:**
- **Provenance:** the installed app selects `yaml.cyaml.CSafeLoader` with libyaml.
- **Checksums:** all 9 checksummed files. 3 hostile archives are rejected.
- **Served:** `/` and `/api/scenarios` return 200, with the three scenarios.
- **Packaged turn:** passed, 13 requests, none off-origin, and the worst feedback was 3.6 ms.
- **F12:** a port collision exits 1. SIGINT exits 0, and a restart serves 200.

| budget | median | worst | STOP |
|---|---:|---:|---:|
| new game | 14.12 ms | 53.89 ms | 300 ms |
| resolve, turns ≤ 20 | 62.03 ms | 125.16 ms | 500 ms |
| resolve, turns 21–40 | 144.35 ms | 214.26 ms | 800 ms |
| read projection | 5.69 ms | 58.77 ms | 200 ms |
| load + validate a 40-turn save | 144.37 ms | 179.00 ms | 1000 ms |
| projection payload | 2,995 B | **73,626 B** | 204,800 B |

- **The largest payload grew,** from 68,113 B (the R1-fix candidate) to 73,626 B. It is still turn 0's
  `/api/game/decision-options`.
  - The growth is the new `constitution_qualifying_reform` card in Valdrun's catalogue, and the
    dashboard's `objective`.
  - It is under the 102,400 B target and well under the STOP.
- **Each figure is a single run in this session.** Nothing here compares builds.
- **The risks are as recorded for the approved build:**
  - **R2:** the `/api/scenarios` worst read is 50.38 ms, with no breach. R2 stays qualified, not
    closed.
  - **R1:** the cold path is unchanged and still open.

## 3. Not done here

- **No installed-build dry run.** The plan's V-3 was the archive and `verify_release` only. The
  approved build's dry runs remain the evidence for that build. A dry run of this candidate can be
  added if you move the playtest to it.
- **No roadmap change.** The approved-build line still names `083c7a98…`.
- **The playtest itself is yours.**
