# Strategic Map M0 — fictional-geography revision (ADDITIVE)

**This document does not replace or amend the frozen M0 plan.** That plan remains
`docs/plans/strategic-military-map-m0-implementation-plan.md`, SHA-256
`c1bdb29080fba4feb6a2943902317783b782df49da431b643941f13f8b672f20`, byte-identical. This is a
separate, additive record of a product decision taken after it was frozen.

## 1. The product ruling

The frozen plan's §5 authored three deliberately minimal maps (5–6 vertex rings), and the
implementation that followed it correctly refused to invent geography at runtime. That refusal
still stands for the RUNTIME. What changed is the authoring rule:

> Fictional geography is authorized when it is deliberately authored into scenario content,
> validated, reviewed and stored as authoritative data. The frontend may never invent geography
> at runtime.

So the richer coastlines below are authored data, reviewed and hashed, exactly like every other
scenario field. No polygon is generated, smoothed, interpolated or inferred by any client.

## 2. Base and approvals

| Item | Value |
|---|---|
| Implementation base commit | `c1b6b7c273b9a3544a4d4cdf3531b963521b1cca` |
| Branch | `claude/phase-4a-graphical-vertical-slice` |
| Frozen M0 plan SHA-256 | `c1bdb29080fba4feb6a2943902317783b782df49da431b643941f13f8b672f20` (unchanged) |
| Coordinate-table artifact SHA-256 | `dcd049b6a4d762cae6e3a060c60c549a2d5485af594ab7989ec3597030fb9794` |

Three independent visual approvals, each against an exact rendered artifact:

| Scenario | Map | Approved preview SHA-256 |
|---|---|---|
| `tiny_valid` | Arken Basin | `0e5b9fbae2943d86801fb37367503615961693852a771afa819551c219f3cb0f` |
| `decree_state` | Valdrun Reach | `1802d862435c45e513263e2514061378373ac76bc736feb7670454528cf47535` |
| `deficit_demo` | Tolvane Strait | `ee492aaf98292f49b3cde3ae77e7548f5b3f7b6fc03cd7ce268474804b79dd89` |

Each preview was rendered directly from the coordinate arrays in §4 — not concept art — so the
approval attaches to the exact numbers being implemented.

## 3. Binding decisions

1. **Freeze all three reviewed coordinate sets exactly.** No redrawing, simplifying, smoothing
   or repositioning.
2. **`shape_arken_isles` approved** as decorative, player-owned geography. It creates no
   theater, route, population, resource, city, province or mechanic of any kind. It is an
   additional shape owned by an existing sovereign and nothing more.
3. **Open-sea proportions accepted as proposed.** Land must not be distorted or enlarged to fill
   the square viewport; the sea does real work separating Tolvane from the mainland.
4. **`RULESET_VERSION = "0.14.0"` and `SAVE_FORMAT_VERSION = 1` retained.** See §8.
5. **Marnil is byte-identical** across `decree_state` and `deficit_demo`.
6. **Tolvane remains an isolated island; `tolvane_isle` remains routeless.**
7. **Presentation only.** No provinces, cities, terrain mechanics, resources, populations, troop
   controls or military simulation are introduced, now or by implication.

## 4. Exact geometry

Shape counts, old → new:

| Scenario | Old shapes | New shapes | Change |
|---|---|---|---|
| `tiny_valid` | 3 | 4 | + `shape_arken_isles` |
| `decree_state` | 3 | 3 | none |
| `deficit_demo` | 3 | 3 | none |

Every polygon below is an OPEN ring in authored order. Vertices are joined, never sorted,
rotated, normalized or recomputed.

### 4.1 `tiny_valid` — Arken Basin (`arken_basin`)

**`shape_arken`** — owner `player_country:arken`, 35 vertices

```
  [3450, 1500], [3620, 2100], [3480, 2700], [3700, 3300], [3520, 3950], [3760, 4600]
  [3600, 5250], [3820, 5900], [3650, 6500], [3300, 6950], [2850, 7180], [2400, 7080]
  [2050, 7350], [1700, 7250], [1450, 6850], [1180, 6400], [1320, 5950], [980, 5600]
  [1150, 5150], [1560, 4980], [1720, 4600], [1420, 4380], [1020, 4520], [760, 4150]
  [900, 3700], [700, 3250], [880, 2800], [760, 2350], [1050, 2000], [1450, 1750]
  [1900, 1620], [2350, 1500], [2600, 1180], [2900, 1350], [3150, 1250]
```

