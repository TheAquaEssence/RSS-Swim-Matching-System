"""Tests for the XAI dashboard routes mounted in FastAPI."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with DataManager and WhatIfEngine mocked for the duration of each test."""
    with patch("backend.xai_router.DataManager") as mock_dm_cls, \
         patch("backend.xai_router.WhatIfEngine") as mock_engine_cls:

        mock_dm = MagicMock()
        mock_dm.summary = {"assigned": 10, "unassigned": 2, "avg_confidence": 75.0, "total_classes": 5}
        mock_dm.matches = [{"idx": 0, "swimmer_id": 1, "instructor_id": 1, "confidence": 80}]
        mock_dm.unassigned = []
        _match = {"idx": 0, "swimmer_id": 1, "instructor_id": 1, "confidence": 80}
        mock_dm.get_match.side_effect = lambda idx: _match if idx == 0 else None
        mock_dm.get_swimmer.return_value = {"swimmer_id": 1, "first_name": "Alice", "last_name": "Smith"}
        mock_dm.get_instructor.return_value = {"instructor_id": 1, "name": "Bob Jones"}
        mock_dm.all_instructors.return_value = []
        mock_dm.get_confidence_distribution.return_value = {"buckets": [], "counts": []}
        mock_dm.get_type_breakdown.return_value = {"continuity": 0, "compatibility": 1}
        mock_dm.get_flagged_matches_with_reasons.return_value = []
        mock_dm_cls.return_value = mock_dm

        mock_engine = MagicMock()
        mock_engine.score_swimmer_instructor.return_value = {"score": 80, "breakdown": {}}
        mock_engine.check_constraints.return_value = []
        mock_engine_cls.return_value = mock_engine

        from backend.xai_router import create_xai_router

        app = FastAPI()
        router = create_xai_router(
            get_job_dir=lambda: "/tmp/fake_job",
            source_dir="/tmp/fake_src",
        )
        app.include_router(router)
        # yield inside the with-block so patches stay active during each test
        yield TestClient(app)


# ---------------------------------------------------------------------------
# GET routes
# ---------------------------------------------------------------------------

def test_matches_returns_200(client):
    resp = client.get("/xai/api/matches")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "matches" in data


def test_overview_returns_200(client):
    resp = client.get("/xai/api/overview")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_match_detail_returns_200(client):
    resp = client.get("/xai/api/match/0")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_match_detail_404_on_missing(client):
    resp = client.get("/xai/api/match/9999")
    assert resp.status_code == 404


def test_alternatives_returns_200(client):
    resp = client.get("/xai/api/match/0/alternatives")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# POST routes — CSRF protection (Content-Type enforcement)
# ---------------------------------------------------------------------------

def test_swap_rejects_form_encoded(client):
    resp = client.post(
        "/xai/api/what-if/swap",
        content="swimmer_id=1&current_instructor_id=2",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 415


def test_relax_rejects_form_encoded(client):
    resp = client.post(
        "/xai/api/what-if/relax",
        content="swimmer_id=1&constraint=adapted",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 415


def test_tune_rejects_form_encoded(client):
    resp = client.post(
        "/xai/api/what-if/tune",
        content="weights={}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 415


def test_reload_rejects_form_encoded(client):
    resp = client.post(
        "/xai/api/reload",
        content="",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 415


def test_swap_accepts_json(client):
    resp = client.post(
        "/xai/api/what-if/swap",
        json={"swimmer_id": "1", "current_instructor_id": "2"},
    )
    assert resp.status_code != 415


def test_reload_accepts_json(client):
    resp = client.post("/xai/api/reload", json={})
    assert resp.status_code != 415
