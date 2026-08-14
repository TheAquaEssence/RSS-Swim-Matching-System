"""
CSV Import Adapter — AquaEssence
Converts industry partner CSV exports into the internal format expected by the solver.

Handles:
  - Classes.csv  (partner)  →  classes.csv  (internal)
  - Students.csv (partner)  →  swimmers.csv (internal)
  - ActiveStaff   (partner) →  instructors.csv (internal)

Known gaps (to be filled by future work):
  - classes:  cat_2 has no source in the partner export (left blank)
  - swimmers: swimmer_type_id has no source — defaults to Non-Response / Unknown
  - swimmers: skill_level uses the exporter Skill Level field or an unambiguous
              RSS level in Current Classes; unresolved rows remain 0 for review
  - swimmers: has_special_needs — read from a "Special Needs" column when present;
              the Notes column is a count (0/1) in Jackrabbit exports and is NOT used
              to set has_special_needs; text-valued Notes are passed to the solver
  - instructors: colors/styles/certifications are not present in ActiveStaff;
                 safe defaults are used until a richer source is available
  - historical_pairings.csv — no partner export exists; TBD data source
"""

import csv
import io
import re
from datetime import datetime, timedelta

from core.swimmer_types import NON_RESPONSE_SWIMMER_TYPE_ID, NON_RESPONSE_SWIMMER_TYPE_NAME
from backend.instructor_source_schema import (
    CERTIFICATION_PROFILE_COLUMNS,
    EDITABLE_INSTRUCTOR_POSITION_VALUES,
    STYLE_COLOR_PROFILE_COLUMNS,
    is_editable_instructor_position,
)

# Header sets used to detect partner format vs internal format
_PARTNER_CLASSES_HEADERS  = {"Class ID", "Class", "Instructors", "Days", "Start Time", "End Time"}
_PARTNER_STUDENTS_HEADERS = {"Student First Name", "Student Last Name", "Family", "DOB"}
_PARTNER_INSTRUCTORS_HEADERS = {"Staff ID", "Name", "Status", "Instructor"}
_INTERNAL_CLASSES_HEADERS  = {"class_id", "instructor_name", "day_of_week"}
_INTERNAL_STUDENTS_HEADERS = {"swimmer_id", "swimmer_type_id", "skill_level"}


def is_partner_classes_csv(csv_text: str) -> bool:
    """Return True if the CSV looks like the partner Classes export format."""
    try:
        headers = set(next(csv.reader(io.StringIO(csv_text))))
        return bool(_PARTNER_CLASSES_HEADERS & headers)
    except Exception:
        return False


def is_partner_students_csv(csv_text: str) -> bool:
    """Return True if the CSV looks like the partner Students export format."""
    try:
        headers = set(next(csv.reader(io.StringIO(csv_text))))
        return bool(_PARTNER_STUDENTS_HEADERS & headers)
    except Exception:
        return False


