"""
Aqua Essence – Host Server (Python / FastAPI)
Replaces the C++ host. Serves the UI, manages settings,
discovers solvers, and runs the solver subprocess.
"""

import csv
import io
import json
import math
import os
import secrets
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

try:
    import uvicorn
except ImportError:  # pragma: no cover - optional for import-time tooling/tests
    uvicorn = None
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from core.flags import FLAG_CODES, expand_flag_codes, get_highest_severity, get_primary_review_action
from core.swimmer_types import coerce_swimmer_type_id, is_non_response_swimmer_type

from backend.xai_router import create_xai_router
from backend.csv_import import (
    import_classes, import_students,
    import_instructors,
    is_partner_classes_csv, is_partner_students_csv, is_partner_instructors_csv,
    generate_historical_pairings,
)
from backend.spreadsheet_import import read_tabular_file_text, xlsx_bytes_to_csv_text
from backend.services.result_files import expose_result_files
from backend.instructor_source_editor import (
    _load_payload as _isce_load_payload,
    _save_payload as _isce_save_payload,
)
from backend.launch_auth import (
    LAUNCH_TOKEN_HEADER,
    LaunchTokenAuth,
    launch_token_from_environment,
    requires_launch_token,
)
from backend.host_security import LoopbackHostMiddleware
from backend.services import solver_runner
from backend.services.generation_service import GenerationDependencies, GenerationService
from backend.services.repository import SqliteRepository
from backend.services.resource_provisioner import provision_default_resource_files
from backend.services.storage import StorageService, read_csv_file, write_csv_file
from backend.application import ApplicationServices, ApplicationState, BackendPaths
from core.aqua_logging import (
    configure_component_logger,
    generate_request_id,
    install_uncaught_exception_logging,
    tail_for_log,
    with_log_context,
)
from core.retention import RetentionPolicy, cleanup_expired_jobs
from core.app_paths import build_app_data_paths
from core.resource_paths import resolve_resource_root

COMPONENT = "backend.server"
_logger_lock = threading.Lock()
_logger = None


def get_logger():
    global _logger
    if _logger is None:
        with _logger_lock:
            if _logger is None:
                _logger = configure_component_logger(COMPONENT)
                install_uncaught_exception_logging(_logger, COMPONENT)
    return _logger


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOST_DIR = Path(__file__).parent.resolve()
APP_ROOT = resolve_resource_root()
UI_DIR = APP_ROOT / "frontend"
SOLVERS_DIR = APP_ROOT / "solvers"
APP_DATA_PATHS = build_app_data_paths(APP_ROOT)
APP_DATA_ROOT = APP_DATA_PATHS.root
JOBS_DIR = APP_DATA_PATHS.jobs
SETTINGS_PATH = APP_DATA_PATHS.settings
DB_PATH = APP_DATA_PATHS.database
WRITABLE_RESOURCES_DIR = APP_DATA_PATHS.resources

DEFAULT_FILE_PATHS = provision_default_resource_files(
    app_root=APP_ROOT,
    app_data_root=APP_DATA_ROOT,
    writable_resources_root=WRITABLE_RESOURCES_DIR,
)

JOBS_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

KNOWN_KEYS = [
    "classes",
    "swimmers",
    "instructors",
    "historical_pairings",
    "swimmer_type_color_rankings",
    "swimmer_type_style_rankings",
    "personality_colors",
    "instructor_styles",
    "swimmer_types",
]


def make_default_settings() -> dict:
    defaults = dict(DEFAULT_FILE_PATHS)
    return {
        "default_files": dict(defaults),
        "last_selected_files": dict(defaults),
        "use_db_instructors": False,
        "deselected_session_ids": [],
        "default_instructor_profile": {
            "primary_color_id": 1,
            "secondary_color_id": 2,
            "primary_style_id": 6,
            "secondary_style_id": 5,
            "is_team_captain": False,
            "can_teach_NL": True,
            "can_teach_babies": False,
            "can_teach_adults": False,
            "can_teach_adapted": False,
        },
    }


_INSTRUCTOR_DEFAULT_BOOL_KEYS = (
    "is_team_captain",
    "can_teach_NL",
    "can_teach_babies",
    "can_teach_adults",
    "can_teach_adapted",
)

_INSTRUCTOR_DEFAULT_ID_KEYS = (
    "primary_color_id",
    "secondary_color_id",
    "primary_style_id",
    "secondary_style_id",
)


def _sanitize_instructor_default_profile(profile: dict | None) -> dict:
    default_profile = make_default_settings()["default_instructor_profile"]
    if not isinstance(profile, dict):
        return dict(default_profile)

    sanitized = dict(default_profile)
    for key in _INSTRUCTOR_DEFAULT_ID_KEYS:
        try:
            value = int(profile.get(key, sanitized[key]))
            sanitized[key] = value if value > 0 else sanitized[key]
        except (TypeError, ValueError):
            pass

    for key in _INSTRUCTOR_DEFAULT_BOOL_KEYS:
        sanitized[key] = _parse_boolish(profile.get(key), sanitized[key])

    return sanitized


def _sanitize_session_id_list(value) -> list[int]:
    """Coerce a saved/posted session id list into a sorted, deduped list[int]."""
    if not isinstance(value, list):
        return []
    out = set()
    for v in value:
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _operator_name(value) -> str | None:
    """Normalize an optional operator name (attribution, not auth): trimmed, capped, or None."""
    name = str(value or "").strip()
    return name[:80] if name else None


def _require_json(request: Request) -> None:
    ct = request.headers.get("content-type", "")
    if "application/json" not in ct:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")


def _storage(settings_path: Path | None = None) -> StorageService:
    """Bind the storage service to the current module path constants.

    Built per call (the dataclass is cheap) so tests that monkeypatch
    APP_ROOT / APP_DATA_ROOT / SETTINGS_PATH / DEFAULT_FILE_PATHS keep
    working; the service itself never reads this module.
    """
    return StorageService(
        app_root=APP_ROOT,
        app_data_root=APP_DATA_ROOT,
        writable_resources_dir=WRITABLE_RESOURCES_DIR,
        settings_path=settings_path or SETTINGS_PATH,
        default_file_paths=DEFAULT_FILE_PATHS,
    )


# Thin wrappers over StorageService keep the historical names on this module
# (call sites and tests patch backend.server.save_settings etc.).

def resolve_from_root(p: str) -> Path:
    return _storage().resolve_from_root(p)


def file_exists_from_root(p: str) -> bool:
    return _storage().file_exists_from_root(p)


def validate_and_fixup(settings: dict) -> None:
    for k in KNOWN_KEYS:
        settings["default_files"].setdefault(k, "")
        settings["last_selected_files"].setdefault(k, settings["default_files"][k])

    for k in KNOWN_KEYS:
        current = settings["last_selected_files"][k]
        if current and file_exists_from_root(current):
            continue
        if k == "classes":
            settings["last_selected_files"][k] = ""
        else:
            default = settings["default_files"][k]
            settings["last_selected_files"][k] = (
                default if default and file_exists_from_root(default) else ""
            )
    settings["default_instructor_profile"] = _sanitize_instructor_default_profile(
        settings.get("default_instructor_profile")
    )
    settings["use_db_instructors"] = bool(settings.get("use_db_instructors", False))
    settings["deselected_session_ids"] = _sanitize_session_id_list(
        settings.get("deselected_session_ids")
    )


