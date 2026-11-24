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

This app turns a bare box into a Universal Traveler in **one button**, and also names your units and makes a scan-to-open QR card.

---

## Before you start — put the box on the right firmware (one time)

The Universal Traveler needs the box to be on the **OpenWrt 24.10 (kernel 6.6)** firmware. That is the firmware where the USB sound card and the map SSD can share the box's one USB hub. A box fresh from the carton is usually on the older firmware.

Flash it once through **GL's own dashboard** (open `http://192.168.8.1` in a browser → **Settings → Upgrade** → choose the **24.10 / op24** image). This app **does not** flash firmware — flashing is GL's job, and doing it from here could brick a box. The app simply checks the firmware and tells you if it's wrong.

> The box also needs the internet **once** during setup, for its system packages (Python, libusb, the sound-card driver) from GL/OpenWrt's own feed. After that it never needs the internet again.

---

## Tab 1 — Set up a box

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

## Tab 2 — Name units

Every radio shows on the map by its unit ID. To give them crew names:

1. Enter the box **IP** and click **Load from box**.
2. Edit the **Name** beside each **Unit ID**, or **+ Add unit** for a new one.
3. **Save to box.** The names appear on the map within a few seconds.

---

## Tab 3 — Make QR card

Makes a print-ready sticker. A crew scans it with a phone camera and the split-screen map opens — no app, no typing, no login.

1. Enter the box **IP** (and an optional label).
2. Click **Make QR card.** The card is saved to your **Downloads** folder.
3. Print it and stick it on the box.

---

## Troubleshooting

- **"This box is on kernel 5.4 … too old."** The box is still on the old firmware. Flash the 24.10 / kernel-6.6 image via GL's dashboard (above), then run setup again.
- **"Could not log in."** Check the IP, that it's the right box, and the admin password. If you just flashed or reset the box, its SSH identity changed — that's normal; the app auto-accepts it.
- **Map page not responding / feed silent after setup.** Re-run setup and watch the log for a package or file error. The box needs its one-time internet for the system packages.
- **No units on the map.** Units appear when a radio transmits a GPS position. The box's own Garmin dot ("you are here") shows as soon as the Garmin has a fix.
- **"needs TWO maps of the same area on the SSD."** Put a matching hybrid **and** street map for the same area on the SSD.
