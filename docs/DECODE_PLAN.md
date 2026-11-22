# Over-the-Air P25 GPS Decoder — the plan, and everything we worked out

**Canonical technical reference for this repo. Written by Claude, for Claude.** Read this before doing any decode work so the hard-won reasoning below is not re-derived from scratch. Public repo → employer-clean (no agency names; Jim's name/handle are fine).

---

## The mission in one paragraph

Jim's existing live-GPS stack (the P25 GPS Tracker, The Lookout, the trifecta — all in the *ArcGIS Earth Unlocked* family) depends on the **BK radio cooperating**: a BK base relay decodes the received P25 GPS itself and squirts clean NMEA out its USB **RNDIS** link, and the tools just read it (`$GNGGA` + `$PP25` on TCP 65535). That tether is the limit. **This project decodes the P25 GPS data OURSELVES, over the air, from a radio's discriminator audio — no RNDIS squirt, no BK cooperation.** If we can slice symbols off discriminator audio and pull the location out, then **any P25 fleet from any manufacturer becomes trackable** from a cheap receiver + a sound card. Jim's words: *"This would break us free from the BK world into the entire world of P25."* And: *"All the scanner people want to listen to traffic. I am the opposite, I just want the gps data."*

**Honesty note (blind test):** Jim has **already walked this path himself** and deliberately withheld his findings so a fresh Claude would reason independently. Where this doc's conclusions match his (the discriminator tap point in particular), that is **confirmation, not discovery** — treat it as a second witness, not a claim of credit.

---

## Why it matters / what it unlocks

- **Breaks the BK dependency.** No more needing a BK base on the RNDIS branch to hand us NMEA. A receiver tuned to the fleet's channel + discriminator tap + sound card is the whole front end.
- **Opens the entire P25 world.** P25 is a public-safety interoperability standard; Tier 1 location is specified (below). Decode it once and the tool is manufacturer-agnostic — Motorola, Harris/L3, Tait, BK, etc.
- **Data-only, so the patent wall does not apply.** We want **location data, not voice**. The IMBE/AMBE vocoder (mbelib / DVSI) is patent-encumbered, but it only guards **voice**. Decoding **data PDUs** sidesteps it entirely. This is a real enabler, not a convenience.
- **Still PTT-shaped.** A fix rides when a radio keys up — same "no big brother" posture as the current tracker; we're just reading it off the air instead of off the BK's USB.

---

## The "apple" insight — the known-plaintext rig (Jim's framing, 2026-11-22)

*"Imagine the P25 packet is a series of images, and after a packet comes in the BK says 'hey look, I found an apple in the packet.' Now if you look for an apple it's a lot easier to find."*

The BK base **already tells us the answer.** On the same transmission, the RNDIS branch hands us the **finished NMEA** (lat/lon/time) — ground truth. So we run a **known-plaintext** bring-up:

1. A functional BK base feeds **known, complete NMEA** via the RNDIS branch we already know how to connect to and engage (subscribe `80 04 18 e4 81` to TCP **65535** over RNDIS at `10.250.46.6` — the Lookout/tracker path).
2. On the **same PC**, the receiver's **discriminator signal feeds a Sound Blaster 3** sound-card input (capture settings in this repo's `capture/`).
3. As our decoder climbs the stack, we **diff what falls out of it against the known NMEA in real time.** We know exactly what lat/lon to look for, so finding where those bytes live in the raw frame — and proving each decode stage — is vastly easier than decoding blind.

This rig is the single most valuable asset we have, and it's the thing almost nobody else building P25 decoders has: a live answer key.

---

## The tap point — PROVEN (Jim confirmed; independently re-derived from the schematic)

**Donor radio:** BK **DPH-CMD** portable (Jim has these in abundance, free from the trash — "very good radios"). We only ever **receive**; nothing is transmitted or altered.

**Where to tap:** the recovered FM baseband — **"DISC AUD"** — on the radio's main board-to-board connector:

