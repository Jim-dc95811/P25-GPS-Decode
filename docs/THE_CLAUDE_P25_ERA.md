# The Claude P25 Era — The Record

**Dated 2026-11-25. Written by Claude, for the record, at Jim's request** — a full dump of
everything held in working memory the day the wall came down, so that no compaction, reset, or
fresh session ever loses it. This is the capstone of the P25-GPS-Decode project: the day a plain
PC, a sound card, and free software read **both P25 GPS location and P25 voice straight off the
air** — no SDR, no cooperating base station, no vendor infrastructure.

> Public-safe: no employer/agency names anywhere (Jim's standing rule). "The fleet" = Jim's
> P25 Phase-1 conventional VHF radios. Precedence as always: live code wins over this prose;
> this is the narrative + the landmines, `docs/DECODE_PLAN.md` is the code-level canonical.

---

## 1. What was achieved

In roughly **one day of focused bench work (2026-11-23 → 2026-11-25)**, the project went from
"can we decode P25 off the air at all" to **both halves of the holy grail proven end to end**:

1. **Tier-1 GPS location, off the air** — a radio's discriminator audio → a USB sound card →
   software → the exact `$G?GGA` + `$PP25,<unit-id>` NMEA sentence the cooperating base reports,
   matching the RNDIS answer-key **character for character**, position *and* unit ID. First live
   over-the-air decode off a real radio: **2026-11-23, 16:17** (unit `9076802`, 12 sats, valid
   checksum, the moment it keyed up). Proven live on the box, on a PC, and plotted on a map.

2. **Receiver sensitivity matching a purpose-built P25 radio** — a calibrated VIAVI sweep put our
   software decoder's 5% BER point at **≈ −119 dBm** (UFO202 line-in off the NX-700 DEO), inside
   the −116…−119 dBm band of commercial P25 gear. Jim's own 1,000-plus bench measurements put a
   real BK at −120/−121 dBm. **"Everybody meets at the cliff, and we made it with everybody."**

3. **Voice, off the air, in free software** — the same decoder that locks the Phase-1 frames for
   GPS also carries the 9 IMBE voice codewords per LDU. Pulled them out (Annex-H deinterleave +
   status-symbol skip), fed them to mbelib's IMBE 4400 synthesizer, and reconstructed
   **"Testing 1234 1234" spoken three times**, decoded entirely in our own software — **no DVstick
   required** for Phase-1 IMBE. Confirmed clean by ear and by energy-envelope structure
   (`2026-11-25`).

The barrier that had stood for years — GPS-out-of-P25 locked behind cooperating base stations,
SDR toolchains, and vocoder patents — turned out to be **a clock that never drifts and a 72-dibit
interleave table.** No magic. The wall was thinner than everyone assumed; it just took the right
ears and the right hands to keep pushing.

---

## 2. The mission (why this exists)

Jim's long-held "original Holy Grail": get **GPS location out of P25 radio transmissions for
firefighter safety**, with no dependency on a cooperating base radio handing over the data. An
earlier agency effort was shot down for anonymity reasons (users control GPS at the radio). This
project is the independent, passive, off-air answer: **Tier-1 GPS for the people** — any Phase-1
fleet, a $40–100 receiver, an offline map, nothing installed on the viewer.

**P25 Tier 1** (TIA-102.BAJB) is the standardized GPS-over-P25 format: NMEA carried in data PDUs.
That is the target — **not** Motorola's proprietary LRRP, **not** Tier 2. We decode **data and
voice, never trunking** — Jim's fleet is **Phase-1 conventional** (FDMA, single channel, voice
on-channel, "the easy one").

---

## 3. The architecture — one engine, two housings, now two repos

The decode engine is the invention; everything else is packaging around the one question
*"where does the operator need this to run?"*

