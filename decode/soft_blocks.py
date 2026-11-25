"""Soft-decision P25 data-block FEC — the soft-symbol twin of pdu_blocks.py.

Same regulated P25 trellis + the SAME tables (_DEINT, _NEXT, _PAIRS, _STMAP)
imported verbatim from pdu_blocks; the ONLY change from the shipping hard
decoder is the branch metric: squared Euclidean distance on the soft C4FM
symbols (the MMSE demod's confidence) instead of Hamming distance on sliced
bits. This is the decoder the soft-decision proof validated at 3.2 dB coding
gain (experiments/soft_decision/soft_decision_proof.py, soft_decode) — lifted
here as a sealed kernel and generalized to a block offset so it drops into the
live path. The hard pdu_blocks.py is left untouched.

A block is 98 C4FM symbols (196 bits). Input `sv` is the soft symbol vector
(one float per symbol, nominal -3,-1,+1,+3), aligned to the SAME symbol order
the hard `bv` uses (status symbols already stripped). `start_sym` is the block's
symbol offset = the hard path's bit offset // 2.

  viterbi_deinterleave_12_soft(sv, start_sym) -> 12 bytes   (rate-1/2; header +
                                                 unconfirmed data blocks)
  block_deinterleave_34_soft(sv, start_sym)   -> 18 bytes   (rate-3/4; confirmed
                                                 data blocks)
"""
from pdu_blocks import _DEINT, _NEXT, _PAIRS, _STMAP

# dibit -> ideal C4FM level, the decode_capture slice map (LVL2DIBIT=[3,2,0,1]):
#   level +1 -> dibit 0, +3 -> 1, -1 -> 2, -3 -> 3
LVL = [1.0, 3.0, -1.0, -3.0]

# the two within-block symbol indices each trellis step reads (same pairing the
# hard decoder's _DEINT indexing produces: _DEINT pairs are (2n, 2n+1) = one
# symbol, so //2 recovers the symbol index).
_STEP12 = [(_DEINT[t * 4] // 2, _DEINT[t * 4 + 2] // 2) for t in range(49)]


def viterbi_deinterleave_12_soft(sv, start_sym):
    """Soft-decision rate-1/2 Viterbi. Exact soft twin of
    pdu_blocks.viterbi_deinterleave_12(bv, start_sym*2)."""
    if start_sym + 97 >= len(sv):
        return None
    INF = 1e18
    N = 49
    cost = [[INF] * 4 for _ in range(N + 1)]
    prev = [[-1] * 4 for _ in range(N + 1)]
    inp = [[-1] * 4 for _ in range(N + 1)]
    cost[0][0] = 0.0
    for t in range(N):
        a, b = _STEP12[t]
        r0 = sv[start_sym + a]
        r1 = sv[start_sym + b]
        for ps in range(4):
            base = cost[t][ps]
            if base >= INF:
                continue
            for d in range(4):
                cw = _NEXT[ps][d]
                e0 = LVL[(cw >> 2) & 3]
                e1 = LVL[cw & 3]
                m = base + (r0 - e0) ** 2 + (r1 - e1) ** 2
                if m < cost[t + 1][d]:
                    cost[t + 1][d] = m
                    prev[t + 1][d] = ps
                    inp[t + 1][d] = d
    end = min(range(4), key=lambda s: cost[N][s])
    dib = [0] * N
    s = end
    for t in range(N, 0, -1):
        dib[t - 1] = inp[t][s]
        s = prev[t][s]
        if s < 0:
            return None
    buf = bytearray(12)
    for d in range(48):
        buf[d >> 2] |= dib[d] << (6 - ((d % 4) * 2))
    return bytes(buf)


def block_deinterleave_34_soft(sv, start_sym):
    """Soft-decision rate-3/4 Viterbi. Soft twin of
    pdu_blocks.block_deinterleave_34 (confirmed data blocks). Same 8-state
    trellis + _STMAP/_PAIRS; Euclidean branch metric on the soft symbols.
    (Not exercised by the GPS PDU path, which is all rate-1/2, but kept so a
    confirmed-data PDU gets the same soft benefit.)"""
    if start_sym + 97 >= len(sv):
        return None
    INF = 1e18
    N = 49
    cost = [[INF] * 8 for _ in range(N + 1)]
    prev = [[-1] * 8 for _ in range(N + 1)]
    cost[0][0] = 0.0
    for t in range(N):
        # same symbol pairing as rate-1/2: the 4 coded bits of step t are the
        # two symbols at within-block indices _DEINT[4t]//2 and _DEINT[4t+2]//2.
        r0 = sv[start_sym + (_DEINT[4 * t] // 2)]
        r1 = sv[start_sym + (_DEINT[4 * t + 2] // 2)]
        for s in range(8):
            base = cost[t][s]
            if base >= INF:
                continue
            for nx in range(8):
                p = _STMAP[s][nx]
                e0 = LVL[_PAIRS[p][0]]
                e1 = LVL[_PAIRS[p][1]]
                nc = base + (r0 - e0) ** 2 + (r1 - e1) ** 2
                if nc < cost[t + 1][nx]:
                    cost[t + 1][nx] = nc
                    prev[t + 1][nx] = s
    end = min(range(8), key=lambda s: cost[N][s])
    path = [0] * N
    s = end
    for t in range(N, 0, -1):
        path[t - 1] = s
        s = prev[t][s]
        if s < 0:
            return None
    buf = bytearray(18)
    acc = 0
    nb = 0
    o = 0
    for i in range(N):
        if o >= 18:
            break
        acc = (acc << 3) | (path[i] & 7)
        nb += 3
        while nb >= 8 and o < 18:
            nb -= 8
            buf[o] = (acc >> nb) & 0xff
            o += 1
            acc &= (1 << nb) - 1
    return bytes(buf)


def pdu_blocks_soft(fb, ssym):
    """Soft twin of framer.pdu_blocks. Faithful mirror of its status-symbol strip
    (every 36th dibit) and block layout (112 + k*196 bits), but carries the soft
    symbols through the strip and decodes each 1/2-rate block with the soft
    Viterbi. The shipping framer.pdu_blocks is left byte-for-byte untouched.

      fb   = frame-body BITS from the frame start (2 per dibit), as framer builds
      ssym = the soft symbol levels from the SAME frame start, one per dibit,
             1:1 with fb's dibits (polarity already applied)
    Returns (sv, blocks): sv = soft symbol vector after the strip (symbol order
    matching the hard bv), blocks = list of 12-byte rate-1/2 soft decodes.
    """
    ndib = len(fb) // 2
    sv = []
    for d in range(ndib):
        if (d + 1) % 36 == 0:          # strip status symbol — identical to framer
            continue
        sv.append(ssym[d])
    nbits = 2 * len(sv)
    nblk = (nbits - 112) // 196 if nbits > (48 + 64) else 1
    nblk = max(1, nblk)
    blocks = [viterbi_deinterleave_12_soft(sv, 56 + k * 98) for k in range(nblk)]
    return sv, blocks