def load_settings(settings_path: Path | None = None) -> dict:
    settings = make_default_settings()
    try:
        parsed = _storage(settings_path).read_settings_payload()
        for k in KNOWN_KEYS:
            if k in (parsed.get("default_files") or {}):
                settings["default_files"][k] = _migrate_bundled_default_path(
                    k, parsed["default_files"][k]
                )
            if k in (parsed.get("last_selected_files") or {}):
                settings["last_selected_files"][k] = _migrate_bundled_default_path(
                    k, parsed["last_selected_files"][k]
                )
        settings["use_db_instructors"] = bool(parsed.get("use_db_instructors", False))
        settings["deselected_session_ids"] = _sanitize_session_id_list(
            parsed.get("deselected_session_ids")
        )
        settings["default_instructor_profile"] = _sanitize_instructor_default_profile(
            parsed.get("default_instructor_profile")
        )
    except Exception:
        pass
    return settings


def save_settings(settings: dict, settings_path: Path | None = None) -> None:
    _storage(settings_path).save_settings(settings)


# CSV helpers (read_csv_file / write_csv_file) live in backend.services.storage
# and are imported above for the rankings / reference table endpoints.


def get_setting_path(key: str, state: ApplicationState | None = None) -> Path | None:
    """Resolve a settings key to an absolute path, or None if not configured."""
    state = state or application_services.state
    with state.settings_lock:
        current_settings = state.settings
        p = current_settings["last_selected_files"].get(key) or current_settings["default_files"].get(key, "")
    if not p:
        return None
    resolved = resolve_from_root(p)
    return resolved if resolved.exists() else None


def _migrate_bundled_default_path(key: str, raw_path: str) -> str:
    """Map an old bundled default to its provisioned writable equivalent."""
    return _storage().migrate_bundled_default_path(key, raw_path)


def get_writable_setting_path(key: str, state: ApplicationState | None = None) -> Path | None:
    """Resolve a selected file and copy bundled resources before editing."""

    state = state or application_services.state
    with state.settings_lock:
        current_settings = state.settings
        raw_path = (
            current_settings["last_selected_files"].get(key)
            or current_settings["default_files"].get(key, "")
        )
        if not raw_path:
            return None
        source = resolve_from_root(raw_path)
        if not source.exists():
            return None
        destination = _storage().provision_for_edit(source)
        if destination != source:
            current_settings["last_selected_files"][key] = destination.as_posix()
            save_settings(current_settings)
        return destination


def _load_swimmer_type_names(path: Path) -> dict[int, str]:
    _, rows = read_csv_file(path)
    swimmer_types = {}
    for row in rows:
        swimmer_type_id = row.get("swimmer_type_id", "").strip()
        if not swimmer_type_id:
            continue
        swimmer_types[int(swimmer_type_id)] = row.get("swimmer_type_name", "").strip()
    return swimmer_types


def _load_reference_name_lookup(path: Path, id_col: str, name_col: str) -> dict[int, str]:
    _, rows = read_csv_file(path)
    lookup: dict[int, str] = {}
    for row in rows:
        raw_id = str(row.get(id_col, "")).strip()
        if not raw_id:
            continue
        try:
            lookup[int(raw_id)] = str(row.get(name_col, "")).strip()
        except (TypeError, ValueError):
            continue
    return lookup


def _load_reference_options(
    setting_key: str,
    id_col: str,
    name_col: str,
    state: ApplicationState | None = None,
) -> tuple[list[dict[str, int | str]], str | None]:
    candidates: list[Path] = []
    selected_path = get_setting_path(setting_key, state)
    if selected_path:
        candidates.append(selected_path)

    default_path = resolve_from_root(make_default_settings()["default_files"].get(setting_key, ""))
    if default_path and default_path.exists():
        candidates.append(default_path)

    deduped_candidates: list[Path] = []
    seen_paths: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        deduped_candidates.append(candidate)

    for candidate in deduped_candidates:
        try:
            lookup = _load_reference_name_lookup(candidate, id_col, name_col)
        except Exception:
            continue
        if lookup:
            return (
                [{"id": key, "name": value} for key, value in sorted(lookup.items())],
                str(candidate),
            )
    return [], None


def _build_instructor_defaults_payload(profile: dict | None = None) -> dict:
    sanitized_profile = _sanitize_instructor_default_profile(profile)
    colors, colors_source = _load_reference_options("personality_colors", "color_id", "color_name")
    styles, styles_source = _load_reference_options("instructor_styles", "style_id", "style_name")
    return {
        "ok": True,
        "profile": sanitized_profile,
        "app_defaults": make_default_settings()["default_instructor_profile"],
        "colors": colors,
        "styles": styles,
        "colors_source": colors_source or "",
        "styles_source": styles_source or "",
    }


def _parse_boolish(value, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"", "nan", "none"}:
        return default
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return default


def normalize_instructors_csv(
    source_path: Path,
    colors_path: Path,
    styles_path: Path,
    output_path: Path,
    default_profile: dict,
) -> tuple[int, set[str]]:
    """Rewrite instructors.csv with missing/invalid profile fields defaulted."""
    headers, rows = read_csv_file(source_path)
    required = [
        "instructor_id",
        "first_name",
        "last_name",
        "primary_color_id",
        "secondary_color_id",
        "primary_style_id",
        "secondary_style_id",
        "is_team_captain",
        "can_teach_NL",
        "can_teach_babies",
        "can_teach_adults",
        "can_teach_adapted",
    ]
    if any(column not in headers for column in required):
        return 0, set()

    color_lookup = _load_reference_name_lookup(colors_path, "color_id", "color_name")
    style_lookup = _load_reference_name_lookup(styles_path, "style_id", "style_name")

    normalized_rows = []
    changed = 0
    defaulted_ids: set[str] = set()
    output_headers = list(headers)
    if "used_default_profile" not in output_headers:
        output_headers.append("used_default_profile")

    incomplete_profile_ids = sorted(
        str(row.get("instructor_id", "")).strip()
        for row in rows
        if str(row.get("profile_source", "")).strip() in {"1", "2"}
    )
    if incomplete_profile_ids:
        rendered = ", ".join(incomplete_profile_ids[:10])
        if len(incomplete_profile_ids) > 10:
            rendered += f", and {len(incomplete_profile_ids) - 10} more"
        raise ValueError(
            "Instructor profiles are incomplete for ID(s): "
            f"{rendered}. Complete their colors, styles, and teaching "
            "qualifications in Data & settings before matching."
        )

    for row in rows:
        normalized = dict(row)
        row_changed = False
        used_default = _parse_boolish(row.get("used_default_profile"), False)

        instructor_id = str(row.get("instructor_id", "")).strip()
        if not instructor_id:
            normalized_rows.append(normalized)
            continue

        for field, lookup in (
            ("primary_color_id", color_lookup),
            ("secondary_color_id", color_lookup),
            ("primary_style_id", style_lookup),
            ("secondary_style_id", style_lookup),
        ):
            current_raw = str(row.get(field, "")).strip()
            try:
                current_value = int(current_raw)
            except (TypeError, ValueError):
                current_value = None

            default_value = int(default_profile[field])
            if current_value is None or current_value not in lookup:
                normalized[field] = str(default_value)
                row_changed = row_changed or current_raw != str(default_value)
                used_default = True
            else:
                normalized[field] = str(current_value)

        for field in _INSTRUCTOR_DEFAULT_BOOL_KEYS:
            default_value = bool(default_profile[field])
            parsed_value = _parse_boolish(row.get(field), default_value)
            raw_value = str(row.get(field, "")).strip()
            if raw_value.lower() in {"", "nan", "none"}:
                used_default = True
                row_changed = True
            normalized[field] = "1" if parsed_value else "0"

        normalized["used_default_profile"] = "1" if used_default else "0"
        if used_default:
            defaulted_ids.add(instructor_id)
        if row_changed or str(row.get("used_default_profile", "")).strip() != normalized["used_default_profile"]:
            changed += 1
        normalized_rows.append(normalized)

    if changed:
        write_csv_file(output_path, output_headers, normalized_rows)
    return changed, defaulted_ids


