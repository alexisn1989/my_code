"""Pure legitimacy and political-capital formulas (Phase 3A).

**No function in this module accepts a constitutional type.** Not `ConstitutionState`, not
`ExecutiveSystem`, not `ExecutiveSelection`, `Legislature`, `JudicialReview`,
`TerritorialOrganization`, `AmendmentDifficulty` or `DecreeAuthority`. Every signature below takes
integers and returns integers. That is a `mypy`-checked, structural guarantee that the *form* of a
government cannot influence how *accepted* it is — stronger than any test, because there is no
argument through which form could arrive. `test_legitimacy_neutrality.py` then proves the numeric
consequence: a monarchy and a democracy with the same authored order support and the same economic
observations produce identical legitimacy sequences.

Legitimacy moves for exactly two reasons:

- **Order-support drift** — legitimacy closes a fixed fraction of the gap toward
  `PoliticalState.constitutional_order_support_bps`, the scenario-authored public acceptance of
  this constitutional order. Bidirectional: legitimacy above its order's support drifts down.
- **Economic performance** — measured from two signals the engine genuinely models,
  `ProductionReport.total_gross_output` and `LaborMarketReport.unemployment_rate_bps`, each
  compared against the previous turn's persisted baseline.

Inflation, wages, household consumption, public-service quality and inequality are **not modeled**
and contribute nothing; inventing effects from systems that do not exist would be dishonest.

Everything is exact integer arithmetic with a single named rounding step
(`core.politics.trunc_div_toward_zero`). No randomness, no floats, no time access. See
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md` and
`docs/economy_methodology.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import BPS_DENOMINATOR
from app.core.politics import (
    LEGITIMACY_MAX_BPS,
    LEGITIMACY_MIN_BPS,
    PoliticalCapital,
    clamp_bps,
    trunc_div_toward_zero,
)

DRIFT_RATE_BPS = 1_000
"""The fraction of the gap between current legitimacy and authored order support closed each turn:
1,000 bps = 10%, so roughly half of any gap closes in about seven turns.

