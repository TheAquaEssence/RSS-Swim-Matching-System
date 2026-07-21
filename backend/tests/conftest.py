"""Shared fixtures for backend tests.

Settings isolation: endpoint tests exercise routes that persist settings
(use_db_instructors, deselected_session_ids, file selections, ...). Without
redirection they overwrite the developer's real settings/user_settings.json —
this actually happened: running the suite flipped use_db_instructors off and
wiped the saved session selection. Every test gets a throwaway settings file
and a restored in-memory settings dict instead.
"""
import copy

import pytest

import backend.server as server


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "user_settings.json")
    state = server.application_services.state
    with state.settings_lock:
        snapshot = copy.deepcopy(state.settings)
    yield
    # Endpoints mutate the module-global dict in place — restore it so tests
    # can't leak state into each other (or into a dev server run afterwards).
    with state.settings_lock:
        state.settings.clear()
        state.settings.update(snapshot)