def normalize_swimmers_csv(source_path: Path, types_path: Path, output_path: Path) -> int:
    """Rewrite swimmers.csv with missing/invalid swimmer types defaulted to Non-Response."""
    headers, rows = read_csv_file(source_path)
    if "swimmer_type_id" not in headers:
        return 0

    swimmer_types = _load_swimmer_type_names(types_path)
    changed = 0
    normalized_rows = []
    for row in rows:
        normalized = dict(row)
        original_value = normalized.get("swimmer_type_id", "")
        swimmer_type_id = coerce_swimmer_type_id(original_value, swimmer_types)
        if swimmer_type_id is None:
            normalized_rows.append(normalized)
            continue
        normalized_value = str(swimmer_type_id)
        if str(original_value).strip() != normalized_value:
            changed += 1
        normalized["swimmer_type_id"] = normalized_value
        normalized_rows.append(normalized)

    if changed:
        write_csv_file(output_path, headers, normalized_rows)
    return changed


def _flag_summary(flag_codes: list[str]) -> str:
    if not flag_codes:
        return ""
    highest = get_highest_severity(flag_codes)
    primary_code = next(
        (code for code in flag_codes if FLAG_CODES.get(code, {}).get("severity") == highest),
        flag_codes[0],
    )
    return FLAG_CODES.get(primary_code, {}).get("description", "")


def annotate_non_response_flags(result_payload: dict, swimmers_path: Path, types_path: Path) -> None:
    """Add the non_response_swimmer_type flag to matches/unassigned rows when needed."""
    swimmer_types = _load_swimmer_type_names(types_path)
    _, swimmer_rows = read_csv_file(swimmers_path)

    swimmer_type_by_swimmer_id = {}
    for row in swimmer_rows:
        swimmer_id = row.get("swimmer_id", "").strip()
        if not swimmer_id:
            continue
        swimmer_type_id = coerce_swimmer_type_id(row.get("swimmer_type_id"), swimmer_types)
        if swimmer_type_id is not None:
            swimmer_type_by_swimmer_id[swimmer_id] = swimmer_type_id

    def merge_flag(entry: dict, swimmer_ids: list[str]) -> None:
        if not any(
            is_non_response_swimmer_type(swimmer_type_by_swimmer_id.get(swimmer_id), swimmer_types)
            for swimmer_id in swimmer_ids
            if swimmer_id
        ):
            return

        existing_flag_codes = entry.get("flag_codes", [])
        flag_codes = list(existing_flag_codes) if isinstance(existing_flag_codes, list) else []
        if "non_response_swimmer_type" not in flag_codes:
            flag_codes.append("non_response_swimmer_type")
        entry["flag_codes"] = flag_codes
        entry["flags"] = expand_flag_codes(flag_codes)
        entry["flag_summary"] = _flag_summary(flag_codes)
        entry["review_action"] = get_primary_review_action(flag_codes)
        entry["review_severity"] = get_highest_severity(flag_codes)

    for match in result_payload.get("matches", []):
        swimmer_ids = []
        if "swimmer_id" in match:
            swimmer_ids.append(str(match.get("swimmer_id", "")))
        if "swimmer_1_id" in match:
            swimmer_ids.append(str(match.get("swimmer_1_id", "")))
        if "swimmer_2_id" in match:
            swimmer_ids.append(str(match.get("swimmer_2_id", "")))
        merge_flag(match, swimmer_ids)

    for unassigned in result_payload.get("unassigned", []):
        swimmer_id = str(unassigned.get("swimmer_id", ""))
        merge_flag(unassigned, [swimmer_id])


def annotate_default_instructor_flags(result_payload: dict, instructors_path: Path) -> None:
    """Add default_instructor_profile flag to matches that used a defaulted instructor profile."""
    _, instructor_rows = read_csv_file(instructors_path)
    defaulted_ids = {
        str(row.get("instructor_id", "")).strip()
        for row in instructor_rows
        if _parse_boolish(row.get("used_default_profile"), False)
    }

    if not defaulted_ids:
        return

    for match in result_payload.get("matches", []):
        instructor_id = str(match.get("instructor_id", "")).strip()
        if instructor_id not in defaulted_ids:
            continue

        existing_flag_codes = match.get("flag_codes", [])
        flag_codes = list(existing_flag_codes) if isinstance(existing_flag_codes, list) else []
        if "default_instructor_profile" not in flag_codes:
            flag_codes.append("default_instructor_profile")
        match["flag_codes"] = flag_codes
        match["flags"] = expand_flag_codes(flag_codes)
        match["flag_summary"] = _flag_summary(flag_codes)
        match["review_action"] = get_primary_review_action(flag_codes)
        match["review_severity"] = get_highest_severity(flag_codes)


# ---------------------------------------------------------------------------
# Win32 file picker (Windows only)
# ---------------------------------------------------------------------------

def _pick_csv_file_on_thread() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select CSV or Excel file",
            filetypes=[("Tabular Files", "*.csv *.xlsx *.xlsm"), ("All Files", "*.*")],
        )
        root.destroy()
        return path or ""
    except Exception:
        pass

    try:
        import ctypes
        import ctypes.wintypes as wt
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        try:
            OFN_PATHMUSTEXIST = 0x00000800
            OFN_FILEMUSTEXIST = 0x00001000
            OFN_NOCHANGEDIR   = 0x00000008
            buf      = ctypes.create_unicode_buffer(260)
            filter_s = ctypes.create_unicode_buffer(
                "Tabular Files (*.csv;*.xlsx;*.xlsm)\x00*.csv;*.xlsx;*.xlsm\x00All Files (*.*)\x00*.*\x00"
            )
            title_s  = ctypes.create_unicode_buffer("Select CSV or Excel file")

            class OPENFILENAMEW(ctypes.Structure):
                _fields_ = [
                    ("lStructSize",       ctypes.c_uint32),
                    ("hwndOwner",         wt.HWND),
                    ("hInstance",         wt.HINSTANCE),
                    ("lpstrFilter",       ctypes.c_wchar_p),
                    ("lpstrCustomFilter", ctypes.c_wchar_p),
                    ("nMaxCustFilter",    ctypes.c_uint32),
                    ("nFilterIndex",      ctypes.c_uint32),
                    ("lpstrFile",         ctypes.c_wchar_p),
                    ("nMaxFile",          ctypes.c_uint32),
                    ("lpstrFileTitle",    ctypes.c_wchar_p),
                    ("nMaxFileTitle",     ctypes.c_uint32),
                    ("lpstrInitialDir",   ctypes.c_wchar_p),
                    ("lpstrTitle",        ctypes.c_wchar_p),
                    ("Flags",             ctypes.c_uint32),
                    ("nFileOffset",       ctypes.c_uint16),
                    ("nFileExtension",    ctypes.c_uint16),
                    ("lpstrDefExt",       ctypes.c_wchar_p),
                    ("lCustData",         ctypes.c_long),
                    ("lpfnHook",          ctypes.c_void_p),
                    ("lpTemplateName",    ctypes.c_wchar_p),
                    ("pvReserved",        ctypes.c_void_p),
                    ("dwReserved",        ctypes.c_uint32),
                    ("FlagsEx",           ctypes.c_uint32),
                ]

            ofn = OPENFILENAMEW()
            ofn.lStructSize  = ctypes.sizeof(OPENFILENAMEW)
            ofn.lpstrFilter  = filter_s
            ofn.lpstrFile    = buf
            ofn.nMaxFile     = 260
            ofn.lpstrTitle   = title_s
            ofn.Flags        = OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST | OFN_NOCHANGEDIR
            ofn.nFilterIndex = 1
            if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
                return buf.value
            return ""
        finally:
            ctypes.windll.ole32.CoUninitialize()
    except Exception:
        return ""


