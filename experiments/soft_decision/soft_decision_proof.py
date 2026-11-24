#!/usr/bin/env python3
"""
Soft-decision vs hard-decision coding-gain proof for the P25 rate-1/2 GPS FEC.

Measures, in a controlled AWGN simulation, how much weaker a signal the decoder
can tolerate if it keeps the SOFT symbol confidence instead of slicing to hard
bits before the Viterbi. Uses the SHIPPING hard decoder (decode/pdu_blocks.py
viterbi_deinterleave_12) verbatim as the "before", and the same trellis + tables
with a Euclidean branch metric as the "after".

Run:  python3 experiments/soft_decision/soft_decision_proof.py
Needs: numpy (+ matplotlib for the plot). Writes images/soft_vs_hard_ber.png.
Result (seed 7): 3.2 dB coding gain at 10% block-error-rate.
"""
import os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "decode"))
from pdu_blocks import _DEINT, _NEXT, viterbi_deinterleave_12   # shipping hard decoder + tables

LVL = [1.0, 3.0, -1.0, -3.0]                 # dibit -> ideal C4FM level (decode_capture slice map)
Es  = float(np.mean([l * l for l in LVL]))   # mean symbol energy = 5.0
STEP = [(_DEINT[t*4]//2, _DEINT[t*4+2]//2) for t in range(49)]   # the 2 symbols each trellis step uses


def encode_block(data12):
    """12 data bytes -> 98 ideal C4FM symbols (the exact inverse of the decoder)."""
    db = []
    for byte in data12:
        for sh in (6, 4, 2, 0):
            db.append((byte >> sh) & 3)
    db.append(0)                              # tail/flush dibit -> 49 trellis steps
    coded = [0]*196; st = 0
    for t in range(49):
        d = db[t]; cw = _NEXT[st][d]
        coded[t*4]=(cw>>3)&1; coded[t*4+1]=(cw>>2)&1; coded[t*4+2]=(cw>>1)&1; coded[t*4+3]=cw&1
        st = d
    tx = [0]*196
    for k in range(196):
        tx[_DEINT[k]] = coded[k]              # interleave
    return np.array([LVL[(tx[2*k] << 1) | tx[2*k+1]] for k in range(98)], float)


def hard_decode(rx):                          # slice to nearest level, then the shipping Viterbi
    bv = [0]*196
    for k in range(98):
        d = int(np.argmin([abs(rx[k]-l) for l in LVL]))
        bv[2*k] = (d >> 1) & 1; bv[2*k+1] = d & 1
    return viterbi_deinterleave_12(bv, 0)


def soft_decode(rx):                          # same trellis/tables, Euclidean metric on soft symbols
    INF = 1e18; N = 49
    cost = [[INF]*4 for _ in range(N+1)]; prev = [[-1]*4 for _ in range(N+1)]; inp = [[-1]*4 for _ in range(N+1)]
    cost[0][0] = 0.0
    for t in range(N):
        s0, s1 = STEP[t]; r0 = rx[s0]; r1 = rx[s1]
        for ps in range(4):
            if cost[t][ps] >= INF:
                continue
            base = cost[t][ps]
            for d in range(4):
                cw = _NEXT[ps][d]; e0 = LVL[(cw>>2)&3]; e1 = LVL[cw&3]
                m = base + (r0-e0)**2 + (r1-e1)**2
                if m < cost[t+1][d]:
                    cost[t+1][d] = m; prev[t+1][d] = ps; inp[t+1][d] = d
    end = min(range(4), key=lambda s: cost[N][s]); dib = [0]*N; s = end
    for t in range(N, 0, -1):
        dib[t-1] = inp[t][s]; s = prev[t][s]
        if s < 0:
            return None
    buf = bytearray(12)
    for d in range(48):
        buf[d>>2] |= dib[d] << (6 - ((d % 4) * 2))
    return bytes(buf)


def main():
    rng = np.random.default_rng(7)
    oh = os_ = 0
    for _ in range(300):
        data = bytes(rng.integers(0, 256, 12, dtype=np.uint8)); sym = encode_block(data)
        oh += (hard_decode(sym) == data); os_ += (soft_decode(sym) == data)
    print("round-trip no-noise: hard %d/300  soft %d/300" % (oh, os_))

    EsN0 = np.arange(3.0, 12.1, 1.0); NT = 3000; H = []; S = []
    print("\nEs/N0(dB)  hard BLER  soft BLER")
    for snr in EsN0:
        sigma = np.sqrt(Es / (2 * 10**(snr/10)))
        eh = es = 0
        for _ in range(NT):
            data = bytes(rng.integers(0, 256, 12, dtype=np.uint8))
            rx = encode_block(data) + rng.normal(0, sigma, 98)
            eh += (hard_decode(rx) != data); es += (soft_decode(rx) != data)
        H.append(eh/NT); S.append(es/NT)
        print("  %5.1f     %7.4f   %7.4f" % (snr, H[-1], S[-1]))

    def x_at(y, x, yt=0.1):
        y = np.array(y); x = np.array(x)
        for i in range(len(y)-1):
            if (y[i]-yt)*(y[i+1]-yt) <= 0 and y[i] != y[i+1]:
                ly = np.log10(np.clip([y[i], y[i+1]], 1e-6, 1))
                return x[i] + (np.log10(yt)-ly[0])*(x[i+1]-x[i])/(ly[1]-ly[0])
        return None
    gh = x_at(H, EsN0); gs = x_at(S, EsN0)
    print("\nEs/N0 at 10%% block error:  hard=%.2f dB  soft=%.2f dB  ->  GAIN = %.2f dB" % (gh, gs, gh-gs))

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        Hc = np.clip(H, 5e-4, 1); Sc = np.clip(S, 5e-4, 1)
        fig, ax = plt.subplots(figsize=(8, 5.2), dpi=150)
        ax.semilogy(EsN0, Hc, "o-", color="#c0392b", lw=2.2, ms=6, label="HARD decision (what we ship)")
        ax.semilogy(EsN0, Sc, "o-", color="#17804a", lw=2.2, ms=6, label="SOFT decision (proposed)")
        ax.axhline(0.1, color="#888", ls="--", lw=1)
        ax.annotate("", xy=(gs, 0.1), xytext=(gh, 0.1), arrowprops=dict(arrowstyle="<->", color="#1f3a52", lw=2))
        ax.text((gh+gs)/2, 0.14, "%.1f dB" % (gh-gs), color="#1f3a52", fontsize=13, fontweight="bold", ha="center")
        ax.set_xlabel("Signal level  Es/N0  (dB)"); ax.set_ylabel("Block error rate (fraction of GPS blocks that FAIL)")
        ax.set_title("P25 rate-1/2 FEC: soft vs hard decoder (AWGN sim)")
        ax.grid(True, which="both", ls=":", alpha=.5); ax.legend(loc="lower left"); ax.set_ylim(5e-4, 1)
        fig.tight_layout(); out = os.path.join(ROOT, "images", "soft_vs_hard_ber.png"); fig.savefig(out)
        print("plot ->", out)
    except Exception as e:
        print("(matplotlib not available: %s)" % e)


if __name__ == "__main__":
    main()
