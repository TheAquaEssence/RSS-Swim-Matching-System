# System-Wide Persistent Logging v1

> **Historical implementation plan (2026-03-20):** References to `backend2/`,
> the C++ host, and legacy solvers reflect the repository when this plan was
> written. Current Python components use `core/aqua_logging.py`, and the active
> FastAPI backend lives in `backend/`.

## Summary

Implement a single persistent logging design across the active runtime: FastAPI host, C++ host, XAI dashboard, Python solver wrappers, and `core.profiles.generate_profiles`. The goal is post-mortem debugging without changing the REST contract: every request, subprocess failure, uncaught Python exception, and important lifecycle event should leave a durable, correlated log record on disk.

## Key Changes

- Add a shared logging policy with component-specific JSONL files under `workspace/logs/`.
  - Layout: `logs/<component>/<YYYY-MM-DD>.jsonl`
  - Rotation: roll the active file when it exceeds 10 MB
  - Retention: delete rotated or daily files older than 14 days
  - Add `logs/` as a directory entry to `.gitignore` — the existing `*.log` rule does not cover `.jsonl` files
- Standardize one event schema across Python and C++ logs.
  - Required fields: `ts_utc`, `level`, `component`, `event`, `message`, `pid`
  - Common optional fields: `request_id`, `job_id`, `solver_id`, `route`, `method`, `status_code`, `duration_ms`, `exception_type`, `exception`, `stacktrace`, `subprocess_output_tail`
- Introduce request and job correlation rules.
  - Generate a `request_id` for every HTTP request in FastAPI, Flask, and the C++ host
  - Reuse existing `job_id` for `/api/generate` flows
  - `backend2/server.py` writes `job_id` into `request.json` before invoking the solver, so wrappers and `generate_profiles` can read it directly from that file without parsing directory names
  - XAI dashboard derives `job_id` from `XAI_JOB_DIR` when present
- Python implementation approach: use stdlib `logging` only.
  - Create one shared Python logging helper in `core/` for JSONL formatting, file handler setup, retention cleanup, and contextual logger adapters
  - Enable uncaught Python exception capture via `sys.excepthook` and `threading.excepthook`
  - Keep concise console output, but treat file logs as the source of truth for debugging
- C++ host implementation approach: add a small native logger helper, not a new dependency.
  - Mutex-protected JSONL writer with the same field names as Python
  - Log request start and end, `/api/generate`, solver launch and timeout and failure, dashboard launch and failure, startup and shutdown, and fatal top-level exceptions
  - Use `cpp-httplib` request and error logger hooks where possible; add explicit structured events inside important handlers where request context or job context is needed
- Component-specific behavior:
  - `backend2/server.py`: request middleware, solver subprocess lifecycle logging, validation failures, profile-generation failures, startup and shutdown events, generate guard rejections (rate-limit hits with cooldown remaining)
  - `frontend/xai_dashboard/app.py` and `__main__.py`: Flask request and response logging, `DataManager` reload failures, what-if endpoint failures, startup context
  - Python solver wrappers: log start, resolved input paths, phase timing summary, output write success, and fatal exceptions
  - `core.profiles.generate_profiles`: log invocation, missing input files, and write success or failure
- Keep public behavior stable in v1.
  - No REST response shape changes
  - No `result.json` contract changes in this pass
  - Detailed failures move into persistent logs, but existing solver and job artifacts stay compatible
  - Solver stderr and internal paths are written to the log file only, not returned to the client — this closes M9 (error response leakage)

## Interfaces / Config

- No public API changes.
- Add two optional env vars for all Python processes and the C++ host:
  - `AQUA_LOG_DIR` default: `workspace/logs`
  - `AQUA_LOG_LEVEL` default: `INFO`
- Define one internal event schema shared by Python and C++ so log consumers do not need per-component parsing rules.

## Test Plan

- Unit tests for the Python logging helper:
  - JSONL record includes required fields
  - rotation occurs at 10 MB
  - retention cleanup removes files older than 14 days
- Backend tests:
  - FastAPI request log contains `request_id`
  - `/api/generate` emits correlated `request_id` and `job_id` entries on success and failure
  - profile-generation warning paths persist logs
- XAI dashboard tests:
  - request logging works for success and error responses
  - uncaught endpoint exceptions produce structured file entries
- Solver wrapper tests:
  - fatal wrapper exception writes a structured error log and keeps current `result.json` failure behavior
  - successful run writes start and end events with `job_id`
- C++ host checks:
  - source-level tests assert logger hookup and generate-path events
  - Release build must pass
  - one manual smoke run should confirm the host writes JSONL entries during startup and `/api/generate`

## Assumptions / Defaults

- Scope for v1 is the active runtime only; `solvers/cpp_exact` and legacy `solvers/greedy/*` are deferred.
- Persistent sink is repo-local `workspace/logs/`.
- File format is JSONL on disk plus concise console output.
- Retention is 14 days with 10 MB rotation.
- v1 includes persistent logs and uncaught Python tracebacks, but not Windows minidumps for the C++ host.
- No third-party logging dependency should be added; use stdlib Python logging and a small native C++ helper.
