# sender.py (bare-bones stub)

from __future__ import annotations
import argparse
import time
import random

# from hudp.game_net_api import GameNetAPI
# from hudp.packet import RELIABLE, UNRELIABLE, now_ms
# from hudp.emulator import UDPEngineEmulator
# from hudp.metrics import MetricsRecorder

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

    # TODO:
    # 1) Construct GameNetAPI(), set_peer((args.server, args.port)), optionally attach UDPEngineEmulator.
    # 2) Start API. Create MetricsRecorder. Ensure channel stats for reliable/unreliable (0/1).
    # 3) Loop until duration: send payloads at target PPS, randomly mark reliable/unreliable,
    #    and record mr.on_sent(channel, nbytes).
    # 4) Optionally drain recv() for any app-level acks or messages you want to track.
    # 5) Stop API; export metrics to args.metrics.
    raise NotImplementedError("sender.main: implement send loop, metrics, and cleanup")

if __name__ == "__main__":
    main()
