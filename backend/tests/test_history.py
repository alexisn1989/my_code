"""Tests for the immutable, hash-chained history layer (`simulation.history`)."""

from __future__ import annotations

import dataclasses

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import HistoryValidationError, SnapshotNotFoundError, TurnResolutionError
from app.simulation.decisions import (
    BudgetDecision,
    DecisionSet,
    InfluenceAllocation,
    SpendingUpdate,
)
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.legislature import ProposalRoute
from app.simulation.report import TurnReportEntry
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json
from app.simulation.state import SpendingCategory
from tests.conftest import make_game_state

_SFV = SAVE_FORMAT_VERSION


def _fresh_save() -> GameSave:
    return new_game(make_game_state(turn=0, state_version=0), save_format_version=_SFV)


def _empty_decisions_for(save: GameSave) -> DecisionSet:
    state = save.current_state()
    return DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=[]
    )


def _advance_n(save: GameSave, n: int) -> GameSave:
    for _ in range(n):
        save = advance_game(save, _empty_decisions_for(save))
    return save


# --- genesis, growth, and per-turn bookkeeping -------------------------------


def test_new_game_has_exactly_one_genesis_entry() -> None:
    save = _fresh_save()
    assert len(save.entries) == 1
    assert save.entry_count == 1
    genesis = save.entries[0]
    assert genesis.turn == 0
    assert genesis.previous_entry_hash is None
    assert genesis.decisions_json is None
    assert genesis.report_json is None
    assert save.head_entry_hash == genesis.entry_hash
    assert validate_history(save) == []


def test_resolving_eight_turns_produces_turn_eight_and_nine_entries() -> None:
    save = _advance_n(_fresh_save(), 8)
    assert save.current_turn() == 8
    assert len(save.entries) == 9
    assert save.entry_count == 9
    assert validate_history(save) == []


def test_every_successful_resolution_appends_exactly_one_entry() -> None:
    save = _fresh_save()
    for expected_len in range(2, 6):
        save = advance_game(save, _empty_decisions_for(save))
        assert len(save.entries) == expected_len
        assert save.entry_count == expected_len


