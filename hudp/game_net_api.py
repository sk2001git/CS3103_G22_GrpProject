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

    def start(self):
        self.running = True
        self._recv_thread.start()
        self._retransmission_thread.start()

    def stop(self):
        self.running = False
        self.sock.close()
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
                        self._handle_reliable(header, payload)
            except (socket.error, OSError):
                break

    def _handle_ack(self, data: bytes):
        ack_seq = unpack_ack(data)
        if ack_seq in self._unacked_packets:
            # print(f"DEBUG: Received ACK for {ack_seq}")
            del self._unacked_packets[ack_seq]

    def _handle_reliable(self, header, payload):
        ack_packet = pack_ack(header.seq_num)
        self._send_internal(ack_packet)

        if header.seq_num == self._next_expected_seq:
            self.recv_queue.append((RELIABLE, header.seq_num, header.timestamp, payload))
            self._next_expected_seq += 1
            self._process_recv_buffer() # Check buffer for subsequent packets
        elif header.seq_num > self._next_expected_seq: # Out-of-order packet
            self._recv_buffer[header.seq_num] = (header, payload, now_ms())
        else: # Duplicate or old packet, ignore
            pass
    def _process_recv_buffer(self):
        while self._next_expected_seq in self._recv_buffer:
            header, payload, _ = self._recv_buffer.pop(self._next_expected_seq)
            self.recv_queue.append((RELIABLE, header.seq_num, header.timestamp, payload))
            self._next_expected_seq += 1

    def _retransmission_loop(self):
        while self.running:
            now = now_ms()

            for seq, (data, send_time, retries) in list(self._unacked_packets.items()):
                if now - send_time > self.RETRANSMIT_TIMEOUT_MS:
                    print(f"INFO: Retransmitting reliable packet {seq} (retry #{retries + 1})")
                    self._send_internal(data)
                    self._unacked_packets[seq] = (data, now, retries + 1)

            # skip packets on receiver side
            if self._recv_buffer:
                hole_seq = self._next_expected_seq
                first_buffered_seq = min(self._recv_buffer.keys())
                if hole_seq < first_buffered_seq:
                    _, _, buffer_time = self._recv_buffer[first_buffered_seq]
                    if now - buffer_time > self.SKIP_THRESHOLD_MS:
                        print(f"WARN: Skipping packet {hole_seq} due to timeout (t={self.SKIP_THRESHOLD_MS}ms).")
                        self._next_expected_seq = first_buffered_seq
                        self._process_recv_buffer()

            time.sleep(0.01)
