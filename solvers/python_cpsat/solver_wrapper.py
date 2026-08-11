"""
Python CP-SAT Solver Wrapper

Bridges the app's JSON contract (request.json / result.json) to the
CP-SAT matching engine. Speaks the same protocol as the C++ solver.

Usage: python solver_wrapper.py <request.json> <result.json>
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

# Add workspace root to sys.path so core/ and solvers/ are importable.
# This file may run from the source tree (workspace/solvers/python_cpsat/)
# or from a build-time copy (backend/build/solvers/python_cpsat/).
# Walk upward until we find a directory containing both core/ and solvers/.
def _find_workspace_root():
    d = os.path.abspath(os.path.dirname(__file__))
    for _ in range(10):
        d = os.path.dirname(d)
        if os.path.isdir(os.path.join(d, 'core')) and os.path.isdir(os.path.join(d, 'solvers')):
            return d
    # Fallback: two levels up (original layout)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _resolve_app_root(request_path, request):
    app_root = request.get("app_root")
    if app_root:
        if not os.path.isabs(app_root):
            app_root = os.path.join(os.path.dirname(os.path.abspath(request_path)), app_root)
        return os.path.abspath(app_root)

    request_file = Path(request_path).resolve()
    for parent in request_file.parents:
        if parent.name == "jobs":
            return str(parent.parent)

    return workspace_root


def _to_contract_path(path, app_root):
    try:
        return Path(os.path.relpath(path, app_root)).as_posix()
    except ValueError:
        # Windows: path and app_root live on different drives (e.g. job dir
        # under a temp app-data drive while app_root is the install drive).
        return Path(path).resolve().as_posix()

workspace_root = _find_workspace_root()
sys.path.insert(0, workspace_root)

# Ensure user site-packages is on sys.path (needed when launched from
# GUI processes like AquaEssenceHost.exe where user packages may not
# be discoverable by default).
import site
_user_site = site.getusersitepackages()
if _user_site and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

from core.scoring import CompatibilityScorer, RankingLoader
from core.flags import (
    FLAG_CODES,
    expand_flag_codes,
    get_highest_severity,
    get_primary_review_action,
)
from core.aqua_logging import configure_component_logger, install_uncaught_exception_logging, with_log_context
from solvers.python_cpsat.engine.data_loader import DataLoader
from solvers.python_cpsat.engine.phase1_continuity import continuity_pass
from solvers.python_cpsat.engine.phase2_cpsat import compatibility_pass, diagnose_unassigned_swimmers
from solvers.python_cpsat.engine.hard_constraints import validate_hard_constraints
from solvers.python_cpsat.engine.phase3_explainability import (
    generate_explanations,
    generate_summary_report,
    generate_output_csv,
    generate_unassigned_report,
)
from solvers.python_cpsat.engine.fixed_class_workflow import (
    preassigned_pass_fixed_rosters,
    compatibility_pass_fixed_rosters,
    continuity_pass_fixed_rosters,
)
try:
    from solvers.python_cpsat.engine.pdf_report import generate_pdf_report
except ImportError:
    generate_pdf_report = None

COMPONENT = "solver.python_cpsat"


def _get_unassigned_reason(swimmer, instructors):
    """Determine why a swimmer couldn't be matched."""
    from solvers.python_cpsat.engine.config import AGE_THRESHOLDS

    eligible = []
    for instr in instructors:
        if swimmer.has_special_needs and not instr.can_teach_adapted:
            continue
        if swimmer.age < AGE_THRESHOLDS['baby_max'] and not instr.can_teach_babies:
            continue
        if swimmer.age >= AGE_THRESHOLDS['adult_min'] and not instr.can_teach_adults:
            continue
        eligible.append(instr)

    if not eligible:
        if swimmer.has_special_needs:
            return "No adapted-capable instructor available"
        if swimmer.age < AGE_THRESHOLDS['baby_max']:
            return "No baby-capable instructor available"
        if swimmer.age >= AGE_THRESHOLDS['adult_min']:
            return "No adult-capable instructor available"
        return "Hard constraints eliminate all instructors"

    return "No instructor capacity remaining"