def pick_csv_file_win32() -> str:
    result = [""]
    error  = [None]

    def run():
        try:
            result[0] = _pick_csv_file_on_thread()
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=run)
    t.start()
    t.join()
    if error[0]:
        return ""
    return result[0]


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def generate_job_id() -> str:
    return f"job_{secrets.token_hex(16)}"


def normalize_path_for_request(p: str) -> str:
    return _storage().normalize_path_for_request(p)


def _is_repo_sample_or_generated_path(path: Path) -> bool:
    return _storage().is_repo_sample_or_generated_path(path)


def _should_default_to_empty_historical(settings_snapshot: dict) -> bool:
    historical_path_str = (
        settings_snapshot["last_selected_files"].get("historical_pairings")
        or settings_snapshot["default_files"].get("historical_pairings", "")
    )
    if not historical_path_str:
        return True

    historical_path = resolve_from_root(historical_path_str)
    if not historical_path.exists():
        return True

    sample_historical_paths = {
        (
            APP_ROOT / "examples" / "demo" / "matching" / "historical_pairings.csv"
        ).resolve()
    }
    provisioned_sample = DEFAULT_FILE_PATHS.get("historical_pairings", "")
    if provisioned_sample:
        sample_historical_paths.add(resolve_from_root(provisioned_sample).resolve())
    if historical_path.resolve() not in sample_historical_paths:
        return False

    for key in ("classes", "swimmers", "instructors"):
        path_str = (
            settings_snapshot["last_selected_files"].get(key)
            or settings_snapshot["default_files"].get(key, "")
        )
        if not path_str:
            continue
        resolved = resolve_from_root(path_str)
        if resolved.exists() and not _is_repo_sample_or_generated_path(resolved):
            return True
    return False


def _write_empty_historical_pairings_csv(path: Path) -> None:
    path.write_text("swimmer_id,instructor_id,session,num_sessions\n", encoding="utf-8")


def _input_file_problem(path: Path) -> Optional[str]:
    """Return 'missing' or 'empty' when a selected input file can't feed the
    solver, or None when it looks usable (or can't be cheaply checked)."""
    if not path.exists():
        return "missing"
    try:
        text = read_tabular_file_text(path)
    except Exception:
        return None  # unreadable files get a specific error downstream
    data_lines = [line for line in text.splitlines() if line.strip()]
    if len(data_lines) < 2:  # header-only or blank
        return "empty"
    return None


def _read_csv_id_set(path: Path, column: str) -> "Optional[set[str]]":
    """Return the set of non-empty values in `column`, or None if the file
    can't be read or lacks that column (caller should skip filtering then)."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or column not in reader.fieldnames:
                return None
            return {
                value
                for row in reader
                if (value := (row.get(column) or "").strip())
            }
    except OSError:
        return None


def filter_historical_pairings_csv(
    csv_text: str,
    swimmer_ids: "Optional[set[str]]",
    instructor_ids: "Optional[set[str]]",
) -> tuple[str, int, int]:
    """Drop historical pairings whose swimmer or instructor isn't in the given
    ID sets. Historical pairings are history, not constraints — unknown IDs
    must not fail the run. A None ID set disables filtering on that column.

    Returns (filtered_csv_text, kept_count, skipped_count).
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or ["swimmer_id", "instructor_id", "session", "num_sessions"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    kept = skipped = 0
    for row in reader:
        swimmer = (row.get("swimmer_id") or "").strip()
        instructor = (row.get("instructor_id") or "").strip()
        if (swimmer_ids is not None and swimmer not in swimmer_ids) or (
            instructor_ids is not None and instructor not in instructor_ids
        ):
            skipped += 1
            continue
        writer.writerow(row)
        kept += 1
    return output.getvalue(), kept, skipped


def build_request_json(settings: dict, job_id: str) -> str:
    def get(k):
        return settings["last_selected_files"].get(k) or settings["default_files"].get(k, "")

    payload = {
        "job_id": job_id,
        "app_root": APP_ROOT.as_posix(),
        "data": {
            "classes":             normalize_path_for_request(get("classes")),
            "swimmers":            normalize_path_for_request(get("swimmers")),
            "instructors":         normalize_path_for_request(get("instructors")),
            "historical_pairings": normalize_path_for_request(get("historical_pairings")),
            "reference": {
                "personality_colors":          normalize_path_for_request(get("personality_colors")),
                "instructor_styles":           normalize_path_for_request(get("instructor_styles")),
                "swimmer_types":               normalize_path_for_request(get("swimmer_types")),
                "swimmer_type_color_rankings": normalize_path_for_request(get("swimmer_type_color_rankings")),
                "swimmer_type_style_rankings": normalize_path_for_request(get("swimmer_type_style_rankings")),
            },
        },
        "config": {
            "enable_continuity":    True,
            "enable_note_requests": True,
        },
    }
    return json.dumps(payload, indent=2)


# Thin wrappers around the extracted SolverRunner service. They keep the
# historical names on this module (call sites and tests patch
# backend.server.run_solver etc.) while the service itself stays free of
# server dependencies.

def run_solver(executable: Path, request_path: Path, result_path: Path) -> None:
    solver_runner.run_solver(executable, request_path, result_path, logger=get_logger())


def read_solver_result(result_path: Path) -> str:
    return solver_runner.read_solver_result(result_path, logger=get_logger())


def parse_and_validate_solver_result(result_text: str) -> dict:
    return solver_runner.parse_and_validate_solver_result(result_text, logger=get_logger())


def create_generation_service(services: ApplicationServices | None = None) -> GenerationService:
    """Build the service from current host dependencies and test seams."""

    services = services or application_services

    return GenerationService(
        GenerationDependencies(
            app_root=services.paths.app_root,
            jobs_dir=services.paths.jobs_dir,
            solvers_dir=services.paths.solvers_dir,
            logger=services.logger,
            generate_job_id=generate_job_id,
            resolve_from_root=resolve_from_root,
            sanitize_instructor_profile=_sanitize_instructor_default_profile,
            input_file_problem=_input_file_problem,
            read_csv_id_set=_read_csv_id_set,
            filter_historical_pairings=filter_historical_pairings_csv,
            should_default_to_empty_historical=_should_default_to_empty_historical,
            write_empty_historical_pairings=_write_empty_historical_pairings_csv,
            normalize_swimmers=normalize_swimmers_csv,
            normalize_instructors=normalize_instructors_csv,
            build_request_json=build_request_json,
            run_solver=run_solver,
            read_solver_result=read_solver_result,
            parse_solver_result=parse_and_validate_solver_result,
            annotate_non_response_flags=annotate_non_response_flags,
            annotate_default_instructor_flags=annotate_default_instructor_flags,
            db_count_instructors=services.repository.count_instructors,
            db_export_instructors_csv=services.repository.export_instructors_solver_csv,
            db_load_historical_csv=services.repository.load_historical_pairings_csv,
            db_save_session=services.repository.save_session_pairings,
            set_last_job_dir=lambda path: setattr(services.state, "last_job_dir", path),
        )
    )


# ---------------------------------------------------------------------------
# Shutdown watchdog
# ---------------------------------------------------------------------------

HEARTBEAT_TIMEOUT = 180  # 3 minutes


def _watchdog(state: ApplicationState):
    while not state.shutdown_event.wait(timeout=5):
        # A synchronous generate request prevents the renderer's heartbeat
        # fetch from completing. Keep the host alive until the bounded solver
        # request finishes so the five-minute solver timeout remains reachable.
        if state.generate_in_progress:
            state.last_heartbeat = time.monotonic()
            continue
        if time.monotonic() - state.last_heartbeat > HEARTBEAT_TIMEOUT:
            print("UI heartbeat timed out. Shutting down.", flush=True)
            os.kill(os.getpid(), signal.SIGINT)
            return


NO_CACHE = {"Cache-Control": "no-store"}
# no-cache (not max-age): browsers kept executing stale app.js after app
# updates. Files are small and served from localhost, so refetching is cheap.
STATIC_CACHE = {"Cache-Control": "no-cache"}
GENERATE_RATE_LIMIT_SECONDS = 5.0
LOOPBACK_HOST = "127.0.0.1"


# -- Security headers --------------------------------------------------------
_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _services_from_request(request: Request) -> ApplicationServices:
    return request.app.state.services


api_router = APIRouter()


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

# -- Health ------------------------------------------------------------------

@api_router.get("/api/health")
def health():
    return JSONResponse({"ok": True, "version": "0.1.0"}, headers=NO_CACHE)


@api_router.get("/api/ready")
def readiness(request: Request):
    """Report whether application startup has completed and requests are safe."""

    ready = _services_from_request(request).state.ready
    return JSONResponse(
        {"ok": ready, "status": "ready" if ready else "starting"},
        status_code=200 if ready else 503,
        headers=NO_CACHE,
    )


# -- Heartbeat / Shutdown ----------------------------------------------------

@api_router.post("/api/heartbeat")
def heartbeat(request: Request):
    _services_from_request(request).state.last_heartbeat = time.monotonic()
    return JSONResponse({"ok": True}, headers=NO_CACHE)


@api_router.post("/api/shutdown")
def shutdown():
    def _do_shutdown():
        time.sleep(8)
        os.kill(os.getpid(), signal.SIGINT)
    threading.Thread(target=_do_shutdown, daemon=True).start()
    return JSONResponse({"ok": True, "shutdown_scheduled": True}, headers=NO_CACHE)


# -- Settings, file picker, and generation routes live in backend/routers/ ---


# -- Rankings editor ---------------------------------------------------------

RANKING_EDITOR_CONFIGS = {
    "swimmer_type_color_rankings": {
        "rankings_key": "swimmer_type_color_rankings",
        "lookup_key": "personality_colors",
        "item_id_col": "color_id",
        "item_name_col": "color_name",
        "item_singular": "color",
        "item_plural": "colors",
        "kind": "color",
    },
    "swimmer_type_style_rankings": {
        "rankings_key": "swimmer_type_style_rankings",
        "lookup_key": "instructor_styles",
        "item_id_col": "style_id",
        "item_name_col": "style_name",
        "item_singular": "style",
        "item_plural": "styles",
        "kind": "style",
    },
}


@api_router.post("/api/rankings_editor/load")
async def rankings_editor_load(request: Request):
    state = _services_from_request(request).state
    body = await request.json()
    purpose = body.get("purpose", "")

    config = RANKING_EDITOR_CONFIGS.get(purpose)
    if not config:
        return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=NO_CACHE)

    rankings_path = get_setting_path(config["rankings_key"], state)
    lookup_path = get_setting_path(config["lookup_key"], state)
    types_path = get_setting_path("swimmer_types", state)

    for label, p in [("rankings", rankings_path), ("lookup", lookup_path), ("swimmer_types", types_path)]:
        if not p:
            return JSONResponse({"ok": False, "error": f"{label} file not configured"}, status_code=400, headers=NO_CACHE)

    try:
        _, rankings_rows  = read_csv_file(rankings_path)
        _, lookup_rows    = read_csv_file(lookup_path)
        _, types_rows     = read_csv_file(types_path)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=NO_CACHE)

    item_id_col   = config["item_id_col"]
    item_name_col = config["item_name_col"]

    # Build item name lookup
    item_names = {row[item_id_col]: row.get(item_name_col, row[item_id_col]) for row in lookup_rows}

    # Build rankings by swimmer type
    rankings_by_type: dict[str, list] = {}
    for row in rankings_rows:
        tid = row.get("swimmer_type_id", "")
        if tid not in rankings_by_type:
            rankings_by_type[tid] = []
        rankings_by_type[tid].append({"id": row[item_id_col], "rank": int(row.get("rank", 999))})

    for tid in rankings_by_type:
        rankings_by_type[tid].sort(key=lambda x: x["rank"])

    swimmer_types_out = []
    for t in types_rows:
        tid = t.get("swimmer_type_id", "")
        ranked = rankings_by_type.get(tid, [])
        # Fallback: append any items not yet ranked
        ranked_ids = {r["id"] for r in ranked}
        for row in lookup_rows:
            if row[item_id_col] not in ranked_ids:
                ranked.append({"id": row[item_id_col], "rank": len(ranked) + 1})

        items = [
            {
                "client_key": f"existing-{r['id']}",
                "id": r["id"],
                "name": item_names.get(r["id"], r["id"]),
                "rank": i + 1,
            }
            for i, r in enumerate(ranked)
        ]
        swimmer_types_out.append({
            "id": tid,
            "name": t.get("swimmer_type_name", tid),
            "items": items,
        })

    return JSONResponse({
        "ok": True,
        "purpose": purpose,
        "kind": config["kind"],
        "item_singular": config["item_singular"],
        "item_plural": config["item_plural"],
        "rankings_path": str(rankings_path),
        "lookup_path": str(lookup_path),
        "swimmer_types": swimmer_types_out,
    }, headers=NO_CACHE)


