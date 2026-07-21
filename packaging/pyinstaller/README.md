# Frozen backend package

This directory builds the FastAPI backend as a Windows PyInstaller **onedir**
application. The directory form keeps native OR-Tools, pandas, and NumPy
libraries inspectable and is the intended input to the Electron packaging
stage.

## Build

Use the supported Python version in `.python-version` from the repository root:

```powershell
python -m pip install -r requirements-packaging.txt
./packaging/pyinstaller/build_backend.ps1
```

The ignored output is `.dist/pyinstaller/aqua-backend/`. Do not commit that
directory. The bundle contains the browser frontend, XAI templates/static
assets, public `data/source` lookup tables, the synthetic `examples/demo`
dataset, and the production Python CP-SAT solver sources. It intentionally
excludes tests, generated/runtime data, logs, settings, jobs, private
instructor/pairing files, and developer tools.

`requirements-runtime-lock.txt` pins the complete Python 3.14/Windows runtime
graph, while `requirements.txt` remains the direct dependency declaration. The
build rejects missing, stale, or differently installed lock entries. Before
PyInstaller runs it creates `.dist/pyinstaller-release-metadata/` containing a
CycloneDX 1.6 `SBOM.cdx.json`, Python's license, and every license/copying/notice
file exposed by every locked wheel. The Electron stage copies that directory
into the final application's `resources/` directory.

When a direct dependency changes, resolve `requirements.txt` on the supported
Python/Windows target, update every exact pin in
`requirements-runtime-lock.txt`, review any new license expression in
`scripts/generate_third_party_notices.py`, and regenerate
`THIRD_PARTY_NOTICES.md`. Never update the lock without reviewing the resulting
wheel license files and SBOM diff.

The spec explicitly collects OR-Tools' `.libs` directory. PyInstaller's
dependency scanner does not automatically locate `ortools.dll`,
`libprotobuf.dll`, and the Abseil DLL from the extension-module imports on
Windows; a package without these native files can start the host but cannot
load CP-SAT.

## Run and smoke test

The executable preserves the normal backend CLI contract:

```powershell
$env:AQUA_LAUNCH_TOKEN = "a-random-per-launch-secret"
./.dist/pyinstaller/aqua-backend/aqua-backend.exe `
  --port 8787 `
  --data-dir "$env:TEMP/aqua-essence-smoke" `
  --no-browser
```

Poll `GET http://127.0.0.1:8787/api/ready`, then send an authenticated
`POST /api/shutdown` with the token in the `X-Aqua-Launch-Token` header.
Always use a disposable `--data-dir` for packaging tests.

`backend.process_harness.BackendProcessHarness` accepts `backend_executable=`
to exercise this packaged lifecycle with the same bounded readiness,
authentication, diagnostics, restart, and shutdown behavior used by source
tests.

## Packaged solver worker

The backend executable is also the isolated solver-worker executable. Frozen
generation respawns it as:

```text
aqua-backend.exe --solver-worker request.json result.json
```

The spec explicitly collects the lazy worker dispatcher and production wrapper
alongside the solver engine and OR-Tools native libraries. After each clean
build, run the repeatable worker smoke test:

```powershell
python packaging/pyinstaller/smoke_solver.py `
  ./.dist/pyinstaller/aqua-backend/aqua-backend.exe
```

This uses only the bundled synthetic demo and a temporary job directory.
