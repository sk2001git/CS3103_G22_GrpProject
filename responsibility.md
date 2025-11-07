## Areas of Responsbility
We acknowledge that all members have an equally important role in their contribution, in both code and report writing and we have successfully divided work equally.


| Team Members | Responsibilities | Work Done and Contributions |
| ------------- | ---------------- | ---------------------------- |
| Sean Koh Hak Guan | Implemented reliable transport layer over UDP | Developed core `reliable.py`, including retransmission, ACK handling, and congestion control, flow control, handled the report writing section on reliable part of the code as well 
| Ryan Chen | Deal with creating the game API and the sender, receiver files to deal with port opening  | Dealt with the `receiver.py` and `sender.py` so we can test the udp locally with traffic sent from a sender to a receiver. Dealt additionally with `game_net_api.py` to deal with the game API's and interaction in order to handle game operations and split into `reliable` or `not reliable` and deals also with `not reliable side`. Contributed to the report
| Ng Ze Rui |  Report writing and also testing and fixing | Dealt with writing a significant part of the report as well as designing and implementing the test with Yarn Meng, additionally, made changes to `game_net_api.py` and `reliable.py` from bugs on  testing. | 
Lam Yarn Meng |  Scripting, testing, fixing bugs and Video |   Dealt with writing the script code for the testing of the different metrics, identify flaws in the testing metrics or different testing paradigms. Writing shell scripts for these test and plotting thenecessary graphs. Dealt with debugging throughout the project and is responsible for `emulator.py`. Additionally, contributed with the video filming, editing and report writing| 