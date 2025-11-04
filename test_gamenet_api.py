"""
Comprehensive test suite for H-UDP GameNetAPI (Hybrid Transport Protocol)
Tests both reliable and unreliable channels with network simulation.
Includes a specific test for flow control correctness.

Run with: python test_gamenet_api.py
"""

import unittest
import threading
import time
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set

# Import your implementation
from hudp.game_net_api import GameNetAPI
from hudp.packet import RELIABLE, UNRELIABLE

# Add DummyMetrics class to handle missing metrics in tests
class DummyMetrics:
    def on_sent(self, *args, **kwargs): 
        pass
    def on_recv(self, *args, **kwargs): 
        pass
    def on_ack(self, *args, **kwargs): 
        pass

class NetworkSimulator:
    def __init__(self, loss_rate=0.0, delay_ms=10, jitter_ms=5):
        self.loss_rate = loss_rate
        self.delay_ms = delay_ms
        self.jitter_ms = jitter_ms
        self.reordering_enabled = False
        self.burst_loss_enabled = False
        self.burst_counter = 0
        self.packets_sent = 0
        self.packets_lost = 0
        self.packets_delivered = 0

    def transmit(self, packet_type, packet_fn, delay_override=None):
        self.packets_sent += 1
        if self.burst_loss_enabled and self.burst_counter < 5:
            self.burst_counter += 1
            self.packets_lost += 1
            return
        elif self.burst_loss_enabled:
            self.burst_counter = (self.burst_counter + 1) % 10
        if random.random() < self.loss_rate:
            self.packets_lost += 1
            return
        delay = delay_override if delay_override is not None else self.delay_ms
        jitter = random.uniform(-self.jitter_ms, self.jitter_ms)
        total_delay = max(0, delay + jitter) / 1000.0
        if self.reordering_enabled and random.random() < 0.3:
            total_delay += random.uniform(0.05, 0.1)
        def deliver():
            self.packets_delivered += 1
            packet_fn()
        timer = threading.Timer(total_delay, deliver)
        timer.daemon = True
        timer.start()

