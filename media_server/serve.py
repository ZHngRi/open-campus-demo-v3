#!/usr/bin/env python3
"""
本地视频 HTTP 服务器
-------------------
把 videos/ 目录下的文件通过 HTTP 暴露出去，
局域网内其他设备（Mac）可以直接用 URL 访问。

用法:
    python serve.py              # 默认端口 8765
    python serve.py 9000         # 指定端口
    python serve.py --host 0.0.0.0 --port 8765

启动后访问:
    http://100.111.140.103:8765/single_leg_hop_turn_around_walk_scaled.mp4
"""
import http.server
import socket
import sys
import os
from pathlib import Path


class VideoHandler(http.server.SimpleHTTPRequestHandler):
    """支持断点续传（Range 请求）的 HTTP 文件服务器"""

    def __init__(self, *args, **kwargs):
        video_dir = Path(__file__).parent / "videos"
        super().__init__(*args, directory=str(video_dir), **kwargs)

    def log_message(self, format, *args):
        """简化日志输出"""
        print("  {} - {}".format(self.address_string(), format % args))


def get_local_ips():
    """获取本机所有 IP"""
    ips = []
    try:
        hostname = socket.gethostname()
        ips.append(("hostname", hostname))
    except Exception:
        pass

    ips.append(("localhost", "127.0.0.1"))

    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for addr in addrs.get(netifaces.AF_INET, []):
                ip = addr.get("addr")
                if ip and ip != "127.0.0.1":
                    ips.append((iface, ip))
    except ImportError:
        # fallback: 用 socket 获取
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(("primary", s.getsockname()[0]))
            s.close()
        except Exception:
            pass

    return ips


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8765
    video_dir = Path(__file__).parent / "videos"

    if not video_dir.exists():
        print("ERROR: videos/ 目录不存在")
        sys.exit(1)

    videos = list(video_dir.glob("*"))
    if not videos:
        print("WARNING: videos/ 目录为空，请放入视频文件")
    else:
        print("视频文件:")
        for v in videos:
            print("  - {} ({:.1f} MB)".format(v.name, v.stat().st_size / 1024 / 1024))

    print()
    print("=" * 65)
    print("  本地视频服务器已启动")
    print("=" * 65)
    print()
    print("  本机访问:")
    print("    http://localhost:{}/".format(port))
    print()
    print("  局域网 / Tailscale 访问:")
    for iface, ip in get_local_ips():
        if ip != "127.0.0.1":
            print("    http://{}:{}/ ({}):".format(ip, port, iface))
    print()
    if videos:
        print("  直接视频链接:")
        for v in videos:
            print("    http://100.111.140.103:{}/{}".format(port, v.name))
    print()
    print("  按 Ctrl+C 停止服务器")
    print("=" * 65)
    print()

    server = http.server.HTTPServer(
        ("0.0.0.0", port),
        VideoHandler
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
