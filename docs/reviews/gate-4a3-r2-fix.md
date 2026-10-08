# Gate 4A3 R2 fix (code): scenario YAML read with libyaml's `CSafeLoader`

This is option (a) from [`gate-4a3-r2-diagnosis.md`](gate-4a3-r2-diagnosis.md) §6, approved by you
with five revisions. It **deliberately changes the engine boundary**: `app/simulation/scenario.py`.

**This commit holds the code, tests and command only. No timing is claimed here.** Every measurement
that needs this commit's own export (the selected loader's timings, the release check's breach rate,
the dry run) belongs to the release record that follows.

**R2 is tracked per build:**
- **The approved playtest archive** (`058d779f…`, built from `81f0648`): R2 stays **open and
  unchanged**. Nothing here touches that archive, its approval, or the roadmap's "approved playtest
  build" line.
- **The candidate built from this commit:** reported separately, in the release record.
- **A supported Python-only install** (no libyaml): it falls back to the pure-Python `SafeLoader`, so it
  keeps the slow path, and therefore keeps R2.

Whether the playtest moves to the candidate is your decision.

## 1. The change

**`app/simulation/scenario.py`:**
- `select_safe_loader(yaml_module)` returns `yaml_module.CSafeLoader` when the module has it, else
  `yaml_module.SafeLoader`.
- `_SAFE_LOADER = select_safe_loader(yaml)` is chosen once, at import.
- `_parse` now calls `yaml.load(raw_text, Loader=_SAFE_LOADER)` in place of `yaml.safe_load`.

**Both are SAFE loaders.** `CSafeLoader` is **not** a `SafeLoader` subclass: it combines `CParser` with
`SafeConstructor`. The return annotation names both classes.

**The error contract is unchanged:**
- invalid YAML is still `ScenarioValidationError` with "invalid YAML: …";
- a non-mapping document still gives "scenario file must contain a YAML mapping";
- only the text after "invalid YAML:" comes from whichever parser ran, and no test matches it.

**What it reaches.** Only new starting states, through `load_scenario_file`: the Title screen cards,
`POST /api/game/new` and the CLI. **Replay and existing saves never read YAML:** `validate_history`
replays from the genesis state stored in the save. No `RULESET_VERSION` bump, because the tests below
show identical parsed data and byte-identical new saves for the shipped scenarios.

**A release install must have libyaml (`scripts/verify_release.py`).**
- The provenance step's probe also prints the installed app's selected loader and
  `yaml.__with_libyaml__`.
- `require_c_loader` raises `VerifyError` unless the loader is `yaml.cyaml.CSafeLoader`.
- The release JSON gains `provenance.yamlLoader` and `provenance.yamlWithLibyaml`. Earlier release
  records are unchanged.

**The candidate's dry-run command (`frontend/package.json`).** `dryrun:installed:r2fix`, with gate label
"4A3 R2-fix (enforced)", writes `gate-4a3-r2fix-dryrun`. It is added here so the release commit can
stay records-only.

## 2. Tests (`backend/tests/test_scenario_loader.py`, 27, plus 5 in `test_release_verifier.py`)

| # | what | how |
|---|---|---|
| 1 | **selection logic** | `select_safe_loader` on a stand-in with both loaders, on one with only `SafeLoader`, and on the real `yaml` (which must match `__with_libyaml__`) |
| 2 | **selection at import, libyaml truly absent** | a `python -I` subprocess sets `sys.modules["yaml._yaml"] = None` before importing `yaml`, so PyYAML's own C import fails. It asserts `__with_libyaml__` is false, there is no `CSafeLoader`, and `_SAFE_LOADER` is `yaml.loader.SafeLoader`. Each shipped scenario's state must equal the parent process's (`model_dump_json`). **Runs on any install.** |
| 3 | the C loader is in use where it exists | `_SAFE_LOADER is yaml.CSafeLoader`. **Skipped** without libyaml, so a supported Python-only install passes its applicable tests; the release requirement is `verify_release`'s |
| 4 | **agreement on the tested corpus only** | for every `*.yaml` in `data/scenarios` (3), `frontend/e2e/fixtures` (2) and `docs/contracts` (1), `yaml.load(…, CSafeLoader) == yaml.load(…, SafeLoader)`. The list is globbed and its size asserted. **No claim is made for any other input:** PyYAML documents differences between its implementations |
| 5 | **a new campaign is the same campaign** | for each shipped scenario, `new_game(load_scenario_text(…))` under each loader (`_SAFE_LOADER` monkeypatched, which tests parse behaviour, not selection). The genesis `entry_hash` must be equal and `dump_save_json` byte-identical |
| 6 | **unsafe tags refused** | `!!python/object/apply:os.system`, `!!python/object:…`, `!!python/name:…`, and an unsafe tag nested as a mapping value, under each available loader. Each raises `ScenarioValidationError` starting "invalid YAML:", and the payload's canary file is asserted absent |
| 7 | error paths | invalid YAML and a non-mapping document, under each available loader |
| v | **the release requirement** | `require_c_loader` accepts `yaml.cyaml.CSafeLoader` and refuses `yaml.loader.SafeLoader`, `""` and `yaml.loader.UnsafeLoader`. The real `PROVENANCE_PROBE`, run by this interpreter, reports the loader it selects |

**Mutation checks.** Each was restored afterwards and checked with `cmp`.

| mutation | failed, as intended |
|---|---|
| `select_safe_loader` always returns `SafeLoader` | 3: test 1 "prefers C", test 1 "real module", test 3 |
| ignore a missing `CSafeLoader` (`yaml_module.CSafeLoader`) | 2: test 1 "fallback", and test 2, the import-time subprocess |
| `_parse` uses `yaml.UnsafeLoader` | 8: every test-6 case, under both loaders. Under this mutation the `touch` payload ran inside pytest's temporary directory, and the canary check caught it |
| `require_c_loader` accepts anything | 3: every refusal case |

## 3. Gates

Each exit status is the command's own `$?`.

| command | exit | result |
|---|---:|---|
| `pytest tests/test_scenario_loader.py` | 0 | 27 passed |
| `pytest tests/test_release_verifier.py` | 0 | 38 passed (33 + 5) |
| backend full suite (`pytest -q`) | 0 | **36,437 passed**, 1 warning (the known `StarletteDeprecationWarning`), in 18:21. That is 36,405 + 32 new |
| `ruff check .`, `ruff format --check .` | 0, 0 | |
| `mypy` (the project's configured packages) | 0 | 57 source files |
| `npm run generate:api` | 0 | byte-identical: no tracked file changed |
| `npm test`, `typecheck`, `build`, `check:bundle`, `check:palette`, `check:copy`, `check:css-sources` | 0 each | 613 passed. **The bundle is byte-identical** to UX-4g's (`index-BumrhHF5.js`, `index-DVVZ_8_3.css`), since only `package.json` changed |
| the 22 save fixtures in `backend/tests/fixtures` | | unchanged (no diff), and their replay tests pass inside the suite |

## 4. Scope

- **Changed:**
  - `backend/app/simulation/scenario.py`, the engine boundary, by your ruling;
  - `scripts/verify_release.py`;
  - `backend/tests/test_release_verifier.py`;
  - `frontend/package.json`.
- **Added:**
  - `backend/tests/test_scenario_loader.py`;
  - this record.
- **Unchanged:**
  - the approved playtest archive and its roadmap line;
  - every other engine module, the contract, the fixtures, the frontend source, and the budgets.
