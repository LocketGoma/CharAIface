from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10420


def _is_backend_reachable(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/health",
            timeout=1.5,
        ):
            return True
    except urllib.error.HTTPError:
        # A 503 health response still means the backend process is alive.
        return True
    except Exception:
        return False


def _wait_for_backend(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_backend_reachable(host, port):
            return True
        time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start CharAIface backend and desktop frontend together."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reload", action="store_true", help="Start uvicorn with --reload.")
    parser.add_argument(
        "--backend-timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for backend startup.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    backend_process: subprocess.Popen | None = None

    if _is_backend_reachable(args.host, args.port):
        print(f"[Launcher] Backend already running on {args.host}:{args.port}.")
    else:
        backend_command = [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        if args.reload:
            backend_command.append("--reload")

        print("[Launcher] Starting backend:", " ".join(backend_command))
        backend_process = subprocess.Popen(
            backend_command,
            cwd=project_root,
        )

        if not _wait_for_backend(args.host, args.port, args.backend_timeout):
            print("[Launcher] Backend did not become reachable in time.")
            if backend_process is not None:
                backend_process.terminate()
            return 1

    desktop_command = [sys.executable, "-m", "desktop.app"]
    print("[Launcher] Starting desktop:", " ".join(desktop_command))

    try:
        return subprocess.call(desktop_command, cwd=project_root)
    finally:
        if backend_process is not None and backend_process.poll() is None:
            print("[Launcher] Stopping backend.")
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
