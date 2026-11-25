#!/usr/bin/env python3
"""voice_ldu.py - extract the 9 IMBE voice frames from each P25 LDU1/LDU2 and
emit an imbe_fr[8][23] stream for the mbelib driver (voice/imbe_ota).

Chain: fixed-timing demod (the NID-clean path) -> frame sync + NID typing ->
for each LDU (DUID 5/10), replicate DSD's sequential read (status symbols every
36 dibits, skipped as encountered) and the Annex-H deinterleave (iW/iX/iY/iZ
from DSD p25p1_const.h) into imbe_fr[8][23] per voice frame.

Writes <out>.imbe = concatenated frames, 8*23 bytes each (row-major, 0/1).
Feed to: voice/imbe_ota <out>.imbe > out.s16
"""
import sys, numpy as np, wave
from scipy.signal import lfilter, resample_poly
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from frontend import c4fm_rx_taps
import framer

LVL2DIBIT = np.array([3, 2, 0, 1])
LV = np.array([-3., -1., 1., 3.])

# --- P25 Phase-1 IMBE interleave schedule (DSD src/include/p25p1_const.h, ISC) ---
iW = [0,2,4,1,3,5, 0,2,4,1,3,6, 0,2,4,1,3,6, 0,2,4,1,3,6,
      0,2,4,1,3,6, 0,2,4,1,3,6, 0,2,5,1,3,6, 0,2,5,1,3,6,
      0,2,5,1,3,7, 0,2,5,1,3,7, 0,2,5,1,4,7, 0,3,5,2,4,7]
iX = [22,20,10,20,18,0, 20,18,8,18,16,13, 18,16,6,16,14,11, 16,14,4,14,12,9,
      14,12,2,12,10,7, 12,10,0,10,8,5, 10,8,13,8,6,3, 8,6,11,6,4,1,
      6,4,9,4,2,6, 4,2,7,2,0,4, 2,0,5,0,13,2, 0,21,3,21,11,0]
iY = [1,3,5,0,2,4, 1,3,6,0,2,4, 1,3,6,0,2,4, 1,3,6,0,2,4,
      1,3,6,0,2,4, 1,3,6,0,2,5, 1,3,6,0,2,5, 1,3,6,0,2,5,
      1,3,6,0,2,5, 1,3,7,0,2,5, 1,4,7,0,3,5, 2,4,7,1,3,5]
iZ = [21,19,1,21,19,9, 19,17,14,19,17,7, 17,15,12,17,15,5, 15,13,10,15,13,3,
      13,11,8,13,11,1, 11,9,6,11,9,14, 9,7,4,9,7,12, 7,5,2,7,5,10,
      5,3,0,5,3,8, 3,1,5,3,1,6, 1,14,3,1,22,4, 22,12,1,22,20,2]
assert len(iW)==72 and len(iX)==72 and len(iY)==72 and len(iZ)==72

def fixed_demod(x, fr0):
    """Fixed-timing demod (no MMSE loop) -> dibit stream at the NID-clean phase."""
    a = x - x.mean()
    rms = np.maximum(lfilter([0.01], [1, -0.99], a*a), 1e-12); a = a/np.sqrt(rms)
    taps = c4fm_rx_taps(fr0); a = np.convolve(a, taps, 'same')
    U = 4; a = resample_poly(a, U, 1); sU = (fr0//4800)*U
    best = None
    for ph in range(sU):
        sm = a[ph::sU]; sm = sm/(np.mean(np.abs(sm))/2.0)
        ok = (np.min(np.abs(sm[:,None]-LV[None,:]),1) < 0.5).mean()
        if best is None or ok > best[0]: best = (ok, ph)
    sym = a[best[1]::sU]; sym = sym/(np.mean(np.abs(sym))/2.0)
    return sym

class Reader:
    """Sequential dibit reader replicating DSD read_dibit: status symbol every
    36 dibits (when status_count hits 35) is skipped; data dibits returned."""
    def __init__(self, dibits, pos, status_count=21):
        self.d = dibits; self.pos = pos; self.sc = status_count
    def read(self):
        if self.sc == 35:
            self.pos += 1          # skip the status dibit
            self.sc = 1
        else:
            self.sc += 1
        v = int(self.d[self.pos]); self.pos += 1
        return v

def imbe_frame(rd):
    """Read 72 data dibits -> imbe_fr[8][23] via the Annex-H deinterleave."""
    fr = [[0]*23 for _ in range(8)]
    for j in range(72):
        dbt = rd.read()
        fr[iW[j]][iX[j]] = (dbt >> 1) & 1   # bit 1 (high)
        fr[iY[j]][iZ[j]] = dbt & 1          # bit 0 (low)
    return fr

def extract_ldu(dibits, start):
    """Extract the 9 voice imbe_fr from one LDU beginning at frame-dibit `start`.
    LDU body starts 57 dibits in (sync 24 + NID 32 + 1 status); status_count=21.
    Between voice frames: 4 hex words = 20 data dibits (x6), LSD = 16 (after #8)."""
    rd = Reader(dibits, start + 57, 21)
    frames = []
    # data dibits BEFORE voice frame k: IMBE1,IMBE2 back-to-back; then 4 hex
    # words (20 dibits) before IMBE3..IMBE8; LSD (16) before IMBE9.
    gaps = [0, 0, 20, 20, 20, 20, 20, 20, 16]
    for k in range(9):
        for _ in range(gaps[k]):
            rd.read()
        frames.append(imbe_frame(rd))
    return frames

def main(wav, out):
    w = wave.open(wav, 'rb'); fr0 = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float); w.close()
    # segment keyups (FM-quieting: keyup = low broadband HF)
    d = np.diff(x); win = int(0.1*fr0)
    hf = np.array([np.sqrt(np.mean(d[i:i+win]**2)) for i in range(0, len(d)-win, win)])
    thr = 0.3*(hf.min()+hf.max()); keyed = hf < thr
    segs = []; i = 0
    while i < len(keyed):
        if keyed[i]:
            j = i
            while j < len(keyed) and keyed[j]: j += 1
            if (j-i)*win > 1.0*fr0: segs.append((i*win, j*win))
            i = j
        else: i += 1
    allframes = []
    for s, e in segs:
        sym = fixed_demod(x[s:e].copy(), fr0)
        # choose polarity that locks the most voice frames
        best = None
        for sg in (1, -1):
            db = LVL2DIBIT[np.digitize(sg*sym, [-2., 0., 2.])]
            fr = framer.decode_frames(db, sync_errth=8)
            vc = sum(1 for q in fr if q['duid'] in (5, 10))
            if best is None or vc > best[0]: best = (vc, sg, db, fr)
        _, sg, db, fr = best
        nvoice = 0
        for q in fr:
            if q['duid'] in (5, 10) and q['start']+875 < len(db):
                allframes.extend(extract_ldu(db, q['start'])); nvoice += 1
        print("  keyup %.1f-%.1fs: pol%+d, %d LDU frames -> %d voice frames"
              % (s/fr0, e/fr0, sg, nvoice, nvoice*9))
    with open(out, 'wb') as f:
        for fr in allframes:
            f.write(bytes(fr[r][c] for r in range(8) for c in range(23)))
    print("wrote %d IMBE voice frames -> %s (%.1f s @8kHz)"
          % (len(allframes), out, len(allframes)*160/8000))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
