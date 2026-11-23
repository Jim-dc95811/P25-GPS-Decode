# CLAUDE.md — P25-GPS-Decode

**Written by Claude, for Claude.** Read this first if you're resuming or picking up this project. It's the fast orientation; the deep technical reasoning is in [`docs/DECODE_PLAN.md`](docs/DECODE_PLAN.md) — **read that before any decode work.**

> **This repo is PUBLIC — keep this file public-safe** (strip any employer/agency names; Jim's own name and GitHub handle are fine). **Precedence:** live code/files win over any prose here; then this file; then older notes. A compacted/auto-summary of a prior session is NOT a source of truth — re-read **Current state** below and `docs/DECODE_PLAN.md` from the live repo before any mission- or architecture-level claim.

> **STANDALONE, DELIBERATELY UNLISTED (Jim, 2026-11-22).** This is its own project, **not** under the *ArcGIS Earth Unlocked* banner. It is **public but NOT advertised** — do **not** link it from the family repos, the front page, the site, the montage, the all-tools zip, the Py Vault, or the family pictogram **until the over-the-air decode is proven working.** Jim: *"You know the drill."* (The Unlocked family `CLAUDE.md` carries a quiet internal continuity pointer so a resuming Claude can find this repo — that's AI continuity, not public advertising. Keep it that way.)

---

## What it is (one breath)

Decode **P25 Tier 1 GPS location straight off the air** from a receiver's **discriminator audio** (via a PC sound card), with **no SDR** and **no cooperating base radio**. The radio already demodulates the RF; we take its recovered 4-level baseband and do the digital decode in software — symbol slice → P25 frames → data PDUs → NMEA. We decode **data, not voice** (so no vocoder, no DVSI patent). Goal: break free of the BK-base-hands-us-NMEA dependency and read **any** P25 fleet's location.

---

## Current state *(update this when it changes)*

**2026-11-22 (night) — THE ANSWER-KEY HALF OF THE RIG IS BUILT + PROVEN ON REAL HARDWARE; the sound-card interface is SETTLED. The OTA/audio half is staged for the bench tomorrow.** The experiment has two independent halves (Jim's point: they share NO hardware — only he, the human, starts them together): (A) the **answer key** = the BK base handing us ground-truth NMEA over RNDIS; (B) the **air** = the receiver's discriminator/DEO audio into a sound card, decoded in software. Half (A) is now DONE and proven on Jim's live BK base tonight. Half (B) wires up tomorrow when Jim has the radio + DEO cable.

**What got built + proven tonight (detail, so compaction can't eat it):**
- **The answer-key logger — `rig/rndis_nmea_logger.py` — BUILT, tested in the sandbox against a framed fake radio, then PROVEN on Jim's real BK base.** Connects to `10.250.46.6:65535`, sends subscribe `80 04 18 e4 81`, keepalive every 20 s, reconnects on drop; extracts NMEA with the regex + XOR checksum **lifted verbatim from the proven `bk_bridge.py`** (The-Lookout); writes a timestamped `rndis_nmea_<ts>.log` (the answer key) + a `rndis_raw_<ts>.bin` (raw bytes, insurance); echoes each fix (parses GGA lat/lon) to the console so you WATCH the key land live. Stdlib only, **read-only** (never transmits). Packaged Jim-standard (one `.bat` + `System Files/`) and delivered to his Downloads; also in the repo at `rig/`. Run it *instead of* the P25 tracker during a capture (both would grab the same radio port).
- **The BK RNDIS framing is DECODED (from the real `.bin`).** This wrapper is the **base's own USB-RNDIS transport — it is NOT what goes over the air** (OTA = TIA-102.BAJB Tier 1, NMEA inside a P25 CAI data unit). Two frame types: **idle/ack** `80 04 19 10 10 07 01 52 53 00 03 13 81` (`52 53` = "RS"), sent continuously (logger ignores them); **data** `80 0d 02 <id-field> <NMEA payload> <1-byte cksum> 81`. The `<id-field>` = the **transmitting radio's INDIVIDUAL ID** (see the landmine below) — radio ID 1 → `00 00 01`; radio ID 9076802 → `8a 82 00 42` (`9076802 = 0x8A8042`).
- **The sound-card interface is SETTLED (full detail in `docs/DECODE_PLAN.md` "Sound-card interface").** Jim's bench card = **Creative Sound Blaster Play! 3** (the Lookout's card) — **mic-in + headphone-out, NO line-in.** The DEO is a line-level output (0.28 Vp-p ≈ 0.1 Vrms, wants ≥47 kΩ); the SB mic input is low-Z (~600–1500 Ω, ~0.1 Vrms sensitivity, electret-type). **Build (locked):** DEO pin 19 → **4.7 µF series cap → 2.2 kΩ series resistor → TIP**; pin 18 ground → **SLEEVE**; **leave the RING OPEN** (Ring = +5 V electret bias). Windows: **mic BOOST off, level LOW.** Level is already a near-match so do NOT heavily attenuate (my earlier 47 kΩ was wrong — would starve it). The 2.2 kΩ passes ~⅓ of the swing (~30 mV p-p, plenty), eases the DEO load, and **limits cap-inrush** (Jim's reasoning). The **eye diagram tunes it**: clipping → bigger R (4.7 k, 10 k); tiny/noisy → raise the Windows level. Schematic: `capture/NX700_DEO_to_SoundBlaster_mic_interface.png` (also in Jim's Downloads).
- Also proven tonight incidentally: the capture/export path (Audacity → **WAV, Mono, 16-bit PCM, 44.1 kHz** — 44.1 k = ~9 samples/symbol at 4800 baud, plenty) and the file handoff all work end to end.

**TOMORROW'S CAPTURE (the plan, agreed):** wire the 2.2 kΩ; stage a portable **stationary** on a periodic cycle (10 s); run the logger next to Audacity; record **~100 s of DEO audio (10 reports)** while the logger records the matching fixes; send back the **WAV + the `.log`**. First thing to do with it: pull up one burst and **look at the eye** — four open bands = the DSP-routed DEO is sliceable and we go straight to the `0x5575F5FF77FF` sync hunt. The answer key gives us BOTH the position AND the individual unit ID to diff against, so a correct decode is unforgeable.

**Still NOT done / the real gates:** (1) the DEO eye on a real P25 burst (tomorrow); (2) donor code (OP25 + the fork) is read but **not pulled into this repo** yet; (3) the transport unknown (simple SAP vs SNDCP/IP) — settled by the first decode diff. --- *Original 2026-11-22 framing kept below for the research tiers.* This project split off from the *ArcGIS Earth Unlocked* family (where the BK-RNDIS tracker + The Lookout live) when Jim declared the OTA decoder the new upstream mission. The full research is in `docs/DECODE_PLAN.md`, honestly tiered.

- **PROVEN tap:** the RX radio only needs to output its raw FM detector (discriminator) signal; it need not understand P25. **★ PREFERRED (2026-11-22, Jim's switch): Kenwood NX-700 mobile, external DB-25 pin 19 = DEO "Detected signal output"** — no disassembly, just a DB-25 cable; ~0.28 Vp-p, AC-coupled 4.7 µF into ≥47 kΩ, gnd pin 18 → the sound card via the SETTLED interface (4.7 µF + 2.2 kΩ series into the SB Play! 3 **mic** jack; the card has no line-in — see the interface detail above and in `docs/DECODE_PLAN.md`). **Must set the radio WIDE** (Narrow droops the DEO ~15 dB and smears the symbols); NOT pin 17 AFO (filtered voice). **Alternate:** BK **DPH-CMD** portable, internal J2 pin **CZ8 = DISC AUD** (schematic p.6-49; needs the radio opened). Either way: discriminator audio = **FM demod already done → straight to symbol slicing** (no SDR). Full detail + the NX-700 electrical spec in `docs/DECODE_PLAN.md`.
- **RESEARCHED:** the location format is a regulated, interoperable standard — **TIA-102.BAJB Tier 1 Location Services**, position as **NMEA 0183** over a **dedicated CAI SAP**; common across manufacturers (the "break free" enabler). **Distinct from Motorola LRRP** (proprietary IP/UDP — don't conflate).
- **KEY ENABLER:** data not voice → **no vocoder → no mbelib/DVSI patent** (the thorniest legal part of P25 decoding is sidestepped).
- **PARTS ALREADY WRITTEN (open):** OP25/DSD do the hard DSP (C4FM slice, 24-dibit sync, NID/DUID, trellis+Golay/Hamming/RS FEC, PDU reassembly); **`russinnes/P25-sndcp-packet-decoder`** (OP25 fork) carries a data channel symbols→PDU→SNDCP→IPv4/UDP→payload. Parts donor, **not a drop-in** (SDR-input not sound-card, trunk-focused, targets text/TMS not location). **Our job is easier than theirs:** the BK radio is already locked on the channel (no channel-chasing — their hardest problem), and we have ground-truth NMEA (they decode blind).
- **THE ONE UNKNOWN:** does BK Tier 1 location ride as full **SNDCP/IP/UDP** (fork's core near-reusable + add NMEA extract) or a **simpler dedicated-SAP data unit** (skip IP, pull NMEA from the PDU)? Standard hints simpler; **don't guess.**
- **THE RIG settles it (Jim's "apple" insight — known-plaintext):** a BK base hands finished NMEA over RNDIS (TCP 65535, subscribe `80 04 18 e4 81`, over RNDIS at `10.250.46.6`) while the SAME PC feeds discriminator audio into a **Sound Blaster 3**. **Experiment #1: DISC AUD → an OP25-based decoder → watch what PDUs/datagrams fall out → diff the bytes against the RNDIS NMEA.** That reveals the transport and decides the whole architecture.

**Next (either order):** (1) **pull the parts** — clone OP25 + the fork, read the real code, map reusable files vs. the sound-card-input adapter + NMEA-extract add (desk task, before the bench); (2) **the bench** — the rig + experiment #1. Optional one more desk thread: exact TIA-102.BAJB Tier 1 SAP data-unit layout, or OP25's discriminator-audio input mode.

---

## Landmines / things not to re-derive

- **The discriminator tap** — don't re-derive it. PREFERRED = **Kenwood NX-700 DB-25 pin 19 (DEO), radio set WIDE** (external, no disassembly); alternate = **BK DPH-CMD J2 pin CZ8**. Both logged in `docs/DECODE_PLAN.md` with the NX-700 electrical spec + confirmed signal path. NUANCE (confirmed from the B51-8822 block diagram): the DPH CZ8 is a pure analog discriminator pin, but the NX-700 **DEO is a DSP-ROUTED detected-signal output** (detector IC202 → ADC/DSP IC510/IC502 → DAC IC712 → pin 19), output flat, 48 kHz internal sampling — almost certainly clean for C4FM but **confirm with the first eye diagram**. We decode P25 in software, so the RX radio's own mode (NXDN/analog) is irrelevant as long as it's a Wide FM channel on the P25 frequency, squelch open.
- **Discriminator audio is already demodulated** — do NOT reach for an SDR or re-demod. Sound card → slice 4 levels → dibits.
- **We want DATA, not voice** — never pull in a vocoder (mbelib/IMBE). It only decodes voice and carries the DVSI patent. Discard voice frames.
- **Tier 1 ≠ LRRP.** Tier 1 (TIA-102.BAJB, NMEA, standardized) is the target. Motorola LRRP is a different, proprietary thing — don't build toward it.
- **The service manual PDF is NOT in this repo** (it's Jim's upload; kept out). A future session needs him to re-attach `bk-dph-digital-service-manual_1.pdf` to re-read the schematic. The CZ8 finding itself is written down, so it's not lost.
- **The radio is RX-only / read-only** — we only ever receive. Never transmit or alter a radio.
- **Validate against ground truth, not guesses** — the RNDIS NMEA feed is the answer key. Any decode claim gets diffed against it before it's believed.
- **INDIVIDUAL ID framework — don't re-derive it as something else (compaction ate this once, 2026-11-22).** Every radio has a programmed **individual ID** (a P25 unit ID). Jim's fleet runs IDs like **9076801 / 9076802 / 9076803**, and a radio can be a short ID like **1**. In the RNDIS feed each GPS report is `$GNGGA` (position) + **`$PP25,<individual-id>`** — the `<id>` is simply the transmitting radio's own ID, **NOT** a PTT-vs-periodic tag, NOT a sequence, NOT a console code. (A resuming Claude wrongly read two reports — one from a radio set to ID 1, one from ID 9076802 — as a "PTT vs periodic" tag; Jim corrected it: two *different radios*, two *individual IDs*. The trigger type, PTT or periodic, is independent of the ID.) This matters for the mission: TIA-102.BAJB Tier 1 carries the **source individual ID + position** over the air, so a decoded burst gives us **two** things to diff against the answer key (position AND unit ID) — a correct decode to a known ID at known coordinates is unforgeable.
- **The sound-card interface is SETTLED — don't re-derive it (and don't "fix" it back to a big attenuator).** SB Play! 3 is **mic-only**. Build: DEO pin 19 → 4.7 µF → **2.2 kΩ series** → mic **TIP**, ground → **SLEEVE**, **RING open** (bias), boost off, level low; eye-tunes. The DEO level ≈ the SB mic sensitivity (~0.1 V), so heavy attenuation STARVES it — the 2.2 kΩ is for load-easing + cap-inrush, not level. Full reasoning (SB mic spec 600–1500 Ω / 0.1 Vrms; why not line-in) in `docs/DECODE_PLAN.md`.
- **The answer-key logger is BUILT + PROVEN (`rig/rndis_nmea_logger.py`).** Don't rebuild it. It de-frames the BK RNDIS wrapper (`80 … 81`) and emits clean timestamped NMEA. That wrapper is **base-local USB transport, NOT over-the-air** — the OTA decode will see a P25 PDU carrying the NMEA, never the `80 0d 02…` bytes. Framing fully documented in `rig/README.md`.

---

## Where the detail lives

| File | What's in it |
|---|---|
| `README.md` | Public front page — what it is, honest status. |
| `docs/DECODE_PLAN.md` | **The canonical technical reference** — the full research, honestly tiered (proven / researched / unknown), the tap, the standard, the stack, the parts donors, the rig, the sources. Read it before any decode work. |
| `capture/` | Sound-card capture settings for the discriminator input (`P25_Discriminator_Capture_Settings.pdf` + its generator). |

Cross-family context (for continuity, not for linking publicly): the BK-RNDIS tracker, the `StreamParser`, and **The Lookout** (which consumes the live GPS) live in Jim's *ArcGIS Earth Unlocked* family; its `CLAUDE.md` is the highest-authority newest cross-family state and holds Jim's working rules + the BK relay facts. This repo is the **upstream OTA alternative** to that family's BK-cooperation dependency.

---

## Resume procedure

1. Clone this repo; attach with push access (`add_repo`, `access: push`) before pushing. It's a shallow clone — push with `git -c push.negotiate=true push`.
2. Read this file → `docs/DECODE_PLAN.md` → (when code exists) the live source.
3. Keep it **standalone and unadvertised** until the OTA decode is proven (see the banner up top).
4. Test logic + exact bytes here; hand hardware/RF and bench-rig steps to Jim.

## Working with Jim on the bench (so it goes smoothly)

- **One step at a time, wait for his confirmation**; spell out the full exact command every time (he doesn't keep commands in memory); ask for a **screenshot**, don't ask him to transcribe.
- **Search first** for an existing/known solution before hand-rolling (his standing rule) — this whole mission already benefits from it (OP25/the fork exist).
- **Verify, don't assume** — build in a check at each step; the RNDIS NMEA is the ground truth to check against.
- Files for him go **straight to his Downloads via the bridge** when the session is linked; tell him after. Commit each change from a **fresh** output path (the bridge re-sends the first snapshot on a repeated path).
- **Bump the version on every change** — the running version is his tell for what's live.
- 37 years of electronics / radio expert, not a coder — name things plainly; he reasons in vision/gist, works out the format/mechanism yourself.
- **Enthusiastic, hands-on partner — "project success, not comfort" (his words, 2026-11-22).** Jim *wants* to be Claude's hands: he'll record the discriminator, run the rig, and save a bot-walled page to a file so Claude can read it. Hand him the physical step plainly; he does it gladly. Don't spare him work to be polite — he'd rather the work get done.
- **Bot-walled pages → ask Jim to save & send (PROVEN 2026-11-22).** Key P25 sources refuse WebFetch with an anti-bot block (Anubis "Access Denied" — notably `osmocom.org`, the OP25 wiki). Workaround: Jim saves the page in his browser (**Ctrl+P → "Save as PDF"** is best — whole page + diagrams + real text; or Ctrl+S → MHTML/HTML, or select-all → `.txt`) and attaches it; Claude reads it fully. This unblocked the OP25 DecoderPage and handed us the slicer LUT + the `0x5575F5FF77FF` frame sync. Standard move for anything walled.

*Keep this file current and lean. Depth belongs in `docs/DECODE_PLAN.md`; this is the map to it and the list of holes not to fall in twice.*
