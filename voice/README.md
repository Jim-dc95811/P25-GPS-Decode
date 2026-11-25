# voice/ — software IMBE voice decode (P25 Phase 1)

Turns P25 Phase 1 voice frames into audio in **pure software** — no DVSI
dongle, no SDR. The vocoder kernel is **mbelib** (ISC license, vendored in
`mbelib/`, unmodified); `imbe_dec.c` is a thin driver around it.

## Why this exists
P25 Phase 1 conventional carries voice as **IMBE 7200×4400** (the "4.4 kb/s
IMBE" of the P25 Common Air Interface). IMBE's patents have expired, so it
can be decoded in free software. (AMBE+2 — Phase 2, DMR, NXDN, D-STAR — is
the still-encumbered codec that needs licensed silicon; it is **not** what
Phase 1 uses over the air. A modern radio's vocoder chip is an AMBE+2 part
running its IMBE mode for Phase 1.) This is the **voice** half of the
project's goal, alongside the Tier-1 GPS decode.

## What was proven (2026-11-25)
A radio-side vocoder tool emits short voice clips as `.ambe` files. Their
container is the simplest possible: **raw 88-bit IMBE voice frames, 11 bytes
each, back to back, no header, MSB-first** (file size is exactly N × 11, and
20 ms/frame matches the source clip length).

Feeding those 88-bit frames straight into mbelib's `mbe_processImbe4400Data`
reconstructs the original speech:
- **Confirmed intelligible by ear** against the source recordings.
- Decoded-vs-source log-energy **envelope correlation +0.933 and +0.950** on
  two independent clips — syllable-for-syllable timing. Wrong bit order (LSB)
  loses clearly, so MSB-first is settled.

Source audio clips are intentionally **not committed** (operational voice is
kept out of the public repo). This README is the record.

## Build & run
```sh
./build.sh                        # vendored mbelib + driver -> ./imbe_dec
./imbe_dec in.ambe out.wav msb    # 88-bit IMBE frames -> 8 kHz/16-bit mono WAV
```
Needs only a C compiler and libm. The `msb` argument is the proven bit order;
`lsb` is kept as a switch for other containers.

## How it folds into the mission
The over-the-air decoder already locks P25 Phase 1 frames to pull the Tier-1
GPS. The **same** frames (LDU1/LDU2) carry the 88-bit IMBE voice — route those
to this kernel and the fleet gains a voice layer: the speaking unit lit on the
map by its source ID, fused by unit ID with the position layer. This is the
sealed voice engine; it folds into The Traveler PC's bundled engine (sibling
repo `The-P25-Project`) when the voice build lands.

Quality gate still applies (project Rule #1): gate on frame/decode quality
*before* the vocoder so marginal frames mute rather than screech.

## License
`mbelib/` is mbelib, ISC license — see `mbelib/COPYRIGHT`. Unmodified, vendored
so this decoder builds with nothing but a C compiler.
