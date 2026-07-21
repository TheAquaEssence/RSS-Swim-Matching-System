# Packaged solver-worker contract

The FastAPI host and CP-SAT solver remain separate operating-system processes
in both source and packaged builds. This preserves the existing timeout, crash
isolation, and shutdown ownership guarantees in `SolverProcessRegistry`.

## Commands

Source mode keeps the existing command exactly:

```text
<python> <solver_wrapper.py> <request.json> <result.json>
```

A frozen backend cannot assume that a Python interpreter or loose wrapper
script exists. It therefore starts a second copy of itself:

```text
<AquaEssenceBackend.exe> --solver-worker <request.json> <result.json>
```

`start.py` recognizes `--solver-worker` before importing `backend.server` or
Uvicorn. The small `backend.solver_worker` dispatcher then imports and invokes
the production `solvers.python_cpsat.solver_wrapper` with an explicit two-path
argument list. No shell is involved in either command.

## Packaging requirements

The PyInstaller analysis must include `backend.solver_worker`, the production
solver wrapper and engine, `core`, and their pandas, OR-Tools, and ReportLab
dependencies and data files. The packaged executable's normal entry point must
remain `start.py` so worker-mode dispatch occurs before web-server startup.

The parent host owns the worker process. It registers the child immediately
after `Popen`, applies the same five-minute timeout, terminates then force-kills
and reaps a stuck worker, and terminates registered workers during application
shutdown. Worker exit and `result.json` retain the existing solver contract.

`backend.tests.test_solver_worker` verifies both command shapes and runs the
source entry executable through the same worker dispatch against the canonical
synthetic demo dataset. The packaged smoke harness should repeat that request
against the built executable to prove that all native OR-Tools libraries and
solver resources were collected.
