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
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.money import Money, StrictBps, StrictMoney
from app.core.politics import (
    StrictInstitutionMetricBps,
    StrictLegitimacyBps,
    StrictPoliticalCapital,
    StrictPoliticalCapitalCapacity,
    StrictPopulationMetricBps,
    StrictPositiveSeatCount,
    StrictPreferenceBps,
    StrictRelationshipBps,
    StrictSeatCount,
    StrictTermsHeld,
    StrictTransitionPressureBps,
)
from app.core.quantity import (
    StrictRealOutput,
    StrictRealOutputPerResourceUnit,
    StrictRealOutputPerWorker,
    StrictResourceQuantity,
    StrictResourceQuantityPerWorker,
)
from app.simulation.constitution import ConstitutionState, Legislature
from app.simulation.foreign_conflict import TERMINAL_STATUSES, ConflictStatus, WarAim
from app.simulation.geography import (
    ROUTE_DUPLICATE,
    ROUTE_NOT_CANONICAL,
    ROUTE_SELF_EDGE,
    SHAPE_ID_DUPLICATE,
    SHAPE_NOT_CANONICAL,
    SHAPE_POLYGON_CLOSING_VERTEX_REPEATED,
    SHAPE_POLYGON_REPEATS_VERTEX,
    SHAPE_POLYGON_ZERO_AREA,
    LabelAnchor,
    RouteKind,
    StrictDisplayName,
    StrictGridCoord,
    StrictMapId,
    TheaterKind,
    shoelace_doubled_area,
)
from app.simulation.legislature import GovernmentRole, LegislativeChamber

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)


