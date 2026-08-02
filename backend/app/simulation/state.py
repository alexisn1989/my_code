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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import Money, StrictBps, StrictMoney
from app.core.quantity import StrictRealOutput, StrictRealOutputPerWorker, StrictWorkerCount

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
    """Taxable bases that tax revenue is computed against (product spec §13, "Government
    Finance"). The model itself is unchanged since Phase 2A — `simulation.accounting.
    compute_tax_revenue` still takes exactly this shape — but as of Phase 2B2 it is no longer
    scenario-authored state. It is now a **derived, turn-local** value: `TaxBaseDerivationReport
    .derived_tax_bases` (`report.py`), computed fresh every turn by
    `simulation.tax_base_derivation` from the player's current `EconomyState` and
    `GovernmentFinanceState.tax_base_coefficients`. Changing a tax *rate* still does not change
    these *bases* directly — only changing production (or the coefficients) does; see
    `docs/economy_methodology.md`.
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


class TaxBaseCoefficients(BaseModel):
    """Country-level fiscal-reach coefficients (Phase 2B2) that turn per-sector modeled value
    added / labor income / operating surplus into national tax bases. Country-level, not
    per-sector (unlike `SectorState.value_added_share_bps`/`labor_income_share_bps`), because
    these describe how much of the economy the tax system reaches — a property of fiscal
    policy, not of any one industry.

    `effective_consumption_base_share_bps` is a reduced-form placeholder: it currently
    conflates household final-demand composition, government-vs-private consumption,
    exports/other non-domestic demand, and exemptions/fiscal coverage into one coefficient,
    because Phase 2B2 does not yet model final demand or trade separately. See
    `docs/economy_methodology.md` and `docs/adr/0005-production-derived-tax-bases.md` for why
    this is temporary and what a later phase should split it into.
    """

    model_config = _STRICT_CONFIG

    personal_taxable_share_bps: StrictBps
    corporate_taxable_share_bps: StrictBps
    effective_consumption_base_share_bps: StrictBps


class GovernmentFinanceState(BaseModel):
    """A country's government accounting state: fiscal coefficients, policy, spending, and the
    interest rate paid on public debt. Optional on `CountryState` — required for the player
    country (`simulation.invariants` enforces this), unused and freely omittable for AI
    countries until Phase 6 gives them budget decisions of their own.

    As of Phase 2B2, tax bases are no longer authored here — `TaxBaseCoefficients` plus the
    player's current-turn `EconomyState` are what `simulation.tax_base_derivation` uses to
    derive them fresh every turn. There is no "opening"/"closing" tax-base concept anymore,
    only "applied this turn" (see `TaxBaseDerivationReport` in `report.py`).
    """

    model_config = _STRICT_CONFIG

    tax_base_coefficients: TaxBaseCoefficients
    tax_policy: TaxPolicyState
    spending_plan: SpendingPlanState
    annual_debt_interest_rate_bps: StrictBps


class SectorCategory(StrEnum):
    """The eleven aggregate economic sectors modeled in Phase 2B1 (product spec §13).

    Declaration order here is the canonical sector ordering used by
    `EconomyState`'s normalization validator and by `ProductionReport.sectors`
    (see both) — changing this order is a ruleset-affecting change, not a
    cosmetic one, since it would change canonical JSON and every `entry_hash`
    computed over an `EconomyState`/`ProductionReport`.
    """

    AGRICULTURE = "agriculture"
    EXTRACTION = "extraction"
    MANUFACTURING = "manufacturing"
    CONSTRUCTION = "construction"
    ENERGY = "energy"
    TRANSPORTATION = "transportation"
    CONSUMER_SERVICES = "consumer_services"
    FINANCE_AND_PROFESSIONAL_SERVICES = "finance_and_professional_services"
    TECHNOLOGY = "technology"
    DEFENSE_INDUSTRY = "defense_industry"
    PUBLIC_SERVICES = "public_services"


class SectorState(BaseModel):
    """One aggregate sector's production inputs, plus (Phase 2B2) its structural tax-base
    decomposition shares.

    Deliberately mutable (no `frozen=True`): `employed_workers` is expected to
    become player/AI-adjustable in a later economy phase. `capacity_utilization_bps`
    and constraint classification are NOT stored here — they are always
    derived from these inputs and live exclusively in `ProductionReport`, so
    there is never a stored value that could disagree with its own formula.

    `value_added_share_bps`/`labor_income_share_bps` are per-sector (not country-level)
    because they are genuinely structural — how much of a sector's gross output survives
    as modeled value added, and how much of that is labor income vs. operating surplus,
    differs meaningfully by industry (extraction vs. professional services, for instance).
    See `simulation.tax_base_derivation` and `docs/economy_methodology.md`.
    """

    model_config = _STRICT_CONFIG

    category: SectorCategory
    quarterly_capacity_output: StrictRealOutput
    output_per_worker: StrictRealOutputPerWorker
    employed_workers: StrictWorkerCount
    value_added_share_bps: StrictBps
    labor_income_share_bps: StrictBps


class EconomyState(BaseModel):
    """A country's Phase-2B1 production state: exactly one `SectorState` per `SectorCategory`.

    All eleven categories must be present, exactly once — a zero-capacity
    sector is a legitimate ("inactive") input, but an absent one is not,
    since that would introduce a second, ambiguous "missing vs. zero" concept
    alongside sector classification (see `docs/economy_methodology.md`).

    This validator runs at construction time only. Because `SectorState` is
    mutable, a later in-place assignment to a nested `sector.category` can
    still desynchronize an already-constructed `EconomyState` from this
    invariant — that risk is *not* fully closed here, and is independently
    re-checked every turn by `simulation.invariants.check_invariants`
    (`economy_sectors_valid`), not just at parse time.
    """

    model_config = _STRICT_CONFIG

    sectors: tuple[SectorState, ...]

    @model_validator(mode="after")
    def _sectors_cover_all_categories_exactly_once_in_canonical_order(self) -> EconomyState:
        seen: set[SectorCategory] = set()
        for sector in self.sectors:
            if sector.category in seen:
                raise ValueError(f"duplicate sector category: {sector.category.value!r}")
            seen.add(sector.category)
        missing = [c for c in SectorCategory if c not in seen]
        if missing:
            raise ValueError(
                "economy is missing sector categories: "
                f"{[c.value for c in missing]!r} — all {len(SectorCategory)} are required"
            )
        by_category = {sector.category: sector for sector in self.sectors}
        canonical_order = tuple(by_category[category] for category in SectorCategory)
        if canonical_order != self.sectors:
            self.sectors = canonical_order
        return self


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
    economy: EconomyState | None = None


class WorldState(BaseModel):
    """All countries in the game world, plus which one the player controls."""

    model_config = _STRICT_CONFIG

    countries: dict[str, CountryState] = Field(default_factory=dict)
    player_country_id: str


RULESET_VERSION = "0.4.0"
"""The current simulation ruleset version, stamped onto every newly created `GameState`
(see `simulation.scenario._to_game_state`) — never authored in scenario content. A scenario
declaring its own ruleset version would let content decide which engine rules it runs under;
instead the *engine* declares what ruleset it implements, and `save_format.SUPPORTED_RULESET_VERSIONS`
gates which values are accepted when loading a save. Bump this when turn-resolution *behavior*
changes (which phases do real work, what formulas they use) in a way that must not silently
apply to already-resolved history — see `docs/adr/0002-snapshot-history-and-versioning.md`,
`docs/adr/0003-government-accounting.md`, `docs/adr/0004-sector-production-fixed-prices.md`, and
`docs/adr/0005-production-derived-tax-bases.md` (bumped `"0.3.0" -> "0.4.0"` for Phase 2B2:
`GovernmentFinanceState.tax_bases` is removed in favor of required `tax_base_coefficients` and
each `SectorState` gains required `value_added_share_bps`/`labor_income_share_bps` — a required
state-shape change in both directions with no data to migrate an older save from, the same kind
of change that justified every prior ruleset bump).
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
