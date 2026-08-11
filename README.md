# Aqua Essence

Aqua Essence is a local-first desktop application that matches swimmers with
instructors for the Ready, Set, Swim! youth program. It combines continuity,
hard safety and qualification constraints, compatibility scoring, CP-SAT
optimization, and explainable review output.

Version 1 targets Windows and packages the existing web interface, FastAPI
backend, and Python solver inside an Electron application. Operational data
stays on the user's machine.

## Status

The application architecture and Windows package are implemented and tested,
including clean-machine installation and removal. The remaining public-release
gates are the GitHub Support purge of pre-rewrite pull-request refs and the
first tag-driven installer/checksum publication. Code signing is explicitly
deferred. See the [Electron migration and release checklist](docs/plans/2026-07-17-electron-migration-checklist.md).

## How it works

```text
Electron desktop shell
└── loopback-only FastAPI backend
    ├── local settings and SQLite persistence
    ├── generation and XAI APIs
    └── isolated Python CP-SAT worker
        ├── continuity pass
        ├── constrained assignment optimization
        └── explanations and review flags
```

The solver never relaxes these hard constraints:

- instructor capacity;
- adapted-capability routing;
- baby and adult qualification routing;
- paired-swimmer age and RSS-level compatibility.

See [Architecture](docs/architecture.md) and
[Matching Rules](docs/matching-process-rules-and-guidelines.md) for the full
contracts.

## Run the Electron desktop app from source

Python 3.14 and Node.js 24 are the supported development and packaging
versions. Install both dependency sets, then start Electron from the repository
root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
npm --prefix desktop ci
npm --prefix desktop start
```

Electron launches the FastAPI backend with browser opening disabled, waits for
readiness, and displays the same loopback-served interface inside a hardened
desktop window. Closing the window shuts down the backend.

For browser-only development, run `python start.py`; that command deliberately
opens the interface in the system's default browser. Use `python start.py
--no-browser` to start only the backend. The tracked synthetic demonstration
dataset under `examples/demo/` is safe for development and evaluation.
Detailed options are in [How to Run the App](docs/RUN_APP.md).

## Verify

```powershell
python -m ruff check .
python -m pytest -q solvers/python_cpsat/engine/tests/ core/scoring/tests/ core/tests/ backend/tests/ frontend/xai_dashboard/tests/ solvers/tests/ data_generation/tests/

Set-Location desktop
npm test
npm run check
```

Contributor setup and package-specific checks are documented in the
[Development Guide](docs/development.md).

## Repository map

| Path | Responsibility |
|---|---|
| `backend/` | FastAPI composition, API routers, services, persistence, security, and process management |
| `frontend/` | Main renderer, feature modules, styles, and XAI interface |
| `solvers/python_cpsat/` | Sole production matching engine and worker entry point |
| `core/` | Shared scoring, flags, profiles, and logging |
| `desktop/` | Electron main process, preload boundary, and desktop tests |
| `packaging/` | PyInstaller, Electron Builder, release metadata, and packaged smoke tests |
| `data_generation/` | Synthetic-data tooling |
| `examples/demo/` | Reproducible tracked demonstration data |
| `scripts/` | Classified administrative and release utilities |
| `docs/` | Current specifications, operations guides, plans, and historical records |

The Jackrabbit browser extension is maintained separately in the private
[TheAquaEssence/jackrabbit-exporter](https://github.com/TheAquaEssence/jackrabbit-exporter)
repository pending public-release review. The projects integrate through CSV
contracts only.

## Privacy and security

Operational swimmer, instructor, enrollment, medical, session, job, report,
and log data is private. Never commit it or place it in issues, pull requests,
prompts, screenshots, fixtures, or release artifacts. Use synthetic data and
invented identifiers.

- [Privacy and data retention](docs/privacy-and-data-retention.md)
- [Security policy](SECURITY.md)
- [Persistence safety](docs/persistence-safety.md)

## Documentation

- [Documentation index](docs/README.md)
- [User manual](USER_MANUAL.md)
- [Developer guide](docs/development.md)
- [Architecture](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Versioning policy](docs/versioning.md)

## License

Licensed under the [MIT License](LICENSE). Bundled dependency notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
