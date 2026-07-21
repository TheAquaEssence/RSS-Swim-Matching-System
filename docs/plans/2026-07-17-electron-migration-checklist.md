# Aqua Essence Cleanup, Electron Migration, and GitHub Release Checklist

**Created:** 2026-07-17  
**Starting branch:** `dev`  
**Purpose:** Preserve the codebase assessment and provide an execution checklist that can be continued by developers or other AI tools without repeating the initial audit.

## Working Rules

These are standing rules rather than completion tasks:

- Make cleanup changes in small, reviewable pull requests.
- Run the full test suite and Ruff after every cleanup batch.
- Do not combine broad file moves with behavior changes in the same pull request.
- Do not rewrite the CP-SAT solver or FastAPI backend in JavaScript for the Electron migration.
- Treat all operational swimmer, instructor, pairing, session, medical-note, job, and log data as private.
- Preserve useful tests before removing an old implementation.
- Record intentional architecture decisions in `docs/decisions.md`.

## Audit Baseline

The initial audit was read-only. At the time of assessment:

- Branch: `dev`, six commits ahead of `origin/dev`.
- Existing working-tree modification: `data/aqua_essence.db`.
- The database modification predated this plan and must not be overwritten or reverted accidentally.
- Tracked files: 191.
- Approximate source size: 32,000 lines including tests, CSS, and the Jackrabbit browser extension.
- Test baseline: **515 passed**.
- Ruff baseline: **all checks passed**.
- The repository is not unusually large; complexity is concentrated in duplicated helpers, obsolete launch/server paths, mixed data responsibilities, and a few large modules.

### Baseline verification commands

```powershell
python -m pytest -q solvers/python_cpsat/engine/tests/ core/scoring/tests/ core/tests/ backend/tests/ frontend/xai_dashboard/tests/ solvers/tests/ data_generation/tests/
python -m ruff check .
git status --short --branch
```

> Note: `.agents/skills/run-all-tests/SKILL.md` is stale. It references the removed `swim_matching/...` layout. Update that skill before relying on it.

## Target Product Direction

The preferred desktop architecture is:

```text
Electron desktop shell
├── Existing HTML/CSS/JavaScript frontend
├── Bundled FastAPI backend
│   ├── Settings and local data services
│   ├── Job orchestration
│   ├── XAI routes
│   └── Solver worker management
├── Python CP-SAT solver worker
└── Electron userData directory
    ├── SQLite database
    ├── settings
    ├── imported files
    ├── jobs
    └── logs
```

Electron should package and manage the existing application. It should not replace the Python solver or duplicate the backend in Node.js.

## Component Decisions

### Keep

- [x] Keep `solvers/python_cpsat/engine/` as the production optimization engine.
- [x] Keep `solvers/python_cpsat/solver_wrapper.py` as the initial isolated worker boundary.
- [x] Keep `core/scoring/` as the shared compatibility implementation.
- [x] Keep `core/flags.py`, `core/aqua_logging.py`, and `core/profiles/`.
- [x] Keep FastAPI as the only production backend.
- [x] Keep the current vanilla HTML/CSS/JavaScript frontend initially.
- [x] Keep `backend/db.py`, but refactor its boundaries after dead code is removed.
- [x] Keep XAI `DataManager`, `WhatIfEngine`, templates, JavaScript, and CSS used by the FastAPI XAI router.
- [x] Keep `data_generation/` as development and synthetic-fixture tooling.
- [x] Keep the active test suites as cleanup safety gates.
- [x] Keep `fixed_class_workflow.py`; it is imported by the production solver wrapper.

### Remove after verification

- [x] Remove `launch.pyw`.
  - It points to nonexistent `backend2.server`.
  - `start.py` is the current functional browser launcher.
- [x] Remove `runtime_helpers/`.
  - It duplicates five modules under `backend/`.
  - One pair is byte-identical and four pairs have diverged.
  - No active application module imports `runtime_helpers`.
- [x] Remove `backend/desktop_host_pipeline.py`.
  - The running server does not import it.
  - Its only importer is `backend/tests/test_desktop_host_pipeline.py`.
  - Transfer any still-useful roster-building behavior before deleting its dedicated test.
- [x] Remove the obsolete Flask XAI server:
  - `frontend/xai_dashboard/app.py`
  - `frontend/xai_dashboard/__main__.py`
- [x] Transfer any missing Flask route/logging assertions to FastAPI tests first.
- [x] Remove Flask-only tests after equivalent FastAPI coverage exists.
- [x] Remove `flask` and `flask-cors` from project dependencies.
- [x] Remove `data/legacy/` after confirming nothing outside historical documentation needs it.
- [x] Archive or remove `reference/Rankings.xlsx` and `reference/combined.xlsx`.
  - They are documented as human reference files.
  - The application does not read them.
  - Move any required provenance or explanations into Markdown documentation first.
- [x] Remove hidden solver-selection UI if version 1 will support only CP-SAT.
- [x] Remove obsolete `.bat`, `.cmd`, and generic `.exe` solver execution branches if the single-solver decision is accepted.

### Consolidate or separate

- [x] Consolidate production XAI routes under FastAPI.
- [x] Integrate the XAI page into the main application navigation.
- [x] Consolidate duplicated reference tables in `data/app_samples/` and `data/source/`.
- [x] Separate immutable public reference data from runtime operational data.
- [x] Separate runtime dependencies from development/test dependencies.
- [x] Consolidate AI/developer guidance in `docs/development.md`, `docs/architecture.md`, and `docs/decisions.md`; tool-specific files point to tracked guidance.
- [x] Treat the Jackrabbit Exporter as a separately versioned deliverable.
  - Preferred options: a separate repository or an isolated `integrations/jackrabbit-exporter/` package.
  - It should have its own README, permissions review, version, and release process.
- [x] Keep one-time administrative scripts under `scripts/` and document support boundaries in `scripts/README.md`.

## Phase 0 — Public-Release Data Safety

This phase blocks any public GitHub release.

### Known risk

The repository currently tracks:

- `data/aqua_essence.db`
- `data/source/instructors.csv`
- `data/source/pairings.csv`

At audit time, the database contained:

- 97 instructor records
- 18,563 pairing records
- 136 sessions

The schemas include instructor names and operational identifiers. These files must be treated as potentially real personal data until proven otherwise.

> **Update 2026-07-18:** classified as real operational data; all three files (plus `data/legacy/` and `reference/`) are now untracked and gitignored, with synthetic stand-ins under `examples/demo/`. The files remain only in this private repo's history and on local disks.

### Checklist

