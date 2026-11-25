#!/usr/bin/env python3
"""lc_source.py — pull the CURRENT SPEAKER (source unit ID) out of P25 voice.

The keystone of the combo platter: a P25 LDU1 carries the Link Control Word in
the hex words interleaved between its voice frames. For a group-voice LC (LCO 0)
the source address is `lcinfo` bits 32..56 — the unit ID of the radio that is
talking. Fused with the position layer by that same ID, the talking unit lights
up on the map.

Mirrors DSD (p25p1_ldu1.c / p25_lcw.c): the three 20-dibit gaps before IMBE
frames 3/4/5 in an LDU1 are the 12 DATA hex words 11..0 (4 per gap, descending);
each hex word = 3 data dibits (6 bits) + 2 parity dibits. Assemble ->
lcformat(8) + mfid(8) + lcinfo(56).

Robustness: a speaker does not change mid-transmission, so the reported ID is a
MAJORITY VOTE of the group-voice source over all LDU1 frames in a keyup — this
rides over the occasional uncorrected LC bit error cleanly.
HARDENING (TODO, for instant per-frame speaker-change response): add the DSD
per-hex-word Hamming(10,6,3) + Reed-Solomon(24,12,13) correction so each LDU1's
LC is self-correcting; the majority vote then becomes belt-and-suspenders.

Reuses the proven voice_ldu demod + framer + Reader; same dibits that produce
correct GPS and correct voice feed the LC.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, wave
from collections import Counter
from voice_ldu import fixed_demod, Reader, LVL2DIBIT
import framer

# hex-word DATA indices filled by the three 20-dibit gaps (DSD p25p1_ldu1.c)
_GAP_HEX = [(11, 10, 9, 8), (7, 6, 5, 4), (3, 2, 1, 0)]


def _read_hexword(rd):
    """3 data dibits -> 6 data bits (hi,lo per dibit); 2 parity dibits skipped."""
    bits = []
    for _ in range(3):
        d = rd.read(); bits += [(d >> 1) & 1, d & 1]
    rd.read(); rd.read()                       # parity dibits
    return bits


def lcw_source(dibits, start):
    """Return the group-voice source unit ID from one LDU1 at frame-dibit `start`,
    or None if the LC is not a group-voice (LCO 0) word / not enough data."""
    rd = Reader(dibits, start + 57, 21)         # body 57 dibits in, status_count 21
    hexd = [None] * 12
    gi = 0
    for k in range(5):                          # walk IMBE1..5 and the 3 data gaps
        if k >= 2:                              # gaps sit before IMBE3,4,5
            for idx in _GAP_HEX[gi]:
                hexd[idx] = _read_hexword(rd)
            gi += 1
        for _ in range(72):                     # the IMBE voice frame itself
            rd.read()
    # assemble per p25p1_ldu1.c: lcformat(8) mfid(8) lcinfo(56)
    lcformat = hexd[11] + hexd[10][:2]
    lcinfo = hexd[9][4:6]
    for i in (8, 7, 6, 5, 4, 3, 2, 1, 0):
        lcinfo += hexd[i]
    if "".join(map(str, lcformat)) != "00000000":   # LCO 0 = group voice channel user
        return None
    return int("".join(map(str, lcinfo[32:56])), 2)  # source address (p25_lcw.c)


def _segment_keyups(x, fr0):
    d = np.diff(x); win = int(0.1 * fr0)
    hf = np.array([np.sqrt(np.mean(d[i:i + win] ** 2)) for i in range(0, len(d) - win, win)])
    thr = 0.3 * (hf.min() + hf.max()); keyed = hf < thr
    segs, i = [], 0
    while i < len(keyed):
        if keyed[i]:
            j = i
            while j < len(keyed) and keyed[j]:
                j += 1
            if (j - i) * win > 1.0 * fr0:
                segs.append((i * win, j * win))
            i = j
        else:
            i += 1
    return segs


def speakers_from_wav(wav):
    """-> list of (t_start_s, t_end_s, source_id, votes, total_ldu1) per keyup."""
    w = wave.open(wav, 'rb'); fr0 = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float); w.close()
    out = []
    for s, e in _segment_keyups(x, fr0):
        sym = fixed_demod(x[s:e].copy(), fr0)
        best = None
        for sg in (1, -1):
            db = LVL2DIBIT[np.digitize(sg * sym, [-2., 0., 2.])]
            fr = framer.decode_frames(db, sync_errth=8)
            vc = sum(1 for q in fr if q['duid'] in (5, 10))
            if best is None or vc > best[0]:
                best = (vc, db, fr)
        _, db, fr = best
        ids = []
        for q in fr:
            if q['duid'] == 5 and q['start'] + 875 < len(db):
                sid = lcw_source(db, q['start'])
                if sid is not None:
                    ids.append(sid)
        if ids:
            sid, votes = Counter(ids).most_common(1)[0]
            out.append((s / fr0, e / fr0, sid, votes, len(ids)))
    return out


if __name__ == "__main__":
    for row in speakers_from_wav(sys.argv[1]):
        t0, t1, sid, votes, tot = row
        print("  keyup %5.1f-%-5.1fs  CURRENT SPEAKER = unit %d   (%d/%d LDU1 agree)"
              % (t0, t1, sid, votes, tot))
