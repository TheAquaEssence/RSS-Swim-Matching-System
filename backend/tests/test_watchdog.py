from unittest.mock import Mock

from backend import server
from backend.application import ApplicationState


class _WaitSequence:
    def __init__(self, *results: bool) -> None:
        self._results = iter(results)

    def wait(self, timeout: float) -> bool:
        assert timeout == 5
        return next(self._results)


def test_watchdog_does_not_expire_during_generation(monkeypatch):
    state = ApplicationState(settings={})
    state.generate_in_progress = True
    state.last_heartbeat = 0.0
    state.shutdown_event = _WaitSequence(False, True)
    kill = Mock()
    monkeypatch.setattr(server.time, "monotonic", lambda: 1_000.0)
    monkeypatch.setattr(server.os, "kill", kill)

    server._watchdog(state)

    kill.assert_not_called()
    assert state.last_heartbeat == 1_000.0


def test_watchdog_still_expires_an_idle_host(monkeypatch):
    state = ApplicationState(settings={})
    state.last_heartbeat = 0.0
    state.shutdown_event = _WaitSequence(False)
    kill = Mock()
    monkeypatch.setattr(server.time, "monotonic", lambda: server.HEARTBEAT_TIMEOUT + 1.0)
    monkeypatch.setattr(server.os, "kill", kill)

    server._watchdog(state)

    kill.assert_called_once_with(server.os.getpid(), server.signal.SIGINT)
