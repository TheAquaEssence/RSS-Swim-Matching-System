# Desktop Process Lifecycle

The Electron main process will own the local FastAPI host. The host, in turn,
owns every solver subprocess it starts. Neither process may be intentionally
detached from its parent.

## Normal shutdown

1. Electron stops sending heartbeats and requests `POST /api/shutdown`.
2. FastAPI receives its shutdown signal and stops accepting new work.
3. The application lifespan cleanup terminates every registered solver child.
4. Each solver gets a two-second grace period to exit before the host kills it.
5. FastAPI completes cleanup and Electron waits for the host process to exit.

Closing the desktop window, choosing Quit, and installing an update should all
use this sequence. Electron should wait for a bounded interval and force-stop
the FastAPI host only if it does not exit.

## Failure and timeout behavior

- A solver has a five-minute execution timeout.
- On timeout, the host first terminates the solver, waits two seconds, then
  kills it if necessary and reaps the process.
- FastAPI lifespan cleanup repeats this policy for all currently registered
  solver children, including a solver that is still running during app exit.
- The heartbeat watchdog signals the host once and then exits; it does not
  repeatedly interrupt shutdown.

The desktop integration test harness should eventually verify this contract
with real packaged processes. The backend unit tests currently verify that
lifespan shutdown invokes solver cleanup and that timeout cleanup reaps the
child.
