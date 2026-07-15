"""
OpenCap API 客户端：上传视频 → 等待处理 → 下载结果。

用法:
    from opencap_client import process_session
    process_session(session_id)
"""

import json
import time
import uuid
import zipfile
from pathlib import Path
import requests

BASE = "https://api.opencap.ai"

USERNAME = "ZHANG"
PASSWORD = "42451205942451205942"
EMAIL = "zhngri4245@gmail.com"
SUBJECT_MASS = "75"
SUBJECT_HEIGHT = "1.75"
SUBJECT_SEX = "male"

DATA = Path(__file__).parent / "data"
VIDEOS = DATA / "videos"
SESSIONS = DATA / "sessions"


TOKEN_FILE = DATA / "token.json"


def _subject_payload():
    """OpenCap processing reads subject dimensions from the Subject record."""
    sex_map = {"male": "man", "female": "woman", "man": "man", "woman": "woman"}
    sex = sex_map.get(str(SUBJECT_SEX).lower(), SUBJECT_SEX)
    return {
        "name": "Demo Subject",
        "weight": float(SUBJECT_MASS),
        "height": float(SUBJECT_HEIGHT),
        "gender": sex,
        "sex_at_birth": sex,
    }


def get_cached_token():
    """从缓存读 token，没有则返回 None"""
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text()).get("token")
    return None


def save_token(token):
    TOKEN_FILE.write_text(json.dumps({"token": token}))


def login_interactive():
    """终端交互登录——首次使用时跑一次就行。
    之后 token 被缓存，Web 后端直接用。"""
    import sys
    r = requests.post(f"{BASE}/login/", json={
        "username": USERNAME, "password": PASSWORD,
    })
    data = r.json()
    token = data["token"]

    if data.get("otp_challenge_sent"):
        print("请查看邮箱，输入 OTP 验证码:")
        code = sys.stdin.readline().strip()
        requests.post(f"{BASE}/verify/",
                      headers={"Authorization": f"Token {token}"},
                      json={"otp_token": code})

    save_token(token)
    print(f"Token 已缓存到 {TOKEN_FILE}")
    return token


def _token():
    """获取 token：先查缓存，没有则报错（不交互）"""
    token = get_cached_token()
    if not token:
        raise RuntimeError(
            "未登录。请先在终端运行一次:\n"
            "  python -c 'from sender.opencap_client import login_interactive; login_interactive()'"
        )
    return token


def process_session(session_id, on_api_session_created=None, video_path=None):
    """
    上传视频、等待 OpenCap 处理、下载结果。
    session_id 对应 data/sessions/{session_id}/
    视频在 data/videos/{session_id}/input.mp4
    """
    token = _token()
    headers = {"Authorization": f"Token {token}"}

    video_path = Path(video_path) if video_path else VIDEOS / session_id / "input.mp4"
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise FileNotFoundError(f"Video file not found or empty: {video_path}")
    result_dir = SESSIONS / session_id
    result_dir.mkdir(parents=True, exist_ok=True)

    # 1. 创建 Session
    r = requests.get(f"{BASE}/sessions/new/", headers=headers)
    api_session_id = r.json()[0]["id"]
    if on_api_session_created:
        on_api_session_created(api_session_id)

    # 单目模式 + metadata
    requests.get(f"{BASE}/sessions/{api_session_id}/set_metadata/",
                 headers=headers, params={"isMono": "true"})

    # 创建 Subject
    r = requests.post(f"{BASE}/subjects/", headers=headers,
                      json=_subject_payload())
    subject_id = r.json()["id"]

    requests.get(f"{BASE}/sessions/{api_session_id}/set_subject/",
                 headers=headers, params={"subject_id": subject_id})

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
                     "settings_augmenter_model": "v0.2",
                     "settings_data_sharing": "true",
                 })

    requests.patch(f"{BASE}/sessions/{api_session_id}/",
                   headers=headers, json={
                       "meta": {
                           "iphoneModel": {"camera1": "iPhone14,5"},
                           "settings": {
                               "framerate": "60",
                               "posemodel": "OPENPOSE",
                               "openSimModel": "LaiArnold",
                               "augmenter_model": "v0.2",
                               "datasharing": "true",
                           },
                           "subject": {
                               "id": str(subject_id),
                               "mass": SUBJECT_MASS,
                               "height": SUBJECT_HEIGHT,
                               "sex": SUBJECT_SEX,
                           },
                       },
                   })

    # 2. 录制
    r = requests.get(f"{BASE}/sessions/{api_session_id}/record/",
                     headers=headers, params={"name": "test"})
    trial_id = r.json()["id"]

    # 预建 Video
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
    requests.get(f"{BASE}/sessions/{api_session_id}/stop/", headers=headers)

    # 3. 上传视频
    with open(video_path, "rb") as f:
        requests.patch(f"{BASE}/videos/{video_id}/",
                       headers=headers, files={"video": f})

    # 4. 等待处理
    while True:
        r = requests.get(f"{BASE}/sessions/{api_session_id}/status/",
                         headers=headers)
        status = r.json()["status"]
        trial_url = r.json().get("trial")

        if status == "ready" and trial_url:
            tid = trial_url.rstrip("/").split("/")[-1]
            tr = requests.get(f"{BASE}/trials/{tid}/", headers=headers)
            t_status = tr.json().get("status")

            if t_status == "done":
                break
            if t_status == "error":
                error = tr.json().get("meta", {}).get("error_msg", "")
                raise RuntimeError(f"OpenCap 处理失败: {error}")

        time.sleep(5)

    # 5. 下载
    r = requests.get(f"{BASE}/sessions/{api_session_id}/async-download/",
                     headers=headers)
    task_id = r.json()["task_id"]

    while True:
        r = requests.get(f"{BASE}/logs/{task_id}/on-ready/", headers=headers)
        if r.text.strip():
            data = r.json()
            url = data.get("url") or data.get("media")
            if url:
                break
        time.sleep(5)

    zip_data = requests.get(url).content
    zip_file = result_dir / "result.zip"
    zip_file.write_bytes(zip_data)

    with zipfile.ZipFile(zip_file, "r") as zf:
        zf.extractall(result_dir)
    zip_file.unlink()

    return api_session_id
