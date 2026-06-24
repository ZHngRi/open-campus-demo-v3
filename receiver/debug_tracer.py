"""
Debug tracer — 非侵入式，删除本文件即恢复原状。
=================================================
用法:
    python debug_tracer.py                       # 等价于 python receive_and_play.py
    python debug_tracer.py 0.0.0.0 5005          # 传参

输出: debug_trace_<时间戳>.log（在 receiver 目录下）

追踪内容:
  - 线程创建 / 启动 / 退出
  - time.sleep 调用（ENTER/EXIT）
  - Queue put / get / get_nowait
  - OpenSim Model 创建次数
  - IK assemble / SO step 时序
  - 所有 print 输出（带时间戳和线程名）
"""

import sys
import os
import time
import threading
import queue as _queue_module
import builtins
import functools
from datetime import datetime
from pathlib import Path

# ================================================================
# Log 基础设施
# ================================================================

_RECEIVER_DIR = Path(__file__).resolve().parent
_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_PATH = _RECEIVER_DIR / f"debug_trace_{_TIMESTAMP}.log"

_t0 = time.perf_counter()


def _elapsed():
    return time.perf_counter() - _t0


def _log(msg: str):
    t = threading.current_thread()
    line = f"[{_elapsed():.4f}s] [{t.name}] {msg}"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    # 用原始 stderr.write 避免递归（print 已被 patch）
    try:
        sys.__stderr__.write(line + "\n")
        sys.__stderr__.flush()
    except Exception:
        pass


_log(f"=== DEBUG TRACER START ===  log: {_LOG_PATH}")

# ================================================================
# Patch 1: time.sleep
# ================================================================

_original_sleep = time.sleep

@functools.wraps(_original_sleep)
def _sleep(seconds):
    _log(f"sleep({seconds:.4f})  ENTER")
    _original_sleep(seconds)
    _log(f"sleep({seconds:.4f})  EXIT")

time.sleep = _sleep

# ================================================================
# Patch 2: threading.Thread.start
# ================================================================

_original_start = threading.Thread.start
_thread_count = [0]

@functools.wraps(_original_start)
def _start(self):
    _thread_count[0] += 1
    tid = _thread_count[0]
    target_name = getattr(self._target, "__name__", str(self._target))
    _log(f"Thread START [#{tid}] name={self.name} target={target_name} daemon={self.daemon}")

    # 包装 target：记录线程 ENTER / EXIT
    _orig_target = self._target
    _orig_args = self._args or ()
    _orig_kwargs = self._kwargs or {}

    def _wrapped(*args, **kwargs):
        _log(f"Thread ENTER [#{tid}] name={self.name}")
        try:
            return _orig_target(*args, **kwargs)
        finally:
            _log(f"Thread EXIT  [#{tid}] name={self.name}")

    self._target = _wrapped
    self._args = _orig_args
    self._kwargs = _orig_kwargs
    return _original_start(self)

threading.Thread.start = _start
threading.Thread._start = _start  # 有些版本用 _start

# ================================================================
# Patch 3: queue.Queue.put
# ================================================================

_original_put = _queue_module.Queue.put

@functools.wraps(_original_put)
def _put(self, item, block=True, timeout=None):
    label = "None" if item is None else str(item)[:120]
    _log(f"Queue PUT  id=0x{id(self):x}  item={label}")
    return _original_put(self, item, block=block, timeout=timeout)

_queue_module.Queue.put = _put

# ================================================================
# Patch 4: queue.Queue.get
# ================================================================

_original_get = _queue_module.Queue.get

@functools.wraps(_original_get)
def _get(self, block=True, timeout=None):
    _log(f"Queue GET  id=0x{id(self):x}  WAIT...")
    result = _original_get(self, block=block, timeout=timeout)
    label = "None" if result is None else str(result)[:120]
    _log(f"Queue GET  id=0x{id(self):x}  GOT {label}")
    return result

_queue_module.Queue.get = _get

# ================================================================
# Patch 5: queue.Queue.get_nowait
# ================================================================

_original_get_nowait = _queue_module.Queue.get_nowait

