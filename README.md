# H-UDP Barebones (CS3103 A4)


This repository contains **stubs** for the H-UDP project. All core methods raise
`NotImplementedError` and include guidance comments. Implement these in your team.


## Getting Started
- Python 3.10+
- `pip install -r requirements.txt`


## Run (after implementation)
- Receiver: `python receiver.py --bind 127.0.0.1 --port 50000`
- Sender: `python sender.py --server 127.0.0.1 --port 50000 --pps 30 --duration 30`


## Files to Implement
- `hudp/packet.py` — packet header encode/decode
- `hudp/reliable.py` — SR sender/receiver (timers, buffering, reordering, skip t)
- `hudp/game_net_api.py` — public API, demux, ACK wiring
- `hudp/emulator.py` — software loss/delay/jitter (optional if you use tc/clumsy)
- `hudp/metrics.py` — metrics recorder for PDR/latency/jitter/throughput
- `sender.py` and `receiver.py` — demo apps
- `plot_metrics.py` — simple plotting of CSV metrics

### Acknowledgements
- AI was used to generate the bare bones file with notImplementedErrors to provide a collaborative space for team work on functional obligation and integration

### Team Photo
  ![Team Photo](https://github.com/user-attachments/assets/58445cec-9b95-43c3-baeb-ab0d0385c937)
