"""The MANDATE simulation engine.

Pure game logic: no FastAPI, no SQLAlchemy, no I/O. Construct a `GameState`
(directly or via `scenario.load_scenario`), submit a `DecisionSet`, call
`resolver.resolve_turn`, and get back a new `GameState` plus a `TurnReport`.
See `docs/architecture.md` for the full contract.
"""
