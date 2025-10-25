from __future__ import annotations
from typing import Tuple, Callable


class UDPEngineEmulator:
    """Software emulator for loss/delay/jitter.
    Use by passing `emulator_send=UDPEngineEmulator(sock.sendto).sendto` to GameNetAPI.
    """


def __init__(self, sock_send: Callable[[bytes, Tuple[str, int]], None], loss=0.0, delay_ms=0, jitter_ms=0):
    raise NotImplementedError("UDPEngineEmulator.__init__: store params and sender callable")


def sendto(self, data: bytes, addr: Tuple[str, int]) -> None:
    """Apply loss/delay/jitter, then call underlying sock_send."""
    raise NotImplementedError