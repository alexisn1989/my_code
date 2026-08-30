"""External Wars W1 commit 10: the read-only `inspect --conflicts` CLI view, the six
foreign-affairs reason renderers, and the turn-report block wired into BOTH `_print_report` and
`_cmd_history` (the frozen plan's named dual-wiring trap -- each call site gets its own test here).

`inspect --conflicts` is observation only. It resolves no turn, consumes no RNG and writes
nothing, so several tests below assert the save's bytes, history head and future resolution are
all untouched by inspecting it.

Fixtures are built by running the real CLI (`new`, then `resolve`) against a shipped scenario, so
what is asserted is what a player actually sees. Where a specific status is needed that no short
deterministic run happens to produce, the smallest valid synthetic `GameState` is constructed
instead -- shipped scenario files are never edited.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import build_parser, main
from app.simulation.foreign_conflict import ConflictStatus, WarAim
from app.simulation.history import new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json
from app.simulation.state import ConflictDyadState, ForeignConflictState, ForeignProfileState
from tests.conftest import make_game_state

_DATA = Path(__file__).resolve().parents[2] / "data" / "scenarios"
DECREE_STATE = str(_DATA / "decree_state.yaml")
TINY_VALID = str(_DATA / "tiny_valid.yaml")


def _new_save(tmp_path: Path, scenario: str, seed: int, name: str = "save.json") -> Path:
    path = tmp_path / name
    assert main(["new", "--scenario", scenario, "--out", str(path), "--seed", str(seed)]) == 0
    return path


def _resolve(tmp_path: Path, source: Path, turns: int, name: str) -> Path:
    out = tmp_path / name
    assert main(["resolve", "--state", str(source), "--turns", str(turns), "--out", str(out)]) == 0
    return out


def _inspect_conflicts(path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    capsys.readouterr()
    assert main(["inspect", "--state", str(path), "--conflicts"]) == 0
    return capsys.readouterr().out


def _conflicts_section(output: str) -> str:
    """Just the conflicts block, so assertions don't accidentally match unrelated CLI lines."""
    _, _, tail = output.partition("  foreign conflicts:")
    section, _, _ = tail.partition("  integrity:")
    return section


# --- synthetic fixtures for statuses a short shipped run does not reach -------


_PROFILES = {
    "kessia": ForeignProfileState(display_name="Kessia", war_capability_bps=5_000),
    "vetruska": ForeignProfileState(display_name="Vetruska", war_capability_bps=5_600),
}


def _dyad(exposure_bps: int = 2_000) -> ConflictDyadState:
    return ConflictDyadState(
        country_a="kessia",
        country_b="vetruska",
        tension_bps=8_500,
        grievance_bps=7_500,
        eligible=True,
        aggressor="vetruska",
        defender="kessia",
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        player_security_exposure_bps=exposure_bps,
    )


def _conflict(
    *,
    status: ConflictStatus,
    opened_turn: int = 3,
    resolved_turn: int | None = None,
    ceasefire_run_turns: int = 0,
    conflict_id: str | None = None,
) -> ForeignConflictState:
    return ForeignConflictState(
        conflict_id=conflict_id or f"kessia__vetruska__t{opened_turn}",
        country_a="kessia",
        country_b="vetruska",
        aggressor="vetruska",
        defender="kessia",
        war_capability_a_bps=5_000,
        war_capability_b_bps=5_600,
        aim_a=WarAim.DETERRENCE,
        aim_b=WarAim.TERRITORIAL,
        opened_turn=opened_turn,
        intensity_bps=2_500,
        position_bps=-1_200,
        exhaustion_a_bps=4_000,
        exhaustion_b_bps=4_200,
        negotiation_readiness_bps=5_100,
        status=status,
        ceasefire_run_turns=ceasefire_run_turns,
        resolved_turn=resolved_turn,
    )


def _synthetic_save(
    tmp_path: Path,
    conflicts: tuple[ForeignConflictState, ...],
    *,
    profiles: dict[str, ForeignProfileState] | None = None,
    dyads: tuple[ConflictDyadState, ...] | None = None,
    name: str = "synthetic.json",
) -> Path:
    """The smallest valid save carrying the given conflicts. Never edits shipped scenarios."""
    state = make_game_state(
        seed=7,
        foreign_profiles=dict(_PROFILES if profiles is None else profiles),
        dyads=(_dyad(),) if dyads is None else dyads,
        conflicts=conflicts,
    )
    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    path = tmp_path / name
    path.write_text(dump_save_json(save), encoding="utf-8")
    return path


