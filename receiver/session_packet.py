"""session_packet.py — 会话包。

示例 JSON:
    {"type": "session", "trc": "path/to/markers.trc", "mot": "path/to/motion.mot"}

IK 线程读 TRC 做 Inverse Kinematics，SO 线程读 MOT 做 Static Optimization。
两者并行、互不干扰。
"""

import json
from dataclasses import dataclass


@dataclass
class SessionPacket:
    """一次会话：trc + mot 文件路径。"""
    trc: str
    mot: str

    # ---- 反序列化 ----

    @classmethod
    def from_json(cls, json_str: str) -> "SessionPacket":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_dict(cls, data: dict) -> "SessionPacket":
        if data.get("type") != "session":
            raise ValueError(f"Expected type='session', got: {data.get('type')}")
        return cls(trc=data["trc"], mot=data["mot"])

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        return {"type": "session", "trc": self.trc, "mot": self.mot}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
