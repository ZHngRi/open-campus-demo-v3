"""Win32 ownership and embedding for the two existing Simbody windows."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

IS_WINDOWS = os.name == "nt"
SIMBODY_EXE = "simbody-visualizer.exe"

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    LONG_PTR = ctypes.c_ssize_t
    HWND = wintypes.HWND
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [HWND]; user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [HWND]; user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [HWND]; user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]; user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetParent.argtypes = [HWND]; user32.GetParent.restype = HWND
    user32.GetClientRect.argtypes = [HWND, ctypes.POINTER(RECT)]; user32.GetClientRect.restype = wintypes.BOOL
    user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]; user32.GetWindowLongPtrW.restype = LONG_PTR
    user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, LONG_PTR]; user32.SetWindowLongPtrW.restype = LONG_PTR
    user32.SetParent.argtypes = [HWND, HWND]; user32.SetParent.restype = HWND
    user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [HWND, ctypes.c_int]; user32.ShowWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]; user32.PostMessageW.restype = wintypes.BOOL

GWL_STYLE = -16
WS_CHILD, WS_VISIBLE, WS_POPUP = 0x40000000, 0x10000000, 0x80000000
WS_CAPTION, WS_THICKFRAME, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00020000, 0x00010000, 0x00080000
SW_SHOW = 5
SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_SHOWWINDOW = 0x0004, 0x0010, 0x0020, 0x0040
WM_CLOSE = 0x0010


def simbody_pids() -> set[int]:
    return {proc.info["pid"] for proc in psutil.process_iter(["pid", "name"])
            if (proc.info.get("name") or "").lower() == SIMBODY_EXE}


@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    parent: int


def top_level_windows_for_pid(pid: int) -> list[WindowInfo]:
    if not IS_WINDOWS:
        return []
    found: list[WindowInfo] = []
    @EnumWindowsProc
    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd) or user32.GetParent(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        found.append(WindowInfo(int(hwnd), pid, buffer.value, int(user32.GetParent(hwnd) or 0)))
        return True

    if not user32.EnumWindows(callback, 0):
        raise OSError(ctypes.get_last_error(), "EnumWindows failed")
    return found


class NativeContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)
        self.hwnd: int | None = None
        self._last_size = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.resize_embedded)

    def resizeEvent(self, event):
        super().resizeEvent(event); self._schedule_resize()

    def showEvent(self, event):
        super().showEvent(event); self._schedule_resize()

    def _schedule_resize(self):
        # Coalesce rapid splitter events; OpenGL child windows otherwise receive hundreds of SetWindowPos calls.
        self._resize_timer.start(16)

    def resize_embedded(self):
        if not self.hwnd or not IS_WINDOWS or not user32.IsWindow(self.hwnd): return
        rect = RECT()
        if not user32.GetClientRect(int(self.winId()), ctypes.byref(rect)):
            raise OSError(ctypes.get_last_error(), "GetClientRect failed for native container")
        size = (rect.right - rect.left, rect.bottom - rect.top)
        if not all(size) or size == self._last_size: return
        self._last_size = size
        if not user32.SetWindowPos(self.hwnd, None, 0, 0, size[0], size[1],
                                   SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW):
            raise OSError(ctypes.get_last_error(), f"SetWindowPos failed for HWND={self.hwnd}")


class EmbeddedWindowPanel(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.container = NativeContainer(self)
        self.status = QLabel("Waiting for receiver...", self)
        self.status.setWordWrap(True)
        layout = QVBoxLayout(self); layout.setContentsMargins(6, 6, 6, 6)
        heading = QLabel(title, self); heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading); layout.addWidget(self.container, 1); layout.addWidget(self.status)

    def set_status(self, text: str): self.status.setText(text)

    def embed(self, info: WindowInfo):
        if not IS_WINDOWS:
            raise RuntimeError("Simbody embedding is only available on Windows.")
        child, parent = info.hwnd, int(self.container.winId())
        ctypes.set_last_error(0)
        style = user32.GetWindowLongPtrW(child, GWL_STYLE)
        error = ctypes.get_last_error()
        if style == 0 and error: raise OSError(error, f"GetWindowLongPtrW pid={info.pid} hwnd={child}")
        new_style = (style | WS_CHILD | WS_VISIBLE) & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        ctypes.set_last_error(0)
        result = user32.SetWindowLongPtrW(child, GWL_STYLE, new_style)
        if result == 0 and ctypes.get_last_error(): raise OSError(ctypes.get_last_error(), f"SetWindowLongPtrW pid={info.pid} child={child} parent={parent}")
        ctypes.set_last_error(0)
        user32.SetParent(child, parent)
        if ctypes.get_last_error(): raise OSError(ctypes.get_last_error(), f"SetParent pid={info.pid} child={child} parent={parent}")
        if int(user32.GetParent(child) or 0) != parent:
            raise RuntimeError(f"SetParent verification failed: pid={info.pid}, child={child}, parent={parent}")
        self.container.hwnd = child; self.container._last_size = None; self.container.resize_embedded()
        user32.ShowWindow(child, SW_SHOW)
        self.set_status(f"Visualizer embedded (PID {info.pid}, HWND {child})")

    def close_visualizer(self):
        if self.container.hwnd and IS_WINDOWS and user32.IsWindow(self.container.hwnd):
            user32.PostMessageW(self.container.hwnd, WM_CLOSE, 0, 0)
