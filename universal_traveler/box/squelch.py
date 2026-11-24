"""Noise-quieting squelch + decode, STDLIB-ONLY for the box.

The right architecture (per the radios and the research):
  Stage 1 - a CHEAP noise-quieting squelch runs continuously. On an open-squelch
    FM discriminator the channel is full-scale broadband NOISE until a carrier
    captures the detector, at which point the high-frequency noise DROPS ("FM
    quieting") -- a P25 packet is a *hole* in the noise, not a spike. We measure
    the high-frequency energy as the mean squared sample-to-sample difference
    (a 1st-order high-pass; ~3 ops/sample) and open the squelch when it falls
    far below the running noise floor. Near-zero CPU through hours of dead air.
  Stage 2 - only while the squelch is OPEN do we run the expensive MMSE demod +
    frame-sync correlation + decode (decode_core.decode_at) on the captured
    quiet segment. The P25 frame-sync word IS the preamble you lock onto.

Measured on Jim's capture: noise HF ~1.0 of baseline; a packet drops to
~0.01-0.05 (20-100x). A threshold at ~0.2 catches every packet, no false opens.

This replaces the old band-ratio gate, which ran two biquads per sample on the
noise continuously and couldn't keep up on the MT3000 (ARM) -> capture overruns.
"""
import time
from decode_core import decode_at, split_nmea

HOP = 512               # samples per squelch evaluation (~11 ms @ 48k)
OPEN_FRAC = 0.30        # open squelch when HF energy < OPEN_FRAC * noise baseline
BASE_EWMA = 0.05        # noise-floor tracker (updated only while in NOISE)
PREROLL_S = 0.35        # capture window starts this far before the onset
CAP_S = 1.40            # total fixed capture length handed to the decoder
REFRACTORY_S = 1.0      # ignore re-opens within this of an onset


class SquelchDecoder:
    def __init__(self, fr, on_report, on_status=None):
        self.fr = int(fr)
        self.on_report = on_report
        self.on_status = on_status or (lambda *a, **k: None)
        self.buf = []            # rolling recent samples
        self.buf0_abs = 0        # abs index of buf[0]
        self.filled = 0
        self.acc = []            # samples not yet grouped into a HOP
        self.prev = 0.0          # last sample (diff continuity across hops)
        self.baseline = None     # HF noise-floor estimate
        self.state = 'NOISE'
        self.onset_abs = 0
        self.last_onset_abs = -10 ** 12
        self.keep = int((PREROLL_S + CAP_S + 1.0) * self.fr)
        self.packets = 0; self.reports = 0

    def _hf(self, blk):
        # mean squared first-difference = high-frequency (noise) energy
        d = 0.0; p = self.prev
        for v in blk:
            dv = v - p; d += dv * dv; p = v
        self.prev = p
        return d / len(blk)

    def feed(self, block):
        self.buf.extend(block); self.filled += len(block)
        self.acc.extend(block)
        while len(self.acc) >= HOP:
            blk = self.acc[:HOP]; del self.acc[:HOP]
            hf = self._hf(blk)
            pos = self.filled - len(self.acc)      # abs index at end of this hop
            self._gate(hf, pos)
        # trim buffer, but never past a pending capture
        need_from = self.filled - self.keep
        if self.state == 'OPEN':
            nf = self.onset_abs - int(PREROLL_S * self.fr)
            if nf < need_from: need_from = nf
        if need_from > self.buf0_abs:
            cut = need_from - self.buf0_abs
            del self.buf[:cut]; self.buf0_abs += cut

    def _seg(self, start_abs, end_abs):
        a = start_abs - self.buf0_abs; b = end_abs - self.buf0_abs
        if a < 0: a = 0
        if b > len(self.buf): b = len(self.buf)
        return self.buf[a:b]

    def _gate(self, hf, pos):
        if self.baseline is None:
            self.baseline = hf; return
        if self.state == 'NOISE':
            # channel quieted far below the noise floor -> a carrier captured.
            if (hf < OPEN_FRAC * self.baseline
                    and (pos - self.last_onset_abs) > REFRACTORY_S * self.fr):
                self.state = 'OPEN'; self.onset_abs = pos - HOP
                self.last_onset_abs = self.onset_abs
            else:
                self.baseline = (1 - BASE_EWMA) * self.baseline + BASE_EWMA * hf
        else:  # OPEN: capture a FIXED window from the onset, then decode.
            if pos - self.onset_abs >= int((CAP_S - PREROLL_S) * self.fr):
                start = self.onset_abs - int(PREROLL_S * self.fr)
                seg = self._seg(start, start + int(CAP_S * self.fr))
                self.state = 'NOISE'; self.packets += 1
                self._decode(seg)

    def _decode(self, seg):
        if len(seg) < int(0.3 * self.fr): return
        # onset sits at PREROLL into the fixed window; decode_at searches
        # leads + both polarities around it (the proven acquisition).
        p = decode_at(seg, self.fr, PREROLL_S)
        t = time.time()
        if not p:
            self.on_status('packet %d: no lock' % self.packets); return
        gga, pp = split_nmea(p)
        if gga:
            self.reports += 1; self.on_report(gga, pp, t)
        else:
            self.on_status('packet %d: partial' % self.packets)

    def flush(self):
        if self.state == 'OPEN':
            start = self.onset_abs - int(PREROLL_S * self.fr)
            self.state = 'NOISE'; self.packets += 1
            self._decode(self._seg(start, start + int(CAP_S * self.fr)))
