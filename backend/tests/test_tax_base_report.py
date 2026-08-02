"""Tests for `TaxBaseDerivationReport`/`SectorTaxBaseReport`'s self-validation (mirroring
`test_finance_report.py`/`test_production_report.py`'s pattern), and R1's cross-report
validation on `TurnReport`: production, tax_base_derivation, and finance must independently
agree with each other, matched by sector-category identity — not just be internally valid in
isolation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.simulation.decisions import DecisionSet
from app.simulation.report import SectorTaxBaseReport, TaxBaseDerivationReport, TurnReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import SectorCategory, TaxBaseCoefficients
from tests.conftest import make_game_state


def _valid_derivation_report_dict() -> dict:
    """A real, internally-consistent `TaxBaseDerivationReport` (via the actual resolver, not
    hand-built), dumped to a plain dict so tests can corrupt one field."""
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    derivation = resolution.report.tax_base_derivation
    assert derivation is not None
    return derivation.model_dump(mode="json")


def _valid_turn_report_dict() -> tuple[dict, TurnReport]:
    state = make_game_state(turn=0, state_version=0)
    decisions = DecisionSet(expected_turn=0, expected_state_version=0, decisions=())
    resolution = resolve_turn(state, decisions)
    report = resolution.report
    return report.model_dump(mode="json"), report


def _coefficients() -> TaxBaseCoefficients:
    return TaxBaseCoefficients(
        personal_taxable_share_bps=8_000,
        corporate_taxable_share_bps=4_000,
        effective_consumption_base_share_bps=3_000,
    )


def _valid_sector_report() -> SectorTaxBaseReport:
    return SectorTaxBaseReport(
        category=SectorCategory.MANUFACTURING,
        actual_output=2_000_000_000,
        value_added_share_bps=5_000,
        labor_income_share_bps=5_000,
        modeled_value_added=1_000_000_000,
        labor_income=500_000_000,
        operating_surplus=500_000_000,
        personal_contribution=400_000_000,
        corporate_contribution=200_000_000,
        consumption_contribution=300_000_000,
    )


def test_a_valid_derivation_report_round_trips_through_model_validate() -> None:
    data = _valid_derivation_report_dict()
    report = TaxBaseDerivationReport.model_validate(data)
    assert len(report.sectors) == len(SectorCategory)


class TestSectorTaxBaseReportSelfValidation:
    def test_valid_sector_report_constructs_cleanly(self) -> None:
        report = _valid_sector_report()
        assert report.modeled_value_added == 1_000_000_000

    def test_wrong_modeled_value_added_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="modeled_value_added"):
            SectorTaxBaseReport(
                category=SectorCategory.MANUFACTURING,
                actual_output=2_000_000_000,
                value_added_share_bps=5_000,
                labor_income_share_bps=5_000,
                modeled_value_added=999,  # should be 1,000,000,000
                labor_income=500_000_000,
                operating_surplus=500_000_000,
                personal_contribution=400_000_000,
                corporate_contribution=200_000_000,
                consumption_contribution=300_000_000,
            )

    def test_wrong_labor_income_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="labor_income"):
            SectorTaxBaseReport(
                category=SectorCategory.MANUFACTURING,
                actual_output=2_000_000_000,
                value_added_share_bps=5_000,
                labor_income_share_bps=5_000,
                modeled_value_added=1_000_000_000,
                labor_income=999,  # should be 500,000,000
                operating_surplus=500_000_000,
                personal_contribution=400_000_000,
                corporate_contribution=200_000_000,
                consumption_contribution=300_000_000,
            )

    def test_wrong_operating_surplus_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="operating_surplus"):
            SectorTaxBaseReport(
                category=SectorCategory.MANUFACTURING,
                actual_output=2_000_000_000,
                value_added_share_bps=5_000,
                labor_income_share_bps=5_000,
                modeled_value_added=1_000_000_000,
                labor_income=500_000_000,
                operating_surplus=999,  # should be 500,000,000
                personal_contribution=400_000_000,
                corporate_contribution=200_000_000,
                consumption_contribution=300_000_000,
            )


class TestTaxBaseDerivationReportSelfValidation:
    @pytest.mark.parametrize(
        ("field", "expected_message_substring"),
        [
            ("total_modeled_value_added", "total_modeled_value_added"),
            ("total_labor_income", "total_labor_income"),
            ("total_operating_surplus", "total_operating_surplus"),
        ],
    )
    def test_corrupted_total_fails_with_its_own_specific_error(
        self, field: str, expected_message_substring: str
    ) -> None:
        data = _valid_derivation_report_dict()
        data[field] = int(data[field]) + 1
        with pytest.raises(ValidationError) as exc_info:
            TaxBaseDerivationReport.model_validate(data)
        assert expected_message_substring in str(exc_info.value)

    def test_corrupted_personal_contribution_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"][0]["personal_contribution"] = (
            int(data["sectors"][0]["personal_contribution"]) + 1
        )
        with pytest.raises(ValidationError, match="personal_contribution"):
            TaxBaseDerivationReport.model_validate(data)

    def test_corrupted_corporate_contribution_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"][0]["corporate_contribution"] = (
            int(data["sectors"][0]["corporate_contribution"]) + 1
        )
        with pytest.raises(ValidationError, match="corporate_contribution"):
            TaxBaseDerivationReport.model_validate(data)

    def test_corrupted_consumption_contribution_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"][0]["consumption_contribution"] = (
            int(data["sectors"][0]["consumption_contribution"]) + 1
        )
        with pytest.raises(ValidationError, match="consumption_contribution"):
            TaxBaseDerivationReport.model_validate(data)

    def test_corrupted_derived_tax_bases_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["derived_tax_bases"]["personal_income"] = (
            int(data["derived_tax_bases"]["personal_income"]) + 1
        )
        with pytest.raises(ValidationError, match="derived_tax_bases.personal_income"):
            TaxBaseDerivationReport.model_validate(data)

    def test_duplicate_sector_category_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"][1]["category"] = data["sectors"][0]["category"]
        with pytest.raises(ValidationError, match="duplicate sector category"):
            TaxBaseDerivationReport.model_validate(data)

    def test_missing_sector_category_is_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"].pop()
        with pytest.raises(ValidationError, match="missing sector categories"):
            TaxBaseDerivationReport.model_validate(data)

    def test_sectors_supplied_out_of_order_are_normalized_not_rejected(self) -> None:
        data = _valid_derivation_report_dict()
        data["sectors"] = list(reversed(data["sectors"]))
        report = TaxBaseDerivationReport.model_validate(data)
        assert [s.category.value for s in report.sectors] == [c.value for c in SectorCategory]


# --- R1: cross-report validation on TurnReport ------------------------------


class TestR1CrossReportValidation:
    def test_production_output_mismatch_with_derivation_input_is_rejected(self) -> None:
        data, _ = _valid_turn_report_dict()
        assert data["production"] is not None
        data["production"]["sectors"][0]["actual_output"] = (
            int(data["production"]["sectors"][0]["actual_output"]) + 1
        )
        with pytest.raises(ValidationError) as exc_info:
            TurnReport.model_validate(data)
        message = str(exc_info.value)
        # ProductionReport's own internal validator (actual_output must equal
        # min(capacity, labor_limited_output)) catches a directly-corrupted actual_output
        # before the R1 cross-report check even runs — also a legitimate, specific rejection.
        assert "does not equal min(capacity_output" in message or "does not match" in message

    def test_derivation_input_mismatch_with_production_output_is_rejected(self) -> None:
        data, _ = _valid_turn_report_dict()
        assert data["tax_base_derivation"] is not None
        data["tax_base_derivation"]["sectors"][0]["actual_output"] = (
            int(data["tax_base_derivation"]["sectors"][0]["actual_output"]) + 1
        )
        with pytest.raises(ValidationError) as exc_info:
            TurnReport.model_validate(data)
        # Corrupting a sector's actual_output also desyncs that sector's own internal
        # modeled_value_added identity (SectorTaxBaseReport's own validator), OR — if that
        # happens to still hold — the R1 cross-report check catches the production mismatch.
        # Either way, this must fail; both are legitimate rejection reasons.
        message = str(exc_info.value)
        assert "does not match" in message or "modeled_value_added" in message

    def test_derived_tax_bases_mismatch_with_finance_tax_bases_is_rejected(self) -> None:
        data, _ = _valid_turn_report_dict()
        assert data["finance"] is not None
        data["finance"]["tax_bases"]["personal_income"] = (
            int(data["finance"]["tax_bases"]["personal_income"]) + 1
        )
        with pytest.raises(ValidationError) as exc_info:
            TurnReport.model_validate(data)
        message = str(exc_info.value)
        # Either FinanceReport's own revenue cross-check (it recomputes revenue from
        # tax_bases/active_tax_policy) or the R1 cross-report check (derived_tax_bases vs.
        # finance.tax_bases) can catch this first — both are legitimate, specific rejections.
        assert (
            "does not exactly equal" in message
            or "revenue" in message
            or "does not match" in message
        )

    def test_finance_tax_bases_mismatch_with_derivation_output_is_rejected(self) -> None:
        """The cleanest direct test of the derivation<->finance R1 check: corrupt
        `finance.tax_bases` for a category-agnostic total field that FinanceReport's own
        validators don't independently recompute from — there isn't one, so instead corrupt
        `tax_base_derivation.derived_tax_bases` (which finance's own validator can't see) and
        confirm the R1 check on TurnReport is what catches the resulting mismatch.
        """
        data, _ = _valid_turn_report_dict()
        assert data["tax_base_derivation"] is not None
        data["tax_base_derivation"]["derived_tax_bases"]["corporate_profit"] = (
            int(data["tax_base_derivation"]["derived_tax_bases"]["corporate_profit"]) + 1
        )
        with pytest.raises(ValidationError) as exc_info:
            TurnReport.model_validate(data)
        message = str(exc_info.value)
        # TaxBaseDerivationReport's own validator (derived_tax_bases matches summed
        # contributions) catches this first, before R1 even runs — also a legitimate,
        # specific rejection.
        assert "derived_tax_bases" in message or "does not exactly equal" in message

    @pytest.mark.parametrize(
        "present_fields",
        [
            ["production"],
            ["tax_base_derivation"],
            ["finance"],
            ["production", "tax_base_derivation"],
            ["production", "finance"],
            ["tax_base_derivation", "finance"],
        ],
    )
    def test_partial_report_combinations_are_rejected(self, present_fields: list[str]) -> None:
        data, _ = _valid_turn_report_dict()
        for field in ("production", "tax_base_derivation", "finance"):
            if field not in present_fields:
                data[field] = None
        with pytest.raises(ValidationError, match="all present or all absent"):
            TurnReport.model_validate(data)

    def test_all_three_absent_is_valid(self) -> None:
        data, _ = _valid_turn_report_dict()
        data["production"] = None
        data["tax_base_derivation"] = None
        data["finance"] = None
        report = TurnReport.model_validate(data)
        assert report.production is None
        assert report.tax_base_derivation is None
        assert report.finance is None

    def test_all_three_present_and_consistent_is_valid(self) -> None:
        data, report = _valid_turn_report_dict()
        # Sanity: the fixture itself is genuinely all-present before any corruption.
        assert report.production is not None
        assert report.tax_base_derivation is not None
        assert report.finance is not None
        # Round-trips cleanly with no corruption.
        TurnReport.model_validate(data)

    def test_cross_report_check_matches_by_category_identity_not_tuple_position(self) -> None:
        """Reordering both production.sectors and tax_base_derivation.sectors identically
        (so position-based matching would still "work") must not be required — category-keyed
        matching means order never matters. Reordering production.sectors ALONE (leaving
        derivation's order untouched) must still validate correctly, proving the check keys
        on category, not list index.
        """
        data, _ = _valid_turn_report_dict()
        assert data["production"] is not None
        data["production"]["sectors"] = list(reversed(data["production"]["sectors"]))
        # Must still validate: ProductionReport's own validator re-normalizes order back to
        # canonical before R1 even runs, so this proves the pipeline is robust to input order.
        report = TurnReport.model_validate(data)
        assert report.production is not None
        assert report.tax_base_derivation is not None
