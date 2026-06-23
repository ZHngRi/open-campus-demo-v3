r"""
接收端 — 先加载模型显示窗口 → 接收 marker 数据 → IK 实时求解播放
===================================================================
用法:
    python receive_and_play.py                      # 监听 0.0.0.0:5005
    python receive_and_play.py 100.111.140.103      # 指定发送端 IP
    python receive_and_play.py 0.0.0.0 5005         # 指定 host 和 port
    python receive_and_play.py --keep-open          # 播完后保持窗口，按 Enter 关闭
"""
import sys
import os
import time
import opensim as osim

import config
from marker_receiver import MarkerFrameReceiver
from opensim_marker_reference1 import make_markers_reference_from_packets


HOST = "0.0.0.0"
PORT = 5005


# ---------------------------------------------------------------
#  自动定位 simbody-visualizer.exe 并加入 PATH
# ---------------------------------------------------------------
def _ensure_visualizer_path():
    if sys.platform != "win32":
        return

    opensim_dir = os.path.dirname(os.path.abspath(osim.__file__))
    env_root = os.path.dirname(os.path.dirname(opensim_dir))
    candidates = [
        os.path.join(env_root, "Library", "bin"),
        os.path.join(env_root, "bin"),
    ]

    for d in candidates:
        exe = os.path.join(d, "simbody-visualizer.exe")
        if os.path.isfile(exe):
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + ";" + os.environ.get("PATH", "")
            return d
    return None


# ---------------------------------------------------------------
#  加载模型 & 打开可视化窗口
# ---------------------------------------------------------------
def load_model():
    print("━" * 50)
    print("  加载模型...")
    print("━" * 50)

    geom_dir = str(config.GEOMETRY_DIR)
    if os.path.isdir(geom_dir):
        osim.ModelVisualizer.addDirToGeometrySearchPaths(geom_dir)
        print(f"  📁 Geometry 路径: {geom_dir}")

    model = osim.Model(str(config.MODEL_FILE))
    print(f"  ✅ 模型已加载: {model.getName()}")

    model.setUseVisualizer(True)

    viz_dir = _ensure_visualizer_path()
    if viz_dir:
        print(f"  🔧 Visualizer 路径: {viz_dir}")

    try:
        state = model.initSystem()
    except RuntimeError as e:
        msg = str(e)
        if "simbody-visualizer" in msg or "Unable to spawn" in msg:
            print("❌ simbody-visualizer 未找到")
            print()
            print("  Windows 解决:")
            print('    $env:PATH = "C:\\others\\software\\canda\\envs\\opensim452\\Library\\bin;" + $env:PATH')
            print()
        raise

    visualizer = model.updVisualizer()

    # 显示初始姿态（窗口立刻弹出）
    model.realizePosition(state)
    visualizer.show(state)

    print("  🖥️  Visualizer 窗口已打开")
    print()

    return model, state, visualizer


# ---------------------------------------------------------------
#  Marker weights & IK helpers
# ---------------------------------------------------------------
def create_marker_weights():
    marker_weights = osim.SetMarkerWeights()
    for name, weight in config.MARKER_WEIGHTS.items():
        marker_weights.cloneAndAppend(
            osim.MarkerWeight(name, float(weight))
        )
    return marker_weights


def filter_packet_markers(packet, marker_names):
    """只保留 IK 需要的 marker，缺失则跳过"""
    available = set(packet.markers.keys())
    required = set(marker_names)
    missing = required - available

    if missing:
        print(f"[skip] missing markers: {sorted(missing)}  "
              f"frame={packet.frame_index}  time={packet.time}")
        return None

    packet.markers = {
        name: packet.markers[name]
        for name in marker_names
    }
    return packet


# ---------------------------------------------------------------
#  main
# ---------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    host = args[0] if len(args) >= 1 else HOST
    port = int(args[1]) if len(args) >= 2 else PORT
    keep_open = "--keep-open" in flags

    # ——— 第 1 步：加载模型，打开可视化窗口 ———
    model, state, visualizer = load_model()

    marker_names = config.REALTIME_MARKER_NAMES
    marker_weights = create_marker_weights()
    coordinate_references = osim.SimTKArrayCoordinateReference()

    # 记下 T-pose 的坐标默认值（用来复位）
    coord_set = model.getCoordinateSet()
    tpose_values = {}
    for i in range(coord_set.getSize()):
        coord = coord_set.get(i)
        tpose_values[coord.getName()] = coord.getValue(state)

    round_num = 0

    try:
        while True:
            round_num += 1

            # ——— 回到 T-pose ———
            if round_num > 1:
                print()
                print("━" * 50)
                print("  回到 T-pose，等待下一轮...")
                print("━" * 50)
                for name, val in tpose_values.items():
                    coord_set.get(name).setValue(state, val)
                model.realizePosition(state)
                visualizer.show(state)

            # ——— 等待发送端连接 ———
            print()
            print("━" * 50)
            print(f"  [轮次 {round_num}] 等待发送端连接 {host}:{port} ...")
            print("━" * 50)
            print()

            try:
                receiver = MarkerFrameReceiver(host=host, port=port)
                receiver.start()
            except Exception as e:
                print(f"  ❌ 无法启动接收: {e}")
                time.sleep(1)
                continue

            # ——— 一次性接收全部 packet ———
            print("  接收 marker 数据...")
            packets = []

            try:
                while True:
                    packet = receiver.receive_next()
                    packet = filter_packet_markers(packet, marker_names)
                    if packet is None:
                        continue
                    packets.append(packet)
            except EOFError:
                print(f"  发送端已断开，共收到 {len(packets)} 帧")
            except KeyboardInterrupt:
                print(f"\n  用户中断，已收到 {len(packets)} 帧")
                try:
                    receiver.close()
                except Exception:
                    pass
                break
            except Exception as e:
                print(f"  ❌ 接收错误: {e}")
                try:
                    receiver.close()
                except Exception:
                    pass
                continue

            try:
                receiver.close()
            except Exception:
                pass

            if not packets:
                print("  ⚠️  没有收到有效数据，继续等待...")
                continue

            # ——— 一次性 IK 求解 + 播放 ———
            print()
            print("━" * 50)
            print(f"  IK 求解 {len(packets)} 帧...")
            print("━" * 50)

            # 从 T-pose 开始（复位所有坐标到默认值）
            for name, val in tpose_values.items():
                coord_set.get(name).setValue(state, val)

            markers_reference = make_markers_reference_from_packets(
                packets=packets,
                marker_names=marker_names,
                marker_weights=marker_weights,
            )

            ik_solver = osim.InverseKinematicsSolver(
                model,
                markers_reference,
                coordinate_references,
                config.CONSTRAINT_WEIGHT,
            )

            t0 = time.time()
            ik_errors = 0

            for packet in packets:
                state.setTime(float(packet.time))

                try:
                    ik_solver.assemble(state)
                except Exception as e:
                    ik_errors += 1
                    print(f"  [ik error] frame={packet.frame_index} time={packet.time:.3f}: {e}")
                    continue

                model.realizePosition(state)
                visualizer.show(state)

            elapsed = time.time() - t0
            print(f"  ✅ 完成  {len(packets)} 帧  "
                  f"IK失败={ik_errors}  "
                  f"耗时={elapsed:.3f}s")

    except KeyboardInterrupt:
        print("\n  已停止")

    # ——— 保持窗口 ———
    if keep_open:
        print()
        print("按 Enter 关闭窗口...")
        try:
            input()
        except EOFError:
            pass


if __name__ == "__main__":
    main()
