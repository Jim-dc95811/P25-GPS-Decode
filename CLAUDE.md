# CLAUDE.md — P25-GPS-Decode

**Written by Claude, for Claude.** Read this first if you're resuming or picking up this project. It's the fast orientation; the deep technical reasoning is in [`docs/DECODE_PLAN.md`](docs/DECODE_PLAN.md) — **read that before any decode work.**

> **This repo is PUBLIC — keep this file public-safe** (strip any employer/agency names; Jim's own name and GitHub handle are fine). **Precedence:** live code/files win over any prose here; then this file; then older notes. A compacted/auto-summary of a prior session is NOT a source of truth — re-read **Current state** below and `docs/DECODE_PLAN.md` from the live repo before any mission- or architecture-level claim.

> **STANDALONE, DELIBERATELY UNLISTED (Jim, 2026-11-22).** This is its own project, **not** under the *ArcGIS Earth Unlocked* banner. It is **public but NOT advertised** — do **not** link it from the family repos, the front page, the site, the montage, the all-tools zip, the Py Vault, or the family pictogram **until the over-the-air decode is proven working.** Jim: *"You know the drill."* (The Unlocked family `CLAUDE.md` carries a quiet internal continuity pointer so a resuming Claude can find this repo — that's AI continuity, not public advertising. Keep it that way.)

---

## What it is (one breath)

Decode **P25 Tier 1 GPS location straight off the air** from a receiver's **discriminator audio** (via a PC sound card), with **no SDR** and **no cooperating base radio**. The radio already demodulates the RF; we take its recovered 4-level baseband and do the digital decode in software — symbol slice → P25 frames → data PDUs → NMEA. We decode **data, not voice** (so no vocoder, no DVSI patent). Goal: break free of the BK-base-hands-us-NMEA dependency and read **any** P25 fleet's location.

---

## Current state  *(update this when it changes)*

**2026-11-23 — FIRST OVER-THE-AIR P25 DECODE: the MMSE symbol front end is ported, works, and the OTA NID reads NAC `0x455` (Jim's confirmed NAC).** On Jim's live-radio DEO capture (10 GPS periodic reports + matching RNDIS answer-key log), the decoder peels discriminator audio down through the frame sync to the NID. **What's proven (code in `decode/`, run `decode/decode_nid.py <wav> <burst_s>`):**
- **`decode/fsk4_demod.py`** = a faithful Python port of **OP25's `fsk4_demod_ff` `tracking_loop_mmse`** (MMSE interpolating symbol-clock recovery + symbol-spread AGC + fine-frequency integrator; taps in `fsk4_taps.npy`). This was the search-first fix for the ~15 % symbol-error rate the earlier hand-rolled fixed-step slicer had. It locks to a **clean, symmetric 4-level eye** over the burst body (kmeans ≈ −3.4,−1,+1,+3.4) straight off 44.1 kHz, no pre-resample.
- Sync-hunt → adaptive kmeans slice → NID → **OP25 BCH(63,16)** (`decode/bch_nid.py`) → on the cleanly-synced bursts, **NAC `0x455`** — matches the NAC Jim programs. First real OTA P25 frame decode in the project; the RNDIS log is the answer key the final payload gets diffed against.

**The two real gates left (next build, honestly):**
1. **Key-up DC transient** compresses the `−3` level in the **sync / early-NID** region of some bursts (AC-coupling recharge at key-up — the sync `+3`s read ~+2.7 but the `−3`s read ~−0.4, a decaying +1.15 offset). A symmetric high-pass can't null it without eating symbol energy → **address at the bench** (capture level/coupling, or trigger capture just before key-up) AND fold a real DC-block into the front end. The **burst body is clean**, so the payload is unaffected.
2. **Robust framing + payload:** `decode_nid.py`'s sync hunt + fixed status-symbol index false-locks on off-position/transient bursts. Port **OP25 `p25_framer.cc`** (status-symbol phase from the sync), then the **PDU payload → NMEA** path (deinterleave + trellis 1/2 + CRC) from the `russinnes/P25-sndcp-packet-decoder` fork. The NMEA then gets byte-diffed against the RNDIS answer key (`rig/`): decoder NMEA == RNDIS NMEA (same position AND same individual ID) = the Universal Traveler input mod proven.

---

## The product architecture — TWO TRAVELERS (Jim, 2026-11-22)

**Two products that differ ONLY in the input stage; everything downstream is the proven Traveler, untouched.** The OTA decoder is a **drop-in replacement for the RNDIS input stage** — not a new system.

1. **The BK Traveler — PROVEN (shipped).** Input = the BK base's **RNDIS** feed: a cooperating BK base/gateway de-frames the received P25 GPS and hands clean NMEA over USB-RNDIS; `bk_bridge` reads it → clean NMEA on `:10110` → `units_kml` → the map any browser opens.

2. **The Universal Traveler — the OTA mission's product.** Input = **C4FM discriminator audio**, **locally decoded + parsed on the box** into the **same NMEA the RNDIS provided**. No cooperating base; any radio that exposes **flat discriminator/detector audio** (e.g. NX-700 DEO pin 19 — NOT filtered voice audio). Because it emits the identical `$GNGGA`+`$PP25` contract on the same feed, `units_kml`, the GPS plotting, the browser display are all **byte-for-byte the proven Traveler**. The only new part is the front-end module that turns discriminator audio into that NMEA. (Eventually runs on the MT3000 itself — phase two; 4800 baud DSP load is light, confirm on the box's ARM when we get there. First we prove the decode on a PC.)

**This sharpens the whole mission's success criterion to one sentence:** the decoder's job is to **emit the same NMEA the RNDIS feed emits** — which the answer-key rig (`rig/rndis_nmea_logger.py`) captures directly. **Decoder NMEA == RNDIS NMEA (same position AND same individual ID) = the Universal Traveler's input mod is proven.** It's a byte diff against ground truth, not a fuzzy "is it working." Develop/prove the decoder standalone (PC, against the log), then slot it in as the input module; the proven box is never touched to find out if the air works.

---

## Landmines / things not to re-derive

- **Symbol recovery is SOLVED — use `decode/fsk4_demod.py`, don't hand-roll it again.** A fixed-step slicer (find s0 by boxcar correlation, step every N samples, fixed thresholds) gives ~15 % symbol errors — it tracks neither clock nor level nor DC drift. The **MMSE loop ported from OP25** (`tracking_loop_mmse`) fixes all three and gives a clean symmetric eye. Feed it a signal scaled so the 4 levels sit near ±1,±3 (std≈√5); it nulls residual DC itself once locked. Slice its soft output with **adaptive 4-level kmeans**, not fixed thresholds (the levels can be asymmetric).
- **Key-up DC transient (a capture artifact, not a decode bug).** At burst onset the AC-coupling cap recharges, leaving a decaying DC offset that compresses one outer level in the **sync / early-NID** region (seen: sync `+3`≈+2.7, `−3`≈−0.4 ⇒ +1.15 offset). A symmetric high-pass can't remove it without eating symbol energy. The **burst body is clean** (payload unaffected). Fix at the bench (capture level/coupling, or trigger just before key-up) and with a real front-end DC-block; don't chase it by shrinking the moving-average window (that distorts symbols).

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
