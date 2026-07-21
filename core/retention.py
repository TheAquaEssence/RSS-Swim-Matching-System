"""Retention policy for application-owned jobs and diagnostic logs."""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_JOB_RETENTION_DAYS = 30
DEFAULT_LOG_RETENTION_DAYS = 14
JOB_RETENTION_ENV = "AQUA_JOB_RETENTION_DAYS"
LOG_RETENTION_ENV = "AQUA_LOG_RETENTION_DAYS"

_SECONDS_PER_DAY = 24 * 60 * 60
_OWNED_JOB_NAME = re.compile(r"job_[0-9a-f]{32}")


@dataclass(frozen=True)
class RetentionPolicy:
    """Maximum ages, in days, for application-owned runtime artifacts."""

    jobs_days: int = DEFAULT_JOB_RETENTION_DAYS
    logs_days: int = DEFAULT_LOG_RETENTION_DAYS

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "RetentionPolicy":
        environment = os.environ if environ is None else environ
        return cls(
            jobs_days=_read_days(environment, JOB_RETENTION_ENV, DEFAULT_JOB_RETENTION_DAYS),
            logs_days=_read_days(environment, LOG_RETENTION_ENV, DEFAULT_LOG_RETENTION_DAYS),
        )


@dataclass(frozen=True)
class JobCleanupResult:
    removed: int = 0
    skipped: int = 0
    errors: int = 0


def _read_days(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def cleanup_expired_jobs(
    jobs_dir: Path,
    app_data_root: Path,
    *,
    retention_days: int,
    now: float | None = None,
) -> JobCleanupResult:
    """Delete expired, application-named job directories without leaving app data.

    Only direct children named ``job_<32 lowercase hex characters>`` are owned
    by this cleanup. Symlinks and every other entry are preserved. A retention
    value of zero removes every eligible job at the next cleanup.
    """

    jobs_dir = Path(jobs_dir)
    app_data_root = Path(app_data_root)
    if not jobs_dir.exists() or jobs_dir.is_symlink() or not jobs_dir.is_dir():
        return JobCleanupResult()

    try:
        resolved_root = app_data_root.resolve(strict=True)
        resolved_jobs = jobs_dir.resolve(strict=True)
    except OSError:
        return JobCleanupResult(errors=1)
    if resolved_jobs == resolved_root or not resolved_jobs.is_relative_to(resolved_root):
        return JobCleanupResult(errors=1)

    cutoff = (time.time() if now is None else now) - retention_days * _SECONDS_PER_DAY
    removed = skipped = errors = 0
    try:
        entries = list(jobs_dir.iterdir())
    except OSError:
        return JobCleanupResult(errors=1)

    for entry in entries:
        if not _OWNED_JOB_NAME.fullmatch(entry.name):
            skipped += 1
            continue
        try:
            if entry.is_symlink() or not entry.is_dir():
                skipped += 1
                continue
            resolved_entry = entry.resolve(strict=True)
            if not resolved_entry.is_relative_to(resolved_jobs):
                skipped += 1
                continue
            if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            errors += 1

    return JobCleanupResult(removed=removed, skipped=skipped, errors=errors)
