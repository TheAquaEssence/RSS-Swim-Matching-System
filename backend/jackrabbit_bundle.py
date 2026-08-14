"""Versioned interchange contract for Jackrabbit Exporter bundles."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime


BUNDLE_FORMAT = "aqua-essence-jackrabbit-export"
BUNDLE_FORMAT_VERSION = 1
EXPORTER_NAME = "Jackrabbit Exporter"
EXPECTED_EXPORTER_VERSION = "1.1.0"
EXPECTED_BUNDLE_FILENAME = "aqua_essence_jackrabbit_export.json"
MAX_BUNDLE_BYTES = 25 * 1024 * 1024

STUDENTS_FILE = "jackrabbit_students.csv"
CLASSES_FILE = "jackrabbit_classes.csv"
STAFF_FILE = "jackrabbit_staff.csv"
PAIRINGS_FILE = "jackrabbit_pairings.csv"

FILE_HEADERS: dict[str, tuple[str, ...]] = {
    STUDENTS_FILE: (
        "Student ID", "Student First Name", "Student Last Name", "Family",
        "Status", "DOB", "Age", "Current Classes", "Skill Level", "Notes",
        "Special Needs",
    ),
    CLASSES_FILE: (
        "Class ID", "Class", "instructor_id", "Instructors", "Days",
        "Start Time", "End Time", "Location", "Status", "Session",
        "Start Date", "End Date", "Cat 1", "Open", "Size",
    ),
    STAFF_FILE: ("Staff ID", "Name", "Status", "Position", "Instructor"),
    PAIRINGS_FILE: (
        "swimmer_id", "class_id", "instructor_id", "class_name", "session",
        "status",
    ),
}
KNOWN_FILES = frozenset(FILE_HEADERS)
REQUIRED_DATA_FILES = frozenset({STUDENTS_FILE, CLASSES_FILE})


@dataclass(frozen=True)
class JackrabbitBundle:
    """Validated bundle payload with CSV contents indexed by contract filename."""

    exporter_name: str
    exporter_version: str
    exported_at: str
    files: dict[str, str]
    row_counts: dict[str, int]
    warnings: tuple[str, ...]


def _validate_exported_at(value: object) -> str:
    exported_at = str(value or "").strip()
    if not exported_at:
        raise ValueError("The Jackrabbit export is missing exported_at metadata")
    try:
        parsed = datetime.fromisoformat(
            exported_at[:-1] + "+00:00" if exported_at.endswith("Z") else exported_at
        )
    except ValueError as exc:
        raise ValueError("The Jackrabbit export exported_at value is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(
            "The Jackrabbit export exported_at value must include an ISO-8601 timezone"
        )
    return exported_at


def _validate_csv(filename: str, csv_text: str, *, require_rows: bool) -> int:
    if "\x00" in csv_text:
        raise ValueError(f"{filename} contains invalid null bytes")

    try:
        rows = csv.reader(io.StringIO(csv_text, newline=""), strict=True)
        header = next(rows, None)
        expected_header = list(FILE_HEADERS[filename])
        if header != expected_header:
            raise ValueError(
                f"{filename} header does not match format version 1; "
                f"expected {expected_header!r}, received {header!r}"
            )

        row_count = 0
        for row_number, row in enumerate(rows, start=2):
            if len(row) != len(expected_header):
                raise ValueError(
                    f"{filename} row {row_number} has {len(row)} fields; "
                    f"expected {len(expected_header)}"
                )
            if any(value.strip() for value in row):
                row_count += 1
    except csv.Error as exc:
        raise ValueError(f"{filename} is not valid CSV: {exc}") from exc

    if require_rows and row_count == 0:
        raise ValueError(f"{filename} has no data rows; students and classes are required")
    return row_count


def parse_jackrabbit_bundle(raw: bytes) -> JackrabbitBundle:
    """Decode and strictly validate one format-version-1 exporter bundle."""

    if not raw:
        raise ValueError("The Jackrabbit export is empty")
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("The Jackrabbit export exceeds the 25 MB limit")

    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The selected file is not a valid Jackrabbit export bundle") from exc

    if not isinstance(payload, dict):
        raise ValueError("The Jackrabbit export bundle must be a JSON object")
    if payload.get("format") != BUNDLE_FORMAT:
        raise ValueError(
            f"Unsupported Jackrabbit export format {payload.get('format')!r}; "
            f"expected {BUNDLE_FORMAT!r}"
        )
    version = payload.get("format_version")
    if isinstance(version, bool) or version != BUNDLE_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported Jackrabbit export version {version!r}; "
            f"this app supports version {BUNDLE_FORMAT_VERSION}"
        )

    exported_at = _validate_exported_at(payload.get("exported_at"))
    exporter = payload.get("exporter")
    if not isinstance(exporter, dict):
        raise ValueError("The Jackrabbit export is missing exporter metadata")
    exporter_name = str(exporter.get("name", "")).strip()
    exporter_version = str(exporter.get("version", "")).strip()
    if exporter_name != EXPORTER_NAME:
        raise ValueError(
            f"Unsupported exporter name {exporter_name!r}; expected {EXPORTER_NAME!r}"
        )
    if exporter_version != EXPECTED_EXPORTER_VERSION:
        raise ValueError(
            f"Unsupported exporter version {exporter_version!r}; "
            f"this app requires {EXPECTED_EXPORTER_VERSION!r}"
        )

    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("The Jackrabbit export is missing its files object")
    supplied_files = set(files)
    missing_files = sorted(KNOWN_FILES - supplied_files)
    unknown_files = sorted(supplied_files - KNOWN_FILES)
    if missing_files or unknown_files:
        details = []
        if missing_files:
            details.append(f"missing {missing_files}")
        if unknown_files:
            details.append(f"unsupported {unknown_files}")
        raise ValueError(
            "The Jackrabbit export files object must contain exactly the four "
            f"format-version-1 filenames ({'; '.join(details)})"
        )

    normalized_files: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    warnings: list[str] = []
    for filename in FILE_HEADERS:
        value = files[filename]
        if not isinstance(value, str):
            raise ValueError(f"{filename} must contain CSV text")
        normalized_files[filename] = value
        row_counts[filename] = _validate_csv(
            filename,
            value,
            require_rows=filename in REQUIRED_DATA_FILES,
        )
        if not row_counts[filename] and filename == STAFF_FILE:
            warnings.append(
                "The staff payload is header-only; staff identities will be supplemented "
                "from numeric class instructor IDs where possible."
            )
        if not row_counts[filename] and filename == PAIRINGS_FILE:
            warnings.append(
                "The historical pairings payload is header-only; no history was imported."
            )

    return JackrabbitBundle(
        exporter_name=exporter_name,
        exporter_version=exporter_version,
        exported_at=exported_at,
        files=normalized_files,
        row_counts=row_counts,
        warnings=tuple(warnings),
    )
