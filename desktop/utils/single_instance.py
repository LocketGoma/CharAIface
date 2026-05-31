from __future__ import annotations

import socket
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal


DEFAULT_FRONTEND_CONTROL_HOST = "127.0.0.1"
DEFAULT_FRONTEND_CONTROL_PORT = 10421
_ACTIVATE_COMMAND = b"activate\n"
_OK_RESPONSE = b"OK\n"


def request_existing_frontend_activation(
    host: str = DEFAULT_FRONTEND_CONTROL_HOST,
    port: int = DEFAULT_FRONTEND_CONTROL_PORT,
    timeout_seconds: float = 0.35,
) -> bool:
    """Ask an already-running frontend instance to show its session window.

    This intentionally uses a tiny localhost TCP control channel instead of
    process-name scanning.  It works the same on Windows and macOS, and it lets
    both the launcher and accidental second frontend processes activate the
    existing window without starting another frontend.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
            sock.settimeout(timeout_seconds)
            sock.sendall(_ACTIVATE_COMMAND)
            response = sock.recv(64)
            return response.startswith(_OK_RESPONSE)
    except OSError:
        return False


class FrontendSingleInstanceServer(QObject):
    """Local control server owned by the first frontend process."""

    activate_requested = Signal()

    def __init__(
        self,
        on_activate: Callable[[], None],
        host: str = DEFAULT_FRONTEND_CONTROL_HOST,
        port: int = DEFAULT_FRONTEND_CONTROL_PORT,
    ) -> None:
        super().__init__()

        self.host = host
        self.port = port
        self.activate_requested.connect(on_activate)

        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        if self._socket is not None:
            return True

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(8)
            server_socket.settimeout(0.25)
        except OSError:
            server_socket.close()
            return False

        self._socket = server_socket
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._serve,
            name="CharAIfaceFrontendSingleInstanceServer",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()

        sock = self._socket
        self._socket = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.6)

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            sock = self._socket
            if sock is None:
                return

            try:
                client, _address = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            with client:
                try:
                    client.settimeout(0.5)
                    data = client.recv(128).strip().lower()
                    if data == b"activate":
                        self.activate_requested.emit()
                        client.sendall(_OK_RESPONSE)
                    else:
                        client.sendall(b"UNKNOWN\n")
                except OSError:
                    pass
