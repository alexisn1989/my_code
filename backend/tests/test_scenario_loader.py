"""Gate 4A3 R2 fix: scenario YAML is read with libyaml's CSafeLoader where the install has it.

What these tests prove, and what they do not:

* Selection: `select_safe_loader` picks `CSafeLoader` when the YAML module has it and the pure-Python
  `SafeLoader` when it does not, and the module-level choice made AT IMPORT falls back correctly in a
  process where libyaml genuinely cannot be imported (tests 1-3).
* Agreement between the two loaders on THIS repository's YAML corpus only -- every `*.yaml` under
  `data/scenarios`, `frontend/e2e/fixtures` and `docs/contracts`. PyYAML documents differences between
  its implementations; nothing here claims they agree on any other input (test 4).
* A new campaign started from each shipped scenario is byte-identical whichever loader parsed it
  (test 5). Existing saves never read YAML: replay starts from the genesis state stored in the save.
* Unsafe Python-object tags are refused, and invalid or non-mapping documents still raise the same
  `ScenarioValidationError`, under each loader this install provides (tests 6-7).

Tests 4 and 5 compare the C loader against the Python one, so they are skipped where libyaml is
absent (a supported Python-only install). A RELEASE install is required to have it by
`scripts/verify_release.py`, not by these skips.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.core.errors import ScenarioValidationError
from app.simulation import scenario as scenario_module
from app.simulation.history import new_game
from app.simulation.save_format import SAVE_FORMAT_VERSION, dump_save_json
from app.simulation.scenario import load_scenario_text, select_safe_loader
from tests.conftest import REPO_ROOT, SCENARIO_DIR

HAS_LIBYAML = bool(getattr(yaml, "__with_libyaml__", False))
needs_libyaml = pytest.mark.skipif(
    not HAS_LIBYAML,
    reason="this PyYAML install has no libyaml; only the Python loader can be tested",
)

SHIPPED = sorted(SCENARIO_DIR.glob("*.yaml"))
CORPUS = sorted(
    [
        *SCENARIO_DIR.glob("*.yaml"),
        *(REPO_ROOT / "frontend" / "e2e" / "fixtures").glob("*.yaml"),
        *(REPO_ROOT / "docs" / "contracts").glob("*.yaml"),
    ]
)
AVAILABLE_LOADERS = [yaml.SafeLoader, *([yaml.CSafeLoader] if HAS_LIBYAML else [])]


def _loader_id(loader: type) -> str:
    return loader.__name__


# --------------------------------------------------------------------------- 1. selection, the function


def test_select_prefers_the_c_loader_when_the_module_has_it() -> None:
    fake = SimpleNamespace(CSafeLoader="the C one", SafeLoader="the Python one")
    assert select_safe_loader(fake) == "the C one"  # type: ignore[arg-type,comparison-overlap]


def test_select_falls_back_to_the_python_loader_when_the_module_lacks_the_c_one() -> None:
    fake = SimpleNamespace(SafeLoader="the Python one")
    assert select_safe_loader(fake) == "the Python one"  # type: ignore[arg-type,comparison-overlap]


def test_select_on_the_real_module_follows_what_pyyaml_reports() -> None:
    expected = yaml.CSafeLoader if HAS_LIBYAML else yaml.SafeLoader
    assert select_safe_loader(yaml) is expected


# --------------------------------------------------------------------------- 2. selection at import, libyaml unavailable

_FALLBACK_PROBE = """
import json, sys
sys.modules["yaml._yaml"] = None          # PyYAML's `from .cyaml import *` now fails at import
sys.path.insert(0, sys.argv[1])
import yaml
from app.simulation import scenario
from app.simulation.scenario import load_scenario_text
from pathlib import Path
print(json.dumps({
    "with_libyaml": yaml.__with_libyaml__,
    "has_c_loader": hasattr(yaml, "CSafeLoader"),
    "selected": scenario._SAFE_LOADER.__module__ + "." + scenario._SAFE_LOADER.__qualname__,
    "states": {p.stem: load_scenario_text(p.read_text(encoding="utf-8"), source=p.name).model_dump_json()
               for p in sorted(Path(sys.argv[2]).glob("*.yaml"))},
}))
"""


def test_import_time_selection_falls_back_when_libyaml_cannot_be_imported() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _FALLBACK_PROBE,
            str(REPO_ROOT / "backend"),
            str(SCENARIO_DIR),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    probe = json.loads(completed.stdout)
    assert probe["with_libyaml"] is False
    assert probe["has_c_loader"] is False
    assert probe["selected"] == "yaml.loader.SafeLoader"
    for path in SHIPPED:
        here = load_scenario_text(path.read_text(encoding="utf-8"), source=path.name)
        assert probe["states"][path.stem] == here.model_dump_json(), path.name


# --------------------------------------------------------------------------- 3. the C loader is the one in use


@needs_libyaml
def test_the_c_loader_is_selected_where_pyyaml_has_libyaml() -> None:
    assert scenario_module._SAFE_LOADER is yaml.CSafeLoader


# --------------------------------------------------------------------------- 4. agreement on the tested corpus only


def test_the_corpus_is_what_this_test_claims() -> None:
    assert len(SHIPPED) == 3
    assert len(CORPUS) >= 6, [p.name for p in CORPUS]


@needs_libyaml
@pytest.mark.parametrize("path", CORPUS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_c_and_python_loaders_agree_on_this_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert yaml.load(text, Loader=yaml.CSafeLoader) == yaml.load(text, Loader=yaml.SafeLoader)  # noqa: S506


# --------------------------------------------------------------------------- 5. a new campaign is the same campaign


@needs_libyaml
@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_a_new_campaign_is_byte_identical_whichever_loader_parsed_it(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = path.read_text(encoding="utf-8")
    saves = {}
    for loader in (yaml.CSafeLoader, yaml.SafeLoader):
        monkeypatch.setattr(scenario_module, "_SAFE_LOADER", loader)
        save = new_game(
            load_scenario_text(text, source=path.name), save_format_version=SAVE_FORMAT_VERSION
        )
        saves[loader.__name__] = save
    c_save, python_save = saves["CSafeLoader"], saves["SafeLoader"]
    assert c_save.entries[0].entry_hash == python_save.entries[0].entry_hash
    assert dump_save_json(c_save) == dump_save_json(python_save)


# --------------------------------------------------------------------------- 6. unsafe tags are refused

UNSAFE_DOCUMENTS = {
    "object_apply": "!!python/object/apply:os.system ['touch {canary}']\n",
    "object": "!!python/object:pathlib.PurePosixPath {{}}\n",
    "name": "!!python/name:os.system\n",
    "mapping_value": "scenario_id: !!python/object/apply:os.system ['touch {canary}']\n",
}


@pytest.mark.parametrize("loader", AVAILABLE_LOADERS, ids=_loader_id)
@pytest.mark.parametrize("kind", sorted(UNSAFE_DOCUMENTS))
def test_unsafe_python_tags_are_refused(
    kind: str, loader: type, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canary = tmp_path / "canary"
    monkeypatch.setattr(scenario_module, "_SAFE_LOADER", loader)
    with pytest.raises(ScenarioValidationError) as raised:
        load_scenario_text(UNSAFE_DOCUMENTS[kind].format(canary=canary), source="unsafe.yaml")
    assert raised.value.problems[0].startswith("invalid YAML:"), raised.value.problems
    assert not canary.exists()


# --------------------------------------------------------------------------- 7. error paths keep their contract


@pytest.mark.parametrize("loader", AVAILABLE_LOADERS, ids=_loader_id)
def test_invalid_yaml_is_reported_as_invalid_yaml(
    loader: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scenario_module, "_SAFE_LOADER", loader)
    with pytest.raises(ScenarioValidationError) as raised:
        load_scenario_text("this: is: not: valid: yaml: [", source="broken.yaml")
    assert raised.value.problems[0].startswith("invalid YAML:"), raised.value.problems


@pytest.mark.parametrize("loader", AVAILABLE_LOADERS, ids=_loader_id)
def test_a_non_mapping_document_is_refused(loader: type, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scenario_module, "_SAFE_LOADER", loader)
    with pytest.raises(ScenarioValidationError) as raised:
        load_scenario_text("- just\n- a\n- list\n", source="broken.yaml")
    assert raised.value.problems == ["scenario file must contain a YAML mapping"]
