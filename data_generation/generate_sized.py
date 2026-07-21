"""
Size-controllable dataset generator.

Usage:
    python -m data_generation.generate_sized --num-instructors 25 --seed 42 --output data/scaling/small
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from data_generation import (
    generate_classes,
    generate_historical_pairings,
    generate_instructors,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = WORKSPACE_ROOT / "data" / "source"


def generate_sized_dataset(
    num_instructors: int,
    seed: int,
    output_dir: str,
    source_dir: str,
) -> None:
    """Generate a complete dataset with exactly ``num_instructors`` instructors."""
    if num_instructors <= 0:
        raise ValueError("num_instructors must be positive")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # The current synthetic generators only need the source directory to exist;
    # they do not read from it directly yet.
    src_dir = Path(source_dir)
    if not src_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {src_dir}")

    generate_instructors.generate_instructors(
        str(out_dir),
        seed=seed,
        num_instructors=num_instructors,
    )
    generate_classes.generate_classes(str(out_dir), seed=seed + 1000)

    random.seed(seed)
    generate_historical_pairings.generate_historical_pairings(str(out_dir))



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a size-controlled synthetic dataset")
    parser.add_argument("--num-instructors", type=int, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True, help="Output directory for generated CSVs")
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Path to data/source; validated for consistency with the rest of the tooling",
    )
    args = parser.parse_args(argv)

    generate_sized_dataset(
        num_instructors=args.num_instructors,
        seed=args.seed,
        output_dir=args.output,
        source_dir=args.source_dir,
    )
    print(f"Dataset written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
