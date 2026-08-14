"""Functional XAI router tests with the real DataManager and WhatIfEngine.

Ported from the retired Flask suite (frontend/xai_dashboard/tests/test_app.py)
so route behavior — not just status codes — stays covered under FastAPI.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = WORKSPACE_ROOT / "data" / "source"


@pytest.fixture
def sample_job_dir(tmp_path):
    result = {
        "ok": True,
        "summary": {
            "classes": 2,
            "assigned_swimmers": 3,
            "unassigned_swimmers": 0,
            "avg_confidence": 70.0,
        },
        "matches": [
            {
                "type": "individual",
                "swimmer_id": 1,
                "swimmer_name": "Alice",
                "instructor_id": 10,
                "instructor_name": "Coach A",
                "confidence": 85.0,
                "compatibility_score": 78.5,
                "reason": "Compatibility match",
                "continuity_dispute": False,
                "flag_codes": ["non_response_swimmer_type"],
                "review_severity": "review",
            },
        ],
        "unassigned": [],
        "result_files": {"profiles": "profiles.json"},
    }
    profiles = {
        "swimmers": {
            "1": {
                "swimmer_id": 1,
                "name": "Alice",
                "swimmer_type_id": 2,
                "swimmer_type_name": "Fearless",
                "skill_level": 3,
                "age": 7,
                "has_special_needs": False,
                "notes": "",
                "pair_id": None,
            }
        },
        "instructors": {
            "10": {
                "instructor_id": 10,
                "name": "Coach A",
                "primary_color_id": 1,
                "primary_color_name": "Blue",
                "secondary_color_id": 2,
                "secondary_color_name": "Orange",
                "primary_style_id": 1,
                "primary_style_name": "Motivational",
                "secondary_style_id": 3,
                "secondary_style_name": "Technique",
                "is_team_captain": False,
                "can_teach_adapted": True,
                "can_teach_adults": False,
                "can_teach_babies": False,
                "can_teach_NL": True,
            }
        },
    }
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (tmp_path / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(sample_job_dir):
    from backend.xai_router import create_xai_router

    app = FastAPI()
    app.include_router(
        create_xai_router(
            get_job_dir=lambda: str(sample_job_dir),
            source_dir=str(SOURCE_DIR),
        )
    )
    return TestClient(app)


def test_index_returns_html(client):
    resp = client.get("/xai/")
    assert resp.status_code == 200
    assert "html" in resp.text.lower()
    assert 'class="product-nav-link" href="/"' in resp.text
    assert '<span>Matching</span>' in resp.text
    assert 'class="product-nav-link active" href="/xai/" aria-current="page"' in resp.text
    assert '<span>Explainability</span>' in resp.text
    assert 'src="/shared/ui_utils.js"' in resp.text
    assert 'src="/xai/static/dashboard.js' in resp.text
    assert 'href="/xai/static/dashboard.css' in resp.text
    assert 'href="/styles/workspace.css' in resp.text


def test_api_matches_returns_real_data(client):
    data = client.get("/xai/api/matches").json()
    assert data["ok"]
    assert len(data["matches"]) == 1
    assert data["summary"]["classes"] == 2


def test_api_match_detail_includes_profiles(client):
    data = client.get("/xai/api/match/0").json()
    assert data["ok"]
    assert data["match"]["swimmer_name"] == "Alice"


def test_api_match_not_found(client):
    assert client.get("/xai/api/match/99").status_code == 404


def test_api_swap_returns_current_assignment(client):
    data = client.post(
        "/xai/api/what-if/swap",
        json={"swimmer_id": 1, "current_instructor_id": 10},
    ).json()
    assert data["ok"]
    assert "current" in data


def test_api_tune_returns_rescored_results(client):
    data = client.post(
        "/xai/api/what-if/tune",
        json={"weights": {"color_vs_style": 0.7}},
    ).json()
    assert data["ok"]
    assert isinstance(data["results"], list)


def test_api_overview_shape(client):
    data = client.get("/xai/api/overview").json()
    assert data["ok"]
    assert "summary" in data
    assert "confidence_distribution" in data
    assert "type_breakdown" in data
    assert isinstance(data["confidence_distribution"]["counts"], list)
    assert len(data["confidence_distribution"]["buckets"]) == 10
    assert len(data["flagged"]) == 1
    assert data["flagged"][0]["review_severity"] == "review"


def test_api_match_alternatives(client):
    data = client.get("/xai/api/match/0/alternatives").json()
    assert data["ok"]
    assert "current" in data
    assert isinstance(data["alternatives"], list)


def test_api_match_alternatives_not_found(client):
    assert client.get("/xai/api/match/99/alternatives").status_code == 404


def test_shared_ui_utils_is_served():
    import backend.server as server

    with TestClient(server.app) as full_client:
        resp = full_client.get("/shared/ui_utils.js")
    assert resp.status_code == 200
    assert "window.AquaUi" in resp.text
