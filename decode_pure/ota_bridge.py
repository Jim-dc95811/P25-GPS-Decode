#!/usr/bin/env python3
"""
ota_bridge.py  -  the Universal Traveler's input stage, ON THE BOX.

Reads the radio's discriminator audio from a USB sound card via ALSA `arecord`,
decodes P25 Tier-1 GPS in pure Python (no numpy/scipy), and re-serves each report
as NMEA-over-TCP on :10110 -- byte-for-byte the same feed bk_bridge put out, so
units_kml reads it unchanged. This is the drop-in replacement for bk_bridge that
turns a BK Traveler into a Universal Traveler: no cooperating base, any P25 fleet.

Runs on the GL-MT3000 (OpenWrt, aarch64) with only python3 + alsa-utils -- the
same sound-card stack the Lookout audio feature already installs. Stdlib only.

  python3 ota_bridge.py                 # live: arecord -> decode -> :10110
  python3 ota_bridge.py --replay x.wav  # self-check on a recording (no sound card)

Env: LOOKOUT_AUDIO_DEV (default plughw:0,0), OTA_PORT (default 10110),
     OTA_RATE (default 48000).  Read-only: a radio is never transmitted to.
"""
import sys, os, time, socket, threading, subprocess, array, wave
try:
    import queue
except ImportError:
    import Queue as queue

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from squelch import SquelchDecoder

VERSION = "1.3"
RATE = int(os.environ.get("OTA_RATE", "48000"))   # card native (direct USB, not behind a hub)
DEV = os.environ.get("LOOKOUT_AUDIO_DEV", "plughw:0,0")
CH = int(os.environ.get("OTA_CH", "2"))        # SB Play! 3 capture is stereo-only; fold to mono
PORT = int(os.environ.get("OTA_PORT", "10110"))
LINK_EVERY_S = 5.0


def _nmea_mk(body):
    g = 0
    for c in body: g ^= ord(c)
    return "$%s*%02X" % (body, g)


class NmeaServer:
    """bk_bridge-compatible :10110 feed: CRLF sentences + $PLKT,LINK,UP heartbeat."""
    def __init__(self, port=PORT):
        self.port = port; self.clients = set(); self.lock = threading.Lock()
        self.stop = threading.Event()

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", self.port)); s.listen(8); self.srv = s
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._beat, daemon=True).start()
        print("[ota] serving NMEA on tcp 0.0.0.0:%d (units_kml reads this)" % self.port, flush=True)

    def _accept(self):
        while not self.stop.is_set():
            try: conn, addr = self.srv.accept()
            except OSError: return
            conn.settimeout(5)
            with self.lock: self.clients.add(conn)
            print("[ota] viewer connected %s (%d)" % (addr[0], len(self.clients)), flush=True)

    def broadcast(self, sentence):
        data = (sentence + "\r\n").encode("ascii", "replace")
        with self.lock: cs = list(self.clients)
        for c in cs:
            try: c.sendall(data)
            except Exception:
                try: c.close()
                except Exception: pass
                with self.lock: self.clients.discard(c)

    def _beat(self):
        while not self.stop.is_set():
            self.broadcast(_nmea_mk("PLKT,LINK,UP")); self.stop.wait(LINK_EVERY_S)


def _logger():
    LOG_DIR = os.path.join(HERE, "logs")
    try: os.makedirs(LOG_DIR, exist_ok=True)
    except Exception: LOG_DIR = HERE
    path = os.path.join(LOG_DIR, "ota_%s.log" % time.strftime("%Y%m%d"))
    return open(path, "a", buffering=1), path


def _make_on_report(server, lf):
    state = {"n": 0}
    def on_report(gga, pp, t_wall):
        state["n"] += 1
        stamp = time.strftime("%H:%M:%S", time.localtime(t_wall))
        print("  [%s] %s   %s" % (stamp, gga, pp or ""), flush=True)
        iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_wall))
        lf.write("%s  %s\n" % (iso, gga))
        if pp: lf.write("%s  %s\n" % (iso, pp))
        server.broadcast(gga)
        if pp: server.broadcast(pp)
    return on_report, state


