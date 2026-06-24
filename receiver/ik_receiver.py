r"""
IK Receiver — 独立进程，只做 Inverse Kinematics
=================================================
收到 TRC 文件 → 保存到 receiver_data → IK 求解 → 循环显示骨骼动画
播放期间收到新 TRC → 复位 T-pose → 切到新动画

用法:
    python ik_receiver.py                      # 监听 0.0.0.0:5005
    python ik_receiver.py 0.0.0.0 5005         # 指定 host 和 port
"""
import queue
import socket
import sys
import threading
from pathlib import Path

from ik_player import IKPlayer

HOST = "0.0.0.0"
PORT = 5005
DATA_DIR = Path(__file__).resolve().parent / "receiver_data"


def _recv_exact(conn, size):
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(min(65536, remaining))
        if not chunk:
            raise EOFError("Sender closed connection.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _receive_file(conn):
    filename_len = int.from_bytes(_recv_exact(conn, 4), "big")
    filename = _recv_exact(conn, filename_len).decode("utf-8")
    file_size = int.from_bytes(_recv_exact(conn, 8), "big")
    data = _recv_exact(conn, file_size)

    DATA_DIR.mkdir(exist_ok=True)
    save_path = DATA_DIR / Path(filename).name
    save_path.write_bytes(data)
    return save_path


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    host = args[0] if len(args) >= 1 else HOST
    port = int(args[1]) if len(args) >= 2 else PORT

    print("=" * 60)
    print("  IK Receiver")
    print("=" * 60)

    player = IKPlayer()
    trc_queue = queue.Queue()

    # --- receive 线程：收到 TRC 文件 → 保存 → 放入队列 ---
    def _recv_loop():
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
        except OSError as e:
            print(f"[ik] cannot start: {e}")
            return

        print(f"[ik] listening on {host}:{port}")
        with server:
            while True:
                try:
                    conn, address = server.accept()
                    with conn:
                        print(f"[ik] connected from {address}")
                        trc_path = _receive_file(conn)
                        print(f"[ik] received TRC: {trc_path}")
                        trc_queue.put(str(trc_path))
                except EOFError:
                    print("[ik] sender disconnected before file was complete")
                except OSError as e:
                    print(f"[ik] receive error: {e}")

    threading.Thread(target=_recv_loop, daemon=True).start()

    # --- 主线程：取 TRC → 播放 → 等新 TRC ---
    next_trc_path = None
    while True:
        trc_path = next_trc_path or trc_queue.get()
        next_trc_path = None
        if trc_path is None:
            break
        result = player.play_trc_file(trc_path, check_queue=trc_queue)
        if result:
            next_trc_path = result


if __name__ == "__main__":
    main()
