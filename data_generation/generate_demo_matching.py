"""Regenerate the tracked, solver-ready demonstration dataset.

The output is deterministic for a given base seed. With seed 42, instructor
profiles use seed 42, swimmers/classes use seed 1042, and historical pairings
use seed 42. Runtime generation remains under data/generated/; this command is
only for maintainers intentionally refreshing the public demo fixtures.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from data_generation.generate_classes import generate_classes
from data_generation.generate_historical_pairings import generate_historical_pairings
from data_generation.generate_instructors import generate_instructors


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "demo" / "matching"


def main(seed: int = 42) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    generate_instructors(str(DEMO_DIR), seed=seed)
    generate_classes(str(DEMO_DIR), seed=seed + 1000)
    random.seed(seed)
    generate_historical_pairings(str(DEMO_DIR))
    print(
        f"Wrote solver demo files to {DEMO_DIR} "
        f"(base seed={seed}; swimmer seed={seed + 1000})"
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate the tracked solver demo dataset"
    )
    parser.add_argument("--seed", type=int, default=42, help="Base seed (default: 42)")
    main(seed=parser.parse_args().seed)


if __name__ == "__main__":
    cli()
