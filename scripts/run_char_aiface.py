from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


if not getattr(sys, "frozen", False):
    source_root = Path(__file__).resolve().parents[1]
    source_root_text = str(source_root)
    if source_root_text not in sys.path:
        sys.path.insert(0, source_root_text)

from shared.runtime_paths import app_data_path, is_frozen, runtime_root


ROOT_DIR = runtime_root()
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 10420
BACKEND_MODULE = "backend.app.main:app"
FRONTEND_CONTROL_HOST = "127.0.0.1"
FRONTEND_CONTROL_PORT = 10421
SETTINGS_PATH = app_data_path("settings.json")
LOG_DIR = app_data_path("logs")
LOG_PATH: Path | None = None
_SHOW_LAUNCHER_STATUS = True


_backend_process: subprocess.Popen | None = None
_backend_pids_to_stop: set[int] = set()
_cleanup_started = False
_stdio_handles: list = []


class _TeeTextIO:
    def __init__(self, *streams) -> None:  # noqa: ANN002
        self._streams = streams

    def write(self, text: str) -> int:
        for stream in self._streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def isatty(self) -> bool:
        return any(
            bool(getattr(stream, "isatty", lambda: False)())
            for stream in self._streams
        )


def _timestamped_log_path(prefix: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().strftime("%y%m%d%H%M%S")
    path = LOG_DIR / f"{prefix}_{created_at}.log"
    if not path.exists():
        return path

    suffix = 2
    while True:
        candidate = LOG_DIR / f"{prefix}_{created_at}_{suffix}.log"
        if not candidate.exists():
            return candidate
        suffix += 1


def _launcher_log_path() -> Path:
    global LOG_PATH
    if LOG_PATH is None:
        LOG_PATH = _timestamped_log_path("launcher")
    return LOG_PATH


def _windows_hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _windows_visible_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NEW_CONSOLE}


def _attach_backend_stdio(visible: bool) -> None:
    if visible and os.name == "nt":
        _attach_windows_console_stdio()
        return

    if sys.stdout is not None and sys.stderr is not None:
        return

    try:
        log_path = Path(
            os.environ.get("CHARAIFACE_BACKEND_LOG_PATH") or _timestamped_log_path("backend")
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        log_file = open(os.devnull, "w", encoding="utf-8", buffering=1)

    _stdio_handles.append(log_file)
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file


def _attach_windows_console_stdio() -> None:
    try:
        stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        stdin = open("CONIN$", "r", encoding="utf-8", buffering=1)
    except OSError:
        try:
            import ctypes

            ctypes.windll.kernel32.AllocConsole()
            stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            stdin = open("CONIN$", "r", encoding="utf-8", buffering=1)
        except Exception:
            _attach_backend_stdio(visible=False)
            return

    log_stream = _open_backend_log_from_env()

    if log_stream is not None:
        _stdio_handles.extend([stdout, stderr, stdin, log_stream])
        sys.stdout = _TeeTextIO(stdout, log_stream)
        sys.stderr = _TeeTextIO(stderr, log_stream)
    else:
        _stdio_handles.extend([stdout, stderr, stdin])
        sys.stdout = stdout
        sys.stderr = stderr
    sys.stdin = stdin


def _open_backend_log_from_env():
    log_path_text = os.environ.get("CHARAIFACE_BACKEND_LOG_PATH")
    if not log_path_text:
        return None

    try:
        log_path = Path(log_path_text)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None


def _write_launcher_log(message: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _launcher_log_path().open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def _launcher_status(message: str, *, always_print: bool = False) -> None:
    _write_launcher_log(message)
    if (always_print or _SHOW_LAUNCHER_STATUS) and sys.stdout is not None:
        print(message)


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


def _request_existing_frontend_activation(timeout: float = 0.35) -> bool:
    """Activate an already-running frontend before touching backend lifecycle."""
    try:
        with socket.create_connection(
            (FRONTEND_CONTROL_HOST, FRONTEND_CONTROL_PORT),
            timeout=timeout,
        ) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"activate\n")
            response = sock.recv(64)
            return response.startswith(b"OK\n")
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
            **_windows_hidden_subprocess_kwargs(),
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
            **_windows_hidden_subprocess_kwargs(),
        )
        return

    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except OSError:
        pass


