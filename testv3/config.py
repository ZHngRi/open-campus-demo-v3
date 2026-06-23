# config.py — testv3 接收端配置

from pathlib import Path
from typing import Dict, Iterable, List, Mapping


# ============================================================
# Paths — 使用 received_data/OpenSimData 下的模型
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

MODEL_FILE = PROJECT_ROOT / "received_data" / "OpenSimData" / "model.osim"
GEOMETRY_DIR = PROJECT_ROOT / "received_data" / "OpenSimData" / "Geometry"


# ============================================================
# Runtime
# ============================================================

FPS = 30.0
CONSTRAINT_WEIGHT = 1.0


# ============================================================
# Markers used for realtime IK
# ============================================================

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


# ============================================================
# Marker weights for IK
# ============================================================

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
