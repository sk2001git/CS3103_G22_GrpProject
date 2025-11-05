from __future__ import annotations
from dataclasses import dataclass, field
import os
from typing import List, Dict, Optional
import csv
import time
from collections import defaultdict
from .packet import now_ms, RELIABLE, UNRELIABLE

RFC3550_CLOCK_HZ = 8000

@dataclass
class MetricsRecorder:
    def __init__(self, role: str = "unknown"):
        self.role = role
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

    def on_sent(self, channel, sequence: int, num_bytes: int) -> None:
        """Record a single packet sent on this channel."""
        if num_bytes is None:
            num_bytes = 0
        stats = self.channel_stats[channel]
        stats['sent_count'] += 1
        stats['total_bytes_sent'] += num_bytes

        self.records.append({
            'timestamp_s': time.monotonic() - self.start_time,
            'channel': channel,
            'sequence': sequence,  # Use actual sequence number
            'bytes': num_bytes,    # Use actual byte count
            'latency_ms': 0.0,
        })

    def on_recv(self, channel: int, sequence: int, num_bytes: int, header_ts_ms: int) -> None:
        """
        Record a single packet received on this channel.
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
            'sequence': sequence,  # Use actual sequence number
            'bytes': num_bytes,    # Use actual byte count
            'latency_ms': one_way_latency
        })

    def get_summary(self) -> dict:
        duration_s = time.monotonic() - self.start_time
        summary = {}
        for ch, stats in self.channel_stats.items():
            # For sender, count unique sequences to avoid counting retransmissions
            if self.role == "sender" and hasattr(self, '_sent_sequences'):
                sent_count = len(self._sent_sequences.get(ch, set()))
            else:
                sent_count = stats['sent_count']
                
            recv_count = stats['recv_count']

            if self.role == "sender" and ch == 0:  # Reliable channel
                pdr = round((recv_count / sent_count * 100.0), 2) if sent_count > 0 else 0.0
            else:
                pdr = "N/A"

            avg_latency = (stats['total_latency_ms'] / recv_count) if recv_count > 0 else 0
            throughput_kbps = (stats['total_bytes_recv'] * 8 / duration_s / 1000) if duration_s > 0 else 0

            summary[ch] = {
                'packets_sent': sent_count,
                'packets_received': recv_count,
                'packet_delivery_ratio_%': pdr,
                'avg_latency_ms': round(avg_latency, 2),
                'jitter_ms': round(stats['jitter'], 2),
                'throughput_kbps': round(throughput_kbps, 2)
            }
        return summary

    def on_ack(self, channel: int, sequence: int, num_bytes: int = 0) -> None:
        """Record that an ACK was received - only count unique ACKs"""
        if channel == RELIABLE:
            # Only count the first ACK for each sequence to avoid counting duplicates
            if not hasattr(self, '_acked_sequences'):
                self._acked_sequences = set()
            
            if sequence in self._acked_sequences:
                return  # Skip duplicate ACKs
                
            self._acked_sequences.add(sequence)
        
        stats = self.channel_stats[channel]
        stats['recv_count'] += 1
        stats['total_bytes_recv'] += num_bytes

    def export_csv(self, filepath: str):
        if not self.records:
            return

        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.records[0].keys())
            writer.writeheader()
            writer.writerows(self.records)

        print(f"Metrics data exported to {filepath}")