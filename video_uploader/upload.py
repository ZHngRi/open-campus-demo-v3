#!/usr/bin/env python3
"""本地视频 → 公网直链，依次尝试可用平台"""

import requests
import sys
import os
from pathlib import Path

VIDEO_DIR = Path(__file__).parent / "videos"


def find_video():
    for f in sorted(VIDEO_DIR.glob("*")):
        if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
            return f
    return None


def upload_catbox(filepath):
    """catbox.moe — 永久有效, 200MB 限制"""
    size_mb = os.path.getsize(filepath) / 1024 / 1024
    if size_mb > 200:
        print("  [catbox.moe] 跳过: {:.1f}MB > 200MB 限制".format(size_mb))
        return None

    print("  [catbox.moe] 上传中 ({:.1f} MB)...".format(size_mb))
    with open(filepath, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=600,
        )
    if resp.status_code == 200 and resp.text.startswith("https://"):
        url = resp.text.strip()
        print("  [catbox.moe] 成功! 永久有效")
        return url
    print("  [catbox.moe] 失败: {}".format(resp.text[:200]))
    return None


def upload_tempsh(filepath):
    """temp.sh — 3天有效, 4GB 限制"""
    size_mb = os.path.getsize(filepath) / 1024 / 1024
    print("  [temp.sh] 上传中 ({:.1f} MB)...".format(size_mb))
    with open(filepath, "rb") as f:
        resp = requests.post(
            "https://temp.sh/upload",
            files={"file": f},
            timeout=600,
        )
    if resp.status_code in (200, 201) and resp.text.strip().startswith("https://"):
        url = resp.text.strip()
        print("  [temp.sh] 成功! 3天内有效")
        return url
    print("  [temp.sh] 失败: {}".format(resp.text[:200]))
    return None


def main():
    if len(sys.argv) > 1:
        filepath = Path(sys.argv[1])
        if not filepath.is_absolute():
            filepath = VIDEO_DIR / sys.argv[1]
    else:
        filepath = find_video()

    if not filepath or not filepath.exists():
        print("❌ 未找到视频文件")
        print("  用法: python upload.py [文件名]")
        print("  视频放于: {}".format(VIDEO_DIR))
        sys.exit(1)

    size_mb = filepath.stat().st_size / 1024 / 1024
    print("📹 {} ({:.1f} MB)".format(filepath.name, size_mb))
    print()

    for uploader in (upload_catbox, upload_tempsh):
        url = uploader(str(filepath))
        if url:
            print()
            print("=" * 60)
            print("复制到 opencap_monocular_demo.py 的 VIDEO_URL:")
            print("  VIDEO_URL = \"{}\"".format(url))
            print("=" * 60)
            return

    print("\n❌ 所有平台上传失败")


if __name__ == "__main__":
    main()
