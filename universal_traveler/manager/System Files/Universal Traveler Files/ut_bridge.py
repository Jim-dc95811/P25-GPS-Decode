#!/usr/bin/env python3
"""
ut_bridge.py  --  The Universal Traveler's input stage, on the box.

This is the one place the Universal Traveler differs from the BK Traveler: instead of
reading clean NMEA that a cooperating BK base already de-framed over USB-RNDIS, it
decodes P25 Tier-1 GPS *straight off the air* from the radio's discriminator audio, on
the box itself, and re-serves the result in the exact same shape the proven map expects.

Built fresh as one coherent program; it bolts in two sealed, proven modules and touches
neither:
  - the DSP decode engine  (squelch -> MMSE -> C4FM -> framer -> BCH/Viterbi -> NMEA)
  - gps_source             (the box's own Garmin "you are here", libusb D800)

What it does:
  1. Capture the radio audio from a USB sound card (arecord), GIL-safe: a reader thread
     does nothing but read() + hand off raw bytes, so a multi-second pure-Python decode
     can never stall the pipe (no arecord overrun on the slow ARM).
  2. Decode each GPS burst with the sealed SquelchDecoder.
  3. Normalise the NMEA  -- force the GGA talker-id to $GPGGA and recompute the checksum,
     so every broadcast sentence is checksum-valid (fixes the cosmetic $DNGGA/$JNGGA slip;
     position/id are untouched).
  4. Fold in the box's own Garmin fix as the reserved unit SELF_ID (what the split-screen
     centres "you are here" on), read on its own daemon thread by gps_source.
  5. Serve it all as plain NMEA-over-TCP on :10110, byte-compatible with bk_bridge, so
     units_kml / the split-screen map / the QR card are the proven Traveler, unchanged.
  6. Announce an audio-link heartbeat ($PLKT,LINK,UP/DOWN) that reflects the sound card:
     capturing -> UP; card pulled / arecord dead -> DOWN, so the map alarms on a lost tap.

Runs on OpenWrt (GL-MT3000) with python3 + alsa-utils + libusb. Stdlib only + the sealed
modules. Read-only: a radio is never transmitted to.

  python3 ut_bridge.py                 # live: sound card -> decode -> :10110
  python3 ut_bridge.py --replay x.wav  # self-check on a recording (no sound card)
"""
import os, re, sys, time, wave, array, socket, threading, subprocess
try:
    import queue
except ImportError:
    import Queue as queue

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from squelch import SquelchDecoder          # sealed DSP engine (entry point)
try:
    import gps_source                       # sealed Garmin "you are here" reader (optional)
except Exception:
    gps_source = None

VERSION = "1.1"

# ---- the sound card (Sound Blaster Play! 3, proven) ----
DEV   = os.environ.get("UT_AUDIO_DEV", "plughw:0,0")
RATE  = int(os.environ.get("UT_RATE", "48000"))     # card native (10 samples/symbol @ 4800 baud)
CH    = int(os.environ.get("UT_CH",   "2"))         # SB Play! 3 capture is stereo-only; fold to mono

# ---- downstream feed (byte-compatible with bk_bridge) ----
SERVE_HOST   = "0.0.0.0"
SERVE_PORT   = int(os.environ.get("UT_PORT", "10110"))
SEND_TMO_S   = 5.0        # drop a viewer that can't accept data this fast
LINK_EVERY_S = 5.0        # audio-link heartbeat cadence
AUDIO_STALL_S = 10.0      # no audio for this long => sound card hung; restart arecord + alarm
FEED_ERR_RESET = 5        # this many consecutive decode errors => rebuild the decoder

# ---- the box's own position ----
GPS_ENABLE   = os.environ.get("UT_GPS", "1") != "0"
SELF_ID      = os.environ.get("UT_SELF_ID", "LOOKOUT")   # must match map.html SELF_ID (centres on it)
GPS_RESCAN_S = 20


# ================= NMEA helpers =================
def _cs(body):
    """Wrap a sentence body as $body*CS with a freshly computed NMEA-0183 XOR checksum."""
    g = 0
    for c in body:
        g ^= ord(c)
    return "$%s*%02X" % (body, g)

def _clean_gga(gga):
    """Normalise a decoded GGA: force the talker-id to GP and recompute the checksum.
    The sentence type and the data fields pass through as decoded; only the (known-fixed)
    talker-id is corrected, so a stray bit in the prefix can't hand the map a bad sentence."""
    body = gga[1:].split("*", 1)[0]
    i = body.find("GGA")
    if i < 0:
        return None
    return _cs("GP" + body[i:])

