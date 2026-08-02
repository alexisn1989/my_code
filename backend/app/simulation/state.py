"""Typed domain state for MANDATE.

This is the minimal Phase-1 slice of the ~29 state classes described in the
product spec (§8): enough to represent a country with population groups,
institutions, and a treasury, nest it in a world, and drive a turn resolution.
The remaining classes (`GovernmentState`, `MilitaryState`, `DiplomaticRelationState`,
etc.) are added in the phase that gives them behavior (see `docs/roadmap.md`)
rather than stubbed out empty here.

All models are Pydantic `BaseModel`s with `extra="forbid"` so malformed
scenario/save data fails loudly, and `validate_assignment=True` so in-place
mutation during turn resolution re-checks field-level constraints (value
ranges, non-negativity) as well as construction. Cross-field invariants (e.g.
population-group shares summing to 1.0) are *not* expressible as per-field
constraints and are checked separately by `simulation.invariants`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money, StrictBps, StrictMoney

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)


class PopulationGroupState(BaseModel):
    """One politically-relevant population segment within a country.

    Segments are exclusive in this initial implementation (§3.3): every
    resident belongs to exactly one group, so `population_share` values
    across a country's groups must sum to 1.0 within `invariants.GROUP_SHARE_TOLERANCE`.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    population_share: float = Field(ge=0.0, le=1.0)
    political_influence: float = Field(ge=0.0, le=100.0, default=50.0)
    approval: float = Field(ge=0.0, le=100.0, default=50.0)
    trust: float = Field(ge=0.0, le=100.0, default=50.0)
    organization: float = Field(ge=0.0, le=100.0, default=20.0)
    radicalization: float = Field(ge=0.0, le=100.0, default=0.0)


class InstitutionState(BaseModel):
    """An independent power center distinct from population groups (§3.4)."""

    model_config = _STRICT_CONFIG

    id: str
    name: str
    loyalty: float = Field(ge=0.0, le=100.0, default=50.0)
    power: float = Field(ge=0.0, le=100.0, default=50.0)
    competence: float = Field(ge=0.0, le=100.0, default=50.0)
    corruption: float = Field(ge=0.0, le=100.0, default=10.0)


class TreasuryState(BaseModel):
    """A country's central financial account, in exact minor-unit `Money`."""

    model_config = _STRICT_CONFIG

    cash_on_hand: StrictMoney
    debt: StrictMoney


class SpendingCategory(StrEnum):
    """The seven government spending categories modeled in Phase 2A (product spec §13).

    Shared between `SpendingPlanState` (field names match these values exactly)
    and `simulation.decisions.SpendingUpdate` (a player's budget target for one
    category) — one enum, not two parallel category lists that could drift.
    """

    HEALTH = "health"
    EDUCATION = "education"
    WELFARE = "welfare"
    INFRASTRUCTURE = "infrastructure"
    DEFENSE = "defense"
    SECURITY = "security"
    ADMINISTRATION = "administration"


class TaxBaseState(BaseModel):
    """Fixed-for-Phase-2A taxable bases (product spec §13, "Government Finance").

    **Limitation, stated prominently per the ticket:** changing a tax *rate* in
    2A does not change these *bases*. Real economic feedback (a higher
    consumption-tax rate suppressing taxable consumption, income tax affecting
    labor supply, etc.) is Phase 2B+ production-sector work. These are static
    scenario-authored numbers that revenue is computed against, not a live
    economic model.
    """

    model_config = _STRICT_CONFIG

    personal_income: StrictMoney
    corporate_profit: StrictMoney
    taxable_consumption: StrictMoney


class TaxPolicyState(BaseModel):
    """Currently active tax rates and compliance, all in basis points (0-10,000 = 0%-100%)."""

    model_config = _STRICT_CONFIG

    personal_income_rate_bps: StrictBps
    corporate_rate_bps: StrictBps
    consumption_rate_bps: StrictBps
    compliance_rate_bps: StrictBps


class SpendingPlanState(BaseModel):
    """Currently active government spending, one field per `SpendingCategory`.

    No defaults: a government finance state must explicitly specify every
    category rather than silently defaulting unset ones to zero, which could
    misrepresent what a scenario or a player's budget actually funds.
    """

    model_config = _STRICT_CONFIG

    health: StrictMoney
    education: StrictMoney
    welfare: StrictMoney
    infrastructure: StrictMoney
    defense: StrictMoney
    security: StrictMoney
    administration: StrictMoney

    def total(self) -> Money:
        return (
            self.health
            + self.education
            + self.welfare
            + self.infrastructure
            + self.defense
            + self.security
            + self.administration
        )

    def get(self, category: SpendingCategory) -> Money:
        return int(getattr(self, category.value))

    def with_update(self, category: SpendingCategory, amount: Money) -> SpendingPlanState:
        """A copy with one category's amount replaced. Does not mutate `self`."""
        return self.model_copy(update={category.value: amount})


class GovernmentFinanceState(BaseModel):
    """A country's Phase-2A government accounting state: bases, policy, spending, and the
    interest rate paid on public debt. Optional on `CountryState` — required for the player
    country (`simulation.invariants` enforces this), unused and freely omittable for AI
    countries until Phase 6 gives them budget decisions of their own.
    """

    model_config = _STRICT_CONFIG

    tax_bases: TaxBaseState
    tax_policy: TaxPolicyState
    spending_plan: SpendingPlanState
    annual_debt_interest_rate_bps: StrictBps


class CountryState(BaseModel):
    """A single country: player-controlled or AI-controlled.

    `population` is the total headcount; `population_groups` partitions it.
    Reconciliation between the two (within tolerance) is a cross-field
    invariant, checked by `simulation.invariants.check_invariants`.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    population: int = Field(ge=0)
    population_groups: list[PopulationGroupState] = Field(default_factory=list)
    institutions: list[InstitutionState] = Field(default_factory=list)
    treasury: TreasuryState
    finance: GovernmentFinanceState | None = None


class WorldState(BaseModel):
    """All countries in the game world, plus which one the player controls."""

    model_config = _STRICT_CONFIG

    countries: dict[str, CountryState] = Field(default_factory=dict)
    player_country_id: str


RULESET_VERSION = "0.2.0"
"""The current simulation ruleset version, stamped onto every newly created `GameState`
(see `simulation.scenario._to_game_state`) — never authored in scenario content. A scenario
declaring its own ruleset version would let content decide which engine rules it runs under;
instead the *engine* declares what ruleset it implements, and `save_format.SUPPORTED_RULESET_VERSIONS`
gates which values are accepted when loading a save. Bump this when turn-resolution *behavior*
changes (which phases do real work, what formulas they use) in a way that must not silently
apply to already-resolved history — see `docs/adr/0002-snapshot-history-and-versioning.md` and
`docs/adr/0003-government-accounting.md`.
"""


class GameState(BaseModel):
    """The complete, serializable state of one game.

    `turn` and `state_version` both start at 0 and are advanced together by
    exactly 1 on every successful `resolve_turn` call (see `resolver.py`);
    they are tracked as separate fields because later phases may need to bump
    `state_version` independently of `turn` (e.g. a manual correction),
    matching the optimistic-concurrency use described in the product spec
    (§30, "include the current turn number or state version in mutation
    requests and reject stale submissions").
    """

    model_config = _STRICT_CONFIG

    schema_version: int = 1
    ruleset_version: str
    content_version: str
    seed: int
    turn: int = Field(ge=0, default=0)
    state_version: int = Field(ge=0, default=0)
    world: WorldState
