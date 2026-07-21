"""
Master script to generate all swim matching data.
Runs all generation scripts in dependency order.

Order:
1. generate_reference_data - static lookup tables
2. generate_instructors - 7-9 instructors (all assumed available)
3. generate_classes - classes and N to 2×N swimmers with pre-pairing
4. generate_historical_pairings - creates pairings for entities

Note: instructor_schedule is no longer needed since all instructors
are assumed available for the time slot being matched.

Usage:
    python run_all.py              # Uses default seed (42)
    python run_all.py --seed 123   # Uses custom seed for different data
"""

import argparse
import random
import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

import generate_reference_data
import generate_instructors
import generate_classes
import generate_historical_pairings
import generate_solution_data


def main(seed: int = 42):
    """
    Run all data generation scripts in dependency order.

    Args:
        seed: Base seed for random generation.
              Instructors use seed, swimmers use seed+1000.
    """
    print("=" * 60)
    print("SWIM MATCHING DATA GENERATION PIPELINE")
    print("=" * 60)
    print(f"\nUsing seed: {seed} (for instructors), {seed + 1000} (for swimmers)")
    print()

    # 1. Reference data (no dependencies, deterministic)
    print("Step 1: Generating reference data...")
    print("-" * 60)
    result = generate_reference_data.main()
    print()

    # 2. Instructors (7-9, all assumed available)
    print("Step 2: Generating instructors...")
    print("-" * 60)
    count = generate_instructors.main(seed=seed)
    print()

    # 3. Classes and swimmers (use different seed for unique names)
    print("Step 3: Generating classes and swimmers...")
    print("-" * 60)
    count = generate_classes.main(seed=seed + 1000)
    print()

    # 4. Historical pairings
    print("Step 4: Generating historical pairings...")
    print("-" * 60)
    count = generate_historical_pairings.main(seed=seed)
    print()

    # 5. Denormalized solution data
    print("Step 5: Generating denormalized solution data...")
    print("-" * 60)
    generate_solution_data.main()
    print()

    print("=" * 60)
    print("DATA GENERATION COMPLETE")
    print("=" * 60)
    print()
    print("Source CSV files have been written to the 'data/source/' directory.")
    print("Generated CSV files have been written to the 'data/generated/' directory.")
    print("Denormalized files have been written to the 'data_solution/' directory.")
    print("The matching algorithm can now use these files as input.")
    print()


def cli():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description='Generate all swim matching data files'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Base seed for random generation (default: 42). '
             'Instructors use seed, swimmers use seed+1000.'
    )

    args = parser.parse_args()
    main(seed=args.seed)


if __name__ == '__main__':
    cli()