@api_router.post("/api/rankings_editor/save")
async def rankings_editor_save(request: Request):
    state = _services_from_request(request).state
    body = await request.json()
    purpose = body.get("purpose", "")
    swimmer_types = body.get("swimmer_types", [])
    items = body.get("items", [])

    config = RANKING_EDITOR_CONFIGS.get(purpose)
    if not config:
        return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=NO_CACHE)
    if (
        not isinstance(swimmer_types, list)
        or not swimmer_types
        or not isinstance(items, list)
        or not items
    ):
        return JSONResponse(
            {"ok": False, "error": "Rankings payload must include items and swimmer types"},
            status_code=400,
            headers=NO_CACHE,
        )

    rankings_path = get_writable_setting_path(config["rankings_key"], state)
    lookup_path = get_writable_setting_path(config["lookup_key"], state)
    if not rankings_path or not lookup_path:
        return JSONResponse(
            {"ok": False, "error": "Rankings or lookup file not configured"},
            status_code=400,
            headers=NO_CACHE,
        )

    item_id_col = config["item_id_col"]
    item_name_col = config["item_name_col"]
    try:
        lookup_headers, lookup_rows = read_csv_file(lookup_path)
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Failed to read lookup file"},
            status_code=500,
            headers=NO_CACHE,
        )
    if item_id_col not in lookup_headers or item_name_col not in lookup_headers:
        return JSONResponse(
            {"ok": False, "error": "Lookup file has an invalid schema"},
            status_code=400,
            headers=NO_CACHE,
        )

    existing_by_id = {
        str(row.get(item_id_col, "")).strip(): row
        for row in lookup_rows
        if str(row.get(item_id_col, "")).strip()
    }
    used_ids = set(existing_by_id)
    numeric_ids = [int(value) for value in used_ids if value.isdigit()]
    next_id = max(numeric_ids, default=0) + 1
    used_names = {
        str(row.get(item_name_col, "")).strip().casefold()
        for row in lookup_rows
        if str(row.get(item_name_col, "")).strip()
    }
    item_ids_by_key: dict[str, str] = {}
    kept_existing_ids: set[str] = set()
    new_lookup_rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            return JSONResponse(
                {"ok": False, "error": "Each rankings item must be an object"},
                status_code=400,
                headers=NO_CACHE,
            )
        client_key = str(item.get("client_key", "")).strip()
        name = str(item.get("name", "")).strip()
        raw_id = str(item.get("id", "") or "").strip()
        if not client_key or not name or client_key in item_ids_by_key:
            return JSONResponse(
                {"ok": False, "error": "Each rankings item needs a unique key and name"},
                status_code=400,
                headers=NO_CACHE,
            )

        if raw_id:
            if raw_id not in existing_by_id:
                return JSONResponse(
                    {"ok": False, "error": "Rankings item references an unknown lookup ID"},
                    status_code=400,
                    headers=NO_CACHE,
                )
            assigned_id = raw_id
            kept_existing_ids.add(raw_id)
        else:
            normalized_name = name.casefold()
            if normalized_name in used_names:
                return JSONResponse(
                    {"ok": False, "error": "Rankings item name already exists"},
                    status_code=400,
                    headers=NO_CACHE,
                )
            while str(next_id) in used_ids:
                next_id += 1
            assigned_id = str(next_id)
            next_id += 1
            used_ids.add(assigned_id)
            used_names.add(normalized_name)
            new_row = {header: "" for header in lookup_headers}
            new_row[item_id_col] = assigned_id
            new_row[item_name_col] = name
            new_lookup_rows.append(new_row)
        item_ids_by_key[client_key] = assigned_id

    expected_keys = set(item_ids_by_key)
    rows = []
    for st in swimmer_types:
        if not isinstance(st, dict):
            return JSONResponse(
                {"ok": False, "error": "Each swimmer type must be an object"},
                status_code=400,
                headers=NO_CACHE,
            )
        tid = st.get("id", "")
        item_keys = st.get("item_keys", [])
        if (
            not str(tid).strip()
            or not isinstance(item_keys, list)
            or len(item_keys) != len(expected_keys)
            or set(item_keys) != expected_keys
        ):
            return JSONResponse(
                {"ok": False, "error": "Each swimmer type must rank every item exactly once"},
                status_code=400,
                headers=NO_CACHE,
            )
        for idx, key in enumerate(item_keys):
            rows.append({
                "swimmer_type_id": str(tid),
                item_id_col: item_ids_by_key[key],
                "rank": str(idx + 1),
            })

    updated_lookup_rows = [
        row
        for row in lookup_rows
        if str(row.get(item_id_col, "")).strip() in kept_existing_ids
    ] + new_lookup_rows
    try:
        write_csv_file(lookup_path, lookup_headers, updated_lookup_rows)
        write_csv_file(rankings_path, ["swimmer_type_id", item_id_col, "rank"], rows)
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Failed to save rankings files"},
            status_code=500,
            headers=NO_CACHE,
        )

    return JSONResponse({
        "ok": True,
        "lookup_updated": bool(new_lookup_rows) or len(updated_lookup_rows) != len(lookup_rows),
        "workbook_synced": False,
        "workbook_warning": "",
    }, headers=NO_CACHE)


