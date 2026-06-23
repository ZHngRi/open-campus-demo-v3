"""
诊断 OpenCap 上传参数，不修改任何文件。
"""
import sys
import json
import pickle
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
VIDEOS = DATA / "videos"
SESSIONS = DATA / "sessions"

# ============================================================
# 1. 视频检查
# ============================================================

def check_video():
    print("[VIDEO]")
    video_dirs = sorted(VIDEOS.iterdir()) if VIDEOS.exists() else []
    if not video_dirs:
        print("  videos/ 目录为空")
        return None

    d = video_dirs[-1]
    videos = list(d.glob("*.mp4")) + list(d.glob("*.mov"))
    if not videos:
        print(f"  {d.name}: 无视频文件")
        return None

    vpath = videos[0]
    size_mb = vpath.stat().st_size / 1024 / 1024

    # 用 OpenCV 读元数据
    try:
        import cv2
        cap = cv2.VideoCapture(str(vpath))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = frames / fps if fps else 0

        # 读第一帧保存
        ok, frame = cap.read()
        cap.release()
    except Exception as e:
        print(f"  cv2 读取失败: {e}")
        w = h = fps = frames = dur = 0
        ok = False

    print(f"  path: {vpath}")
    print(f"  size: {size_mb:.1f} MB")
    print(f"  resolution: {w} x {h}")
    print(f"  fps: {fps:.1f}")
    print(f"  frames: {frames}")
    print(f"  duration: {dur:.1f}s")
    orient = "竖屏" if h > w else "横屏"
    print(f"  orientation: {orient}")
    print(f"  center: ({w/2:.1f}, {h/2:.1f})")

    # 保存帧
    if ok:
        debug_dir = ROOT / "debug_frames"
        debug_dir.mkdir(exist_ok=True)
        mid = frames // 2
        cap2 = cv2.VideoCapture(str(vpath))
        for target in [0, mid, frames - 1]:
            cap2.set(cv2.CAP_PROP_POS_FRAMES, target)
            _, f = cap2.read()
            if f is not None:
                cv2.imwrite(str(debug_dir / f"frame_{target:04d}.jpg"), f)
        cap2.release()
        print(f"  帧已保存: {debug_dir}/")

    return {"path": str(vpath), "w": w, "h": h, "fps": fps, "frames": frames}


# ============================================================
# 2. 相机内参检查
# ============================================================

def check_intrinsics():
    print("\n[CAMERA_INTRINSICS]")
    # 搜索所有 cameraIntrinsics.pickle
    pickle_files = list(ROOT.rglob("cameraIntrinsics.pickle"))
    if not pickle_files:
        pickle_files = list(Path("/home/zhr").rglob("cameraIntrinsics.pickle"))
    if not pickle_files:
        # opencap-core 的
        base = Path("/home/zhr/opencap")
        pickle_files = list(base.rglob("cameraIntrinsics.pickle"))

    if not pickle_files:
        print("  未找到 cameraIntrinsics.pickle")
        return None

    pf = pickle_files[0]
    print(f"  文件: {pf}")
    with open(pf, "rb") as f:
        data = pickle.load(f)

    print(f"  内容类型: {type(data)}")
    if isinstance(data, dict):
        for k in sorted(data.keys()):
            v = data[k]
            print(f"  {k}: {v}")
            if hasattr(v, "shape"):
                print(f"    shape: {v.shape}")

    return data


# ============================================================
# 3. 上传 payload
# ============================================================

def check_upload_payload():
    print("\n[UPLOAD_PAYLOAD]")
    payload_found = False

    # 搜索 opencap_client.py 里的 parameters
    client = ROOT / "opencap_client.py"
    if client.exists():
        content = client.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            if "parameters" in line.lower() or "fov" in line.lower() or "model" in line.lower():
                print(f"  {client.name}:{i}: {line.strip()}")
                payload_found = True

    if not payload_found:
        print("  未在代码中找到 parameters 定义")

    # 打印实际会发送的值
    print("\n  代码中硬编码的 parameters:")
    print('    fov: "69.46971893310547"')
    print('    model: "iPhone14,5"')
    print('    max_framerate: 240')


# ============================================================
# 4. 文件上传链路
# ============================================================

def check_upload_file(video_info):
    print("\n[UPLOAD_FILE]")

    client = ROOT / "opencap_client.py"
    if client.exists():
        content = client.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            if "video_path" in line.lower() or "VIDEOS" in line.lower():
                print(f"  {client.name}:{i}: {line.strip()}")

    if video_info:
        print(f"\n  实际上传文件: {video_info['path']}")
        print(f"  分辨率: {video_info['w']}x{video_info['h']}")

    # 检查是否有 resize/crop/rotate 操作
    resize_patterns = ["resize", "crop", "rotate", "transpose", "cv2.imwrite", "cv2.VideoWriter"]
    print("\n  搜索图像处理操作:")
    for pat in resize_patterns:
        hits = []
        for py_file in ROOT.glob("*.py"):
            for i, line in enumerate(py_file.read_text().split("\n"), 1):
                if pat.lower() in line.lower() and not line.strip().startswith("#"):
                    hits.append(f"    {py_file.name}:{i}: {line.strip()}")
        if hits:
            for h in hits:
                print(h)
    print("  (以上是代码中的操作，不一定是上传链路的)")


