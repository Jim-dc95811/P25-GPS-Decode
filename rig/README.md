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