def test_failed_resolution_appends_nothing() -> None:
    save = _fresh_save()
    stale = DecisionSet(expected_turn=99, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        advance_game(save, stale)
    assert len(save.entries) == 1
    assert save.entry_count == 1


def test_invalid_decisions_leave_save_byte_equivalent() -> None:
    save = _fresh_save()
    before = dump_save_json(save)
    stale = DecisionSet(expected_turn=99, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        advance_game(save, stale)
    assert dump_save_json(save) == before


def test_successful_turn_updates_count_and_head_hash_exactly_once() -> None:
    save = _fresh_save()
    before_count, before_head = save.entry_count, save.head_entry_hash

    advanced = advance_game(save, _empty_decisions_for(save))

    assert advanced.entry_count == before_count + 1
    assert advanced.head_entry_hash == advanced.entries[-1].entry_hash
    assert advanced.head_entry_hash != before_head
    # advance_game never mutates its input.
    assert save.entry_count == before_count
    assert save.head_entry_hash == before_head


def test_failed_turn_changes_neither_count_nor_head_hash() -> None:
    save = _fresh_save()
    before_count, before_head = save.entry_count, save.head_entry_hash
    stale = DecisionSet(expected_turn=99, expected_state_version=0, decisions=[])
    with pytest.raises(TurnResolutionError):
        advance_game(save, stale)
    assert save.entry_count == before_count
    assert save.head_entry_hash == before_head


def test_advance_game_refuses_to_advance_an_invalid_save() -> None:
    bad_save = dataclasses.replace(_fresh_save(), head_entry_hash="0" * 64)
    with pytest.raises(HistoryValidationError):
        advance_game(bad_save, _empty_decisions_for(bad_save))


# --- retrieval and immutability ----------------------------------------------


def test_any_entry_retrievable_by_turn_number() -> None:
    save = _advance_n(_fresh_save(), 5)
    for turn in range(6):
        assert save.entry_at(turn).turn == turn


def test_invalid_turn_request_raises_clearly() -> None:
    save = _advance_n(_fresh_save(), 3)
    with pytest.raises(SnapshotNotFoundError):
        save.entry_at(99)
    with pytest.raises(SnapshotNotFoundError):
        save.entry_at(-1)


def test_mutating_retrieved_state_does_not_affect_history() -> None:
    save = _fresh_save()
    before = dump_save_json(save)

    retrieved = save.entry_at(0).state()
    retrieved.world.countries[retrieved.world.player_country_id].population = 999_999_999

    assert dump_save_json(save) == before
    reloaded = save.current_state()
    assert reloaded.world.countries[reloaded.world.player_country_id].population != 999_999_999


def test_mutating_current_state_does_not_affect_history() -> None:
    save = _fresh_save()
    before = dump_save_json(save)

    current = save.current_state()
    current.world.countries[current.world.player_country_id].population = 42

    assert dump_save_json(save) == before


def test_mutating_retrieved_decisions_does_not_affect_history() -> None:
    save = _advance_n(_fresh_save(), 1)
    before = dump_save_json(save)

    decisions = save.entry_at(1).decisions()
    assert decisions is not None
    decisions.decisions = (*decisions.decisions, BudgetDecision(personal_income_rate_bps=1234))

    assert dump_save_json(save) == before


def test_mutating_retrieved_report_does_not_affect_history() -> None:
    save = _advance_n(_fresh_save(), 1)
    before = dump_save_json(save)

    report = save.entry_at(1).report()
    assert report is not None
    report.entries.append(TurnReportEntry(category="tamper", reason_id="tampered"))

    assert dump_save_json(save) == before


def test_independent_retrievals_return_independent_objects() -> None:
    save = _advance_n(_fresh_save(), 1)
    entry = save.entry_at(1)

    state_a, state_b = entry.state(), entry.state()
    assert state_a is not state_b
    assert state_a == state_b

    decisions_a, decisions_b = entry.decisions(), entry.decisions()
    assert decisions_a is not decisions_b

    report_a, report_b = entry.report(), entry.report()
    assert report_a is not report_b

    current_a, current_b = save.current_state(), save.current_state()
    assert current_a is not current_b


# --- tampering: state, decisions, report, each independently ----------------


def _tamper_state_json(save: GameSave, index: int) -> GameSave:
    original = save.entries[index]
    tampered_state = original.state()
    country_id = tampered_state.world.player_country_id
    tampered_state.world.countries[country_id].population += 1
    tampered_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    return dataclasses.replace(save, entries=entries)


def test_tampering_with_state_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    tampered = _tamper_state_json(save, index=len(save.entries) - 1)
    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_decisions_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    decisions = original.decisions()
    assert decisions is not None
    decisions.decisions = (*decisions.decisions, BudgetDecision(personal_income_rate_bps=1234))
    tampered_json = canonical_dumps(decisions.model_dump(mode="json"))
    tampered_entry = dataclasses.replace(original, decisions_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_report_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    tampered_report = report.model_copy(
        update={"entries": [*report.entries, TurnReportEntry(category="tamper", reason_id="x")]}
    )
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_production_report_is_detected() -> None:
    """Dedicated Phase 2B1 tamper test: `report.production` is new surface
    area covered by `entry_hash` — this must not be assumed to work just
    because the generic `report.entries` tamper test above passes.
    """
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.production is not None
    tampered_production = report.production.model_copy(
        update={"total_gross_output": report.production.total_gross_output + 1}
    )
    tampered_report = report.model_copy(update={"production": tampered_production})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_economy_state_is_detected() -> None:
    """Dedicated Phase 2B1 tamper test: `state...economy` is new surface area
    covered by `entry_hash`, independent of the report-tamper test above."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    tampered_state = original.state()
    country_id = tampered_state.world.player_country_id
    country = tampered_state.world.countries[country_id]
    assert country.economy is not None
    tampered_state.world.countries[country_id] = country.model_copy(
        update={
            "economy": country.economy.model_copy(
                update={
                    "sectors": tuple(
                        s.model_copy(update={"output_per_worker": s.output_per_worker + 1})
                        if i == 0
                        else s
                        for i, s in enumerate(country.economy.sectors)
                    )
                }
            )
        }
    )
    tampered_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_tax_base_derivation_report_is_detected() -> None:
    """Dedicated Phase 2B2 tamper test: `report.tax_base_derivation` is new surface area
    covered by `entry_hash`, independent of the production/finance tamper tests above."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.tax_base_derivation is not None
    tampered_derivation = report.tax_base_derivation.model_copy(
        update={
            "total_modeled_value_added": report.tax_base_derivation.total_modeled_value_added + 1
        }
    )
    tampered_report = report.model_copy(update={"tax_base_derivation": tampered_derivation})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_resource_deposit_state_is_detected() -> None:
    """Dedicated Phase 2C1 tamper test (T16): `state...economy.resource_deposits` is new surface
    area covered by `entry_hash`, independent of every other tamper test above. Tampers a
    nonrenewable category (`IRON_ORE`, index 1) rather than `TIMBER` (index 0) specifically to
    avoid also tripping the renewable ceiling invariant — `make_resource_deposits`'s default sets
    a renewable's `stock_ceiling` equal to its `remaining_stock`, so bumping the stock alone
    would push it past its own ceiling and conflate two different kinds of detection.
    """
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    tampered_state = original.state()
    country_id = tampered_state.world.player_country_id
    country = tampered_state.world.countries[country_id]
    assert country.economy is not None
    tampered_state.world.countries[country_id] = country.model_copy(
        update={
            "economy": country.economy.model_copy(
                update={
                    "resource_deposits": tuple(
                        d.model_copy(update={"remaining_stock": d.remaining_stock + 1})
                        if i == 1
                        else d
                        for i, d in enumerate(country.economy.resource_deposits)
                    )
                }
            )
        }
    )
    tampered_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_resource_extraction_report_is_detected() -> None:
    """Dedicated Phase 2C1 tamper test (T16): `report.resources` is new surface area covered by
    `entry_hash`, independent of the production/labor-market/tax-base tamper tests above."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.resources is not None
    tampered_resources = report.resources.model_copy(
        update={"unassigned_resource_workers": report.resources.unassigned_resource_workers + 1}
    )
    tampered_report = report.model_copy(update={"resources": tampered_resources})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_resource_output_coefficients_is_detected() -> None:
    """Dedicated Phase 2C2 tamper test (T24): `state...economy.resource_output_coefficients` is
    new surface area covered by `entry_hash`, independent of every other tamper test above."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    tampered_state = original.state()
    country_id = tampered_state.world.player_country_id
    country = tampered_state.world.countries[country_id]
    assert country.economy is not None
    tampered_state.world.countries[country_id] = country.model_copy(
        update={
            "economy": country.economy.model_copy(
                update={
                    "resource_output_coefficients": tuple(
                        c.model_copy(update={"real_output_per_unit": c.real_output_per_unit + 1})
                        if i == 0
                        else c
                        for i, c in enumerate(country.economy.resource_output_coefficients)
                    )
                }
            )
        }
    )
    tampered_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_extraction_sector_output_totals_is_detected() -> None:
    """Dedicated Phase 2C2 tamper test (T24): `report.resources.extraction_sector_real_output`/
    `.extraction_sector_potential_output` are new surface area covered by `entry_hash`,
    independent of `test_tampering_with_only_the_resource_extraction_report_is_detected` above
    (which tampers a pre-existing Phase 2C1 field)."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.resources is not None
    tampered_resources = report.resources.model_copy(
        update={"extraction_sector_real_output": report.resources.extraction_sector_real_output + 1}
    )
    tampered_report = report.model_copy(update={"resources": tampered_resources})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_a_deposit_real_output_contribution_is_detected() -> None:
    """Dedicated Phase 2C2 tamper test (T24): `ResourceDepositReport.real_output_contribution`
    is new surface area covered by `entry_hash`."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.resources is not None
    tampered_deposits = tuple(
        d.model_copy(update={"real_output_contribution": d.real_output_contribution + 1})
        if i == 0
        else d
        for i, d in enumerate(report.resources.deposits)
    )
    tampered_resources = report.resources.model_copy(update={"deposits": tampered_deposits})
    tampered_report = report.model_copy(update={"resources": tampered_resources})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_tampering_with_only_the_tax_base_coefficients_is_detected() -> None:
    """Dedicated Phase 2B2 tamper test: `finance.tax_base_coefficients` is new surface area
    covered by `entry_hash`, independent of the economy-sector tamper test above."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    tampered_state = original.state()
    country_id = tampered_state.world.player_country_id
    country = tampered_state.world.countries[country_id]
    assert country.finance is not None
    coefficients = country.finance.tax_base_coefficients
    tampered_state.world.countries[country_id] = country.model_copy(
        update={
            "finance": country.finance.model_copy(
                update={
                    "tax_base_coefficients": coefficients.model_copy(
                        update={
                            "personal_taxable_share_bps": coefficients.personal_taxable_share_bps
                            + 1
                        }
                    )
                }
            )
        }
    )
    tampered_json = canonical_dumps(tampered_state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_noncanonical_stored_payload_is_rejected_without_normalization() -> None:
    save = _fresh_save()
    genesis = save.entries[0]
    # Same JSON *value* as the canonical form (json.loads ignores whitespace),
    # but the *stored string* is no longer byte-identical to its canonical
    # form — this is invisible to hash recomputation (which operates on the
    # parsed value) and must be caught by the separate canonical-JSON check.
    noncanonical = genesis.state_json.replace('"turn":0', '"turn": 0')
    assert noncanonical != genesis.state_json
    bad_genesis = dataclasses.replace(genesis, state_json=noncanonical)
    bad_save = dataclasses.replace(save, entries=(bad_genesis,))

    problems = validate_history(bad_save)
    assert any("not canonical JSON" in p for p in problems)
    assert not any("entry_hash does not match" in p for p in problems)


# --- reordering, truncation, and envelope consistency ------------------------


def test_reordering_entries_is_detected() -> None:
    save = _advance_n(_fresh_save(), 3)
    swapped = (save.entries[0], save.entries[2], save.entries[1], save.entries[3])
    reordered = dataclasses.replace(save, entries=swapped)
    assert validate_history(reordered)


def test_removing_an_internal_entry_is_detected() -> None:
    save = _advance_n(_fresh_save(), 3)
    without_middle = (*save.entries[:2], *save.entries[3:])
    tampered = dataclasses.replace(
        save,
        entries=without_middle,
        entry_count=len(without_middle),
        head_entry_hash=without_middle[-1].entry_hash,
    )
    assert validate_history(tampered)


def test_removing_the_final_entry_without_updating_envelope_is_detected() -> None:
    save = _advance_n(_fresh_save(), 3)
    truncated = dataclasses.replace(save, entries=save.entries[:-1])
    problems = validate_history(truncated)
    assert any("entry_count" in p for p in problems)
    assert any("head_entry_hash" in p for p in problems)


def test_removing_several_final_entries_is_detected() -> None:
    save = _advance_n(_fresh_save(), 5)
    truncated = dataclasses.replace(save, entries=save.entries[:2])
    problems = validate_history(truncated)
    assert any("entry_count" in p for p in problems)
    assert any("head_entry_hash" in p for p in problems)


def test_incorrect_entry_count_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    bad = dataclasses.replace(save, entry_count=save.entry_count + 1)
    assert any("entry_count" in p for p in validate_history(bad))


def test_incorrect_head_entry_hash_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    bad = dataclasses.replace(save, head_entry_hash="0" * 64)
    assert any("head_entry_hash" in p for p in validate_history(bad))


def test_empty_history_is_rejected() -> None:
    save = _fresh_save()
    empty = dataclasses.replace(save, entries=(), entry_count=0)
    problems = validate_history(empty)
    assert any("empty" in p for p in problems)


def test_null_decisions_or_report_on_non_genesis_entry_is_rejected() -> None:
    save = _advance_n(_fresh_save(), 1)
    stripped = dataclasses.replace(save.entries[1], decisions_json=None, report_json=None)
    bad = dataclasses.replace(save, entries=(save.entries[0], stripped))
    problems = validate_history(bad)
    assert any("no decisions" in p for p in problems)
    assert any("no report" in p for p in problems)


def test_decisions_on_genesis_is_rejected() -> None:
    save = _fresh_save()
    fake_decisions = canonical_dumps(
        DecisionSet(expected_turn=0, expected_state_version=0, decisions=[]).model_dump(mode="json")
    )
    bad_genesis = dataclasses.replace(save.entries[0], decisions_json=fake_decisions)
    bad = dataclasses.replace(save, entries=(bad_genesis,))
    problems = validate_history(bad)
    assert any("decisions=None" in p for p in problems)


def test_report_on_genesis_is_rejected() -> None:
    save = _fresh_save()
    fake_report = canonical_dumps(
        TurnReportEntry(category="x", reason_id="y").model_dump(mode="json")
    )
    # Not even a valid TurnReport shape — any non-null value at genesis is invalid.
    bad_genesis = dataclasses.replace(save.entries[0], report_json=fake_report)
    bad = dataclasses.replace(save, entries=(bad_genesis,))
    problems = validate_history(bad)
    assert any("report=None" in p for p in problems)


def test_entry_version_mismatch_with_envelope_is_detected() -> None:
    save = _fresh_save()
    bad_genesis = dataclasses.replace(save.entries[0], ruleset_version="9.9.9")
    bad = dataclasses.replace(save, entries=(bad_genesis,))
    assert any("ruleset_version" in p for p in validate_history(bad))


# --- T-R7 (Phase 3A, §9.4): tampered history re-runs reconciliation, not just the hash chain ----


def _retamper_state_with_consistent_hash(save: GameSave, *, index: int, tampered_state_json: str):  # type: ignore[no-untyped-def]
    """Replace one entry's `state_json` AND recompute `entry_hash` to match — simulating a
    knowledgeable tamperer who edits a value and does the hash arithmetic themselves, rather
    than the "forgot to update the hash" tamper every other test in this file exercises. The
    resulting chain passes every hash check; only a check that understands what the DATA means
    (not just whether it's internally consistent) can still catch it.
    """
    import json

    from app.core.canonical_json import canonical_digest
    from app.simulation.history import _entry_hash_payload

    original = save.entries[index]
    decisions_payload = json.loads(original.decisions_json) if original.decisions_json else None
    report_payload = json.loads(original.report_json) if original.report_json else None
    new_hash = canonical_digest(
        _entry_hash_payload(
            turn=original.turn,
            previous_entry_hash=original.previous_entry_hash,
            state=json.loads(tampered_state_json),
            decisions=decisions_payload,
            report=report_payload,
            ruleset_version=original.ruleset_version,
            content_version=original.content_version,
        )
    )
    tampered_entry = dataclasses.replace(
        original, state_json=tampered_state_json, entry_hash=new_hash
    )
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    new_head = entries[-1].entry_hash if index == len(save.entries) - 1 else save.head_entry_hash
    return dataclasses.replace(save, entries=entries, head_entry_hash=new_head)


def _tamper_player_politics(state, **updates):  # type: ignore[no-untyped-def]
    country_id = state.world.player_country_id
    country = state.world.countries[country_id]
    assert country.politics is not None
    tampered_politics = country.politics.model_copy(update=updates)
    state.world.countries[country_id] = country.model_copy(update={"politics": tampered_politics})
    return canonical_dumps(state.model_dump(mode="json"))


def test_consistently_rehashed_legitimacy_tamper_still_fails_reconciliation() -> None:
    """The hash chain passes (entry_hash was recomputed to match); the stored report's
    `closing_legitimacy_bps` still describes the ORIGINAL value, so reconciliation -- not the
    hash check -- is what catches this."""
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    state = save.entries[index].state()
    tampered_json = _tamper_player_politics(
        state,
        legitimacy_bps=state.world.countries[state.world.player_country_id].politics.legitimacy_bps
        + 1,
    )
    tampered = _retamper_state_with_consistent_hash(
        save, index=index, tampered_state_json=tampered_json
    )

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems), (
        "the hash was recomputed consistently and must NOT trip the hash check"
    )
    assert any("closing_legitimacy_bps" in p for p in problems)


def test_consistently_rehashed_constitutional_field_tamper_still_fails_reconciliation() -> None:
    from app.simulation.constitution import JudicialReview

    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    state = save.entries[index].state()
    current = state.world.countries[state.world.player_country_id].politics.constitution
    new_review = (
        JudicialReview.STRONG
        if current.judicial_review != JudicialReview.STRONG
        else JudicialReview.WEAK
    )
    country_id = state.world.player_country_id
    country = state.world.countries[country_id]
    tampered_constitution = country.politics.constitution.model_copy(
        update={"judicial_review": new_review}
    )
    tampered_politics = country.politics.model_copy(update={"constitution": tampered_constitution})
    state.world.countries[country_id] = country.model_copy(update={"politics": tampered_politics})
    tampered_json = canonical_dumps(state.model_dump(mode="json"))
    tampered = _retamper_state_with_consistent_hash(
        save, index=index, tampered_state_json=tampered_json
    )

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("judicial_review" in p for p in problems)


def test_consistently_rehashed_political_capital_capacity_tamper_still_fails_reconciliation() -> (
    None
):
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    state = save.entries[index].state()
    capacity = state.world.countries[
        state.world.player_country_id
    ].politics.political_capital_capacity
    tampered_json = _tamper_player_politics(state, political_capital_capacity=capacity + 1)
    tampered = _retamper_state_with_consistent_hash(
        save, index=index, tampered_state_json=tampered_json
    )

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("political_capital_capacity" in p for p in problems)


# --- T-H1 (Phase 3A, §14): traditional stale-hash tamper -- entry_hash NOT recomputed ------------
#
# The complement of the T-R7 tests above: an ordinary tamperer who edits a stored value and
# forgets to redo the hash arithmetic. Every case here must be caught by the *hash* check alone
# ("entry_hash does not match"), exactly like every pre-3A tamper test in this file
# (`test_tampering_with_only_the_economy_state_is_detected` et al.) — proving political fields are
# ordinary `entry_hash`-covered surface area, not a special case.


def test_traditional_stale_hash_tamper_of_legitimacy_bps_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    state = original.state()
    tampered_json = _tamper_player_politics(
        state,
        legitimacy_bps=state.world.countries[state.world.player_country_id].politics.legitimacy_bps
        + 1,
    )
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_traditional_stale_hash_tamper_of_political_capital_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    state = original.state()
    tampered_json = _tamper_player_politics(
        state,
        political_capital=state.world.countries[
            state.world.player_country_id
        ].politics.political_capital
        + 1,
    )
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_traditional_stale_hash_tamper_of_constitutional_order_support_bps_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    state = original.state()
    current_support = state.world.countries[
        state.world.player_country_id
    ].politics.constitutional_order_support_bps
    tampered_json = _tamper_player_politics(
        state, constitutional_order_support_bps=current_support + 1
    )
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_traditional_stale_hash_tamper_of_a_constitution_axis_is_detected() -> None:
    from app.simulation.constitution import JudicialReview

    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    state = original.state()
    country_id = state.world.player_country_id
    country = state.world.countries[country_id]
    assert country.politics is not None
    current = country.politics.constitution
    new_review = (
        JudicialReview.STRONG
        if current.judicial_review != JudicialReview.STRONG
        else JudicialReview.WEAK
    )
    tampered_constitution = current.model_copy(update={"judicial_review": new_review})
    tampered_politics = country.politics.model_copy(update={"constitution": tampered_constitution})
    state.world.countries[country_id] = country.model_copy(update={"politics": tampered_politics})
    tampered_json = canonical_dumps(state.model_dump(mode="json"))
    assert tampered_json != original.state_json
    tampered_entry = dataclasses.replace(original, state_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    tampered = dataclasses.replace(save, entries=entries)

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


def test_traditional_stale_hash_tamper_of_report_closing_legitimacy_bps_is_detected() -> None:
    save = _advance_n(_fresh_save(), 2)
    index = len(save.entries) - 1
    original = save.entries[index]
    report = original.report()
    assert report is not None
    assert report.political is not None
    tampered_political = report.political.model_copy(
        update={"closing_legitimacy_bps": report.political.closing_legitimacy_bps + 1}
    )
    tampered_report = report.model_copy(update={"political": tampered_political})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered_entry = dataclasses.replace(original, report_json=tampered_json)
    entries = (*save.entries[:index], tampered_entry)
    tampered = dataclasses.replace(save, entries=entries, entry_count=len(entries))

    problems = validate_history(tampered)
    assert any("entry_hash does not match" in p for p in problems)


# --- Phase 3B1, R8: consistently re-hashed DECISION and REPORT tampering ------------------------
#
# The complement of the state-only T-R7 tests above: a knowledgeable tamperer who edits the
# SUBMITTED DECISION (`decisions_json`) or the REPORT'S OWN provenance field (`report_json`),
# recomputes `entry_hash` to match, and produces a save whose hash chain verifies perfectly.
# Before R8, `_validate_entry_payload` parsed `decisions_json` only for its hash contribution and
# never validated it as a `DecisionSet` or handed it to reconciliation -- these tampers would have
# passed silently. Now group 16 (gating against the real decision) and group 18 (route/digest/
# influence provenance) catch them.


def _retamper_entry_with_consistent_hash(
    save: GameSave,
    *,
    index: int,
    state_json: str | None = None,
    decisions_json: str | None = None,
    report_json: str | None = None,
) -> GameSave:
    """The general form of `_retamper_state_with_consistent_hash` above (Phase 3B1, R8):
    replaces whichever of `state_json`/`decisions_json`/`report_json` is given on one entry (the
    rest keep their original stored value) and recomputes `entry_hash` to match -- simulating a
    tamperer who edits the SUBMITTED DECISION or the REPORT ITSELF, not just the resulting state,
    and does the hash arithmetic themselves. Only ever used on the LAST entry in this file's
    tests, so `head_entry_hash` is updated too and no downstream re-chaining is needed (mirroring
    `_retamper_state_with_consistent_hash`'s own restriction).
    """
    import json

    from app.core.canonical_json import canonical_digest
    from app.simulation.history import _entry_hash_payload

    original = save.entries[index]
    new_state_json = state_json if state_json is not None else original.state_json
    new_decisions_json = decisions_json if decisions_json is not None else original.decisions_json
    new_report_json = report_json if report_json is not None else original.report_json

    new_hash = canonical_digest(
        _entry_hash_payload(
            turn=original.turn,
            previous_entry_hash=original.previous_entry_hash,
            state=json.loads(new_state_json),
            decisions=(json.loads(new_decisions_json) if new_decisions_json is not None else None),
            report=json.loads(new_report_json) if new_report_json is not None else None,
            ruleset_version=original.ruleset_version,
            content_version=original.content_version,
        )
    )
    tampered_entry = dataclasses.replace(
        original,
        state_json=new_state_json,
        decisions_json=new_decisions_json,
        report_json=new_report_json,
        entry_hash=new_hash,
    )
    entries = (*save.entries[:index], tampered_entry, *save.entries[index + 1 :])
    new_head = entries[-1].entry_hash if index == len(save.entries) - 1 else save.head_entry_hash
    return dataclasses.replace(save, entries=entries, head_entry_hash=new_head)


def _quiet_decision() -> BudgetDecision:
    """A minimal, uncontested proposal: one tax-rate target, no influence -- deliberately no
    influence so a route tamper to `DECREE` still parses as a legal `BudgetDecision` (a decree
    takes no influence allocations, per `_decree_route_takes_no_influence`)."""
    return BudgetDecision(personal_income_rate_bps=2_500)


def _rich_decision() -> BudgetDecision:
    """A proposal touching every field group 16/18 must check independently: two tax-rate
    targets, two spending targets, and one influence allocation against the default legislature's
    real party/bloc ids (`tests.conftest.make_legislature`: `governing_party`/`core` holds 90 of
    100 seats, so this proposal passes regardless of the influence allocation's presence)."""
    return BudgetDecision(
        personal_income_rate_bps=2_500,
        corporate_rate_bps=3_000,
        spending_updates=(
            SpendingUpdate(category=SpendingCategory.HEALTH, amount=31_000_00),
            SpendingUpdate(category=SpendingCategory.EDUCATION, amount=23_000_00),
        ),
        influence=(
            InfluenceAllocation(party_id="governing_party", bloc_id="core", political_capital=10),
        ),
    )


def _save_with_decision(decision: BudgetDecision) -> tuple[GameSave, int]:
    """Advance two quiet (no-decision) turns, then one turn submitting `decision`. Returns the
    save and the index of the entry `decision` produced -- always the last entry."""
    save = _advance_n(_fresh_save(), 2)
    state = save.current_state()
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=[decision]
    )
    save = advance_game(save, decisions)
    return save, len(save.entries) - 1


def test_consistently_rehashed_decision_route_tamper_still_fails_reconciliation() -> None:
    """Editing a stored decision's `route` from LEGISLATIVE to DECREE (still a legal
    `BudgetDecision` shape, since `_quiet_decision` carries no influence) and recomputing the hash
    leaves the chain intact; only group 18's route comparison against the real report catches it."""
    save, index = _save_with_decision(_quiet_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    tampered_budget = decision_set.decisions[0].model_copy(update={"route": ProposalRoute.DECREE})
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    assert tampered_json != original.decisions_json
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems), (
        "the hash was recomputed consistently and must NOT trip the hash check"
    )
    assert any("does not match the submitted decision's route" in p for p in problems)


def test_consistently_rehashed_decision_tax_target_value_tamper_still_fails_reconciliation() -> (
    None
):
    """A single rate target changed to a different value the closing policy cannot possibly
    match (the closing policy reflects what was ACTUALLY submitted)."""
    save, index = _save_with_decision(_rich_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    tampered_budget = decision_set.decisions[0].model_copy(
        update={"personal_income_rate_bps": 2_600}
    )
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("finance.tax_policy.personal_income_rate_bps" in p for p in problems)


def test_consistently_rehashed_decision_spending_target_value_tamper_still_fails_reconciliation() -> (
    None
):
    save, index = _save_with_decision(_rich_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    original_budget = decision_set.decisions[0]
    tampered_updates = tuple(
        update.model_copy(update={"amount": 32_000_00})
        if update.category is SpendingCategory.HEALTH
        else update
        for update in original_budget.spending_updates
    )
    tampered_budget = original_budget.model_copy(update={"spending_updates": tampered_updates})
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("finance.spending_plan.health" in p for p in problems)


def test_consistently_rehashed_tax_category_swap_preserving_aggregate_still_fails_reconciliation() -> (
    None
):
    """Swapping the personal-income and corporate targets leaves their SUM unchanged (5,500 bps
    either way) -- an aggregate-only check would see nothing wrong. Group 16 compares each tax
    field independently, so the swap is caught anyway."""
    save, index = _save_with_decision(_rich_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    original_budget = decision_set.decisions[0]
    assert original_budget.personal_income_rate_bps == 2_500
    assert original_budget.corporate_rate_bps == 3_000
    tampered_budget = original_budget.model_copy(
        update={"personal_income_rate_bps": 3_000, "corporate_rate_bps": 2_500}
    )
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("finance.tax_policy.personal_income_rate_bps" in p for p in problems)
    assert any("finance.tax_policy.corporate_rate_bps" in p for p in problems)


def test_consistently_rehashed_spending_category_swap_preserving_total_still_fails_reconciliation() -> (
    None
):
    """Swapping the health and education amounts leaves their SUM unchanged (54,000.00 either
    way) -- an aggregate-only check would see nothing wrong. Group 16 compares each spending
    category independently, so the swap is caught anyway."""
    save, index = _save_with_decision(_rich_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    original_budget = decision_set.decisions[0]
    amounts = {update.category: update.amount for update in original_budget.spending_updates}
    assert amounts[SpendingCategory.HEALTH] == 31_000_00
    assert amounts[SpendingCategory.EDUCATION] == 23_000_00
    swapped = {
        SpendingCategory.HEALTH: 23_000_00,
        SpendingCategory.EDUCATION: 31_000_00,
    }
    tampered_updates = tuple(
        update.model_copy(update={"amount": swapped[update.category]})
        for update in original_budget.spending_updates
    )
    tampered_budget = original_budget.model_copy(update={"spending_updates": tampered_updates})
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("finance.spending_plan.health" in p for p in problems)
    assert any("finance.spending_plan.education" in p for p in problems)


def test_consistently_rehashed_influence_allocation_tamper_still_fails_reconciliation() -> None:
    """The allocated amount is edited upward; the report's stored `political_capital_allocated`
    row (fixed at resolution time) cannot possibly agree, so group 18's bidirectional allocation
    check catches it -- independent of whether the vote would still have passed."""
    save, index = _save_with_decision(_rich_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None and decision_set.decisions
    original_budget = decision_set.decisions[0]
    assert len(original_budget.influence) == 1
    assert original_budget.influence[0].political_capital == 10
    tampered_budget = original_budget.model_copy(
        update={
            "influence": (
                original_budget.influence[0].model_copy(update={"political_capital": 20}),
            )
        }
    )
    tampered_set = decision_set.model_copy(update={"decisions": (tampered_budget,)})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("does not show that allocation" in p for p in problems)


def test_consistently_rehashed_expected_turn_tamper_still_fails_reconciliation() -> None:
    save, index = _save_with_decision(_quiet_decision())
    original = save.entries[index]
    decision_set = original.decisions()
    assert decision_set is not None
    tampered_set = decision_set.model_copy(update={"expected_turn": decision_set.expected_turn + 1})
    tampered_json = canonical_dumps(tampered_set.model_dump(mode="json"))
    assert tampered_json != original.decisions_json
    tampered = _retamper_entry_with_consistent_hash(save, index=index, decisions_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("decisions.expected_turn" in p for p in problems)


def test_consistently_rehashed_report_decision_digest_tamper_still_fails_reconciliation() -> None:
    """The REPORT's own `budget_decision_digest` is edited (the decision itself is untouched) --
    still a syntactically valid 64-character hex digest, so `LegislativeReport`'s syntax-only
    validator does not reject it on replay; only group 18 recomputing the real digest from the
    real submitted decision catches the mismatch."""
    save, index = _save_with_decision(_quiet_decision())
    original = save.entries[index]
    report = original.report()
    assert report is not None and report.legislative is not None
    real_digest = report.legislative.budget_decision_digest
    assert real_digest is not None
    fake_digest = ("0" if real_digest[0] != "0" else "1") + real_digest[1:]
    tampered_legislative = report.legislative.model_copy(
        update={"budget_decision_digest": fake_digest}
    )
    tampered_report = report.model_copy(update={"legislative": tampered_legislative})
    tampered_json = canonical_dumps(tampered_report.model_dump(mode="json"))
    assert tampered_json != original.report_json
    tampered = _retamper_entry_with_consistent_hash(save, index=index, report_json=tampered_json)

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert any("budget_decision_digest" in p for p in problems)


def test_malformed_decisions_json_with_consistent_hash_is_a_schema_problem_not_a_crash() -> None:
    """(Phase 3B1, R8) Canonically-formatted, JSON-valid text carrying an invalid `DecisionSet`
    *shape* -- `expected_turn` holding a string -- clears the JSON-decode check AND the
    canonical-form check (both pre-existing) and must be caught by the genuinely new semantic
    parse (`DecisionSet.model_validate`) instead. Garbage bytes or non-canonical spacing would be
    caught by one of the two pre-existing checks and would prove nothing about this one; this
    payload is deliberately well-formed everywhere except the one place the new check exists to
    catch, and must not crash `validate_history`."""
    save, index = _save_with_decision(_quiet_decision())
    malformed_json = canonical_dumps(
        {"decisions": [], "expected_state_version": 0, "expected_turn": "not-an-int"}
    )
    tampered = _retamper_entry_with_consistent_hash(
        save, index=index, decisions_json=malformed_json
    )

    problems = validate_history(tampered)
    assert not any("entry_hash does not match" in p for p in problems)
    assert not any("not valid JSON" in p for p in problems)
    assert not any("not canonical JSON" in p for p in problems)
    assert any("stored decisions fail schema validation" in p for p in problems)
