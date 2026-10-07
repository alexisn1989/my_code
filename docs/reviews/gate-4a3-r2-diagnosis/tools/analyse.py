"""R2 diagnosis: the paired-round analysis of the 20 x 4 block design.

    python3 analyse.py --root <r2 scratch dir> --seed 7 --resamples 10000 --out <file.json>

For each round and build: the block's median, p95 and max (from the block's own 50 samples).
Difference = NEWER minus BASELINE (6c, d1c09201) within the same round: > 0 is a slowdown, < 0 an
improvement. 95% intervals are percentile bootstrap intervals over ROUNDS (a resampled round keeps
all four of its builds together), so the pairing is preserved and calls are never treated as
independent. Reading: an interval excluding 0 = a difference detected in THIS harness; containing 0 =
not detected at this sample size.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

BASELINE = "d1c09201"
STATS = ("median", "p95", "max")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    design = json.loads((args.root / "out" / "rounds-design.json").read_text())
    builds = design["builds"]
    rounds = len(design["order"])
    blocks: dict[int, dict[str, dict[str, object]]] = {}
    identity: dict[str, set[str]] = {}
    for r in range(rounds):
        blocks[r] = {}
        for b in builds:
            block = json.loads((args.root / "out" / "blocks" / f"round{r:02d}-{b}.json").read_text())
            assert block["commit"] == b and f"/exports/{b}/backend/" in block["appFile"], block["appFile"]
            identity.setdefault("python", set()).add(block["python"])
            identity.setdefault("dependencies", set()).add(json.dumps(block["dependencies"], sort_keys=True))
            blocks[r][b] = block
    assert len(identity["python"]) == 1 and len(identity["dependencies"]) == 1, identity

    per_build = {}
    for b in builds:
        all_samples = [s for r in range(rounds) for s in blocks[r][b]["samplesMs"]]  # type: ignore[union-attr]
        ordered = sorted(all_samples)
        per_build[b] = {
            "pooledSamples": len(all_samples),
            "pooledMedian": round(statistics.median(all_samples), 3),
            "pooledP95": ordered[int(round(0.95 * (len(ordered) - 1)))],
            "pooledP99": ordered[int(round(0.99 * (len(ordered) - 1)))],
            "pooledMax": ordered[-1],
            "blocksOver200msMax": sum(1 for r in range(rounds) if blocks[r][b]["max"] > 200),  # type: ignore[operator]
            "samplesOver200ms": sum(1 for s in all_samples if s > 200),
            "meanOfBlockMedians": round(statistics.mean(blocks[r][b]["median"] for r in range(rounds)), 3),  # type: ignore[misc]
        }

    rng = random.Random(args.seed)
    comparisons = {}
    for b in builds:
        if b == BASELINE:
            continue
        out = {}
        for stat in STATS:
            diffs = [blocks[r][b][stat] - blocks[r][BASELINE][stat] for r in range(rounds)]  # type: ignore[operator]
            boots = []
            for _ in range(args.resamples):
                sample = [diffs[rng.randrange(rounds)] for _ in range(rounds)]
                boots.append(statistics.mean(sample))
            boots.sort()
            low = boots[int(0.025 * args.resamples)]
            high = boots[int(0.975 * args.resamples) - 1]
            verdict = (
                "slowdown detected in this harness" if low > 0
                else "improvement detected in this harness" if high < 0
                else "not detected at this sample size"
            )
            out[stat] = {
                "meanDifferenceMs": round(statistics.mean(diffs), 3),
                "ci95": [round(low, 3), round(high, 3)],
                "reading": verdict,
                "perRoundDifferencesMs": [round(d, 3) for d in diffs],
            }
        comparisons[f"{b} minus {BASELINE}"] = out

    args.out.write_text(json.dumps({
        "design": {k: design[k] for k in ("seed", "builds", "warmupDiscarded", "samplesPerBlock", "order")},
        "rounds": rounds,
        "identity": {"python": sorted(identity["python"]), "dependencies": json.loads(next(iter(identity["dependencies"])))},
        "bootstrap": {"seed": args.seed, "resamples": args.resamples, "unit": "round (paired)"},
        "perBuild": per_build,
        "differences": comparisons,
    }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
