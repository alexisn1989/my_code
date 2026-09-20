"""Commit 8: the portrait reference, and the four boundaries that keep it honest.

A portrait is the one field in this slice the engine never reads. That makes it unusually easy to
get subtly wrong — nothing downstream fails when a depiction is missing, mismatched or invented —
so the guarantees are pinned here rather than left to the renderer to get right.
"""

from __future__ import annotations

import json
import pathlib
import re
import typing

import pytest
from pydantic import ValidationError

from app.api.projections import (
    ForeignAssistanceCounterpartyOption,
    ProjectedPromiseStatus,
    ProjectedPromiseTermKind,
    build_decision_options,
)
from app.content.scenarios import load_scenario_file
from app.simulation.promises import PromiseStatus, PromiseTermKind
from app.simulation.save_format import (
    SUPPORTED_CONTENT_VERSIONS,
    UnsupportedContentVersionError,
    UnsupportedRulesetVersionError,
    load_save_json,
)
from app.simulation.state import RULESET_VERSION, GameState
from tests.conftest import SCENARIO_DIR

SCENARIOS = ("tiny_valid.yaml", "decree_state.yaml", "deficit_demo.yaml")


def _state(name: str) -> GameState:
    return load_scenario_file(SCENARIO_DIR / name)


class TestTheProjectedLiteralsEqualTheProductionEnums:
    """The projection spells the vocabulary a second time, so the two must be proved equal.

    Set equality, never containment: a projection that DROPPED a member would pass a subset check
    while silently making that term or status unrepresentable on the wire.
    """

    def test_the_term_kind_literal_equals_the_promise_term_kind_alias(self) -> None:
        assert set(typing.get_args(ProjectedPromiseTermKind)) == set(
            typing.get_args(PromiseTermKind)
        )

    def test_the_status_literal_equals_the_promise_status_enum(self) -> None:
        assert set(typing.get_args(ProjectedPromiseStatus)) == {
            status.value for status in PromiseStatus
        }

    def test_neither_literal_is_merely_a_string(self) -> None:
        """Anti-vacuity: `get_args` of a bare `str` is empty, so both assertions above would pass
        vacuously if a field were ever widened back to `str`."""
        assert typing.get_args(ProjectedPromiseTermKind)
        assert typing.get_args(ProjectedPromiseStatus)


