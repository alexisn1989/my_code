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
from app.core.politics import (
    StrictLegitimacyBps,
    StrictPoliticalCapital,
    StrictPoliticalCapitalCapacity,
)
from app.core.quantity import (
    StrictRealOutput,
    StrictRealOutputPerResourceUnit,
    StrictRealOutputPerWorker,
    StrictResourceQuantity,
    StrictResourceQuantityPerWorker,
)
from app.simulation.constitution import ConstitutionState

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
    """One aggregate sector's production inputs, plus its structural tax-base decomposition
    shares (Phase 2B2).

    As of Phase 2B3, `employed_workers` no longer exists here: employment is fully derived
    every turn by `simulation.labor_allocation` from `EconomyState.effective_labor_force_share_bps`
    and each sector's labor demand, exactly mirroring why `GovernmentFinanceState.tax_bases` was
    removed in Phase 2B2 — a value that is always recomputed from other state should not also be
    stored, or it can drift from its own derivation. `capacity_utilization_bps` and constraint
    classification remain NOT stored here either — both live exclusively in `ProductionReport`.

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
    value_added_share_bps: StrictBps
    labor_income_share_bps: StrictBps


class ResourceCategory(StrEnum):
    """The eight physical natural resources modeled in Phase 2C1.

    Declaration order here is the canonical resource ordering used by `EconomyState`'s
    completeness validator and by `ResourceExtractionReport.deposits` (`report.py`) — changing
    this order is a ruleset-affecting change, not a cosmetic one, exactly like `SectorCategory`
    above. Unlike `SectorCategory`'s and every other canonical-order validator in this codebase,
    the resource-facing validators **reject** noncanonical order rather than silently normalizing
    it — see `ResourceDepositState`'s sibling validator on `EconomyState` below and
    `docs/adr/0007-resource-endowments-and-extraction.md` for why.
    """

    TIMBER = "timber"
    IRON_ORE = "iron_ore"
    COAL = "coal"
    CRUDE_OIL = "crude_oil"
    NATURAL_GAS = "natural_gas"
    URANIUM = "uranium"
    COPPER = "copper"
    CRITICAL_MINERALS = "critical_minerals"


RENEWABLE_RESOURCES: frozenset[ResourceCategory] = frozenset({ResourceCategory.TIMBER})
"""The only renewable resource this phase — everything else is a finite, nonrenewable reserve
that only ever depletes. Determines which `ResourceDepositState`/`ResourceDepositReport` fields
(`regeneration_per_turn`, `stock_ceiling`) are legal to be nonzero/non-`None`.
"""

RESOURCE_UNITS: dict[ResourceCategory, str] = {
    ResourceCategory.TIMBER: "m³",
    ResourceCategory.IRON_ORE: "t",
    ResourceCategory.COAL: "t",
    ResourceCategory.CRUDE_OIL: "bbl",
    ResourceCategory.NATURAL_GAS: "thousand m³",
    ResourceCategory.URANIUM: "t",
    ResourceCategory.COPPER: "t",
    ResourceCategory.CRITICAL_MINERALS: "t",
}
"""A physical unit is a fixed property of the category, not authored per-deposit state — a
per-deposit unit string would be a redundant, driftable value, exactly what Phase 2B2/2B3 removed
from tax bases and employment. Used by the CLI for display only; never affects arithmetic."""


class ResourceDepositState(BaseModel):
    """One country's physical endowment of one `ResourceCategory` (Phase 2C1).

    `remaining_stock` is the only field this phase's turn resolution ever mutates — and it does
    so exactly once per turn, inside `resolve_production_and_trade` (phase 3), immediately after
    `simulation.resource_extraction` computes that turn's extraction — never inside phase 5,
    which historically owned "closing" mutations for treasury cash/debt. See
    `docs/adr/0007-resource-endowments-and-extraction.md` for why extraction and its depletion
    are one domain operation performed together, and what that means for phase 3's previously
    mutation-free contract.

    `output_per_worker` is strictly positive for the same reason `SectorState`'s is: "no
    extraction" is expressed only via zero allocated workers or zero remaining stock, never by
    also allowing this to be zero — one way to model idle, not two redundant ones.

    `regeneration_per_turn`/`stock_ceiling` are legal to be nonzero/non-`None` if and only if
    `category in RENEWABLE_RESOURCES` — enforced by the two validators below, which **raise**
    rather than silently correcting a miscategorized deposit.
    """

    model_config = _STRICT_CONFIG

    category: ResourceCategory
    remaining_stock: StrictResourceQuantity
    extraction_capacity_per_turn: StrictResourceQuantity
    output_per_worker: StrictResourceQuantityPerWorker
    regeneration_per_turn: StrictResourceQuantity = 0
    stock_ceiling: StrictResourceQuantity | None = None

    @model_validator(mode="after")
    def _nonrenewables_have_no_regeneration_or_ceiling(self) -> ResourceDepositState:
        if self.category not in RENEWABLE_RESOURCES:
            if self.regeneration_per_turn != 0:
                raise ValueError(
                    f"{self.category.value} is nonrenewable but has "
                    f"regeneration_per_turn={self.regeneration_per_turn}; nonrenewables must "
                    "have regeneration_per_turn == 0"
                )
            if self.stock_ceiling is not None:
                raise ValueError(
                    f"{self.category.value} is nonrenewable but has "
                    f"stock_ceiling={self.stock_ceiling}; nonrenewables must have "
                    "stock_ceiling == None"
                )
        return self

    @model_validator(mode="after")
    def _renewables_have_a_ceiling_not_below_stock(self) -> ResourceDepositState:
        if self.category in RENEWABLE_RESOURCES:
            if self.stock_ceiling is None:
                raise ValueError(
                    f"{self.category.value} is renewable but has stock_ceiling=None; "
                    "renewables must declare a stock_ceiling"
                )
            if self.stock_ceiling < self.remaining_stock:
                raise ValueError(
                    f"{self.category.value} has stock_ceiling={self.stock_ceiling} below its "
                    f"own remaining_stock={self.remaining_stock}"
                )
        return self


class ResourceOutputCoefficient(BaseModel):
    """How much fixed-base-year `RealOutput` one physical unit of one `ResourceCategory`
    embodies (Phase 2C2) — the scenario-authored input to
    `simulation.resource_output.compute_resource_output_contributions`, which multiplies it by
    that turn's extracted (and separately, potential) quantity via the single named
    `core.quantity.extracted_resource_to_real_output` bridge. Never zero (`gt=0`,
    `StrictRealOutputPerResourceUnit`): "zero contribution because nothing was extracted" (legal)
    must stay cleanly distinct from "zero contribution despite extraction" (impossible by type) —
    see `docs/adr/0008-physical-extraction-derived-sector-output.md`.

    Persisted on `EconomyState`, not a bare mapping, so it travels with the rest of scenario-
    authored economy state through `state_json`/the history hash chain exactly like
    `resource_deposits` does — never re-read from scenario YAML after `new`.
    """

    model_config = _STRICT_CONFIG

    category: ResourceCategory
    real_output_per_unit: StrictRealOutputPerResourceUnit


class EconomyState(BaseModel):
    """A country's Phase-2B1 production state: exactly one `SectorState` per `SectorCategory`,
    plus (Phase 2B3) the reduced-form labor-supply coefficient that feeds those sectors, plus
    (Phase 2C1) exactly one `ResourceDepositState` per `ResourceCategory`, plus (Phase 2C2)
    exactly one `ResourceOutputCoefficient` per `ResourceCategory`.

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

    `effective_labor_force_share_bps` (Phase 2B3) is a deliberate reduced-form placeholder —
    it currently conflates working-age share, labor-force participation, and any other
    structural availability factor into one coefficient, the same kind of temporary
    simplification `TaxBaseCoefficients.effective_consumption_base_share_bps` already is (see
    ADR 0005 R4). It lives here, alongside the sectors it feeds, rather than on
    `CountryState` directly — `CountryState.population` stays the single authoritative
    population source; this coefficient only says what *share* of it is economically active.

    `resource_deposits` (Phase 2C1) covers all eight `ResourceCategory` members exactly once,
    zero-stock/zero-capacity entries legal (a resource-poor country still declares every
    category, just at zero — the same "no ambiguous missing-vs-zero concept" reasoning
    `sectors` already follows). Grouped here, not on `CountryState` directly, because deposits
    are worked by the same extraction sector's labor this economy already allocates.

    `resource_output_coefficients` (Phase 2C2) covers all eight `ResourceCategory` members
    exactly once, canonical order, **rejected not normalized** on reorder — following the
    `resource_deposits` precedent (R3, not the `sectors` normalize-on-reorder one), since this is
    a second resource-facing tuple. Read-only after construction: no decision in this phase
    mutates it, and it is a genuine schema addition (old-ruleset saves have none), not a
    per-scenario "content-value fingerprint" — different scenarios routinely carry different
    coefficients under the same `content_version`, exactly like they already carry different
    `resource_deposits`/`sectors` values (see `docs/adr/0008-physical-extraction-derived-sector-output.md`,
    "Content-version policy").
    """

    model_config = _STRICT_CONFIG

    effective_labor_force_share_bps: StrictBps
    sectors: tuple[SectorState, ...]
    resource_deposits: tuple[ResourceDepositState, ...]
    resource_output_coefficients: tuple[ResourceOutputCoefficient, ...]

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

    @model_validator(mode="after")
    def _deposits_cover_all_categories_exactly_once_in_canonical_order(self) -> EconomyState:
        """Diverges from `_sectors_cover_all_categories_exactly_once_in_canonical_order` above on
        purpose (R3 — see `docs/adr/0007-resource-endowments-and-extraction.md`): duplicates and
        missing categories still raise, but noncanonical order also **raises** here rather than
        being silently reassigned to canonical order. Deterministic canonical serialization
        should be a property proven of valid input, not a repair silently applied to invalid
        input — a rule not applied retroactively to `sectors` above, which keeps its established
        normalize-on-reorder behavior unchanged.
        """
        seen: set[ResourceCategory] = set()
        for deposit in self.resource_deposits:
            if deposit.category in seen:
                raise ValueError(f"duplicate resource category: {deposit.category.value!r}")
            seen.add(deposit.category)
        missing = [c for c in ResourceCategory if c not in seen]
        if missing:
            raise ValueError(
                "economy is missing resource categories: "
                f"{[c.value for c in missing]!r} — all {len(ResourceCategory)} are required"
            )
        by_category = {deposit.category: deposit for deposit in self.resource_deposits}
        canonical_order = tuple(by_category[category] for category in ResourceCategory)
        if canonical_order != self.resource_deposits:
            got = [d.category.value for d in self.resource_deposits]
            expected = [c.value for c in ResourceCategory]
            raise ValueError(
                "resource_deposits are not in canonical ResourceCategory order: "
                f"got {got!r}, expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _output_coefficients_cover_all_categories_exactly_once_in_canonical_order(
        self,
    ) -> EconomyState:
        """Structurally identical to `_deposits_cover_all_categories_exactly_once_in_canonical_order`
        above (Phase 2C2) — a second, independent resource-facing tuple that follows the same
        reject-not-normalize-on-reorder policy (R3)."""
        seen: set[ResourceCategory] = set()
        for coefficient in self.resource_output_coefficients:
            if coefficient.category in seen:
                raise ValueError(
                    f"duplicate resource output coefficient category: {coefficient.category.value!r}"
                )
            seen.add(coefficient.category)
        missing = [c for c in ResourceCategory if c not in seen]
        if missing:
            raise ValueError(
                "economy is missing resource output coefficient categories: "
                f"{[c.value for c in missing]!r} — all {len(ResourceCategory)} are required"
            )
        by_category = {
            coefficient.category: coefficient for coefficient in self.resource_output_coefficients
        }
        canonical_order = tuple(by_category[category] for category in ResourceCategory)
        if canonical_order != self.resource_output_coefficients:
            got = [c.category.value for c in self.resource_output_coefficients]
            expected = [c.value for c in ResourceCategory]
            raise ValueError(
                "resource_output_coefficients are not in canonical ResourceCategory order: "
                f"got {got!r}, expected {expected!r}"
            )
        return self


class EconomicBaselineState(BaseModel):
    """The economic observations of one specific resolved turn, persisted so the next turn's
    political phase can compute a change without reading history (Phase 3A, §6.4).

    Written by the political phase from that same turn's own reports; never scenario-authored, and
    nothing else reads or writes it. `source_turn` is `state.turn` of the state that carries this
    baseline — the closing baseline written on resolving turn *N* has `source_turn == N`, and the
    following turn reads it back as its opening baseline. `simulation.invariants` checks this
    relationship (`economic_baseline_turn_mismatch`); `simulation.legitimacy` never sees this type
    at all — it takes and returns plain integers, per `PerformanceSignals`.
    """

    model_config = _STRICT_CONFIG

    source_turn: int = Field(ge=0)
    total_gross_output: StrictRealOutput
    unemployment_rate_bps: StrictBps


class PoliticalState(BaseModel):
    """A country's constitutional order, its current legitimacy, and its political capital
    (Phase 3A, §4.3).

    **`constitutional_order_support_bps` is scenario-authored, never derived from `constitution`'s
    axes.** This is the load-bearing guarantee behind R1: the engine has no legitimacy-anchor table
    keyed on government form. A monarchy may be authored at 8,500 and a democracy at 2,000, or the
    reverse — both are equally valid, and both drift toward their own authored value at the same
    rate (`simulation.legitimacy.DRIFT_RATE_BPS`). Static in Phase 3A (nothing in this phase mutates
    it or `constitution`, proven by `simulation.reconciliation`); Phase 3B/3C amendments and coups
    may move it.

    `economic_baseline` is `None` at scenario authoring and before the first resolution; the
    political phase sets it at the end of every resolved turn (§6.4). `None` is legal *only* at
    `state.turn == 0` — `simulation.invariants` enforces both directions
    (`economic_baseline_present_at_genesis`, `economic_baseline_missing_after_genesis`).
    """

    model_config = _STRICT_CONFIG

    constitution: ConstitutionState
    constitutional_order_support_bps: StrictLegitimacyBps
    legitimacy_bps: StrictLegitimacyBps
    political_capital: StrictPoliticalCapital
    political_capital_capacity: StrictPoliticalCapitalCapacity
    economic_baseline: EconomicBaselineState | None = None


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
    politics: PoliticalState | None = None
    """Optional like `finance`/`economy`: AI countries may omit it — Phase 3A cannot resolve
    politics for a country with no economy to derive performance from
    (`non_player_politics_not_supported`). Required for the player, enforced by
    `player_politics_required`, mirroring `player_finance_required`/`player_economy_required`."""


class WorldState(BaseModel):
    """All countries in the game world, plus which one the player controls."""

    model_config = _STRICT_CONFIG

    countries: dict[str, CountryState] = Field(default_factory=dict)
    player_country_id: str


RULESET_VERSION = "0.8.0"
"""The current simulation ruleset version, stamped onto every newly created `GameState`
(see `simulation.scenario._to_game_state`) — never authored in scenario content. A scenario
declaring its own ruleset version would let content decide which engine rules it runs under;
instead the *engine* declares what ruleset it implements, and `save_format.SUPPORTED_RULESET_VERSIONS`
gates which values are accepted when loading a save. Bump this when turn-resolution *behavior*
changes (which phases do real work, what formulas they use) in a way that must not silently
apply to already-resolved history — see `docs/adr/0002-snapshot-history-and-versioning.md`,
`docs/adr/0003-government-accounting.md`, `docs/adr/0004-sector-production-fixed-prices.md`,
`docs/adr/0005-production-derived-tax-bases.md`,
`docs/adr/0006-labor-allocation-at-fixed-prices.md`,
`docs/adr/0007-resource-endowments-and-extraction.md` (bumped `"0.5.0" -> "0.6.0"` for Phase 2C1:
`EconomyState.resource_deposits` becomes a new required field with no data to backfill from an
older save — the same kind of change that justified every prior ruleset bump), and
`docs/adr/0009-constitutional-foundation-legitimacy-political-capital.md` (bumped `"0.7.0" ->
"0.8.0"` for Phase 3A: `CountryState.politics` becomes a new required field for the player, with
no constitution, authored order support, legitimacy or political capital to backfill from an
older save).
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
