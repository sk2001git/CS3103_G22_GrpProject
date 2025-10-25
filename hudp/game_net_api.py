from __future__ import annotations
from typing import Optional, Tuple, Callable


# Import after you implement packet/reliable
# from .packet import Header, pack_packet, unpack_packet, now_ms, RELIABLE, UNRELIABLE
# from .reliable import SRSender, SRReceiver


class GameNetAPI:
    """Public API surface for H-UDP over a single UDP socket.


    Must support:
    - send(payload: bytes, reliable: bool) -> Optional[int]
    - recv(block=False, timeout=None) -> Tuple[channel_type, seq_or_none, header_ts_ms, payload]
    - Demultiplex by ChannelType in header
    - For reliable: integrate SRSender/SRReceiver, ACK wiring
    - Expose header timestamp to app for one-way latency measurements
    """


def __init__(
self,
bind_addr: Optional[Tuple[str, int]] = None,
peer_addr: Optional[Tuple[str, int]] = None,
skip_threshold_ms: int = 200,
rto_ms: int = 120,
window_size: int = 64,
emulator_send: Optional[Callable[[bytes, Tuple[str, int]], None]] = None,
on_rtt: Optional[Callable[[int, int], None]] = None,
):
    raise NotImplementedError("GameNetAPI.__init__: create UDP socket, queues, SR objects, threads")


def start(self) -> None:
    """Start RX thread(s) and SR timers."""
    raise NotImplementedError


def stop(self) -> None:
    """Stop threads and close socket."""
    raise NotImplementedError


def set_peer(self, addr: Tuple[str, int]) -> None:
    """Set remote peer (IP, port)."""
    raise NotImplementedError


def send(self, payload: bytes, reliable: bool = True) -> Optional[int]:
    """Send a payload. Reliable returns seq; unreliable returns None."""
    raise NotImplementedError


def recv(self, block: bool = False, timeout: Optional[float] = None):
    """Return next delivered msg: (channel_type, seq_or_none, header_ts_ms, payload)."""
    raise NotImplementedError


# Internal helpers (suggested): _rx_loop, _send_bytes, _send_ack, etc.