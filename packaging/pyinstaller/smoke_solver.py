"""Run the frozen CP-SAT worker against the bundled synthetic demo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args(argv)

    executable = args.executable.expanduser().resolve()
    if not executable.is_file():
        parser.error(f"packaged backend does not exist: {executable}")

    resource_root = executable.parent / "_internal"
    demo = resource_root / "examples" / "demo" / "matching"
    required = tuple(demo / name for name in ("classes.csv", "swimmers.csv", "instructors.csv"))
    if not all(path.is_file() for path in required):
        parser.error("packaged synthetic matching demo is incomplete")

    with tempfile.TemporaryDirectory(prefix="aqua-packaged-solver-") as temporary:
        job_dir = Path(temporary)
        request_path = job_dir / "request.json"
        result_path = job_dir / "result.json"
        request_path.write_text(
            json.dumps(
                {
                    "job_id": "job_packaged_worker_smoke",
                    "app_root": str(resource_root),
                    "data": {
                        "classes": str(required[0]),
                        "swimmers": str(required[1]),
                        "instructors": str(required[2]),
                        "historical_pairings": "",
                        "reference": {},
                    },
                    "config": {"enable_continuity": False},
                }
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["AQUA_LOG_DIR"] = str(job_dir / "logs")
        completed = subprocess.run(
            [str(executable), "--solver-worker", str(request_path), str(result_path)],
            cwd=executable.parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout)
            return completed.returncode or 1
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("ok") is not True:
            print("Packaged solver returned a failed result")
            return 1
        print(
            "Packaged solver smoke passed: "
            f"{len(result.get('matches', []))} matches, "
            f"{len(result.get('unassigned', []))} unassigned"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
