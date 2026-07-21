# Development Guide

This is the canonical contributor setup and engineering guide for Aqua
Essence. Tool-specific instruction files should point here instead of copying
architecture or command lists.

## Supported environment

- Windows is the supported desktop packaging platform for version 1.
- Python 3.14 is pinned in `.python-version` and used by CI and packaging.
- Node.js is required only for the Electron shell and its tests.

Create and activate a virtual environment, then install the development set:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Install the desktop dependencies when working on Electron or packaging:

```powershell
Set-Location desktop
npm install
Set-Location ..
```

## Run the application

```powershell
python start.py
```

Use `python start.py --nb` to suppress browser launch or `python start.py
--port 0` to request an operating-system-selected loopback port. See
[RUN_APP.md](RUN_APP.md) for the full launch, authentication, application-data,
and troubleshooting contracts.

## Verification

Run the same Python gates as CI:

```powershell
python -m ruff check .
python -m pytest -q solvers/python_cpsat/engine/tests/ core/scoring/tests/ core/tests/ backend/tests/ frontend/xai_dashboard/tests/ solvers/tests/ data_generation/tests/
```

Run desktop checks when Electron-owned files change:

```powershell
Set-Location desktop
npm test
npm run check
Set-Location ..
```

Packaging instructions and smoke-test commands live under `packaging/`.

## Architecture and ownership

- `backend/` owns the FastAPI host, services, persistence, and API routes.
- `frontend/` owns the main browser renderer and XAI assets.
- `solvers/python_cpsat/` is the sole production solver.
- `core/` owns shared scoring, flags, profiles, and logging.
- `data_generation/` and `examples/demo/` contain synthetic development data.
- `desktop/` owns the Electron process and trusted preload boundary.
- `packaging/` owns PyInstaller, Electron Builder, release metadata, and smoke
  harnesses.
- `scripts/` contains explicitly classified administrative and release tools;
  see `scripts/README.md` before using them.

The complete component and process boundaries are documented in
[architecture.md](architecture.md), with current product decisions in
[decisions.md](decisions.md). Matching policy belongs in
[matching-process-rules-and-guidelines.md](matching-process-rules-and-guidelines.md),
not in developer instruction files.

## Engineering rules

- Preserve the four hard constraints documented in the matching rules.
- Keep solver weights and thresholds in
  `solvers/python_cpsat/engine/config.py`.
- Use `Path.is_relative_to()` for containment checks.
- Keep settings writes atomic through the storage service.
- Add SQLite changes as ordered migrations; never edit a released migration.
- Register new solver flags in `core/flag_vocabulary.json`.
- Keep the CP-SAT worker in a separate process with bounded timeout and
  shutdown behavior.
- Keep Electron renderer isolation enabled and expose only validated preload
  operations.
- Add or update tests with behavior changes.

## Private-data rules

Operational swimmer, instructor, enrollment, medical, session, job, report,
and log data is private. Never place it in source control, fixtures, issues,
pull requests, prompts, screenshots, or build artifacts. Use synthetic data
and invented identifiers. See [privacy-and-data-retention.md](privacy-and-data-retention.md).

## Change workflow

Keep commits focused. Do not stage unrelated working-tree changes. Run the
relevant focused tests while iterating and the complete gates before
publishing. See the root [CONTRIBUTING.md](../CONTRIBUTING.md) for review and
security-reporting expectations.
