import os
import time
from pathlib import Path

import pytest

from core.aqua_logging import configure_component_logger, reset_logging_state
from core.retention import (
    DEFAULT_JOB_RETENTION_DAYS,
    DEFAULT_LOG_RETENTION_DAYS,
    JobCleanupResult,
    RetentionPolicy,
    cleanup_expired_jobs,
)


def _job(jobs_dir: Path, suffix: str, age_days: int) -> Path:
    path = jobs_dir / f"job_{suffix}"
    path.mkdir()
    (path / "result.json").write_text("{}", encoding="utf-8")
    timestamp = time.time() - age_days * 24 * 60 * 60
    os.utime(path, (timestamp, timestamp))
    return path


def test_job_cleanup_removes_only_expired_owned_jobs(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    old_job = _job(jobs_dir, "a" * 32, 31)
    new_job = _job(jobs_dir, "b" * 32, 29)
    malformed = _job(jobs_dir, "not-a-valid-id", 90)
    unrelated_file = jobs_dir / "notes.txt"
    unrelated_file.write_text("preserve", encoding="utf-8")

    result = cleanup_expired_jobs(jobs_dir, tmp_path, retention_days=30)

    assert result == JobCleanupResult(removed=1, skipped=2, errors=0)
    assert not old_job.exists()
    assert new_job.exists()
    assert malformed.exists()
    assert unrelated_file.exists()


def test_job_cleanup_rejects_directory_outside_app_data(tmp_path):
    app_data = tmp_path / "app-data"
    outside_jobs = tmp_path / "external" / "jobs"
    app_data.mkdir()
    outside_jobs.mkdir(parents=True)
    old_job = _job(outside_jobs, "c" * 32, 90)

    result = cleanup_expired_jobs(outside_jobs, app_data, retention_days=30)

    assert result.errors == 1
    assert old_job.exists()


def test_job_cleanup_does_not_follow_symlink(tmp_path):
    jobs_dir = tmp_path / "jobs"
    external = tmp_path / "external"
    jobs_dir.mkdir()
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    link = jobs_dir / f"job_{'d' * 32}"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    result = cleanup_expired_jobs(jobs_dir, tmp_path, retention_days=0)

    assert result.skipped == 1
    assert link.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_retention_policy_defaults_and_invalid_values():
    assert RetentionPolicy.from_environment({}) == RetentionPolicy(
        jobs_days=DEFAULT_JOB_RETENTION_DAYS,
        logs_days=DEFAULT_LOG_RETENTION_DAYS,
    )
    assert RetentionPolicy.from_environment(
        {
            "AQUA_JOB_RETENTION_DAYS": "invalid",
            "AQUA_LOG_RETENTION_DAYS": "-1",
        }
    ) == RetentionPolicy(
        jobs_days=DEFAULT_JOB_RETENTION_DAYS,
        logs_days=DEFAULT_LOG_RETENTION_DAYS,
    )


def test_configured_log_retention_uses_central_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUA_LOG_RETENTION_DAYS", "3")
    reset_logging_state()
    logger = configure_component_logger("test.retention-policy", log_root=tmp_path, console=False)

    file_handler = logger.handlers[0]
    assert file_handler.retention_days == 3

    reset_logging_state()
