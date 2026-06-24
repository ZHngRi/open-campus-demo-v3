"""二进制文件发送：TRC → :5005，MOT → :5006。"""

import socket
from pathlib import Path


def send_file(host, port, path):
    """发送单个文件：4B 文件名长度 + 文件名 + 8B 文件大小 + 文件内容"""
    path = Path(path)
    data = path.read_bytes()
    name = path.name.encode("utf-8")

    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(len(name).to_bytes(4, "big"))
        s.sendall(name)
        s.sendall(len(data).to_bytes(8, "big"))
        s.sendall(data)


def send_session(trc_path, mot_path, host, trc_port=5005, mot_port=5006):
    sent = []
    if trc_path:
        send_file(host, trc_port, trc_path)
        sent.append("trc")
    if mot_path:
        send_file(host, mot_port, mot_path)
        sent.append("mot")
    return sent
