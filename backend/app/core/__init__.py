"""Infrastructure primitives with no game-specific rules.

`app.core` sits below `app.simulation`. Nothing here knows what a "policy" or a
"population group" is — it provides deterministic randomness, a fixed-point
money type, canonical serialization, and shared error types that the
simulation engine builds on.
"""
