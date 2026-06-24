"""
Static Optimization 播放器。
从 receiver/test_so/static_optimization_visual_demo.py 提取并复用已验证的方法。

IK 和 SO 使用不同 OpenSim Model 实例。
IK 和 SO 不做时间同步。
IK 和 SO 分别打开两个 Simbody Visualizer 窗口：
一个窗口显示 IK 动作，一个窗口显示 Static Optimization 肌肉 activation。
"""
import math
import os
import sys
import time
from pathlib import Path

import config

# ============================================================
# 工具函数（无 config 依赖，可直接从 demo 复用）
# ============================================================

def _call_if_exists(obj, method_name, *args):
    """安全调用可能不存在的方法。"""
    if hasattr(obj, method_name):
        getattr(obj, method_name)(*args)
        return True
    return False


def _array_size(arr):
    if hasattr(arr, "getSize"):
        return arr.getSize()
    return arr.size()


def _array_get(arr, index):
    if hasattr(arr, "get"):
        return arr.get(index)
    return arr[index]


def _osim_array_to_list(arr):
    return [_array_get(arr, i) for i in range(_array_size(arr))]


def _vector_set(vec, index, value):
    try:
        vec[index] = value
    except TypeError:
        vec.set(index, value)


def _motion_file_is_in_degrees(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip().lower().replace(" ", "")
            if clean.startswith("indegrees="):
                return clean.split("=", 1)[1] in ("yes", "true", "1")
            if clean == "endheader":
                break
    return False


def _configure_logger(osim):
    logger = getattr(osim, "Logger", None)
    if logger is None:
        return
    for method_name, value in (
        ("setLevelString", "Info"),
        ("setLevel", "Info"),
    ):
        try:
            if _call_if_exists(logger, method_name, value):
                return
        except Exception:
            pass


def _labels_from_storage(storage):
    return [str(x) for x in _osim_array_to_list(storage.getColumnLabels())]


def _storage_row(storage, index):
    row = storage.getStateVector(index)
    data = row.getData()
    values = [float(_array_get(data, i)) for i in range(_array_size(data))]
    return float(row.getTime()), values


def _latest_storage_row(storage):
    if storage is None or storage.getSize() <= 0:
        return None, []
    return _storage_row(storage, storage.getSize() - 1)


def _model_muscle_names(model):
    muscles = model.getMuscles()
    return {str(muscles.get(i).getName()) for i in range(muscles.getSize())}


def _model_visual_muscles(model):
    muscles = model.updMuscles() if hasattr(model, "updMuscles") else model.getMuscles()
    result = []
    for i in range(muscles.getSize()):
        muscle = muscles.get(i)
        result.append((str(muscle.getName()), muscle))
    return result


def _top_values(storage, count, by_abs, allowed_names=None):
    if storage is None or storage.getSize() <= 0:
        return []
    labels = _labels_from_storage(storage)
    _, values = _latest_storage_row(storage)
    pairs = []
    for name, value in zip(labels[1:], values):
        if allowed_names is not None and name not in allowed_names:
            continue
        if math.isfinite(value):
            pairs.append((name, value))
    key = (lambda item: abs(item[1])) if by_abs else (lambda item: item[1])
    return sorted(pairs, key=key, reverse=True)[:count]


def _latest_named_values(storage):
    if storage is None or storage.getSize() <= 0:
        return {}
    labels = _labels_from_storage(storage)[1:]
    _, values = _latest_storage_row(storage)
    return dict(zip(labels, values))


def _clamp01(value):
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _lerp(a, b, t):
    return a + (b - a) * t


def _activation_to_color(osim, activation):
    x = _clamp01(activation)
    low = (0.15, 0.25, 0.95)
    mid = (0.85, 0.15, 0.75)
    high = (1.0, 0.0, 0.02)
    if x < 0.5:
        t = x / 0.5
        color = tuple(_lerp(low[i], mid[i], t) for i in range(3))
    else:
        t = (x - 0.5) / 0.5
        color = tuple(_lerp(mid[i], high[i], t) for i in range(3))
    return osim.Vec3(color[0], color[1], color[2])


def _build_state_mapping(osim, model, states_store):
    state_labels = _labels_from_storage(states_store)[1:]
    model_state_names = [str(x) for x in _osim_array_to_list(model.getStateVariableNames())]
    name_to_model_index = {name: i for i, name in enumerate(model_state_names)}
    return [name_to_model_index.get(name, -1) for name in state_labels]


def _selected_frame_indices(total_frames):
    step = max(1, int(config.SO_STEP_INTERVAL))
    indices = list(range(0, total_frames, step))
    if config.SO_INCLUDE_LAST_FRAME and total_frames > 0 and indices[-1] != total_frames - 1:
        indices.append(total_frames - 1)
    if config.SO_MAX_FRAMES is not None:
        indices = indices[: int(config.SO_MAX_FRAMES)]
    return indices


def _set_analysis_time_window(static_opt, states_store):
    start_time = float(states_store.getFirstTime())
    end_time = float(states_store.getLastTime())
    _call_if_exists(static_opt, "setStartTime", start_time)
    _call_if_exists(static_opt, "setEndTime", end_time)


# ============================================================
# 配置感知函数（使用 config.SO_* 值）
# ============================================================

def _prepare_opensim_runtime_path():
    """确保 simbody-visualizer 等 DLL 在 PATH 中。"""
    python_dir = Path(sys.executable).resolve().parent
    candidate_dirs = [
        python_dir,
        python_dir / "Library" / "bin",
        python_dir / "Scripts",
        Path(r"C:\opensim\OpenSim 4.4\bin"),
    ]

    existing = [str(path) for path in candidate_dirs if path.exists()]
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(existing + [old_path])

    if hasattr(os, "add_dll_directory"):
        for path in existing:
            try:
                os.add_dll_directory(path)
            except OSError:
                pass


def _add_geometry_search_path():
    """添加模型 Geometry 目录到 Simbody Visualizer 搜索路径。"""
    geometry_dir = config.MODEL_FILE.parent / "Geometry"
    if not geometry_dir.exists():
        return
    import opensim as osim
    if hasattr(osim, "ModelVisualizer"):
        try:
            osim.ModelVisualizer.addDirToGeometrySearchPaths(str(geometry_dir))
        except Exception:
            pass


def _make_static_optimization(osim, model):
    """创建并配置 StaticOptimization 分析对象。"""
    static_opt = osim.StaticOptimization()
    static_opt.setModel(model)
    static_opt.setStepInterval(max(1, int(config.SO_STEP_INTERVAL)))
    static_opt.setUseModelForceSet(config.SO_USE_MODEL_FORCE_SET)
    static_opt.setActivationExponent(config.SO_ACTIVATION_EXPONENT)
    static_opt.setConvergenceCriterion(config.SO_CONVERGENCE_CRITERION)
    static_opt.setMaxIterations(config.SO_MAX_ITERATIONS)
    if hasattr(static_opt, "setUseMusclePhysiology"):
        static_opt.setUseMusclePhysiology(config.SO_USE_MUSCLE_PHYSIOLOGY)
    return static_opt


def _create_states_from_motion(osim, model, state, motion_path):
    """从 .mot 文件创建完整状态存储。"""
    motion = osim.Storage(str(motion_path))
    tool = osim.AnalyzeTool(model)
    _call_if_exists(tool, "setLowpassCutoffFrequency", -1.0)
    tool.setStatesFromMotion(state, motion, _motion_file_is_in_degrees(motion_path))
    return tool, tool.getStatesStorage()


def _create_states_storage(osim, motion_path, existing_model=None, existing_state=None):
    """创建 states storage。

    如果提供了 existing_model / existing_state，直接复用它（不创建新 Model，
    避免额外的 simbody-visualizer 窗口）。
    否则按 config 设置创建独立 states model。
    """
    if existing_model is not None and existing_state is not None:
        # 复用已有 model，不创建新 Model → 无额外 Visualizer 窗口
        states_tool, states_store = _create_states_from_motion(
            osim, existing_model, existing_state, motion_path,
        )
        return existing_model, states_tool, states_store

    if config.SO_USE_SEPARATE_STATES_MODEL:
        states_model = osim.Model(str(config.MODEL_FILE))
        states_model.setUseVisualizer(False)
        states_state = states_model.initSystem()
        states_tool, states_store = _create_states_from_motion(osim, states_model, states_state, motion_path)
        return states_model, states_tool, states_store

    model = osim.Model(str(config.MODEL_FILE))
    model.setUseVisualizer(config.SO_SHOW_VISUALIZER)
    state = model.initSystem()
    states_tool, states_store = _create_states_from_motion(osim, model, state, motion_path)
    return model, states_tool, states_store


def _apply_states_row_to_model(osim, model, state, states_store, row_index, data_to_model):
    """将 states storage 中的一行状态写入 model 的 SimTK::State。"""
    frame_time, values = _storage_row(states_store, row_index)
    state.setTime(frame_time)

    state_values = model.getStateVariableValues(state)
    for data_index, model_index in enumerate(data_to_model):
        if model_index >= 0:
            _vector_set(state_values, model_index, values[data_index])
    model.setStateVariableValues(state, state_values)

    model.assemble(state)
    if config.SO_SOLVE_FOR_EQUILIBRIUM:
        try:
            model.equilibrateMuscles(state)
        except Exception:
            pass
    if hasattr(model, "realizeVelocity"):
        model.realizeVelocity(state)
    return frame_time


def _apply_activation_to_muscles(osim, model, state, visual_muscles, activations):
    """将 activation 值写入肌肉并更新可视化颜色。"""
    if not config.SO_SHOW_MUSCLE_ACTIVATION_COLORS and not config.SO_SET_MUSCLE_ACTIVATION_STATE:
        return

    for name, muscle in visual_muscles:
        if name not in activations:
            continue
        activation = _clamp01(float(activations[name]))

        if config.SO_SET_MUSCLE_ACTIVATION_STATE:
            try:
                muscle.setActivation(state, activation)
            except Exception:
                pass

        if config.SO_SHOW_MUSCLE_ACTIVATION_COLORS:
            path = muscle.updGeometryPath() if hasattr(muscle, "updGeometryPath") else muscle.getGeometryPath()
            path.setColor(state, _activation_to_color(osim, activation))

    if config.SO_SHOW_MUSCLE_ACTIVATION_COLORS:
        try:
            model.realizeDynamics(state)
        except Exception:
            pass


def _show_state(model, state):
    """更新 Simbody Visualizer 显示。"""
    if not config.SO_SHOW_VISUALIZER:
        return
    model.updVisualizer().show(state)
    if config.SO_PLAYBACK_DELAY_SECONDS > 0:
        time.sleep(config.SO_PLAYBACK_DELAY_SECONDS)


# ============================================================
# 主入口
# ============================================================

def run_static_optimization_from_mot_file(motion_path=None, model=None, state=None):
    """
    读取 .mot 文件，运行 Static Optimization，在独立的 Simbody Visualizer 窗口中显示肌肉 activation。

    IK 和 SO 使用不同 OpenSim Model 实例。
    IK 和 SO 不做时间同步。
    IK 和 SO 分别打开两个 Simbody Visualizer 窗口。

    如果 model/state 为 None，会创建新的 Model 实例（独立使用场景）。
    如果传入已有 model/state，则复用（StaticOptimizationPlayer 场景）。
    """
    _prepare_opensim_runtime_path()
    import opensim as osim

    motion_path = Path(motion_path) if motion_path else Path(config.SO_MOTION_PATH)
    if not motion_path.exists():
        print(f"[SO] mot file not found: {motion_path}")
        return

    _configure_logger(osim)
    _add_geometry_search_path()

    mode = config.SO_MODE
    print(f"[SO] model: {config.MODEL_FILE}")
    print(f"[SO] motion: {motion_path}")
    print(f"[SO] mode: {mode}")

    if mode == "manual_per_frame":
        _run_manual_per_frame(osim, motion_path, model=model, state=state)
    elif mode == "analyze_then_playback":
        _run_analyze_then_playback(osim, motion_path, model=model, state=state)
    else:
        raise ValueError(f"SO_MODE must be 'manual_per_frame' or 'analyze_then_playback', got: {mode}")


def _run_manual_per_frame(osim, motion_path, model=None, state=None):
    """逐帧运行 Static Optimization（默认模式，demo 已验证）。

    如果 model/state 为 None，会创建新的 Model 实例（独立使用）。
    如果传入已有 model/state，则复用（StaticOptimizationPlayer 场景）。
    """
    if config.SO_EXTERNAL_LOADS_XML:
        print("[SO] manual_per_frame does not apply external loads; "
              "switch SO_MODE to 'analyze_then_playback' if needed.")

    # 创建无 visualizer 的 work_model，给 AnalyzeTool + StaticOptimization 共用。
    # 这两个类内部都会 clone model → 用无 visualizer 的避免每 session 开新窗口。
    work_model = osim.Model(str(config.MODEL_FILE))
    work_model.setUseVisualizer(False)
    work_state = work_model.initSystem()

    states_model, states_tool, states_store = _create_states_storage(
        osim, motion_path, existing_model=work_model, existing_state=work_state,
    )
    _ = states_model, states_tool

    if model is None:
        model = osim.Model(str(config.MODEL_FILE))
        model.setUseVisualizer(config.SO_SHOW_VISUALIZER)
        state = model.initSystem()

    static_opt = _make_static_optimization(osim, work_model)
    static_opt.setStatesStore(states_store)
    _set_analysis_time_window(static_opt, states_store)

    activation_names = _model_muscle_names(model) if config.SO_MUSCLE_ONLY_ACTIVATION_TOP else None
    visual_muscles = _model_visual_muscles(model)
    data_to_model = _build_state_mapping(osim, model, states_store)

    selected_indices = _selected_frame_indices(states_store.getSize())
    print(f"[SO] solving {len(selected_indices)} frames "
          f"(step_interval={config.SO_STEP_INTERVAL}, motion_rows={states_store.getSize()})")

    for selected_number, i in enumerate(selected_indices):
        frame_time = _apply_states_row_to_model(osim, model, state, states_store, i, data_to_model)

        if selected_number == 0:
            static_opt.begin(state)
        elif selected_number == len(selected_indices) - 1:
            static_opt.end(state)
        else:
            static_opt.step(state, i)

        _apply_activation_to_muscles(
            osim, model, state, visual_muscles,
            _latest_named_values(static_opt.getActivationStorage()),
        )
        _show_state(model, state)

        # 每帧打印 top activation / force
        _print_top_results(osim, frame_time, static_opt, activation_names)

    # 保存结果文件
    config.SO_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    static_opt.printResults(config.SO_RESULT_BASENAME, str(config.SO_RESULTS_DIR), -1.0, ".sto")
    print(f"[SO] results saved in: {config.SO_RESULTS_DIR}")


def _run_analyze_then_playback(osim, motion_path, model=None, state=None):
    """先用 AnalyzeTool 离线计算，再逐帧播放结果。

    如果 model/state 为 None，会创建新的 Model 实例（独立使用）。
    如果传入已有 model/state，则复用（StaticOptimizationPlayer 场景）。
    """
    config.SO_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- 离线分析 ---
    analysis_model = osim.Model(str(config.MODEL_FILE))
    analysis_model.setUseVisualizer(False)
    static_opt = _make_static_optimization(osim, analysis_model)
    analysis_model.updAnalysisSet().cloneAndAppend(static_opt)

    tool = osim.AnalyzeTool(analysis_model)
    tool.setName(config.SO_RESULT_BASENAME)
    tool.setCoordinatesFileName(str(motion_path))
    _call_if_exists(tool, "setLowpassCutoffFrequency", -1.0)
    _call_if_exists(tool, "setInitialTime", osim.Storage(str(motion_path)).getFirstTime())
    _call_if_exists(tool, "setFinalTime", osim.Storage(str(motion_path)).getLastTime())
    _call_if_exists(tool, "setResultsDir", str(config.SO_RESULTS_DIR))
    _call_if_exists(tool, "setPrintResultFiles", True)
    if config.SO_EXTERNAL_LOADS_XML:
        if not _call_if_exists(tool, "setExternalLoadsFileName", str(config.SO_EXTERNAL_LOADS_XML)):
            print("[SO] warning: setExternalLoadsFileName() not available in this OpenSim build.")

    print("[SO] running AnalyzeTool...")
    tool.run()

    # --- 加载结果 ---
    activation_path = _find_result_file("activation")
    force_path = _find_result_file("force")
    activation_storage = osim.Storage(str(activation_path))
    force_storage = osim.Storage(str(force_path))

    # --- 播放 ---
    # 用无 visualizer 的 work_model，避免 AnalyzeTool 克隆出窗口
    work_model = osim.Model(str(config.MODEL_FILE))
    work_model.setUseVisualizer(False)
    work_state = work_model.initSystem()

    states_model, states_tool, states_store = _create_states_storage(
        osim, motion_path, existing_model=work_model, existing_state=work_state,
    )
    _ = states_model, states_tool

    if model is None:
        playback_model = osim.Model(str(config.MODEL_FILE))
        playback_model.setUseVisualizer(config.SO_SHOW_VISUALIZER)
        state = playback_model.initSystem()
    else:
        playback_model = model
    data_to_model = _build_state_mapping(osim, playback_model, states_store)
    activation_names = _model_muscle_names(playback_model) if config.SO_MUSCLE_ONLY_ACTIVATION_TOP else None
    visual_muscles = _model_visual_muscles(playback_model)

    for i in _selected_frame_indices(states_store.getSize()):
        frame_time = _apply_states_row_to_model(osim, playback_model, state, states_store, i, data_to_model)
        activation_index = activation_storage.findIndex(frame_time)
        _, activation_values = _storage_row(activation_storage, activation_index)
        activation_labels = _labels_from_storage(activation_storage)[1:]
        _apply_activation_to_muscles(
            osim, playback_model, state, visual_muscles,
            dict(zip(activation_labels, activation_values)),
        )
        _show_state(playback_model, state)
        _print_playback_results(osim, frame_time, activation_storage, force_storage, activation_names)

    print(f"[SO] results saved in: {config.SO_RESULTS_DIR}")


def _find_result_file(suffix):
    """在 SO_RESULTS_DIR 中查找 StaticOptimization 结果文件。"""
    expected = config.SO_RESULTS_DIR / f"{config.SO_RESULT_BASENAME}_StaticOptimization_{suffix}.sto"
    if expected.exists():
        return expected
    matches = sorted(config.SO_RESULTS_DIR.glob(f"*StaticOptimization_{suffix}.sto"))
    if not matches:
        raise FileNotFoundError(f"Could not find StaticOptimization {suffix} file in {config.SO_RESULTS_DIR}")
    return matches[-1]


def _clear_muscle_state(osim, model, state):
    """清除所有肌肉的 activation 和颜色，为下一次 SO 运行做准备。"""
    muscles = model.updMuscles() if hasattr(model, "updMuscles") else model.getMuscles()
    neutral_color = osim.Vec3(0.6, 0.6, 0.6)  # 中性灰色

    for i in range(muscles.getSize()):
        muscle = muscles.get(i)
        # 清除 activation
        try:
            muscle.setActivation(state, 0.01)
        except Exception:
            pass
        # 清除颜色
        try:
            path = muscle.updGeometryPath() if hasattr(muscle, "updGeometryPath") else muscle.getGeometryPath()
            path.setColor(state, neutral_color)
        except Exception:
            pass

    try:
        model.realizeDynamics(state)
    except Exception:
        pass


# ============================================================
# StaticOptimizationPlayer — 预加载模型，启动时即打开 SO Visualizer 窗口
# ============================================================

class StaticOptimizationPlayer:
    """
    SO 播放器，在构造时加载模型并打开 Simbody Visualizer 窗口。
    后续收到 mot_file packet 时调用 play_mot_file() 运行 Static Optimization。

    IK 和 SO 使用不同 OpenSim Model 实例。
    IK 和 SO 分别打开两个 Simbody Visualizer 窗口：
    一个窗口显示 IK 动作，一个窗口显示 Static Optimization 肌肉 activation。
    """

    def __init__(self):
        _prepare_opensim_runtime_path()
        import opensim as osim
        self._osim = osim

        _configure_logger(osim)
        _add_geometry_search_path()

        print("[SO] loading model...")
        self.model = osim.Model(str(config.MODEL_FILE))
        self.model.setUseVisualizer(True)
        self.state = self.model.initSystem()
        self.model.realizePosition(self.state)
        self.model.updVisualizer().show(self.state)

        # 保存 T-pose 坐标值，用于播放完成后复位
        coord_set = self.model.getCoordinateSet()
        self._tpose_coord_values = {}
        for i in range(coord_set.getSize()):
            coord = coord_set.get(i)
            self._tpose_coord_values[coord.getName()] = coord.getValue(self.state)

        print("[SO] model loaded, visualizer window opened (waiting for mot data)")

    def _reset_to_tpose(self):
        """复位到 T-pose。"""
        coord_set = self.model.getCoordinateSet()
        for name, val in self._tpose_coord_values.items():
            coord_set.get(name).setValue(self.state, val)
        self.model.realizePosition(self.state)

    def play_mot_file(self, motion_path, check_queue=None):
        """对指定的 .mot 文件运行 Static Optimization，然后全帧播放。

        check_queue: 可选 queue.Queue，播放时每帧非阻塞检查。
                    有新 MOT 路径 → 返回该路径，调用方立即切换。
        """
        motion_path = Path(motion_path)
        if not motion_path.exists():
            print(f"[SO] mot file not found: {motion_path}")
            return

        print(f"[SO] running on: {motion_path}")
        mode = config.SO_MODE
        next_motion_path = None

        if mode == "manual_per_frame":
            next_motion_path = self._solve_and_play(motion_path, check_queue)
        elif mode == "analyze_then_playback":
            _run_analyze_then_playback(self._osim, motion_path,
                                       model=self.model, state=self.state)
        else:
            raise ValueError(
                f"SO_MODE must be 'manual_per_frame' or 'analyze_then_playback', got: {mode}"
            )

        # 播放结束（新 MOT 到达） → 复位 + 清肌肉
        self._reset_to_tpose()
        _clear_muscle_state(self._osim, self.model, self.state)
        self.model.updVisualizer().show(self.state)
        print("[SO] reset to T-pose, switching to next mot...")
        return next_motion_path

    # ------------------------------------------------------------
    # SO 求解 + 全帧播放
    # ------------------------------------------------------------

    def _solve_and_play(self, motion_path, check_queue):
        """求解 SO → 逐帧播放 MOT 全 925 帧，SO 帧亮肌肉颜色，中间帧灰色。"""
        osim = self._osim

        # ---- 准备：work_model + states_store ----
        work_model = osim.Model(str(config.MODEL_FILE))
        work_model.setUseVisualizer(False)
        work_state = work_model.initSystem()

        _, _tool, states_store = _create_states_storage(
            osim, motion_path, existing_model=work_model, existing_state=work_state,
        )
        total_frames = states_store.getSize()

        # ---- SO 求解（仅 selected frames）----
        static_opt = _make_static_optimization(osim, work_model)
        static_opt.setStatesStore(states_store)
        _set_analysis_time_window(static_opt, states_store)

        visual_muscles = _model_visual_muscles(self.model)
        data_to_model = _build_state_mapping(osim, self.model, states_store)

        selected_indices = set(_selected_frame_indices(total_frames))
        selected_list = sorted(selected_indices)
        print(f"[SO] solving {len(selected_list)} / {total_frames} frames "
              f"(step_interval={config.SO_STEP_INTERVAL})")

        for sel_n, i in enumerate(selected_list):
            frame_time = _apply_states_row_to_model(
                osim, self.model, self.state,
                states_store, i, data_to_model,
            )

            if sel_n == 0:
                static_opt.begin(self.state)
            elif sel_n == len(selected_list) - 1:
                static_opt.end(self.state)
            else:
                static_opt.step(self.state, i)

            # 可视化当前 SO 帧：关节姿态 + 肌肉 activation 颜色
            _apply_activation_to_muscles(
                osim, self.model, self.state, visual_muscles,
                _latest_named_values(static_opt.getActivationStorage()),
            )
            _show_state(self.model, self.state)
            _print_top_results(osim, frame_time, static_opt)

        activation_storage = static_opt.getActivationStorage()
        act_labels = _labels_from_storage(activation_storage)[1:]

        # 保存结果
        config.SO_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        static_opt.printResults(config.SO_RESULT_BASENAME,
                                str(config.SO_RESULTS_DIR), -1.0, ".sto")
        print(f"[SO] solve done, starting full playback ({total_frames} frames)")

        # ---- 预计算：每个 solved 帧的 activation，以及每帧对应的最近 solved 帧 ----
        solved_list = sorted(selected_indices)
        solved_activations = {}  # {frame_index: {muscle_name: value}}
        for si in solved_list:
            t, _ = _storage_row(states_store, si)
            act_idx = activation_storage.findIndex(t)
            _, act_vals = _storage_row(activation_storage, act_idx)
            solved_activations[si] = dict(zip(act_labels, act_vals))

        # 每帧映射到最近的 solved 帧
        frame_to_solved = {}
        for i in range(total_frames):
            nearest = min(solved_list, key=lambda s: abs(s - i))
            frame_to_solved[i] = nearest

        # ---- 全帧播放 ----
        frame_delay = 1.0 / config.FPS

        while True:
            self._reset_to_tpose()
            self.model.updVisualizer().show(self.state)

            for i in range(total_frames):
                # --- 检查新 MOT ---
                if check_queue is not None:
                    try:
                        item = check_queue.get_nowait()
                    except Exception:
                        item = None
                    if item is not None:
                        return item  # 退出播放，外层立即处理新 MOT

                # --- 关节角度（MOT 每一帧都有）---
                _apply_states_row_to_model(
                    osim, self.model, self.state,
                    states_store, i, data_to_model,
                )

                # --- 肌肉颜色：用最近 solved 帧的 activation ---
                si = frame_to_solved[i]
                _apply_activation_to_muscles(
                    osim, self.model, self.state, visual_muscles,
                    solved_activations[si],
                )

                self.model.updVisualizer().show(self.state)
                time.sleep(frame_delay)


def _print_top_results(osim, frame_time, static_opt, activation_names=None):
    """打印当前帧的 top activation 和 force。"""
    print(f"\ntime = {frame_time:.6f}")

    print("top activations:")
    activations = _top_values(static_opt.getActivationStorage(), config.SO_TOP_N,
                              by_abs=False, allowed_names=activation_names)
    for name, value in activations:
        print(f"    {name} = {value:.3f}")

    print("top forces:")
    forces = _top_values(static_opt.getForceStorage(), config.SO_TOP_N, by_abs=True)
    for name, value in forces:
        print(f"    {name} = {value:.3f}")


def _print_playback_results(osim, frame_time, activation_storage, force_storage, activation_names=None):
    """播放模式：根据时间查找最近的结果行并打印。"""
    activation_index = activation_storage.findIndex(frame_time)
    force_index = force_storage.findIndex(frame_time)

    print(f"\ntime = {frame_time:.6f}")

    print("top activations:")
    _, act_values = _storage_row(activation_storage, activation_index)
    act_labels = _labels_from_storage(activation_storage)[1:]
    act_pairs = []
    for name, value in zip(act_labels, act_values):
        if activation_names is None or name in activation_names:
            act_pairs.append((name, value))
    act_pairs = sorted(act_pairs, key=lambda item: item[1], reverse=True)[:config.SO_TOP_N]
    for name, value in act_pairs:
        print(f"    {name} = {value:.3f}")

    print("top forces:")
    _, force_values = _storage_row(force_storage, force_index)
    force_labels = _labels_from_storage(force_storage)[1:]
    force_pairs = sorted(zip(force_labels, force_values), key=lambda item: abs(item[1]), reverse=True)[:config.SO_TOP_N]
    for name, value in force_pairs:
        print(f"    {name} = {value:.3f}")
