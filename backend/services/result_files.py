"""Translate solver-owned output paths into stable HTTP download URLs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


PUBLIC_RESULT_FILES = {
    "classes_filled": "classes_filled.csv",
    "report": "report.txt",
    "pdf": "matching_report.pdf",
    "profiles": "profiles.json",
}


def expose_result_files(result_payload: dict, job_dir: Path) -> dict:
    """Return a shallow payload copy with no internal filesystem paths exposed."""

    payload = dict(result_payload)
    source_files = result_payload.get("result_files")
    if not isinstance(source_files, dict):
        payload["result_files"] = {}
        return payload

    job_id = job_dir.name
    encoded_job_id = quote(job_id, safe="")
    public_files: dict[str, str] = {}
    for key, filename in PUBLIC_RESULT_FILES.items():
        if key not in source_files or not (job_dir / filename).is_file():
            continue
        public_files[key] = f"/jobs/{encoded_job_id}/{quote(filename, safe='')}"

    if "classes_filled" in public_files:
        public_files["filled_classes_export"] = public_files["classes_filled"]
    payload["result_files"] = public_files
    return payload
