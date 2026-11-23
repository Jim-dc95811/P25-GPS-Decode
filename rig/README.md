# rig/ — the known-plaintext bench

Tools for the "apple" experiment: the BK base hands us finished NMEA over its
USB-RNDIS link (ground truth) while the SAME PC records the receiver's
discriminator/DEO audio into a sound card. Decode the audio, diff against the
NMEA, and the air is proven.

## rndis_nmea_logger.py — the answer-key recorder

Connects to the BK base relay (`10.250.46.6:65535`), subscribes
(`80 04 18 e4 81`), and writes every GPS sentence it hands us to a timestamped
log, echoing each fix to the console. Radio facts + the NMEA extractor
(regex + XOR checksum) are lifted **verbatim** from the proven `bk_bridge.py`
(The-Lookout). Stdlib only. **Read-only — never transmits to or alters a radio.**

Run it next to Audacity while you record the DEO audio:

    python3 rndis_nmea_logger.py

Writes `rndis_nmea_<timestamp>.log` (timestamped sentences — the answer key)
and `rndis_raw_<timestamp>.bin` (raw received bytes, insurance). Each 10-second
periodic report lands as a timestamped `$GNGGA`+`$PP25`, so every burst in the
WAV maps to a known fix. Proven end-to-end against a framed fake radio
2026-11-22 (clean `$GNGGA`/`$PP25` extracted, checksum-validated, fix parsed).

## Proven on real hardware 2026-11-22 (+ the BK RNDIS framing, decoded)

Ran against Jim's live BK base. Connected, subscribed, and logged clean
checksum-valid `$GNGGA`+`$PP25` for both PTT-triggered and periodic reports.
The raw `.bin` revealed the base's **USB-RNDIS transport framing** (this is the
base's own USB wrapper — **NOT** what goes over the air):

- **Idle/ack frame:** `80 04 19 10 10 07 01 52 53 00 03 13 81` (the `52 53` = "RS"
  ack), sent continuously. The logger's NMEA regex ignores these.
- **Data frame:** `80 0d 02 <id-field> <NMEA payload> <1-byte cksum> 81`.
  The `<id-field>` distinguishes report type:
  - **PTT-derived:** `00 00 01` → `$PP25,1` (trailing `01` = the console/keyed ID).
  - **Periodic:** `8a 82 00 42` → `$PP25,9076802` (full radio ID; `9076802 = 0x8A8042`).

**Mission implication:** the `80 … 81` wrapper is base-local USB transport and
will NOT appear in the over-the-air decode. OTA (TIA-102.BAJB Tier 1) carries the
`$GNGGA` NMEA inside a P25 CAI data unit. So the **answer key is the NMEA payload
(the position)** — identical whichever pipe it arrives on. The PTT-vs-periodic ID
contrast (`1` vs `9076802`) is a bonus cross-check if it survives to the air.
