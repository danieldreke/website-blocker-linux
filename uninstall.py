#!/usr/bin/env python3
import os
import shutil
import subprocess

INSTALL_DIR = os.path.expanduser("~/.local/share/website-blocker")
DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/website-blocker.desktop")
APPS_DIR = os.path.expanduser("~/.local/share/applications")

def main():
    removed = False

    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR)
        print(f"Removed {INSTALL_DIR}")
        removed = True

    if os.path.isfile(DESKTOP_FILE):
        os.remove(DESKTOP_FILE)
        print(f"Removed {DESKTOP_FILE}")
        removed = True

    if removed:
        subprocess.run(["update-desktop-database", APPS_DIR], check=False)
        print("Done. Website Blocker uninstalled.")
    else:
        print("Nothing to uninstall.")

if __name__ == "__main__":
    main()
