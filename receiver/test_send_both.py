"""
发送 session packet 到 IK (5005) 和 SO (5006) 两个端口。

用法:
    python test_send_both.py
    python test_send_both.py --mot path/to/motion.mot --trc path/to/markers.trc
"""
import json
import socket
import sys
from pathlib import Path

IK_HOST = "127.0.0.1"
IK_PORT = 5005
SO_HOST = "127.0.0.1"
SO_PORT = 5006

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_SO_DIR = SCRIPT_DIR / "test_so"
DEFAULT_MOT = str(TEST_SO_DIR / "single_leg_hop_turn_around_walk.mot")
DEFAULT_TRC = str(TEST_SO_DIR / "single_leg_hop_turn_around_walk.trc")


def _send(host, port, packet):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
        sock.sendall((json.dumps(packet) + "\n").encode("utf-8"))
        print(f"  -> sent to {host}:{port}")
    finally:
        sock.close()


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

    if not Path(trc).exists():
        print(f"TRC not found: {trc}")
        return
    if not Path(mot).exists():
        print(f"MOT not found: {mot}")
        return

    packet = {"type": "session", "trc": trc, "mot": mot}

    print(f"TRC: {trc}")
    print(f"MOT: {mot}")
    print()

    _send(IK_HOST, IK_PORT, packet)
    _send(SO_HOST, SO_PORT, packet)

    print()
    print("done — check both windows:")
    print("  IK window: skeleton animation (looping)")
    print("  SO window: muscle activation")


if __name__ == "__main__":
    main()
