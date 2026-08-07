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
from app.simulation.report import (
    FinanceReport,
    LaborMarketReport,
    PoliticalReport,
    ProductionReport,
    ResourceExtractionReport,
    TaxBaseDerivationReport,
    TurnReport,
    TurnReportEntry,
)
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json, load_save_json
from app.simulation.state import RESOURCE_UNITS

# --- reason_id -> English rendering (presentation layer only; never stored) --

_TAX_FIELD_LABELS = {
    "personal_income_rate_bps": "Personal-income tax",
    "corporate_rate_bps": "Corporate tax",
    "consumption_rate_bps": "Consumption tax",
}


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
