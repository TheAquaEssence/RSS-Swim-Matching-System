from __future__ import annotations

import csv
import io
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.jackrabbit_bundle import (
    BUNDLE_FORMAT,
    CLASSES_FILE,
    FILE_HEADERS,
    PAIRINGS_FILE,
    STAFF_FILE,
    STUDENTS_FILE,
    parse_jackrabbit_bundle,
)


def _csv_text(filename: str, rows: list[list[str]] | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(FILE_HEADERS[filename])
    writer.writerows(rows or [])
    return output.getvalue()


def _complete_files() -> dict[str, str]:
    return {
        STUDENTS_FILE: _csv_text(
            STUDENTS_FILE,
            [[
                "00101", "Ada, Jr.", "Example", "Example Family", "Active",
                "1/1/2018", "8 yrs, 0 mths", "RSS 4 Monday", "4",
                'Line one\r\nLine "two"', "",
            ]],
        ),
        CLASSES_FILE: _csv_text(
            CLASSES_FILE,
            [
                [
                    "00201", "RSS 4 Monday", "00301", "Grace Coach", "Mon",
                    "04:00 PM", "04:30 PM", "Pool", "Active", "Fall 2026",
                    "9/1/2026", "12/1/2026", "RSS", "1", "2",
                ],
                [
                    "00201", "RSS 4 Monday", "00302", "Robin Coach", "Mon",
                    "04:00 PM", "04:30 PM", "Pool", "Active", "Fall 2026",
                    "9/1/2026", "12/1/2026", "RSS", "1", "2",
                ],
            ],
        ),
        STAFF_FILE: _csv_text(
            STAFF_FILE,
            [
                ["00301", "Grace Coach", "Active", "Instructor", "1"],
                ["00302", "Robin Coach", "Active", "Instructor", "1"],
            ],
        ),
        PAIRINGS_FILE: _csv_text(
            PAIRINGS_FILE,
            [["00101", "00199", "00301", "RSS 3 Monday", "Spring 2026", "archived"]],
        ),
    }


def make_bundle(
    *,
    version: object = 1,
    bundle_format: str = BUNDLE_FORMAT,
    exported_at: str = "2026-08-12T12:00:00.000Z",
    exporter: dict | None = None,
    files: dict[str, str] | None = None,
) -> bytes:
    return json.dumps(
        {
            "format": bundle_format,
            "format_version": version,
            "exported_at": exported_at,
            "exporter": exporter or {"name": "Jackrabbit Exporter", "version": "1.1.0"},
            "files": _complete_files() if files is None else files,
        }
    ).encode("utf-8")


def _test_services(tmp_path):
    paths = replace(
        server.DEFAULT_BACKEND_PATHS,
        app_data_root=tmp_path,
        jobs_dir=tmp_path / "jobs",
        settings_path=tmp_path / "settings" / "user_settings.json",
        database_path=tmp_path / "data" / "aqua_essence.db",
        writable_resources_dir=tmp_path / "resources",
    )
    return server.create_application_services(
        paths=paths,
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
    )


def _post_bundle(
    client: TestClient,
    raw: bytes,
    *,
    filename: str = "aqua_essence_jackrabbit_export.json",
):
    return client.post(
        "/api/jackrabbit/import",
        files={"file": (filename, raw, "application/json")},
        data={"operator": "Synthetic Operator"},
    )


def _selected_csv(services, key: str) -> list[dict[str, str]]:
    path = services.state.settings["last_selected_files"][key]
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_parse_complete_bundle_validates_metadata_headers_and_csv_escaping():
    bundle = parse_jackrabbit_bundle(make_bundle())

    assert bundle.exporter_name == "Jackrabbit Exporter"
    assert bundle.exporter_version == "1.1.0"
    assert bundle.row_counts[STUDENTS_FILE] == 1
    assert bundle.row_counts[CLASSES_FILE] == 2
    student = next(csv.DictReader(io.StringIO(bundle.files[STUDENTS_FILE], newline="")))
    assert student["Student First Name"] == "Ada, Jr."
    assert student["Notes"] == 'Line one\r\nLine "two"'


def test_header_only_pairings_and_staff_are_valid_optional_data():
    files = _complete_files()
    files[STAFF_FILE] = _csv_text(STAFF_FILE)
    files[PAIRINGS_FILE] = _csv_text(PAIRINGS_FILE)

    bundle = parse_jackrabbit_bundle(make_bundle(files=files))

    assert bundle.row_counts[STAFF_FILE] == 0
    assert bundle.row_counts[PAIRINGS_FILE] == 0
    assert any("staff payload is header-only" in warning for warning in bundle.warnings)
    assert any("pairings payload is header-only" in warning for warning in bundle.warnings)


@pytest.mark.parametrize("missing_filename", [STUDENTS_FILE, CLASSES_FILE, STAFF_FILE, PAIRINGS_FILE])
def test_files_object_requires_exactly_four_contract_keys(missing_filename):
    files = _complete_files()
    del files[missing_filename]

    with pytest.raises(ValueError, match="must contain exactly the four"):
        parse_jackrabbit_bundle(make_bundle(files=files))


def test_students_and_classes_require_data_rows():
    files = _complete_files()
    files[STUDENTS_FILE] = _csv_text(STUDENTS_FILE)

    with pytest.raises(ValueError, match="students and classes are required"):
        parse_jackrabbit_bundle(make_bundle(files=files))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"version": 2}, "Unsupported Jackrabbit export version"),
        ({"version": True}, "Unsupported Jackrabbit export version"),
        ({"bundle_format": "something-else"}, "Unsupported Jackrabbit export format"),
        ({"exported_at": "not-a-date"}, "ISO-8601"),
        ({"exported_at": "2026-08-12T12:00:00"}, "timezone"),
        ({"exporter": {"name": "Other", "version": "1.1.0"}}, "Unsupported exporter name"),
        (
            {"exporter": {"name": "Jackrabbit Exporter", "version": "1.0.0"}},
            "Unsupported exporter version",
        ),
    ],
)
def test_invalid_contract_metadata_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        parse_jackrabbit_bundle(make_bundle(**kwargs))


