import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import argparse

SENDER_NAME = "sender"
RECEIVER_NAME = "receiver"


# --------------------------------------------
# Helper functions
# --------------------------------------------

def extract_variable_value(folder_name, experiment_name):
    """
    Extracts the numeric experiment variable (e.g., 0.1 from 'loss_0.1').
    """
    match = re.search(rf"{experiment_name}_([\d\.]+)", folder_name)
    value = float(match.group(1)) if match else None
    if value and value > 1: 
        return int(value)
    return value

def load_metrics(base_dir, role, experiment_name, value):
    """
    Load a metrics CSV (sender or receiver) for a given experiment and variable value.
    """
    exp_dir = os.path.join(base_dir, f"{experiment_name}_{value}")
    metrics_file = os.path.join(
        exp_dir, f"{role}_metrics_{experiment_name}_{value}.csv"
    )
    if not os.path.exists(metrics_file):
        print(f"[WARN] Missing {role} metrics for {experiment_name}={value}")
        return None
    try:
        df = pd.read_csv(metrics_file)
        return df
    except Exception as e:
        print(f"[ERROR] Failed to load {metrics_file}: {e}")
        return None

def compute_summary(sender_df:pd.DataFrame, receiver_df:pd.DataFrame):
    results = {}
    results["reliability"] = compute_reliability(sender_df, receiver_df)
    results["sender_reliable_latency"] = compute_latency(sender_df[sender_df["channel"] == 0])
    results["receiver_reliable_latency"] = compute_latency(receiver_df[receiver_df["channel"] == 0])
    results["sender_unreliable_latency"] = compute_latency(sender_df[sender_df["channel"] == 1])
    results["receiver_unreliable_latency"] = compute_latency(receiver_df[receiver_df["channel"] == 1])
    results["throughput"] = compute_throughput(receiver_df)
    window = compute_reliable_window(sender_df, receiver_df)
    results["window"] = window 
    results["inverse_window"] = sender_df["timestamp_s"].max() - window
    return results

def compute_reliability(sender_df:pd.DataFrame, receiver_df:pd.DataFrame, window=None):
    if window:
        sender_df = sender_df[sender_df["timestamp_s"] < window]
    sender_df = sender_df[sender_df["channel"] == 0]
    receiver_df = receiver_df[receiver_df["channel"] == 0]

    sent_sequences = set(sender_df["sequence"].unique())
    received_sequences = set(receiver_df["sequence"].unique())
    received_sequences = received_sequences.intersection(sent_sequences) 

    n_sent = len(sent_sequences)
    n_received = len(received_sequences)

    if n_sent == 0:
        return 1.0
    return n_received / n_sent

def compute_latency(df:pd.DataFrame):
    return df["latency_ms"].mean()

def compute_throughput(receiver_df:pd.DataFrame):
    reliable = receiver_df[receiver_df["channel"] == 0]
    unreliable = receiver_df[receiver_df["channel"] == 1]
    first_received = reliable.sort_values("timestamp_s").drop_duplicates(subset="sequence", keep="first")
    reliable_bytes = first_received["bytes"].sum()
    unreliable_bytes = unreliable["bytes"].sum()
    total_bytes = reliable_bytes + unreliable_bytes
    duration = reliable["timestamp_s"].max()
    if duration == 0:
        return 0.0
    return total_bytes / duration

def compute_reliable_window(sender_df: pd.DataFrame, receiver_df: pd.DataFrame):
    low = 0.0
    high = sender_df["timestamp_s"].max()   # upper bound = total experiment time
    eps = 0.01  # binary search tolerance (seconds)
    
    if compute_reliability(sender_df, receiver_df, high) >= 1.0:
        return high
    
    while high - low > eps:
        mid = (low + high) / 2
        rel = compute_reliability(sender_df, receiver_df, mid)
        if rel < 1.0:
            high = mid
        else:
            low = mid

    return round(low, 3)

