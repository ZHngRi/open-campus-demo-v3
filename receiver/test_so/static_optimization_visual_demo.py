from pathlib import Path
import math
import os
import sys
import time


# ----------------------------
# Paths and knobs to edit first
# ----------------------------
ROOT = Path(__file__).resolve().parent

MODEL_PATH = ROOT / "received_data" / "OpenSimData" / "model.osim"
MOTION_PATH = ROOT  / "single_leg_hop_turn_around_walk.mot"
EXTERNAL_LOADS_XML = None  # Example: ROOT / "received_data" / "OpenSimData" / "external_loads.xml"

RESULTS_DIR = ROOT / "results_static_optimization"
RESULT_BASENAME = "static_opt_visual_demo"

# "manual_per_frame" is closest to the GUI loop: each frame calls Analysis.begin/step/end,
# which internally calls StaticOptimization.record().
# "analyze_then_playback" first runs AnalyzeTool offline, then plays motion + result .sto files.
MODE = "manual_per_frame"

SHOW_VISUALIZER = True
PLAYBACK_DELAY_SECONDS = 0.02
TOP_N = 5
MAX_FRAMES = None  # Set to a small integer while debugging, for example 10.
MUSCLE_ONLY_ACTIVATION_TOP = True

# OpenSim Analysis has a step_interval property. Increasing this skips frames for
# StaticOptimization, printing, and visualizer playback. Example: 5 solves every
# 5th .mot row. The full motion storage is still used for state derivatives.
STEP_INTERVAL = 10
INCLUDE_LAST_FRAME = True

# Use a non-visualizer model for the motion->states helper so only the main model
# opens a Simbody Visualizer window.
USE_SEPARATE_STATES_MODEL = True

SHOW_MUSCLE_ACTIVATION_COLORS = True
SET_MUSCLE_ACTIVATION_STATE = True

ACTIVATION_EXPONENT = 2.0
CONVERGENCE_CRITERION = 1e-4
MAX_ITERATIONS = 100
USE_MODEL_FORCE_SET = True
USE_MUSCLE_PHYSIOLOGY = True
SOLVE_FOR_EQUILIBRIUM = True


def prepare_opensim_runtime_path():
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


def call_if_exists(obj, method_name, *args):
    if hasattr(obj, method_name):
        getattr(obj, method_name)(*args)
        return True
    return False


def array_size(arr):
    if hasattr(arr, "getSize"):
        return arr.getSize()
    return arr.size()


def array_get(arr, index):
    if hasattr(arr, "get"):
        return arr.get(index)
    return arr[index]


def osim_array_to_list(arr):
    return [array_get(arr, i) for i in range(array_size(arr))]


def vector_set(vec, index, value):
    try:
        vec[index] = value
    except TypeError:
        vec.set(index, value)


