# marker_receiver.py

import json
import socket
from marker_packet import MarkerFramePacket


class MarkerFrameReceiver:
    def __init__(self, host: str = "127.0.0.1", port: int = 5005):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.client_file = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)

        print(f"[receiver] listening on {self.host}:{self.port}")

        self.client_socket, address = self.server_socket.accept()
        self.client_file = self.client_socket.makefile("r", encoding="utf-8")

        print(f"[receiver] connected from {address}")

    def receive_next(self) -> MarkerFramePacket:
        if self.client_file is None:
            raise RuntimeError("Receiver is not started. Call start() first.")

        line = self.client_file.readline()

        if not line:
            raise EOFError("Sender closed connection.")

        data = json.loads(line)
        packet = MarkerFramePacket.from_dict(data)

        return packet

    def close(self):
        if self.client_file:
            self.client_file.close()

        if self.client_socket:
            self.client_socket.close()

        if self.server_socket:
            self.server_socket.close()
