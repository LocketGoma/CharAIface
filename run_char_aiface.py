from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 10420
BACKEND_MODULE = "backend.app.main:app"
SETTINGS_PATH = ROOT_DIR / "resources" / "data" / "settings.json"


_backend_process: subprocess.Popen | None = None
_backend_pids_to_stop: set[int] = set()
_cleanup_started = False


def _read_developer_mode() -> bool:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False

    return bool(data.get("developer_mode", False))


def _is_port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout_seconds: float = 20.0) -> bool:
    started_at = time.monotonic()
    while time.monotonic() - started_at < timeout_seconds:
        if _is_port_open(host, port):
            return True
        time.sleep(0.25)
    return False


def _parse_windows_netstat_pids(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return pids

    port_suffix = f":{port}"
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if "LISTENING" not in line.upper():
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        local_address = parts[1]
        pid_text = parts[-1]
        if not local_address.endswith(port_suffix):
            continue

        try:
            pid = int(pid_text)
        except ValueError:
            continue

        if pid > 0 and pid != os.getpid():
            pids.add(pid)

    return pids


def _parse_posix_lsof_pids(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return pids

    for raw_line in result.stdout.splitlines():
        try:
            pid = int(raw_line.strip())
        except ValueError:
            continue

        if pid > 0 and pid != os.getpid():
            pids.add(pid)

    return pids


def _find_port_listener_pids(port: int) -> set[int]:
    if os.name == "nt":
        return _parse_windows_netstat_pids(port)
    return _parse_posix_lsof_pids(port)


def _terminate_pid(pid: int, force: bool = False) -> None:
    if pid <= 0 or pid == os.getpid():
        return

    if os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except OSError:
        pass


def _stop_backend_pids(pids: set[int], label: str) -> None:
    if not pids:
        return

    print(f"[Launcher] Stopping {label} backend process(es): {sorted(pids)}")

    for pid in sorted(pids):
        _terminate_pid(pid, force=False)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        remaining = _find_port_listener_pids(BACKEND_PORT).intersection(pids)
        if not remaining:
            return
        time.sleep(0.25)

    remaining = _find_port_listener_pids(BACKEND_PORT).intersection(pids)
    for pid in sorted(remaining):
        _terminate_pid(pid, force=True)


def _cleanup_backend() -> None:
    global _cleanup_started
    if _cleanup_started:
        return
    _cleanup_started = True

    pids: set[int] = set(_backend_pids_to_stop)
    if _backend_process is not None and _backend_process.poll() is None:
        pids.add(_backend_process.pid)

    current_listeners = _find_port_listener_pids(BACKEND_PORT)
    pids.update(current_listeners.intersection(_backend_pids_to_stop))

    if pids:
        _stop_backend_pids(pids, "owned/adopted")


def _signal_handler(signum, frame) -> None:  # noqa: ANN001
    _cleanup_backend()
    raise SystemExit(128 + int(signum))


def _start_backend(show_backend: bool) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        BACKEND_MODULE,
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
    ]

    stdout = None if show_backend else subprocess.DEVNULL
    stderr = None if show_backend else subprocess.DEVNULL
    creationflags = 0

    if os.name == "nt" and not show_backend:
        creationflags = subprocess.CREATE_NO_WINDOW

    print("[Launcher] Starting backend.")
    return subprocess.Popen(
        command,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )


def _run_desktop() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    command = [sys.executable, "-m", "desktop.app"]
    completed = subprocess.run(command, cwd=str(ROOT_DIR), env=env, check=False)
    return int(completed.returncode)


def main() -> int:
    global _backend_process, _backend_pids_to_stop

    parser = argparse.ArgumentParser(description="Run CharAIface backend and desktop together.")
    parser.add_argument(
        "--show-backend",
        action="store_true",
        help="Show backend logs even when developer_mode is false.",
    )
    parser.add_argument(
        "--reuse-backend",
        action="store_true",
        help="Reuse an already-running backend instead of stopping it first. The launcher will still stop adopted listeners when the desktop exits.",
    )
    parser.add_argument(
        "--keep-backend",
        action="store_true",
        help="Do not stop backend processes when the desktop exits.",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    developer_mode = _read_developer_mode()
    show_backend = bool(args.show_backend or developer_mode)

    existing_pids = _find_port_listener_pids(BACKEND_PORT)
    if existing_pids:
        if args.reuse_backend:
            print(f"[Launcher] Backend is already running. Adopting listener process(es): {sorted(existing_pids)}")
            _backend_pids_to_stop.update(existing_pids)
        else:
            print(f"[Launcher] Backend port is already in use. Restarting listener process(es): {sorted(existing_pids)}")
            _stop_backend_pids(existing_pids, "existing")

    if not _is_port_open(BACKEND_HOST, BACKEND_PORT):
        _backend_process = _start_backend(show_backend=show_backend)
        _backend_pids_to_stop.add(_backend_process.pid)

        if not _wait_for_port(BACKEND_HOST, BACKEND_PORT, timeout_seconds=20.0):
            print("[Launcher] Backend did not open the expected port.")
            _cleanup_backend()
            return 1
    else:
        active_pids = _find_port_listener_pids(BACKEND_PORT)
        _backend_pids_to_stop.update(active_pids)
        print(f"[Launcher] Backend is running on port {BACKEND_PORT}: {sorted(active_pids)}")

    try:
        return _run_desktop()
    finally:
        if args.keep_backend:
            print("[Launcher] Keeping backend process alive because --keep-backend was specified.")
        else:
            _cleanup_backend()


if __name__ == "__main__":
    raise SystemExit(main())