- [x] Determine whether every tracked database and operational CSV record is synthetic.
- Treat the prohibition on copying names, notes, dates of birth, medical information, or identifiers into issues, logs, prompts, and pull requests as a standing privacy rule.
- [x] Replace operational repository data with a fully synthetic demonstration dataset.
- [x] Generate synthetic data from a documented seed so fixtures can be reproduced.
- [x] Add `data/aqua_essence.db` to `.gitignore` as an active rule, not a commented example.
- [x] Ignore runtime imports, jobs, settings, logs, and generated reports.
- [x] Move runtime database creation to a configurable application-data directory.
- [x] Scan the full Git history for secrets and personal information. *(Superseded: the public release is a new repository with no inherited history — see Recorded Decisions. This private repo's history intentionally remains as the archive.)*
- [x] Purge sensitive files from Git history if they were ever committed. *(Superseded: satisfied by the new-repository release strategy — see Recorded Decisions.)*
- [x] No credentials requiring rotation were found during the completed secret/history scans.
- [x] Check GitHub issues, pull requests, workflow artifacts, and releases for copied private data before making the repository public.
- [x] Add automated secret scanning to CI.
- [x] Add a privacy/data-retention document.
- [x] Document how users can delete local jobs, logs, imported data, and the database.

### Phase 0 exit gate

- [x] A clean clone contains no operational or personal data.
- [x] Demo workflows operate entirely on synthetic data.
- [x] Repository history handling is resolved by retaining this repository privately and creating the public repository from a sanitized tree without inherited history.
- [x] Full tests and Ruff pass.

## Phase 1 — Remove Confirmed Dead Paths

Perform these as separate cleanup pull requests when practical.

- [x] Delete broken `launch.pyw` and update launch documentation to use `start.py`.
- [x] Delete `runtime_helpers/` and update stale documentation that describes it.
- [x] Delete `backend/desktop_host_pipeline.py` after preserving any required behavior.
- [x] Remove or replace `backend/tests/test_desktop_host_pipeline.py`.
- [x] Compare Flask XAI route tests with `backend/tests/test_xai_router.py`.
- [x] Port missing XAI index, summary, tuning, alternatives, logging, and error assertions to FastAPI tests.
- [x] Delete the Flask XAI app and its Flask-only tests.
- [x] Remove Flask dependencies.
- [x] Delete `data/legacy/`.
- [x] Archive/remove unused reference spreadsheets.
- [x] Remove stale documentation references to `backend2/`, removed C++ backends, old solvers, and old paths.
- [x] Re-run the complete baseline after every removal batch.

### Phase 1 exit gate

- [x] Only one production backend implementation remains.
- [x] No active module imports removed compatibility packages.
- [x] No production dependency exists solely to test an obsolete implementation.
- [x] Full tests and Ruff pass.

## Phase 2 — Establish One Canonical Application

### Data layout

Adopt a structure similar to:

```text
resources/reference/       Public non-personal lookup and ranking tables
examples/demo/             Complete synthetic demonstration dataset
tests/fixtures/            Small test-specific datasets
<userData>/                Runtime database, settings, jobs, logs, and imports
```

- [x] Select one canonical copy of each personality color, instructor style, swimmer type, and ranking table.
- [x] Update tests that currently read duplicate tables from both `data/source/` and `data/app_samples/`.
- [x] Keep synthetic entity files only under `examples/demo/` or test fixtures.
- [x] Prevent data-generation scripts from overwriting canonical business/reference data unexpectedly.
- [x] Make all writable paths configurable through one application-data root.
- [x] Ensure installed application resources are treated as read-only.

### Dependencies and packaging metadata

- [x] Introduce `pyproject.toml` or clearly separated runtime/dev requirements.
- [x] Keep runtime dependencies limited to what the shipped backend and solver use.
- [x] Move `faker`, `pytest`, `httpx`, and linting tools to development dependencies.
- [x] Pin and test one supported Python version for desktop packaging.
- [x] Align local documentation and GitHub Actions with the supported Python version.

### Single-solver decision

- [x] Decide whether third-party/multiple solver plugins are a real product requirement.
- [x] If no, remove:
  - `/api/solvers`
  - `/api/set_solver`
  - `active_solver` settings
  - hidden frontend solver picker
  - generic solver manifest discovery
  - `.bat`, `.cmd`, and unrelated executable handling
- [x] Keep the CP-SAT worker in a separate process for timeout and crash isolation.
- [x] Solver plugins are not required for version 1; manifest discovery and the plugin contract were removed.

### Phase 2 exit gate

- [x] `python start.py` exposes the complete product.
- [x] The application has one backend and one documented production solver strategy.
- [x] Public resources, demo fixtures, and private runtime data have distinct locations.
- [x] Full tests and Ruff pass from clean GitHub Actions checkouts.

## Phase 3 — Reduce Backend and Frontend Coupling

### Backend

`backend/server.py` currently combines application creation, global state, settings, file handling, normalization, solver orchestration, result processing, static serving, and lifecycle management.

- [x] Introduce a FastAPI application factory.
- [x] Replace module-wide mutable state with an explicit application state/service container.
- [x] Replace router `host` module injection with narrow service dependencies.
- [x] Extract generation orchestration into a `GenerationService`.
- [x] Extract process management into a `SolverRunner`.
- [x] Extract path and storage rules into a storage service.
- [x] Keep database operations behind a narrow repository/service interface.
- [x] Replace `_HAS_DB`, `_HAS_XAI`, `_HAS_CSV_IMPORT`, `_HAS_ISCE`, and `_HAS_LOGGING` degradation branches with required imports or explicit feature configuration.
- [x] Fail clearly during startup when required components are missing.
- [x] Preserve API behavior with tests during each extraction.

A possible direction—not a required one-shot restructure—is:

```text
backend/
├── app.py
├── config.py
├── api/
│   ├── generation.py
│   ├── instructors.py
│   ├── sessions.py
│   ├── settings.py
│   └── xai.py
├── services/
│   ├── generation_service.py
│   ├── solver_runner.py
│   ├── import_service.py
│   └── storage.py
└── db.py
```

### Frontend

- [x] Keep vanilla JavaScript unless a separate product requirement justifies a framework migration.
- [x] Split `frontend/app.js` into feature modules.
- [x] Split the large stylesheet by feature or component.
- [x] Keep instructor editing and generation flows as explicit modules.
- [x] Integrate XAI into main navigation instead of presenting it as a separate application.
- [x] Remove hidden and unreachable controls.
- [x] Add browser-level smoke tests for critical user workflows.

### Phase 3 exit gate

- [x] Generation can be tested without importing the entire server module.
- [x] Routers depend on explicit services rather than server globals.
- [x] The main frontend and XAI experience behave as one application.
- [x] Full tests, Ruff, and critical UI smoke tests pass.

## Phase 4 — Prepare the Electron Boundary

Complete these before building the full installer.

- [x] Allow the backend port to be supplied explicitly.
- [x] Support selection of a random available port.
- [x] Bind only to `127.0.0.1`.
- [x] Add a per-launch authentication/capability token shared between Electron and FastAPI.
- [x] Require the token on state-changing and private-data API operations.
- [x] Add a reliable health/readiness endpoint.
- [x] Define graceful shutdown and forced-termination behavior.
- [x] Ensure solver child processes are terminated when the desktop app exits.
- [x] Pass the Electron `userData` directory to Python as the application-data root.
- [x] Replace Tkinter/backend file selection with Electron-native file dialogs.
- [x] Define database migration/version behavior.
- [x] Define job and log retention limits.
- [x] Ensure crashes do not leave corrupt settings or partially written databases.
- [x] Test backend startup, readiness, failure reporting, restart, and shutdown independently of the UI.

### Phase 4 exit gate

- [x] A small process harness can start and stop the packaged backend predictably.
- [x] All runtime writes stay inside a supplied temporary application-data directory.
- [x] The backend is inaccessible without the launch token for protected operations.
- [x] Solver timeouts and application shutdown leave no orphan processes.

## Phase 5 — Build the Electron Application

### Electron structure

- [x] Add a `desktop/` or equivalent Electron package.
- [x] Implement the Electron main process.
- [x] Implement a minimal preload bridge.
- [x] Create the BrowserWindow only after backend readiness succeeds.
- [x] Display a useful startup failure screen if Python cannot start.
- [x] Use Electron-native open/save dialogs.
- [x] Forward safe diagnostic information without exposing private data or internal paths unnecessarily.
- [x] Shut down Python and solver processes when the final window closes.

### Security configuration

- [x] Set `nodeIntegration: false`.
- [x] Set `contextIsolation: true`.
- [x] Enable renderer sandboxing where compatible.
- [x] Use a restrictive Content Security Policy.
- [x] Expose only specific preload functions; do not expose raw IPC.
- [x] Validate every IPC argument in the main process.
- [x] Block unexpected external navigation and window creation.
- [x] Open approved external URLs through the system browser only.
- [x] Review FastAPI CORS and host validation for the Electron environment.

### Python packaging

- [x] Prototype PyInstaller directory-mode packaging for FastAPI, pandas, OR-Tools, and ReportLab.
- [x] Include required reference resources explicitly.
- [x] Verify OR-Tools native libraries are present in a clean installation.
- [x] Package the solver worker so subprocess invocation works outside the source tree.
- [x] Do not bundle pytest, Faker, Flask, or other development-only dependencies.
- [x] Record third-party licenses included in the distribution.

### Phase 5 exit gate

- [x] A clean Windows machine can install and launch the application without Python installed.
- [x] Generate, review, XAI, import, export, and shutdown workflows pass.
- [x] The application works offline.
- [x] No runtime data is written into the installation directory.
- [x] Uninstalling does not silently delete user data unless the user chooses that option.

## Phase 6 — GitHub and Release Readiness

### Repository documentation

- [x] Replace the oversized README landing page with a concise product README.
- [x] Keep detailed domain rules in `docs/matching-process-rules-and-guidelines.md` and the CP-SAT specification.
- [x] Add an architecture document.
- [x] Add developer setup and testing instructions.
- [x] Add `CONTRIBUTING.md`.
- [x] Add `SECURITY.md` with private vulnerability-reporting instructions.
- [x] Add privacy and data-retention documentation.
- [x] Add a changelog and versioning policy.
- [x] Review the existing LICENSE and bundled dependency obligations.
- [x] Transfer current decisions to `docs/decisions.md` and classify dated audits/plans as historical in `docs/README.md`.

### CI and release automation

- [x] Test the supported Python version or version matrix.
- [x] Run Ruff and all active Python tests.
- [x] Add frontend linting/testing if a JavaScript toolchain is introduced.
- [x] Add a Windows Electron build job.
- [x] Add a packaged-application smoke test.
- [x] Publish installer artifacts only from version tags.
- [ ] Publish SHA-256 checksums.
- [x] Generate release notes from the changelog.
- [ ] Add code signing when practical.
- [x] Document that unsigned Windows builds may trigger SmartScreen warnings until signing is established.

### Final release gate

- [x] Fresh-clone test passes.
- [x] Clean-machine installer test passes.
- [ ] No personal or operational data exists in the current tree, history, artifacts, or releases.
- [x] Security and privacy documentation is complete.
- [x] All automated tests pass.
- [ ] Installer checksum is published.
- [ ] Release tag and application version agree.

## Recommended Pull Request Order

- [x] **PR 1:** Data classification, synthetic replacement plan, and ignore rules.
- [x] **PR 2:** Remove broken launcher and stale path documentation.
- [x] **PR 3:** Remove `runtime_helpers/` duplication.
- [x] **PR 4:** Remove unused desktop host pipeline.
- [x] **PR 5:** Transfer Flask coverage to FastAPI and remove Flask.
- [x] **PR 6:** Remove/archive legacy data and unused reference workbooks.
- [x] **PR 7:** Consolidate reference, demo, and test data layout.
- [x] **PR 8:** Decide and simplify the single-solver interface.
- [x] **PR 9+:** Incremental backend/frontend modularization.
- [x] **Electron spike:** Prove process startup, readiness, secure local communication, shutdown, and packaged OR-Tools execution before building full desktop UI integration.

## Resolved Decisions

- [x] The sanitized public repository is open source under the MIT License.
- [x] Windows is the only supported desktop platform for version 1.
- [x] Existing compatible user databases survive upgrades through transactional schema migrations.
- [x] Multiple solver plugins are not a version 1 requirement.
- [x] The Jackrabbit Exporter lives in `TheAquaEssence/jackrabbit-exporter` as a separately versioned project.
- [x] Application-owned jobs are retained for 30 days and logs for 14 days by default; externally selected inputs and exports are never automatically deleted.
- [x] Automatic updates are deferred until after version 1.
- [x] Code signing is deferred until capability is available; the first installer remains explicitly unsigned.

## Recorded Decisions

- **Data classification (2026-07-17):** `data/aqua_essence.db`, `data/source/instructors.csv`, and `data/source/pairings.csv` contain **real operational data**. The repository and installers ship synthetic data only; the real dataset is delivered to the client once, out of band (password-protected archive over a private channel), and imported into the local application-data database on first launch. Do not commit real data in any form, including encrypted blobs.
- **Public release strategy (2026-07-17):** The current repository stays **private permanently** as the development archive (its history contains the real data). The public release is a **new repository** seeded from a single clean initial commit of the sanitized tree — no inherited history. History-purge checklist items are satisfied by this decision.
- **Single-solver decision (2026-07-18):** Version 1 supports CP-SAT only; solver plugins are not a product requirement. `/api/solvers`, `/api/set_solver`, the `active_solver` setting, manifest discovery, the hidden frontend picker, and `.bat`/`.cmd`/`.exe` execution branches were removed. The solver entry is fixed at `solvers/python_cpsat/solver_wrapper.py`, still run in a separate process for timeout/crash isolation (`SOLVERS_DIR` remains the test seam).
- **Commit attribution in the new public repo (2026-07-17):** Every commit must end with `Co-Authored-By:` trailers crediting Daniel Nwogo (nigerianpickle) and Ibrahim Mamman (Nabxz). No other co-author trailers (including AI tool attributions) are permitted. **Deferred:** which email addresses to use is undecided — personal emails must not appear in public commits, so noreply addresses (`users.noreply.github.com`) or another option will be chosen when the new repository is created. Enforce with a `prepare-commit-msg` hook or commit template at that time.

## Progress Log

- **2026-07-21 (fresh-clone release-candidate verification):** Commit `18b3d6b` was pushed to `dev` and cloned from GitHub into a new `C:\tmp` directory with no inherited working files. The exact remote commit restored 285 lockfile-pinned desktop packages with zero npm audit vulnerabilities; all 29 desktop tests and JavaScript checks passed. The current Python/CI suite passed 605 tests with three expected environment/artifact-gated skips, while Ruff, third-party-notice drift, tag/version/changelog release validation, and clean-worktree checks passed. The fresh clone tracks only canonical lookup tables and the seeded synthetic `examples/demo/` dataset; scans found none of the forbidden operational paths, runtime data, project-personal identifiers, or credential patterns. The local working tree run remained 606 passed/two skipped because it could exercise one additional packaged-artifact test against `.dist`; the fresh source clone correctly skipped it.

- **2026-07-21 (tag-gated release automation and GitHub privacy audit):** The Windows workflow now builds on semantic-version tags but grants release-write permission only to a tag-only publication job. `scripts/prepare_release.py` rejects disagreement among the `vMAJOR.MINOR.PATCH` tag, `desktop/package.json`, backend health version, installer filename, and dated changelog section; it extracts that section into release notes and produces deterministic SHA-256 sums for the installer before `gh release create` publishes either asset. Focused tests exercised valid and invalid contracts, and the current 0.1.0 installer reproduced checksum `8A9D3DF3D4DF774C83DBE87870C7C0601F451F8CC9782E3B7F861BC82C3E6CF5`. GitHub inspection found no issues, pull requests, or releases; ten retained workflow artifacts came only from sanitized post-removal commits. The latest installer and unpacked artifacts were downloaded and scanned: no operational database, private instructor/pairing paths, runtime jobs/settings/logs, project-personal identifiers, credentials, or private keys were present (email matches were license/third-party metadata only). The current tracked tree likewise contains only canonical lookup CSVs and synthetic `examples/demo/` entity data. The private archive history still contains the previously classified operational files by deliberate recorded decision; it must remain private, and the eventual public repository must start from a single sanitized commit without inherited history.

- **2026-07-21 (replacement installer confirmed on clean machine):** The corrected installer and bundled synthetic matching dataset were exercised successfully on the fresh Windows machine. Installation, application startup, native Classes and Swimmers file dialogs, matching-data selection, and the tested application workflow now work on that machine; uninstall through Windows Settings and AppData retention were confirmed in the preceding pass. The clean-machine installer gate is complete. Testing on additional clean Windows machines remains useful compatibility coverage, but is tracked as follow-up validation rather than a blocker for proceeding to GitHub/release readiness.

- **2026-07-21 (clean-machine installer feedback and native dialog repair):** A fresh Windows-machine test confirmed that the application installs, launches without a Python dependency, and uninstalls through Windows Settings while retaining its AppData. The test also found that the Classes and Swimmers `Select/Change file` buttons did not open Windows File Explorer. Diagnosis against the packaged runtime showed `window.AquaDesktop` was absent because the sandboxed preload tried to `require()` the local `ipc_contract.cjs`; Electron sandboxed preloads permit only a limited built-in module set, so the entire bridge aborted. The preload now remains single-file with the narrow dialog channel inlined while main-process purpose, extension, and path validation remain unchanged. The packaged-renderer smoke now asserts that the native bridge exists and that its IPC handler responds, closing the coverage gap where the test previously posted a selected path directly to the backend. The replacement installer rebuilt successfully; package audit passed (1,579 backend entries, 35 SBOM components), all 29 desktop tests passed, and direct Windows UI verification opened both `Select classes data` and `Select swimmers data` native dialogs. Final clean-machine release approval remains open until this replacement installer is retested; manual installation-directory data-location inspection was not performed in the first test.

Add short dated entries here so future developers and AI tools can resume without repeating discovery.

- **2026-07-19 (renderer workflow automation):** Added a repeatable Playwright Core harness for the real packaged Electron renderer (`npm run smoke:renderer`). It launches the packaged executable with disposable app data, waits for authenticated backend readiness, selects the bundled classes input, generates and renders results, opens a match/profile review, verifies XAI overview and Match Explorer, submits an instructor CSV through import preview, and resolves the actual PDF/CSV export controls before checking their downloaded bytes. The first full run uncovered a release-blocking API/UI contract defect: solver-owned filesystem paths were exposed as browser URLs and the frontend's `filled_classes_export` key did not match `classes_filled`; PDF returned 404 and CSV was unwired. `backend.services.result_files` now exposes only known, existing job artifacts as authenticated `/jobs/{job_id}/{filename}` URLs and supplies the compatibility alias, both on generation and latest-result reload. The rebuilt packaged application passed the complete workflow in 39.2 seconds with 9 match rows, 11 assigned swimmers, a 3,444-byte PDF, and a 1,583-byte CSV; screenshots were inspected and Electron/backend both exited without orphans. Clean-machine install/uninstall behavior remains a manual release gate.
- **2026-07-19 (license/SBOM closure):** Closed the Phase 5 third-party-license gate. `requirements-runtime-lock.txt` now records the complete exact Python 3.14/Windows dependency graph behind the direct runtime requirements, and the deterministic notice generator inventories all 30 direct/transitive Python packages with reviewed SPDX expressions alongside Electron and vendored web assets. Every backend build validates both the installed versions and dependency closure, collects every wheel `LICENSE`/`COPYING`/`NOTICE` file plus Python's own license, and generates a deterministic CycloneDX 1.6 `SBOM.cdx.json`. Electron packages those files under `resources/`; package verification checks the SBOM format, complete Python component count, and every referenced license path. A clean isolated dependency installation generated 35 SBOM components and 52 license/notice files; the frozen backend and unsigned NSIS installer rebuilt successfully, with 29 desktop tests and package verification passing. The complete repository suite passed with 643 tests and 2 expected environment-gated skips; Ruff, notice drift, JavaScript syntax, and `git diff --check` were clean. Remaining Phase 5 exit work is clean-machine installer execution, renderer-level workflow coverage, and uninstall data-preservation verification.
- **2026-07-19 (later):** First real CI executions after pushing the seventh wave surfaced and fixed five latent environment bugs: `jinja2` was missing from `requirements.txt` (only present incidentally in the local venv; now pinned at 3.1.6 and added to the third-party notices); three Ubuntu-only test failures (backslash request-path normalization now handled on every platform in `StorageService.resolve_from_root`, the XAI `TemplateResponse` call migrated to the modern Starlette signature — which also removed the long-standing deprecation warning — and the committed-demo byte comparison now normalizes CRLF/LF); and a Windows cross-drive failure where `os.path.relpath` in the solver wrapper raised `ValueError` when the job directory (temp drive C:) and `app_root` (checkout drive D:) differ — the contract path now falls back to an absolute POSIX path, which `resolve_from_root` accepts. Packaged-smoke failures now attach a bounded, redacted backend log tail and job `result.json` error fields, which is how the cross-drive bug was diagnosed. As of `e181d87`, CI, Secret scan, and the new `windows-package` workflow all pass on `dev`; the Windows job builds the frozen backend and NSIS installer in ~5.5 minutes and uploads both artifacts (installer ~148 MB, unpacked ~192 MB compressed) with 10-day retention.
- **2026-07-19:** Seventh parallel migration wave removed runtime network dependencies, automated packaged-workflow smoke coverage, and added Windows release CI. Chart.js 4.5.1 (MIT) and Fontsource Outfit/JetBrains Mono 5.3.0 (OFL-1.1) are now vendored under `frontend/` with licenses registered in the third-party notice generator's drift check, replacing the jsDelivr and Google Fonts references; the CSP `script-src` is now `'self'` only, `.woff2` gets a correct MIME type, and seven new offline-asset tests scan every served HTML/CSS/JS file for remote runtime references. A reusable packaged smoke (`packaging/smoke/packaged_smoke.py` + pytest wrapper, skipping cleanly when artifacts are absent) drives the frozen backend end-to-end with a disposable app-data directory: readiness, token auth, demo generation (9 matches, 0 unassigned), latest-result retrieval, XAI page and API, instructor export, import preview, and authenticated shutdown — verifying no orphan processes, a byte-identical installation tree, and all writes under temporary app data with tokens/paths redacted. An opt-in Electron GUI smoke plus a validated `AQUA_USER_DATA` override (with a new desktop unit test) launches the real packaged GUI against a disposable profile and confirmed backend child startup, graceful close, no orphans, and user-data isolation against the rebuilt artifact. A new SHA-pinned, least-privilege `windows-package` GitHub Actions workflow builds the frozen backend and NSIS installer on `windows-latest`, smoke-tests the frozen executable with the runner's Python scrubbed from its environment, runs the packaging-contract and packaged-smoke pytest suites, and uploads unsigned installer/unpacked artifacts with 10-day retention; `ci.yml` gained explicit `permissions` and `concurrency`. The package was rebuilt after integration (installer 150,865,750 bytes; unpacked 532,075,358 bytes) and re-verified. Integrated verification: 639 Python tests passed, two skipped (Windows symlink permission; env-gated GUI smoke, which passed when enabled), one pre-existing Starlette deprecation warning; 29 desktop Node tests passed; Ruff, package verification, notice drift, JavaScript syntax, YAML validation, and `git diff --check` clean. Honest gaps: the CI runner is not a true clean machine and never executes the NSIS installer; renderer-level UI interaction, install/uninstall automation, uninstall data preservation, signing, branding, and transitive SBOM/license closure remain open; the first real `windows-package` run happens on GitHub.
- **2026-07-19:** Sixth parallel migration wave assembled and smoke-tested the first complete Windows Electron package. Packaged mode now launches `resources/backend/aqua-backend.exe` directly with no system-Python dependency, while source mode retains `start.py`; missing-executable failures are bounded and path-redacted. Electron-native save dialogs now mediate CSV/PDF exports with extension/path validation, safe suggested names, and cancellation/error handling. External navigation is denied by default and only exact HTTPS paths under the approved Aqua Essence GitHub repository open through the operating-system browser. Electron Builder 26.15.3 produces an NSIS installer and unpacked x64 application, includes the frozen backend plus project/third-party/Chromium notices, and verifies that operational/private/runtime/test paths are absent. The integrated installer is 150,684,059 bytes and the unpacked application is 531,740,981 bytes. A real packaged GUI smoke launched with disposable `userData`, rendered the Matching UI with `Host online`, and shut down cleanly without orphaned Electron/backend processes; runtime `data/`, `jobs/`, `logs/`, `resources/`, and `settings/` were created only beneath the supplied application-data directory, not the installation directory. Integrated verification: 631 Python tests passed, one Windows symlink-permission test skipped, one pre-existing Starlette deprecation warning; all 28 desktop Node tests passed; Ruff, package structure, license-notice drift, JavaScript syntax, and `git diff --check` passed. The artifacts remain unsigned and use Electron's default icon. Clean-machine installation, complete workflow testing, offline removal of CDN dependencies, automated packaged-app CI smoke, transitive license/SBOM closure, signing, and branding remain open.
- **2026-07-19:** Fifth parallel migration wave produced and exercised the frozen Python backend boundary. PyInstaller 6.21.0 on Python 3.14 now builds a Windows onedir artifact from a pinned packaging requirements file and explicit spec. The clean integrated artifact is 159.8 MiB / 1,448 files; it bundles frontend/XAI assets, public reference tables, the canonical synthetic demo, solver modules, `core/flag_vocabulary.json`, and nine required OR-Tools DLLs totaling 69.54 MiB. Private/runtime paths and pytest, Faker, Flask, HTTPX, Ruff, plus unused optional database/scientific/web stacks are excluded. Frozen generation self-dispatches the same executable with `--solver-worker`, preserving subprocess isolation without installed Python; the packaged worker completed the bundled demo with 9 matches and 0 unassigned. The reusable process harness also started the packaged executable, observed readiness, authenticated shutdown, and confirmed exit with all writes under temporary app data. `THIRD_PARTY_NOTICES.md` and its deterministic verifier document the direct runtime license boundary; no incompatible direct license was found, but a resolved transitive Python lock/artifact SBOM and shipping Electron's version-matched Chromium notices remain release gates, so the final third-party-license packaging checkbox stays open. Integrated verification: 631 Python tests passed, one Windows symlink-permission test skipped, one pre-existing Starlette deprecation warning; 19 desktop Node tests passed; Ruff, notice drift, JavaScript syntax, and `git diff --check` clean. The ignored packaged artifact was rebuilt locally and is not committed.
- **2026-07-19:** Fourth parallel migration wave introduced the source-mode Electron boundary. `desktop/` now pins Electron 43.1.1 with a genuine npm lockfile and zero reported audit vulnerabilities. The main process passes Electron `userData` to Python, creates a per-launch token and loopback port, waits for the real FastAPI readiness contract before creating a hardened sandboxed BrowserWindow, injects authentication only for the exact backend origin, redacts token/repository/user-data paths from bounded startup diagnostics, blocks in-app external navigation/window creation, and owns graceful-to-forced backend shutdown. A frozen preload exposes only a validated native input-file dialog; every purpose/extension/path is checked again in the main process and backend, while source-browser mode retains its development fallback. FastAPI now rejects non-loopback and malformed Host headers before readiness/auth/routes and intentionally emits no cross-origin permission headers because Electron loads the UI same-origin. Integration review caught and fixed an initial `ready: true` versus `status: "ready"` contract mismatch. Still open: an Electron-native save/export dialog, an explicit external-link host allowlist, bundled Python/PyInstaller packaging, and a real packaged GUI smoke test. Combined verification: 616 Python tests passed, one Windows symlink-permission test skipped, one pre-existing Starlette deprecation warning; 19 desktop Node tests passed; Ruff, desktop/frontend JavaScript syntax, and `git diff --check` clean. The installed Electron 43.1.1 binary was verified in the isolated track and `npm audit` reported zero vulnerabilities.
- **2026-07-18:** Third parallel migration wave completed the remaining source-backend persistence boundary. SQLite now uses ordered transactional migrations with `PRAGMA user_version` (current schema v2), preserves and upgrades unversioned databases, safely retries a rolled-back migration, and rejects databases created by a newer app version without modifying them; upgrade/backup behavior is documented. Runtime retention is centralized at 30 days for application-owned `job_<32 lowercase hex>` directories and 14 days for logs, supports non-negative environment overrides, and skips symlinks, malformed names, and paths outside the application-data root. Settings interruption tests prove a failed atomic replacement preserves the last complete file, while SQLite transactions protect multi-row writes and schema/version changes. A reusable real-process harness now starts `start.py` on loopback with a mandatory temporary data root and per-launch token, verifies readiness/authentication/restart/token rotation/shutdown and source-tree write isolation, captures bounded redacted failure diagnostics, and guarantees terminate/kill fallback. It remains a source-process harness, so the separate packaged-backend harness gate stays open until PyInstaller/Electron artifacts exist. Combined verification after integration: 606 tests passed, one Windows symlink-permission test skipped, one pre-existing Starlette `TemplateResponse` deprecation warning; Ruff clean, all frontend JavaScript passed `node --check`, and `git diff --check` clean.
- **2026-07-18:** Second parallel migration wave integrated across four isolated tracks. Data layout: all tracked synthetic entities now live under `examples/demo/{matching,database}/`, legacy `data/app_samples/` selections migrate safely, and the matching fixture is reproducible byte-for-byte from seed 42. Frontend: Matching and Explainability share primary navigation, Explainability becomes available when results exist, and the duplicate hidden XAI launcher was removed after auditing conditional controls. Desktop security: a per-process capability token uses `AQUA_LAUNCH_TOKEN` and `X-Aqua-Launch-Token`, constant-time validation, generic 401 responses, and protects API/job/XAI routes while health/readiness remain available; absent configuration preserves source-browser development. Process lifecycle: solver children are registered, terminated with a two-second grace period, force-killed if necessary, reaped on timeout and FastAPI lifespan shutdown, and the ownership contract is documented in `docs/desktop-process-lifecycle.md`. Electron must still inject the header, pass its `userData` directory, and exercise these contracts in a packaged process harness. Visual browser smoke was unavailable during the XAI track, so the browser-level smoke item remains open. Combined verification after integration: 593 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning), Ruff clean, all frontend JavaScript passed `node --check`, and `git diff --check` clean.
- **2026-07-18:** First parallel migration wave integrated across four isolated branches. Frontend CSS: deleted the 2,483-line `frontend/styles.css` and split its byte-order-preserved cascade into `styles/{base,results,overlays,sessions,instructor-editor}.css`, with load-order/static-cache contract tests. Desktop launch boundary: `start.py` now supports explicit `--port N`, `--port 0` for an OS-selected random port, retains legacy positional/`PORT` forms, centralizes loopback-only binding through `LOOPBACK_HOST = "127.0.0.1"`, and exposes lifecycle-aware `GET /api/ready` (503 before/after lifespan, 200 only while ready). CI: `.python-version` pins the supported packaging interpreter to Python 3.14, CI consumes it and `requirements-dev.txt`, action versions are SHA-pinned, and a checksum-verified/redacted Gitleaks workflow scans committed history without artifact or PR-comment permissions. Release hygiene: current guides were corrected for the sole FastAPI/CP-SAT architecture, dated audits are explicitly historical snapshots, and `docs/privacy-and-data-retention.md` documents local storage, manual deletion, and clean-public-release rules. Remaining decisions include automatic retention/cleanup and a user-facing delete-all-data control; the Gitleaks download/scan still needs its first real GitHub Actions run, and visual browser smoke coverage remains open. Combined verification after integration: 578 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning), Ruff clean, all frontend JavaScript passed `node --check`, and `git diff --check` clean.
- **2026-07-18:** Settings/file frontend modularization completed the broad Phase 3 `frontend/app.js` split: added `frontend/settings_files.js`, an IIFE-owned classic script exposing the frozen `window.AquaSettingsFiles` namespace. Host settings requests, JSON POST handling, guarded file picking, file metadata rendering, browse/reset/clear wiring, reference-option loading, instructor DB/file-source switching, and settings-driven UI refresh moved behind that boundary. `app.js` now acts primarily as shell/bootstrap and dropped from 486 to 222 lines; `generate_flow.js` and `instructor_editor.js` now consume the explicit namespace instead of ambient helper globals. Script-order, ownership, security-header/static-serving, and delegation tests were updated; the already separate `generate_flow.js` and `instructor_editor.js` satisfy the explicit-flow item. Verified: all frontend scripts pass `node --check`, Ruff clean, `git diff --check` clean, and the complete root suite passes with 572 tests (one pre-existing Starlette `TemplateResponse` deprecation warning). A local isolated backend returned health 200, but the in-app browser environment could not reach the host localhost, so the browser-level smoke-test checklist item remains open.
- **2026-07-18:** Profile/review drawer frontend modularization executed (next incremental Phase 3 item "split `frontend/app.js` into feature modules"): added `frontend/profile_drawer.js`, an IIFE-owned classic script exposing the frozen `window.AquaProfileDrawer` namespace. Drawer state and lifecycle, safe DOM-based swimmer/instructor profile rendering, review-detail cards, flag normalization/severity helpers, age/name formatting, latest-result state, delegated result-table clicks, and keyboard interactions moved behind that boundary. `generate_flow.js` now calls the explicit namespace instead of relying on implicit globals, and `app.js` only initializes the module. `app.js` dropped from 818 to 486 lines. Updated script ordering, frontend ownership/security assertions, and static-asset cache coverage. The broad modularization checkbox remains open for the smaller settings/file/lifecycle responsibilities still in `app.js`. Verified: all frontend JavaScript passes `node --check`, `git diff --check` passes, Ruff clean, and all 569 tests pass (one pre-existing Starlette `TemplateResponse` deprecation warning). A real backend and browser smoke test confirmed the app loads with the host online, `/profile_drawer.js` is present, and no JavaScript console errors occur; the cached workspace state exposed no visible result rows, so profile/review click behavior was not exercised live in this pass.
- **2026-07-18:** Instructor-defaults frontend modularization executed (next incremental Phase 3 item "split `frontend/app.js` into feature modules"): added `frontend/instructor_defaults.js`, an IIFE-owned classic script exposing the frozen `window.AquaInstructorDefaults` namespace. Default-instructor profile state, option loading/fallback behavior, save/reset actions, style/color editor state and rendering, API calls, modal lifecycle, filtering, and event wiring moved behind that boundary; `app.js` injects its shared request/settings/path/reference helpers before the initial UI refresh and delegates later default-profile refreshes to the module. `app.js` dropped from 1,223 to 818 lines. Updated script ordering, frontend ownership assertions, and static-asset cache coverage. The broad modularization checkbox remains open for the remaining cohesive `app.js` features. Verified: `app.js` and `instructor_defaults.js` pass `node --check`, `git diff --check` passes, Ruff clean, and all 566 tests pass (one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Frontend reference-editor modularization executed (incremental Phase 3 item "split `frontend/app.js` into feature modules"): added `frontend/reference_editors.js`, an IIFE-owned classic script exposing only `window.AquaReferenceEditors.wireReferenceEditors()`. Rankings and reference-table editor state, rendering, validation, drag/reorder behavior, API calls, modal lifecycle, and event wiring moved behind that boundary; `app.js` injects only `postJson`, `getFileNameFromPath`, and `refreshUiFromHost`. `app.js` dropped from about 2,051 to 1,223 lines; no ES modules, bundler, API, CSS, or dialog-markup changes were introduced. Updated frontend source assertions and static-asset cache/content-type coverage. Verified: both JavaScript files pass `node --check`, Ruff clean, 546 tests passed, and a real backend using an isolated temporary application-data root passed browser checks for editor loading, swimmer-type switching, existing-item reordering and persistence, reference add/edit/delete validation, hidden non-response type filtering, modal cancel/Escape handling, Manage Instructors coexistence, and `/reference_editors.js` no-cache serving. No new JavaScript console errors appeared; the existing blocked Google Fonts CSP request and missing favicon remain. Live testing also confirmed a pre-existing rankings endpoint contract defect outside this extraction: `/api/rankings_editor/load` omits the singular/plural/lookup metadata expected by the UI, and newly added ranking items round-trip as `None`; existing-item reorder/save works. The broad modularization checkbox remains open for the other cohesive `app.js` features.
- **2026-07-18:** Repository interface executed (final Phase 3 backend item "keep database operations behind a narrow repository/service interface"): added `backend/services/repository.py` with `SqliteRepository`, the single sanctioned database entry point for the application — constructor takes the database path and initializes the schema (replacing the module-level `_db_init(DB_PATH)` in `backend/server.py`), methods delegate to `backend.db` grouped by concern (sessions/pairings, instructors, imports). `ApplicationServices` gained a `repository` field built in `create_application_services()` from `paths.database_path`. The instructors/sessions/settings-files router dependency containers replaced their 17 individual `_db_*` callables with the one `repository` field; `GenerationDependencies` keeps its four narrow callables, now wired to repository bound methods. `backend/server.py` no longer imports `backend.db` at all (the 24-name import block is gone; two of those names were dead imports). Known limitation documented in the module: `backend.db` still holds a process-wide connection path, so the repository is a facade today — making `backend.db` connection-scoped can now happen behind this interface without touching consumers. Added `backend/tests/test_repository.py` (schema init, session and instructor roundtrips, subprocess proof the repository module does not import `backend.server`). Verified: Ruff clean, 533 tests passed (529 + 4 new; one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Storage service extraction executed (Phase 3 item "extract path and storage rules into a storage service"): added `backend/services/storage.py` with `StorageService`, a frozen dataclass bound to explicit roots (`app_root`, `app_data_root`, `writable_resources_dir`, `settings_path`, `default_file_paths`) that owns path resolution (`resolve_from_root`, `file_exists_from_root`, `normalize_path_for_request`, `is_repo_sample_or_generated_path`), atomic settings persistence (`read_settings_payload`/`save_settings` with the `.tmp` + `os.replace` pattern), legacy bundled-path migration, and copy-on-write provisioning (`provision_for_edit`). The generic `read_csv_file`/`write_csv_file` helpers moved there too. `backend/server.py` keeps same-named thin wrappers that build the service per call from the current module constants, so existing test seams (`patch("backend.server.save_settings")`, monkeypatched `APP_ROOT`/`APP_DATA_ROOT`/`SETTINGS_PATH`/`DEFAULT_FILE_PATHS`) are unchanged — the same pattern used for the SolverRunner extraction. Added `backend/tests/test_storage_service.py` (11 direct tests: path resolution, atomic settings roundtrip, migration rules, copy-on-write vs external files, CSV roundtrip, and a subprocess proof that importing the storage module does not import `backend.server`). Verified: Ruff clean, 529 tests passed (518 + 11 new; one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** FastAPI application factory and explicit runtime state executed: added `backend/application.py` with `BackendPaths`, `ApplicationState`, and `ApplicationServices`. `backend.server.create_app()` now owns lifespan/watchdog startup, middleware, XAI mounting, dependency-router assembly, and API/static route registration; `backend.server:app` remains only the ASGI compatibility instance. Settings, generation throttling, last-job selection, heartbeat, and shutdown coordination are owned by each app's `app.state.services.state`, not module-wide mutable globals. Existing tests now patch the container seams, and new factory tests prove independently created apps do not share settings, job, or generation state. Verified: Ruff clean, 518 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Generation orchestration and router decoupling executed: added `backend/services/generation_service.py`, whose explicit `GenerationDependencies` own job creation, input preparation, historical-pairing handling, solver execution/result parsing, annotation/profile generation, and persistence without importing FastAPI or `backend.server`. Added a thin `backend/routers/generation.py` HTTP adapter. All four extracted routers now receive narrow dependency dataclasses/callbacks rather than the complete server module; the generation endpoint's former 414-line orchestration block was removed from `backend/server.py`. Added direct service tests for validation failure and successful persistence, and retained endpoint behavior tests. Verified that importing `GenerationService` does not import `backend.server`; Ruff clean, 515 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Read-only bundled-resource provisioning executed: added `backend/services/resource_provisioner.py`. When `AQUA_APP_DATA_DIR` differs from `APP_ROOT`, the eight non-empty bundled default CSVs are copied once to `<app-data>/resources/data/{app_samples,source}/`; existing copies are never overwritten, preserving user edits across launches/upgrades. Default and legacy `data/source/...` / `data/app_samples/...` settings migrate to these writable copies. Ranking saves, reference-table load/save, and instructor style/color load/save now call `get_writable_setting_path()`, which copy-on-writes any bundled CSV selected for editing and updates settings atomically; explicitly selected external files remain in place. Source-development mode retains its historical workspace behavior. `docs/RUN_APP.md` documents the layout and semantics. Added provisioning, no-overwrite, external-file, legacy-migration, backend-startup, and real FastAPI endpoint immutability tests. Verified: Ruff clean, 513 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Configurable application-data root executed: added `core/app_paths.py` with the `AQUA_APP_DATA_DIR` runtime contract and a single derived layout for `data/aqua_essence.db`, `settings/user_settings.json`, `jobs/`, and `logs/`. `backend/server.py` now keeps read-only application resources (`frontend/`, `solvers/`, bundled reference files) rooted at `APP_ROOT` while all application-managed runtime paths derive from `APP_DATA_ROOT`. `core/aqua_logging.py` follows the same root while preserving the more-specific `AQUA_LOG_DIR` override. `start.py` accepts `--data-dir PATH`, documented in `docs/RUN_APP.md`. Added pure path tests, logging precedence tests, and a fresh-process backend integration test proving a supplied temporary root receives the database and runtime directories while resources remain separate. Source development still defaults to the workspace for backward compatibility; Electron must later pass its platform `userData` directory. Read-only/copy-on-write provisioning for editable bundled reference tables remains open. Verified: Ruff clean, 507 tests passed (one pre-existing Starlette `TemplateResponse` deprecation warning).
- **2026-07-18:** Dependency split executed (Phase 2 "Dependencies and packaging metadata"): `requirements.txt` now holds runtime-only deps (ortools, pandas, fastapi, uvicorn, python-multipart, reportlab); new `requirements-dev.txt` includes the runtime set plus pytest, httpx, faker, and ruff (previously used but undeclared). Development happens on Python 3.14 — noted in the requirements header; the formal supported-version pin for desktop packaging remains a Phase 5 decision. `docs/RUN_APP.md` documents both installs. Verified: Ruff clean, 500 tests passed.
- **2026-07-18:** Data-generation overwrite guard executed (Phase 2 item "prevent data-generation scripts from overwriting canonical business/reference data"): `generate_reference_data.py` now keeps existing files in `data/source/` by default and only overwrites with an explicit `--force` (CLI) / `force=True` (API). `run_all.py` therefore can no longer clobber the canonical reference tables — or anything else in `data/source/` — as a side effect. Added `data_generation/tests/test_reference_overwrite_guard.py` (keep/force/write-when-missing). Verified: Ruff clean, 500 tests passed, and a live `python data_generation/generate_reference_data.py` run left every `data/source/` file byte-identical (checksummed).
- **2026-07-18:** PR 10 (SolverRunner extraction) executed: `run_solver`, `read_solver_result`, and `parse_and_validate_solver_result` moved to `backend/services/solver_runner.py` (new `backend/services/` package). The service takes an explicit `logger` argument and has no server dependency; the solver timeout is now the named constant `SOLVER_TIMEOUT_SECONDS = 300`. `backend/server.py` keeps same-named thin wrappers so call sites and test patches (`patch("backend.server.run_solver")`) are unchanged. Verified: Ruff clean, 497 tests passed.
- **2026-07-18:** PR 9 (first Phase 3 increment) executed: removed all `_HAS_DB`/`_HAS_XAI`/`_HAS_CSV_IMPORT`/`_HAS_ISCE`/`_HAS_LOGGING` degradation branches. `backend/server.py` now imports xai_router, csv_import, spreadsheet_import, db, instructor_source_editor, and core.aqua_logging as required modules — a missing component fails at startup instead of silently disabling features. DB init, XAI mount, partner CSV auto-conversion, DB historical pairings, and session persistence are unconditional; routers (instructors/sessions/settings_files) lost their per-endpoint "Database not available" 503 guards. No test asserted the degraded paths. Verified: Ruff clean, 497 tests passed, live boot check (health/sessions/instructors/xai all 200, no console errors).
- **2026-07-18:** PR 8 (single-solver simplification) executed per the CP-SAT-only decision: removed `/api/solvers` + `/api/set_solver` endpoints, `active_solver` settings handling, manifest discovery/reading (`solvers/python_cpsat/manifest.json` deleted), `.bat`/`.cmd`/`.exe` branches in `run_solver` (Python entry only), the frontend solver picker (app.js functions, index.html markup, styles.css rules), and `backend/tests/test_solver_discovery.py`. Generate now resolves a fixed `SOLVERS_DIR / "python_cpsat" / "solver_wrapper.py"`; tests inject fakes by patching `SOLVERS_DIR` with a `python_cpsat/solver_wrapper.py` inside. Verified: Ruff clean, 497 tests passed (503 − 6 discovery tests), and a live browser check — app loads with no console errors, no picker, `/api/solvers` 404, `/api/health` 200.
- **2026-07-18:** PR 7 (reference-table consolidation) executed: the five reference tables (`personality_colors`, `instructor_styles`, `swimmer_types`, `swimmer_type_color_rankings`, `swimmer_type_style_rankings`) were byte-identical between `data/source/` and `data/app_samples/`; `data/source/` is now the single canonical copy. Deleted the `app_samples` duplicates; `make_default_settings()` and tests (`test_data_loader_class_schema`, `test_csv_import`, removed duplicate `test_non_response_type_exists_in_app_samples_csv`) now read `data/source/`. Local `settings/user_settings.json` paths migrated in place. `data/app_samples/` retains only entity files (classes/swimmers/instructors/historical_pairings) as test fixtures and first-run samples. Still open from the Phase 2 data-layout list: guard data-generation scripts against overwriting `data/source/`, and the writable-paths/app-data-root work. Verified: Ruff clean, 503 tests passed.
- **2026-07-17:** PR 6 executed: untracked `data/legacy/` and `reference/` (files kept on disk, both gitignored) after inspecting contents. `reference/combined.xlsx` contains a Jackrabbit class-export sheet with an Instructors column — reclassified as potentially real operational data, must never be committed. `Rankings.xlsx` content is fully transcribed in the tracked ranking CSVs. Legacy CSVs were the superseded compatibility-matrix format. Provenance recorded in `docs/reference-data-provenance.md`. Verified: Ruff clean, 504 tests passed.
- **2026-07-17:** PR 5 executed: ported the Flask-only XAI coverage to FastAPI as `backend/tests/test_xai_functional.py` (real DataManager/WhatIfEngine against a sample job dir: index HTML, matches+summary, match detail, swap, tune, overview shape, alternatives, 404s, `/shared/ui_utils.js` static). CSRF assertions already existed in `test_xai_router.py`; request-logging assertions already existed in `backend/tests/test_logging.py` (Flask `reload_failed` event is moot — the FastAPI reload endpoint is a no-op by design). Deleted `frontend/xai_dashboard/app.py`, `__main__.py`, and Flask-only tests (`test_app.py`, `test_csrf.py`, `test_logging.py`); removed `flask`/`flask-cors` from requirements.txt. Kept framework-agnostic tests (data_manager, what_if, dashboard JS, heartbeat). Verified: Ruff clean, 504 tests passed (513 − 19 Flask tests + 10 ported).
- **2026-07-17:** PR 4 executed: deleted `backend/desktop_host_pipeline.py` and `backend/tests/test_desktop_host_pipeline.py`. No production module imported the pipeline. Its roster-building (fuzzy class-name matching at prepare time) is a superseded design — the live fixed-roster path is `DataLoader` → `solvers/python_cpsat/engine/fixed_class_workflow.py`, covered by `test_data_loader_class_schema.py` — so no behavior or test assertions needed transferring. Verified: Ruff clean, 513 tests passed (baseline 515 minus the two deleted tests).
- **2026-07-17:** PR 3 executed: deleted `runtime_helpers/` (five modules duplicating `backend/`). Verified before deletion: no module outside the package imports it, and ignoring line endings plus the `runtime_helpers`→`backend` import rename, `backend/` copies were identical or strictly newer supersets (extra comments; `spreadsheet_import.xlsx_bytes_to_csv_text` exists only in `backend/`). Verified: Ruff clean, 515 tests passed. Note: root `CLAUDE.md` still describes `runtime_helpers/` — pending explicit approval to edit that file.
- **2026-07-17:** PR 2 executed: deleted broken `launch.pyw` (pointed at nonexistent `backend2.server`); `docs/RUN_APP.md` now documents `python start.py` as the primary launcher with `backend/server.py` as the direct alternative. Verified: Ruff clean, 515 tests passed.
- **2026-07-17:** PR 1 executed (staged, not committed): activated the `data/aqua_essence.db` ignore rule; untracked `data/aqua_essence.db`, `data/source/instructors.csv`, and `data/source/pairings.csv` via `git rm --cached` — the real files remain on disk unchanged and are now gitignored. Added `data_generation/generate_demo_source.py` (seed 42, deterministic) producing schema-compatible synthetic `examples/demo/instructors.csv` (25 rows) and `examples/demo/pairings.csv` (720 rows). Admin scripts (`scripts/import_pairings.py`, `scripts/enrich_instructors.py`) still default to the private `data/source/` paths, which continue to work locally. Verified: Ruff clean, 515 tests passed.
- **2026-07-17:** Data classified as real operational data (see Recorded Decisions). Confirmed `data/aqua_essence.db` was still tracked — the `.gitignore` rule was commented out. PR 1 scope: activate ignore rules, untrack operational data files, replace with seeded synthetic fixtures.
- **2026-07-17:** Initial read-only audit completed. Confirmed 515 passing tests and clean Ruff baseline. Identified tracked operational-data risk, broken `launch.pyw`, unused `runtime_helpers/`, unused desktop host pipeline, obsolete Flask XAI server, duplicated reference/sample data, and hidden single-solver abstraction overhead. No source files were modified during the audit.

