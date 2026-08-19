"""The Phase 4A local graphical application's HTTP boundary.

This package is a **thin adapter over the frozen engine**, never a second
implementation of it. It imports `app.simulation` / `app.content` / `app.saves`
and calls them; it contains no simulation formula, no calibration, and no
mechanic of its own. Anything that decides what is *true* in the game lives in
the engine and is reached from here by a function call.

Design record: `docs/adr/0014-graphical-vertical-slice-architecture.md`.
Shape record: `docs/contracts/phase4a-api-contract.yaml`.
Binding plan: `docs/plans/phase-4a-graphical-vertical-slice-implementation-plan.md`.

Why this package sits outside the determinism guard: the AST scan in
`tests/test_no_forbidden_imports.py` covers `app/core` and `app/simulation`
only, because those must be free of randomness, wall-clock time and floats. An
HTTP layer legitimately needs `uuid4` for save IDs and the filesystem for save
storage -- exactly the reasoning that already puts `app/saves.py` outside the
scan. None of it touches game determinism: every seeded stream still belongs to
the engine alone.
"""
