# How To Run The App

This project runs as a local desktop-style app:

- The **Python (FastAPI) backend** starts a local HTTP server.
- It opens your browser automatically.
- The frontend UI talks to the backend on `127.0.0.1`.

## Prerequisites

- Python 3.14 available on `PATH`. Python 3.14 is the tested development and
  desktop-packaging interpreter; `.python-version` is the canonical version
  pin used by CI and compatible version managers.

Install Python dependencies once:

```powershell
pip install -r requirements.txt
```

To also run tests and lint (contributors), install the development set instead:

```powershell
pip install -r requirements-dev.txt
```

## Run The App

From the workspace root:

```powershell
python start.py
```

`start.py` picks an available port (8787–8794 by default), starts the FastAPI
backend, and opens your browser. Options:

```powershell
python start.py 9000    # use a specific port
python start.py --port 9000       # explicit port (desktop-host form)
python start.py --port 0          # OS-selected random available port
python start.py --nb    # don't open the browser
```

(`start.py` is a thin CLI wrapper around the FastAPI app defined in
`backend/server.py` — there is only one server.)

What should happen:

- The app starts a local server on `http://127.0.0.1` using an available port in the `8787` to `8794` range.
- Your browser should open automatically.
- If the browser does not open, check the terminal output and open the printed URL manually.

You can also override the port with the `PORT` environment variable:

```powershell
$env:PORT=8787; python start.py
```

`PORT=0` has the same random-port meaning as `--port 0`. The backend always
binds to `127.0.0.1`, never to a LAN/public interface. Process hosts should
poll `GET /api/ready`; it returns HTTP 200 with `{"ok":true,"status":"ready"}`
only after application startup finishes. `GET /api/health` remains the basic
process-liveness endpoint.

### Desktop launch token

A desktop host should create a new cryptographically random capability token
for every backend process, pass it only through the child process environment,
and add it to backend requests using the `X-Aqua-Launch-Token` header:

```text
AQUA_LAUNCH_TOKEN=<new random token for this process>
X-Aqua-Launch-Token: <the same token>
```

The token must not be placed in a URL, command-line argument, log message, or
response. `backend.launch_auth.generate_launch_token()` is available to Python
process hosts; an Electron host can generate an equivalent value with a secure
random-number API. When configured, the token protects all `/api/*` operations
except `GET /api/health` and `GET /api/ready`, and all `/jobs/*` and `/xai/*`
content. This lets a host probe liveness and readiness before installing its
authenticated request handling. Omitting `AQUA_LAUNCH_TOKEN` deliberately keeps
the current unauthenticated source-development/browser workflow.

### Local HTTP trust boundary and CORS

The backend accepts only `Host: 127.0.0.1` or `Host: localhost`, with an
optional valid TCP port. Other and lookalike hostnames are rejected before
health/readiness handling, launch-token authentication, or application routes.
This complements loopback-only socket binding and prevents an arbitrary Host
header from being treated as part of the desktop application origin.

The packaged Electron UI is served by this FastAPI process and loaded from the
same loopback origin as its API. The backend therefore does not enable CORS or
emit `Access-Control-Allow-Origin`/credential permissions. Cross-origin API
access is intentionally unavailable; Electron should navigate to the backend
URL rather than a `file://` or separately hosted renderer. Source-browser
development follows the same same-origin model, so there is no broad CORS
development exception to accidentally carry into a desktop release.

### Runtime data directory

The source-development default stores runtime state in the workspace for
backward compatibility. You can redirect every application-managed writable
path to one separate directory:

```powershell
python start.py --data-dir "C:\path\to\AquaEssenceData"
```

The equivalent environment variable is useful for process hosts and future
desktop packaging:

```powershell
$env:AQUA_APP_DATA_DIR="C:\path\to\AquaEssenceData"
python start.py
```

The selected directory contains:

```text
AquaEssenceData/
├── data/aqua_essence.db
├── settings/user_settings.json
├── jobs/
├── logs/
└── resources/
    ├── data/source/
    └── examples/demo/matching/
```

