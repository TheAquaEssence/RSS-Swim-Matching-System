"""Minimal entry point for an isolated production solver worker.

The frozen backend executable dispatches here before importing FastAPI.  Keeping
the worker protocol in this small module also gives packaging and subprocess
tests one stable command-line contract.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

SOLVER_WORKER_ARGUMENT = "--solver-worker"


def is_solver_worker_invocation(argv: Sequence[str]) -> bool:
    """Return whether *argv* requests the internal solver worker mode."""

    return bool(argv) and argv[0] == SOLVER_WORKER_ARGUMENT


def run_solver_worker(argv: Sequence[str]) -> int:
    """Run the production solver wrapper for one request/result pair.

    ``argv`` may include the worker-mode argument (as it does when dispatched
    by the frozen backend) or contain only the two paths (as with ``-m``).
    Heavy solver imports intentionally happen only after validating the mode.
    """

    args = list(argv)
    if is_solver_worker_invocation(args):
        args = args[1:]

    if len(args) != 2:
        print(
            f"Usage: {SOLVER_WORKER_ARGUMENT} <request.json> <result.json>",
            file=sys.stderr,
        )
        return 2

    from solvers.python_cpsat import solver_wrapper

    result = solver_wrapper.main(args)
    return 0 if result is None else int(result)


def main(argv: Sequence[str] | None = None) -> int:
    return run_solver_worker(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
