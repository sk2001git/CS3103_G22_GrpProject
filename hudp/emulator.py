from __future__ import annotations
from typing import Tuple, Callable
import random
import time

class UDPEngineEmulator:
    """Software emulator for loss/delay/jitter.
    Use by passing `emulator_send=UDPEngineEmulator(sock.sendto).sendto` to GameNetAPI.
    """
    def __init__(self, sock_send: Callable[[bytes, Tuple[str, int]], None], loss=0.0, delay_ms=0, jitter_ms=0):
        """Initialize emulator with given parameters.
        Args:
            sock_send: underlying socket sendto function to call after emulation.
            loss: packet loss rate [0.0..1.0].
            delay_ms: base delay in milliseconds.
            jitter_ms: max jitter in milliseconds (+/-).
        """
        self.sock_send = sock_send
        self.loss = loss
        self.delay_ms = delay_ms
        self.jitter_ms = jitter_ms

    def get_delay_ms(self) -> float:
        """Get current delay in milliseconds, including jitter."""
        delay_ms = self.delay_ms
        if self.jitter_ms > 0:
            delay_ms += random.uniform(-self.jitter_ms, self.jitter_ms)
        return self.delay_ms

    def drop_packet(self) -> bool:
        """Decide whether to drop the packet based on loss rate."""
        return random.random() < self.loss

    def send_packet(self, sock, data: bytes, addr: Tuple[str, int]) -> None:
        """Apply loss/delay/jitter, then call underlying sock_send."""
        if self.drop_packet(): # Simulate packet loss
            return

        delay_ms = self.delay_ms
        if self.jitter_ms > 0:
            delay_ms += random.randint(-self.jitter_ms, self.jitter_ms)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        sock.send_to(data, addr)
