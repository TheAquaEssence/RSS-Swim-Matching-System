"""End-to-end smoke workflow for the packaged (PyInstaller-frozen) backend.

Runs the frozen ``aqua-backend.exe`` exactly the way the Electron shell does:
disposable application-data directory, per-launch capability token in the
environment, free loopback port. It then exercises a realistic workflow using
only the bundled synthetic demo dataset (``examples/demo``): generate matches,
read the latest result, open the XAI dashboard, export instructors, preview a
tiny synthetic instructors import, and finally request authenticated shutdown.

Isolation guarantees asserted by the run:
  * the installation directory is byte-for-byte untouched (file set, sizes,
    and mtimes are snapshotted before and after);
  * all runtime writes land under the disposable app-data directory;
  * neither the backend child nor any solver worker survives shutdown.

The launch token and absolute private paths are never included in log or
assertion text; failures reference file *names* and counts only.

Standalone use (from the repository root):

    python packaging/smoke/packaged_smoke.py [path\\to\\aqua-backend.exe]

This directory is intentionally not an importable package (the name would
shadow the PyPI ``packaging`` distribution); the pytest wrapper loads this
file by path.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from backend.process_harness import BackendProcessHarness  # noqa: E402
from core.aqua_logging import configure_component_logger  # noqa: E402

BACKEND_IMAGE_NAME = "aqua-backend.exe"
ELECTRON_IMAGE_NAME = "Aqua Essence.exe"
PACKAGED_BACKEND_CANDIDATES = (
    Path(".dist/electron/win-unpacked/resources/backend/aqua-backend.exe"),
    Path(".dist/pyinstaller/aqua-backend/aqua-backend.exe"),
)
GENERATE_TIMEOUT_SECONDS = 300.0
JSON_HEADERS = {"Content-Type": "application/json"}
SYNTHETIC_IMPORT_CSV = "instructor_id,first_name,last_name\n900001,Smoke,Tester\n"

LOGGER = configure_component_logger("packaging_smoke")


class SmokeFailure(AssertionError):
    """A smoke step failed. Messages contain no secrets or private paths."""


@dataclass
class SmokeReport:
    """Redacted, shareable outcome of one packaged-backend smoke run."""

    backend_variant: str = ""
    steps: list[str] = field(default_factory=list)
    match_count: int = 0
    unassigned_count: int = 0
    generate_seconds: float = 0.0
    total_seconds: float = 0.0
    backend_exit_code: int | None = None
    install_tree_files: int = 0

    def record(self, step: str) -> None:
        self.steps.append(step)
        LOGGER.info("Smoke step passed", extra={"event": "smoke_step", "route": step})

    def summary(self) -> str:
        lines = [
            f"packaged backend smoke ({self.backend_variant})",
            *(f"  ok: {step}" for step in self.steps),
            f"  matches={self.match_count} unassigned={self.unassigned_count}",
            f"  generate={self.generate_seconds:.1f}s total={self.total_seconds:.1f}s",
            f"  backend exit code={self.backend_exit_code}",
            f"  install tree unchanged ({self.install_tree_files} files)",
        ]
        return "\n".join(lines)


def find_packaged_backend(repository_root: Path | None = None) -> Path | None:
    """Return the first available frozen backend executable, or ``None``."""

    root = repository_root or _REPOSITORY_ROOT
    for candidate in PACKAGED_BACKEND_CANDIDATES:
        path = root / candidate
        if path.is_file():
            return path
    return None


def installation_root(backend_executable: Path) -> Path:
    """Return the directory tree that must stay untouched by a smoke run."""

    backend_executable = backend_executable.resolve()
    parents = backend_executable.parents
    # Electron layout: <install>/resources/backend/aqua-backend.exe
    if parents[0].name == "backend" and parents[1].name == "resources":
        return parents[2]
    # Standalone PyInstaller layout: <install>/aqua-backend.exe
    return parents[0]


def snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    """Map relative file paths to (mtime_ns, size) for write-isolation checks."""

    state: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            state[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size)
    return state


def list_image_pids(image_name: str) -> set[int]:
    """Return the PIDs of running processes with the given image name (Windows)."""

    if sys.platform != "win32":
        return set()
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {image_name}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        parts = [part.strip('"') for part in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].lower() == image_name.lower():
            try:
                pids.add(int(parts[1]))
            except ValueError:
                continue
    return pids


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


_DIAGNOSTIC_LOG_LINES = 40
_DIAGNOSTIC_LINE_LIMIT = 400


def _redact(text: str, app_data_dir: Path, launch_token: str | None) -> str:
    replacements = [
        (str(app_data_dir), "<app-data>"),
        (app_data_dir.as_posix(), "<app-data>"),
        (str(_REPOSITORY_ROOT), "<repo>"),
        (_REPOSITORY_ROOT.as_posix(), "<repo>"),
    ]
    if launch_token:
        replacements.append((launch_token, "<token>"))
    for needle, placeholder in replacements:
        text = text.replace(needle, placeholder)
    return text


def _failure_diagnostics(app_data_dir: Path, launch_token: str | None) -> str:
    """Bounded, redacted backend-side evidence for a failed smoke step.

    Collects the newest JSONL log lines and any solver job ``result.json``
    error fields from the disposable app-data directory before it is deleted.
    """

    sections: list[str] = []
    log_files = sorted(
        (app_data_dir / "logs").rglob("*.jsonl"),
        key=lambda path: path.stat().st_mtime_ns,
    )
    if log_files:
        newest = log_files[-1]
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = [line[:_DIAGNOSTIC_LINE_LIMIT] for line in lines[-_DIAGNOSTIC_LOG_LINES:]]
        sections.append(
            f"--- log tail ({newest.parent.name}/{newest.name}, last {len(tail)} lines) ---\n"
            + "\n".join(tail)
        )
    jobs_dir = app_data_dir / "jobs"
    if jobs_dir.is_dir():
        for job_dir in sorted(jobs_dir.iterdir()):
            names = sorted(entry.name for entry in job_dir.iterdir())
            sections.append(f"--- job {job_dir.name}: files {names} ---")
            result_path = job_dir / "result.json"
            if result_path.is_file():
                try:
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                except ValueError:
                    sections.append("result.json is not valid JSON")
                else:
                    for key in ("ok", "error", "error_kind", "message", "detail"):
                        if key in result:
                            sections.append(f"result.{key}={str(result[key])[:_DIAGNOSTIC_LINE_LIMIT]}")
    if not sections:
        return "no backend-side diagnostics were written under the app-data directory"
    return _redact("\n".join(sections), app_data_dir, launch_token)


def _demo_classes_path(backend_executable: Path) -> Path:
    """Locate the bundled synthetic demo classes.csv next to the frozen exe."""

    bundled = backend_executable.parent / "_internal" / "examples" / "demo" / "matching" / "classes.csv"
    _require(bundled.is_file(), "bundled demo dataset (classes.csv) is missing from the package")
    return bundled


def run_packaged_smoke(backend_executable: Path, work_dir: Path) -> SmokeReport:
    """Run the full packaged-backend workflow and return a redacted report."""

    backend_executable = backend_executable.resolve()
    report = SmokeReport(
        backend_variant="electron-bundled"
        if backend_executable.parent.name == "backend"
        else "pyinstaller-standalone",
    )
    started = time.monotonic()

    install_root = installation_root(backend_executable)
    install_before = snapshot_tree(install_root)
    report.install_tree_files = len(install_before)
    backend_pids_before = list_image_pids(BACKEND_IMAGE_NAME)

    app_data_dir = work_dir / "smoke-app-data"
    harness = BackendProcessHarness(
        app_data_dir,
        repository_root=_REPOSITORY_ROOT,
        backend_executable=backend_executable,
        startup_timeout=60.0,
    )

    try:
        harness.start()
        report.record("start + /api/ready")

        _require(
            harness.request("/api/settings", authenticated=False).status == 401,
            "unauthenticated /api/settings should be rejected with 401",
        )
        _require(
            harness.request("/api/settings").status == 200,
            "authenticated /api/settings should return 200",
        )
        report.record("launch-token auth (401 without header, 200 with)")

        picked = harness.request(
            "/api/pick_file",
            method="POST",
            body=json.dumps(
                {
                    "purpose": "classes",
                    "selected_path": str(_demo_classes_path(backend_executable)),
                }
            ).encode("utf-8"),
            headers=JSON_HEADERS,
            timeout=10.0,
        )
        _require(
            picked.status == 200 and picked.json().get("ok") is True,
            f"selecting the bundled demo classes.csv failed (status {picked.status})",
        )
        report.record("select bundled demo classes.csv via /api/pick_file")

        generate_started = time.monotonic()
        generated = harness.request(
            "/api/generate",
            method="POST",
            body=b"{}",
            headers=JSON_HEADERS,
            timeout=GENERATE_TIMEOUT_SECONDS,
        )
        report.generate_seconds = time.monotonic() - generate_started
        _require(
            generated.status == 200,
            f"/api/generate returned status {generated.status}",
        )
        generation = generated.json()
        _require(generation.get("ok") is True, "/api/generate result payload was not ok")
        matches = generation.get("matches")
        unassigned = generation.get("unassigned")
        _require(isinstance(matches, list), "generation result is missing the matches array")
        _require(isinstance(unassigned, list), "generation result is missing the unassigned array")
        _require(len(matches) > 0, "generation produced zero matches from the demo dataset")
        report.match_count = len(matches)
        report.unassigned_count = len(unassigned)
        report.record(
            f"/api/generate ({report.match_count} matches, "
            f"{report.unassigned_count} unassigned, {report.generate_seconds:.1f}s)"
        )

        latest = harness.request("/api/latest_generation_result", timeout=10.0)
        _require(latest.status == 200, f"/api/latest_generation_result status {latest.status}")
        latest_payload = latest.json()
        _require(
            latest_payload.get("ok") is True and latest_payload.get("has_result") is True,
            "latest generation result was not available after generate",
        )
        _require(
            len(latest_payload.get("matches", [])) == report.match_count,
            "latest generation result match count differs from the generate response",
        )
        report.record("/api/latest_generation_result matches the generate response")

        xai_page = harness.request("/xai/", timeout=15.0)
        _require(xai_page.status == 200, f"/xai/ dashboard page status {xai_page.status}")
        _require(b"<html" in xai_page.body.lower(), "/xai/ did not return an HTML page")
        overview = harness.request("/xai/api/overview", timeout=15.0)
        _require(overview.status == 200, f"/xai/api/overview status {overview.status}")
        overview_payload = overview.json()
        _require(overview_payload.get("ok") is True, "/xai/api/overview payload was not ok")
        _require(
            isinstance(overview_payload.get("summary"), dict),
            "/xai/api/overview payload is missing its summary",
        )
        report.record("/xai/ page + /xai/api/overview")

        export = harness.request("/api/instructors/export", timeout=15.0)
        _require(export.status == 200, f"/api/instructors/export status {export.status}")
        _require(
            "instructor_id" in export.body.decode("utf-8-sig", errors="replace").splitlines()[0],
            "instructors export CSV is missing its header row",
        )
        report.record("/api/instructors/export CSV")

        preview = harness.request(
            "/api/instructors/import/preview",
            method="POST",
            body=json.dumps({"csv": SYNTHETIC_IMPORT_CSV}).encode("utf-8"),
            headers=JSON_HEADERS,
            timeout=15.0,
        )
        _require(preview.status == 200, f"import preview status {preview.status}")
        preview_payload = preview.json()
        _require(preview_payload.get("ok") is True, "import preview payload was not ok")
        _require(
            len(preview_payload.get("new", [])) == 1,
            "import preview did not classify the synthetic instructor as new",
        )
        report.record("/api/instructors/import/preview with synthetic CSV")
    except SmokeFailure as failure:
        diagnostics = _failure_diagnostics(app_data_dir, harness.launch_token)
        raise SmokeFailure(f"{failure}\n{diagnostics}") from None
    finally:
        harness.stop()

    _require(
        harness.process is not None and harness.process.poll() is not None,
        "backend process is still running after authenticated shutdown",
    )
    report.backend_exit_code = harness.process.returncode
    report.record(f"authenticated /api/shutdown (exit code {report.backend_exit_code})")

    leftover = list_image_pids(BACKEND_IMAGE_NAME) - backend_pids_before
    _require(
        not leftover,
        f"{len(leftover)} orphaned backend/solver process(es) survived shutdown",
    )
    report.record("no orphaned backend or solver-worker processes")

    install_after = snapshot_tree(install_root)
    added = sorted(set(install_after) - set(install_before))
    removed = sorted(set(install_before) - set(install_after))
    modified = sorted(
        name for name in set(install_before) & set(install_after)
        if install_before[name] != install_after[name]
    )
    _require(
        not added and not removed and not modified,
        "installation directory changed during the smoke run: "
        f"{len(added)} added, {len(removed)} removed, {len(modified)} modified "
        f"(e.g. {(added + removed + modified)[:3]})",
    )
    report.record("installation directory untouched")

    for relative in ("data/aqua_essence.db", "settings/user_settings.json", "jobs", "logs"):
        _require(
            (app_data_dir / relative).exists(),
            f"expected runtime artifact missing under the app-data directory: {relative}",
        )
    _require(
        any((app_data_dir / "jobs").iterdir()),
        "no solver job directory was written under the app-data directory",
    )
    report.record("runtime writes confined to the disposable app-data directory")

    _require(
        harness.launch_token not in report.summary(),
        "internal error: report text leaked the launch token",
    )
    report.total_seconds = time.monotonic() - started
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        backend_executable = Path(arguments[0])
        if not backend_executable.is_file():
            print("smoke: the supplied backend executable does not exist", file=sys.stderr)
            return 2
    else:
        found = find_packaged_backend()
        if found is None:
            print("smoke: no packaged backend found under .dist/ — build it first", file=sys.stderr)
            return 2
        backend_executable = found

    import tempfile

    with tempfile.TemporaryDirectory(prefix="aqua-smoke-") as scratch:
        try:
            report = run_packaged_smoke(backend_executable, Path(scratch))
        except SmokeFailure as failure:
            print(f"smoke: FAILED — {failure}", file=sys.stderr)
            return 1
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
