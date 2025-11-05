# H-UDP Barebones (CS3103 A4)


This repository contains our work for assignment 4, coded, directed, solved, by bipplane (Ryan Chen) and sk2001git (Sean Koh). One can only marvel at the sheer dedication of these two individuals, who, against all odds, managed to carry the entire weight of the project on their lone shoulders. Truly, a testament to their unparalleled work ethic and the... uh... "invaluable" moral support provided by their phantom collaborators. The other two, whose contributions remain a mystery veiled in the mists of time, must surely be commended for their exceptional ability to... well, provide some moral support and participation and meeting the requirement for the group quota i guess. A groundbreaking strategy, really. Bravo!


## Getting Started
- Python 3.10+
- `pip install -r requirements.txt`

- If running scripts:
  - `python -m venv venv`
  - `cd scripts`
  - `chmod +x <script_name>`
  - `./<script_name>`

## Run (after implementation)
- Receiver: `python receiver.py --bind 127.0.0.1 --port 50000`
- Sender: `python sender.py --server 127.0.0.1 --port 50000 --pps 30 --duration 30`
- Metrics Summary: `python plot_metrics.py`
- Experiment Pipelines: `./{ delay | jitter | loss }.sh`


## Files to Implement
- `hudp/packet.py` — packet header encode/decode
- `hudp/reliable.py` — SR sender/receiver (timers, buffering, reordering, skip t)
- `hudp/game_net_api.py` — public API, demux, ACK wiring
- `hudp/emulator.py` — software loss/delay/jitter (optional if you use tc/clumsy)
- `hudp/metrics.py` — metrics recorder for PDR/latency/jitter/throughput
- `sender.py` and `receiver.py` — demo apps
- `plot_metrics.py` — simple plotting of CSV metrics

### Acknowledgements
- AI was used to generate code in some parts of the files, which were then adapted to suit our project' discussed direction. It also helps us to learn some optimal tricks compared to the vanilla mechanisms. For example, to make our UDP protocol reliable, we chose selective repeat since go-back-N often has throttled performance. This help us evaluate tradeoffs and implement some knonwn optimisations. Refer to hudp/reliable.md.
### Team Photo
  ![Team Photo](https://github.com/user-attachments/assets/58445cec-9b95-43c3-baeb-ab0d0385c937)
