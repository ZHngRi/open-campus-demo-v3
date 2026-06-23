"""
读取 marker 文件，通过 TCP 发给 receiver。
支持 .json (frames格式) 和 .trc (OpenCap 原生格式)。
"""

import json
import socket
from pathlib import Path

MARKERS = [
    "Neck", "RShoulder", "LShoulder",
    "RElbow", "LElbow", "RWrist", "LWrist",
    "RHip", "LHip", "RKnee", "LKnee",
    "RAnkle", "LAnkle", "RHeel", "LHeel",
    "RBigToe", "LBigToe", "RSmallToe", "LSmallToe",
    "T6",
]


def _parse_trc(path):
    """TRC → frames 列表"""
    lines = Path(path).read_text().splitlines()

    marker_names = []
    for token in lines[3].split("\t"):
        t = token.strip()
        if t and t not in ("Frame#", "Time"):
            marker_names.append(t)

    frames = []
    for line in lines[5:]:
        vals = line.split()
        if len(vals) < 2:
            continue
        frame_idx = int(vals[0]) - 1
        t = float(vals[1])
        markers = {}
        for i, name in enumerate(marker_names):
            base = 2 + i * 3
            if base + 2 < len(vals):
                markers[name] = [float(vals[base]), float(vals[base + 1]), float(vals[base + 2])]
        frames.append({"time": t, "frame_index": frame_idx, "markers": markers})
    return frames


def send_marker_file(file_path, host, port):
    """读取 marker 文件，逐帧发送到 TCP receiver"""
    file_path = str(file_path)

    if file_path.endswith(".json"):
        data = json.loads(open(file_path).read())
        frames = data["frames"]
    elif file_path.endswith(".trc"):
        frames = _parse_trc(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {file_path}")

    sock = socket.create_connection((host, port), timeout=10)

    for f in frames:
        packet = {
            "type": "marker_frame",
            "time": f["time"],
            "frame_index": f["frame_index"],
            "markers": {name: f["markers"].get(name, [0, 0, 0]) for name in MARKERS},
            "confidence": f.get("confidence"),
        }
        sock.sendall((json.dumps(packet) + "\n").encode())

    sock.close()
    return len(frames)