def is_partner_instructors_csv(csv_text: str) -> bool:
    """Return True if the CSV looks like the partner ActiveStaff export format."""
    try:
        headers = set(next(csv.reader(io.StringIO(csv_text))))
        return bool(_PARTNER_INSTRUCTORS_HEADERS & headers)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_partner_date(date_str: str) -> str:
    """Convert M/D/YYYY → YYYY-MM-DD.  Returns original string on failure."""
    s = str(date_str).strip()
    if s.isdigit():
        try:
            serial = int(s)
            excel_epoch = datetime(1899, 12, 30)
            return (excel_epoch + timedelta(days=serial)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _parse_age(age_str: str) -> float:
    """
    Convert '07 yrs, 08 mths' → 7.67 (years as float).
    Falls back to parsing a bare float/int string.
    """
    s = str(age_str).strip()
    m = re.match(r"(\d+)\s*yrs?,\s*(\d+)\s*mths?", s, re.IGNORECASE)
    if m:
        years = int(m.group(1))
        months = int(m.group(2))
        return round(years + months / 12, 2)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _split_instructors(raw: str) -> list[str]:
    """
    Split a possibly multi-value Instructors cell into individual names.
    e.g. '"Nikki L., Creek H., Olivia R."' → ['Nikki L.', 'Creek H.', 'Olivia R.']
    Single name cells are returned as a one-element list.
    """
    raw = raw.strip().strip('"')
    if not raw:
        return []
    # Split on comma+space only when followed by a word char (catches "First L., ...")
    parts = re.split(r",\s+(?=[A-Za-z])", raw)
    return [p.strip() for p in parts if p.strip()]


def _split_person_name(raw: str) -> tuple[str, str]:
    """Split a full name into first and last name parts."""
    normalized = " ".join(str(raw).strip().split())
    if not normalized:
        return "", ""
    if "," in normalized:
        last, first = [part.strip() for part in normalized.split(",", 1)]
        return first, last
    parts = normalized.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _get_first_present_value(row: dict, *column_names: str) -> str:
    """Return the first non-blank value from the provided column names."""
    for column_name in column_names:
        value = str(row.get(column_name, "")).strip()
        if value:
            return value
    return ""


def _is_truthy_export_value(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


# Normalised names we recognise as a "special needs" column in partner exports.
_SPECIAL_NEEDS_COLUMN_VARIANTS = {
    "special needs",
    "has special needs",
    "special need",
    "adapted",
    "disabilities",
    "disability",
    "special_needs",
}


def _find_special_needs_column(fieldnames: list[str] | None) -> str | None:
    """Return the first column name that looks like a special-needs indicator, or None."""
    for col in fieldnames or []:
        normalised = col.strip().lower().replace("_", " ")
        if normalised in _SPECIAL_NEEDS_COLUMN_VARIANTS:
            return col
    return None


def _normalize_profile_bool(value, default: bool) -> tuple[bool, bool]:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True, False
    if normalized in {"0", "false", "no", "n"}:
        return False, False
    return default, True


def _normalize_profile_int(value, default: int) -> tuple[int, bool]:
    normalized = str(value).strip()
    try:
        parsed = int(normalized)
        return (parsed, False) if parsed > 0 else (default, True)
    except (TypeError, ValueError):
        return default, True


# ---------------------------------------------------------------------------
# Classes import
# ---------------------------------------------------------------------------

CLASSES_INTERNAL_HEADERS = [
    "class_id",
    "start_time",
    "end_time",
    "day_of_week",
    "location",
    "class_name",
    "session",
    "instructor_id",    # Jackrabbit staff xID — used directly by DataLoader (no name matching)
    "instructor_name",  # Human-readable; DataLoader falls back to this if instructor_id absent
    "open",
    "size",
    "status",
    "cat_1",
    "cat_2",        # No source in partner export — left blank
    "start_date",
    "end_date",
]


def import_classes(partner_csv_text: str) -> tuple[str, list[str]]:
    """
    Convert a partner Classes.csv string into the internal classes.csv format.

    Returns:
        (csv_text, warnings)
        csv_text  — the converted CSV as a string, ready to write to a file
        warnings  — list of non-fatal issues found during conversion
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(partner_csv_text))

    headers = set(reader.fieldnames or [])
    required = {"Class ID", "Location", "Status", "Session", "Start Date", "End Date",
                "Days", "Start Time", "End Time", "Instructors", "Cat 1", "Open", "Size"}
    missing = required - headers
    if "Class" not in headers and "Current Classes" not in headers:
        missing.add("Class")
    if missing:
        raise ValueError(f"Partner Classes CSV is missing required columns: {sorted(missing)}")

    out_rows: list[dict] = []
    seen_assignments: set[tuple[str, ...]] = set()

    for row_num, row in enumerate(reader, start=2):  # row 1 is header
        try:
            status = row.get("Status", "").strip()
            class_name = _get_first_present_value(row, "Class", "Current Classes", "Description")
            if status.lower() != "active":
                warnings.append(f"Row {row_num}: skipped (Status={status!r})")
                continue

            class_id_raw = row.get("Class ID", "").strip()
            if not class_id_raw:
                warnings.append(f"Row {row_num}: '{class_name}' skipped — missing Class ID (Jackrabbit xID required)")
                continue
            if not class_id_raw.isascii() or not class_id_raw.isdigit():
                warnings.append(f"Row {row_num}: '{class_name}' skipped — Class ID {class_id_raw!r} is not a valid integer")
                continue
            class_id = class_id_raw

            raw_instructors = row.get("Instructors", "").strip()
            instructor_names = _split_instructors(raw_instructors)

            if not instructor_names:
                instructor_names = [""]

            # instructor_id column: Jackrabbit staff xID(s), comma-separated for splits.
            # When present the DataLoader uses it directly; instructor_name is kept for
            # human readability only.
            raw_instructor_ids = [
                iid.strip()
                for iid in row.get("instructor_id", "").split(",")
                if iid.strip()
            ]

            # One output row per instructor (multi-instructor classes get split).
            if len(instructor_names) > 1:
                warnings.append(
                    f"Row {row_num}: '{class_name}' has {len(instructor_names)} "
                    f"instructors — split into {len(instructor_names)} rows"
                )

            start_time = row.get("Start Time", "").strip()
            end_time   = row.get("End Time", "").strip()
            if not start_time or not end_time:
                warnings.append(
                    f"Row {row_num}: '{class_name}' is missing Start Time or End Time — skipped"
                )
                continue

            for i, instructor in enumerate(instructor_names):
                # Prefer per-split xID; fall back to the single xID for all splits
                instr_id = (
                    raw_instructor_ids[i] if i < len(raw_instructor_ids)
                    else (raw_instructor_ids[0] if raw_instructor_ids else "")
                )
                # instructor_name is kept only for human readability alongside the xID.
                # If no xID is available, blank the name too — name-only rows are not
                # supported; the DataLoader requires instructor_id for matching.
                instr_name = instructor if instr_id else ""
                assignment_key = (
                    (class_id, instr_id)
                    if instr_id
                    else (class_id, "", instructor.casefold(), str(i))
                )
                if assignment_key in seen_assignments:
                    warnings.append(
                        f"Row {row_num}: duplicate Class ID/instructor_id assignment "
                        f"{class_id}/{instr_id or '(blank)'} skipped"
                    )
                    continue
                seen_assignments.add(assignment_key)
                out_rows.append({
                    "class_id":        class_id,
                    "start_time":      start_time,
                    "end_time":        end_time,
                    "day_of_week":     row.get("Days", "").strip(),
                    "location":        row.get("Location", "").strip(),
                    "class_name":      class_name,
                    "session":         row.get("Session", "").strip(),
                    "instructor_id":   instr_id,
                    "instructor_name": instr_name,
                    "open":            row.get("Open", "0").strip(),
                    "size":            row.get("Size", "0").strip(),
                    "status":          status,
                    "cat_1":           row.get("Cat 1", "").strip(),
                    "cat_2":           "",
                    "start_date":      _parse_partner_date(row.get("Start Date", "")),
                    "end_date":        _parse_partner_date(row.get("End Date", "")),
                })
        except Exception as e:
            warnings.append(f"Row {row_num}: unexpected error — {e} — skipped")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CLASSES_INTERNAL_HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

    return output.getvalue(), warnings


# ---------------------------------------------------------------------------
# Students import
# ---------------------------------------------------------------------------

SWIMMERS_INTERNAL_HEADERS = [
    "swimmer_id",
    "first_name",
    "last_name",
    "swimmer_type_id",  # STUB: populated via survey flow (not in partner export)
    "skill_level",      # Exporter value or unambiguous RSS class-name inference
    "age",
    "has_special_needs",
    "notes",
    "pair_id",
    "registered_class_name",
]

# Default stub values for fields with no source in the partner export
_DEFAULT_SWIMMER_TYPE_ID = NON_RESPONSE_SWIMMER_TYPE_ID
_DEFAULT_SKILL_LEVEL = 0


def _parse_exported_skill_level(
    row: dict,
    *,
    allow_class_inference: bool = True,
) -> tuple[int | str, str | None]:
    """Return a single RSS level from exporter data, or 0 when ambiguous.

    The extension can populate ``Skill Level`` directly.  For list exports it
    may only have the registered class name, so accept an unambiguous ``RSS N``
    marker from ``Current Classes`` as a fallback.
    """

    explicit = _get_first_present_value(row, "Skill Level", "RSS Level", "Level")
    if explicit:
        match = re.fullmatch(r"(?:RSS\s*)?(\d{1,2})", explicit, re.IGNORECASE)
        if match and 1 <= int(match.group(1)) <= 12:
            return int(match.group(1)), None
        return 0, f"unrecognized Skill Level {explicit!r}"

    if not allow_class_inference:
        return "", "no Skill Level was exported"

    registered_classes = str(row.get("Current Classes", "")).strip()
    levels = {
        int(value)
        for value in re.findall(r"\bRSS\s*(\d{1,2})\b", registered_classes, re.IGNORECASE)
        if 1 <= int(value) <= 12
    }
    if len(levels) == 1:
        return levels.pop(), None
    if len(levels) > 1:
        return 0, f"multiple RSS levels found in Current Classes {registered_classes!r}"
    return 0, "no Skill Level or unambiguous RSS class level was exported"


def import_students(
    partner_csv_text: str,
    *,
    preserve_missing: bool = False,
    allow_class_level_inference: bool = True,
) -> tuple[str, list[str]]:
    """
    Convert a partner Students.csv string into the internal swimmers.csv format.

    Returns:
        (csv_text, warnings)
        csv_text  — the converted CSV as a string, ready to write to a file
        warnings  — list of non-fatal issues found during conversion

    Known stubs in the output:
        swimmer_type_id = Non-Response / Unknown
        skill_level     = exporter value/class-name inference, or 0 for review
        pair_id         = blank — pairs are set manually by staff (same pair_id
            on both swimmers); never inferred from the Family column
        has_special_needs — read from a "Special Needs" column if present; otherwise False.
            The Notes count column is never used to infer has_special_needs.
        notes — populated from a text-valued Notes column (passed to solver's notes_parser);
            numeric Notes counts are ignored.
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(partner_csv_text))

    required = {"Student ID", "Student First Name", "Student Last Name", "Status", "Age", "Family"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Partner Students CSV is missing required columns: {sorted(missing)}")

    special_needs_col = _find_special_needs_column(reader.fieldnames)

    # --- First pass: collect rows and build family → [swimmer_ids] map -------
    raw_rows: list[dict] = []
    # Non-Active students are routine in full exports — count them and emit a
    # single summary warning instead of one line per skipped row.
    skipped_statuses: dict[str, int] = {}

    for row_num, row in enumerate(reader, start=2):
        try:
            status = row.get("Status", "").strip()
            if status.lower() != "active":
                key = status or "(blank)"
                skipped_statuses[key] = skipped_statuses.get(key, 0) + 1
                continue

            swimmer_id_raw = row.get("Student ID", "").strip()
            if not swimmer_id_raw:
                warnings.append(f"Row {row_num}: skipped — missing Student ID (Jackrabbit xID required)")
                continue
            if not swimmer_id_raw.isascii() or not swimmer_id_raw.isdigit():
                warnings.append(f"Row {row_num}: skipped — Student ID {swimmer_id_raw!r} is not a valid integer")
                continue
            swimmer_id = swimmer_id_raw

            first_name = row.get("Student First Name", "").strip()
            last_name  = row.get("Student Last Name", "").strip()
            if not first_name and not last_name:
                warnings.append(f"Row {row_num}: skipped — no name found")
                continue

            # has_special_needs: use dedicated column when present; never infer from Notes.
            if special_needs_col is not None:
                special_needs_raw = str(row.get(special_needs_col, "")).strip()
                has_special_needs = (
                    _is_truthy_export_value(special_needs_raw)
                    if special_needs_raw
                    else ("" if preserve_missing else False)
                )
                if preserve_missing and not special_needs_raw:
                    warnings.append(
                        f"Row {row_num}: {first_name} {last_name} has no Special Needs "
                        "value — left blank for review"
                    )
            else:
                has_special_needs = False

            # Notes: count values (Jackrabbit default) are ignored for special-needs;
            # text values are passed through to the solver's notes_parser.
            notes_raw = row.get("Notes", "").strip()
            notes_text = ""
            try:
                notes_count = int(notes_raw)
                if notes_count > 0 and special_needs_col is None:
                    warnings.append(
                        f"Row {row_num}: {first_name} {last_name} has Notes count={notes_count} "
                        f"but no Special Needs column found — has_special_needs left False; "
                        f"verify manually"
                    )
            except ValueError:
                # Notes is free text — pass it to the solver (prefer/avoid/always/never)
                notes_text = notes_raw

            age_str = row.get("Age", "").strip()
            if not age_str:
                warnings.append(f"Row {row_num}: {first_name} {last_name} has no Age — defaulting to 0")
            age = _parse_age(age_str) if age_str else 0.0

            skill_level, skill_problem = _parse_exported_skill_level(
                row,
                allow_class_inference=allow_class_level_inference,
            )
            if preserve_missing and skill_level == _DEFAULT_SKILL_LEVEL:
                skill_level = ""
            if skill_problem:
                warnings.append(
                    f"Row {row_num}: {first_name} {last_name} has unresolved skill_level — "
                    f"{skill_problem}"
                )

            raw_rows.append({
                "swimmer_id":       swimmer_id,
                "first_name":       first_name,
                "last_name":        last_name,
                "swimmer_type_id":  _DEFAULT_SWIMMER_TYPE_ID,
                "skill_level":      skill_level,
                "age":              age,
                "has_special_needs": has_special_needs,
                "notes":            notes_text,
                "pair_id":          "",
                "registered_class_name": row.get("Current Classes", "").strip(),
            })
        except Exception as e:
            warnings.append(f"Row {row_num}: unexpected error — {e} — skipped")

    if skipped_statuses:
        total_skipped = sum(skipped_statuses.values())
        breakdown = ", ".join(
            f"{status}: {n}" for status, n in sorted(skipped_statuses.items())
        )
        warnings.append(
            f"Skipped {total_skipped} student(s) with non-Active status ({breakdown}) — "
            "only Active students are imported."
        )

    # pair_id is intentionally left blank for every imported student: Jackrabbit
    # has no pairing concept, and pairing siblings automatically by Family was
    # unreliable (e.g. it paired siblings 4+ years apart, against HC-4). Staff
    # decide pairs manually by setting the same pair_id on both swimmers.
    if raw_rows:
        warnings.append(
            "pair_id is blank for all imported swimmers — set the same pair_id "
            "on two swimmers to pair them (pairs are no longer inferred from Family)."
        )

    unresolved_levels = sum(row["skill_level"] in (_DEFAULT_SKILL_LEVEL, "") for row in raw_rows)
    if unresolved_levels:
        warnings.append(
            f"skill_level is unresolved for {unresolved_levels} of {len(raw_rows)} "
            "imported swimmer(s). Staff must set those levels before running the solver."
        )

    # --- Build output CSV ----------------------------------------------------
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SWIMMERS_INTERNAL_HEADERS, lineterminator="\n")
    writer.writeheader()
    for r in raw_rows:
        writer.writerow({k: r[k] for k in SWIMMERS_INTERNAL_HEADERS})

    if raw_rows:
        warnings.append(
            f"Defaulted swimmer_type_id to {NON_RESPONSE_SWIMMER_TYPE_NAME} "
            f"(id={NON_RESPONSE_SWIMMER_TYPE_ID}) for imported students without survey data"
        )

    return output.getvalue(), warnings


# ---------------------------------------------------------------------------
# Instructors import
# ---------------------------------------------------------------------------

INSTRUCTORS_INTERNAL_HEADERS = [
    "instructor_id",
    "first_name",
    "last_name",
    "primary_color_id",
    "secondary_color_id",
    "primary_style_id",
    "secondary_style_id",
    "is_team_captain",
    "can_teach_NL",
    "can_teach_babies",
    "can_teach_adults",
    "can_teach_adapted",
    "used_default_profile",
    "profile_source",
]

def import_instructors(
    partner_csv_text: str,
    default_profile: dict | None = None,
    *,
    preserve_missing: bool = False,
) -> tuple[str, list[str]]:
    """Convert a partner ActiveStaff export into the internal instructors.csv format.

    ``preserve_missing`` is used by the versioned Jackrabbit bundle path. It
    keeps matcher-owned profile fields blank instead of inventing attributes
    that the exporter did not capture.
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(partner_csv_text))
    profile = default_profile or {}

    required = {"Staff ID", "Name", "Status"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Partner instructors file is missing required columns: {sorted(missing)}")

    out_rows: list[dict] = []
    seen_ids: set[str] = set()
    has_position_column = "Position" in (reader.fieldnames or [])

    for row_num, row in enumerate(reader, start=2):
        status = str(row.get("Status", "")).strip()
        if status.lower() != "active" and not (preserve_missing and not status):
            warnings.append(f"Row {row_num}: skipped (Status={status!r})")
            continue

        instructor_id_raw = row.get("Staff ID", "").strip()
        if not instructor_id_raw:
            warnings.append(f"Row {row_num}: skipped — missing Staff ID (Jackrabbit xID required)")
            continue
        if not instructor_id_raw.isascii() or not instructor_id_raw.isdigit():
            warnings.append(f"Row {row_num}: skipped — Staff ID {instructor_id_raw!r} is not a valid integer")
            continue
        instructor_id = instructor_id_raw

        position = " ".join(str(row.get("Position", "")).split())
        if has_position_column and not (preserve_missing and not position):
            if not is_editable_instructor_position(position):
                warnings.append(
                    f"Row {row_num}: skipped (Position={position!r}; expected one of {list(EDITABLE_INSTRUCTOR_POSITION_VALUES)})"
                )
                continue
        elif (
            "Instructor" in (reader.fieldnames or [])
            and not _is_truthy_export_value(row.get("Instructor", ""))
            and not (preserve_missing and not str(row.get("Instructor", "")).strip())
        ):
            warnings.append(f"Row {row_num}: skipped (Instructor flag is not truthy)")
            continue

        raw_name = " ".join(str(row.get("Name", "")).split())
        if not raw_name and not preserve_missing:
            warnings.append(f"Row {row_num}: skipped — no instructor name found")
            continue
        if not raw_name:
            warnings.append(
                f"Row {row_num}: Staff ID {instructor_id} has no name — identity retained "
                "with blank descriptive fields for review"
            )

        if instructor_id in seen_ids:
            warnings.append(f"Row {row_num}: duplicate Staff ID {instructor_id} skipped")
            continue
        seen_ids.add(instructor_id)

        first_name, last_name = _split_person_name(raw_name)
        used_default_profile = _is_truthy_export_value(row.get("used_default_profile", "0"))

        normalized_ids: dict[str, int | str] = {}
        for field in STYLE_COLOR_PROFILE_COLUMNS:
            if preserve_missing and not str(row.get(field, "")).strip():
                normalized_ids[field] = ""
                used_default_profile = True
                continue
            default_value = int(profile.get(field, {
                "primary_color_id": 1,
                "secondary_color_id": 2,
                "primary_style_id": 6,
                "secondary_style_id": 5,
            }[field]))
            parsed_value, did_default = _normalize_profile_int(row.get(field, ""), default_value)
            normalized_ids[field] = parsed_value
            used_default_profile = used_default_profile or did_default

        normalized_flags: dict[str, int | str] = {}
        for field in CERTIFICATION_PROFILE_COLUMNS:
            if preserve_missing and not str(row.get(field, "")).strip():
                normalized_flags[field] = ""
                used_default_profile = True
                continue
            default_value = bool(profile.get(field, {
                "is_team_captain": False,
                "can_teach_NL": True,
                "can_teach_babies": False,
                "can_teach_adults": False,
                "can_teach_adapted": False,
            }[field]))
            parsed_value, did_default = _normalize_profile_bool(row.get(field, ""), default_value)
            normalized_flags[field] = int(parsed_value)
            used_default_profile = used_default_profile or did_default

        out_rows.append({
            "instructor_id": instructor_id,
            "first_name": first_name,
            "last_name": last_name,
            "primary_color_id": normalized_ids["primary_color_id"],
            "secondary_color_id": normalized_ids["secondary_color_id"],
            "primary_style_id": normalized_ids["primary_style_id"],
            "secondary_style_id": normalized_ids["secondary_style_id"],
            "is_team_captain": normalized_flags["is_team_captain"],
            "can_teach_NL": normalized_flags["can_teach_NL"],
            "can_teach_babies": normalized_flags["can_teach_babies"],
            "can_teach_adults": normalized_flags["can_teach_adults"],
            "can_teach_adapted": normalized_flags["can_teach_adapted"],
            "used_default_profile": 1 if used_default_profile else 0,
            # The generation service uses this provenance marker to prevent
            # identity-only Jackrabbit records from silently receiving the
            # desktop's generic matcher defaults.
            "profile_source": 1 if preserve_missing else "",
        })

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=INSTRUCTORS_INTERNAL_HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

    if out_rows:
        if any(str(row["used_default_profile"]) == "1" for row in out_rows):
            warnings.append(
                (
                    "Jackrabbit staff identities have incomplete matcher-owned profile fields; "
                    "review colors, styles, and teaching qualifications before matching"
                    if preserve_missing
                    else "ActiveStaff import used default instructor profile values for colors, "
                    "styles, or teaching certifications where the export did not provide them"
                )
            )

    return output.getvalue(), warnings


# ---------------------------------------------------------------------------
# Historical pairings generator
# ---------------------------------------------------------------------------

HISTORICAL_PAIRINGS_HEADERS = ["swimmer_id", "instructor_id", "session", "num_sessions"]


def generate_historical_pairings(
    classes_filled_csv_text: str,
    session: str,
) -> tuple[str, list[str]]:
    """
    Build historical_pairings.csv from a completed session's classes_filled.csv.

    Each assigned swimmer is emitted once with num_sessions=1.
    Unfilled class rows (no swimmer_1_id) are skipped.

    Args:
        classes_filled_csv_text: Contents of classes_filled.csv from the last solver run.
        session: Session label for the output rows, e.g. "2026-Spring".

    Returns:
        (csv_text, warnings)
    """
    warnings: list[str] = []
    reader = csv.DictReader(io.StringIO(classes_filled_csv_text))

    required = {"instructor_id", "swimmer_1_id"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(
            f"classes_filled.csv is missing required columns: {sorted(missing)}. "
            "Ensure the file comes from a completed solver run."
        )

    out_rows: list[dict] = []
    skipped = 0

    for row in reader:
        instructor_id = row.get("instructor_id", "").strip()
        swimmer_1_id = row.get("swimmer_1_id", "").strip()

        if not instructor_id or not swimmer_1_id:
            skipped += 1
            continue

        out_rows.append({
            "swimmer_id": swimmer_1_id,
            "instructor_id": instructor_id,
            "session": session,
            "num_sessions": 1,
        })

        swimmer_2_id = row.get("swimmer_2_id", "").strip()
        if swimmer_2_id:
            out_rows.append({
                "swimmer_id": swimmer_2_id,
                "instructor_id": instructor_id,
                "session": session,
                "num_sessions": 1,
            })

    if skipped:
        warnings.append(f"{skipped} unfilled class slot(s) skipped (no swimmer assigned).")

    if not out_rows:
        warnings.append(
            "No pairings were generated — classes_filled.csv contained no assigned swimmers."
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HISTORICAL_PAIRINGS_HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

    return output.getvalue(), warnings
