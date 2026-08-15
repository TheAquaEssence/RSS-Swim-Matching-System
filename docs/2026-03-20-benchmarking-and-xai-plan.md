# Plan: Benchmarking Tool + XAI Dashboard Improvements

> **Historical implementation plan (2026-03-20):** File paths and solver lists
> below preserve the repository state used by this plan. The current app uses
> `backend/` and only the Python CP-SAT solver; `backend2/`, C++ solvers, and
> graph/greedy solver variants no longer exist. See `docs/RUN_APP.md` for
> current launch instructions.

**Date:** 2026-03-20
**Branch:** `main`

Two independent workstreams to be worked on iteratively. Each phase is independently valuable.

---

## PLAN A: Benchmarking Tool — Solver Comparison

### Context

The existing `benchmarks/` module was built for an older architecture where solvers exposed a `main(data_dir, output_dir)` Python function returning a CSV path. The production contract is now `request.json` → subprocess → `result.json` via `solver_wrapper.py`. The module also has stale imports (`from swim_matching.scoring import ...` at `metrics.py:15`) and the validator only checks HC-1. The goal is 7 metrics compared across all active solvers.

**STATUS: ALL PHASES COMPLETE (A1–A5). 56 tests pass. E2E verified against `data/app_samples/`.**

### Metric Inventory

| # | Metric | Status | Source |
|---|--------|--------|--------|
| 1 | Average compatibility score | ~~NEW~~ **DONE** | `calculate_compatibility_score()` → `compare_algorithms()` column |
| 2 | Minimum compatibility score (fairness) | ~~NEW~~ **DONE** | Same function, `min_compatibility` field → column |
| 3 | Continuity preservation rate | ~~NEW~~ **DONE** | `calculate_continuity_rate()` → column |
| 4 | % of note requests satisfied | ~~NEW~~ **DONE** (A3) | `calculate_notes_satisfaction()` in `metrics.py` |
| 5 | % of exclusions enforced | ~~NEW~~ **DONE** (A3) | `calculate_exclusion_enforcement()` in `metrics.py` |
| 6 | Number of unassigned units | ~~NEW~~ **DONE** (A4) | `calculate_unassigned_metrics()` in `metrics.py` |
| 7 | Runtime performance | ~~NEW~~ **DONE** (A1) | `SolverRunResult.speed_seconds` from `solver_runner.py` |

### ~~Phase A1: Modernize Runner~~ **DONE**

**Goal:** Rewrite solver invocation to use the production subprocess contract.

**Files to modify:**
- `benchmarks/benchmark.py` — Replace `run_algorithm()` with `run_solver(solver_id, output_dir)` that builds `request.json`, invokes solver as subprocess, reads `result.json`
- `benchmarks/run_benchmark.py` — Replace CLI (`--modules/--names` → `--solvers python_cpsat,graph_based,greedy_based,cpp_exact`; add `--data-dir`, `--source-dir`). Default includes all four active solvers.
- `benchmarks/metrics.py:15` — Fix import: `from swim_matching.scoring` → `from core.scoring`

**Files to create:**
- `benchmarks/solver_runner.py` — Encapsulates: manifest discovery from `solvers/{id}/manifest.json`, `request.json` construction (follow pattern at `backend2/server.py:286-311`), subprocess execution with timeout, `result.json` parsing via `parse_and_validate_solver_result()` pattern

**Key patterns to reuse:**
- `backend2/server.py:build_request_json()` (line 286) — request construction
- `backend2/server.py:run_solver()` (line 314) — subprocess launch with timeout
- `backend2/server.py:parse_and_validate_solver_result()` (line 433) — result validation

**Changes to `BenchmarkResult`:**
- Add `matches: List[Dict]`, `unassigned: List[Dict]`, `summary: Dict` fields
- Keep existing `speed_seconds`, `valid`, `validation_errors`, `error`

**Note on `cpp_exact`:** Requires a compiled `solver.exe` (see `solvers/cpp_exact/`). If the binary is missing, the runner reports an ERROR status for that solver without crashing the benchmark run. The runner handles both `.py` (invoked via `sys.executable`) and `.exe` (invoked directly) entry points from `manifest.json`.

**Tests:** `benchmarks/tests/test_solver_runner.py` — 11 tests: request.json generation, result parsing, timeout handling, missing-binary graceful error. All passing.

