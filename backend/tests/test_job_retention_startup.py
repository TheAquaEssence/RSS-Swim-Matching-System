from copy import deepcopy
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import server
from core.retention import JobCleanupResult


def test_application_startup_runs_job_retention_cleanup():
    services = server.create_application_services(
        initial_settings=deepcopy(server.make_default_settings()),
        persist_settings=False,
    )
    application = server.create_app(services)

    with patch.object(
        server,
        "cleanup_expired_jobs",
        return_value=JobCleanupResult(),
    ) as cleanup:
        with TestClient(application):
            pass

    cleanup.assert_called_once_with(
        services.paths.jobs_dir,
        services.paths.app_data_root,
        retention_days=30,
    )
