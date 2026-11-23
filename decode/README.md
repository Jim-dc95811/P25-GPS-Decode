# decode/ — the over-the-air P25 symbol + NID decoder (first layers)

Reads **discriminator audio** (a WAV from the sound-card tap, no SDR) and peels the
P25 Tier-1 frame down to the **NID** (NAC + DUID). This is the front half of the
OTA mission; the PDU payload -> NMEA path is the next build.

## Files
- **`fsk4_demod.py`** — the keeper. A faithful port of **OP25's `fsk4_demod_ff`
  `tracking_loop_mmse`**: MMSE fractional-interpolation symbol-clock recovery +
  symbol-spread AGC + fine-frequency integrator. Float discriminator samples in →
  soft 4-level symbols out (−3,−1,+1,+3). No pre-resampling needed; locks at 44.1 kHz
  native for 4800 baud. (Search-first win: this solved the ~15 %-symbol-error problem
  the hand-rolled fixed-step slicer had — the loop tracks clock + level + DC drift.)
- **`fsk4_taps.npy`** — OP25's machine-generated 129×8 MMSE interpolator table.
- **`bch_nid.py`** — OP25's BCH(63,16) tables + decoder + `nid_codeword` (NAC/DUID).
- **`decode_nid.py`** — the glue: WAV → DC-block → scale → `fsk4_demod` → soft-NCC
  frame-sync hunt → adaptive 4-level kmeans slice → NID → BCH.
  `python3 decode_nid.py <capture.wav> <burst_start_s> [...]`

## Proven 2026-11-23 (Jim's live-radio DEO capture, 10 GPS periodic reports)
- The MMSE loop locks to a **clean, symmetric 4-level eye** over the burst body
  (kmeans levels ≈ −3.4, −1.0, +1.0, +3.4 every burst).
- On the cleanly-synced bursts the recovered **NID BCH-decodes to NAC `0x455`** —
  **Jim's actual, independently-confirmed NAC.** First genuine OTA P25 decode here.

## Known, open (the real gates — next build)
1. **Key-up DC transient** compresses the `−3` level in the sync / early-NID region
   of some bursts (a capture-side artifact: AC-coupling cap recharge at key-up).
   A symmetric high-pass can't remove it without eating symbol energy. Address at
   the bench (level/coupling, or capture slightly before key-up) **and** fold a
   proper DC-block into the front end.
2. **Robust framing:** `decode_nid.py`'s sync hunt + fixed status-symbol index is
   fragile — off-position / transient-hit bursts false-lock on idle runs. Port
   **OP25 `p25_framer.cc`** (tracks the status-symbol phase from the sync position).
3. **Payload → NMEA:** the GPS lives in the PDU payload (deinterleave + trellis 1/2
   + CRC), not the NID. That's the `russinnes/P25-sndcp-packet-decoder` fork's core.
   The payload rides the clean burst body, so the transient doesn't block it.
