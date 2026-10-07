"""R2 diagnosis: the fixed, balanced round design. 20 rounds x 4 builds, one fresh process per block.

Order: the 4 rotations of the build list form a Latin square (each build in each position once);
5 independent seeded shuffles of those 4 rows give 20 rounds, so every build sits in every position
exactly 5 times. The seed and the realised order are recorded. Every block is retained.

    python3 rounds.py --root <r2 scratch dir> --python <backend venv python> --seed 4242
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

BUILDS = ("d1c09201", "5a1b2eb", "44fbd5a", "81f0648")
ROUNDS_PER_SHUFFLE = 4
SHUFFLES = 5
WARMUP = 5
N = 50


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    rotations = [list(BUILDS[i:] + BUILDS[:i]) for i in range(len(BUILDS))]
    rng = random.Random(args.seed)
    order: list[list[str]] = []
    for _ in range(SHUFFLES):
        rows = [list(r) for r in rotations]
        rng.shuffle(rows)
        order.extend(rows)

    blocks_dir = args.root / "out" / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=False)
    log = []
    for round_index, row in enumerate(order):
        for position, build in enumerate(row):
            out = blocks_dir / f"round{round_index:02d}-{build}.json"
            completed = subprocess.run(
                [args.python, "-I", str(args.root / "tools" / "block.py"),
                 "--tree", str(args.root / "exports" / build), "--commit", build,
                 "--warmup", str(WARMUP), "--n", str(N), "--out", str(out)],
                capture_output=True, text=True, check=False,
            )
            log.append({"round": round_index, "position": position, "build": build,
                        "exit": completed.returncode})
            if completed.returncode != 0:
                print(completed.stdout, completed.stderr, file=sys.stderr)
                raise SystemExit(f"block failed: round {round_index} {build}")
            print(f"round {round_index:02d} pos {position} {build} done", flush=True)

    (args.root / "out" / "rounds-design.json").write_text(json.dumps(
        {"seed": args.seed, "builds": BUILDS, "warmupDiscarded": WARMUP, "samplesPerBlock": N,
         "order": order, "log": log}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