def plot_experiment(experiment_name, df_summary, base_dir):
    x = df_summary["variable"]
    plt.figure(figsize=(12, 10))

    # Sender Latency
    plt.subplot(4, 1, 1)
    plt.plot(x, df_summary["sender_reliable_latency"], "o-", color="tab:blue", label="Sender Reliable Latency (s)")
    plt.plot(x, df_summary["receiver_reliable_latency"], "s--", color="tab:green", label="Receiver Reliable Latency (s)")
    plt.plot(x, df_summary["sender_unreliable_latency"], "o-", color="tab:orange", label="Sender Unreliable Latency (s)")
    plt.plot(x, df_summary["receiver_unreliable_latency"], "s--", color="tab:red", label="Receiver Unreliable Latency (s)")
    plt.ylabel("Latency (s)")
    plt.grid(True)
    plt.legend()
    
    # Throughput
    plt.subplot(4, 1, 2)
    plt.plot(x, df_summary["throughput"], "o-", color="tab:orange", label="Throughput (B/s)")
    plt.ylabel("Throughput (B/s)")
    plt.grid(True)
    plt.legend()

    # Reliable Window
    plt.subplot(4, 1, 3)
    plt.plot(x, df_summary["inverse_window"], "s--", color="tab:purple", label="Length of tail unreliability(s)")
    plt.xlabel(experiment_name.capitalize())
    plt.ylabel("Length of tail unreliability(s)")
    plt.grid(True)
    plt.legend()

    # Reliability
    plt.subplot(4, 1, 4)
    plt.plot(x, df_summary["reliability"], "o-", color="tab:red", label="Reliability")
    plt.xlabel(experiment_name.capitalize())
    plt.ylabel("Reliability")
    plt.grid(True)
    plt.legend()

    plt.tight_layout()
    plt.suptitle(f"{experiment_name.capitalize()} Experiment Results", fontsize=14, y=1.02)
    plt.subplots_adjust(top=0.92)

    # Save figure
    out_path = os.path.join(base_dir, f"{experiment_name}_summary.png")
    plt.savefig(out_path, dpi=300)
    print(f"[INFO] Saved plot to {out_path}")
    plt.close()

# --------------------------------------------
# Main
# --------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--EXP_NAME", type=str, required=True, help="Experiment name (loss/delay/jitter)")
    parser.add_argument("--BASE_DIR", type=str, required=True, help="Base directory of experiments")
    args = parser.parse_args()

    experiment_name = args.EXP_NAME
    base_dir = args.BASE_DIR


    experiment_dir = base_dir
    if not os.path.exists(experiment_dir):
        print(f"[WARN] Directory not found: {experiment_dir}")
        return

    subdirs = sorted([d for d in os.listdir(experiment_dir) if os.path.isdir(os.path.join(experiment_dir, d))])

    results = {
        "variable": [],
        "sender_reliable_latency": [],
        "receiver_reliable_latency": [],
        "sender_unreliable_latency": [],
        "receiver_unreliable_latency": [],
        "throughput": [],
        "reliability": [],
        "window": [],
        "inverse_window": []
    }

    for folder in subdirs:
        value = extract_variable_value(folder, experiment_name)
        if value is None:
            continue

        sender_df = load_metrics(base_dir, SENDER_NAME, experiment_name, value)
        receiver_df = load_metrics(base_dir, RECEIVER_NAME, experiment_name, value)
        if sender_df is None or receiver_df is None:
            continue

        summary = compute_summary(sender_df, receiver_df)
        if summary:
            results["variable"].append(value)
            results["sender_reliable_latency"].append(summary["sender_reliable_latency"])
            results["receiver_reliable_latency"].append(summary["receiver_reliable_latency"])
            results["sender_unreliable_latency"].append(summary["sender_unreliable_latency"])
            results["receiver_unreliable_latency"].append(summary["receiver_unreliable_latency"])
            results["throughput"].append(summary["throughput"])
            results["reliability"].append(summary["reliability"])
            results["window"].append(summary["window"])
            results["inverse_window"].append(summary["inverse_window"])

    if not results["variable"]:
        print(f"[WARN] No valid data found for experiment '{experiment_name}'")
        return

    df_summary = pd.DataFrame(results).sort_values("variable")
    print(f"\n=== {experiment_name.upper()} SUMMARY ===")
    print(df_summary)

    plot_experiment(experiment_name, df_summary, base_dir)

if __name__ == "__main__":
    main()
