"""Thread-safe HTTP client for the existing sender FastAPI service.

The endpoint paths and payload keys in this module mirror ``sender/main.py``.
No OpenCap or TCP sending logic lives here; those remain owned by the backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

REQUEST_TIMEOUT_SECONDS = 20


class BackendError(RuntimeError):
    pass


def validate_backend_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BackendError("Sender Server must be a complete http:// or https:// URL.")
    return value


class BackendClient:
    def __init__(self, base_url: str):
        self.base_url = validate_backend_url(base_url).rstrip("/")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = requests.request(method, self.base_url + path,
                                        timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            if "RemoteDisconnected" in str(exc) or "Remote end closed connection" in str(exc):
                raise BackendError(f"Backend closed the connection. Check the sender server log. ({method} {path})") from exc
            raise BackendError(f"Network error calling {method} {path}: {exc}") from exc
        except requests.RequestException as exc:
            raise BackendError(f"Network error calling {method} {path}: {exc}") from exc
        if not response.ok:
            raise BackendError(f"HTTP {response.status_code} for {method} {path}: {response.text[:500]}")
        try:
            return response.json()
        except ValueError as exc:
            raise BackendError(f"Invalid JSON from {method} {path}: {response.text[:500]}") from exc

    def sessions(self): return self._request("GET", "/sessions")
    def sync_all(self): return self._request("POST", "/sessions/sync-all")
    def pull_remote(self): return self._request("POST", "/sessions/pull-remote")
    def start_processing(self, session_id: str): return self._request("POST", f"/sessions/{session_id}/start")
    def delete_session(self, session_id: str): return self._request("DELETE", f"/sessions/{session_id}")
    def files(self, session_id: str): return self._request("GET", f"/sessions/{session_id}/files")
    def active_file(self): return self._request("GET", "/active-file")
    def set_active_file(self, config: dict): return self._request("POST", "/active-file", json=config)
    def send_active_file(self): return self._request("POST", "/send-active-file")
    def send_queue(self): return self._request("GET", "/send-queue")

    def upload_video(self, path: str, processing_target: str):
        if processing_target not in {"opencap", "planb", "race"}:
            raise BackendError(f"Unsupported processing target: {processing_target}")
        with open(path, "rb") as handle:
            return self._request("POST", "/videos/upload", files={"file": handle},
                                 data={"processing_target": processing_target})


class _RequestSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(object, str)


class _Request(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _RequestSignals()

    def run(self):
        try:
            self.signals.completed.emit(self, self.operation())
        except Exception as exc:  # carried to the GUI thread as text
            self.signals.failed.emit(self, str(exc))


class AsyncBackend(QObject):
    """Runs every requests call in Qt's global thread pool."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        # Keep QRunnable and callbacks alive until their result is delivered on
        # the GUI thread. Without this, a fast QThreadPool auto-delete can drop
        # a queued Python callback after the HTTP server has already returned 200.
        self._active: dict[_Request, tuple[Callable[[Any], None], Callable[[str], None]]] = {}

    def submit(self, operation: Callable[[], Any], done: Callable[[Any], None],
               failed: Callable[[str], None]):
        request = _Request(operation)
        request.setAutoDelete(False)
        self._active[request] = (done, failed)
        # Bound QObject methods are queued back to this object's GUI thread.
        request.signals.completed.connect(self._deliver_success)
        request.signals.failed.connect(self._deliver_failure)
        self.pool.start(request)

    def _deliver_success(self, request: _Request, data: Any):
        callbacks = self._active.pop(request, None)
        if callbacks:
            callbacks[0](data)

    def _deliver_failure(self, request: _Request, error: str):
        callbacks = self._active.pop(request, None)
        if callbacks:
            callbacks[1](error)
