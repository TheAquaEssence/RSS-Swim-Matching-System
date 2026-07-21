"""Tests for POST /api/generate_historical_pairings endpoint."""
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.server import app


@pytest.fixture
def client():
    return TestClient(app)


CLASSES_FILLED_CSV = (
    "class_id,day_of_week,start_time,end_time,instructor_name,instructor_id,"
    "class_level,swimmer_1_name,swimmer_1_id,swimmer_2_name,swimmer_2_id,"
    "match_type,compatibility_score,match_confidence,match_reason,"
    "continuity_dispute,flag_codes,flag_summary,review_action,review_severity\n"
    "1,Monday,07:30,08:00,Jane,1,RSS 3,Alex,10,,,"
    "continuity,,90.0%,Continuity: 1 session(s) together,False,,,,none\n"
)


def test_generate_historical_pairings_endpoint_no_job(client):
    """Returns 503 when no completed job exists yet."""
    with patch.object(app.state.services.state, "last_job_dir", None):
        response = client.post(
            "/api/generate_historical_pairings",
            json={"session": "2026-Spring"},
        )
    assert response.status_code == 503


def test_generate_historical_pairings_endpoint_returns_csv(client, tmp_path):
    """Returns CSV content when a completed job with classes_filled.csv exists."""
    job_dir = tmp_path / "job_abc"
    job_dir.mkdir()
    (job_dir / "classes_filled.csv").write_text(CLASSES_FILLED_CSV, encoding="utf-8")

    with patch.object(app.state.services.state, "last_job_dir", job_dir):
        response = client.post(
            "/api/generate_historical_pairings",
            json={"session": "2026-Spring"},
        )
    assert response.status_code == 200
    assert "swimmer_id" in response.text
    assert "instructor_id" in response.text


def test_generate_historical_pairings_endpoint_missing_session(client, tmp_path):
    """Returns 400 when session field is missing or empty."""
    job_dir = tmp_path / "job_abc"
    job_dir.mkdir()
    (job_dir / "classes_filled.csv").write_text(CLASSES_FILLED_CSV, encoding="utf-8")

    with patch.object(app.state.services.state, "last_job_dir", job_dir):
        response = client.post(
            "/api/generate_historical_pairings",
            json={},
        )
    assert response.status_code == 400
