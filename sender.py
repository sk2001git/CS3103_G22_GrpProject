# sender.py

from __future__ import annotations
import argparse
import time
import os
import random

from hudp.game_net_api import GameNetAPI
from hudp.packet import RELIABLE, UNRELIABLE, now_ms
from hudp.emulator import UDPEngineEmulator
from hudp.metrics import MetricsRecorder

def main():
    parser = argparse.ArgumentParser(description="H-UDP Sender (stub)")
    parser.add_argument("--server", required=True, help="Receiver IP or hostname")
    parser.add_argument("--port", type=int, required=True, help="Receiver UDP port")
    parser.add_argument("--pps", type=int, default=30, help="Packets per second")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--loss", type=float, default=0.0, help="Sender-side emulator loss [0..1]")
    parser.add_argument("--delay", type=int, default=0, help="Sender-side emulator base delay ms")
    parser.add_argument("--jitter", type=int, default=0, help="Sender-side emulator jitter ms")
    parser.add_argument("--metrics", default="metrics_sender.csv", help="Output CSV for metrics")
    args = parser.parse_args()

    mr = MetricsRecorder(role="sender")
    api = GameNetAPI(metrics=mr)
    api.set_peer((args.server, args.port))

    if args.loss > 0 or args.delay > 0 or args.jitter > 0:
        print(f"Attaching emulator: loss={args.loss}, delay={args.delay}, jitter={args.jitter}")
        emulator = UDPEngineEmulator(
            loss=args.loss,
            delay_ms=args.delay,
            jitter_ms=args.jitter
        )
        api.attach_emulator(emulator)

    api.start()
    print(f"Sending {args.pps} packets/sec for {args.duration} seconds to {args.server}:{args.port}")

    start_time = time.time()
    packet_count = 0
    try:
        while time.time() - start_time < args.duration:
            # Check if peer has signaled shutdown (zero window)
            if api.is_peer_shutdown():
                print("\nPeer has shut down (received zero-window signal). Stopping sender.")
                break

            is_reliable = random.random() < 0.2
            channel = RELIABLE if is_reliable else UNRELIABLE

            payload = f"packet_{packet_count}".encode('utf-8')

            # Send and get sequence number
            seq_num = api.send(payload, reliable=is_reliable)
            
            if seq_num is None:
                # Window is full, check if peer shut down
                if api.is_peer_shutdown():
                    print("\nPeer has shut down while window was full. Stopping sender.")
                    break
                # Otherwise just skip this packet and continue
                time.sleep(0.01)
                continue

            # Calculate actual bytes including header (7 bytes)
            total_bytes = len(payload) + 7
            mr.on_sent(channel, seq_num, total_bytes)  # Pass sequence and actual bytes

            packet_count += 1
            time.sleep(1.0 / args.pps)

    except KeyboardInterrupt:
        print("\nSender shutting down.")
    finally:
        print("Stopping API and generating report...")
        api.stop()

        mr.export_csv(args.metrics)

        # Read the CSV to count unique sequences (like plot_metrics does)
        import pandas as pd
        try:
            df_send = pd.read_csv(args.metrics)
            
            # Count unique sequences per channel
            reliable_sent = df_send[df_send['channel'] == 0]['sequence'].nunique()
            unreliable_sent = df_send[df_send['channel'] == 1]['sequence'].nunique()
            
            # Get ACK count from metrics
            summary = mr.get_summary()
            reliable_acked = summary[0]['packets_received'] if 0 in summary else 0
            
        except Exception as e:
            print(f"Error analyzing metrics: {e}")
            # Fallback to old method
            summary = mr.get_summary()
            reliable_sent = summary[0]['packets_sent'] if 0 in summary else 0
            unreliable_sent = summary[1]['packets_sent'] if 1 in summary else 0
            reliable_acked = summary[0]['packets_received'] if 0 in summary else 0

        print("\n--- Sender Summary ---")
        print(f"  Channel 0 (Reliable):")
        print(f"    Unique Packets Sent: {reliable_sent}")
        print(f"    Unique ACKs Received: {reliable_acked}")
        if reliable_sent > 0:
            pdr = (reliable_acked / reliable_sent * 100.0)
            print(f"    ACK-based Delivery Ratio: {pdr:.2f}%")
        else:
            print(f"    ACK-based Delivery Ratio: N/A")
        
        print(f"  Channel 1 (Unreliable):")
        print(f"    Unique Packets Sent: {unreliable_sent}")
        print(f"    Packet Delivery Ratio: N/A (use receiver metrics)")
        print("----------------------\n")
        
if __name__ == "__main__":
    main()
