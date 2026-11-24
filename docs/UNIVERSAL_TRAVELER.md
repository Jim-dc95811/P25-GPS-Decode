# The Universal Traveler — Spec & Build Decisions

*Public-safe. Written as the from-scratch spec for the Universal Traveler and its one-shot Manager. This is the living record of what we decided and why, so nothing gets lost to compaction — update it as each decision is locked.*

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
