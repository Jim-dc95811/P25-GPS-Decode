# The Universal Traveler — End-to-End Bring-Up, 2026-11-23

*Written Claude-to-Claude. This is the dense technical record of the night the whole
chain closed: P25 Tier-1 GPS decoded off the air, on a $40 battery router, plotted on
an offline split-screen map with the box's own position, nothing installed on the
viewer. If you're resuming, read `CLAUDE.md` → `docs/DECODE_PLAN.md` →
`docs/UNIVERSAL_TRAVELER.md` for the spec; this doc is the **how it actually works and
why each piece is shaped the way it is**, at a level only a future me will care about.*

---

## 0. What closed tonight (the one-sentence result)

On a bare GL-MT3000 (MediaTek MT7981, aarch64 Cortex-A53, 512 MB) running OpenWrt
24.10 / kernel 6.6.110, a Sound Blaster Play! 3, a 124 GB SSD, and a Garmin GPS 18 USB
all on one powered hub: a live P25 fleet radio (unit `9076802`) was **decoded off the
air by the box** and plotted live in both panes of a locked hybrid|street Leaflet
split-screen served over the box's own offline TPKX basemap, alongside the box's own
Garmin fix (`LOOKOUT`), with **nothing installed on the viewing browser** and **no
cooperating base radio anywhere in the chain**. Reboot-survival proven (both services
came back on a cold power cycle with all three USB devices attached).

This is the BK-independent product: the "Universal Traveler." Its input stage is a
software P25 receiver; everything downstream is the proven Traveler, untouched.

---

## 1. The architecture invariant that made it tractable

**The decoder's entire job is to emit the exact NMEA that `bk_bridge` emits.** Nothing
more. `units_kml`, `map.html`, the split-screen, the you-are-here centering, the unit
aging — all of it already works against a `:10110` TCP feed of
`$GxGGA … \r\n` + `$PP25,<id>,*cs \r\n`. So the OTA work is a **drop-in replacement
for the RNDIS input stage**, not a new system. `ut_bridge.py` replaces `bk_bridge.py`
and emits byte-compatible sentences; `units_kml` cannot tell the difference.

That invariant is also the success criterion: **decoder NMEA == RNDIS NMEA (same
position AND same individual ID)** is a byte diff against ground truth, provable
standalone against `rig/rndis_nmea_logger.py` before the box is ever touched. We proved
10/10 position+ID exact on a clean capture earlier; tonight was the on-box live run.

---

## 2. The box can't have numpy/scipy — so the DSP is stdlib, and that's the whole trick

`opkg` on op24/MT3000 offers only `python3-numpy-src` (source, no compiled C) and **no
`python3-scipy` at all**. The numpy/scipy decoder that was proven on the PC cannot run
on the box. The entire on-box decoder is therefore **pure standard-library Python**,
which is the Lookout-family way (`bk_bridge`/`units_kml` are all stdlib).

Why that was feasible and not insane:
- `framer.py` + `pdu_blocks.py` (the FEC: frame sync, BCH NID, Viterbi 1/2-rate PDU
  deinterleave, CRC) were **already numpy-free**.
- **No runtime FFT is needed.** The old burst gate used two time-domain biquads; the
  new squelch (below) needs none. The C4FM RX filter and MMSE filter taps are
  **precomputed once** into `taps_data.py`.
- The MMSE symbol-tracking loop (`tracking_loop_mmse`, ported from OP25) was already
  scalar arithmetic — it ports to stdlib unchanged.

Feasibility measured: gate ~0.007× realtime, decode ~0.1 s/burst, streaming ~0.023×
realtime on the dev box → ~0.46× realtime on the MT3000 (~20× slower ARM). Bursts are
~10 s apart, so it keeps up in real time with margin.

---

## 3. The noise-quieting squelch — the single most important box-side idea

**The problem it solves:** a continuous band-ratio gate (two biquads per sample over
the open-squelch noise) could not keep up on the MT3000 and overran `arecord`
instantly. You cannot run expensive DSP continuously on this ARM.

**Jim's insight, which is the whole design:** on an open-squelch FM discriminator the
channel is **full-scale broadband noise** until a carrier captures the detector, at
which point the high-frequency noise **drops** ("FM quieting"). **A P25 packet is a
*hole* in the noise, not a spike.** So the continuous stage can be dirt cheap: measure
high-frequency energy and watch for it to *fall*.

Implementation (`decode_pure/squelch.py`, bolted into `universal_traveler/box/`):
- HF energy = **mean squared sample-to-sample difference** (a 1st-order high-pass,
  ~3 ops/sample), evaluated per `HOP = 512` samples (~11 ms @ 48 k). `_hf()` carries
  `self.prev` across hops so the difference is continuous.