# -- Reference table editor --------------------------------------------------

REFERENCE_TABLE_CONFIGS = {
    "personality_colors": {
        "key": "personality_colors",
        "id_col": "color_id",
        "field_cols": ["color_name", "traits"],
        "title_field": "color_name",
        "item_singular": "color",
        "item_plural": "colors",
    },
    "instructor_styles": {
        "key": "instructor_styles",
        "id_col": "style_id",
        "field_cols": ["style_code", "style_name", "traits", "expertise_area"],
        "title_field": "style_name",
        "item_singular": "style",
        "item_plural": "styles",
    },
    "swimmer_types": {
        "key": "swimmer_types",
        "id_col": "swimmer_type_id",
        "field_cols": ["swimmer_type_name"],
        "title_field": "swimmer_type_name",
        "item_singular": "swimmer type",
        "item_plural": "swimmer types",
    },
}


@api_router.post("/api/reference_table/load")
async def reference_table_load(request: Request):
    state = _services_from_request(request).state
    body = await request.json()
    purpose = body.get("purpose", "")
    config = REFERENCE_TABLE_CONFIGS.get(purpose)
    if not config:
        return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=NO_CACHE)

    path = get_writable_setting_path(config["key"], state)
    if not path:
        return JSONResponse({"ok": False, "error": f"{purpose} file not configured"}, status_code=400, headers=NO_CACHE)

    try:
        _, rows = read_csv_file(path)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=NO_CACHE)

    items = []
    for row in rows:
        item_id = row.get(config["id_col"], "")
        fields = {col: row.get(col, "") for col in config["field_cols"]}
        items.append({
            "client_key": f"existing-{item_id}",
            "id": item_id,
            "fields": fields,
        })

    return JSONResponse({
        "ok": True,
        "purpose": purpose,
        "item_singular": config["item_singular"],
        "item_plural": config["item_plural"],
        "path": str(path),
        "id_column": config["id_col"],
        "field_columns": config["field_cols"],
        "title_field": config["title_field"],
        "items": items,
    }, headers=NO_CACHE)


@api_router.post("/api/reference_table/save")
async def reference_table_save(request: Request):
    state = _services_from_request(request).state
    body = await request.json()
    purpose = body.get("purpose", "")
    incoming_items = body.get("items", [])
    config = REFERENCE_TABLE_CONFIGS.get(purpose)
    if not config:
        return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=NO_CACHE)

    path = get_writable_setting_path(config["key"], state)
    if not path:
        return JSONResponse({"ok": False, "error": f"{purpose} file not configured"}, status_code=400, headers=NO_CACHE)

    # Load existing to preserve IDs and get next_id
    try:
        _, existing_rows = read_csv_file(path)
    except Exception:
        existing_rows = []

    existing_ids = {}
    next_id = 1
    for row in existing_rows:
        try:
            eid = int(row.get(config["id_col"], 0))
            existing_ids[row.get(config["id_col"], "")] = eid
            next_id = max(next_id, eid + 1)
        except (ValueError, TypeError):
            pass

    headers = [config["id_col"]] + config["field_cols"]
    rows = []
    for item in incoming_items:
        item_id = item.get("id")
        if not item_id or item_id == "null":
            item_id = str(next_id)
            next_id += 1
        fields = item.get("fields", {})
        row = {config["id_col"]: str(item_id)}
        for col in config["field_cols"]:
            row[col] = fields.get(col, "")
        rows.append(row)

    try:
        write_csv_file(path, headers, rows)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=NO_CACHE)

    return JSONResponse({
        "ok": True,
        "rankings_updated": False,
        "swimmer_type_rankings_synced": False,
        "dependent_rankings_synced": False,
        "workbook_synced": False,
        "workbook_warning": "",
    }, headers=NO_CACHE)


# -- Profile lookup ----------------------------------------------------------

@api_router.get("/api/profile/{profile_type}/{profile_id}")
def get_profile(request: Request, profile_type: str, profile_id: str):
    if profile_type not in ("swimmer", "instructor"):
        return JSONResponse({"ok": False, "error": "Invalid type"}, status_code=400, headers=NO_CACHE)
    last_job_dir = _services_from_request(request).state.last_job_dir
    if not last_job_dir:
        return JSONResponse({"ok": False, "error": "No profiles available. Run a generation first."}, status_code=503, headers=NO_CACHE)

    profiles_path = Path(last_job_dir) / "profiles.json"
    if not profiles_path.exists():
        return JSONResponse({"ok": False, "error": "No profiles available. Run a generation first."}, status_code=503, headers=NO_CACHE)

    try:
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "Failed to read profiles.json"}, status_code=500, headers=NO_CACHE)

    section = profiles.get(profile_type + "s")
    if not section:
        return JSONResponse({"ok": False, "error": "Profile section not found"}, status_code=404, headers=NO_CACHE)

    profile = section.get(str(profile_id))
    if not profile:
        return JSONResponse({"ok": False, "error": f"{profile_type} {profile_id} not found"}, status_code=404, headers=NO_CACHE)

    return JSONResponse({"ok": True, "profile": profile}, headers=NO_CACHE)


# -- Latest generation result ------------------------------------------------

