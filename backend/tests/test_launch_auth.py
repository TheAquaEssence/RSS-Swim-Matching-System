from copy import deepcopy

from fastapi.testclient import TestClient

from backend import server
from backend.launch_auth import (
    LAUNCH_TOKEN_ENV,
    LAUNCH_TOKEN_HEADER,
    LaunchTokenAuth,
    generate_launch_token,
)


def _client(token: str | None):
    services = server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
        launch_token=token,
    )
    return TestClient(server.create_app(services))


def test_generated_tokens_are_strong_unique_and_url_safe():
    first = generate_launch_token()
    second = generate_launch_token()

    assert first != second
    assert len(first) >= 43
    assert all(character.isalnum() or character in "-_" for character in first)


def test_validator_uses_compare_digest(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.launch_auth.secrets.compare_digest",
        lambda candidate, expected: calls.append((candidate, expected)) or True,
    )

    assert LaunchTokenAuth.configured("secret").accepts("presented") is True
    assert calls == [(b"presented", b"secret")]


def test_liveness_readiness_and_static_ui_are_exempt():
    with _client("secret") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
        assert client.get("/").status_code == 200


def test_api_and_private_data_routes_require_exact_header():
    client = _client("correct-secret")

    for path, method in (
        ("/api/settings", "get"),
        ("/api/shutdown", "post"),
        ("/jobs/missing.csv", "get"),
        ("/xai/", "get"),
    ):
        unauthorized = getattr(client, method)(path)
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"ok": False, "error": "Unauthorized"}
        assert unauthorized.headers["cache-control"] == "no-store"
        assert "correct-secret" not in unauthorized.text

        wrong = getattr(client, method)(path, headers={LAUNCH_TOKEN_HEADER: "wrong"})
        assert wrong.status_code == 401

    authorized = client.get(
        "/jobs/missing.csv", headers={LAUNCH_TOKEN_HEADER: "correct-secret"}
    )
    assert authorized.status_code == 404


def test_missing_configuration_preserves_source_development_behavior(monkeypatch):
    monkeypatch.delenv(LAUNCH_TOKEN_ENV, raising=False)
    client = _client(None)

    assert client.get("/api/settings").status_code == 200


def test_services_read_launch_token_from_environment(monkeypatch):
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "environment-secret")
    services = server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
    )

    assert services.launch_auth.enabled is True
    assert services.launch_auth.accepts("environment-secret") is True
    assert "environment-secret" not in repr(services.launch_auth)
