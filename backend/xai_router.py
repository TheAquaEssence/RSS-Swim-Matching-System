"""XAI Dashboard routes — FastAPI APIRouter.

Replaces frontend/xai_dashboard/app.py (Flask) as the server for the
explainability dashboard.  All routes live under the /xai prefix.

DataManager and WhatIfEngine are imported unchanged from the existing
frontend package — no logic is duplicated here.

Design note: create_xai_router accepts a *get_job_dir* callable rather
than a static path so the router always serves data from the most-recent
completed solver job without needing an explicit reload call.
"""
import traceback
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from frontend.xai_dashboard.data_manager import DataManager
from frontend.xai_dashboard.what_if import WhatIfEngine

_XAI_DIR = Path(__file__).resolve().parent.parent / "frontend" / "xai_dashboard"
_TEMPLATES_DIR = _XAI_DIR / "templates"
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _require_json(content_type: Optional[str]) -> Optional[JSONResponse]:
    """Return a 415 JSONResponse if Content-Type is not application/json.

    Mirrors the @require_json decorator used in the Flask version (H5 fix).
    Browsers cannot set Content-Type: application/json cross-origin without a
    CORS pre-flight, so this acts as a lightweight CSRF mitigation.
    """
    if not content_type or "application/json" not in content_type:
        return JSONResponse(
            {"ok": False, "error": "Content-Type must be application/json"},
            status_code=415,
        )
    return None


