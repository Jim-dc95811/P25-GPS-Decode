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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from live_pure import LivePureDecoder

VERSION = "1.0"
RATE = int(os.environ.get("OTA_RATE", "48000"))
DEV = os.environ.get("LOOKOUT_AUDIO_DEV", "plughw:0,0")
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


def run_live(server):
    lf, path = _logger()
    on_report, state = _make_on_report(server, lf)
    dec = LivePureDecoder(RATE, on_report, lambda m: print("  .. %s" % m, flush=True))
    cmd = ["arecord", "-D", DEV, "-f", "S16_LE", "-c", "1", "-r", str(RATE), "-t", "raw", "-q"]
    print("[ota] P25 OTA bridge v%s - capturing %s @ %d Hz" % (VERSION, DEV, RATE), flush=True)
    print("[ota] log: %s" % path, flush=True)
    while not server.stop.is_set():
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        except Exception as e:
            print("[ota] cannot start arecord (%s) - is alsa-utils installed? retrying" % e, flush=True)
            time.sleep(4); continue
        print("[ota] listening for GPS bursts ...", flush=True)
        try:
            while True:
                data = p.stdout.read(8192)
                if not data:
                    break
                a = array.array("h"); a.frombytes(data if len(data) % 2 == 0 else data[:-1])
                dec.feed([v / 32768.0 for v in a])
        except Exception as e:
            print("[ota] capture error: %s - restarting arecord" % e, flush=True)
        finally:
            try: p.kill()
            except Exception: pass
        time.sleep(2)   # card yanked / arecord died -> reopen


def run_replay(wav, server):
    w = wave.open(wav, "rb"); fr = w.getframerate(); nch = w.getnchannels()
    a = array.array("h"); a.frombytes(w.readframes(w.getnframes())); w.close()
    x = [v / 32768.0 for v in (a[::nch] if nch > 1 else a)]
    lf, path = _logger()
    on_report, state = _make_on_report(server, lf)
    dec = LivePureDecoder(fr, on_report, lambda m: None)
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
