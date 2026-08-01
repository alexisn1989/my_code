"""Deterministic, namespaced random number generation.

Every `GameState` carries an integer `seed`. Simulation code that needs
randomness must obtain a `random.Random` from `derive_rng` rather than using
the `random` module's global functions or any other entropy source — this is
what makes turn resolution reproducible given the same seed, turn, and
decisions (see `docs/architecture.md`, "Deterministic simulation").

`random` itself may only be imported here. `tests/test_no_forbidden_imports.py`
enforces that with an AST walk over `app/simulation` — not a docstring promise.
"""

from __future__ import annotations

import random
from hashlib import blake2b

_DIGEST_SIZE = 8  # bytes; plenty of entropy for seeding random.Random, small hash cost


def derive_seed(game_seed: int, turn: int, stream: str) -> int:
    """Derive a deterministic integer seed for one (game, turn, stream) triple.

    `stream` namespaces independent random draws within a turn (e.g. "events"
    vs. "combat") so that adding a new consumer of randomness for one system
    cannot shift the sequence drawn by an unrelated system — a common source
    of "deterministic but fragile" bugs where reordering call sites changes
    outcomes.
    """
    if not stream:
        raise ValueError("stream name must be non-empty")
    payload = f"{game_seed}:{turn}:{stream}".encode()
    digest = blake2b(payload, digest_size=_DIGEST_SIZE).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def derive_rng(game_seed: int, turn: int, stream: str) -> random.Random:
    """Return a `random.Random` deterministically seeded for this draw.

    Identical `(game_seed, turn, stream)` always yields an RNG that produces
    the identical sequence of outputs; any difference in any of the three
    inputs is expected to (and, per `test_rng.py`, does) produce a different
    sequence.
    """
    return random.Random(derive_seed(game_seed, turn, stream))
