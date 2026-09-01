"""Immutable, hash-chained game history — built above the pure resolver.

`simulation.resolver.resolve_turn` stays exactly what it was: a pure function
of `(GameState, DecisionSet) -> (GameState, TurnReport)` with no notion of
"the game so far." This module adds that notion on top, without touching the
resolver, because the two concerns are genuinely separate: turn resolution is
about correctly computing *one* transition; history is about durably,
verifiably remembering the sequence of transitions that produced the current
state. Keeping them apart means the resolver's own test suite (determinism,
invariant-preservation, stale-decision rejection) needed no changes at all —
this module is purely additive.

## Representation and immutability

A `HistoryEntry` does not hold a live `GameState`/`DecisionSet`/`TurnReport`
instance. It holds **canonical JSON text** for each (`state_json`,
`decisions_json`, `report_json`) plus a handful of `str`/`int`/`None` fields.
There is no nested mutable object anywhere in a `HistoryEntry` or `GameSave`
for a caller to reach and mutate — the immutability guarantee is structural,
not just a `frozen=True` flag on an outer wrapper. `HistoryEntry.state()` /
`.decisions()` / `.report()` parse a **fresh** Pydantic model from that text
on every call; two calls return two independent objects, and mutating either
cannot touch what's stored. `GameSave.current_state()` is derived the same
way from the final entry rather than cached as a second mutable copy, which
also means "current state matches the final entry" holds by construction
instead of needing a separate check.

## What the hash chain protects — and what it does not

Every entry's `entry_hash` is a BLAKE2b-256 digest over the canonical JSON of
`{turn, previous_entry_hash, decisions, report, state, ruleset_version,
content_version}` — the complete record of how that turn was reached, not
just its resulting state. Changing any of those seven fields on any entry
changes that entry's hash, which breaks the `previous_entry_hash` link on
every entry after it. `GameSave.entry_count` / `head_entry_hash` additionally
guard against **truncating the tail**: deleting the last N entries would
otherwise leave a shorter chain that still validates internally, since the
current state and turn are derived from whatever the last remaining entry
happens to be.

This is deterministic **integrity and corruption detection**, not anti-cheat
security. The hashes are unkeyed — anyone who can edit a save file can
recompute the entire chain (including `entry_count`/`head_entry_hash`) by
running the same public algorithm. What it reliably catches is accidental
corruption and unsophisticated hand-editing (changing a number in a JSON
file without also fixing every downstream hash), not a knowledgeable
adversary willing to do the arithmetic.

`validate_history` never silently repairs or normalizes a malformed stored
payload — a non-canonical stored JSON string is itself reported as a
problem, not quietly re-canonicalized and accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.canonical_json import canonical_digest, canonical_dumps
from app.core.errors import HistoryValidationError, SnapshotNotFoundError
from app.simulation.decisions import DecisionSet
from app.simulation.invariants import check_invariants
from app.simulation.reconciliation import (
    reconcile_foreign_affairs_report,
    reconcile_political_legislative_and_survival_report,
    reconcile_strategic_map_staticness,
)
from app.simulation.report import TurnReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState


def _entry_hash_payload(
    *,
    turn: int,
    previous_entry_hash: str | None,
    state: Any,
    decisions: Any,
    report: Any,
    ruleset_version: str,
    content_version: str,
) -> dict[str, Any]:
    """The exact object hashed for one entry. `state`/`decisions`/`report` are
    already-parsed JSON values (dict/list/scalar/None), not JSON text."""
    return {
        "turn": turn,
        "previous_entry_hash": previous_entry_hash,
        "decisions": decisions,
        "report": report,
        "state": state,
        "ruleset_version": ruleset_version,
        "content_version": content_version,
    }


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One immutable, hash-verified record: a state and how it was reached.

    `previous_entry_hash`, `decisions_json`, and `report_json` are `None`
    only for the genesis entry (`turn == 0`); every later entry has all
    three populated. `state_json`/`decisions_json`/`report_json` are always
    canonical JSON text (see module docstring, "Representation").
    """

    turn: int
    previous_entry_hash: str | None
    state_json: str
    decisions_json: str | None
    report_json: str | None
    ruleset_version: str
    content_version: str
    entry_hash: str

    def state(self) -> GameState:
        """Parse a fresh `GameState` from this entry. Independent on every call."""
        return GameState.model_validate_json(self.state_json)

    def decisions(self) -> DecisionSet | None:
        """Parse a fresh `DecisionSet`, or `None` at genesis."""
        if self.decisions_json is None:
            return None
        return DecisionSet.model_validate_json(self.decisions_json)

    def report(self) -> TurnReport | None:
        """Parse a fresh `TurnReport`, or `None` at genesis."""
        if self.report_json is None:
            return None
        return TurnReport.model_validate_json(self.report_json)


