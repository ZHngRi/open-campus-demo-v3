# config.py — testv3 接收端配置

from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent


# ============================================================
# IK settings
# ============================================================

MODEL_FILE = PROJECT_ROOT / "received_data" / "OpenSimData" / "model.osim"
GEOMETRY_DIR = PROJECT_ROOT / "received_data" / "OpenSimData" / "Geometry"

FPS = 30.0
CONSTRAINT_WEIGHT = 1.0

REALTIME_MARKER_NAMES = [
    "Neck",
    "RShoulder",
    "LShoulder",

    "RElbow",
    "LElbow",
    "RWrist",
    "LWrist",

    "RHip",
    "LHip",

    "RKnee",
    "LKnee",
    "RAnkle",
    "LAnkle",

    "RHeel",
    "LHeel",

    "RBigToe",
    "LBigToe",
    "RSmallToe",
    "LSmallToe",

    "T6",
]

MARKER_WEIGHTS = {
    "Neck": 10.0,
    "T6": 8.0,

    "RShoulder": 10.0,
    "LShoulder": 10.0,

    "RElbow": 5.0,
    "LElbow": 5.0,

    "RWrist": 3.0,
    "LWrist": 3.0,

    "RHip": 20.0,
    "LHip": 20.0,

    "RKnee": 10.0,
    "LKnee": 10.0,

    "RAnkle": 10.0,
    "LAnkle": 10.0,

    "RHeel": 5.0,
    "LHeel": 5.0,

    "RBigToe": 5.0,
    "LBigToe": 5.0,

    "RSmallToe": 3.0,
    "LSmallToe": 3.0,
}


# ============================================================
# Static Optimization settings
# ============================================================

# -- 路径 --
SO_MOTION_PATH = PROJECT_ROOT / "test_so" / "single_leg_hop_turn_around_walk.mot"
SO_EXTERNAL_LOADS_XML = None  # 例如: PROJECT_ROOT / "received_data" / "OpenSimData" / "external_loads.xml"
SO_RESULTS_DIR = PROJECT_ROOT / "test_so" / "results_static_optimization"
SO_RESULT_BASENAME = "static_opt_visual_demo"

# -- 运行模式 --
# "manual_per_frame": 逐帧调用 Analysis.begin/step/end（与 GUI 循环最接近）
# "analyze_then_playback": 先用 AnalyzeTool 离线计算，再播放结果
SO_MODE = "manual_per_frame"

# -- 显示 --
SO_SHOW_VISUALIZER = True
SO_PLAYBACK_DELAY_SECONDS = 0.02

# -- 结果输出 --
SO_TOP_N = 5
SO_MAX_FRAMES = None  # 调试时可设为小整数，例如 10
SO_MUSCLE_ONLY_ACTIVATION_TOP = True

# -- 帧采样 --
SO_STEP_INTERVAL = 150
SO_INCLUDE_LAST_FRAME = True

# -- 状态模型 --
SO_USE_SEPARATE_STATES_MODEL = True

# -- 肌肉可视化 --
SO_SHOW_MUSCLE_ACTIVATION_COLORS = True
SO_SET_MUSCLE_ACTIVATION_STATE = True

# -- Static Optimization 求解参数 --
SO_ACTIVATION_EXPONENT = 2.0
SO_CONVERGENCE_CRITERION = 1e-4
SO_MAX_ITERATIONS = 100
SO_USE_MODEL_FORCE_SET = True
SO_USE_MUSCLE_PHYSIOLOGY = True
SO_SOLVE_FOR_EQUILIBRIUM = True
