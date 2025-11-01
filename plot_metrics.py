# plot_metrics.py (bare-bones stub)

from __future__ import annotations
import argparse
import pandas as pd 

# import pandas as pd
# import matplotlib.pyplot as plt

def main():
    parser = argparse.ArgumentParser(description="Plot H-UDP metrics (stub)")
    parser.add_argument("csv_path", help="Path to metrics CSV")
    parser.add_argument("--out_prefix", default="metrics", help="Output image prefix")
    args = parser.parse_args()

    # TODO:
    # 1) Read CSV with pandas.
    # 2) Produce separate bar charts (matplotlib) for:
    #    - throughput_bps
    #    - pdr_percent
    #    - avg_latency_ms
    #    - jitter_ms
    # 3) Save figures as f\"{args.out_prefix}_throughput.png\" etc.
    raise NotImplementedError("plot_metrics.main: implement CSV read and plotting")

if __name__ == "__main__":
    main()
