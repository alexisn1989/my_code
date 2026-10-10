"""Victory-route search (v2: adds the executive-system companion change for a monarchy): can a NEW campaign of each shipped scenario reach a VICTORY outcome, using only
actions the interface offers, judged only by the engine's own `/api/game/preview`?

    python -I victory_search.py --backend <repo>/backend --scenario <id> --max-turns 60 --out <file.json>

Plays one campaign at the scenario's authored seed through FastAPI's TestClient on `create_app`. Each
turn, with only the decision options the API serves and the preview's verdict:

* before the qualifying transition: propose the amendment that makes the constitution competitive
  (decree authority `none`, plus an elected executive and an election interval where those are
  missing), trying no influence, then influence placed on one bloc, then on two, then with any bargain a
  leader will accept -- and submit the first combination the preview says passes and is affordable.
  If none does, spend the turn's capital on relationship investment in the blocs of the chamber that
  failed (largest shortfall first), which is what moves future votes;
* after the transition: invest capital in relationships each turn (election support reads them) and
  otherwise resolve empty turns until the election decides.

The harness READS the session's engine state only to record what happened (the transition marker,
the next election turn, the terminal outcome); it never uses that to choose an action the interface
could not. Every submitted decision set is recorded, so a route found here can be replayed by hand.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

INTERVAL_FOR_REFORM = 4  # used only where the scenario has no election interval (Valdrun)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--max-turns", type=int, default=60)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.backend.resolve()))

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api.main import ApiSettings, create_app  # noqa: PLC0415

    log: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as saves:
        port = 48992
        application = create_app(ApiSettings(port=port, save_root=Path(saves), serve_spa=False))
        client = TestClient(application, base_url=f"http://127.0.0.1:{port}")
        assert client.post("/api/game/new", json={"scenario_id": args.scenario}).status_code == 200

        def politics() -> Any:
            state = application.state.session.current_save.current_state()
            return state.world.countries[state.world.player_country_id].politics

        def envelope(decisions: list[dict[str, Any]]) -> dict[str, Any]:
            state = client.get("/api/game/state").json()
            return {"revision": state["revision"], "campaign_id": state["campaign_id"],
                    "decisions": sorted(decisions, key=lambda d: d["kind"])}

        def preview(decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
            response = client.post("/api/game/preview", json=envelope(decisions))
            return response.json() if response.status_code == 200 else None

        for _ in range(args.max_turns):
            pol = politics()
            if pol.terminal_outcome is not None:
                break
            options = client.get("/api/game/decision-options").json()
            opening = options["opening_capital"]
            constitution = pol.constitution
            turn_row: dict[str, Any] = {
                "turn": application.state.session.current_save.current_state().turn,
                "opening_capital": opening,
                "pending_liberalization": pol.pending_liberalization is not None,
                "next_election_turn": pol.next_election_turn,
            }
            chosen: list[dict[str, Any]] | None = None
            tried = 0
            if pol.pending_liberalization is None:
                targets = [{"axis": "decree_authority", "value": "none"}]
                if constitution.executive_selection.value not in ("direct_election", "legislative_selection"):
                    targets.append({"axis": "executive_selection", "value": "direct_election"})
                    # v2: a monarchical executive cannot be directly elected (the preview refuses the
                    # combination as incoherent), so the companion change is the executive system.
                    if constitution.executive_system.value == "monarchical":
                        targets.append({"axis": "executive_system", "value": "presidential"})
                if constitution.national_election_interval_turns is None:
                    targets.append({"axis": "national_election_interval_turns", "value": INTERVAL_FOR_REFORM})
                targets.sort(key=lambda t: t["axis"])
                blocs = sorted({(b["party_id"], b["bloc_id"]) for b in options["blocs"]})
                bargains = [b for b in options["legislative_bargain_counterparties"] if b["will_deal"]]
                influence_plans: list[list[dict[str, Any]]] = [[]]
                for bloc in blocs:
                    influence_plans.append([{"party_id": bloc[0], "bloc_id": bloc[1], "political_capital": opening}])
                for a, b in itertools.combinations(blocs, 2):
                    half = opening // 2
                    if half > 0:
                        influence_plans.append(sorted(
                            [{"party_id": a[0], "bloc_id": a[1], "political_capital": half},
                             {"party_id": b[0], "bloc_id": b[1], "political_capital": opening - half}],
                            key=lambda r: (r["party_id"], r["bloc_id"])))
                bargain_options: list[dict[str, Any] | None] = [None] + [
                    {"kind": "legislative_bargain", "character_id": b["character_id"],
                     "proposal_kind": "constitutional_amendment"} for b in bargains]
                for bargain in bargain_options:
                    for plan in influence_plans:
                        if bargain is not None:
                            price = next(b["asking_price"] for b in bargains if b["character_id"] == bargain["character_id"])
                            scale = max(opening - price, 0)
                            plan = [dict(r, political_capital=max(1, r["political_capital"] * scale // max(opening, 1))) for r in plan]
                            if any(r["political_capital"] <= 0 for r in plan) or scale == 0 and plan:
                                continue
                        amendment = {"kind": "constitutional_amendment", "targets": targets,
                                     "route": "legislative", "influence": plan}
                        decisions = [amendment] + ([bargain] if bargain else [])
                        result = preview(decisions)
                        tried += 1
                        if result and result["would_pass"] and result["affordable"]:
                            chosen = decisions
                            turn_row["preview_chambers"] = result["chambers"]
                            break
                    if chosen:
                        break
                if chosen is None:
                    last = preview([{"kind": "constitutional_amendment", "targets": targets, "route": "legislative", "influence": []}])
                    turn_row["best_failing_preview"] = None if last is None else last["chambers"]
            if chosen is None:
                # Invest: in the failing chamber's blocs before the transition, in every bloc after it.
                lo, hi = options["relationship_investment_minimum"], options["relationship_investment_maximum"]
                budget = opening
                rows = []
                ranked = sorted({(b["party_id"], b["bloc_id"]): b["seats"] for b in options["blocs"]}.items(),
                                key=lambda kv: -kv[1])
                for (party_id, bloc_id), _ in ranked:
                    amount = min(hi, budget)
                    if amount < lo:
                        break
                    rows.append({"party_id": party_id, "bloc_id": bloc_id, "political_capital": amount})
                    budget -= amount
                rows.sort(key=lambda r: (r["party_id"], r["bloc_id"]))
                chosen = [{"kind": "bloc_relationship_investment", "investments": rows}] if rows else []
                if chosen and not (preview(chosen) or {}).get("affordable", False):
                    chosen = []
            response = client.post("/api/game/resolve", json=envelope(chosen))
            turn_row["previews_tried"] = tried
            turn_row["submitted"] = chosen
            turn_row["status"] = response.status_code
            if response.status_code == 200:
                body = response.json()["turnResult"]
                turn_row["headline"] = body["outcome_headline"]
            else:
                turn_row["error"] = response.text[:400]
            log.append(turn_row)
            if response.status_code != 200:
                break

        pol = politics()
        final = application.state.session.current_save.current_state()
        outcome = None if pol.terminal_outcome is None else {
            "bucket": pol.terminal_outcome.bucket.value,
            "victory_reason": None if pol.terminal_outcome.victory_reason is None else pol.terminal_outcome.victory_reason.value,
            "removal_reason": None if pol.terminal_outcome.removal_reason is None else pol.terminal_outcome.removal_reason.value,
            "turn": pol.terminal_outcome.turn,
        }
    args.out.write_text(json.dumps({"scenario": args.scenario, "final_turn": final.turn, "outcome": outcome,
                                    "turns": log}, indent=2) + "\n")
    print(json.dumps({"scenario": args.scenario, "final_turn": final.turn, "outcome": outcome,
                      "transition_turns": [r["turn"] for r in log if r.get("submitted") and r["submitted"][0]["kind"] == "constitutional_amendment"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