- A noise-floor EWMA (`BASE_EWMA = 0.05`) tracks the baseline **only while in NOISE**.
- Open when `hf < OPEN_FRAC * baseline` (`OPEN_FRAC = 0.30`), guarded by a
  `REFRACTORY_S = 1.0` s refractory so one burst can't re-trigger.
- Measured contrast: noise HF ~1.0× baseline; a keyed GPS burst drops to ~0.01–0.05
  (20–100×). Detection is not marginal.

**The capture-geometry landmine (cost two rebuilds):** the decoder needs the *full*
~0.55 s burst span *after* the onset, but the HF ratio falls ~0.25 s in, so gating the
capture on the ratio *drop/release* truncates the burst → garbled GGA (ID still fine,
because the ID PDU happens to sit early). The fix is a **fixed-geometry window**: on
open, mark `onset_abs`, then once `CAP_S - PREROLL_S` of samples have arrived past the
onset, slice a fixed `[onset - PREROLL_S, onset - PREROLL_S + CAP_S]` window
(`PREROLL_S = 0.35`, `CAP_S = 1.40`) and hand it to the proven `decode_at(seg, fr,
PREROLL_S)`. A **variable window + a custom onset-finder regressed to 1–2/10**; fixed
geometry = 10/10. Do not "improve" this by re-deriving the onset. The rolling buffer is
a plain contiguous list with exact absolute-index slicing (`_seg`), never a circular
ring with abs-index math — the ring was the *other* misalignment source.

`decode_at` itself is the proven robust acquisition: strict NID-validated framer →
fallback force-lock at the best-Hamming sync near the onset, **validated by the payload
itself** ($PP25 id + readable GGA), across a few lead offsets and both polarities.

---

## 4. The GIL overrun bug (ut_bridge `_drain`) — why the reader does *nothing* but read

The pure-Python decode is CPU-bound and holds the GIL for **seconds per burst** on ARM.
The symptom live: decoding only started at the *4th* burst, then caught up.

Root cause: `ut_bridge` v1.2's reader thread did the stereo→mono fold itself. The fold
is Python-level arithmetic → **needs the GIL** → the reader got starved whenever the
consumer was mid-decode → it stopped draining `arecord`'s pipe → `overrun!!!` for 7+ s
→ ALSA dropped the next 1–3 bursts.

Fix (v1.3, the shipped `_drain`): the reader thread does **nothing but
`proc.stdout.read(8192)` (releases the GIL) and `q.put(raw_bytes)` (trivial)**. The
stereo→mono fold and all decode moved to the *consumer* (`run_live`), which has idle
time between the ~10 s-apart bursts to catch up. The pipe stays drained even mid-decode
→ no overruns, consecutive bursts caught. `arecord` is left exactly as proven on the SB
Play! 3: **stereo-only** (`-c 2`), `plughw:0,0`, `S16_LE`, 48 k, `-t raw`. Fold in the
consumer: `array('h')` from the raw bytes, `sum(a[i:i+CH]) * (1/(32768*CH))`, carry the
partial trailing frame across reads (`carry = data[usable:]`).

---

## 5. ut_bridge as a byte-compatible bk_bridge, and the NMEA normalization

`ut_bridge.py` is built fresh (not patched from bk_bridge) but emits an identical wire
feed:
- **Fan-out** (`broadcast`): copy the client set under a lock, then `sendall` *without*
  holding the lock; per-socket `SEND_TMO_S = 5` s timeout so a stuck viewer raises
  `OSError` and gets reaped. Same shape as the proven bk_bridge.
- **Link heartbeat**: `$PLKT,LINK,UP/DOWN` every `LINK_EVERY_S = 5` s and instantly on
  change, reflecting the **sound card** now (not a radio-link). `units_kml`'s alarm
  logic consumes this unchanged, so the box never sits in a false RADIO-LINK-DOWN.
