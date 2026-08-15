# Aqua Essence Repository Audit — 2026-03-19

> **Historical snapshot:** Findings and file paths below record the codebase as
> audited on this date. The active backend is now `backend/` (FastAPI);
> `backend2/`, the C++ host, and legacy solvers have been removed. Open findings
> in this snapshot are not a current issue tracker.

## 1. Executive Summary

The Aqua Essence swim matching system has a solid core solver (CP-SAT) with good test coverage, but suffers from **massive code duplication** across solver implementations, **missing enforcement of hard constraint HC-4**, **no CI/CD pipeline**, **no solver subprocess timeout** in the Python backend, and **no persistent logging**. Security has been significantly hardened by recent audit work (C1, C2, H1-H5, M1-M3, M5-M7 all resolved), with 4 medium issues remaining (M8-M11). The dual-backend situation adds maintenance burden without clear deprecation plans.

**Top-line numbers:**
- 149 tracked source files
- ~12,000 lines of Python across solvers (with ~40% duplication)
- 4 solver implementations, only 1 tested thoroughly
- 0 CI/CD configuration files
- 0 linting configuration files

---

## 2. Audit by Category

### 1. Security

**Summary:** Substantially improved by recent audit work. 4 medium issues remain open.

**Resolved (confirmed in code):**
- C1: Command injection — `CreateProcessW` replaces `std::system()` (`AquaEssenceHost.cpp`)
- C2: Predictable job IDs — `secrets.token_hex()` in Python, `UuidCreate()` in C++
- H1: Hand-rolled JSON — replaced with nlohmann/json (`backend/json.hpp`)
- H2: Solver timeout — 5-min `WaitForSingleObject` + `TerminateProcess` (`AquaEssenceHost.cpp:346`)
- H3: Exit code checked (`AquaEssenceHost.cpp:353`)
- H4: Timestamp collision — `UuidCreate()` for C++ job IDs
- H5: CSRF — `@require_json` decorator returns 415 for form-encoded (`xai_dashboard/app.py`)
- M1: Path traversal — `Path.is_relative_to()` (`backend2/server.py:602,636`)
- M2: Solver ID validation — rejects `/`, `\`, `..` (`backend2/server.py:453-456`)
- M3: Graceful shutdown — `signal.SIGINT` replaces `os._exit()` (`backend2/server.py:344-350`)
- M5: `.bat` wrappers removed — manifests point to `solver_wrapper.py` directly
- M6: CSV error handling — `DataLoader._read_csv()` with descriptive errors
- M7: Atomic settings — `.tmp` + `os.replace()` (`backend2/server.py:121-126`)

**Open findings:**

| ID | Issue | Severity | File:Line | Status |
|----|-------|----------|-----------|--------|
| M8 | TOCTOU on result.json — `exists()` check then `read_text()` with no exception guard | Medium | `backend2/server.py:517-518` | Confirmed |
| M9 | Error responses leak solver stderr, exit codes, internal paths | Medium | `backend2/server.py:293,515`, `AquaEssenceHost.cpp:406` | Confirmed |
| M10 | `openDrawer()` accepts raw HTML via `innerHTML` — callers escape but function is fragile | Medium | `frontend/app.js:66` | Confirmed, mitigated |
| M11 | No persistent logging anywhere — all stdout/stderr lost on exit | Medium | System-wide | Confirmed |
| NEW-S1 | No rate limiting on `/api/generate` — each POST spawns solver subprocess | Low | `backend2/server.py:472` | Confirmed |
| NEW-S2 | No security headers (CSP, X-Frame-Options, X-Content-Type-Options) on any backend | Low | `backend2/server.py`, `AquaEssenceHost.cpp` | Confirmed |

**No secrets or credentials found in tracked files.**

---

### 2. Architecture

**Summary:** Clean phase separation in CP-SAT solver. Major concern is dual-backend maintenance burden and no clear deprecation path.

**Findings:**

| Finding | Severity | Evidence |
|---------|----------|----------|
| **Dual backends** — C++ (`backend/`) and Python (`backend2/`) both active with no deprecation plan. Feature parity unclear. | Medium | Both serve same API surface, both maintained |
| **No circular dependencies** — dependency graph is acyclic: data → solvers → backend → frontend | N/A (good) | Verified via import analysis |
| **Solver contract is clean** — `manifest.json` → `request.json` → `result.json` pattern is well-defined | N/A (good) | All 4 solvers follow the same contract |
| **XAI dashboard is a separate Flask app** — runs on port 5050, not integrated into main backend | Low | `frontend/xai_dashboard/app.py:156` — separate process, separate CORS config |

---

### 3. Code Quality

**Summary:** Severe code duplication across solvers. This is the single largest maintainability issue.

**Findings:**

| Finding | Severity | Evidence |
|---------|----------|----------|
| **DataLoader duplicated 3x** — `python_cpsat/engine/data_loader.py` (527 lines), `graph_based/data_loader.py` (513 lines), `greedy_based/data_loader.py` (513 lines). All share identical domain objects, `from_files()`, `_validate_data()`. Only difference: `python_cpsat` has `_read_csv()` with error handling; others have bare `pd.read_csv()`. | **High** | 3 files, ~1,550 lines of near-identical code |
| **notes_parser.py duplicated 3x** — byte-for-byte identical 62-line file in all three solver dirs | **High** | 186 lines of pure duplication |
| **solver_wrapper.py ~30% shared** — `_find_workspace_root()`, request parsing, PDF generation, `write_profiles_json()`, summary generation all duplicated across 3 wrappers | Medium | `python_cpsat/solver_wrapper.py`, `graph_based/solver_wrapper.py`, `greedy_based/solver_wrapper.py` |
| **greedy_based + graph_based data loaders lack error handling** — bare `pd.read_csv()` with no try-except at 8 call sites each | **High** | `greedy_based/data_loader.py:262,271,282,292,312,332,353,375` (same lines in graph_based) |
| **Legacy `solvers/greedy/` directory** — old prototype, 4 files (~1,400 lines), not used by any manifest, not tested by CI | Low | `solvers/greedy/matcher.py`, `data_loader.py`, `run_matcher.py`, `validate_output.py` |

**Fix:** Extract shared domain objects + `DataLoader` + `notes_parser` into `core/` module. All three solvers import from there.

---

### 4. Testing

**Summary:** CP-SAT solver well-tested. Graph-based and greedy-based solvers have zero tests. Data generation scripts untested.

| Component | Test Files | Coverage | Severity |
|-----------|-----------|----------|----------|
| `solvers/python_cpsat/engine/` | 7 test files (74+ tests) | Good | N/A |
| `solvers/graph_based/` (658 LOC in `networkx_bipartite.py`) | **0 test files** | **None** | **High** |
| `solvers/greedy_based/` (539 LOC in `greedy.py`) | **0 test files** | **None** | **High** |
| `core/scoring/` | 2 test files | Good | N/A |
| `core/profiles/` | 1 test file | Good | N/A |
| `backend2/` | 2 test files (profile endpoint + security) | Partial | Medium |
| `frontend/xai_dashboard/` | 4 test files | Good | N/A |
| `data_generation/` (7 scripts) | **0 test files** | **None** | Medium |
| `frontend/app.js` (654 LOC, vanilla JS) | **0 test files** | **None** | Low |
| `solvers/greedy/` (legacy, 1,400 LOC) | 1 file (`test_matcher.py`) | Minimal | Low |

**Missing edge case tests:** No tests verify behavior with malformed CSVs, empty datasets, or boundary ages (exactly 2.5, exactly 18).

---

### 5. Documentation

**Summary:** The development guide is thorough and current. RUN_APP.md has stale references. No API documentation.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **RUN_APP.md references deleted `solver.bat`** | Medium | `docs/RUN_APP.md:102` — "The Python solver is launched by `solvers/python_cpsat/solver.bat`" (file deleted in `d4db7cf`) |
| **RUN_APP.md documents C++ backend as primary** | Medium | `docs/RUN_APP.md:3-8` — but `backend2/server.py` is the active dev backend |
| **PLAN.md has stale `swim_matching/` references** | Low | `docs/PLAN.md` — references `swim_matching/matcher.py`, `swim_matching/data/classes.csv` etc. |
| **No API endpoint documentation** | Medium | 18+ endpoints across 3 servers, none documented outside code |
| **The development guide is accurate and comprehensive** | N/A (good) | Cross-verified against codebase |

---

### 6. Dependencies

**Summary:** Minimal dependencies, but no version pinning for reproducible builds.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No version pinning** — `requirements.txt` uses `>=` for all packages | Medium | `requirements.txt:6-9` — e.g., `ortools>=9.8.0` could pull incompatible 10.x |
| **`reportlab` not declared** — used in `pdf_report.py` via try-except import | Low | `solvers/python_cpsat/engine/pdf_report.py:1` — optional but undeclared |
| **`flask` and `flask-cors` not in requirements.txt** — needed by XAI dashboard | Medium | `frontend/xai_dashboard/app.py` imports both; not in `requirements.txt` |
| **`httpx` not in requirements.txt** — needed by backend2 tests | Low | `backend2/tests/test_profile_endpoint.py` imports `httpx` |
| **Stale comment in requirements.txt** — references `swim_matching/scripts` | Low | `requirements.txt:8` |
| **`nlohmann/json` vendored at 24,765 lines** — tracked in git, reasonable for C++ single-header lib | N/A | `backend/json.hpp` |

**Fix:** Create `requirements.txt` with pinned versions and a `requirements-dev.txt` for test/optional deps.

---

### 7. Data Handling

**Summary:** Good validation in CP-SAT data loader. Other solvers lack equivalent error handling.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **`_validate_data()` checks referential integrity only** — no bounds checking on age, skill_level | Low | `data_loader.py:403-453` — validates FK relationships but not value ranges |
| **HC-4 pair constraints not validated at load time** — pairs can have level diff > 1 or age diff > 2 without error | **High** | `data_loader.py:403-453` — no pair compatibility check; `PAIRING_CONSTRAINTS` defined in `config.py:75-76` but never used |
| **Age thresholds hardcoded as magic numbers** — `2.5` and `18` appear in `data_loader.py` properties (lines 36-41) but also as config values in `config.py` | Low | `data_loader.py:36-41` vs `config.py` `AGE_THRESHOLDS` |
| **greedy_based + graph_based data loaders: no error wrapping** — bare `pd.read_csv()` exposes raw pandas tracebacks | High | See Code Quality section |

---

### 8. Performance

**Summary:** Appropriate for the problem scale (~1,800 swimmers). No critical performance issues.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **All data loaded to memory** — no lazy loading or pagination | Low | `data_loader.py:180-244` — acceptable for ~1,800 swimmers |
| **CP-SAT has 5-minute timeout** | N/A (good) | `config.py:59` — `max_time_seconds = 300` |
| **No compatibility score caching between runs** — scores recomputed each time | Low | `phase2_cpsat.py:80-150` — fresh computation per invocation |
| **Profile generation runs as subprocess** — 30s timeout set | N/A (good) | `backend2/server.py:528-535` |

---

### 9. CI/CD & DevOps

**Summary:** No CI/CD exists. No linting. No automated quality gates.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No CI/CD configuration** — no `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile` | **High** | Absent from repository |
| **No linting config** — no `.flake8`, `pyproject.toml`, `.eslintrc`, `ruff.toml` | Medium | Absent from repository |
| **No pre-commit hooks** — no `.pre-commit-config.yaml` | Medium | Absent from repository |
| **No Dockerfile** — no containerization for reproducible environments | Low | Absent from repository |

---

### 10. Accessibility & UX

**Summary:** Basic HTML frontend without accessibility features.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No ARIA attributes** in frontend HTML | Low | `frontend/index.html` — no `role`, `aria-label`, `aria-describedby` |
| **No keyboard navigation** for side drawer | Low | `frontend/app.js:58-80` — drawer opened by click, no keyboard trap/focus management |
| **Error states display well** — errors shown in result area with proper escaping | N/A (good) | `frontend/app.js:118,122,126` |

---

### 11. Maintainability

**Summary:** Dominated by the duplication problem described in Code Quality. Otherwise, the codebase is well-structured.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **Code duplication is the #1 maintainability risk** | **High** | ~1,550 lines of `data_loader.py` duplication + 186 lines of `notes_parser.py` |
| **Config centralization is good** | N/A (good) | `config.py` holds all tunable values |
| **Dataclass usage is consistent** | N/A (good) | All domain objects use `@dataclass` |
| **Phase separation is clean** | N/A (good) | 3 pipeline phases in 3 modules |

---

### 12. Reliability & Resilience

**Summary:** Good timeout handling in C++ backend. Python backend missing solver subprocess timeout.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No solver timeout in Python backend** — `subprocess.run()` has no `timeout=` parameter; hung solver blocks backend indefinitely | **High** | `backend2/server.py:290` — contrast with C++ backend's 5-min `WaitForSingleObject` |
| **TOCTOU on result.json** (M8) — file can be deleted between existence check and read | Medium | `backend2/server.py:517-518` |
| **Job directories never cleaned up** — accumulate in `jobs/` indefinitely | Low | No cleanup logic in either backend |
| **Graceful shutdown works** — `signal.SIGINT` allows uvicorn to drain | N/A (good) | `backend2/server.py:344-350` |
| **Heartbeat watchdog kills abandoned backend** | N/A (good) | `backend2/server.py:305-309` — 120s timeout |

---

### 13. Observability

**Summary:** No structured logging. All output to stdout/stderr, lost on exit. (M11 from prior audit.)

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No `import logging` anywhere in Python code** | **High** | Grep for `import logging` returns 0 results |
| **Print statements used for diagnostics** | Medium | `backend2/server.py:308,534,668`, `phase2_cpsat.py:76-86` |
| **No correlation IDs** — no way to trace a request through solver invocation | Medium | System-wide |
| **No metrics collection** | Low | No prometheus, statsd, or custom metrics |

---

### 14. Configuration Management

**Summary:** Config centralized in `config.py` (good). Port numbers hardcoded (minor).

| Finding | Severity | Evidence |
|---------|----------|----------|
| **`config.py` centralizes all weights/thresholds** | N/A (good) | `solvers/python_cpsat/engine/config.py` — 87 lines, well-organized |
| **Port numbers hardcoded** — 8787-8794 in backend2, 5050 in XAI dashboard | Low | `backend2/server.py:653`, `xai_dashboard/app.py:28,156` |
| **Settings use safe defaults** | N/A (good) | `backend2/server.py:103-118` |
| **Debug mode disabled** | N/A (good) | `xai_dashboard/app.py:156`, `__main__.py:18` |

---

### 15. Release & Change Management

**Summary:** No versioning scheme, no changelog, no migration handling.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No version number** beyond hardcoded `"0.1.0"` in health endpoint | Low | `backend2/server.py` health endpoint |
| **No CHANGELOG file** | Low | Absent from repository |
| **No database migrations** — CSV-only, no schema versioning | N/A | Not applicable (CSV-based) |
| **Git history is clean** — descriptive commit messages | N/A (good) | Verified via `git log` |

---

### 16. Operational Support

**Summary:** No production monitoring, alerting, or runbooks.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No monitoring or alerting** | Low | Absent — appropriate for academic/local tool |
| **No runbook or ops guide** | Low | Only `docs/RUN_APP.md` which is partially stale |
| **Health endpoint exists** | N/A (good) | `GET /api/health` on both backends |

*Note: This is an academic project primarily run locally, so production ops tooling is not expected.*

---

### 17. Compatibility & Portability

**Summary:** Python backend is cross-platform. C++ backend is Windows-only.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **C++ backend is Windows-only** — Win32 API (`CreateProcessW`, `WaitForSingleObject`, `UuidCreate`) | Medium | `backend/AquaEssenceHost.cpp` — entire file uses Win32 |
| **Python backend is cross-platform** — uses `pathlib`, `subprocess.run()`, no hardcoded paths | N/A (good) | `backend2/server.py` |
| **File picker has Win32 fallback** — gracefully degrades to tkinter on non-Windows | N/A (good) | `backend2/server.py:134-212` |
| **`Path.is_relative_to()` requires Python 3.9+** — no explicit minimum version stated | Low | `backend2/server.py:602` |

---

### 18. API / Interface Design

**Summary:** Consistent JSON response format. Good input validation. Missing security headers.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **Consistent response format** — all endpoints return `{"ok": bool, ...}` | N/A (good) | All endpoints in `backend2/server.py` |
| **`Cache-Control: no-store` on all API responses** | N/A (good) | `NO_CACHE` dict applied everywhere |
| **No security headers** — no CSP, X-Frame-Options, X-Content-Type-Options | Low | `backend2/server.py` — no middleware for security headers |
| **Profile endpoint: 503 if no job run, 400 for invalid type, 404 for missing ID** | N/A (good) | `backend2/server.py:549-594` — proper HTTP status codes |
| **C++ backend profile regex limits ID to digits** — `/api/profile/(swimmer|instructor)/(\d+)` | N/A (good) | `AquaEssenceHost.cpp` |

---

### 19. Database / Persistence

**Summary:** CSV-only system. No database. Job artifacts stored as files.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No database** — all data in CSV files | N/A | By design |
| **Job results stored in `jobs/{id}/`** — no TTL, no cleanup | Low | `backend2/server.py` writes to `jobs/` |
| **`profiles.json` contains PII** — swimmer names, ages, medical notes | Medium | Generated by `core/profiles/generate_profiles.py` |
| **No backup or recovery mechanism** | Low | CSV source files are git-tracked; generated data is reproducible |

---

### 20. Privacy & Compliance

**Summary:** System handles children's PII (names, ages, medical notes) with no data retention controls.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **Swimmer PII stored indefinitely** — names, ages, medical notes (e.g., "ADHD") in `profiles.json` within job dirs | Medium | `data/app_samples/swimmers.csv` — real format includes `first_name, last_name, age, has_special_needs, notes` |
| **Historical pairings link swimmers to instructors** — could reveal relationship patterns | Low | `data/app_samples/historical_pairings.csv` |
| **No data retention policy or auto-deletion** | Medium | `jobs/` directory grows unbounded |
| **PII in error messages possible** — solver errors could include swimmer data | Low | Cross-ref with M9 |

*Note: Current data is synthetic (faker-generated). For production with real children's data, COPPA/PIPEDA compliance would be required.*

---

### 21. Internationalization & Localization

**Summary:** Not applicable. English-only, single-locale system for a specific swim program.

No findings. This is appropriate for the scope of the project.

---

### 22. Usability

**Summary:** Frontend is functional but basic. Good error messaging. No loading indicators during solver execution.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No loading indicator during solver execution** — solver can take up to 5 minutes; no spinner or progress | Low | `frontend/app.js` — form submission triggers fetch with no UI feedback during wait |
| **Clickable names with side drawer** — good UX for exploring profiles | N/A (good) | `frontend/app.js:58-80` |
| **Unassigned swimmers section** — clearly shows who wasn't matched and why | N/A (good) | `frontend/app.js` |

---

### 23. Business Logic Correctness

**Summary:** HC-1, HC-2, HC-3 correctly implemented. HC-4 is **not enforced**.

| Constraint | Status | Evidence |
|------------|--------|----------|
| **HC-1: Instructor capacity** (≤1 entity per slot) | **Correct** | `phase2_cpsat.py:213-223` — `model.Add(individuals_assigned + pairs_assigned <= 1)` |
| **HC-2: Adapted swimmers need adapted instructors** | **Correct** | `phase2_cpsat.py:225-239` — blocks non-adapted instructors |
| **HC-3: Age routing** (babies <2.5yr, adults 18+) | **Correct** | `phase2_cpsat.py:241-273` — blocks non-qualified instructors for age categories |
| **HC-4: Paired swimmers ≤1 RSS level, ≤2 years apart** | **NOT ENFORCED** | `config.py:75-76` defines `PAIRING_CONSTRAINTS = {'max_level_diff': 1, 'max_age_diff': 2}` but **no code references these values**. `_validate_data()` at `data_loader.py:403-453` does not check pair compatibility. `phase2_cpsat.py` has no constraints using these values. |
| **Notes boosts (prefer/always)** | **Correct** | `phase2_cpsat.py:115-120,136-145` — `NOTES_BOOSTS` applied to scores |
| **Notes exclusions (avoid/never)** | **Correct** | `phase2_cpsat.py:275-295` — hard constraints block assignment |
| **Pair scoring (harmonic mean)** | **Correct** | `phase2_cpsat.py:127-150` — uses `scorer.score_pair_match()` |

**HC-4 is the most critical finding in this audit.** The constraint is specified, configured, but never enforced — neither at data validation time nor in the CP-SAT model.

---

### 24. Code Security Hygiene

**Summary:** Good practices overall. Recent security audit addressed major issues.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **All `innerHTML` callers use `esc()` / `escapeHtml()`** | N/A (good) | `frontend/app.js`, `frontend/xai_dashboard/static/dashboard.js` |
| **No `shell=True` in subprocess calls** | N/A (good) | `backend2/server.py:290` uses list args |
| **Path traversal blocked with `is_relative_to()`** | N/A (good) | `backend2/server.py:602,636` |
| **Job IDs use `secrets.token_hex()`** | N/A (good) | `backend2/server.py` |
| **Solver ID rejects path traversal chars** | N/A (good) | `backend2/server.py:453-456` |

Cross-references Security section for remaining M8, M9, M10, M11.

---

### 25. Governance / Project Health

**Summary:** Single-contributor academic project. No formal review process or contribution guidelines.

| Finding | Severity | Evidence |
|---------|----------|----------|
| **No CONTRIBUTING.md** | Low | Absent — appropriate for academic project |
| **No PR template or review process** | Low | Absent |
| **No branch protection** | Low | `main` accepts direct pushes |
| **Clean git history with descriptive commits** | N/A (good) | Verified via `git log` |
| **Multiple stale feature branches** | Low | `feature/cpp-implementation`, `feature/python-gap-fixes`, `feature/xai-dashboard`, etc. |

---

## 3. Highest-Priority Issues

| Rank | Issue | Category | Severity | Location |
|------|-------|----------|----------|----------|
| **1** | **HC-4 pair constraints not enforced** — `PAIRING_CONSTRAINTS` defined in config but never checked in solver or data validation | Business Logic | **Critical** | `config.py:75-76`, absent from `phase2_cpsat.py` and `data_loader.py:403-453` |
| **2** | **DataLoader + notes_parser duplicated 3x** — ~1,750 lines of near-identical code across 3 solvers | Code Quality | **High** | `solvers/*/data_loader.py`, `solvers/*/notes_parser.py` |
| **3** | **No solver subprocess timeout in Python backend** — hung solver blocks backend indefinitely | Reliability | **High** | `backend2/server.py:290` — `subprocess.run()` without `timeout=` |
| **4** | **No CI/CD pipeline** — no automated testing, linting, or build verification | CI/CD | **High** | Absent from repository |
| **5** | **Graph-based + greedy-based solvers have 0 tests** — 1,197 LOC of untested algorithm code in production use | Testing | **High** | `solvers/graph_based/`, `solvers/greedy_based/` |
| **6** | **No persistent logging** (M11) — all stdout/stderr lost on exit; no structured logging | Observability | **High** | System-wide — no `import logging` anywhere |
| **7** | **greedy_based + graph_based data loaders lack error handling** — bare `pd.read_csv()` with no descriptive errors | Data Handling | **High** | `greedy_based/data_loader.py:262+`, `graph_based/data_loader.py:262+` |
| **8** | **Flask + httpx not in requirements.txt** — XAI dashboard and backend2 tests won't install cleanly | Dependencies | **Medium** | `requirements.txt` |
| **9** | **TOCTOU on result.json** (M8) — race between existence check and file read | Security | **Medium** | `backend2/server.py:517-518` |
| **10** | **Error responses leak internal details** (M9) — solver stderr + paths exposed to clients | Security | **Medium** | `backend2/server.py:293,515` |

---

## 4. Suggested Next Steps (in order)

1. **Enforce HC-4** — Add pair validation in `_validate_data()` or as CP-SAT constraints in `phase2_cpsat.py`. This is a correctness bug: the system may assign pairs that violate documented business rules.

2. **Extract shared code to `core/`** — Move `DataLoader`, domain objects (`Swimmer`, `Instructor`, etc.), and `notes_parser` into `core/data/` or similar. All 3 solver wrappers import from there. This eliminates ~1,750 lines of duplication and ensures bug fixes propagate.

3. **Add solver timeout to Python backend** — Add `timeout=300` to `subprocess.run()` in `backend2/server.py:290` to match C++ backend's 5-minute limit. Catch `subprocess.TimeoutExpired`.

4. **Fix remaining security issues** — M8 (wrap file reads in try-except), M9 (sanitize error messages before returning to client), M11 (add Python `logging` with rotating file handler).

5. **Add CI/CD** — GitHub Actions workflow: run `python -m pytest` across all test suites, add `ruff` or `flake8` for linting. Baseline config.

6. **Fix dependencies** — Pin versions in `requirements.txt`. Add `flask`, `flask-cors`, `reportlab` (optional), `httpx` (dev).

7. **Update stale docs** — Fix `docs/RUN_APP.md` solver.bat reference, update backend primary status, remove `swim_matching/` references from `docs/PLAN.md`.

8. **Add tests for graph_based + greedy_based solvers** — At minimum, smoke tests verifying hard constraints are respected.

9. **Clean up stale branches** — Delete merged/abandoned branches (`feature/python-gap-fixes`, `feature/xai-dashboard`, etc.).

10. **Add PII retention policy** — Auto-delete job directories after configurable TTL, or at minimum document the retention behavior.
