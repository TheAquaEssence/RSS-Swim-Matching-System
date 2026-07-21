"""Loopback Host and same-origin policy tests for the desktop backend."""

from copy import deepcopy

from fastapi.testclient import TestClient

from backend import server
from backend.launch_auth import LAUNCH_TOKEN_HEADER


def _client(
    token: str = "desktop-secret",
    *,
    peer: tuple[str, int] = ("testclient", 50000),
) -> TestClient:
    services = server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
        launch_token=token,
    )
    return TestClient(server.create_app(services), client=peer)


def test_loopback_hosts_and_ports_are_allowed():
    with _client() as client:
        for host in (
            "127.0.0.1",
            "127.0.0.1:8787",
            "localhost",
            "LOCALHOST:65535",
        ):
            response = client.get("/api/ready", headers={"Host": host})
            assert response.status_code == 200


def test_arbitrary_and_lookalike_hosts_are_rejected_before_routes():
    with _client() as client:
        for host in (
            "example.com",
            "127.0.0.1.example.com",
            "localhost.example.com",
            "localhost:0",
            "localhost:not-a-port",
        ):
            response = client.get("/api/ready", headers={"Host": host})
            assert response.status_code == 400
            assert response.json() == {"ok": False, "error": "Invalid request host"}


def test_testclient_host_exception_is_not_available_to_an_http_peer():
    with _client(peer=("127.0.0.1", 50000)) as client:
        response = client.get("/api/health", headers={"Host": "testserver"})

    assert response.status_code == 400


def test_cross_origin_requests_receive_no_cors_permission_headers():
    with _client() as client:
        response = client.get(
            "/api/health",
            headers={"Host": "127.0.0.1:8787", "Origin": "https://attacker.example"},
        )
        preflight = client.options(
            "/api/settings",
            headers={
                "Host": "127.0.0.1:8787",
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-credentials" not in preflight.headers


def test_valid_host_does_not_bypass_protected_endpoint_authentication():
    with _client() as client:
        unauthorized = client.get("/api/settings", headers={"Host": "localhost:8787"})
        authorized = client.get(
            "/api/settings",
            headers={"Host": "localhost:8787", LAUNCH_TOKEN_HEADER: "desktop-secret"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200


def test_invalid_host_rejection_keeps_security_headers_and_precedes_auth():
    with _client() as client:
        response = client.get(
            "/api/settings",
            headers={"Host": "attacker.example", LAUNCH_TOKEN_HEADER: "desktop-secret"},
        )

    assert response.status_code == 400
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "access-control-allow-origin" not in response.headers