**`shape_arken_isles`** — owner `player_country:arken`, 8 vertices

```
  [330, 6720], [700, 6560], [1010, 6760], [880, 7060], [1050, 7350], [700, 7520]
  [380, 7330], [250, 7020]
```

**`shape_kessia`** — owner `foreign_profile:kessia`, 31 vertices

```
  [3450, 1500], [3800, 1250], [4200, 1400], [4600, 1150], [5000, 1300], [5400, 1100]
  [5800, 1350], [6150, 1180], [6400, 1450], [6550, 1900], [6720, 2500], [6580, 3100]
  [6800, 3700], [6620, 4300], [6840, 4900], [6660, 5500], [6300, 5900], [5900, 6150]
  [5500, 6050], [5100, 6350], [4700, 6250], [4300, 6500], [3950, 6350], [3650, 6500]
  [3820, 5900], [3600, 5250], [3760, 4600], [3520, 3950], [3700, 3300], [3480, 2700]
  [3620, 2100]
```

**`shape_vetruska`** — owner `foreign_profile:vetruska`, 30 vertices

```
  [6550, 1900], [6900, 1600], [7300, 1750], [7700, 1500], [8100, 1650], [8500, 1450]
  [8850, 1700], [9150, 2100], [9280, 2600], [9050, 3050], [9300, 3500], [9120, 4000]
  [9250, 4500], [9380, 5000], [9200, 5500], [9320, 6000], [9050, 6450], [8600, 6650]
  [8200, 6500], [7900, 6800], [7550, 6600], [7200, 6750], [6950, 6450], [6800, 6000]
  [6660, 5500], [6840, 4900], [6620, 4300], [6800, 3700], [6580, 3100], [6720, 2500]
```

Theater presentation, old → new (identity, kind and owner all unchanged):

| Theater | Owner | Old centroid | New centroid | Old anchor | New anchor |
|---|---|---|---|---|---|
| `arken_capital` | `arken` | (1900, 3200) | (2200, 3250) | `center` | `n` |
| `arken_coast` | `arken` | (1200, 5200) | (1550, 5600) | `w` | `s` |
| `arken_north` | `arken` | (2200, 1900) | (2300, 2050) | `n` | `n` |
| `kessia_south` | `kessia` | (5400, 3800) | (5150, 4750) | `center` | `s` |
| `vetruska_frontier` | `vetruska` | (8200, 3500) | (8150, 3300) | `e` | `s` |

### 4.2 `decree_state` — Valdrun Reach (`valdrun_reach`)

**`shape_marnil`** — owner `foreign_profile:marnil`, 35 vertices

```
  [4350, 1700], [4700, 1400], [5050, 1600], [5300, 1250], [5450, 1750], [5750, 1900]
  [6000, 1500], [6300, 1350], [6600, 1600], [6850, 2000], [7000, 2600], [6820, 3200]
  [7050, 3800], [6880, 4400], [7100, 5000], [6900, 5550], [6600, 5950], [6250, 6150]
  [5950, 6500], [5850, 7050], [6050, 7500], [5750, 7800], [5450, 7500], [5550, 7000]
  [5350, 6600], [5000, 6750], [4800, 6500], [4520, 6400], [4700, 5900], [4480, 5300]
  [4650, 4700], [4420, 4100], [4600, 3500], [4380, 2900], [4520, 2300]
```

**`shape_sorrend`** — owner `foreign_profile:sorrend`, 26 vertices

```
  [6850, 2000], [7200, 1650], [7600, 1800], [8000, 1550], [8400, 1700], [8750, 1500]
  [9100, 1900], [9250, 2400], [9050, 2900], [9300, 3400], [9150, 3900], [9350, 4400]
  [9150, 4900], [9300, 5400], [9000, 5850], [8600, 6050], [8200, 5900], [7800, 6150]
  [7400, 5950], [7100, 6050], [6900, 5550], [7100, 5000], [6880, 4400], [7050, 3800]
  [6820, 3200], [7000, 2600]
```

**`shape_valdrun`** — owner `player_country:valdrun`, 36 vertices

