"""
IK 播放器 — 读取 TRC 文件，运行 Inverse Kinematics，在独立 Simbody Visualizer 窗口中循环显示。
"""

import queue
import sys
import os
import time
from pathlib import Path

import config


def _ensure_visualizer_path():
    if sys.platform != "win32":
        return
    import opensim as osim
    opensim_dir = os.path.dirname(os.path.abspath(osim.__file__))
    env_root = os.path.dirname(os.path.dirname(opensim_dir))
    for d in [os.path.join(env_root, "Library", "bin"), os.path.join(env_root, "bin")]:
        exe = os.path.join(d, "simbody-visualizer.exe")
        if os.path.isfile(exe):
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + ";" + os.environ.get("PATH", "")
            return d
    return None


class IKPlayer:
    """IK 播放器。

    读取 TRC → batch IK 求解 → 循环显示骨骼动画。
    与 SO 完全独立，互不干扰。
    """

    def __init__(self):
        import opensim as osim
        self._osim = osim

        _ensure_visualizer_path()

        geom_dir = str(config.GEOMETRY_DIR)
        if os.path.isdir(geom_dir):
            osim.ModelVisualizer.addDirToGeometrySearchPaths(geom_dir)
            print(f"  [IK] Geometry: {geom_dir}")

        print("[IK] loading model...")
        self.model = osim.Model(str(config.MODEL_FILE))
        self.model.setUseVisualizer(True)
        self.state = self.model.initSystem()
        self.model.realizePosition(self.state)
        self.model.updVisualizer().show(self.state)

        # 保存 T-pose，用于循环间隙复位
        self._tpose_values = self._snapshot_coord_values()

        # IK 常量
        self._marker_names = config.REALTIME_MARKER_NAMES
        self._marker_weights = self._build_marker_weights()
        self._coordinate_refs = osim.SimTKArrayCoordinateReference()

        print("[IK] model loaded, visualizer window opened\n")

    # ------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------

    def play_trc_file(self, trc_path, check_queue=None):
        """读取 TRC，batch IK 求解，循环显示。

        check_queue: 可选 queue.Queue，每帧非阻塞检查。
                    收到新 TRC 路径 → 返回该路径（调用方切到新 TRC）
                    收到 None    → 返回 False（调用方退出）
        """
        trc_path = Path(trc_path)
        if not trc_path.exists():
            print(f"[IK] TRC not found: {trc_path}")
            return False

        print(f"[IK] reading: {trc_path}")

        frames = list(self._parse_trc(trc_path))
        if not frames:
            print("[IK] no valid frames in TRC")
            return False
        print(f"[IK] {len(frames)} frames")

        # 构建 batch MarkersReference + IK Solver
        markers_ref = self._build_markers_ref(frames)
        ik_solver = self._osim.InverseKinematicsSolver(
            self.model, markers_ref, self._coordinate_refs, config.CONSTRAINT_WEIGHT,
        )

        frame_delay = 1.0 / config.FPS

        while True:
            self._reset_to_tpose()
            self.model.updVisualizer().show(self.state)

            for _, frame_time, _ in frames:
                # 非阻塞检查队列
                result = self._check_queue(check_queue)
                if result is not None:
                    self._reset_to_tpose()
                    self.model.updVisualizer().show(self.state)
                    return result

                self.state.setTime(frame_time)
                try:
                    ik_solver.assemble(self.state)
                except RuntimeError:
                    pass
                self.model.realizePosition(self.state)
                self.model.updVisualizer().show(self.state)
                # time.sleep(frame_delay)

    # ------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------

    def _snapshot_coord_values(self):
        cs = self.model.getCoordinateSet()
        return {cs.get(i).getName(): cs.get(i).getValue(self.state)
                for i in range(cs.getSize())}

    def _reset_to_tpose(self):
        cs = self.model.getCoordinateSet()
        for name, val in self._tpose_values.items():
            cs.get(name).setValue(self.state, val)
        self.model.realizePosition(self.state)

    def _build_marker_weights(self):
        w = self._osim.SetMarkerWeights()
        for name, weight in config.MARKER_WEIGHTS.items():
            w.cloneAndAppend(self._osim.MarkerWeight(name, float(weight)))
        return w

    @staticmethod
    def _check_queue(q):
        if q is None:
            return None
        try:
            item = q.get_nowait()
            return False if item is None else item
        except queue.Empty:
            return None

    # ------------------------------------------------------------
    # TRC 解析
    # ------------------------------------------------------------

    def _parse_trc(self, trc_path):
        """解析 TRC 文件，yield (frame_index, time, {marker: (x,y,z)})。"""
        with open(trc_path, "r", encoding="utf-8", errors="ignore") as f:
            f.readline()  # line 1: PathFileType
            f.readline()  # line 2: field labels
            meta = f.readline().strip().split("\t")
            num_frames = int(meta[2])

            marker_line = f.readline().strip().split("\t")
            trc_names = []
            for i in range(2, len(marker_line), 3):
                name = marker_line[i].strip()
                if name:
                    trc_names.append(name)

            # IK marker → TRC 列偏移
            name_to_col = {}
            for ik_name in self._marker_names:
                if ik_name in trc_names:
                    name_to_col[ik_name] = 2 + trc_names.index(ik_name) * 3

            f.readline()  # line 5（空行或第二行列名）

            for fi in range(num_frames):
                line = f.readline()
                if not line:
                    break
                parts = line.strip().split("\t")
                if len(parts) < 2:
                    continue

                t = float(parts[1])
                markers = {}
                for ik_name, col in name_to_col.items():
                    if col + 2 < len(parts):
                        markers[ik_name] = (
                            float(parts[col]),
                            float(parts[col + 1]),
                            float(parts[col + 2]),
                        )

                if len(markers) == len(name_to_col):
                    yield fi, t, markers

    def _build_markers_ref(self, frames):
        """帧列表 → multi-frame MarkersReference（batch IK）。"""
        table = self._osim.TimeSeriesTableVec3()

        labels = self._osim.StdVectorString()
        for name in self._marker_names:
            labels.append(name)
        table.setColumnLabels(labels)

        for _, t, markers in frames:
            row = self._osim.RowVectorVec3(
                len(self._marker_names),
                self._osim.Vec3(0.0, 0.0, 0.0),
            )
            for i, name in enumerate(self._marker_names):
                x, y, z = markers[name]
                row[i] = self._osim.Vec3(x, y, z)
            table.appendRow(t, row)

        return self._osim.MarkersReference(table, self._marker_weights)