@api_router.get("/api/latest_generation_result")
def api_latest_generation_result(request: Request):
    last_job_dir = _services_from_request(request).state.last_job_dir
    if not last_job_dir:
        return JSONResponse({"ok": True, "has_result": False}, headers=NO_CACHE)

    job_path = Path(last_job_dir)
    result_json_path = job_path / "result.json"
    if not result_json_path.exists():
        return JSONResponse({"ok": True, "has_result": False}, headers=NO_CACHE)

    try:
        result_text = read_solver_result(result_json_path)
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=NO_CACHE)

    try:
        result_payload = parse_and_validate_solver_result(result_text)
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=NO_CACHE)

    result_payload = expose_result_files(result_payload, job_path)
    result_payload["has_result"] = True

    prepared_settings_path = job_path / "prepared_settings.json"
    if prepared_settings_path.exists():
        try:
            prepared = json.loads(prepared_settings_path.read_text(encoding="utf-8"))
            if "import_diagnostics" in prepared:
                result_payload["import_diagnostics"] = prepared["import_diagnostics"]
        except Exception:
            pass

    warnings_path = job_path / "generation_warnings.json"
    if warnings_path.exists():
        try:
            saved = json.loads(warnings_path.read_text(encoding="utf-8"))
            if isinstance(saved, list):
                result_payload["warnings"] = [str(w) for w in saved]
        except Exception:
            pass

    return JSONResponse(result_payload, headers=NO_CACHE)


# -- Instructor style/color editor -------------------------------------------

@api_router.post("/api/instructor_style_color_editor/load")
async def api_instructor_style_color_editor_load(request: Request):
    services = _services_from_request(request)
    state = services.state
    try:
        get_writable_setting_path("instructors", state)
        payload = _isce_load_payload(
            services.paths.app_root,
            services.paths.app_root,
            services.paths.settings_path,
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=NO_CACHE)

    colors, _ = _load_reference_options("personality_colors", "color_id", "color_name")
    styles, _ = _load_reference_options("instructor_styles", "style_id", "style_name")
    payload["colors"] = colors
    payload["styles"] = styles
    payload["default_profile"] = _sanitize_instructor_default_profile(state.settings.get("default_instructor_profile"))
    return JSONResponse(payload, headers=NO_CACHE)


@api_router.post("/api/instructor_style_color_editor/save")
async def api_instructor_style_color_editor_save(request: Request):
    services = _services_from_request(request)
    state = services.state
    get_writable_setting_path("instructors", state)
    try:
        body = await request.body()
    except Exception:
        body = b"{}"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="wb")
    try:
        tmp.write(body)
        tmp.close()
        payload = _isce_save_payload(
            services.paths.app_root,
            services.paths.app_root,
            services.paths.settings_path,
            Path(tmp.name),
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=NO_CACHE)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    colors, _ = _load_reference_options("personality_colors", "color_id", "color_name")
    styles, _ = _load_reference_options("instructor_styles", "style_id", "style_name")
    payload["colors"] = colors
    payload["styles"] = styles
    payload["default_profile"] = _sanitize_instructor_default_profile(state.settings.get("default_instructor_profile"))
    return JSONResponse(payload, headers=NO_CACHE)


# -- Historical pairings / sessions routes live in backend/routers/sessions.py
# -- Instructor routes live in backend/routers/instructors.py -----------------

# -- XAI dashboard launch ----------------------------------------------------

@api_router.post("/api/launch_dashboard")
def launch_dashboard(request: Request):
    if not _services_from_request(request).state.last_job_dir:
        return JSONResponse({"ok": False, "error": "No job has been run yet"}, status_code=503, headers=NO_CACHE)
    return JSONResponse({"ok": True, "url": "/xai/"}, headers=NO_CACHE)


# -- Extracted routers --------------------------------------------------------
# Registered before the /jobs/{path} and /{path} catch-alls below. Each router
# receives an explicit, narrow dependency container; lambdas preserve dynamic
# state and the existing test seams without exposing this entire module.
from backend.routers.instructors import (  # noqa: E402
    InstructorsDependencies,
    create_instructors_router,
)
from backend.routers.generation import (  # noqa: E402
    GenerationRouterDependencies,
    create_generation_router,
)
from backend.routers.sessions import SessionsDependencies, create_sessions_router  # noqa: E402
from backend.routers.settings_files import (  # noqa: E402
    SettingsFilesDependencies,
    create_settings_files_router,
)
from backend.routers.jackrabbit_import import (  # noqa: E402
    JackrabbitImportDependencies,
    create_jackrabbit_import_router,
)

def _include_dependency_routers(application: FastAPI, services: ApplicationServices) -> None:
    state = services.state
    application.include_router(
        create_jackrabbit_import_router(
            JackrabbitImportDependencies(
                no_cache_headers=NO_CACHE,
                app_data_root=services.paths.app_data_root,
                settings_lock=state.settings_lock,
                get_settings=lambda: state.settings,
                validate_settings=validate_and_fixup,
                save_settings=lambda value: save_settings(value, services.paths.settings_path),
                sanitize_instructor_profile=_sanitize_instructor_default_profile,
                import_classes=import_classes,
                import_students=import_students,
                import_instructors=import_instructors,
                repository=services.repository,
                operator_name=_operator_name,
            )
        )
    )
    application.include_router(
        create_generation_router(
            GenerationRouterDependencies(
                no_cache_headers=NO_CACHE,
                settings_lock=state.settings_lock,
                get_settings=lambda: state.settings,
                validate_settings=validate_and_fixup,
                save_settings=lambda value: save_settings(value, services.paths.settings_path),
                try_begin=lambda: state.try_begin_generation(GENERATE_RATE_LIMIT_SECONDS),
                finish=state.finish_generation,
                create_service=lambda: create_generation_service(services),
            )
        )
    )
    application.include_router(
        create_settings_files_router(
            SettingsFilesDependencies(
                NO_CACHE=NO_CACHE,
                _settings_lock=state.settings_lock,
                get_settings=lambda: state.settings,
                validate_and_fixup=validate_and_fixup,
                make_default_settings=make_default_settings,
                _sanitize_instructor_default_profile=_sanitize_instructor_default_profile,
                save_settings=lambda value: save_settings(value, services.paths.settings_path),
                _build_instructor_defaults_payload=_build_instructor_defaults_payload,
                _require_json=_require_json,
                repository=services.repository,
                _sanitize_session_id_list=_sanitize_session_id_list,
                pick_csv_file_win32=pick_csv_file_win32,
            )
        )
    )
    application.include_router(
        create_instructors_router(
            InstructorsDependencies(
                NO_CACHE=NO_CACHE,
                APP_ROOT=services.paths.app_root,
                _settings_lock=state.settings_lock,
                get_settings=lambda: state.settings,
                _load_reference_options=lambda *args, **kwargs: _load_reference_options(
                    *args, state=state, **kwargs
                ),
                xlsx_bytes_to_csv_text=xlsx_bytes_to_csv_text,
                is_partner_instructors_csv=is_partner_instructors_csv,
                _sanitize_instructor_default_profile=_sanitize_instructor_default_profile,
                import_instructors=import_instructors,
                repository=services.repository,
                _require_json=_require_json,
                _operator_name=_operator_name,
                resolve_from_root=resolve_from_root,
            )
        )
    )
    application.include_router(
        create_sessions_router(
            SessionsDependencies(
                NO_CACHE=NO_CACHE,
                get_last_job_dir=lambda: state.last_job_dir,
                generate_historical_pairings=generate_historical_pairings,
                repository=services.repository,
                _operator_name=_operator_name,
            )
        )
    )


# -- Job file serving --------------------------------------------------------

@api_router.get("/jobs/{path:path}")
def serve_job_file(request: Request, path: str):
    jobs_dir = _services_from_request(request).paths.jobs_dir
    resolved = (jobs_dir / path).resolve()
    if not resolved.is_relative_to(jobs_dir.resolve()):
        return Response("Forbidden", status_code=403)
    if not resolved.exists() or resolved.is_dir():
        return Response("Not found", status_code=404)
    return FileResponse(resolved, headers=NO_CACHE)