**Side-fix:** `solvers/graph_based/solver_wrapper.py` and `solvers/greedy_based/solver_wrapper.py` — both had a latent bug where `app_root` was computed by a hard-coded 3-level directory walk from `request_path`, which only worked for the production `<app_root>/jobs/<job_id>/request.json` layout. Both now prefer `request.get('app_root')` (already present in the request.json payload) and fall back to the walk only if absent.

### ~~Phase A2: Full Hard-Constraint Validator~~ **DONE**

**Goal:** Extend `validator.py` from HC-1-only to all 4 hard constraints.

**Files to modify:**
- `benchmarks/validator.py` — Add new function `validate_result_matches(matches, swimmers, instructors)` that works on parsed `result.json` data and checks:
  - HC-1: Instructor/swimmer uniqueness (existing logic, adapted)
  - HC-2: Adapted swimmers → `can_teach_adapted` instructors
  - HC-3: Age routing — babies (<2.5yr) need `can_teach_babies`, adults (≥18) need `can_teach_adults` (use `config.AGE_THRESHOLDS`)
  - HC-4: Pair constraints — `max_level_diff ≤ 1`, `max_age_diff ≤ 2` (use `config.PAIRING_CONSTRAINTS`)

**Key data to reuse:**
- `solvers/python_cpsat/engine/config.py` — `AGE_THRESHOLDS`, `PAIRING_CONSTRAINTS`
- `DataLoader.from_files()` — load swimmer/instructor domain objects with all attributes

**Tests:** `benchmarks/tests/test_validator.py` — 11 tests covering valid baseline + all 4 HC violation types. All passing.

**Advisory (data-validator finding):** `validate_result_matches()` reads `rss_level` from swimmer dicts, but `Swimmer` dataclass stores the field as `skill_level`. Callers must remap the key before passing dataclass `__dict__` to avoid silent zero-diff comparisons on HC-4. No violations masked in `data/app_samples/` (both pairs pass on real values), but latent bug for generated data with wider level spreads.

### ~~Phase A3: Notes Satisfaction & Exclusion Metrics~~ **DONE**

**Goal:** Add 2 new metric functions checking whether solver results respect swimmer notes.

**Files to modify:**
- `benchmarks/metrics.py` — Add:
  - `calculate_notes_satisfaction(matches, swimmers_lookup, instructors_lookup)` → `{prefer_total, prefer_satisfied, prefer_rate, always_total, always_satisfied, always_rate, combined_rate}`
  - `calculate_exclusion_enforcement(matches, swimmers_lookup, instructors_lookup)` → `{avoid_total, avoid_violated, avoid_rate, never_total, never_violated, never_rate, combined_rate}`

**Key function to reuse:**
- `solvers/python_cpsat/engine/notes_parser.py:parse_notes()` — extracts prefer/always/avoid/never entries from swimmer notes text

**Notes:** Notes reference instructor names (strings), not IDs. Must join `instructor_id` → `instructor_name` via the instructors lookup.

**Tests:** `benchmarks/tests/test_metrics_notes.py` — 13 tests in `TestNoteSatisfaction` (7) and `TestExclusionEnforcement` (6). All passing.

### ~~Phase A4: Unassigned Count, Runtime & Full Report~~ **DONE**

**Goal:** Wire remaining metrics into the comparison report.

**Files to modify:**
- `benchmarks/metrics.py` — Add `calculate_unassigned_metrics(unassigned_list)` → `{count, reasons_breakdown}`
- `benchmarks/benchmark.py` — Update `compare_algorithms()` output DataFrame to include all 7 metrics:

  | Column | Source |
  |--------|--------|
  | Solver | solver manifest name |
  | Status | VALID / INVALID / ERROR |
  | Runtime (s) | wall-clock from Phase A1 |
  | Avg Compatibility | `compatibility_metrics['average_compatibility']` |
  | Min Compatibility | `compatibility_metrics['min_compatibility']` |
  | Continuity Rate % | `continuity_metrics['continuity_rate']` |
  | Notes Satisfied % | `notes_metrics['combined_rate']` |
  | Exclusions Enforced % | `exclusion_metrics['combined_rate']` |
  | Unassigned Count | `unassigned_metrics['count']` |
  | Weighted Quality | existing formula |

**Tests:** `benchmarks/tests/test_report.py` — 9 tests covering `calculate_unassigned_metrics()` (4) and `compare_algorithms()` column structure (5). All passing.

**Note:** `Notes Satisfied %` and `Exclusions Enforced %` columns are `N/A` in the `compare_algorithms()` (CSV-based) path — those metrics require match-level data only available via the subprocess path (`run_solver_by_id` / `run_multi_dataset`).

### ~~Phase A5: Multi-Dataset & End-to-End~~ **DONE**