@functools.wraps(_original_get_nowait)
def _get_nowait(self):
    try:
        result = _original_get_nowait(self)
        label = "None" if result is None else str(result)[:120]
        _log(f"Queue NOWAIT id=0x{id(self):x}  GOT {label}")
        return result
    except _queue_module.Empty:
        _log(f"Queue NOWAIT id=0x{id(self):x}  EMPTY")
        raise

_queue_module.Queue.get_nowait = _get_nowait

# ================================================================
# Patch 6: builtins.print — 统一加时间戳
# ================================================================

_original_print = builtins.print

@functools.wraps(_original_print)
def _print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    _log(f"PRINT {msg}")
    return _original_print(*args, **kwargs)

builtins.print = _print

# ================================================================
# Patch 7: OpenSim Model 创建追踪（延迟注入）
# ================================================================

_osim_patched = False
_osim_model_count = [0]


def _patch_opensim(osim_module):
    global _osim_patched
    if _osim_patched:
        return
    _osim_patched = True

    _log("--- patching OpenSim ---")

    # --- Model.__init__ ---
    if hasattr(osim_module, "Model"):
        _orig_model_init = osim_module.Model.__init__

        @functools.wraps(_orig_model_init)
        def _model_init(self, *args, **kwargs):
            _osim_model_count[0] += 1
            n = _osim_model_count[0]
            arg_str = ", ".join(str(a)[:80] for a in args)
            _log(f"OpenSim Model.__init__ [#{n}]  args=({arg_str})")
            _orig_model_init(self, *args, **kwargs)
            # 检查是否开启了 visualizer
            try:
                has_viz = self.getUseVisualizer() if hasattr(self, "getUseVisualizer") else "?"
                _log(f"OpenSim Model.__init__ [#{n}]  DONE  useVisualizer={has_viz}")
            except Exception:
                _log(f"OpenSim Model.__init__ [#{n}]  DONE")

        osim_module.Model.__init__ = _model_init

    # --- Model.setUseVisualizer ---
    if hasattr(osim_module.Model, "setUseVisualizer"):
        _orig_set_viz = osim_module.Model.setUseVisualizer

        @functools.wraps(_orig_set_viz)
        def _set_viz(self, flag):
            _log(f"OpenSim Model.setUseVisualizer({flag})  id=0x{id(self):x}")
            return _orig_set_viz(self, flag)

        osim_module.Model.setUseVisualizer = _set_viz

    # --- InverseKinematicsSolver.assemble ---
    if hasattr(osim_module, "InverseKinematicsSolver"):
        _orig_assemble = osim_module.InverseKinematicsSolver.assemble

        _assemble_count = [0]

        @functools.wraps(_orig_assemble)
        def _assemble(self, state):
            _assemble_count[0] += 1
            if _assemble_count[0] <= 10 or _assemble_count[0] % 100 == 0:
                _log(f"IK assemble [#{_assemble_count[0]}]")
            return _orig_assemble(self, state)

        osim_module.InverseKinematicsSolver.assemble = _assemble

    # --- StaticOptimization.begin / step / end ---
    for method_name in ("begin", "step", "end"):
        if hasattr(osim_module, "StaticOptimization") and hasattr(
            osim_module.StaticOptimization, method_name
        ):
            _orig = getattr(osim_module.StaticOptimization, method_name)

            @functools.wraps(_orig)
            def _so_method(self, state, _method=method_name, _orig=_orig):
                _log(f"SO.{_method}()")
                return _orig(self, state)

            setattr(osim_module.StaticOptimization, method_name, _so_method)

    _log("--- OpenSim patched ---")


# 通过 import hook 拦截 opensim 的首次 import
_original_import = builtins.__import__


@functools.wraps(_original_import)
def _import(name, *args, **kwargs):
    module = _original_import(name, *args, **kwargs)
    if name == "opensim":
        _patch_opensim(module)
    return module


builtins.__import__ = _import

# ================================================================
# 入口
# ================================================================

if __name__ == "__main__":
    _log("Launching receive_and_play.main()")

    sys.path.insert(0, str(_RECEIVER_DIR))

    import receive_and_play

    receive_and_play.main()

    _log("=== DEBUG TRACER END ===")
