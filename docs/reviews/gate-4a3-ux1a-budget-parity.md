# Gate 4A3 UX-1a: the budget-parity gap in UX-1's tests, closed

This is a forward-only correction to UX-1 (`bf66b8e6`). It changes tests and adds this record. No
production code changes, and the committed UX-1 record (`gate-4a3-ux1-route-aware-preview.md`) is
left as it is. This file is the correction to it.

## 1. The finding

The finding comes from the user's review of the pushed `bf66b8e6`.

The approved plan required preview/resolve parity for `tiny_valid` (bicameral) in two cases:

> a budget failing in **one** chamber and one failing in **both**, compared row for row.

UX-1 shipped two tests.
- **A budget failing in one chamber.** This matched the plan: chamber verdicts, then supporting and
  required seats compared with the resolved trace row by row.
- **An amendment failing in both chambers.** This was **not** a budget. It checked only the preview's
  `carries` flags and that the headline said "fail" or "blocked". It never compared the resolved
  chamber tallies.

The UX-1 record still described the amendment row's resolution as "equal" (§1, parity table, row "bicameral
amendment failing in **both**"), and no assertion proved it. **UX-1 therefore fell short of the
approved test requirement on both points.**

**Measured, not assumed.** I ran the committed test file against a preview whose amendment tallies
were deliberately wrong, with `supporting_seats + 1` and then `required_seats + 1`. Both times the
committed test **passed**: `1 passed`. The gap was real.

## 2. The correction (`backend/tests/test_api_preview_parity.py`)

**New: `test_a_bicameral_budget_failing_in_both_chambers_matches_resolution_row_for_row`.**
- Shipped `tiny_valid` cannot produce a budget failing in either chamber, as UX-1 measured. So this
  test uses a **test-only variant**, written under `tmp_path` and loaded through the production
  scenario loader. **No shipped scenario changes.**
- `_rebalance_tiny_both_chambers` moves seats from `civic_union/mainstream` to
  `national_front/conservatives`: 10 lower and 6 upper.
- Measured on the default budget, moving lower seats only (with 6 upper):

  | lower seats moved | 0 | 2 | 4 | 6 | 8 |
  |---|---|---|---|---|---|
  | lower supporting, of 51 required | 58 | 56 | 54 | 52 | 50, fails |

  The upper chamber fails at 27 of 31 throughout. Eight is the knife edge, so ten leaves a margin.
- It asserts:
  - the preview gives `{lower: false, upper: false}` and `would_pass: false`;
  - resolution returns 200;
  - for **each** chamber, the resolved trace row exists, and its supporting and required seats equal
    the preview's;
  - the headline says "blocked".
- The comparison lives in `_assert_budget_tallies_match`. That helper first asserts that each trace
  row **exists**, so a missing row cannot pass by never being compared.

**Strengthened: `test_a_bicameral_amendment_failing_in_both_chambers_matches_resolution`.** The record's
"equal" claim is now **proved**, not narrowed.
- Resolution records each amendment chamber in the trace as `Amendment {chamber}: supporting of
  required` = `"{supporting} of {required}"`. Measured: `58 of 67` for the lower chamber and
  `33 of 40` for the upper.
- The test asserts that both rows exist and equal the preview's `supporting_seats` and
  `required_seats` for that chamber.
- It also asserts that the headline starts with "Amendment failed". Previously it accepted either
  "fail" or "blocked".

## 3. The new assertions bite

Each mutation below was applied to `app/api/preview.py`, then the file was restored and verified with
`cmp` and a clean `git diff`.

| mutation | failing test |
|---|---|
| budget chamber `supporting_seats + 1` (line 429) | `…budget_failing_in_both_chambers…` |
| budget chamber `required_seats + 1` (line 430) | `…budget_failing_in_both_chambers…` |
| amendment chamber `supporting_seats + 1` (line 483) | `…amendment_failing_in_both_chambers…` |
| amendment chamber `required_seats + 1` (line 484) | `…amendment_failing_in_both_chambers…` |

A +1 changes no verdict here: 48 of 51 and 58 of 67 still fail. So each failure comes from the tally
comparison itself, not from a flipped `carries`.

## 4. Isolation

The UX-2 work was uncommitted in the main checkout throughout. This correction was made and gated in
a separate detached `git worktree` at `bf66b8e6`, with the main checkout's virtualenv interpreter
called directly. There was no `uv run`, so no environment was synced or created.
- `app` was confirmed to import from the worktree.
- The worktree's resolved headline still read "…Committed capital was still spent." for a turn with
  no capital committed. That is the **pre-UX-2** wording, so UX-2's uncommitted `projections.py`
  change was not in play.

The commit was made in the worktree. The branch then fast-forwarded to it (`git merge --ff-only`),
which did not touch the UX-2 working-tree changes: the correction modifies none of their paths.

## 5. Gates

Each gate was run separately in the worktree, and each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `pytest -q tests/test_api_preview_parity.py` | 0 | `41 passed`: 40 → 41, +1 test (`test_a_bicameral_budget_failing_in_both_chambers_matches_resolution_row_for_row`); the amendment test is strengthened, not added |
| `ruff check .` | 0 | `All checks passed!` |
| `ruff format --check .` | 0 | `190 files already formatted` |
| bare `mypy` | 0 | `Success: no issues found in 56 source files` |
| full backend suite `pytest -q; echo PYTEST_EXIT=$?` | **0** | `36364 passed, 1 warning in 1445.00s (0:24:04)`: +1 from UX-1's 36,363, exactly the new test; the 1 warning is the known `StarletteDeprecationWarning` |

**Not run, and why.** No frontend, browser or contract gate was run: this commit changes one backend
test file and adds this record. Production code is unchanged, so `generate:api` and the built SPA
cannot differ from UX-1.
