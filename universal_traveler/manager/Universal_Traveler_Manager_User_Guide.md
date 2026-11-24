# Universal Traveler Manager — User Guide

## Installing — read this first

1. **Extract All** from the zip first (don't run it from inside the zip).
2. Open the folder. There is **one** thing to double-click: **`Start Universal Traveler Manager.bat`**. Everything else lives in the **System Files** folder — leave it alone.
3. Windows may show a blue "Windows protected your PC" box the first time. Click **More info → Run anyway**.
4. The first run installs two small helpers (the SSH helper and the image helper) automatically — just wait a moment. If it can't, it prints the one command to run and stops.
5. You need **Python 3** on the PC (from python.org — tick *Add python.exe to PATH* when you install it).

---

## What it is

The **Universal Traveler** is a small battery box (a GL-MT3000 travel router) that **decodes GPS positions straight off the radio** — from the radio's audio, with a USB sound card — and serves a live **split-screen map** to any phone, tablet or laptop with nothing installed on it. No cooperating base, no SDR, no PC in the field.

This app turns a bare box into a Universal Traveler in **one button**. It also flashes the box to the right firmware, names your units, and makes scan-to-open QR stickers. There are four tabs, left to right in the order you use them: **Flash to op24 → Set up a box → Name units → Make QR card.**

---

## The firmware the box needs (one time)

The Universal Traveler needs the box on the **OpenWrt 24.10 (kernel 6.6)** firmware. That is the firmware where the USB sound card and the map SSD can share the box's one USB hub. A box fresh from the carton is usually on the older (5.4) firmware, so it must be flashed once. You have two ways to do it:

- **The "Flash to op24" tab in this app** (Tab 1 below) — scripted, with a byte-for-byte check on the box before it flashes.
- **GL's own dashboard** — open `http://192.168.8.1` → **Settings → Upgrade** → choose the **24.10 / op24** image, **keep-settings OFF**.

Either way the box also needs the internet **once** during *setup* (not the flash), for its system packages (Python, libusb, the sound-card driver) from GL/OpenWrt's own feed. After that it never needs the internet again.

---

## Tab 1 — Flash to op24

Only needed if the box is still on the old (5.4) firmware. **This erases the box** (resets it to factory), so do it on a bench with steady power, not in the field.

1. Plug the box in, connect your PC to it.
2. Enter the box **IP** (`192.168.8.1`) and its current **admin password** (set on GL's first-boot).
3. The **firmware image** box should already point at the op24 `.bin` in your Downloads; if not, click **Change…** and pick it.
4. Click **Flash to op24** and confirm. Keep the box on power and don't touch it for ~3–4 minutes.

The app uploads the image to the box's memory, **verifies its SHA-256 on the box** (it refuses to flash a corrupt or wrong image), flashes it, waits for the box to come back, and then **confirms the flash actually took** before saying FLASHED. When it's done the box is factory op24 — open `http://192.168.8.1`, do GL first-boot (set a new admin password), then go to **Set up a box**.

> If a flash ever fails, the box isn't lost: hold its **reset** button ~10 seconds for GL's recovery page and flash again.

---

## Tab 2 — Set up a box

1. Plug the new box in, connect your PC to it (its Wi-Fi or its LAN port).
2. In **New box IP** leave `192.168.8.1` (the default) unless you changed it.
3. Type the box's **admin password** (the one you set on GL's first-boot screen). It is used over SSH and **not saved**.
4. Click **Set up this box**.

The log shows each step. First it checks the firmware — if the box is still on the old firmware it stops and tells you to flash 6.6 first. Otherwise it installs Python, libusb and the sound-card driver, delivers the decode engine and the map, installs the two boot services, starts them, and then **actually checks the map is serving** before saying **DONE**.

When it's done, plug the **sound card** (radio audio), the **map SSD** and the **Garmin GPS** into the powered hub, and open the map at **`http://192.168.8.1:8088/`**.

### What goes on the hub

- **USB sound card** — takes the radio's discriminator/detector audio (the flat detected audio, not the speaker audio). This is what the box decodes GPS from.
- **Map SSD** — holds a **matching pair** of maps for the same area: one **hybrid/satellite** and one **street**. Name them so one reads as hybrid and one as street; the split-screen uses the pair.
- **Garmin GPS 18 USB** — the box's own "you are here" position, centered on the map.

Use a **powered** USB hub — the box's own USB power is tight for three devices.

---

## Tab 3 — Name units

Every radio shows on the map by its unit ID. To give them crew names:

1. Enter the box **IP** and click **Load from box**.
2. Edit the **Name** beside each **Unit ID**, or **+ Add unit** for a new one.
3. **Save to box.** The names appear on the map within a few seconds.

---

## Tab 4 — Make QR card

Makes a print-ready sticker a crew scans with a phone camera — no app, no typing, no login. Pick what the sticker should do:

- **Open the map** — scanning opens the split-screen map. The address is carried as `http://` so the phone won't force `https`.
- **Join the Wi-Fi** — scanning joins the box's Wi-Fi. Enter the **Wi-Fi name (SSID)** and **password** (leave the password blank for an open network).
- **Join + open** — one card with **two** codes: scan the first to join the Wi-Fi, the second to open the map.

Enter the box **IP** (and an optional label for the box), choose the mode, then click **Make QR card**. The card is saved to your **Downloads** folder — print it and stick it on the box.

> **Wi-Fi tip:** if a phone was ever connected to this box's network before, **Forget** that network first or it won't act on the join code. When the phone asks *"stay connected? — the network has no internet,"* answer **Always**, and turn on **Auto-connect**, or Android will drop the box for cellular.

---

## Troubleshooting

- **"This box is on kernel 5.4 … too old."** The box is still on the old firmware. Flash it with **Tab 1 (Flash to op24)** or GL's dashboard, then run setup again.
- **"Stopped at: … the box needs the internet once."** Setup stops and names the step that failed. The box needs a working internet uplink the first time (for Python, libusb, the sound-card driver). Give it internet and run setup again.
- **"it did NOT flash … still accepts the old password."** The scripted flash refused the image, so the box is unchanged (not bricked). Flash it with **GL's dashboard** instead (keep-settings OFF), then do first-boot and run Set up a box.
- **"Could not log in."** Check the IP, that it's the right box, and the admin password. If you just flashed or reset the box, its SSH identity changed — that's normal; the app auto-accepts it.
- **Map page not responding / feed silent after setup.** Watch the log for the step that failed and re-run setup. The box needs its one-time internet for the system packages.
- **No units on the map.** Units appear when a radio transmits a GPS position. The box's own Garmin dot ("you are here") shows as soon as the Garmin has a fix with a clear sky view.
- **"needs TWO maps of the same area on the SSD."** Put a matching hybrid **and** street map for the same area on the SSD.
