# plot_metrics.py
from __future__ import annotations
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import os


def compute_metrics(sender_csv: str, receiver_csv: str):
    """
    Compute performance metrics from sender & receiver CSVs.
    Metrics:
        1. Latency (ms)
        2. Jitter (ms)
        3. Throughput (kbps)
        4. Packet Delivery Ratio (%)
    """
    df_send = pd.read_csv(sender_csv)
    df_recv = pd.read_csv(receiver_csv)

    # Compute duration
    duration_s = df_recv["timestamp_s"].max() - df_recv["timestamp_s"].min()
    if duration_s <= 0:
        duration_s = 1.0

    metrics = []

    for ch in sorted(set(df_send["channel"]).union(set(df_recv["channel"]))):
        sent_df = df_send[df_send["channel"] == ch]
        recv_df = df_recv[df_recv["channel"] == ch]

        sent_count = len(sent_df)
        recv_count = len(recv_df)
        pdr = (recv_count / sent_count * 100.0) if sent_count > 0 else 0.0

        avg_latency = recv_df["latency_ms"].mean() if recv_count > 0 else 0.0
        jitter = recv_df["latency_ms"].std() if recv_count > 0 else 0.0

        total_bytes = recv_df["bytes"].sum()
        throughput_kbps = (total_bytes * 8 / 1000) / duration_s

        metrics.append({
            "channel": ch,
            "packets_sent": sent_count,
            "packets_received": recv_count,
            "packet_delivery_ratio_%": round(pdr, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "jitter_ms": round(jitter, 2),
            "throughput_kbps": round(throughput_kbps, 3),
        })

    return pd.DataFrame(metrics)


def plot_all_metrics(df: pd.DataFrame, out_path: str):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    fig.suptitle("H-UDP Performance Metrics Summary", fontsize=14, fontweight="bold")

    metrics_info = [
        ("avg_latency_ms", "Average Latency (ms)"),
        ("jitter_ms", "Jitter (ms)"),
        ("throughput_kbps", "Throughput (kbps)"),
        ("packet_delivery_ratio_%", "Packet Delivery Ratio (%)"),
    ]

    for ax, (metric, ylabel) in zip(axes.flat, metrics_info):
        ax.bar(df["channel"].astype(str), df[metric], color="steelblue")
        ax.set_xlabel("Channel")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.6)
        for i, v in enumerate(df[metric]):
            ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(out_path)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot combined H-UDP performance metrics")
    parser.add_argument("--sender", default="metrics_sender.csv", help="Sender metrics CSV path")
    parser.add_argument("--receiver", default="metrics_receiver.csv", help="Receiver metrics CSV path")
    parser.add_argument("--out", default="metrics_summary.png", help="Output combined plot filename")
    args = parser.parse_args()

    results_dir = os.path.join(os.getcwd(), "results")
    os.makedirs(results_dir, exist_ok=True)

    sender_path = os.path.join(results_dir, os.path.basename(args.sender))
    receiver_path = os.path.join(results_dir, os.path.basename(args.receiver))
    out_path = os.path.join(results_dir, os.path.basename(args.out))

    missing = []
    if not os.path.exists(sender_path):
        missing.append(sender_path)
    if not os.path.exists(receiver_path):
        missing.append(receiver_path)

    if missing:
        print("Error: The following required CSV file(s) were not found:")
        for path in missing:
            print(f"  - {path}")
        print("\nPlease ensure both sender and receiver metrics CSVs are exported under the 'results/' folder.")
        return

    df_metrics = compute_metrics(sender_path, receiver_path)
    print("\n=== Computed Metrics Summary ===")
    print(df_metrics.to_string(index=False))
    print()

    plot_all_metrics(df_metrics, out_path)
    print(f"Combined metrics summary plot saved to: {out_path}")


if __name__ == "__main__":
    main()
