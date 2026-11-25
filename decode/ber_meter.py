#!/usr/bin/env python3
"""ber_meter.py - symbol/bit error rate of a captured P25 test pattern (DEO audio).

  python3 ber_meter.py <capture.wav>                  # self-consistency BER (period-fold)
  python3 ber_meter.py <capture.wav> --ref <ref.wav>  # BER vs a reference capture

SELF mode (for STD 1011 / STD 511 sweeps): folds the repeating pattern on its own
period, majority-votes a clean reference, and reports the error rate. ~0% on a strong
clean signal; climbs with noise. The RF level where BER crosses 5% = sensitivity.

REF mode (for STD CAL calibration): aligns this capture's decoded bits to a reference
capture's clean pattern. CAL vs a clean 1011 reference should read ~4.98% (its baked-in
172/3456 injected errors) - that proves the bit counter is honest.
"""
import sys, os, numpy as np, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fsk4_demod import fsk4_demod
from frontend import c4fm_rx_taps
from scipy.signal import lfilter

LVL2DIBIT = np.array([3, 2, 0, 1], dtype=np.uint8)

def demod(wavpath):
    w = wave.open(wavpath, 'rb'); fs = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float); w.close()
    taps = c4fm_rx_taps(fs)
    a = x - np.mean(x)
    rms = np.maximum(lfilter([0.01], [1.0, -0.99], a * a), 1e-12); a = a / np.sqrt(rms)
    a = np.convolve(a, taps, 'same'); a = a / (np.std(a) + 1e-9) * np.sqrt(5.0)
    return fsk4_demod(a, fs, 4800)

def slice_dibits(sym, sgn):
    return LVL2DIBIT[np.digitize(sgn * sym, [-2., 0., 2.])]

def to_bits(dib):
    return np.column_stack([(dib >> 1) & 1, dib & 1]).reshape(-1).astype(np.uint8)

def find_period(dib, lo=48, hi=4000):
    N = len(dib); hi = min(hi, N // 3); best = None
    for lag in range(lo, hi):
        m = np.mean(dib[:N - lag] != dib[lag:])
        if best is None or m < best[1]: best = (lag, m)
    return best  # (period, mismatch_frac)

def clean_pattern(sym):
    """Pick polarity with the cleanest period; return (sgn, P, ref_dibits, folded, K)."""
    best = None
    for sgn in (1, -1):
        dib = slice_dibits(sym, sgn)
        P, m = find_period(dib)
        if best is None or m < best[1]: best = (sgn, m, P, dib)
    sgn, _, P, dib = best
    N = len(dib); K = N // P
    M = dib[:K * P].reshape(K, P)
    ref = np.array([np.bincount(M[:, c], minlength=4).argmax() for c in range(P)], dtype=np.uint8)
    return sgn, P, ref, M, K

def self_ber(sym):
    sgn, P, ref, M, K = clean_pattern(sym)
    if K < 2: return None
    serr = float(np.mean(M != ref[None, :]))
    refbits = to_bits(ref)
    berr = float(np.mean(np.array([to_bits(M[k]) for k in range(K)]) != refbits[None, :]))
    return dict(period=P, repeats=K, polarity=sgn, symbol_err=serr, ber=berr, nbits=K * P * 2)

def ber_vs_ref(cap_sym, ref_sym):
    _, P, ref, _, _ = clean_pattern(ref_sym)         # clean reference pattern
    reftile = np.tile(ref, 4)
    best = None
    for sgn in (1, -1):
        dec = slice_dibits(cap_sym, sgn)
        N = min(len(dec), 20000); dec = dec[:N]
        rt = np.tile(ref, N // P + 2)
        for off in range(P):
            m = int(np.sum(rt[off:off + N] != dec))
            if best is None or m < best[1]: best = (m, sgn, off, dec, rt[off:off + N])
        _ = reftile
    _, sgn, off, dec, r = best
    serr = float(np.mean(dec != r))
    berr = float(np.mean(to_bits(dec) != to_bits(r)))
    return dict(period=P, polarity=sgn, offset=off, symbol_err=serr, ber=berr, nbits=len(dec) * 2)

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cap = args[0]
    ref = args[args.index('--ref') + 1] if '--ref' in args else None
    sym = demod(cap)
    print("capture: %s  (%d symbols recovered)" % (cap, len(sym)))
    if ref:
        r = ber_vs_ref(sym, demod(ref))
        print("mode: vs reference %s" % ref)
        print("  polarity %+d  offset %d  period %d" % (r['polarity'], r['offset'], r['period']))
        print("  symbol error: %.3f%%" % (100 * r['symbol_err']))
        print("  >>> BER: %.3f%%   (%d bits)" % (100 * r['ber'], r['nbits']))
    else:
        r = self_ber(sym)
        if not r: print("  too few pattern repeats to fold"); return
        print("mode: self-consistency (period fold)")
        print("  period %d dibits, %d repeats, polarity %+d" % (r['period'], r['repeats'], r['polarity']))
        print("  symbol error: %.3f%%" % (100 * r['symbol_err']))
        print("  >>> BER: %.3f%%   (%d bits)" % (100 * r['ber'], r['nbits']))

if __name__ == '__main__':
    main()