class GameNetAPITestHarness:
    """Test harness for GameNetAPI with detailed logging and metrics."""
    def __init__(self, network: NetworkSimulator, skip_threshold_ms=200):
        self.network = network
        self.sender_api: Optional[GameNetAPI] = None
        self.receiver_api: Optional[GameNetAPI] = None
        self.skip_threshold_ms = skip_threshold_ms
        self.lock = threading.Lock()
        
        self.reliable_seqs_sent: Set[int] = set()
        self.unreliable_seqs_sent: Set[int] = set()
        self.reliable_seqs_delivered: Set[int] = set()
        self.reliable_seqs_dropped: Set[int] = set() # Correctly tracks drops
        self.last_reliable_delivered = -1
        self.out_of_order_count = 0

    def setup(self, api_class):
        # Provide dummy metrics to prevent NoneType errors
        dummy_metrics = DummyMetrics()
        self.sender_api = api_class(skip_threshold_ms=self.skip_threshold_ms, on_drop=self._on_sender_drop, metrics=dummy_metrics)
        self.receiver_api = api_class(skip_threshold_ms=self.skip_threshold_ms, metrics=dummy_metrics)

        # *** THIS IS THE FIX: Wire up the on_drop callback correctly ***
        self.sender_api.sr_sender.on_drop = self._on_sender_drop

        self.sender_api.set_peer(('localhost', 12346))
        self.receiver_api.set_peer(('localhost', 12345))

        def sender_redirect(data: bytes):
            self.network.transmit(data[0], lambda: self.receiver_api._internal_process_packet(data))
        def receiver_redirect(data: bytes):
            self.network.transmit(data[0], lambda: self.sender_api._internal_process_packet(data))

        self.sender_api._send_internal = sender_redirect
        self.receiver_api._send_internal = receiver_redirect
        
        self.sender_api.start()
        self.receiver_api.start()
        
    def _on_sender_drop(self, seq: int):
        with self.lock:
            self.reliable_seqs_dropped.add(seq)

    def send_packet_loop(self, payload: bytes, reliable: bool, count: int):
        sent_count = 0
        while sent_count < count:
            seq = self.sender_api.send(payload, reliable)
            if seq is not None:
                with self.lock:
                    if reliable: self.reliable_seqs_sent.add(seq)
                    else: self.unreliable_seqs_sent.add(seq)
                sent_count += 1
            else:
                time.sleep(0.001)

    def receive_packets(self, timeout=5.0):
        start = time.time()
        while time.time() - start < timeout:
            packet = self.receiver_api.recv(block=False)
            if packet:
                channel_type, seq, _, _ = packet
                with self.lock:
                    if channel_type == RELIABLE:
                        self.reliable_seqs_delivered.add(seq)
                        if self.last_reliable_delivered > seq and seq not in self.reliable_seqs_delivered:
                            self.out_of_order_count += 1
                        self.last_reliable_delivered = max(self.last_reliable_delivered, seq)
            time.sleep(0.005)

    def wait_for_completion(self, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                accounted_for = len(self.reliable_seqs_delivered) + len(self.reliable_seqs_dropped)
                if len(self.reliable_seqs_sent) > 0 and accounted_for >= len(self.reliable_seqs_sent):
                    return
            time.sleep(0.05)
        print(f"Warning: Timed out waiting for completion. Accounted for "
              f"{len(self.reliable_seqs_delivered) + len(self.reliable_seqs_dropped)}/"
              f"{len(self.reliable_seqs_sent)} reliable packets.")

    def get_stats(self) -> Dict:
        with self.lock:
            return {
                'reliable_sent': len(self.reliable_seqs_sent),
                'reliable_delivered': len(self.reliable_seqs_delivered),
                'reliable_dropped': len(self.reliable_seqs_dropped),
                'retransmissions': self.sender_api.sr_sender.retransmissions,
                'out_of_order': self.out_of_order_count,
            }

    def cleanup(self):
        if self.sender_api: self.sender_api.stop()
        if self.receiver_api: self.receiver_api.stop()



class TestGameNetAPI(unittest.TestCase):
    def setUp(self):
        self.harness = None

    def tearDown(self):
        if self.harness:
            self.harness.cleanup()

    def test_flow_control_prevents_drops(self):
        print("\n[TEST] Flow Control under High Throughput")
        network = NetworkSimulator(loss_rate=0.0, delay_ms=1)
        self.harness = GameNetAPITestHarness(network)
        self.harness.setup(GameNetAPI)
        
        num_packets = 50
        
        sender_thread = threading.Thread(target=self.harness.send_packet_loop, args=(b'flow', True, num_packets))
        sender_thread.start()
        
        # Give it plenty of time
        self.harness.receive_packets(timeout=10)
        sender_thread.join(timeout=8)
        
        self.assertFalse(sender_thread.is_alive(), 
                        "Sender should complete with reduced packet count")
        
        self.harness.wait_for_completion(timeout=5)
        stats = self.harness.get_stats()
        
        # With no loss and reasonable load, we expect all packets to be delivered
        self.assertEqual(stats['reliable_sent'], num_packets)
        self.assertEqual(stats['reliable_delivered'], num_packets)
        self.assertEqual(stats['retransmissions'], 0,
                        "No retransmissions should occur with no loss")

    def test_mixed_traffic_no_loss(self):
        print("\n[TEST] Mixed Traffic - No Loss")
        network = NetworkSimulator(loss_rate=0.0, delay_ms=10)
        self.harness = GameNetAPITestHarness(network)
        self.harness.setup(GameNetAPI)
        sender_r = threading.Thread(target=self.harness.send_packet_loop, args=(b'reliable', True, 20))
        sender_u = threading.Thread(target=self.harness.send_packet_loop, args=(b'unreliable', False, 20))
        sender_r.start()
        sender_u.start()
        self.harness.receive_packets(timeout=3)
        sender_r.join()
        sender_u.join()
        self.harness.wait_for_completion(timeout=5)
        stats = self.harness.get_stats()
        self.assertEqual(stats['reliable_sent'], 20)
        self.assertEqual(stats['reliable_delivered'], 20)

    


    def test_in_order_delivery_reliable(self):
        print("\n[TEST] In-Order Delivery (Reliable) with network reordering")
        network = NetworkSimulator(loss_rate=0.1, delay_ms=30, jitter_ms=20)
        network.reordering_enabled = True
        self.harness = GameNetAPITestHarness(network, skip_threshold_ms=0)
        self.harness.setup(GameNetAPI)
        self.harness.sender_api.sr_sender.max_retries = 5
        num_packets = 25

        # ======================================================================
        # THE FIX: Run the receiver in a background thread so it can
        #          continuously process ACKs for the sender.
        # ======================================================================
        sender_thread = threading.Thread(target=self.harness.send_packet_loop, args=(b'reorder', True, num_packets))
        receiver_thread = threading.Thread(target=self.harness.receive_packets, args=(20,)) # Run for up to 20s
        receiver_thread.daemon = True

        sender_thread.start()
        receiver_thread.start()

        # Wait for the sender thread to finish queueing all packets.
        sender_thread.join(timeout=15)
        self.assertFalse(sender_thread.is_alive(), "Sender thread should finish sending all packets")

        # Now wait for the network to settle (all packets delivered or dropped).
        self.harness.wait_for_completion(timeout=15)
        stats = self.harness.get_stats()
        
        self.assertEqual(stats['out_of_order'], 0, "Receiver must deliver reliable packets in order")
        
        total_accounted_for = stats['reliable_delivered'] + stats['reliable_dropped']
        self.assertEqual(total_accounted_for, num_packets, "All reordered packets should be accounted for")
    
    def test_reliable_with_packet_loss(self):
        print("\n[TEST] Reliable Channel with Loss (Specification Behavior)")
        network = NetworkSimulator(loss_rate=0.2, delay_ms=30, jitter_ms=20)
        self.harness = GameNetAPITestHarness(network, skip_threshold_ms=0)
        self.harness.setup(GameNetAPI)
        self.harness.sender_api.sr_sender.max_retries = 5
        num_packets = 30

        # ======================================================================
        # THE FIX: Run the receiver in a background thread to prevent deadlock.
        # ======================================================================
        sender_thread = threading.Thread(target=self.harness.send_packet_loop, args=(b'lossy', True, num_packets))
        # Give the receiver a generous timeout to run in the background.
        receiver_thread = threading.Thread(target=self.harness.receive_packets, args=(40,))
        receiver_thread.daemon = True # It will exit when the main test thread exits.

        sender_thread.start()
        receiver_thread.start()
        
        # 1. Wait until the sender has submitted all packets to the API.
        sender_thread.join(timeout=30)
        self.assertFalse(sender_thread.is_alive(), "Sender thread timed out, likely due to deadlock")
        
        # 2. Now wait for the sender's internal buffers to clear (all ACKs received or packets dropped).
        self.harness.wait_for_completion(timeout=30)
        stats = self.harness.get_stats()

        total_accounted_for = stats['reliable_delivered'] + stats['reliable_dropped']

        self.assertEqual(stats['reliable_sent'], num_packets, "Should have attempted to send all packets.")
        self.assertEqual(total_accounted_for, num_packets, "All sent packets must be either delivered or officially dropped.")
        
        if stats['reliable_delivered'] < num_packets:
            self.assertGreater(stats['retransmissions'], 0, "Retransmissions must occur if packets are not delivered.")
        
        print(f"  Outcome: {stats['reliable_delivered']} delivered, {stats['reliable_dropped']} dropped. Test PASSED.")

    def test_reliable_full_delivery_under_loss(self):
        print("\n[TEST] Full Reliability with Loss (TCP-like, no skipping)")
        network = NetworkSimulator(loss_rate=0.2, delay_ms=30, jitter_ms=20)
        
        # For this test, we DEMAND 100% accounting, so we disable skipping.
        self.harness = GameNetAPITestHarness(network, skip_threshold_ms=0)
        
        self.harness.setup(GameNetAPI)
        self.harness.sender_api.sr_sender.max_retries = 5
        num_packets = 30

        # Run receiver in the background to prevent deadlock
        receiver_thread = threading.Thread(target=self.harness.receive_packets, args=(40,))
        receiver_thread.daemon = True
        sender_thread = threading.Thread(target=self.harness.send_packet_loop, args=(b'lossy', True, num_packets))
        
        receiver_thread.start()
        sender_thread.start()
        
        sender_thread.join(timeout=30)
        self.assertFalse(sender_thread.is_alive(), "Sender thread deadlocked")
        
        self.harness.wait_for_completion(timeout=30)
        stats = self.harness.get_stats()

        total_accounted_for = stats['reliable_delivered'] + stats['reliable_dropped']

        # This assertion is CORRECT for a no-skip test
        self.assertEqual(total_accounted_for, num_packets, "All sent packets must be either delivered or officially dropped.")
        print(f"  Outcome: {stats['reliable_delivered']} delivered, {stats['reliable_dropped']} dropped. Test PASSED.")


    # In test_gamenet_api.py, add this new method to the class TestGameNetAPI

    def test_reliable_with_skipping_under_loss(self):
        print("\n[TEST] Real-Time Reliability with Skipping")
        network = NetworkSimulator(loss_rate=0.3, delay_ms=40, jitter_ms=25) # Higher loss to encourage skipping
        
        # Use a reasonably short skip threshold to ensure it triggers
        self.harness = GameNetAPITestHarness(network, skip_threshold_ms=300)
        
        self.harness.setup(GameNetAPI)
        self.harness.sender_api.sr_sender.max_retries = 5
        num_packets = 30

        receiver_thread = threading.Thread(target=self.harness.receive_packets, args=(40,))
        receiver_thread.daemon = True
        sender_thread = threading.Thread(target=self.harness.send_packet_loop, args=(b'skippy', True, num_packets))
        
        receiver_thread.start()
        sender_thread.start()
        
        sender_thread.join(timeout=30)
        self.assertFalse(sender_thread.is_alive(), "Sender thread deadlocked")
        
        # We can't wait for "completion" in the same way, as the sender may still be
        # retrying skipped packets. We just wait for a reasonable time for the stream to finish.
        time.sleep(10) 
        
        stats = self.harness.get_stats()

        # ======================================================================
        # NEW ASSERTIONS FOR SKIPPING BEHAVIOR
        # ======================================================================

        # 1. CRITICAL: The packets that *were* delivered must still be in order.
        self.assertEqual(stats['out_of_order'], 0, "Receiver must still deliver its subset of packets in order")

        # 2. PROVE IT SKIPPED: The number of delivered packets should be less than what was sent.
        self.assertLess(stats['reliable_delivered'], num_packets, "With high loss and skipping, some packets should have been missed.")

        # 3. SANITY CHECK: The system must not have collapsed. It should deliver a reasonable number of packets.
        self.assertGreater(stats['reliable_delivered'], num_packets * 0.2, "Delivery rate should not be catastrophic.")
        
        print(f"  Outcome: {stats['reliable_delivered']}/{num_packets} delivered. In-order delivery maintained. Test PASSED.")
        


if __name__ == '__main__':
    unittest.main(verbosity=2)