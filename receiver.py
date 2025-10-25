# receiver.py (bare-bones stub)

from __future__ import annotations
import argparse
import time

# from hudp.game_net_api import GameNetAPI
# from hudp.packet import RELIABLE, UNRELIABLE, now_ms
# from hudp.metrics import MetricsRecorder

def main():
    parser = argparse.ArgumentParser(description="H-UDP Receiver (stub)")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind IP")
    parser.add_argument("--port", type=int, required=True, help="Listen UDP port")
    parser.add_argument("--metrics", default="metrics_receiver.csv", help="Output CSV for metrics")
    parser.add_argument("--t_skip", type=int, default=200, help="Skip threshold t (ms) for reliable holes")
    args = parser.parse_args()

    # TODO:
    # 1) Construct GameNetAPI(bind_addr=(args.bind, args.port), skip_threshold_ms=args.t_skip).
    # 2) Start API. Create MetricsRecorder and ensure channels (0/1).
    # 3) Loop recv(block=True): returns (channel, seq_or_none, header_ts_ms, payload).
    #    Compute one-way latency as now_ms() - header_ts_ms (if clocks are comparable),
    #    then mr.on_recv(channel, nbytes, one_way_ms).
    # 4) Graceful shutdown on KeyboardInterrupt: stop API and mr.export_csv(args.metrics).
    raise NotImplementedError("receiver.main: implement receive loop and metrics export")

if __name__ == "__main__":
    main()
