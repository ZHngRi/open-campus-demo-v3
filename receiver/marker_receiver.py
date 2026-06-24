"""TCP receiver — 接收一行 JSON，解析为 SessionPacket。"""

import json
import socket

from session_packet import SessionPacket


class SessionReceiver:
    """TCP 服务端：accept 一个连接，逐行读取 JSON 并解析为 SessionPacket。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5005):
        self.host = host
        self.port = port
        self._server_socket = None
        self._client_socket = None
        self._client_file = None

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)

        print(f"[receiver] listening on {self.host}:{self.port}")

        self._client_socket, address = self._server_socket.accept()
        self._client_file = self._client_socket.makefile("r", encoding="utf-8")

        print(f"[receiver] connected from {address}")

    def receive(self) -> SessionPacket:
        """读取一行 JSON，返回 SessionPacket。"""
        if self._client_file is None:
            raise RuntimeError("Not started. Call start() first.")

        line = self._client_file.readline()
        if not line:
            raise EOFError("Sender closed connection.")

        return SessionPacket.from_dict(json.loads(line))

    def close(self):
        if self._client_file:
            self._client_file.close()
        if self._client_socket:
            self._client_socket.close()
        if self._server_socket:
            self._server_socket.close()
