from __future__ import annotations
import argparse
import sys
import signal

from hudp.game_net_api import GameNetAPI
from hudp.packet import RELIABLE, UNRELIABLE, now_ms
from hudp.metrics import MetricsRecorder



def main():
    parser = argparse.ArgumentParser(description="H-UDP Receiver (stub)")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind IP")
    parser.add_argument("--port", type=int, required=True, help="Listen UDP port")
    parser.add_argument("--metrics", default="metrics_receiver.csv", help="Output CSV for metrics")
    parser.add_argument("--t_skip", type=int, default=200, help="Skip threshold t (ms) for reliable holes")
    args = parser.parse_args()

    api = GameNetAPI(bind_addr=(args.bind, args.port), skip_threshold_ms=args.t_skip)
    api.start()
    mr = MetricsRecorder()
    print(f"Receiver listening on {args.bind}:{args.port}")


    def shutdown_handler(sig, frame):
        print("\nReceiver shutting down (signal received).")
        try:
            api.stop()
            mr.export_csv(args.metrics) 
            summary = mr.get_summary()  
            print("\n--- Receiver Summary ---")
            for ch, stats in summary.items():
                ch_name = "Reliable" if ch == RELIABLE else "Unreliable"
                print(f"  Channel {ch} ({ch_name}):")
                for key, val in stats.items():
                    print(f"    {key.replace('_', ' ').title()}: {val}")
            print(f"Metrics data exported to {args.metrics}")
            print("------------------------\n")
            sys.stdout.flush()
        except Exception as e:
            print(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)


    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        while True:
            channel, seq_num, ts, payload = api.recv(block=True)
            mr.on_recv(channel, len(payload) + 7, 0, ts)  # 7 bytes for header
            ch_type = "RELIABLE" if channel == RELIABLE else "UNRELIABLE"
            latency = now_ms() - ts
            print(f"[{ch_type}] Seq: {seq_num}, Latency: {latency}ms, Payload: {payload.decode('utf-8')}")

    except KeyboardInterrupt:
        print("\nReceiver shutting down.")
    finally:
        shutdown_handler(None, None)

if __name__ == "__main__":
    main()