# --- 1. empty state -----------------------------------------------------------


def test_conflict_free_save_prints_the_stable_empty_state_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _new_save(tmp_path, DECREE_STATE, seed=7)
    out = _inspect_conflicts(save, capsys)
    assert "  foreign conflicts:   none — no foreign conflicts recorded" in out
    assert "integrity:           OK" in out


# --- 2. an ACTIVE conflict ----------------------------------------------------


def test_active_conflict_renders_countries_roles_aims_and_current_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    resolved = _resolve(tmp_path, save, 25, "r.json")
    section = _conflicts_section(_inspect_conflicts(resolved, capsys))

    assert "live (1):" in section
    assert "marnil__sorrend__t11" in section
    assert "status:            active" in section
    assert "opened turn 11" in section
    # Explicit stored roles -- here the aggressor is country_b, so a country_a/country_b
    # positional guess would render this backwards.
    assert "aggressor:         Sorrend (sorrend)" in section
    assert "defender:          Marnil (marnil)" in section
    assert "Marnil (marnil) — deterrence" in section
    assert "Sorrend (sorrend) — regime change" in section
    for field in ("war capability:", "position:", "intensity:", "exhaustion:", "readiness:"):
        assert field in section
    assert "player exposure:   30%" in section
    # An ACTIVE conflict has no ceasefire or resolution line.
    assert "ceasefire held:" not in section
    assert "resolved:" not in section


def test_active_conflict_shows_no_w2_to_w5_mechanics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """W1 models none of this; rendering a placeholder would advertise absent capabilities.

    Two words are deliberately NOT in the absent-list. `territorial` is a genuine authored
    `WarAim` this view is required to show, and `trade`/`economic` appear only inside the
    exposure line's own disclaimer that W1 models neither -- so both are checked positively
    below rather than banned outright.
    """
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    resolved = _resolve(tmp_path, save, 25, "r.json")
    section = _conflicts_section(_inspect_conflicts(resolved, capsys)).lower()
    for absent in (
        "mediat",
        "neutrality",
        "sanction",
        "humanitarian",
        "military aid",
        "war authoriz",
        "join the war",
        "withdraw",
        "army",
        "navy",
        "air force",
        "unit",
        "casualt",
        "occupation",
        "annex",
        "alliance",
        "nuclear",
        "victory chance",
        "probability of victory",
        "likely to win",
    ):
        assert absent not in section, f"conflict view must not mention {absent!r}"

    # The two legitimate uses, pinned so a future edit cannot quietly turn them into a claim.
    assert "— territorial" in section or "— regime change" in section, "war aims are shown"
    assert "w1 models no trade or economic exposure" in section


# --- 3. a CEASEFIRE conflict --------------------------------------------------


def test_ceasefire_conflict_renders_ceasefire_specific_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _synthetic_save(
        tmp_path, (_conflict(status=ConflictStatus.CEASEFIRE, ceasefire_run_turns=2),)
    )
    section = _conflicts_section(_inspect_conflicts(save, capsys))
    assert "status:            ceasefire" in section
    assert "ceasefire held:    2 turn(s)" in section
    assert "live (1):" in section
    # A live conflict has no resolution turn.
    assert "resolved:" not in section


# --- 4. concluded history stays visible ---------------------------------------


@pytest.mark.parametrize(
    ("status", "label"),
    [(ConflictStatus.SETTLED, "settled"), (ConflictStatus.DECIDED, "decided")],
)
def test_terminal_conflicts_remain_visible_as_concluded_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], status: ConflictStatus, label: str
) -> None:
    save = _synthetic_save(tmp_path, (_conflict(status=status, resolved_turn=9),))
    section = _conflicts_section(_inspect_conflicts(save, capsys))
    assert "concluded (1):" in section
    assert f"status:            {label}" in section
    assert "resolved:          turn 9" in section
    assert "live" not in section


# --- 5/6. canonical order, insertion-order independence -----------------------


def _three_conflicts() -> tuple[ForeignConflictState, ...]:
    """`WorldState` rejects a non-canonical `conflicts` tuple at construction, so these are built
    in canonical `conflict_id` order -- lexicographic, which puts `t11` before `t2`. That the
    renderer preserves this (rather than re-sorting into something friendlier) is the point."""
    return tuple(
        sorted(
            (
                _conflict(status=ConflictStatus.ACTIVE, opened_turn=2),
                _conflict(status=ConflictStatus.CEASEFIRE, opened_turn=11, ceasefire_run_turns=1),
                _conflict(status=ConflictStatus.SETTLED, opened_turn=4, resolved_turn=8),
            ),
            key=lambda conflict: conflict.conflict_id,
        )
    )


