#!/usr/bin/python3
import fcntl
import os
import subprocess
from pathlib import Path

MANAGED_FILE = Path('/var/lib/paimenos/flatpak-apps.list')
ALLOWED = {'org.luanti.luanti', 'org.kde.gcompris', 'net.supertuxkart.SuperTuxKart',
           'org.gimp.GIMP', 'org.libreoffice.LibreOffice'}


def main():
    if not MANAGED_FILE.is_file():
        return 0
    with open('/run/paimenos-app-update.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        apps = sorted(set(MANAGED_FILE.read_text().splitlines()) & ALLOWED)
        failed = False
        for app in apps:
            ref = app + '//stable'
            # Manuell entfernte Apps nicht erneut installieren.
            if subprocess.run(['/usr/bin/flatpak', 'info', '--system', ref],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                continue
            result = subprocess.run(['/usr/bin/flatpak', 'update', '--system', '--noninteractive', '-y', ref])
            failed = failed or result.returncode != 0
        return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
