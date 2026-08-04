"""Tests for the immutable, hash-chained history layer (`simulation.history`)."""

from __future__ import annotations

import dataclasses

import pytest

from app.core.canonical_json import canonical_dumps
from app.core.errors import HistoryValidationError, SnapshotNotFoundError, TurnResolutionError
from app.simulation.decisions import BudgetDecision, DecisionSet
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.report import TurnReportEntry
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json
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
