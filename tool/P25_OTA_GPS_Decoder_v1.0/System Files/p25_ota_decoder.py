#!/usr/bin/env python3
"""
P25 OTA GPS Decoder  -  decode P25 Tier-1 GPS location straight off the air.

Point it at a WAV recording of a radio's DISCRIMINATOR / detector audio (e.g.
Kenwood NX-700 DEO pin 19, set WIDE) and it recovers each GPS report as NMEA --
the exact $G?GGA + $PP25,<unit-id> sentence the fleet transmits -- with no BK
base, no SDR, no cooperating gateway. It is the over-the-air counterpart to the
RNDIS NMEA Logger: that one reads finished NMEA from a cooperating BK base; this
one decodes it from the raw air.

Usage:  drop a .wav file onto 'Decode P25 GPS from a recording.bat',
        or run:  python3 p25_ota_decoder.py <capture.wav>

Output: prints every decoded report, and writes a timestamped log next to this
tool (decoded_nmea_YYYYMMDD_HHMMSS.log) in the same $GNGGA/$PP25 form as the
RNDIS logger, so the two can be diffed line for line.

Capture: mono PCM WAV, 48 kHz preferred (integer 10 samples/symbol). Radio WIDE,
squelch open, Windows audio 'enhancements' OFF. Needs: numpy, scipy (the .bat
installs them). Read-only throughout; a radio is never transmitted to or altered.
"""
import sys, os, re, wave
from datetime import datetime
import numpy as np
from scipy.signal import spectrogram, lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fsk4_demod import fsk4_demod
from framer import decode_frames, pdu_blocks
from frontend import c4fm_rx_taps
from pdu_blocks import count_bits

VERSION = "1.0"
LVL2DIBIT = [3, 2, 0, 1]
MAGIC = 0x5575F5FF77FF; MASK = (1 << 48) - 1

def _asc(bs): return "".join(chr(c) if 32 <= c < 127 else "." for c in bs)
def _rmsagc(x, a=0.01, k=1.0):
    r = np.maximum(lfilter([a], [1.0, -(1.0 - a)], x * x), 1e-12); return x * (k / np.sqrt(r))

def detect_bursts(x, fr0):
    f, t, S = spectrogram(x, fr0, nperseg=1024, noverlap=512)
    low = S[(f >= 100) & (f <= 2900)].sum(0); high = S[(f > 3000) & (f <= 10000)].sum(0) + 1e-12
    r = np.convolve(low / high, np.ones(9) / 9, 'same'); thr = 0.5 * (np.median(r) + r.max())
    starts = []; prev = False
    for i, a in enumerate(r > thr):
        if a and not prev and (not starts or t[i] - starts[-1] > 1.0): starts.append(float(t[i]))
        prev = a
    return starts

def _best_sync(db, region=700):
    acc = 0; best = 99; bi = 0
    for i, d in enumerate(db[:region]):
        acc = ((acc << 2) | (d & 3)) & MASK
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

def decode_burst(x, fr0, tstart, taps, span=0.55):
    for lead in (0.06, 0.10, 0.03, 0.15, 0.00):
        a = x[int((tstart - lead) * fr0):int((tstart + span) * fr0)].copy()
        a = a - np.mean(a); a = _rmsagc(a); a = np.convolve(a, taps, 'same'); a = a / (np.std(a) + 1e-9) * np.sqrt(5.0)
        sym = fsk4_demod(a, fr0, 4800)
        for sgn in (1, -1):
            db = [LVL2DIBIT[b] for b in np.digitize(sgn * sym, [-2., 0., 2.])]
            frames = decode_frames(db, sync_errth=6)
            if frames:
                p = _payload_at(db, frames[0]['start'])
                if _good(p): return p
            bi, h = _best_sync(db)
            if bi >= 23:
                p = _payload_at(db, bi - 23)
                if _good(p): return p
    return None

_GGA = re.compile(r"\$..GGA,[^*]*\*[0-9A-Fa-f]{2}")
_PP25 = re.compile(r"\$PP25,[0-9]+,?\*?[0-9A-Fa-f]{0,2}")

def sentences(pay):
    gga = _GGA.search(pay); pp = _PP25.search(pay)
    return (gga.group(0) if gga else None), (pp.group(0) if pp else None)

def main(wav):
    w = wave.open(wav, 'rb'); fr0 = w.getframerate(); nch = w.getnchannels()
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float) / 32768.0; w.close()
    if nch > 1: raw = raw[::nch]          # take one channel if stereo
    taps = c4fm_rx_taps(fr0)
    bursts = detect_bursts(raw, fr0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logpath = os.path.join(HERE, "..", "decoded_nmea_%s.log" % ts)
    print("P25 OTA GPS Decoder v%s" % VERSION)
    print("file: %s  (%d Hz, %.1fs, %d bursts detected)\n" % (os.path.basename(wav), fr0, len(raw) / fr0, len(bursts)))
    ok = 0
    with open(logpath, "w") as lf:
        lf.write("# P25 OTA GPS decode  %s  file=%s\n" % (ts, os.path.basename(wav)))
        for i, t in enumerate(bursts):
            p = decode_burst(raw, fr0, t, taps)
            if not p:
                print("  report %2d (t=%6.2fs):  [no lock - weak burst]" % (i + 1, t)); continue
            gga, pp = sentences(p)
            if gga: print("  report %2d (t=%6.2fs):  %s   %s" % (i + 1, t, gga, pp or "")); ok += 1
            else:   print("  report %2d (t=%6.2fs):  [partial] %s" % (i + 1, t, p[:60]))
            if gga: lf.write("%s\n" % gga)
            if pp:  lf.write("%s\n" % pp)
    print("\n%d of %d reports decoded.  Log written: %s" % (ok, len(bursts), os.path.abspath(logpath)))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".wav"):
        wav = sys.argv[1]
    else:
        wav = input("Drag a .wav recording here (or type its path) and press Enter:\n> ").strip().strip('"')
    if not os.path.isfile(wav):
        print("File not found: %s" % wav); sys.exit(1)
    main(wav)
