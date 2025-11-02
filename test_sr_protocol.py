"""
Comprehensive test suite for the Selective Repeat (SR) Protocol implementation.

This suite tests the SRSender and SRReceiver classes in isolation from the
network socket layer, using a simulated network to introduce controlled
conditions like packet loss, latency, and reordering. It validates
correctness for basic transmission, loss recovery, and advanced features
like flow control.

Run with: python test_sr_protocol.py
"""

import unittest
import threading
import time
import random
from typing import List, Dict, Tuple, Optional

# Import the SR protocol implementation from the application's hudp package
from hudp.reliable import SRReceiver, SRSender

# --- Test Infrastructure ---

class NetworkSimulator:
    """
    Simulates an unreliable network link with configurable loss, delay, jitter,
    and reordering to test protocol resilience.
    """
    def __init__(self, loss_rate=0.0, delay_ms=10, jitter_ms=5):
        self.loss_rate = loss_rate
        self.delay_ms = delay_ms
        self.jitter_ms = jitter_ms
        self.reordering_enabled = False
        self.burst_loss_enabled = False
        self.burst_counter = 0
        self.packets_sent = 0
        self.packets_lost = 0
        
    def transmit(self, packet_fn: callable, delay_override: Optional[float] = None):
        """
        Schedules a function (representing a packet delivery) to be called
        after a simulated network traversal.
        """
        self.packets_sent += 1
        
        # Simulate a burst of consecutive packet drops
        if self.burst_loss_enabled and self.burst_counter < 5:
            self.burst_counter += 1
            self.packets_lost += 1
            return  # Drop the packet
        elif self.burst_loss_enabled:
            self.burst_counter = (self.burst_counter + 1) % 10

        # Random, independent packet loss
        if random.random() < self.loss_rate:
            self.packets_lost += 1
            return  # Drop

        # Compute delay + jitter
        delay = delay_override if delay_override is not None else self.delay_ms
        jitter = random.uniform(-self.jitter_ms, self.jitter_ms)
        total_delay_sec = max(0, delay + jitter) / 1000.0
        
        # Optional reordering
        if self.reordering_enabled and random.random() < 0.3:
            total_delay_sec += random.uniform(0.05, 0.1)
        
        # Schedule "arrival"
        timer = threading.Timer(total_delay_sec, packet_fn)
        timer.daemon = True
        timer.start()


