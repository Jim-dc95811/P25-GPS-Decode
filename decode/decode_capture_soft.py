"""Soft-decision OTA P25 GPS decode — hard vs soft, side by side, on one WAV.
  python3 decode_capture_soft.py <capture.wav>

Runs the SHIPPING hard decoder (decode_capture.decode_burst) and the SOFT
decoder on every detected burst and prints both, with a tally, so a bench run
at each attenuation step shows the hard-vs-soft delta directly. The soft path:

  fsk4_demod (MMSE soft symbols)
    -> moving-average DC-block (tracks the key-up transient)        [DC tracker]
    -> tier 1: strict hard sync + NID, SOFT rate-1/2 FEC payload
    -> tier 2: soft-NCC sync acquisition + SOFT FEC, payload-validated
       (recovers marginal-sync bursts the hard popcount sync misses)

Everything downstream of the slice is unchanged from the hard path except the
branch metric (Euclidean on soft symbols) and the sync acquisition (soft NCC).
The shipping decode_capture.py and framer.py are untouched; the soft block
decoders live in soft_blocks.py.

Soft-decision coding gain proven at 3.16 dB in a controlled AWGN sim
(experiments/soft_decision + scratchpad block-verify); the REAL field delta is
what this tool measures on Jim's captures at known attenuation.
"""
import sys
import numpy as np
import wave
from fsk4_demod import fsk4_demod
from framer import decode_frames
from frontend import c4fm_rx_taps
from soft_blocks import pdu_blocks_soft
import decode_capture as hard   # shipping hard decoder, reused verbatim

LVL2DIBIT = [3, 2, 0, 1]
# soft sync template: 24 sync dibits -> ideal C4FM levels, normalized (from decode_nid)
_SYNC = 0x5575F5FF77FF
_b = [(_SYNC >> (47 - i)) & 1 for i in range(48)]
_SD = [(_b[2 * k] << 1) | _b[2 * k + 1] for k in range(24)]
_SYMVAL = {1: +3.0, 0: +1.0, 2: -1.0, 3: -3.0}
_TEMPL = np.array([_SYMVAL[d] for d in _SD], float)
_TN = _TEMPL / np.linalg.norm(_TEMPL)


def _dc_block(a, fr0):
    """Moving-average DC-block (the key-up transient tracker). Removes slow DC
    drift the AC-coupled capture leaves at burst onset without eating symbol
    energy (window ~20 symbols, as proven in decode_nid)."""
    w = int(round(fr0 / 4800.0 * 20)) | 1
    if len(a) <= w:
        return a - np.mean(a)
    return a - np.convolve(a, np.ones(w) / w, mode='same')


def _soft_ncc(sym):
    """Soft normalized cross-correlation sync hunt -> (start_symbol, polarity, peak)."""
    if len(sym) < 24:
        return None, 1, 0.0
    en = np.sqrt(np.convolve(sym ** 2, np.ones(24), 'valid')) + 1e-9
    cc = np.correlate(sym, _TN, 'valid') / en
    bi = int(np.argmax(np.abs(cc)))
    best = float(cc[bi])
    return bi, (1 if best > 0 else -1), best


def _payload_soft(db, ssym, start):
    fb = []
    for d in db[start:]:
        fb.append((d >> 1) & 1)
        fb.append(d & 1)
    _sv, blocks = pdu_blocks_soft(fb, list(ssym[start:]))
    pay = bytearray()
    for b in blocks:
        if b is None:
            break
        pay += b
    return hard.asc(pay)


def decode_burst_soft(x, fr0, tstart, taps, span=0.55):
    """Soft twin of decode_capture.decode_burst: DC-tracked, soft-NCC acquisition,
    soft rate-1/2 FEC. Same lead-offset / polarity robustness."""
    for lead in (0.06, 0.10, 0.03, 0.15, 0.00):
        a = x[int((tstart - lead) * fr0):int((tstart + span) * fr0)].copy()
        a = _dc_block(a, fr0)                       # DC transient tracker
        a = hard.rmsagc_vec(a)
        a = np.convolve(a, taps, 'same')
        a = a / (np.std(a) + 1e-9) * np.sqrt(5.0)
        sym = fsk4_demod(a, fr0, 4800)
        # tier 1: strict hard sync + NID validation, SOFT payload
        for sgn in (1, -1):
            ssym = sgn * sym
            db = [LVL2DIBIT[b] for b in np.digitize(ssym, [-2., 0., 2.])]
            frames = decode_frames(db, sync_errth=6)
            if frames:
                p = _payload_soft(db, ssym, frames[0]['start'])
                if hard._good(p):
                    return frames[0], p
        # tier 2: soft-NCC acquisition + SOFT payload, payload-validated
        bi, sgn, _peak = _soft_ncc(sym)
        if bi is not None and bi >= 0:
            ssym = sgn * sym
            db = [LVL2DIBIT[b] for b in np.digitize(ssym, [-2., 0., 2.])]
            p = _payload_soft(db, ssym, bi)
            if hard._good(p):
                return {'start': bi, 'nac': 0x455, 'duid': 0xc, 'ec': -1}, p
    return None


def _frag(pay):
    i = pay.find("GGA")
    return pay[max(0, i - 1):i + 86] if i >= 0 else pay[:80]


def main(wav):
    w = wave.open(wav, 'rb')
    fr0 = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float) / 32768.0
    w.close()
    taps = c4fm_rx_taps(fr0)
    bursts = hard.detect_bursts(x, fr0)
    print("%s: %d Hz, %.1fs, %d bursts detected\n" % (wav, fr0, len(x) / fr0, len(bursts)))
    oh = os_ = 0
    print("   burst      HARD                              SOFT")
    for t in bursts:
        rh = hard.decode_burst(x, fr0, t, taps)
        rs = decode_burst_soft(x, fr0, t, taps)
        hok = rh is not None and "GGA" in rh[1] and "PP25" in rh[1]
        sok = rs is not None and "GGA" in rs[1] and "PP25" in rs[1]
        oh += hok
        os_ += sok
        hs = _frag(rh[1]) if rh else "no-lock"
        ss = _frag(rs[1]) if rs else "no-lock"
        print("  t=%6.2f  %-34.34s %s" % (t, hs, ss))
    print("\n  HARD: %d/%d     SOFT: %d/%d     (soft - hard = %+d bursts)"
          % (oh, len(bursts), os_, len(bursts), os_ - oh))


if __name__ == "__main__":
    main(sys.argv[1])
