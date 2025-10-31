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
    def __init__(self, bind_addr=('0.0.0.0', 0), skip_threshold_ms=200):
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
        self._retransmission_thread = threading.Thread(target=self._retransmission_loop, daemon=True)

        self.emulator = None
        self.RETRANSMIT_TIMEOUT_MS = 100
        self.SKIP_THRESHOLD_MS = skip_threshold_ms
        
        self._rx_ts = {}  # seq -> header.timestamp_ms for reliable delivery
        self.sr_sender = SRSender(
            window_size=64,
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
            window_size=64,
        )

    def start(self):
        self.running = True
        self.sr_sender.start()               # start SR timers
        self._recv_thread.start()
        self._retransmission_thread.start()

    def stop(self):
        self.running = False
        self.sock.close()
        self.sr_receiver.stop()
        self.sr_sender.stop()
        self._recv_thread.join()
        self._retransmission_thread.join()

    def set_peer(self, addr):
        self.peer_addr = addr

    def attach_emulator(self, emulator: UDPEngineEmulator):
        self.emulator = emulator

    def send(self, payload: bytes, reliable: bool):
        if not self.peer_addr:
            raise ConnectionError("No peer address, Call set_peer() first.")

        channel = RELIABLE if reliable else UNRELIABLE

        if reliable:
            seq_num = self._send_seq_reliable
            self._send_seq_reliable += 1
        else:
            seq_num = self._send_seq_unreliable
            self._send_seq_unreliable += 1

        header = pack_header(channel, seq_num)
        data = header + payload

        if reliable:
            self._unacked_packets[seq_num] = (data, now_ms(), 0)

        self._send_internal(data)
        return len(data)

    def recv(self, block=True):
        if not block:
            return self.recv_queue.popleft() if self.recv_queue else None

        while not self.recv_queue and self.running:
            time.sleep(0.001) # to prevent busy-waiting

        return self.recv_queue.popleft() if self.running else None

    def _send_internal(self, data: bytes):
        if self.emulator:
            self.emulator.send_emulated(self.sock, self.peer_addr, data)
        else:
            self.sock.sendto(data, self.peer_addr)
            

    def _sr_on_send_raw(self, seq: int, payload: bytes) -> None:
        """Wrap reliable payload with your header and send."""
        if not self.peer_addr:
            return
        hdr = pack_header(RELIABLE, seq)
        self._send_internal(hdr + payload)

    def _sr_send_ack(self, ack_seq: int) -> None:
        """Emit per-packet ACK (unchanged wire format)."""
        if not self.peer_addr:
            return
        ack_packet = pack_ack(ack_seq)
        self._send_internal(ack_packet)

    def _sr_deliver_in_order(self, seq: int, payload: bytes) -> None:
        """Deliver in-order to app; include the original header timestamp if we saw it."""
        ts = self._rx_ts.pop(seq, now_ms())
        self.recv_queue.append((RELIABLE, seq, ts, payload))
        
    def _sr_on_drop(self, seq: int) -> None:
        # Optional: surface to app/log
        # print(f"[RELIABLE] drop seq={seq} after max retries")
        pass

    def _sr_on_rtt(self, seq: int, rtt_ms: int) -> None:
        # Hook for metrics if desired
        pass
    

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                if not self.peer_addr:
                    self.peer_addr = addr

                if len(data) == ACK_SIZE and data[0] == ACK:
                    self._handle_ack(data)
                elif len(data) >= HEADER_SIZE:
                    header = unpack_header(data[:HEADER_SIZE])
                    payload = data[HEADER_SIZE:]

                    if header.channel_type == UNRELIABLE:
                        self.recv_queue.append((UNRELIABLE, header.seq_num, header.timestamp_ms, payload))
                    elif header.channel_type == RELIABLE:
                        self._rx_ts[header.seq_num] = header.timestamp_ms
                        # Hand to SRReceiver: it will ACK immediately and deliver in-order via callback
                        self.sr_receiver.on_data(header.seq_num, payload)
                        
            except (socket.error, OSError):
                break

    def _handle_ack(self, data: bytes):
        ack_seq = unpack_ack(data)
        self.sr_sender.ack(ack_seq)

    def _retransmission_loop(self):
        """Minimal-change retention of your thread: SR manages timers, so we idle here."""
        while self.running:
            # No manual retransmit/skip needed; SR handles both.
            time.sleep(0.01)

   