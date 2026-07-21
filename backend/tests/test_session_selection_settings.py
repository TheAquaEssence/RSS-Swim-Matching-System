"""Tests for POST /api/settings/deselected_session_ids (persisted session selection)."""
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.server import app


@pytest.fixture
def client(tmp_path):
    # Settings isolation (real settings file + in-memory dict) is handled by
    # the autouse fixture in conftest.py.
    db.init_db(tmp_path / "test.db")
    return TestClient(app)


def test_save_and_read_back(client):
    response = client.post("/api/settings/deselected_session_ids", json={"ids": [3, 1, 2]})
    assert response.status_code == 200
    assert response.json()["deselected_session_ids"] == [1, 2, 3]

    settings = client.get("/api/settings").json()
    assert settings["deselected_session_ids"] == [1, 2, 3]


def test_ids_deduped_and_non_numeric_dropped(client):
    response = client.post(
        "/api/settings/deselected_session_ids",
        json={"ids": [5, "5", "7", "x", None]},
    )
    assert response.status_code == 200
    assert response.json()["deselected_session_ids"] == [5, 7]


def test_ids_must_be_list(client):
    response = client.post("/api/settings/deselected_session_ids", json={"ids": "1,2"})
    assert response.status_code == 400
    response = client.post("/api/settings/deselected_session_ids", json={})
    assert response.status_code == 400


def test_requires_json_content_type(client):
    response = client.post(
        "/api/settings/deselected_session_ids",
        content="ids=1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_empty_list_clears_selection(client):
    client.post("/api/settings/deselected_session_ids", json={"ids": [9]})
    response = client.post("/api/settings/deselected_session_ids", json={"ids": []})
    assert response.status_code == 200
    assert client.get("/api/settings").json()["deselected_session_ids"] == []