# -- Static UI ---------------------------------------------------------------

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".pdf":  "application/pdf",
    ".csv":  "text/csv; charset=utf-8",
    ".woff2": "font/woff2",
}


@api_router.get("/{path:path}")
def serve_static(request: Request, path: str):
    if path.startswith("api/") or path.startswith("xai/"):
        return Response("Not found", status_code=404)

    relative = path.strip("/") or "index.html"
    ui_dir = _services_from_request(request).paths.ui_dir
    target = (ui_dir / relative).resolve()

    if not target.is_relative_to(ui_dir.resolve()):
        return Response("Forbidden", status_code=403)

    if target.is_dir():
        target = target / "index.html"

    if not target.exists():
        return Response("Not found", status_code=404)

    mime = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
    cache_headers = NO_CACHE if target.suffix.lower() in (".html", ".htm") else STATIC_CACHE
    return Response(content=target.read_bytes(), media_type=mime, headers=cache_headers)


# ---------------------------------------------------------------------------
# Application assembly
# ---------------------------------------------------------------------------

DEFAULT_BACKEND_PATHS = BackendPaths(
    app_root=APP_ROOT,
    ui_dir=UI_DIR,
    solvers_dir=SOLVERS_DIR,
    app_data_root=APP_DATA_ROOT,
    jobs_dir=JOBS_DIR,
    settings_path=SETTINGS_PATH,
    database_path=DB_PATH,
    writable_resources_dir=WRITABLE_RESOURCES_DIR,
)


def create_application_services(
    *,
    paths: BackendPaths = DEFAULT_BACKEND_PATHS,
    initial_settings: dict | None = None,
    persist_settings: bool = True,
    launch_token: str | None = None,
) -> ApplicationServices:
    """Create the explicit services and isolated mutable state for one app."""

    current_settings = initial_settings if initial_settings is not None else load_settings(paths.settings_path)
    validate_and_fixup(current_settings)
    if persist_settings:
        save_settings(current_settings, paths.settings_path)
    configured_token = launch_token if launch_token is not None else launch_token_from_environment()
    return ApplicationServices(
        paths=paths,
        state=ApplicationState(settings=current_settings),
        logger=get_logger(),
        repository=SqliteRepository(paths.database_path),
        launch_auth=LaunchTokenAuth.configured(configured_token),
    )


def create_app(services: ApplicationServices | None = None) -> FastAPI:
    """Assemble and return an independently stateful FastAPI application."""

    services = services or create_application_services()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        state = services.state
        state.shutdown_event.clear()
        retention = RetentionPolicy.from_environment()
        cleanup = cleanup_expired_jobs(
            services.paths.jobs_dir,
            services.paths.app_data_root,
            retention_days=retention.jobs_days,
        )
        services.logger.info(
            "Application job retention cleanup completed",
            extra={
                "event": "job_retention_cleanup",
                "retention_days": retention.jobs_days,
                "removed_count": cleanup.removed,
                "skipped_count": cleanup.skipped,
                "error_count": cleanup.errors,
            },
        )
        if state.watchdog_thread is None or not state.watchdog_thread.is_alive():
            state.watchdog_thread = threading.Thread(
                target=_watchdog,
                args=(state,),
                daemon=True,
            )
            state.watchdog_thread.start()
        state.ready = True
        services.logger.info("FastAPI host startup complete", extra={"event": "startup"})
        try:
            yield
        finally:
            state.ready = False
            state.shutdown_event.set()
            solver_runner.ACTIVE_SOLVER_PROCESSES.terminate_all(services.logger)
            if state.watchdog_thread is not None:
                state.watchdog_thread.join(timeout=1)
                state.watchdog_thread = None
            services.logger.info("FastAPI host shutting down", extra={"event": "shutdown"})

    application = FastAPI(lifespan=lifespan)
    application.state.services = services

    xai_static_dir = services.paths.ui_dir / "xai_dashboard" / "static"
    application.mount(
        "/xai/static",
        StaticFiles(directory=str(xai_static_dir)),
        name="xai_static",
    )
    application.include_router(
        create_xai_router(
            get_job_dir=lambda: services.state.last_job_dir or str(services.paths.jobs_dir),
            source_dir=str(services.paths.app_root / "data" / "source"),
        )
    )

    @application.middleware("http")
    async def launch_token_middleware(request: Request, call_next):
        if requires_launch_token(request.url.path) and not services.launch_auth.accepts(
            request.headers.get(LAUNCH_TOKEN_HEADER)
        ):
            return JSONResponse(
                {"ok": False, "error": "Unauthorized"},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        return await call_next(request)

    @application.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        if request.url.path.startswith("/xai/static") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        path = request.url.path
        if not (path.startswith("/api/") or path.startswith("/xai/") or path.startswith("/jobs/")):
            return await call_next(request)
        request_id = generate_request_id()
        request.state.request_id = request_id
        started = time.perf_counter()
        services.logger.info(
            "Request started",
            extra={
                "event": "request_started",
                "request_id": request_id,
                "route": path,
                "method": request.method,
            },
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            services.logger.error(
                "Request failed",
                extra={
                    "event": "request_failed",
                    "request_id": request_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "exception": str(exc),
                },
            )
            raise
        completed_extra = {
            "event": "request_completed",
            "request_id": request_id,
            "route": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        job_id = getattr(request.state, "job_id", None)
        if job_id:
            completed_extra["job_id"] = job_id
        services.logger.info("Request completed", extra=completed_extra)
        return response

    # Added after the function middleware so Host validation is the outermost
    # request boundary. Invalid hosts never reach readiness, auth, or routes.
    application.add_middleware(
        LoopbackHostMiddleware,
        security_headers=tuple(_SECURITY_HEADERS.items()),
    )

    _include_dependency_routers(application, services)
    application.include_router(api_router)
    return application


# ASGI compatibility: uvicorn and existing integrations may still import
# backend.server:app, while tests and desktop hosts can call create_app().
application_services = create_application_services()
app = create_app(application_services)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DEFAULT_CANDIDATE_PORTS = [8787, 8788, 8789, 8790, 8791, 8792, 8793, 8794]


def parse_port_env() -> int | None:
    """Read PORT; zero requests an OS-selected ephemeral loopback port."""
    raw = os.environ.get("PORT", "").strip()
    if not raw:
        return None
    return validate_requested_port(raw)


def validate_requested_port(value: int | str) -> int:
    """Validate an explicit port value; zero means choose an ephemeral port."""

    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("PORT must be an integer between 0 and 65535")
    if not (0 <= port <= 65535):
        raise ValueError("PORT must be an integer between 0 and 65535")
    return port


def get_candidate_ports() -> list[int]:
    return list(DEFAULT_CANDIDATE_PORTS)


def reserve_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOOPBACK_HOST, 0))
        return s.getsockname()[1]


def find_listen_port(requested_port: int | None = None) -> int:
    port = parse_port_env() if requested_port is None else validate_requested_port(requested_port)
    if port == 0:
        return reserve_ephemeral_port()
    if port is not None:
        return port
    for port in get_candidate_ports():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((LOOPBACK_HOST, port)) != 0:
                return port
    return reserve_ephemeral_port()


if __name__ == "__main__":
    import webbrowser
    if uvicorn is None:
        raise RuntimeError("uvicorn is required to run the Aqua Essence host server")
    port = find_listen_port()
    url = f"http://{LOOPBACK_HOST}:{port}/"
    print(f"Listening on {url}", flush=True)
    threading.Timer(1.0, webbrowser.open, args=[url]).start()
    uvicorn.run(app, host=LOOPBACK_HOST, port=port, log_level="warning")