```
  [4350, 1700], [4050, 1350], [3650, 1500], [3250, 1250], [2850, 1450], [2500, 1200]
  [2150, 1400], [1750, 1650], [1500, 2100], [1650, 2600], [1300, 3000], [1450, 3500]
  [1900, 3750], [2150, 4150], [1750, 4400], [1350, 4250], [1100, 4650], [1250, 5150]
  [1000, 5600], [1200, 6100], [1550, 6450], [1950, 6800], [2400, 6950], [2800, 6750]
  [3200, 7000], [3600, 6850], [4000, 7050], [4300, 6800], [4520, 6400], [4700, 5900]
  [4480, 5300], [4650, 4700], [4420, 4100], [4600, 3500], [4380, 2900], [4520, 2300]
```

Theater presentation, old → new (identity, kind and owner all unchanged):

| Theater | Owner | Old centroid | New centroid | Old anchor | New anchor |
|---|---|---|---|---|---|
| `marnil_border` | `marnil` | (5700, 3600) | (5350, 3600) | `center` | `n` |
| `sorrend_plain` | `sorrend` | (8400, 4000) | (8200, 3550) | `e` | `n` |
| `valdrun_capital` | `valdrun` | (1900, 3000) | (2750, 3100) | `center` | `n` |
| `valdrun_east` | `valdrun` | (3300, 4200) | (3800, 4350) | `s` | `s` |
| `valdrun_highlands` | `valdrun` | (2400, 1700) | (2900, 2050) | `n` | `n` |

### 4.3 `deficit_demo` — Tolvane Strait (`tolvane_strait`)

**`shape_marnil`** — owner `foreign_profile:marnil`, 35 vertices

```
  [4350, 1700], [4700, 1400], [5050, 1600], [5300, 1250], [5450, 1750], [5750, 1900]
  [6000, 1500], [6300, 1350], [6600, 1600], [6850, 2000], [7000, 2600], [6820, 3200]
  [7050, 3800], [6880, 4400], [7100, 5000], [6900, 5550], [6600, 5950], [6250, 6150]
  [5950, 6500], [5850, 7050], [6050, 7500], [5750, 7800], [5450, 7500], [5550, 7000]
  [5350, 6600], [5000, 6750], [4800, 6500], [4520, 6400], [4700, 5900], [4480, 5300]
  [4650, 4700], [4420, 4100], [4600, 3500], [4380, 2900], [4520, 2300]
```

**`shape_strapped`** — owner `player_country:strapped`, 36 vertices

```
  [4350, 1700], [4050, 1400], [3600, 1250], [3150, 1500], [2750, 1300], [2350, 1550]
  [1950, 1400], [1600, 1750], [1750, 2250], [1350, 2600], [1500, 3050], [1950, 3250]
  [2250, 3600], [1850, 3850], [1400, 3700], [1150, 4100], [1300, 4600], [1050, 5050]
  [1250, 5550], [1050, 6000], [1400, 6400], [1800, 6750], [2250, 6900], [2650, 6700]
  [3050, 6950], [3450, 6800], [3850, 7000], [4250, 6750], [4520, 6400], [4700, 5900]
  [4480, 5300], [4650, 4700], [4420, 4100], [4600, 3500], [4380, 2900], [4520, 2300]
```

**`shape_tolvane`** — owner `foreign_profile:tolvane`, 15 vertices

```
  [7900, 6350], [8350, 6200], [8750, 6400], [9100, 6250], [9300, 6600], [9350, 7050]
  [9150, 7450], [9300, 7850], [8950, 8100], [8500, 7950], [8100, 8150], [7800, 7850]
  [7650, 7400], [7800, 6900], [7600, 6600]
```

Theater presentation, old → new (identity, kind and owner all unchanged):

| Theater | Owner | Old centroid | New centroid | Old anchor | New anchor |
|---|---|---|---|---|---|
| `home_capital` | `strapped` | (1800, 3200) | (2650, 4700) | `center` | `w` |
| `home_lowlands` | `strapped` | (2500, 2000) | (3750, 3150) | `n` | `n` |
| `home_port` | `strapped` | (1300, 5300) | (2100, 4150) | `w` | `w` |
| `marnil_march` | `marnil` | (5500, 3400) | (5400, 4300) | `center` | `e` |
| `tolvane_isle` | `tolvane` | (8600, 6800) | (8450, 7150) | `s` | `s` |

## 5. What does not change

Proven mechanically by the tests in §9, not asserted:

- **Theater ids, display names, kinds and owners** — identical.
- **Capital theater** — identical in all three scenarios.
- **Route rows, modes and directions** — the full directed graph is carried through unchanged:
  `tiny_valid` keeps its 8 directed rows.
  `decree_state` keeps its 8 directed rows.
  `deficit_demo` keeps its 6 directed rows.