class TestEveryProjectedPortraitIsCopiedFromState:
    """All four row types copy `CharacterState.portrait_ref` VERBATIM — never derived, never
    defaulted, never inferred from `character_id`."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_bargain_counterparties_copy_the_authored_ref(self, scenario: str) -> None:
        state = _state(scenario)
        rows = build_decision_options(state).legislative_bargain_counterparties
        assert rows, scenario
        for row in rows:
            assert row.portrait_ref == state.world.characters[row.character_id].portrait_ref

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_foreign_counterparties_copy_the_authored_ref(self, scenario: str) -> None:
        state = _state(scenario)
        rows = build_decision_options(state).foreign_assistance_counterparties
        assert rows, scenario
        for row in rows:
            if row.counterpart_character_id is None:
                continue
            expected = state.world.characters[row.counterpart_character_id].portrait_ref
            assert row.counterpart_portrait_ref == expected

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_promise_options_copy_the_authored_ref(self, scenario: str) -> None:
        state = _state(scenario)
        rows = build_decision_options(state).promise_options
        assert rows, scenario
        for row in rows:
            expected = state.world.characters[row.character_id].portrait_ref
            assert row.character_portrait_ref == expected

    def test_active_promises_copy_the_authored_ref(self) -> None:
        """Built through the resolver, because a fresh scenario carries no promises — and because
        an active promise's character is precisely one EXCLUDED from `promise_options`, so this row
        cannot borrow a portrait from a sibling."""
        from app.simulation.decisions import DecisionSet, PromiseDecision
        from app.simulation.resolver import resolve_turn

        state = _state("tiny_valid.yaml")
        option = build_decision_options(state).promise_options[0]
        resolved = resolve_turn(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(
                    PromiseDecision(
                        action="make",
                        character_id=option.character_id,
                        term_kind=option.term_kind,
                        subject_id=option.subject_id,
                        deadline_turn=option.earliest_legal_deadline,
                    ),
                ),
            ),
        ).state

        views = build_decision_options(resolved).active_promises
        assert views, "the resolved turn must leave a live promise"
        offered = {row.character_id for row in build_decision_options(resolved).promise_options}
        for view in views:
            expected = resolved.world.characters[view.character_id].portrait_ref
            assert view.character_portrait_ref == expected
            # The structural reason this field exists at all.
            assert view.character_id not in offered, (
                "an occupied pair is excluded from promise_options, so this row cannot borrow"
            )


class TestTheForeignCounterpartTrioIsAllOrNothing:
    """Identity, name and depiction arrive together or not at all."""

    BASE = {
        "profile_id": "kessia",
        "display_name": "Kessia",
        "standing_bps": 2_000,
        "remaining_capacity": 100,
        "will_assist": True,
        "estimated_grant": 10,
    }

    def test_the_whole_trio_present_is_accepted(self) -> None:
        row = ForeignAssistanceCounterpartyOption(
            **self.BASE,
            counterpart_character_id="leader_kessia",
            counterpart_display_name="Chancellor Dietrich Halm",
            counterpart_portrait_ref="portrait_leader_kessia",
        )
        assert row.counterpart_portrait_ref == "portrait_leader_kessia"

    def test_the_whole_trio_absent_is_accepted(self) -> None:
        """A profile whose leader no scenario authored is a coherent state."""
        row = ForeignAssistanceCounterpartyOption(**self.BASE)
        assert row.counterpart_character_id is None
        assert row.counterpart_portrait_ref is None

    @pytest.mark.parametrize(
        "partial",
        [
            {"counterpart_character_id": "leader_kessia"},
            {"counterpart_display_name": "Chancellor Dietrich Halm"},
            {"counterpart_portrait_ref": "portrait_leader_kessia"},
            {
                "counterpart_character_id": "leader_kessia",
                "counterpart_display_name": "Chancellor Dietrich Halm",
            },
            {
                "counterpart_character_id": "leader_kessia",
                "counterpart_portrait_ref": "portrait_leader_kessia",
            },
        ],
    )
    def test_every_partial_combination_is_unconstructible(self, partial: dict[str, str]) -> None:
        """A name with no portrait would make the client pick a fallback likeness; a portrait with
        no id would show a face nothing identifies. Both are refused by the model, not merely
        discouraged in a docstring."""
        with pytest.raises(ValidationError) as exc_info:
            ForeignAssistanceCounterpartyOption(**self.BASE, **partial)
        assert "present or absent together" in str(exc_info.value)


class TestACorruptedPromiseIsUnrenderableInEveryRuntimeMode:
    """The missing-character guard is RAISED, not asserted.

    `python -O` strips assertions, so an invariant expressed as `assert` protects the development
    runtime and abandons the optimized one — which is precisely where a corrupted save would be
    loaded without anyone watching. A test that only ran unoptimized could never tell the
    difference, so this one checks the mechanism rather than the behaviour.
    """

    def test_a_promise_naming_an_unknown_character_is_refused(self) -> None:
        from app.simulation.decisions import DecisionSet, PromiseDecision
        from app.simulation.resolver import resolve_turn

        state = _state("tiny_valid.yaml")
        option = build_decision_options(state).promise_options[0]
        resolved = resolve_turn(
            state,
            DecisionSet(
                expected_turn=state.turn,
                expected_state_version=state.state_version,
                decisions=(
                    PromiseDecision(
                        action="make",
                        character_id=option.character_id,
                        term_kind=option.term_kind,
                        subject_id=option.subject_id,
                        deadline_turn=option.earliest_legal_deadline,
                    ),
                ),
            ),
        ).state

        # Corrupt the registry the way a damaged save would: the promise survives, its counterparty
        # does not.
        characters = {
            cid: row for cid, row in resolved.world.characters.items() if cid != option.character_id
        }
        corrupted = resolved.model_copy(
            update={"world": resolved.world.model_copy(update={"characters": characters})}
        )
        with pytest.raises(ValueError, match="not renderable"):
            build_decision_options(corrupted)

    def test_the_guard_is_not_an_assert_statement(self) -> None:
        """Structural, so the guarantee survives `python -O`.

        Checking the SOURCE rather than the behaviour is the only way to tell an `assert` from a
        `raise` here: under a normal test run both raise, and under `-O` only one does.
        """
        import ast
        import inspect
        import textwrap

        from app.api import projections

        source = textwrap.dedent(inspect.getsource(projections._active_promises))
        tree = ast.parse(source)
        assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)], (
            "_active_promises must not guard renderability with `assert`; -O would strip it"
        )
        assert [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]


class TestTheFrontendPortraitListCannotDriftIntoFiction:
    """The frontend proves "every authored reference renders" against a hand-written list.

    A hand-written list that only tests itself proves nothing, and this is not hypothetical: the
    first draft of `portrait.test.ts` invented three references that no scenario authors and omitted
    one that every run of `decree_state` produces — and passed, because totality and distinctness
    were checked over the invented list rather than over the content. This test is what makes that
    list answerable to the scenarios.
    """

    FRONTEND_TEST = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "format"
        / "portrait.test.ts"
    )

    def _authored_refs(self) -> list[str]:
        refs: list[str] = []
        for scenario in SCENARIOS:
            state = _state(scenario)
            refs.extend(row.portrait_ref for row in state.world.characters.values())
        return sorted(refs)

    def _listed_refs(self) -> list[str]:
        source = self.FRONTEND_TEST.read_text(encoding="utf-8")
        block = source[source.index("const AUTHORED_REFS = [") : source.index("] as const;")]
        return sorted(re.findall(r'"(portrait_[a-z0-9_]+)"', block))

    def test_the_lists_are_equal_as_multisets(self) -> None:
        """Multiset, not set: two scenarios legitimately author the same reference
        (`portrait_leader_governing_party` and `portrait_leader_marnil` each appear in both
        `decree_state` and `deficit_demo`), so a set comparison would hide a dropped duplicate."""
        assert self._listed_refs() == self._authored_refs()

    def test_the_counts_the_frontend_asserts_are_the_real_ones(self) -> None:
        """The two magic numbers in `portrait.test.ts` are facts about the content, so they are
        pinned here rather than left as numbers someone updated by eye."""
        authored = self._authored_refs()
        assert len(authored) == 26, "26 authored character rows across the three scenarios"
        assert len(set(authored)) == 24, "24 distinct references; two are shared by two scenarios"

    def test_every_scenarios_own_refs_are_internally_distinct(self) -> None:
        """Sharing ACROSS scenarios is content working as intended; sharing WITHIN one would mean
        two people in the same campaign wearing the same face."""
        for scenario in SCENARIOS:
            refs = [row.portrait_ref for row in _state(scenario).world.characters.values()]
            assert len(refs) == len(set(refs)), scenario


class TestCompatibility:
    """Two gates moved in this slice, for two unrelated reasons, so each is proved on its own.

    `content_version` `0.18.0 -> 0.19.0` is PORTRAITS: every character gained an authored
    `portrait_ref`, which is scenario shape. `RULESET_VERSION` `0.22.0 -> 0.23.0` is the
    DECREE-ROUTE BARGAIN REFUSAL, which is a rules change: a decision set the 0.22.0 engine accepted
    is now refused at submission.

    The 8a fixture (`0.22.0 / 0.18.0`) is old on BOTH axes, and `check_compatibility` reports the
    ruleset first, so the fixture alone can only ever prove one of the two gates. The content gate
    is therefore proved on a copy whose ruleset stamp is moved forward to the current one — a
    test-local edit, never a regenerated fixture — which is the only shape that reaches it.

    Each proof also corrupts every payload beyond parsing while leaving the envelope intact. What
    that actually establishes is narrower than the usual wording, and the last test says so: this
    loader never parses a payload at all, so the probative claim is that the same corrupted file
    with current stamps loads cleanly and fails only when the state is read.
    """

    FIXTURE = (
        pathlib.Path(__file__).resolve().parent / "fixtures" / "portrait_save_content_0.18.0.json"
    )

    def _raw(self) -> dict[str, typing.Any]:
        return json.loads(self.FIXTURE.read_text(encoding="utf-8"))

    def _with_unparseable_payloads(self, raw: dict[str, typing.Any]) -> dict[str, typing.Any]:
        for entry in raw["entries"]:
            entry["state_json"] = "{not even valid json"
            if entry.get("report_json"):
                entry["report_json"] = "{not even valid json"
        return raw

    def test_the_fixture_really_predates_both_bumps(self) -> None:
        """The sanity half. Without it, a fixture silently regenerated under the current engine
        would make both rejections below pass for the wrong reason."""
        raw = self._raw()
        assert raw["ruleset_version"] == "0.22.0"
        assert raw["content_version"] == "0.18.0"
        assert RULESET_VERSION == "0.23.0"
        assert frozenset({"0.19.0"}) == SUPPORTED_CONTENT_VERSIONS

    def test_the_stored_characters_really_lack_a_portrait(self) -> None:
        """What the CONTENT bump is actually about, read out of the fixture rather than asserted:
        every stored `CharacterState` predates `portrait_ref`."""
        rows = 0
        for entry in self._raw()["entries"]:
            payload = entry.get("state_json")
            if not payload:
                continue
            for character in json.loads(payload)["world"]["characters"].values():
                rows += 1
                assert "portrait_ref" not in character
        assert rows > 0, "the fixture must carry characters for this to prove anything"

    def test_the_old_ruleset_is_rejected_before_any_payload_is_parsed(self) -> None:
        raw = self._with_unparseable_payloads(self._raw())
        with pytest.raises(UnsupportedRulesetVersionError) as exc_info:
            load_save_json(json.dumps(raw), source="portrait-fixture-ruleset-gate")
        message = str(exc_info.value)
        assert "0.22.0" in message
        assert RULESET_VERSION in message

    def test_the_old_content_is_rejected_before_any_payload_is_parsed(self) -> None:
        """The content gate ON ITS OWN, reachable only once the ruleset stamp is current.

        The edit is to the test's local copy and to the envelope only: the stored states still
        carry no `portrait_ref`, which is exactly why the content stamp must still be refused."""
        raw = self._with_unparseable_payloads(self._raw())
        raw["ruleset_version"] = RULESET_VERSION
        for entry in raw["entries"]:
            entry["ruleset_version"] = RULESET_VERSION
        with pytest.raises(UnsupportedContentVersionError) as exc_info:
            load_save_json(json.dumps(raw), source="portrait-fixture-content-gate")
        message = str(exc_info.value)
        assert "0.18.0" in message
        assert "0.19.0" in message

    def test_the_gate_is_what_rejects_these_files_and_nothing_else_would(self) -> None:
        """Anti-vacuity for both proofs above, and a correction to how they are worded.

        `load_save_json` keeps every `state_json` as an OPAQUE STRING — it version-checks the
        envelope and never parses a payload at all — so "rejected before any payload is parsed" is
        true here only in the weak sense that nothing parses them either way. The falsifiable claim
        is therefore this one: the SAME corrupted file, with both stamps moved to current, LOADS
        CLEANLY, and the corruption surfaces only when the state is actually read.

        That is what makes the two rejections above attributable to the version gate specifically,
        rather than to a loader that refuses anything malformed.
        """
        raw = self._with_unparseable_payloads(self._raw())
        raw["ruleset_version"] = RULESET_VERSION
        raw["content_version"] = next(iter(SUPPORTED_CONTENT_VERSIONS))
        for entry in raw["entries"]:
            entry["ruleset_version"] = RULESET_VERSION
            entry["content_version"] = next(iter(SUPPORTED_CONTENT_VERSIONS))

        save = load_save_json(json.dumps(raw), source="portrait-fixture-anti-vacuity")
        assert save.ruleset_version == RULESET_VERSION

        with pytest.raises(Exception) as exc_info:
            save.current_state()
        assert not isinstance(
            exc_info.value, (UnsupportedRulesetVersionError, UnsupportedContentVersionError)
        )
