## Acknowledgements 
In this project, we acknowledge the use of fair use of AI to help guide our work. We used it in summarising some parts of the writeup as well. For the code section, we will be declaring in general some of the uses and documenting the generic purpose and outputs given

### AI Table of Usage 
| Provider              | Problem | Problem Description / Prompt | AI Suggestion |
| -------|-------- | ------ | ----- |
ChatGPT 5.0 / Gemini 2.5 Pro |   General project code structure (all .py files ) for initial set up  |  Given the project assignment description, could you generate template code for us to work on , we wish to implement reliability  similar to TCP on top of UDP |  Generated project structure of emulator.py, game_net_api.py, metrics.py , packet.py, reliable.py as starting structure and code to fill in | 
ChatGPT 5. 0 | Reliable.py | Given that we are trying to build reliability over UDP, and given that we have chosen to emulate reliability by taking inspiration from TCP, generate us code given the following methods that we wish to adopt in TCP and give us any critiques on improvement (Go-back N algorithm where we keep a window for receiving in order) |  The AI suggested Selective Repeat (SR) as a modern approach and generated  the boiler code for us to at least establish a bare minimum baseline|
ChatGPT 5.0 / Gemini 2.5 Pro |  Reliable Part of sender / receiver (reliable.py )|The sender is currently sending too fast for our reliable,  insert logs here , it seems like the buffer is overwhelmed, can u give us suggestion as to why its behaving as such | It recommends some code correction and suggested the implementation of network congestion control and sender / receiver window being used in acknowledgement as flow control |
ChatGPT 5.0 / Gemini 2.5 Pro |  Reliable Part of sender / receiver (reliable.py )|  The sender is currently sending too fast for our reliable,  insert logs here , it seems like the buffer is overwhelmed, can u give us suggestion as to why its behaving as such | It recommends some code correction and suggested the implementation of network congestion control and sender / receiver window being used in acknowledgement as flow control |
ChatGPT 5.0 |  Reliable Part of sender / receiver (reliable.py )|  The backoff is taking too long and the test are running too slowly, what might be possible factors causing such delays `insert code here` | The delays are due to the exponential backoff algorithm doubling twice everyime, change the algorithm for backing off and tune the factor of backing off
ChatGPT 5.0 |  Generate Plots and Parse CLI arguments and syntax | Can you write me code given that i want to generate code based on metrics like throughput, different packet drop configurations | Outputted code and shellscript to do so.|