def _make_entry(
    *,
    turn: int,
    previous_entry_hash: str | None,
    state: GameState,
    decisions: DecisionSet | None,
    report: TurnReport | None,
    ruleset_version: str,
    content_version: str,
) -> HistoryEntry:
    state_json = canonical_dumps(state.model_dump(mode="json"))
    decisions_json = (
        canonical_dumps(decisions.model_dump(mode="json")) if decisions is not None else None
    )
    report_json = canonical_dumps(report.model_dump(mode="json")) if report is not None else None

    payload = _entry_hash_payload(
        turn=turn,
        previous_entry_hash=previous_entry_hash,
        state=json.loads(state_json),
        decisions=json.loads(decisions_json) if decisions_json is not None else None,
        report=json.loads(report_json) if report_json is not None else None,
        ruleset_version=ruleset_version,
        content_version=content_version,
    )
    entry_hash = canonical_digest(payload)

    return HistoryEntry(
        turn=turn,
        previous_entry_hash=previous_entry_hash,
        state_json=state_json,
        decisions_json=decisions_json,
        report_json=report_json,
        ruleset_version=ruleset_version,
        content_version=content_version,
        entry_hash=entry_hash,
    )


@dataclass(frozen=True, slots=True)
class GameSave:
    """A complete, immutable game: its version envelope plus its full history.

    `entry_count` and `head_entry_hash` are redundant with `len(entries)` and
    `entries[-1].entry_hash` when the save is valid — they exist so that
    `validate_history` can detect a truncated tail, which a chain-link check
    alone cannot: deleting the last N entries yields a shorter chain that is
    still internally consistent unless something outside the truncated
    entries themselves records how long the chain used to be.
    """

    save_format_version: int
    ruleset_version: str
    content_version: str
    entry_count: int
    head_entry_hash: str
    entries: tuple[HistoryEntry, ...]

    def current_state(self) -> GameState:
        """The state after the most recent entry. Derived, not stored twice."""
        return self.entries[-1].state()

    def current_turn(self) -> int:
        return self.entries[-1].turn

    def entry_at(self, turn: int) -> HistoryEntry:
        """Look up a single historical entry by turn number, without mutating history."""
        for entry in self.entries:
            if entry.turn == turn:
                return entry
        raise SnapshotNotFoundError(turn, [e.turn for e in self.entries])


def new_game(state: GameState, *, save_format_version: int) -> GameSave:
    """Start a new `GameSave` from a freshly-loaded initial `GameState`.

    `state` must be at turn 0 / state_version 0 (i.e. straight out of
    `content.scenarios.load_scenario_file`, never a state that has already
    had turns resolved against it).
    """
    if state.turn != 0 or state.state_version != 0:
        raise ValueError(
            f"new_game requires a fresh state (turn=0, state_version=0); "
            f"got turn={state.turn}, state_version={state.state_version}"
        )

    genesis = _make_entry(
        turn=0,
        previous_entry_hash=None,
        state=state,
        decisions=None,
        report=None,
        ruleset_version=state.ruleset_version,
        content_version=state.content_version,
    )
    return GameSave(
        save_format_version=save_format_version,
        ruleset_version=state.ruleset_version,
        content_version=state.content_version,
        entry_count=1,
        head_entry_hash=genesis.entry_hash,
        entries=(genesis,),
    )


