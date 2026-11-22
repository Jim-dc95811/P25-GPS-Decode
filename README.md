# P25-GPS-Decode

**Decode Tier 1 GPS location broadcast over the air on a P25 radio channel — from a receiver's discriminator audio, with a sound card, no SDR.**

> 🤖 **Using AI assistance?** Have the agent read [`CLAUDE.md`](CLAUDE.md) first, then [`docs/DECODE_PLAN.md`](docs/DECODE_PLAN.md).

## What this is

A radio set to a P25 channel already demodulates the signal — the **discriminator output** is the recovered 4-level baseband, before any digital processing. This project takes that audio into a PC sound card and decodes the **P25 Tier 1 location data** (position as NMEA, a regulated public-safety interoperability format) **straight off the air** — without asking the radio to hand it over, and without a software-defined radio.

The point is independence and reach:

- **No cooperating base radio.** Existing tools read GPS out of a specific manufacturer's base over a USB link. This reads it off the RF, from any compatible receiver's discriminator.
- **The whole P25 world, not one brand.** Tier 1 location is a common, regulated format across manufacturers.
- **Data, not voice.** We decode the location data units and ignore voice entirely — so there's no vocoder and none of the patent baggage that comes with P25 voice decoding.

## Status — early, honest

This is a **research build, not yet proven end-to-end over the air.** What's settled and what isn't is laid out plainly in [`docs/DECODE_PLAN.md`](docs/DECODE_PLAN.md):

- ✅ The tap point on the donor radio (discriminator audio off a connector pin).
- ✅ The standard the location rides in (TIA-102.BAJB Tier 1, NMEA inside).
- ✅ That the hard decode stages already exist in open tools (OP25 and a packet-data fork of it) and that no voice vocoder is needed.
- ❓ One real unknown — exactly how the location data unit is wrapped — which a bench rig with a **known-NMEA reference feed** resolves by direct comparison.
- ⬜ End-to-end decode of a live fix: the goal.

`capture/` holds the sound-card capture settings for the discriminator input.

## License

MIT — see [`LICENSE`](LICENSE). This project distributes a tool, not any agency's data. It only ever *receives*; it never transmits or alters a radio. Users are responsible for the laws and licenses that apply where they operate.
