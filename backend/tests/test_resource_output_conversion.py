"""Tests for Phase 2C2's unit-bridge conversion function: `extracted_resource_to_real_output` is
the single named, explicit physical-to-real conversion point (not an implicit `int` pass-through
or a general-purpose `ResourceQuantity`-to-`RealOutput` cast).
"""

from __future__ import annotations

import pytest

from app.core.quantity import extracted_resource_to_real_output


def test_conversion_is_exact_multiplication_no_division() -> None:
    assert extracted_resource_to_real_output(extracted=0, real_output_per_unit=1_000) == 0
    assert extracted_resource_to_real_output(extracted=1, real_output_per_unit=1_000) == 1_000
    assert (
        extracted_resource_to_real_output(extracted=100_000, real_output_per_unit=1_000)
        == 100_000_000
    )
    assert (
        extracted_resource_to_real_output(extracted=500, real_output_per_unit=100_000) == 50_000_000
    )


def test_conversion_result_is_a_plain_int() -> None:
    result = extracted_resource_to_real_output(extracted=1_234, real_output_per_unit=567)
    assert isinstance(result, int)
    assert not isinstance(result, float)


def test_zero_extraction_yields_zero_output_regardless_of_coefficient() -> None:
    assert extracted_resource_to_real_output(extracted=0, real_output_per_unit=1) == 0
    assert extracted_resource_to_real_output(extracted=0, real_output_per_unit=10**12) == 0


def test_large_magnitudes_stay_exact() -> None:
    extracted = 90_000_000
    real_output_per_unit = 1_200
    assert (
        extracted_resource_to_real_output(
            extracted=extracted, real_output_per_unit=real_output_per_unit
        )
        == extracted * real_output_per_unit
    )


@pytest.mark.parametrize(
    "bad_extracted",
    [
        pytest.param(-1, id="negative"),
        pytest.param(10.0, id="whole-number-float"),
        pytest.param(10.5, id="fractional-float"),
        pytest.param("10", id="numeric-string"),
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
    ],
)
def test_conversion_rejects_invalid_extracted(bad_extracted: object) -> None:
    with pytest.raises(ValueError):
        extracted_resource_to_real_output(
            extracted=bad_extracted,  # type: ignore[arg-type]
            real_output_per_unit=1_000,
        )


@pytest.mark.parametrize(
    "bad_coefficient",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(10.0, id="whole-number-float"),
        pytest.param(10.5, id="fractional-float"),
        pytest.param("10", id="numeric-string"),
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
    ],
)
def test_conversion_rejects_invalid_coefficient(bad_coefficient: object) -> None:
    with pytest.raises(ValueError):
        extracted_resource_to_real_output(
            extracted=100,
            real_output_per_unit=bad_coefficient,  # type: ignore[arg-type]
        )


def test_conversion_is_used_identically_for_actual_and_potential_quantities() -> None:
    """The bridge takes no notion of "actual" vs. "potential" — the caller (`resource_output.py`)
    calls it twice per category with different inputs. Pinned here so a future refactor can't
    accidentally special-case one call site."""
    actual_extracted = 100_000
    potential_extracted = 150_000
    coefficient = 1_000
    assert (
        extracted_resource_to_real_output(
            extracted=actual_extracted, real_output_per_unit=coefficient
        )
        == actual_extracted * coefficient
    )
    assert (
        extracted_resource_to_real_output(
            extracted=potential_extracted, real_output_per_unit=coefficient
        )
        == potential_extracted * coefficient
    )
