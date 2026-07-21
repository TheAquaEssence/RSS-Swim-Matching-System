from copy import deepcopy

from fastapi.testclient import TestClient

from backend import server
from backend.application import ApplicationServices, ApplicationState


def _services():
    return server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
    )


def test_factory_attaches_explicit_services_and_state():
    services = _services()
    application = server.create_app(services)

    assert application is not server.app
    assert application.state.services is services
    assert isinstance(services, ApplicationServices)
    assert isinstance(services.state, ApplicationState)
    assert TestClient(application).get("/api/health").status_code == 200


def test_factory_instances_do_not_share_mutable_state(tmp_path):
    first_services = _services()
    second_services = _services()
    first_app = server.create_app(first_services)
    second_app = server.create_app(second_services)

    first_services.state.settings["use_db_instructors"] = True
    first_services.state.last_job_dir = str(tmp_path / "job_one")
    first_services.state.generate_in_progress = True

    assert second_services.state.settings["use_db_instructors"] is False
    assert second_services.state.last_job_dir == ""
    assert second_services.state.generate_in_progress is False

    assert TestClient(first_app).post("/api/launch_dashboard").status_code == 200
    assert TestClient(second_app).post("/api/launch_dashboard").status_code == 503


def test_generation_throttle_is_owned_by_each_application_state():
    first = _services().state
    second = _services().state

    assert first.try_begin_generation(5.0) == (True, 0)
    assert first.try_begin_generation(5.0) == (False, 1)
    assert second.try_begin_generation(5.0) == (True, 0)

    first.finish_generation()
    assert first.generate_in_progress is False
    assert second.generate_in_progress is True