def advance_game(save: GameSave, decisions: DecisionSet) -> GameSave:
    """Resolve one turn and return a *new* `GameSave` with one more entry.

    Order of operations (product spec, "atomic history updates"):

    1. Validate `save`'s history — a corrupt save is never advanced further.
    2/3/4. Validate the decision set against the current state, resolve the
       turn, and validate the resulting state. All three are delegated to
       the existing, separately-tested `resolve_turn`: `save.current_state()`
       has exactly the turn/state_version `resolve_turn` needs to check the
       decision set against, so re-implementing that check here would only
       risk drifting from the resolver's own guarantee.
    5/6. Build the next `HistoryEntry` and return a new `GameSave` with it
       appended.

    On any failure, a specific exception propagates and nothing is returned:
    `save` (frozen, immutable) cannot have been mutated regardless, and no
    new `GameSave` is constructed, so there is nothing partial to discard.
    """
    problems = validate_history(save)
    if problems:
        raise HistoryValidationError(problems)

    current_state = save.current_state()
    resolution = resolve_turn(current_state, decisions)

    new_entry = _make_entry(
        turn=resolution.state.turn,
        previous_entry_hash=save.head_entry_hash,
        state=resolution.state,
        decisions=decisions,
        report=resolution.report,
        ruleset_version=save.ruleset_version,
        content_version=save.content_version,
    )
    return GameSave(
        save_format_version=save.save_format_version,
        ruleset_version=save.ruleset_version,
        content_version=save.content_version,
        entry_count=save.entry_count + 1,
        head_entry_hash=new_entry.entry_hash,
        entries=(*save.entries, new_entry),
    )


