"""TDD tests for security headers middleware (Phase B2 — NEW-S2 resolution).

Tests verify that every HTTP response from the FastAPI app includes the
four required security headers with the correct values.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.server as server

# ---------------------------------------------------------------------------
# Fixture — mirrors the pattern in test_server_security.py
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture(autouse=True)
def reset_generate_rate_limit(monkeypatch):
    monkeypatch.setattr(server.application_services.state, "generate_in_progress", False)
    monkeypatch.setattr(server.application_services.state, "last_generate_started_at", float("-inf"))


# ---------------------------------------------------------------------------
# Helper constant — the four headers we require
# ---------------------------------------------------------------------------

_REQUIRED_HEADERS = {
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Content-Security-Policy",
    "Referrer-Policy",
}


# ---------------------------------------------------------------------------
# Test 1 — all four headers present on GET /
# ---------------------------------------------------------------------------

def test_security_headers_present_on_root(client):
    resp = client.get("/")
    for header in _REQUIRED_HEADERS:
        assert header in resp.headers, f"Missing header: {header}"


# ---------------------------------------------------------------------------
# Test 2 — all four headers present on GET /api/health
# ---------------------------------------------------------------------------

def test_security_headers_present_on_api_solvers(client):
    resp = client.get("/api/health")
    for header in _REQUIRED_HEADERS:
        assert header in resp.headers, f"Missing header on /api/health: {header}"


# ---------------------------------------------------------------------------
# Test 3 — X-Frame-Options is exactly DENY
# ---------------------------------------------------------------------------

def test_xframe_options_is_deny(client):
    resp = client.get("/")
    assert resp.headers["X-Frame-Options"] == "DENY"


# ---------------------------------------------------------------------------
# Test 4 — X-Content-Type-Options is exactly nosniff
# ---------------------------------------------------------------------------

def test_x_content_type_options_is_nosniff(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------------
# Test 5 — Content-Security-Policy is self-only (no CDN hosts; offline app)
# ---------------------------------------------------------------------------

def test_csp_script_src_is_self_only(client):
    resp = client.get("/")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "script-src 'self';" in csp, (
        f"CSP script-src must be 'self' only. Got: {csp!r}"
    )
    assert "cdn.jsdelivr.net" not in csp, (
        f"CSP must not reference remote CDNs. Got: {csp!r}"
    )


# ---------------------------------------------------------------------------
# Cache headers — stale JavaScript and stylesheets must revalidate on every load
# ---------------------------------------------------------------------------

def test_static_js_and_css_are_no_cache(client):
    paths = (
        "/app.js",
        "/profile_drawer.js",
        "/settings_files.js",
        "/reference_editors.js",
        "/instructor_defaults.js",
        "/styles/base.css",
        "/styles/results.css",
        "/styles/overlays.css",
        "/styles/sessions.css",
        "/styles/instructor-editor.css",
        "/styles/ux-refresh.css",
        "/xai/static/dashboard.js",
        "/xai/static/dashboard.css",
        "/xai/static/ux-refresh.css",
    )
    for path in paths:
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "no-cache", (
            f"{path} must use no-cache so browsers revalidate after app updates; "
            f"got: {resp.headers.get('Cache-Control')!r}"
        )
        if path.endswith(".js"):
            assert "javascript" in resp.headers.get("Content-Type", "").lower(), (
                f"{path} must use a JavaScript-compatible content type; "
                f"got: {resp.headers.get('Content-Type')!r}"
            )


def test_html_is_no_store(client):
    resp = client.get("/")
    assert resp.headers.get("Cache-Control") == "no-store"
