"""Single-step import route for Jackrabbit Exporter bundles."""

from __future__ import annotations

import csv
import io
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.jackrabbit_bundle import (
    BUNDLE_FORMAT_VERSION,
    CLASSES_FILE,
    EXPECTED_BUNDLE_FILENAME,
    MAX_BUNDLE_BYTES,
    PAIRINGS_FILE,
    STAFF_FILE,
    STUDENTS_FILE,
    parse_jackrabbit_bundle,
)


def _require_converted_rows(filename: str, csv_text: str) -> None:
    """Reject a required payload when conversion produced only its header."""

    reader = csv.reader(io.StringIO(csv_text, newline=""), strict=True)
    next(reader, None)
    if not any(any(value.strip() for value in row) for row in reader):
        raise ValueError(
            f"{filename} did not contain any usable records after conversion; "
            "review its required IDs and fields"
        )


def _supplement_staff_from_classes(
    staff_csv: str,
    classes_csv: str,
) -> tuple[str, list[str], int]:
    """Add identity-only staff rows for numeric class instructor xIDs."""

    staff_reader = csv.DictReader(io.StringIO(staff_csv, newline=""))
    staff_rows = list(staff_reader)
    known_ids = {
        str(row.get("Staff ID", "")).strip()
        for row in staff_rows
        if str(row.get("Staff ID", "")).strip()
    }
    warnings: list[str] = []
    supplemented = 0

    for row_number, row in enumerate(
        csv.DictReader(io.StringIO(classes_csv, newline="")),
        start=2,
    ):
        class_id = str(row.get("Class ID", "")).strip()
        instructor_id = str(row.get("instructor_id", "")).strip()
        instructor_name = " ".join(str(row.get("Instructors", "")).split())
        if not instructor_id:
            warnings.append(
                f"Class row {row_number} ({class_id or 'missing Class ID'}) has no "
                "instructor_id; its staff identity could not be linked."
            )
            continue
        if not instructor_id.isascii() or not instructor_id.isdigit():
            warnings.append(
                f"Class row {row_number} has non-numeric instructor_id "
                f"{instructor_id!r}; staff supplementation requires a numeric xID."
            )
            continue
        if instructor_id in known_ids:
            continue
        staff_rows.append(
            {
                "Staff ID": instructor_id,
                "Name": instructor_name,
                "Status": "",
                "Position": "",
                "Instructor": "",
            }
        )
        known_ids.add(instructor_id)
        supplemented += 1
        warnings.append(
            f"Staff ID {instructor_id} was supplemented from class {class_id or '(blank)'} "
            "with identity fields only; status, position, and matcher-owned profile "
            "attributes remain blank and require review."
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=["Staff ID", "Name", "Status", "Position", "Instructor"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(staff_rows)
    return output.getvalue(), warnings, supplemented


@dataclass(frozen=True)
class JackrabbitImportDependencies:
    no_cache_headers: dict[str, str]
    app_data_root: Path
    settings_lock: Any
    get_settings: Callable[[], dict]
    validate_settings: Callable[[dict], None]
    save_settings: Callable[[dict], None]
    sanitize_instructor_profile: Callable[[dict | None], dict]
    import_classes: Callable[..., tuple[str, list[str]]]
    import_students: Callable[..., tuple[str, list[str]]]
    import_instructors: Callable[..., tuple[str, list[str]]]
    repository: Any
    operator_name: Callable[[Any], str | None]


def create_jackrabbit_import_router(deps: JackrabbitImportDependencies) -> APIRouter:
    router = APIRouter()

    @router.post("/api/jackrabbit/import")
    async def import_jackrabbit_export(request: Request):
        try:
            form = await request.form()
            uploaded = form.get("file")
            if uploaded is None or not hasattr(uploaded, "read"):
                return JSONResponse(
                    {"ok": False, "error": "Choose an Aqua Essence Jackrabbit export file."},
                    status_code=400,
                    headers=deps.no_cache_headers,
                )
            uploaded_name = str(getattr(uploaded, "filename", "") or "").strip()
            if uploaded_name != EXPECTED_BUNDLE_FILENAME:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": (
                            f"Choose {EXPECTED_BUNDLE_FILENAME}; received "
                            f"{uploaded_name or '(unnamed file)'}."
                        ),
                    },
                    status_code=400,
                    headers=deps.no_cache_headers,
                )
            bundle = parse_jackrabbit_bundle(await uploaded.read(MAX_BUNDLE_BYTES + 1))
            operator = deps.operator_name(form.get("operator"))

            with deps.settings_lock:
                settings = deps.get_settings()
                default_profile = deps.sanitize_instructor_profile(
                    settings.get("default_instructor_profile")
                )

            classes_csv, class_warnings = deps.import_classes(bundle.files[CLASSES_FILE])
            swimmers_csv, swimmer_warnings = deps.import_students(
                bundle.files[STUDENTS_FILE],
                preserve_missing=True,
                allow_class_level_inference=False,
            )
            _require_converted_rows(CLASSES_FILE, classes_csv)
            _require_converted_rows(STUDENTS_FILE, swimmers_csv)
            supplemented_staff_csv, supplementation_warnings, supplemented_count = (
                _supplement_staff_from_classes(
                    bundle.files[STAFF_FILE],
                    bundle.files[CLASSES_FILE],
                )
            )
            instructors_csv, instructor_warnings = deps.import_instructors(
                supplemented_staff_csv,
                default_profile=default_profile,
                preserve_missing=True,
            )

            import_dir = deps.app_data_root / "data" / "imports" / f"jackrabbit_{secrets.token_hex(16)}"
            import_dir.mkdir(parents=True, exist_ok=False)
            classes_path = import_dir / "classes.csv"
            swimmers_path = import_dir / "swimmers.csv"
            instructors_path = import_dir / "instructors.csv"
            classes_path.write_text(classes_csv, encoding="utf-8", newline="")
            swimmers_path.write_text(swimmers_csv, encoding="utf-8", newline="")
            instructors_path.write_text(instructors_csv, encoding="utf-8", newline="")

            preview = deps.repository.preview_instructors_import(instructors_csv)
            new_instructor_ids = [str(row["instructor_id"]) for row in preview.get("new", [])]
            instructor_result = deps.repository.apply_instructors_import(
                instructors_csv,
                new_instructor_ids,
                imported_by=operator,
            )

            pairing_result = {"imported": 0, "skipped": 0, "sessions": []}
            pairings_csv = bundle.files.get(PAIRINGS_FILE, "")
            if bundle.row_counts.get(PAIRINGS_FILE, 0):
                pairing_result = deps.repository.import_jackrabbit_pairings_csv(
                    pairings_csv,
                    imported_by=operator,
                )

            with deps.settings_lock:
                settings = deps.get_settings()
                settings["last_selected_files"]["classes"] = str(classes_path)
                settings["last_selected_files"]["swimmers"] = str(swimmers_path)
                settings["last_selected_files"]["instructors"] = str(instructors_path)
                settings["use_db_instructors"] = deps.repository.count_instructors() > 0
                deps.validate_settings(settings)
                deps.save_settings(settings)

            warnings = (
                list(bundle.warnings)
                + class_warnings
                + swimmer_warnings
                + supplementation_warnings
                + instructor_warnings
            )
            skipped_pairings = int(pairing_result.get("skipped", 0))
            if skipped_pairings:
                warnings.append(
                    f"{skipped_pairings} historical pairing row(s) were skipped because "
                    "required IDs/session values were missing, invalid, or duplicated."
                )
            return JSONResponse(
                {
                    "ok": True,
                    "format_version": BUNDLE_FORMAT_VERSION,
                    "exporter_version": bundle.exporter_version,
                    "row_counts": bundle.row_counts,
                    "instructors_added": instructor_result.get("created", 0),
                    "existing_instructors_preserved": preview.get("unchanged", 0)
                    + len(preview.get("changed", [])),
                    "staff_supplemented_from_classes": supplemented_count,
                    "pairings_imported": pairing_result.get("imported", 0),
                    "pairings_skipped": skipped_pairings,
                    "sessions": pairing_result.get("sessions", []),
                    "warnings": warnings,
                },
                headers=deps.no_cache_headers,
            )
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)},
                status_code=400,
                headers=deps.no_cache_headers,
            )
        except OSError as exc:
            return JSONResponse(
                {"ok": False, "error": f"Could not store the Jackrabbit export: {exc}"},
                status_code=500,
                headers=deps.no_cache_headers,
            )

    return router
