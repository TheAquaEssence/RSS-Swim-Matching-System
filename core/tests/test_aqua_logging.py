import json
import os
import time
from pathlib import Path

from core.aqua_logging import (
    cleanup_old_log_files,
    configure_component_logger,
    default_log_root,
    reset_logging_state,
    with_log_context,
)


def _read_records(component_dir: Path):
    records = []
    for path in sorted(component_dir.glob("*.jsonl*")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_jsonl_record_includes_required_fields(tmp_path):
    reset_logging_state()
    logger = configure_component_logger("test.helper", log_root=tmp_path, console=False)

    with with_log_context(request_id="req-1", job_id="job-1"):
        logger.info(
            "hello",
            extra={
                "event": "test_event",
                "method": "POST",
                "route": "/api/generate",
                "status_code": 200,
                "duration_ms": 12.5,
            },
        )

    records = _read_records(tmp_path / "test.helper")
    assert len(records) == 1
    record = records[0]
    assert record["level"] == "INFO"
    assert record["component"] == "test.helper"
    assert record["event"] == "test_event"
    assert record["message"] == "hello"
    assert record["request_id"] == "req-1"
    assert record["job_id"] == "job-1"
    assert record["method"] == "POST"
    assert record["route"] == "/api/generate"
    assert record["status_code"] == 200
    assert record["duration_ms"] == 12.5
    assert isinstance(record["pid"], int)
    assert record["ts_utc"].endswith("Z")


def test_rotation_occurs_when_active_file_exceeds_limit(tmp_path):
    reset_logging_state()
    logger = configure_component_logger(
        "test.rotation",
        log_root=tmp_path,
        max_bytes=220,
        console=False,
    )

    for index in range(8):
        logger.info("x" * 120, extra={"event": f"event_{index}"})

    component_dir = tmp_path / "test.rotation"
    files = sorted(path.name for path in component_dir.glob("*.jsonl*"))
    assert len(files) >= 2
    assert any(name.endswith(".1") for name in files)


def test_retention_cleanup_removes_old_files(tmp_path):
    old_dir = tmp_path / "component"
    old_dir.mkdir()
    old_file = old_dir / "2026-01-01.jsonl"
    old_file.write_text("{}", encoding="utf-8")
    fresh_file = old_dir / "2026-03-20.jsonl"
    fresh_file.write_text("{}", encoding="utf-8")

    old_timestamp = time.time() - (15 * 24 * 60 * 60)
    os.utime(old_file, (old_timestamp, old_timestamp))

    cleanup_old_log_files(tmp_path, retention_days=14)

    assert not old_file.exists()
    assert fresh_file.exists()


def test_default_log_root_follows_application_data_root(tmp_path, monkeypatch):
    monkeypatch.delenv("AQUA_LOG_DIR", raising=False)
    monkeypatch.setenv("AQUA_APP_DATA_DIR", str(tmp_path))

    assert default_log_root() == tmp_path.resolve() / "logs"


def test_log_specific_override_takes_precedence(tmp_path, monkeypatch):
    app_data = tmp_path / "app-data"
    log_data = tmp_path / "custom-logs"
    monkeypatch.setenv("AQUA_APP_DATA_DIR", str(app_data))
    monkeypatch.setenv("AQUA_LOG_DIR", str(log_data))

    assert default_log_root() == log_data.resolve()