- **The Traveler PC** (canonical home: sibling repo **`The-P25-Project`**) — the pure-PC product.
  On a normal PC you can run Python on, the whole invention is just: USB sound card on the radio's
  detector audio + a USB Garmin + drop in offline maps → a live fleet map in a browser tab, your
  own position in teal, name units from the map. One `.bat`, nothing to flash or SSH. This is the
  product; **the VOICE build happens here.**

- **The Universal Traveler** (this repo, `P25-GPS-Decode`) — the **Group-Policy-locked-PC
  variant**: the same decode, but on a ~$40 GL-MT3000 travel router (OpenWrt), because agency PCs
  are locked down (Python blocked, GitHub blocked). Proven self-contained on the box: a **stdlib
  pure-Python decoder** (no numpy/scipy — the box's opkg has neither) runs on the router itself,
  SoundBlaster → arecord → `ota_bridge.py` → `:10110` → the Traveler's own `units_kml` →
  split-screen map. A one-click **Universal Traveler Manager** (PC app) flashes a carton box from
  kernel 5.4 to OpenWrt 24.10/6.6 and provisions it end to end — **proven on a brand-new factory
  box 2026-11-24.** Every path closed.

- **The join** (Jim's distribution insight): share the Traveler PC's screen + PC audio over
  **Microsoft Teams** and the product becomes a live, shareable P25 common operating picture —
  fleet map + positions + voice — delivered through a tool the agency already runs. The capture
  half solved *acquisition* (off-air, cheap, no infrastructure); Teams solves *distribution* (one
  receiver PC = the headend, everyone else is a viewer with nothing installed). Carried node =
  receiver + sound card + Traveler PC + USB GPS + **Starlink Mini** uplink + Teams out. No-cell
  wildland command is exactly where vendor AVL *cannot* deploy — so there's not just no product for
  sale, there's no alternative at all.

**Build rule throughout (Jim's):** proven engines are kept as **sealed modules bolted in** (the
bit-exact DSP decode kernel, `units_kml`, `map.html`, the Garmin reader); the plumbing is built
**clean, one coherent program** — never a "50-patch" patchwork of byte-for-byte old parts.

---

## 4. The GPS decode chain (every stage)

Discriminator audio in, NMEA out. All in `decode/` (numpy/scipy research engine) with a byte-equal
stdlib twin in `decode_pure/` for the box. `python3 decode/decode_capture.py <wav>`.

1. **The tap.** Preferred = **Kenwood NX-700 DB-25 pin 19 (DEO), radio set WIDE** (external, no
   disassembly). Alternate = BK DPH J2 pin CZ8. The DEO is a DSP-routed detected-signal output
   (flat, 48 kHz internal) — confirm cleanliness with the first eye diagram; it proved clean. We
   only ever **receive** — never transmit or alter a radio.

2. **Front end** (`frontend.py`) — OP25's exact front end: `rmsagc` → `c4fm` RX de-emphasis symbol
   filter (`transfer_function_rx`, span 9). **This was the key early fix** — a hand-rolled
   moving-average pre-filter was the fault, not the capture. Dropped it for OP25's real filter.

3. **Capture format** — **48 kHz** native (integer 10 samples/symbol at 4800 baud) is cleaner than
   44.1 k resampled. Windows audio "enhancements" OFF, Communications tab "Do nothing", no clip,
   ~2 s lead-in before the first key-up.

4. **Demod.** Two paths, and **which one you use matters** (see §6, the landmine that cracked
   voice):
   - **GPS path** → `fsk4_demod.py`, the OP25 **MMSE tracking loop** (`tracking_loop_mmse`). Gives a
     clean symmetric eye; it force-locks on the *payload* deep in the body, so it never needs the
     NID.
   - **NID/header path** → **fixed-timing demod** (upsample ×4, pick the crispest fixed sample
     phase, sample every symbol, **no tracking loop**). Because 48 kHz = exactly 10× 4800 baud, the
     clock never drifts; the MMSE loop *over-corrects* a clock that isn't moving and wobbles ~30
     symbols after each sync — landing the fuzz on the NID.

5. **Slice** — adaptive 4-level **kmeans**, not fixed thresholds (the levels can sit asymmetric).

6. **Frame sync** (`framer.py`) — OP25 streaming sync on `0x5575F5FF77FF` (24 dibits, popcount
   ≤ 6) → NID (BCH(63,16,11), ec ≤ 4, DUID/parity) → `process_blocks`. DUID 5 = LDU1, 10 = LDU2.

7. **FEC** (`pdu_blocks.py`) — OP25 1/2 + 3/4 trellis/deinterleave + CRC, **plus
   `viterbi_deinterleave_12`**: a proper Viterbi decode of the rate-1/2 data blocks. OP25's
   *greedy* 1/2 decoder hard-failed on residual errors (4/12 blocks); **Viterbi recovers 12/12** →
   the whole sentence. Second key win.

8. **Robust acquisition** — strict NID-validated framer, then a fallback **force-lock at the
   best-Hamming sync near the onset, validated by the PAYLOAD itself** ($PP25 ID + readable GGA,
   not the NID), across a few window offsets + both polarities.

**Burst gate** (`decode_capture.py` / `live_core.py` / `squelch.py`): a packet is a **drop in the
broadband discriminator noise** (FM quieting — Jim's insight), measured as HF energy
(mean-squared first-difference). Open the expensive decode only while quieted, on a **fixed-geometry
window** from the onset (a variable window regressed to 1–2/10; fixed geometry = 10/10). On the box,
`arecord` reads the card raw; the GIL-safe reader does nothing but `read()` + put raw bytes (the
stereo→mono fold moved to the consumer, or a seconds-long pure-Python decode starves the pipe and
swallows the next bursts).

**Ground truth** = the base's RNDIS NMEA feed (`rig/rndis_nmea_logger.py`, de-frames the `80 … 81`
USB wrapper). Every decode claim is **diffed against it** — position AND unit ID — before it's
believed. That RNDIS wrapper is base-local USB transport, NOT over-the-air; the OTA decode sees the
P25 PDU, never the wrapper bytes.

**Proven:** 10/10 bursts on a clean capture, position + unit ID exact. Residual: occasional
single-glyph slips in the UTC *time* field (cosmetic; never touches position/ID/checksum), and a
garbled talker-ID prefix the box runtime normalizes to `$GPGGA` + recomputed checksum.

---

## 5. The sensitivity result (2026-11-25)

Front end **settled**: **Behringer UFO202 USB interface straight off the NX-700 DEO** (pin 19 →
RCA center / gnd → shell, switch on **LINE** not PHONO — PHONO's RIAA preamp mangles C4FM). No
external cap/pad/series-R: the radio's internal 4.7 µF (C789) already AC-couples the DEO, so it's
literally a wire. Flat 20 Hz–48 kHz line-in removes the SoundBlaster mic path's voice-band
eye-shaping + key-up DC transient (that's *distortion, not noise*, so soft-decision can't touch it —
the two gains stack).

**The patterns** (Jim corrected these; the reference is `docs/P25_RX_Test_Patterns.pdf`):
- **STD 1011** — clean tone, **0% injected errors** = the 0% baseline + decoder/chain control.
- **STD CAL** — 1011 with every 20th bit inverted = **4.977% BER baked in, level-independent**;
  it NEVER reads 0%. Purpose = **calibrate the BER meter**, not sensitivity.
- **STD 511 / O.153** — PRBS-9, the **rigorous sweep** pattern. Our DEO tap reads detected symbols
  directly, so we need no OEM test mode on the radio.
- **STD Silence** — valid voice frames at zero audio (noise-floor/squelch), not BER.

**Meter** (`decode/ber_meter.py`): self-consistency for 1011/baseline; **raw-vs-−90-clean-reference**
for the sweep (near/below the cliff, self-consistency mislocks the period and under-reports —
score against the clean reference pattern, period-folded + circular-aligned, and **trim the ~1.5 s
key-up/settling transient** before scoring). Calibrated live: **1011 @ −90 → 0.030%** (chain
control), **CAL @ −90 → 5.122%** (vs spec 4.977% — the error counter is honest).

**The sweep** (scored vs −90 clean 511): −112 → 0.06% · −116 → 1.01% · −117 → 1.57% · −118 → 2.89% ·
−119 → 4.35% · −120 → 13.5%. **5% crossing interpolates to ≈ −119.1 dBm.** A plain line-in on a
detector pin + our software **matches commercial P25 raw-symbol sensitivity.** (This is pre-FEC raw
BER; the soft-decision ~3 dB edge is a separate post-FEC/GPS-frame test.)

**Soft-decision FEC** (built, sandbox-verified, fold-in pending): `decode/soft_blocks.py` +
`decode_capture_soft.py` — soft-Viterbi twins (Euclidean metric on the MMSE soft symbols, same P25
trellis/tables). Measured **3.16 dB coding gain** at 10% block-error in AWGN sim; 4463 blocks
rescued vs 31 lost; byte-for-byte == hard on clean data (shipping path untouched, soft is additive).
That's ~40–50% more range — the weakest firefighter at the edge plotting instead of dropping off.
Lifts GPS *and* voice alike. Real field gain to be measured with Jim's calibrated step attenuator
(hard-vs-soft delta at 50% success).

---

## 6. The voice decode (every stage) — the day's breakthrough

The voice half was blocked, then unblocked, then finished — all 2026-11-25.

**The block, and the crack.** First OTA voice capture: `fsk4_demod` (MMSE) locked the frame
**syncs** perfectly (864-dibit spacing, NAC decoded to the real **0x455**) but **every NID failed
BCH**. Diagnosis that cracked it: **symbol crispness by region** — sync 74% on-target, body 78%,
but the **NID only 29%.** The NID is the only fuzzy region, sitting right after each sync. Root
cause: the MMSE timing loop over-corrects a clock that never drifts (48 kHz = 10× 4800), wobbling
~30 symbols after each strong sync — landing the fuzz on the NID. **Fix: fixed-timing demod** (no
tracking loop). Result: each keyup → **~29/28/28 valid frames, NAC 0x455 every frame, clean
alternating LDU1(5)/LDU2(10)**, ec mean 0.6.

**Jim's nudge** — *"any chance it's AMBE+2 not IMBE? we have the DVstick to fall back on"* — is what
drove looking **below** the vocoder. The answer: a **codec-independent frame/demod bug, not the
codec.** (See §7 for the IMBE/AMBE+2 settlement.)

**Extraction** (`decode/voice_ldu.py`, new today): for each LDU (DUID 5/10), replicate DSD's
sequential dibit read and pull the 9 IMBE voice frames:
- **Reader** — DSD `read_dibit`: a status symbol occurs every 36 dibits; `status_count` starts at
  **21** at the LDU body (sync 24 + NID 32 + 1 status = **57 dibits in**); when it hits 35, skip the
  status dibit and reset to 1.
- **Inter-frame gaps** (data dibits before each voice frame): `[0, 0, 20, 20, 20, 20, 20, 20, 16]`
  — IMBE1 & IMBE2 back-to-back; 4 hex words (20 dibits) before IMBE3…IMBE8; LSD (16) before IMBE9.
- **Annex-H deinterleave** (TIA-102.BABA, tables `iW/iX/iY/iZ` verbatim from DSD `p25p1_const.h`):
  72 data dibits → `imbe_fr[8][23]`, high bit → `fr[iW[j]][iX[j]]`, low bit → `fr[iY[j]][iZ[j]]`.
- Writes `<out>.imbe` = concatenated frames, 8×23 bytes each (row-major 0/1).

**Synthesis** (`voice/imbe_ota.c`, mbelib vendored in `voice/mbelib/`): each frame → `imbe_fr[8][23]`
→ `mbe_processImbe7200x4400Frame(...)` (the Frame/ECC path: C0 Golay + PN descramble + Golay/Hamming
+ synthesis) → 160 shorts → s16 PCM 8 kHz mono. Build: `gcc -O2 -I mbelib mbelib/*.c imbe_ota.c
-lm -o imbe_ota` (`voice/build_ota.sh`; no cmake, just a C compiler + libm).

**Result** (the "Testing 1234 1234" ×3 capture, 27 s, 3 keyups):
- Keyup 1 (2.5–8.1 s): 29 LDU → 261 voice frames · Keyup 2 (10.0–15.5 s): 26 → 234 ·
  Keyup 3 (18.1–23.4 s): 28 → 252. **747 IMBE voice frames, 14.9 s @ 8 kHz, NAC 0x455 every frame.**
- Output energy envelope = **three loud bursts separated by near-silent gaps** = the exact shape of
  the phrase spoken three times. Speech structure, not a noise smear. **Confirmed by ear.**

**The earlier `.ambe`-container proof** (2026-11-25 am, settled the mechanism): Jim's BK tool
converts a 2 s `.wav` → `.ambe` = raw **88-bit IMBE voice frames, 11 bytes each, back-to-back, no
header, MSB-first** (file size = N×11; 20 ms/frame). Those are already-de-FEC'd **info** bits → feed
them to mbelib's `mbe_processImbe4400Data` (the **Data** path, NOT the 7200×4400 Frame path which is
for the 144-bit over-air frame). Decoded audio ear-confirmed + log-energy envelope correlation
**+0.933 / +0.950** vs source on two clips (LSB order loses clearly → MSB settled). Ear-confirmed by
Jim: *"WE ARE IN!!!! WORKS PERFECT!"*

---

## 7. The landmines (holes not to fall in twice)

- **Symbol recovery is SOLVED — use `fsk4_demod.py`, don't hand-roll it.** A fixed-step slicer
  gives ~15% symbol errors (tracks neither clock nor level nor DC). The MMSE loop fixes all three.
- **But for the NID/header, demod with FIXED timing** when fs is an integer multiple of the symbol
  rate — the MMSE loop *hurts* there (the discovery that cracked voice). **Diagnose demod health by
  region** (sync vs NID vs body on-target %), not just by sync lock.
- **Key-up DC transient is a capture artifact, not a decode bug.** The AC-coupling cap recharges at
  onset, compressing one outer level in the sync/early-NID region. The burst body is clean. Fix at
  the bench / with a real DC-block; don't shrink the demod window (that distorts symbols). Also
  **trim ~1.5 s of settling before scoring BER.**
- **BER patterns:** STD CAL is **NOT** a clean pattern (4.98% baked in — it calibrates the meter);
  **STD 1011** is the 0% baseline; **STD 511/O.153** is the sweep. Our DEO tap reads BER in software
  **without** the radio in OEM test mode. 5% point = pre-FEC raw BER (we match a good radio there);
  the soft-decision edge is post-FEC/message. **Near the cliff, score vs the clean −90 reference,
  not self-consistency** (it mislocks the period and under-reports).
- **IMBE is NOT a separate obstacle.** The fleet's vocoder is "Enhanced IMBE … AMBE+2 V1.80." In a
  modern radio, Phase-1 full-rate voice is just the full-rate mode of the AMBE+2 family (DVSI brands
  AMBE+2 "Enhanced IMBE"). **The IMBE 4.4k patents have expired → legal free-software decode**
  (mbelib), which is exactly what we did. AMBE+2 (Phase-2/DMR/NXDN) remains encumbered → that's the
  *only* case where the DVstick is needed. **So the DVstick is OPTIONAL for this Phase-1 project**
  (keep it as the sanity-check arbiter). Don't keep flagging "IMBE" as a blocker — it's the AMBE+2
  family throughout.
- **mbelib has two IMBE paths — pick the right one.** 88-bit already-de-FEC'd info bits (BK `.ambe`
  container) → `mbe_processImbe4400Data`. The 144-bit over-the-air LDU frame (`imbe_fr[8][23]`) →
  `mbe_processImbe7200x4400Frame` (does the Golay/Hamming FEC itself).
- **The individual ID is just the radio's own unit ID.** `$PP25,<id>` — NOT a PTT-vs-periodic tag,
  NOT a sequence. IDs like 9076801/02/03, or a short ID like 1. A decoded burst gives **two**
  things to diff against ground truth (position AND unit ID). The voice link-control **source ID**
  is the join key between the position layer and the voice layer (the combo platter).
- **Validate against ground truth, not guesses** — the RNDIS NMEA is the answer key; diff before
  believing. The RNDIS `80…81` wrapper is base-local USB, never over-the-air.
- **The service-manual PDF and operational voice captures are NOT in the repo** (Jim's uploads;
  kept out — operational voice stays public-safe-out). The CZ8/DEO findings themselves are written
  down so they're not lost.
- **Receive-only, always.** Never transmit or alter a radio.

---

## 8. Proven vs open (as of 2026-11-25)

**Proven / demonstrated:**
- OTA Tier-1 GPS decode off a radio, live, position + unit ID exact vs ground truth (10/10 clean).
- Receiver sensitivity ≈ −119 dBm (matches commercial P25).
- OTA voice decode in free software (IMBE via mbelib), "Testing 1234 1234" ×3, ear-confirmed.
- Self-contained decode on a $40 box; one-click flash + provision of a carton box; map plotting.
- BER meter calibrated on live signal (CAL counter honest, 1011 control clean).
- Soft-decision FEC built + sandbox-verified (3.16 dB sim).

**Open (all Jim's-hands or straightforward):**
1. **DVstick cross-check** — run today's keyup through the AMBE+2 stick, confirm ours matches it
   word for word → settles IMBE-vs-AMBE+2 permanently, makes the claim unassailable.
2. **A second, independent voice capture** — a different phrase → "it decoded *your* voice" becomes
   "it decodes voice."
3. **Soft-decision field measurement** — `decode_capture_soft.py` on captures at each attenuator
   step; hard-vs-soft delta at 50% = real field coding gain vs the 3.2 dB sim.
4. **Fuse the voice layer with the position layer by unit ID** — the combo platter: speaking unit
   lit on the map by its link-control source ID, VU meter, current-speaker panel.
5. **Rule #1 quality gate** (Jim's) — gate on decode quality *before* the vocoder (mute marginal
   frames, hold through fades, picky-but-tunable); never feed the vocoder garbage.
6. **GitHub reorg** — rationalize `decode/` (numpy) vs `decode_pure/` (stdlib), the tool lineages,
   and settle how the two P25 repos relate to the ArcGIS Earth Unlocked family now that OTA works.
   Both P25 repos stay **unadvertised** to the family until Jim's explicit go.

---

## 9. For the record — how it actually happened

This was not a machine teaching itself in a vacuum. A radio expert with 37 years at the bench
handed clean captures at calibrated levels, caught the errors (STD CAL is not a 0% pattern), and —
the nudge that cracked the voice half — looked at a stuck decode and said *"any chance it's AMBE+2,
we have the DVstick to fall back on,"* which sent the search **below** the vocoder where the real
bug was. The crispness-by-region diagnosis and the MMSE-vs-fixed-timing fix came out of decades of
intuition for how a signal degrades. Jim ran every capture, every level, every keyup; Claude wrote
the code and did the DSP. **We read P25 off the air in about a day.**

Jim called it his Riemann hypothesis — the thing he'd chased for years. The honest difference: the
Riemann hypothesis is one person's monument; this is a thing firefighters will carry on a cheap box
someday because he refused to let "the agency wasn't interested" be the end of it. Off the air,
free, nobody's gatekeeper.

**2026-11-25 — the day the wall came down.**
