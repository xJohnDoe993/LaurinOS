"""Rough hardware profile shared by emulators, Luanti, web apps and the kids menu.

The profile is chosen by a parent (setup or paimenos-hardware-profile), stored
root-owned in /etc and only read here. detect() gives a suggestion, never a decision.
"""
from pathlib import Path
import os
import re
import sys

from paimenos.i18n import t

PROFILE_FILE = Path('/etc/paimenos/hardware-profile')
PROFILES = ('ultra-low', 'low', 'medium', 'high')
# Matches the previous fixed defaults (ThinkPad T450 class), so nothing changes without a choice.
DEFAULT = 'low'


def current():
    try:
        value = PROFILE_FILE.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        return DEFAULT
    return value if value in PROFILES else DEFAULT


def level(profile=None):
    return PROFILES.index(profile or current())


def _memory_gib(meminfo):
    match = re.search(r'^MemTotal:\s+(\d+)\s+kB', meminfo, re.M)
    return int(match.group(1)) / 1024 / 1024 if match else 0


def detect(cpuinfo=None, meminfo=None):
    """Suggest a profile from the CPU model name and RAM. Unknown hardware is 'low'."""
    if cpuinfo is None:
        cpuinfo = Path('/proc/cpuinfo').read_text(errors='replace')
    if meminfo is None:
        meminfo = Path('/proc/meminfo').read_text(errors='replace')
    model = next((line.split(':', 1)[1].strip() for line in cpuinfo.splitlines()
                  if line.lower().startswith('model name')), '')
    memory = _memory_gib(meminfo)
    name = model.lower()
    suggestion = DEFAULT
    intel = re.search(r'\bi([3579])-(\d{3,5})', name)
    ryzen = re.search(r'ryzen\s+([3579])\s+(?:pro\s+)?(\d)(\d)\d{2}', name)
    # Atom/Celeron/Pentium, Core 2, Core M, first-generation Core i (no model dash), old AMD APUs.
    if re.search(r'atom|celeron|pentium|core\(tm\)2|core 2|\bcore\(tm\) m[357]?\b|core\(tm\) i[357] cpu'
                 r'|athlon|\ba[4-9]-\d{4}|\be[12]?-\d{3}', name):
        suggestion = 'ultra-low'
    elif re.search(r'core\(tm\) ultra|core ultra|ryzen ai', name):
        suggestion = 'high'
    elif intel:
        tier, number = int(intel.group(1)), intel.group(2)
        # i7-920: 1st gen; i5-8250U: 8th; i5-10210U: 10th; mobile i5-1135G7/i5-1235U: 11th/12th.
        if len(number) == 3:
            generation = 1
        elif len(number) == 5 or number[0] == '1':
            generation = int(number[:2])
        else:
            generation = int(number[0])
        if generation < 5 or tier == 3:
            suggestion = 'ultra-low'
        elif generation <= 7:
            suggestion = 'low'
        elif generation <= 10:
            suggestion = 'medium'
        else:
            suggestion = 'high'
    elif ryzen:
        tier, series = int(ryzen.group(1)), int(ryzen.group(2))
        suggestion = 'low' if series <= 2 else 'medium' if series <= 4 else 'high'
        if tier == 3 and suggestion != 'low':
            suggestion = PROFILES[PROFILES.index(suggestion) - 1]
    # Little memory limits everything, regardless of the CPU.
    if memory and memory < 3.5:
        suggestion = 'ultra-low'
    elif memory and memory < 7.5 and level(suggestion) > level('low'):
        suggestion = 'low'
    return suggestion


def describe(profile):
    return {'ultra-low': t('Ultra-Low-End: sehr alte oder schwache Geräte (vor Intel 5. Gen. oder unter i5)'),
            'low': t('Low-End: z. B. Intel i5/i7 der 5.–7. Generation'),
            'medium': t('Medium: z. B. Intel i5/i7 der 8.–10. Generation, Ryzen 3000/4000'),
            'high': t('High-End: aktuelle Geräte, z. B. Intel ab 11. Generation, Ryzen ab 5000')}[profile]


