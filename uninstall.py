#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import tempfile

INSTALL_DIR = os.path.expanduser("~/.local/share/website-blocker")
DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/website-blocker.desktop")
APPS_DIR = os.path.expanduser("~/.local/share/applications")
HOSTS_FILEPATH = "/etc/hosts"
MARKER_START = "# --- Website Blocker START ---"
MARKER_END = "# --- Website Blocker END ---"

def clear_hosts():
    if not os.path.exists(HOSTS_FILEPATH):
        return
    with open(HOSTS_FILEPATH) as f:
        content = f.read()
    if MARKER_START not in content:
        return
    new_content = re.sub(
        rf"\n?{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        "", content, flags=re.DOTALL
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".hosts", delete=False) as tmp:
        tmp.write(new_content)
        tmp_path = tmp.name
    result = subprocess.run(["pkexec", "cp", tmp_path, HOSTS_FILEPATH])
    os.unlink(tmp_path)
    if result.returncode == 0:
        print(f"Removed blocked sites from {HOSTS_FILEPATH}")
    else:
        print(f"Failed to update {HOSTS_FILEPATH} — blocked sites were not removed")

def main():
    clear_hosts()

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

if __name__ == "__main__":
    main()
