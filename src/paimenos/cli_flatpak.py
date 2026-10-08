"""Shared launcher for installed native Flatpak apps."""
from paimenos.i18n import t
import os
import re
import sys

if len(sys.argv) < 2 or not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_-]+){2,}', sys.argv[1]):
    raise SystemExit(t('Ungültige Flatpak-App-ID.'))
options = ['--system', '--nofilesystem=home', '--nofilesystem=host',
           '--nofilesystem=~/.config/paimenos', '--nofilesystem=~/.local/state/paimenos',
           '--nofilesystem=~/.mozilla', '--env=GTK_USE_PORTAL=1', '--env=QT_USE_PORTAL=1']
os.execv('/usr/bin/flatpak', ['flatpak', 'run', *options, sys.argv[1] + '//stable', *sys.argv[2:]])
