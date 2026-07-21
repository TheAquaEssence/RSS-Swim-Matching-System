"""Tests for GET /api/instructors/stats and db.instructor_stats()."""
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.server import app


@pytest.fixture
def client(tmp_path):
    db.init_db(tmp_path / "test.db")
    return TestClient(app)


SEED_CSV = (
    "instructor_id,first_name,last_name,"
    "primary_color_id,secondary_color_id,primary_style_id,secondary_style_id,"
    "is_team_captain,can_teach_babies,can_teach_adults,can_teach_adapted,"
    "used_default_profile\n"
    "101,Ada,Lovelace,1,2,3,4,0,1,1,0,0\n"
    "102,Grace,Hopper,1,3,3,4,1,1,0,1,0\n"
    "103,Mary,Jackson,2,,4,,0,0,0,0,0\n"
)


def _seed(client):
    resp = client.post(
        "/api/instructors/import/apply",
        json={"csv": SEED_CSV, "accepted_ids": ["101", "102", "103"]},
    )
    assert resp.status_code == 200


def test_stats_empty_db(client):
    data = client.get("/api/instructors/stats").json()
    assert data["ok"] is True
    assert data["total"] == 0
    assert data["complete"] == 0
    assert data["colors"] == []
    assert data["styles"] == []
    assert data["capabilities"]["can_teach_babies"] == 0


def test_stats_counts(client):
    _seed(client)
    data = client.get("/api/instructors/stats").json()
    assert data["ok"] is True
    assert data["total"] == 3
    # 101 and 102 have all four profile fields; 103 is partial
    assert data["complete"] == 2

    caps = data["capabilities"]
    assert caps["can_teach_babies"] == 2
    assert caps["can_teach_adults"] == 1
    assert caps["can_teach_adapted"] == 1
    assert caps["is_team_captain"] == 1

    colors = {c["id"]: c for c in data["colors"]}
    assert colors[1]["primary"] == 2
    assert colors[2]["primary"] == 1
    assert colors[2]["secondary"] == 1
    assert colors[3]["secondary"] == 1
    # 103 has no secondary color → counted under id None
    assert colors[None]["secondary"] == 1
    assert colors[None]["primary"] == 0

    styles = {s["id"]: s for s in data["styles"]}
    assert styles[3]["primary"] == 2
    assert styles[4]["primary"] == 1
    assert styles[4]["secondary"] == 2


def test_stats_entries_have_names(client):
    _seed(client)
    data = client.get("/api/instructors/stats").json()
    for entry in data["colors"] + data["styles"]:
        assert "name" in entry
        if entry["id"] is None:
            assert entry["name"] is None
        else:
            assert isinstance(entry["name"], str) and entry["name"]


def test_stats_unset_ids_sorted_last(client):
    _seed(client)
    data = client.get("/api/instructors/stats").json()
    color_ids = [c["id"] for c in data["colors"]]
    assert color_ids[-1] is None
    assert color_ids[:-1] == sorted(color_ids[:-1])


def test_stats_not_shadowed_by_instructor_id_route(client):
    # /api/instructors/stats must not be treated as instructor_id="stats"
    resp = client.get("/api/instructors/stats")
    assert resp.status_code == 200
    assert "total" in resp.json()
