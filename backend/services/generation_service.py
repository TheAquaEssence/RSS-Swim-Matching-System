"""Application service for one complete swimmer-matching generation job."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from backend.csv_import import (
    import_classes,
    import_instructors,
    import_students,
    is_partner_classes_csv,
    is_partner_instructors_csv,
    is_partner_students_csv,
)
from backend.spreadsheet_import import read_tabular_file_text
from backend.services.result_files import expose_result_files


@dataclass(frozen=True)
class GenerationDependencies:
    """Narrow boundary between generation orchestration and the host app."""

    app_root: Path
    jobs_dir: Path
    solvers_dir: Path
    logger: Any
    generate_job_id: Callable[[], str]
    resolve_from_root: Callable[[str], Path]
    sanitize_instructor_profile: Callable[[dict | None], dict]
    input_file_problem: Callable[[Path], str | None]
    read_csv_id_set: Callable[[Path, str], set[str] | None]
    filter_historical_pairings: Callable[..., tuple[str, int, int]]
    should_default_to_empty_historical: Callable[[dict], bool]
    write_empty_historical_pairings: Callable[[Path], None]
    normalize_swimmers: Callable[..., int]
    normalize_instructors: Callable[..., tuple[int, list[str]]]
    build_request_json: Callable[[dict, str], str]
    run_solver: Callable[[Path, Path, Path], None]
    read_solver_result: Callable[[Path], str]
    parse_solver_result: Callable[[str], dict]
    annotate_non_response_flags: Callable[[dict, Path, Path], None]
    annotate_default_instructor_flags: Callable[[dict, Path], None]
    db_count_instructors: Callable[[], int]
    db_export_instructors_csv: Callable[[], str]
    db_load_historical_csv: Callable[..., str]
    db_save_session: Callable[..., int]
    set_last_job_dir: Callable[[str], None]


@dataclass(frozen=True)
class GenerationResult:
    payload: dict
    status_code: int = 200
    job_id: str | None = None


class GenerationService:
    """Run the matching pipeline without depending on FastAPI or server globals."""

    def __init__(self, dependencies: GenerationDependencies):
        self.deps = dependencies

    def generate(
        self,
        settings_snapshot: dict,
        *,
        selected_session_ids: list[int] | None = None,
        request_id: str | None = None,
    ) -> GenerationResult:
        job_id = self.deps.generate_job_id()
        job_dir = self.deps.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        logger = self.deps.logger
        logger.info(
            "Generate job started",
            extra={"event": "generate_started", "job_id": job_id, "request_id": request_id},
        )
        default_profile = self.deps.sanitize_instructor_profile(
            settings_snapshot.get("default_instructor_profile")
        )
        warnings: list[str] = []

        self._use_database_instructors(settings_snapshot, job_dir, warnings)

        failure = self._validate_inputs(settings_snapshot, job_id)
        if failure:
            return failure

        failure = self._convert_partner_files(
            settings_snapshot,
            job_dir,
            default_profile,
            warnings,
            job_id,
        )
        if failure:
            return failure
        if warnings:
            logger.warning("Partner CSV import warnings: %s", "; ".join(warnings))

        failure = self._prepare_historical_pairings(
            settings_snapshot,
            job_dir,
            selected_session_ids,
            warnings,
            job_id,
        )
        if failure:
            return failure

        failure = self._normalize_inputs(
            settings_snapshot,
            job_dir,
            default_profile,
            job_id,
        )
        if failure:
            return failure

        request_path = job_dir / "request.json"
        result_path = job_dir / "result.json"
        request_path.write_text(
            self.deps.build_request_json(settings_snapshot, job_id),
            encoding="utf-8",
        )

        solver_path = self.deps.solvers_dir / "python_cpsat" / "solver_wrapper.py"
        if not solver_path.exists():
            return self._failure("Solver is unavailable", 500, job_id=job_id)

        try:
            self.deps.run_solver(solver_path, request_path, result_path)
        except RuntimeError as exc:
            kind = "solver_timeout" if str(exc) == "Solver timed out" else "solver_failed"
            return self._failure(str(exc), 500, error_kind=kind, job_id=job_id)

        try:
            result_text = self.deps.read_solver_result(result_path)
            result_payload = self.deps.parse_solver_result(result_text)
        except RuntimeError as exc:
            return self._failure(str(exc), 500, error_kind="solver_failed", job_id=job_id)

        self._annotate_result(result_payload, settings_snapshot)
        self._ensure_profiles(request_path, job_dir)
        self.deps.set_last_job_dir(str(job_dir))

        if not result_payload["ok"]:
            return self._failure(
                "Solver execution failed",
                500,
                error_kind="solver_failed",
                job_id=job_id,
            )

        try:
            run_label = f"Solver run {time.strftime('%Y-%m-%d')}"
            self.deps.db_save_session(result_payload.get("matches", []), label=run_label)
        except Exception:
            pass

        if warnings:
            existing = result_payload.get("warnings")
            result_payload["warnings"] = warnings + (
                list(existing) if isinstance(existing, list) else []
            )
            try:
                (job_dir / "generation_warnings.json").write_text(
                    json.dumps(result_payload["warnings"]),
                    encoding="utf-8",
                )
            except OSError:
                pass

        logger.info(
            "Generate job completed",
            extra={
                "event": "generate_completed",
                "job_id": job_id,
                "request_id": request_id,
                "solver_id": "python_cpsat",
            },
        )
        return GenerationResult(expose_result_files(result_payload, job_dir), job_id=job_id)

    def _use_database_instructors(
        self,
        settings_snapshot: dict,
        job_dir: Path,
        warnings: list[str],
    ) -> None:
        if not settings_snapshot.get("use_db_instructors"):
            return
        try:
            count = self.deps.db_count_instructors()
            if count > 0:
                path = job_dir / "instructors_db.csv"
                path.write_text(self.deps.db_export_instructors_csv(), encoding="utf-8")
                settings_snapshot["last_selected_files"]["instructors"] = str(path)
                self.deps.logger.info(
                    "Using instructors from DB",
                    extra={"event": "instructors_from_db", "rows": count},
                )
            else:
                warnings.append(
                    "Database instructors enabled but the database is empty — "
                    "falling back to the selected instructors file."
                )
        except Exception as exc:
            self.deps.logger.warning("DB instructors failed, falling back to file: %s", exc)
            warnings.append(
                f"Could not read instructors from the database ({exc}) — "
                "falling back to the selected instructors file."
            )

    def _validate_inputs(self, settings_snapshot: dict, job_id: str) -> GenerationResult | None:
        for key in ("classes", "swimmers", "instructors"):
            raw_path = self._selected_path(settings_snapshot, key)
            if not raw_path:
                continue
            path = self.deps.resolve_from_root(raw_path)
            problem = self.deps.input_file_problem(path)
            if problem == "missing":
                return self._failure(
                    f"The selected {key} file no longer exists: {path.name}",
                    400,
                    error_kind="missing_input_file",
                    job_id=job_id,
                )
            if problem == "empty":
                return self._failure(
                    f"The selected {key} file has no data rows: {path.name}",
                    400,
                    error_kind="empty_input_file",
                    job_id=job_id,
                )
        return None

    def _convert_partner_files(
        self,
        settings_snapshot: dict,
        job_dir: Path,
        default_profile: dict,
        warnings: list[str],
        job_id: str,
    ) -> GenerationResult | None:
        conversions = (
            ("classes", is_partner_classes_csv, import_classes, "classes_converted.csv"),
            ("swimmers", is_partner_students_csv, import_students, "swimmers_converted.csv"),
            ("instructors", is_partner_instructors_csv, import_instructors, "instructors_converted.csv"),
        )
        for key, detect, importer, output_name in conversions:
            raw_path = self._selected_path(settings_snapshot, key)
            if not raw_path:
                continue
            path = self.deps.resolve_from_root(raw_path)
            if not path.exists():
                continue
            try:
                raw_text = read_tabular_file_text(path)
                if not detect(raw_text):
                    continue
                self.deps.logger.info("Detected partner format for '%s', converting…", key)
                if key == "instructors":
                    converted, import_warnings = import_instructors(
                        raw_text,
                        default_profile=default_profile,
                    )
                else:
                    converted, import_warnings = importer(raw_text)
                warnings.extend(import_warnings or [])
                destination = job_dir / output_name
                destination.write_text(converted, encoding="utf-8")
                settings_snapshot["last_selected_files"][key] = str(destination)
            except ValueError as exc:
                return self._failure(f"Invalid {key} file: {exc}", 400, job_id=job_id)
            except OSError as exc:
                return self._failure(f"Could not read {key} file: {exc}", 400, job_id=job_id)
            except Exception as exc:
                return self._failure(
                    f"Unexpected error processing {key} file: {exc}",
                    500,
                    job_id=job_id,
                )
        return None

    def _prepare_historical_pairings(
        self,
        settings_snapshot: dict,
        job_dir: Path,
        selected_session_ids: list[int] | None,
        warnings: list[str],
        job_id: str,
    ) -> GenerationResult | None:
        database_path = job_dir / "historical_pairings_db.csv"
        try:
            csv_text = self.deps.db_load_historical_csv(session_ids=selected_session_ids)
            swimmer_ids = instructor_ids = None
            for key, column in (("swimmers", "swimmer_id"), ("instructors", "instructor_id")):
                raw_path = self._selected_path(settings_snapshot, key)
                if not raw_path:
                    continue
                path = self.deps.resolve_from_root(raw_path)
                if not path.exists():
                    continue
                ids = self.deps.read_csv_id_set(path, column)
                if key == "swimmers":
                    swimmer_ids = ids
                else:
                    instructor_ids = ids
            csv_text, kept, skipped = self.deps.filter_historical_pairings(
                csv_text,
                swimmer_ids,
                instructor_ids,
            )
            if skipped:
                total = kept + skipped
                if kept == 0 and selected_session_ids:
                    return self._failure(
                        (
                            f"All {total:,} historical pairings from the selected sessions "
                            "reference swimmers or instructors that aren't in your selected "
                            "swimmer/instructor files. Choose matching files, or deselect "
                            "those sessions to run without history."
                        ),
                        400,
                        job_id=job_id,
                    )
                if kept == 0:
                    warnings.append(
                        f"No usable history: none of the {total:,} historical pairings in "
                        "the database involve the swimmers or instructors in your selected "
                        "files, so this run used no history. If you expected continuity "
                        "matches, make sure the swimmers file and the imported history come "
                        "from the same Jackrabbit roster."
                    )
                else:
                    warnings.append(
                        f"History connected: {kept:,} past pairing(s) found for this "
                        f"roster ({skipped:,} database records for other swimmers or "
                        "instructors were not needed)."
                    )
                self.deps.logger.warning(
                    "Filtered historical pairings with unknown IDs",
                    extra={
                        "event": "historical_pairings_filtered",
                        "kept": kept,
                        "skipped": skipped,
                    },
                )
            database_path.write_text(csv_text, encoding="utf-8")
            settings_snapshot["last_selected_files"]["historical_pairings"] = str(database_path)
            self.deps.logger.info(
                "Using historical pairings from DB",
                extra={
                    "event": "historical_pairings_from_db",
                    "rows": kept,
                    "session_ids": selected_session_ids,
                },
            )
        except Exception as exc:
            self.deps.logger.warning("DB historical pairings failed, falling back to file: %s", exc)

        if not database_path.exists() and self.deps.should_default_to_empty_historical(settings_snapshot):
            empty_path = job_dir / "historical_pairings_empty.csv"
            self.deps.write_empty_historical_pairings(empty_path)
            settings_snapshot["last_selected_files"]["historical_pairings"] = str(empty_path)
            self.deps.logger.info(
                "Using empty historical pairings input",
                extra={"event": "historical_pairings_defaulted_empty"},
            )
        return None

    def _normalize_inputs(
        self,
        settings_snapshot: dict,
        job_dir: Path,
        default_profile: dict,
        job_id: str,
    ) -> GenerationResult | None:
        swimmers = self._selected_path(settings_snapshot, "swimmers")
        swimmer_types = self._selected_path(settings_snapshot, "swimmer_types")
        if swimmers and swimmer_types:
            swimmers_path = self.deps.resolve_from_root(swimmers)
            types_path = self.deps.resolve_from_root(swimmer_types)
            if swimmers_path.exists() and types_path.exists():
                destination = job_dir / "swimmers_normalized.csv"
                try:
                    count = self.deps.normalize_swimmers(swimmers_path, types_path, destination)
                    if count:
                        settings_snapshot["last_selected_files"]["swimmers"] = str(destination)
                        self.deps.logger.info(
                            "Normalized swimmer_type_id values before solve",
                            extra={"event": "swimmer_types_normalized", "rows_changed": count},
                        )
                except Exception as exc:
                    return self._failure(
                        f"Could not normalize swimmers file: {exc}",
                        400,
                        job_id=job_id,
                    )

        instructors = self._selected_path(settings_snapshot, "instructors")
        colors = self._selected_path(settings_snapshot, "personality_colors")
        styles = self._selected_path(settings_snapshot, "instructor_styles")
        if instructors and colors and styles:
            instructors_path = self.deps.resolve_from_root(instructors)
            colors_path = self.deps.resolve_from_root(colors)
            styles_path = self.deps.resolve_from_root(styles)
            if instructors_path.exists() and colors_path.exists() and styles_path.exists():
                destination = job_dir / "instructors_normalized.csv"
                try:
                    count, _ = self.deps.normalize_instructors(
                        instructors_path,
                        colors_path,
                        styles_path,
                        destination,
                        default_profile,
                    )
                    if count:
                        settings_snapshot["last_selected_files"]["instructors"] = str(destination)
                        self.deps.logger.info(
                            "Normalized instructor profile defaults before solve",
                            extra={"event": "instructor_profiles_normalized", "rows_changed": count},
                        )
                except Exception as exc:
                    return self._failure(
                        f"Could not normalize instructors file: {exc}",
                        400,
                        job_id=job_id,
                    )
        return None

    def _annotate_result(self, result_payload: dict, settings_snapshot: dict) -> None:
        swimmers = self._selected_path(settings_snapshot, "swimmers")
        swimmer_types = self._selected_path(settings_snapshot, "swimmer_types")
        if swimmers and swimmer_types:
            swimmers_path = self.deps.resolve_from_root(swimmers)
            types_path = self.deps.resolve_from_root(swimmer_types)
            if swimmers_path.exists() and types_path.exists():
                self.deps.annotate_non_response_flags(result_payload, swimmers_path, types_path)

        instructors = self._selected_path(settings_snapshot, "instructors")
        if instructors:
            instructors_path = self.deps.resolve_from_root(instructors)
            if instructors_path.exists():
                self.deps.annotate_default_instructor_flags(result_payload, instructors_path)

    def _ensure_profiles(self, request_path: Path, job_dir: Path) -> None:
        if (job_dir / "profiles.json").exists():
            return
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "core.profiles.generate_profiles",
                    str(request_path),
                    str(job_dir),
                ],
                capture_output=True,
                cwd=str(self.deps.app_root),
                timeout=30,
            )
        except Exception:
            pass

    @staticmethod
    def _selected_path(settings_snapshot: dict, key: str) -> str:
        return (
            settings_snapshot["last_selected_files"].get(key)
            or settings_snapshot["default_files"].get(key, "")
        )

    @staticmethod
    def _failure(
        error: str,
        status_code: int,
        *,
        error_kind: str | None = None,
        job_id: str | None = None,
    ) -> GenerationResult:
        payload = {"ok": False, "error": error}
        if error_kind:
            payload["error_kind"] = error_kind
        return GenerationResult(payload, status_code=status_code, job_id=job_id)
