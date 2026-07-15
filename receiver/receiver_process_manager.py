"""Sequential receiver launcher with exact log and process-delta checks."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from embedded_visualizer import SIMBODY_EXE, simbody_pids, top_level_windows_for_pid


def port_owner(port: int) -> int | None:
    for connection in psutil.net_connections(kind="tcp"):
        if connection.laddr and connection.laddr.port == port and connection.status == psutil.CONN_LISTEN:
            return connection.pid
    return None


class ReceiverProcessManager(QObject):
    status_changed = Signal(str, str)
    visualizer_ready = Signal(str, object)
    visualizer_failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent); self.receiver_dir = Path(__file__).resolve().parent
        self.processes: dict[str, QProcess] = {}; self.ports = {"IK": 5005, "SO": 5006}
        self.baselines: dict[str, set[int]] = {}; self.visualizer_pids: dict[str, int] = {}
        self._pending: str | None = None; self._timer = QTimer(self); self._timer.timeout.connect(self._find_visualizer)
        self._attempts = 0

    def start_all(self): self.start("IK")

    def start(self, kind: str):
        port = self.ports[kind]; owner = port_owner(port)
        if owner:
            self.status_changed.emit(kind, f"Port {port} is already listening (PID {owner}); receiver not started."); return
        self.baselines[kind] = simbody_pids(); self._pending = kind; self._attempts = 0
        process = QProcess(self); process.setWorkingDirectory(str(self.receiver_dir)); process.setProcessChannelMode(QProcess.MergedChannels)
        script = "ik_receiver.py" if kind == "IK" else "so_receiver.py"
        process.readyReadStandardOutput.connect(lambda k=kind, p=process: self._drain(k, p))
        process.finished.connect(lambda code, _status, k=kind: self.status_changed.emit(k, f"Receiver stopped (exit {code})"))
        self.processes[kind] = process; self.status_changed.emit(kind, f"Starting {script} on 0.0.0.0:{port}...")
        process.start(sys.executable, ["-u", script, "0.0.0.0", str(port)])

    def _drain(self, kind, process):
        text = bytes(process.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            print(f"[{kind}] {line}")
            if line.startswith(f"[{kind.lower()}] listening on "):
                self.status_changed.emit(kind, f"Listening on {self.ports[kind]}")
                if self._pending == kind: self._timer.start(250)
            elif line.startswith(f"[{kind.lower()}] cannot start:"):
                self.status_changed.emit(kind, line); self._timer.stop()

    def _find_visualizer(self):
        kind = self._pending
        if not kind: self._timer.stop(); return
        self._attempts += 1
        candidates = simbody_pids() - self.baselines[kind]
        if len(candidates) == 1:
            pid = next(iter(candidates)); windows = top_level_windows_for_pid(pid)
            if len(windows) == 1:
                self.visualizer_pids[kind] = pid; self.visualizer_ready.emit(kind, windows[0]); self._timer.stop(); self._pending = None
                if kind == "IK": self.start("SO")
                return
            if len(windows) > 1:
                self.visualizer_failed.emit(kind, f"PID {pid} has ambiguous visible top-level HWNDs: {[w.hwnd for w in windows]}"); self._timer.stop(); return
        elif len(candidates) > 1:
            self.visualizer_failed.emit(kind, f"New {SIMBODY_EXE} PIDs are ambiguous: {sorted(candidates)}"); self._timer.stop(); return
        if self._attempts >= 120:
            self.visualizer_failed.emit(kind, f"No new {SIMBODY_EXE} window was found after receiver started."); self._timer.stop(); self._pending = None
            if kind == "IK": self.start("SO")

    def retry_embed(self, kind: str):
        pid = self.visualizer_pids.get(kind)
        if not pid: self.visualizer_failed.emit(kind, "No recorded Visualizer PID; restart this receiver."); return
        windows = top_level_windows_for_pid(pid)
        if len(windows) == 1: self.visualizer_ready.emit(kind, windows[0])
        else: self.visualizer_failed.emit(kind, f"PID {pid} has {len(windows)} visible top-level HWNDs.")

    def stop(self, kind: str):
        process = self.processes.get(kind)
        if process and process.state() != QProcess.NotRunning:
            process.terminate()
            if not process.waitForFinished(2000): process.kill(); process.waitForFinished(2000)

    def shutdown(self, panels: dict[str, object]):
        self._timer.stop()
        for panel in panels.values(): panel.close_visualizer()
        for kind in ("IK", "SO"): self.stop(kind)
