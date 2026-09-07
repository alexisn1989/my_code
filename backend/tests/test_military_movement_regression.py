"""Military Movement, commit 5 -- the scoped quiet-turn regression against the frozen 0.14.0 save.

The honest baseline. Revision 2 claimed the complete `TurnReport` and the complete closing state
would be byte-identical across the ruleset bump; that claim is impossible and was withdrawn --
the ruleset adds required military state and a fourteenth report, so neither whole object can be
identical. What IS assertable is the seven comparisons below, each checked separately.

The frozen fixture is read here and NEVER rewritten, migrated or regenerated. It is also never
loaded through `load_save_json`: `SUPPORTED_CONTENT_VERSIONS` is `{"0.16.0"}`, so a 0.14.0 save is
refused by design, and `test_compatibility.py` owns proving that. Here it is read as raw JSON --
a frozen record of what the unmodified 0.14.0 engine produced from this exact recipe.

Recipe, matching how the fixture was generated at commit 2: `tiny_valid`, seed 42, two EMPTY
canonical `DecisionSet`s.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.content.scenarios import load_scenario_file
from app.core.rng import derive_rng
from app.simulation.decisions import DecisionSet
from app.simulation.phases import PHASE_IDS, PHASE_ORDER
from app.simulation.resolver import resolve_turn

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "military_movement_save_ruleset_0.14.0.json"
)
TINY_VALID = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "tiny_valid.yaml"

PLAYER = "arken"
BASELINE_TURNS = 2

#: The thirteen report subtrees that existed before this commit. Listed as literals rather than
#: derived from `TurnReport.model_fields`, so adding a fifteenth report later cannot silently
#: enlarge what this test claims to have compared.
THIRTEEN_PRE_EXISTING_REPORTS = (
    "labor_market",
    "resources",
    "production",
    "tax_base_derivation",
    "finance",
    "political",
    "legislative",
    "political_capital",
    "political_relationship",
    "election",
    "coup_unrest",
    "constitutional_amendment",
    "foreign_affairs",
)

#: The one of those thirteen that the LATER map-resources slice legitimately changes. `resources`
#: gained a ninth (`gold`) deposit row and `crude_oil`'s coefficient was re-authored to offset it,
#: so this subtree cannot be byte-identical to a record produced by an eight-category engine.
#: Named here and excluded from assertion 1 rather than deleted from the tuple above -- the tuple
#: still means "the thirteen that existed before commit 5", and the exclusion has to justify
#: itself in exactly one place. Assertion 1a then pins HOW it differs, so "changed" never becomes
#: "unchecked".
CHANGED_BY_THE_MAP_RESOURCES_SLICE = frozenset({"resources"})

TWELVE_BYTE_IDENTICAL_REPORTS = tuple(
    field
    for field in THIRTEEN_PRE_EXISTING_REPORTS
    if field not in CHANGED_BY_THE_MAP_RESOURCES_SLICE
)

#: Every RNG stream the engine drew from before this commit. `foreign_conflict_progress:{id}` is
#: omitted deliberately: it is parameterised by a conflict id, and `tiny_valid` resolves these two
#: turns with no conflict, so there is no such stream to compare. The nine below are the fixed
#: names, and `derive_rng` namespaces on (seed, turn, stream) -- so if a new substep had perturbed
#: any of them, these draws would differ.
PRE_EXISTING_RNG_STREAMS = (
    "coup_attempt",
    "coup_outcome",
    "election",
    "foreign_conflict_outbreak",
    "impeachment_attempt",
    "impeachment_outcome",
    "unrest_attempt",
    "unrest_outcome",
    "unrest_severity",
)

#: The state paths that differ because of the ruleset bump itself, beyond the excluded military
#: subtree -- precisely what the fixture exists to record.
EXPECTED_ENVELOPE_DIFFERENCES = {"content_version", "ruleset_version"}

EXPECTED_MAP_RESOURCES_DIFFERENCES = {
    f"world.countries.{PLAYER}.economy.resource_deposits",
    f"world.countries.{PLAYER}.economy.resource_output_coefficients",
    "world.strategic_map.rivers",
}
"""The three paths the map-resources slice authors, kept as their own set rather than folded into
the envelope set above so each named difference still says WHY it is there: authored economy
content (a ninth deposit, a ninth coefficient and crude_oil's offset) and authored map content
(rivers). None is a version stamp.

`world.strategic_map.rivers` is the ONLY map path here, which is the statement: no theater, route,
shape, centroid or vertex moved when rivers were authored. `test_scenario.py` makes the same claim
about the authored file; this makes it about the loaded state a real turn resolves against."""


# --------------------------------------------------------------------------
# The named exclusion helper, and nothing broader
# --------------------------------------------------------------------------


def strip_commit_five_additions(
    *, state: dict[str, Any] | None = None, report: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Remove EXACTLY the two paths commit 5 adds, from a state dict, a report dict, or both.

    Named, explicit and separately tested, because "excluding" must be a mechanism rather than a
    promise: a bug that removed one path too many would quietly hide a real regression, which is
    the entire failure mode this baseline exists to catch.

    Removes:
      * `world.countries[*].military`
      * `report["movement"]`

    and nothing else. Operates on a deep copy, so the caller's dict is untouched.
    """
    if (state is None) == (report is None):
        raise ValueError("pass exactly one of state= or report=")
    if state is not None:
        stripped = json.loads(json.dumps(state))
        for country in stripped["world"]["countries"].values():
            country.pop("military", None)
        return stripped
    stripped = json.loads(json.dumps(report))
    stripped.pop("movement", None)
    return stripped


def _differing_paths(live: Any, base: Any, path: str = "") -> list[str]:
    """Every leaf path at which two JSON structures differ. Used to make the assertions state
    WHAT differs rather than merely that something does."""
    if type(live) is not type(base):
        return [path or "<root>"]
    if isinstance(live, dict):
        out: list[str] = []
        for key in sorted(set(live) | set(base)):
            child = f"{path}.{key}" if path else key
            if key not in live or key not in base:
                out.append(child)
            else:
                out += _differing_paths(live[key], base[key], child)
        return out
    if isinstance(live, list):
        if len(live) != len(base):
            return [path or "<root>"]
        out = []
        for index, (a, b) in enumerate(zip(live, base, strict=True)):
            out += _differing_paths(a, b, f"{path}[{index}]")
        return out
    return [] if live == base else [path or "<root>"]


@pytest.fixture(scope="module")
def baseline() -> list[dict[str, Any]]:
    """The frozen 0.14.0 entries, as raw JSON. Read-only; the file is never written."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert raw["ruleset_version"] == "0.14.0"
    assert raw["content_version"] == "0.14.0"
    assert len(raw["entries"]) == BASELINE_TURNS + 1
    return [
        {
            "turn": entry["turn"],
            "state": json.loads(entry["state_json"]),
            "report": json.loads(entry["report_json"]) if entry["report_json"] else None,
            "decisions": entry["decisions_json"],
        }
        for entry in raw["entries"]
    ]


@pytest.fixture(scope="module")
def live() -> list[dict[str, Any]]:
    """The same recipe under this build: `tiny_valid`, two EMPTY canonical decision sets."""
    state = load_scenario_file(TINY_VALID)
    assert state.seed == 42, "the fixture was generated from this scenario's own seed"
    rows = [{"turn": state.turn, "state": json.loads(state.model_dump_json()), "report": None}]
    for _ in range(BASELINE_TURNS):
        resolution = resolve_turn(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(),
            ),
        )
        state = resolution.state
        rows.append(
            {
                "turn": state.turn,
                "state": json.loads(state.model_dump_json()),
                "report": json.loads(resolution.report.model_dump_json()),
            }
        )
    return rows


class TestTheExclusionHelperRemovesOnlyTwoPaths:
    """Anti-vacuity for the helper itself. Without these, a helper that stripped too much would
    make every comparison below pass for the wrong reason."""

    def test_it_removes_military_from_every_country_and_nothing_else(
        self, live: list[dict[str, Any]]
    ) -> None:
        state = live[-1]["state"]
        stripped = strip_commit_five_additions(state=state)
        assert _differing_paths(state, stripped) == [
            f"world.countries.{country}.military" for country in sorted(state["world"]["countries"])
        ]

    def test_it_removes_movement_from_a_report_and_nothing_else(
        self, live: list[dict[str, Any]]
    ) -> None:
        report = live[-1]["report"]
        stripped = strip_commit_five_additions(report=report)
        assert _differing_paths(report, stripped) == ["movement"]

    def test_it_does_not_mutate_its_input(self, live: list[dict[str, Any]]) -> None:
        state = live[-1]["state"]
        before = json.dumps(state, sort_keys=True)
        strip_commit_five_additions(state=state)
        assert json.dumps(state, sort_keys=True) == before

    def test_a_genuinely_unrelated_perturbation_is_still_detected(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """The load-bearing anti-vacuity case: perturb a field the helper does NOT remove, and the
        comparison must fail. A helper that stripped too much would swallow this."""
        perturbed = json.loads(json.dumps(live[-1]["state"]))
        perturbed["world"]["countries"][PLAYER]["treasury"]["cash"] = -12345
        stripped = strip_commit_five_additions(state=perturbed)
        differences = set(_differing_paths(stripped, baseline[-1]["state"]))
        assert f"world.countries.{PLAYER}.treasury.cash" in differences

    def test_it_refuses_an_ambiguous_call(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            strip_commit_five_additions()


class TestQuietTurnRegressionAgainstFrozenBaseline:
    def test_1_the_twelve_untouched_pre_existing_report_subtrees_are_byte_identical(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """`production`, `tax_base_derivation` and `finance` are in this list, which is the whole
        calibration claim of the map-resources slice proven against a frozen record from an engine
        that had never heard of gold: the resource catalogue grew by a category that really is
        extracted every turn, and the country's output, tax bases, revenue and treasury did not
        move by one minor unit."""
        for live_row, base_row in zip(live[1:], baseline[1:], strict=True):
            for field in TWELVE_BYTE_IDENTICAL_REPORTS:
                assert json.dumps(live_row["report"][field], sort_keys=True) == json.dumps(
                    base_row["report"][field], sort_keys=True
                ), f"turn {live_row['turn']}: {field}"

    def test_1a_the_resources_report_differs_only_where_the_ninth_deposit_lands(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """The excluded subtree, pinned as an EXACT difference set rather than skipped.

        Three leaves differ and no others -- in particular `extraction_sector_real_output` and
        `extraction_sector_potential_output` are absent from the set, which is the offset holding
        against a pre-gold record. The two worker counts move by exactly 500 in opposite
        directions, which is gold taking its miners out of the sector's existing slack rather than
        out of another deposit's allocation.
        """
        for live_row, base_row in zip(live[1:], baseline[1:], strict=True):
            live_resources = live_row["report"]["resources"]
            base_resources = base_row["report"]["resources"]
            assert _differing_paths(live_resources, base_resources) == [
                "deposits",
                "total_extraction_workers",
                "unassigned_resource_workers",
            ], f"turn {live_row['turn']}"

            assert len(base_resources["deposits"]) == 8
            assert len(live_resources["deposits"]) == 9
            live_rows = {row["category"]: row for row in live_resources["deposits"]}
            base_rows = {row["category"]: row for row in base_resources["deposits"]}
            assert set(live_rows) - set(base_rows) == {"gold"}

            # Every pre-existing deposit row is byte-identical except crude_oil, whose
            # coefficient was lowered by exactly what gold contributes.
            for category, base_deposit in base_rows.items():
                if category == "crude_oil":
                    continue
                assert json.dumps(live_rows[category], sort_keys=True) == json.dumps(
                    base_deposit, sort_keys=True
                ), f"turn {live_row['turn']}: {category}"
            assert _differing_paths(live_rows["crude_oil"], base_rows["crude_oil"]) == [
                "potential_output_contribution",
                "real_output_contribution",
                "real_output_per_unit",
            ], f"turn {live_row['turn']}"
            # Crude oil's PHYSICAL extraction is untouched -- same stock, same capacity, same
            # workers, same barrels. Only the coefficient that converts those barrels to output
            # moved, and it moved by exactly gold's contribution.
            assert live_rows["crude_oil"]["extracted"] == base_rows["crude_oil"]["extracted"]
            assert (
                base_rows["crude_oil"]["real_output_contribution"]
                - live_rows["crude_oil"]["real_output_contribution"]
                == live_rows["gold"]["real_output_contribution"]
            )

            assert (
                live_resources["total_extraction_workers"]
                - base_resources["total_extraction_workers"]
                == 500
            )
            assert (
                base_resources["unassigned_resource_workers"]
                - live_resources["unassigned_resource_workers"]
                == 500
            )

    def test_2_w1_foreign_affairs_rows_and_outcomes_are_byte_identical(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """Called out separately from the thirteen because slot 8 is the phase movement now shares
        with the W1 progression -- if anything reordered or perturbed it, it would show here."""
        for live_row, base_row in zip(live[1:], baseline[1:], strict=True):
            assert json.dumps(live_row["report"]["foreign_affairs"], sort_keys=True) == json.dumps(
                base_row["report"]["foreign_affairs"], sort_keys=True
            )

    def test_3_closing_state_differs_only_by_military_the_envelope_and_this_slices_authoring(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """Stated as an EXACT remaining-difference set, not as a wider exclusion.

        The frozen plan's own wording for this comparison is "closing state excluding
        `countries[*].military`". Measured against the real fixture, two further scalars also
        differ -- `ruleset_version` and `content_version` -- and they cannot not differ: they ARE
        the 0.14.0 -> 0.15.0 bump the fixture exists to record. Rather than widen the exclusion
        helper (which would weaken every comparison above), the entire remaining difference is
        enumerated and pinned here. This is strictly stronger than an exclusion: a third differing
        field fails this test instead of disappearing into it.
        """
        for live_row, base_row in zip(live, baseline, strict=True):
            differences = set(
                _differing_paths(
                    strip_commit_five_additions(state=live_row["state"]), base_row["state"]
                )
            )
            assert differences == (
                EXPECTED_ENVELOPE_DIFFERENCES | EXPECTED_MAP_RESOURCES_DIFFERENCES
            ), f"turn {live_row['turn']}: {sorted(differences)}"

    def test_3a_the_envelope_difference_is_exactly_the_ruleset_bump(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """So the pinned set above can never quietly absorb a different meaning."""
        assert live[-1]["state"]["ruleset_version"] == "0.16.0"
        assert live[-1]["state"]["content_version"] == "0.16.0"
        assert baseline[-1]["state"]["ruleset_version"] == "0.14.0"
        assert baseline[-1]["state"]["content_version"] == "0.14.0"

    def test_4_military_state_is_unchanged_from_opening_on_a_quiet_turn(
        self, live: list[dict[str, Any]]
    ) -> None:
        opening = live[0]["state"]["world"]["countries"]
        for row in live[1:]:
            closing = row["state"]["world"]["countries"]
            for country_id, country in closing.items():
                assert json.dumps(country["military"], sort_keys=True) == json.dumps(
                    opening[country_id]["military"], sort_keys=True
                ), f"turn {row['turn']}: {country_id}"

    def test_5_the_movement_report_is_present_and_empty(self, live: list[dict[str, Any]]) -> None:
        for row in live[1:]:
            assert row["report"]["movement"] == {"movements": []}

    def test_6_every_pre_existing_rng_stream_produced_identical_draws(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """Compares what the streams ACTUALLY produced in the two runs, not `derive_rng` against
        itself -- which would be a tautology, since it is a pure function of (seed, turn, stream).

        Each path below is the direct observable output of one stream: the outbreak draw and its
        selection, the election's polling swing, and the attempt/outcome of each of the three
        government-survival channels. Assertion 1 covers these as part of whole subtrees; they are
        pinned individually here so a regression names the stream it broke.
        """
        assert live[0]["state"]["seed"] == baseline[0]["state"]["seed"] == 42
        draw_paths = (
            ("foreign_affairs", "outbreak", "occurrence_draw"),
            ("foreign_affairs", "outbreak", "selection_draw"),
            ("election", "polling_uncertainty_bps"),
            ("coup_unrest", "coup", "attempted"),
            ("coup_unrest", "coup", "succeeded"),
            ("coup_unrest", "popular_unrest", "attempted"),
            ("coup_unrest", "popular_unrest", "outcome"),
            ("coup_unrest", "impeachment", "attempted"),
            ("coup_unrest", "impeachment", "succeeded"),
        )
        for live_row, base_row in zip(live[1:], baseline[1:], strict=True):
            for path in draw_paths:
                live_value: Any = live_row["report"]
                base_value: Any = base_row["report"]
                for key in path:
                    live_value = live_value[key]
                    base_value = base_value[key]
                assert live_value == base_value, f"turn {live_row['turn']}: {'.'.join(path)}"

    def test_6a_a_new_stream_name_cannot_perturb_an_existing_stream(self) -> None:
        """Why the property above is structural rather than lucky: `derive_rng` namespaces on the
        stream name, so streams are independent sequences. A future substep drawing from a fresh
        name therefore cannot consume or shift an existing stream's draws -- and the nine existing
        names are genuinely distinct, so this is not vacuous."""
        sequences = {
            stream: [derive_rng(42, 1, stream).random() for _ in range(3)]
            for stream in (*PRE_EXISTING_RNG_STREAMS, "military_movement")
        }
        distinct = {tuple(values) for values in sequences.values()}
        assert len(distinct) == len(PRE_EXISTING_RNG_STREAMS) + 1
        assert sequences["military_movement"] not in [
            sequences[stream] for stream in PRE_EXISTING_RNG_STREAMS
        ]

    def test_7_phase_ids_and_phase_ordering_are_unchanged(
        self, live: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> None:
        """Two separate statements, because the stored form supports only one of them.

        `dev.phase_statuses` is serialized as a JSON object with SORTED keys, so the frozen
        fixture records the phase id SET and its size -- not the execution order. Both runs'
        stored key sets must therefore be identical, and the ORDER is asserted against
        `PHASE_ORDER` itself, whose slot-8 entry gained a substep rather than a phase.

        Claiming the fixture proves ordering would be reading something out of it that is not
        there.
        """
        frozen_ids = list(baseline[-1]["report"]["dev"]["phase_statuses"])
        assert len(frozen_ids) == 15
        assert set(PHASE_IDS) == set(frozen_ids)
        # Compared as SETS on both sides: the fixture's `report_json` was written through
        # `canonical_dumps`, which sorts object keys, while a live `model_dump_json()` preserves
        # insertion order. The two serializations differ in key order for reasons that have
        # nothing to do with phase ordering.
        assert set(live[-1]["report"]["dev"]["phase_statuses"]) == set(frozen_ids)

        assert len(PHASE_ORDER) == 15
        assert PHASE_IDS[7] == "resolve_military_movement_and_combat"
        assert PHASE_IDS[8] == "apply_casualties_occupation_disruption_war_costs"

    def test_the_frozen_fixture_is_not_loadable_by_this_build(self) -> None:
        """Guards the whole file against a future 'fix' that migrates the fixture: it must remain
        a 0.14.0 save that this build refuses, exactly as `test_compatibility.py` requires."""
        from app.simulation.save_format import SUPPORTED_CONTENT_VERSIONS

        assert "0.14.0" not in SUPPORTED_CONTENT_VERSIONS
