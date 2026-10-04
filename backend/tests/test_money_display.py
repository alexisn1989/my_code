"""Gate 4A3 UX-4a (U9): player-facing money is grouped, and money is never shown as a count.

Three things are pinned here:

* `app.api.display.format_money_display` -- the player-facing form the projections now use for the
  Money concern -- states amounts with digit grouping, and signs a change;
* `app.core.money.format_money`, the CLI and the reports are untouched: the module is byte-identical
  to its `d1c09201` blob, and the CLI still prints the bare fixed-point form;
* a DRIFT GUARD for the browser: every driver param the CLI renders as money (`format_money(...)`)
  and that `frontend/src/format/format.ts` also words must reach `formatMoney` there, never
  `formatAmount`. UX-2's tax-bases sentence used `formatAmount` on minor units and showed every
  amount 100 times too large; this test is what would have caught it.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
from typing import Any

import pytest

from app.api.display import format_money_display
from app.cli import _render_tax_bases_derived
from tests.test_api_preview_parity import _make_client, _new

REPO = pathlib.Path(__file__).resolve().parents[2]
CLI_PY = REPO / "backend" / "app" / "cli.py"
FORMAT_TS = REPO / "frontend" / "src" / "format" / "format.ts"
MONEY_BLOB_AT_6C = "d1c09201"


@pytest.mark.parametrize(
    ("amount", "signed", "shown"),
    [
        (10_000_000_000, False, "100,000,000.00"),
        (315_000_000, True, "+3,150,000.00"),
        (-1_205, True, "-12.05"),
        (-1_205, False, "-12.05"),
        (0, True, "0.00"),
        (7, False, "0.07"),
    ],
)
def test_format_money_display(amount: int, signed: bool, shown: str) -> None:
    assert format_money_display(amount, signed=signed) == shown


def test_the_money_concern_is_grouped_through_the_api(tmp_path: pathlib.Path) -> None:
    with _make_client(tmp_path) as client:
        _new(client, "decree_state")
        money: dict[str, Any] = client.get("/api/game/state").json()["concerns"]["money"]
    assert re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{2}", money["headline"]), money["headline"]


def test_core_money_is_unchanged_since_6c() -> None:
    current = subprocess.run(
        ["git", "hash-object", "backend/app/core/money.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    at_6c = subprocess.run(
        ["git", "rev-parse", f"{MONEY_BLOB_AT_6C}:backend/app/core/money.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current == at_6c


def test_the_cli_still_prints_the_bare_fixed_point_form() -> None:
    line = _render_tax_bases_derived(
        {
            "personal_income": 2_150_000_000,
            "corporate_profit": 640_000_000,
            "taxable_consumption": 70,
        }
    )
    assert "21500000.00" in line
    assert "6400000.00" in line
    assert "21,500,000" not in line


def _cli_money_params() -> set[str]:
    return set(re.findall(r'format_money\(int\(params\["([a-z_]+)"\]\)\)', CLI_PY.read_text()))


def test_the_cli_money_params_are_actually_found() -> None:
    """Anti-vacuity: the guard below runs over the real list, not an empty parse."""
    assert {
        "personal_income",
        "corporate_profit",
        "taxable_consumption",
        "amount",
    } <= _cli_money_params()


def test_every_money_param_the_browser_words_goes_through_format_money() -> None:
    source = FORMAT_TS.read_text(encoding="utf-8")
    worded = [p for p in sorted(_cli_money_params()) if f'params["{p}"]' in source]
    assert worded, "format.ts words at least one money param (the tax bases)"
    for param in worded:
        bindings = re.findall(rf'const (\w+) = [^;]*params\["{param}"\]', source)
        assert bindings, f"{param} is read but not bound to a name the guard can follow"
        for name in bindings:
            assert re.search(rf"formatMoney\({name}\)", source), (
                f"{param} ({name}) not via formatMoney"
            )
            assert not re.search(rf"formatAmount\({name}\)", source), (
                f"{param} ({name}) via formatAmount"
            )
