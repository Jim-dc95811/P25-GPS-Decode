"""STDLIB-ONLY P25 OTA GPS decode core (no numpy/scipy) -- runs on the box.

Same proven pipeline as the numpy decode_capture, re-implemented in pure Python:
  time-domain band-ratio burst gate (two biquad band-pass + RMS; no FFT)
  -> per burst: mean/AGC/C4FM-FIR/scale -> fsk4_demod (MMSE) -> 4-level slice
     -> streaming framer (sync + NID) -> Viterbi PDU blocks -> NMEA,
  with the robust acquisition (strict NID-validated, then payload-validated
  force-lock, across leads + both polarities).

framer.py, pdu_blocks.py, bch_nid.py are the numpy-free OP25 port, used as-is.
"""
import math, re
from frontend import prep_segment
from fsk4_demod import fsk4_demod
from framer import decode_frames, pdu_blocks
from pdu_blocks import count_bits

MAGIC = 0x5575F5FF77FF; MASK = (1 << 48) - 1
LVL2DIBIT = [3, 2, 0, 1]          # slice order for levels [-3,-1,+1,+3]

def _asc(bs): return "".join(chr(c) if 32 <= c < 127 else "." for c in bs)

def _slice(sym, sgn):
    # numpy.digitize(sgn*sym, [-2,0,2]) -> 0..3, mapped by LVL2DIBIT
    db = []
    for v in sym:
        s = sgn * v
        if s < -2.0:   idx = 0
        elif s < 0.0:  idx = 1
        elif s < 2.0:  idx = 2
        else:          idx = 3
        db.append(LVL2DIBIT[idx])
    return db

def _best_sync(db, region=700):
    acc = 0; best = 99; bi = 0
    for i in range(min(region, len(db))):
        acc = ((acc << 2) | (db[i] & 3)) & MASK
        if i >= 23:
            e = count_bits((acc ^ MAGIC) & MASK)
            if e < best: best = e; bi = i
    return bi, best

def _payload_at(db, start):
    fb = []
    for d in db[start:]:
        fb.append((d >> 1) & 1); fb.append(d & 1)
    bv, blocks = pdu_blocks(fb); pay = bytearray()
    for b in blocks:
        if b is None: break
        pay += b
    return _asc(pay)

def _good(p): return ("GGA" in p) and ("$PP25,907" in p)

def decode_at(seg, fr, tstart, span=0.55):
    """Robust acquisition on a captured window at onset tstart (seconds)."""
    for lead in (0.06, 0.10, 0.03, 0.15, 0.00):
        i0 = int((tstart - lead) * fr); i1 = int((tstart + span) * fr)
        if i0 < 0: i0 = 0
        a = seg[i0:i1]
        if len(a) < int(0.2 * fr): continue
        prepped = prep_segment(a, fr)
        sym = fsk4_demod(prepped, float(fr), 4800.0)
        for sgn in (1, -1):
            db = _slice(sym, sgn)
            frames = decode_frames(db, sync_errth=6)        # strict, NID-validated
            if frames:
                p = _payload_at(db, frames[0]['start'])
                if _good(p): return p
            bi, h = _best_sync(db)                           # force-lock, payload-validated
            if bi >= 23:
                p = _payload_at(db, bi - 23)
                if _good(p): return p
    return None

# ---- time-domain burst gate (no FFT): two band-pass biquads + per-hop RMS ----
HOP = 512
def _biquad(f0, Q, fs):
    w0 = 2 * math.pi * f0 / fs; a = math.sin(w0) / (2 * Q); c = math.cos(w0)
    b0 = a; b1 = 0.0; b2 = -a; a0 = 1 + a; a1 = -2 * c; a2 = 1 - a
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

def _band_rms(x, coef, hop=HOP):
    b0, b1, b2, a1, a2 = coef; z1 = z2 = 0.0; s = 0.0; n = 0; res = []
    for xi in x:
        y = b0 * xi + z1; z1 = b1 * xi - a1 * y + z2; z2 = b2 * xi - a2 * y
        s += y * y; n += 1
        if n == hop: res.append(s / hop); s = 0.0; n = 0
    return res

def detect_bursts(x, fr, thr=8.0, lo_f=1500, hi_f=6000):
    """Onset times (s) of C4FM bursts: low-band(<2.9k) vs high-band(3-10k) RMS ratio."""
    L = _band_rms(x, _biquad(lo_f, 0.7, fr))
    H = _band_rms(x, _biquad(hi_f, 0.9, fr))
    nb = min(len(L), len(H)); dt = HOP / fr
    starts = []; prev = False
    for i in range(nb):
        r = L[i] / (H[i] + 1e-12)
        on = r > thr
        t = i * dt
        if on and not prev and (not starts or t - starts[-1] > 1.0):
            starts.append(t)
        prev = on
    return starts

_GGA = re.compile(r"\$..GGA,[^*]*\*[0-9A-Fa-f]{2}")
_PP25 = re.compile(r"\$PP25,[0-9]+,?\*?[0-9A-Fa-f]{0,2}")
def split_nmea(pay):
    g = _GGA.search(pay); p = _PP25.search(pay)
    return (g.group(0) if g else None), (p.group(0) if p else None)
