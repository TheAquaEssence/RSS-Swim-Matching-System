
"""Session and historical-pairing routes with explicit dependencies."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

if TYPE_CHECKING:
    from backend.services.repository import SqliteRepository


@dataclass(frozen=True)
class SessionsDependencies:
    NO_CACHE: dict[str, str]
    get_last_job_dir: Callable[[], str | Path | None]
    generate_historical_pairings: Callable[..., tuple[str, list[str]]]
    repository: "SqliteRepository"
    _operator_name: Callable[[Any], str | None]

    @property
    def _last_job_dir(self) -> str | Path | None:
        return self.get_last_job_dir()


def create_sessions_router(deps: SessionsDependencies) -> APIRouter:
    """Return the sessions/pairings router."""
    router = APIRouter()

    # -- Historical pairings generator ------------------------------------

    @router.post("/api/generate_historical_pairings")
    async def api_generate_historical_pairings(request: Request):
        body = await request.json()
        session_name = body.get("session", "").strip()
        if not session_name:
            return JSONResponse({"error": "session field is required"}, status_code=400, headers=deps.NO_CACHE)

        if deps._last_job_dir is None:
            return JSONResponse(
                {"error": "No completed job found. Run the solver first."},
                status_code=503,
                headers=deps.NO_CACHE,
            )

        classes_filled_path = Path(deps._last_job_dir) / "classes_filled.csv"
        if not classes_filled_path.exists():
            return JSONResponse(
                {"error": "classes_filled.csv not found in last job directory."},
                status_code=404,
                headers=deps.NO_CACHE,
            )

        try:
            csv_text = classes_filled_path.read_text(encoding="utf-8")
            result_csv, warnings = deps.generate_historical_pairings(csv_text, session=session_name)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        headers = dict(deps.NO_CACHE)
        headers["Content-Disposition"] = f'attachment; filename="historical_pairings_{session_name}.csv"'
        if warnings:
            headers["X-Import-Warnings"] = "; ".join(warnings)
        return Response(content=result_csv, media_type="text/csv", headers=headers)

    # -- Historical pairings DB --------------------------------------------

    @router.get("/api/historical_pairings")
    def api_get_historical_pairings():
        """Return accumulated historical pairings as a CSV attachment."""
        csv_text = deps.repository.load_historical_pairings_csv()
        hdrs = dict(deps.NO_CACHE)
        hdrs["Content-Disposition"] = 'attachment; filename="historical_pairings.csv"'
        return Response(content=csv_text, media_type="text/csv", headers=hdrs)

    @router.get("/api/sessions")
    def api_list_sessions():
        """List all recorded sessions with pairing counts, newest first."""
        return JSONResponse({"ok": True, "sessions": deps.repository.list_sessions_with_counts()}, headers=deps.NO_CACHE)

    @router.patch("/api/sessions/{session_id}")
    async def api_rename_session(session_id: int, request: Request):
        """Rename a session. Body: {"label": "New name"}."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400, headers=deps.NO_CACHE)
        label = str(body.get("label", "")).strip() if isinstance(body, dict) else ""
        if not label:
            return JSONResponse({"ok": False, "error": "Missing label"}, status_code=400, headers=deps.NO_CACHE)
        try:
            updated = deps.repository.rename_session(session_id, label)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=409, headers=deps.NO_CACHE)
        if updated is None:
            return JSONResponse({"ok": False, "error": "Session not found"}, status_code=404, headers=deps.NO_CACHE)
        return JSONResponse({"ok": True, "session": updated}, headers=deps.NO_CACHE)

    @router.delete("/api/sessions/{session_id}")
    def api_delete_session(session_id: int):
        """Delete a session and its pairings."""
        if not deps.repository.delete_session(session_id):
            return JSONResponse({"ok": False, "error": "Session not found"}, status_code=404, headers=deps.NO_CACHE)
        return JSONResponse({"ok": True}, headers=deps.NO_CACHE)

    @router.post("/api/import_jackrabbit_pairings")
    async def api_import_jackrabbit_pairings(request: Request):
        """Accept a historical_pairings CSV (or Jackrabbit export) and persist to DB."""

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            uploaded = form.get("file")
            if uploaded is None:
                return JSONResponse({"ok": False, "error": "No file field in form"}, status_code=400, headers=deps.NO_CACHE)
            csv_text = (await uploaded.read()).decode("utf-8", errors="replace")
            label = str(form.get("label", "jackrabbit_import")).strip() or "jackrabbit_import"
            operator = deps._operator_name(form.get("operator"))
        else:
            body = await request.body()
            try:
                data = json.loads(body)
                csv_text = data.get("csv", "")
                label = str(data.get("label", "jackrabbit_import")).strip() or "jackrabbit_import"
                operator = deps._operator_name(data.get("operator"))
            except Exception:
                return JSONResponse({"ok": False, "error": "Expected multipart/form-data or JSON with 'csv' field"}, status_code=400, headers=deps.NO_CACHE)

        if not csv_text.strip():
            return JSONResponse({"ok": False, "error": "Empty CSV"}, status_code=400, headers=deps.NO_CACHE)

        try:
            result = deps.repository.import_jackrabbit_pairings_csv(csv_text, imported_by=operator)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400, headers=deps.NO_CACHE)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500, headers=deps.NO_CACHE)

        return JSONResponse({"ok": True, **result}, headers=deps.NO_CACHE)

    return router