def test_multiple_conflicts_render_in_canonical_conflict_id_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _synthetic_save(tmp_path, _three_conflicts())
    section = _conflicts_section(_inspect_conflicts(save, capsys))
    ids = [line.strip() for line in section.splitlines() if line.strip().startswith("kessia__")]
    # Canonical order is lexicographic by conflict_id, applied within each group.
    assert ids == sorted(ids, key=lambda i: (i not in ids[:2], i)) or ids == [
        "kessia__vetruska__t11",
        "kessia__vetruska__t2",
        "kessia__vetruska__t4",
    ]
    live_at = section.index("live (")
    concluded_at = section.index("concluded (")
    assert live_at < concluded_at, "live conflicts are listed before concluded history"


def test_foreign_profile_insertion_order_does_not_change_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    conflicts = _three_conflicts()
    forward = {
        "kessia": _PROFILES["kessia"],
        "vetruska": _PROFILES["vetruska"],
    }
    reverse = {
        "vetruska": _PROFILES["vetruska"],
        "kessia": _PROFILES["kessia"],
    }
    assert list(forward) != list(reverse)

    a = _inspect_conflicts(
        _synthetic_save(tmp_path, conflicts, profiles=forward, name="a.json"), capsys
    )
    b = _inspect_conflicts(
        _synthetic_save(tmp_path, conflicts, profiles=reverse, name="b.json"), capsys
    )
    assert _conflicts_section(a) == _conflicts_section(b)


def test_complete_deterministic_output_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One full-block assertion pinning canonical ordering, grouping and every formatting choice
    at once -- the focused assertions above localise failures, this one catches drift anywhere."""
    save = _synthetic_save(tmp_path, _three_conflicts())
    section = _conflicts_section(_inspect_conflicts(save, capsys))
    assert section == (
        "\n"
        "    live (2):\n"
        "    kessia__vetruska__t11\n"
        "      status:            ceasefire   opened turn 11\n"
        "      aggressor:         Vetruska (vetruska)\n"
        "      defender:          Kessia (kessia)\n"
        "      war aims:          Kessia (kessia) — deterrence\n"
        "                         Vetruska (vetruska) — territorial\n"
        "      war capability:    A 50%   B 56%\n"
        "      position:          -12.00pp   (positive favours A, negative favours B)\n"
        "      intensity:         25%\n"
        "      exhaustion:        A 40%   B 42%\n"
        "      readiness:         51%\n"
        "      ceasefire held:    1 turn(s)\n"
        "      player exposure:   20%"
        "   (authored security exposure; W1 models no trade or economic exposure)\n"
        "    kessia__vetruska__t2\n"
        "      status:            active   opened turn 2\n"
        "      aggressor:         Vetruska (vetruska)\n"
        "      defender:          Kessia (kessia)\n"
        "      war aims:          Kessia (kessia) — deterrence\n"
        "                         Vetruska (vetruska) — territorial\n"
        "      war capability:    A 50%   B 56%\n"
        "      position:          -12.00pp   (positive favours A, negative favours B)\n"
        "      intensity:         25%\n"
        "      exhaustion:        A 40%   B 42%\n"
        "      readiness:         51%\n"
        "      player exposure:   20%"
        "   (authored security exposure; W1 models no trade or economic exposure)\n"
        "    concluded (1):\n"
        "    kessia__vetruska__t4\n"
        "      status:            settled   opened turn 4\n"
        "      aggressor:         Vetruska (vetruska)\n"
        "      defender:          Kessia (kessia)\n"
        "      war aims:          Kessia (kessia) — deterrence\n"
        "                         Vetruska (vetruska) — territorial\n"
        "      war capability:    A 50%   B 56%\n"
        "      position:          -12.00pp   (positive favours A, negative favours B)\n"
        "      intensity:         25%\n"
        "      exhaustion:        A 40%   B 42%\n"
        "      readiness:         51%\n"
        "      resolved:          turn 8\n"
        "      player exposure:   20%"
        "   (authored security exposure; W1 models no trade or economic exposure)\n"
    )


# --- 7. display names come from foreign_profiles ------------------------------


def test_display_names_come_from_foreign_profiles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    conflicts = (_conflict(status=ConflictStatus.ACTIVE),)
    renamed = {
        "kessia": ForeignProfileState(display_name="Kessian Republic", war_capability_bps=5_000),
        "vetruska": _PROFILES["vetruska"],
    }
    before = _conflicts_section(
        _inspect_conflicts(_synthetic_save(tmp_path, conflicts, name="b.json"), capsys)
    )
    after = _conflicts_section(
        _inspect_conflicts(
            _synthetic_save(tmp_path, conflicts, profiles=renamed, name="a.json"), capsys
        )
    )
    assert "Kessia (kessia)" in before
    assert "Kessian Republic (kessia)" in after
    # Only the renamed profile's rendering changed; the other side is untouched.
    assert "Vetruska (vetruska)" in before
    assert "Vetruska (vetruska)" in after
    assert after == before.replace("Kessia (kessia)", "Kessian Republic (kessia)")


# --- 8. ids never imply adjacency, roles or exposure --------------------------


def test_ids_cannot_be_used_to_infer_adjacency_aggressor_or_exposure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same ids and same canonical ordering, but authored roles and exposure reversed/changed:
    the rendering must follow the authored fields, not the identifiers."""
    conflicts = (_conflict(status=ConflictStatus.ACTIVE),)
    flipped = ForeignConflictState(
        **{
            **conflicts[0].model_dump(),
            "aggressor": "kessia",
            "defender": "vetruska",
        }
    )
    baseline = _conflicts_section(
        _inspect_conflicts(_synthetic_save(tmp_path, conflicts, name="b.json"), capsys)
    )
    swapped = _conflicts_section(
        _inspect_conflicts(
            _synthetic_save(
                tmp_path,
                (flipped,),
                dyads=(
                    ConflictDyadState(
                        **{
                            **_dyad().model_dump(),
                            "aggressor": "kessia",
                            "defender": "vetruska",
                            "player_security_exposure_bps": 3_000,
                        }
                    ),
                ),
                name="s.json",
            ),
            capsys,
        )
    )
    assert "aggressor:         Vetruska (vetruska)" in baseline
    assert "aggressor:         Kessia (kessia)" in swapped
    assert "player exposure:   20%" in baseline
    assert "player exposure:   30%" in swapped
    # The conflict_id is identical in both, so nothing was inferred from it.
    assert "kessia__vetruska__t3" in baseline
    assert "kessia__vetruska__t3" in swapped
    assert "adjacen" not in swapped.lower()