class PopulationGroupState(BaseModel):
    """One politically-relevant population segment within a country.

    Segments are exclusive in this initial implementation (§3.3): every
    resident belongs to exactly one group, so `population_share` values
    across a country's groups must sum to 1.0 within `invariants.GROUP_SHARE_TOLERANCE`.

    **Phase 3C (R8):** `political_influence`/`approval`/`trust`/`organization`/`radicalization`
    convert from Phase-1 floats (0.0-100.0) to strict basis points (0-10,000) in this phase —
    the first phase to read any of them by a real formula
    (`simulation.government_survival`'s popular-unrest channel). `population_share` stays a plain
    float in `[0, 1]`: it is a proportion, not one of the five converted metrics.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    population_share: float = Field(ge=0.0, le=1.0)
    political_influence: StrictPopulationMetricBps = 5_000
    approval: StrictPopulationMetricBps = 5_000
    trust: StrictPopulationMetricBps = 5_000
    organization: StrictPopulationMetricBps = 2_000
    radicalization: StrictPopulationMetricBps = 0


class InstitutionState(BaseModel):
    """An independent power center distinct from population groups (§3.4).

    **Phase 3C (R8):** `loyalty`/`power`/`competence`/`corruption` convert from Phase-1 floats
    (0.0-100.0) to strict basis points (0-10,000) in this phase — the first phase to read any of
    them by a real formula (`simulation.government_survival`'s coup channel). Converted in the same
    commit as `PopulationGroupState`'s metrics, not bridged from floats: this phase is the first
    real formula consumer of both models, and a permanent float-to-bps bridge would be exactly the
    kind of unconverted-precision debt this codebase's discipline forbids building on top of.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    loyalty: StrictInstitutionMetricBps = 5_000
    power: StrictInstitutionMetricBps = 5_000
    competence: StrictInstitutionMetricBps = 5_000
    corruption: StrictInstitutionMetricBps = 1_000


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


class BlocSeats(BaseModel):
    """How many seats one bloc holds in one chamber.

    Zero is legal and meaningful: a caucus may be absent from the upper house and still be a
    caucus. A bloc simply omits the chambers it holds nothing in, so an explicit zero and an
    omission mean the same thing — both are permitted rather than one being canonicalised, because
    an author writing `seats: 0` is saying something true.
    """

    model_config = _STRICT_CONFIG

    chamber: LegislativeChamber
    seats: StrictSeatCount


class LegislativeBlocState(BaseModel):
    """An internal caucus of a party — the unit that actually votes.

    **Blocs, not parties, carry `government_relationship_bps`.** A rebel caucus inside a governing
    party is the interesting case in every real legislature, and party-level-only loyalty would
    make it unrepresentable. The party keeps its *formal* role; the bloc keeps how it actually
    feels.

    `discipline_bps` is how tightly the caucus votes together, and amplifies whichever way it
    already leans (`simulation.legislative_voting`). The two preference fields are directional:
    negative prefers a decrease, positive an increase, zero indifferent — deliberately separate
    from the relationship, because a bloc can be devoted to a government and still hate its
    budget.

    **`baseline_government_relationship_bps` (Phase 3B2B) is the bloc's authored, structural
    disposition toward the government — a political FACT about who these people are, not a
    running total.** `government_relationship_bps` decays toward THIS every turn
    (`simulation.political_memory.relationship_decay_bps`), never toward zero. It is authored
    independently of `government_relationship_bps` — never derived from it, from
    `government_role`, or from any constitutional axis — and is static: nothing in Phase 3B2B
    moves it, and `simulation.reconciliation` proves so (group 12). A scenario author sets both
    fields explicitly; setting them equal (the only choice all three shipped scenarios make) means
    the bloc opens with zero deviation and decay is a no-op until something moves it.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    seats: tuple[BlocSeats, ...] = Field(default_factory=tuple)
    discipline_bps: StrictBps
    government_relationship_bps: StrictRelationshipBps
    baseline_government_relationship_bps: StrictRelationshipBps
    tax_preference_bps: StrictPreferenceBps
    spending_preference_bps: StrictPreferenceBps

    @model_validator(mode="after")
    def _seats_are_unique_and_in_canonical_chamber_order(self) -> LegislativeBlocState:
        """Follows `resource_deposits`' reject-not-normalize rule (R3), not `sectors`'
        normalize-on-reorder one: noncanonical order **raises**. Completeness is not required —
        a bloc absent from a chamber simply omits it.
        """
        seen: set[LegislativeChamber] = set()
        for entry in self.seats:
            if entry.chamber in seen:
                raise ValueError(f"duplicate chamber in bloc seats: {entry.chamber.value!r}")
            seen.add(entry.chamber)
        canonical = tuple(
            sorted(self.seats, key=lambda e: tuple(LegislativeChamber).index(e.chamber))
        )
        if canonical != self.seats:
            raise ValueError(
                "bloc seats must be in canonical chamber order "
                f"{[c.value for c in LegislativeChamber]!r}, got "
                f"{[e.chamber.value for e in self.seats]!r}"
            )
        return self


class PartyState(BaseModel):
    """A party: a formal role in relation to the government, and one or more internal blocs.

    The role is the party's *declared* position — in the coalition, supporting it on confidence
    and supply, or in opposition. It sets where the party's caucuses start; what moves them from
    there is each bloc's own relationship and preferences.
    """

    model_config = _STRICT_CONFIG

    id: str
    name: str
    government_role: GovernmentRole
    blocs: tuple[LegislativeBlocState, ...]

    @model_validator(mode="after")
    def _blocs_are_non_empty_unique_and_sorted_by_id(self) -> PartyState:
        if not self.blocs:
            raise ValueError(f"party {self.id!r} has no blocs; a party is at least one caucus")
        ids = [bloc.id for bloc in self.blocs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate bloc id within party {self.id!r}: {ids!r}")
        if ids != sorted(ids):
            raise ValueError(f"blocs of party {self.id!r} must be sorted by id, got {ids!r}")
        return self


class ChamberState(BaseModel):
    """One chamber, and how many seats it has in total.

    **No passage threshold.** Passage is a strict majority derived from `total_seats` alone
    (`legislative_voting.required_yes_seats`). A per-chamber threshold would be a second, silently
    authorable source of truth for the same rule; per-proposal-type supermajorities arrive in 3B2
    alongside a proposal type that actually needs one.
    """

    model_config = _STRICT_CONFIG

    chamber: LegislativeChamber
    total_seats: StrictPositiveSeatCount


class LegislatureState(BaseModel):
    """The chambers and parties of one country's legislature.

    Static in Phase 3B1: nothing mutates seats, roles, relationships or preferences, and
    `simulation.reconciliation` asserts as much. That is not the same as inert — the legislature is
    read every turn and decides whether the budget applies at all.
    """

    model_config = _STRICT_CONFIG

    chambers: tuple[ChamberState, ...]
    parties: tuple[PartyState, ...]

    @model_validator(mode="after")
    def _chambers_are_unique_non_empty_and_in_canonical_order(self) -> LegislatureState:
        if not self.chambers:
            raise ValueError("a legislature must have at least one chamber")
        seen: set[LegislativeChamber] = set()
        for chamber in self.chambers:
            if chamber.chamber in seen:
                raise ValueError(f"duplicate chamber: {chamber.chamber.value!r}")
            seen.add(chamber.chamber)
        canonical = tuple(
            sorted(self.chambers, key=lambda c: tuple(LegislativeChamber).index(c.chamber))
        )
        if canonical != self.chambers:
            raise ValueError(
                "chambers must be in canonical order "
                f"{[c.value for c in LegislativeChamber]!r}, got "
                f"{[c.chamber.value for c in self.chambers]!r}"
            )
        return self

    @model_validator(mode="after")
    def _parties_are_non_empty_unique_and_sorted_by_id(self) -> LegislatureState:
        if not self.parties:
            raise ValueError("a legislature must have at least one party")
        ids = [party.id for party in self.parties]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate party id: {ids!r}")
        if ids != sorted(ids):
            raise ValueError(f"parties must be sorted by id, got {ids!r}")
        return self

    @model_validator(mode="after")
    def _blocs_are_only_seated_in_chambers_that_exist(self) -> LegislatureState:
        """A bloc holding seats in an upper house of a unicameral legislature is not a small
        inconsistency to tolerate — it is seats that exist nowhere, which would be counted by
        apportionment against a chamber with no size to compare them to."""
        existing = {chamber.chamber for chamber in self.chambers}
        for party in self.parties:
            for bloc in party.blocs:
                for entry in bloc.seats:
                    if entry.chamber not in existing:
                        raise ValueError(
                            f"bloc {party.id!r}/{bloc.id!r} holds seats in "
                            f"{entry.chamber.value!r}, which this legislature does not have"
                        )
        return self

    @model_validator(mode="after")
    def _blocs_account_for_every_seat_in_every_chamber(self) -> LegislatureState:
        """Every seat in every chamber is held by exactly one bloc — an **equality**, not a bound.

        Rejecting only the excess would leave unheld seats representable, and unheld seats are not
        a harmless rounding of the truth: passage is measured against `total_seats`, so a chamber
        whose blocs account for 80 of 100 seats would need 51 supporters out of a body that can
        only ever produce 80. The missing 20 would behave as permanent, invisible abstentions that
        no bloc owns, that no player can bargain with, and that no report can explain.

        A genuinely unaligned crossbench is a real thing to model, but it must be modelled as a
        bloc — with a relationship, preferences and a discipline anyone can read — rather than as
        an authoring gap.
        """
        for chamber in self.chambers:
            held = sum(
                entry.seats
                for party in self.parties
                for bloc in party.blocs
                for entry in bloc.seats
                if entry.chamber is chamber.chamber
            )
            if held != chamber.total_seats:
                raise ValueError(
                    f"blocs hold {held} seats in the {chamber.chamber.value} chamber, which has "
                    f"{chamber.total_seats}; every seat must be held by exactly one bloc"
                )
        return self


class OutcomeBucket(StrEnum):
    """Which of the two terminal buckets a concluded game landed in (Phase 3C)."""

    VICTORY = "victory"
    DEFEAT = "defeat"


class RemovalReason(StrEnum):
    """Why a government's DEFEAT terminal outcome occurred (Phase 3C).

    A fact about what happened to *the office*, never about a named person — see §0 item 1 of the
    Phase 3C plan: this engine has no character/actor layer.
    """

    COUP = "coup"
    FORCED_ABDICATION = "forced_abdication"
    ASSASSINATION = "assassination"
    IMPEACHMENT = "impeachment"
    ELECTORAL_DEFEAT = "electoral_defeat"
    TERM_LIMIT_EXIT = "term_limit_exit"


class VictoryReason(StrEnum):
    """Why a government's VICTORY terminal outcome occurred (Phase 3C)."""

    PEACEFUL_LIBERALIZATION_COMPLETED = "peaceful_liberalization_completed"


class TerminalOutcomeState(BaseModel):
    """Set exactly once, by slot 12 or slot 13, and never cleared or altered afterward. `None` on
    `PoliticalState.terminal_outcome` means the game is still being played; `resolve_turn` refuses
    to resolve any further turn once this is set (Phase 3C, §6)."""

    model_config = _STRICT_CONFIG

    bucket: OutcomeBucket
    removal_reason: RemovalReason | None = None
    victory_reason: VictoryReason | None = None
    turn: int = Field(ge=0)

    @model_validator(mode="after")
    def _reason_matches_bucket(self) -> TerminalOutcomeState:
        if self.bucket is OutcomeBucket.VICTORY:
            if self.victory_reason is None or self.removal_reason is not None:
                raise ValueError("VICTORY requires victory_reason and forbids removal_reason")
        else:
            if self.removal_reason is None or self.victory_reason is not None:
                raise ValueError("DEFEAT requires removal_reason and forbids victory_reason")
        return self


class PendingLiberalizationState(BaseModel):
    """Explicit provenance for the liberalization-victory check (Phase 3C, §5). Set only when a
    `ConstitutionalAmendmentDecision` transitions the constitution from a qualifying noncompetitive
    shape to a qualifying competitive-elected shape. Both digests are stored
    (`constitution.constitution_digest`) so reconciliation can prove the transition really
    happened, not merely that the field is set."""

    model_config = _STRICT_CONFIG

    set_at_turn: int = Field(ge=0)
    opening_constitution_digest: str
    closing_constitution_digest: str


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
    legislature: LegislatureState | None = None
    """`None` if and only if `constitution.legislature is Legislature.NONE` (Phase 3B1).

    Both directions are enforced below, because each failure is a different kind of lie: a
    constitution declaring a legislature with no chambers to show for it, or chambers sitting under
    a constitution that says no legislature exists.
    """
    consecutive_terms_held: StrictTermsHeld = 1
    """(Phase 3C) How many elections in a row (including the one already underway at genesis) the
    incumbent has won. Incremented on every electoral WIN, including the win that completes a
    liberalization victory (slot 13). No "reset to 0" path exists: a loss or term-limit exit ends
    the game."""
    next_election_turn: int | None = None
    """(Phase 3C) The exact turn the next scheduled election falls on, replacing
    `turn % interval == 0` arithmetic, which breaks the moment the interval changes mid-game.
    `None` if and only if `constitution.national_election_interval_turns is None`. The sole writer
    after genesis is slot 2 (interval amendments) or slot 13 (scheduled-election outcomes)."""
    regime_transition_pressure_bps: StrictTransitionPressureBps = 0
    """(Phase 3C) Elevated coup risk from a recent constitutional amendment, direction-blind by
    construction. Written in exactly one place, slot 12, from one combining formula."""
    pending_liberalization: PendingLiberalizationState | None = None
    """(Phase 3C) Explicit provenance for the liberalization-victory check — see
    `PendingLiberalizationState`'s docstring."""
    terminal_outcome: TerminalOutcomeState | None = None
    """(Phase 3C) Set exactly once, by slot 12 or slot 13, and never cleared or altered afterward.
    `None` means the game is still being played."""

    @model_validator(mode="after")
    def _next_election_turn_nullness_matches_the_constitution(self) -> PoliticalState:
        """`next_election_turn` is authored directly at genesis (not derived from
        `national_election_interval_turns` at load time), so a future scenario is free to schedule
        a first election sooner or later than a full interval after genesis. The two fields are
        required to agree on nullness, but not on value."""
        has_interval = self.constitution.national_election_interval_turns is not None
        has_next_election = self.next_election_turn is not None
        if has_interval != has_next_election:
            raise ValueError(
                "next_election_turn must be set if and only if "
                "constitution.national_election_interval_turns is set: "
                f"national_election_interval_turns={self.constitution.national_election_interval_turns!r} "
                f"next_election_turn={self.next_election_turn!r}"
            )
        return self

    @model_validator(mode="after")
    def _legislature_presence_matches_the_constitution(self) -> PoliticalState:
        declared = self.constitution.legislature
        if declared is Legislature.NONE and self.legislature is not None:
            raise ValueError(
                "constitution.legislature is 'none' but a legislature is present; chambers cannot "
                "sit under a constitution that does not establish them"
            )
        if declared is not Legislature.NONE and self.legislature is None:
            raise ValueError(
                f"constitution.legislature is {declared.value!r} but no legislature is present"
            )
        return self

    @model_validator(mode="after")
    def _chamber_count_matches_the_constitutional_shape(self) -> PoliticalState:
        """`unicameral` means one chamber and `bicameral` means two — the constitution names the
        shape, and the legislature must be that shape rather than merely some shape."""
        if self.legislature is None:
            return self
        expected = 1 if self.constitution.legislature is Legislature.UNICAMERAL else 2
        actual = len(self.legislature.chambers)
        if actual != expected:
            raise ValueError(
                f"constitution.legislature is {self.constitution.legislature.value!r} but the "
                f"legislature has {actual} chamber(s), expected {expected}"
            )
        return self

    @model_validator(mode="after")
    def _a_unicameral_legislature_seats_its_lower_chamber(self) -> PoliticalState:
        """A single-chamber legislature is a `LOWER` chamber, not an `UPPER` one. Without this a
        unicameral state could be authored as an upper house alone, which no constitution here
        describes and which would silently change nothing except the label a player reads."""
        if self.legislature is None or self.constitution.legislature is not Legislature.UNICAMERAL:
            return self
        only = self.legislature.chambers[0].chamber
        if only is not LegislativeChamber.LOWER:
            raise ValueError(
                f"a unicameral legislature's single chamber must be "
                f"{LegislativeChamber.LOWER.value!r}, got {only.value!r}"
            )
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
    politics: PoliticalState | None = None
    """Optional like `finance`/`economy`: AI countries may omit it — Phase 3A cannot resolve
    politics for a country with no economy to derive performance from
    (`non_player_politics_not_supported`). Required for the player, enforced by
    `player_politics_required`, mirroring `player_finance_required`/`player_economy_required`."""


class ForeignProfileState(BaseModel):
    """An abstract foreign actor (External Wars, Gate W1).

    Not a `CountryState`: `CountryState` requires `population` and `treasury` with no defaults,
    so representing an abstract foreign actor that way would force inventing demographic and
    fiscal data no scenario has any business authoring for a country the player never governs.
    `war_capability_bps` is an ABSTRACT AUTHORED CAPABILITY used ONLY for non-player conflict
    progression (`simulation.foreign_conflict`). It is structurally separate from, and never
    read by: the player's future `MilitaryState` (W4), `InstitutionState(id="military")`, and
    the coup/unrest/impeachment formulas in `simulation.government_survival` — enforced by an
    AST/source scan in `tests/test_foreign_conflict.py` and
    `tests/test_legislative_neutrality.py`, and by the behavioural
    `test_foreign_capability_cannot_reach_domestic_coup_math` (commit 6, once a resolver exists
    to run it against).

    Lives in `WorldState.foreign_profiles: dict[str, ForeignProfileState]`, keyed by the stable
    foreign-country id. The id is deliberately **not** duplicated inside this value, so key and
    value can never disagree.
    """

    model_config = _STRICT_CONFIG

    display_name: str
    war_capability_bps: StrictBps


class ConflictDyadState(BaseModel):
    """An authored bilateral relationship between two FOREIGN countries (External Wars, Gate
    W1). Only `eligible` dyads may ever generate a war — generic per-actor belligerence never
    causes an outbreak on its own; the dyad is the only thing that can express that a specific
    pair has a specific quarrel.

    `country_a`/`country_b` are canonical: `country_a < country_b` lexicographically, enforced
    below and **rejected, never reordered**, matching every other ordered collection in this
    module (`resource_deposits`, `resource_output_coefficients`).

    `aggressor`/`defender` are separate, explicit, authored fields and are NEVER inferred from
    `country_a`/`country_b`'s canonical ordering — that ordering exists only to make the pair's
    identity and serialization stable, and carries no role meaning. Enforced below: `{aggressor,
    defender} == {country_a, country_b}` and `aggressor != defender`.
    """

    model_config = _STRICT_CONFIG

    country_a: str
    country_b: str
    tension_bps: StrictBps
    """Standing bilateral hostility."""
    grievance_bps: StrictBps
    """Accumulated specific casus belli."""
    eligible: bool
    """Authored gate: may this pair ever fight? A pair with `eligible=False` can never generate
    an outbreak regardless of `tension_bps`/`grievance_bps`."""
    aggressor: str
    defender: str
    aim_a: WarAim
    """Each side's war aim IF war occurs — authored, never drawn. `aim_a` belongs to the
    canonical `country_a` actor and `aim_b` to `country_b`, following canonical ordering, never
    aggressor/defender roles."""
    aim_b: WarAim
    player_security_exposure_bps: StrictBps
    """AUTHORED security exposure of the player to THIS dyad's war. Explicit content, never
    inferred from a country id, name, adjacency heuristic, or any other derived signal. Economic
    exposure is deliberately NOT modelled here and is zero in W1 — it arrives only when W3
    builds a real trade channel."""

    @model_validator(mode="after")
    def _pair_is_canonically_ordered(self) -> ConflictDyadState:
        """Invariant code (construction-time half): `dyad_pair_not_canonical`."""
        if self.country_a >= self.country_b:
            raise ValueError(
                f"dyad pair ({self.country_a!r}, {self.country_b!r}) is not canonically "
                "ordered; country_a must be strictly less than country_b lexicographically"
            )
        return self

    @model_validator(mode="after")
    def _roles_are_distinct_and_match_the_pair(self) -> ConflictDyadState:
        """Invariant codes (construction-time half): `dyad_aggressor_equals_defender`,
        `dyad_roles_do_not_match_pair`. A dedicated test authors a dyad whose aggressor is
        `country_b` to prove role and ordering are genuinely independent."""
        if self.aggressor == self.defender:
            raise ValueError(
                f"dyad ({self.country_a!r}, {self.country_b!r}): aggressor and defender are "
                f"both {self.aggressor!r}"
            )
        if {self.aggressor, self.defender} != {self.country_a, self.country_b}:
            raise ValueError(
                f"dyad ({self.country_a!r}, {self.country_b!r}): "
                f"{{aggressor={self.aggressor!r}, defender={self.defender!r}}} does not match "
                f"{{country_a, country_b}}"
            )
        return self


class ForeignConflictState(BaseModel):
    """A persistent, self-running war between two foreign countries (External Wars, Gate W1).

    `country_a`/`country_b` mirror the originating dyad's canonical pair. `aggressor`/`defender`
    and `war_capability_a_bps`/`war_capability_b_bps` are COPIED at outbreak from the dyad and
    each country's `ForeignProfileState` respectively, and never re-derived — the conflict is
    self-contained once it exists, so a later authored-content edit cannot retroactively change
    an already-fought war's terms.

    `status`/`resolved_turn` follow one rule, enforced below: `ACTIVE`/`CEASEFIRE` are
    reversible and `resolved_turn` must be `None`; `SETTLED`/`DECIDED` (`TERMINAL_STATUSES`,
    `simulation.foreign_conflict`) are terminal and `resolved_turn` is required.
    """

    model_config = _STRICT_CONFIG

    conflict_id: str
    """`f"{country_a}__{country_b}__t{opened_turn}"` — deterministic and unique; a pair cannot
    re-fight while an existing conflict between them is still `ACTIVE` or `CEASEFIRE`."""
    country_a: str
    country_b: str
    aggressor: str
    defender: str
    war_capability_a_bps: StrictBps
    war_capability_b_bps: StrictBps
    aim_a: WarAim
    aim_b: WarAim
    opened_turn: int = Field(ge=0)
    intensity_bps: StrictBps
    position_bps: StrictRelationshipBps
    """Signed: positive favours the canonical `country_a` actor, negative favours `country_b`."""
    exhaustion_a_bps: StrictBps
    exhaustion_b_bps: StrictBps
    negotiation_readiness_bps: StrictBps
    status: ConflictStatus
    ceasefire_run_turns: int = Field(ge=0, default=0)
    resolved_turn: int | None = None

    @model_validator(mode="after")
    def _pair_is_canonically_ordered(self) -> ForeignConflictState:
        """Invariant code (construction-time half): `conflict_ids_not_canonical`."""
        if self.country_a >= self.country_b:
            raise ValueError(
                f"conflict {self.conflict_id!r}: pair ({self.country_a!r}, {self.country_b!r}) "
                "is not canonically ordered; country_a must be strictly less than country_b"
            )
        return self

    @model_validator(mode="after")
    def _roles_are_distinct_and_match_the_pair(self) -> ForeignConflictState:
        if self.aggressor == self.defender:
            raise ValueError(
                f"conflict {self.conflict_id!r}: aggressor and defender are both {self.aggressor!r}"
            )
        if {self.aggressor, self.defender} != {self.country_a, self.country_b}:
            raise ValueError(
                f"conflict {self.conflict_id!r}: "
                f"{{aggressor={self.aggressor!r}, defender={self.defender!r}}} does not match "
                f"{{country_a, country_b}}"
            )
        return self

    @model_validator(mode="after")
    def _resolved_turn_matches_terminal_status(self) -> ForeignConflictState:
        """Invariant codes (construction-time half): `conflict_resolved_turn_requires_terminal_status`,
        `conflict_terminal_status_requires_resolved_turn`. Enforced by a row self-validator here
        AND by two `check_invariants` codes, so neither a report nor a state can carry the
        mismatch alone."""
        is_terminal = self.status in TERMINAL_STATUSES
        if is_terminal and self.resolved_turn is None:
            raise ValueError(
                f"conflict {self.conflict_id!r}: status {self.status.value!r} is terminal but "
                "resolved_turn is None"
            )
        if not is_terminal and self.resolved_turn is not None:
            raise ValueError(
                f"conflict {self.conflict_id!r}: status {self.status.value!r} is reversible but "
                f"resolved_turn={self.resolved_turn} is set"
            )
        return self


class PlayerCountryRef(BaseModel):
    """Ownership by the player's own country. Resolves through `WorldState.countries`."""

    model_config = _STRICT_CONFIG

    kind: Literal["player_country"] = "player_country"
    country_id: StrictMapId


class ForeignProfileRef(BaseModel):
    """Ownership by a W1 foreign actor. Resolves through `WorldState.foreign_profiles`.

    Grants that profile no population, treasury, economy or politics -- a foreign profile stays
    exactly what W1 made it, and owning map area does not upgrade it into a country.
    """

    model_config = _STRICT_CONFIG

    kind: Literal["foreign_profile"] = "foreign_profile"
    foreign_profile_id: StrictMapId


SovereignRef: TypeAlias = Annotated[
    PlayerCountryRef | ForeignProfileRef, Field(discriminator="kind")
]
"""A tagged reference into the two EXISTING authoritative namespaces (Strategic Military Map,
Gate M0).

Deliberately NOT a third actor registry: a registry could disagree with `countries` /
`foreign_profiles` about who exists and what they are called, and there would be no principled
answer to which one is right. Discriminated on `kind`, matching every other tagged union in this
codebase.
"""


class TheaterPresentation(BaseModel):
    """Presentation only.

    Read by the map projection and by the renderer; by NO formula, and by no validator that
    decides legality. Enforced structurally by `test_map_presentation_boundary.py` and
    behaviourally by `test_map_presentation_neutrality.py`.
    """

    model_config = _STRICT_CONFIG

    centroid_x: StrictGridCoord
    centroid_y: StrictGridCoord
    label_anchor: LabelAnchor


class TheaterState(BaseModel):
    """One strategic theater: a military operating area, NOT a simulated province.

    It has no population, budget, election, approval, tax base or city economy, and never will --
    that is the Cities & Provinces expansion boundary.
    """

    model_config = _STRICT_CONFIG

    display_name: StrictDisplayName
    kind: TheaterKind
    owner: SovereignRef
    presentation: TheaterPresentation

    # NOTE: no `id` field. The `StrategicMapState.theaters` dict KEY is authoritative, so key and
    # value can never disagree -- the same discipline as `ForeignProfileState` above.


class RouteState(BaseModel):
    """One DIRECTED mechanical adjacency (Strategic Military Map, Gate M0).

    Two-way passage is TWO rows. There is no implicit symmetry, because implicit reciprocity is
    exactly how a deliberately one-way or impassable-in-return edge silently becomes passable.
    """

    model_config = _STRICT_CONFIG

    from_theater: StrictMapId
    to_theater: StrictMapId
    kind: RouteKind

    @model_validator(mode="after")
    def _not_a_self_edge(self) -> RouteState:
        """Emits `ROUTE_SELF_EDGE`."""
        if self.from_theater == self.to_theater:
            raise ValueError(
                f"{ROUTE_SELF_EDGE}: route is a self-edge on theater {self.from_theater!r}"
            )
        return self


class CountryShapeState(BaseModel):
    """An authored fictional political outline (Strategic Military Map, Gate M0).

    Presentation only. Polygon contact NEVER creates mechanical adjacency; only `RouteState`
    does. Two shapes may share a border pixel-for-pixel and still have no route between their
    theaters, and that is a legal, meaningful map.
    """

    model_config = _STRICT_CONFIG

    shape_id: StrictMapId
    owner: SovereignRef
    polygon: tuple[tuple[StrictGridCoord, StrictGridCoord], ...] = Field(min_length=3)

    @model_validator(mode="after")
    def _polygon_is_well_formed(self) -> CountryShapeState:
        """Emits `SHAPE_POLYGON_CLOSING_VERTEX_REPEATED`, `SHAPE_POLYGON_REPEATS_VERTEX` or
        `SHAPE_POLYGON_ZERO_AREA`.

        Vertex representation: an OPEN RING stored in AUTHORED ORDER. The closing vertex is
        implicit; repeating the first vertex at the end is REJECTED rather than trimmed, so there
        is exactly one representation of a given ring outline.

        NO rotation normalization and NO winding normalization is performed. Starting vertex and
        winding direction are stored as authored, and two rings that differ only by rotation are
        DIFFERENT authored values that serialize to different bytes.
        """
        if self.polygon[0] == self.polygon[-1]:
            raise ValueError(
                f"{SHAPE_POLYGON_CLOSING_VERTEX_REPEATED}: polygon repeats its first vertex "
                f"as a closing vertex; rings are open"
            )
        for first, second in zip(self.polygon, self.polygon[1:], strict=False):
            if first == second:
                raise ValueError(
                    f"{SHAPE_POLYGON_REPEATS_VERTEX}: polygon has a duplicate consecutive "
                    f"vertex {first!r}"
                )
        if shoelace_doubled_area(self.polygon) == 0:
            raise ValueError(f"{SHAPE_POLYGON_ZERO_AREA}: polygon encloses zero area")
        return self


class StrategicMapState(BaseModel):
    """The authoritative strategic map (Strategic Military Map, Gate M0).

    IMMUTABLE during a campaign: no M0 phase writes it, and `reconcile_strategic_map_staticness`
    proves it byte-identical across every resolved turn.
    """

    model_config = _STRICT_CONFIG

    map_id: StrictMapId
    capital_theater_id: StrictMapId
    theaters: dict[StrictMapId, TheaterState] = Field(min_length=1)
    """The authoritative theater registry, keyed by theater id.

    The KEY is annotated `StrictMapId`, not bare `str`: the dict key is the authoritative
    identifier (TheaterState carries no `id` field), so it must enforce exactly the same
    nonempty / strict-string / max-length-64 rules as every other map identifier. A bare
    `dict[str, ...]` would accept an empty key, a coerced non-string key, or a 4,000-character
    key, and the fault would only surface later -- and only by accident -- if some route happened
    to reference it. Validating the key at construction means an invalid key is impossible to
    store, not merely likely to be noticed.
    """
    routes: tuple[RouteState, ...] = ()
    shapes: tuple[CountryShapeState, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _routes_unique_and_ordered(self) -> StrategicMapState:
        """Emits `ROUTE_DUPLICATE` or `ROUTE_NOT_CANONICAL`.

        Two SEPARATE failures with two separate codes. Duplicates are checked FIRST and
        independently of ordering, so each is reachable on its own: a duplicated pair such as
        (a,b),(a,b) is already sorted and trips ONLY the duplicate check, while two distinct
        pairs in the wrong order trip ONLY the ordering check.

        Non-canonical order is REJECTED, never normalized -- the repository-wide rule for every
        ordered collection.
        """
        keys = [(r.from_theater, r.to_theater, r.kind.value) for r in self.routes]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{ROUTE_DUPLICATE}: duplicate route(s) in the map: {keys!r}")
        if keys != sorted(keys):
            raise ValueError(
                f"{ROUTE_NOT_CANONICAL}: routes are not in canonical (from, to, kind) "
                f"order: {keys!r}"
            )
        return self

    @model_validator(mode="after")
    def _shapes_unique_and_ordered(self) -> StrategicMapState:
        """Emits `SHAPE_ID_DUPLICATE` or `SHAPE_NOT_CANONICAL`.

        Two SEPARATE failures, for the same reason as routes and reachable independently:
        ['s_a', 's_a'] is sorted and trips ONLY the duplicate check; ['s_b', 's_a'] has no
        duplicate and trips ONLY the ordering check.
        """
        shape_ids = [s.shape_id for s in self.shapes]
        if len(set(shape_ids)) != len(shape_ids):
            raise ValueError(
                f"{SHAPE_ID_DUPLICATE}: duplicate shape_id(s) in the map: {shape_ids!r}"
            )
        if shape_ids != sorted(shape_ids):
            raise ValueError(
                f"{SHAPE_NOT_CANONICAL}: shapes are not in canonical shape_id order: {shape_ids!r}"
            )
        return self


class WorldState(BaseModel):
    """All countries in the game world, plus which one the player controls.

    `foreign_profiles`/`dyads`/`conflicts` (External Wars, Gate W1) represent foreign actors and
    their persistent, self-running wars — entirely separate from `countries`, which remains
    exactly what it always was: the player and any future player-style AI country. See
    `ForeignProfileState`'s docstring for why foreign actors are not `CountryState` entries.
    """

    model_config = _STRICT_CONFIG

    countries: dict[str, CountryState] = Field(default_factory=dict)
    player_country_id: str
    foreign_profiles: dict[str, ForeignProfileState] = Field(default_factory=dict)
    """Keyed by the stable foreign-country id. Every read — validation, outbreak candidate
    assembly, weighted selection, report row emission, canonical JSON — iterates
    `sorted(foreign_profiles)`; canonical JSON serialization already sorts mapping keys
    (`core.canonical_json`), so a different construction order produces byte-identical output."""
    dyads: tuple[ConflictDyadState, ...] = Field(default_factory=tuple)
    """Canonical by `(country_a, country_b)`, **reject-not-normalize** — matching
    `resource_deposits`' policy (ADR 0007 R3), not `sectors`' normalize-on-reorder one."""
    conflicts: tuple[ForeignConflictState, ...] = Field(default_factory=tuple)
    """Canonical by `conflict_id`, **reject-not-normalize**."""
    strategic_map: StrategicMapState
    """The campaign's defining strategic map (Strategic Military Map, Gate M0). REQUIRED: no
    default, no `| None`.

    A valid 0.14.0 game carries its map or fails construction. There is deliberately no synthetic
    fallback map hidden inside the model -- a fallback would mean a save could silently lose its
    map and still load, which is precisely the failure `reconcile_strategic_map_staticness` exists
    to detect.
    """

    @model_validator(mode="after")
    def _dyads_are_unique_and_canonically_ordered(self) -> WorldState:
        """Invariant codes (construction-time half): `dyad_duplicate_pair`,
        `dyad_pair_not_canonical` (the tuple-level half; each dyad's own field-level ordering is
        already enforced by `ConflictDyadState`'s own validator)."""
        pairs = [(dyad.country_a, dyad.country_b) for dyad in self.dyads]
        if len(set(pairs)) != len(pairs):
            raise ValueError(f"duplicate dyad pair(s) in world.dyads: {pairs!r}")
        if pairs != sorted(pairs):
            raise ValueError(
                f"world.dyads is not in canonical (country_a, country_b) order: got {pairs!r}, "
                f"expected {sorted(pairs)!r}"
            )
        return self

    @model_validator(mode="after")
    def _conflicts_are_unique_and_canonically_ordered(self) -> WorldState:
        """Invariant codes (construction-time half): `conflict_duplicate_id`,
        `conflict_ids_not_canonical` (the tuple-level half)."""
        ids = [conflict.conflict_id for conflict in self.conflicts]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate conflict_id(s) in world.conflicts: {ids!r}")
        if ids != sorted(ids):
            raise ValueError(
                f"world.conflicts is not in canonical conflict_id order: got {ids!r}, expected "
                f"{sorted(ids)!r}"
            )
        return self


RULESET_VERSION = "0.14.0"
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
older save), and
`docs/adr/0010-legislature-parties-and-political-capital-bargaining.md` (bumped `"0.8.0" ->
"0.9.0"` for Phase 3B1: `PoliticalState.legislature` becomes required whenever the constitution
declares a legislature, and a 0.8.0 save has no chambers, parties, blocs, seats, relationships or
preferences to backfill from — inventing them would be inventing a legislature, not migrating
one; and turn resolution now routes the budget through a vote that can fail, so the same decisions
no longer produce the same turn), and
`docs/adr/0011-competing-political-capital-uses-and-bloc-relationships.md` (bumped `"0.9.0" ->
"0.10.0"` for Phase 3B2A: `DecisionSet.decisions` becomes a tagged union rather than a homogeneous
tuple, so a 0.9.0 decision payload lacking an explicit `kind` per element no longer round-trips
through the same parse path; `TurnReport` gains an eighth report,
`political_capital: PoliticalCapitalReport`, with no data in a 0.9.0 save to backfill it from — a
0.9.0 turn spent capital on exactly one thing and has no expenditure ledger to reconstruct; and
`PoliticalState.legislature`'s `government_relationship_bps` becomes mutable turn to turn, so
replaying 0.9.0 history against 3B2A's reconciliation groups 12/14 would require inventing
relationship provenance no 0.9.0 save ever recorded), and
`docs/adr/0012-political-memory-policy-reactions-and-relationship-decay.md` (bumped `"0.10.0" ->
"0.11.0"` for Phase 3B2B: `LegislativeBlocState.baseline_government_relationship_bps` becomes a
new required field with no authored political history in a 0.10.0 save to backfill it from —
defaulting it to that save's *current* relationship would assert every historical bloc was exactly
at its structural baseline at the moment of the save, a claim about political history the save
does not contain; `TurnReport` gains a ninth report, `political_relationship:
PoliticalRelationshipReport`, and `PoliticalCapitalReport.relationship_changes` is removed (moved
onto the new report), so a 0.10.0 turn's relationship-investment ledger no longer round-trips
through the same field; and turn resolution now writes `government_relationship_bps` on turns with
no decisions at all (decay), so the same decisions no longer produce the same closing state), and
`docs/adr/0013-government-survival.md` (bumped `"0.11.0" -> "0.12.0"` for the whole of Phase 3C
(Gates 3C1-3C3, one bump for the phase, not one per gate):
`InstitutionState`/`PopulationGroupState`'s loyalty/power/competence/corruption and political_
influence/approval/trust/organization/radicalization convert from Phase-1 floats (0.0-100.0) to
strict basis points, so a 0.11.0 save's float values no longer satisfy the strict-int fields at
all; `PoliticalState` gains five new fields (`consecutive_terms_held`, `next_election_turn`,
`regime_transition_pressure_bps`, `pending_liberalization`, `terminal_outcome`) with no authored
political-survival history in a 0.11.0 save to backfill them from; and `TurnReport` grows from
nine reports to twelve -- `election: ElectionReport` (Gate 3C1), `coup_unrest: CoupUnrestReport`
(Gate 3C2), and `constitutional_amendment: ConstitutionalAmendmentReport` (Gate 3C3) -- with no
data in a 0.11.0 save to reconstruct any of the three from: a 0.11.0 turn never evaluated an
election, assessed coup/unrest/impeachment risk, or resolved a constitutional amendment at all),
and `docs/adr/0016-external-wars-foreign-conflicts.md` (bumped `"0.12.0" -> "0.13.0"` for External
Wars Gate W1: `WorldState` gains `foreign_profiles`, `dyads` and `conflicts`, and turn resolution
now draws foreign-conflict outbreaks and progression from three new RNG streams
(`foreign_conflict_outbreak`, `foreign_conflict_progress:{cid}`, `foreign_conflict_termination:
{cid}`), so replaying a 0.12.0 turn under 0.13.0 rules would draw randomness a 0.12.0 turn never
consumed and could start a war a 0.12.0 turn's decisions never anticipated; `TurnReport` grows
from twelve reports to thirteen -- `foreign_affairs: ForeignAffairsReport` -- with no data in a
0.12.0 save to reconstruct it from: a 0.12.0 turn never evaluated a foreign-conflict outbreak or
progression at all. **No migration**: a 0.12.0 save has no dyads; synthesising a peaceful world
would assert a fact the save does not contain. `SAVE_FORMAT_VERSION` stays `1`), and
`docs/adr/0017-strategic-military-map-m0.md` (bumped `"0.13.0" -> "0.14.0"` for Strategic Military
Map Gate M0: `WorldState` gains a REQUIRED `strategic_map: StrategicMapState`, with no map
authored in any 0.13.0 save to backfill it from -- synthesising one would assert authored content
(theater names, ownership, geometry) the save never contained, and there is no principled way to
choose it. Unlike every prior bump, this one changes NO turn-resolution behavior at all: M0 adds
no phase, no formula, no RNG stream and no report -- `reconcile_strategic_map_staticness` proves
the map byte-identical across every resolved turn, so replaying 0.13.0-authored decisions under
0.14.0 rules produces the identical turn. The bump exists purely because the new field is
required, matching the schema-shape rationale of every ruleset bump above rather than a
behavior-change one. `SAVE_FORMAT_VERSION` stays `1`.
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
