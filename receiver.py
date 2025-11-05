# receiver.py
from __future__ import annotations
import argparse
import time
from hudp.packet import RELIABLE, UNRELIABLE, now_ms
from hudp.game_net_api import GameNetAPI
from hudp.packet import RELIABLE, now_ms
from hudp.metrics import MetricsRecorder



def main():
    parser = argparse.ArgumentParser(description="H-UDP Receiver (stub)")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind IP")
    parser.add_argument("--port", type=int, required=True, help="Listen UDP port")
    parser.add_argument("--metrics", default="metrics_receiver.csv", help="Output CSV for metrics")
    parser.add_argument("--t_skip", type=int, default=200, help="Skip threshold t (ms) for reliable holes")
    args = parser.parse_args()

    mr = MetricsRecorder(role="receiver")
    api = GameNetAPI(bind_addr=(args.bind, args.port), skip_threshold_ms=args.t_skip)
    api.start()
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
            
            # Calculate actual bytes including header (7 bytes)
            total_bytes = len(payload) + 7
            mr.on_recv(channel, seq_num, total_bytes, ts)  # Pass sequence and actual bytes
            
            ch_type = "RELIABLE" if channel == RELIABLE else "UNRELIABLE"
            latency = now_ms() - ts
            if ch_type == "UNRELIABLE":
                print(f"({ch_type}) Seq: {seq_num}, Latency: {latency}ms, Payload: {payload.decode('utf-8')}")
            elif ch_type == "RELIABLE":
                print(f"( {ch_type} ) Seq: {seq_num}, Latency: {latency}ms, Payload: {payload.decode('utf-8')}")
    except KeyboardInterrupt:
        print("\nReceiver shutting down.")
    finally:
        api.stop()
        mr.export_csv(args.metrics)
        summary = mr.get_summary()
        print("\n--- Receiver Summary ---")
        
        # Print Channel 0 (Reliable) first, then Channel 1 (Unreliable)
        for ch in [RELIABLE, UNRELIABLE]:
            if ch in summary:
                stats = summary[ch]
                ch_name = "Reliable" if ch == RELIABLE else "Unreliable"
                print(f"  Channel {ch} ({ch_name}):")
                print(f"    Packets Received: {stats['packets_received']}")
                print(f"    Average Latency: {stats['avg_latency_ms']} ms")
                print(f"    Jitter: {stats['jitter_ms']} ms")
                print(f"    Throughput: {stats['throughput_kbps']} kbps")
            
        print(f"Metrics data exported to {args.metrics}")
        print("Note: For Packet Delivery Ratio, use plot_metrics.py with sender data")
        print("------------------------\n")

if __name__ == "__main__":
    main()
