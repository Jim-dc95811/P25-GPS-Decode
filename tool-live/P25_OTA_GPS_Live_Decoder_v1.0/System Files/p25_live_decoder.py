#!/usr/bin/env python3
"""
P25 OTA GPS Live Decoder  -  decode P25 Tier-1 GPS location LIVE off the air.

Listens to a radio's DISCRIMINATOR / detector audio on a USB sound card (e.g. a
Sound Blaster taking the Kenwood NX-700 DEO pin 19, radio set WIDE) and decodes
each GPS report as it keys up -- the exact $G?GGA + $PP25,<unit-id> sentence the
fleet transmits -- with no BK base, no SDR, no cooperating gateway. This is the
live counterpart of the recording decoder: same proven decode core, fed by the
sound card instead of a WAV file. (The Traveler ingests the air live; it does
not use wave files -- this is that front end.)

Run it, pick the sound-card input, and leave it listening. Every GPS report
prints with a wall-clock time and is appended to a timestamped log in the same
$GNGGA/$PP25 form as the RNDIS reference feed, so the two diff line for line.
Ctrl+C to stop.

Needs: numpy, scipy, sounddevice (the .bat installs them). 48 kHz mono capture,
Windows audio 'enhancements' OFF. Read-only throughout -- a radio is never
transmitted to or altered.
"""
import sys, os, time, queue, threading
from datetime import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from live_core import LiveDecoder

VERSION = "1.0"
RATE = 48000                      # ask the card for 48 kHz mono (integer 10 sps)
BLOCK = 2048                      # callback block size
DEV_HINTS = ("blaster", "sb play", "usb audio", "usb-audio", "usb pnp", "line (")


def pick_device(sd, forced=None):
    """Return (device_index, name). Auto-pick a likely discriminator input,
    else list inputs and ask."""
    devs = sd.query_devices()
    ins = [(i, d) for i, d in enumerate(devs) if d["max_input_channels"] > 0]
    if forced is not None:
        d = devs[forced]; return forced, d["name"]
    # auto: first input whose name matches a hint
    for i, d in ins:
        nm = d["name"].lower()
        if any(h in nm for h in DEV_HINTS):
            return i, d["name"]
    # otherwise ask
    print("\nAvailable sound-card inputs:")
    for i, d in ins:
        print("  [%d] %s  (%d ch, %d Hz)" % (i, d["name"], d["max_input_channels"], int(d["default_samplerate"])))
    while True:
        s = input("Enter the number of the input the radio is wired to: ").strip()
        if s.isdigit() and int(s) in [i for i, _ in ins]:
            return int(s), devs[int(s)]["name"]
        print("  not a listed input number; try again.")


def replay(wavpath):
    """Feed a recording through the live streaming engine (no sound card) --
    proves the live decode path against a known capture."""
    import wave
    w = wave.open(wavpath, "rb"); rate = w.getframerate(); nch = w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float) / 32768.0
    w.close()
    if nch > 1: x = x[::nch]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logpath = os.path.join(HERE, "..", "live_nmea_%s.log" % ts)
    lf = open(logpath, "w", buffering=1)
    lf.write("# P25 OTA GPS live decode (REPLAY of %s)  %s\n" % (os.path.basename(wavpath), ts))
    state = {"n": 0}
    def on_report(gga, pp, t_wall):
        state["n"] += 1
        print("  report %2d:  %s   %s" % (state["n"], gga, pp or ""))
        lf.write("%s\n" % gga)
        if pp: lf.write("%s\n" % pp)
    dec = LiveDecoder(rate, on_report, lambda m: None)
    print("P25 OTA GPS Live Decoder v%s  --  REPLAY mode" % VERSION)
    print("file: %s  (%d Hz, %.1fs)\n" % (os.path.basename(wavpath), rate, len(x) / rate))
    for s in range(0, len(x), BLOCK):   # feed as if arriving from the card
        dec.feed(x[s:s + BLOCK])
    dec.flush()
    lf.close()
    print("\n%d report%s decoded. log: %s" % (state["n"], "" if state["n"] == 1 else "s", os.path.abspath(logpath)))


def main():
    for i, a in enumerate(sys.argv[1:]):
        if a == "--replay" and i + 2 <= len(sys.argv) - 1:
            return replay(sys.argv[i + 2])
        if a.lower().endswith(".wav"):
            return replay(a)
    try:
        import sounddevice as sd
    except Exception as e:
        print("Could not load sounddevice (%s)." % e)
        print("The .bat installs it; if you ran the .py directly: pip install sounddevice")
        sys.exit(1)

    forced = None
    for a in sys.argv[1:]:
        if a.startswith("--device="): forced = int(a.split("=", 1)[1])
    dev, name = pick_device(sd, forced)

    rate = RATE
    try:
        sd.check_input_settings(device=dev, channels=1, samplerate=RATE, dtype="float32")
    except Exception:
        rate = int(sd.query_devices(dev)["default_samplerate"])
        print("Note: device won't do 48 kHz; using its %d Hz." % rate)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logpath = os.path.join(HERE, "..", "live_nmea_%s.log" % ts)
    lf = open(logpath, "w", buffering=1)
    lf.write("# P25 OTA GPS live decode  started %s  device='%s' %d Hz\n"
             % (datetime.now().isoformat(timespec="milliseconds"), name, rate))

    state = {"n": 0}

    def on_report(gga, pp, t_wall):
        state["n"] += 1
        stamp = datetime.fromtimestamp(t_wall).strftime("%H:%M:%S")
        iso = datetime.fromtimestamp(t_wall).isoformat(timespec="milliseconds")
        print("  [%s]  %s   %s" % (stamp, gga, pp or ""))
        lf.write("%s  %s\n" % (iso, gga))
        if pp: lf.write("%s  %s\n" % (iso, pp))

    def on_status(msg):
        print("   .. %s" % msg)

    dec = LiveDecoder(rate, on_report, on_status)
    q = queue.Queue()

    def cb(indata, frames, tinfo, status):
        # keep the audio callback light: copy one channel and hand off
        q.put(indata[:, 0].copy())

    print("P25 OTA GPS Live Decoder v%s" % VERSION)
    print("listening on: %s  (%d Hz mono)" % (name, rate))
    print("log: %s" % os.path.abspath(logpath))
    print("waiting for GPS bursts ... (Ctrl+C to stop)\n")

    stop = threading.Event()

    def worker():
        last_beat = time.time()
        while not stop.is_set():
            try:
                blk = q.get(timeout=0.5)
            except queue.Empty:
                blk = None
            if blk is not None:
                dec.feed(blk)
            # quiet heartbeat every ~30 s so the operator sees it's alive
            if time.time() - last_beat > 30:
                last_beat = time.time()
                print("   .. listening (%d report%s so far)"
                      % (state["n"], "" if state["n"] == 1 else "s"))

    th = threading.Thread(target=worker, daemon=True); th.start()
    try:
        with sd.InputStream(device=dev, channels=1, samplerate=rate,
                            dtype="float32", blocksize=BLOCK, callback=cb):
            while True:
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nstopping ...")
    finally:
        stop.set(); th.join(timeout=2)
        lf.close()
        print("stopped. %d report%s decoded. log: %s"
              % (state["n"], "" if state["n"] == 1 else "s", os.path.abspath(logpath)))


if __name__ == "__main__":
    main()
