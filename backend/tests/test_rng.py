from __future__ import annotations

import random

import pytest

from app.core.rng import derive_rng, derive_seed


def _draw(seed: int, turn: int, stream: str, n: int = 8) -> list[float]:
    rng = derive_rng(seed, turn, stream)
    return [rng.random() for _ in range(n)]


def test_same_inputs_produce_identical_sequences() -> None:
    assert _draw(1, 0, "events") == _draw(1, 0, "events")


def test_different_seed_produces_different_sequence() -> None:
    assert _draw(1, 0, "events") != _draw(2, 0, "events")


def test_different_turn_produces_different_sequence() -> None:
    assert _draw(1, 0, "events") != _draw(1, 1, "events")


def test_different_stream_produces_different_sequence() -> None:
    assert _draw(1, 0, "events") != _draw(1, 0, "combat")


def test_empty_stream_name_rejected() -> None:
    with pytest.raises(ValueError, match="stream"):
        derive_rng(1, 0, "")


def test_derive_seed_is_what_derive_rng_actually_uses() -> None:
    seed = derive_seed(1, 0, "events")
    expected = random.Random(seed)
    actual = derive_rng(1, 0, "events")
    assert [expected.random() for _ in range(8)] == [actual.random() for _ in range(8)]


def test_derive_seed_is_deterministic_across_calls() -> None:
    assert derive_seed(5, 3, "combat") == derive_seed(5, 3, "combat")
