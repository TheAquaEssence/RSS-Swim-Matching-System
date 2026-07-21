"""Tests for /api/instructors/import/preview and /api/instructors/import/apply."""
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.server import app


@pytest.fixture
def client(tmp_path):
    db.init_db(tmp_path / "test.db")
    return TestClient(app)


INTERNAL_CSV = (
    "instructor_id,first_name,last_name,"
    "primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
    "is_team_captain,can_teach_babies,can_teach_adults,can_teach_adapted,"
    "used_default_profile\n"
    "101,Ada,Lovelace,1,2,3,4,0,1,1,0,0\n"
    "102,Grace,Hopper,1,2,3,4,1,1,1,1,0\n"
)

PARTNER_CSV = (
    "Staff ID,Name,Status,Position\n"
    "201,Mary Jackson,Active,Instructor\n"
    "202,Inactive Person,Inactive,Instructor\n"
)


def test_preview_multipart_upload(client):
    response = client.post(
        "/api/instructors/import/preview",
        files={"file": ("instructors.csv", INTERNAL_CSV, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["new"]) == 2
    assert data["changed"] == []
    assert data["csv"].startswith("instructor_id")


def test_preview_json_body(client):
    response = client.post("/api/instructors/import/preview", json={"csv": INTERNAL_CSV})
    assert response.status_code == 200
    assert len(response.json()["new"]) == 2


def test_preview_empty_csv_rejected(client):
    response = client.post("/api/instructors/import/preview", json={"csv": "  "})
    assert response.status_code == 400


def test_preview_bad_headers_rejected(client):
    response = client.post("/api/instructors/import/preview", json={"csv": "foo,bar\n1,2\n"})
    assert response.status_code == 400


def test_preview_converts_partner_format(client):
    response = client.post("/api/instructors/import/preview", json={"csv": PARTNER_CSV})
    assert response.status_code == 200
    data = response.json()
    new_ids = {row["instructor_id"] for row in data["new"]}
    assert "201" in new_ids          # active instructor converted
    assert "202" not in new_ids      # inactive row skipped
    assert data["csv"].startswith("instructor_id")  # normalized internal CSV returned


def test_apply_only_accepted(client):
    response = client.post(
        "/api/instructors/import/apply",
        json={"csv": INTERNAL_CSV, "accepted_ids": ["101"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert (data["created"], data["updated"]) == (1, 0)
    assert db.get_instructor("101") is not None
    assert db.get_instructor("102") is None


def test_apply_requires_accepted_ids(client):
    response = client.post(
        "/api/instructors/import/apply",
        json={"csv": INTERNAL_CSV, "accepted_ids": []},
    )
    assert response.status_code == 400


def test_apply_requires_json_content_type(client):
    response = client.post(
        "/api/instructors/import/apply",
        content="csv=x",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_preview_then_apply_flow(client):
    # Seed one instructor, then preview a CSV that changes them and adds one
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101", "102"]})

    updated_csv = INTERNAL_CSV.replace("Ada,Lovelace", "Ada,Byron")
    preview = client.post("/api/instructors/import/preview", json={"csv": updated_csv}).json()
    assert [c["instructor_id"] for c in preview["changed"]] == ["101"]
    assert preview["unchanged"] == 1

    apply_resp = client.post(
        "/api/instructors/import/apply",
        json={"csv": preview["csv"], "accepted_ids": ["101"]},
    ).json()
    assert (apply_resp["created"], apply_resp["updated"]) == (0, 1)
    assert db.get_instructor("101")["last_name"] == "Byron"


def test_apply_field_level_selection(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101"]})

    updated_csv = INTERNAL_CSV.replace("Ada,Lovelace,1,2,3,4,0,1,1,0", "Ada,Byron,1,2,3,4,0,1,1,1")
    response = client.post(
        "/api/instructors/import/apply",
        json={"csv": updated_csv, "accepted_ids": [{"instructor_id": "101", "fields": ["last_name"]}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert (data["created"], data["updated"]) == (0, 1)
    inst = db.get_instructor("101")
    assert inst["last_name"] == "Byron"
    assert inst["can_teach_adapted"] == 0  # rejected field unchanged


def test_export_has_bom_and_dated_filename(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101"]})
    response = client.get("/api/instructors/export")
    assert response.status_code == 200
    assert response.text.startswith("﻿instructor_id")
    disposition = response.headers["content-disposition"]
    assert "instructors_" in disposition and disposition.endswith(".csv")


def test_export_filters_match_view(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101", "102"]})
    # name filter
    response = client.get("/api/instructors/export", params={"q": "grace"})
    body = response.text.lstrip("﻿")
    assert "Grace" in body and "Lovelace" not in body
    # needs_update filter: both seeded rows are complete, so the export is headers-only
    response = client.get("/api/instructors/export", params={"needs_update": "true"})
    lines = [l for l in response.text.lstrip("﻿").strip().splitlines() if l]
    assert len(lines) == 1


def test_bom_export_reimports_cleanly(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101", "102"]})
    exported = client.get("/api/instructors/export").text  # includes BOM
    preview = client.post("/api/instructors/import/preview", json={"csv": exported}).json()
    assert preview["ok"] is True
    assert preview["new"] == [] and preview["changed"] == []
    assert preview["unchanged"] == 2


def test_preview_accepts_xlsx_upload(client, tmp_path):
    from backend.tests.test_csv_import import _write_minimal_xlsx

    rows = [
        ["instructor_id", "first_name", "last_name",
         "primary_color_id", "secondary_color_id", "primary_style_id", "secondary_style_id",
         "is_team_captain", "can_teach_babies", "can_teach_adults", "can_teach_adapted",
         "used_default_profile"],
        ["101", "Ada", "Lovelace", "1", "2", "3", "4", "0", "1", "1", "0", "0"],
    ]
    workbook = tmp_path / "instructors.xlsx"
    _write_minimal_xlsx(workbook, rows)

    response = client.post(
        "/api/instructors/import/preview",
        files={"file": ("instructors.xlsx", workbook.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["new"]) == 1
    assert data["new"][0]["first_name"] == "Ada"


def test_preview_rejects_corrupt_xlsx(client):
    response = client.post(
        "/api/instructors/import/preview",
        files={"file": ("broken.xlsx", b"PK\x03\x04garbage", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_undo_endpoint_flow(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101", "102"]})

    last = client.get("/api/instructors/import/last").json()
    assert last["last_import"]["summary"] == "2 added, 0 updated"

    response = client.post("/api/instructors/import/undo", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["removed"] == 2 and data["restored"] == 0
    assert db.get_instructor("101") is None

    # nothing left to undo
    assert client.get("/api/instructors/import/last").json()["last_import"] is None
    assert client.post("/api/instructors/import/undo", json={}).status_code == 400


def test_solver_export_includes_can_teach_nl(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101"]})
    csv_text = db.export_instructors_solver_csv()
    lines = csv_text.strip().splitlines()
    header = lines[0].split(",")
    assert "can_teach_NL" in header
    row = dict(zip(header, lines[1].split(",")))
    assert row["can_teach_NL"] == "1"
    assert row["instructor_id"] == "101"


def test_use_db_instructors_toggle_requires_instructors(client):
    # empty DB → enabling is rejected
    response = client.post("/api/settings/use_db_instructors", json={"enabled": True})
    assert response.status_code == 400

    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101"]})
    response = client.post("/api/settings/use_db_instructors", json={"enabled": True})
    assert response.status_code == 200
    assert response.json()["instructor_count"] == 1
    assert client.get("/api/settings").json()["use_db_instructors"] is True

    # disabling always works
    response = client.post("/api/settings/use_db_instructors", json={"enabled": False})
    assert response.status_code == 200
    assert client.get("/api/settings").json()["use_db_instructors"] is False


HUMAN_CSV = (
    "instructor_id,first_name,last_name,"
    "primary_color,secondary_color,primary_style,secondary_style,"
    "is_team_captain,can_teach_babies,can_teach_adults,can_teach_adapted\n"
    "201,Mary,Jackson,Blue,Orange,Technique Driven,Adapted,,X,Yes,true\n"
)


def test_import_parses_human_friendly_format(client):
    preview = client.post("/api/instructors/import/preview", json={"csv": HUMAN_CSV}).json()
    assert preview["ok"] is True
    row = preview["new"][0]
    # names resolved to ids via the data/source reference tables
    assert isinstance(row["primary_color_id"], int)
    assert isinstance(row["primary_style_id"], int)
    # X / Yes / true / blank all parsed
    assert row["can_teach_babies"] == 1
    assert row["can_teach_adults"] == 1
    assert row["can_teach_adapted"] == 1
    assert row["is_team_captain"] == 0


def test_import_fuzzy_matches_misspelled_names_with_warning(client):
    csv_text = HUMAN_CSV.replace("Blue", "Bleu")
    preview = client.post("/api/instructors/import/preview", json={"csv": csv_text}).json()
    assert preview["ok"] is True
    assert any("interpreted as" in w and "Bleu" in w for w in preview["warnings"])
    # fuzzy match resolved to the same id as the correctly spelled export
    correct = client.post("/api/instructors/import/preview", json={"csv": HUMAN_CSV}).json()
    assert preview["new"][0]["primary_color_id"] == correct["new"][0]["primary_color_id"]


def test_import_unknown_name_left_empty_with_warning(client):
    csv_text = HUMAN_CSV.replace("Blue", "NotAColor")
    preview = client.post("/api/instructors/import/preview", json={"csv": csv_text}).json()
    assert preview["new"][0]["primary_color_id"] is None
    assert any("not a known name" in w for w in preview["warnings"])


def test_import_unrecognized_capability_warns(client):
    csv_text = HUMAN_CSV.replace(",,X,Yes,true", ",,maybe,Yes,true")
    preview = client.post("/api/instructors/import/preview", json={"csv": csv_text}).json()
    assert preview["new"][0]["can_teach_babies"] == 0
    assert any("unrecognized can_teach_babies" in w for w in preview["warnings"])


def test_human_export_roundtrip_is_noop(client):
    client.post("/api/instructors/import/apply", json={"csv": INTERNAL_CSV, "accepted_ids": ["101", "102"]})
    exported = client.get("/api/instructors/export").text
    # human format: names, X marks, no used_default_profile column
    header = exported.lstrip("﻿").splitlines()[0]
    assert "primary_color" in header and "primary_color_id" not in header
    assert "used_default_profile" not in header
    assert ",X," in exported or exported.rstrip().endswith("X")
    preview = client.post("/api/instructors/import/preview", json={"csv": exported}).json()
    assert preview["new"] == [] and preview["changed"] == []
    assert preview["unchanged"] == 2
