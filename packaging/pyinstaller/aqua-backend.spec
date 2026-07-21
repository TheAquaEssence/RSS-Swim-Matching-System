"""Windows directory-mode PyInstaller recipe for the FastAPI backend."""

from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


repo_root = Path(SPECPATH).resolve().parents[1]
ortools_binaries = collect_dynamic_libs("ortools")

# Only redistributable, read-only application resources belong in the bundle.
# Operational data, settings, jobs, logs, generated files, and tests are
# deliberately absent.
resource_trees = [
    Tree(str(repo_root / "frontend"), prefix="frontend", excludes=["tests", "__pycache__", "*.pyc"]),
    Tree(
        str(repo_root / "data" / "source"),
        prefix="data/source",
        excludes=["instructors.csv", "pairings.csv"],
    ),
    Tree(str(repo_root / "examples" / "demo"), prefix="examples/demo", excludes=["__pycache__", "*.pyc"]),
    Tree(
        str(repo_root / "solvers" / "python_cpsat"),
        prefix="solvers/python_cpsat",
        excludes=["tests", "engine/tests", "__pycache__", "*.pyc", "output"],
    ),
]

hiddenimports = [
    "backend.server",
    "backend.solver_worker",
    "solvers.python_cpsat.solver_wrapper",
    "uvicorn.lifespan.off",
    "uvicorn.lifespan.on",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
]
hiddenimports += collect_submodules(
    "solvers.python_cpsat.engine",
    filter=lambda name: ".tests" not in name,
)

excluded_modules = [
    "asyncpg",
    "cryptography",
    "dns",
    "faker",
    "flask",
    "httpx",
    "IPython",
    "jupyter",
    "lxml",
    "matplotlib",
    "notebook",
    "PIL",
    "psutil",
    "psycopg2",
    "pytest",
    "ruff",
    "scipy",
    "sqlalchemy",
    "tkinter",
    "trio",
    "watchdog",
    "watchfiles",
    "websockets",
    "werkzeug",
]

a = Analysis(
    [str(Path(SPECPATH) / "backend_entry.py")],
    pathex=[str(repo_root)],
    binaries=ortools_binaries,
    datas=[(str(repo_root / "core" / "flag_vocabulary.json"), "core")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aqua-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *resource_trees,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="aqua-backend",
)
