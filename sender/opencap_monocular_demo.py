#!/usr/bin/env python3
"""
OpenCap 单目动作捕捉 API Demo
===============================
通过 api.opencap.ai 上传单段视频，获取 3D 运动学结果。

使用方法:
    python opencap_monocular_demo.py

首次使用会自动注册账号。已有账号可以跳过注册直接登录。
需要真实邮箱来接收 OTP 验证码。
"""

import requests
import sys
import time
import os
from pathlib import Path
import json
from pathlib import Path

BASE = "https://api.opencap.ai"

# ============================================================
# 配置区 - 填写你的信息
# ============================================================
USERNAME = "ZHANG"                  # 你的用户名
EMAIL = "zhngri4245@gmail.com"       # 你的真实邮箱（收验证码）
PASSWORD = "42451205942451205942"    # 你的密码 (最少8位)s
FIRST_NAME = "ZHANG"
LAST_NAME = ""

# 你要上传的视频文件路径（本地文件）
VIDEO_PATH = str(Path(__file__).resolve().parent / "video" / "single_leg_hop_turn_around_walk_scaled.mp4")

# 拍摄对象信息（可选，提高结果准确度）
SUBJECT_MASS_KG = "75"       # 体重（公斤）
SUBJECT_HEIGHT_M = "1.75"    # 身高（米）
SUBJECT_SEX = "male"         # male / female
# ============================================================


def api_request(method, path, headers=None, json_data=None, params=None, files=None):
    """发送 API 请求并处理错误"""
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=json_data, files=files)
        elif method == "PATCH":
            if files:
                # multipart 上传，不要设置 Content-Type，让 requests 自动处理
                patch_headers = {k: v for k, v in (headers or {}).items()
                                 if k.lower() != "content-type"}
                resp = requests.patch(url, headers=patch_headers, files=files)
            else:
                resp = requests.patch(url, headers=headers, json=json_data)
        else:
            raise ValueError(f"不支持的请求方法: {method}")

        if resp.status_code >= 400:
            print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp
    except requests.RequestException as e:
        print(f"  ❌ 网络错误: {e}")
        return None


def step(message):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}")




def login():
    """登录获取 token"""
    step("1. 登录")
    resp = api_request("POST", "/login/", json_data={
        "username": USERNAME,
        "password": PASSWORD,
    })

    if resp is None:
        print("  ❌ 登录失败，请检查用户名密码")
        sys.exit(1)

    token = resp.get("token")
    print(f"  ✅ 登录成功! user_id={resp.get('user_id')}")
    print(f"  Token: {token[:20]}...")

    otp_sent = resp.get("otp_challenge_sent", False)
    return token, otp_sent


def verify_otp(token):
    """验证 OTP"""
    step("3. OTP 验证")
    print("  请查看你的邮箱，输入收到的 6 位验证码")
    otp_code = input("  验证码: ").strip()

    if not otp_code:
        print("  ❌ 未输入验证码，跳过 OTP")
        return False

    resp = api_request("POST", "/verify/",
                       headers={"Authorization": f"Token {token}"},
                       json_data={"otp_token": otp_code})

    if resp is not None:
        print("  ✅ OTP 验证成功!")
        return True
    else:
        print("  ❌ OTP 验证失败")
        return False


def create_mono_session(token):
    """创建单目 Session"""
    step("4. 创建单目 Session")
    headers = {"Authorization": f"Token {token}"}

    resp = api_request("GET", "/sessions/new/", headers=headers)

    if resp is None:
        print("  ❌ 创建 Session 失败")
        sys.exit(1)

    # API 返回的是列表，取第一个
    if isinstance(resp, list):
        session = resp[0]
    else:
        session = resp

    session_id = session.get("id")
    print(f"  ✅ Session 创建成功!")
    print(f"  Session ID: {session_id}")

    # 设置单目模式
    print("  设置单目模式 (isMono=true)...")
    set_resp = api_request(
        "GET", f"/sessions/{session_id}/set_metadata/",
        headers=headers,
        params={"isMono": "true"}
    )
    if set_resp is not None:
        print("  ✅ 单目模式已启用")
    else:
        print("  ⚠️  单目模式设置可能失败")

    return session_id