Frontend assets, solver code, and bundled reference tables continue to load
from the application directory. When a separate runtime directory is used,
bundled CSVs that the UI can edit are copied once into `resources/data/` and
settings point to those writable copies. Existing copies are never overwritten,
so application upgrades do not erase user edits. External files explicitly
selected by the user remain in place. Electron will pass its platform-specific
`userData` directory through this same contract.

### Real-process host test harness

Desktop-shell and packaging tests can reuse `BackendProcessHarness` from
`backend.process_harness`. It launches the real `start.py` entry point on a
dynamically allocated loopback port, waits for `/api/ready`, supplies a fresh
launch token through the child environment, and performs bounded graceful and
forced shutdown. A writable application-data directory is mandatory:

```python
from backend.process_harness import BackendProcessHarness

with BackendProcessHarness(temporary_user_data_directory) as backend:
    response = backend.request("/api/settings")
    assert response.status == 200
```

Use `restart()` to verify a second launch against the same data root. Startup
exceptions include the backend's bounded output tail and exit code for useful
CI diagnostics; capability tokens are redacted and are never added to command
lines, URLs, or captured output. The harness disables child bytecode writes,
passes `--data-dir`, uses no shell, and always escalates from the authenticated
shutdown endpoint to terminate/kill within bounded timeouts.

The directory can contain children's personal information and staff records.
See [Privacy and Data Retention](privacy-and-data-retention.md) before using
operational exports. Application-created jobs expire after 30 days and logs
after 14 days by default. Override these limits with non-negative whole-day
values in `AQUA_JOB_RETENTION_DAYS` and `AQUA_LOG_RETENTION_DAYS`; `0` expires
eligible artifacts at the next cleanup. Cleanup never deletes source files or
exports selected outside the application-data directory.

The database schema upgrades automatically at startup using explicit SQLite
versions and transactional migrations. Back up the database while the app is
stopped before a schema-changing application upgrade; downgrade attempts are
rejected without modifying the database. See
[Database Schema Migrations](database-schema-migrations.md) for the complete
upgrade, failure, and recovery contract.

Settings use atomic replacement and database writes use SQLite transactions so
an interrupted application write does not expose a partial logical update. See
[Persistence and Crash Safety](persistence-safety.md) for guarantees and limits.

## First Run: Select Input Files

At minimum, you must select a `classes.csv` file in the UI before `Generate solution` becomes enabled.

Working synthetic demo files already exist in this repo:

- `examples/demo/matching/classes.csv`
- `examples/demo/matching/swimmers.csv`
- `examples/demo/matching/instructors.csv`
- `examples/demo/matching/historical_pairings.csv`

You can also use generated files here:

- `data/generated/classes.csv`
- `data/generated/swimmers.csv`
- `data/generated/instructors.csv`
- `data/generated/historical_pairings.csv`

Recommended first-run setup in the UI:

1. Click `Select file` for `classes.csv` and choose `examples/demo/matching/classes.csv`.
2. Open `Advanced inputs (optional)`.
3. The remaining inputs default to their writable copies of the corresponding
   `examples/demo/matching/` files; select those bundled files manually if you
   previously changed your settings.
4. Leave the solver as `Python CP-SAT Solver`.
5. Click `Generate solution`.

## Optional: Generate Fresh Data

If you want a fresh generated dataset instead of the sample files:

```powershell
python data_generation/run_all.py --seed 42
```

Then select the CSV files from `data/generated/` in the UI.

To reproduce the committed first-run demo instead, run
`python -m data_generation.generate_demo_matching --seed 42`. This command
intentionally refreshes `examples/demo/matching/`; ordinary generated data
continues to stay in the ignored `data/generated/` directory.

## Notes

- The app saves your last selected files in `<app-data>/settings/user_settings.json`.
- The Python solver is invoked directly — no `.bat` wrapper needed.

## Troubleshooting

- If you see `python is not recognized`, install Python and make sure it is on `PATH`.
- If the app opens but `Generate solution` stays disabled, `classes.csv` has not been selected yet.
- If no browser opens, manually visit the `http://127.0.0.1:<port>/` URL printed in the terminal.

---

## C++ Backend (Removed)

The original C++ backend was discontinued and removed from the `dev` branch.
`backend/` is the Python FastAPI host. The C++ sources are preserved on
`origin/main` for historical reference.