def _drain(proc, q, stop):
    """Reader thread: drain arecord's pipe as RAW BYTES only -- no conversion.
    read() releases the GIL and the put is trivial, so even while a pure-Python
    decode hogs the GIL for seconds in the consumer (the ARM is ~20x slower than
    a PC), this thread keeps the pipe empty and arecord never overruns. The
    byte->float fold is deferred to the consumer, which has idle time between
    the ~10 s-apart bursts to catch up on any backlog."""
    while not stop.is_set():
        data = proc.stdout.read(8192)
        if not data:
            break
        try:
            q.put(data, timeout=2)
        except queue.Full:
            pass   # consumer wedged badly; drop a chunk (pipe stays drained)
    q.put(None)   # sentinel: arecord ended


def run_live(server):
    lf, path = _logger()
    on_report, state = _make_on_report(server, lf)
    dec = SquelchDecoder(RATE, on_report, lambda m: print("  .. %s" % m, flush=True))
    cmd = ["arecord", "-D", DEV, "-f", "S16_LE", "-c", str(CH), "-r", str(RATE), "-t", "raw", "-q"]
    print("[ota] P25 OTA bridge v%s - capturing %s @ %d Hz, %d ch -> mono (noise-quieting squelch)"
          % (VERSION, DEV, RATE, CH), flush=True)
    print("[ota] log: %s" % path, flush=True)
    frame = CH * 2  # bytes per frame (S16 = 2 bytes/sample)
    while not server.stop.is_set():
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        except Exception as e:
            print("[ota] cannot start arecord (%s) - is alsa-utils installed? retrying" % e, flush=True)
            time.sleep(4); continue
        print("[ota] listening for GPS bursts ...", flush=True)
        q = queue.Queue(maxsize=1024)                   # ~40s of raw audio backlog
        rstop = threading.Event()
        rt = threading.Thread(target=_drain, args=(p, q, rstop), daemon=True)
        rt.start()
        inv = 1.0 / (32768.0 * CH)
        carry = b""
        try:
            while not server.stop.is_set():
                data = q.get()                          # raw bytes; reader keeps pipe drained
                if data is None:
                    break                               # arecord ended
                data = carry + data
                usable = len(data) - (len(data) % frame)   # whole frames only
                carry = data[usable:]
                a = array.array("h"); a.frombytes(data[:usable])
                if CH == 1:
                    blk = [v / 32768.0 for v in a]
                else:                                   # fold interleaved ch -> mono
                    blk = [sum(a[i:i + CH]) * inv for i in range(0, len(a), CH)]
                if blk:
                    dec.feed(blk)                       # decode here; pipe still drains
        except Exception as e:
            print("[ota] decode error: %s - restarting arecord" % e, flush=True)
        finally:
            rstop.set()
            try: p.kill()
            except Exception: pass
        time.sleep(2)   # card yanked / arecord died -> reopen


def run_replay(wav, server):
    w = wave.open(wav, "rb"); fr = w.getframerate(); nch = w.getnchannels()
    a = array.array("h"); a.frombytes(w.readframes(w.getnframes())); w.close()
    x = [v / 32768.0 for v in (a[::nch] if nch > 1 else a)]
    lf, path = _logger()
    on_report, state = _make_on_report(server, lf)
    dec = SquelchDecoder(fr, on_report, lambda m: None)
    print("[ota] REPLAY %s (%d Hz, %.1fs)" % (os.path.basename(wav), fr, len(x) / fr), flush=True)
    if server: time.sleep(1.5)
    for s in range(0, len(x), 2048): dec.feed(x[s:s + 2048])
    dec.flush()
    print("[ota] replay done: %d reports. feed stays up (Ctrl+C to stop)." % state["n"], flush=True)
    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def main():
    server = NmeaServer(PORT); server.start()
    wav = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--replay" and i + 1 < len(args): wav = args[i + 1]
        elif a.lower().endswith(".wav"): wav = a
    try:
        if wav: run_replay(wav, server)
        else:   run_live(server)
    except KeyboardInterrupt:
        print("\n[ota] stopped.", flush=True)
    finally:
        server.stop.set()


if __name__ == "__main__":
    main()
