import csv
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.csv_import import (
    import_classes,
    import_instructors,
    import_students,
    is_partner_classes_csv,
    is_partner_students_csv,
)
from backend.spreadsheet_import import read_tabular_file_text
from core.swimmer_types import NON_RESPONSE_SWIMMER_TYPE_ID
from solvers.python_cpsat.engine.data_loader import DataLoader as CpsatDataLoader


def _workspace_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "examples" / "demo" / "matching").is_dir():
            return parent
    raise RuntimeError("workspace root not found")


JACKRABBIT_CLASSES_CSV = """Class ID,Location,Class,Status,Session,Start Date,End Date,Days,Start Time,End Time,Instructors,Cat 1,Open,Size
00201,Synthetic Pool,RSS 1 Synthetic Class A,Active,Synthetic Session,4/27/2026,6/15/2026,Mon,07:30 AM,08:00 AM,Synthetic A.,RSS,0,2
00202,Synthetic Pool,RSS 5/6 Synthetic Class B,Active,Synthetic Session,4/27/2026,6/15/2026,Mon,07:30 AM,08:00 AM,"Synthetic B., Synthetic A.",RSS,0,2
00203,Synthetic Pool,Inactive Example,Inactive,Synthetic Session,4/27/2026,6/15/2026,Tue,08:00 AM,08:30 AM,Synthetic B.,RSS,0,2
"""

JACKRABBIT_STUDENTS_CSV = """Student ID,Student First Name,Student Last Name,Family,Status,Age,Notes
00101,Student,Example A,Synthetic Family,Active,"07 yrs, 08 mths",0
00102,Student,Example B,Synthetic Family,Active,"09 yrs, 00 mths",1
"""

ACTIVE_STAFF_CSV = """Staff ID,Name,Status,Instructor,Type
00301,Synthetic Instructor A,Active,1,Part-Time
00302,Synthetic Instructor B,Active,1,Part-Time
00303,Synthetic Front Desk,Active,0,Part-Time
00304,Synthetic Inactive Staff,Inactive,1,Part-Time
"""