**Goal:** Support running benchmarks against multiple datasets and produce cross-dataset reports.

**Files modified:**
- `benchmarks/benchmark.py` — `run_multi_dataset(solver_ids, datasets, output_base_dir, workspace_root=None, timeout=300)` added as module-level function; returns `Dict[str, pd.DataFrame]`; uses `run_solver_by_id()` internally; same 9-column structure as `compare_algorithms()`
- `benchmarks/run_benchmark.py` — Rewritten with `create_parser()` (exposed for testing); flags: `--data-dir`, `--source-dir`, `--solvers` (comma-separated), `--seed`, `--output`, `--historical`; `--seed` calls `data_generation/run_all.py --seed <N>` before benchmarking

**Tests:** `benchmarks/tests/test_multi_dataset.py` — 12 tests: `run_multi_dataset()` structure (7) + CLI parser (5). All passing.

**E2E verified:** `python -m benchmarks --data-dir data/app_samples --source-dir data/source --solvers python_cpsat,graph_based,greedy_based --output benchmark_results/`
- python_cpsat: VALID, 1.22s, 0 unassigned
- graph_based: VALID, 1.55s, 2 unassigned
- greedy_based: VALID, 1.01s, 1 unassigned

**Data validator:** 0 HC-4 violations in `data/app_samples/` confirmed before E2E run.

### Phase Dependencies (Plan A)

```
A1 (Runner) ──┬──> A2 (Validator)
              └──> A3 (Notes Metrics)  ──> A4 (Report) ──> A5 (Multi-dataset)
```
A2 and A3 can run in parallel after A1.

---

## PLAN B: XAI Dashboard Features & Issues

### Context

