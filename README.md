# H-UDP Group 22 (CS3103 A4)


This repository contains our source code for assignment 4. Below are the instructions for compiling and running the application. Our designed protocol is meant to be a solution that can meet the demands of real-time applications (e.g. multiplayer games) by providing two communication channel types that run over a single UDP socket. This includes: a reliable channel for critical data, and an unreliable channel for non-essential updates.

Key Features include:
* A GameNetAPI that manages both reliable and unreliable data transmission.
* A robust Selective Repeat (SR) protocol to efficiently handle and buffer out-of-order packets to minimise retransmission count.
* A packet skip mechanism wheerby the receiver "skips" an expected reliable packet if it doesn't arrive after some time, preventing infinite-waiting of this missing packet.
* A configurable simulation of real-world network conditions such as packet loss, latency, and jitter.


## Getting Started
- This program requires Python 3.10+
- Clone the repository: `git clone <your-repo-url>`
- Cd into repository: `cd <repo-directory>`
- (Recommended) Create a venv: `python -m venv venv`
- Activate venv:
  - For Windows: `venv\Scripts\activate`
  - For Mac/Linux: `source venv/bin/activate`

- Install required dependencies `pip install -r requirements.txt`

- If running scripts:
  - `cd scripts`
  - `chmod +x <script_name>`
  - `./<script_name>`

## Run (after implementation)
1. Start receiver: `python receiver.py --bind 127.0.0.1 --port 50000`

* --port: UDP port to listen on (required).
* --bind <ip_address>: IP address to bind to (default: 0.0.0.0).
* --metrics <filename.csv>: File to save metrics data to (default: metrics_receiver.csv).
* --t_skip <ms>: Timeout (in milliseconds) for skipping a lost reliable packet (default: 200).


2. Start sender pointing to IP of receiver: `python sender.py --server 127.0.0.1 --port 50000 --pps 30 --duration 30`

* --server <ip_address>: IP address of server, to be set with the same IP as receiver (required0.
* --pps: Packets to send per second.
* --duration <secs>: Period that sender actively sends packets.
* --loss <% number>: Simulation of packet loss (e.g. 0.1 for 10% loss).
* --delay: Base delay to send a packet (in milliseconds).
* --jitter: Variation in delay between packets sent (in milliseconds).

3. Stop receiver: `Ctrl + C` keyboard interrupt
4. Metrics Summary: `python plot_metrics.py`

- Experiment Pipelines: `./{ delay | jitter | loss }.sh`


### Acknowledgements
- AI was used to generate code in some parts of the files, which were then adapted to suit our project' discussed direction. It also helps us to learn some optimal tricks compared to the vanilla mechanisms. For example, to make our UDP protocol reliable, we chose selective repeat since go-back-N often has throttled performance. This help us evaluate tradeoffs and implement some knonwn optimisations. Refer to hudp/reliable.md.
