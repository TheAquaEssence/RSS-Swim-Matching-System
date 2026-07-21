"""Tests for A1: historical pairings filtered against selected input files.

Historical pairings are history, not constraints — pairings referencing
swimmers/instructors absent from the selected files must be skipped with a
warning, not fail the run.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.server import _read_csv_id_set, filter_historical_pairings_csv


HEADER = "swimmer_id,instructor_id,session,num_sessions\n"


def _csv(*rows: str) -> str:
    return HEADER + "".join(r + "\n" for r in rows)


# -- filter_historical_pairings_csv -------------------------------------------

def test_keeps_all_rows_when_ids_match():
    text = _csv("1,10,Spring,2", "2,11,Spring,1")
    out, kept, skipped = filter_historical_pairings_csv(text, {"1", "2"}, {"10", "11"})
    assert (kept, skipped) == (2, 0)
    assert out == text


def test_skips_unknown_swimmer():
    text = _csv("1,10,Spring,2", "15319687,10,Spring,1")
    out, kept, skipped = filter_historical_pairings_csv(text, {"1"}, {"10"})
    assert (kept, skipped) == (1, 1)
    assert "15319687" not in out
    assert "1,10,Spring,2" in out


def test_skips_unknown_instructor():
    text = _csv("1,10,Spring,2", "1,999,Spring,1")
    out, kept, skipped = filter_historical_pairings_csv(text, {"1"}, {"10"})
    assert (kept, skipped) == (1, 1)
    assert "999" not in out


def test_none_id_set_disables_that_filter():
    text = _csv("1,10,Spring,2", "999,10,Spring,1")
    out, kept, skipped = filter_historical_pairings_csv(text, None, {"10"})
    assert (kept, skipped) == (2, 0)

    out, kept, skipped = filter_historical_pairings_csv(text, None, None)
    assert (kept, skipped) == (2, 0)
    assert out == text


def test_all_rows_skipped_returns_header_only():
    text = _csv("5,50,Fall,1", "6,51,Fall,3")
    out, kept, skipped = filter_historical_pairings_csv(text, {"1"}, {"10"})
    assert (kept, skipped) == (0, 2)
    assert out == HEADER


def test_empty_input_csv():
    out, kept, skipped = filter_historical_pairings_csv(HEADER, {"1"}, {"10"})
    assert (kept, skipped) == (0, 0)
    assert out == HEADER


# -- _read_csv_id_set ----------------------------------------------------------

def test_read_csv_id_set_basic(tmp_path):
    p = tmp_path / "swimmers.csv"
    p.write_text("swimmer_id,first_name\n1,Ann\n2,Bo\n,\n", encoding="utf-8")
    assert _read_csv_id_set(p, "swimmer_id") == {"1", "2"}


def test_read_csv_id_set_handles_bom(tmp_path):
    p = tmp_path / "swimmers.csv"
    p.write_text("﻿swimmer_id,first_name\n7,Cy\n", encoding="utf-8")
    assert _read_csv_id_set(p, "swimmer_id") == {"7"}


def test_read_csv_id_set_missing_column_returns_none(tmp_path):
    p = tmp_path / "other.csv"
    p.write_text("name,age\nAnn,9\n", encoding="utf-8")
    assert _read_csv_id_set(p, "swimmer_id") is None


def test_read_csv_id_set_missing_file_returns_none(tmp_path):
    assert _read_csv_id_set(tmp_path / "nope.csv", "swimmer_id") is None


# -- /api/latest_generation_result re-shows persisted warnings -----------------

def test_latest_generation_result_includes_saved_warnings(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    import backend.server as server

    job_dir = tmp_path / "job_test"
    job_dir.mkdir()
    (job_dir / "result.json").write_text(
        json.dumps({"ok": True, "result_files": {}, "matches": [], "unassigned": []}),
        encoding="utf-8",
    )
    warning = "412 of 18,543 historical pairings were ignored."
    (job_dir / "generation_warnings.json").write_text(json.dumps([warning]), encoding="utf-8")
    monkeypatch.setattr(server.application_services.state, "last_job_dir", str(job_dir))

    resp = TestClient(server.app).get("/api/latest_generation_result")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["has_result"] is True
    assert payload["warnings"] == [warning]


def test_latest_generation_result_without_warnings_file(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    import backend.server as server

    job_dir = tmp_path / "job_test"
    job_dir.mkdir()
    (job_dir / "result.json").write_text(
        json.dumps({"ok": True, "result_files": {}, "matches": [], "unassigned": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(server.application_services.state, "last_job_dir", str(job_dir))

    resp = TestClient(server.app).get("/api/latest_generation_result")
    assert resp.status_code == 200
    assert "warnings" not in resp.json()
