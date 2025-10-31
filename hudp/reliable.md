We implement reliability with a Selective Repeat (SR) sender and a Go-Back-N (GBN)–style receiver discipline. On the sender, each reliable packet is assigned a 16-bit sequence number and tracked independently with a per-packet timer. If an ACK isn’t received before the Retransmission Timeout (RTO) expires, the sender retransmits only that specific packet, minimizing redundant traffic under loss. To keep timers tight and stable, we use Karn’s rule (ignore RTT samples from retransmitted packets) and a RFC-6298–style adaptive RTO: an exponentially weighted SRTT/RTTVAR estimator updates on “clean” ACKs, with exponential backoff on timeouts and clamping to reasonable bounds. This gives us TCP-like timing behavior without implementing full congestion control. (Optionally, duplicate cumulative ACKs can trigger fast retransmit for the earliest unacked packet.)

On the receiving side, we enforce strict in-order delivery to the application using a GBN ordering policy while still accepting out-of-order arrivals at the transport layer. Concretely, every reliable packet is ACKed immediately upon receipt (to keep the sender informed), and packets that arrive ahead of the next expected sequence are buffered (SR capability). Delivery to the app only proceeds at the head of the stream. To prevent head-of-line stalls in real-time scenarios, we implement the assignment’s skip-after-t rule: if a gap persists for ≥ t ms (default 200 ms), we skip the missing sequence number, advance the expected pointer, and immediately drain any buffered packets that now become in-order. A lightweight background timer enforces this policy even if no further traffic arrives.

Sure — let’s break that paragraph down clearly and intuitively:

---

### 1️⃣ **What the problem is**

When you send packets reliably over an unreliable network (like UDP), you need a timer to detect packet loss.
If you set the **retransmission timeout (RTO)** too short → you’ll resend too aggressively and waste bandwidth.
If you set it too long → recovery from loss will be sluggish, increasing latency.

TCP solved this long ago with **adaptive timers** that continuously estimate the network’s round-trip time (RTT) and adjust the RTO accordingly.
That’s what we’re replicating.

---

### 2️⃣ **Karn’s rule**

When a packet is **retransmitted**, we no longer know which transmission the ACK corresponds to — the original or the retransmission.
If we incorrectly use that RTT sample, it could make our estimate wildly wrong (too small or too big).

👉 **Karn’s rule** says:

> *Ignore RTT measurements for retransmitted packets.*
> Only use RTTs from packets that were sent once and acknowledged once (called “clean” samples).

This keeps the RTT estimate stable and prevents spurious updates during loss bursts.

---

### 3️⃣ **RFC 6298 adaptive RTO algorithm**

Instead of using a fixed timeout, we adapt the RTO dynamically using **exponential smoothing**:

We maintain:

* `SRTT`: Smoothed RTT (the running average)
* `RTTVAR`: RTT variance (how much the RTT fluctuates)
* `RTO`: Retransmission timeout derived from both

The standard update formulas (simplified) are:

```
RTTVAR = (1 - β) * RTTVAR + β * |SRTT - RTT_sample|
SRTT   = (1 - α) * SRTT + α * RTT_sample
RTO     = SRTT + 4 * RTTVAR
```

Where:

* α = 1/8 (weight for new RTT samples)
* β = 1/4 (weight for variance)
* “4” is the safety multiplier (to cover jitter)

This way, if network delay rises gradually, the sender automatically relaxes its timer, and if the path stabilizes, the timer tightens again.

We also **clamp** RTO within sane limits (e.g., min 50 ms, max 4000 ms) so it never becomes too small or absurdly large.

---

### 4️⃣ **Exponential backoff**

If a retransmission timeout actually happens (packet lost, no ACK received), we assume possible congestion or a large delay.
Instead of instantly retrying at the same rate, we **double** the RTO (exponential backoff):

```
RTO = min(RTO * 2, RTO_max)
```

This helps the network stabilize and prevents the sender from flooding it with repeated retransmissions (similar to TCP’s congestion avoidance).

---

### 5️⃣ **Fast retransmit**

In TCP, if the sender receives **3 duplicate ACKs** for the same sequence number, it assumes the next packet was lost (since later packets arrived).
It retransmits that missing packet immediately — without waiting for the RTO to expire.

We optionally add a similar **fast retransmit** optimization in our SR sender:
if multiple duplicate ACKs are observed for the same missing packet, we resend it early, improving latency recovery.

---

### ✅ **In summary**

This part of your system implements **a self-tuning, stable retransmission timer**:

| Mechanism                      | Purpose                                         |
| ------------------------------ | ----------------------------------------------- |
| **Karn’s rule**                | Prevent RTT confusion after retransmits         |
| **SRTT/RTTVAR estimator**      | Smooth RTT variation and predict future RTTs    |
| **Exponential backoff**        | Handle severe loss or congestion safely         |
| **Clamping**                   | Prevent unrealistic timer values                |
| **Fast retransmit** | Accelerate recovery when loss is detected early |

Together, these techniques give **TCP-like timing accuracy and stability** — fast enough for games, but robust under variable network conditions — without needing full TCP congestion control logic.
