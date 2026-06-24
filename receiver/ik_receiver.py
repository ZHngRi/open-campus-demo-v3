r"""
IK Receiver — 独立进程，只做 Inverse Kinematics
=================================================
收到 session_packet → 取 trc 字段 → IK 求解 → 循环显示骨骼动画
播放期间收到新 TRC → 复位 T-pose → 切到新动画

用法:
    python ik_receiver.py                      # 监听 0.0.0.0:5005
    python ik_receiver.py 0.0.0.0 5005         # 指定 host 和 port
"""
import queue
import sys
import threading

from marker_receiver import SessionReceiver
from session_packet import SessionPacket
from ik_player import IKPlayer

HOST = "0.0.0.0"
PORT = 5005


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    host = args[0] if len(args) >= 1 else HOST
    port = int(args[1]) if len(args) >= 2 else PORT

    print("=" * 60)
    print("  IK Receiver")
    print("=" * 60)

    player = IKPlayer()
    trc_queue = queue.Queue()

    # --- receive 线程：收到 session_packet → 取 trc → 放入队列 ---
    def _recv_loop():
        while True:
            try:
                receiver = SessionReceiver(host=host, port=port)
                receiver.start()
            except OSError as e:
                print(f"[ik] cannot start: {e}")
                continue

            try:
                while True:
                    packet = receiver.receive()
                    print(f"[ik] session → TRC: {packet.trc}")
                    trc_queue.put(packet.trc)
            except EOFError:
                print("[ik] sender disconnected")
            finally:
                try:
                    receiver.close()
                except OSError:
                    pass

    threading.Thread(target=_recv_loop, daemon=True).start()

    # --- 主线程：取 TRC → 播放 → 等新 TRC ---
    while True:
        trc_path = trc_queue.get()
        if trc_path is None:
            break
        player.play_trc_file(trc_path, check_queue=trc_queue)


if __name__ == "__main__":
    main()
