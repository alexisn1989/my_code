"""Version compatibility policy tests (product spec §30, ADR 0002/0003).

The centerpiece is `phase1_save_ruleset_0.1.0.json` — a save frozen with
unmodified Phase-1 code, committed to `tests/fixtures/` *before*
`RULESET_VERSION` was bumped to `0.2.0` for Phase 2A. There is no other way
to produce a genuine pre-2A save to test rejection against: once the bump
landed, `mandate.simulation.state.RULESET_VERSION` only ever stamps `0.2.0`
onto new games.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.content.scenarios import load_scenario_file
from app.core.errors import (
    UnsupportedContentVersionError,
    UnsupportedRulesetVersionError,
    UnsupportedSaveFormatVersionError,
)
from app.saves import read_save_file
from app.simulation.save_format import load_save_json
from app.simulation.state import RULESET_VERSION

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PHASE1_SAVE_PATH = FIXTURES_DIR / "phase1_save_ruleset_0.1.0.json"
PHASE2A_SAVE_PATH = FIXTURES_DIR / "phase2a_save_ruleset_0.2.0.json"
PHASE2B1_SAVE_PATH = FIXTURES_DIR / "phase2b1_save_ruleset_0.3.0.json"
PHASE2B2_SAVE_PATH = FIXTURES_DIR / "phase2b2_save_ruleset_0.4.0.json"
PHASE2B3_SAVE_PATH = FIXTURES_DIR / "phase2b3_save_ruleset_0.5.0.json"
PHASE2C1_SAVE_PATH = FIXTURES_DIR / "phase2c1_save_ruleset_0.6.0.json"
PHASE2C2_SAVE_PATH = FIXTURES_DIR / "phase2c2_save_ruleset_0.7.0.json"
PHASE3B1_SAVE_PATH = FIXTURES_DIR / "phase3b1_save_ruleset_0.9.0.json"
PHASE3B2B_SAVE_PATH = FIXTURES_DIR / "phase3b2b_save_ruleset_0.11.0.json"
"""Phase 3A's (`"0.8.0"`) and Phase 3B2A's (`"0.10.0"`) frozen fixtures exist on disk but were
never wired into a rejection test here -- a pre-existing gap, not a Phase 3C defect, left flagged
rather than silently bundled into this fix (the same "note, don't bundle" discipline
`test_legislative_neutrality.py`'s TEST-1 note already documents elsewhere in this codebase)."""

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def test_frozen_phase1_save_fixture_declares_the_old_ruleset_version() -> None:
    # Sanity check on the fixture itself, so a future accidental regeneration
    # with the *current* code (which would make every test below vacuous)
    # fails loudly right here instead of silently.
    raw = json.loads(PHASE1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.1.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    raw_text = read_save_file(PHASE1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.1.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message  # "nothing was modified" framing


def test_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """A save with both an unsupported ruleset_version *and* completely garbage
    entry state must fail with the ruleset error, not a state-parsing error —
    proving `check_compatibility` runs before any entry's state/decisions/report
    JSON is ever touched."""
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible")


def test_unsupported_future_ruleset_version_is_rejected() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["ruleset_version"] = "99.0.0"
    for entry in raw["entries"]:
        entry["ruleset_version"] = "99.0.0"

    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="future")
    assert "99.0.0" in str(exc_info.value)


def test_unsupported_content_version_is_rejected_specifically_not_ruleset() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    # Give it a supported ruleset so the *content* check is what's exercised.
    raw["ruleset_version"] = RULESET_VERSION
    for entry in raw["entries"]:
        entry["ruleset_version"] = RULESET_VERSION

    with pytest.raises(UnsupportedContentVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="bad-content-version")
    assert "0.1.0" in str(exc_info.value)


def test_unsupported_save_format_version_is_rejected_specifically() -> None:
    raw = json.loads(read_save_file(PHASE1_SAVE_PATH))
    raw["save_format_version"] = 999

    with pytest.raises(UnsupportedSaveFormatVersionError) as exc_info:
        load_save_json(json.dumps(raw), source="bad-envelope")
    assert "999" in str(exc_info.value)


def test_all_three_version_errors_are_distinct_types() -> None:
    assert UnsupportedSaveFormatVersionError is not UnsupportedRulesetVersionError
    assert UnsupportedRulesetVersionError is not UnsupportedContentVersionError
    assert UnsupportedSaveFormatVersionError is not UnsupportedContentVersionError


# --- Phase 2A -> Phase 2B1 ruleset bump (mirrors the Phase 1 -> 2A fixture) --
#
# `phase2a_save_ruleset_0.2.0.json` was frozen with unmodified Phase-2A code
# (no sector production, no EconomyState) *before* RULESET_VERSION was bumped
# to 0.3.0 for Phase 2B1 — the same one-shot-only sequencing as the Phase-1
# fixture above.


def test_frozen_phase2a_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2A_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.2.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2a_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via
    `player_economy_required` — proving the fixture was frozen *before* the
    bump (R1 sequencing risk): compatibility is checked before any entry
    payload is parsed at all, so the missing-economy invariant is never even
    reached for this save.
    """
    raw_text = read_save_file(PHASE2A_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2A_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.2.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2a_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2A_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2a")


# --- Phase 2B1 -> Phase 2B2 ruleset bump -------------------------------------
#
# `phase2b1_save_ruleset_0.3.0.json` was frozen with unmodified Phase-2B1 code (production
# sectors exist, but tax bases are still authored, not derived) *before* RULESET_VERSION was
# bumped to 0.4.0 for Phase 2B2 — mirroring the Phase 1 -> 2A and Phase 2A -> 2B1 fixtures.


def test_frozen_phase2b1_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.3.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `tax_base_coefficients` field or `player_economy_required` — proving compatibility is
    checked before any entry payload is parsed, and that the fixture was frozen before the
    bump (sequencing risk, same as every prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.3.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b1_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b1")


# --- Phase 2B2 -> Phase 2B3 ruleset bump -------------------------------------
#
# `phase2b2_save_ruleset_0.4.0.json` was frozen with unmodified Phase-2B2 code (tax bases are
# production-derived, but employment is still scenario-authored) *before* RULESET_VERSION was
# bumped to 0.5.0 for Phase 2B3 — mirroring every prior fixture above.


def test_frozen_phase2b2_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B2_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.4.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b2_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `effective_labor_force_share_bps` field — proving compatibility is checked before any entry
    payload is parsed, and that the fixture was frozen before the bump (sequencing risk, same
    as every prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B2_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B2_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.4.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b2_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B2_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b2")


# --- Phase 2B3 -> Phase 2C1 ruleset bump (T19) --------------------------------
#
# `phase2b3_save_ruleset_0.5.0.json` was frozen with unmodified Phase-2B3 code (labor allocation
# derives employment, but there are no resource endowments at all) *before* RULESET_VERSION was
# bumped to 0.6.0 for Phase 2C1 — mirroring every prior fixture above.


def test_frozen_phase2b3_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2B3_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.5.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2b3_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Rejected specifically via the ruleset-version gate, not incidentally via a missing
    `resource_deposits` field — proving compatibility is checked before any entry payload is
    parsed, and that the fixture was frozen before the bump (sequencing risk, same as every
    prior ruleset bump).
    """
    raw_text = read_save_file(PHASE2B3_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2B3_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.5.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2b3_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2B3_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2b3")


def test_frozen_phase2c1_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2C1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.6.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2c1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """T27: rejected specifically via the ruleset-version gate, not incidentally via a missing
    `resource_output_coefficients` field — proving compatibility is checked before any entry
    payload is parsed, and that the fixture was frozen (genuinely, with the unmodified 0.6.0
    engine) before the Phase 2C2 bump — no equality assertion against any 2C2 save anywhere in
    this test (§10, R7): rejection alone is what's asserted.
    """
    raw_text = read_save_file(PHASE2C1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2C1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.6.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2c1_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    raw = json.loads(read_save_file(PHASE2C1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2c1")


# --- Phase 2C2 -> Phase 3A ruleset bump (T-X1) --------------------------------
#
# `phase2c2_save_ruleset_0.7.0.json` was frozen with unmodified Phase-2C2 code (extraction drives
# sector output, but there is no constitution, legitimacy or political capital at all) *before*
# RULESET_VERSION was bumped to 0.8.0 for Phase 3A — mirroring every prior fixture above.


def test_frozen_phase2c2_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE2C2_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.7.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase2c2_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """T-X1: rejected specifically via the ruleset-version gate, not incidentally via a missing
    `politics` field — proving compatibility is checked before any entry payload is parsed, and
    that the fixture was frozen (genuinely, with the unmodified 0.7.0 engine) before the Phase 3A
    bump. No equality assertion against any 3A save anywhere in this test: rejection alone is
    what's asserted.
    """
    raw_text = read_save_file(PHASE2C2_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE2C2_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.7.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase2c2_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """T-X1: even a corrupted entry payload does not change which error fires -- the version gate
    runs first, regardless of what garbage the payload contains."""
    raw = json.loads(read_save_file(PHASE2C2_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-2c2")


# --- Phase 3B1 -> Phase 3B2A ruleset bump (T18) -------------------------------
#
# `phase3b1_save_ruleset_0.9.0.json` (plan commit 1) was frozen with unmodified Phase-3B1 code
# *before* RULESET_VERSION was bumped to 0.10.0 for Phase 3B2A -- mirroring every prior fixture
# above. Unlike the earlier fixtures it carries a real `LegislativeReport` on two of its three
# resolved turns (a passed legislative vote and a decree), so rejection is proven against a
# payload that actually exercises the structure this phase changes, not a trivial one.


def test_frozen_phase3b1_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE3B1_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.9.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase3b1_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """T18: rejected specifically via the ruleset-version gate, not incidentally via a decision
    union that can't parse a bare `{"kind": "budget", ...}` payload without the new report field,
    or any other structural difference -- proving compatibility is checked before any entry
    payload is parsed."""
    raw_text = read_save_file(PHASE3B1_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE3B1_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.9.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase3b1_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """Even a corrupted entry payload does not change which error fires -- the version gate runs
    first, regardless of what garbage the payload contains."""
    raw = json.loads(read_save_file(PHASE3B1_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-3b1")


def test_frozen_phase3b2b_save_fixture_declares_the_old_ruleset_version() -> None:
    raw = json.loads(PHASE3B2B_SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.11.0"
    assert raw["ruleset_version"] != RULESET_VERSION


def test_phase3b2b_save_is_rejected_with_an_actionable_ruleset_version_error() -> None:
    """Gate 3C1: rejected specifically via the ruleset-version gate. Before the bump to `0.12.0`
    that this test proves, the fixture's genuinely stale schema (float institution/population
    metrics, no `election` report) silently loaded as if current and only failed deep inside
    `GameState` validation with a raw `ValidationError` on first access -- exactly the "ugly crash
    instead of a clean rejection" this gate exists to prevent."""
    raw_text = read_save_file(PHASE3B2B_SAVE_PATH)
    with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
        load_save_json(raw_text, source=str(PHASE3B2B_SAVE_PATH))

    message = str(exc_info.value)
    assert "0.11.0" in message
    assert RULESET_VERSION in message
    assert "not loaded" in message


def test_phase3b2b_save_compatibility_is_checked_before_any_entry_payload_is_parsed() -> None:
    """Even a corrupted entry payload does not change which error fires -- the version gate runs
    first, regardless of what garbage the payload contains."""
    raw = json.loads(read_save_file(PHASE3B2B_SAVE_PATH))
    raw["entries"][0]["state_json"] = "{not even valid json"

    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(json.dumps(raw), source="corrupted-and-incompatible-3b2b")


def test_ruleset_0_12_0_covers_the_full_twelve_report_shape() -> None:
    """Gate 3C3: `RULESET_VERSION` was bumped exactly once, at Gate 3C1, for the whole of Phase
    3C -- not once per gate. This proves that single bump's rationale actually covers what Gate
    3C3 added too: a real `resolve_turn` call produces all twelve top-level Phase-3C reports,
    including `constitutional_amendment`, still true today even though `RULESET_VERSION` has
    since moved on again (External Wars Gate W1 bumped `"0.12.0" -> "0.13.0"` for its own,
    unrelated thirteenth report) -- no *further* Phase-3C-specific bump was ever required."""
    from app.simulation.decisions import DecisionSet
    from app.simulation.resolver import resolve_turn

    state = load_scenario_file(SCENARIOS_DIR / "tiny_valid.yaml")
    assert state.ruleset_version == RULESET_VERSION == "0.13.0"
    decisions = DecisionSet(
        expected_turn=state.turn, expected_state_version=state.state_version, decisions=()
    )
    report = resolve_turn(state, decisions).report
    assert report.election is not None
    assert report.coup_unrest is not None
    assert report.constitutional_amendment is not None
    assert report.constitutional_amendment.proposed is False


def test_no_migration_is_fabricated_for_a_0_9_0_save() -> None:
    """A 0.9.0 save has no expenditure ledger and no relationship-investment decisions to have
    ever carried. Nothing here invents an empty `PoliticalCapitalReport` to let the save through
    with a plausible-looking gap -- rejection is the only correct behaviour, because a fabricated
    empty ledger would assert the government committed nothing on turns whose real commitments
    (if any) are simply unrecorded, which is a lie about history in a format whose entire purpose
    is that it cannot lie."""
    with pytest.raises(UnsupportedRulesetVersionError):
        load_save_json(read_save_file(PHASE3B1_SAVE_PATH), source=str(PHASE3B1_SAVE_PATH))


# --- T25: the scenario content-version bump changed exactly one line (historical, 0.10.0 ->
# --- 0.11.0 only; retired below in favor of the Gate 3C1 bump's own semantic proof) -----------


@pytest.mark.parametrize(
    "scenario_name", ["tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml"]
)
def test_scenario_content_version_is_current(scenario_name: str) -> None:
    """Every shipped scenario declares the current content version -- the load-bearing half of
    the byte-for-byte reproduction proof this test used to run for the 0.10.0 -> 0.11.0 bump
    (Phase 3B2B, still true of that historical transition, but no longer reproducible against the
    NOW-current file without fabricating the intermediate 0.11.0 text). Gate 3C1's own bump
    (0.11.0 -> 0.12.0) gets its own semantic proof below instead of a text-diff reproduction,
    since it changes field TYPES (float -> strict bps) as well as adding/removing whole rows --
    not a case a line-level text rebuild can express cleanly."""
    state = load_scenario_file(SCENARIOS_DIR / scenario_name)
    assert state.content_version == "0.13.0"


@pytest.mark.parametrize(
    "scenario_name", ["tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml"]
)
def test_gate_3c1_bps_conversion_covers_every_metric(scenario_name: str) -> None:
    """Every `InstitutionState`/`PopulationGroupState` metric is a genuine basis-points value in
    `[0, 10_000]` -- Pydantic's strict-int validation already guarantees the TYPE (a 0.11.0 float
    like `80.0` is rejected outright, proven by `test_phase3b2b_save_is_rejected_...` above), but
    this proves the CONVERSION was actually applied uniformly across every field and every row,
    not merely that the schema now demands it. `population_share` is deliberately excluded (it
    stays a `[0, 1]` float proportion, never a metric -- §2.1)."""
    state = load_scenario_file(SCENARIOS_DIR / scenario_name)
    for country in state.world.countries.values():
        for institution in country.institutions:
            for metric in (
                institution.loyalty,
                institution.power,
                institution.competence,
                institution.corruption,
            ):
                assert 0 <= metric <= 10_000
                assert metric % 100 == 0, (
                    f"{scenario_name}/{country.id}/{institution.id}: {metric} is not a clean "
                    "hundred-bps value (a real ×100 conversion should never produce one)"
                )
        for group in country.population_groups:
            for metric in (
                group.political_influence,
                group.approval,
                group.trust,
                group.organization,
                group.radicalization,
            ):
                assert 0 <= metric <= 10_000
                assert metric % 100 == 0, (
                    f"{scenario_name}/{country.id}/{group.id}: {metric} is not a clean "
                    "hundred-bps value"
                )


def test_gate_3c1_redundant_legislature_institution_row_is_gone() -> None:
    """POL-2's exact complaint: an `id: legislature` institution row duplicated
    `LegislatureState`, which already carries this country's real legislative composition.
    Removed from `tiny_valid`/`decree_state` (the two scenarios that authored it); `deficit_demo`
    never had one."""
    for scenario_name in ("tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml"):
        state = load_scenario_file(SCENARIOS_DIR / scenario_name)
        player = state.world.countries[state.world.player_country_id]
        institution_ids = {institution.id for institution in player.institutions}
        assert "legislature" not in institution_ids, scenario_name


@pytest.mark.parametrize(
    "scenario_name", ["tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml"]
)
def test_gate_3c1_every_scenario_authors_exactly_one_military_institution(
    scenario_name: str,
) -> None:
    """The coup channel's guaranteed input (`player_military_institution_required`,
    `simulation.invariants`): every scenario's player country authors exactly one `id: military`
    row. `deficit_demo` gained this row new in Gate 3C1 -- it previously authored only
    `executive`."""
    state = load_scenario_file(SCENARIOS_DIR / scenario_name)
    player = state.world.countries[state.world.player_country_id]
    military_rows = [
        institution for institution in player.institutions if institution.id == "military"
    ]
    assert len(military_rows) == 1, scenario_name


@pytest.mark.parametrize(
    "scenario_name", ["tiny_valid.yaml", "deficit_demo.yaml", "decree_state.yaml"]
)
def test_every_bloc_baseline_equals_its_opening_relationship(scenario_name: str) -> None:
    """The design rule every scenario author must follow, established at 0.11.0 and unchanged
    since: initially authored equal, so turn 1 opens at zero deviation and decay is a no-op until
    something moves the relationship.
    Reject-not-normalize -- the loader never defaults one field from the other -- so this is a
    genuine content fact about the three shipped files, not something the schema enforces."""
    state = load_scenario_file(SCENARIOS_DIR / scenario_name)
    player = state.world.countries[state.world.player_country_id]
    assert player.politics is not None
    assert player.politics.legislature is not None
    for party in player.politics.legislature.parties:
        for bloc in party.blocs:
            assert bloc.baseline_government_relationship_bps == bloc.government_relationship_bps, (
                f"{scenario_name}: {party.id}/{bloc.id} authored baseline does not match opening "
                "relationship"
            )
