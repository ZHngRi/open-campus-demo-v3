r"""
SO Receiver — 独立进程，只做 Static Optimization
=================================================
收到 MOT 文件 → 保存到 receiver_data → SO 求解 → 全帧播放（SO 帧亮肌肉，中间帧灰色）
播放期间收到新 MOT → 复位 → 重新求解 → 切换播放

用法:
    python so_receiver.py                      # 监听 0.0.0.0:5006
    python so_receiver.py 0.0.0.0 5006         # 指定 host 和 port
"""
import queue
import socket
import sys
import threading
from pathlib import Path

from static_optimization_player import StaticOptimizationPlayer

HOST = "0.0.0.0"
PORT = 5006
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
    print("  SO Receiver")
    print("=" * 60)

    player = StaticOptimizationPlayer()
    mot_queue = queue.Queue()

    # --- receive 线程：收到 MOT 文件 → 保存 → 放入队列 ---
    def _recv_loop():
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
        except OSError as e:
            print(f"[so] cannot start: {e}")
            return

        print(f"[so] listening on {host}:{port}")
        with server:
            while True:
                try:
                    conn, address = server.accept()
                    with conn:
                        print(f"[so] connected from {address}")
                        mot_path = _receive_file(conn)
                        print(f"[so] received MOT: {mot_path}")
                        mot_queue.put(str(mot_path))
                except EOFError:
                    print("[so] sender disconnected before file was complete")
                except OSError as e:
                    print(f"[so] receive error: {e}")

    threading.Thread(target=_recv_loop, daemon=True).start()

    # --- 主线程：取 MOT → solve → 播放 → 等新 MOT ---
    next_mot_path = None
    while True:
        mot_path = next_mot_path or mot_queue.get()
        next_mot_path = None
        if mot_path is None:
            break
        result = player.play_mot_file(mot_path, check_queue=mot_queue)
        if result:
            next_mot_path = result


if __name__ == "__main__":
    main()
