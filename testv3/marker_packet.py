# marker_packet.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


Vec3 = Tuple[float, float, float]


@dataclass
class MarkerFramePacket:
    time: float
    frame_index: int
    markers: Dict[str, Vec3]
    confidence: Optional[Dict[str, float]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "MarkerFramePacket":
        if data.get("type") != "marker_frame":
            raise ValueError(f"Unsupported packet type: {data.get('type')}")

        markers = {
            name: (float(v[0]), float(v[1]), float(v[2]))
            for name, v in data["markers"].items()
        }

        return cls(
            time=float(data["time"]),
            frame_index=int(data["frame_index"]),
            markers=markers,
            confidence=data.get("confidence"),
        )

    def to_dict(self) -> dict:
        return {
            "type": "marker_frame",
            "time": self.time,
            "frame_index": self.frame_index,
            "markers": {
                name: [float(x), float(y), float(z)]
                for name, (x, y, z) in self.markers.items()
            },
            "confidence": self.confidence,
        }
