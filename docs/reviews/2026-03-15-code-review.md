# Aqua Essence — Known Issues & Problems

> **Historical snapshot (2026-03-15):** This review intentionally describes
> the former C++ host and dual-server architecture. Those components have since
> been replaced by the single FastAPI application in `backend/`. The findings
> below are retained as engineering history, not current run instructions.

**Date:** 2026-03-15
**Branch:** `feature/xai-dashboard`

---

## 1. XSS via `innerHTML` with unsanitized user data

**Problem:** Swimmer names, instructor names, reason text, and flag reasons from CSV data are injected into the DOM via `innerHTML` without escaping in `dashboard.js` (6+ locations) and `app.js`. A malicious CSV entry like `<script>alert('xss')</script>` would execute in the coordinator's browser.

**Why:** The code uses template literals with `innerHTML` for convenience, never sanitizing the interpolated values.

**Fix:** Create an `escapeHtml()` helper that replaces `&`, `<`, `>`, `"`, `'` with HTML entities. Apply it to every user-derived string before `innerHTML`. Alternatively, use `textContent` with `document.createElement` for table cells.

---

## 2. Unvalidated JSON bodies in POST routes

**Problem:** The `/api/what-if/swap`, `/api/what-if/relax`, and `/api/what-if/tune` routes in `app.py` access `data["swimmer_id"]` directly after `request.get_json()`. If the request body is malformed, missing keys, or invalid JSON, Flask returns an unhandled 500 error with a traceback visible to the client.

**Why:** No input validation was added — the routes assume well-formed requests.

**Fix:** Check `data is not None`, verify required keys exist, and return a `400 Bad Request` with a descriptive error message for missing/invalid fields.

---

## 3. CORS wide open on XAI Dashboard

**Problem:** `CORS(app)` in `app.py` allows any origin to make requests to the Flask API, including the what-if POST endpoints. Any browser tab or script on the local network can hit the API.

**Why:** `flask-cors` was added for development convenience and never locked down.

**Fix:** Either restrict to `CORS(app, origins=["http://localhost:5050"])` or remove CORS entirely since the dashboard frontend is served from the same Flask origin.

---

## 4. Flask `debug=True` when running `app.py` directly

**Problem:** `__main__.py` correctly sets `debug=False`, but `app.py`'s own `if __name__ == "__main__"` block sets `debug=True`. The Flask debug mode enables an interactive debugger that is a known remote code execution vector if the server is network-accessible.

**Why:** `debug=True` was left from development and the two entry points were never synchronized.

**Fix:** Set `debug=False` in `app.py`'s `__main__` block, or remove it entirely since `__main__.py` is the intended entry point.

---

## 5. Path traversal risk in DataManager

**Problem:** `data_manager.py` reads a `profiles` path from `result.json` and joins it to `job_dir` without validating the result stays within that directory. A tampered `result.json` with `"profiles": "../../../../etc/passwd"` would read arbitrary files.

**Why:** The code trusts `result.json` contents without boundary checking.

**Fix:** After resolving the path, verify it's a child of `job_dir`:
```python
profiles_path = (self.job_dir / profiles_rel).resolve()
if not str(profiles_path).startswith(str(self.job_dir.resolve())):
    profiles_path = self.job_dir / "profiles.json"
```

---

## 6. No caching on `/api/match/<idx>/alternatives`

**Problem:** Every time a user clicks a match row, the endpoint iterates over all instructors and runs the scoring function for each one. With 50+ instructors this is tolerable, but the computation repeats on every click even though the data hasn't changed.

**Why:** The endpoint was built for correctness first, caching was deferred.

**Fix:** Cache alternatives results in a dict keyed by match index. Invalidate on `/api/reload`.

---

## 7. Overview re-fetches data on every tab switch

**Problem:** `loadOverview()` in `dashboard.js` makes two API calls (`/api/overview` and `/api/matches`) every time the user clicks the Overview tab. The data doesn't change between tab switches.

**Why:** No client-side caching — each tab activation triggers a fresh fetch.

**Fix:** Store fetched data in the `state` object. Only re-fetch when the user clicks "Reload Data". Load `/api/matches` lazily when the Explorer tab is first opened instead of bundling it with overview.

---

## 8. No loading or error states in the dashboard frontend

**Problem:** All API errors are caught with `console.error` but no visual feedback is shown to the user. If the Flask server is down or data is corrupted, the dashboard shows stale or empty data with no explanation.

**Why:** Error UI was not part of the initial implementation pass.

**Fix:** Add a toast notification or error banner that appears when any API call fails, showing a user-friendly message like "Failed to load data — is the server running?"

---

## 9. Private methods called from Flask routes