def _write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    def col_name(index: int) -> str:
        value = ""
        current = index + 1
        while current:
            current, rem = divmod(current - 1, 26)
            value = chr(ord("A") + rem) + value
        return value

    row_xml_parts = []
    for row_index, row in enumerate(rows, start=1):
        cell_parts = []
        for col_index, value in enumerate(row, start=1):
            escaped = (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            cell_parts.append(
                f'<c r="{col_name(col_index - 1)}{row_index}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        row_xml_parts.append(f'<row r="{row_index}">{"".join(cell_parts)}</row>')

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
        '</worksheet>'
    )

    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '</Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)


def test_is_partner_students_csv_detects_age_column():
    """Detection must fire when Jackrabbit export has Age (not DOB)."""
    csv_with_age = (
        "Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "Alex,Smith,Active,10 yrs 0 mths,Smith Family,0\n"
    )
    assert is_partner_students_csv(csv_with_age) is True


def test_is_partner_students_csv_does_not_fire_on_internal_format():
    """Internal swimmers.csv must NOT be detected as partner format."""
    internal = "swimmer_id,first_name,last_name,swimmer_type_id,skill_level,age,has_special_needs,notes,pair_id\n"
    assert is_partner_students_csv(internal) is False


def test_import_students_warns_about_skill_level_zero():
    """import_students must include a summary warning about skill_level=0."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,10 yrs 0 mths,Synthetic Family,0\n"
    )
    _, warnings = import_students(csv_text)
    skill_warning = any("skill_level" in w.lower() for w in warnings)
    assert skill_warning, f"Expected a skill_level warning. Got: {warnings}"


def test_import_students_uses_exported_skill_level():
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Skill Level\n"
        "00101,Synthetic,Student,Active,10,Synthetic Family,6\n"
    )
    converted, warnings = import_students(csv_text)
    row = next(csv.DictReader(io.StringIO(converted)))

    assert row["skill_level"] == "6"
    assert not any("skill_level is unresolved" in warning for warning in warnings)


def test_import_students_infers_unambiguous_rss_level_from_current_class():
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Current Classes\n"
        "00101,Synthetic,Student,Active,10,Synthetic Family,RSS 5 Monday 4:00 pm\n"
    )
    converted, _ = import_students(csv_text)
    row = next(csv.DictReader(io.StringIO(converted)))

    assert row["skill_level"] == "5"


CLASSES_FILLED_CSV = """\
class_id,day_of_week,start_time,end_time,instructor_name,instructor_id,class_level,swimmer_1_name,swimmer_1_id,swimmer_2_name,swimmer_2_id,match_type,compatibility_score,match_confidence,match_reason,continuity_dispute,flag_codes,flag_summary,review_action,review_severity
1,Monday,07:30,08:00,Synthetic Instructor A,1,RSS 3,Synthetic Student A,10,,,,continuity,,Continuity: 1 session(s) together,False,,,, none
2,Monday,08:00,08:30,Synthetic Instructor B,2,RSS 4,Synthetic Student B,11,Synthetic Student C,12,pair,compatibility,80.0%,78.0%,Optimal compatibility match (80.0%),False,,,,none
3,Monday,08:30,09:00,Synthetic Instructor C,3,RSS 2,,,,,,,,,,False,,,,none
"""


def test_generate_historical_pairings_individual():
    from backend.csv_import import generate_historical_pairings
    result, warnings = generate_historical_pairings(CLASSES_FILLED_CSV, session="2026-Spring")
    rows = list(csv.DictReader(io.StringIO(result)))
    individual = next((r for r in rows if r["swimmer_id"] == "10"), None)
    assert individual is not None
    assert individual["instructor_id"] == "1"
    assert individual["session"] == "2026-Spring"
    assert individual["num_sessions"] == "1"


def test_generate_historical_pairings_pair():
    from backend.csv_import import generate_historical_pairings
    result, warnings = generate_historical_pairings(CLASSES_FILLED_CSV, session="2026-Spring")
    rows = list(csv.DictReader(io.StringIO(result)))
    ids = {r["swimmer_id"] for r in rows}
    assert "11" in ids
    assert "12" in ids


def test_generate_historical_pairings_skips_unfilled_classes():
    from backend.csv_import import generate_historical_pairings
    result, warnings = generate_historical_pairings(CLASSES_FILLED_CSV, session="2026-Spring")
    rows = list(csv.DictReader(io.StringIO(result)))
    assert len(rows) == 3  # swimmer 10, 11, 12 only


def test_generate_historical_pairings_all_unfilled():
    """All rows have no swimmer — returns empty pairings with a warning."""
    from backend.csv_import import generate_historical_pairings
    csv_text = (
        "class_id,instructor_id,swimmer_1_id,swimmer_2_id\n"
        "1,1,,\n"
        "2,2,,\n"
    )
    result, warnings = generate_historical_pairings(csv_text, session="2026-Spring")
    rows = list(csv.DictReader(io.StringIO(result)))
    assert rows == []
    assert any("no assigned" in w.lower() for w in warnings)


def test_generate_historical_pairings_missing_required_columns():
    """Raises ValueError when classes_filled.csv is missing required columns."""
    from backend.csv_import import generate_historical_pairings
    csv_text = "class_id,day_of_week\n1,Monday\n"
    with pytest.raises(ValueError, match="missing required columns"):
        generate_historical_pairings(csv_text, session="2026-Spring")


def test_generate_historical_pairings_warns_about_skipped_unfilled():
    """Warns when some rows are unfilled."""
    from backend.csv_import import generate_historical_pairings
    csv_text = (
        "class_id,instructor_id,swimmer_1_id,swimmer_2_id\n"
        "1,1,10,\n"
        "2,2,,\n"
    )
    _, warnings = generate_historical_pairings(csv_text, session="2026-Spring")
    assert any("unfilled" in w.lower() for w in warnings)


def test_import_classes_no_instructor_id_blanks_name():
    """When the input has no instructor_id column, both instructor_id and
    instructor_name must be blank — name-only rows are not supported."""
    assert is_partner_classes_csv(JACKRABBIT_CLASSES_CSV)

    converted, warnings = import_classes(JACKRABBIT_CLASSES_CSV)
    rows = list(csv.DictReader(io.StringIO(converted)))

    # No xID supplied → both fields must be empty (name-only matching is obsolete)
    assert all(row["instructor_id"] == "" for row in rows)
    assert all(row["instructor_name"] == "" for row in rows)
    assert [row["day_of_week"] for row in rows] == ["Mon", "Mon", "Mon"]
    assert [row["start_time"] for row in rows] == ["07:30 AM", "07:30 AM", "07:30 AM"]
    assert any("split into 2 rows" in warning for warning in warnings)
    assert any("skipped (Status='Inactive')" in warning for warning in warnings)


def test_import_students_defaults_missing_survey_type_to_non_response():
    converted, warnings = import_students(JACKRABBIT_STUDENTS_CSV)
    rows = list(csv.DictReader(io.StringIO(converted)))

    assert rows
    assert all(int(row["swimmer_type_id"]) == NON_RESPONSE_SWIMMER_TYPE_ID for row in rows)
    assert any("Non-Response / Unknown" in warning for warning in warnings)


def test_import_students_does_not_set_has_special_needs_from_notes_count():
    """A numeric Notes count must never set has_special_needs."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,7,Synthetic Family,1\n"
    )
    converted, _ = import_students(csv_text)
    row = next(csv.DictReader(io.StringIO(converted)))
    assert row["has_special_needs"].lower() in ("0", "false", "")


