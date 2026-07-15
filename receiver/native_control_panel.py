"""Native PySide6 management UI for the existing sender FastAPI endpoints."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy)

from backend_client import AsyncBackend, BackendClient, BackendError, REQUEST_TIMEOUT_SECONDS

POLL_INTERVAL_MS = 3000


class BusyButton(QPushButton):
    """A button-local animated busy marker, so each operation shows its state."""
    _frames = ("◐", "◓", "◑", "◒")

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._idle_text = text
        self._frame = 0
        self._busy_text = "Processing"
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._advance)

    def set_busy(self, busy: bool, text: str = "Processing"):
        if busy:
            self._busy_text = text
            self.setEnabled(False)
            self.setText(f"{self._frames[self._frame]} {text}")
            self._timer.start()
        else:
            self._timer.stop()
            self.setText(self._idle_text)
            self.setEnabled(True)

    def _advance(self):
        self._frame = (self._frame + 1) % len(self._frames)
        self.setText(f"{self._frames[self._frame]} {self._busy_text}")


class NativeControlPanel(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent); self.config = config; self.client: BackendClient | None = None; self.sessions = []
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.async_backend = AsyncBackend(self); self.selected_video = ""; self._build(); self.poll_timer = QTimer(self); self.poll_timer.timeout.connect(self.refresh_sessions)

    def _group(self, title):
        group = QGroupBox(title, self); group.setLayout(QVBoxLayout()); return group

    def _build(self):
        root = QVBoxLayout(self)
        backend = self._group("Backend"); row = QHBoxLayout(); self.backend_url = QLineEdit(self.config["backend_url"]); self.connect_btn = BusyButton("Connect")
        row.addWidget(self.backend_url, 1); row.addWidget(self.connect_btn); backend.layout().addLayout(row); self.connection = self._status_label("Not connected"); backend.layout().addWidget(self.connection); self.connect_btn.clicked.connect(self.connect_backend); root.addWidget(backend)
        video = self._group("Video"); name_form = QFormLayout(); self.video_name = QLineEdit(); self.video_name.setPlaceholderText("Legacy OpenCap name (not sent to Plan B backend)")
        name_form.addRow("OpenCap Name", self.video_name); video.layout().addLayout(name_form)
        target_form = QFormLayout(); self.processing_target = QComboBox()
        self.processing_target.addItem("OpenCap", "opencap"); self.processing_target.addItem("Linux Plan B", "planb"); self.processing_target.addItem("Race Both", "race")
        target_form.addRow("Processing Target", self.processing_target); video.layout().addLayout(target_form)
        self.processing_target.currentIndexChanged.connect(self._target_changed)
        row = QHBoxLayout(); choose = QPushButton("Choose Video"); self.upload_btn = BusyButton("Upload & Process"); choose.clicked.connect(self.choose_video); self.upload_btn.clicked.connect(self.upload_video)
        row.addWidget(choose); row.addWidget(self.upload_btn); video.layout().addLayout(row); self.video_label = self._status_label("No file selected (.mp4, .mov)"); video.layout().addWidget(self.video_label); root.addWidget(video)
        sessions = self._group("Sessions"); self.table = QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["Name", "Status", "Created At", "Download", "Note"])
        self.table.itemSelectionChanged.connect(self.load_files)
        # Explicit cell click avoids relying solely on itemSelectionChanged,
        # which may not fire when a refresh preserves the selected row.
        self.table.cellClicked.connect(lambda row, _column: self.load_files_for_row(row))
        sessions.layout().addWidget(self.table); buttons = QHBoxLayout();
        self.session_buttons = {}
        for label, action in [("Refresh", self.refresh_sessions), ("Start Selected", self.process_selected), ("Pull Remote", self.pull_remote), ("Sync All", self.sync_all), ("Delete", self.delete_selected)]:
            button = BusyButton(label); button.clicked.connect(action); buttons.addWidget(button); self.session_buttons[label] = button
        sessions.layout().addLayout(buttons); root.addWidget(sessions, 1)
        self.session_details = self._status_label("Selected Session Details: none")
        sessions.layout().addWidget(self.session_details)
        files = self._group("Result Files"); form = QFormLayout(); self.trc = QComboBox(); self.mot = QComboBox(); form.addRow("IK TRC", self.trc); form.addRow("IK MOT (for SO)", self.mot); files.layout().addLayout(form)
        self.files_status = self._status_label("Select a session to load its result files."); files.layout().addWidget(self.files_status)
        self.refresh_files_btn = BusyButton("Refresh Files"); self.refresh_files_btn.clicked.connect(self.load_files); files.layout().addWidget(self.refresh_files_btn); root.addWidget(files)
        receiver = self._group("Receiver"); form = QFormLayout(); self.host = QLineEdit(self.config["receiver_host"]); self.ik_port = QSpinBox(); self.so_port = QSpinBox()
        for box, value in ((self.ik_port, self.config["ik_port"]), (self.so_port, self.config["so_port"])): box.setRange(1, 65535); box.setValue(value)
        form.addRow("Receiver Host", self.host); form.addRow("IK Port", self.ik_port); form.addRow("SO Port", self.so_port); receiver.layout().addLayout(form); self.send_btn = BusyButton("Send Selected Files"); self.send_btn.clicked.connect(self.send_selected); receiver.layout().addWidget(self.send_btn); self.send_status = self._status_label("Idle"); receiver.layout().addWidget(self.send_status); root.addWidget(receiver)

    def _status_label(self, text: str):
        """Status text must wrap without imposing its long error-line width on the splitter."""
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setMinimumWidth(0)
        return label

    def _run(self, operation, done, label, button: BusyButton | None = None, busy_text="Processing", on_failure=None):
        if not self.client: self._error("Connect to Sender Server first."); return
        # Each action owns one request. A response arriving after the UI timeout
        # is ignored, preventing a second click from racing the first operation.
        settled = False
        if button: button.set_busy(True, busy_text)
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        def finish(callback, value):
            nonlocal settled
            if settled: return
            settled = True
            watchdog.stop(); watchdog.deleteLater()
            if button: button.set_busy(False)
            callback(value)
        def completed(data):
            finish(done, data)
        def failed(error):
            finish(on_failure or (lambda message: self._error(f"{label}: {message}")), error)
        watchdog.timeout.connect(lambda: finish(
            on_failure or (lambda message: self._error(f"{label}: {message}")),
            f"request timed out after {REQUEST_TIMEOUT_SECONDS} seconds"))
        watchdog.start((REQUEST_TIMEOUT_SECONDS + 2) * 1000)
        self.async_backend.submit(operation, completed, failed)

    def _error(self, text): self.connection.setText(text)
    def _target_changed(self):
        is_planb = self.processing_target.currentData() == "planb"
        self.video_name.setEnabled(not is_planb)
        if is_planb: self.video_name.setToolTip("Not used by Plan B")
        else: self.video_name.setToolTip("")
    def connect_backend(self):
        try: self.client = BackendClient(self.backend_url.text())
        except BackendError as exc: self._error(str(exc)); return
        self._run(self.client.sessions, lambda data: self._connected(data), "Connect failed", self.connect_btn, "Connecting")
    def _connected(self, data): self.connection.setText("Connected"); self.config["backend_url"] = self.backend_url.text(); self._set_sessions(data)
    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose video", "", "Video (*.mp4 *.mov)")
        if path:
            self.selected_video = path; self.video_label.setText(path)
            if not self.video_name.text().strip(): self.video_name.setText(Path(path).stem)
    def upload_video(self):
        if not self.selected_video: self._error("Choose a .mp4 or .mov video first."); return
        target = self.processing_target.currentData()
        self.video_label.setText("Uploading..."); self._run(lambda: self.client.upload_video(self.selected_video, target), self._uploaded, "Upload failed", self.upload_btn, "Uploading")
    def _uploaded(self, data):
        session_id = data.get("session_id", "")
        target = data.get("processing_target", self.processing_target.currentData())
        label = {"opencap": "Starting OpenCap", "planb": "Starting Plan B", "race": "Starting Race"}[target]
        self.video_label.setText(f"Uploaded: {session_id}; {label}...")
        self._run(lambda: self.client.start_processing(session_id), self._submitted_to_opencap,
                  "Start failed", self.upload_btn, label)
    def _submitted_to_opencap(self, data):
        self.video_label.setText(f"OpenCap processing: {data.get('session_id', '')}")
        self.refresh_sessions()
    def refresh_sessions(self): self._run(self.client.sessions, self._set_sessions, "Refresh failed", self.session_buttons["Refresh"], "Refreshing")
    def sync_all(self): self._run(self.client.sync_all, lambda _: self.refresh_sessions(), "Sync failed", self.session_buttons["Sync All"], "Syncing")
    def pull_remote(self): self._run(self.client.pull_remote, lambda _: self.refresh_sessions(), "Pull failed", self.session_buttons["Pull Remote"], "Pulling")
    def _set_sessions(self, data):
        selected_id = self.selected_id()
        self.sessions = data.get("sessions", []); self.table.blockSignals(True); self.table.setRowCount(len(self.sessions)); active = False
        selected_row = -1
        for row, session in enumerate(self.sessions):
            active |= self._session_is_active(session)
            if session.get("session_id") == selected_id: selected_row = row
            fields = ("name", self._status_text(session), "created_at", "download_status", "note")
            for column, value in enumerate(fields):
                item = QTableWidgetItem(str(value)); item.setData(256, session.get("session_id", "")); self.table.setItem(row, column, item)
        if selected_row >= 0: self.table.selectRow(selected_row)
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        if active and not self.poll_timer.isActive(): self.poll_timer.start(POLL_INTERVAL_MS)
        elif not active: self.poll_timer.stop()
    def selected_id(self):
        row = self.table.currentRow(); return self.table.item(row, 0).data(256) if row >= 0 and self.table.item(row, 0) else ""
    def process_selected(self):
        sid = self.selected_id();
        if not sid: self._error("Select a session first."); return
        session = next((item for item in self.sessions if item.get("session_id") == sid), {})
        if session.get("status") in {"processing", "done"}:
            self._error(f"Session is already {session.get('status')}."); return
        target = session.get("processing_target", "opencap")
        self._run(lambda: self.client.start_processing(sid), lambda _: self.refresh_sessions(), "Start failed", self.session_buttons["Start Selected"], f"Starting {self._target_label(target)}")
    def delete_selected(self):
        sid = self.selected_id()
        if not sid: self._error("Select a session first."); return
        if QMessageBox.question(self, "Delete session", f"Delete {sid}?") != QMessageBox.Yes: return
        self._run(lambda: self.client.delete_session(sid), lambda _: self.refresh_sessions(), "Delete failed", self.session_buttons["Delete"], "Deleting")
    def load_files(self):
        sid = self.selected_id()
        if sid: self.load_files_for_session(sid)
        else: self.files_status.setText("Select a session first.")

    def load_files_for_row(self, row: int):
        item = self.table.item(row, 0)
        if item: self.load_files_for_session(item.data(256))

    def load_files_for_session(self, session_id: str):
        session = next((item for item in self.sessions if item.get("session_id") == session_id), {})
        self._update_session_details(session)
        self.files_status.setText(f"Loading result files for {session_id}...")
        self._run(lambda: self.client.files(session_id), self._set_files,
                  "File list failed", self.refresh_files_btn, "Loading",
                  lambda error: self.files_status.setText(f"Result Files error: {error}"))

    def _set_files(self, data):
        if data.get("error"):
            self.files_status.setText(f"Result Files: {data['error']}")
            return
        self.trc.clear(); self.mot.clear(); self.trc.addItem("(none)", ""); self.mot.addItem("(none)", "")
        trc_count = mot_count = 0
        for file in data.get("files", []):
            file_type = str(file.get("file_type", "")).lower()
            if file_type == "trc": self.trc.addItem(file["file_name"], file["file_path"]); trc_count += 1
            elif file_type == "mot": self.mot.addItem(file["file_name"], file["file_path"]); mot_count += 1
        self.files_status.setText(
            f"Loaded {trc_count} TRC and {mot_count} MOT file(s)."
            if trc_count or mot_count else "No TRC or MOT files were returned for this session."
        )
        session = next((item for item in self.sessions if item.get("session_id") == data.get("session_id")), {})
        if session.get("winner"):
            if trc_count: self.trc.setCurrentIndex(1)
            if mot_count: self.mot.setCurrentIndex(1)

    @staticmethod
    def _target_label(value): return {"opencap": "OpenCap", "planb": "Linux Plan B", "race": "Race Both"}.get(value, "Legacy/OpenCap")
    @staticmethod
    def _branch_label(value): return {"opencap": "OpenCap", "planb": "Plan B"}.get(value, value)
    def _status_text(self, session):
        branches = session.get("branches") or {}
        lines = [str(session.get("status", ""))]
        for key in ("opencap", "planb"):
            if key in branches:
                state = branches[key].get("status", "queued")
                lines.append(f"{self._branch_label(key)}: {'Backup result' if state == 'backup' else state}")
        if session.get("winner"):
            lines.append(f"Winner: {self._branch_label(session['winner'])}")
        return "\n".join(lines)
    def _session_is_active(self, session):
        if session.get("status") == "processing" or session.get("download_status") == "downloading": return True
        return any((state or {}).get("status") in {"queued", "processing"} for state in (session.get("branches") or {}).values())
    def _update_session_details(self, session):
        if not session: self.session_details.setText("Selected Session Details: none"); return
        branches = session.get("branches") or {}
        details = [f"Target: {self._target_label(session.get('processing_target', 'opencap'))}"]
        for key in ("opencap", "planb"):
            if key in branches: details.append(f"{self._branch_label(key)}: {'Backup result' if branches[key].get('status') == 'backup' else branches[key].get('status', 'queued')}")
        details.append(f"Winner: {self._branch_label(session.get('winner')) if session.get('winner') else 'None'}")
        if session.get("note"): details.append(f"Message: {session['note']}")
        self.session_details.setText(" | ".join(details))
    def send_selected(self):
        trc, mot, host = self.trc.currentData() or "", self.mot.currentData() or "", self.host.text().strip()
        if not (trc or mot): self._error("Select at least one TRC or MOT file."); return
        if not host: self._error("Receiver Host is required."); return
        self.send_status.setText("Saving active file...")
        def save_then_send():
            active = self.client.active_file(); active.update({"file_path": trc, "file_path_so": mot, "receiver_host": host, "receiver_port": self.ik_port.value(), "receiver_port_mot": self.so_port.value()})
            self.client.set_active_file(active); return self.client.send_active_file()
        self._run(save_then_send, self._sent, "Send failed", self.send_btn, "Sending",
                  lambda error: self.send_status.setText(f"Send failed: {error}"))
    def _sent(self, data): self.send_status.setText("Queued" if data.get("queued") else data.get("error", str(data)))
