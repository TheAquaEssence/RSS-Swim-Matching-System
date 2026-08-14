from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_matching_workspace_exposes_single_bundle_import():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert 'id="jackrabbitImportButton"' in html
    assert html.count('id="jackrabbitImportButton"') == 1
    assert 'id="jackrabbitPairingsImportButton"' in html
    assert 'id="jackrabbitImportFileInput"' in html
    assert 'accept=".json,application/json"' in html
    assert 'id="jackrabbitImportStatus" role="status" aria-live="polite"' in html
    assert 'aria-describedby="jackrabbitImportStatus"' in html
    assert '<script src="./jackrabbit_import.js"></script>' in html


def test_bundle_import_uses_multipart_endpoint_and_safe_status_text():
    source = (ROOT / "frontend" / "jackrabbit_import.js").read_text(encoding="utf-8")

    assert 'fetch("/api/jackrabbit/import"' in source
    assert "new FormData()" in source
    assert 'file.name !== "aqua_essence_jackrabbit_export.json"' in source
    assert "status.textContent = message" in source
    assert "status.innerHTML" not in source
    assert 'document.createElement("li")' in source
    assert "item.textContent = String(warning)" in source
    assert "output.innerHTML" not in source
