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

def decode_burst(x, fr0, tstart, taps, lead=0.06, span=0.55):
    a=x[int((tstart-lead)*fr0):int((tstart+span)*fr0)].copy()
    a=a-np.mean(a); a=rmsagc_vec(a); a=np.convolve(a,taps,'same'); a=a/(np.std(a)+1e-9)*np.sqrt(5.0)
    sym=fsk4_demod(a,fr0,4800)
    for sgn in (1,-1):
        db=[LVL2DIBIT[b] for b in np.digitize(sgn*sym,[-2.,0.,2.])]
        frames=decode_frames(db)
        if frames: break
    if not frames: return None
    f=frames[0]
    if f['duid']!=0xc: return f, ""
    bv,blocks=pdu_blocks(f['fb']); pay=bytearray()
    for b in blocks:
        if b is None: break
        pay+=b
    return f, asc(pay)

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
