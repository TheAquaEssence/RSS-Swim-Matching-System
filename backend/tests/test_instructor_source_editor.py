import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

from backend.instructor_source_editor import _load_payload, _save_payload
from backend.spreadsheet_import import read_tabular_file_text


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


def test_instructor_source_editor_normalizes_partner_workbook_and_saves_updates(tmp_path):
    workbook_path = tmp_path / "ActiveStaff.xlsx"
    _write_minimal_xlsx(
        workbook_path,
        [
            ["Name", "Status", "Position", "Instructor", "Type"],
            ["Coach One", "Active", "Coach", "1", "Part-Time"],
            ["Customer Service Example", "Active", "Customer Service", "1", "Part-Time"],
            ["Youth Leader Example", "Active", "Youth Leader", "1", "Part-Time"],
        ],
    )

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "default_files": {
                    "instructors": str(workbook_path),
                    "personality_colors": "",
                    "instructor_styles": "",
                },
                "last_selected_files": {
                    "instructors": str(workbook_path),
                    "personality_colors": "",
                    "instructor_styles": "",
                },
                "default_instructor_profile": {
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
            }
        ),
        encoding="utf-8",
    )

    payload = _load_payload(tmp_path, tmp_path, settings_path)

    assert payload["ok"] is True
    assert payload["editable_count"] == 2
    assert [row["name"] for row in payload["instructors"]] == ["Coach One", "Youth Leader Example"]
    assert all(row["used_default_profile"] for row in payload["instructors"])

    normalized_rows = list(csv.DictReader(io.StringIO(read_tabular_file_text(workbook_path))))
    assert "primary_color_id" in normalized_rows[0]
    assert normalized_rows[0]["primary_color_id"] == "1"
    assert normalized_rows[1]["primary_color_id"] == ""

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "updates": [
                    {
                        "source_row_number": payload["instructors"][0]["source_row_number"],
                        "primary_color_id": 4,
                        "secondary_color_id": 3,
                        "primary_style_id": 2,
                        "secondary_style_id": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    saved_payload = _save_payload(tmp_path, tmp_path, settings_path, request_path)
    edited_row = next(row for row in saved_payload["instructors"] if row["name"] == "Coach One")
    assert edited_row["primary_color_id"] == 4
    assert edited_row["used_default_profile"] is False

    saved_rows = list(csv.DictReader(io.StringIO(read_tabular_file_text(workbook_path))))
    assert saved_rows[0]["primary_color_id"] == "4"
    assert saved_rows[0]["secondary_style_id"] == "1"
    assert saved_rows[0]["used_default_profile"] == "0"
