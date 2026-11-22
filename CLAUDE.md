# CLAUDE.md — P25-GPS-Decode

**Written by Claude, for Claude.** Read this first if you're resuming or picking up this project. It's the fast orientation; the deep technical reasoning is in [`docs/DECODE_PLAN.md`](docs/DECODE_PLAN.md) — **read that before any decode work.**

> **This repo is PUBLIC — keep this file public-safe** (strip any employer/agency names; Jim's own name and GitHub handle are fine). **Precedence:** live code/files win over any prose here; then this file; then older notes. A compacted/auto-summary of a prior session is NOT a source of truth — re-read **Current state** below and `docs/DECODE_PLAN.md` from the live repo before any mission- or architecture-level claim.

> **STANDALONE, DELIBERATELY UNLISTED (Jim, 2026-11-22).** This is its own project, **not** under the *ArcGIS Earth Unlocked* banner. It is **public but NOT advertised** — do **not** link it from the family repos, the front page, the site, the montage, the all-tools zip, the Py Vault, or the family pictogram **until the over-the-air decode is proven working.** Jim: *"You know the drill."* (The Unlocked family `CLAUDE.md` carries a quiet internal continuity pointer so a resuming Claude can find this repo — that's AI continuity, not public advertising. Keep it that way.)

---

## What it is (one breath)

Decode **P25 Tier 1 GPS location straight off the air** from a receiver's **discriminator audio** (via a PC sound card), with **no SDR** and **no cooperating base radio**. The radio already demodulates the RF; we take its recovered 4-level baseband and do the digital decode in software — symbol slice → P25 frames → data PDUs → NMEA. We decode **data, not voice** (so no vocoder, no DVSI patent). Goal: break free of the BK-base-hands-us-NMEA dependency and read **any** P25 fleet's location.

---

## Current state *(update this when it changes)*

**2026-11-22 — Repo created; the research is captured; nothing built or proven over the air yet.** This project split off from the *ArcGIS Earth Unlocked* family (where the BK-RNDIS tracker + The Lookout live) when Jim declared the OTA decoder the new upstream mission. What's done: the full research is in `docs/DECODE_PLAN.md`, honestly tiered. What's **not** done: the donor code isn't pulled yet, and nothing has decoded a real fix off the air.

- **PROVEN tap:** the RX radio only needs to output its raw FM detector (discriminator) signal; it need not understand P25. **★ PREFERRED (2026-11-22, Jim's switch): Kenwood NX-700 mobile, external DB-25 pin 19 = DEO "Detected signal output"** — no disassembly, just a DB-25 cable; ~0.28 Vp-p, AC-coupled 4.7 µF into ≥47 kΩ → sound-card LINE-IN (gnd pin 18). **Must set the radio WIDE** (Narrow droops the DEO ~15 dB and smears the symbols); NOT pin 17 AFO (filtered voice). **Alternate:** BK **DPH-CMD** portable, internal J2 pin **CZ8 = DISC AUD** (schematic p.6-49; needs the radio opened). Either way: discriminator audio = **FM demod already done → straight to symbol slicing** (no SDR). Full detail + the NX-700 electrical spec in `docs/DECODE_PLAN.md`.
- **RESEARCHED:** the location format is a regulated, interoperable standard — **TIA-102.BAJB Tier 1 Location Services**, position as **NMEA 0183** over a **dedicated CAI SAP**; common across manufacturers (the "break free" enabler). **Distinct from Motorola LRRP** (proprietary IP/UDP — don't conflate).
- **KEY ENABLER:** data not voice → **no vocoder → no mbelib/DVSI patent** (the thorniest legal part of P25 decoding is sidestepped).
- **PARTS ALREADY WRITTEN (open):** OP25/DSD do the hard DSP (C4FM slice, 24-dibit sync, NID/DUID, trellis+Golay/Hamming/RS FEC, PDU reassembly); **`russinnes/P25-sndcp-packet-decoder`** (OP25 fork) carries a data channel symbols→PDU→SNDCP→IPv4/UDP→payload. Parts donor, **not a drop-in** (SDR-input not sound-card, trunk-focused, targets text/TMS not location). **Our job is easier than theirs:** the BK radio is already locked on the channel (no channel-chasing — their hardest problem), and we have ground-truth NMEA (they decode blind).
- **THE ONE UNKNOWN:** does BK Tier 1 location ride as full **SNDCP/IP/UDP** (fork's core near-reusable + add NMEA extract) or a **simpler dedicated-SAP data unit** (skip IP, pull NMEA from the PDU)? Standard hints simpler; **don't guess.**
- **THE RIG settles it (Jim's "apple" insight — known-plaintext):** a BK base hands finished NMEA over RNDIS (TCP 65535, subscribe `80 04 18 e4 81`, over RNDIS at `10.250.46.6`) while the SAME PC feeds discriminator audio into a **Sound Blaster 3**. **Experiment #1: DISC AUD → an OP25-based decoder → watch what PDUs/datagrams fall out → diff the bytes against the RNDIS NMEA.** That reveals the transport and decides the whole architecture.

**Next (either order):** (1) **pull the parts** — clone OP25 + the fork, read the real code, map reusable files vs. the sound-card-input adapter + NMEA-extract add (desk task, before the bench); (2) **the bench** — the rig + experiment #1. Optional one more desk thread: exact TIA-102.BAJB Tier 1 SAP data-unit layout, or OP25's discriminator-audio input mode.

---

## Landmines / things not to re-derive

- **The discriminator tap** — don't re-derive it. PREFERRED = **Kenwood NX-700 DB-25 pin 19 (DEO), radio set WIDE** (external, no disassembly); alternate = **BK DPH-CMD J2 pin CZ8**. Both logged in `docs/DECODE_PLAN.md` with the NX-700 electrical spec. It's the raw FM detector output either way; we decode P25 in software, so the RX radio's own mode (NXDN/analog) is irrelevant as long as it's a Wide FM channel on the P25 frequency with squelch open.
- **Discriminator audio is already demodulated** — do NOT reach for an SDR or re-demod. Sound card → slice 4 levels → dibits.
- **We want DATA, not voice** — never pull in a vocoder (mbelib/IMBE). It only decodes voice and carries the DVSI patent. Discard voice frames.
- **Tier 1 ≠ LRRP.** Tier 1 (TIA-102.BAJB, NMEA, standardized) is the target. Motorola LRRP is a different, proprietary thing — don't build toward it.
- **The service manual PDF is NOT in this repo** (it's Jim's upload; kept out). A future session needs him to re-attach `bk-dph-digital-service-manual_1.pdf` to re-read the schematic. The CZ8 finding itself is written down, so it's not lost.
- **The radio is RX-only / read-only** — we only ever receive. Never transmit or alter a radio.
- **Validate against ground truth, not guesses** — the RNDIS NMEA feed is the answer key. Any decode claim gets diffed against it before it's believed.

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