def _flag_summary(flag_codes):
    """Return the highest-severity flag description for result.json output."""
    if not flag_codes:
        return ''
    highest = get_highest_severity(flag_codes)
    primary = next(
        (
            code for code in flag_codes
            if FLAG_CODES.get(code, {}).get('severity') == highest
        ),
        flag_codes[0],
    )
    return FLAG_CODES.get(primary, {}).get('description', '')


def main(argv=None):
    logger = configure_component_logger(COMPONENT)
    install_uncaught_exception_logging(logger, COMPONENT)

    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 2:
        logger.error("Invalid CLI arguments", extra={"event": "usage_error"})
        print("Usage: solver_wrapper.py <request.json> <result.json>", file=sys.stderr)
        return 1

    request_path, result_path = args

    with open(request_path, 'r') as f:
        request = json.load(f)

    data = request['data']
    config = request.get('config', {})
    job_id = request.get("job_id")

    job_dir = os.path.dirname(os.path.abspath(result_path))
    os.makedirs(job_dir, exist_ok=True)

    with with_log_context(job_id=job_id, solver_id="python_cpsat"):
        started = time.perf_counter()
        logger.info("Solver wrapper started", extra={"event": "wrapper_started"})

        try:
            # Resolve file paths (may be relative to app root).
            app_root = _resolve_app_root(request_path, request)

            def resolve(p):
                if not p:
                    return None
                if os.path.isabs(p):
                    return p
                return os.path.normpath(os.path.join(app_root, p))

            classes_path = resolve(data.get('classes', ''))
            swimmers_path = resolve(data.get('swimmers', ''))
            instructors_path = resolve(data.get('instructors', ''))
            historical_path = resolve(data.get('historical_pairings', ''))

            # Reference data directory
            ref = data.get('reference', {})
            source_dir = None
            for ref_file in ref.values():
                if ref_file:
                    source_dir = os.path.dirname(resolve(ref_file))
                    break
            if not source_dir:
                source_dir = os.path.join(workspace_root, 'data', 'source')

            logger.info("Resolved solver input paths", extra={"event": "wrapper_inputs_resolved"})

            # Load data via from_files factory
            loader = DataLoader.from_files(
                classes_path=classes_path,
                swimmers_path=swimmers_path,
                instructors_path=instructors_path,
                historical_path=historical_path,
                source_dir=source_dir,
            )

            # Build scorer
            ranking_loader = RankingLoader(source_dir)
            color_rankings, style_rankings = ranking_loader.load_all()
            scorer = CompatibilityScorer(color_rankings, style_rankings)

            swimmers = loader.get_all_swimmers()
            instructors = loader.get_all_instructors()
            use_fixed_class_rosters = loader.uses_fixed_class_rosters()

            continuity_started = time.perf_counter()
            enable_continuity = config.get('enable_continuity', True)
            if use_fixed_class_rosters:
                individual_classes, pair_classes = loader.get_fixed_class_entities()
                (
                    preassigned_matches,
                    unmatched_individual_classes,
                    unmatched_pair_classes,
                    available_instructors,
                ) = preassigned_pass_fixed_rosters(
                    individual_classes,
                    pair_classes,
                    instructors,
                )
                if enable_continuity:
                    (
                        continuity_matches,
                        unmatched_individual_classes,
                        unmatched_pair_classes,
                        available_instructors,
                        disputed_ids,
                        swimmer_blocked_flags,
                    ) = continuity_pass_fixed_rosters(
                        unmatched_individual_classes,
                        unmatched_pair_classes,
                        available_instructors,
                        loader.historical_pairings,
                    )
                    continuity_matches = preassigned_matches + continuity_matches
                else:
                    continuity_matches = preassigned_matches
                    disputed_ids = set()
                    swimmer_blocked_flags = {}
            else:
                if enable_continuity:
                    continuity_matches, unmatched_swimmers, available_instructors, disputed_ids, swimmer_blocked_flags = continuity_pass(
                        swimmers, instructors, loader.historical_pairings
                    )
                else:
                    continuity_matches = []
                    unmatched_swimmers = swimmers
                    available_instructors = instructors
                    disputed_ids = set()
                    swimmer_blocked_flags = {}
            continuity_ms = round((time.perf_counter() - continuity_started) * 1000, 2)

            optimization_started = time.perf_counter()
            if use_fixed_class_rosters:
                compatibility_matches = compatibility_pass_fixed_rosters(
                    unmatched_individual_classes,
                    unmatched_pair_classes,
                    available_instructors,
                    scorer,
                    loader,
                    config=config,
                )
            else:
                compatibility_kwargs = {'config': config} if config else {}
                compatibility_matches = compatibility_pass(
                    unmatched_swimmers, available_instructors, scorer, loader, **compatibility_kwargs
                )
            optimization_ms = round((time.perf_counter() - optimization_started) * 1000, 2)

            all_matches = continuity_matches + compatibility_matches
            validate_hard_constraints(
                all_matches,
                swimmers,
                instructors,
                loader.classes,
            )

            assigned_ids = set()
            for m in all_matches:
                if m['type'] == 'pair':
                    assigned_ids.add(m['swimmer_1_id'])
                    assigned_ids.add(m['swimmer_2_id'])
                else:
                    assigned_ids.add(m['swimmer_id'])
            truly_unassigned = [s for s in swimmers if s.swimmer_id not in assigned_ids]
            if use_fixed_class_rosters:
                unassigned_diagnostics = {}
            else:
                unassigned_diagnostics = diagnose_unassigned_swimmers(
                    truly_unassigned,
                    unmatched_swimmers,
                    available_instructors,
                    scorer,
                    loader,
                    config=config,
                )

            explain_started = time.perf_counter()
            annotated_matches = generate_explanations(
                all_matches, instructors, swimmers, scorer, loader,
                disputed_ids=disputed_ids,
                swimmer_flags=swimmer_blocked_flags,
            )
            explain_ms = round((time.perf_counter() - explain_started) * 1000, 2)

            output_csv_path = os.path.join(job_dir, 'classes_filled.csv')
            generate_output_csv(
                annotated_matches, loader.classes, output_csv_path,
                disputed_ids=disputed_ids,
            )

            report = generate_summary_report(
                annotated_matches,
                sum(1 for m in continuity_matches if m.get('match_type') == 'continuity'),
                len(compatibility_matches),
                preassigned_count=sum(1 for m in continuity_matches if m.get('match_type') == 'pre-assigned'),
            )
            report_path = os.path.join(job_dir, 'report.txt')
            with open(report_path, 'w') as f:
                f.write(report)

            pdf_path = os.path.join(job_dir, 'matching_report.pdf')
            if generate_pdf_report is not None:
                generate_pdf_report(
                    pdf_path, annotated_matches, truly_unassigned,
                    len(continuity_matches), len(compatibility_matches),
                    loader.classes, disputed_ids=disputed_ids,
                    unassigned_diagnostics=unassigned_diagnostics,
                )

            from core.profiles.profile_reader import write_profiles_json
            profiles_path = os.path.join(job_dir, 'profiles.json')
            write_profiles_json(
                output_path=profiles_path,
                swimmers_path=swimmers_path,
                instructors_path=instructors_path,
                colors_path=resolve(ref.get('personality_colors', '')),
                styles_path=resolve(ref.get('instructor_styles', '')),
                types_path=resolve(ref.get('swimmer_types', '')),
            )

            total_assigned = sum(
                2 if m['type'] == 'pair' else 1
                for m in annotated_matches
            )
            avg_confidence = (
                sum(m['confidence'] for m in annotated_matches) / len(annotated_matches)
                if annotated_matches else 0
            )

            summary = {
                "classes": len(loader.classes),
                "assigned_swimmers": total_assigned,
                "unassigned_swimmers": len(truly_unassigned),
                "empty_classes": max(len(loader.classes) - len(annotated_matches), 0),
                "avg_confidence": round(avg_confidence, 2),
            }

            serialized_matches = []
            for m in annotated_matches:
                flag_codes = m.get('flag_codes', [])
                entry = {
                    'class_id': m.get('class_id'),
                    'type': m['type'],
                    'instructor_id': m['instructor_id'],
                    'instructor_name': m.get('instructor_name', ''),
                    'confidence': m.get('confidence', 0),
                    'compatibility_score': m.get('compatibility_score', 0),
                    'reason': m.get('reason_summary', ''),
                    'reason_summary': m.get('reason_summary', ''),
                    'match_type': m.get('match_type', 'compatibility'),
                    'explanation': m.get('explanation', ''),
                    'continuity_dispute': False,
                    'flag_codes': flag_codes,
                    'flags': expand_flag_codes(flag_codes),
                    'flag_summary': _flag_summary(flag_codes),
                    'review_action': get_primary_review_action(flag_codes),
                    'review_severity': get_highest_severity(flag_codes),
                }
                if m['type'] == 'pair':
                    entry['swimmer_1_id'] = m['swimmer_1_id']
                    entry['swimmer_2_id'] = m['swimmer_2_id']
                    entry['swimmer_1_name'] = m['swimmer_1'].name if hasattr(m.get('swimmer_1'), 'name') else str(m['swimmer_1_id'])
                    entry['swimmer_2_name'] = m['swimmer_2'].name if hasattr(m.get('swimmer_2'), 'name') else str(m['swimmer_2_id'])
                    entry['continuity_dispute'] = (
                        m.get('swimmer_1_id') in disputed_ids or
                        m.get('swimmer_2_id') in disputed_ids
                    )
                else:
                    entry['swimmer_id'] = m['swimmer_id']
                    entry['swimmer_name'] = m['swimmer'].name if hasattr(m.get('swimmer'), 'name') else str(m['swimmer_id'])
                    entry['continuity_dispute'] = m.get('swimmer_id') in disputed_ids
                serialized_matches.append(entry)

            serialized_unassigned = []
            for s in truly_unassigned:
                diagnostic = unassigned_diagnostics.get(s.swimmer_id, {})
                flag_codes = diagnostic.get('flag_codes', [])
                reason = (
                    "No legal match met the minimum auto-assign compatibility threshold"
                    if flag_codes
                    else _get_unassigned_reason(s, instructors)
                )
                entry = {
                    'swimmer_id': s.swimmer_id,
                    'swimmer_name': s.name,
                    'skill_level': s.skill_level,
                    'age': s.age,
                    'has_special_needs': s.has_special_needs,
                    'reason': reason,
                    'flag_codes': flag_codes,
                    'flags': expand_flag_codes(flag_codes),
                    'flag_summary': _flag_summary(flag_codes),
                    'review_action': get_primary_review_action(flag_codes),
                    'review_severity': get_highest_severity(flag_codes),
                }
                for key, value in diagnostic.items():
                    if key != 'flag_codes':
                        entry[key] = value
                serialized_unassigned.append(entry)

            result = {
                "ok": True,
                "result_files": {
                    "classes_filled": _to_contract_path(output_csv_path, app_root),
                    "report": _to_contract_path(report_path, app_root),
                    **({"pdf": _to_contract_path(pdf_path, app_root)} if generate_pdf_report is not None and os.path.exists(pdf_path) else {}),
                    "profiles": _to_contract_path(profiles_path, app_root),
                },
                "summary": summary,
                "matches": serialized_matches,
                "unassigned": serialized_unassigned,
            }
            logger.info(
                f"Solver phases completed continuity_ms={continuity_ms} optimization_ms={optimization_ms} explain_ms={explain_ms}",
                extra={
                    "event": "wrapper_completed",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )

        except Exception as e:
            logger.error(
                "Solver wrapper failed",
                extra={
                    "event": "wrapper_failed",
                    "exception_type": type(e).__name__,
                    "exception": str(e),
                    "stacktrace": "".join(traceback.format_exception(type(e), e, e.__traceback__)),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            result = {
                "ok": False,
                "error": str(e),
            }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2)
    logger.info(
        "result.json written",
        extra={"event": "wrapper_result_written", "job_id": job_id, "solver_id": "python_cpsat"},
    )


if __name__ == '__main__':
    raise SystemExit(main())
