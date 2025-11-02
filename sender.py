# sender.py (bare-bones stub)

from __future__ import annotations
import argparse
import time
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

    mr = MetricsRecorder()
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
            is_reliable = random.random() < 0.2 # simulate that 20% of packets are reliable
            channel = RELIABLE if is_reliable else UNRELIABLE

            payload = f"packet_{packet_count}".encode('utf-8')

            num_bytes = api.send(payload, reliable=is_reliable)
            mr.on_sent(channel, num_bytes)

            packet_count += 1
            time.sleep(1.0 / args.pps)

    except KeyboardInterrupt:
        print("\nSender shutting down.")
    finally:
        print("Stopping API and generating report...")
        api.stop()

        summary = mr.get_summary()
        print("\n--- Sender Summary ---")
        for ch, stats in summary.items():
            ch_name = "Reliable" if ch == RELIABLE else "Unreliable"
            print(f"  Channel {ch} ({ch_name}):")
            sent = stats.get('packets_sent', 0)
            acked = stats.get('packets_received', 'N/A')
            pdr = stats.get('packet_delivery_ratio_%', 'N/A')
            print(f"    Packets Sent: {sent}")
            if ch_name == "Reliable": print(f"    Packets Acked: {acked}")
            if isinstance(pdr, (int, float)) and ch_name == "Reliable":
                print(f"    Packet Delivery Ratio %: {pdr}%")
            elif ch_name == "Reliable":
                print(f"    Packet Delivery Ratio %: {pdr}")
        print("----------------------\n")

if __name__ == "__main__":
    main()
