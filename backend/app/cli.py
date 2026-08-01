"""Headless entry point: create games and resolve turns without a server.

Proves the simulation engine works end to end (construct a `GameState`,
submit `DecisionSet`s, call `resolve_turn`, get back a new `GameState` and
`TurnReport`) without FastAPI or a database. Three subcommands, each doing a
real state-file round trip:

    mandate new --scenario data/scenarios/tiny_valid.yaml --out save.json
    mandate inspect --state save.json
    mandate resolve --state save.json --turns 8 --out save.turn8.json

`new` writes a versioned JSON state file. `inspect` reads and validates one
without writing anything. `resolve` reads one, resolves N turns (submitting
an empty `DecisionSet` each turn — no decision *content* exists yet, only the
pipeline that would consume it), and writes the result to a distinct output
path; it refuses to overwrite its own input, foreshadowing the "new snapshot
row per turn, never overwritten" persistence model Phase 4 will use for real.

This state-file format is a Phase 1 stand-in for testing, not the durable
save-game format described in the product spec (§29) — that is built on top
of the database in Phase 4. It is kept in `cli.py` rather than a shared module
for that reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.errors import MandateError, SaveFileError
from app.simulation.decisions import DecisionSet
from app.simulation.report import TurnReport
from app.simulation.resolver import resolve_turn
from app.simulation.state import GameState

STATE_FILE_SCHEMA_VERSION = 1


def _write_state_file(path: Path, state: GameState) -> None:
    payload: dict[str, Any] = {
        "state_file_schema_version": STATE_FILE_SCHEMA_VERSION,
        "state": state.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_state_file(path: Path) -> GameState:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SaveFileError(f"could not read state file {path}: {exc}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SaveFileError(f"state file {path} is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or "state" not in payload:
        raise SaveFileError(f"state file {path} is missing the top-level 'state' object")

    file_version = payload.get("state_file_schema_version")
    if file_version != STATE_FILE_SCHEMA_VERSION:
        raise SaveFileError(
            f"state file {path} has state_file_schema_version={file_version!r}; "
            f"this build only reads version {STATE_FILE_SCHEMA_VERSION!r}"
        )

    try:
        return GameState.model_validate(payload["state"])
    except ValidationError as exc:
        raise SaveFileError(f"state file {path} failed validation: {exc}") from exc


def _cmd_new(args: argparse.Namespace) -> int:
    from app.content.scenarios import load_scenario_file

    state = load_scenario_file(args.scenario)
    if args.seed is not None:
        state = state.model_copy(update={"seed": args.seed})

    out_path = Path(args.out)
    _write_state_file(out_path, state)
    print(
        f"created game from scenario {args.scenario!r}: "
        f"seed={state.seed} turn={state.turn} -> wrote {out_path}"
    )
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    state = _read_state_file(Path(args.state))
    player = state.world.countries[state.world.player_country_id]
    print(f"state file: {args.state}")
    print(f"  schema_version:   {state.schema_version}")
    print(f"  ruleset_version:  {state.ruleset_version}")
    print(f"  content_version:  {state.content_version}")
    print(f"  seed:             {state.seed}")
    print(f"  turn:             {state.turn}")
    print(f"  state_version:    {state.state_version}")
    print(f"  player_country:   {player.id} ({player.name}), population={player.population}")
    print(f"  countries:        {', '.join(sorted(state.world.countries))}")
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

    state = _read_state_file(state_path)
    print(f"resolving {args.turns} turn(s) from turn {state.turn} (seed={state.seed})")

    for _ in range(args.turns):
        decisions = DecisionSet(
            expected_turn=state.turn,
            expected_state_version=state.state_version,
            decisions=[],
        )
        resolution = resolve_turn(state, decisions)
        _print_report(resolution.report)
        state = resolution.state

    _write_state_file(out_path, state)
    print(f"final: turn={state.turn} state_version={state.state_version} -> wrote {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mandate", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_new = subparsers.add_parser("new", help="create a new game from a scenario file")
    p_new.add_argument("--scenario", required=True, help="path to a scenario YAML file")
    p_new.add_argument("--out", required=True, help="path to write the new state file")
    p_new.add_argument("--seed", type=int, default=None, help="override the scenario's seed")
    p_new.set_defaults(func=_cmd_new)

    p_inspect = subparsers.add_parser("inspect", help="load and validate a state file")
    p_inspect.add_argument("--state", required=True, help="path to a state file")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_resolve = subparsers.add_parser("resolve", help="resolve N turns and write a new state file")
    p_resolve.add_argument("--state", required=True, help="path to the input state file")
    p_resolve.add_argument("--turns", type=int, default=1, help="number of turns to resolve")
    p_resolve.add_argument("--out", required=True, help="path to write the resulting state file")
    p_resolve.set_defaults(func=_cmd_resolve)

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
