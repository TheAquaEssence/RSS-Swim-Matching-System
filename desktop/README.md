# Aqua Essence Desktop Host

This package is the Electron shell for the FastAPI application. In source mode
it runs the repository's `start.py` with the supported Python runtime. In a
packaged Electron build it runs the bundled PyInstaller executable directly,
without relying on a system Python installation.

## Source development

From `desktop/`:

```powershell
npm ci
npm test
npm run check
npm start
```

Set `AQUA_PYTHON_EXECUTABLE` when the desired Python interpreter is not
available as `python.exe` on Windows or `python3` elsewhere.

## Packaged runtime layout

The Windows package must place the frozen backend at:

```text
resources/
└── backend/
    └── aqua-backend.exe
```

Electron validates that file before reserving a port or spawning a process. A
missing backend stops startup with a path-redacted reinstall message. The
packaged command invokes the executable directly; `AQUA_PYTHON_EXECUTABLE` is
source-mode only.

## Runtime contract

The main process:

1. Gets Electron's `userData` directory and passes it to Python as both
   `--data-dir` and `AQUA_APP_DATA_DIR`.
2. Selects a loopback port and generates a new capability token.
3. Starts `start.py`, polls the unauthenticated readiness endpoint, and creates
   the BrowserWindow only after the backend reports `status: "ready"`.
4. Adds the capability header only to requests for the exact backend origin.
5. Requests authenticated graceful shutdown and then uses bounded process
   termination if the backend does not exit.

The renderer has no Node.js access. Its frozen preload surface exposes only a
validated native input-file dialog. Raw IPC, filesystem access, and the launch
token are not exposed to renderer JavaScript.

The Electron installer assembly, code signing, and update support remain
separate packaging concerns.
