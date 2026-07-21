# Windows Electron package

The Windows release combines the hardened Electron shell with the frozen
PyInstaller backend. `electron-builder` is pinned exactly in
`desktop/package-lock.json`; generated installers and unpacked trees remain in
the ignored `.dist/electron/` directory.

## Build

From the repository root, install the Python packaging requirements and run:

```powershell
python -m pip install -r requirements-packaging.txt
./packaging/electron/build_windows.ps1
```

The script builds the backend first, restores Node dependencies with `npm ci`,
runs desktop tests and syntax checks, creates an unpacked Windows application
and an NSIS installer, and audits the unpacked resource tree. For a deliberate
local rebuild, `-SkipBackend` or `-SkipInstall` can reuse an already verified
backend or `node_modules` directory.

Expected outputs:

- `.dist/electron/win-unpacked/Aqua Essence.exe`
- `.dist/electron/Aqua-Essence-Setup-<version>-<arch>.exe`

## Packaged renderer smoke

After building, run the critical operator workflow against the real packaged
renderer from `desktop/`:

```powershell
cd desktop
npm run smoke:renderer
```

The Playwright Core harness uses Electron's bundled Chromium (it does not
download another browser). It verifies backend readiness, input selection,
generation, rendered results, profile review, XAI overview and Match Explorer,
instructor import preview, authenticated PDF/CSV exports, and clean Electron
shutdown. Screenshots and export artifacts are retained under
`.dist/renderer-smoke-artifacts/`; runtime data is isolated under
`.dist/renderer-smoke-user-data/`. The harness deliberately previews rather
than commits the bundled instructor import, so repeated smoke runs do not alter
the test database's instructor records.

The resource audit requires the frozen backend, project license, complete
direct/transitive third-party notices, a CycloneDX 1.6 SBOM, the locked Python
wheel license bundle, Python's license, and Electron's version-matched
`LICENSE.electron.txt` and `LICENSES.chromium.html`. Every SBOM license pointer
must resolve inside the unpacked application. The audit also rejects operational databases, private
instructor/pairing CSVs, jobs, logs, settings, generated data, tests, and source
control metadata from the backend resource tree.

## Continuous integration

`.github/workflows/windows-package.yml` runs the full
`packaging/electron/build_windows.ps1` pipeline on `windows-latest` for pushes
to `dev`/`main` and for pull requests, then uploads the unsigned NSIS installer
and the unpacked application tree as build artifacts (10-day retention).

What the CI job proves:

- The frozen backend and Electron package build cleanly from a fresh checkout
  with pinned dependencies (`npm ci`, `requirements-packaging.txt`).
- Desktop unit tests, syntax checks, and the packaged-resource audit
  (`verify:package`) pass against the freshly built tree.
- The frozen `aqua-backend.exe` starts, serves `/api/ready`, and enforces
  launch-token auth with `PYTHONPATH`/`PYTHONHOME` unset and every
  Python-related directory stripped from the child `PATH` — so the executable
  demonstrably does not lean on the runner's system Python.
- Packaging-contract tests (`test_packaged_resources.py`,
  `test_third_party_notices.py`, `test_release_metadata.py`,
  `test_process_harness.py`) pass on Windows.

What it does **not** prove (future work):

- It is not a true clean-machine test: the runner has Python, Node, and build
  tooling installed. Only the child-process PATH stripping approximates their
  absence for the frozen exe itself.
- The NSIS installer is built but never executed — install, shortcuts,
  uninstall, and upgrade flows are unverified in CI.
- The Electron GUI is not launched in CI. The renderer workflow is automated
  for a local interactive Windows session with `npm run smoke:renderer`; CI
  exercises only the backend process contract.
- No code signing: CI produces unsigned artifacts only. Signing is a later
  release gate (see below) and no signing secrets exist in the repository or
  workflow.

## Signing warning

Local builds are intentionally unsigned. Windows SmartScreen can warn or block
an unsigned installer, and users cannot verify a publisher identity. Public
GitHub releases must add a protected code-signing identity to CI and sign both
the application executable and NSIS installer before publication. Never commit
certificate files or signing secrets.
