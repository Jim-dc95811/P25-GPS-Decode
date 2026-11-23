import sys, numpy as np, wave
from fsk4_demod import fsk4_demod
from frontend import front_end
from framer import decode_frames, pdu_blocks
from pdu_blocks import crc16
LVL2DIBIT=[3,2,0,1]
def km(v,it=80):
    c=np.quantile(v,[.125,.375,.625,.875])
    for _ in range(it):
        lab=np.abs(v[:,None]-c[None,:]).argmin(1);nc=np.array([v[lab==j].mean() if np.any(lab==j) else c[j] for j in range(4)])
        if np.allclose(nc,c):break
        c=nc
    return np.sort(c)
def asc(bs): return "".join(chr(c) if 32<=c<127 else "." for c in bs)
def slice_fixed(sym, pol):
    # fsk4_demod output is AGC'd to nominal +/-1,+/-3; slice at fixed [-2,0,2] (OP25-style)
    v = sym*pol
    return [LVL2DIBIT[b] for b in np.digitize(v, [-2.0, 0.0, 2.0])]
def burst_syms(x,fr0,s,span):
    a=x[int((s)*fr0):int((s+span)*fr0)].copy()
    a=front_end(a,fr0)                              # OP25 rmsagc + c4fm RX filter
    a=a/(np.std(a)+1e-9)*np.sqrt(5.0)
    return fsk4_demod(a,fr0,4800)
if __name__=="__main__":
    wav=sys.argv[1]; starts=[float(z) for z in sys.argv[2:]] or [1.0]
    w=wave.open(wav,'rb'); fr0=w.getframerate()
    x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768.0; w.close()
    for s in starts:
        sym=burst_syms(x,fr0,s-0.12,0.60)
        frames=[]
        for pol in (1,-1):                      # hardware polarity is fixed; try both, keep what locks
            fr=decode_frames(slice_fixed(sym,pol))
            if fr: frames=fr; break
        print(f"\n=== window @{s:.2f}s : {len(frames)} valid frame(s) ===")
        for f in frames:
            print(f"  frame start_sym {f['start']} nsyms {f['nsyms']} NAC 0x{f['nac']:03x} DUID 0x{f['duid']:x} ec {f['ec']}")
            if f['duid']==0xc:
                bv,blocks=pdu_blocks(f['fb'])
                payload=bytearray()
                for k,blk in enumerate(blocks):
                    if blk is None: continue
                    tag="HDR crc=%s"%("OK" if crc16(blk)==0 else "bad") if k==0 else ""
                    print(f"    blk{k}: {blk.hex()} |{asc(blk)}| {tag}")
                    if k>0: payload+=blk
                print("    PAYLOAD:", asc(payload))
