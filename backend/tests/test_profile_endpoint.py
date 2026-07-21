"""Tests for GET /api/profile/{type}/{id} endpoint."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def profiles_dir(tmp_path):
    """Create a fake job dir with a profiles.json."""
    profiles = {
        "swimmers": {
            "1": {
                "swimmer_id": 1,
                "first_name": "John",
                "last_name": "Kelly",
                "name": "John Kelly",
                "swimmer_type_id": 2,
                "swimmer_type_name": "The Fearless/Energetic",
                "skill_level": 6,
                "age": 5.5,
                "has_special_needs": False,
                "notes": "",
                "pair_id": None,
            }
        },
        "instructors": {
            "10": {
                "instructor_id": 10,
                "first_name": "Sarah",
                "last_name": "Martinez",
                "name": "Sarah Martinez",
                "primary_color_id": 1,
                "primary_color_name": "Blue",
                "secondary_color_id": 2,
                "secondary_color_name": "Orange",
                "primary_style_id": 1,
                "primary_style_name": "New RSS/Babies",
                "secondary_style_id": 3,
                "secondary_style_name": "Technique Driven",
                "is_team_captain": False,
                "can_teach_NL": True,
                "can_teach_babies": True,
                "can_teach_adults": False,
                "can_teach_adapted": False,
            }
        },
    }
    (tmp_path / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    return tmp_path


def test_no_job_run_returns_503(client):
    with patch.object(app.state.services.state, "last_job_dir", ""):
        resp = client.get("/api/profile/swimmer/1")
    assert resp.status_code == 503
    assert resp.json()["error"] == "No profiles available. Run a generation first."


def test_swimmer_profile_found(client, profiles_dir):
    with patch.object(app.state.services.state, "last_job_dir", str(profiles_dir)):
        resp = client.get("/api/profile/swimmer/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["profile"]["name"] == "John Kelly"
    assert data["profile"]["skill_level"] == 6


def test_instructor_profile_found(client, profiles_dir):
    with patch.object(app.state.services.state, "last_job_dir", str(profiles_dir)):
        resp = client.get("/api/profile/instructor/10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["profile"]["name"] == "Sarah Martinez"
    assert data["profile"]["can_teach_babies"] is True


def test_invalid_type_returns_400(client, profiles_dir):
    with patch.object(app.state.services.state, "last_job_dir", str(profiles_dir)):
        resp = client.get("/api/profile/alien/1")
    assert resp.status_code == 400


def test_missing_id_returns_404(client, profiles_dir):
    with patch.object(app.state.services.state, "last_job_dir", str(profiles_dir)):
        resp = client.get("/api/profile/swimmer/999")
    assert resp.status_code == 404
    assert "999" in resp.json()["error"]


def test_missing_profiles_json_returns_503(client, tmp_path):
    empty_dir = tmp_path / "empty_job"
    empty_dir.mkdir()
    with patch.object(app.state.services.state, "last_job_dir", str(empty_dir)):
        resp = client.get("/api/profile/swimmer/1")
    assert resp.status_code == 503
