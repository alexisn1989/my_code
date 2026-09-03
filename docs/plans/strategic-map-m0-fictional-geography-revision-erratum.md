# Strategic Map M0 — fictional-geography revision erratum

**Status:** docs-only. Corrects two reporting defects in the frozen revision document. No geometry,
no coordinate, no version, no mechanic and no plan decision changes.
**Frozen revision document:** `docs/plans/strategic-map-m0-fictional-geography-revision.md`,
SHA-256 `651c20fba139365e6b229131eb2f5a673ceb344e58810deaa4d760abd567b97f`, frozen in commit
`7d3537a` and left byte-identical by this erratum.
**Frozen M0 plan:** `docs/plans/strategic-military-map-m0-implementation-plan.md`, SHA-256
`c1bdb29080fba4feb6a2943902317783b782df49da431b643941f13f8b672f20`, likewise unchanged.
**Applies to:** §11 (changed-file inventory), and the prose vertex count reported for
`shape_vetruska` during the proposal round.

Both corrections are to *reporting*. The approved coordinate arrays in §4 are authoritative and are
untouched; the scenario YAML carries them through byte-for-byte.

## 1. §11 omitted `backend/tests/test_api_contract.py`

The changed-file inventory in §11 lists four backend test files. It should have listed five.

`backend/tests/test_api_contract.py::test_strategic_map_matches_the_authored_tiny_valid_scenario`
pins the shape count of the `tiny_valid` projection:

```python
assert len(body["shapes"]) == 3
```

That assertion changes to `== 4`, and for exactly one reason: the revision adds
`shape_arken_isles` to `tiny_valid`. That addition is an approved decision — §3 item 1 of the frozen
revision authorizes it as a decorative, player-owned shape that creates no theater, route,
population, resource, city, province or mechanic, and §4's shape-count table already records
`tiny_valid` 3 → 4 with the annotation "+ `shape_arken_isles`".

The new expected value is therefore derived from the approved decision, not from the failing test's
output. No other assertion in that test changes: `map_id`, `capital_theater_id`, the theater count,
the sorted-id ordering, the capital flag and the capital's owner display name all hold as written.

Inventory row that §11 should have carried:

| File | Change | Commit |
|---|---|---|
| `backend/tests/test_api_contract.py` | `tiny_valid` shape count 3 → 4, per §3 item 1 and §4 | B |

## 2. `shape_vetruska` has 30 vertices; the "25" reported during the proposal round was a typo

A proposal-round summary described `shape_vetruska` as having 25 vertices. Every authoritative
artifact says 30. The four sources were counted mechanically and compared for exact array equality,
not merely for matching counts:

| Source | SHA-256 | `shape_vetruska` |
|---|---|---|
| Frozen revision document §4.1 | `651c20fba139365e6b229131eb2f5a673ceb344e58810deaa4d760abd567b97f` | 30 |
| Approved coordinate tables (`coordinate-tables.txt`) | `dcd049b6a4d762cae6e3a060c60c549a2d5485af594ab7989ec3597030fb9794` | 30 |
| Approved preview source SVG (`tiny-valid-fictional-map-preview.svg`) | `1090857c820b85092d89489ff13237adf775918ce896a215db753735676c8d82` | 30 |
| Scenario YAML as implemented (`data/scenarios/tiny_valid.yaml`) | `d19200c5f6962c0249458efe3203294c144c1e65f57c7edf93cdbd60be73896c` | 30 |

The reviewed PNG for that SVG hashes to
`0e5b9fbae2943d86801fb37367503615961693852a771afa819551c219f3cb0f`. The scenario YAML hash above is
the content that lands in commit B; this erratum is docs-only and is pushed ahead of it.

The audit covered every `tiny_valid` shape, so a discrepancy elsewhere could not hide behind a
vetruska-only check. For all four shapes, the revision document, the coordinate tables and the
scenario YAML hold **identical** integer arrays, and each YAML array occurs verbatim among the
approved preview SVG's `points` arrays:

| Shape | Revision | Tables | YAML | Present verbatim in the approved preview SVG |
|---|---|---|---|---|
| `shape_arken` | 35 | 35 | 35 | yes, exact |
| `shape_arken_isles` | 8 | 8 | 8 | yes, exact |
| `shape_kessia` | 31 | 31 | 31 | yes, exact |
| `shape_vetruska` | 30 | 30 | 30 | yes, exact |

`shape_vetruska` runs from `[6550, 1900]` to `[6720, 2500]` as an open ring, sharing its western
boundary with `shape_kessia` exactly as §4.1 records.

**Resolution:** the authoritative count is 30. The "25" was a reporting typo in prose and never
reached any artifact, table, preview or scenario file. No polygon is redrawn, and the preflight
expectation of 30 vertices stands.

## 3. What this erratum does not change

No approved coordinate array, no centroid, no label anchor, no shape ordering, no owner, no theater
id, no route, no capital. `RULESET_VERSION` stays `0.14.0` and `SAVE_FORMAT_VERSION` stays `1`, on
the evidence recorded in the frozen revision. The three pinned canonical-JSON digests keep the
values pre-recorded in the revision document before implementation. Gate 9 and Commit 10 remain
paused, and M1–M5 mechanics remain out of scope.
