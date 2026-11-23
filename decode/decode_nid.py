"""Over-the-air P25 Tier-1 NID decode from a discriminator-audio WAV.
  python3 decode_nid.py <capture.wav> [burst_start_seconds ...]

Chain: WAV -> gentle DC-block -> scale to nominal 4 levels -> fsk4_demod (MMSE
symbol recovery) -> soft-NCC frame-sync hunt -> adaptive 4-level kmeans slice ->
dibits -> NID (status symbol stripped) -> BCH(63,16) -> NAC + DUID.

PROVEN 2026-11-23: NAC 0x455 (Jim's confirmed NAC) recovered on cleanly-synced
GPS bursts of the live-radio DEO capture. NOTE a key-up DC transient compresses
the sync/early-NID region of some bursts (a capture-side artifact — see
docs/DECODE_PLAN.md); robust all-burst framing + the PDU payload->NMEA path are
the next build (port OP25 p25_framer + the sndcp-fork trellis/deinterleave)."""
import sys, numpy as np, wave
from fsk4_demod import fsk4_demod
import bch_nid
SYNC=0x5575F5FF77FF; _b=[(SYNC>>(47-i))&1 for i in range(48)]
SD=[(_b[2*k]<<1)|_b[2*k+1] for k in range(24)]
SYMVAL={1:+3,0:+1,2:-1,3:-3}; TEMPL=np.array([SYMVAL[d] for d in SD],float)
TN=TEMPL/np.linalg.norm(TEMPL); LVL2DIBIT=[3,2,0,1]

def kmeans4(v,it=80):
    c=np.quantile(v,[.125,.375,.625,.875])
    for _ in range(it):
        lab=np.abs(v[:,None]-c[None,:]).argmin(1)
        nc=np.array([v[lab==j].mean() if np.any(lab==j) else c[j] for j in range(4)])
        if np.allclose(nc,c): break
        c=nc
    return np.sort(c)

def decode_burst(x, fr0, s):
    a=x[int((s-0.09)*fr0):int((s+0.32)*fr0)].copy()
    a-=np.convolve(a,np.ones(201)/201,mode='same'); a=a/(np.std(a)+1e-9)*np.sqrt(5.0)
    sym=fsk4_demod(a,fr0,4800)
    en=np.sqrt(np.convolve(sym**2,np.ones(24),'valid'))+1e-9
    cc=np.correlate(sym,TN,'valid')/en; bi=int(np.argmax(np.abs(cc))); best=cc[bi]
    use=sym*(1 if best>0 else -1)
    lv=kmeans4(use[max(0,bi-10):bi+130])   # LOCAL kmeans: adapt to the key-up transient levels near the header
    thr=[(lv[i]+lv[i+1])/2 for i in range(3)]
    db=np.array([LVL2DIBIT[bb] for bb in np.digitize(use,thr)])
    nidslots=list(db[bi+24:bi+57]); del nidslots[35-24]
    acc=0
    for d in nidslots[:32]: acc=(acc<<1)|((d>>1)&1); acc=(acc<<1)|(d&1)
    nac,duid,ec=bch_nid.nid_codeword(acc)
    return best,nac,duid,ec

if __name__=="__main__":
    wav=sys.argv[1]; starts=[float(z) for z in sys.argv[2:]] or [1.16]
    w=wave.open(wav,'rb'); fr0=w.getframerate()
    x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768.0; w.close()
    print("burst  syncNCC   NAC   DUID  ec")
    for k,s in enumerate(starts):
        best,nac,duid,ec=decode_burst(x,fr0,s)
        print(f"  {k+1:2d}   {best:+.2f}   0x{nac:03X}  {duid:2d}  {ec:3d}")
