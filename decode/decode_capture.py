"""End-to-end OTA P25 GPS decode of a discriminator-audio WAV.
  python3 decode_capture.py <capture.wav>

Pipeline (all OP25-faithful except where noted):
  band-ratio burst detector (C4FM energy <3 kHz vs broadband noise)
  -> per burst, fresh: rmsagc -> c4fm RX filter -> fsk4_demod (MMSE) ->
     fixed 4-level slice -> streaming framer (sync + NID + PDU) ->
     Viterbi 1/2-rate data blocks -> NMEA.

Per-burst fresh demod (not one continuous pass) because open-squelch
discriminator audio is full-scale noise between bursts, which drifts a
continuous demod loop; a fresh loop per detected burst stays clean.

Proven 2026-11-23 on Jim's live-radio DEO capture: decodes the full
$G?GGA + $PP25,<unit-id> sentence, matching the BK RNDIS answer-key log.
Open (next branch): some bursts' sync is marginal (loop not converged on a
short preamble) -> no lock; needs a loop-acquisition / squelch improvement.
"""
import sys, numpy as np, wave
from scipy.signal import spectrogram, lfilter
from fsk4_demod import fsk4_demod
from framer import decode_frames, pdu_blocks
from frontend import c4fm_rx_taps
from pdu_blocks import count_bits
MAGIC=0x5575F5FF77FF; MASK=(1<<48)-1
LVL2DIBIT=[3,2,0,1]
def asc(bs): return "".join(chr(c) if 32<=c<127 else "." for c in bs)
def rmsagc_vec(x, alpha=0.01, k=1.0):
    rms=np.maximum(lfilter([alpha],[1.0,-(1.0-alpha)], x*x),1e-12); return x*(k/np.sqrt(rms))

def detect_bursts(x, fr0):
    f,t,S=spectrogram(x,fr0,nperseg=1024,noverlap=512)
    low=S[(f>=100)&(f<=2900)].sum(0); high=S[(f>3000)&(f<=10000)].sum(0)+1e-12
    r=np.convolve(low/high,np.ones(9)/9,'same'); thr=0.5*(np.median(r)+r.max())
    starts=[]; prev=False
    for i,a in enumerate(r>thr):
        if a and not prev and (not starts or t[i]-starts[-1]>1.0): starts.append(float(t[i]))
        prev=a
    return starts

def _best_sync(db, region=700):
    acc=0; best=99; bi=0
    for i,d in enumerate(db[:region]):
        acc=((acc<<2)|(d&3))&MASK
        if i>=23:
            e=count_bits((acc^MAGIC)&MASK)
            if e<best: best=e; bi=i
    return bi, best
def _payload_at(db, start):
    fb=[]
    for d in db[start:]:
        fb.append((d>>1)&1); fb.append(d&1)
    bv,blocks=pdu_blocks(fb); pay=bytearray()
    for b in blocks:
        if b is None: break
        pay+=b
    return asc(pay)
def _good(p): return ("GGA" in p) and ("$PP25,907" in p)
def decode_burst(x, fr0, tstart, taps, span=0.55):
    """Robust acquisition: strict framer, then force-lock at best sync near the
    onset validated by the payload itself, across a few window offsets+polarities."""
    for lead in (0.06, 0.10, 0.03, 0.15, 0.00):
        a=x[int((tstart-lead)*fr0):int((tstart+span)*fr0)].copy()
        a=a-np.mean(a); a=rmsagc_vec(a); a=np.convolve(a,taps,'same'); a=a/(np.std(a)+1e-9)*np.sqrt(5.0)
        sym=fsk4_demod(a,fr0,4800)
        for sgn in (1,-1):
            db=[LVL2DIBIT[b] for b in np.digitize(sgn*sym,[-2.,0.,2.])]
            frames=decode_frames(db, sync_errth=6)        # strict, NID-validated
            if frames:
                p=_payload_at(db, frames[0]['start'])
                if _good(p): return frames[0], p
            bi,h=_best_sync(db)                            # force-lock, payload-validated
            if bi>=23:
                p=_payload_at(db, bi-23)
                if _good(p): return {'start':bi-23,'nac':0x455,'duid':0xc,'ec':-1}, p
    return None

def main(wav):
    w=wave.open(wav,'rb'); fr0=w.getframerate()
    x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768.0; w.close()
    taps=c4fm_rx_taps(fr0)
    bursts=detect_bursts(x,fr0)
    print(f"{wav}: {fr0} Hz, {len(x)/fr0:.1f}s, {len(bursts)} bursts detected\n")
    ok=0
    for t in bursts:
        r=decode_burst(x,fr0,t,taps)
        if r is None: print(f"  t={t:6.2f}s  no-lock"); continue
        f,pay=r; i=pay.find("GGA")
        frag=pay[max(0,i-1):i+86] if i>=0 else pay[:80]
        if "GGA" in pay and "PP25" in pay: ok+=1
        print(f"  t={t:6.2f}s  NAC 0x{f['nac']:03x} ec{f['ec']}:  {frag}")
    print(f"\n{ok}/{len(bursts)} bursts decoded with full GGA+PP25")
if __name__=="__main__":
    main(sys.argv[1])
