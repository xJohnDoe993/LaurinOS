#!/usr/bin/python3 -I
"""Device-local PIN initialization; root-owned and callable once without arguments."""
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = Path('/var/lib/paimenos/iso')
PENDING = BASE / 'pending'
WRITE = '''
import json, os, tempfile, sys
from pathlib import Path
path = Path('/home/kids/.config/paimenos/settings.json')
data = json.load(sys.stdin)
fd, name = tempfile.mkstemp(dir=path.parent, prefix='.iso-settings-')
with os.fdopen(fd, 'w') as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
os.replace(name, path)
'''


def main():
    if os.geteuid() != 0:
        raise SystemExit('Bitte über sudo starten.')
    with open('/run/paimenos-iso-setup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if sys.argv[1:] == ['--reset']:
            if os.environ.get('SUDO_USER'):
                raise SystemExit('Reset ist nur für den ISO-Bau/Installer vorgesehen.')
            subprocess.run(['runuser', '-u', 'kids', '--', '/usr/bin/python3', '-I', '-c',
                            "from pathlib import Path; Path('/home/kids/.config/paimenos/settings.json').unlink(missing_ok=True)"], check=True)
            BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Parent directories must be traversable for the session gate.
            BASE.chmod(0o755)
            PENDING.touch(mode=0o644)
            return
        if sys.argv[1:]:
            raise SystemExit('Keine Argumente erlaubt.')
        if not PENDING.exists():
            return
        print('Willkommen bei PaimenOS!\nNeue Eltern-PIN für dieses Gerät festlegen.')
        while True:
            pin = getpass.getpass('Eltern-PIN (4 bis 12 Ziffern): ')
            repeat = getpass.getpass('PIN wiederholen: ')
            if re.fullmatch(r'[0-9]{4,12}', pin) and pin == repeat:
                break
            print('Bitte 4 bis 12 Ziffern eingeben; beide Eingaben müssen übereinstimmen.')
        settings = json.loads((BASE / 'settings.json').read_text())
        settings['pin'] = pin
        # Never write as root into a child-writable directory.
        subprocess.run(['runuser', '-u', 'kids', '--', '/usr/bin/python3', '-I', '-c', WRITE],
                       input=json.dumps(settings), text=True, check=True)
        PENDING.unlink()
        subprocess.run(['systemctl', 'start', 'paimenos-parent-web.service', 'paimenos-updates.service'], check=True)
        print('Einrichtung abgeschlossen. PaimenOS wird gestartet.')


if __name__ == '__main__':
    main()