def test_locked_header_rejects_reordered_or_extra_columns():
    files = _complete_files()
    files[STAFF_FILE] = "Name,Staff ID,Status,Position,Instructor,Extra\r\nCoach,1,Active,Instructor,1,x\r\n"

    with pytest.raises(ValueError, match="header does not match format version 1"):
        parse_jackrabbit_bundle(make_bundle(files=files))


def test_desktop_import_requires_the_contract_filename(tmp_path):
    services = _test_services(tmp_path)

    response = _post_bundle(
        TestClient(server.create_app(services)),
        make_bundle(),
        filename="renamed-export.json",
    )

    assert response.status_code == 400
    assert "aqua_essence_jackrabbit_export.json" in response.json()["error"]
    assert services.state.settings["last_selected_files"]["classes"] == ""


def test_required_rows_that_all_fail_conversion_are_rejected(tmp_path):
    files = _complete_files()
    files[CLASSES_FILE] = _csv_text(
        CLASSES_FILE,
        [[
            "not-numeric", "Synthetic Class", "00301", "Synthetic Coach", "Mon",
            "04:00 PM", "04:30 PM", "Pool", "Active", "Synthetic Session",
            "9/1/2026", "12/1/2026", "RSS", "1", "2",
        ]],
    )
    services = _test_services(tmp_path)

    response = _post_bundle(TestClient(server.create_app(services)), make_bundle(files=files))

    assert response.status_code == 400
    assert "did not contain any usable records after conversion" in response.json()["error"]
    assert services.state.settings["last_selected_files"]["classes"] == ""


def test_desktop_import_preserves_leading_zero_ids_quoted_newlines_and_multi_instructors(tmp_path):
    services = _test_services(tmp_path)
    response = _post_bundle(TestClient(server.create_app(services)), make_bundle())

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["instructors_added"] == 2
    assert payload["pairings_imported"] == 1
    assert payload["sessions"] == ["Spring 2026"]

    swimmers = _selected_csv(services, "swimmers")
    assert swimmers[0]["swimmer_id"] == "00101"
    assert swimmers[0]["notes"] == 'Line one\r\nLine "two"'
    assert swimmers[0]["has_special_needs"] == ""

    classes = _selected_csv(services, "classes")
    assert [(row["class_id"], row["instructor_id"]) for row in classes] == [
        ("00201", "00301"),
        ("00201", "00302"),
    ]
    assert services.repository.get_instructor("00301")["instructor_id"] == "00301"

    history = list(csv.DictReader(io.StringIO(services.repository.load_historical_pairings_csv())))
    assert history[0]["swimmer_id"] == "00101"
    assert history[0]["instructor_id"] == "00301"


