from __future__ import annotations
from typing import Optional, Tuple, Callable
import socket
import threading
import time
from collections import deque
from .packet import (RELIABLE, UNRELIABLE, ACK, HEADER_SIZE, ACK_SIZE,
                     pack_header, unpack_header, pack_ack, unpack_ack, now_ms)
from .emulator import UDPEngineEmulator
from .reliable import SRSender, SRReceiver


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
        bind_addr: Tuple[str, int] = ('0.0.0.0', 0),
        # Default skip threshold to reflect ~1.5RTT links
        skip_threshold_ms: int = 300,
        on_drop: Optional[Callable[[int], None]] = None,
        metrics=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind_addr)
        self.peer_addr = None
        
        self._send_seq_reliable = 0
        self._send_seq_unreliable = 0

        self._unacked_packets = {}  # {seq: (data, send_time, retries)}
        self._recv_buffer = {}  # For out-of-order reliable packets {seq: (header, payload)}
        self._next_expected_seq = 0

        self.recv_queue = deque()
        self.running = False
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)

        self.emulator = None
        self.SKIP_THRESHOLD_MS = skip_threshold_ms
        self.on_drop = on_drop
        self.metrics = metrics

        # Initialize metrics with a dummy if none provided
        if self.metrics is None:
        # Create a dummy metrics object that has the required methods but does nothing
            class DummyMetrics:
                def on_sent(self, *args, **kwargs): pass
                def on_recv(self, *args, **kwargs): pass
                def on_ack(self, *args, **kwargs): pass
            self.metrics = DummyMetrics()

        self._rx_ts = {}  # seq -> header.timestamp_ms for reliable delivery
        self.sr_sender = SRSender(
            window_size=32,
            rto_ms=200,
            max_retries=10,
            on_send_raw=self._sr_on_send_raw,  # wrap + send reliable
            on_drop=self._sr_on_drop,
            on_rtt=self._sr_on_rtt,
            clock_ms=lambda: int(time.time() * 1000),
        )
        self.sr_receiver = SRReceiver(
            deliver_in_order=self._sr_deliver_in_order,
            send_ack=self._sr_send_ack,        # emit ACKs
            skip_threshold_ms=skip_threshold_ms,
            clock_ms=lambda: int(time.time() * 1000),
            window_size=32,
        )

    def start(self):
        self.running = True
        self.sr_sender.start()               # start SR timers
        self._recv_thread.start()

    def stop(self):
        self.running = False
        self.sr_sender.stop()
        self.sock.close()
        self._recv_thread.join(timeout=1.0)

    def set_peer(self, addr):
        self.peer_addr = addr

    def attach_emulator(self, emulator: UDPEngineEmulator):
        self.emulator = emulator

    def send(self, payload: bytes, reliable: bool):
        if not self.peer_addr:
            raise ConnectionError("No peer address, Call set_peer() first.")

        if reliable:
            # Let SRSender handle all sequence numbering for reliable packets
            seq = self.sr_sender.send(payload)
            if seq is None:
                # Window is full, packet was not sent
                return None
            
            # Calculate actual bytes including header
            total_bytes = HEADER_SIZE + len(payload)
            if self.metrics:  # ADD THIS CHECK
                self.metrics.on_sent(RELIABLE, seq, total_bytes)
            return seq
        else:
            # UNRELIABLE uses its own sequence numbers
            seq_num = self._send_seq_unreliable
            self._send_seq_unreliable += 1
            header = pack_header(UNRELIABLE, seq_num)
            total_bytes = len(header) + len(payload)
            if self.metrics:  # ADD THIS CHECK
                self.metrics.on_sent(UNRELIABLE, seq_num, total_bytes)
            self._send_internal(header + payload)
            return seq_num

        
    def recv(self, block=True, timeout=None):
        start_time = time.time()
        while True:
            if self.recv_queue:
                return self.recv_queue.popleft()
            if not block:
                return None
            if timeout is not None and (time.time() - start_time) > timeout:
                return None
            if not self.running:
                return None
            time.sleep(0.001)


    def _send_internal(self, data: bytes):
        if self.emulator:
            self.emulator.send_emulated(self.sock, self.peer_addr, data)
        else:
            self.sock.sendto(data, self.peer_addr)
    
    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                if not self.peer_addr:
                    self.peer_addr = addr
                self._internal_process_packet(data)
            except (socket.error, OSError):
                if self.running:
                    # Only print error if we weren't expecting to stop
                    print("Socket error in recv_loop, shutting down.")
                    pass
                break

    def _internal_process_packet(self, data: bytes):
        """Processes a raw packet as if it were just received from the socket."""
        # Check for ACK packet first (most common check)
        if len(data) == ACK_SIZE and data[0] == ACK:
            self._handle_ack(data)
        elif len(data) >= HEADER_SIZE:
            header = unpack_header(data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:]

            if header.channel_type == UNRELIABLE:
                self.recv_queue.append((UNRELIABLE, header.seq_num, header.timestamp_ms, payload))
            elif header.channel_type == RELIABLE:
                # Store timestamp for later delivery
                self._rx_ts[header.seq_num] = header.timestamp_ms
                # Hand off to the SRReceiver for buffering and ACK management
                self.sr_receiver.on_data(header.seq_num, payload)

    def _handle_ack(self, data: bytes):
        """Handles an incoming ACK packet."""
        ack_seq, recv_window = unpack_ack(data) 
        was_new_ack = self.sr_sender.ack(ack_seq, recv_window)
        
        try:
            if self.metrics and was_new_ack:  # Only record new ACKs, not duplicates
                self.metrics.on_ack(RELIABLE, ack_seq, ACK_SIZE)
        except Exception:
            # Metrics updates must not crash packet processing
            pass

    def _sr_on_send_raw(self, seq: int, payload: bytes) -> None:
        """Wrap reliable payload with your header and send."""
        if not self.peer_addr:
            return
        hdr = pack_header(RELIABLE, seq)
        total_bytes = len(hdr) + len(payload)
        if self.metrics:  # ADD THIS CHECK
            self.metrics.on_sent(RELIABLE, seq, total_bytes)
        self._send_internal(hdr + payload)

    def _sr_send_ack(self, ack_seq: int, recv_window: int) -> None:
        """Emit per-packet ACK (unchanged wire format)."""
        if not self.peer_addr:
            return
        ack_packet = pack_ack(ack_seq, recv_window) 
        self._send_internal(ack_packet)

    def _sr_deliver_in_order(self, seq: int, payload: bytes) -> None:
        """Deliver in-order to app; include the original header timestamp if we saw it."""
        ts = self._rx_ts.pop(seq, now_ms())
        self.recv_queue.append((RELIABLE, seq, ts, payload))

    def _sr_on_drop(self, seq: int) -> None:
        print(f"[RELIABLE] drop seq={seq} after max retries")
        if self.on_drop:
            self.on_drop(seq)



    def _sr_on_rtt(self, seq: int, rtt_ms: int) -> None:
        # Hook for metrics if desired
        pass
