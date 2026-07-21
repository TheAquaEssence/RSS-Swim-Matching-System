"""Tests for operator-name change attribution (B4): updated_by / imported_by."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.server import app


@pytest.fixture
def client(tmp_path):
    db.init_db(tmp_path / "test.db")
    return TestClient(app)


CSV = (
    "instructor_id,first_name,last_name,"
    "primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
    "is_team_captain,can_teach_babies,can_teach_adults,can_teach_adapted,"
    "used_default_profile\n"
    "101,Ada,Lovelace,1,2,3,4,0,1,1,0,0\n"
)


def test_patch_records_operator(client):
    client.post("/api/instructors/import/apply", json={"csv": CSV, "accepted_ids": ["101"]})
    resp = client.patch(
        "/api/instructors/101",
        json={"last_name": "Byron", "operator": "  Jordan  "},
    )
    assert resp.status_code == 200
    inst = resp.json()["instructor"]
    assert inst["last_name"] == "Byron"
    assert inst["updated_by"] == "Jordan"


def test_patch_without_operator_clears_attribution(client):
    client.post("/api/instructors/import/apply", json={"csv": CSV, "accepted_ids": ["101"]})
    client.patch("/api/instructors/101", json={"last_name": "Byron", "operator": "Jordan"})
    resp = client.patch("/api/instructors/101", json={"last_name": "King"})
    assert resp.json()["instructor"]["updated_by"] is None


def test_operator_is_not_an_editable_field(client):
    client.post("/api/instructors/import/apply", json={"csv": CSV, "accepted_ids": ["101"]})
    # updated_by in the body must not bypass attribution
    resp = client.patch("/api/instructors/101", json={"updated_by": "Mallory"})
    assert resp.status_code == 200
    assert resp.json()["instructor"]["updated_by"] is None


def test_import_apply_records_operator(client):
    resp = client.post(
        "/api/instructors/import/apply",
        json={"csv": CSV, "accepted_ids": ["101"], "operator": "Sam"},
    )
    assert resp.status_code == 200
    assert db.get_instructor("101")["updated_by"] == "Sam"

    last = client.get("/api/instructors/import/last").json()["last_import"]
    assert last["imported_by"] == "Sam"


def test_undo_restores_previous_attribution(client):
    client.post("/api/instructors/import/apply", json={"csv": CSV, "accepted_ids": ["101"], "operator": "Sam"})
    changed = CSV.replace("Lovelace", "Byron")
    client.post("/api/instructors/import/apply", json={"csv": changed, "accepted_ids": ["101"], "operator": "Alex"})
    assert db.get_instructor("101")["updated_by"] == "Alex"

    resp = client.post("/api/instructors/import/undo", json={})
    assert resp.status_code == 200
    inst = db.get_instructor("101")
    assert inst["last_name"] == "Lovelace"
    assert inst["updated_by"] == "Sam"


def test_pairings_import_records_operator(client):
    pairings = "swimmer_id,instructor_id,session\n1,2,Winter 2026\n"
    resp = client.post(
        "/api/import_jackrabbit_pairings",
        json={"csv": pairings, "operator": "Taylor"},
    )
    assert resp.status_code == 200
    with sqlite3.connect(str(db._db_path)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT imported_by FROM sessions WHERE label = 'Winter 2026'").fetchone()
    assert row["imported_by"] == "Taylor"


def test_operator_name_capped_at_80_chars(client):
    client.post("/api/instructors/import/apply", json={"csv": CSV, "accepted_ids": ["101"]})
    long_name = "x" * 200
    resp = client.patch("/api/instructors/101", json={"last_name": "Byron", "operator": long_name})
    assert len(resp.json()["instructor"]["updated_by"]) == 80


def test_migration_adds_columns_to_old_db(tmp_path):
    # Simulate a pre-B4 database (no updated_by / imported_by columns)
    old = tmp_path / "old.db"
    with sqlite3.connect(str(old)) as con:
        con.execute(
            "CREATE TABLE instructors (instructor_id TEXT PRIMARY KEY, first_name TEXT NOT NULL, "
            "last_name TEXT NOT NULL DEFAULT '', primary_color_id INTEGER, secondary_color_id INTEGER, "
            "primary_style_id INTEGER, secondary_style_id INTEGER, is_team_captain INTEGER NOT NULL DEFAULT 0, "
            "can_teach_babies INTEGER NOT NULL DEFAULT 0, can_teach_adults INTEGER NOT NULL DEFAULT 0, "
            "can_teach_adapted INTEGER NOT NULL DEFAULT 0, used_default_profile INTEGER NOT NULL DEFAULT 1, "
            "profile_source INTEGER NOT NULL DEFAULT 1, updated_at TEXT)"
        )
        con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, imported_at TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE instructor_import_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "imported_at TEXT NOT NULL, summary TEXT NOT NULL, snapshot TEXT NOT NULL)"
        )
        con.execute("INSERT INTO instructors (instructor_id, first_name) VALUES ('1', 'Old')")

    db.init_db(old)
    inst = db.get_instructor("1")
    assert inst is not None
    assert inst["updated_by"] is None