**Problem:** `app.py` calls `engine._score_swimmer_instructor()` and `engine._check_constraints()` — both prefixed with `_`, indicating they're internal to `WhatIfEngine`.

**Why:** The routes needed scoring logic that only existed as private helpers.

**Fix:** Either rename them to drop the underscore (making them part of the public API), or add public wrapper methods like `engine.score_pair(swimmer_id, instructor_id)` and `engine.check_constraints(swimmer_id, instructor_id)`.

---

## 10. Confidence scale inconsistency (0-1 vs 0-100)

**Problem:** The C++ solver outputs confidence on a 0-1 scale, the Python solver outputs 0-100. Normalization guards (`if conf <= 1: conf *= 100`) are scattered across 4+ files in both Python and JS. The logic is duplicated and the edge case of `conf == 1.0` (is it 1% or 100%?) creates ambiguity.

**Why:** Two solvers were built independently with different output conventions.

**Fix:** Standardize to 0-100 at the source — have the C++ solver multiply by 100 before writing `result.json`. Then delete all normalization code everywhere.

---

## 11. C++ backend doing Python's job (1,484 lines)

**Problem:** `AquaEssenceHost.cpp` is 1,484 lines hand-rolling JSON parsing (doesn't handle escapes properly), Windows-only process spawning with `CreateProcessW`, native file dialogs, and static file serving. This is work that ~200 lines of Python/Flask could do, with cross-platform support for free.

**Why:** The backend was originally built in C++ as a learning exercise and to match the C++ solver. But the primary solver is Python, and the dashboard is already Flask.

**Fix:** Replace the C++ backend with a Python Flask server. The solver is already Python, the dashboard is already Flask — merging them into one server eliminates subprocess management, CORS headaches, and the dual-port architecture.

---

## 12. Two separate web servers (dual-port architecture)

**Problem:** The main app runs on C++ (port 8787) and the XAI Dashboard runs on Flask (port 5050). This requires subprocess management to launch the dashboard, CORS configuration between the two, and users seeing two different ports.

**Why:** The dashboard was added as a separate service rather than integrated into the existing backend.

**Fix:** If the C++ backend is replaced with Python (see #11), merge the dashboard as a Flask Blueprint on the same server. One port, no subprocess launching, no CORS needed.

---

## 13. Fragile `.bat` subprocess chain

**Problem:** The solver launch path is: C++ -> `cmd.exe` -> `solver.bat` -> `py.exe` -> `solver_wrapper.py` — 4 hops, each with different environment behavior (PATH, PYTHONPATH, user site-packages). This has caused multiple bugs where packages installed for the user aren't visible to the subprocess.

**Why:** The C++ backend can't run Python directly, so it shells out through batch files. Each hop inherits a slightly different environment.

**Fix:** If the backend becomes Python, import the solver module directly — zero hops, zero environment issues.

---

## 14. Vanilla JS duplication across two frontends

**Problem:** `normalizeConfidence()`, `personName()`, and profile rendering logic are all duplicated between `frontend/app.js` (main app) and `frontend/xai_dashboard/static/dashboard.js` (dashboard). Changes to one must be manually mirrored in the other.

**Why:** The two frontends were built independently without shared utilities.

**Fix:** Extract a shared `frontend/shared/utils.js` with common functions, imported by both `app.js` and `dashboard.js` via `<script>` tags.

---

## 15. Solver path resolution walks directory levels

**Problem:** `solver_wrapper.py` determines `app_root` by walking 3 `dirname()` levels up from the `request.json` path. If the directory structure changes, this silently resolves to the wrong location.

**Why:** The solver receives a `request.json` path but no explicit workspace root.

**Fix:** Include `app_root` or `workspace_root` as a field in `request.json` so the solver doesn't need to guess.

---

## 16. Missing test coverage

**Problem:** Several routes and edge cases lack automated tests:
- No test for `/api/reload`
- No test for `/api/what-if/relax`
- `normalizeConfidence` edge cases untested
- Unknown `match_type` values silently create new dict keys in `get_type_breakdown`

**Why:** Tests were written for the happy path; edge cases and some routes were skipped.

**Fix:** Add tests for the missing routes. Add a test for unknown `match_type` values to verify they're either rejected or counted under "other". Add confidence normalization edge case tests (0, 1, 1.0, 50, 0.5).

---

## 17. Port 5050 hardcoded in 4 locations

**Problem:** The dashboard port is hardcoded as `5050` in `__main__.py`, `app.py`, and `AquaEssenceHost.cpp` (2 locations). Changing it requires editing all four files.

**Why:** No centralized config for the dashboard port.

**Fix:** Define the port in one place — either an environment variable (`XAI_DASHBOARD_PORT`) or a config file — and read it from all locations.
