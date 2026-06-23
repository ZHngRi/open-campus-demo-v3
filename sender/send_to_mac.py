"""
从本地 .trc 文件中提取 20 个 marker，通过 TCP 发给 Windows 接收端。

用法:
    python send_to_mac.py                        # 自动找最新的 trc
    python send_to_mac.py /path/to/file.trc      # 指定文件
"""

import sys
import json
import socket
from pathlib import Path

RECEIVER = ("100.82.248.104", 5005)

MARKERS = [
    "Neck", "RShoulder", "LShoulder",
    "RElbow", "LElbow", "RWrist", "LWrist",
    "RHip", "LHip", "RKnee", "LKnee",
    "RAnkle", "LAnkle", "RHeel", "LHeel",
    "RBigToe", "LBigToe", "RSmallToe", "LSmallToe",
    "T6",
]


OUTPUTS = Path(__file__).resolve().parent / "outputs"


def find_latest_trc():
    """在 outputs/ 下找最新 session 的 .trc 文件"""
    sessions = sorted(OUTPUTS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for s in sessions:
        if not s.is_dir():
            continue
        trc_files = list(s.rglob("MarkerData/*.trc"))
        if trc_files:
            return trc_files[0]
    raise FileNotFoundError("outputs/ 下没有 .trc 文件")


def parse_trc(path):
    """读取 TRC 文件，返回帧列表。每帧: {time, frame_index, markers: {name: [x,y,z]}}"""
    lines = path.read_text().splitlines()

    # 第 4 行是 marker 名（tab 分隔）
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

        frames.append({
            "time": t,
            "frame_index": frame_idx,
            "markers": markers,
        })

    return frames


def build_payload(frames):
    """把帧数据转成 JSON Lines 字符串，只保留接收端需要的 20 个 marker"""
    lines = []
    for f in frames:
        filtered_markers = {}
        for name in MARKERS:
            filtered_markers[name] = f["markers"].get(name, [0.0, 0.0, 0.0])

        lines.append(json.dumps({
            "type": "marker_frame",
            "time": f["time"],
            "frame_index": f["frame_index"],
            "markers": filtered_markers,
        }))

    return "\n".join(lines) + "\n"


def send(payload):
    """TCP 发送，不重试，失败直接报错"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(RECEIVER)
    sock.sendall(payload.encode())
    sock.close()


def main():
    if len(sys.argv) > 1:
        trc_path = Path(sys.argv[1])
    else:
        trc_path = find_latest_trc()

    print(f"trc: {trc_path}")

    frames = parse_trc(trc_path)
    print(f"帧数: {len(frames)}")

    payload = build_payload(frames)

    print(f"发送 {len(frames)} 帧 -> {RECEIVER[0]}:{RECEIVER[1]}")
    send(payload)
    print("完成")


if __name__ == "__main__":
    main()
