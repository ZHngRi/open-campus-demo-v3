"""
OpenCap 单目 API: 上传视频 → 云端处理 → 下载 3D 运动学结果。

用法:
    python opencap_monocular_demo.py

配置:
    修改下面 USERNAME / PASSWORD / EMAIL / VIDEO_PATH / SUBJECT_*
"""

import sys
import time
import json
import uuid
import math
import zipfile
from pathlib import Path
import requests

# ======== 你的账号 ========
USERNAME = "ZHANG"
PASSWORD = "42451205942451205942"
EMAIL = "zhngri4245@gmail.com"

# ======== 视频和拍摄对象 ========
VIDEO_PATH = "video/single_leg_hop_turn_around_walk_scaled.mp4"
SUBJECT_MASS = "75"
SUBJECT_HEIGHT = "1.75"
SUBJECT_SEX = "male"

# ======== API 地址 ========
BASE = "https://api.opencap.ai"


def login():
    """登录，返回 token"""
    r = requests.post(f"{BASE}/login/", json={
        "username": USERNAME,
        "password": PASSWORD,
    })
    if r.status_code != 200:
        print(f"登录失败: {r.status_code} {r.text}")
        sys.exit(1)

    data = r.json()
    token = data["token"]
    need_otp = data.get("otp_challenge_sent", False)

    if need_otp:
        print("OTP 验证: 输入邮箱收到的 6 位验证码")
        code = input("> ").strip()
        requests.post(f"{BASE}/verify/",
                      headers={"Authorization": f"Token {token}"},
                      json={"otp_token": code})

    return token


def create_session(token):
    """创建单目 Session，返回 session_id"""
    headers = {"Authorization": f"Token {token}"}

    # 新建 session
    r = requests.get(f"{BASE}/sessions/new/", headers=headers)
    session_id = r.json()[0]["id"]

    # 启用单目模式
    requests.get(f"{BASE}/sessions/{session_id}/set_metadata/",
                 headers=headers, params={"isMono": "true"})

    # 创建 Subject
    r = requests.post(f"{BASE}/subjects/", headers=headers,
                      json={"name": "Demo Subject"})
    subject_id = r.json()["id"]

    # 关联 Subject
    requests.get(f"{BASE}/sessions/{session_id}/set_subject/",
                 headers=headers, params={"subject_id": subject_id})

    # 设置元数据（体重、身高、模型参数）
    requests.get(f"{BASE}/sessions/{session_id}/set_metadata/",
                 headers=headers, params={
                     "isMono": "true",
                     "subject_id": str(subject_id),
                     "subject_mass": SUBJECT_MASS,
                     "subject_height": SUBJECT_HEIGHT,
                     "subject_sex": SUBJECT_SEX,
                     "settings_framerate": "60",
                     "settings_pose_model": "OPENPOSE",
                     "settings_openSimModel": "LaiArnold",
                 })

    # 写入 iPhone 型号（让 Worker 找到正确的相机内参）
    requests.patch(f"{BASE}/sessions/{session_id}/",
                   headers=headers, json={
                       "meta": {
                           "iphoneModel": {"camera1": "iPhone14,5"},
                       }
                   })

    return session_id


def record_and_stop(token, session_id):
    """录制一段 Trial，返回 trial_id 和 video_id"""
    headers = {"Authorization": f"Token {token}"}

    # 开始录制
    r = requests.get(f"{BASE}/sessions/{session_id}/record/",
                     headers=headers, params={"name": "test"})
    trial_id = r.json()["id"]

    # 预建 Video 记录（Worker 在 stop 后检查无 video 就不会立即取走）
    device_id = str(uuid.uuid4())
    r = requests.post(f"{BASE}/videos/", headers=headers, json={
        "trial": trial_id,
        "device_id": device_id,
        "parameters": {
            "fov": "69.46971893310547",
            "model": "iPhone14,5",
            "max_framerate": 240,
        },
    })
    video_id = r.json()["id"]

    time.sleep(1)

    # 停止
    requests.get(f"{BASE}/sessions/{session_id}/stop/", headers=headers)

    return trial_id, video_id


def upload_video(token, video_id):
    """上传本地视频文件到 Video 记录"""
    video_path = Path(VIDEO_PATH)

    with open(video_path, "rb") as f:
        requests.patch(f"{BASE}/videos/{video_id}/",
                       headers={"Authorization": f"Token {token}"},
                       files={"video": f})


def wait_until_done(token, session_id):
    """轮询直到处理完成"""
    headers = {"Authorization": f"Token {token}"}

    while True:
        r = requests.get(f"{BASE}/sessions/{session_id}/status/",
                         headers=headers)
        status = r.json()["status"]
        trial_url = r.json().get("trial")

        # 检查真实 trial 状态
        if status == "ready" and trial_url:
            trial_id = trial_url.rstrip("/").split("/")[-1]
            tr = requests.get(f"{BASE}/trials/{trial_id}/", headers=headers)
            t_status = tr.json().get("status")

            if t_status == "done":
                print("处理完成")
                return True
            elif t_status == "error":
                error = tr.json().get("meta", {}).get("error_msg", "")
                print(f"处理失败: {error}")
                return False

        print(f"  {status} ... 等 5 秒")
        time.sleep(5)


def download_and_unzip(token, session_id):
    """下载结果 zip 并解压到 outputs/ 下"""
    headers = {"Authorization": f"Token {token}"}
    out_dir = Path(__file__).parent / "outputs" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 异步下载
    r = requests.get(f"{BASE}/sessions/{session_id}/async-download/",
                     headers=headers)
    task_id = r.json()["task_id"]

    # 等就绪
    while True:
        r = requests.get(f"{BASE}/logs/{task_id}/on-ready/", headers=headers)
        data = r.json()
        url = data.get("url") or data.get("media")
        if url:
            break
        time.sleep(5)

    # 下载
    zip_data = requests.get(url).content
    zip_file = out_dir / "result.zip"
    zip_file.write_bytes(zip_data)

    # 解压
    with zipfile.ZipFile(zip_file, "r") as zf:
        zf.extractall(out_dir)
    zip_file.unlink()

    print(f"结果: {out_dir}")

    # 列出关键文件
    for mot in out_dir.rglob("*.mot"):
        print(f"  .mot: {mot}")
    for osim in out_dir.rglob("*.osim"):
        print(f"  .osim: {osim}")
    for trc in out_dir.rglob("*.trc"):
        print(f"  .trc: {trc}")


def main():
    print("登录...")
    token = login()

    print("创建 Session...")
    session_id = create_session(token)

    print("录制...")
    trial_id, video_id = record_and_stop(token, session_id)

    print("上传视频...")
    upload_video(token, video_id)

    print("等待处理...")
    ok = wait_until_done(token, session_id)

    if ok:
        print("下载结果...")
        download_and_unzip(token, session_id)

    print(f"\nSession: {session_id}")
    print(f"Web: https://app.opencap.ai/session/{session_id}/")


if __name__ == "__main__":
    main()