def _is_truthy_csv(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y")


def test_import_students_uses_special_needs_column_when_present():
    """A dedicated Special Needs column takes precedence for has_special_needs."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes,Special Needs\n"
        "00101,Synthetic,Student A,Active,7,Synthetic Family A,0,1\n"
        "00102,Synthetic,Student B,Active,9,Synthetic Family B,0,0\n"
    )
    converted, _ = import_students(csv_text)
    rows = list(csv.DictReader(io.StringIO(converted)))
    assert _is_truthy_csv(rows[0]["has_special_needs"])
    assert not _is_truthy_csv(rows[1]["has_special_needs"])


def test_import_students_warns_when_notes_count_nonzero_and_no_special_needs_column():
    """Warn the user when Notes is a nonzero count but there's no Special Needs column."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,8,Synthetic Family,2\n"
    )
    _, warnings = import_students(csv_text)
    assert any("notes count" in w.lower() and "special needs" in w.lower() for w in warnings)


def test_import_students_text_notes_preserved_for_solver():
    """Text-valued Notes are passed through to the notes field for the solver's notes_parser."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,10,Synthetic Family,prefer Synthetic Instructor A\n"
    )
    converted, _ = import_students(csv_text)
    row = next(csv.DictReader(io.StringIO(converted)))
    assert row["notes"] == "prefer Synthetic Instructor A"
    assert not _is_truthy_csv(row["has_special_needs"])


def test_import_students_text_notes_do_not_set_has_special_needs():
    """Text in Notes must not cause has_special_needs to be set."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,6,Synthetic Family,avoid Synthetic Instructor B\n"
    )
    converted, _ = import_students(csv_text)
    row = next(csv.DictReader(io.StringIO(converted)))
    assert not _is_truthy_csv(row["has_special_needs"])


def test_import_students_notes_count_zero_no_warning():
    """Notes=0 should not produce any notes-count warning."""
    csv_text = (
        "Student ID,Student First Name,Student Last Name,Status,Age,Family,Notes\n"
        "00101,Synthetic,Student,Active,5,Synthetic Family,0\n"
    )
    _, warnings = import_students(csv_text)
    assert not any("notes count" in w.lower() for w in warnings)


