"""Authored player-facing wording for why a campaign ended.

The engine records a concluded campaign as an enum value -- `term_limit_exit`,
`electoral_defeat` -- which is an identifier, not prose. Before this module the
API rendered that identifier to the player verbatim as `reason_label`, and built
the headline by replacing underscores with spaces: a transformation of an
identifier into text, which is exactly what `POST_DISPLAY_NAMES` and
`LEGISLATIVE_PROPOSAL_DISPLAY_NAMES` exist to prevent.

So each reason is authored here once, as two strings with two jobs:

* `label` stands on its own, sentence case, where the screen names the reason;
* `phrase` is the same reason as it reads inside the headline sentence.

The phrases are deliberately the words the old underscore replacement produced,
so every headline a player has already seen stays byte-identical; only the label
stops being an identifier.

This lives in the API layer, not in `app/simulation/state.py` beside the other
display maps, because it is presentation only: no resolution reads it, so it
belongs with the projections that render it. There is deliberately no fallback
for a missing entry -- indexing fails -- and a test pins each map's keys to
every member of its enum, so a new reason cannot ship without its wording.
"""

from __future__ import annotations

from typing import NamedTuple

from app.simulation.state import RemovalReason, VictoryReason


class OutcomeReasonText(NamedTuple):
    label: str
    phrase: str


REMOVAL_REASON_TEXT: dict[RemovalReason, OutcomeReasonText] = {
    RemovalReason.COUP: OutcomeReasonText("Coup", "coup"),
    RemovalReason.FORCED_ABDICATION: OutcomeReasonText("Forced abdication", "forced abdication"),
    RemovalReason.ASSASSINATION: OutcomeReasonText("Assassination", "assassination"),
    RemovalReason.IMPEACHMENT: OutcomeReasonText("Impeachment", "impeachment"),
    RemovalReason.ELECTORAL_DEFEAT: OutcomeReasonText("Electoral defeat", "electoral defeat"),
    RemovalReason.TERM_LIMIT_EXIT: OutcomeReasonText("Term limit exit", "term limit exit"),
}

VICTORY_REASON_TEXT: dict[VictoryReason, OutcomeReasonText] = {
    VictoryReason.PEACEFUL_LIBERALIZATION_COMPLETED: OutcomeReasonText(
        "Peaceful liberalization completed", "peaceful liberalization completed"
    ),
}

UNKNOWN_REASON_TEXT = OutcomeReasonText("Unknown", "unknown")
"""Only for an outcome that carries no reason at all -- the pre-existing `None`
path, kept unchanged. It is never used for a reason that has no entry."""


def outcome_reason_text(reason: RemovalReason | VictoryReason | None) -> OutcomeReasonText:
    if reason is None:
        return UNKNOWN_REASON_TEXT
    if isinstance(reason, VictoryReason):
        return VICTORY_REASON_TEXT[reason]
    return REMOVAL_REASON_TEXT[reason]
