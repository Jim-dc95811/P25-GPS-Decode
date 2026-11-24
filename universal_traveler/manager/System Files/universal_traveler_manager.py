#!/usr/bin/env python3
"""Universal Traveler Manager - set up a Universal Traveler box in one shot, from the PC.

The Universal Traveler decodes P25 GPS straight off the air (radio audio -> USB sound
card -> on-box decode) and serves a live split-screen map to any browser - no cooperating
base, no SDR, no PC. This app turns a bare GL-MT3000 into one in a single button.

A fully independent product: its own files, zero shared with the BK/Lookout managers
(a Universal Traveler box carries only Universal Traveler files).

Three tabs:
  * Set up a box  - point it at a GL-MT3000 (IP + admin password). It FIRST checks the
    box is on the kernel-6.6 firmware (OpenWrt 24.10), because that is the kernel where
    the USB sound card and the map SSD coexist on one hub. If the box is still on the old
    21.02/5.4 firmware it refuses and tells you to flash 6.6 via GL's dashboard first (a
    supported button - this app never flashes firmware itself). Then it installs
    everything over SSH: python3 + libusb + the sound-card driver, the decode engine, the
    GPS reader, the split-screen map server, the two boot services, starts them, verifies
    the map actually serves, and saves to flash.
  * Name units    - load the unit-ID -> name table from a running box, edit, save back.
  * Make QR card  - a print-ready sticker: scan it, the split-screen map opens. No typing.

The box files ship bundled beside this app (the "Universal Traveler Files" folder). Each
is streamed to the box with `cat > file`, which works on the box's dropbear SSH (no SFTP).
The box needs the internet only once, for the system packages from GL/OpenWrt's own feed.

Standard library + paramiko (SSH) + Pillow (the QR card). The .bat installs both.

Run:  double-click  Start Universal Traveler Manager.bat
"""
import os, sys, json, socket, http.client, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                 # so the QR tab can import the sealed lookout_qr

VERSION       = "1.0"
MAP_PORT      = 8088
FEED_PORT     = 10110
DEFAULT_IP    = "192.168.8.1"
DEFAULT_TOKEN = "lookout"


# --- the provisioning sequence -------------------------------------------------
# Built on the proven Lookout/Traveler provisioning engine. Two kinds of step:
#   sh(label, cmd)                        - a plain shell command
#   fetch(label, files, pre=.., post=..)  - stream files from the bundled
#       "Universal Traveler Files" folder onto the box (cat > remote).
# The kernel-6.6 check is NOT a step here - it runs first, before anything is
# touched, so a box on the wrong firmware is refused cleanly (see _run).
def sh(label, cmd):                            return ("sh", label, cmd)
def fetch(label, files, pre=None, post=None):  return ("fetch", label, files, pre, post)

# the sealed DSP decode engine (bit-exact, bolted in untouched)
_ENGINE = ["squelch.py", "decode_core.py", "frontend.py", "fsk4_demod.py",
           "framer.py", "pdu_blocks.py", "bch_nid.py", "taps_data.py"]

SETUP_STEPS = [
    sh("Updating the package list",            "opkg update"),
    sh("Installing Python (takes a minute)",   "which python3 >/dev/null 2>&1 && echo 'already installed' || opkg install python3"),
    sh("Installing GPS support (libusb)",      "opkg list-installed | grep -q '^libusb-1.0-0 ' && echo 'already installed' || opkg install libusb-1.0-0"),
    sh("Installing sound-card support",        "opkg list-installed | grep -q '^kmod-usb-audio ' && echo 'already installed' || opkg install kmod-usb-audio alsa-utils"),
    fetch("Delivering the decode engine",      [("ut_bridge.py", "/root/ut_bridge.py")] +
                                               [(f, "/root/" + f) for f in _ENGINE]),
    fetch("Delivering the GPS reader",         [("gps_source.py",   "/root/gps_source.py"),
                                                ("garmin_linux.py", "/root/garmin_linux.py")]),
    fetch("Delivering the map server",         [("units_kml.py",    "/root/units_kml.py")]),
    fetch("Delivering the split-screen map",   [("map.html",        "/root/map.html"),
                                                ("leaflet.js",      "/root/leaflet.js"),
                                                ("leaflet.css",     "/root/leaflet.css")]),
    fetch("Installing the boot services",      [("openwrt/ut-bridge", "/etc/init.d/ut-bridge"),
                                                ("openwrt/units-kml", "/etc/init.d/units-kml")],
                                               post="chmod +x /etc/init.d/ut-bridge /etc/init.d/units-kml"),
    sh("Enabling them on boot",                "/etc/init.d/ut-bridge enable && /etc/init.d/units-kml enable"),
    sh("Starting the services",                "/etc/init.d/ut-bridge start && /etc/init.d/units-kml start"),
    sh("Checking they are running",            "sleep 2; ps | grep -c '[p]ython3 /root'"),
    sh("Saving everything to flash",           "sync"),   # REQUIRED - or a power-pull reverts the whole setup
]

