from copy import deepcopy
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import start
from backend import server


def _services():
    return server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
    )


def test_explicit_port_flag_and_legacy_position_are_supported():
    assert start.parse_args(["--port", "9012", "--no-browser"]).port == 9012
    assert start.parse_args(["9013", "--nb"]).port == 9013
    assert start.parse_args(["--port", "0"]).port == 0


def test_duplicate_port_forms_are_rejected():
    with pytest.raises(SystemExit):
        start.parse_args(["9012", "--port", "9013"])


def test_readiness_tracks_application_lifespan():
    services = _services()
    application = server.create_app(services)

    assert TestClient(application).get("/api/ready").status_code == 503
    with TestClient(application) as client:
        response = client.get("/api/ready")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "status": "ready"}
    assert services.state.ready is False


def test_application_shutdown_terminates_active_solver_processes():
    services = _services()
    application = server.create_app(services)

    with patch.object(server.solver_runner.ACTIVE_SOLVER_PROCESSES, "terminate_all") as terminate_all:
        with TestClient(application):
            pass

    terminate_all.assert_called_once_with(services.logger)


def test_launcher_binds_uvicorn_to_loopback(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    with patch("backend.server.find_listen_port", return_value=9012), patch("uvicorn.run") as run:
        start.main(["--port", "9012", "--no-browser"])

    run.assert_called_once_with(
        server.app,
        host=server.LOOPBACK_HOST,
        port=9012,
        log_level="warning",
    )
    assert server.LOOPBACK_HOST == "127.0.0.1"