def _clean_pp(pp):
    """Canonical $PP25,<id>, with a fresh checksum (real radio shape: trailing comma keeps
    the checksum out of the id field so units_kml reads the id clean)."""
    m = re.search(r"PP25,(\d+)", pp)
    if not m:
        return None
    return _cs("PP25,%s," % m.group(1))


# ================= client fan-out (proven bk_bridge design) =================
_clients = set()
_lock = threading.Lock()

def broadcast(sentence):
    data = (sentence + "\r\n").encode("ascii", "replace")
    with _lock:
        clients = list(_clients)                 # copy, then send WITHOUT holding the lock
    dead = []
    for c in clients:
        try:
            c.sendall(data)                      # socket has a send timeout; a stuck reader raises
        except OSError:
            dead.append(c)
    if dead:
        with _lock:
            for c in dead:
                _clients.discard(c)
        for c in dead:
            try: c.close()
            except OSError: pass

def _serve_clients():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((SERVE_HOST, SERVE_PORT))
    srv.listen(16)
    print("[ut] serving NMEA on tcp %s:%d (units_kml reads this)" % (SERVE_HOST, SERVE_PORT), flush=True)
    while True:
        try:
            conn, addr = srv.accept()
        except OSError:
            time.sleep(0.5); continue
        conn.settimeout(SEND_TMO_S)
        with _lock:
            _clients.add(conn); n = len(_clients)
        print("[ut] viewer connected %s (%d)" % (addr[0], n), flush=True)


# ================= audio-link heartbeat (reflects the sound card) =================
_link_up = False
_link_printed = None

def _set_link(up):
    global _link_up, _link_printed
    _link_up = up
    if _link_printed != up:
        print("[ut] audio link %s" % ("UP" if up else "DOWN"), flush=True)
        _link_printed = up
        broadcast(_cs("PLKT,LINK,UP" if up else "PLKT,LINK,DOWN"))   # announce change at once

def _link_beat():
    while True:
        broadcast(_cs("PLKT,LINK,UP" if _link_up else "PLKT,LINK,DOWN"))
        time.sleep(LINK_EVERY_S)


# ================= the box's own position (Garmin "you are here") =================
def _gps_loop():
    """Read the local Garmin over libusb and broadcast the box's own fix as unit SELF_ID.
    Own daemon thread; swallows every error so it can never disturb the decoded feed."""
    if not (GPS_ENABLE and gps_source):
        return
    absent = False
    while True:
        try:
            src, stream = gps_source.open_source(SELF_ID, log=lambda m: print(m, flush=True))
        except Exception as e:
            src, stream = None, None
            print("[gps] reader error: %s - will look again" % e, flush=True)
        if not src:
            if not absent:
                print("[gps] no local GPS yet - box won't show its own position "
                      "(decoded feed unaffected). Still looking.", flush=True)
                absent = True
            time.sleep(GPS_RESCAN_S); continue
        absent = False
        print("[gps] local GPS live on %s - adding this box as unit '%s'" % (src.name, SELF_ID), flush=True)
        try:
            for sen in stream:                   # gps_source already outputs clean, tagged NMEA
                broadcast(sen)
        except Exception as e:
            print("[gps] %s stopped: %s - will look again" % (getattr(src, "name", "GPS"), e), flush=True)
        finally:
            try: src.close()
            except Exception: pass
        time.sleep(GPS_RESCAN_S)


# ================= decode: a report -> normalised NMEA on the feed =================
def _on_report(gga, pp, t_wall):
    g = _clean_gga(gga) if gga else None
    p = _clean_pp(pp) if pp else None
    if not g:
        return
    stamp = time.strftime("%H:%M:%S", time.localtime(t_wall))
    print("  [%s] %s   %s" % (stamp, g, p or ""), flush=True)
    broadcast(g)
    if p:
        broadcast(p)


# ================= live capture (GIL-safe) =================
def _drain(proc, q, stop):
    """Reader thread: drain arecord's pipe as RAW BYTES only. read() releases the GIL and the
    put is trivial, so even while a pure-Python decode holds the GIL for seconds in the
    consumer, this keeps the pipe empty and arecord never overruns. The fold is deferred to
    the consumer, which has idle time between the ~10 s-apart bursts to catch up."""
    while not stop.is_set():
        data = proc.stdout.read(8192)
        if not data:
            break
        try:
            q.put(data, timeout=2)
        except queue.Full:
            pass
    q.put(None)