SERVICES_EXPECTED = 2   # decode bridge + map server


def all_fetch_files():
    out = []
    for step in SETUP_STEPS:
        if step[0] == "fetch":
            out.extend(step[2])
    return out

def default_files_dir():
    return HERE / "Universal Traveler Files"


# ======================= Set up a box tab =======================
class SetupTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.q = queue.Queue(); self.running = False
        self.files_dir = tk.StringVar(value=str(default_files_dir()))

        top = tk.Frame(self, padx=10, pady=10); top.pack(fill="x")
        tk.Label(top, text="New box IP").grid(row=0, column=0, sticky="w")
        self.ip = tk.Entry(top, width=16); self.ip.insert(0, DEFAULT_IP); self.ip.grid(row=0, column=1, padx=6)
        tk.Label(top, text="Admin password").grid(row=0, column=2, sticky="w")
        self.pw = tk.Entry(top, width=16, show="*"); self.pw.grid(row=0, column=3, padx=6)
        self.btn = tk.Button(top, text="Set up this box", command=self.start,
                             bg="#1f6feb", fg="white", font=("Segoe UI", 9, "bold"))
        self.btn.grid(row=0, column=4, padx=6)

        src = tk.LabelFrame(self, text=" Universal Traveler program files ", padx=10, pady=6)
        src.pack(fill="x", padx=12, pady=(2, 4))
        tk.Entry(src, textvariable=self.files_dir, width=52).grid(row=0, column=0, sticky="w", padx=(2, 4))
        tk.Button(src, text="Change...", command=self._browse).grid(row=0, column=1, sticky="w")

        tk.Label(self, anchor="w", padx=12, fg="#555", justify="left",
                 text="The box must already be on the kernel-6.6 firmware (OpenWrt 24.10) - flash it "
                      "once via GL's dashboard; this app checks and will tell you if it isn't. The box "
                      "then needs internet once for the system packages (python3 + libusb + sound-card "
                      "driver). Everything else streams from the folder above. SSH password is not saved."
                 ).pack(fill="x")

        box = tk.Frame(self, padx=12, pady=6); box.pack(fill="both", expand=True)
        self.log = tk.Text(box, wrap="word", height=16, font=("Consolas", 9),
                           bg="#101418", fg="#d6e2ee", insertbackground="#d6e2ee")
        lsb = tk.Scrollbar(box, command=self.log.yview); self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True); lsb.pack(side="right", fill="y")
        self.log.configure(state="disabled")
        self.log.tag_config("ok", foreground="#49d17a")
        self.log.tag_config("err", foreground="#ff6b6b")
        self.log.tag_config("step", foreground="#8ab4ff")
        self.after(120, self._drain)

    def _browse(self):
        d = filedialog.askdirectory(title="Pick the Universal Traveler Files folder",
                                    initialdir=self.files_dir.get() or ".")
        if d: self.files_dir.set(d)

    def write(self, msg, tag=None): self.q.put((msg, tag))

    def _drain(self):
        try:
            while True:
                msg, tag = self.q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n", tag or ())
                self.log.see("end"); self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def start(self):
        if self.running: return
        ip = self.ip.get().strip(); pw = self.pw.get()
        if not ip or not pw:
            return self.write("Enter the box IP and its admin password first.", "err")
        files_dir = self.files_dir.get().strip()
        missing = self._missing_local_files(files_dir)
        if missing is None:
            return self.write("Universal Traveler Files folder not found: %s\nClick \"Change...\" "
                              "and pick the folder bundled with this app." % files_dir, "err")
        if missing:
            return self.write("These files are missing from %s:\n   %s\nPick the right folder."
                              % (files_dir, "\n   ".join(missing)), "err")
        self.running = True
        self.btn.config(state="disabled", text="Setting up...")
        self.log.configure(state="normal"); self.log.delete("1.0", "end"); self.log.configure(state="disabled")
        threading.Thread(target=self._run, args=(ip, pw, files_dir), daemon=True).start()

    def _missing_local_files(self, files_dir):
        base = Path(files_dir)
        if not base.is_dir(): return None
        return [bp for bp, _r in all_fetch_files() if not (base / Path(bp)).is_file()]

    def _exec(self, c, cmd):
        _in, out, err = c.exec_command(cmd, timeout=240)
        for line in iter(out.readline, ""):
            if line.strip(): self.write("   " + line.rstrip())
        rc = out.channel.recv_exit_status()
        etxt = err.read().decode("utf-8", "replace").strip()
        if etxt:
            for line in etxt.splitlines(): self.write("   " + line)
        return rc

    def _capture(self, c, cmd):
        _in, out, _e = c.exec_command(cmd, timeout=20)
        return out.read().decode("utf-8", "replace").strip()

    def _put_file(self, c, local, remote):
        """Stream a local file to the box with `cat > remote` over a plain exec channel -
        works on dropbear SSH (no SFTP subsystem)."""
        with open(local, "rb") as fh:
            data = fh.read()
        stdin, stdout, stderr = c.exec_command("cat > '%s'" % remote, timeout=120)
        stdin.write(data); stdin.flush(); stdin.channel.shutdown_write()
        rc = stdout.channel.recv_exit_status()
        etxt = stderr.read().decode("utf-8", "replace").strip()
        if etxt:
            for line in etxt.splitlines(): self.write("   " + line)
        return rc

    def _kernel_ok(self, c):
        """Refuse any box not on the kernel-6.x firmware (OpenWrt 24.10). That is the kernel
        with the xhci-mtk fix, so the USB sound card and the map SSD coexist on one hub."""
        rel = self._capture(c, "uname -r") or "?"
        glv = self._capture(c, "cat /etc/glversion 2>/dev/null") or "?"
        self.write("Box kernel %s  (GL %s)" % (rel, glv), "step")
        major = rel.split(".", 1)[0]
        if major.isdigit() and int(major) >= 6:
            self.write("Kernel 6.x confirmed - sound card + SSD can share the hub.", "ok")
            return True
        self.write("This box is on kernel %s - too old for the Universal Traveler." % rel, "err")
        self.write("It needs the OpenWrt 24.10 / kernel-6.6 firmware so the USB sound card and the "
                   "map SSD work together on one hub.", "err")
        self.write("Flash it via GL's dashboard (Settings -> Upgrade -> the 24.10 / op24 image), "
                   "then run this again. This app never flashes firmware itself.", "err")
        return False

    def _verify(self, ip):
        """Functional check (not just 'a process is alive'): the map page actually serves on
        :8080 and the decoded feed is listening on :10110."""
        ok_map = ok_feed = False
        try:
            c = http.client.HTTPConnection(ip, MAP_PORT, timeout=6)
            c.request("GET", "/"); r = c.getresponse(); body = r.read(4000)
            ok_map = (r.status == 200 and (b"leaflet" in body.lower() or b"traveler" in body.lower()))
        except Exception:
            ok_map = False
        try:
            s = socket.create_connection((ip, FEED_PORT), timeout=6)
            s.settimeout(7)
            data = b""
            try:
                while b"\r\n" not in data and len(data) < 400:
                    chunk = s.recv(200)
                    if not chunk: break
                    data += chunk
            except socket.timeout:
                pass
            s.close()
            ok_feed = b"$" in data          # any NMEA line (the LINK heartbeat arrives within ~5s)
        except Exception:
            ok_feed = False
        return ok_map, ok_feed

    def _run(self, ip, pw, files_dir):
        try:
            import paramiko
        except ImportError:
            self.write("The SSH library (paramiko) is not installed. Close this and run the .bat "
                       "again - it installs it. Or: pip install paramiko", "err")
            return self._done()
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.write("Connecting to %s ..." % ip, "step")
            c.connect(ip, username="root", password=pw, timeout=12,
                      look_for_keys=False, allow_agent=False)
            self.write("Connected.", "ok")
        except Exception as e:
            self.write("Could not log in: %s" % e, "err")
            self.write("Check the IP, that it is a GL-MT3000, and the admin password.", "err")
            return self._done()
        try:
            if not self._kernel_ok(c):            # the firmware gate - refuse early, cleanly
                return self._done()
            self.write("Files: %s\n" % files_dir, "ok")
            for step in SETUP_STEPS:
                kind, label = step[0], step[1]
                self.write("== %s ==" % label, "step")
                if kind == "sh":
                    self._exec(c, step[2])
                else:
                    _, _, files, pre, post = step
                    if pre: self._exec(c, pre)
                    for bundle_path, remote in files:
                        local = str(Path(files_dir) / Path(bundle_path))
                        rc = self._put_file(c, local, remote)
                        self.write(("   sent %s" % remote) if rc == 0
                                   else ("   FAILED writing %s (exit %s)" % (remote, rc)),
                                   None if rc == 0 else "err")
                    if post: self._exec(c, post)
            count = self._capture(c, "ps | grep -c '[p]ython3 /root'") or "0"
            self.write("\nServices running: %s (expected %d)" % (count, SERVICES_EXPECTED), "step")
            self.write("Checking the map actually serves ...", "step")
            ok_map, ok_feed = self._verify(ip)
            self.write("   map page on :%d  -> %s" % (MAP_PORT, "OK" if ok_map else "not responding"),
                       "ok" if ok_map else "err")
            self.write("   decoded feed on :%d -> %s" % (FEED_PORT, "listening" if ok_feed else "silent"),
                       "ok" if ok_feed else "err")
            if ok_map and ok_feed:
                self.write("\nDONE - this box is now a Universal Traveler.", "ok")
                self.write("Plug the sound card (radio audio), the map SSD and the Garmin into the "
                           "powered hub, then open the split-screen map at  http://%s:%d/" % (ip, MAP_PORT), "ok")
                self.write("Make a QR sticker for it on the \"Make QR card\" tab.", "ok")
            else:
                self.write("\nSetup ran but the functional check did not pass - see the lines above "
                           "and the log for a package or file error, then re-run.", "err")
        except Exception as e:
            self.write("Setup stopped: %s" % e, "err")
        finally:
            try: c.close()
            except Exception: pass
            self._done()

    def _done(self):
        self.running = False
        self.after(0, lambda: self.btn.config(state="normal", text="Set up this box"))


