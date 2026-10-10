"""Gemeinsame, feste Emulator-Auswahl für Setup, Installationsdienst und Uploads."""
from paimenos.i18n import t
import glob
import json
from paimenos.paths import DATA_DIR

_catalog = json.loads((DATA_DIR / "emulator-catalog.json").read_text(encoding="utf-8"))
import os
from pathlib import Path
import shutil

SHARED_SYSTEM = Path('/usr/local/share/paimenos/retroarch-system')
CATALOG = _catalog["systems"]
RECOMMENDED = _catalog["recommended"]


def selection(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError(t('Ungültige Emulator-Auswahl.'))
    value = value.strip().lower()
    if value in ('none', 'keine', '0'):
        return []
    if value in ('all', 'alle'):
        return list(CATALOG)
    if value in ('recommended', 'empfohlen'):
        return list(RECOMMENDED)
    keys = value.replace(',', ' ').split()
    if not keys or any(key not in CATALOG for key in keys):
        raise ValueError(t('Bitte gültige Konsolen auswählen: ') + ', '.join(CATALOG))
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


# Debian packages and manually installed cores may live in different trees.
CORE_INFO_DIRS = (Path('/usr/share/libretro/info'), Path('/usr/share/libretro'),
                  Path('/usr/local/share/libretro/info'))


def core_info_path(core):
    """Find metadata for the actual loaded core, not RetroArch's user defaults."""
    core = Path(core)
    name = core.with_suffix('.info').name
    for directory in (*CORE_INFO_DIRS, core.parent, DATA_DIR / 'libretro-info'):
        if (directory / name).is_file():
            return directory
    return None


def psp_assets_ready():
    assets = SHARED_SYSTEM / 'PPSSPP'
    return (assets / 'ppge_atlas.zim').is_file() and (assets / 'lang').is_dir() and (assets / 'flash0/font').is_dir()


def dolphin_assets_ready():
    folder = SHARED_SYSTEM / 'dolphin-emu' / 'Sys'
    return ((folder / 'GC/dsp_coef.bin').is_file() and (folder / 'GC/dsp_rom.bin').is_file()
            and any((folder / 'GameSettings').glob('*.ini')))


def assets_ready(system):
    if system == 'psp':
        return psp_assets_ready()
    if system == 'dolphin':
        return dolphin_assets_ready()
    return True


def status():
    frontend = bool(shutil.which('retroarch'))
    result = []
    for key, item in CATALOG.items():
        core = bool(core_path(key))
        assets = assets_ready(key)
        ready = frontend and core and assets
        reason = t('Installiert') if ready else (t('Zusatzdateien fehlen') if frontend and core and not assets else t('Noch nicht installiert'))
        hint = t('Niedrige Auflösung voreingestellt; Leistung hängt vom Spiel ab.') if key in ('n64', 'psp', 'dolphin') else t('Für ältere Notebooks geeignet.')
        result.append(dict(id=key, name=item['name'], ready=ready, reason=reason, hint=hint,
                           formats=' / '.join(ext[1:].upper() for ext in item['extensions'])))
    return result

