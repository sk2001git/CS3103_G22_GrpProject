from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


# Constants for channel types
RELIABLE = 0
UNRELIABLE = 1


@dataclass
class Header:
    """Protocol header fields.
    | ChannelType (1 B) | SeqNo (2 B) | Timestamp (4 B) | => 7 bytes
    """
    channel_type: int
    seq: int
    ts_ms: int




def now_ms() -> int:
    """Return current time in milliseconds (uint32 wrap is fine)."""
    raise NotImplementedError("now_ms: implement using time.time()*1000 & 0xFFFFFFFF")




def pack_packet(header: Header, payload: bytes) -> bytes:
    """Serialize header + payload to bytes using network byte order (big-endian)."""
    raise NotImplementedError("pack_packet: use struct.pack with format !BHI + payload")




def unpack_packet(data: bytes) -> Tuple[Header, bytes]:
    """Parse bytes into (Header, payload). Validate minimum length (>= 7)."""
    raise NotImplementedError("unpack_packet: use struct.unpack and slice payload")