**A single engine constant applied identically to every government form.** There is no per-form
rate, no per-axis modifier and no table — that uniformity is precisely the neutrality guarantee.
"""

OUTPUT_SENSITIVITY_BPS = 2_500
"""How far a 1% change in total gross output moves legitimacy: 2,500 bps of the change, i.e.
0.25 percentage points. A catastrophic 10% output collapse therefore costs 2.5 pp in one turn —
visible but survivable, which is *required* because Phase 3A must never remove the player."""

UNEMPLOYMENT_SENSITIVITY_BPS = 5_000
"""How far a 1 percentage-point change in unemployment moves legitimacy, with the opposite sign:
0.5 pp. Deliberately twice as sharp per point as output, because unemployment is directly
experienced by the governed whereas aggregate output is not."""

MAX_PERFORMANCE_CONTRIBUTION_BPS = 300
"""Symmetric per-turn cap on the combined economic-performance contribution: +/- 3 pp."""

MAX_TOTAL_LEGITIMACY_CHANGE_BPS = 500
"""Symmetric per-turn cap on the *combined* change from both sources: +/- 5 pp, so no single turn
can traverse the metric regardless of how extreme its inputs are."""

POLITICAL_CAPITAL_BASE_REGENERATION = 200
"""Political capital regenerated each turn regardless of standing: any functioning government
recovers some capacity to act. The floor exists so an illegitimate government is *constrained*,
never *frozen* — freezing would be a removal mechanic, and removal is Phase 3C."""

LEGITIMACY_REGENERATION_COEFFICIENT = 300
"""Additional political capital per turn scaled by legitimacy: at full legitimacy this adds 300,
making regeneration 500 — 2.5x the illegitimate-government floor of 200. Depends on legitimacy,
never on government form, so a legitimate monarchy and a legitimate democracy at the same
legitimacy regenerate identically."""


@dataclass(frozen=True, slots=True)
class PerformanceSignals:
    """The four integers economic-performance legitimacy is computed from.

    Deliberately a flat integer record rather than references to the reports they came from: the
    caller (`phases.py`) reads them out of `ProductionReport`/`LaborMarketReport`, and everything
    downstream works on plain numbers, so no report or state object can reach these formulas.
    """

    baseline_total_gross_output: int
    current_total_gross_output: int
    baseline_unemployment_rate_bps: int
    current_unemployment_rate_bps: int


@dataclass(frozen=True, slots=True)
class PerformanceAssessment:
    """Every intermediate value of the performance calculation, so the report can publish each one
    and re-derive it independently rather than trusting a single opaque total."""

    output_change_bps: int
    output_contribution_bps: int
    unemployment_change_bps: int
    unemployment_contribution_bps: int
    performance_contribution_bps: int


def assess_economic_performance(signals: PerformanceSignals | None) -> PerformanceAssessment:
    """Compute this turn's economic-performance legitimacy contribution.

    `signals is None` means there is no previous-turn baseline — only possible on the very first
    resolution of a fresh scenario — and returns an all-zero assessment. There is no prior turn, so
    there is no performance to assess. A zero-output baseline is **never** fabricated to stand in
    for a missing one: `None` and `baseline_total_gross_output == 0` are different states with
    different meanings, and conflating them would let a first turn register a fictitious collapse.

    When `baseline_total_gross_output == 0` (a genuine zero-output economy on a later turn),
    `output_change_bps` is `0`: there is no proportional change to measure against nothing, and the
    alternative is an unbounded percentage with no meaning. `trunc_div_toward_zero` returns 0 for a
    zero denominator, so no `ZeroDivisionError` path exists. Unemployment needs no such guard — it
    is a difference of two basis-point values, never a quotient.
    """
    if signals is None:
        return PerformanceAssessment(
            output_change_bps=0,
            output_contribution_bps=0,
            unemployment_change_bps=0,
            unemployment_contribution_bps=0,
            performance_contribution_bps=0,
        )

    output_change_bps = trunc_div_toward_zero(
        (signals.current_total_gross_output - signals.baseline_total_gross_output)
        * BPS_DENOMINATOR,
        signals.baseline_total_gross_output,
    )
    output_contribution_bps = trunc_div_toward_zero(
        output_change_bps * OUTPUT_SENSITIVITY_BPS, BPS_DENOMINATOR
    )

    unemployment_change_bps = (
        signals.current_unemployment_rate_bps - signals.baseline_unemployment_rate_bps
    )
    unemployment_contribution_bps = trunc_div_toward_zero(
        -unemployment_change_bps * UNEMPLOYMENT_SENSITIVITY_BPS, BPS_DENOMINATOR
    )

    performance_contribution_bps = clamp_bps(
        output_contribution_bps + unemployment_contribution_bps,
        low=-MAX_PERFORMANCE_CONTRIBUTION_BPS,
        high=MAX_PERFORMANCE_CONTRIBUTION_BPS,
    )
    return PerformanceAssessment(
        output_change_bps=output_change_bps,
        output_contribution_bps=output_contribution_bps,
        unemployment_change_bps=unemployment_change_bps,
        unemployment_contribution_bps=unemployment_contribution_bps,
        performance_contribution_bps=performance_contribution_bps,
    )


def order_support_contribution_bps(*, support_bps: int, opening_legitimacy_bps: int) -> int:
    """Legitimacy's drift toward the authored acceptance of this constitutional order.

    A partial-adjustment step: close `DRIFT_RATE_BPS` (10%) of the remaining gap. Bidirectional —
    a government more accepted than its order's support drifts down toward it, exactly as one less
    accepted drifts up.

    Both arguments are plain integers. `support_bps` comes from
    `PoliticalState.constitutional_order_support_bps`, which is scenario-authored; it is never
    computed from the constitution's axes, and this function has no way to see them.
    """
    return trunc_div_toward_zero(
        (support_bps - opening_legitimacy_bps) * DRIFT_RATE_BPS, BPS_DENOMINATOR
    )


def resolve_legitimacy(
    *, opening_bps: int, order_support_contribution: int, performance_contribution: int
) -> tuple[int, int]:
    """Apply both contributions to opening legitimacy.

    Returns `(applied_total_change_bps, closing_legitimacy_bps)`. The *applied* change is reported,
    not the requested one: when the scale bound bites, `closing - opening` is what actually
    happened, and the report re-derives exactly that rather than storing a "was clamped" flag
    nobody can verify.
    """
    requested = order_support_contribution + performance_contribution
    capped = clamp_bps(
        requested,
        low=-MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
        high=MAX_TOTAL_LEGITIMACY_CHANGE_BPS,
    )
    closing = clamp_bps(opening_bps + capped, low=LEGITIMACY_MIN_BPS, high=LEGITIMACY_MAX_BPS)
    return closing - opening_bps, closing


def political_capital_regeneration(*, legitimacy_bps: int) -> PoliticalCapital:
    """Political capital recovered this turn: a base amount plus a legitimacy-scaled bonus.

    A widely-accepted government spends less of its governing effort compelling baseline
    compliance and can direct more at initiatives; a government whose authority is contested burns
    capacity holding position. Scales with legitimacy only — never with government form.
    """
    return POLITICAL_CAPITAL_BASE_REGENERATION + trunc_div_toward_zero(
        legitimacy_bps * LEGITIMACY_REGENERATION_COEFFICIENT, BPS_DENOMINATOR
    )


def resolve_political_capital(
    *, opening: PoliticalCapital, capacity: PoliticalCapital, legitimacy_bps: int, spent: int
) -> tuple[PoliticalCapital, PoliticalCapital]:
    """Returns `(regeneration, closing)` for this turn's political capital.

    `closing = min(capacity, opening + regeneration - spent)`. The `min` is the only clamp.
    `spent` is always `0` in Phase 3A — nothing consumes political capital yet, because passing
    laws needs a legislature with members, negotiating factions needs factions, and reforms need a
    reform system, all of which are Phase 3B/3C. The parameter exists so the identity shipped now
    is already the final one and 3B changes a value rather than reopening the equation.

    A scenario authoring `opening > capacity` is **rejected** by `simulation.invariants` before
    resolution rather than silently clamped here — repairing invalid authored content is exactly
    what this codebase's reject-not-normalize rule forbids.
    """
    if spent < 0:
        raise ValueError(f"political capital spent must be nonnegative, got {spent}")
    regeneration = political_capital_regeneration(legitimacy_bps=legitimacy_bps)
    available = opening + regeneration - spent
    if available < 0:
        raise ValueError(
            f"political capital spent={spent} exceeds opening={opening} plus "
            f"regeneration={regeneration}"
        )
    return regeneration, min(capacity, available)
