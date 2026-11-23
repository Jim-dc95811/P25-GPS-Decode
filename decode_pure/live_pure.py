"""Streaming STDLIB-ONLY P25 OTA decoder for the box (no numpy/scipy).

Feed audio BLOCKS (lists of mono float samples) with LivePureDecoder.feed();
two stateful band-pass biquads run continuously as the burst gate, and when a
transmission keys up a fixed-length window is captured and decoded with the
proven decode_at. on_report(gga, pp25, t_wall) fires per GPS report.

Same design as the numpy live_core, re-implemented pure-Python so it runs on the
MT3000: the biquads carry their own z-state across blocks, so the gate is a
constant, cheap per-sample IIR (no FFT).
"""
import time, math
from decode_core import _biquad, decode_at, split_nmea

HOP = 512
RATIO_K = 8.0; RATIO_ABS_MIN = 8.0
PREROLL_S = 0.35; CAP_S = 1.40; REFRACTORY_S = 1.0; NOISE_EWMA = 0.02
LO_F = 1500; HI_F = 6000


class _Band:
    """A single band-pass biquad that keeps its state across feed() blocks and
    emits one mean-square value per HOP samples."""
    def __init__(self, f0, Q, fs):
        self.b0, self.b1, self.b2, self.a1, self.a2 = _biquad(f0, Q, fs)
        self.z1 = self.z2 = 0.0; self.s = 0.0; self.n = 0

    def push(self, xi):
        y = self.b0 * xi + self.z1
        self.z1 = self.b1 * xi - self.a1 * y + self.z2
        self.z2 = self.b2 * xi - self.a2 * y
        self.s += y * y; self.n += 1
        if self.n == HOP:
            ms = self.s / HOP; self.s = 0.0; self.n = 0
            return ms
        return None


class LivePureDecoder:
    def __init__(self, fr, on_report, on_status=None):
        self.fr = int(fr)
        self.on_report = on_report
        self.on_status = on_status or (lambda *a, **k: None)
        self.lo = _Band(LO_F, 0.7, self.fr)
        self.hi = _Band(HI_F, 0.9, self.fr)
        self.keep = int((PREROLL_S + CAP_S + 1.0) * self.fr)
        self.buf = []            # rolling recent samples
        self.buf0_abs = 0        # absolute index of buf[0]
        self.filled = 0
        self.noise = 1.0; self.trig = RATIO_ABS_MIN
        self.state = 'IDLE'; self.onset_abs = 0; self.last_onset_abs = -10 ** 12
        self.reports = 0; self.bursts = 0

    def feed(self, block):
        base = self.filled
        self.buf.extend(block); self.filled += len(block)
        lo = self.lo; hi = self.hi
        for k, xi in enumerate(block):
            lo_ms = lo.push(xi); hi_ms = hi.push(xi)   # lockstep: both close the same hop
            if lo_ms is not None:
                r = lo_ms / (hi_ms + 1e-12)
                self._gate(r, base + k + 1)
        # trim buffer (keep enough for a pending capture)
        need_from = self.filled - self.keep
        if self.state == 'BURST':
            nf = self.onset_abs - int(PREROLL_S * self.fr)
            if nf < need_from: need_from = nf
        if need_from > self.buf0_abs:
            cut = need_from - self.buf0_abs
            del self.buf[:cut]; self.buf0_abs += cut

    def _seg(self, start_abs, length):
        a = start_abs - self.buf0_abs
        if a < 0: a = 0
        return self.buf[a:a + length]

    def _gate(self, r, pos_abs):
        if self.state == 'IDLE':
            self.trig = max(RATIO_ABS_MIN, RATIO_K * self.noise)
            if r > self.trig and (pos_abs - self.last_onset_abs) > REFRACTORY_S * self.fr:
                self.state = 'BURST'; self.onset_abs = pos_abs - HOP
                self.last_onset_abs = self.onset_abs
            else:
                self.noise = (1 - NOISE_EWMA) * self.noise + NOISE_EWMA * (r if r < 5.0 else 5.0)
        else:
            if pos_abs - self.onset_abs >= int((CAP_S - PREROLL_S) * self.fr):
                seg = self._seg(self.onset_abs - int(PREROLL_S * self.fr), int(CAP_S * self.fr))
                self.state = 'IDLE'; self.bursts += 1; self._decode(seg)

    def _decode(self, seg):
        if len(seg) < int(0.3 * self.fr): return
        p = decode_at(seg, self.fr, PREROLL_S)
        t = time.time()
        if not p:
            self.on_status('burst %d: no lock (weak)' % self.bursts); return
        gga, pp = split_nmea(p)
        if gga:
            self.reports += 1; self.on_report(gga, pp, t)
        else:
            self.on_status('burst %d: partial' % self.bursts)

    def flush(self):
        if self.state == 'BURST':
            seg = self._seg(self.onset_abs - int(PREROLL_S * self.fr), int(CAP_S * self.fr))
            self.state = 'IDLE'; self.bursts += 1; self._decode(seg)