- **NMEA normalization** — the cosmetic-but-necessary cleanup of decoder output:
  - `_clean_gga`: find `"GGA"` in the decoded body, force the talker-id to **`GP`**,
    recompute the XOR checksum. This fixes the decoder's occasional garbled talker-id
    (`$DNGGA`, `$JNGGA` — residual bit errors Viterbi didn't fully clean) **without
    touching position/id**, which are already clean. A stray prefix bit can't hand the
    map a bad sentence.
  - `_clean_pp`: canonical `$PP25,<id>,` with a fresh checksum. The **trailing comma**
    matters — it keeps the checksum out of the id field so `units_kml`'s
    `split(",")[1]` reads a clean id.
  - `_cs(body)`: the one XOR-checksum wrapper both use.

`units_kml` searched for "GGA" and read the id after `PP25,`, so even pre-normalization
the dot plotted; normalization makes the sentences textbook-clean for anything stricter
downstream.

---

## 6. The USB bandwidth story — the real fix, not the workaround

**Why kernel 6.6 at all.** On the MT3000's shipped kernel 5.4.211, the `xhci-mtk`
scheduler rejects a full-speed USB audio device sitting **behind a hub** with a
periodic-bandwidth error — the Transaction Translator periodic-bandwidth accounting is
buggy. That forced the sound card to be plugged **directly** into the box, which left
nowhere for the map SSD. Jim explicitly **rejected** the rate-reduction workaround
(cripple the capture to fit the broken accounting) as "slumming."

**The root fix:** the `xhci-mtk` TT periodic-bandwidth fix is in **kernel 6.6**
(mainline). GL's `4.8.3-op24` line is OpenWrt 24.10.4 / kernel 6.6.110. On 6.6 the
full-speed sound card, the full-speed Garmin, and the SuperSpeed SSD **all enumerate
together behind one powered hub** — proven tonight in `dmesg`:
```
usb 1-1.2: new full-speed USB device ...   (sound card)
usb 1-1.4: new full-speed USB device ...   (Garmin 091e:0003)
usb 2-1.1: new SuperSpeed USB device ...   (PNY SSD, sda1, 124 GB)
```
`/dev/snd/` → `controlC0 pcmC0D0c pcmC0D0p timer` (capture node present),
`/tmp/mountd/disk1_part1` mounted. **This is the entire hardware risk of the project,
cleared on real silicon.** op24's feed also carries `python3` (3.11.18), `libusb`,
`kmod-usb-audio` (6.6.110-r1), `alsa-utils` — all resolved during the Manager run, so
the whole stack stands up on op24. (Flash is manual via GL's dashboard; keep-settings
OFF when crossing op21→op24.)

---

## 7. The box's own position — Garmin over libusb, and the fix-gate decision

`gps_source.open_source()` tries, in order: **Garmin GPS 18 USB direct over libusb**
(ctypes, the proven D800 path) → gpsd → serial NMEA puck → Garmin-over-pyusb fallback.
Garmin-first fails instantly when absent, so it's free on other setups and leads on the
proven hardware. Only dependency: `libusb-1.0-0`.

`garmin_linux.GarminLibusb` (sealed, proven 2026-11-16 on the router):
- Enumerate `091e:0003`, `detach_kernel_driver(0)` to take it from the `garmin_gps`
  kmod if loaded, claim interface 0.
- **Discover the endpoints from the device's own config descriptor** — hardcoding
  `0x02` fails `rc=-1`; discovery found `OUT=0x03(bulk) IN=0x82(int) bulk_in=0x81`.
- D800 session: send Start_Session, send Start_Pvt → device streams type-20/id-51 PVT
  ~1/s. Reassemble the interrupt packets. Decode the 64-byte D800 record
  (`lat/lon` in **radians** → ×180/π; MSL alt = `alt − msl_hght`).

**The fix-gate decision (the thing Jim caught me on, and was right about).** The reader
emitted a GGA only when the D800 `fix` field was `>= 2` (2D/3D). The puck indoors
reported `fix=1` ("invalid/unavailable") **with a stable, precise, correct position**
(30.39384, −81.93782, repeated exactly). That `>= 2` threshold was **my arbitrary
choice, not Garmin's rule**, and it threw away a usable position — exactly the degraded
fix a firefighter gets indoors or under canopy, which is *when they most need to be
located*. Changed `garmin_linux.py:191` from `if fix < 2` → `if fix < 1`: reject only
`fix=0` (Garmin's own "failed integrity check"), **trust 1+** with the existing
coordinate sanity check (`_coords_ok`: NaN / (0,0) / out-of-range). The system already
ages units to stale/amber, so a degraded fix is labeled, not hidden. With sky view the
puck locks `fix=3` and plots regardless; the change is purely about **not discarding a
usable low-confidence position**. Applied to the box reader *and* the Manager's bundled
copy. (The fixed Lookout/BK-Traveler is a separate product; left untouched.)

Lesson for next-me: **don't blame the puck.** When the hardware is handing you a stable
correct position, a threshold you wrote is the suspect, not the GPS.

`ut_bridge._gps_loop` runs this on its own daemon thread, swallowing every error so a
GPS hiccup can never disturb the decoded feed, and `broadcast`s each tagged sentence as
unit `SELF_ID = "LOOKOUT"` (what `map.html` centers "you are here" on). Note: a silent
`import gps_source` failure zeroes the whole self-GPS path with no log — if there's no
`[gps]` line at all, suspect the import or that the thread never started, not the Garmin.

---

## 8. The Manager (one-shot provisioner) — what it actually does

PC-side tkinter app, family-standard package (one `.bat` + `System Files` + PDF with
install blurb), zero shared files with the BK Traveler Manager. Three tabs: **Set up a
box** / **Name units** / **Make QR card**.

Provision sequence (`SETUP_STEPS`), each step verified, all over the box's real
dropbear SSH:
1. **Kernel-6.6 gate FIRST** — read `uname -r`; a 5.4 box is **refused** with "flash
   24.10/6.6 via GL's dashboard first." No scripted `sysupgrade` (brick risk); the user
   flashes via GL's supported dashboard button.
2. `opkg update` → `python3` → `libusb-1.0-0` → `kmod-usb-audio` + `alsa-utils`.
3. **Stream the whole box bundle via `cat > '<remote>'` on a plain exec channel**
   (bytes to stdin, `shutdown_write()`). **Never SFTP** — dropbear has no SFTP
   subsystem; `paramiko.open_sftp()` → `EOF during negotiation`. (This crashed an
   earlier Lookout Manager that passed the sandbox because the stub faked SFTP.)
4. Install + enable the two **procd** boot services (`ut-bridge`, `units-kml`), start
   them, **`sync`** (overlay writes sit in page cache; a power-pull before sync reverts
   to flash state).
5. **Functional verify** — GET the map on the map port AND socket-check the feed port
   (`:10110`). Not a process count — the "3 services alive but map dead" trap is real.

---

## 9. Tonight's bring-up log (the bugs, in order)

1. **Manager v1.0 run ended in a loud FAILURE** with the USB unplugged. Two faults,
   both mine: (a) a too-strict/too-alarming verify that *worded* a port-conflict failure
   as if the whole thing was dead, which misled Jim into suspecting the unplugged cable;
   (b) the actual failure was a **port conflict**, not the cable. The map page lives on
   the box, so the map server runs with or without the SSD — an unplugged stick does NOT
   fail the server check. (Behavioral lesson, logged because it matters: answer the
   exact question asked, plainly, then wait.)
2. **Port 8080 conflict.** On op24, GL's **uhttpd** owns `127.0.0.1:8080` (and 8443).
   `units_kml`'s `0.0.0.0:8080` bind → `OSError: [Errno 98] Address in use`, so the map
   server died the instant it started while `ut_bridge` (`:10110`) was fine. `netstat
   -ltnp` confirmed uhttpd on 8080. **Fix: move the map server to `:8088`** (free on
   op24). `map.html` uses relative URLs, so it's a one-line `SERVE_PORT` change end to
   end. Baked into the repo, the Manager's `MAP_PORT` (verify + QR default), the bundled
   `units_kml`, and the manual. (The 5.4 Lookout/BK-Traveler keep 8080.)
3. **Three USB devices coexist on 6.6** (§6) — proven.
4. **Reboot-survival** — `sync; reboot`, both services auto-returned with fresh PIDs
   (`:10110` = 8838, `:8088` = 10089), all three devices present. The crew's real
   power-on-with-everything-attached path.
5. **No `[gps]` log, no LOOKOUT dot** — not an import failure (`import gps_source` was
   clean, both files present). The built-in verbose test `python3 /root/garmin_linux.py`
   showed the Garmin opening perfectly and streaming `fix=1` with a correct position →
   the `fix < 2` gate (§7). Loosened to `fix < 1`, restarted `ut-bridge`, and **LOOKOUT
   (cyan) + 9076802 (green) both plotted live in both panes.** Done.

---

## 10. Landmines for the next me (box-specific; the family set is in `CLAUDE.md`)

- **op24 map server is `:8088`, not 8080** — uhttpd owns 8080/8443 on op24. Don't
  "restore" 8080.
- **Fixed-geometry squelch capture** (§3) — never regress to a variable window /
  custom onset-finder. 10/10 depends on the fixed `[onset−PREROLL, +CAP]` slice.
- **The reader thread reads bytes only** (§4) — moving the fold back into it
  re-introduces the GIL-starvation overruns on ARM.
- **`arecord` stays stereo** on the SB Play! 3 (`-c 2`, `plughw:0,0`); the consumer
  folds to mono. The card is capture-only stereo.
- **Garmin: trust `fix >= 1`** with coord sanity (§7). Don't re-tighten to `>= 2`.
- **dropbear = no SFTP** — stream files with `cat >`, never paramiko SFTP/scp-subsystem.
- **`sync` ends every deploy.** procd services + `sync` = survives a truck power-cut.
- **No numpy/scipy on the box** — the decoder is stdlib forever. Don't reach for them.
- **You can't test ALSA/USB/AE-render here** — logic + exact bytes in the sandbox;
  hardware and the browser map go to Jim with one-command-at-a-time steps.

---

*The chain is closed. A public-safety agency with one of these boxes, a cheap receiver,
and a browser can locate its people off a P25 channel with no base, no SDR, no cloud,
no internet. That's the point. — logged before compaction, 2026-11-23.*