def create_xai_router(
    get_job_dir: Callable[[], str],
    source_dir: str = "data/source",
) -> APIRouter:
    """Return a configured APIRouter for the XAI dashboard.

    Args:
        get_job_dir: Zero-argument callable that returns the path to the
                     current solver job directory.  Called on every request
                     so the router always reflects the latest completed job.
        source_dir:  Path to the source data directory (passed to WhatIfEngine).
    """
    router = APIRouter(prefix="/xai")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # ------------------------------------------------------------------
    # Helpers — instantiate DataManager / WhatIfEngine per-request so
    # the view is always up-to-date after a new solve.
    # ------------------------------------------------------------------

    def _dm() -> DataManager:
        return DataManager(get_job_dir())

    def _engine(dm: DataManager) -> WhatIfEngine:
        return WhatIfEngine(dm, source_dir=source_dir)

    # ------------------------------------------------------------------
    # Dashboard HTML
    # ------------------------------------------------------------------

    @router.get("/", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        dm = _dm()
        response = templates.TemplateResponse(
            request,
            "index.html",
            {
                "summary": dm.summary,
                "match_count": len(dm.matches),
            },
        )
        response.headers.update(_NO_CACHE_HEADERS)
        return response

    # ------------------------------------------------------------------
    # GET API routes
    # ------------------------------------------------------------------

    @router.get("/api/matches")
    def api_matches():
        dm = _dm()
        return JSONResponse(
            {"ok": True, "summary": dm.summary,
             "matches": dm.matches, "unassigned": dm.unassigned},
            headers=_NO_CACHE_HEADERS,
        )

    @router.get("/api/overview")
    def api_overview():
        dm = _dm()
        return JSONResponse(
            {
                "ok": True,
                "summary": dm.summary,
                "confidence_distribution": dm.get_confidence_distribution(),
                "type_breakdown": dm.get_type_breakdown(),
                "flagged": dm.get_flagged_matches_with_reasons(),
            },
            headers=_NO_CACHE_HEADERS,
        )

    @router.get("/api/match/{idx}")
    def api_match_detail(idx: int):
        dm = _dm()
        match = dm.get_match(idx)
        if not match:
            return JSONResponse({"ok": False, "error": "Match not found"}, status_code=404)

        swimmer_id = match.get("swimmer_id") or match.get("swimmer_1_id")
        instr_id = match["instructor_id"]
        swimmer = dm.get_swimmer(swimmer_id)
        instructor = dm.get_instructor(instr_id)

        breakdown = None
        if swimmer and instructor:
            breakdown = _engine(dm).score_swimmer_instructor(swimmer, instructor)

        return JSONResponse(
            {"ok": True, "match": match, "breakdown": breakdown,
             "swimmer": swimmer, "instructor": instructor},
            headers=_NO_CACHE_HEADERS,
        )

    @router.get("/api/match/{idx}/alternatives")
    def api_match_alternatives(idx: int):
        dm = _dm()
        match = dm.get_match(idx)
        if not match:
            return JSONResponse({"ok": False, "error": "Match not found"}, status_code=404)

        swimmer_id = match.get("swimmer_id") or match.get("swimmer_1_id")
        instr_id = match["instructor_id"]
        swimmer = dm.get_swimmer(swimmer_id)
        instructor = dm.get_instructor(instr_id)

        if not swimmer or not instructor:
            return JSONResponse({"ok": False, "error": "Profile data missing"}, status_code=404)

        engine = _engine(dm)
        current_breakdown = engine.score_swimmer_instructor(swimmer, instructor)
        current_breakdown["instructor_id"] = instr_id
        current_breakdown["instructor_name"] = instructor.get("name", "")

        alternatives = []
        for other in dm.all_instructors():
            other_id = other["instructor_id"]
            if other_id == instr_id:
                continue
            scores = engine.score_swimmer_instructor(swimmer, other)
            scores["instructor_id"] = other_id
            scores["instructor_name"] = other.get("name", "")
            blocked = engine.check_constraints(swimmer, other)
            scores["why_not"] = ", ".join(blocked) if blocked else "lower score or capacity"
            alternatives.append(scores)

        alternatives.sort(key=lambda x: x["score"], reverse=True)
        return JSONResponse(
            {"ok": True, "current": current_breakdown, "alternatives": alternatives[:5]},
            headers=_NO_CACHE_HEADERS,
        )

    # ------------------------------------------------------------------
    # POST API routes — all require Content-Type: application/json (H5)
    # ------------------------------------------------------------------

    @router.post("/api/what-if/swap")
    async def api_swap(request: Request):
        err = _require_json(request.headers.get("content-type"))
        if err:
            return err
        data = await request.json()
        if not data or "swimmer_id" not in data or "current_instructor_id" not in data:
            return JSONResponse(
                {"ok": False, "error": "Missing required fields: swimmer_id, current_instructor_id"},
                status_code=400,
            )
        try:
            result = _engine(_dm()).swap_explore(
                swimmer_id=data["swimmer_id"],
                current_instructor_id=data["current_instructor_id"],
            )
        except Exception:
            return JSONResponse({"ok": False, "error": "Swap exploration failed"}, status_code=500)
        return {"ok": True, **result}

    @router.post("/api/what-if/relax")
    async def api_relax(request: Request):
        err = _require_json(request.headers.get("content-type"))
        if err:
            return err
        data = await request.json()
        if not data or "swimmer_id" not in data or "constraint" not in data:
            return JSONResponse(
                {"ok": False, "error": "Missing required fields: swimmer_id, constraint"},
                status_code=400,
            )
        try:
            result = _engine(_dm()).relax_constraint(
                swimmer_id=data["swimmer_id"],
                constraint=data["constraint"],
            )
        except Exception:
            return JSONResponse({"ok": False, "error": "Constraint relaxation failed"}, status_code=500)
        return {"ok": True, **result}

    @router.post("/api/what-if/tune")
    async def api_tune(request: Request):
        err = _require_json(request.headers.get("content-type"))
        if err:
            return err
        data = await request.json()
        if data is None:
            return JSONResponse({"ok": False, "error": "Missing JSON body"}, status_code=400)
        try:
            results = _engine(_dm()).tune_weights(weights=data.get("weights", {}))
        except Exception:
            return JSONResponse({"ok": False, "error": "Weight tuning failed"}, status_code=500)
        return {"ok": True, "results": results}

    @router.post("/api/reload")
    async def api_reload(request: Request):
        """No-op in the per-request design — data is always fresh on next GET.

        Kept for API compatibility with existing dashboard.js callers.
        """
        err = _require_json(request.headers.get("content-type"))
        if err:
            return err
        return JSONResponse({"ok": True}, headers=_NO_CACHE_HEADERS)

    return router
