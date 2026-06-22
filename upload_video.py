#!/usr/bin/env python3
"""
本地视频 → 公网 URL 工具
支持多种上传方式，方便 OpenCap API 使用
"""
import requests
import sys
import os

VIDEO_PATH = "your_video.mp4"  # 改成你的视频文件路径


def upload_transfer_sh(filepath):
    """方式1: transfer.sh (最快，14天有效，最大10GB)"""
    print(f"上传到 transfer.sh: {filepath}")
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        resp = requests.put(f"https://transfer.sh/{filename}", data=f)
    if resp.status_code == 200:
        url = resp.text.strip()
        print(f"✅ URL: {url}")
        return url
    print(f"❌ 失败: {resp.status_code}")
    return None


def upload_fileio(filepath):
    """方式2: file.io (一次性下载后自动删除)"""
    print(f"上传到 file.io: {filepath}")
    with open(filepath, "rb") as f:
        resp = requests.post("https://file.io", files={"file": f})
    if resp.status_code == 200:
        data = resp.json()
        url = data.get("link")
        print(f"✅ URL: {url}")
        print(f"   ⚠️ 下载一次后文件自动删除!")
        return url
    print(f"❌ 失败: {resp.text}")
    return None


def upload_gofile(filepath):
    """方式3: gofile.io (免费，不限大小)"""
    print(f"上传到 gofile.io: {filepath}")
    # 获取服务器
    resp = requests.get("https://api.gofile.io/servers")
    server = resp.json()["data"]["servers"][0]["name"]

    # 上传
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"https://{server}.gofile.io/uploadFile",
            files={"file": f}
        )
    if resp.status_code == 200:
        data = resp.json()
        url = data["data"]["downloadPage"]
        # gofile 的直接下载链接
        file_id = data["data"]["fileId"]
        direct_url = f"https://{server}.gofile.io/download/{file_id}/{os.path.basename(filepath)}"
        print(f"✅ 下载页: {url}")
        print(f"✅ 直链: {direct_url}")
        return direct_url
    print(f"❌ 失败: {resp.text}")
    return None


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else VIDEO_PATH

    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        print(f"用法: python upload_video.py /path/to/video.mp4")
        sys.exit(1)

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"文件: {filepath} ({size_mb:.1f} MB)")
    print()

    # 依次尝试
    url = upload_transfer_sh(filepath)
    if not url:
        url = upload_gofile(filepath)
    if not url:
        url = upload_fileio(filepath)

    if url:
        print(f"\n{'='*60}")
        print(f"复制这个 URL 到 opencap_monocular_demo.py 的 VIDEO_URL:")
        print(f"  VIDEO_URL = \"{url}\"")
        print(f"{'='*60}")
    else:
        print("\n❌ 所有方式都失败了，手动上传到云盘后获取直链")


if __name__ == "__main__":
    main()
