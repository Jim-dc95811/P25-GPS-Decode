"""OP25-faithful C4FM front end, STDLIB-ONLY (no numpy/scipy) for the box.
discriminator float -> RMS-AGC -> C4FM RX de-emphasis FIR -> ready for fsk4_demod.

Identical math to the numpy frontend.py; the C4FM taps are precomputed per
sample rate in taps_data.py (so no runtime FFT), and the FIR is a plain
'same'-mode convolution matching numpy.convolve exactly.
"""
import math
from taps_data import C4FM_TAPS

def c4fm_taps(sample_rate):
    sr = int(sample_rate)
    if sr in C4FM_TAPS:
        return C4FM_TAPS[sr]
    # nearest known rate (48000 preferred)
    return C4FM_TAPS[min(C4FM_TAPS, key=lambda k: abs(k - sr))]

def rmsagc(x, alpha=0.01, k=1.0):
    out = [0.0] * len(x); rms = 1.0
    for i, v in enumerate(x):
        rms = (1.0 - alpha) * rms + alpha * (v * v)
        out[i] = v * (k / math.sqrt(rms) if rms > 1e-12 else 1.0)
    return out

def fir_same(a, v):
    """numpy.convolve(a, v, 'same') in pure Python: full conv then center slice."""
    M = len(v); N = len(a); off = (M - 1) // 2
    out = [0.0] * N
    for n in range(N):
        fn = n + off
        kmin = fn - (M - 1)
        if kmin < 0: kmin = 0
        kmax = fn
        if kmax > N - 1: kmax = N - 1
        s = 0.0
        for k in range(kmin, kmax + 1):
            s += a[k] * v[fn - k]
        out[n] = s
    return out

def _mean(x):
    return sum(x) / len(x) if x else 0.0

def _std(x):
    n = len(x)
    if n == 0: return 0.0
    m = sum(x) / n
    return math.sqrt(sum((v - m) * (v - m) for v in x) / n)

def prep_segment(a, sample_rate):
    """discriminator slice -> AGC'd, filtered, level-scaled signal for fsk4_demod
    (matches decode_capture: x-mean -> rmsagc -> c4fm FIR -> /std*sqrt(5))."""
    m = _mean(a)
    a = [v - m for v in a]
    a = rmsagc(a)
    a = fir_same(a, c4fm_taps(sample_rate))
    sd = _std(a) + 1e-9
    g = math.sqrt(5.0) / sd
    return [v * g for v in a]