# ============================================================
# 5. 代码搜索
# ============================================================

def search_codebase():
    print("\n[CODE_SEARCH]")
    keywords = [
        "cameraIntrinsics.pickle", "intrinsicMat", "distortion",
        "imageSize", "fov", "max_framerate", "model",
        "iPhone14,5", "resize", "crop", "rotate", "transpose",
        "VideoCapture", "cv2.imwrite", "cv2.VideoWriter",
        "requests.post", "/videos/",
    ]

    for kw in keywords:
        locations = []
        for py_file in ROOT.glob("*.py"):
            for i, line in enumerate(py_file.read_text().split("\n"), 1):
                if kw.lower() in line.lower():
                    locations.append(f"    {py_file.name}:{i}")
        if locations:
            print(f"  {kw}:")
            for loc in locations[:5]:
                print(loc)
        else:
            print(f"  {kw}: NOT FOUND in sender/")


# ============================================================
# 6. 内参 vs 视频一致性
# ============================================================

def check_consistency(video_info, intrinsics):
    print("\n[CONSISTENCY CHECK]")
    if not video_info:
        print("  跳过（无视频信息）")
        return
    if not intrinsics:
        print("  跳过（无内参信息）")
        return

    vw = video_info["w"]
    vh = video_info["h"]

    img_size = intrinsics.get("imageSize")
    if img_size is not None and hasattr(img_size, "shape"):
        iw = int(img_size[0][0]) if img_size.shape[0] >= 1 else 0
        ih = int(img_size[1][0]) if img_size.shape[0] >= 2 else 0
    else:
        iw = ih = 0

    mat = intrinsics.get("intrinsicMat")
    if mat is not None and hasattr(mat, "shape") and mat.shape == (3, 3):
        fx, fy = float(mat[0, 0]), float(mat[1, 1])
        cx, cy = float(mat[0, 2]), float(mat[1, 2])
    else:
        fx = fy = cx = cy = 0

    print(f"  视频尺寸:  {vw} x {vh}")
    print(f"  内参尺寸:  {iw} x {ih}")
    print(f"  fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f}")
    print(f"  预期中心:   ({vw/2:.1f}, {vh/2:.1f})")
    print(f"  实际主点:   ({cx:.1f}, {cy:.1f})")
    print(f"  cx 偏差:    {cx - vw/2:.1f}")
    print(f"  cy 偏差:    {cy - vh/2:.1f}")

    if vw != iw or vh != ih:
        print(f"  ❌ 视频尺寸 ({vw}x{vh}) 与内参尺寸 ({iw}x{ih}) 不一致!")
    else:
        print(f"  ✅ 视频尺寸与内参尺寸一致")

    if abs(cx - vw/2) > vw * 0.1 or abs(cy - vh/2) > vh * 0.1:
        print(f"  ❌ 主点严重偏离图像中心!")


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  OpenCap 上传参数诊断")
    print("=" * 60)

    video_info = check_video()
    intrinsics = check_intrinsics()
    check_upload_payload()
    check_upload_file(video_info)
    search_codebase()
    check_consistency(video_info, intrinsics)

    print("\n" + "=" * 60)
    print("[POSSIBLE_CAUSES]")
    print("=" * 60)
    print()

    if video_info and intrinsics:
        vw, vh = video_info["w"], video_info["h"]
        img_size = intrinsics.get("imageSize")
        if img_size is not None and hasattr(img_size, "shape"):
            iw = int(img_size[0][0]) if img_size.shape[0] >= 1 else 0
            ih = int(img_size[1][0]) if img_size.shape[0] >= 2 else 0
            if vw != iw or vh != ih:
                print("  1. ❌ 视频尺寸与 cameraIntrinsics 不匹配 (确认)")
                print(f"     视频 {vw}x{vh} vs 内参 {iw}x{ih}")

    print("  2. FOV 硬编码为 69.47° (iPhone 13 主摄)")
    print("     如果上传视频不是 iPhone 13 主摄直出，FOV 一定错")
    print()
    print("  3. model 硬编码为 iPhone14,5")
    print("     如果设备型号不是 iPhone 13，相机模型不匹配")
    print()
    print("  4. 内参 imageSize=1280x720 是 iPhone 13 720p 模式")
    print("     如果视频是 1080p，内参尺寸就不对")
    print()
    print("  5. SUBJECT_MASS/HEIGHT 硬编码")
    print("     如果拍摄对象不是 80kg 1.76m，OpenSim 缩放会错")
    print()

    print("[NEXT_ACTION]")
    print("  确认上传视频的来源设备/分辨率，必要时修改 opencap_client.py 中的 fov/model")
    print("  或从 iPhone 13 拍摄原始 720p 视频上传")


if __name__ == "__main__":
    main()
