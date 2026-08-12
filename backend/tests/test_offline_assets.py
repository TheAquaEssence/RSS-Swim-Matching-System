"""Offline-asset guarantees for the packaged desktop application.

The Electron build must work fully offline, so no HTML/CSS/JS served from
frontend/ may load resources from a remote host at runtime.  Anchor links to
the project's GitHub repository are permitted — desktop/main.cjs opens them in
the system browser — but loaded resources (scripts, stylesheets, fonts,
images, fetches) must all be same-origin.

Also verifies the vendored replacements (Chart.js, Fontsource fonts) exist on
disk and are actually served by the FastAPI app.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.server as server

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

# Directories under frontend/ that are never served to the browser.
_UNSERVED_DIRS = {"tests", "__pycache__"}

# Vendored third-party bundles may embed homepage URLs in comments/banners;
# they are audited via THIRD_PARTY_NOTICES.md instead of this scan.
_VENDOR_DIRS = {"vendor"}

# Anchor links allowed to leave the app (opened in the system browser by
# desktop/main.cjs isAllowedExternalUrl).
_ALLOWED_ANCHOR_PREFIX = "https://github.com/TheAquaEssence/AquaEssence"

_URL_RE = re.compile(r"https?://[^\s\"'<>()]+")
_TAG_URL_RE = re.compile(
    r"<(?P<tag>[a-zA-Z][a-zA-Z0-9-]*)[^>]*?(?:src|href)\s*=\s*[\"'](?P<url>https?://[^\"']+)[\"']"
)


@pytest.fixture
def client():
    return TestClient(server.app)


def _served_files(suffixes: tuple[str, ...]) -> list[Path]:
    files = []
    for path in sorted(FRONTEND.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        parts = set(path.relative_to(FRONTEND).parts)
        if parts & _UNSERVED_DIRS:
            continue
        files.append(path)
    return files


def _is_vendored(path: Path) -> bool:
    return bool(set(path.relative_to(FRONTEND).parts) & _VENDOR_DIRS)


def test_html_loads_no_remote_resources():
    for path in _served_files((".html", ".htm")):
        text = path.read_text(encoding="utf-8")
        for match in _TAG_URL_RE.finditer(text):
            tag, url = match.group("tag").lower(), match.group("url")
            assert tag == "a" and url.startswith(_ALLOWED_ANCHOR_PREFIX), (
                f"{path.relative_to(ROOT)} loads a remote resource at runtime: "
                f"<{tag} ... {url}>"
            )


def test_first_party_css_and_js_have_no_remote_urls():
    for path in _served_files((".css", ".js")):
        if _is_vendored(path):
            continue
        text = path.read_text(encoding="utf-8")
        urls = [
            url for url in _URL_RE.findall(text)
            if not url.startswith(_ALLOWED_ANCHOR_PREFIX)
        ]
        assert not urls, (
            f"{path.relative_to(ROOT)} references remote URLs: {urls}"
        )


def test_vendored_offline_assets_exist():
    required = [
        FRONTEND / "xai_dashboard" / "static" / "vendor" / "chartjs" / "chart.umd.min.js",
        FRONTEND / "xai_dashboard" / "static" / "vendor" / "chartjs" / "LICENSE.md",
        FRONTEND / "vendor" / "fonts" / "fonts.css",
        FRONTEND / "vendor" / "fonts" / "outfit" / "LICENSE",
        FRONTEND / "vendor" / "fonts" / "jetbrains-mono" / "LICENSE",
    ]
    required += [
        FRONTEND / "vendor" / "fonts" / "outfit" / f"outfit-latin-{weight}-normal.woff2"
        for weight in (300, 400, 500, 600, 700)
    ]
    required += [
        FRONTEND / "vendor" / "fonts" / "jetbrains-mono"
        / f"jetbrains-mono-latin-{weight}-normal.woff2"
        for weight in (400, 500)
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, f"Missing vendored offline assets: {missing}"


def test_vendored_assets_are_served(client):
    expectations = {
        "/vendor/fonts/fonts.css": "text/css",
        "/styles/ux-refresh.css": "text/css",
        "/styles/workspace.css": "text/css",
        "/styles/matching-workspace.css": "text/css",
        "/vendor/fonts/outfit/outfit-latin-400-normal.woff2": "font/woff2",
        "/vendor/fonts/jetbrains-mono/jetbrains-mono-latin-400-normal.woff2": "font/woff2",
        "/xai/static/ux-refresh.css": "text/css",
        "/xai/static/vendor/chartjs/chart.umd.min.js": "javascript",
    }
    for path, content_type in expectations.items():
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} not served: {resp.status_code}"
        assert content_type in resp.headers.get("Content-Type", ""), (
            f"{path} served with wrong content type: "
            f"{resp.headers.get('Content-Type')!r}"
        )


def test_index_html_uses_local_fonts(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "fonts.googleapis.com" not in resp.text
    assert "fonts.gstatic.com" not in resp.text
    assert "vendor/fonts/fonts.css" in resp.text


def test_xai_template_uses_local_chartjs():
    template = FRONTEND / "xai_dashboard" / "templates" / "index.html"
    text = template.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in text
    assert "/xai/static/vendor/chartjs/chart.umd.min.js" in text
    assert '/vendor/fonts/fonts.css' in text
    assert '/xai/static/ux-refresh.css' in text
    assert '/styles/workspace.css' in text


def test_fonts_css_declares_expected_families():
    text = (FRONTEND / "vendor" / "fonts" / "fonts.css").read_text(encoding="utf-8")
    assert "font-family: 'Outfit'" in text
    assert "font-family: 'JetBrains Mono'" in text
