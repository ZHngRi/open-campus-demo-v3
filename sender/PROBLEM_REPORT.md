# OpenCap 单目上传：昨天正常，今天骨盆畸形

## 问题描述

两套代码通过 OpenCap API 上传视频做单目动作捕捉：

- **旧版代码**（昨天，结果正常，人体没有畸形）
- **新版代码**（今天，结果骨盆巨大、人体畸形）

两套代码的相机参数、视频文件、上传链路完全相同，但结果差异巨大。

---

## 一、完全相同的部分（已排除）

以下参数两套代码一致，不是问题根源：

| 参数 | 值 |
|------|-----|
| `fov` | `"69.46971893310547"` |
| `model` | `"iPhone14,5"` |
| `max_framerate` | `240` |
| `subject_mass` | `"75"` |
| `subject_height` | `"1.75"` |
| `settings_framerate` | `"60"` |
| `settings_pose_model` | `"OPENPOSE"` |
| `settings_openSimModel` | `"LaiArnold"` |
| 视频文件 | 同一个 `single_leg_hop_turn_around_walk.mov`（720×1280, 60fps, HEVC） |
| 上传方式 | 都是 multipart `PATCH /videos/{id}/` 直传 OpenCap S3 |
| 账号 | 同一个 ZHANG |

## 二、旧版代码（昨天正常）

这是昨天能正常运行的完整代码：

```python
#!/usr/bin/env python3
"""
OpenCap 单目动作捕捉 API Demo
"""

import requests
import sys
import time
import os
from pathlib import Path
import json

BASE = "https://api.opencap.ai"

USERNAME = "ZHANG"
EMAIL = "zhngri4245@gmail.com"
PASSWORD = "42451205942451205942"
FIRST_NAME = "ZHANG"
LAST_NAME = ""

VIDEO_PATH = "video_uploader/videos/hard.mp4"
SUBJECT_MASS_KG = "75"
SUBJECT_HEIGHT_M = "1.75"
SUBJECT_SEX = "male"


def api_request(method, path, headers=None, json_data=None, params=None, files=None):
    url = f"{BASE}{path}"
    if method == "GET":
        resp = requests.get(url, headers=headers, params=params)
    elif method == "POST":
        resp = requests.post(url, headers=headers, json=json_data, files=files)
    elif method == "PATCH":
        if files:
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


def login():
    resp = api_request("POST", "/login/", json_data={
        "username": USERNAME, "password": PASSWORD,
    })
    if resp is None:
        sys.exit(1)
    token = resp.get("token")
    otp_sent = resp.get("otp_challenge_sent", False)
    return token, otp_sent


def verify_otp(token):
    print("  请查看你的邮箱，输入收到的 6 位验证码")
    otp_code = input("  验证码: ").strip()
    if not otp_code:
        return False
    resp = api_request("POST", "/verify/",
                       headers={"Authorization": f"Token {token}"},
                       json_data={"otp_token": otp_code})
    return resp is not None


def create_mono_session(token):
    headers = {"Authorization": f"Token {token}"}
    resp = api_request("GET", "/sessions/new/", headers=headers)
    if resp is None:
        sys.exit(1)
    session = resp[0] if isinstance(resp, list) else resp
    session_id = session.get("id")
    api_request("GET", f"/sessions/{session_id}/set_metadata/",
                headers=headers, params={"isMono": "true"})
    return session_id


def set_metadata(token, session_id):
    headers = {"Authorization": f"Token {token}"}
    resp = api_request("POST", "/subjects/", headers=headers, json_data={
        "name": "Demo Subject",
    })
    subject_id = resp.get("id") if resp else None

    if subject_id:
        api_request("GET", f"/sessions/{session_id}/set_subject/",
                    headers=headers, params={"subject_id": subject_id})

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

    api_request("GET", f"/sessions/{session_id}/set_metadata/",
                headers=headers, params=params)

    # 写入 iPhone 型号 + settings
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
    api_request("PATCH", f"/sessions/{session_id}/",
                headers=headers, json_data=meta_patch)


def record_and_stop(token, session_id):
    headers = {"Authorization": f"Token {token}"}
    resp = api_request("GET", f"/sessions/{session_id}/record/",
                       headers=headers, params={"name": "test"})
    if resp is None:
        sys.exit(1)
    trial_id = resp.get("id")

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
        sys.exit(1)
    video_id = resp.get("id")

    time.sleep(1)
    api_request("GET", f"/sessions/{session_id}/stop/", headers=headers)
    return trial_id, video_id


def upload_video(token, trial_id, video_id):
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        print(f"  ❌ 视频文件不存在: {video_path}")
        sys.exit(1)
    with open(video_path, "rb") as f:
        resp = api_request("PATCH", f"/videos/{video_id}/",
                           files={"video": f})
    if resp is None:
        sys.exit(1)


def wait_for_processing(token, session_id):
    headers = {"Authorization": f"Token {token}"}
    while True:
        resp = api_request("GET", f"/sessions/{session_id}/status/",
                           headers=headers)
        if resp is None:
            time.sleep(5)
            continue

        status = resp.get("status")
        n_uploaded = resp.get("n_videos_uploaded", 0)

        if status == "ready" and n_uploaded > 0:
            trial_url = resp.get("trial", "")
            if trial_url:
                tid = trial_url.rstrip("/").split("/")[-1]
                trial_resp = api_request("GET", f"/trials/{tid}/", headers=headers)
                if trial_resp and isinstance(trial_resp, dict):
                    t_status = trial_resp.get("status", "")
                    if t_status == "done":
                        return True
                    elif t_status == "error":
                        return False
            return True
        time.sleep(3)


def download_results(token, session_id):
    import zipfile
    headers = {"Authorization": f"Token {token}"}
    project_root = Path(__file__).resolve().parent
    output_dir = project_root / "outputs"
    output_dir.mkdir(exist_ok=True)
    session_dir = output_dir / session_id
    session_dir.mkdir(exist_ok=True)
    zip_file = output_dir / f"session_{session_id[:8]}.zip"

    # 异步下载
    resp = api_request("GET", f"/sessions/{session_id}/async-download/", headers=headers)
    if resp and isinstance(resp, dict) and "task_id" in resp:
        task_id = resp["task_id"]
        waited = 0
        while waited < 600:
            log_resp = api_request("GET", f"/logs/{task_id}/on-ready/", headers=headers)
            if isinstance(log_resp, dict):
                dl_url = log_resp.get("url") or log_resp.get("media")
                if dl_url:
                    dl_resp = requests.get(dl_url, stream=True)
                    with open(zip_file, "wb") as f:
                        for chunk in dl_resp.iter_content(8192):
                            f.write(chunk)
                    with zipfile.ZipFile(zip_file, "r") as zf:
                        zf.extractall(session_dir)
                    zip_file.unlink()
                    return session_dir
            time.sleep(10)
            waited += 10


def main():
    token, otp_sent = login()
    if otp_sent:
        if not verify_otp(token):
            print("OTP 未验证")
    session_id = create_mono_session(token)
    set_metadata(token, session_id)
    trial_id, video_id = record_and_stop(token, session_id)
    upload_video(token, trial_id, video_id)
    success = wait_for_processing(token, session_id)
    if success:
        download_results(token, session_id)
    print(f"Session: {session_id}")


if __name__ == "__main__":
    main()
```