def _mk_decoder():
    return SquelchDecoder(RATE, _on_report, lambda m: None)

def run_live():
    cmd = ["arecord", "-D", DEV, "-f", "S16_LE", "-c", str(CH), "-r", str(RATE), "-t", "raw", "-q"]
    frame = CH * 2
    inv = 1.0 / (32768.0 * CH)
    print("[ut] Universal Traveler bridge v%s - %s @ %d Hz, %d ch -> mono (OTA decode)"
          % (VERSION, DEV, RATE, CH), flush=True)
    while True:
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            _set_link(False)
            print("[ut] cannot start arecord (%s) - alsa-utils installed? retrying" % e, flush=True)
            time.sleep(4); continue
        print("[ut] listening for GPS bursts ...", flush=True)
        _set_link(True)
        dec = _mk_decoder()                  # fresh decoder each session - no stale buffer/baseline
        q = queue.Queue(maxsize=1024)
        rstop = threading.Event()
        threading.Thread(target=_drain, args=(p, q, rstop), daemon=True).start()
        carry = b""; feed_errs = 0; got_audio = False
        try:
            while True:
                try:
                    data = q.get(timeout=AUDIO_STALL_S)      # watchdog: a hung card never delivers
                except queue.Empty:
                    print("[ut] no audio for %gs - sound card hung or gone; restarting arecord"
                          % AUDIO_STALL_S, flush=True)
                    break
                if data is None:                              # arecord ended (card pulled / died)
                    break
                got_audio = True
                data = carry + data
                usable = len(data) - (len(data) % frame)
                carry = data[usable:]
                a = array.array("h"); a.frombytes(data[:usable])
                if CH == 1:
                    blk = [v / 32768.0 for v in a]
                else:
                    blk = [sum(a[i:i + CH]) * inv for i in range(0, len(a), CH)]
                if not blk:
                    continue
                try:                                          # isolate the decode: one bad burst
                    dec.feed(blk); feed_errs = 0              # must not drop the audio tap
                except Exception as e:
                    feed_errs += 1
                    print("[ut] decode block error: %s (skipped, capture continues)" % e, flush=True)
                    if feed_errs >= FEED_ERR_RESET:
                        print("[ut] repeated decode errors - rebuilding the decoder", flush=True)
                        dec = _mk_decoder(); feed_errs = 0
        except Exception as e:
            print("[ut] capture error: %s - restarting arecord" % e, flush=True)
        finally:
            rstop.set()
            try: p.kill()
            except Exception: pass
        if not got_audio:                     # fast fail: surface why arecord produced nothing
            try:
                err = (p.stderr.read() or b"").decode("utf-8", "replace").strip() if p.stderr else ""
            except Exception:
                err = ""
            if err:
                print("[ut] arecord: %s" % err.splitlines()[0], flush=True)
            print("[ut] no audio captured - check the sound card / 'arecord -l' and the DEV (%s)." % DEV, flush=True)
        _set_link(False)
        time.sleep(2)


# ================= replay (no sound card) =================
def run_replay(wav):
    w = wave.open(wav, "rb"); fr = w.getframerate(); nch = w.getnchannels()
    a = array.array("h"); a.frombytes(w.readframes(w.getnframes())); w.close()
    x = [v / 32768.0 for v in (a[::nch] if nch > 1 else a)]
    dec = SquelchDecoder(fr, _on_report, lambda m: None)
    print("[ut] REPLAY %s (%d Hz, %.1fs)" % (os.path.basename(wav), fr, len(x) / fr), flush=True)
    _set_link(True)
    time.sleep(1.0)
    for s in range(0, len(x), 2048):
        dec.feed(x[s:s + 2048])
    dec.flush()
    print("[ut] replay done. feed stays up (Ctrl+C to stop).", flush=True)
    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def main():
    threading.Thread(target=_serve_clients, daemon=True).start()
    threading.Thread(target=_link_beat, daemon=True).start()
    if GPS_ENABLE and gps_source:
        threading.Thread(target=_gps_loop, daemon=True).start()
    args = sys.argv[1:]
    wav = None
    if "--replay" in args:
        k = args.index("--replay")
        if k + 1 < len(args):
            wav = args[k + 1]
    else:
        for a in args:
            if a.lower().endswith(".wav"):
                wav = a; break
    try:
        if wav: run_replay(wav)
        else:   run_live()
    except KeyboardInterrupt:
        print("\n[ut] stopped.", flush=True)


if __name__ == "__main__":
    main()