class TestHarness:
    """
    Connects an SRSender and SRReceiver instance through the NetworkSimulator,
    acting as the "wire" and capturing events for test assertions.
    """
    def __init__(self, network: NetworkSimulator):
        self.network = network
        self.sender: Optional[SRSender] = None
        self.receiver: Optional[SRReceiver] = None
        
        # Log events from callbacks
        self.delivered_packets: List[Tuple[int, bytes]] = []
        self.dropped_packets: List[int] = []
        self.sent_packets: Dict[int, bytes] = {}
        self.rtt_samples: List[int] = []
        self.lock = threading.Lock()
        
    def setup_sender(self, **kwargs):
        """Initializes the SRSender with callbacks wired to the harness."""
        self.sender = SRSender(
            on_send_raw=self._on_send_raw,
            on_drop=self._on_drop,
            on_rtt=self._on_rtt,
            **kwargs
        )
        self.sender.start()
        
    def setup_receiver(self, **kwargs):
        """Initializes the SRReceiver with callbacks wired to the harness."""
        self.receiver = SRReceiver(
            deliver_in_order=self._deliver_in_order,
            send_ack=self._send_ack,
            **kwargs
        )
        
    def _on_send_raw(self, seq: int, payload: bytes):
        """Callback from sender for data packet emission (enter the 'wire')."""
        with self.lock:
            self.sent_packets[seq] = payload
        
        delivery_action = lambda: self.receiver.on_data(seq, payload) if self.receiver else None
        self.network.transmit(delivery_action)
        
    def _send_ack(self, seq: int, recv_window: int):
        """Callback from receiver to send ACK back to sender (with flow control)."""
        ack_delivery_action = lambda: self.sender.ack(seq, recv_window) if self.sender else None
        # Small ACK delay for realism
        self.network.transmit(ack_delivery_action, delay_override=5)
        
    def _on_drop(self, seq: int):
        """Callback when sender permanently drops a packet."""
        with self.lock:
            self.dropped_packets.append(seq)
            
    def _on_rtt(self, seq: int, rtt_ms: int):
        """Callback for new RTT sample."""
        with self.lock:
            self.rtt_samples.append(rtt_ms)
            
    def _deliver_in_order(self, seq: int, payload: bytes):
        """Receiver delivers to app layer."""
        with self.lock:
            self.delivered_packets.append((seq, payload))
            
    def send_messages_in_loop(self, messages: List[bytes]):
        """
        Sends a list of messages synchronously on the current thread. If the
        send window is full, SRSender.send() blocks internally and will return
        once space is available or timeout (None) if it cannot proceed.
        """
        for msg in messages:
            # Keep trying until accepted (or fail the test if it times out)
            while True:
                assert self.sender is not None, "Sender not initialized"
                seq = self.sender.send(msg)
                if seq is not None:
                    break  # accepted into flight/queue
                # Window still full after timeout; yield a beat and retry
                time.sleep(0.001)

    def wait_for_completion(self, expected_sent: int, timeout: float = 10.0, idle_grace: float = 0.2):
        """
        Blocks until all expected_sent packets are either delivered or dropped,
        or until timeout. Uses an idle grace to avoid exiting on transient equality.
        """
        deadline = time.time() + timeout
        idle_since: Optional[float] = None

        while time.time() < deadline:
            with self.lock:
                total_accounted = len(self.delivered_packets) + len(self.dropped_packets)
                total_sent = len(self.sent_packets)

            # Only consider completion once we've observed the expected total sent
            if total_sent >= expected_sent and total_accounted >= expected_sent:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= idle_grace:
                    return
            else:
                idle_since = None

            time.sleep(0.01)

        # Diagnostic on timeout
        with self.lock:
            accounted = len(self.delivered_packets) + len(self.dropped_packets)
            sent = len(self.sent_packets)
        print(f"Warning: Timed out waiting for completion. "
              f"Accounted {accounted}/{expected_sent}, observed sent={sent}/{expected_sent}.")

    def cleanup(self):
        """Stops all background threads in the sender and receiver."""
        if self.sender: self.sender.stop()
        if self.receiver: self.receiver.stop()
            
    def get_stats(self) -> Dict:
        """Returns a dictionary of final statistics for assertions."""
        with self.lock:
            return {
                'sent': len(self.sent_packets),
                'delivered': len(self.delivered_packets),
                'dropped': len(self.dropped_packets),
                'retransmissions': self.sender.retransmissions if self.sender else 0,
            }

# --- Unit Test Cases ---