# ======================= Name units tab =======================
class NamesTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        top = tk.Frame(self, padx=10, pady=10); top.pack(fill="x")
        tk.Label(top, text="Box IP").grid(row=0, column=0, sticky="w")
        self.ip = tk.Entry(top, width=16); self.ip.insert(0, DEFAULT_IP); self.ip.grid(row=0, column=1, padx=6)
        tk.Label(top, text="Token").grid(row=0, column=2, sticky="w")
        self.token = tk.Entry(top, width=12); self.token.insert(0, DEFAULT_TOKEN); self.token.grid(row=0, column=3, padx=6)
        tk.Button(top, text="Load from box", command=self.load).grid(row=0, column=4, padx=4)

        hdr = tk.Frame(self, padx=12); hdr.pack(fill="x")
        tk.Label(hdr, text="Unit ID", width=20, anchor="w", font=("Segoe UI", 9, "bold")).grid(row=0, column=0)
        tk.Label(hdr, text="Name",    width=28, anchor="w", font=("Segoe UI", 9, "bold")).grid(row=0, column=1)

        mid = tk.Frame(self); mid.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(mid, highlightthickness=0)
        sb = tk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.rows_frame = tk.Frame(self.canvas)
        self.rows_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.rows = []

        bot = tk.Frame(self, padx=10, pady=8); bot.pack(fill="x")
        tk.Button(bot, text="+ Add unit", command=lambda: self.add_row("", "")).pack(side="left")
        tk.Button(bot, text="Save to box", command=self.save, bg="#228B55", fg="white",
                  font=("Segoe UI", 9, "bold")).pack(side="right")
        self.status = tk.Label(self, text="Enter the box IP and click \"Load from box\".",
                               anchor="w", fg="#555", padx=12, pady=4)
        self.status.pack(fill="x")
        self.add_row("", "")

    def add_row(self, uid, name):
        fr = tk.Frame(self.rows_frame)
        e1 = tk.Entry(fr, width=20); e1.insert(0, uid); e1.grid(row=0, column=0, padx=2, pady=2)
        e2 = tk.Entry(fr, width=28); e2.insert(0, name); e2.grid(row=0, column=1, padx=2, pady=2)
        tk.Button(fr, text="-", width=2, command=lambda: self.del_row(fr)).grid(row=0, column=2, padx=4)
        fr.pack(anchor="w"); self.rows.append((fr, e1, e2))

    def del_row(self, fr):
        self.rows = [r for r in self.rows if r[0] is not fr]; fr.destroy()

    def clear(self):
        for fr, _, _ in self.rows: fr.destroy()
        self.rows = []

    def _conn(self):
        return http.client.HTTPConnection(self.ip.get().strip(), MAP_PORT, timeout=6)

    def load(self):
        try:
            c = self._conn()
            c.request("GET", "/admin/aliases?token=" + self.token.get().strip())
            r = c.getresponse(); data = json.loads(r.read() or b"{}")
            if r.status != 200 or not data.get("ok"):
                return self.set_status("Load failed: " + str(data.get("error", r.status)), True)
            al = data.get("aliases", {}); self.clear()
            for uid, name in sorted(al.items()): self.add_row(uid, name)
            if not al: self.add_row("", "")
            self.set_status("Loaded %d name(s) from %s." % (len(al), self.ip.get().strip()))
        except Exception as e:
            self.set_status("Could not reach the box: %s" % e, True)

    def save(self):
        out = {}
        for _, e1, e2 in self.rows:
            uid = e1.get().strip()
            if uid: out[uid] = e2.get().strip()
        try:
            c = self._conn()
            c.request("POST", "/admin/aliases?token=" + self.token.get().strip(),
                      body=json.dumps(out).encode(), headers={"Content-Type": "application/json"})
            r = c.getresponse(); data = json.loads(r.read() or b"{}")
            if r.status != 200 or not data.get("ok"):
                return self.set_status("Save failed: " + str(data.get("error", r.status)), True)
            self.set_status("Saved %s name(s). The map updates within a few seconds." % data.get("count"))
        except Exception as e:
            self.set_status("Could not reach the box: %s" % e, True)

    def set_status(self, msg, err=False):
        self.status.config(text=msg, fg="#c00" if err else "#282")


