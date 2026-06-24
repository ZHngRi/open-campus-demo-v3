"""
直接发送 TRC/MOT 文件到 IK (5005) 和 SO (5006) 两个端口。

用法:
    python test_send_both.py
    python test_send_both.py --mot path/to/motion.mot --trc path/to/markers.trc
"""
import socket
import sys
from pathlib import Path

IK_HOST = "127.0.0.1"
IK_PORT = 5005
SO_HOST = "127.0.0.1"
SO_PORT = 5006

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SO_DIR = SCRIPT_DIR / "test_so"
DEFAULT_MOT = TEST_SO_DIR / "single_leg_hop_turn_around_walk.mot"
DEFAULT_TRC = TEST_SO_DIR / "single_leg_hop_turn_around_walk.trc"


def send_file(host, port, path):
    path = Path(path)
    data = path.read_bytes()
    filename = path.name.encode("utf-8")

    with socket.create_connection((host, port)) as sock:
        sock.sendall(len(filename).to_bytes(4, "big"))
        sock.sendall(filename)
        sock.sendall(len(data).to_bytes(8, "big"))
        sock.sendall(data)

    print(f"  -> sent {path.name} ({len(data)} bytes) to {host}:{port}")


def main():
    args = sys.argv[1:]

    mot = DEFAULT_MOT
    trc = DEFAULT_TRC

    i = 0
    while i < len(args):
        if args[i] == "--mot" and i + 1 < len(args):
            mot = args[i + 1]; i += 2
        elif args[i] == "--trc" and i + 1 < len(args):
            trc = args[i + 1]; i += 2
        else:
            i += 1

    trc = Path(trc)
    mot = Path(mot)

    if not trc.exists():
        print(f"TRC not found: {trc}")
        return
    if not mot.exists():
        print(f"MOT not found: {mot}")
        return

    print(f"TRC: {trc.name}")
    print(f"MOT: {mot.name}")
    print()

    for label, host, port, path in (
        ("IK", IK_HOST, IK_PORT, trc),
        ("SO", SO_HOST, SO_PORT, mot),
    ):
        try:
            send_file(host, port, path)
        except ConnectionRefusedError:
            print(f"  -> {label} receiver not running at {host}:{port}, skipped")

    print()
    print("done - check receiver windows:")
    print("  IK window: skeleton animation (looping)")
    print("  SO window: muscle activation")


if __name__ == "__main__":
    main()