The XAI Dashboard v2 is fully implemented per its 2026-03-15 design spec (2 tabs, detail panel, audit modal). Three what-if backend endpoints exist (`/api/what-if/swap`, `/api/what-if/relax`, `/api/what-if/tune`) but have **no UI**. Known issues from audits: no loading spinners (#8), overview re-fetches on every tab switch (#7), no caching on alternatives (#6), and no security headers (NEW-S2).

### ~~Phase B1: Loading States & Client-Side Caching~~ **DONE**

**Goal:** Add loading spinners during API calls; cache overview and alternatives data client-side.

**Files to modify:**
- `frontend/xai_dashboard/static/dashboard.js` —
  - Add `showLoading(container)` / `hideLoading(container)` helpers inserting a CSS spinner overlay
  - Wrap `loadOverview()`, `loadMatchDetail()` with spinner show/hide
  - Add `cache = { overview: null, overviewAt: 0, alternatives: {} }` — return cached data if <30s old; clear on reload
- `frontend/xai_dashboard/static/dashboard.css` — Add `.loading-overlay` + `@keyframes spin` (pure CSS, no assets)

**Resolves:** Audit #7 (overview re-fetch), #8 (no loading states) — **DONE**

**Implemented:** `cache = { overview, overviewAt, alternatives }` in `dashboard.js`; `showLoading()`/`hideLoading()` helpers with CSS spinner overlay in `dashboard.css`; 30s TTL on overview; per-index cache on alternatives; reload button clears all caches.

### ~~Phase B2: Security Headers~~ **DONE**

**Goal:** Add CSP, X-Frame-Options, X-Content-Type-Options to resolve audit NEW-S2.

**Files to modify:**
- `backend2/server.py` — Add a second `@app.middleware("http")` handler (after the existing `request_logging_middleware` at line 560) that injects security headers on every response:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'`
  - `Referrer-Policy: strict-origin-when-cross-origin`

**Note:** CSP must allow Chart.js CDN (`cdn.jsdelivr.net`) and inline styles (confidence pills, chart rendering). Do **not** modify `frontend/xai_dashboard/app.py` — it is no longer the active server (Flask `__main__` block removed; kept only for reversibility and existing Flask-based tests).

**Files to create:**
- `backend2/tests/test_security_headers.py` — Use FastAPI `TestClient` against `backend2/server.py`; verify all 4 headers present on `GET /`, `GET /xai/`, and `GET /api/solvers` responses

**Resolves:** Audit NEW-S2 — **DONE**

**Implemented:** `security_headers_middleware` added to `backend2/server.py` via `@app.middleware("http")`; 5 TDD tests in `backend2/tests/test_security_headers.py` all pass.

### Phase B3: What-If UI — Swap Tab (M)

**Goal:** Wire `/api/what-if/swap` into a new "What-If" tab with a Swap sub-tab.

**Files to modify:**
- `frontend/xai_dashboard/templates/index.html` — Add third tab button (`data-view="whatif"`), new `<section id="view-whatif">` with 3 inner sub-tabs (swap/relax/tune), swap sub-tab with swimmer dropdown + "Explore" button + results area
- `frontend/xai_dashboard/static/dashboard.js` —
  - `showView` handler for `whatif`
  - `loadWhatIfSwap()`: read swimmer selection, call `apiPost('/api/what-if/swap', {swimmer_id, current_instructor_id})`, render current vs alternative cards with score deltas
  - Populate swimmer dropdown from `state.matches`
  - Reuse `confidenceColor()`, `esc()`, chart patterns
- `frontend/xai_dashboard/static/dashboard.css` — `.whatif-container`, `.whatif-tabs`, `.swap-card`, `.delta-badge`

**Backend already done:** `backend2/xai_router.py` has `/api/what-if/swap` (line 164); `frontend/xai_dashboard/what_if.py` has `swap_explore()` returning ranked alternatives with scores. (Also present in legacy `frontend/xai_dashboard/app.py` line 189, but that Flask file is no longer the active server.)

### Phase B4: What-If UI — Relax & Tune Tabs (M)

**Goal:** Wire `/api/what-if/relax` and `/api/what-if/tune` into remaining sub-tabs.

**Files to modify:**
- `frontend/xai_dashboard/templates/index.html` —
  - Relax sub-tab: swimmer selector + constraint dropdown (`adapted`/`babies`/`adults`) + results showing newly eligible instructors
  - Tune sub-tab: weight sliders (primary/secondary, color/style) + "Re-Score All" button + results table with original vs tuned scores
- `frontend/xai_dashboard/static/dashboard.js` —
  - `loadWhatIfRelax()`: call `/api/what-if/relax`, render eligible instructors sorted by score
  - `loadWhatIfTune()`: read slider values, call `/api/what-if/tune`, render sortable table with delta highlighting
- `frontend/xai_dashboard/static/dashboard.css` — Slider styles, tune table, delta highlights

**Backend already done:** `backend2/xai_router.py` has `/api/what-if/relax` (line 184) and `/api/what-if/tune` (line 204); `frontend/xai_dashboard/what_if.py` has `relax_constraint()` and `tune_weights()`. (Also present in legacy `frontend/xai_dashboard/app.py` lines 213–249.)

### Phase B5: Server-Side Caching & Polish (S)

**Goal:** Cache expensive alternatives computation server-side; polish UX.

**Files to modify:**
- `backend2/xai_router.py` — In-memory cache for `/api/match/<idx>/alternatives` keyed by match index, cleared on `/api/reload`; cache dict lives in `create_xai_router()` closure scope (or on the `DataManager` instance passed in)
- `frontend/xai_dashboard/what_if.py` — Optional cache dict on `WhatIfEngine` for `swap_explore()` results
- `frontend/xai_dashboard/data_manager.py` — `reload()` clears caches
- `frontend/xai_dashboard/static/dashboard.js` — Keyboard nav in dropdowns, focus management

**Resolves:** Audit #6 (no caching on alternatives)

**Tests:** Cache hit/miss test in `backend2/tests/test_xai_router.py`; cache clear on reload verified via FastAPI `TestClient`

### Phase Dependencies (Plan B)

```
B1 (Loading/Cache) ──┐
B2 (Security Headers) ├──> B3 (Swap UI) ──> B4 (Relax/Tune UI) ──> B5 (Server Cache)
```
B1 and B2 are fully independent and can be done in parallel.

---

## Cross-Plan Notes

- **Plan A and Plan B are fully independent** — can be interleaved in any order
- **Suggested starting order:** A1 → B1+B2 → A2+A3 → B3 → A4 → B4 → A5 → B5
- Both plans update the project documentation as phases complete

## Verification

**Plan A verification (after each phase):**
```bash
python -m pytest benchmarks/tests/ -v
python -m benchmarks --solvers python_cpsat,graph_based,greedy_based --data-dir data/ --source-dir data/source --output benchmark_results/
```

**Plan B verification (after each phase):**
```bash
python -m pytest frontend/xai_dashboard/tests/ -v
python -m pytest backend2/tests/ -v
# Manual: start the FastAPI server, run a solve job, then open the XAI dashboard
python backend2/server.py
# POST /api/launch_dashboard after a job completes, or navigate directly to:
# http://localhost:8787/xai/  (port auto-selected from 8787-8794; set PORT env var to override)
```
