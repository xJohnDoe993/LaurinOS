"""Gemeinsame, feste Emulator-Auswahl für Setup, Installationsdienst und Uploads."""
import glob
import json
from laurinos.paths import DATA_DIR

_catalog = json.loads((DATA_DIR / "emulator-catalog.json").read_text(encoding="utf-8"))
import os
from pathlib import Path
import shutil

SHARED_SYSTEM = Path('/usr/local/share/laurinos/retroarch-system')
CATALOG = _catalog["systems"]
RECOMMENDED = _catalog["recommended"]


def selection(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError('Ungültige Emulator-Auswahl.')
    value = value.strip().lower()
    if value in ('none', 'keine', '0'):
        return []
    if value in ('all', 'alle'):
        return list(CATALOG)
    if value in ('recommended', 'empfohlen'):
        return list(RECOMMENDED)
    keys = value.replace(',', ' ').split()
    if not keys or any(key not in CATALOG for key in keys):
        raise ValueError('Bitte gültige Konsolen auswählen: ' + ', '.join(CATALOG))
    return list(dict.fromkeys(keys))


def core_path(system):
    names = [CATALOG[system]['core'] + '_libretro.so']
    if system == 'snes':
        names.append('bsnes_mercury_performance_libretro.so')
    for name in names:
        paths = glob.glob('/usr/lib/*/libretro/' + name) + ['/usr/lib/libretro/' + name, '/usr/local/lib/libretro/' + name]
        for path in paths:
            if os.path.isfile(path):
                return path
    return None


def psp_assets_ready():
    assets = SHARED_SYSTEM / 'PPSSPP'
    return (assets / 'ppge_atlas.zim').is_file() and (assets / 'lang').is_dir() and (assets / 'flash0/font').is_dir()


def status():
    frontend = bool(shutil.which('retroarch'))
    result = []
    for key, item in CATALOG.items():
        core = bool(core_path(key))
        assets = key != 'psp' or psp_assets_ready()
        ready = frontend and core and assets
        reason = 'Installiert' if ready else ('PSP-Zusatzdateien fehlen' if frontend and core and not assets else 'Noch nicht installiert')
        hint = 'Niedrige Auflösung voreingestellt; Leistung hängt vom Spiel ab.' if key in ('n64', 'psp') else 'Für ältere Notebooks geeignet.'
        result.append(dict(id=key, name=item['name'], ready=ready, reason=reason, hint=hint,
                           formats=' / '.join(ext[1:].upper() for ext in item['extensions'])))
    return result