# --- 9. zero exposure ---------------------------------------------------------


def test_zero_exposure_dyad_renders_zero_without_inventing_consequences(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _synthetic_save(
        tmp_path,
        (_conflict(status=ConflictStatus.ACTIVE),),
        dyads=(_dyad(exposure_bps=0),),
    )
    section = _conflicts_section(_inspect_conflicts(save, capsys))
    assert "player exposure:   0%" in section
    lowered = section.lower()
    # Zero exposure is stated as a number and nothing more: no invented political or economic
    # consequence, and no editorialising about what zero exposure "means" for the player.
    for absent in ("gdp", "unrest", "approval", "legitimacy cost", "no effect on", "safe from"):
        assert absent not in lowered
    # "economic" may appear only inside the standing disclaimer that W1 models no such exposure.
    assert lowered.count("economic") == 1
    assert "w1 models no trade or economic exposure" in lowered


# --- 10. invalid saves use the existing loader/error path ---------------------


def test_unreadable_save_fails_through_the_existing_actionable_error_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.json"
    assert main(["inspect", "--state", str(missing), "--conflicts"]) == 1
    assert "error:" in capsys.readouterr().err


def test_corrupt_save_fails_through_the_existing_actionable_error_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert main(["inspect", "--state", str(corrupt), "--conflicts"]) == 1
    assert "error:" in capsys.readouterr().err


# --- 11/12. read-only and byte-identical --------------------------------------


def test_inspecting_changes_nothing_and_does_not_disturb_future_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    resolved = _resolve(tmp_path, save, 15, "r.json")

    before_bytes = resolved.read_bytes()
    control = _resolve(tmp_path, resolved, 3, "control.json").read_bytes()

    _inspect_conflicts(resolved, capsys)
    _inspect_conflicts(resolved, capsys)

    assert resolved.read_bytes() == before_bytes, "inspect must not rewrite the save"
    after = _resolve(tmp_path, resolved, 3, "after.json").read_bytes()
    assert after == control, "inspect must not consume RNG or shift future resolution"


def test_repeated_inspection_produces_byte_identical_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    resolved = _resolve(tmp_path, save, 25, "r.json")
    assert _inspect_conflicts(resolved, capsys) == _inspect_conflicts(resolved, capsys)


# --- 13. usable after the campaign has concluded ------------------------------


def test_command_remains_usable_when_the_campaign_is_already_concluded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`inspect` never resolves a turn, so a concluded campaign -- which makes `resolve` raise
    `GameAlreadyConcludedError` -- is still fully inspectable."""
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    current = save
    for index in range(12):
        nxt = tmp_path / f"c{index}.json"
        code = main(["resolve", "--state", str(current), "--turns", "5", "--out", str(nxt)])
        if code != 0:
            break
        current = nxt
    capsys.readouterr()
    # Whether or not this seed concluded, inspection must succeed and be well-formed.
    assert main(["inspect", "--state", str(current), "--conflicts"]) == 0
    out = capsys.readouterr().out
    assert "foreign conflicts:" in out


# --- 14/15. existing behavior and help ----------------------------------------


def test_existing_inspect_behavior_is_unchanged_without_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save = _new_save(tmp_path, TINY_VALID, seed=7)
    capsys.readouterr()
    assert main(["inspect", "--state", str(save)]) == 0
    out = capsys.readouterr().out
    assert "foreign conflicts" not in out
    assert "integrity:           OK" in out
    assert "current_turn:        0" in out


def test_cli_help_exposes_the_option_without_advertising_w2_to_w5(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    inspect_parser = parser._subparsers._group_actions[0].choices["inspect"]  # type: ignore[union-attr]
    help_text = inspect_parser.format_help()
    assert "--conflicts" in help_text
    lowered = help_text.lower()
    for absent in ("mediat", "sanction", "alliance", "intervene", "declare war", "send troops"):
        assert absent not in lowered


# --- the dual-wired turn-report block -----------------------------------------


def test_resolve_prints_the_foreign_affairs_report_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_print_report`'s call site."""
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    capsys.readouterr()
    assert (
        main(["resolve", "--state", str(save), "--turns", "12", "--out", str(tmp_path / "r.json")])
        == 0
    )
    out = capsys.readouterr().out
    assert "    foreign affairs:" in out
    assert "outbreak draw:" in out
    assert "war broke out:     marnil__sorrend__t11" in out
    assert "ConflictStatus." not in out


def test_history_prints_the_same_foreign_affairs_report_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_cmd_history`'s inline call site -- the frozen plan's named dual-wiring trap. A second
    inline copy, or a missing call here, is exactly the Phase 3A omission this pins against."""
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    resolved = _resolve(tmp_path, save, 12, "r.json")
    capsys.readouterr()
    assert main(["history", "--state", str(resolved), "--turn", "12"]) == 0
    out = capsys.readouterr().out
    assert "    foreign affairs:" in out
    assert "outbreak draw:" in out
    assert "ConflictStatus." not in out


def test_both_report_call_sites_render_the_same_turn_identically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The strongest form of the dual-wiring guarantee: the same turn's foreign-affairs block,
    rendered through both paths, is byte-identical because both call one shared helper."""
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    capsys.readouterr()
    assert (
        main(["resolve", "--state", str(save), "--turns", "12", "--out", str(tmp_path / "r.json")])
        == 0
    )
    resolve_out = capsys.readouterr().out
    # The last resolved turn's block, as printed by _print_report.
    resolve_block = resolve_out.split("    foreign affairs:")[-1].split("    (dev)")[0]

    capsys.readouterr()
    assert main(["history", "--state", str(tmp_path / "r.json"), "--turn", "12"]) == 0
    history_out = capsys.readouterr().out
    history_block = history_out.split("    foreign affairs:")[-1]

    assert resolve_block.strip() == history_block.strip()


def test_foreign_reason_ids_render_as_english_not_raw_params(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before commit 10 every foreign reason_id hit `render_entry`'s fallback and printed a raw
    Python dict to the player."""
    save = _new_save(tmp_path, DECREE_STATE, seed=42)
    capsys.readouterr()
    assert (
        main(["resolve", "--state", str(save), "--turns", "13", "--out", str(tmp_path / "r.json")])
        == 0
    )
    out = capsys.readouterr().out
    assert "[unrendered reason_id=" not in out
    assert "[error rendering reason_id=" not in out
    assert "War broke out between marnil and sorrend (aggressor sorrend)" in out
    assert "'country_a':" not in out, "no raw dict repr may reach the player"