def set_metadata(token, session_id):
    """创建 Subject 并关联到 Session"""
    step("5. 创建拍摄对象并设置元数据")
    headers = {"Authorization": f"Token {token}"}

    # 先创建一个 Subject
    resp = api_request("POST", "/subjects/", headers=headers, json_data={
        "name": "Demo Subject",
    })
    if resp is None:
        print("  ⚠️  创建 Subject 失败，继续执行...")
        subject_id = None
    else:
        subject_id = resp.get("id")
        print(f"  ✅ Subject 已创建: {subject_id}")

        # 关联 Subject 到 Session
        resp2 = api_request("GET", f"/sessions/{session_id}/set_subject/",
                            headers=headers, params={"subject_id": subject_id})
        if resp2 is not None:
            print(f"  ✅ Subject 已关联到 Session")

    # 设置详细元数据（monocular 需要的全部参数）
    params = {
        "isMono": "true",
        "settings_framerate": "60",
        "settings_pose_model": "OPENPOSE",
        "settings_openSimModel": "LaiArnold",
        "settings_augmenter_model": "v0.2",
        "settings_data_sharing": "true",
    }
    if subject_id:
        params["subject_id"] = subject_id
    if SUBJECT_MASS_KG:
        params["subject_mass"] = SUBJECT_MASS_KG
    if SUBJECT_HEIGHT_M:
        params["subject_height"] = SUBJECT_HEIGHT_M
    if SUBJECT_SEX:
        params["subject_sex"] = SUBJECT_SEX

    resp3 = api_request("GET", f"/sessions/{session_id}/set_metadata/",
                        headers=headers, params=params)

    if resp3 is not None:
        print(f"  ✅ 元数据设置完成")
        print(f"     体重: {SUBJECT_MASS_KG}kg, 身高: {SUBJECT_HEIGHT_M}m")
        print(f"     模型: OpenPose + LaiArnold")
    else:
        print("  ⚠️  元数据设置失败，继续执行...")

    # 关键：PATCH session.meta 加入 iPhone 型号信息
    # 这样 Worker 才知道用哪套相机内参来做 3D 重建
    print("  设置 iPhone 型号 (iPhone14,5 = iPhone 13)...")
    meta_patch = {
        "meta": {
            "iphoneModel": {"camera1": "iPhone14,5"},
            "settings": {
                "framerate": "60",
                "posemodel": "OPENPOSE",
                "openSimModel": "LaiArnold",
                "augmenter_model": "v0.2",
                "datasharing": "true",
            },
        }
    }
    if subject_id:
        meta_patch["meta"]["subject"] = {
            "id": str(subject_id),
            "mass": SUBJECT_MASS_KG,
            "height": SUBJECT_HEIGHT_M,
            "sex": SUBJECT_SEX,
        }
    # 合并已有的 meta
    if resp3 and isinstance(resp3, dict) and resp3.get("meta"):
        existing_meta = resp3["meta"]
        # PATCH 用全量覆盖
        pass

    resp4 = api_request("PATCH", f"/sessions/{session_id}/",
                        headers=headers, json_data=meta_patch)
    if resp4 is not None:
        print(f"  ✅ iPhone 型号已写入 session.meta")
    else:
        print("  ⚠️  iPhone 型号写入失败")


def record_and_stop(token, session_id):
    """开始录制，预创建 Video 记录，然后停止，最后上传视频"""
    step("6. 创建录制 Trial")
    headers = {"Authorization": f"Token {token}"}

    # 开始录制
    print("  开始录制...")
    resp = api_request("GET", f"/sessions/{session_id}/record/",
                       headers=headers, params={"name": "test"})
    if resp is None:
        print("  ❌ 开始录制失败")
        sys.exit(1)
    trial_id = resp.get("id")
    print(f"  ✅ 录制已开始 (Trial: {trial_id[:8]}...)")

    # 创建 Video 记录 (带 iPhone 13 主摄参数)
    import uuid
    device_id = str(uuid.uuid4())
    resp = api_request("POST", "/videos/", json_data={
        "trial": trial_id,
        "device_id": device_id,
        "parameters": {
            "fov": "69.46971893310547",
            "model": "iPhone14,5",
            "max_framerate": 240,
        },
    })
    if resp is None:
        print("  ❌ 创建 Video 记录失败")
        sys.exit(1)
    video_id = resp.get("id")
    print(f"  ✅ Video 记录已预创建: {video_id[:8]}...")

    # 停止录制
    time.sleep(1)
    print("  停止录制...")
    resp = api_request("GET", f"/sessions/{session_id}/stop/",
                       headers=headers)
    if resp is None:
        print("  ❌ 停止录制失败")
        sys.exit(1)
    print("  ✅ 录制已停止")

    return trial_id, video_id