# ======================= Make QR card tab =======================
class QrTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        top = tk.Frame(self, padx=10, pady=12); top.pack(fill="x")
        tk.Label(top, text="Box IP").grid(row=0, column=0, sticky="w")
        self.ip = tk.Entry(top, width=16); self.ip.insert(0, DEFAULT_IP); self.ip.grid(row=0, column=1, padx=6)
        tk.Label(top, text="Label (optional)").grid(row=0, column=2, sticky="w")
        self.name = tk.Entry(top, width=20); self.name.grid(row=0, column=3, padx=6)
        tk.Button(top, text="Make QR card", command=self.make, bg="#1f6feb", fg="white",
                  font=("Segoe UI", 9, "bold")).grid(row=0, column=4, padx=6)
        tk.Label(self, anchor="w", padx=12, pady=8, fg="#555", justify="left",
                 text="Makes a print-ready sticker for the box. A crew scans it with a phone camera and "
                      "the split-screen map opens - no app, no typing, no login. The QR carries the "
                      "address explicitly as http:// so the phone won't force https.").pack(fill="x")
        self.status = tk.Label(self, text="", anchor="w", fg="#282", padx=12, pady=6, justify="left")
        self.status.pack(fill="x")

    def make(self):
        try:
            import lookout_qr                      # sealed QR encoder (bolted in)
        except Exception as e:
            return self._err("QR library not available (%s). Run the .bat so Pillow installs." % e)
        ip = self.ip.get().strip()
        if not ip:
            return self._err("Enter the box IP first.")
        url = lookout_qr.normalize("http://%s:%d/" % (ip, MAP_PORT))
        try:
            img = lookout_qr.make_card(url, box_name=self.name.get().strip())
            out_dir = Path.home() / "Downloads"
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = (self.name.get().strip() or ip).replace(os.sep, "_").replace(" ", "_")
            path = out_dir / ("Universal_Traveler_QR_%s.png" % safe)
            img.save(str(path))
            self.status.config(fg="#282",
                               text="Saved: %s\nScan opens  %s\nPrint it and stick it on the box." % (path, url))
        except Exception as e:
            self._err("Could not make the card: %s" % e)

    def _err(self, msg):
        self.status.config(text=msg, fg="#c00")


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Universal Traveler Manager v" + VERSION)
    root.geometry("620x620")
    nb = ttk.Notebook(root)
    nb.add(SetupTab(nb), text="  Set up a box  ")
    nb.add(NamesTab(nb), text="  Name units  ")
    nb.add(QrTab(nb),    text="  Make QR card  ")
    nb.pack(fill="both", expand=True)
    root.mainloop()