- Connector **J2 "TO SYSTEM BOARD"**, pin **CZ8 = DISC AUD** (schematic page **6-49** in the DPH-CMD service manual; the J2 pin list ran CZ1 GND · CZ2 SQ_NOISE · CZ3 PST · CZ4 SWA+ · CZ5 — · CZ6 RX+5V · CZ7 -DPTT · **CZ8 DISC AUD** · CZ9 CAR_PRES · CZ10 WIDE_IF).
- **A pin on a major connector is preferred** (Jim's rule): mechanically clean, repeatable, no fine soldering to an IC leg.

**Why discriminator audio is the right tap:** it is the **FM demodulator's output — demodulation is already done.** We do NOT need an SDR or an RF front end to recover C4FM; the radio's own receiver has already turned RF into the 4-level baseband. We go **straight to symbol slicing.** This is the whole reason tapping a hardware radio is cleaner than SDR for our narrow goal.

**RX chain context (so a future Claude can re-read the schematic):** dual-conversion receiver, IFs ~**16.9 MHz** then **455 kHz**; FM IF IC **U7 = BA4116FV** (BK p/n 3134-30670-620); **CF3** 455 kHz ceramic discriminator; **Y1** 17.355 MHz 2nd LO. In the stock radio the recovered **Disc Audio → CODEC → DSP**. **We tap Disc Audio before the CODEC** and do the DSP ourselves in software.

> The service manual is Jim's PDF (uploaded attachment: `bk-dph-digital-service-manual_1.pdf`, 149 pp; TOC ~PDF p.1–10, Theory of Operation ~PDF p.46–56 incl. Fig 4-1 RX block diagram + Fig 4-6 DSP block diagram, RX/TX parts list + schematic ~PDF p.106–121, schematic p.6-49 at ~PDF p.114). It is **not in this repo** (service manual, kept out). A future session needs Jim to re-attach it to re-read the schematic.

---

## The standard — RESEARCHED (strong, to be confirmed on the bench)

Jim's steer: *"The P25 packet structure is highly regulated for public safety use and interoperability. We are using Tier 1 GPS information — research deep to see if that chunk is regulated to be in a common format across manufacturers."* It is.

- **TIA-102.BAJB-A — "Project 25 Tier 1 Location Services."** Position is formatted as **NMEA 0183** and carried **SU-to-SU, Direct Data / Repeated Data**, over a **dedicated CAI SAP** (service access point). Tier 2 = fixed-network / advanced location services.
- Because it's an **interoperability standard**, the location "chunk" is a **common format across manufacturers** — exactly the property that lets one decoder serve the whole P25 world. This is the enabler for the "break free from BK" goal.
- **Distinct from Motorola LRRP** (Location Request/Response Protocol): LRRP is **proprietary/vendor-specific** (IPv4/UDP, token-based). Do **not** conflate the two — Tier 1 (NMEA, standardized) is our target; LRRP is a different, closed thing.

**Caveat kept honest:** "Tier 1 = NMEA inside a dedicated SAP" is the documented standard, but **how BK actually encapsulates it on the air is the one real unknown** (next section). Don't state the encapsulation as settled until the rig shows it.

---

## P25 Phase 1 physical-layer facts (for the symbol slicer)

- **C4FM**, 4-level FM: **4800 symbols/s × 2 bits = 9600 bps**.
- **Exact dibit → symbol → deviation (the slicer LUT — authoritative, from the OP25 DecoderPage):**

  | dibit | symbol | C4FM deviation | CQPSK phase (Phase-1 QPSK equiv) |
  |---|---|---|---|
  | `01` | +3 | **+1.8 kHz** (top level) | +135° |
  | `00` | +1 | **+0.6 kHz** | +45° |
  | `10` | −1 | **−0.6 kHz** | −45° |
  | `11` | −3 | **−1.8 kHz** (bottom level) | −135° |

  On the discriminator, deviation ∝ amplitude, so the four amplitude bands map top→bottom = `01 / 00 / 10 / 11`. (We're C4FM; the CQPSK column is the π/4-DQPSK equivalent, listed for completeness.)
- **Frame sync (FS)** = the fixed 48-bit / 24-dibit pattern **`0x5575F5FF77FF`** — confirmed straight off the OP25 DecoderPage Wireshark capture ("Frame Synchronization: 5575F5FF77FF"). This is the **correlation template** that locates frame start in the symbol stream. After FS: **NID = NAC + DUID** (DUID 7 = TSBK; data PDUs carry the packet payload).
- **PDU**: 12-byte header + 12-byte (unconfirmed) or 16-byte (confirmed) data blocks.
- **FEC** on the data path: **trellis** coding (rate 1/2 unconfirmed, 3/4 confirmed), plus **Golay / Hamming / Reed-Solomon / CRC** depending on the field. The decoder has to undo these to recover clean bytes.
- **Our entry point, confirmed against OP25's own block diagram** (DecoderPage): the chain is USRP → Channel Filter → Power Squelch → **FM Demodulator** → Symbol Filter → 4FSK Demodulator → Symbol Slicer → P25 Decoder → Audio Sink, with a **Packet Sniffer / IP-encapsulation** branch off the P25 Decoder. Our **discriminator tap = the FM-Demodulator output**, so we enter at the **Symbol Filter**, skip the whole RF front end, and follow the **Packet Sniffer (data) branch**, not the IMBE/voice branch. OP25's own "Signal Scope" tap sits exactly where Jim's scope shot came from.

Because we start from **discriminator audio**, the chain is: **DISC AUD → sound card → 4-level symbol slice → frame sync → NID → PDU reassembly + FEC → payload bytes → NMEA extraction.** No RF, no vocoder.

---

## Tooling / parts donors — what's already written and open

- **OP25** (osmocom) — the base P25 decoder. Crucially, **OP25 can take discriminator / sound-card audio input** (not only SDR). This is the project to wire the Sound Blaster into. Confirm its discriminator-input mode when we go to the bench.
- **DSD / DSD+ / dsd-fme** — decode from discriminator audio; voice-centric but useful reference for the symbol/sync front end.
- **SDRTrunk** — SDR-centric, trunk-following; reference, not a fit.
- **`russinnes/P25-sndcp-packet-decoder`** (an **OP25 fork**) — decodes a P25 data channel all the way: **symbols → frames → PDU reassembly → SNDCP → IPv4 → UDP → readable payload.** This proves the **hard middle of the stack is already written and open.** Strong parts donor.
  - **Honest edges (not a drop-in):** (1) **SDR input**, not sound card — its whole hard problem is *retuning an SDR to chase bursty trunked data channels*; (2) **trunk-focused** with channel-chasing; (3) targets **text (Motorola TMS/ARS)**, **not** location/NMEA.
  - **Why our job is EASIER than theirs:** the **BK radio is already locked on the channel**, pumping DISC AUD **continuously** — so we **never chase channels** (their single hardest problem is a non-issue for us). And we have **ground-truth NMEA** to validate against; they decode blind. We feed one sound card and add an "extract NMEA from the payload" step (and the project already parses NMEA).

---

## The one real unknown — and the rig settles it

**Does BK's Tier 1 location ride as full SNDCP / IPv4 / UDP packet data, or as the simpler "dedicated SAP, Direct/Repeated Data" unit** that TIA-102.BAJB describes (NMEA carried more directly, no IP layer)?

- If **SNDCP/IP/UDP** → the russinnes fork's reassembly core is near-directly reusable; we just add NMEA extraction from the datagram payload.
- If **simpler dedicated SAP** → we use OP25/the fork for frame + PDU decode, skip the SNDCP/IP layer, and pull NMEA straight out of the SAP data unit ourselves.
- The standard's wording ("dedicated SAP, direct data") **hints at the simpler path**, but don't guess — the rig shows it in one session.

**First experiment (the whole thing turns on this):**
> **DISC AUD → an OP25-based decoder → watch what PDUs / datagrams actually fall out → diff the bytes against the known RNDIS NMEA.** The transport structure reveals itself, and that decides the architecture of everything we build.

---

## Status ledger (keep this honest)

| Thing | State |
|---|---|
| BK RNDIS NMEA path (the answer key) | **PROVEN** — live, in use (tracker + Lookout, in the Unlocked family) |
| Discriminator tap = DPH-CMD J2 pin **CZ8 DISC AUD** | **PROVEN** (Jim confirmed; re-derived from schematic p.6-49) |
| Discriminator audio = FM demod done → straight to symbols | **ESTABLISHED** (radio theory of operation) |
| Standard = TIA-102.BAJB Tier 1, NMEA in a dedicated SAP, interoperable | **RESEARCHED** (strong; distinct from Motorola LRRP) |
| No vocoder needed (data not voice → no DVSI patent) | **ESTABLISHED** |
| Decode stack + parts donors (OP25, russinnes fork) | **MAPPED** |
| Donor code pulled/studied in-repo | **NOT YET** — clone OP25 + the fork, map reusable parts |
| Transport encapsulation (SNDCP/IP vs simple SAP) | **UNKNOWN** — the rig resolves it |
| End-to-end OTA decode of a real GPS fix | **NOT YET** — the goal |

## Next steps

Desk research has done its job: standard, stack, tap, tooling, and the one empirical fork in the road are all mapped. Two tracks, either order:

1. **Pull the parts (desk task, before the bench).** Clone **OP25** (osmocom) and **`russinnes/P25-sndcp-packet-decoder`** and READ the real implementation — the C4FM symbol slicer, the 24-dibit sync, NID/DUID typing, the trellis/Golay/Hamming/RS FEC, the PDU reassembly, and (in the fork) the SNDCP→IP/UDP path + its NMEA parser. Map exactly which files/functions are reusable as-is vs. need an input adapter (discriminator / sound-card in place of SDR) and the NMEA-extract add. Turns "the chain is buildable" into "here are the specific parts and the specific glue."
2. **The bench (the real progress).** The known-plaintext rig and experiment #1 above. Optionally one more desk thread first — the exact **TIA-102.BAJB Tier 1 SAP data-unit layout**, or **OP25's discriminator-audio input mode** (so the Sound Blaster is ready to wire straight in).

---

## Prior art, reference captures & the first rung (researched 2026-11-22)

Jim's first gate: **feed the sound card something a decoder says "yep, that's real data."** And: find existing Wireshark P25 work so we learn the structure precisely. Both answered — we even cloned and read the real code.

**Is there a P25 Wireshark dissector / captures? Yes, partially.**
- **The precise structural reference is one file: `wireshark/plugins/p25/packet-p25cai.c`** — the OP25 team's **P25 Common Air Interface dissector** (decodes CAI frames field-by-field; a commit history entry reads "added TSBK dissection"). It's fed to Wireshark via **OP25's "P25-in-UDP" encapsulation** (UDP port **23456**). Wireshark has **no built-in P25 dissector** and ships **no sample `.pcap`** (its P25 page is a stub with a placeholder). The dissector source lives only on an anti-bot-walled host (gitea.osmocom.org) — to read it we clone a mirror, not WebFetch.
- **Motorola LRRP location** has been community-reverse-engineered (DSD+ forums): binary **CMD/token** structure (e.g. a "Triggered Location Start Response" = CMD `0x0B`, token `0x22`…), riding SNDCP→IP/UDP. **This is the proprietary path — NOT our target.** Our Tier 1 is **ASCII NMEA**, not LRRP's binary tokens. Useful only so we don't chase it.

**The hard middle is real, and we've read it.** Cloned to the sandbox (`/home/claude/p25src/`, NOT vendored into this repo): **`boatbod/op25`** (maintained fork — note it **dropped** the legacy Wireshark plugin) and **`russinnes/P25-sndcp-packet-decoder`** (the data fork). The fork's **`op25/gr-op25_repeater/lib/p25p1_fdma.cc`** (~2800 lines, "heavily modified for PDU decoding") already does: P25 **PDU reassembly → IP datagram build → IP/UDP header validation (checksums) → payload extraction → full hexdump**, with per-RID reassembly windows, CRC32 checks, salvage logic, a **header-format × SAP histogram**, and fire-and-forget JSON/UDP output of recovered text (to `127.0.0.1:51001/51003`). Observed real traffic on its target systems: **SNDCP header begins `51 00`**, datagrams are TMS/ARS **text** on UDP ports **4005 (ARS) / 4007 (TMS)**, ~200 bytes. **What it is NOT:** it takes **SDR input** (not a sound card) and targets **text, not location/NMEA**. So the reusable gift is the entire symbols→PDU→IP/UDP→hexdump core + diagnostics; the glue we add is (a) sound-card/discriminator input and (b) recognize-and-extract NMEA.
- **This sharpens the one unknown into a one-glance read:** the fork already classifies every PDU by **SAP**. SNDCP packet data carries a specific SAP; a TIA "dedicated SAP, direct data" Tier 1 unit carries a *different* one. So when we feed our discriminator, **the SAP value in the decoded header tells us immediately** whether BK's location rides SNDCP/IP/UDP or a simpler direct-SAP unit — the fork's own hexdump/ledger shows it.

**Known-good signals to feed first (the "yep, real data" input), best → good:**
1. **Jim's own rig** — the ultimate reference: BK base RNDIS NMEA = labeled ground truth for the *exact* bytes his radios send (the "apple").
2. **Tait Phase-1 P25 GPS WAV files "using NMEA formatting"** — offered by user *hrh17* on the RadioReference DSD+ thread. A *different manufacturer's* P25 Phase-1 GPS in NMEA → corroborates the interoperable-Tier-1-NMEA story AND is a near-exact analog of our target. (Jim can grab these from the thread.)
3. **SIGID's `APCO25_P1_Data_C4FM_Audio.mp3`** — a free Phase-1 **data channel** C4FM recording (SIGID also has voice + trunking-control samples). Not GPS, but proves the sound→symbol→frame chain locks on real P25 data before we touch the radio.

**So the first rung, concretely:** run a known-good recording (Tait NMEA WAV ideal; SIGID data mp3 as a warm-up) through a discriminator-audio-capable decoder (DSD-FME, or OP25's UDP/audio input) and watch it **lock sync and emit frames / a hexdump** — that readout *is* "yep, that's real data." Then swap in our own DISC AUD and diff against the RNDIS NMEA. The fork's hexdump + SAP ledger is the exact instrument for both.

---

## First-capture & bring-up method (planned 2026-11-22; Jim leads the bench, Claude leads the decode)

**Roles (Jim, 2026-11-22):** Claude is lead on all DSP/decode (slicer, sync, de-trellis, deinterleave, FEC, parsing — writes every line). Jim provides clean signal + is the hands on the bench + holds the ground truth. Both halves load-bearing; Claude has no radio/bench and can't fake the RF side. Claude reports honestly per stage ("worked / didn't / stuck here") and spells out every hands-on step one at a time (Jim doesn't keep commands in memory; ask for a screenshot, don't ask him to transcribe).

**The capture (Jim's hands):** a *straight discriminator* recording in Audacity — **mono, 96 kHz, 16-bit**, a few **clean GPS keyups with silence between**, DISC AUD (DPH-CMD J2 CZ8) → sound-card line-in. For each keyup, note the NMEA the tracker showed = the answer key. Packets carry **no voice**, so a burst reads as: full-scale **noise → structured "head"** (frame sync/preamble, where deviation snaps to 4 bounded levels) → **data**.
- *AC-coupling caveat (Claude handles in software):* most line-ins high-pass, so a long run of one symbol droops (baseline wander) and can smear the 4 levels; short bursts limit it + DC-restoration fixes it. Flagged so a droopy capture doesn't fool us.

**Structure discovery before bit-decode ("packet place awareness" — Jim's framing):**
1. **Auto-segment** bursts (noise→4-level structure via sample variance / 4800 Hz symbol energy) — no hand-trimming.
2. **Diff multiple packets** → zone map: **rock-constant** (frame sync + NID, identical every frame) / **ticking** (PDU header seq/fragment counters) / **fully-varying** (payload + CRC = the GPS). Even a stationary unit varies the data zone because the **UTC time ticks every fix**.
3. **Correlate the fixed 24-dibit P25 frame sync** to anchor exact frame start = the precise ruler for every later stage.
4. *Caveat:* interleaving + FEC **spread** the varying bits across the data block, so the raw-symbol diff localizes the **data region & its length**, NOT lat-vs-lon; byte-level localization appears after de-interleave.

**Dual known-plaintext harness (we have BOTH ends):**
- **RNDIS byte-exact NMEA = the debugger** during bring-up — tells *which byte* broke when a sentence comes out 90% right (the map can't).
- **The existing P25 GPS Tracker / The Lookout live-map plot = the acceptance test** — a decoded fix lands on the real truck (Jim's point: visual confirmation, no string diff needed).
- **SUCCESS CRITERION = THE MISSION:** a fix decoded from **discriminator audio alone, RNDIS unplugged**, that still plots correctly on the map. That's "broke free of BK," on screen.

**Decode order once a good WAV is in hand:** segment bursts → diff to map overhead-vs-data → correlate sync to anchor frame start → slice 4-level symbols → NID/DUID → de-trellis → deinterleave → Golay/Hamming/RS + CRC → payload bytes → NMEA → (confirm against RNDIS byte feed, then against the map).

## Sources
- russinnes/P25-sndcp-packet-decoder (GitHub) — SNDCP→IPv4/UDP decode fork of OP25 (read its `lib/p25p1_fdma.cc`)
- boatbod/op25 (GitHub) — maintained OP25 fork (no legacy Wireshark plugin)
- OP25 legacy `wireshark/plugins/p25/packet-p25cai.c` (gitea.osmocom.org) — the P25 CAI Wireshark dissector
- wiki.wireshark.org/P25 — Wireshark P25 page (no native dissector, no sample pcap; P25-in-UDP port 23456)
- sigidwiki.com/wiki/P25 — sample recordings incl. `APCO25_P1_Data_C4FM_Audio.mp3` (Phase-1 data channel)
- RadioReference "Analyze P25 Packet Data (LRRP/Location)" DSD+ thread — LRRP structure + hrh17's Tait Phase-1 NMEA GPS WAVs
- OP25 decoder + P25-in-UDP encapsulation wikis (osmocom)
- "A Look at Project 25 (P25) Digital Radio" — CAI/framing (GNU Radio wiki, PDF)
- dsd-fme / OP25 / SDRTrunk comparison (pistack.xyz guide)
- TIA-102.BAJB-A Project 25 Tier 1 Location Services (the standard; NMEA 0183 position, dedicated CAI SAP)
- BK DPH-CMD service manual (Jim's PDF) — RX theory of operation, Fig 4-1/4-6, schematic p.6-49 (J2 pinout)
