import time
import threading
import numpy as np
import matplotlib.pyplot as plt
from test_gamenet_api import GameNetAPITestHarness, NetworkSimulator # Import from your test file
from hudp.game_net_api import GameNetAPI

def run_experiment(loss_rate, duration_sec=30, packet_rate=50):
    """Runs a single experiment and returns the harness with collected data."""
    print(f"\n--- Running Experiment: {loss_rate*100}% packet loss ---")
    
    network = NetworkSimulator(loss_rate=loss_rate, delay_ms=30, jitter_ms=15)
    harness = GameNetAPITestHarness(network, skip_threshold_ms=200)
    harness.setup(GameNetAPI)

    num_packets = duration_sec * packet_rate
    packet_interval = 1.0 / packet_rate

    def sender_task():
        for i in range(num_packets):
            # Send a mix of reliable and unreliable packets
            is_reliable = random.random() > 0.5
            payload = f"R_{i}".encode() if is_reliable else f"U_{i}".encode()
            
            # This loop ensures we send at the correct rate even if the window is full
            while harness.sender_api.send(payload, is_reliable) is None:
                time.sleep(0.001)
            time.sleep(packet_interval)

    sender_thread = threading.Thread(target=sender_task)
    sender_thread.start()
    
    # Let the receiver run for the whole duration + a grace period
    harness.receive_packets(timeout=duration_sec + 5)
    sender_thread.join()
    harness.wait_for_completion(timeout=5)
    
    harness.cleanup()
    return harness

def generate_report(harness: GameNetAPITestHarness, condition_name: str):
    """Calculates metrics and generates plots for a single experiment."""
    stats = harness.get_stats()
    
    # --- Calculate Final Metrics ---
    reliable_pdr = (stats['reliable_delivered'] / stats['reliable_sent'] * 100) if stats['reliable_sent'] > 0 else 0
    
    latency_avg = np.mean(harness.latency_samples) if harness.latency_samples else 0
    jitter_avg = np.mean(harness.jitter_samples) if harness.jitter_samples else 0
    
    print("\n--- Results for: " + condition_name + " ---")
    print(f"Reliable PDR:         {reliable_pdr:.2f}%")
    print(f"Average Latency:      {latency_avg:.2f} ms")
    print(f"Average Jitter:       {jitter_avg:.2f} ms")
    print(f"Total Retransmissions: {stats['retransmissions']}")
    
    # --- Generate Plots ---
    plt.figure(figsize=(12, 5))
    
    plt.subplot(1, 2, 1)
    plt.hist(harness.latency_samples, bins=50, color='skyblue', edgecolor='black')
    plt.title(f'Latency Distribution ({condition_name})')
    plt.xlabel('One-way Latency (ms)')
    plt.ylabel('Packet Count')
    plt.axvline(latency_avg, color='r', linestyle='dashed', linewidth=1, label=f'Avg: {latency_avg:.2f}ms')
    plt.legend()
    
    plt.subplot(1, 2, 2)
    plt.plot(harness.jitter_samples, alpha=0.7)
    plt.title(f'Jitter Over Time ({condition_name})')
    plt.xlabel('Received Packet Sequence')
    plt.ylabel('Jitter (ms)')
    
    plt.tight_layout()
    plt.savefig(f"report_{condition_name.replace(' ', '_')}.png")
    plt.show()


if __name__ == '__main__':
    # Run two experiments as required by the specification
    low_loss_harness = run_experiment(loss_rate=0.02) # 2% loss
    high_loss_harness = run_experiment(loss_rate=0.10) # 10% loss

    # Generate the output for each
    generate_report(low_loss_harness, "Low Loss Condition (2%)")
    generate_report(high_loss_harness, "High Loss Condition (10%)")