"""Headless entry point: create games, resolve turns, and inspect history —
all without a server or database.

    mandate new --scenario data/scenarios/tiny_valid.yaml --out save.json
    mandate inspect --state save.json
    mandate resolve --state save.json --turns 8 --out save.turn8.json
    mandate history --state save.turn8.json
    mandate history --state save.turn8.json --turn 3

`new` creates a save containing only the genesis (turn-0) entry. `inspect`
loads a save, reports its version envelope and integrity status, and writes
nothing — even an invalid save can be inspected (that is the point of
"integrity status"), reported via a nonzero exit rather than a stack trace.
`resolve` appends N turns via `simulation.history.advance_game` and writes
the result atomically; on any failure nothing is written and the input file
is untouched. `history` lists every turn or, with `--turn N`, prints one
historical entry — without mutating anything. It refuses to operate on an
invalid save (unlike `inspect`, whose job is to report exactly that).

Save files are the real, versioned, hash-chained format from
`simulation.save_format` — not the flat `{state_file_schema_version, state}`
format Phase 0 wrote. That format is not read by this build at all; see
`docs/adr/0002-snapshot-history-and-versioning.md` for why it isn't migrated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.content.scenarios import load_scenario_file
from app.core.errors import HistoryValidationError, MandateError
from app.saves import read_save_file, write_save_atomic
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.report import TurnReport
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json, load_save_json


def _write_save(path: Path, save: GameSave) -> None:
    write_save_atomic(path, dump_save_json(save).encode("utf-8"))


def _read_save(path: Path) -> GameSave:
    return load_save_json(read_save_file(path), source=str(path))


def _cmd_new(args: argparse.Namespace) -> int:
    state = load_scenario_file(args.scenario)
    if args.seed is not None:
        state = state.model_copy(update={"seed": args.seed})

    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    out_path = Path(args.out)
    _write_save(out_path, save)
    print(
        f"created game from scenario {args.scenario!r}: seed={state.seed} turn=0 "
        f"-> wrote {out_path}"
    )
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.state)
    save = _read_save(path)
    current = save.current_state()
    player = current.world.countries[current.world.player_country_id]
    problems = validate_history(save)

    print(f"save file: {path}")
    print(f"  save_format_version: {save.save_format_version}")
    print(f"  ruleset_version:     {save.ruleset_version}")
    print(f"  content_version:     {save.content_version}")
    print(f"  current_turn:        {save.current_turn()}")
    print(f"  entries:             {len(save.entries)} (entry_count={save.entry_count})")
    print(f"  player_country:      {player.id} ({player.name}), population={player.population}")

    if problems:
        print(f"  integrity:           INVALID ({len(problems)} problem(s))")
        for problem in problems:
            print(f"    - {problem}")
        return 1

    print("  integrity:           OK")
    return 0


def _print_report(report: TurnReport) -> None:
    print(f"  turn {report.resolved_turn} resolved:")
    for entry in report.entries:
        print(f"    [{entry.category}] {entry.summary}")
    not_implemented = [
        phase_id
        for phase_id, status in report.dev.phase_statuses.items()
        if status.value == "not_implemented"
    ]
    if not_implemented:
        print(f"    (dev) not yet implemented: {', '.join(not_implemented)}")


def _cmd_resolve(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    out_path = Path(args.out)
    if out_path.resolve() == state_path.resolve():
        print("error: --out must not be the same file as --state (inputs are never overwritten)")
        return 2

    save = _read_save(state_path)
    print(f"resolving {args.turns} turn(s) from turn {save.current_turn()}")

    for _ in range(args.turns):
        current = save.current_state()
        decisions = DecisionSet(
            expected_turn=current.turn,
            expected_state_version=current.state_version,
            decisions=[],
        )
        # advance_game validates history + the decision set + the resolved
        # state, in that order, and raises before appending anything on any
        # failure — so a mid-batch failure here leaves `save` (this local
        # variable) pointing at the last good save and never reaches the
        # write below, matching "no partial output file."
        save = advance_game(save, decisions)
        report = save.entries[-1].report()
        assert report is not None, "a just-appended, non-genesis entry always has a report"
        _print_report(report)

    _write_save(out_path, save)
    final = save.current_state()
    print(
        f"final: turn={final.turn} state_version={final.state_version} "
        f"entries={len(save.entries)} -> wrote {out_path}"
    )
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    path = Path(args.state)
    save = _read_save(path)

    problems = validate_history(save)
    if problems:
        raise HistoryValidationError(problems)

    if args.turn is None:
        print(f"save file: {path}")
        print(f"  {len(save.entries)} entries (turns 0-{save.current_turn()})")
        for entry in save.entries:
            label = "genesis" if entry.turn == 0 else "turn   "
            print(f"    {label} {entry.turn}: entry_hash={entry.entry_hash[:16]}...")
        return 0

    # SnapshotNotFoundError is a MandateError; letting it propagate to
    # main()'s generic handler gives the same "error: ..." + exit 1 behavior
    # as every other domain error, for an invalid/unavailable turn number.
    entry = save.entry_at(args.turn)
    entry_state = entry.state()
    player = entry_state.world.countries[entry_state.world.player_country_id]

    print(f"turn {entry.turn}:")
    print(f"  entry_hash:          {entry.entry_hash}")
    print(f"  previous_entry_hash: {entry.previous_entry_hash}")
    print(f"  state_version:       {entry_state.state_version}")
    print(f"  player_country:      {player.id} ({player.name}), population={player.population}")

    report = entry.report()
    if report is None:
        print("  report:              (genesis — no turn was resolved to reach this state)")
    else:
        # report.resolved_turn is the turn *before* this one — the turn whose
        # decisions were resolved to produce this entry's state.
        print(f"  report (from resolving turn {report.resolved_turn}):")
        for report_entry in report.entries:
            print(f"    [{report_entry.category}] {report_entry.summary}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mandate", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_new = subparsers.add_parser("new", help="create a new game from a scenario file")
    p_new.add_argument("--scenario", required=True, help="path to a scenario YAML file")
    p_new.add_argument("--out", required=True, help="path to write the new save file")
    p_new.add_argument("--seed", type=int, default=None, help="override the scenario's seed")
    p_new.set_defaults(func=_cmd_new)

    p_inspect = subparsers.add_parser("inspect", help="load a save and report its integrity status")
    p_inspect.add_argument("--state", required=True, help="path to a save file")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_resolve = subparsers.add_parser("resolve", help="resolve N turns and write a new save file")
    p_resolve.add_argument("--state", required=True, help="path to the input save file")
    p_resolve.add_argument("--turns", type=int, default=1, help="number of turns to resolve")
    p_resolve.add_argument("--out", required=True, help="path to write the resulting save file")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_history = subparsers.add_parser("history", help="list turns, or inspect one historical turn")
    p_history.add_argument("--state", required=True, help="path to a save file")
    p_history.add_argument("--turn", type=int, default=None, help="show one specific turn")
    p_history.set_defaults(func=_cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MandateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