## 三、新版代码（今天，骨盆畸形）

新版是 FastAPI 后端的一部分，`sender/opencap_client.py` 中的 `process_session()` 函数。

### 最初版本（有畸形）

```python
# set_metadata 调用：
requests.get(f"{BASE}/sessions/{api_session_id}/set_metadata/",
             headers=headers, params={
                 "isMono": "true",
                 "subject_id": str(subject_id),
                 "subject_mass": SUBJECT_MASS,
                 "subject_height": SUBJECT_HEIGHT,
                 "subject_sex": SUBJECT_SEX,
                 "settings_framerate": "60",
                 "settings_pose_model": "OPENPOSE",
                 "settings_openSimModel": "LaiArnold",
                 # ❌ 缺少 settings_augmenter_model
                 # ❌ 缺少 settings_data_sharing
             })

# PATCH session 调用：
requests.patch(f"{BASE}/sessions/{api_session_id}/",
               headers=headers, json={
                   "meta": {"iphoneModel": {"camera1": "iPhone14,5"}},
                   # ❌ 缺少整个 settings 块
               })
```

其余部分（video.parameters、上传方式等）和旧版完全一致。

### 已修复版本（补上缺失参数后）

```python
# set_metadata 调用：
requests.get(f"{BASE}/sessions/{api_session_id}/set_metadata/",
             headers=headers, params={
                 "isMono": "true",
                 "subject_id": str(subject_id),
                 "subject_mass": SUBJECT_MASS,
                 "subject_height": SUBJECT_HEIGHT,
                 "subject_sex": SUBJECT_SEX,
                 "settings_framerate": "60",
                 "settings_pose_model": "OPENPOSE",
                 "settings_openSimModel": "LaiArnold",
                 "settings_augmenter_model": "v0.2",     # ✅ 补上
                 "settings_data_sharing": "true",         # ✅ 补上
             })

# PATCH session 调用：
requests.patch(f"{BASE}/sessions/{api_session_id}/",
               headers=headers, json={
                   "meta": {
                       "iphoneModel": {"camera1": "iPhone14,5"},
                       "settings": {                      # ✅ 补上整个块
                           "framerate": "60",
                           "posemodel": "OPENPOSE",
                           "openSimModel": "LaiArnold",
                           "augmenter_model": "v0.2",
                           "datasharing": "true",
                       },
                   },
               })
```

## 四、差异总结

| 调用 | 旧版 | 新版（原始） | 新版（已修复） |
|------|------|-------------|---------------|
| `set_metadata` 有 `augmenter_model` | ✅ | ❌ | ✅ |
| `set_metadata` 有 `data_sharing` | ✅ | ❌ | ✅ |
| `PATCH` body 有 `settings` 块 | ✅ | ❌ | ✅ |
| 其他所有参数 | 一致 | 一致 | 一致 |

## 五、疑问

1. 缺失的 `augmenter_model` 和 `settings` 块是否足以导致骨盆巨大这类严重畸变？
2. 如果不足以致畸变，还有哪些两版代码之间未检查到的差异？
3. 参数补上后是否仍有畸变？（等待用户下一次运行反馈）
