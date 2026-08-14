# Architecture

## Product boundary

Aqua Essence is a local-first Windows desktop application. Electron packages
the existing web interface and manages a bundled FastAPI/CP-SAT backend; it
does not reimplement matching logic in Node.js.

```text
Electron main process
├── sandboxed renderer and validated preload bridge
└── bundled FastAPI process on 127.0.0.1
    ├── API routers and application services
    ├── SQLite/settings/job storage under Electron userData
    ├── XAI routes and static assets
    └── isolated CP-SAT solver worker
```

Source-browser development uses the same FastAPI application through
`python start.py`. The packaged application supplies a random loopback port,
per-launch capability token, and application-data root.

## Runtime sequence

1. Electron selects an available loopback port and creates a launch token.
2. It starts the frozen backend with its `userData` directory.
3. Electron polls `/api/ready` and creates the renderer only after readiness.
4. The renderer loads from the backend origin; authenticated requests receive
   the launch-token header in the trusted Electron boundary.
5. A generation request is validated and delegated to `GenerationService`.
6. `SolverRunner` launches the CP-SAT worker with a bounded timeout.
7. The worker writes the validated result and known report artifacts into its
   job directory.
8. FastAPI exposes only authenticated, allowlisted job artifacts and XAI data.
9. Closing the final window requests graceful shutdown, then uses bounded
   terminate/kill fallback for backend and solver children.

## Backend

`backend/server.py` is the composition root and FastAPI application factory.
It wires explicit state and services from `backend/application.py` into API
routers:

- `routers/generation.py` — solver generation and result retrieval
- `routers/settings_files.py` — settings and file selection
- `routers/instructors.py` — instructor CRUD/import/export
- `routers/sessions.py` — historical pairing sessions
- `xai_router.py` — explainability pages and APIs

Core services are separated by responsibility:

- `GenerationService` validates settings and orchestrates jobs.
- `SolverRunner` owns worker invocation, timeout, and process cleanup.
- `StorageService` owns path containment, settings persistence, and file I/O.
- `ResourceProvisioner` copies editable bundled resources into user data.
- Repository services keep database access behind narrow interfaces.
- `result_files.py` maps known result artifacts to authenticated URLs.

## Solver

Version 1 has one production strategy: the Python OR-Tools CP-SAT worker in
`solvers/python_cpsat/`. The three phases are:

1. continuity matching;
2. CP-SAT assignment optimization;
3. explanation and review-flag generation.

The worker process is an intentional crash and timeout boundary. Electron and
FastAPI must not duplicate or bypass solver hard constraints.

## Persistence

All installed-mode writes stay beneath the supplied application-data root:

```text
userData/
├── data/aqua_essence.db
├── settings/user_settings.json
├── resources/
├── jobs/
└── logs/
```

SQLite uses ordered transactional migrations through `PRAGMA user_version`.
Settings use atomic replacement. Job and log cleanup is restricted to
application-owned paths and skips symlinks and malformed entries. Detailed
contracts are in [database-schema-migrations.md](database-schema-migrations.md),
[persistence-safety.md](persistence-safety.md), and
[privacy-and-data-retention.md](privacy-and-data-retention.md).

## Security boundary

- Backend sockets bind only to `127.0.0.1`.
- Host headers are restricted to loopback names.
- Protected application, job, and XAI routes require the per-launch token in
  packaged mode.
- Renderer Node integration is disabled; context isolation and sandboxing are
  enabled.
- Navigation, popups, downloads, and file dialogs use validated allowlists.
- The packaged UI and API share one origin; broad CORS permissions are not
  enabled.
- Responses include CSP and defensive browser headers.

## External integrations

The separately versioned
[Jackrabbit Exporter](https://github.com/TheAquaEssence/jackrabbit-exporter)
integrates through a versioned JSON bundle containing CSV payloads. Aqua
Essence owns contract validation, conversion, and database import; it has no
runtime dependency on extension source code.
