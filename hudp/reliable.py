from __future__ import annotations
from typing import Callable, Optional, Dict


Clock = Callable[[], int]


class SRSender:
    """Selective Repeat sender with per-packet timers.
    Required behaviors:
    - Window control (base/next_seq, modulo 16 bits)
    - Per-packet RTO; retransmit on timeout
    - Track retries; drop after max_retries
    - Callbacks:
    * on_send_raw(seq:int, bytes)
    * on_drop(seq:int)
    * on_rtt(seq:int, rtt_ms:int) [optional]
    """


def __init__(
self,
window_size: int = 64,
rto_ms: int = 120,
max_retries: int = 10,
on_send_raw: Optional[Callable[[int, bytes], None]] = None,
on_drop: Optional[Callable[[int], None]] = None,
on_rtt: Optional[Callable[[int, int], None]] = None,
clock_ms: Clock = lambda: 0,
):
    raise NotImplementedError("SRSender.__init__: initialize state, buffers, locks, thread")


def start(self) -> None:
    """Start timer thread for retransmissions."""
    raise NotImplementedError


def stop(self) -> None:
    """Stop timer thread and clean up."""
    raise NotImplementedError


def send(self, serialized_payload: bytes) -> Optional[int]:
    """Queue a reliable packet. Assign seq and trigger first send.
    Return seq or None if window full.
    """
    raise NotImplementedError


def ack(self, seq: int) -> None:
    """Handle received ACK for seq. Slide window, compute RTT if possible."""
    raise NotImplementedError


def _timer_loop(self) -> None:
    """Background: iterate unacked packets, (re)send on timeout."""
    raise NotImplementedError

class SRReceiver:
    """Selective Repeat receiver with buffering + reordering + skip after t.
    Required behaviors:
    - Maintain expected seq and a buffer for out-of-order packets
    - On data: ACK immediately; if seq==expected, deliver and advance
    - If hole at expected persists for >= skip_threshold_ms, skip it and continue
    - Callback deliver_in_order(seq:int, payload:bytes)
    - Callback send_ack(seq:int)
    """


def __init__(
self,
deliver_in_order: Callable[[int, bytes], None],
send_ack: Callable[[int], None],
skip_threshold_ms: int = 200,
clock_ms: Clock = lambda: 0,
window_size: int = 64,
):
    raise NotImplementedError("SRReceiver.__init__: set state for expected, buffers, timers")


def on_data(self, seq: int, payload: bytes) -> None:
    """Process incoming data packet on reliable channel."""
    raise NotImplementedError