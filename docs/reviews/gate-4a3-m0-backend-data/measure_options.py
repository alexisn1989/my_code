"""Gate 4A3 M-0 targeted check: the COMPLETE GET /api/game/decision-options request over HTTP.

Method mirrors scripts/measure_budgets.py: client wall clock over loopback (time.perf_counter),
request sent to body fully read; every response must be 200. Fixed sample: 5 warm-up requests
discarded, then 50 timed, all retained.

usage: measure_options.py <base-url> <history: novote|recent> <label> <out.json>
"""
import json, statistics, sys, time, urllib.request

BASE, HISTORY, LABEL, OUT = sys.argv[1:5]
WARMUP, SAMPLES, TURNS = 5, 50, 40


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
        status = resp.status
    elapsed = (time.perf_counter() - t0) * 1000
    if status != 200:
        raise SystemExit(f"{method} {path} -> {status}")
    return json.loads(raw), elapsed


def resolve(decisions):
    state, _ = call("GET", "/api/game/state")
    call("POST", "/api/game/resolve", {"revision": state["revision"], "campaign_id": state["campaign_id"], "decisions": decisions})


call("POST", "/api/game/new", {"scenario_id": "decree_state"})
budget = {"kind": "budget", "personal_income_rate_bps": 1800, "spending_updates": [], "route": "legislative", "influence": []}
for turn in range(1, TURNS + 1):
    resolve([budget] if (HISTORY == "recent" and turn == TURNS) else [])
state, _ = call("GET", "/api/game/state")

options, _ = call("GET", "/api/game/decision-options")
last = options.get("last_recorded_vote", "ABSENT")
if HISTORY == "novote":
    assert last in (None, "ABSENT"), f"expected no recorded vote, got {last!r}"
else:
    if last != "ABSENT":  # the reference build (HEAD, pre-M-0) has no such field
        assert last["turn"] == state["turn"], (last["turn"], state["turn"])
        chamber = last["vote"]["chambers"][0]
        assert (chamber["supporting_seats"], chamber["required_seats"]) == (45, 51), chamber

for _ in range(WARMUP):
    call("GET", "/api/game/decision-options")
samples = [call("GET", "/api/game/decision-options")[1] for _ in range(SAMPLES)]
ordered = sorted(samples)
result = {
    "label": LABEL, "history": HISTORY, "turns_resolved": TURNS, "current_turn": state["turn"],
    "last_recorded_vote_present": last != "ABSENT",
    "last_recorded_vote_turn": None if last in (None, "ABSENT") else last["turn"],
    "warmup_discarded": WARMUP, "n": SAMPLES,
    "median_ms": round(statistics.median(samples), 2),
    "p95_ms": round(ordered[int(0.95 * SAMPLES) - 1], 2),
    "worst_ms": round(max(samples), 2),
    "samples_ms": [round(x, 3) for x in samples],
}
json.dump(result, open(OUT, "w"), indent=1)
print(f"{LABEL} {HISTORY}: turn {state['turn']}, last vote {result['last_recorded_vote_turn']}, "
      f"median {result['median_ms']} ms, p95 {result['p95_ms']} ms, worst {result['worst_ms']} ms (n={SAMPLES})")
