"""Headless entry point: create games, resolve turns, and inspect history —
all without a server or database.

    mandate new --scenario data/scenarios/tiny_valid.yaml --out save.json
    mandate inspect --state save.json
    mandate resolve --state save.json --turns 8 --out save.turn8.json
    mandate resolve --state save.json --turns 1 --decisions-file budget.json --out save2.json
    mandate history --state save.turn8.json
    mandate history --state save.turn8.json --turn 3

`new` creates a save containing only the genesis (turn-0) entry. `inspect`
loads a save, reports its version envelope and integrity status, and writes
nothing — even an invalid save can be inspected (that is the point of
"integrity status"), reported via a nonzero exit rather than a stack trace.
`resolve` appends N turns via `simulation.history.advance_game` and writes
the result atomically; on any failure nothing is written and the input file
is untouched. With `--decisions-file`, the file's JSON is parsed as a full
`DecisionSet` (including `expected_turn`/`expected_state_version` — a
mismatch against the save's actual current turn is rejected the same way any
other stale decision set is) and applied to exactly one turn; `--decisions-file`
requires `--turns 1`, enforced as a hard error rather than silently applying
the file only to the first of several turns. `history` lists every turn or,
with `--turn N`, prints one historical entry — without mutating anything. It
refuses to operate on an invalid save (unlike `inspect`, whose job is to
report exactly that).

Save files are the real, versioned, hash-chained format from
`simulation.save_format` — not the flat `{state_file_schema_version, state}`
format Phase 0 wrote. That format is not read by this build at all; see
`docs/adr/0002-snapshot-history-and-versioning.md` for why it isn't migrated.

## Reason-ID rendering

`TurnReportEntry`/`FinanceReport` store `reason_id` + structured `params`,
not English prose (see `simulation.report` module docstring for why: report
text lives inside hash-protected history and could never be re-rendered
otherwise). `REASON_RENDERERS` is the presentation-layer table that turns
those back into English for this CLI; `render_entry` falls back to a visibly
labeled placeholder for an unmapped id rather than crashing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from app.content.scenarios import load_scenario_file
from app.core.errors import DecisionSetError, HistoryValidationError, MandateError
from app.core.money import format_money
from app.saves import read_save_file, write_save_atomic
from app.simulation.decisions import DecisionSet
from app.simulation.history import GameSave, advance_game, new_game, validate_history
from app.simulation.legislative_voting import required_yes_seats
from app.simulation.legislature import GovernmentRole, LegislativeChamber, LegislativeOutcome
from app.simulation.report import (
    BlocVoteReport,
    FinanceReport,
    LaborMarketReport,
    LegislativeReport,
    PoliticalCapitalReport,
    PoliticalReport,
    ProductionReport,
    ResourceExtractionReport,
    TaxBaseDerivationReport,
    TurnReport,
    TurnReportEntry,
)
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json, load_save_json
from app.simulation.state import RESOURCE_UNITS, PoliticalState

# --- reason_id -> English rendering (presentation layer only; never stored) --

_TAX_FIELD_LABELS = {
    "personal_income_rate_bps": "Personal-income tax",
    "corporate_rate_bps": "Corporate tax",
    "consumption_rate_bps": "Consumption tax",
}


def _format_bps_delta(bps: int) -> str:
    """A signed percentage-point delta, e.g. `+5.00pp` / `-2.50pp` / `+0.00pp`. Always carries an
    explicit sign so an increase is never mistaken for a decrease at a glance."""
    return f"{bps / 100:+.2f}pp"


def _bps_to_percent_str(bps: object) -> str:
    return f"{int(bps) / 100:g}%"


def _render_turn_resolved(params: dict[str, str | int]) -> str:
    return f"Turn {params['turn']} resolved."


def _render_no_budget_changes_submitted(_params: dict[str, str | int]) -> str:
    return "No budget changes were submitted; the current tax and spending plan continues."


def _render_tax_rate_changed(params: dict[str, str | int]) -> str:
    field = str(params["field"])
    label = _TAX_FIELD_LABELS.get(field, field)
    old_pct = _bps_to_percent_str(params["old_bps"])
    new_pct = _bps_to_percent_str(params["new_bps"])
    return f"{label} rate changed from {old_pct} to {new_pct}."


def _render_spending_category_changed(params: dict[str, str | int]) -> str:
    category = str(params["category"]).replace("_", " ")
    old_amount = format_money(int(params["old_amount"]))
    new_amount = format_money(int(params["new_amount"]))
    return f"{category.capitalize()} spending changed from {old_amount} to {new_amount} denars."


def _render_deficit_financed_with_new_borrowing(params: dict[str, str | int]) -> str:
    amount = format_money(int(params["amount"]))
    return (
        f"The treasury issued {amount} denars of new debt because cash was insufficient "
        "to cover the quarterly deficit."
    )


def _render_sector_inactive(params: dict[str, str | int]) -> str:
    category = str(params["category"]).replace("_", " ")
    return f"{category.capitalize()} sector is inactive (zero production capacity)."


def _render_labor_market_resolved(params: dict[str, str | int]) -> str:
    effective_labor_force = int(params["effective_labor_force"])
    total_employment = int(params["total_employment"])
    unemployed_workers = int(params["unemployed_workers"])
    unfilled_jobs = int(params["unfilled_jobs"])
    unemployment_rate = _bps_to_percent_str(params["unemployment_rate_bps"])
    return (
        f"Labor market resolved: labor_force={effective_labor_force:,} "
        f"employment={total_employment:,} unemployed={unemployed_workers:,} "
        f"unfilled_jobs={unfilled_jobs:,} unemployment_rate={unemployment_rate}."
    )


def _render_production_summary(params: dict[str, str | int]) -> str:
    total_employment = int(params["total_employment"])
    total_gross_output = int(params["total_gross_output"])
    return (
        f"Sector production resolved: total_employment={total_employment:,} workers, "
        f"total_gross_output={total_gross_output:,} (fixed base-year output units, not money). "
        f"capacity_constrained={params['sectors_capacity_constrained']} "
        f"labor_constrained={params['sectors_labor_constrained']} "
        f"exactly_balanced={params['sectors_exactly_balanced']} "
        f"inactive={params['sectors_inactive']}"
    )


def _render_resource_extraction_resolved(params: dict[str, str | int]) -> str:
    deposits_active = int(params["deposits_active"])
    deposits_depleted = int(params["deposits_depleted"])
    total_extraction_workers = int(params["total_extraction_workers"])
    unassigned_resource_workers = int(params["unassigned_resource_workers"])
    extraction_sector_real_output = int(params["extraction_sector_real_output"])
    extraction_sector_potential_output = int(params["extraction_sector_potential_output"])
    return (
        f"Resource extraction resolved: deposits_active={deposits_active} "
        f"deposits_depleted={deposits_depleted} "
        f"total_extraction_workers={total_extraction_workers:,} "
        f"unassigned_resource_workers={unassigned_resource_workers:,} "
        f"extraction_output={extraction_sector_real_output:,} "
        f"potential={extraction_sector_potential_output:,}."
    )


def _render_tax_bases_derived(params: dict[str, str | int]) -> str:
    personal = format_money(int(params["personal_income"]))
    corporate = format_money(int(params["corporate_profit"]))
    consumption = format_money(int(params["taxable_consumption"]))
    return (
        f"Tax bases derived from this turn's production: personal={personal} "
        f"corporate={corporate} consumption={consumption} denars."
    )


def _render_legitimacy_resolved(params: dict[str, str | int]) -> str:
    opening = _bps_to_percent_str(params["opening_legitimacy_bps"])
    order_support = _bps_to_percent_str(params["order_support_contribution_bps"])
    performance = _bps_to_percent_str(params["performance_contribution_bps"])
    total_change = _bps_to_percent_str(params["total_legitimacy_change_bps"])
    closing = _bps_to_percent_str(params["closing_legitimacy_bps"])
    support = _bps_to_percent_str(params["constitutional_order_support_bps"])
    return (
        f"Legitimacy resolved: opening={opening} order_support_drift={order_support} "
        f"(toward authored support {support}) performance={performance} "
        f"total_change={total_change} closing={closing}."
    )


def _render_political_capital_resolved(params: dict[str, str | int]) -> str:
    opening = int(params["opening"])
    regeneration = int(params["regeneration"])
    spent = int(params["spent"])
    capacity = int(params["capacity"])
    closing = int(params["closing"])
    return (
        f"Political capital resolved: opening={opening:,} regeneration=+{regeneration:,} "
        f"spent={spent:,} -> closing={closing:,} / {capacity:,}."
    )


def _render_legislative_vote_resolved(params: dict[str, str | int]) -> str:
    route = str(params["route"])
    outcome = str(params["outcome"])
    chambers_passed = int(params["chambers_passed"])
    chambers_total = int(params["chambers_total"])
    supporting = int(params["supporting_seats"])
    required = int(params["required_yes_seats"])
    committed = int(params["political_capital_committed"])

    if chambers_total == 0:
        # A decree: no chamber voted, so there is no tally to report. Saying "0 of 0 chambers
        # passed" would read as a defeat rather than as "no vote was held".
        return (
            f"Budget resolved by {route}: {outcome} — enacted through executive decree "
            f"authority, no chamber vote held. Political capital committed: {committed:,}."
        )

    # (§14) For a bicameral legislature these are SUMS across chambers that were each decided
    # separately — said explicitly, because passage is per-chamber and a pooled total never
    # determines it. The per-chamber breakdown is in the `legislative:` block.
    scope = (
        "across 1 chamber"
        if chambers_total == 1
        else f"totalled across {chambers_total} separately decided chambers"
    )
    return (
        f"Budget resolved by {route}: {outcome} — {chambers_passed} of {chambers_total} "
        f"chamber(s) passed; {supporting:,} supporting seats against {required:,} required "
        f"({scope}; each chamber must reach its own majority independently). "
        f"Political capital committed: {committed:,}."
    )


def _render_budget_blocked_by_legislature(params: dict[str, str | int]) -> str:
    chamber = str(params["chamber"])
    supporting = int(params["supporting_seats"])
    required = int(params["required_yes_seats"])
    shortfall = int(params["shortfall_seats"])
    return (
        f"Budget blocked by the {chamber} chamber: {supporting:,} supporting seats against "
        f"{required:,} required, short {shortfall:,}."
    )


def _render_political_capital_ledger_resolved(params: dict[str, str | int]) -> str:
    opening = int(params["opening"])
    total_committed = int(params["total_committed"])
    legislative_committed = int(params["legislative_committed"])
    relationship_committed = int(params["relationship_committed"])
    regeneration = int(params["regeneration"])
    closing = int(params["closing"])
    capacity = int(params["capacity"])
    return (
        f"Political capital ledger resolved: opening={opening:,} committed={total_committed:,} "
        f"(legislative/decree={legislative_committed:,}, "
        f"relationship investment={relationship_committed:,}) regeneration=+{regeneration:,} "
        f"-> closing={closing:,} / {capacity:,}."
    )


def _render_bloc_relationship_investment_resolved(params: dict[str, str | int]) -> str:
    party_id = str(params["party_id"])
    bloc_id = str(params["bloc_id"])
    political_capital = int(params["political_capital"])
    opening_bps = int(params["opening_relationship_bps"])
    applied_bps = int(params["applied_change_bps"])
    closing_bps = int(params["closing_relationship_bps"])
    return (
        f"Relationship investment in {party_id}/{bloc_id}: {political_capital:,} political "
        f"capital moved the relationship from {_bps_to_percent_str(opening_bps)} to "
        f"{_bps_to_percent_str(closing_bps)} ({_format_bps_delta(applied_bps)})."
    )


REASON_RENDERERS: dict[str, Callable[[dict[str, str | int]], str]] = {
    "turn_resolved": _render_turn_resolved,
    "no_budget_changes_submitted": _render_no_budget_changes_submitted,
    "tax_rate_changed": _render_tax_rate_changed,
    "spending_category_changed": _render_spending_category_changed,
    "deficit_financed_with_new_borrowing": _render_deficit_financed_with_new_borrowing,
    "sector_inactive": _render_sector_inactive,
    "labor_market_resolved": _render_labor_market_resolved,
    "resource_extraction_resolved": _render_resource_extraction_resolved,
    "production_summary": _render_production_summary,
    "tax_bases_derived": _render_tax_bases_derived,
    "legitimacy_resolved": _render_legitimacy_resolved,
    "political_capital_resolved": _render_political_capital_resolved,
    "legislative_vote_resolved": _render_legislative_vote_resolved,
    "budget_blocked_by_legislature": _render_budget_blocked_by_legislature,
    "political_capital_ledger_resolved": _render_political_capital_ledger_resolved,
    "bloc_relationship_investment_resolved": _render_bloc_relationship_investment_resolved,
}
"""Every `reason_id` this build can emit must be a key here — proven by
`tests/test_reason_renderers.py`, which calls every phase-emittable reason_id
through `render_entry` and asserts none of them hit the fallback branch.
"""


def render_entry(entry: TurnReportEntry) -> str:
    """Render one report entry as English. Never raises: an unmapped `reason_id`
    or a renderer that can't make sense of `params` produces a visibly-labeled
    fallback string instead of crashing the CLI or displaying wrong information.
    """
    renderer = REASON_RENDERERS.get(entry.reason_id)
    if renderer is None:
        return f"[unrendered reason_id={entry.reason_id!r} params={entry.params!r}]"
    try:
        return renderer(entry.params)
    except (KeyError, ValueError, TypeError) as exc:
        return f"[error rendering reason_id={entry.reason_id!r}: {exc}]"


# --- save file I/O ------------------------------------------------------------


def _write_save(path: Path, save: GameSave) -> None:
    write_save_atomic(path, dump_save_json(save).encode("utf-8"))


def _read_save(path: Path) -> GameSave:
    return load_save_json(read_save_file(path), source=str(path))


def _read_decisions_file(path: Path) -> DecisionSet:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DecisionSetError(f"could not read decisions file {path}: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise DecisionSetError(f"decisions file {path} is not valid JSON: {exc}") from exc
    try:
        return DecisionSet.model_validate(raw)
    except ValidationError as exc:
        raise DecisionSetError(f"decisions file {path} failed validation: {exc}") from exc


# --- subcommands ---------------------------------------------------------------


def _cmd_new(args: argparse.Namespace) -> int:
    state = load_scenario_file(args.scenario)
    if args.seed is not None:
        state = state.model_copy(update={"seed": args.seed})

    save = new_game(state, save_format_version=SAVE_FORMAT_VERSION)
    out_path = Path(args.out)
    _write_save(out_path, save)
    print(
        f"created game from scenario {args.scenario!r}: seed={state.seed} turn=0 "
        f"-> wrote {out_path}"
    )
    return 0


_ROLE_LABELS: dict[GovernmentRole, str] = {
    GovernmentRole.COALITION: "coalition",
    GovernmentRole.CONFIDENCE_AND_SUPPLY: "confidence-and-supply",
    GovernmentRole.OPPOSITION: "opposition",
}


def _print_legislature_composition(politics: PoliticalState) -> None:
    """(Phase 3B1, §14) `inspect --legislature`: the AUTHORED INSTITUTIONAL COMPOSITION held in
    state, and nothing else.

    Deliberately shows **no support tally**. A figure like "58/100" is not a property of a
    legislature — it is the result of *a specific proposal* being voted on, and it changes with
    every proposal and every capital allocation. It exists only inside a resolved turn's
    `LegislativeReport` and is printed there (`_print_legislative_report`). Printing one here
    would invent a proposal the player never made and imply a standing majority that does not
    exist.

    The seat totals below are summed directly from each bloc's authored `seats` entries, which
    `LegislatureState`'s own validator already requires to reconcile exactly against each
    chamber's `total_seats` — so these are the real authored seats, not a derived estimate.
    """
    decree = politics.constitution.decree_authority.value
    legislature = politics.legislature
    if legislature is None:
        # An explicit line, never an empty table: "no legislature" is a real, C10-constrained
        # constitutional arrangement (and one that REQUIRES unlimited decree authority), not a
        # missing-data case.
        print("  legislature:         none — this constitution has no legislature")
        print(f"  decree authority:    {decree}")
        return

    print(f"  legislature:         {politics.constitution.legislature.value}")
    print(f"  decree authority:    {decree}")

    role_by_party = {party.id: party.government_role for party in legislature.parties}

    for chamber in legislature.chambers:
        majority = required_yes_seats(total_seats=chamber.total_seats)
        print(
            f"    {chamber.chamber.value} chamber: {chamber.total_seats} seats "
            f"(strict majority {majority})"
        )
        seats_by_role: dict[GovernmentRole, int] = {role: 0 for role in GovernmentRole}
        for party in legislature.parties:
            for bloc in party.blocs:
                for entry in bloc.seats:
                    if entry.chamber is chamber.chamber:
                        seats_by_role[role_by_party[party.id]] += entry.seats
        composition = "  ".join(
            f"{_ROLE_LABELS[role]} {seats_by_role[role]}" for role in GovernmentRole
        )
        print(f"      authored seats: {composition}")

    print(f"    parties: {len(legislature.parties)}")
    for party in legislature.parties:
        print(
            f"      {party.id} ({party.name}) — {_ROLE_LABELS[party.government_role]}, "
            f"{len(party.blocs)} bloc(s)"
        )
        for bloc in party.blocs:
            seats = "  ".join(f"{entry.chamber.value} {entry.seats}" for entry in bloc.seats)
            print(f"        {bloc.id} ({bloc.name}): {seats or 'no seats'}")
            print(
                f"          discipline={_bps_to_percent_str(bloc.discipline_bps)} "
                f"relationship={_bps_to_percent_str(bloc.government_relationship_bps)} "
                f"tax_pref={_bps_to_percent_str(bloc.tax_preference_bps)} "
                f"spending_pref={_bps_to_percent_str(bloc.spending_preference_bps)}"
            )


def _print_capital_relationships(politics: PoliticalState) -> None:
    """(Phase 3B2A, §16) `inspect --capital`: every bloc's CURRENT `government_relationship_bps`,
    read directly from state. The political-capital figure itself is already printed unconditionally
    a few lines above this (like legitimacy) — this flag adds only what is genuinely opt-in: the
    per-bloc relationship table.

    Deliberately narrower than `--legislature`, which already shows this same field alongside
    the full authored composition (seats, discipline, preferences) — this flag exists for the
    player who only wants "what will next turn's investment be scored against", not the whole
    institutional table. Unlike `--legislature`'s relationship figure (still authored-looking in
    Phase 3B1), this one is genuinely live: slot 11 is `government_relationship_bps`'s only
    writer, so the value shown here can differ from what a fresh scenario authored, and a
    relationship-investment decision changes what it prints on the very next resolved turn.
    """
    legislature = politics.legislature
    if legislature is None:
        print("  bloc relationships:  none — this constitution has no legislature")
        return
    print("  bloc relationships:")
    rows = [
        (f"{party.id}/{bloc.id}", party.government_role, bloc.government_relationship_bps)
        for party in legislature.parties
        for bloc in party.blocs
    ]
    identity_width = max((len(identity) for identity, _, _ in rows), default=0)
    for identity, role, relationship_bps in rows:
        print(
            f"    {identity:<{identity_width}}  {_ROLE_LABELS[role]:<21} "
            f"{_bps_to_percent_str(relationship_bps):>8}"
        )


def _cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.state)
    save = _read_save(path)
    current = save.current_state()
    player = current.world.countries[current.world.player_country_id]
    problems = validate_history(save)

    print(f"save file: {path}")
    print(f"  save_format_version: {save.save_format_version}")
    print(f"  ruleset_version:     {save.ruleset_version}")
    print(f"  content_version:     {save.content_version}")
    print(f"  current_turn:        {save.current_turn()}")
    print(f"  entries:             {len(save.entries)} (entry_count={save.entry_count})")
    print(f"  player_country:      {player.id} ({player.name}), population={player.population}")
    if player.finance is not None:
        print(
            f"  treasury:            cash={format_money(player.treasury.cash_on_hand)} "
            f"debt={format_money(player.treasury.debt)} denars"
        )
    if player.economy is not None:
        # Unlike production/labor/tax-base figures (which are turn-local and only exist inside
        # a resolved TurnReport), resource endowments live in state itself and are available at
        # turn 0 — a fresh save can show them without having resolved anything yet.
        print("  resource endowments:")
        for deposit in player.economy.resource_deposits:
            unit = RESOURCE_UNITS[deposit.category]
            print(
                f"    {deposit.category.value}: remaining_stock={deposit.remaining_stock:,} {unit}"
            )
        if args.coefficients:
            # Read directly from state — never from data/scenarios/*.yaml, which is parsed only
            # once, at `new` — proving resource_output_coefficients travels with the save itself.
            print("  resource_output_coefficients:")
            for coefficient in player.economy.resource_output_coefficients:
                unit = RESOURCE_UNITS[coefficient.category]
                print(
                    f"    {coefficient.category.value}: "
                    f"real_output_per_unit={coefficient.real_output_per_unit:,} per {unit}"
                )

    if player.economy is not None and save.entries:
        latest_report = save.entries[-1].report()
        if latest_report is not None and latest_report.production is not None:
            production = latest_report.production
            print(
                f"  production (latest): total_employment={production.total_employment:,} "
                f"total_gross_output={production.total_gross_output:,} "
                "(fixed base-year output units, not money)"
            )
        if latest_report is not None and latest_report.tax_base_derivation is not None:
            derived = latest_report.tax_base_derivation.derived_tax_bases
            print(
                "  tax bases (latest): "
                f"personal={format_money(derived.personal_income)} "
                f"corporate={format_money(derived.corporate_profit)} "
                f"consumption={format_money(derived.taxable_consumption)} denars"
            )

    if player.politics is not None:
        # Read directly from state, like resource endowments above -- legitimacy and political
        # capital are turn-0-available state, not turn-local report detail.
        politics = player.politics
        print(f"  legitimacy:          {_bps_to_percent_str(politics.legitimacy_bps)}")
        print(
            f"  political capital:   {politics.political_capital:,} / "
            f"{politics.political_capital_capacity:,}"
        )
        if args.politics:
            axes = politics.constitution
            election = (
                f"every {axes.national_election_interval_turns} turns"
                if axes.national_election_interval_turns is not None
                else "none scheduled"
            )
            term_limit = (
                f"{axes.executive_term_limit_terms} terms"
                if axes.executive_term_limit_terms is not None
                else "none"
            )
            print(
                f"  constitution:        {axes.executive_system.value} / "
                f"{axes.executive_selection.value} / {axes.legislature.value} / "
                f"{axes.territorial_organization.value}"
            )
            print(
                f"                       judicial_review={axes.judicial_review.value} "
                f"amendment={axes.amendment_difficulty.value} "
                f"decree={axes.decree_authority.value}"
            )
            print(f"                       term_limit={term_limit}  national_election={election}")
            print(
                "  order support:       "
                f"{_bps_to_percent_str(politics.constitutional_order_support_bps)}   "
                "(authored acceptance of this constitutional order)"
            )
            if politics.economic_baseline is None:
                print("  economic baseline:   (none yet — no turn resolved)")
            else:
                baseline = politics.economic_baseline
                print(
                    f"  economic baseline:   turn {baseline.source_turn}  "
                    f"output={baseline.total_gross_output:,}  "
                    f"unemployment={_bps_to_percent_str(baseline.unemployment_rate_bps)}"
                )
        if args.legislature:
            _print_legislature_composition(politics)
        if args.capital:
            _print_capital_relationships(politics)

    if problems:
        print(f"  integrity:           INVALID ({len(problems)} problem(s))")
        for problem in problems:
            print(f"    - {problem}")
        return 1

    print("  integrity:           OK")
    return 0


def _print_finance_report(finance: FinanceReport) -> None:
    print("    finance:")
    print(
        f"      opening cash={format_money(finance.opening_cash)} "
        f"debt={format_money(finance.opening_debt)}"
    )
    print(
        f"      revenue: personal={format_money(finance.revenue.personal_income_tax)} "
        f"corporate={format_money(finance.revenue.corporate_tax)} "
        f"consumption={format_money(finance.revenue.consumption_tax)} "
        f"total={format_money(finance.revenue.total_revenue)}"
    )
    print(
        f"      spending: total={format_money(finance.total_program_spending)} "
        f"interest={format_money(finance.quarterly_interest_expense)}"
    )
    print(
        f"      pre_financing_balance={format_money(finance.pre_financing_balance)} "
        f"new_borrowing={format_money(finance.new_borrowing)}"
    )
    print(
        f"      closing cash={format_money(finance.closing_cash)} "
        f"debt={format_money(finance.closing_debt)}"
    )
    print(f"      reconciliation: {finance.reconciliation_status}")


def _print_labor_market_report(labor_market: LaborMarketReport) -> None:
    print("    labor_market:")
    print(
        f"      labor_force={labor_market.effective_labor_force:,} "
        f"employment={labor_market.total_employment:,} "
        f"unemployed={labor_market.unemployed_workers:,} "
        f"unfilled_jobs={labor_market.unfilled_jobs:,} "
        f"unemployment_rate={labor_market.unemployment_rate_bps / 100:g}%"
    )
    for sector in labor_market.sectors:
        print(
            f"      {sector.category.value}: required={sector.required_workers:,} "
            f"allocated={sector.allocated_workers:,} unfilled={sector.unfilled_workers:,}"
        )


def _print_resource_extraction_report(resources: ResourceExtractionReport) -> None:
    print("    resources:")
    print(
        f"      extraction_sector_workers={resources.extraction_sector_workers:,} "
        f"total_extraction_workers={resources.total_extraction_workers:,} "
        f"unassigned_resource_workers={resources.unassigned_resource_workers:,}"
    )
    utilization_bps = (
        (resources.extraction_sector_real_output * 10_000)
        // resources.extraction_sector_potential_output
        if resources.extraction_sector_potential_output > 0
        else 0
    )
    print(
        f"      extraction_sector_real_output={resources.extraction_sector_real_output:,} "
        f"potential={resources.extraction_sector_potential_output:,} "
        f"utilization={utilization_bps / 100:g}%"
    )
    for deposit in resources.deposits:
        unit = RESOURCE_UNITS[deposit.category]
        print(
            f"      {deposit.category.value}: opening={deposit.opening_stock:,} "
            f"regenerated={deposit.regenerated:,} extracted={deposit.extracted:,} "
            f"closing={deposit.closing_stock:,} {unit} "
            f"-> output={deposit.real_output_contribution:,} "
            f"(potential={deposit.potential_output_contribution:,}) "
            f"status={deposit.status.value}"
        )


def _print_production_report(production: ProductionReport) -> None:
    print("    production:")
    print(
        f"      total_employment={production.total_employment:,} workers "
        f"total_gross_output={production.total_gross_output:,} "
        "(fixed base-year output units, not money)"
    )
    for sector in production.sectors:
        print(
            f"      {sector.category.value}: actual_output={sector.actual_output:,} "
            f"capacity={sector.capacity_output:,} "
            f"utilization={sector.capacity_utilization_bps / 100:g}% "
            f"employed={sector.employed_workers:,} constraint={sector.constraint.value}"
        )


def _print_tax_base_derivation_report(derivation: TaxBaseDerivationReport) -> None:
    print("    tax_base_derivation:")
    print(
        f"      total_modeled_value_added={derivation.total_modeled_value_added:,} "
        f"total_labor_income={derivation.total_labor_income:,} "
        f"total_operating_surplus={derivation.total_operating_surplus:,} "
        "(fixed base-year output units, not money)"
    )
    print(
        "      derived_tax_bases: "
        f"personal={format_money(derivation.derived_tax_bases.personal_income)} "
        f"corporate={format_money(derivation.derived_tax_bases.corporate_profit)} "
        f"consumption={format_money(derivation.derived_tax_bases.taxable_consumption)} denars"
    )
    for sector in derivation.sectors:
        print(
            f"      {sector.category.value}: "
            f"modeled_value_added={sector.modeled_value_added:,} "
            f"labor_income={sector.labor_income:,} "
            f"operating_surplus={sector.operating_surplus:,} "
            f"personal={sector.personal_contribution:,} "
            f"corporate={sector.corporate_contribution:,} "
            f"consumption={sector.consumption_contribution:,}"
        )


def _print_political_report(political: PoliticalReport) -> None:
    print("    political:")
    axes = political.constitution
    election = (
        f"every {axes.national_election_interval_turns} turns"
        if axes.national_election_interval_turns is not None
        else "none scheduled"
    )
    term_limit = (
        f"{axes.executive_term_limit_terms} terms"
        if axes.executive_term_limit_terms is not None
        else "none"
    )
    print(
        f"      constitution: {axes.executive_system.value}/{axes.executive_selection.value}/"
        f"{axes.legislature.value}/{axes.territorial_organization.value} "
        f"judicial_review={axes.judicial_review.value} "
        f"amendment={axes.amendment_difficulty.value} decree={axes.decree_authority.value} "
        f"term_limit={term_limit} national_election={election} "
        f"digest={axes.constitution_digest[:8]}..."
    )
    print(f"      order support: {_bps_to_percent_str(political.constitutional_order_support_bps)}")
    print(
        f"      legitimacy: opening={_bps_to_percent_str(political.opening_legitimacy_bps)} "
        f"order_support={_bps_to_percent_str(political.order_support_contribution_bps)} "
        f"performance={_bps_to_percent_str(political.performance_contribution_bps)} -> "
        f"closing={_bps_to_percent_str(political.closing_legitimacy_bps)}"
    )
    if political.opening_economic_baseline is None:
        print("      opening baseline: (none — first resolved turn, performance contribution 0)")
    else:
        opening_baseline = political.opening_economic_baseline
        print(
            f"      opening baseline: turn {opening_baseline.source_turn} "
            f"output={opening_baseline.total_gross_output:,} "
            f"unemployment={_bps_to_percent_str(opening_baseline.unemployment_rate_bps)}"
        )
    print(
        "      observations: "
        f"output={political.current_total_gross_output:,} "
        f"unemployment={_bps_to_percent_str(political.current_unemployment_rate_bps)}"
    )
    closing_baseline = political.closing_economic_baseline
    print(
        f"      closing baseline: turn {closing_baseline.source_turn} "
        f"output={closing_baseline.total_gross_output:,} "
        f"unemployment={_bps_to_percent_str(closing_baseline.unemployment_rate_bps)}"
    )
    print(
        "      political capital: "
        f"opening={political.opening_political_capital:,} "
        f"regeneration=+{political.political_capital_regeneration:,} "
        f"spent={political.political_capital_spent:,} -> "
        f"closing={political.closing_political_capital:,} / "
        f"{political.political_capital_capacity:,}"
    )


def _print_legislative_report(legislative: LegislativeReport) -> None:
    """(Phase 3B1, §14) The ONE legislative renderer. Both live `resolve` output and historical
    `history --turn N` output call this — deliberately, because Phase 3A shipped a bug where
    `_cmd_history` had its own inline printing path and silently omitted a whole report section
    that `resolve` displayed. Two copies of this formatting would drift the same way.

    Every value printed below is read straight off the stored, already-self-validated
    `LegislativeReport`. Nothing here recomputes a vote, a support figure, a seat apportionment,
    whether the budget applied, or any capital arithmetic — those are the report's own 13
    validators' job, re-run on every construction and every history replay. This function is
    presentation only.
    """
    print("    legislative:")

    if legislative.outcome is LegislativeOutcome.NO_PROPOSAL:
        # No route, no chambers, no blocs — printing an empty table or a fabricated route would
        # imply a vote that never happened.
        print("      no budget proposal submitted")
        print(f"      political capital committed: {legislative.political_capital_committed:,}")
        return

    assert legislative.route is not None, "every non-NO_PROPOSAL outcome carries a route"
    print(
        f"      proposal: budget  route={legislative.route.value}  "
        f"outcome={legislative.outcome.value}"
    )
    print(
        f"      tax change:      {_format_bps_delta(legislative.tax_delta_bps)} "
        f"({legislative.tax_direction.value}, intensity "
        f"{_bps_to_percent_str(legislative.tax_intensity_bps)})"
    )
    print(
        f"      spending change: {format_money(legislative.opening_total_program_spending)} -> "
        f"{format_money(legislative.proposed_total_program_spending)} "
        f"({legislative.spending_direction.value}, intensity "
        f"{_bps_to_percent_str(legislative.spending_intensity_bps)})"
    )
    print(
        f"      political capital: committed {legislative.political_capital_committed:,} "
        f"of {legislative.opening_political_capital:,} opening"
    )

    if legislative.outcome is LegislativeOutcome.ENACTED_BY_DECREE:
        # No chamber table and no bloc table: a decree is not voted on, so there is nothing to
        # tabulate. Anything printed here would be invented.
        print("      enacted through executive decree authority — no chamber vote")
        return

    blocs_by_chamber: dict[LegislativeChamber, list[BlocVoteReport]] = {}
    for bloc in legislative.blocs:
        blocs_by_chamber.setdefault(bloc.chamber, []).append(bloc)

    for chamber in legislative.chambers:
        status = "PASSED" if chamber.passed else "FAILED"
        # Margin when passed, shortfall when failed — never both, and never a pooled figure:
        # each chamber is decided entirely against its own size and its own majority.
        detail = (
            f"margin +{chamber.supporting_seats - chamber.required_yes_seats}"
            if chamber.passed
            else f"short {chamber.shortfall_seats}"
        )
        print(
            f"      {chamber.chamber.value} chamber: {chamber.supporting_seats}/"
            f"{chamber.total_seats} supporting, majority {chamber.required_yes_seats} "
            f"-> {status} ({detail})"
        )
        print(
            f"        apportionment: target {chamber.target_total}, "
            f"{chamber.extras_awarded} extra seat(s) awarded on remainders"
        )
        rows = blocs_by_chamber.get(chamber.chamber, [])
        # Pad the whole `party/bloc` identity, not `bloc_id` alone: party ids vary in length, so
        # padding only the second half leaves the columns ragged and hard to compare down.
        identity_width = max((len(f"{r.party_id}/{r.bloc_id}") for r in rows), default=0)
        for bloc in rows:
            identity = f"{bloc.party_id}/{bloc.bloc_id}"
            bonus = "+1" if bloc.bonus_seat else " 0"
            print(
                f"        {identity:<{identity_width}}  "
                f"{bloc.government_role.value:<21} {bloc.seats:>4} seats  "
                f"effective={_bps_to_percent_str(bloc.effective_support_bps):>7}  "
                f"base {bloc.base_seats:>3} rem {bloc.remainder:>6} bonus {bonus} "
                f"-> {bloc.supporting_seats:>3}"
            )

    if legislative.outcome is LegislativeOutcome.FAILED_LEGISLATIVE:
        print("      budget NOT applied — existing tax policy and spending plan remain in force")


def _print_political_capital_ledger(political_capital: PoliticalCapitalReport) -> None:
    """(Phase 3B2A, §16) The ONE capital-ledger renderer, following the rule
    `_print_legislative_report` established: both live `resolve` output and historical
    `history --turn N` output call this one function, so the two print paths can never drift
    apart the way `_cmd_history`'s own inline path once silently omitted a whole section (Phase
    3A). Every value is read straight off the already-self-validated `PoliticalCapitalReport` —
    presentation only, nothing recomputed.
    """
    print("    political capital:")
    print(
        f"      opening {political_capital.opening_political_capital:,}  "
        f"committed {political_capital.total_committed:,}  "
        f"regeneration {political_capital.political_capital_regeneration:,}  "
        f"closing {political_capital.closing_political_capital:,} of "
        f"{political_capital.political_capital_capacity:,} capacity"
    )
    if not political_capital.expenditures:
        print("      no political capital committed")
        return

    print("      expenditures:")
    for expenditure in political_capital.expenditures:
        target = (
            f"{expenditure.party_id}/{expenditure.bloc_id}"
            if expenditure.party_id is not None and expenditure.bloc_id is not None
            else ""
        )
        print(
            f"        {expenditure.category.value:<28} {target:<28} {expenditure.political_capital:,}"
        )

    if political_capital.relationship_changes:
        print("      relationship changes:")
        for change in political_capital.relationship_changes:
            gap_pp = change.gap_bps / 100
            print(
                f"        {change.party_id}/{change.bloc_id}   "
                f"{_bps_to_percent_str(change.opening_relationship_bps)} -> "
                f"{_bps_to_percent_str(change.closing_relationship_bps)}  "
                f"({_format_bps_delta(change.applied_change_bps)} on a {gap_pp:g}pp gap, "
                f"{change.political_capital:,} capital)"
            )


def _print_report(report: TurnReport) -> None:
    print(f"  turn {report.resolved_turn} resolved:")
    for entry in report.entries:
        print(f"    [{entry.category}] {render_entry(entry)}")
    if report.labor_market is not None:
        _print_labor_market_report(report.labor_market)
    if report.resources is not None:
        _print_resource_extraction_report(report.resources)
    if report.production is not None:
        _print_production_report(report.production)
    if report.tax_base_derivation is not None:
        _print_tax_base_derivation_report(report.tax_base_derivation)
    if report.finance is not None:
        _print_finance_report(report.finance)
    if report.political is not None:
        _print_political_report(report.political)
    if report.legislative is not None:
        _print_legislative_report(report.legislative)
    if report.political_capital is not None:
        _print_political_capital_ledger(report.political_capital)
    not_implemented = [
        phase_id
        for phase_id, status in report.dev.phase_statuses.items()
        if status.value == "not_implemented"
    ]
    if not_implemented:
        print(f"    (dev) not yet implemented: {', '.join(not_implemented)}")


def _cmd_resolve(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    out_path = Path(args.out)
    if out_path.resolve() == state_path.resolve():
        print("error: --out must not be the same file as --state (inputs are never overwritten)")
        return 2

    if args.decisions_file is not None and args.turns != 1:
        print(
            "error: --decisions-file requires --turns 1 (a decisions file targets exactly one turn)"
        )
        return 2

    save = _read_save(state_path)
    print(f"resolving {args.turns} turn(s) from turn {save.current_turn()}")

    for _ in range(args.turns):
        if args.decisions_file is not None:
            decisions = _read_decisions_file(Path(args.decisions_file))
        else:
            current = save.current_state()
            decisions = DecisionSet(
                expected_turn=current.turn,
                expected_state_version=current.state_version,
                decisions=(),
            )
        # advance_game validates history + the decision set + the resolved
        # state, in that order, and raises before appending anything on any
        # failure — so a mid-batch failure here leaves `save` (this local
        # variable) pointing at the last good save and never reaches the
        # write below, matching "no partial output file."
        save = advance_game(save, decisions)
        report = save.entries[-1].report()
        assert report is not None, "a just-appended, non-genesis entry always has a report"
        _print_report(report)

    _write_save(out_path, save)
    final = save.current_state()
    print(
        f"final: turn={final.turn} state_version={final.state_version} "
        f"entries={len(save.entries)} -> wrote {out_path}"
    )
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    path = Path(args.state)
    save = _read_save(path)

    problems = validate_history(save)
    if problems:
        raise HistoryValidationError(problems)

    if args.turn is None:
        print(f"save file: {path}")
        print(f"  {len(save.entries)} entries (turns 0-{save.current_turn()})")
        for entry in save.entries:
            label = "genesis" if entry.turn == 0 else "turn   "
            print(f"    {label} {entry.turn}: entry_hash={entry.entry_hash[:16]}...")
        return 0

    # SnapshotNotFoundError is a MandateError; letting it propagate to
    # main()'s generic handler gives the same "error: ..." + exit 1 behavior
    # as every other domain error, for an invalid/unavailable turn number.
    entry = save.entry_at(args.turn)
    entry_state = entry.state()
    player = entry_state.world.countries[entry_state.world.player_country_id]

    print(f"turn {entry.turn}:")
    print(f"  entry_hash:          {entry.entry_hash}")
    print(f"  previous_entry_hash: {entry.previous_entry_hash}")
    print(f"  state_version:       {entry_state.state_version}")
    print(f"  player_country:      {player.id} ({player.name}), population={player.population}")

    report = entry.report()
    if report is None:
        print("  report:              (genesis — no turn was resolved to reach this state)")
    else:
        # report.resolved_turn is the turn *before* this one — the turn whose
        # decisions were resolved to produce this entry's state.
        print(f"  report (from resolving turn {report.resolved_turn}):")
        for report_entry in report.entries:
            print(f"    [{report_entry.category}] {render_entry(report_entry)}")
        if report.labor_market is not None:
            _print_labor_market_report(report.labor_market)
        if report.resources is not None:
            _print_resource_extraction_report(report.resources)
        if report.production is not None:
            _print_production_report(report.production)
        if report.tax_base_derivation is not None:
            _print_tax_base_derivation_report(report.tax_base_derivation)
        if report.finance is not None:
            _print_finance_report(report.finance)
        if report.political is not None:
            _print_political_report(report.political)
        if report.legislative is not None:
            # The SAME helper `_print_report` uses, never a second inline copy — see
            # `_print_legislative_report`'s docstring for the Phase 3A omission this prevents.
            _print_legislative_report(report.legislative)
        if report.political_capital is not None:
            # Same discipline as the legislative block just above (Phase 3B2A): the SAME shared
            # helper `_print_report` uses, never a second inline copy.
            _print_political_capital_ledger(report.political_capital)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mandate", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_new = subparsers.add_parser("new", help="create a new game from a scenario file")
    p_new.add_argument("--scenario", required=True, help="path to a scenario YAML file")
    p_new.add_argument("--out", required=True, help="path to write the new save file")
    p_new.add_argument("--seed", type=int, default=None, help="override the scenario's seed")
    p_new.set_defaults(func=_cmd_new)

    p_inspect = subparsers.add_parser("inspect", help="load a save and report its integrity status")
    p_inspect.add_argument("--state", required=True, help="path to a save file")
    p_inspect.add_argument(
        "--coefficients",
        action="store_true",
        help="also show the canonical resource_output_coefficients table, read directly from "
        "state (never re-read from scenario YAML)",
    )
    p_inspect.add_argument(
        "--politics",
        action="store_true",
        help="also show the full constitutional axis table and the persisted economic "
        "baseline, read directly from state",
    )
    p_inspect.add_argument(
        "--legislature",
        action="store_true",
        help="also show the authored legislature composition (chambers, seats, strict-majority "
        "thresholds, parties, blocs, roles and preferences) read directly from state. Shows no "
        "support tally: a tally depends on a specific proposal and appears only in a resolved "
        "turn's legislative report",
    )
    p_inspect.add_argument(
        "--capital",
        action="store_true",
        help="also show every bloc's CURRENT government relationship, read directly from state "
        "(Phase 3B2A: relationships are mutable, so this is this turn's live figure, not an "
        "authored constant). Shows no ledger: a ledger is turn-local and appears only in a "
        "resolved turn's political-capital report",
    )
    p_inspect.set_defaults(func=_cmd_inspect)

    p_resolve = subparsers.add_parser("resolve", help="resolve N turns and write a new save file")
    p_resolve.add_argument("--state", required=True, help="path to the input save file")
    p_resolve.add_argument("--turns", type=int, default=1, help="number of turns to resolve")
    p_resolve.add_argument("--out", required=True, help="path to write the resulting save file")
    p_resolve.add_argument(
        "--decisions-file",
        default=None,
        help="path to a JSON DecisionSet to apply (requires --turns 1)",
    )
    p_resolve.set_defaults(func=_cmd_resolve)

    p_history = subparsers.add_parser("history", help="list turns, or inspect one historical turn")
    p_history.add_argument("--state", required=True, help="path to a save file")
    p_history.add_argument("--turn", type=int, default=None, help="show one specific turn")
    p_history.set_defaults(func=_cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MandateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
