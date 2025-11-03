from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import csv
import time
from collections import defaultdict
from .packet import now_ms

RFC3550_CLOCK_HZ = 8000

@dataclass
class MetricsRecorder:
    def __init__(self):
        self.records = []
        self.start_time = time.monotonic()
        self.channel_stats = defaultdict(lambda: {
            'sent_count': 0,
            'recv_count': 0,
            'total_bytes_sent': 0,
            'total_bytes_recv': 0,
            'total_latency_ms': 0,
            'last_arrival_time_ms': 0,
            'last_transit_time': 0,
            'jitter': 0.0
        })

    def on_sent(self, channel, num_bytes: int) -> None:
        """Record a single packet sent on this channel."""
        if num_bytes is None:
            num_bytes = 0  # Defensive programming for metrics
        stats = self.channel_stats[channel]
        stats['sent_count'] += 1
        stats['total_bytes_sent'] += num_bytes

    def on_recv(self, channel: int, num_bytes: int, one_way_ms: Optional[float], header_ts_ms: int) -> None:
        """
        Record a single packet received on this channel.
        If one_way_ms is provided, update latency samples and RFC3550-like jitter estimate:
           J = J + (|D(i)-D(i-1)| - J) / 16
        Jitter calculation based on RFC3550
        """
        arrival_time_ms = now_ms()
        one_way_latency = arrival_time_ms - header_ts_ms

        stats = self.channel_stats[channel]
        stats['recv_count'] += 1
        stats['total_bytes_recv'] += num_bytes
        stats['total_latency_ms'] += one_way_latency

        transit_time = one_way_latency
        if stats['last_transit_time'] > 0:
            d = abs(transit_time - stats['last_transit_time'])
            stats['jitter'] += (d - stats['jitter']) / 16.0
        stats['last_transit_time'] = transit_time

        self.records.append({
            'timestamp_s': time.monotonic() - self.start_time,
            'channel': channel,
            'bytes': num_bytes,
            'latency_ms': one_way_latency
        })
        return None

    def get_summary(self) -> dict:
        duration_s = time.monotonic() - self.start_time
        summary = {}
        for ch, stats in self.channel_stats.items():
            sent = stats['sent_count']
            recv = stats['recv_count']

            pdr = round((recv / sent * 100.0), 2) if sent > 0 else 'N/A'
            avg_latency = (stats['total_latency_ms'] / recv) if recv > 0 else 0
            throughput_kbps = (stats['total_bytes_recv'] * 8 / duration_s / 1000) if duration_s > 0 else 0

            summary[ch] = {
                'packets_sent': sent,
                'packets_received': recv,
                'packet_delivery_ratio_%': pdr,
                'avg_latency_ms': round(avg_latency, 2),
                'jitter_ms': round(stats['jitter'], 2),
                'throughput_kbps': round(throughput_kbps, 2)
            }
        return summary

    def on_ack(self, channel: int, num_bytes: int = 0) -> None:
        """Record that an ACK (or ACK-like signal) was received for the given channel.
        This is used by sender-side code to count acknowledgements as "received".
        It does not update latency/jitter (ACKs don't carry the original header timestamp).
        """
        stats = self.channel_stats[channel]
        stats['recv_count'] += 1
        stats['total_bytes_recv'] += num_bytes

    def export_csv(self, filename: str):
        if not self.records:
            return
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.records[0].keys())
            writer.writeheader()
            writer.writerows(self.records)

