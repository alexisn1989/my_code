"""Presentation-layer calibration for generic policy-card presets (Gate 4A3A).

A policy card offers ONE step in a direction, not an arbitrary target -- "raise
this tax rate" rather than "enter a tax rate". How large that step is is a
catalog-generation choice, not a simulation rule, so it is calibrated HERE, in
`app/api/`, deliberately outside `app/simulation/`: this module changes no
engine constant, no `RULESET_VERSION`, and no scenario content. `policy_cards.py`
(the catalog generator) is the only importer.

Both constants were measured against all three shipped scenarios before being
pinned (Gate 4A3A plan, R8); `tests/test_policy_card_calibration.py` pins the
exact per-category, per-scenario numbers this module produces so a future
change to either constant is caught rather than silently reshaping every card.
"""

from __future__ import annotations

TAX_STEP_BPS = 500
"""A generic tax card moves a rate by +/-5.00pp (500 bps).

Not a new number invented for the catalog: it is the exact step the engine's
own calibration tests (`tests/test_scenario_legislature_calibration.py`'s
`_tax_rise_5pp`) already exercise, reused here rather than authored fresh.
"""

SPENDING_STEP_NUMERATOR = 1
SPENDING_STEP_DENOMINATOR = 10


def spending_step(current_amount: int) -> int:
    """The generic spending-card step for one category: 10% of its current
    amount, integer floor (`current // 10`).

    Measured across all three shipped scenarios: 0.57%-2.38% of TOTAL program
    spending in every category, in every scenario -- small enough to be a real
    budgetary choice, never a shock, and never zero for any category any
    shipped scenario actually authors.

    Returns 0 when `current_amount < 10` (including 0), which callers MUST
    treat as "no baseline to scale from" (`no_baseline_to_scale`), never as a
    legal no-op card: `SpendingPlanState` permits an authored zero even though
    no shipped scenario currently uses one.
    """
    return (current_amount * SPENDING_STEP_NUMERATOR) // SPENDING_STEP_DENOMINATOR