- **Foreign profiles, conflict dyads, war capability, aims and exposure** — untouched. No W1
  content is edited by this revision.
- **Economic, political, constitutional and fiscal scenario content** — untouched.
- **API schema and frontend component behaviour** — untouched. The shipped screen already
  renders whatever the data says; richer polygons need no client change.

### Marnil's cross-scenario identity

`shape_marnil` is authored once (35 vertices) and appears byte-identical in
both `decree_state` and `deficit_demo`. A recurring actor with two unrelated silhouettes would
be a continuity error, so this is enforced by test, not by care.

### Tolvane's isolation

`tolvane_isle` has zero incoming and zero outgoing routes, and `shape_tolvane` shares no
boundary segment with any other sovereign. Both are enforced by test.

## 6. Shared borders

Where two sovereigns are meant to share a land border, the border is authored ONCE as a
polyline and both rings walk that same vertex sequence (one forward, one reversed). The segments
are therefore exactly equal, not approximately coincident — which is what makes a border look
like a border rather than two nearly-touching coastlines.

| Scenario | Border | Exactly shared segments |
|---|---|---|
| `tiny_valid` | `shape_arken` \| `shape_kessia` | 8 |
| `tiny_valid` | `shape_kessia` \| `shape_vetruska` | 6 |
| `decree_state` | `shape_valdrun` \| `shape_marnil` | 8 |
| `decree_state` | `shape_marnil` \| `shape_sorrend` | 6 |
| `deficit_demo` | `shape_strapped` \| `shape_marnil` | 8 |

## 7. Scenario digests

Recomputed deliberately and recorded here BEFORE the pinned values in
`backend/tests/test_scenario.py` are replaced. A digest must never be refreshed to whatever a
failing test happens to print.

| Scenario | Old digest | New digest |
|---|---|---|
| `tiny_valid.yaml` | `4224643b62655296e07b7a033751ffec4e1c04a2982a1bf38603c1d42c7f11c1` | `920b3a149f909267d9fa82eb564b77dc5fc1c51758152aa28ee6f09faf78281e` |
| `decree_state.yaml` | `516beb9fd5117b84cc3c0b6e4381fd40da6e86ce2246a0267e913636d45f457c` | `a4480c83d1d6f298baf7c7e3711d748b3f21b7336bf0bce5a4438cfa51fd6e99` |
| `deficit_demo.yaml` | `23ad68a04b47195dd2b57cda012ad1974301b5eca0d675b0034307fd5c496e4b` | `d542a2cf42b1451b234c36871cc80a9cae5a4724954d57feb32a126a172ff067` |

(canonical-JSON BLAKE2b of `state.world.strategic_map`, via `app.core.canonical_json`.)

## 8. Version ruling

**Retain `RULESET_VERSION = "0.14.0"` and `SAVE_FORMAT_VERSION = 1`.** Evidence, not assumption:

- `git tag -l` is empty: `0.14.0` has never been released or tagged.
- The branch carrying `0.14.0` is unmerged; `0.14.0` was introduced on it (`a4c3be1`).
- Save fixtures stop at `0.13.0`; no authentic `0.14.0` fixture exists. The `0.13.0` fixture
  exists precisely to prove `0.14.0` rejects it.
- A save embeds its complete strategic map in `state_json` and loads it from the save, never
  re-reading the scenario. Re-authoring scenario geometry therefore cannot invalidate or
  retroactively alter any existing save.

Re-authoring content inside an unreleased ruleset is a correction, not a compatibility break.

## 9. Validation method and permanent test matrix

### The LAND-route containment algorithm

The proposal stage used 160-point sampling per route. That is retired here, because sampling can
only fail to find a gap — it can never prove absence. The durable check is exact:

1. Intersect the route segment with every edge of every land polygon, collecting the parameter
   `t` of each crossing.
2. Partition the segment at those parameters, plus `t=0` and `t=1`.
3. Classify the MIDPOINT of each resulting subsegment.
4. Require every subsegment's midpoint to lie inside, or on the boundary of, the land union.

Parameters are kept as exact rational values (`fractions.Fraction`) over integer vertex
coordinates, so the classification carries no floating-point tolerance and no epsilon.

**Negative controls are mandatory.** A validator that cannot fail is not evidence, so the suite
includes a route deliberately crossing a concave water gap, and a deliberately self-intersecting
polygon, and asserts that each is REJECTED.

### Requirement-to-test matrix

