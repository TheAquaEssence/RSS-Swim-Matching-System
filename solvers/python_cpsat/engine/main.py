"""Main orchestration module for the production CP-SAT matching system.

Runs the three-phase matching pipeline with ranking-based compatibility:
1. Phase 1: Greedy continuity matching
2. Phase 2: CP-SAT optimization using shared CompatibilityScorer
3. Phase 3: Explainability layer with confidence scores

Usage from the repository root:
    python -m solvers.python_cpsat.engine [--data-dir PATH] [--output-dir PATH]
"""

import os
import sys
import argparse

from core.scoring import CompatibilityScorer, RankingLoader

from .data_loader import DataLoader
from .phase1_continuity import continuity_pass
from .phase2_cpsat import compatibility_pass
from .hard_constraints import validate_hard_constraints
from .phase3_explainability import (
    generate_explanations,
    generate_summary_report,
    generate_output_csv,
    generate_unassigned_report,
)


def main(data_dir: str = None, output_dir: str = None) -> None:
    """
    Main entry point for the matching system.

    Args:
        data_dir: Path to directory containing input CSV files.
                  Defaults to ../../data relative to this file.
        output_dir: Path to directory for output files.
                    Defaults to ../output relative to this file.
    """
    if data_dir is None:
        # engine/ -> python_cpsat/ -> solvers/ -> workspace/ -> data/
        data_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', 'data'
        )
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(__file__),
            'output'
        )

    data_dir = os.path.abspath(data_dir)
    output_dir = os.path.abspath(output_dir)

    print("=" * 60)
    print("CP-SAT v2 SWIMMER-INSTRUCTOR MATCHING SYSTEM")
    print("  (Ranking-based compatibility scoring)")
    print("=" * 60)
    print(f"\nData directory: {data_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # =========================================================================
    # LOAD DATA
    # =========================================================================

    print("Loading data...")
    data_loader = DataLoader(data_dir)
    data_loader.load_all()

    swimmers = data_loader.get_all_swimmers()
    instructors = data_loader.get_all_instructors()

    print(f"  Loaded {len(swimmers)} swimmers")
    print(f"  Loaded {len(instructors)} instructors")
    print(f"  Loaded {len(data_loader.classes)} classes")
    print(f"  Loaded {len(data_loader.historical_pairings)} historical pairings")
    print(f"  Loaded {len(data_loader.color_rankings)} color rankings")
    print(f"  Loaded {len(data_loader.style_rankings)} style rankings")
    print()

    # =========================================================================
    # INITIALIZE SHARED SCORER
    # =========================================================================

    print("Initializing ranking-based scorer...")
    ranking_loader = RankingLoader(os.path.join(data_dir, 'source'))
    color_rankings, style_rankings = ranking_loader.load_all()
    scorer = CompatibilityScorer(color_rankings, style_rankings)
    print("  Scorer ready (ranking-based, harmonic mean for pairs)")
    print()

    # =========================================================================
    # PHASE 1: CONTINUITY MATCHING
    # =========================================================================

    print("Phase 1: Continuity matching...")
    continuity_matches, unmatched_swimmers, available_instructors, disputed_swimmer_ids, swimmer_blocked_flags = continuity_pass(
        swimmers,
        instructors,
        data_loader.historical_pairings
    )

    continuity_swimmer_count = sum(
        2 if m['type'] == 'pair' else 1
        for m in continuity_matches
    )
    print(f"  + {len(continuity_matches)} entities matched via continuity")
    print(f"  + {continuity_swimmer_count} swimmers assigned")
    print(f"  + {len(unmatched_swimmers)} swimmers remaining for Phase 2")
    print(f"  + {len(available_instructors)} instructors available for Phase 2")
    print()

    # =========================================================================
    # PHASE 2: CP-SAT OPTIMIZATION
    # =========================================================================

    print("Phase 2: CP-SAT optimization (ranking-based scoring)...")
    try:
        compatibility_matches = compatibility_pass(
            unmatched_swimmers,
            available_instructors,
            scorer,
            data_loader
        )

        compatibility_swimmer_count = sum(
            2 if m['type'] == 'pair' else 1
            for m in compatibility_matches
        )
        print(f"  + {len(compatibility_matches)} entities matched via optimization")
        print(f"  + {compatibility_swimmer_count} swimmers assigned")

        if compatibility_matches:
            avg_score = sum(
                m.get('compatibility_score', 0) for m in compatibility_matches
            ) / len(compatibility_matches)
            print(f"  + Average compatibility score: {avg_score:.1f}%")

    except RuntimeError as e:
        print(f"  ! CP-SAT solver failed: {e}")
        print("  ! Falling back to empty compatibility matches")
        compatibility_matches = []

    print()

    # =========================================================================
    # COMBINE ALL MATCHES
    # =========================================================================

    all_matches = continuity_matches + compatibility_matches
    validate_hard_constraints(
        all_matches,
        swimmers,
        instructors,
        data_loader.classes,
    )

    total_assigned = sum(
        2 if m['type'] == 'pair' else 1
        for m in all_matches
    )
    print(f"Total: {total_assigned} swimmers assigned to {len(all_matches)} entities")
    print()

    # Determine truly unassigned swimmers (not in any match)
    assigned_ids = set()
    for m in all_matches:
        if m['type'] == 'pair':
            assigned_ids.add(m['swimmer_1_id'])
            assigned_ids.add(m['swimmer_2_id'])
        else:
            assigned_ids.add(m['swimmer_id'])

    truly_unassigned = [s for s in swimmers if s.swimmer_id not in assigned_ids]
    unassigned_reasons = {s.swimmer_id: 'no_available_instructor' for s in truly_unassigned}

    if truly_unassigned:
        print(f"  ! {len(truly_unassigned)} swimmers could not be assigned")
        print()

    # =========================================================================
    # PHASE 3: EXPLAINABILITY
    # =========================================================================

    print("Phase 3: Generating explanations...")
    annotated_matches = generate_explanations(
        all_matches,
        instructors,
        swimmers,
        scorer,
        data_loader,
        disputed_ids=disputed_swimmer_ids,
        swimmer_flags=swimmer_blocked_flags,
    )

    avg_confidence = (
        sum(m['confidence'] for m in annotated_matches) / len(annotated_matches)
        if annotated_matches else 0
    )
    print(f"  + Average confidence: {avg_confidence:.1f}%")

    low_confidence_count = sum(
        1 for m in annotated_matches if m['confidence'] < 70
    )
    if low_confidence_count > 0:
        print(f"  ! {low_confidence_count} matches require review (confidence < 70%)")
    print()

    # =========================================================================
    # GENERATE OUTPUT
    # =========================================================================

    print("Generating output files...")

    os.makedirs(output_dir, exist_ok=True)

    output_csv_path = os.path.join(output_dir, 'classes_completed.csv')
    df = generate_output_csv(
        annotated_matches,
        data_loader.classes,
        output_csv_path,
        disputed_ids=disputed_swimmer_ids,
    )
    print(f"  + Wrote {output_csv_path}")

    report = generate_summary_report(
        annotated_matches,
        len(continuity_matches),
        len(compatibility_matches)
    )

    report_path = os.path.join(output_dir, 'matching_report.txt')
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"  + Wrote {report_path}")

    explanations_path = os.path.join(output_dir, 'match_explanations.txt')
    with open(explanations_path, 'w') as f:
        f.write("DETAILED MATCH EXPLANATIONS (v2 — Ranking-Based)\n")
        f.write("=" * 60 + "\n\n")
        for match in annotated_matches:
            f.write(match['explanation'])
            f.write("\n" + "-" * 40 + "\n\n")
    print(f"  + Wrote {explanations_path}")

    if truly_unassigned:
        unassigned_path = os.path.join(output_dir, 'unassigned_swimmers.csv')
        generate_unassigned_report(truly_unassigned, unassigned_reasons, unassigned_path)
        print(f"  + Wrote {unassigned_path} ({len(truly_unassigned)} unassigned)")

    print()
    print(report)
    print("\nMatching complete!")
    print(f"Output written to: {output_dir}/")


def cli():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description='CP-SAT v2 Swimmer-Instructor Matching System (Ranking-Based)'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default=None,
        help='Path to directory containing input CSV files'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Path to directory for output files'
    )

    args = parser.parse_args()

    try:
        main(data_dir=args.data_dir, output_dir=args.output_dir)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    cli()