def test_import_instructors_from_active_staff_defaults_missing_profile_fields():
    converted, warnings = import_instructors(ACTIVE_STAFF_CSV)
    rows = list(csv.DictReader(io.StringIO(converted)))

    assert [row["first_name"] for row in rows] == ["Synthetic", "Synthetic"]
    assert [row["last_name"] for row in rows] == ["Instructor A", "Instructor B"]
    assert all(row["primary_style_id"] == "6" for row in rows)
    assert all(row["can_teach_babies"] == "0" for row in rows)
    assert all(row["can_teach_adults"] == "0" for row in rows)
    assert all(row["can_teach_adapted"] == "0" for row in rows)
    assert all(row["used_default_profile"] == "1" for row in rows)
    assert any("default instructor profile values" in warning for warning in warnings)


def test_import_instructors_uses_configured_default_profile():
    converted, _ = import_instructors(
        ACTIVE_STAFF_CSV,
        default_profile={
            "primary_color_id": 4,
            "secondary_color_id": 3,
            "primary_style_id": 2,
            "secondary_style_id": 1,
            "is_team_captain": True,
            "can_teach_NL": False,
            "can_teach_babies": False,
            "can_teach_adults": True,
            "can_teach_adapted": False,
        },
    )
    row = next(csv.DictReader(io.StringIO(converted)))

    assert row["primary_color_id"] == "4"
    assert row["secondary_style_id"] == "1"
    assert row["is_team_captain"] == "1"
    assert row["can_teach_NL"] == "0"


def test_import_instructors_filters_to_editable_positions_and_preserves_source_profile_values():
    source_csv = """Staff ID,Name,Status,Position,Instructor,primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,is_team_captain,can_teach_NL,can_teach_babies,can_teach_adults,can_teach_adapted,used_default_profile
00301,Synthetic Coach,Active,Coach,1,4,3,2,1,0,1,1,1,1,0
00303,Synthetic Front Desk,Active,Customer Service,1,2,1,6,5,0
00302,Synthetic Youth Leader,Active,Youth Leader,1,,,,,
"""
    converted, _ = import_instructors(
        source_csv,
        default_profile={
            "primary_color_id": 1,
            "secondary_color_id": 2,
            "primary_style_id": 6,
            "secondary_style_id": 5,
            "is_team_captain": False,
            "can_teach_NL": True,
            "can_teach_babies": True,
            "can_teach_adults": True,
            "can_teach_adapted": True,
        },
    )
    rows = list(csv.DictReader(io.StringIO(converted)))

    assert [f"{row['first_name']} {row['last_name']}".strip() for row in rows] == [
        "Synthetic Coach",
        "Synthetic Youth Leader",
    ]
    assert rows[0]["primary_color_id"] == "4"
    assert rows[0]["secondary_style_id"] == "1"
    assert rows[0]["used_default_profile"] == "0"
    assert rows[1]["primary_color_id"] == "1"
    assert rows[1]["used_default_profile"] == "1"


def test_import_instructors_accepts_compound_editable_positions():
    source_csv = """Staff ID,Name,Status,Position,Instructor
00301,Synthetic Instructor A,Active,Instructor Office Staff,1
00302,Synthetic Instructor B,Active,Instructor Team Captain Office Staff,1
00303,Synthetic Front Desk,Active,Customer Service Office Staff,1
"""
    converted, warnings = import_instructors(source_csv)
    rows = list(csv.DictReader(io.StringIO(converted)))

    assert [f"{row['first_name']} {row['last_name']}".strip() for row in rows] == [
        "Synthetic Instructor A",
        "Synthetic Instructor B",
    ]
    assert not any("Synthetic Instructor A" in warning and "skipped" in warning for warning in warnings)
    assert not any("Synthetic Instructor B" in warning and "skipped" in warning for warning in warnings)