| # | Property | Test |
|---|---|---|
| 1 | Coordinates within the 0..10,000 grid | `test_map_authored_geometry.py` |
| 2 | Open rings, ≥3 unique vertices | `test_map_authored_geometry.py` |
| 3 | No consecutive duplicates; nonzero area | `test_map_authored_geometry.py` |
| 4 | No polygon self-intersection (+ negative control) | `test_map_authored_geometry.py` |
| 5 | No cross-owner interior overlap, shared borders permitted | `test_map_authored_geometry.py` |
| 6 | Every theater centroid inside its own sovereign's territory | `test_map_authored_geometry.py` |
| 7 | Capital inside player-owned territory | `test_map_authored_geometry.py` |
| 8 | Approved shared borders are exactly matching segments | `test_map_authored_geometry.py` |
| 9 | Every route endpoint resolves | `test_map_authored_geometry.py` |
| 10 | Theater ids/owners/capital/directed routes unchanged | `test_map_authored_geometry.py` |
| 11 | Marnil byte-identical across two scenarios | `test_map_authored_geometry.py` |
| 12 | `tolvane_isle` zero in, zero out | `test_map_authored_geometry.py` |
| 13 | Canonical shape ordering | `test_map_authored_geometry.py` |
| 14 | Scenario digests equal the reviewed new values | `test_scenario.py` |
| 15 | LAND routes on land, exact partition (+ negative control) | `test_map_authored_geometry.py` |
| 16 | `shape_arken_isles` owns no theater and no mechanic | `test_map_authored_geometry.py` |

This validation lives in **test support**. It introduces no runtime invariant and no new
dependency: the state model's existing construction-time validators are unchanged, and the exact
geometry code uses only the standard library.

## 10. Pre-Gate-9 frontend requirements

**R1 — the complete map frame must fit at 1440×900.** The whole framed map AND its legend must
be visible without scrolling at the Gate 9 viewport. This must be proven in a real browser with
bounding-box evidence; a JSDOM assertion cannot establish pixel layout. If a correction is
needed it is the smallest responsive layout change, in its own commit. The viewBox stays
`0 0 10000 10000` — cropping it to hide the problem is forbidden.

**R2 — no raw underscore identifiers as player-facing headings.** Scope stated precisely: the
shipped `StrategicMapScreen` does not currently violate this (its heading is "Strategic map" and
every row and detail field already uses `display_name`). The violation observed during review
came from the scratch preview harness, which is not production code. R2 is therefore added as a
standing guard test against the shipped screen, not a production text change.

## 11. Changed-file inventory

| File | Change | Commit |
|---|---|---|
| `docs/plans/strategic-map-m0-fictional-geography-revision.md` | new (this document) | A |
| `data/scenarios/tiny_valid.yaml` | polygons, centroids, anchors, + `shape_arken_isles` | B |
| `data/scenarios/decree_state.yaml` | polygons, centroids, anchors | B |
| `data/scenarios/deficit_demo.yaml` | polygons, centroids, anchors | B |
| `backend/tests/test_scenario.py` | three pinned digests | B |
| `backend/tests/test_map_authored_geometry.py` | new exact-geometry suite | B |
| `backend/tests/test_map_presentation_neutrality.py` | coordinate-bound docstring only, if stale | B |
| frontend layout + R2 guard | only if the real browser reproduces R1 | C |

Explicitly NOT changed: the frozen M0 plan, `RULESET_VERSION`, `SAVE_FORMAT_VERSION`, any save
fixture, `app/simulation/**`, `app/api/**`, the generated OpenAPI contract, and every non-map
field of all three scenarios.

## 12. Exclusions

This revision authorizes authored map GEOMETRY and nothing else. It does not introduce, imply or
prepare: provinces, cities, terrain mechanics, rivers, roads, resources, populations, military
bases, troop icons, units, movement, orders or combat. M1–M5 remain nonbinding and unstarted.
Selection on the strategic map remains inspection only.

## 13. Commit sequence

- **A** — `Strategic Map M0: freeze fictional-geography revision`. This document alone.
- **B** — `Strategic Map M0: author approved fictional scenario geography`. The three scenario
  YAMLs, the recomputed digests, and the exact-geometry suite. Pushed only after the full
  backend gate, OpenAPI drift check and determinism comparison are green.
- **C** — frontend viewport fit and the R2 guard, only if the real browser shows R1 failing.
- Then: real-browser preflight at 1440×900 for all three scenarios, delivered for review.
- Gate 9 and Commit 10 remain unstarted until that preflight is reviewed.

