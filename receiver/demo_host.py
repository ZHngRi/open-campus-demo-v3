"""Windows native desktop host for the existing FastAPI sender and OpenSim receivers."""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

if os.name == "nt":
    # One DPI policy, set before QApplication. Cross-process GLUT embedding can still be limited on mixed-DPI monitors.
    ctypes.WinDLL("user32", use_last_error=True).SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QScrollArea, QSplitter, QStatusBar, QToolBar

from embedded_visualizer import EmbeddedWindowPanel
from native_control_panel import NativeControlPanel
from receiver_process_manager import ReceiverProcessManager

CONFIG_PATH = Path(__file__).resolve().parent / "demo_host_config.json"
DEFAULT_CONFIG = {"backend_url": "http://127.0.0.1:8056", "receiver_host": "", "ik_port": 5005, "so_port": 5006,
    "main_window_geometry": {"x": 100, "y": 100, "width": 1800, "height": 1000}, "controls_visible": True,
    "visualizer_layout": "horizontal", "outer_splitter_sizes": [520, 1280], "horizontal_visualizer_sizes": [640, 640], "vertical_visualizer_sizes": [500, 500]}


def load_config():
    config = dict(DEFAULT_CONFIG)
    if not CONFIG_PATH.exists(): return config
    try: raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc: print(f"Invalid demo host configuration: {exc}"); return config
    for key, default in DEFAULT_CONFIG.items():
        if isinstance(raw.get(key), type(default)): config[key] = raw[key]
        elif key in raw: print(f"Invalid demo host configuration field {key}; using default.")
    if not isinstance(config["main_window_geometry"], dict) or not all(isinstance(config["main_window_geometry"].get(k), int) for k in ("x", "y", "width", "height")):
        print("Invalid main_window_geometry; using default."); config["main_window_geometry"] = dict(DEFAULT_CONFIG["main_window_geometry"])
    for key in ("outer_splitter_sizes", "horizontal_visualizer_sizes", "vertical_visualizer_sizes"):
        value = config[key]
        if not (isinstance(value, list) and len(value) == 2 and all(isinstance(n, int) and n > 0 for n in value)):
            print(f"Invalid {key}; using default."); config[key] = list(DEFAULT_CONFIG[key])
    for key in ("ik_port", "so_port"):
        if not isinstance(config[key], int) or not 1 <= config[key] <= 65535:
            print(f"Invalid {key}; using default."); config[key] = DEFAULT_CONFIG[key]
    if config["visualizer_layout"] not in {"horizontal", "vertical"}: print("Invalid visualizer_layout; using horizontal."); config["visualizer_layout"] = "horizontal"
    return config


class DemoHostWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.config = load_config(); self.closing = False; self.setWindowTitle("OpenCampus Native Desktop Demo")
        g = self.config["main_window_geometry"]; self.setGeometry(g["x"], g["y"], g["width"], g["height"]); self._build()
        self.manager = ReceiverProcessManager(self); self.manager.status_changed.connect(self._receiver_status); self.manager.visualizer_ready.connect(self._embed); self.manager.visualizer_failed.connect(self._embed_failed); self.manager.start_all()

    def _build(self):
        toolbar = QToolBar("Visualizer"); self.addToolBar(toolbar)
        for name, callback in [("Side by Side", lambda: self.set_layout("horizontal")), ("Top and Bottom", lambda: self.set_layout("vertical")), ("Hide Controls", self.toggle_controls), ("Fullscreen", self.toggle_fullscreen), ("Retry Embed", self.retry_embed), ("Restart IK", lambda: self.restart("IK")), ("Restart SO", lambda: self.restart("SO"))]:
            action = QAction(name, self); action.triggered.connect(callback); toolbar.addAction(action)
            if name == "Hide Controls": self.controls_action = action
        self.controls = NativeControlPanel(self.config, self)
        self.controls_scroll = QScrollArea(self); self.controls_scroll.setWidget(self.controls); self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setMinimumWidth(280); self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ik = EmbeddedWindowPanel("Inverse Kinematics", self); self.so = EmbeddedWindowPanel("Static Optimization", self)
        self.visualizers = QSplitter(Qt.Horizontal); self.visualizers.addWidget(self.ik); self.visualizers.addWidget(self.so)
        self.outer = QSplitter(Qt.Horizontal); self.outer.setChildrenCollapsible(False); self.outer.setHandleWidth(9); self.outer.setOpaqueResize(True)
        self.outer.addWidget(self.controls_scroll); self.outer.addWidget(self.visualizers); self.outer.setStretchFactor(0, 0); self.outer.setStretchFactor(1, 1); self.setCentralWidget(self.outer)
        self.visualizers.setChildrenCollapsible(False); self.visualizers.setHandleWidth(9); self.visualizers.setOpaqueResize(True); self.visualizers.setStretchFactor(0, 1); self.visualizers.setStretchFactor(1, 1)
        self.outer.setSizes(self.config["outer_splitter_sizes"]); self.set_layout(self.config["visualizer_layout"])
        if not self.config["controls_visible"]: self.toggle_controls()
        self.status = QStatusBar(self); self.setStatusBar(self.status); self.status.showMessage("Starting receivers...")
    def _receiver_status(self, kind, text):
        (self.ik if kind == "IK" else self.so).set_status(text); self.status.showMessage(f"{kind}: {text}")
    def _embed(self, kind, info):
        panel = self.ik if kind == "IK" else self.so
        try: panel.embed(info); self.status.showMessage(f"{kind} Visualizer embedded")
        except Exception as exc: self._embed_failed(kind, str(exc))
    def _embed_failed(self, kind, message):
        (self.ik if kind == "IK" else self.so).set_status(f"Embedding failed: {message}"); self.status.showMessage(f"{kind}: {message}")
    def set_layout(self, layout):
        self.config["visualizer_layout"] = layout; self.visualizers.setOrientation(Qt.Horizontal if layout == "horizontal" else Qt.Vertical)
        self.visualizers.setSizes(self.config["horizontal_visualizer_sizes"] if layout == "horizontal" else self.config["vertical_visualizer_sizes"])
    def toggle_controls(self):
        visible = not self.controls_scroll.isHidden(); self.controls_scroll.setVisible(not visible); self.controls_action.setText("Show Controls" if visible else "Hide Controls")
        if not visible: self.outer.setSizes(self.config["outer_splitter_sizes"])
    def toggle_fullscreen(self): self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen(): self.showNormal(); return
        super().keyPressEvent(event)
    def retry_embed(self): self.manager.retry_embed("IK"); self.manager.retry_embed("SO")
    def restart(self, kind): self.manager.stop(kind); (self.ik if kind == "IK" else self.so).set_status("Restart requested..."); self.manager.start(kind)
    def closeEvent(self, event):
        self.closing = True; self.controls.poll_timer.stop(); self.manager.shutdown({"IK": self.ik, "SO": self.so})
        self.config.update({"receiver_host": self.controls.host.text(), "ik_port": self.controls.ik_port.value(), "so_port": self.controls.so_port.value(), "controls_visible": not self.controls_scroll.isHidden(), "outer_splitter_sizes": self.outer.sizes()})
        self.config["horizontal_visualizer_sizes" if self.config["visualizer_layout"] == "horizontal" else "vertical_visualizer_sizes"] = self.visualizers.sizes()
        self.config["main_window_geometry"] = {"x": self.x(), "y": self.y(), "width": self.width(), "height": self.height()}; CONFIG_PATH.write_text(json.dumps(self.config, indent=2), encoding="utf-8"); event.accept()


def main():
    app = QApplication(sys.argv); window = DemoHostWindow(); window.show(); return app.exec()

if __name__ == "__main__": raise SystemExit(main())