def test_import_classes_accepts_excel_serial_dates():
    serial_date_classes_csv = """Class ID,Location,Class,Status,Session,Start Date,End Date,Days,Start Time,End Time,Instructors,Cat 1,Open,Size
00201,Synthetic Pool,RSS 1 Synthetic Class,Active,Synthetic Session,46139,46188,Mon,07:30 AM,08:00 AM,Synthetic A.,RSS,0,2
"""
    converted, _ = import_classes(serial_date_classes_csv)
    row = next(csv.DictReader(io.StringIO(converted)))
    assert row["start_date"] == "2026-04-27"
    assert row["end_date"] == "2026-06-15"


def test_read_tabular_file_text_reads_xlsx_workbooks(tmp_path):
    workbook_path = tmp_path / "students.xlsx"
    _write_minimal_xlsx(
        workbook_path,
        [
            ["Student First Name", "Student Last Name", "Family", "Status", "Age", "Notes"],
            ["Alice", "Smith", "Smith Family", "Active", "07 yrs, 08 mths", "0"],
        ],
    )

    text = read_tabular_file_text(workbook_path)

    assert "Student First Name,Student Last Name,Family,Status,Age,Notes" in text
    assert "Alice,Smith,Smith Family,Active" in text


@pytest.mark.parametrize(
    "loader_cls",
    [CpsatDataLoader],
)
def test_imported_jackrabbit_classes_without_instructor_id_yield_no_instructor(tmp_path, loader_cls):
    """When imported classes have no instructor_id (Jackrabbit export without xID column),
    both instructor_id and instructor_name are blank in the internal CSV.  The DataLoader
    must load the classes successfully but leave instructor_id as None — name-only matching
    is not supported."""
    sample_dir = _workspace_root() / "examples" / "demo" / "matching"
    converted, _ = import_classes(JACKRABBIT_CLASSES_CSV)
    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(converted, encoding="utf-8")

    loader = loader_cls.from_files(
        classes_path=classes_path,
        swimmers_path=sample_dir / "swimmers.csv",
        instructors_path=sample_dir / "instructors.csv",
        historical_path=sample_dir / "historical_pairings.csv",
        source_dir=_workspace_root() / "data" / "source",
    )

    sorted_ids = sorted(loader.classes)
    # No xID → DataLoader has no instructor to resolve; all return None
    assert all(loader.classes[cid].instructor_id is None for cid in sorted_ids)
    first_class = loader.classes[sorted_ids[0]]
    assert first_class.day_of_week == "Monday"
    assert first_class.start_time == "07:30"
    assert first_class.end_time == "08:00"


@pytest.mark.parametrize(
    "loader_cls",
    [CpsatDataLoader],
)
def test_imported_active_staff_resolves_full_instructor_names(tmp_path, loader_cls):
    sample_dir = _workspace_root() / "examples" / "demo" / "matching"
    instructors_csv, _ = import_instructors(ACTIVE_STAFF_CSV)
    instructors_path = tmp_path / "instructors.csv"
    instructors_path.write_text(instructors_csv, encoding="utf-8")

    classes_path = tmp_path / "classes.csv"
    classes_path.write_text(
        "\n".join([
            "class_id,start_time,end_time,day_of_week,location,class_name,session,instructor_name,open,size,status,cat_1,cat_2,start_date,end_date",
            "1,07:30 AM,08:00 AM,Mon,Synthetic Pool,Synthetic Class A,Synthetic Session,Synthetic Instructor A,0,2,Active,RSS,,2026-04-27,2026-06-15",
            "2,08:00 AM,08:30 AM,Mon,Synthetic Pool,Synthetic Class B,Synthetic Session,Synthetic Instructor B,0,2,Active,RSS,,2026-04-27,2026-06-15",
        ]),
        encoding="utf-8",
    )

    loader = loader_cls.from_files(
        classes_path=classes_path,
        swimmers_path=sample_dir / "swimmers.csv",
        instructors_path=instructors_path,
        historical_path=None,
        source_dir=_workspace_root() / "data" / "source",
    )

    assert [loader.classes[class_id].instructor_id for class_id in sorted(loader.classes)] == ["00301", "00302"]
