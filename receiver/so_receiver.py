r"""
SO Receiver — 独立进程，只做 Static Optimization
=================================================
收到 session_packet → 取 mot 字段 → SO 求解 → 全帧播放（SO 帧亮肌肉，中间帧灰色）
播放期间收到新 MOT → 复位 → 重新求解 → 切换播放

用法:
    python so_receiver.py                      # 监听 0.0.0.0:5006
    python so_receiver.py 0.0.0.0 5006         # 指定 host 和 port
"""
import queue
import sys
import threading

from marker_receiver import SessionReceiver
from session_packet import SessionPacket
from static_optimization_player import StaticOptimizationPlayer

HOST = "0.0.0.0"
PORT = 5006


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    host = args[0] if len(args) >= 1 else HOST
    port = int(args[1]) if len(args) >= 2 else PORT

    print("=" * 60)
    print("  SO Receiver")
    print("=" * 60)

    player = StaticOptimizationPlayer()
    mot_queue = queue.Queue()

    # --- receive 线程：收到 session_packet → 取 mot → 放入队列 ---
    def _recv_loop():
        while True:
            try:
                receiver = SessionReceiver(host=host, port=port)
                receiver.start()
            except OSError as e:
                print(f"[so] cannot start: {e}")
                continue

            try:
                while True:
                    packet = receiver.receive()
                    print(f"[so] session → MOT: {packet.mot}")
                    mot_queue.put(packet.mot)
            except EOFError:
                print("[so] sender disconnected")
            finally:
                try:
                    receiver.close()
                except OSError:
                    pass

    threading.Thread(target=_recv_loop, daemon=True).start()

    # --- 主线程：取 MOT → solve → 播放 → 等新 MOT ---
    while True:
        mot_path = mot_queue.get()
        if mot_path is None:
            break
        player.play_mot_file(mot_path, check_queue=mot_queue)


if __name__ == "__main__":
    main()
