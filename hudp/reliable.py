from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Dict, List, Tuple
import threading
import time


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
    retransmitted: bool  # Karn's rule: if True, don't use its ACK for RTT sample


class SRSender:
    """
    Selective Repeat sender with per-packet timers and TCP-like polish:
      - Window control (base/next_seq)
      - Per-packet timeouts, retransmit only that packet
      - Drop after max_retries
      - RTT estimation with Karn’s rule + RFC6298-style adaptive RTO
      - Callbacks:
          * on_send_raw(seq:int, payload:bytes)
          * on_drop(seq:int)
          * on_rtt(seq:int, rtt_ms:int) [optional]
    API compatible with your existing GameNetAPI (ACKs are per-seq).
    """

    def __init__(
        self,
        window_size: int = 64,
        rto_ms: int = 200,                   # initial RTO per RFC6298 default (1s) but we use 200ms as a low-latency start
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

        # Callbacks
        self.on_send_raw = on_send_raw or (lambda _s, _p: None)
        self.on_drop = on_drop or (lambda _s: None)
        self.on_rtt = on_rtt or (lambda _s, _r: None)

        # Window state
        self._base = 0
        self._next_seq = 0
        self._out: Dict[int, _TxItem] = {}

        # RFC6298-style RTT estimator (simple form)
        # If no samples yet, use _rto as configured; adapt once we get a clean sample.
        self._srtt: Optional[float] = None
        self._rttvar: Optional[float] = None
        self._rto: float = float(rto_ms)  # ms
        self._K = 4.0
        self._alpha = 1.0 / 8.0
        self._beta = 1.0 / 4.0
        self._min_rto = 50.0             # clamp RTO to avoid too-small timers
        self._max_rto = 4000.0           # clamp RTO top

        # Threading
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._timer_thread: Optional[threading.Thread] = None
        
        self._last_cum_ack = u16(self._next_seq - 1)  
        self._dupacks = 0                            
        self._dupacks_threshold = 3       

    # ---------- Lifecycle ----------
    def start(self) -> None:
        with self._lock:
            if self._timer_thread is not None:
                return
            self._stop_evt.clear()
            self._timer_thread = threading.Thread(
                target=self._timer_loop, name="SRSenderTimer", daemon=True
            )
            self._timer_thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        t = None
        with self._lock:
            t = self._timer_thread
            self._timer_thread = None
        if t:
            t.join(timeout=1.0)

    # ---------- Public API ----------
    def send(self, serialized_payload: bytes) -> Optional[int]:
        """Queue a reliable packet. Assign seq and trigger first send.
        Return seq or None if window full."""
        now = self.clock_ms()
        with self._lock:
            if len(self._out) >= self.window_size:
                return None

            seq = self._next_seq
            self._next_seq = u16_incr(self._next_seq, 1)

            self._out[seq] = _TxItem(
                seq=seq,
                payload=serialized_payload,
                first_send_ms=now,
                last_send_ms=now,
                retries=0,
                retransmitted=False,
            )

        # I/O out of lock
        try:
            self.on_send_raw(seq, serialized_payload)
        except Exception:
            pass
        return seq

    def ack(self, ack_seq: int) -> None:
        """
        Per-packet ACK handler (matches SRReceiver's behavior of ACKing each seq it sees).
        Removes only the acknowledged seq from the outstanding map, updates RTT/RTO
        if the packet was never retransmitted (Karn's rule), and slides the base.
        """
        now = self.clock_ms()
        rtt_sample: Optional[int] = None

        with self._lock:
            it = self._out.pop(ack_seq, None)
            if it is not None:
                # Karn's rule: only take RTT if this copy wasn't retransmitted
                if it.retries == 0:
                    rtt_sample = max(0, now - it.last_send_ms)

            # Slide base past any cleared holes
            while self._base != self._next_seq and self._base not in self._out:
                self._base = u16_incr(self._base, 1)

        # Update RTT/RTO and notify outside the lock
        if rtt_sample is not None:
            try:
                self._update_rto(rtt_sample)
            except Exception:
                pass
            try:
                self.on_rtt(ack_seq, rtt_sample)
            except Exception:
                pass
                
        
    # ---------- Internals ----------
    def _update_rto(self, rtt_ms: int) -> None:
        """RFC 6298 SRTT/RTTVAR update (simplified), with clamping."""
        rtt = float(rtt_ms)
        if self._srtt is None:
            # First measurement
            self._srtt = rtt
            self._rttvar = rtt / 2.0
        else:
            assert self._rttvar is not None
            self._rttvar = (1 - self._beta) * self._rttvar + self._beta * abs(self._srtt - rtt)
            self._srtt = (1 - self._alpha) * self._srtt + self._alpha * rtt

        self._rto = self._srtt + self._K * (self._rttvar if self._rttvar is not None else 0.0)
        # Clamp RTO for sanity
        self._rto = max(self._min_rto, min(self._rto, self._max_rto))

    def _backoff_rto(self) -> None:
        """Exponential backoff on timeout, as TCP would do."""
        self._rto = min(self._rto * 2.0, self._max_rto)

    def _timer_loop(self) -> None:
        while not self._stop_evt.is_set():
            now = self.clock_ms()
            to_resend: List[_TxItem] = []
            to_drop: List[int] = []

            # Snapshot current RTO (ms) under lock
            with self._lock:
                rto_ms = int(self._rto)

            with self._lock:
                for seq, it in list(self._out.items()):
                    if now - it.last_send_ms >= rto_ms:
                        if it.retries < self.max_retries:
                            # schedule retransmit
                            it.retries += 1
                            it.last_send_ms = now
                            it.retransmitted = True  # Karn: mark as retransmitted
                            to_resend.append(it)
                        else:
                            to_drop.append(seq)

                for s in to_drop:
                    self._out.pop(s, None)
                while self._base != self._next_seq and self._base not in self._out:
                    self._base = u16_incr(self._base, 1)

                # Timeout implies congestion or loss → backoff RTO (once per loop if any timed out)
                if to_resend:
                    self._backoff_rto()

            # I/O out of lock
            for it in to_resend:
                try:
                    self.on_send_raw(it.seq, it.payload)
                except Exception:
                    pass
            for s in to_drop:
                try:
                    self.on_drop(s)
                except Exception:
                    pass

            # Sleep a fraction of current RTO to get sub-RTO granularity
            sleep_ms = max(5, int(self._rto // 4))
            self._stop_evt.wait(sleep_ms / 1000.0)


# ===============================
# Receiver (SR buffering + skip timer)
# ===============================
class SRReceiver:
    """
    Selective Repeat receiver with buffering + reordering + skip-after-t.
      - Accepts out-of-order packets within window; buffers them.
      - ACKs every packet immediately (compatible with your GameNetAPI).
      - Delivers in-order. If a hole persists for >= skip_threshold_ms,
        skip it and continue delivering (assignment requirement).
      - Background timer enforces skipping even if traffic stops.
    """

    def __init__(
        self,
        deliver_in_order: Callable[[int, bytes], None],
        send_ack: Callable[[int], None],
        skip_threshold_ms: int = 200,
        clock_ms: Clock = lambda: int(time.time() * 1000),
        window_size: int = 64,
        max_buffer: Optional[int] = None,  # cap buffer to avoid unbounded memory
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
        self.max_buffer = max_buffer or (2 * window_size)  # sane cap

        self._lock = threading.Lock()
        self._expected = 0
        self._buffer: Dict[int, Tuple[bytes, int]] = {}  # seq -> (payload, first_seen_ms)
        self._hole_since_ms: Optional[int] = None

        # background skip timer
        self._stop_evt = threading.Event()
        self._timer_thread = threading.Thread(target=self._timer_loop, name="SRReceiverTimer", daemon=True)
        self._timer_thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._timer_thread.join(timeout=1.0)

    def on_data(self, seq: int, payload: bytes) -> None:
        """Process incoming reliable data; ACK immediately; deliver in-order; buffer OOO; skip holes after t."""
        # ACK immediately (even duplicates/out-of-window)
        try:
            self.send_ack(seq)
        except Exception:
            pass

        deliver_list: List[Tuple[int, bytes]] = []

        now = self.clock_ms()
        with self._lock:
            if not u16_in_window(seq, self._expected, self.window_size):
                # too old or too far ahead → ignore after ACK
                pass
            else:
                if seq == self._expected:
                    # In-order → deliver and drain
                    deliver_list.append((seq, payload))
                    self._expected = u16_incr(self._expected)
                    self._hole_since_ms = None

                    while self._expected in self._buffer:
                        p, _ts = self._buffer.pop(self._expected)
                        deliver_list.append((self._expected, p))
                        self._expected = u16_incr(self._expected)
                        self._hole_since_ms = None
                else:
                    # Out-of-order within window → buffer if space
                    if seq not in self._buffer:
                        if len(self._buffer) < self.max_buffer:
                            self._buffer[seq] = (payload, now)
                        # else: silently drop OOO to avoid memory blowup

            # Maintain/update hole timer: if expected is missing and not present in buffer, ensure timer running
            if self._expected not in self._buffer:
                if self._hole_since_ms is None:
                    self._hole_since_ms = now
            else:
                self._hole_since_ms = None

        # callbacks out of lock
        for s, p in deliver_list:
            try:
                self.deliver_in_order(s, p)
            except Exception:
                pass

    # ---------- Internals ----------
    def _timer_loop(self) -> None:
        """Periodically check for a stuck hole and skip it after threshold, then drain buffered."""
        tick_ms = max(10, self.skip_threshold_ms // 5 if self.skip_threshold_ms > 0 else 50)

        while not self._stop_evt.is_set():
            do_deliver: List[Tuple[int, bytes]] = []

            with self._lock:
                if self._hole_since_ms is not None and self.skip_threshold_ms > 0:
                    if self.clock_ms() - self._hole_since_ms >= self.skip_threshold_ms:
                        # Skip current expected
                        self._expected = u16_incr(self._expected)
                        # Reset hole timer for the new expected (will be set below)
                        self._hole_since_ms = None

                        # If new expected already buffered, drain burst
                        while self._expected in self._buffer:
                            p, _ts = self._buffer.pop(self._expected)
                            do_deliver.append((self._expected, p))
                            self._expected = u16_incr(self._expected)

                        # Re-arm hole timer for next gap
                        if self._expected not in self._buffer:
                            self._hole_since_ms = self.clock_ms()

            # Deliver outside lock
            for s, p in do_deliver:
                try:
                    self.deliver_in_order(s, p)
                except Exception:
                    pass

            self._stop_evt.wait(tick_ms / 1000.0)
