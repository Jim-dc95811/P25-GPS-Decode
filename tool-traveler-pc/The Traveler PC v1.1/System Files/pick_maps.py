#!/usr/bin/env python3
"""
Maps-folder picker for The Traveler PC.

The Traveler PC is not locked to the bundled Maps folder - the user can point it
at ANY folder on this PC that holds their offline maps (.tpkx / .mbtiles). The
chosen folder is remembered in maps_folder.txt beside this script, which the map
server (units_kml.py) reads each time it scans for maps.

  (no args)   if maps_folder.txt already holds a valid folder, print it and exit
              (silent); otherwise pop the folder dialog, save the choice, print it.
  --dialog    always pop the folder dialog (used by the in-app "Change maps
              folder..." button), save the choice, and print it.

Prints the resulting folder path on the last line of stdout. Read-only to the GPS;
this only chooses where the maps live.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "maps_folder.txt")


def read_cfg():
    try:
        p = open(CFG, encoding="utf-8").read().strip()
        return p if p and os.path.isdir(p) else ""
    except OSError:
        return ""


def save_cfg(path):
    try:
        with open(CFG, "w", encoding="utf-8") as f:
            f.write(path)
    except OSError:
        pass


def pick(initial):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title="Choose the folder that holds your maps (.tpkx / .mbtiles)",
            initialdir=initial or os.path.expanduser("~"))
        root.destroy()
        return folder or ""
    except Exception:
        return ""


def main():
    force = "--dialog" in sys.argv[1:]
    current = read_cfg()
    if current and not force:
        print(current)
        return
    chosen = pick(current)
    if chosen and os.path.isdir(chosen):
        save_cfg(chosen)
        print(chosen)
    else:
        print(current)   # dialog cancelled - keep whatever was there


if __name__ == "__main__":
    main()
