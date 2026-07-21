"""Shared structured logging helpers for Aqua Essence components."""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import logging.handlers
import os
import secrets
import sys
import threading
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from core.app_paths import build_app_data_paths
from core.resource_paths import resolve_resource_root
from core.retention import DEFAULT_LOG_RETENTION_DAYS, RetentionPolicy

DEFAULT_COMPONENT_LEVEL = "INFO"
DEFAULT_RETENTION_DAYS = DEFAULT_LOG_RETENTION_DAYS
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

_WORKSPACE_ROOT = resolve_resource_root()
_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "aqua_log_context",
    default={},
)
_LOGGER_LOCK = threading.Lock()
_CONFIGURED_LOGGERS: dict[str, logging.Logger] = {}
_ORIGINAL_SYS_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREADING_EXCEPTHOOK = threading.excepthook
_EXCEPTION_HOOK_OWNER: str | None = None

_COMMON_OPTIONAL_FIELDS = (
    "request_id",
    "job_id",
    "solver_id",
    "route",
    "method",
    "status_code",
    "duration_ms",
    "exception_type",
    "exception",
    "stacktrace",
    "subprocess_output_tail",
    "retention_days",
    "removed_count",
    "skipped_count",
    "error_count",
)


def default_log_root() -> Path:
    override = os.environ.get("AQUA_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return build_app_data_paths(_WORKSPACE_ROOT).logs


def generate_request_id() -> str:
    return secrets.token_hex(16)


def tail_for_log(text: str | None, max_length: int = 1000) -> str | None:
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return "..." + text[-max_length:]


def _coerce_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    raw = str(level or os.environ.get("AQUA_LOG_LEVEL", DEFAULT_COMPONENT_LEVEL)).upper()
    return getattr(logging, raw, logging.INFO)


def _active_log_path(component_dir: Path, current_date: date | None = None) -> Path:
    current_date = current_date or datetime.now(UTC).date()
    return component_dir / f"{current_date.isoformat()}.jsonl"


def cleanup_old_log_files(log_root: Path, retention_days: int = DEFAULT_RETENTION_DAYS) -> None:
    if not log_root.exists():
        return
    cutoff = time.time() - retention_days * 24 * 60 * 60
    for path in log_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


class _ContextFilter(logging.Filter):
    def __init__(self, component: str):
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        context = _LOG_CONTEXT.get()
        record.component = getattr(record, "component", self.component)
        record.pid = getattr(record, "pid", os.getpid())
        for key, value in context.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts_utc": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
            "pid": getattr(record, "pid", os.getpid()),
        }

        for key in _COMMON_OPTIONAL_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload.setdefault("exception_type", exc_type)
            if record.exc_info[1] is not None:
                payload.setdefault("exception", str(record.exc_info[1]))
            payload.setdefault("stacktrace", "".join(traceback.format_exception(*record.exc_info)))

        return json.dumps(payload, ensure_ascii=True)


class ConsoleEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [f"[{record.levelname}]", f"[{getattr(record, 'component', record.name)}]"]
        event = getattr(record, "event", None)
        if event:
            parts.append(event)
        parts.append(record.getMessage())
        for key in ("request_id", "job_id", "solver_id", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                parts.append(f"{key}={value}")
        return " ".join(parts)


class DailyJsonlRotatingFileHandler(logging.Handler):
    def __init__(
        self,
        component: str,
        *,
        log_root: Path,
        max_bytes: int = DEFAULT_MAX_BYTES,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):
        super().__init__()
        self.component = component
        self.log_root = Path(log_root)
        self.component_dir = self.log_root / component
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self._stream = None
        self._active_path: Path | None = None
        self._last_cleanup_at = 0.0
        self.createLock()
        self.component_dir.mkdir(parents=True, exist_ok=True)
        self._run_cleanup(force=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record) + "\n"
            encoded = line.encode("utf-8")
            with self.lock:
                self._run_cleanup(force=False)
                target_path = _active_log_path(self.component_dir)
                if self._active_path != target_path:
                    self._close_stream()
                    self._active_path = target_path
                self._maybe_rotate(len(encoded))
                if self._stream is None:
                    self.component_dir.mkdir(parents=True, exist_ok=True)
                    self._stream = self._active_path.open("a", encoding="utf-8", newline="")
                self._stream.write(line)
                self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self.lock:
            self._close_stream()
        super().close()

    def _maybe_rotate(self, incoming_size: int) -> None:
        if self._active_path is None:
            return
        current_size = self._active_path.stat().st_size if self._active_path.exists() else 0
        if current_size + incoming_size <= self.max_bytes:
            return
        self._close_stream()
        rotated_path = self._next_rotated_path(self._active_path)
        if self._active_path.exists():
            self._active_path.replace(rotated_path)

    def _next_rotated_path(self, active_path: Path) -> Path:
        index = 1
        while True:
            candidate = active_path.with_name(f"{active_path.name}.{index}")
            if not candidate.exists():
                return candidate
            index += 1

    def _run_cleanup(self, *, force: bool) -> None:
        now = time.time()
        if not force and now - self._last_cleanup_at < 3600:
            return
        cleanup_old_log_files(self.log_root, self.retention_days)
        self._last_cleanup_at = now

    def _close_stream(self) -> None:
        if self._stream is None:
            return
        self._stream.close()
        self._stream = None


class ContextualLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = dict(self.extra)
        extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs

    def bind(self, **extra: Any) -> "ContextualLoggerAdapter":
        bound = dict(self.extra)
        bound.update({key: value for key, value in extra.items() if value is not None})
        return ContextualLoggerAdapter(self.logger, bound)


def configure_component_logger(
    component: str,
    *,
    log_root: Path | None = None,
    level: str | int | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    retention_days: int | None = None,
    console: bool = True,
) -> logging.Logger:
    log_root = Path(log_root) if log_root is not None else default_log_root()
    if retention_days is None:
        retention_days = RetentionPolicy.from_environment().logs_days
    logger_name = f"aqua.{component}"
    desired_level = _coerce_level(level)

    with _LOGGER_LOCK:
        existing = _CONFIGURED_LOGGERS.get(component)
        if existing is not None:
            existing.setLevel(desired_level)
            for handler in existing.handlers:
                handler.setLevel(desired_level)
            return existing

        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(desired_level)
        logger.propagate = False

        context_filter = _ContextFilter(component)

        file_handler = DailyJsonlRotatingFileHandler(
            component,
            log_root=log_root,
            max_bytes=max_bytes,
            retention_days=retention_days,
        )
        file_handler.setLevel(desired_level)
        file_handler.setFormatter(JsonEventFormatter())
        file_handler.addFilter(context_filter)
        logger.addHandler(file_handler)

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(desired_level)
            console_handler.setFormatter(ConsoleEventFormatter())
            console_handler.addFilter(context_filter)
            logger.addHandler(console_handler)

        _CONFIGURED_LOGGERS[component] = logger
        return logger


def get_context_logger(component: str, **extra: Any) -> ContextualLoggerAdapter:
    return ContextualLoggerAdapter(configure_component_logger(component), extra)


@contextlib.contextmanager
def with_log_context(**values: Any):
    current = dict(_LOG_CONTEXT.get())
    current.update({key: value for key, value in values.items() if value is not None})
    token = _LOG_CONTEXT.set(current)
    try:
        yield current
    finally:
        _LOG_CONTEXT.reset(token)


def install_uncaught_exception_logging(logger: logging.Logger, component: str) -> None:
    global _EXCEPTION_HOOK_OWNER
    with _LOGGER_LOCK:
        if _EXCEPTION_HOOK_OWNER == component:
            return

        def _log_sys_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                _ORIGINAL_SYS_EXCEPTHOOK(exc_type, exc_value, exc_traceback)
                return
            logger.error(
                "Uncaught Python exception",
                extra={
                    "event": "uncaught_exception",
                    "exception_type": exc_type.__name__,
                    "exception": str(exc_value),
                    "stacktrace": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
                },
            )
            _ORIGINAL_SYS_EXCEPTHOOK(exc_type, exc_value, exc_traceback)

        def _log_thread_exception(args: threading.ExceptHookArgs):
            if args.exc_type is KeyboardInterrupt:
                _ORIGINAL_THREADING_EXCEPTHOOK(args)
                return
            logger.error(
                "Uncaught thread exception",
                extra={
                    "event": "uncaught_thread_exception",
                    "exception_type": args.exc_type.__name__,
                    "exception": str(args.exc_value),
                    "stacktrace": "".join(
                        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                    ),
                },
            )
            _ORIGINAL_THREADING_EXCEPTHOOK(args)

        sys.excepthook = _log_sys_exception
        threading.excepthook = _log_thread_exception
        _EXCEPTION_HOOK_OWNER = component


def reset_logging_state() -> None:
    global _EXCEPTION_HOOK_OWNER
    with _LOGGER_LOCK:
        for logger in _CONFIGURED_LOGGERS.values():
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
        _CONFIGURED_LOGGERS.clear()
        _EXCEPTION_HOOK_OWNER = None
        sys.excepthook = _ORIGINAL_SYS_EXCEPTHOOK
        threading.excepthook = _ORIGINAL_THREADING_EXCEPTHOOK
    _LOG_CONTEXT.set({})