def validate_history(save: GameSave) -> list[str]:
    """Return every history integrity problem found in `save`. Empty means valid.

    Never raises; `advance_game` and CLI callers decide what to do with a
    non-empty result (typically raising `HistoryValidationError`). Checks,
    per entry and across the whole chain:

    - at least one entry exists, and the first is turn 0 (genesis)
    - genesis has no previous hash / decisions / report; every later entry has all three
    - turns are consecutive starting at 0, with no duplicates or gaps
    - each non-genesis entry's `previous_entry_hash` matches the preceding entry's `entry_hash`
    - every entry's ruleset/content version matches the save envelope
    - every stored JSON payload is itself already canonical (never silently renormalized)
    - every entry's `entry_hash` recomputes correctly from its (possibly-tampered) contents
    - every entry's state independently satisfies `simulation.invariants.check_invariants`
    - `entry_count` matches the actual number of entries (tail-truncation guard)
    - `head_entry_hash` matches the final entry's hash (tail-truncation / tail-replacement guard)
    """
    problems: list[str] = []

    if not save.entries:
        problems.append("history is empty; a save must contain at least the genesis entry")
        return problems

    genesis = save.entries[0]
    if genesis.turn != 0:
        problems.append(f"first entry has turn={genesis.turn}, expected 0 (genesis)")
    if genesis.previous_entry_hash is not None:
        problems.append("genesis entry (turn 0) must have previous_entry_hash=None")
    if genesis.decisions_json is not None:
        problems.append("genesis entry (turn 0) must have decisions=None")
    if genesis.report_json is not None:
        problems.append("genesis entry (turn 0) must have report=None")

    previous_state_model: GameState | None = None
    concluded_at: int | None = None
    """(Phase 3C) The turn a `terminal_outcome` was first observed, or `None`. A genuine save
    could never contain an entry after this turn — `resolve_turn`'s own top-of-function refusal
    (`GameAlreadyConcludedError`) prevents advancing a concluded save through the CLI, but a
    hand-assembled save could still smuggle extra entries in from the start; this is the
    independent guard that catches that case."""
    for index, entry in enumerate(save.entries):
        if entry.turn != index:
            problems.append(
                f"entry at position {index} has turn={entry.turn}; turns must be consecutive "
                "starting at 0 with no duplicates or gaps"
            )

        if index > 0:
            if entry.previous_entry_hash is None:
                problems.append(f"turn {entry.turn}: non-genesis entry has no previous_entry_hash")
            if entry.decisions_json is None:
                problems.append(f"turn {entry.turn}: non-genesis entry has no decisions")
            if entry.report_json is None:
                problems.append(f"turn {entry.turn}: non-genesis entry has no report")

            previous = save.entries[index - 1]
            if entry.previous_entry_hash != previous.entry_hash:
                problems.append(
                    f"turn {entry.turn}: previous_entry_hash does not match the preceding "
                    "entry's hash (broken chain link — entries may be reordered, removed, or "
                    "the preceding entry was modified)"
                )

        if entry.ruleset_version != save.ruleset_version:
            problems.append(
                f"turn {entry.turn}: ruleset_version {entry.ruleset_version!r} does not match "
                f"the save envelope's {save.ruleset_version!r}"
            )
        if entry.content_version != save.content_version:
            problems.append(
                f"turn {entry.turn}: content_version {entry.content_version!r} does not match "
                f"the save envelope's {save.content_version!r}"
            )

        entry_problems, state_model, decisions_model, report_model = _validate_entry_payload(entry)
        problems.extend(entry_problems)

        # (Phase 3A, §9.4; Phase 3B1, R8) Entry N-1's parsed state IS entry N's opening state --
        # the history chain supplies both sides of the reconciler with no extra information and
        # no additional state parse (the per-entry GameState parse above is not new work; only
        # the DecisionSet/TurnReport parses in _validate_entry_payload are genuinely new).
        # `decisions_model` may legitimately be `None` here (a malformed `decisions_json` already
        # recorded its own problem above) -- the reconciler skips only the two groups that need a
        # real decision and still runs every other group against `None`.
        if (
            index > 0
            and previous_state_model is not None
            and state_model is not None
            and report_model is not None
        ):
            problems.extend(
                f"turn {entry.turn}: {problem}"
                for problem in reconcile_political_legislative_and_survival_report(
                    opening_state=previous_state_model,
                    closing_state=state_model,
                    report=report_model,
                    decisions=decisions_model,
                )
            )
            # External Wars Gate W1, commit 7 (frozen plan sec.12, groups 46-52): a separate
            # entrypoint, not an extension of the political/legislative/survival reconciler
            # above -- same opening/closing state and report, independent ownership.
            problems.extend(
                f"turn {entry.turn}: {problem}"
                for problem in reconcile_foreign_affairs_report(
                    opening_state=previous_state_model,
                    closing_state=state_model,
                    report=report_model,
                )
            )
        # Strategic Military Map Gate M0, commit 5 (group 53): a third, independent entrypoint,
        # deliberately in its OWN guard rather than nested in the block above -- it takes no
        # `report` argument (staticness is a pure state-to-state property), so it must not be
        # suppressed on a turn whose report_json happens to be malformed. A tampered map paired
        # with a tampered report should still be caught here even though the report-dependent
        # reconcilers above cannot run on that turn.
        if index > 0 and previous_state_model is not None and state_model is not None:
            problems.extend(
                f"turn {entry.turn}: {problem}"
                for problem in reconcile_strategic_map_staticness(
                    opening_state=previous_state_model,
                    closing_state=state_model,
                )
            )
        if concluded_at is not None:
            problems.append(
                f"turn {entry.turn}: entry exists after the game concluded at turn "
                f"{concluded_at}; a concluded game cannot be advanced further, and a genuine "
                "save could never contain entries after that turn"
            )
        if state_model is not None:
            player = state_model.world.countries.get(state_model.world.player_country_id)
            if (
                player is not None
                and player.politics is not None
                and player.politics.terminal_outcome is not None
                and concluded_at is None
            ):
                concluded_at = entry.turn

        previous_state_model = state_model

    if save.entry_count != len(save.entries):
        problems.append(
            f"entry_count={save.entry_count} does not match the actual number of stored "
            f"entries ({len(save.entries)}); the history may have been truncated"
        )

    if save.head_entry_hash != save.entries[-1].entry_hash:
        problems.append(
            "head_entry_hash does not match the final entry's hash; the history may have been "
            "truncated or its final entry replaced"
        )

    return problems


