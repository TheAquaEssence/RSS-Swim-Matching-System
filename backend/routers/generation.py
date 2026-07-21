"""Thin HTTP adapter for the generation application service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.services.generation_service import GenerationService


@dataclass(frozen=True)
class GenerationRouterDependencies:
    no_cache_headers: dict[str, str]
    settings_lock: Lock
    get_settings: Callable[[], dict]
    validate_settings: Callable[[dict], None]
    save_settings: Callable[[dict], None]
    try_begin: Callable[[], tuple[bool, int]]
    finish: Callable[[], None]
    create_service: Callable[[], GenerationService]


def create_generation_router(deps: GenerationRouterDependencies) -> APIRouter:
    router = APIRouter()

    @router.post("/api/generate")
    async def generate(request: Request):
        with deps.settings_lock:
            active_settings = deps.get_settings()
            deps.validate_settings(active_settings)
            deps.save_settings(active_settings)
            snapshot = json.loads(json.dumps(active_settings))

        selected_session_ids: list[int] | None = None
        try:
            body = await request.json()
            if isinstance(body, dict) and "selected_session_ids" in body:
                raw_ids = body["selected_session_ids"]
                if isinstance(raw_ids, list):
                    selected_session_ids = [
                        int(value)
                        for value in raw_ids
                        if str(value).strip().lstrip("-").isdigit()
                    ]
        except Exception:
            pass

        if not snapshot["last_selected_files"].get("classes"):
            return JSONResponse(
                {"ok": False, "error": "classes.csv is required"},
                status_code=400,
                headers=deps.no_cache_headers,
            )

        can_generate, retry_after = deps.try_begin()
        if not can_generate:
            return JSONResponse(
                {"ok": False, "error": "Generate is rate-limited. Please wait and try again."},
                status_code=429,
                headers={**deps.no_cache_headers, "Retry-After": str(retry_after)},
            )

        try:
            result = deps.create_service().generate(
                snapshot,
                selected_session_ids=selected_session_ids,
                request_id=getattr(request.state, "request_id", None),
            )
            if result.job_id:
                request.state.job_id = result.job_id
            return JSONResponse(
                result.payload,
                status_code=result.status_code,
                headers=deps.no_cache_headers,
            )
        finally:
            deps.finish()

    return router
