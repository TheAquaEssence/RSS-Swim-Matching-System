"""
start.py — launch the Aqua Essence FastAPI backend

Usage:
    python start.py                # auto-selects port 8787-8794, opens browser
    python start.py 9000           # specific port, opens browser
    python start.py --port 9000    # explicit desktop/backend port
    python start.py --port 0       # OS-selected random available port
    python start.py --nb           # skip opening the browser
    python start.py 9000 --nb
    python start.py --data-dir PATH  # store runtime data under PATH
    python start.py --help
"""
import argparse
import os
import sys
import threading
from pathlib import Path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Launch the Aqua Essence local application")
    parser.add_argument("legacy_port", nargs="?", type=int, help="specific localhost port (legacy syntax)")
    parser.add_argument("--port", dest="explicit_port", type=int, help="localhost port; use 0 for a random available port")
    parser.add_argument("--nb", "--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="writable root for the database, settings, jobs, and logs",
    )
    args = parser.parse_args(argv)
    if args.legacy_port is not None and args.explicit_port is not None:
        parser.error("specify the port either positionally or with --port, not both")
    args.port = args.explicit_port if args.explicit_port is not None else args.legacy_port
    return args


def main(argv=None):
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # PyInstaller directory-mode builds use this same executable for the
    # isolated CP-SAT worker. Dispatch before importing the FastAPI server.
    from backend.solver_worker import is_solver_worker_invocation, run_solver_worker

    if is_solver_worker_invocation(raw_args):
        return run_solver_worker(raw_args)

    args = parse_args(raw_args)

    open_browser = not args.nb
    if args.data_dir is not None:
        os.environ["AQUA_APP_DATA_DIR"] = str(args.data_dir.expanduser().resolve())

    # Ensure workspace root is on sys.path so all imports resolve
    workspace = os.path.dirname(os.path.abspath(__file__))
    if workspace not in sys.path:
        sys.path.insert(0, workspace)

    from backend.server import LOOPBACK_HOST, app, find_listen_port
    import uvicorn

    port = find_listen_port(args.port)
    url = f"http://{LOOPBACK_HOST}:{port}/"
    print(f"Starting Aqua Essence on {url}")

    if open_browser:
        import webbrowser
        threading.Timer(1.0, webbrowser.open, args=[url]).start()

    uvicorn.run(app, host=LOOPBACK_HOST, port=port, log_level="warning")


if __name__ == "__main__":
    raise SystemExit(main())
