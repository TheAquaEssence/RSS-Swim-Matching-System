
"""Instructor routes with explicit database, settings, and import dependencies."""
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

if TYPE_CHECKING:
    from backend.services.repository import SqliteRepository


@dataclass(frozen=True)
class InstructorsDependencies:
    NO_CACHE: dict[str, str]
    APP_ROOT: Path
    _settings_lock: Any
    get_settings: Callable[[], dict]
    _load_reference_options: Callable[..., tuple[list[dict], Path | None]]
    xlsx_bytes_to_csv_text: Callable[[bytes], str]
    is_partner_instructors_csv: Callable[[str], bool]
    _sanitize_instructor_default_profile: Callable[[dict | None], dict]
    import_instructors: Callable[..., tuple[str, list[str]]]
    repository: "SqliteRepository"
    _require_json: Callable[[Request], None]
    _operator_name: Callable[[Any], str | None]
    resolve_from_root: Callable[[str], Path]

    @property
    def settings(self) -> dict:
        return self.get_settings()


def create_instructors_router(deps: InstructorsDependencies) -> APIRouter:
    """Return the instructors router."""
    router = APIRouter()

    def _instructor_reference_maps() -> dict:
        """
        Reference data for human-readable instructor CSVs:
          color_names / style_names — id → name (for export)
          color_lookup / style_lookup — lowercase name → (id, canonical name) (for import)
        Values are None when the reference tables can't be loaded.
        """
        maps = {"color_names": None, "style_names": None, "color_lookup": None, "style_lookup": None}
        for key, names_key, lookup_key, id_col, name_col in [
            ("personality_colors", "color_names", "color_lookup", "color_id", "color_name"),
            ("instructor_styles", "style_names", "style_lookup", "style_id", "style_name"),
        ]:
            try:
                options, _ = deps._load_reference_options(key, id_col, name_col)
                if options:
                    maps[names_key] = {int(o["id"]): str(o["name"]) for o in options}
                    maps[lookup_key] = {
                        str(o["name"]).strip().lower(): (int(o["id"]), str(o["name"]))
                        for o in options if str(o["name"]).strip()
                    }
            except Exception:
                pass
        return maps

    async def _read_instructors_csv_upload(request: Request) -> str:
        """Extract CSV text from a multipart upload ('file' field) or JSON body ('csv' field).

        Multipart uploads may be .csv text or an .xlsx/.xlsm workbook (detected by
        the zip magic bytes) — workbooks are converted to CSV text.
        """
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            uploaded = form.get("file")
            if uploaded is None:
                raise ValueError("No file field in form")
            raw = await uploaded.read()
            if raw[:4] == b"PK\x03\x04":  # zip container → Excel workbook
                try:
                    return deps.xlsx_bytes_to_csv_text(raw)
                except Exception:
                    raise ValueError("Could not read the Excel workbook — is it a valid .xlsx file?")
            return raw.decode("utf-8-sig", errors="replace")
        body = await request.body()
        try:
            data = json.loads(body)
        except Exception:
            raise ValueError("Expected multipart/form-data or JSON with 'csv' field")
        return str(data.get("csv", ""))

    def _convert_partner_instructors_if_needed(csv_text: str) -> tuple[str, list[str]]:
        """Auto-convert a partner ActiveStaff export to the internal format."""
        if deps.is_partner_instructors_csv(csv_text):
            with deps._settings_lock:
                profile = deps._sanitize_instructor_default_profile(deps.settings.get("default_instructor_profile"))
            return deps.import_instructors(csv_text, default_profile=profile)
        return csv_text, []

    @router.get("/api/instructors")
    def api_list_instructors(needs_update: bool = False):
        """
        List all instructors from the DB.
        ?needs_update=true filters to only those missing profile data (profile_source != 0).
        """
        return JSONResponse({"ok": True, "instructors": deps.repository.list_instructors(needs_update_only=needs_update)}, headers=deps.NO_CACHE)

    @router.get("/api/instructors/export")
    def api_export_instructors(needs_update: bool = False, q: str = ""):
        """
        Download instructors as a CSV in the solver-compatible format.
        ?needs_update=true and ?q=<name substring> mirror the Manage Instructors
        filters so the export matches what's on screen.
        Content is UTF-8 with BOM so Excel renders accented names correctly.
        """
        refs = _instructor_reference_maps()
        csv_text = deps.repository.export_instructors_csv(
            needs_update_only=needs_update,
            name_query=q,
            color_names=refs["color_names"],
            style_names=refs["style_names"],
        )
        filename = f"instructors_{time.strftime('%Y-%m-%d')}.csv"
        return Response(
            content="﻿" + csv_text,
            media_type="text/csv; charset=utf-8",
            headers={**deps.NO_CACHE, "Content-Disposition": f"attachment; filename={filename}"},
        )

    @router.get("/api/instructors/stats")
    def api_instructor_stats():
        """
        Staffing overview from the instructors DB: total/complete profile counts,
        capability counts, and primary/secondary distribution per personality
        color and style (with names resolved from the reference tables).
        """
        stats = deps.repository.instructor_stats()
        refs = _instructor_reference_maps()
        for key, names in (("colors", refs["color_names"]), ("styles", refs["style_names"])):
            for entry in stats[key]:
                if entry["id"] is None:
                    entry["name"] = None
                else:
                    entry["name"] = (names or {}).get(entry["id"], str(entry["id"]))
        return JSONResponse({"ok": True, **stats}, headers=deps.NO_CACHE)

    @router.get("/api/instructors/{instructor_id}")
    def api_get_instructor(instructor_id: str):
        """Get a single instructor by Jackrabbit Staff ID."""
        instructor = deps.repository.get_instructor(instructor_id)
        if instructor is None:
            return JSONResponse({"ok": False, "error": "Not found"}, status_code=404, headers=deps.NO_CACHE)
        return JSONResponse({"ok": True, "instructor": instructor}, headers=deps.NO_CACHE)

    @router.patch("/api/instructors/{instructor_id}")
    async def api_update_instructor(instructor_id: str, request: Request):
        """
        Update editable fields on an instructor.
        Accepts JSON body with any subset of editable fields:
          first_name, last_name,
          primary_color_id, secondary_color_id, primary_style_id, secondary_style_id,
          is_team_captain, can_teach_babies, can_teach_adults, can_teach_adapted
        profile_source and used_default_profile are recalculated automatically.
        """
        deps._require_json(request)
        try:
            fields = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)
        if not isinstance(fields, dict):
            return JSONResponse({"ok": False, "error": "Body must be a JSON object"}, status_code=400, headers=deps.NO_CACHE)

        # 'operator' is attribution metadata, not an editable field
        operator = deps._operator_name(fields.pop("operator", None))
        fields.pop("updated_by", None)
        updated = deps.repository.update_instructor(instructor_id, fields, updated_by=operator)
        if updated is None:
            return JSONResponse({"ok": False, "error": "Instructor not found"}, status_code=404, headers=deps.NO_CACHE)
        return JSONResponse({"ok": True, "instructor": updated}, headers=deps.NO_CACHE)

    @router.post("/api/instructors/import/preview")
    async def api_preview_instructors_import(request: Request):
        """
        Dry-run an instructors CSV import against the DB.
        Accepts multipart/form-data ('file') or JSON {"csv": "..."}.
        Partner ActiveStaff exports are auto-converted to the internal format.
        Returns a field-level diff plus the normalized CSV text to send back to
        /api/instructors/import/apply. Nothing is written to the DB.
        """

        try:
            csv_text = await _read_instructors_csv_upload(request)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        if not csv_text.strip():
            return JSONResponse({"ok": False, "error": "Empty CSV"}, status_code=400, headers=deps.NO_CACHE)

        try:
            csv_text, convert_warnings = _convert_partner_instructors_if_needed(csv_text)
            refs = _instructor_reference_maps()
            preview = deps.repository.preview_instructors_import(
                csv_text,
                color_lookup=refs["color_lookup"],
                style_lookup=refs["style_lookup"],
            )
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        preview["warnings"] = convert_warnings + preview.get("warnings", [])
        return JSONResponse({"ok": True, "csv": csv_text, **preview}, headers=deps.NO_CACHE)

    @router.post("/api/instructors/import/apply")
    async def api_apply_instructors_import(request: Request):
        """
        Apply a previously previewed instructors import.
        Accepts JSON {"csv": "...", "accepted_ids": [...]} where each entry is
        either an instructor_id string (take the full CSV row) or
        {"instructor_id": "...", "fields": ["last_name", ...]} (take only those
        fields, keeping the rest of the DB row). Everything else is untouched.
        """
        deps._require_json(request)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)

        csv_text = str((body or {}).get("csv", ""))
        accepted_ids = (body or {}).get("accepted_ids")
        if not csv_text.strip():
            return JSONResponse({"ok": False, "error": "'csv' is required"}, status_code=400, headers=deps.NO_CACHE)
        if not isinstance(accepted_ids, list) or not accepted_ids:
            return JSONResponse({"ok": False, "error": "'accepted_ids' must be a non-empty list"}, status_code=400, headers=deps.NO_CACHE)

        try:
            refs = _instructor_reference_maps()
            result = deps.repository.apply_instructors_import(
                csv_text,
                accepted_ids,
                color_lookup=refs["color_lookup"],
                style_lookup=refs["style_lookup"],
                imported_by=deps._operator_name((body or {}).get("operator")),
            )
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        return JSONResponse({"ok": True, **result}, headers=deps.NO_CACHE)

    @router.get("/api/instructors/import/last")
    def api_last_instructor_import():
        """Return the most recent undoable instructor import, or null."""
        return JSONResponse({"ok": True, "last_import": deps.repository.last_instructor_import()}, headers=deps.NO_CACHE)

    @router.post("/api/instructors/import/undo")
    async def api_undo_instructors_import(request: Request):
        """
        Revert an instructor import (default: the most recent one).
        Accepts JSON {} or {"history_id": n}. Created rows are deleted, changed
        rows restored to their pre-import state. One-shot — consumes the history entry.
        """
        deps._require_json(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        history_id = (body or {}).get("history_id")

        try:
            result = deps.repository.undo_instructors_import(history_id)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        return JSONResponse({"ok": True, **result}, headers=deps.NO_CACHE)

    @router.post("/api/instructors/import")
    async def api_import_instructors(request: Request):
        """
        Import (or re-import) instructors from the enriched CSV.
        Accepts JSON: {"path": "data/source/instructors.csv"}
        Uses UPSERT — safe to call multiple times; source=0 rows in the DB are
        overwritten only if the CSV also has them at source=0.
        """
        deps._require_json(request)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)

        raw_path = body.get("path", "")
        if not raw_path:
            return JSONResponse({"ok": False, "error": "'path' is required"}, status_code=400, headers=deps.NO_CACHE)

        csv_path = deps.resolve_from_root(raw_path)
        if not csv_path.is_relative_to(deps.APP_ROOT):
            return JSONResponse({"ok": False, "error": "Path outside workspace"}, status_code=400, headers=deps.NO_CACHE)
        if not csv_path.exists():
            return JSONResponse({"ok": False, "error": f"File not found: {raw_path}"}, status_code=404, headers=deps.NO_CACHE)

        try:
            count = deps.repository.import_instructors_csv(csv_path)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        return JSONResponse({"ok": True, "imported": count}, headers=deps.NO_CACHE)

    return router
