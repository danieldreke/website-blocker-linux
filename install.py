#!/usr/bin/env python3
import os
import subprocess
import stat

INSTALL_DIR = os.path.expanduser("~/.local/share/website-blocker")
APPS_DIR = os.path.expanduser("~/.local/share/applications")
DESKTOP_FILE = os.path.join(APPS_DIR, "website-blocker.desktop")
LAUNCH_SH = os.path.join(INSTALL_DIR, "launch.sh")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DESKTOP_ENTRY = """\
[Desktop Entry]
Name=Website Blocker
Comment=Block websites by editing /etc/hosts
Exec={launch}
Icon=network-error
Terminal=false
Type=Application
Categories=Network;Utility;
"""

LAUNCH_SCRIPT = """\
#!/bin/bash
python3 {app}
"""

def main():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    os.makedirs(APPS_DIR, exist_ok=True)

    src = os.path.join(SCRIPT_DIR, "website_blocker.py")
    dst = os.path.join(INSTALL_DIR, "website_blocker.py")
    if os.path.lexists(dst):
        os.remove(dst)
    os.symlink(src, dst)
    print(f"Symlinked website_blocker.py -> {INSTALL_DIR}")

    app_path = os.path.join(INSTALL_DIR, "website_blocker.py")
    with open(LAUNCH_SH, "w") as f:
        f.write(LAUNCH_SCRIPT.format(app=app_path))
    os.chmod(LAUNCH_SH, os.stat(LAUNCH_SH).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Created {LAUNCH_SH}")

    with open(DESKTOP_FILE, "w") as f:
        f.write(DESKTOP_ENTRY.format(launch=LAUNCH_SH))
    print(f"Created {DESKTOP_FILE}")

    subprocess.run(["update-desktop-database", APPS_DIR], check=False)
    print("Done. Website Blocker installed.")

if __name__ == "__main__":
    main()
