# The Universal Traveler — Spec & Build Decisions

*Public-safe. Written as the from-scratch spec for the Universal Traveler and its one-shot Manager. This is the living record of what we decided and why, so nothing gets lost to compaction — update it as each decision is locked.*

> **✅ PROVEN END-TO-END ON THE BOX — 2026-11-23.** A live P25 fleet unit decoded off
> the air by a GL-MT3000 (op24 / kernel 6.6.110) and plotted with the box's own Garmin
> fix on the offline split-screen, all three USB devices coexisting on one powered hub,
> reboot-survival proven. Full technical account:
> [`UNIVERSAL_TRAVELER_BRINGUP_2026-11-23.md`](UNIVERSAL_TRAVELER_BRINGUP_2026-11-23.md).
> Shipped as **Universal Traveler Manager v1.1** (map server on `:8088` to clear op24's
> uhttpd; Garmin self-GPS trusts `fix>=1`).

## What it is (one breath)

A man-packable, battery **GL-MT3000** that decodes **P25 Tier-1 GPS straight off the air** (radio discriminator audio → USB sound card → on-box pure-Python decode) and serves a live **offline** map — locked split-screen hybrid | street, the box's own GPS "you are here", and every decoded fleet unit — to **any browser, nothing installed on the viewer**. No cooperating base, no SDR, no PC. Built fresh as its **own independent product** with a one-shot **Universal Traveler Manager**.

## Build philosophy (the line we drew)

- The **DSP decode engine** — noise-quieting squelch → MMSE symbol tracker → C4FM filter → framer → BCH/Viterbi FEC → NMEA — is validated **bit-exact** against ground truth and is kept as a **sealed, tested module**. We assemble around it; we do **not** rewrite proven math "from scratch."
- **Everything else** — the Manager, the provisioning sequence, the glue, the boot services — is built **clean and coherent as one program**. No byte-cramming of mismatched parts, no 50-patch pile.

## Feature set (agreed 2026-11-23)

**1 — What it does off the air (the reason it exists)**
- Decode P25 Tier-1 GPS from discriminator audio — no base, no SDR, any P25 fleet
- Noise-quieting squelch: idle through dead air, decode only on a real packet
- Every transmitting radio plotted by its individual ID, nameable to a crew label
- Emit clean NMEA — talker-ID + checksum normalized correctly

**2 — What it shows (the map)**
- Offline basemap from an SSD (`.tpkx`/`.mbtiles`), zero internet
- Locked, synced split-screen: hybrid | street, same area, centered on you/the fleet
- Any browser, any device — nothing installed on the viewer
- Units plot live, update, age to stale, and never hijack the view
- QR card: scan → map opens, no typing, no app

**3 — Where it is (own position)**
- Local GPS puck for the box's own "you are here" — **STAYS** (the box's own puck, not the phone). Settled.

**4 — The box (field platform)**
- GL-MT3000, battery, man-packable
- A kernel where the sound card and the SSD coexist (the real USB fix, not a crippled capture)
- Powered USB hub (sound card + SSD + GPS) for power headroom
- Reboot-survival (every service returns on power-up) + flash-durable (`sync`)
- Isolation: the audio card, the SSD, or the GPS can each drop without taking down the rest
- Recognizable Wi-Fi SSID + fixed address the QR carries

**5 — The Manager (one shot, PC side)**
- One click: bare box → working Universal Traveler, start to finish
- Puts the box on the right firmware/kernel, or refuses to provision onto a bad one — handled, not left to chance
- Installs the whole stack in order: python3 → audio (`kmod-usb-audio`/alsa) → GPS → decode engine → map server → boot services → `sync`
- All files bundled in the package (GitHub-free install), streamed over the box's real SSH (`cat >`, never SFTP)
- Functional verification at each step — the map actually draws, a unit actually plots — not just "process alive"
- Live unit naming built in (ID → crew name)
- Family standard: one obvious `.bat` + `System Files` + a PDF manual that opens with the install blurb
- Fully independent product — its own files, zero shared with the BK Traveler Manager

## Decisions log

