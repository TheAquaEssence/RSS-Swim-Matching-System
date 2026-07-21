import logging
import subprocess

from backend.services.solver_runner import SolverProcessRegistry


class StubbornProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if timeout is not None:
            raise subprocess.TimeoutExpired("solver", timeout)
        return 0


def test_registry_forces_and_reaps_solver_that_ignores_termination():
    registry = SolverProcessRegistry()
    process = StubbornProcess()
    registry.add(process)

    registry.terminate_all(logging.getLogger("test"), grace_seconds=0)

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == [0.0, None]
