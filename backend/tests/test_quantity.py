from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.core.quantity import (
    StrictRealOutput,
    StrictRealOutputPerResourceUnit,
    StrictRealOutputPerWorker,
    StrictWorkerCount,
)


class _WorkerCountHolder(BaseModel):
    value: StrictWorkerCount


class _RealOutputHolder(BaseModel):
    value: StrictRealOutput


class _RealOutputPerWorkerHolder(BaseModel):
    value: StrictRealOutputPerWorker


class _RealOutputPerResourceUnitHolder(BaseModel):
    value: StrictRealOutputPerResourceUnit


INVALID_INT_REPRESENTATIONS = [
    pytest.param(10.0, id="whole-number-float"),
    pytest.param(10.5, id="fractional-float"),
    pytest.param("10", id="numeric-string"),
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_worker_count_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _WorkerCountHolder(value=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_real_output_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _RealOutputHolder(value=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_real_output_per_worker_rejects_invalid_representations(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        _RealOutputPerWorkerHolder(value=bad_value)


@pytest.mark.parametrize("bad_value", INVALID_INT_REPRESENTATIONS)
def test_strict_real_output_per_resource_unit_rejects_invalid_representations(
    bad_value: object,
) -> None:
    with pytest.raises(ValidationError):
        _RealOutputPerResourceUnitHolder(value=bad_value)


def test_strict_worker_count_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _WorkerCountHolder(value=-1)


def test_strict_worker_count_accepts_zero() -> None:
    assert _WorkerCountHolder(value=0).value == 0


def test_strict_real_output_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _RealOutputHolder(value=-1)


def test_strict_real_output_accepts_zero() -> None:
    assert _RealOutputHolder(value=0).value == 0


def test_strict_real_output_per_worker_rejects_zero() -> None:
    # gt=0, not ge=0 (R2/decision #3): "no output" is expressed only via
    # employed_workers == 0, not by zeroing output_per_worker too.
    with pytest.raises(ValidationError):
        _RealOutputPerWorkerHolder(value=0)


def test_strict_real_output_per_worker_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _RealOutputPerWorkerHolder(value=-1)


def test_strict_real_output_per_worker_accepts_positive() -> None:
    assert _RealOutputPerWorkerHolder(value=1).value == 1


def test_strict_real_output_per_resource_unit_rejects_zero() -> None:
    # gt=0, not ge=0 (Phase 2C2, D5): "no output from this resource" is expressed only via
    # extracted == 0, not by zeroing the coefficient too.
    with pytest.raises(ValidationError):
        _RealOutputPerResourceUnitHolder(value=0)


def test_strict_real_output_per_resource_unit_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        _RealOutputPerResourceUnitHolder(value=-1)


def test_strict_real_output_per_resource_unit_accepts_positive() -> None:
    assert _RealOutputPerResourceUnitHolder(value=1).value == 1


def test_ordinary_integers_still_work() -> None:
    assert _WorkerCountHolder(value=42).value == 42
    assert _RealOutputHolder(value=42).value == 42


def test_very_large_integers_still_work_deterministically() -> None:
    large = 10**15
    assert _WorkerCountHolder(value=large).value == large
    assert _RealOutputHolder(value=large).value == large
    assert _RealOutputPerWorkerHolder(value=large).value == large
    assert _RealOutputPerResourceUnitHolder(value=large).value == large


def test_no_actual_bool_subclass_leaks_through() -> None:
    """Same empirically-verified pydantic strict-int behavior pinned for
    `StrictMoney` in `test_money.py`, re-verified for the quantity aliases:
    `bool` is an `int` subclass in plain Python, but strict=True rejects it."""
    with pytest.raises(ValidationError):
        _WorkerCountHolder(value=True)
    with pytest.raises(ValidationError):
        _RealOutputHolder(value=True)
