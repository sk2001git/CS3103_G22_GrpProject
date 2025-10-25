# hudp/metrics.py (bare-bones stubs)

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import csv
import time

@dataclass
class ChannelStats:
    name: str
    sent: int = 0
    recv: int = 0
    bytes_sent: int = 0
    bytes_recv: int = 0
    latencies_ow: List[float] = field(default_factory=list)  # one-way ms samples
    jitter_est: float = 0.0                                  # RFC3550-like estimator
    _last_transit: Optional[float] = None

    def on_sent(self, nbytes: int) -> None:
        """Record a single packet sent on this channel."""
        raise NotImplementedError("ChannelStats.on_sent: increment sent/bytes_sent")

    def on_recv(self, nbytes: int, one_way_ms: Optional[float]) -> None:
        """
        Record a single packet received on this channel.
        If one_way_ms is provided, update latency samples and RFC3550-like jitter estimate:
           J = J + (|D(i)-D(i-1)| - J) / 16
        """
        raise NotImplementedError("ChannelStats.on_recv: increment recv/bytes_recv and update jitter")

    def pdr(self) -> float:
        """Packet Delivery Ratio (received/sent * 100)."""
        raise NotImplementedError("ChannelStats.pdr: compute PDR")

    def throughput_bps(self, duration_s: float) -> float:
        """Throughput in bits per second over duration_s, using bytes_recv."""
        raise NotImplementedError("ChannelStats.throughput_bps: compute bytes_recv*8/duration")


class MetricsRecorder:
    """
    Simple per-channel metrics aggregator.
    Typical usage:
      mr = MetricsRecorder()
      mr.ensure(0, "reliable")
      mr.ensure(1, "unreliable")
      mr.on_sent(0, nbytes)
      mr.on_recv(0, nbytes, one_way_ms)
      mr.export_csv("metrics.csv")
    """
    def __init__(self) -> None:
        raise NotImplementedError("MetricsRecorder.__init__: init start_ts and channel dict")

    def ensure(self, ch: int, name: str) -> None:
        """Ensure a ChannelStats exists for channel id ch."""
        raise NotImplementedError("MetricsRecorder.ensure: create ChannelStats if missing")

    def on_sent(self, ch: int, nbytes: int) -> None:
        raise NotImplementedError("MetricsRecorder.on_sent: forward to ChannelStats.on_sent")

    def on_recv(self, ch: int, nbytes: int, one_way_ms: Optional[float]) -> None:
        raise NotImplementedError("MetricsRecorder.on_recv: forward to ChannelStats.on_recv")

    def duration_s(self) -> float:
        raise NotImplementedError("MetricsRecorder.duration_s: return elapsed seconds since start")

    def export_csv(self, path: str) -> None:
        """
        Write a one-row-per-channel CSV:
          channel,sent,recv,pdr_percent,throughput_bps,avg_latency_ms,jitter_ms
        """
        raise NotImplementedError("MetricsRecorder.export_csv: write summary CSV")