def upload_video(token, trial_id, video_id):
    """上传本地视频文件到已有的 Video 记录"""
    step("7. 上传视频")
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        print(f"  ❌ 视频文件不存在: {video_path}")
        print(f"  请修改 VIDEO_PATH 变量")
        sys.exit(1)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"  视频文件: {video_path}")
    print(f"  文件大小: {size_mb:.1f} MB")
    print(f"  Video 记录: {video_id[:8]}...")

    # 直接上传视频文件（multipart/form-data）
    print("  上传视频文件中...")
    with open(video_path, "rb") as f:
        resp = api_request("PATCH", f"/videos/{video_id}/",
                           files={"video": f})

    if resp is not None:
        print(f"  ✅ 视频上传成功!")
    else:
        print("  ❌ 视频上传失败")
        sys.exit(1)


def wait_for_processing(token, session_id):
    """轮询等待处理完成"""
    step("9. 等待云端处理")
    print("  云端 Worker 正在处理视频...")
    print("  （这可能需要几分钟到十几分钟）")
    headers = {"Authorization": f"Token {token}"}

    max_wait = 1800  # 最多等 30 分钟
    check_interval = 10  # 每 3 秒检查一次
    waited = 0
    last_status = None

    while waited < max_wait:
        resp = api_request("GET", f"/sessions/{session_id}/status/",
                           headers=headers)

        if resp is None:
            print(f"  ⚠️  查询失败，{check_interval}秒后重试...")
            time.sleep(check_interval)
            waited += check_interval
            continue

        status = resp.get("status")
        n_uploaded = resp.get("n_videos_uploaded", 0)
        n_cameras = resp.get("n_cameras_connected", 0)

        if status != last_status:
            print(f"  [{waited}s] 状态: {status} (已上传 {n_uploaded}/{n_cameras} 视频)")
            last_status = status
        else:
            sys.stdout.write(f"\r  [{waited}s] 状态: {status} (已上传 {n_uploaded}/{n_cameras} 视频)")
            sys.stdout.flush()

        # 同时检查 Trial 的真实状态（ready 可能掩盖 error）
        if status == "ready" and n_uploaded > 0:
            trial_url = resp.get("trial", "")
            if trial_url:
                tid = trial_url.rstrip("/").split("/")[-1]
                trial_resp = api_request("GET", f"/trials/{tid}/", headers=headers)
                if trial_resp and isinstance(trial_resp, dict):
                    t_status = trial_resp.get("status", "")
                    if t_status == "done":
                        print(f"\n  ✅ 处理完成! (有 {len(trial_resp.get('results', []))} 个结果)")
                        return True
                    elif t_status == "error":
                        meta = trial_resp.get("meta") or {}
                        print(f"\n  ❌ 处理出错: {meta.get('error_msg', '未知错误')}")
                        return False
            print(f"\n  ✅ Session 状态 ready!")
            return True

        time.sleep(check_interval)
        waited += check_interval

    print(f"\n  ⚠️  超时 ({max_wait}s)，处理可能仍在进行中")
    print(f"  可以通过以下命令手动检查: ")
    print(f"  curl -H 'Authorization: Token {token}' {BASE}/sessions/{session_id}/status/")
    return False


