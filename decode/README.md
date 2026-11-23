# decode/ — over-the-air P25 Tier-1 GPS decoder (PROVEN)

Reads **discriminator audio** (a WAV from an FM-detector tap, no SDR) and
decodes P25 Tier-1 location to **NMEA**, matching a BK base's RNDIS output
character-for-character. See `../docs/P25_OTA_GPS_Decoder_Engineering_Reference.pdf`
for the full engineering writeup.

## Run
```
python3 decode_capture.py <discriminator_capture.wav>
```
Mono PCM WAV, 48 kHz preferred (integer 10 samples/symbol). Radio WIDE, squelch
open, on the fleet's P25 channel. Deps: numpy, scipy.

## Pipeline (entry point: decode_capture.py)
band-ratio burst detect → per-burst fresh demod → robust acquisition → NMEA.

| File | Role |
|---|---|
| `frontend.py` | OP25 RMS-AGC + **c4fm RX de-emphasis filter** — the piece that unlocked the decode (don't improvise a front end) |
| `fsk4_demod.py` | OP25 `tracking_loop_mmse` symbol recovery (clean eye) |
| `framer.py` | OP25 streaming sync (popcount≤6 vs `0x5575F5FF77FF`) + NID (BCH ec≤4, DUID/parity) + `process_blocks` |
| `bch_nid.py` | OP25 BCH(63,16) + `nid_codeword` |
| `pdu_blocks.py` | 1/2 greedy + **`viterbi_deinterleave_12`** (recovers 12/12 blocks vs greedy 4/12) + 3/4 Viterbi + CRC-16/32 |
| `decode_capture.py` | band-ratio detector + robust acquisition (strict framer → force-lock validated by the payload) |
| `fsk4_taps.npy` | OP25 129×8 MMSE interpolator table |
| `decode_nid.py`, `run_decode.py` | earlier single-burst harnesses (superseded by decode_capture.py) |

## Proven (2026-11-23, Jim's live DEO capture)
Full `$G?GGA` + `$PP25,9076802` sentences == the RNDIS answer key. 6/11 bursts
decode fully; the remaining 5 are signal-limited (a degraded ~30 s mid-capture
segment), proven not algorithm-limited.

## Landmines (full list in the engineering PDF §12)
- The "key-up transient" was a hand-rolled moving-average pre-filter, NOT the
  capture. Use OP25's c4fm RX filter + fixed-threshold slicing.
- Greedy 1/2 trellis hard-fails on ties → use Viterbi.
- Energy burst-detection fails on open-squelch audio → band-ratio (<3 kHz).
- One continuous demod drifts through inter-burst silence → fresh demod per burst.
- Relaxing the global sync threshold truncates the PDU body → strict + targeted
  force-lock validated by the payload.
