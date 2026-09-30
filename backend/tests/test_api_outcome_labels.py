"""Gate 4A3 Commit 5b, finding T1: a concluded campaign names its reason in words.

Before this, `TerminalSummary.reason_label` was the engine's own enum value, so the
terminal screen showed a player `term_limit_exit, turn 32`. The wording now comes
from one authored map in `app.api.outcome_labels`; these tests pin that the map is
complete, that no identifier leaks through it, and that every headline a player has
already seen is unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.outcome_labels import (
    REMOVAL_REASON_TEXT,
    VICTORY_REASON_TEXT,
    outcome_reason_text,
)
from app.api.projections import TerminalSummary, _terminal_summary
from app.api.save_registry import SaveRepository
from app.content.scenarios import load_scenario_file
from app.simulation.state import (
    GameState,
    OutcomeBucket,
    RemovalReason,
    TerminalOutcomeState,
    VictoryReason,
)
from tests.conftest import SCENARIO_DIR

ALL_REASONS: tuple[RemovalReason | VictoryReason, ...] = (*RemovalReason, *VictoryReason)


def _concluded(reason: RemovalReason | VictoryReason, turn: int = 11) -> GameState:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    country = state.world.countries[state.world.player_country_id]
    assert country.politics is not None
    if isinstance(reason, VictoryReason):
        outcome = TerminalOutcomeState(
            bucket=OutcomeBucket.VICTORY, victory_reason=reason, turn=turn
        )
    else:
        outcome = TerminalOutcomeState(
            bucket=OutcomeBucket.DEFEAT, removal_reason=reason, turn=turn
        )
    country.politics = country.politics.model_copy(update={"terminal_outcome": outcome})
    return state


def _summary(state: GameState) -> TerminalSummary:
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None
    summary = _terminal_summary(politics)
    assert summary is not None
    return summary


def test_each_map_covers_exactly_its_enum() -> None:
    """Set equality, not containment: a reason added to the engine without wording fails here,
    and so does a stale entry for a reason the engine no longer has."""
    assert set(REMOVAL_REASON_TEXT) == set(RemovalReason)
    assert set(VICTORY_REASON_TEXT) == set(VictoryReason)


@pytest.mark.parametrize("reason", ALL_REASONS, ids=lambda r: r.value)
def test_no_label_or_phrase_is_an_identifier(reason: RemovalReason | VictoryReason) -> None:
    text = outcome_reason_text(reason)
    for value in (text.label, text.phrase):
        assert value.strip() == value and value
        assert "_" not in value
    # A single-word phrase ("coup") is the same letters as its identifier by design -- the
    # headline must not change -- so only the LABEL is required to differ from the raw value.
    assert text.label != reason.value
    assert text.label[0].isupper()


@pytest.mark.parametrize("reason", ALL_REASONS, ids=lambda r: r.value)
def test_the_projected_label_is_the_authored_one(reason: RemovalReason | VictoryReason) -> None:
    summary = _summary(_concluded(reason))
    assert summary.reason_label == outcome_reason_text(reason).label
    assert reason.value not in summary.reason_label


@pytest.mark.parametrize("reason", ALL_REASONS, ids=lambda r: r.value)
def test_every_headline_is_byte_identical_to_the_legacy_one(
    reason: RemovalReason | VictoryReason,
) -> None:
    """The legacy headline replaced underscores in the identifier. The authored phrases were
    chosen to be exactly those words, so no headline a player has seen changes -- only the label
    stops being an identifier. This test is the proof, per reason."""
    spoken = reason.value.replace("_", " ")
    expected = (
        f"Victory: {spoken}, turn 11."
        if isinstance(reason, VictoryReason)
        else f"Removed from office: {spoken}, turn 11."
    )
    assert _summary(_concluded(reason)).headline == expected


@pytest.mark.parametrize("reason", ALL_REASONS, ids=lambda r: r.value)
def test_the_save_list_summary_uses_the_same_wording(
    reason: RemovalReason | VictoryReason,
) -> None:
    """The save index is persisted, so its text is also pinned to the legacy format."""
    state = _concluded(reason, turn=32)
    fake_save = SimpleNamespace(current_state=lambda: state)
    text = SaveRepository._terminal_summary_text(fake_save)  # type: ignore[arg-type]
    bucket = "Victory" if isinstance(reason, VictoryReason) else "Defeat"
    assert text == f"{bucket} - {reason.value.replace('_', ' ')}, turn 32"
    assert text == f"{bucket} - {outcome_reason_text(reason).phrase}, turn 32"


def test_an_ongoing_campaign_has_no_terminal_summary() -> None:
    state = load_scenario_file(SCENARIO_DIR / "tiny_valid.yaml")
    politics = state.world.countries[state.world.player_country_id].politics
    assert politics is not None and politics.terminal_outcome is None
    assert _terminal_summary(politics) is None
