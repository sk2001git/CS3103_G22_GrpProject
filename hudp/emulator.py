from __future__ import annotations
from typing import Tuple, Callable
import random
import time
import socket

class UDPEngineEmulator:
    """Software emulator for loss/delay/jitter.
    GameNetAPI expects: emulator.send_emulated(sock, addr, data)
    """

    def __init__(self, loss: float = 0.0, delay_ms: int = 0, jitter_ms: int = 0):
        """
        Args:
            loss: packet loss rate [0.0..1.0]
            delay_ms: base delay in milliseconds
            jitter_ms: max jitter in milliseconds (+/-)
        """
        self.loss = float(loss)
        self.delay_ms = int(delay_ms)
        self.jitter_ms = int(jitter_ms)

    def get_delay_ms(self) -> float:
        """Return current delay including jitter."""
        delay_ms = float(self.delay_ms)
        if self.jitter_ms > 0:
            delay_ms += random.uniform(-self.jitter_ms, self.jitter_ms)
        return max(0.0, delay_ms)

    def drop_packet(self) -> bool:
        """Decide whether to drop the packet based on loss rate."""
        return random.random() < self.loss

    def send_emulated(self, sock: socket.socket, addr: Tuple[str, int], data: bytes) -> None:
        """Apply loss/delay/jitter, then send via the provided socket."""
        if self.drop_packet():
            return
        d = self.get_delay_ms()
        if d > 0:
            time.sleep(d / 1000.0)
        sock.sendto(data, addr)