def download_results(token, session_id):
    """下载处理结果并自动解压到 outputs/"""
    step("10. 下载结果并解压")
    import zipfile

    headers = {"Authorization": f"Token {token}"}

    # outputs 在项目根目录下
    project_root = Path(__file__).resolve().parent
    output_dir = project_root / "outputs"
    output_dir.mkdir(exist_ok=True)

    # 每个 session 一个子目录
    session_dir = output_dir / session_id
    session_dir.mkdir(exist_ok=True)

    zip_file = output_dir / f"session_{session_id[:8]}.zip"

    # ----- 下载 -----
    print(f"  下载中...")

    resp = api_request("GET", f"/sessions/{session_id}/download/",
                       headers=headers)

    downloaded = False
    if hasattr(resp, "iter_content"):
        with open(zip_file, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        size_mb = zip_file.stat().st_size / (1024 * 1024)
        if size_mb > 0.01:
            print(f"  ✅ 下载完成 ({size_mb:.1f} MB)")
            downloaded = True
        else:
            print(f"  ⚠️  文件太小 ({size_mb:.3f} MB)，尝试异步下载...")
    else:
        print(f"  ⚠️  直接下载失败，尝试异步下载...")

    if not downloaded:
        resp = api_request("GET", f"/sessions/{session_id}/async-download/",
                           headers=headers)
        if resp and isinstance(resp, dict) and "task_id" in resp:
            task_id = resp["task_id"]
            print(f"  异步任务已创建: {task_id}")
            waited = 0
            while waited < 600:
                log_resp = api_request("GET", f"/logs/{task_id}/on-ready/",
                                       headers=headers)
                if isinstance(log_resp, dict):
                    dl_url = log_resp.get("url") or log_resp.get("media")
                    if dl_url:
                        print(f"  下载地址已获取")
                        dl_resp = requests.get(dl_url, stream=True)
                        with open(zip_file, "wb") as f:
                            for chunk in dl_resp.iter_content(8192):
                                f.write(chunk)
                        size_mb = zip_file.stat().st_size / (1024 * 1024)
                        print(f"  ✅ 下载完成 ({size_mb:.1f} MB)")
                        downloaded = True
                        break
                time.sleep(10)
                waited += 10

    if not downloaded:
        print("  ❌ 下载失败")
        return

    # ----- 解压 -----
    print(f"  解压到: {session_dir}")
    with zipfile.ZipFile(zip_file, "r") as zf:
        zf.extractall(session_dir)

    # 删掉 zip，只留解压后的文件
    zip_file.unlink()

    # 列出结果
    files = sorted(session_dir.rglob("*"))
    # 只看第一层和第二层
    top_dirs = sorted(set(p.relative_to(session_dir).parts[0] for p in files if p.is_file()))
    print(f"  ✅ 解压完成! 内容:")
    for d in top_dirs:
        sub = session_dir / d
        count = len(list(sub.rglob("*")))
        print(f"      {d}/ ({count} 个文件)")

    return session_dir


def main():



    token, otp_sent = login()


    # ----- OTP 验证 -----
    # 如果已在本设备验证过，可能跳过
    if otp_sent:
        verified = verify_otp(token)
        if not verified:
            print("\n  ⚠️  OTP 未验证，后续需要认证的操作可能失败")
    else:
        print("\n  ✅ 已在本设备验证过 OTP，跳过")



    # ----- 核心流程 -----
    session_id = create_mono_session(token)
    set_metadata(token, session_id)
    trial_id, video_id = record_and_stop(token, session_id)

    # 上传视频（使用预创建的 video_id）
    upload_video(token, trial_id, video_id)

    # 等待处理
    success = wait_for_processing(token, session_id)

    # 下载结果
    result_dir = None
    if success:
        result_dir = download_results(token, session_id)

    # ----- 最终报告 -----
    step("完成!")
    print(f"""
  Session ID:  {session_id}
  Trial ID:    {trial_id}
  API 文档:    https://api.opencap.ai/docs/
  Web 查看:    https://app.opencap.ai/session/{session_id}/""")
    if result_dir:
        print(f"  结果目录:    {result_dir}")
    print(f"""
  结果文件包含:
    - 3D 运动学数据 (.mot 文件，可用 OpenSim 打开)
    - Marker 位置数据 (.trc 文件)
    - OpenSim 缩放模型 (.osim 文件)
    - 处理后的视频文件
    - 会话元数据
""")


if __name__ == "__main__":
    main()