def motion_file_is_in_degrees(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip().lower().replace(" ", "")
            if clean.startswith("indegrees="):
                return clean.split("=", 1)[1] in ("yes", "true", "1")
            if clean == "endheader":
                break
    return False


def configure_logger():
    # OpenSim's C++ StaticOptimization prints target performance when Logger is at Info.
    logger = getattr(osim, "Logger", None)
    if logger is None:
        return
    for method_name, value in (
        ("setLevelString", "Info"),
        ("setLevel", "Info"),
    ):
        try:
            if call_if_exists(logger, method_name, value):
                return
        except Exception:
            pass


def add_geometry_search_path():
    geometry_dir = MODEL_PATH.parent / "Geometry"
    if geometry_dir.exists() and hasattr(osim, "ModelVisualizer"):
        # Helps Simbody Visualizer find .vtp/.obj geometry next to the model.
        try:
            osim.ModelVisualizer.addDirToGeometrySearchPaths(str(geometry_dir))
        except Exception:
            pass


def make_static_optimization(model):
    static_opt = osim.StaticOptimization()
    static_opt.setModel(model)  # Attach this Analysis to the model, as AnalyzeTool does.
    static_opt.setStepInterval(max(1, int(STEP_INTERVAL)))
    static_opt.setUseModelForceSet(USE_MODEL_FORCE_SET)
    static_opt.setActivationExponent(ACTIVATION_EXPONENT)
    static_opt.setConvergenceCriterion(CONVERGENCE_CRITERION)
    static_opt.setMaxIterations(MAX_ITERATIONS)
    if hasattr(static_opt, "setUseMusclePhysiology"):
        static_opt.setUseMusclePhysiology(USE_MUSCLE_PHYSIOLOGY)
    return static_opt


def create_states_from_motion(model, state):
    motion = osim.Storage(str(MOTION_PATH))  # OpenSim Storage reads .mot/.sto tables.
    tool = osim.AnalyzeTool(model)
    call_if_exists(tool, "setLowpassCutoffFrequency", -1.0)
    # This is the same utility AnalyzeTool uses to turn coordinates into full states.
    tool.setStatesFromMotion(state, motion, motion_file_is_in_degrees(MOTION_PATH))
    return tool, tool.getStatesStorage()


def create_states_storage():
    if USE_SEPARATE_STATES_MODEL:
        states_model = osim.Model(str(MODEL_PATH))
        states_model.setUseVisualizer(False)
        states_state = states_model.initSystem()
        states_tool, states_store = create_states_from_motion(states_model, states_state)
        return states_model, states_tool, states_store

    model = osim.Model(str(MODEL_PATH))
    model.setUseVisualizer(SHOW_VISUALIZER)
    state = model.initSystem()
    states_tool, states_store = create_states_from_motion(model, state)
    return model, states_tool, states_store


def labels_from_storage(storage):
    return [str(x) for x in osim_array_to_list(storage.getColumnLabels())]


def storage_row(storage, index):
    row = storage.getStateVector(index)
    data = row.getData()
    values = [float(array_get(data, i)) for i in range(array_size(data))]
    return float(row.getTime()), values


def latest_storage_row(storage):
    if storage is None or storage.getSize() <= 0:
        return None, []
    return storage_row(storage, storage.getSize() - 1)


def model_muscle_names(model):
    muscles = model.getMuscles()
    return {str(muscles.get(i).getName()) for i in range(muscles.getSize())}


def model_visual_muscles(model):
    muscles = model.updMuscles() if hasattr(model, "updMuscles") else model.getMuscles()
    result = []
    for i in range(muscles.getSize()):
        muscle = muscles.get(i)
        result.append((str(muscle.getName()), muscle))
    return result


def top_values(storage, count, by_abs, allowed_names=None):
    if storage is None or storage.getSize() <= 0:
        return []
    labels = labels_from_storage(storage)
    _, values = latest_storage_row(storage)
    pairs = []
    for name, value in zip(labels[1:], values):
        if allowed_names is not None and name not in allowed_names:
            continue
        if math.isfinite(value):
            pairs.append((name, value))
    key = (lambda item: abs(item[1])) if by_abs else (lambda item: item[1])
    return sorted(pairs, key=key, reverse=True)[:count]


def print_top_results(frame_time, static_opt, activation_names=None):
    print(f"\ntime = {frame_time:.6f}")

    print("top activations:")
    activations = top_values(static_opt.getActivationStorage(), TOP_N, by_abs=False, allowed_names=activation_names)
    for name, value in activations:
        print(f"    {name} = {value:.3f}")

    print("top forces:")
    forces = top_values(static_opt.getForceStorage(), TOP_N, by_abs=True)
    for name, value in forces:
        print(f"    {name} = {value:.3f}")


def latest_named_values(storage):
    if storage is None or storage.getSize() <= 0:
        return {}
    labels = labels_from_storage(storage)[1:]
    _, values = latest_storage_row(storage)
    return dict(zip(labels, values))


def clamp01(value):
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def lerp(a, b, t):
    return a + (b - a) * t


def activation_to_color(activation):
    x = clamp01(activation)
    low = (0.15, 0.25, 0.95)
    mid = (0.85, 0.15, 0.75)
    high = (1.0, 0.0, 0.02)
    if x < 0.5:
        t = x / 0.5
        color = tuple(lerp(low[i], mid[i], t) for i in range(3))
    else:
        t = (x - 0.5) / 0.5
        color = tuple(lerp(mid[i], high[i], t) for i in range(3))
    return osim.Vec3(color[0], color[1], color[2])


def apply_activation_to_muscles(model, state, visual_muscles, activations):
    if not SHOW_MUSCLE_ACTIVATION_COLORS and not SET_MUSCLE_ACTIVATION_STATE:
        return

    for name, muscle in visual_muscles:
        if name not in activations:
            continue
        activation = clamp01(float(activations[name]))

        if SET_MUSCLE_ACTIVATION_STATE:
            try:
                muscle.setActivation(state, activation)
            except Exception:
                pass

        if SHOW_MUSCLE_ACTIVATION_COLORS:
            # GeometryPath.setColor() writes the runtime path color cache used by
            # Simbody Visualizer decorations. This is the OpenSim visual path, not
            # an external overlay.
            path = muscle.updGeometryPath() if hasattr(muscle, "updGeometryPath") else muscle.getGeometryPath()
            path.setColor(state, activation_to_color(activation))

    if SHOW_MUSCLE_ACTIVATION_COLORS:
        try:
            model.realizeDynamics(state)
        except Exception:
            pass


def build_state_mapping(model, states_store):
    state_labels = labels_from_storage(states_store)[1:]
    model_state_names = [str(x) for x in osim_array_to_list(model.getStateVariableNames())]
    name_to_model_index = {name: i for i, name in enumerate(model_state_names)}
    return [name_to_model_index.get(name, -1) for name in state_labels]


def apply_states_row_to_model(model, state, states_store, row_index, data_to_model):
    frame_time, values = storage_row(states_store, row_index)
    state.setTime(frame_time)

    # Copy the row's OpenSim state variables into the current SimTK::State.
    state_values = model.getStateVariableValues(state)
    for data_index, model_index in enumerate(data_to_model):
        if model_index >= 0:
            vector_set(state_values, model_index, values[data_index])
    model.setStateVariableValues(state, state_values)

    # Match AnalyzeTool::run(): assemble, optionally equilibrate muscles, then realize velocity.
    model.assemble(state)
    if SOLVE_FOR_EQUILIBRIUM:
        try:
            model.equilibrateMuscles(state)
        except Exception as exc:
            print(f"Analyze-style muscle equilibration warning at time {frame_time:.6f}: {exc}")
    if hasattr(model, "realizeVelocity"):
        model.realizeVelocity(state)
    return frame_time


def show_state(model, state):
    if not SHOW_VISUALIZER:
        return
    # This is the direct Simbody Visualizer update call.
    model.updVisualizer().show(state)
    if PLAYBACK_DELAY_SECONDS > 0:
        time.sleep(PLAYBACK_DELAY_SECONDS)


def selected_frame_indices(total_frames):
    step = max(1, int(STEP_INTERVAL))
    indices = list(range(0, total_frames, step))
    if INCLUDE_LAST_FRAME and total_frames > 0 and indices[-1] != total_frames - 1:
        indices.append(total_frames - 1)
    if MAX_FRAMES is not None:
        indices = indices[: int(MAX_FRAMES)]
    return indices


def set_analysis_time_window(static_opt, states_store):
    start_time = float(states_store.getFirstTime())
    end_time = float(states_store.getLastTime())
    call_if_exists(static_opt, "setStartTime", start_time)
    call_if_exists(static_opt, "setEndTime", end_time)


def run_manual_per_frame():
    if EXTERNAL_LOADS_XML:
        print("manual_per_frame does not apply external loads by itself.")
        print("Switch MODE to 'analyze_then_playback' if you need AnalyzeTool external loads handling.")

    add_geometry_search_path()
    states_model, states_tool, states_store = create_states_storage()
    _ = states_model, states_tool  # Keep these alive because AnalyzeTool owns states_store.

    model = osim.Model(str(MODEL_PATH))  # Load model.osim for solving and display.
    model.setUseVisualizer(SHOW_VISUALIZER)  # Only this model opens Simbody Visualizer.
    state = model.initSystem()

    static_opt = make_static_optimization(model)
    static_opt.setStatesStore(states_store)  # StaticOptimization needs full state history for derivatives.
    set_analysis_time_window(static_opt, states_store)
    activation_names = model_muscle_names(model) if MUSCLE_ONLY_ACTIVATION_TOP else None
    visual_muscles = model_visual_muscles(model)

    data_to_model = build_state_mapping(model, states_store)

    selected_indices = selected_frame_indices(states_store.getSize())
    print(f"Running StaticOptimization on {len(selected_indices)} selected frames.")
    print(f"STEP_INTERVAL = {STEP_INTERVAL}; motion rows = {states_store.getSize()}")
    for selected_number, i in enumerate(selected_indices):
        frame_time = apply_states_row_to_model(model, state, states_store, i, data_to_model)

        # These public Analysis methods call protected StaticOptimization.record() internally.
        if selected_number == 0:
            static_opt.begin(state)
        elif selected_number == len(selected_indices) - 1:
            static_opt.end(state)
        else:
            static_opt.step(state, i)

        apply_activation_to_muscles(
            model,
            state,
            visual_muscles,
            latest_named_values(static_opt.getActivationStorage()),
        )
        show_state(model, state)
        print_top_results(frame_time, static_opt, activation_names)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Writes *_StaticOptimization_activation.sto, *_force.sto, and *_controls.xml.
    static_opt.printResults(RESULT_BASENAME, str(RESULTS_DIR), -1.0, ".sto")
    print(f"\nSaved results in: {RESULTS_DIR}")


def configure_analyze_tool(model):
    static_opt = make_static_optimization(model)
    model.updAnalysisSet().cloneAndAppend(static_opt)

    tool = osim.AnalyzeTool(model)  # AnalyzeTool reproduces the standard OpenSim analysis pipeline.
    tool.setName(RESULT_BASENAME)
    tool.setCoordinatesFileName(str(MOTION_PATH))
    call_if_exists(tool, "setLowpassCutoffFrequency", -1.0)
    call_if_exists(tool, "setInitialTime", osim.Storage(str(MOTION_PATH)).getFirstTime())
    call_if_exists(tool, "setFinalTime", osim.Storage(str(MOTION_PATH)).getLastTime())
    call_if_exists(tool, "setResultsDir", str(RESULTS_DIR))
    call_if_exists(tool, "setPrintResultFiles", True)
    if EXTERNAL_LOADS_XML:
        if not call_if_exists(tool, "setExternalLoadsFileName", str(EXTERNAL_LOADS_XML)):
            print("Warning: this OpenSim Python build did not expose setExternalLoadsFileName().")
    return tool


def find_result_file(suffix):
    expected = RESULTS_DIR / f"{RESULT_BASENAME}_StaticOptimization_{suffix}.sto"
    if expected.exists():
        return expected
    matches = sorted(RESULTS_DIR.glob(f"*StaticOptimization_{suffix}.sto"))
    if not matches:
        raise FileNotFoundError(f"Could not find StaticOptimization {suffix} file in {RESULTS_DIR}")
    return matches[-1]


def print_playback_results(frame_time, activation_storage, force_storage, activation_names=None):
    activation_index = activation_storage.findIndex(frame_time)
    force_index = force_storage.findIndex(frame_time)

    print(f"\ntime = {frame_time:.6f}")

    print("top activations:")
    act_time, act_values = storage_row(activation_storage, activation_index)
    act_labels = labels_from_storage(activation_storage)[1:]
    act_pairs = []
    for name, value in zip(act_labels, act_values):
        if activation_names is None or name in activation_names:
            act_pairs.append((name, value))
    act_pairs = sorted(act_pairs, key=lambda item: item[1], reverse=True)[:TOP_N]
    for name, value in act_pairs:
        print(f"    {name} = {value:.3f}")

    print("top forces:")
    force_time, force_values = storage_row(force_storage, force_index)
    force_labels = labels_from_storage(force_storage)[1:]
    force_pairs = sorted(zip(force_labels, force_values), key=lambda item: abs(item[1]), reverse=True)[:TOP_N]
    for name, value in force_pairs:
        print(f"    {name} = {value:.3f}")

    if abs(act_time - frame_time) > 1e-6 or abs(force_time - frame_time) > 1e-6:
        print(f"    nearest result rows: activation_time={act_time:.6f}, force_time={force_time:.6f}")


def run_analyze_then_playback():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    add_geometry_search_path()
    analysis_model = osim.Model(str(MODEL_PATH))
    tool = configure_analyze_tool(analysis_model)

    print("Running AnalyzeTool first. Visualizer playback starts after optimization finishes.")
    tool.run()

    activation_storage = osim.Storage(str(find_result_file("activation")))
    force_storage = osim.Storage(str(find_result_file("force")))

    states_model, states_tool, states_store = create_states_storage()
    _ = states_model, states_tool

    playback_model = osim.Model(str(MODEL_PATH))
    playback_model.setUseVisualizer(SHOW_VISUALIZER)
    state = playback_model.initSystem()
    data_to_model = build_state_mapping(playback_model, states_store)
    activation_names = model_muscle_names(playback_model) if MUSCLE_ONLY_ACTIVATION_TOP else None
    visual_muscles = model_visual_muscles(playback_model)

    for i in selected_frame_indices(states_store.getSize()):
        frame_time = apply_states_row_to_model(playback_model, state, states_store, i, data_to_model)
        activation_index = activation_storage.findIndex(frame_time)
        _, activation_values = storage_row(activation_storage, activation_index)
        activation_labels = labels_from_storage(activation_storage)[1:]
        apply_activation_to_muscles(
            playback_model,
            state,
            visual_muscles,
            dict(zip(activation_labels, activation_values)),
        )
        show_state(playback_model, state)
        print_playback_results(frame_time, activation_storage, force_storage, activation_names)

    print(f"\nSaved results in: {RESULTS_DIR}")


def main():
    global osim
    prepare_opensim_runtime_path()
    import opensim as osim

    configure_logger()

    print("OpenSim Static Optimization visual demo")
    print(f"model: {MODEL_PATH}")
    print(f"motion: {MOTION_PATH}")
    print(f"mode: {MODE}")

    if MODE == "manual_per_frame":
        run_manual_per_frame()
    elif MODE == "analyze_then_playback":
        run_analyze_then_playback()
    else:
        raise ValueError("MODE must be 'manual_per_frame' or 'analyze_then_playback'")


if __name__ == "__main__":
    main()