- **GPS — STAYS.** The box carries its own GPS puck for "you are here"; not the phone. Settled (pre-dates this spec).
- **D1 (2026-11-23) — Kernel base = OpenWrt 24.10 / kernel 6.6** (GL's `4.9.0-op24` line). The `xhci-mtk` TT periodic-bandwidth fix is present in 6.6, so the full-speed USB sound card and the USB SSD **coexist on a powered hub** — the root fix, not a rate-reduction workaround. Action before committing: confirm the `kmod-usb-audio` and GPS (serial/`cdc-acm` + libusb) packages exist in that build's feed so the whole stack still stands up.
- **D2 (2026-11-23) — Audio device = Sound Blaster Play! 3** (unchanged). The device the whole OTA decode is already proven on, end to end. Kernel 6.6 removes the bandwidth bug, so it works behind the hub; no new hardware, no new unknowns (capture handle `plughw:0,0`, S16_LE, tap/levels all validated). Full-speed USB audio + control + HID.
- **D3 (2026-11-23) — GPS puck = Garmin GPS 18 USB** (libusb). The puck proven on both the Lookout and the Traveler bench — binary D800 read in pure ctypes/libusb, locked a real 3D fix, no re-lock trouble. Only dependency is `libusb`. (The serial VK172 u-blox was tried and dropped — one fix, then wouldn't re-lock.) So three USB devices on the powered hub: sound card + SSD + Garmin.
- **D4 (2026-11-23) — Firmware step = Manager verifies, user flashes.** The user flashes the 24.10/6.6 image once through GL's own dashboard (a supported button, same place as first-boot setup — no brick risk). The Manager checks the kernel, **refuses to proceed if it's wrong**, then does the entire software provision in one shot. No scripted `sysupgrade` (a dropped connection/power mid-flash can brick a field box; GL doesn't cleanly support third-party sysupgrade). Matches the proven Lookout Manager pattern (SSH + opkg only, never flashes firmware).
- **D5 (2026-11-23) — Radio audio in the browser = NO.** The Universal Traveler is **GPS-decode only**; the sound card feeds only the decoder (single consumer of `arecord`). Keeps it focused and matches the Traveler's stripped identity. (A browser-audio variant could come later, but would require re-architecting the capture to tee one `arecord` stream to both the decoder and an audio streamer — the card can't be opened twice. Not in scope now.)
- **D6 (2026-11-23) — v1 scope = full-featured.** v1 ships the whole thing: OTA decode + split-screen map + Garmin "you are here" + reboot-survival + **live unit-naming** (ID → crew label) + **QR-card generation**, all in one Manager. Complete for crews on day one.

---

## Architecture (the from-scratch design)

Two layers, both **fully independent of the BK Traveler** (zero shared files). Per the build philosophy: proven engines are **sealed modules bolted in**; the plumbing is **built fresh and coherent**.

**Sealed modules — proven, reused as-is (not rewritten):**
- **DSP decode engine** — `decode_pure/` (squelch → MMSE → C4FM → framer → BCH/Viterbi → NMEA). Bit-exact, validated.
- **`units_kml`** — the Traveler map server (serves the split-screen, tiles from the SSD, live units, the naming endpoint).
- **`map.html` + leaflet** — the locked synced split-screen (hybrid | street).
- **Garmin reader** — `garmin_linux` / `gps_source` (libusb D800 "you are here").
- **QR encoder** — the proven pure-Python QR maker (byte-mode, decode-verified).

**Built fresh — clean, one purpose each:**
- **`ut_bridge.py`** — the input stage, one coherent program: open the sound card → run the sealed decode engine → fold in the Garmin fix as the own-position unit → **normalize NMEA** (`$GPGGA` + recomputed checksum, fixing the garbled talker-ID) → serve the bk_bridge-compatible feed on `:10110`. Replaces `bk_bridge` so `units_kml` is untouched. Reader-thread/queue design (the proven GIL-safe capture).
- **Boot services** — procd init scripts for **OpenWrt 24.10 / kernel 6.6** (bridge + map server, respawn, reboot-survival, end with `sync`).
- **The Universal Traveler Manager** (PC, one program, tabbed): **Provision** (verify kernel 6.6 → `opkg` deps: python3, libusb, `kmod-usb-audio`/alsa → stream bundled box files via `cat >` → install + enable boot services → `sync` → **functional verify**: map draws, a unit plots) · **Name Units** (ID → label) · **Make QR** (address → print-ready card). One obvious `.bat` + `System Files` + PDF manual (install blurb on top). Files bundled (GitHub-free). Zero shared files with the BK Traveler Manager.

**Maps:** the user drops a hybrid+street pair (same area) on the SSD, named to pair — the family model. The box detects and serves them; the Manager's functional check confirms a pair is present.

**Build order:** (1) clean `ut_bridge.py` + NMEA normalization — verifiable here by replay → `:10110` → clean feed; (2) the 6.6 boot services; (3) assemble the box-file bundle; (4) the Manager program; (5) the PDF manual; (6) hand Jim the package → he flashes 6.6, runs the Manager, we prove the whole box end to end.
