from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Dict, List, Tuple
import threading
import time
from collections import deque

Clock = Callable[[], int]

# ===============================
# Mod-16 (uint16) helpers
# ===============================
_U16_MOD = 1 << 16
_U16_MASK = _U16_MOD - 1


def u16(x: int) -> int:
    return x & _U16_MASK


def u16_incr(x: int, inc: int = 1) -> int:
    return (x + inc) & _U16_MASK


def u16_distance(start: int, end: int) -> int:
    """Unsigned distance from start -> end on a ring of 2^16."""
    return (end - start) & _U16_MASK


def u16_in_window(seq: int, start: int, size: int) -> bool:
    """True iff seq in [start, start+size) modulo 2^16."""
    return u16_distance(start, seq) < size

# ===============================
# Sender (SR + adaptive RTO)
# ===============================
@dataclass
class _TxItem:
    seq: int
    payload: bytes
    first_send_ms: int
    last_send_ms: int
    retries: int
    retransmitted: bool


class SRSender:
    def __init__(
        self,
        window_size: int = 64,
        rto_ms: int = 200,
        max_retries: int = 10,
        on_send_raw: Optional[Callable[[int, bytes], None]] = None,
        on_drop: Optional[Callable[[int], None]] = None,
        on_rtt: Optional[Callable[[int, int], None]] = None,
        clock_ms: Clock = lambda: int(time.time() * 1000),
    ):
        if window_size <= 0 or window_size > _U16_MOD:
            raise ValueError("SRSender: invalid window_size")
        if rto_ms <= 0:
            raise ValueError("SRSender: rto_ms must be > 0")

        self.window_size = int(window_size)
        self.max_retries = int(max_retries)
        self.clock_ms = clock_ms
        self.on_send_raw = on_send_raw or (lambda _s, _p: None)
        self.on_drop = on_drop or (lambda _s: None)
        self.on_rtt = on_rtt or (lambda _s, _r: None)

        self._base = 0
        self._next_seq = 0
        self._out: Dict[int, _TxItem] = {}

        self._srtt: Optional[float] = None
        self._rttvar: Optional[float] = None
        self._rto: float = float(rto_ms)
        self._avg_rtt: Optional[float] = None
        self._initial_rto = float(rto_ms)
        self._K = 4.0
        self._alpha = 1.0 / 8.0
        self._beta = 1.0 / 4.0
        self._min_rto = 200.0
        self._max_rto = 4000.0
        self.retransmissions = 0

        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._timer_thread: Optional[threading.Thread] = None

        # --- Fast Retransmit State ---
        self._dupacks = 0
        self._dupacks_threshold = 3

        # --- Flow/Congestion Control ---
        self._peer_rwnd = float(self.window_size)
        self._INITIAL_CWND = 10.0
        self._cwnd = self._INITIAL_CWND
        self._ssthresh = float(self.window_size) 

        self._pacing_queue = deque()
        self._pacing_thread: Optional[threading.Thread] = None
        self._last_win_full_log_ms = 0 # Add this line

        self._cv = threading.Condition(self._lock) # Add this line


        print(f"[SENDER] Initialized. WinSize={self.window_size}, RTO={self._rto:.1f}ms, CWND={self._cwnd:.1f}")

    def start(self) -> None:
        with self._lock:
            if self._timer_thread is not None:
                return
            self._stop_evt.clear()
            self._timer_thread = threading.Thread(
                target=self._timer_loop, name="SRSenderTimer", daemon=True
            )
            self._timer_thread.start()
            print("[SENDER] Timer thread started.")

            self._pacing_thread = threading.Thread(
                target=self._pacing_loop, name="SRSenderPacer", daemon=True
            )
            self._pacing_thread.start()
            print("[SENDER] Timer and Pacing threads started.")

    def stop(self) -> None:
        self._stop_evt.set()
        threads_to_join = []
        with self._lock:
            if self._timer_thread:
                threads_to_join.append(self._timer_thread)
                self._timer_thread = None
            if self._pacing_thread:
                threads_to_join.append(self._pacing_thread)
                self._pacing_thread = None

        for t in threads_to_join:
            t.join(timeout=1.0)
        print("[SENDER] Stopped.")

    def _queue_packet_for_pacing(self, seq: int, payload: bytes, is_retransmission: bool):
        """Adds a packet to the pacing queue. Retransmissions get priority."""
        with self._lock:
            if is_retransmission:
                # Retransmitted packets jump to the front of the line
                self._pacing_queue.appendleft((seq, payload))
            else:
                self._pacing_queue.append((seq, payload))

    def _pacing_loop(self) -> None:
        """
        Runs in a dedicated thread, pulling packets from a queue and sending
        them at a rate controlled by the congestion window and RTT.
        """
        while not self._stop_evt.is_set():
            packet_to_send = None
            with self._lock:
                if self._pacing_queue:
                    packet_to_send = self._pacing_queue.popleft()

            if packet_to_send:
                seq, payload = packet_to_send
                # Send the packet using the actual socket function
                self.on_send_raw(seq, payload)

                # Calculate the delay until the next packet can be sent
                with self._lock:
                    # Use smoothed RTT if available, otherwise fall back to RTO
                    rtt_s = (self._srtt / 1000.0) if self._srtt is not None else (self._rto / 1000.0)
                    # Ensure cwnd is at least 1 to avoid division by zero
                    cwnd = self._cwnd if self._cwnd >= 1.0 else 1.0

                # The core pacing calculation: distribute the CWND over one RTT
                inter_packet_gap_s = rtt_s / cwnd
                
                # Wait for the calculated gap, but be interruptible by stop()
                self._stop_evt.wait(inter_packet_gap_s)
            else:
                # Queue is empty, wait a very small amount of time to avoid busy-waiting
                self._stop_evt.wait(0.001)

    def _get_effective_window(self) -> int:
        return int(min(self.window_size, self._peer_rwnd, self._cwnd))

    def send(self, serialized_payload: bytes, timeout_s: float = 1.0) -> Optional[int]:
        now = self.clock_ms()
        with self._lock:
            effective_win = self._get_effective_window()
            while len(self._out) >= self._get_effective_window():
                now = self.clock_ms()  
                if now - self._last_win_full_log_ms > 500: # Log at most every 500ms
                    print(f"[SENDER] !! WINDOW FULL !! Cannot send. InFlight={len(self._out)}, EffWin={effective_win} (CWND={self._cwnd:.1f}, PeerRWND={self._peer_rwnd:.1f})")
                    self._last_win_full_log_ms = now

                if not self._cv.wait(timeout=timeout_s):
                    # If we timed out, the window is still full. Give up.
                    print(f"[SENDER] !! TIMEOUT waiting for send window space.")
                    return None
            
            seq = self._next_seq
            self._next_seq = u16_incr(self._next_seq, 1)

            self._out[seq] = _TxItem(
                seq=seq, payload=serialized_payload, first_send_ms=now,
                last_send_ms=now, retries=0, retransmitted=False,
            )
            print(f"[SENDER] -> Queued packet {seq}. Base={self._base}, Next={self._next_seq}, InFlight={len(self._out)}")

        # MODIFIED: Instead of sending, we now queue it for the pacer
        self._queue_packet_for_pacing(seq, serialized_payload, is_retransmission=False)
        return seq

    def ack(self, ack_seq: int, peer_rwnd: Optional[int] = None) -> None:
        # This method's logic doesn't change much, but the call to on_send_raw
        # at the end will now be correctly routed to the pacer queue.
        now = self.clock_ms()
        rtt_sample: Optional[int] = None
        fast_retransmit_item: Optional[_TxItem] = None
        was_new_ack = False
        
        with self._lock:
            if peer_rwnd is not None:
                self._peer_rwnd = float(peer_rwnd)
            item_was_in_flight = self._out.pop(ack_seq, None)

            if item_was_in_flight:
                was_new_ack = True
                self._cv.notify_all()
                if item_was_in_flight.retries == 0:
                    rtt_sample = max(1, now - item_was_in_flight.first_send_ms)
                
                if self._cwnd < self._ssthresh:
                    self._cwnd += 1.0
                    print(f"[SENDER] <- ACK {ack_seq} (NEW). In Slow Start. CWND -> {self._cwnd:.1f}")
                else:
                    self._cwnd += 1.0 / self._cwnd
                    print(f"[SENDER] <- ACK {ack_seq} (NEW). In Congestion Avoidance. CWND -> {self._cwnd:.1f}")

                self._dupacks = 0
                while self._base != self._next_seq and self._base not in self._out:
                    self._base = u16_incr(self._base, 1)
            else:
                was_new_ack = False
                self._dupacks += 1
                print(f"[SENDER] <- ACK {ack_seq} (DUPLICATE). Count={self._dupacks}/{self._dupacks_threshold}. Base={self._base}")

                if self._dupacks >= self._dupacks_threshold and self._base in self._out:
                    print(f"[SENDER] !!! FAST RETRANSMIT of {self._base} !!!")
                    self._ssthresh = max(10.0, self._cwnd / 2.0)
                    self._cwnd = self._ssthresh 
                    print(f"[SENDER]    Congestion event: SSTHRESH={self._ssthresh:.1f}, CWND={self._cwnd:.1f}")

                    fast_retransmit_item = self._out[self._base]
                    fast_retransmit_item.last_send_ms = now
                    fast_retransmit_item.retransmitted = True
                    self.retransmissions += 1
                    self._dupacks = 0

        if rtt_sample is not None:
            self._update_rto(rtt_sample)
            self.on_rtt(ack_seq, rtt_sample)

        if fast_retransmit_item:
            self._queue_packet_for_pacing(
                fast_retransmit_item.seq, fast_retransmit_item.payload, is_retransmission=True
            )
        return was_new_ack

    def _update_rto(self, rtt_ms: int) -> None:
        rtt = float(rtt_ms)
        if self._avg_rtt is None:
            self._avg_rtt = rtt
            self._rttvar = rtt / 2.0
        else:
            self._rttvar = (1 - self._beta) * self._rttvar + self._beta * abs(self._avg_rtt - rtt)
            self._avg_rtt = (1 - self._alpha) * self._avg_rtt + self._alpha * rtt

        candidate = max(self._initial_rto, 2.0 * self._avg_rtt)
        self._rto = max(self._min_rto, min(candidate, self._max_rto))
         # Keep SR RTT/RTTVAR machinery unchanged if present (no-op if not used)

    def _backoff_rto(self) -> None:
        rto_before = self._rto
        self._rto = min(self._rto * 2.0, self._max_rto)
        print(f"[SENDER]    RTO backoff: {rto_before:.1f}ms -> {self._rto:.1f}ms")

    def _timer_loop(self) -> None:
        while not self._stop_evt.is_set():
            now = self.clock_ms()
            to_resend: List[_TxItem] = []
            to_drop: List[int] = []

            with self._lock:
                rto_ms = int(self._rto)
                for seq, it in list(self._out.items()):
                    if now - it.last_send_ms >= rto_ms:
                        if it.retries < self.max_retries:
                            print(f"[SENDER] !!! TIMEOUT on packet {seq} !!! (Retries: {it.retries+1}/{self.max_retries})")
                            it.retries += 1
                            it.last_send_ms = now
                            it.retransmitted = True
                            to_resend.append(it)
                            self.retransmissions += 1
                        else:
                            print(f"[SENDER] !!! DROPPING packet {seq} !!! (Max retries exceeded)")
                            to_drop.append(seq)

                for s in to_drop:
                    self._out.pop(s, None)
                    self._cv.notify_all()

                while self._base != self._next_seq and self._base not in self._out:
                    self._base = u16_incr(self._base, 1)

                if to_resend:
                    # Apply the less punishing congestion response
                    self._ssthresh = max(10.0, self._cwnd / 2.0)
                    self._cwnd = self._INITIAL_CWND
                    print(f"[SENDER]    Congestion event (Timeout): CWND reduced to {self._cwnd:.1f}")
                    self._backoff_rto()
            
            for it in to_resend:
                # MODIFIED: Queue the retransmission with high priority
                self._queue_packet_for_pacing(it.seq, it.payload, is_retransmission=True)
            for s in to_drop:
                self.on_drop(s)

            # The timer loop can tick less frequently now
            sleep_ms = max(10, int(self._rto // 4))
            self._stop_evt.wait(sleep_ms / 1000.0)




# ===============================
# Receiver (SR buffering + skip timer)
# ===============================
class SRReceiver:
    def __init__(
        self,
        deliver_in_order: Callable[[int, bytes], None],
        send_ack: Callable[[int, int], None],
        skip_threshold_ms: int = 200,
        clock_ms: Clock = lambda: int(time.time() * 1000),
        window_size: int = 64,
        max_buffer: Optional[int] = None,
    ):
        if window_size <= 0 or window_size > _U16_MOD:
            raise ValueError("SRReceiver: invalid window_size")
        if skip_threshold_ms < 0:
            raise ValueError("SRReceiver: skip_threshold_ms must be >= 0")

        self.deliver_in_order = deliver_in_order
        self.send_ack = send_ack
        self.clock_ms = clock_ms
        self.window_size = int(window_size)
        self.skip_threshold_ms = int(skip_threshold_ms)
        self.max_buffer = max_buffer or (2 * window_size)

        self._lock = threading.Lock()
        self._expected = 0
        self._buffer: Dict[int, Tuple[bytes, int]] = {}
        self._hole_since_ms: Optional[int] = None

        self._stop_evt = threading.Event()
        self._timer_thread: Optional[threading.Thread] = None
        
        print(f"[RECEIVER] Initialized. Expected={self._expected}, WinSize={self.window_size}, MaxBuffer={self.max_buffer}")

        if self.skip_threshold_ms > 0:
            self._timer_thread = threading.Thread(
                target=self._timer_loop, name="SRReceiverTimer", daemon=True
            )
            self._timer_thread.start()
            print(f"[RECEIVER] Skip timer started (threshold: {self.skip_threshold_ms}ms).")

    def stop(self) -> None:
        self._stop_evt.set()
        if self._timer_thread:
            self._timer_thread.join(timeout=1.0)
        print("[RECEIVER] Stopped.")

    def on_data(self, seq: int, payload: bytes) -> None:
        deliver_list: List[Tuple[int, bytes]] = []
        now = self.clock_ms()
        should_ack = False
        processed_successfully = False

        with self._lock:
            if u16_in_window(seq, u16(self._expected - self.window_size), self.window_size * 2):
                should_ack = True

            if u16_in_window(seq, self._expected, self.window_size):
                if seq == self._expected:
                    # --- Case A: IN-ORDER PACKET ---
                    print(f"[RECEIVER] <- Data {seq} (IN-ORDER). Delivering to app.")
                    deliver_list.append((seq, payload))
                    processed_successfully = True
                    self._expected = u16_incr(self._expected)
                    self._hole_since_ms = None
                    
                    # Drain buffer
                    drained = []
                    while self._expected in self._buffer:
                        p, _ts = self._buffer.pop(self._expected)
                        deliver_list.append((self._expected, p))
                        drained.append(self._expected)
                        self._expected = u16_incr(self._expected)
                    if drained:
                         print(f"[RECEIVER]    Drained [{', '.join(map(str, drained))}] from buffer. New Expected={self._expected}")

                elif u16_distance(self._expected, seq) > 0:
                    # --- Case B: OUT-OF-ORDER (FUTURE) PACKET ---
                    if seq not in self._buffer:
                        if len(self._buffer) < self.max_buffer:
                            print(f"[RECEIVER] <- Data {seq} (OUT-OF-ORDER). Buffering. Expected={self._expected}, BufSize={len(self._buffer)+1}")
                            self._buffer[seq] = (payload, now)
                            processed_successfully = True
                        else:
                            print(f"[RECEIVER] !! BUFFER FULL !! Dropping packet {seq}. BufSize={len(self._buffer)}")
                            # processed_successfully remains False
                    else:
                        print(f"[RECEIVER] <- Data {seq} (DUPLICATE of buffered). Ignoring.")
                        processed_successfully = True

                    if self._hole_since_ms is None:
                        self._hole_since_ms = now
            
            elif seq < self._expected:
                # --- Case C: OLD PACKET ---
                print(f"[RECEIVER] <- Data {seq} (OLD/Stale). Discarding data. Expected={self._expected}")
                processed_successfully = True

            # Send ACK if we handled the packet
            if should_ack and processed_successfully:
                available_window = self.max_buffer - len(self._buffer)
                print(f"[RECEIVER] -> Queued ACK {seq}. (Available buffer: {available_window})")
                self.send_ack(seq, available_window)

        # --- Deliver Data outside the lock ---
        for s, p in deliver_list:
            try:
                self.deliver_in_order(s, p)
            except Exception as e:
                print(f"[RECEIVER] !! Error delivering packet {s}: {e}")

    def _timer_loop(self) -> None:
        tick_ms = max(10, self.skip_threshold_ms // 4)
        while not self._stop_evt.is_set():
            do_deliver: List[Tuple[int, bytes]] = []
            now = self.clock_ms()

            with self._lock:
                if self._hole_since_ms is not None and (now - self._hole_since_ms >= self.skip_threshold_ms):
                    print(f"[RECEIVER] !!! SKIP MECHANISM: Waited too long for {self._expected}. Skipping it.")
                    self._expected = u16_incr(self._expected)
                    self._hole_since_ms = None 

                    drained = []
                    while self._expected in self._buffer:
                        p, _ts = self._buffer.pop(self._expected)
                        do_deliver.append((self._expected, p))
                        drained.append(self._expected)
                        self._expected = u16_incr(self._expected)
                    
                    if drained:
                        print(f"[RECEIVER]    Delivering [{', '.join(map(str, drained))}] from buffer after skip. New Expected={self._expected}")

                    if self._buffer and self._expected not in self._buffer:
                        self._hole_since_ms = now

            for s, p in do_deliver:
                try:
                    self.deliver_in_order(s, p)
                except Exception as e:
                    print(f"[RECEIVER] !! Error delivering packet {s} after skip: {e}")

            self._stop_evt.wait(tick_ms / 1000.0)

    def _pacing_loop(self) -> None:
        """
        Runs in a dedicated thread, pulling packets from a queue and sending
        them at a rate controlled by the congestion window and RTT.
        Now also respects the remote advertised window: if peer_rwnd <= 0
        the pacer will pause and requeue the packet.
        """
        while not self._stop_evt.is_set():
            packet_to_send = None
            with self._lock:
                if self._pacing_queue:
                    packet_to_send = self._pacing_queue.popleft()

            if packet_to_send:
                seq, payload = packet_to_send

                # Respect peer advertised window; if it's zero, requeue and wait a bit.
                with self._lock:
                    effective_win = self._get_effective_window()
                    if effective_win < 1:
                        # Put it back at front to preserve priority and wait to be notified
                        self._pacing_queue.appendleft((seq, payload))
                        # Wait until either stop requested or a short timeout; ack() will notify on window changes
                        # Use a short wait so shutdown remains responsive
                        self._stop_evt.wait(0.05)
                        continue

                # Send the packet using the actual socket function
                self.on_send_raw(seq, payload)

                # Calculate the delay until the next packet can be sent
                with self._lock:
                    rtt_s = (self._srtt / 1000.0) if self._srtt is not None else (self._rto / 1000.0)
                    cwnd = self._cwnd if self._cwnd >= 1.0 else 1.0

                inter_packet_gap_s = rtt_s / cwnd
                self._stop_evt.wait(inter_packet_gap_s)
            else:
                self._stop_evt.wait(0.001)