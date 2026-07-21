"""
Tests for heartbeat and shutdown behaviour across app.js and dashboard.js.

Root cause: the pagehide handler in app.js fired POST /api/shutdown whenever
the user navigated away from the main page — including to /xai/. This killed
the server 8 seconds after the user opened the XAI dashboard.

Fixes verified here:
  1. dashboard.js sends periodic heartbeats to /api/heartbeat so the 120-second
     watchdog doesn't kill the server while the dashboard is open.
  2. app.js no longer registers a pagehide handler that calls /api/shutdown
     (registerShutdownOnPageClose removed; server lifetime managed by watchdog).
"""
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
DASHBOARD_JS = WORKSPACE / "frontend" / "xai_dashboard" / "static" / "dashboard.js"
APP_JS = WORKSPACE / "frontend" / "app.js"


# ---------------------------------------------------------------------------
# dashboard.js — must keep the server alive while /xai/ is open
# ---------------------------------------------------------------------------

def test_dashboard_sends_heartbeat():
    """dashboard.js must POST to /api/heartbeat periodically.

    Without this, the server's 120-second watchdog kills the process while
    the user is on the XAI dashboard (heartbeats only came from app.js).
    """
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "/api/heartbeat" in source, (
        "dashboard.js must call /api/heartbeat to keep the server alive"
    )


def test_dashboard_heartbeat_is_periodic():
    """Heartbeat must repeat on an interval, not just fire once on load."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "setInterval" in source, (
        "dashboard.js must use setInterval so heartbeats repeat, "
        "not just fire once at DOMContentLoaded"
    )


def test_dashboard_fetches_api_without_browser_cache():
    """Overview fetches must bypass browser caches so /xai/ reflects the latest job."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "cache: 'no-store'" in source or 'cache: "no-store"' in source, (
        "dashboard.js must fetch XAI API responses with cache disabled"
    )


def test_dashboard_refreshes_when_page_returns():
    """Returning to an existing XAI page must trigger a fresh overview load."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "pageshow" in source, (
        "dashboard.js must handle pageshow so restored XAI pages refresh data"
    )


# ---------------------------------------------------------------------------
# app.js — must NOT kill the server on same-tab navigation to /xai/
# ---------------------------------------------------------------------------

def test_app_js_does_not_register_pagehide_shutdown():
    """app.js must not call registerShutdownOnPageClose().

    That function wired a pagehide listener that fired POST /api/shutdown
    on every navigation away from the main page — including to /xai/.
    Server lifetime is now managed by the heartbeat watchdog alone.
    """
    source = APP_JS.read_text(encoding="utf-8")
    assert "registerShutdownOnPageClose" not in source, (
        "registerShutdownOnPageClose must be removed from app.js; "
        "it caused the server to die 8s after navigating to the XAI dashboard"
    )


def test_app_js_pagehide_does_not_call_api_shutdown():
    """No pagehide handler in app.js may reference /api/shutdown.

    Even if the function is renamed, the underlying behaviour (calling
    /api/shutdown from pagehide) must not exist in app.js.
    """
    source = APP_JS.read_text(encoding="utf-8")
    # Check that /api/shutdown does not appear inside a pagehide block.
    # The simplest structural check: if pagehide and /api/shutdown co-exist
    # in the file, they are almost certainly wired together.
    has_pagehide = "pagehide" in source
    has_shutdown_call = '"/api/shutdown"' in source or "'/api/shutdown'" in source
    assert not (has_pagehide and has_shutdown_call), (
        "app.js must not combine pagehide with /api/shutdown; "
        "this fires on same-tab navigation and kills the server"
    )
