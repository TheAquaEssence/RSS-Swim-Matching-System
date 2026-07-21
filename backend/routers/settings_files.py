
"""Settings and file-selection routes with explicit host dependencies."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from backend.services.repository import SqliteRepository


@dataclass(frozen=True)
class SettingsFilesDependencies:
    NO_CACHE: dict[str, str]
    _settings_lock: Any
    get_settings: Callable[[], dict]
    validate_and_fixup: Callable[[dict], None]
    make_default_settings: Callable[[], dict]
    _sanitize_instructor_default_profile: Callable[[dict | None], dict]
    save_settings: Callable[[dict], None]
    _build_instructor_defaults_payload: Callable[[dict | None], dict]
    _require_json: Callable[[Request], None]
    repository: "SqliteRepository"
    _sanitize_session_id_list: Callable[[Any], list[int]]
    pick_csv_file_win32: Callable[[], str]

    @property
    def settings(self) -> dict:
        return self.get_settings()


def create_settings_files_router(deps: SettingsFilesDependencies) -> APIRouter:
    """Return the settings/files router."""
    router = APIRouter()

    # -- Settings --------------------------------------------------------

    @router.get("/api/settings")
    def get_settings():
        with deps._settings_lock:
            deps.validate_and_fixup(deps.settings)
            response_payload = json.loads(json.dumps(deps.settings))
        response_payload["app_default_instructor_profile"] = deps.make_default_settings()["default_instructor_profile"]
        return JSONResponse(response_payload, headers=deps.NO_CACHE)

    @router.get("/api/instructor_defaults")
    def get_instructor_defaults():
        with deps._settings_lock:
            profile = deps._sanitize_instructor_default_profile(deps.settings.get("default_instructor_profile"))
            deps.settings["default_instructor_profile"] = dict(profile)
            deps.save_settings(deps.settings)
        return JSONResponse(deps._build_instructor_defaults_payload(profile), headers=deps.NO_CACHE)

    @router.post("/api/instructor_defaults")
    async def save_instructor_defaults(request: Request):
        try:
            body = await request.json()
            profile = deps._sanitize_instructor_default_profile((body or {}).get("profile"))
            with deps._settings_lock:
                deps.settings["default_instructor_profile"] = dict(profile)
                deps.validate_and_fixup(deps.settings)
                deps.save_settings(deps.settings)
            return JSONResponse(deps._build_instructor_defaults_payload(profile), headers=deps.NO_CACHE)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": f"Could not save default instructor profile: {exc}"},
                status_code=500,
                headers=deps.NO_CACHE,
            )

    @router.post("/api/settings/default_instructor_profile")
    async def save_default_instructor_profile(request: Request):
        return await save_instructor_defaults(request)

    @router.post("/api/settings/use_db_instructors")
    async def save_use_db_instructors(request: Request):
        """Toggle whether the solver reads instructors from the app database."""
        deps._require_json(request)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)
        enabled = bool((body or {}).get("enabled"))

        instructor_count = deps.repository.count_instructors()
        if enabled and instructor_count == 0:
            return JSONResponse(
                {"ok": False, "error": "The database has no instructors yet — import a CSV first."},
                status_code=400, headers=deps.NO_CACHE,
            )

        with deps._settings_lock:
            deps.settings["use_db_instructors"] = enabled
            deps.validate_and_fixup(deps.settings)
            deps.save_settings(deps.settings)
        return JSONResponse(
            {"ok": True, "use_db_instructors": enabled, "instructor_count": instructor_count},
            headers=deps.NO_CACHE,
        )

    @router.post("/api/settings/deselected_session_ids")
    async def save_deselected_session_ids(request: Request):
        """Persist which historical sessions the user has deselected.

        Stored as *deselected* ids so sessions imported later default to selected
        (history grows by default). Body: {"ids": [1, 2, ...]}.
        """
        deps._require_json(request)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)
        raw_ids = (body or {}).get("ids")
        if not isinstance(raw_ids, list):
            return JSONResponse({"ok": False, "error": "'ids' must be a list"}, status_code=400, headers=deps.NO_CACHE)
        ids = deps._sanitize_session_id_list(raw_ids)

        with deps._settings_lock:
            deps.settings["deselected_session_ids"] = ids
            deps.validate_and_fixup(deps.settings)
            deps.save_settings(deps.settings)
        return JSONResponse({"ok": True, "deselected_session_ids": ids}, headers=deps.NO_CACHE)

    # -- File picker -----------------------------------------------------

    @router.post("/api/pick_file")
    async def pick_file(request: Request):
        body = await request.json()
        purpose = body.get("purpose", "")
        with deps._settings_lock:
            if not purpose or purpose not in deps.settings["last_selected_files"]:
                return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=deps.NO_CACHE)
        selected_path = body.get("selected_path")
        if selected_path is not None:
            if not isinstance(selected_path, str) or not selected_path or len(selected_path) > 32767:
                return JSONResponse(
                    {"ok": False, "error": "Invalid selected file"}, status_code=400, headers=deps.NO_CACHE
                )
            candidate = Path(selected_path)
            allowed_extensions = (
                {".csv", ".xlsx", ".xlsm"}
                if purpose in {"classes", "swimmers", "instructors"}
                else {".csv"}
            )
            if (
                not candidate.is_absolute()
                or candidate.suffix.lower() not in allowed_extensions
                or not candidate.is_file()
            ):
                return JSONResponse(
                    {"ok": False, "error": "Invalid selected file"}, status_code=400, headers=deps.NO_CACHE
                )
            picked = str(candidate.resolve())
        else:
            picked = deps.pick_csv_file_win32()
        if not picked:
            return JSONResponse({"ok": False, "cancelled": True}, headers=deps.NO_CACHE)
        with deps._settings_lock:
            deps.settings["last_selected_files"][purpose] = picked
            deps.validate_and_fixup(deps.settings)
            deps.save_settings(deps.settings)
        return JSONResponse({"ok": True}, headers=deps.NO_CACHE)

    @router.post("/api/reset_file")
    async def reset_file(request: Request):
        body = await request.json()
        purpose = body.get("purpose", "")
        with deps._settings_lock:
            if not purpose or purpose not in deps.settings["last_selected_files"]:
                return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=deps.NO_CACHE)
            deps.settings["last_selected_files"][purpose] = deps.settings["default_files"][purpose]
            deps.validate_and_fixup(deps.settings)
            deps.save_settings(deps.settings)
        return JSONResponse({"ok": True}, headers=deps.NO_CACHE)

    @router.post("/api/clear_file")
    async def clear_file(request: Request):
        body = await request.json()
        purpose = body.get("purpose", "")
        with deps._settings_lock:
            if not purpose or purpose not in deps.settings["last_selected_files"]:
                return JSONResponse({"ok": False, "error": "Invalid purpose"}, status_code=400, headers=deps.NO_CACHE)
            deps.settings["last_selected_files"][purpose] = ""
            deps.validate_and_fixup(deps.settings)
            deps.save_settings(deps.settings)
        return JSONResponse({"ok": True}, headers=deps.NO_CACHE)

    return router
