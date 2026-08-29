"""Shared support for "knowledgeable tamperer" history tests.

A naive tamper edits a payload and forgets the hash, so the chain check catches it and nothing
deeper is ever exercised. The helpers here instead simulate a tamperer who does the hash
arithmetic themselves: they edit one entry's state or report and then **re-link and re-hash the
entire downstream chain**, so `validate_history` finds no hash problem at all. Whatever it does
still report is therefore attributable to semantic reconciliation, not to hashing.

Not a `conftest.py` resident on purpose: these are ordinary functions, not pytest fixtures, and
importing plain callables out of a conftest module is not a pattern this repository uses.

Why the whole chain and not just the edited entry: every later entry's `previous_entry_hash`
points at the edited entry's OLD hash, and each entry's own hash covers its
`previous_entry_hash` -- so a single-entry rehash silently breaks the link for every entry after
it. That is invisible while only the LAST entry is ever tampered (the case the original
`test_history.py` helper was written for) and wrong the moment an earlier entry is targeted.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from app.core.canonical_json import canonical_digest
from app.simulation.decisions import DecisionSet
from app.simulation.history import HistoryEntry, _entry_hash_payload, advance_game
from app.simulation.save_format import GameSave


def advance_n(save: GameSave, n: int) -> GameSave:
    """Resolve `n` further turns with empty decisions."""
    for _ in range(n):
        state = save.current_state()
        save = advance_game(
            save,
            DecisionSet(
                expected_turn=state.turn, expected_state_version=state.state_version, decisions=[]
            ),
        )
    return save


def _payload_of(entry: HistoryEntry, *, previous_entry_hash: str | None) -> dict[str, Any]:
    """The exact object production hashes for `entry`, via the production builder."""
    return _entry_hash_payload(
        turn=entry.turn,
        previous_entry_hash=previous_entry_hash,
        state=json.loads(entry.state_json),
        decisions=json.loads(entry.decisions_json) if entry.decisions_json else None,
        report=json.loads(entry.report_json) if entry.report_json else None,
        ruleset_version=entry.ruleset_version,
        content_version=entry.content_version,
    )


def _relink_and_rehash(
    entries: tuple[HistoryEntry, ...], *, first_dirty: int
) -> tuple[HistoryEntry, ...]:
    """Re-link and re-hash every entry from `first_dirty` onward, left to right.

    Each entry's `previous_entry_hash` is set to the freshly recomputed hash of the entry before
    it, then its own `entry_hash` is recomputed over that. Genesis (index 0) keeps
    `previous_entry_hash=None`, exactly as production requires.
    """
    rebuilt = list(entries[:first_dirty])
    for index in range(first_dirty, len(entries)):
        entry = entries[index]
        previous_hash = None if index == 0 else rebuilt[index - 1].entry_hash
        new_hash = canonical_digest(_payload_of(entry, previous_entry_hash=previous_hash))
        rebuilt.append(
            dataclasses.replace(entry, previous_entry_hash=previous_hash, entry_hash=new_hash)
        )
    return tuple(rebuilt)


def _rebuild(save: GameSave, entries: tuple[HistoryEntry, ...], *, first_dirty: int) -> GameSave:
    relinked = _relink_and_rehash(entries, first_dirty=first_dirty)
    return dataclasses.replace(save, entries=relinked, head_entry_hash=relinked[-1].entry_hash)


def retamper_state_with_consistent_hash(
    save: GameSave, *, index: int, tampered_state_json: str
) -> GameSave:
    """Replace entry `index`'s `state_json`, then re-link and re-hash the whole downstream chain."""
    entries = (
        *save.entries[:index],
        dataclasses.replace(save.entries[index], state_json=tampered_state_json),
        *save.entries[index + 1 :],
    )
    return _rebuild(save, entries, first_dirty=index)


def retamper_report_with_consistent_hash(
    save: GameSave, *, index: int, tampered_report_json: str
) -> GameSave:
    """Replace entry `index`'s `report_json`, then re-link and re-hash the whole downstream chain.

    The symmetric counterpart of `retamper_state_with_consistent_hash`: most External Wars W1
    tamper cases forge the stored REPORT while leaving real state alone, which is precisely the
    shape reconciliation exists to catch.
    """
    entries = (
        *save.entries[:index],
        dataclasses.replace(save.entries[index], report_json=tampered_report_json),
        *save.entries[index + 1 :],
    )
    return _rebuild(save, entries, first_dirty=index)


def hash_chain_problems(save: GameSave) -> list[str]:
    """Every HASH-ONLY problem in `save`, recomputed independently of `validate_history`.

    Deliberately narrow: it knows nothing about what any value MEANS, so an empty result is
    positive proof that the chain itself is intact and that anything `validate_history` reports
    is semantic. Checks, using the production `_entry_hash_payload` + `canonical_digest`:

    - genesis carries no `previous_entry_hash`, and no later entry omits one
    - every entry's `previous_entry_hash` equals the preceding entry's `entry_hash`
    - every entry's `entry_hash` equals the digest of its own canonical payload
    - `head_entry_hash` equals the final entry's `entry_hash`
    """
    problems: list[str] = []
    for index, entry in enumerate(save.entries):
        if index == 0:
            if entry.previous_entry_hash is not None:
                problems.append(f"entry {index}: genesis carries a previous_entry_hash")
        else:
            expected_previous = save.entries[index - 1].entry_hash
            if entry.previous_entry_hash is None:
                problems.append(f"entry {index}: previous_entry_hash is missing")
            elif entry.previous_entry_hash != expected_previous:
                problems.append(
                    f"entry {index}: previous_entry_hash {entry.previous_entry_hash} does not "
                    f"link to the preceding entry_hash {expected_previous}"
                )
        expected_hash = canonical_digest(
            _payload_of(entry, previous_entry_hash=entry.previous_entry_hash)
        )
        if entry.entry_hash != expected_hash:
            problems.append(
                f"entry {index}: entry_hash {entry.entry_hash} does not match the digest of its "
                f"canonical payload ({expected_hash})"
            )
    if save.entries and save.head_entry_hash != save.entries[-1].entry_hash:
        problems.append("head_entry_hash does not match the final entry's entry_hash")
    return problems