def test_header_only_staff_is_supplemented_from_class_identity_without_invented_fields(tmp_path):
    files = _complete_files()
    files[CLASSES_FILE] = _csv_text(
        CLASSES_FILE,
        [[
            "00077", "Synthetic Class", "00009", "Taylor Example", "Tue",
            "05:00 PM", "05:30 PM", "Pool", "Active", "Synthetic Session",
            "1/1/2026", "2/1/2026", "", "1", "2",
        ]],
    )
    files[STAFF_FILE] = _csv_text(STAFF_FILE)
    files[PAIRINGS_FILE] = _csv_text(PAIRINGS_FILE)
    services = _test_services(tmp_path)

    response = _post_bundle(TestClient(server.create_app(services)), make_bundle(files=files))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["staff_supplemented_from_classes"] == 1
    assert payload["instructors_added"] == 1
    identity = services.repository.get_instructor("00009")
    assert identity["first_name"] == "Taylor"
    assert identity["primary_color_id"] is None
    assert identity["primary_style_id"] is None
    assert identity["can_teach_adapted"] == 0
    assert any("identity fields only" in warning for warning in payload["warnings"])

    generation = TestClient(server.create_app(services)).post(
        "/api/generate",
        json={"selected_session_ids": []},
    )
    assert generation.status_code == 400
    assert "Instructor profiles are incomplete" in generation.json()["error"]


def test_skipped_historical_pairings_are_reported_as_warnings(tmp_path):
    files = _complete_files()
    files[PAIRINGS_FILE] = _csv_text(
        PAIRINGS_FILE,
        [["00101", "00201", "00301", "Synthetic Class", "", "archived"]],
    )
    services = _test_services(tmp_path)

    response = _post_bundle(TestClient(server.create_app(services)), make_bundle(files=files))

    assert response.status_code == 200
    payload = response.json()
    assert payload["pairings_imported"] == 0
    assert payload["pairings_skipped"] == 1
    assert any("historical pairing row(s) were skipped" in item for item in payload["warnings"])


def test_incomplete_optional_staff_fields_are_warnings_not_silent_defaults(tmp_path):
    files = _complete_files()
    files[STAFF_FILE] = _csv_text(STAFF_FILE, [["00301", "", "", "", ""]])
    services = _test_services(tmp_path)

    response = _post_bundle(TestClient(server.create_app(services)), make_bundle(files=files))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert any("blank descriptive fields" in warning for warning in payload["warnings"])
    assert any("incomplete matcher-owned profile fields" in warning for warning in payload["warnings"])


def test_bundle_reimport_preserves_existing_curated_instructor_profile(tmp_path):
    services = _test_services(tmp_path)
    client = TestClient(server.create_app(services))
    assert _post_bundle(client, make_bundle()).status_code == 200
    services.repository.update_instructor(
        "00301",
        {
            "primary_color_id": 4,
            "secondary_color_id": 3,
            "primary_style_id": 2,
            "secondary_style_id": 1,
            "can_teach_adapted": 1,
        },
    )

    response = _post_bundle(client, make_bundle())

    assert response.status_code == 200
    assert response.json()["instructors_added"] == 0
    instructor = services.repository.get_instructor("00301")
    assert instructor["primary_color_id"] == 4
    assert instructor["can_teach_adapted"] == 1


def test_completed_bundle_flows_through_solver_profiles_results_and_export(tmp_path):
    files = _complete_files()
    student_rows = list(csv.reader(io.StringIO(files[STUDENTS_FILE], newline="")))
    student_rows[1][-1] = "0"
    files[STUDENTS_FILE] = _csv_text(STUDENTS_FILE, student_rows[1:])

    services = _test_services(tmp_path)
    client = TestClient(server.create_app(services))
    imported = _post_bundle(client, make_bundle(files=files))
    assert imported.status_code == 200, imported.text

    for instructor_id in ("00301", "00302"):
        services.repository.update_instructor(
            instructor_id,
            {
                "primary_color_id": 1,
                "secondary_color_id": 2,
                "primary_style_id": 1,
                "secondary_style_id": 2,
                "is_team_captain": 0,
                "can_teach_babies": 0,
                "can_teach_adults": 0,
                "can_teach_adapted": 0,
            },
        )

    generated = client.post("/api/generate", json={"selected_session_ids": []})

    assert generated.status_code == 200, generated.text
    assert generated.json()["ok"] is True
    job_dir = Path(services.state.last_job_dir)
    with (job_dir / "classes_filled.csv").open(encoding="utf-8", newline="") as handle:
        output_rows = list(csv.DictReader(handle))
    assert {(row["class_id"], row["instructor_id"]) for row in output_rows} == {
        ("00201", "00301"),
        ("00201", "00302"),
    }
    assert {row["swimmer_1_id"] for row in output_rows} == {"", "00101"}

    profiles = json.loads((job_dir / "profiles.json").read_text(encoding="utf-8"))
    assert profiles["swimmers"]["00101"]["swimmer_id"] == "00101"
    assert profiles["instructors"]["00301"]["instructor_id"] == "00301"