def _validate_entry_payload(
    entry: HistoryEntry,
) -> tuple[list[str], GameState | None, DecisionSet | None, TurnReport | None]:
    """Canonical-payload, hash-recompute, state-invariant, and report-schema checks for one entry.

    Returns `(problems, state_model, decisions_model, report_model)` — the parsed models (or
    `None` if parsing failed, or if genuinely absent at genesis) are handed back so
    `validate_history`'s loop can thread the state forward to the NEXT entry's reconciliation
    check, and this entry's own decisions into its OWN reconciliation check, without a second
    parse of the same JSON (§9.4; Phase 3B1, R8).

    `decisions_model` is parsed via `DecisionSet.model_validate` -- not merely checked for
    canonical JSON form -- so a `decisions_json` that is well-formed, canonical JSON but not a
    valid `DecisionSet` *shape* (e.g. `expected_turn` holding a string) is caught here, by the
    same semantic parse `resolve_turn` itself performs, rather than only by the weaker canonical-
    form check above it. A malformed `decisions_json` is an actionable problem, never a crash.
    """
    problems: list[str] = []

    try:
        parsed_state = json.loads(entry.state_json)
    except json.JSONDecodeError as exc:
        return [f"turn {entry.turn}: state payload is not valid JSON: {exc}"], None, None, None
    if canonical_dumps(parsed_state) != entry.state_json:
        problems.append(f"turn {entry.turn}: stored state payload is not canonical JSON")

    parsed_decisions: Any = None
    if entry.decisions_json is not None:
        try:
            parsed_decisions = json.loads(entry.decisions_json)
        except json.JSONDecodeError as exc:
            problems.append(f"turn {entry.turn}: decisions payload is not valid JSON: {exc}")
            return problems, None, None, None
        if canonical_dumps(parsed_decisions) != entry.decisions_json:
            problems.append(f"turn {entry.turn}: stored decisions payload is not canonical JSON")

    parsed_report: Any = None
    if entry.report_json is not None:
        try:
            parsed_report = json.loads(entry.report_json)
        except json.JSONDecodeError as exc:
            problems.append(f"turn {entry.turn}: report payload is not valid JSON: {exc}")
            return problems, None, None, None
        if canonical_dumps(parsed_report) != entry.report_json:
            problems.append(f"turn {entry.turn}: stored report payload is not canonical JSON")

    payload = _entry_hash_payload(
        turn=entry.turn,
        previous_entry_hash=entry.previous_entry_hash,
        state=parsed_state,
        decisions=parsed_decisions,
        report=parsed_report,
        ruleset_version=entry.ruleset_version,
        content_version=entry.content_version,
    )
    if canonical_digest(payload) != entry.entry_hash:
        problems.append(
            f"turn {entry.turn}: stored entry_hash does not match the recomputed hash "
            "(state, decisions, report, turn, versions, or previous_entry_hash was modified)"
        )

    state_model: GameState | None = None
    try:
        state_model = GameState.model_validate(parsed_state)
    except ValidationError as exc:
        problems.append(f"turn {entry.turn}: stored state fails schema validation: {exc}")
    else:
        for violation in check_invariants(state_model):
            problems.append(f"turn {entry.turn}: {violation.code}: {violation.message}")

    decisions_model: DecisionSet | None = None
    if entry.decisions_json is not None:
        # (Phase 3B1, R8) The genuinely new parse: `HistoryEntry.decisions()` already existed but
        # was unused on this path -- `decisions_json` was hash-covered and canonical-form-checked
        # above, but never actually validated AS a `DecisionSet`, so a consistently-rehashed
        # tamper to its shape passed every prior check silently.
        try:
            decisions_model = DecisionSet.model_validate(parsed_decisions)
        except ValidationError as exc:
            problems.append(f"turn {entry.turn}: stored decisions fail schema validation: {exc}")

    report_model: TurnReport | None = None
    if entry.report_json is not None:
        # (Phase 3A, §9.4) Parsing via model_validate re-runs EVERY report self-validator
        # (PoliticalReport's ten, LegislativeReport's thirteen, TurnReport's own cross-validators,
        # every prior phase's report validators too) -- so a report tampered and then re-hashed
        # consistently is still caught here, even though the hash chain itself would pass.
        try:
            report_model = TurnReport.model_validate(parsed_report)
        except ValidationError as exc:
            problems.append(f"turn {entry.turn}: stored report fails schema validation: {exc}")

    return problems, state_model, decisions_model, report_model