class TestSRProtocol(unittest.TestCase):
    """Contains a suite of tests for the SRSender and SRReceiver logic."""

    def setUp(self):
        self.harness: Optional[TestHarness] = None
        random.seed(1337)

    def tearDown(self):
        if self.harness:
            self.harness.cleanup()

    def _loss_wait_budget(self, max_retries: int, margin_s: float = 5.0) -> float:
        # Sender caps at ~4000ms RTO; worst case ≈ retries * 4.0s
        return max(12.0, max_retries * 4.0 + margin_s)

    def test_flow_control_prevents_buffer_overflow(self):
        """
        Verifies that the sender throttles its sending rate based on the
        receiver's advertised buffer space (flow control).
        """
        print("\n[TEST] Flow Control Throttling")
        
        network = NetworkSimulator(loss_rate=0.0, delay_ms=20)
        harness = TestHarness(network)
        self.harness = harness

        # Sender has a large window, Receiver has small buffer -> peer_rwnd limits effective window.
        harness.setup_sender(window_size=64, rto_ms=200)
        harness.setup_receiver(skip_threshold_ms=500, max_buffer=10)
        
        messages = [f"MSG_{i}".encode('utf-8') for i in range(50)]

        # Act: Send synchronously on the main thread
        harness.send_messages_in_loop(messages)

        # Then wait for completion of all packets
        harness.wait_for_completion(expected_sent=len(messages), timeout=10)

        # Assert
        stats = harness.get_stats()
        self.assertEqual(stats['sent'], 50, "All messages should have been accepted by the sender.")
        self.assertEqual(stats['delivered'], 50, "Flow control failed: receiver dropped packets.")
        self.assertEqual(stats['dropped'], 0, "No messages should be dropped on a perfect network.")
        self.assertEqual(stats['retransmissions'], 0, "No retransmissions should occur on a perfect network.")
        print("✓ PASSED")

    def test_basic_transmission(self):
        """Verifies simple, in-order delivery on a perfect network."""
        print("\n[TEST] Basic Transmission")
        network = NetworkSimulator(loss_rate=0.0, delay_ms=10)
        harness = TestHarness(network)
        self.harness = harness

        harness.setup_sender(window_size=32, rto_ms=100)
        harness.setup_receiver(skip_threshold_ms=500)
        
        messages = [f"MSG_{i}".encode('utf-8') for i in range(20)]
        harness.send_messages_in_loop(messages)
        harness.wait_for_completion(expected_sent=len(messages), timeout=5)
        
        stats = harness.get_stats()
        self.assertEqual(stats['sent'], 20)
        self.assertEqual(stats['delivered'], 20)
        self.assertEqual(stats['dropped'], 0)
        print("✓ PASSED")
            
    def test_packet_loss(self):
        """Moderate network loss (20%): all packets should be delivered with 10 retries."""
        print("\n[TEST] Packet Loss (20%)")
        network = NetworkSimulator(loss_rate=0.2, delay_ms=20)
        harness = TestHarness(network)
        self.harness = harness

        max_retries = 10
        harness.setup_sender(window_size=32, rto_ms=150, max_retries=max_retries)
        harness.setup_receiver(skip_threshold_ms=0)

        messages = [f"MSG_{i}".encode("utf-8") for i in range(30)]
        harness.send_messages_in_loop(messages)

        wait_s = self._loss_wait_budget(max_retries, margin_s=6.0)  # ≈ 46s
        harness.wait_for_completion(expected_sent=len(messages), timeout=wait_s)

        stats = harness.get_stats()
        self.assertEqual(stats["sent"], 30)
        # With 10 retries and 20% i.i.d. loss, delivery is expected for all.
        self.assertEqual(stats["delivered"], 30, "All packets must be delivered despite loss")
        self.assertGreater(stats["retransmissions"], 0, "Retransmissions must occur to recover from loss")
        self.assertEqual(stats["dropped"], 0, "Generous retries at 20% loss should avoid drops")
        print("✓ PASSED")

    def test_packet_loss_heavy(self):
        """Heavier loss (40%) with bounded retries: all packets must be accounted for."""
        print("\n[TEST] Packet Loss (40%)")
        network = NetworkSimulator(loss_rate=0.4, delay_ms=20)
        harness = TestHarness(network)
        self.harness = harness

        max_retries = 8
        harness.setup_sender(window_size=64, rto_ms=150, max_retries=max_retries)
        harness.setup_receiver(skip_threshold_ms=0)

        messages = [f"MSG_{i}".encode("utf-8") for i in range(30)]
        harness.send_messages_in_loop(messages)

        wait_s = self._loss_wait_budget(max_retries, margin_s=8.0)  # ≈ 40s
        harness.wait_for_completion(expected_sent=len(messages), timeout=wait_s)

        stats = harness.get_stats()
        self.assertEqual(stats["sent"], 30)
        # At 40% loss, full delivery is likely but not guaranteed within 8 retries.
        accounted = stats["delivered"] + stats["dropped"]
        self.assertEqual(accounted, 30, "Every packet must be delivered or explicitly dropped")
        self.assertGreater(stats["retransmissions"], 0)
        print("✓ PASSED")

    

if __name__ == '__main__':
    unittest.main(verbosity=2)
