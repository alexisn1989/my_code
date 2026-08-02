"""Player (and, later, AI) decisions submitted for a turn.

`Decision` is intentionally generic in this Phase-1 skeleton: no concrete
decision kinds (budget change, policy enactment, diplomatic action, ...)
exist yet, since none of the systems that would act on them are implemented.
Concrete kinds are added alongside the systems that interpret them (Phase 2+)
by extending `kind` with a registered literal and giving `payload` a typed
shape — `Decision` itself does not need to change shape when that happens.

`DecisionSet.expected_turn` and `expected_state_version` are the
stale-submission guard described in the product spec (§30): a decision set
built against an out-of-date view of the game must be rejected, not silently
applied against whatever the state has since become.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_STRICT_CONFIG = ConfigDict(extra="forbid")


class Decision(BaseModel):
    """One player-submitted action. Shape is deliberately loose in Phase 1."""

    model_config = _STRICT_CONFIG

    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DecisionSet(BaseModel):
    """All decisions a player submits for a single turn resolution attempt."""

    model_config = _STRICT_CONFIG

    expected_turn: int = Field(ge=0)
    expected_state_version: int = Field(ge=0)
    decisions: list[Decision] = Field(default_factory=list)