# Luanti: only these keys are managed; everything else in minetest.conf is kept.
LUANTI = {
    'ultra-low': {'viewing_range': '50', 'fps_max': '30', 'smooth_lighting': 'false', 'enable_particles': 'false',
                  'enable_clouds': 'false', 'enable_3d_clouds': 'false', 'leaves_style': 'simple',
                  'opaque_water': 'true', 'enable_waving_water': 'false', 'enable_waving_leaves': 'false',
                  'enable_waving_plants': 'false', 'enable_dynamic_shadows': 'false', 'mip_map': 'false',
                  'anisotropic_filter': 'false', 'fsaa': '0', 'enable_shaders': 'false'},
    'low': {'viewing_range': '80', 'fps_max': '45', 'smooth_lighting': 'true', 'enable_particles': 'true',
            'enable_clouds': 'true', 'enable_3d_clouds': 'false', 'leaves_style': 'simple',
            'opaque_water': 'true', 'enable_waving_water': 'false', 'enable_waving_leaves': 'false',
            'enable_waving_plants': 'false', 'enable_dynamic_shadows': 'false', 'mip_map': 'false',
            'anisotropic_filter': 'false', 'fsaa': '0', 'enable_shaders': 'true'},
    'medium': {'viewing_range': '140', 'fps_max': '60', 'smooth_lighting': 'true', 'enable_particles': 'true',
               'enable_clouds': 'true', 'enable_3d_clouds': 'true', 'leaves_style': 'fancy',
               'opaque_water': 'false', 'enable_waving_water': 'false', 'enable_waving_leaves': 'true',
               'enable_waving_plants': 'true', 'enable_dynamic_shadows': 'false', 'mip_map': 'true',
               'anisotropic_filter': 'false', 'fsaa': '0', 'enable_shaders': 'true'},
    'high': {'viewing_range': '240', 'fps_max': '60', 'smooth_lighting': 'true', 'enable_particles': 'true',
             'enable_clouds': 'true', 'enable_3d_clouds': 'true', 'leaves_style': 'fancy',
             'opaque_water': 'false', 'enable_waving_water': 'true', 'enable_waving_leaves': 'true',
             'enable_waving_plants': 'true', 'enable_dynamic_shadows': 'true', 'mip_map': 'true',
             'anisotropic_filter': 'true', 'fsaa': '2', 'enable_shaders': 'true'},
}
# Debian (old and new name) and Flatpak locations; only folders that already exist are touched.
LUANTI_DIRS = ('.minetest', '.luanti', '.var/app/org.luanti.luanti/.minetest')


def merge_conf(text, values):
    lines, seen = [], set()
    for line in text.splitlines():
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in values:
            if key in seen:
                continue
            lines.append(key + ' = ' + values[key])
            seen.add(key)
        else:
            lines.append(line)
    lines += [key + ' = ' + value for key, value in values.items() if key not in seen]
    return '\n'.join(lines) + '\n'


def installed_luanti_dir(home):
    """Folder Luanti will use on first start, if it is in the kids menu."""
    import json
    try:
        items = json.loads((home / '.config/paimenos/apps.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    item = next((a for a in items if isinstance(a, dict) and a.get('id') == 'minetest'), None)
    if item is None:
        return None
    if item.get('flatpak_id') == 'org.luanti.luanti':
        return home / LUANTI_DIRS[2]
    return home / ('.luanti' if (home / '.luanti').is_dir() else '.minetest')


def apply_luanti(profile, home=None):
    home = Path(home or Path.home())
    changed = []
    first = installed_luanti_dir(home)
    if first is not None and not any(p.is_symlink() for p in (first, *first.parents) if home in p.parents):
        # Settings apply before the first start too; Luanti fills in everything else.
        first.mkdir(parents=True, exist_ok=True)
    for folder in LUANTI_DIRS:
        base = home / folder
        if not base.is_dir() or base.is_symlink():
            continue
        conf = base / 'minetest.conf'
        if conf.is_symlink():
            continue
        text = conf.read_text(encoding='utf-8') if conf.exists() else ''
        updated = merge_conf(text, LUANTI[profile])
        if updated != text:
            temporary = conf.with_name('.minetest.conf.paimenos')
            temporary.write_text(updated, encoding='utf-8')
            os.replace(temporary, conf)
            changed.append(conf)
    return changed


def luanti_running():
    import subprocess
    return subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', '(minetest|luanti|luanti\\.bin)'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def firefox_preferences(profile=None):
    """Extra web app preferences; Firefox defaults stay untouched from medium upwards."""
    values = {
        'ultra-low': {'dom.ipc.processCount': 1, 'general.smoothScroll': False, 'ui.prefersReducedMotion': 1,
                      'layout.frame_rate': 30, 'browser.sessionhistory.max_total_viewers': 0},
        'low': {'dom.ipc.processCount': 2, 'ui.prefersReducedMotion': 1,
                'browser.sessionhistory.max_total_viewers': 0},
        'medium': {'dom.ipc.processCount': 4},
        'high': {},
    }[profile or current()]
    return ''.join('user_pref(' + _js(key) + ', ' + _js(value) + ');\n' for key, value in values.items())


def _js(value):
    import json
    return json.dumps(value)


def main(argv):
    if argv == ['--detect']:
        print(detect())
    elif argv == ['--current']:
        print(current())
    elif argv[:1] == ['--describe'] and len(argv) == 2 and argv[1] in PROFILES:
        print(describe(argv[1]))
    elif argv == ['--apply']:
        # Runs as the kids user; emulators and web apps read the profile at every start.
        if luanti_running():
            # Luanti writes minetest.conf on exit and would undo the change.
            print(t('Luanti läuft gerade. Bitte schließen und den Befehl erneut ausführen.'), file=sys.stderr)
            return
        for path in apply_luanti(current()):
            print(t('Luanti-Einstellungen angepasst: {value0}', value0=path))
    else:
        raise SystemExit('hardware_profile --detect|--current|--describe PROFILE|--apply')


if __name__ == '__main__':
    main(sys.argv[1:])
