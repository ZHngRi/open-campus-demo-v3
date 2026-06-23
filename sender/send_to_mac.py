#!/usr/bin/env python3
"""
发送端 — 读 .trc 文件 → 提取 20 个 marker → TCP JSON Lines 发送
=============================================================
运行在本机 (100.111.140.103)，接收端在 Windows (100.82.248.104:5005)

用法:
    python send_to_mac.py --latest
    python send_to_mac.py /path/to/file.trc
    python send_to_mac.py --loop
"""
import sys
import os
import json
import socket
from pathlib import Path

RECEIVER_IP = "100.75.207.73"
RECEIVER_PORT = 5005
# sender/ 的上层是项目根目录
ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
DEMO_SCRIPT = ROOT / "opencap_monocular_demo.py"

# 接收端需要的 20 个 marker
MARKER_NAMES = [
    "Neck", "RShoulder", "LShoulder",
    "RElbow", "LElbow", "RWrist", "LWrist",
    "RHip", "LHip", "RKnee", "LKnee",
    "RAnkle", "LAnkle", "RHeel", "LHeel",
    "RBigToe", "LBigToe", "RSmallToe", "LSmallToe",
    "T6",
]


def parse_trc(trc_path):
    """解析 .trc 文件"""
    with open(trc_path) as f:
        lines = f.readlines()

    # 解析第 3 行（marker 名，tab 分隔，每名后跟两个空列对应 X Y Z）
    marker_line = lines[3].rstrip("\n")
    marker_names = []
    for token in marker_line.split("\t"):
        t = token.strip()
        if t and t != "" and t not in ("Frame#", "Time"):
            marker_names.append(t)

    # 数据从第 6 行（0-indexed）开始
    frames = []
    for line in lines[5:]:
        vals = line.strip().split()
        if len(vals) < 2:
            continue
        try:
            frame_num = int(vals[0])
            t = float(vals[1])
        except ValueError:
            continue

        markers = {}
        for i, name in enumerate(marker_names):
            base = 2 + i * 3
            if base + 2 < len(vals):
                markers[name] = [float(vals[base]), float(vals[base+1]), float(vals[base+2])]
            else:
                markers[name] = [0.0, 0.0, 0.0]

        frames.append({
            "time": t,
            "frame_index": frame_num - 1,
            "markers": markers,
        })

    return frames


def send_frames(frames):
    """连接并发送"""
    payload = "\n".join(json.dumps({
        "type": "marker_frame",
        "time": f["time"],
        "frame_index": f["frame_index"],
        "markers": {name: f["markers"].get(name, [0, 0, 0]) for name in MARKER_NAMES},
    }) for f in frames) + "\n"

    print(f"  {len(frames)} 帧 → {len(payload)/1024:.0f} KB")

    for attempt in range(10):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((RECEIVER_IP, RECEIVER_PORT))
            print(f"  ✅ 已连接 {RECEIVER_IP}:{RECEIVER_PORT}")
            sock.sendall(payload.encode())
            print(f"  ✅ 已发送")
            sock.close()
            return
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            print(f"  连接尝试 {attempt+1}/10...")
            import time
            time.sleep(1)
    print("  ❌ 无法连接")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))

    # --full: 先跑 API Demo 获取数据
    if "--full" in flags:
        import subprocess
        print("  先跑 API Demo...")
        subprocess.run([sys.executable, str(DEMO_SCRIPT)],
                       cwd=str(ROOT))
        print()

    trc_paths = []

    if args and not args[0].startswith("-"):
        trc_paths = [Path(args[0])]
    else:
        for s in sorted(OUTPUTS_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if not s.is_dir():
                continue
            trc_paths.extend(s.rglob("MarkerData/*.trc"))

    if not trc_paths:
        print("❌ 找不到 .trc 文件")
        print("   先跑 python sender/opencap_monocular_demo.py 获取数据")
        sys.exit(1)

    for trc_path in trc_paths:
        print(f"  trc: {trc_path}")

        frames = parse_trc(trc_path)
        print(f"  读取: {len(frames)} 帧")

        send_frames(frames)

    if "--loop" in flags:
        print("  --loop 暂不支持，手动重新运行即可")


if __name__ == "__main__":
    main()
