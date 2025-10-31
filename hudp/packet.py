from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, NamedTuple
import time
import struct


# Constants for channel types
RELIABLE = 0
UNRELIABLE = 1
ACK = 2

HEADER_FORMAT = "!BHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# ACK Packet
ACK_FORMAT = "!BH"
ACK_SIZE = struct.calcsize(ACK_FORMAT)
@dataclass
class PacketHeader:
    """Protocol header fields.
    | ChannelType (1 B) | SeqNo (2 B) | Timestamp (4 B) | => 7 bytes
    """
    channel_type: int
    seq_num: int
    timestamp_ms: int

def now_ms() -> int:
    """Return current time in milliseconds (uint32 wrap is fine)."""
    return int(time.time() * 1000) & 0xFFFFFFFF

def pack_header(channel: int, seq_num: int) -> bytes:
    """Packs header for data packet."""
    return struct.pack(HEADER_FORMAT, channel, seq_num, now_ms())

def unpack_header(data: bytes) -> PacketHeader:
    """Unpacks header from received data packet."""
    channel, seq_num, timestamp = struct.unpack(HEADER_FORMAT, data)
    return PacketHeader(channel, seq_num, timestamp)

def pack_ack(seq_num: int) -> bytes:
    """Packs ACK packet."""
    return struct.pack(ACK_FORMAT, ACK, seq_num)

def unpack_ack(data: bytes) -> int:
    """Unpacks ACK packet to get seq num."""
    _, seq_num = struct.unpack(ACK_FORMAT, data)
    return seq_num