def _stop_backend_pids(pids: set[int], label: str) -> None:
    if not pids:
        return

    _launcher_status(f"[Launcher] Stopping {label} backend process(es): {sorted(pids)}")

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

    if is_frozen():
        command = [sys.executable, "--backend-only"]
    else:
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

    env["CHARAIFACE_BACKEND_VISIBLE"] = "1" if show_backend else "0"
    backend_log_path = _timestamped_log_path("backend")
    env["CHARAIFACE_BACKEND_LOG_PATH"] = str(backend_log_path)

    if show_backend:
        stdout = None
        stderr = None
    else:
        backend_log_path.parent.mkdir(parents=True, exist_ok=True)
        backend_log = open(backend_log_path, "a", encoding="utf-8")
        stdout = backend_log
        stderr = backend_log
    backend_window_kwargs = (
        _windows_visible_subprocess_kwargs()
        if show_backend
        else _windows_hidden_subprocess_kwargs()
    )

    _launcher_status(
        "[Launcher] Starting backend: "
        f"visible={show_backend}, frozen={is_frozen()}, "
        f"log={backend_log_path}, command={command}"
    )
    return subprocess.Popen(
        command,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=stdout,
        stderr=stderr,
        **backend_window_kwargs,
    )


def _run_desktop() -> int:
    if is_frozen():
        from desktop.app import main as desktop_main

        return int(desktop_main())

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    command = [sys.executable, "-m", "desktop.app"]
    completed = subprocess.run(command, cwd=str(ROOT_DIR), env=env, check=False)
    return int(completed.returncode)


def _run_backend_only() -> int:
    _attach_backend_stdio(
        visible=os.environ.get("CHARAIFACE_BACKEND_VISIBLE") == "1"
    )

    import uvicorn

    from backend.app.main import app

    uvicorn.run(
        app,
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        log_level="info",
    )
    return 0


def main() -> int:
    global _backend_process, _backend_pids_to_stop, _SHOW_LAUNCHER_STATUS

    parser = argparse.ArgumentParser(description="Run CharAIface backend and desktop together.")
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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

    if args.backend_only:
        return _run_backend_only()

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    developer_mode = _read_developer_mode()
    show_backend = bool(args.show_backend or developer_mode)
    _SHOW_LAUNCHER_STATUS = bool(show_backend)
    _write_launcher_log(
        "[Launcher] CharAIface launcher started. "
        f"pid={os.getpid()}, frozen={is_frozen()}, root={ROOT_DIR}, "
        f"settings={SETTINGS_PATH}, log={_launcher_log_path()}"
    )
    _write_launcher_log(
        f"[Launcher] developer_mode={developer_mode}, show_backend={show_backend}"
    )

    if _request_existing_frontend_activation():
        _launcher_status("[Launcher] Existing frontend session window activated.")
        return 0

    existing_pids = _find_port_listener_pids(BACKEND_PORT)
    if existing_pids:
        if args.reuse_backend:
            _launcher_status(f"[Launcher] Backend is already running. Adopting listener process(es): {sorted(existing_pids)}")
            _backend_pids_to_stop.update(existing_pids)
        else:
            _launcher_status(f"[Launcher] Backend port is already in use. Restarting listener process(es): {sorted(existing_pids)}")
            _stop_backend_pids(existing_pids, "existing")

    if not _is_port_open(BACKEND_HOST, BACKEND_PORT):
        _backend_process = _start_backend(show_backend=show_backend)
        _backend_pids_to_stop.add(_backend_process.pid)

        if not _wait_for_port(BACKEND_HOST, BACKEND_PORT, timeout_seconds=20.0):
            return_code = _backend_process.poll()
            _launcher_status(
                "[Launcher] Backend did not open the expected port. "
                f"backend_pid={_backend_process.pid}, returncode={return_code}",
                always_print=True,
            )
            _cleanup_backend()
            return 1
    else:
        active_pids = _find_port_listener_pids(BACKEND_PORT)
        _backend_pids_to_stop.update(active_pids)
        _launcher_status(f"[Launcher] Backend is running on port {BACKEND_PORT}: {sorted(active_pids)}")

    try:
        return _run_desktop()
    finally:
        if args.keep_backend:
            _launcher_status("[Launcher] Keeping backend process alive because --keep-backend was specified.")
        else:
            _cleanup_backend()


if __name__ == "__main__":
    raise SystemExit(main())
