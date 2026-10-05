#!/usr/bin/python3
"""Generate component inventory. Run after adding/removing repository files."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
groups = {
    'shared': ['__init__', 'paths', 'state', 'diagnostics', 'images', 'categories', 'fullscreen', 'webapp', 'osd_state'],
    'desktop': ['menu', 'parent_ui', 'status_overlay', 'close_overlay', 'lockscreen', 'timer', 'media'],
    'controller': ['controller', 'controller_profiles', 'input_devices'],
    'network': ['wifi', 'bluetooth', 'wifi_ui', 'bluetooth_ui', 'network_status'],
    'emulators': ['emulators', 'emulator_install', 'emulator_catalog', 'emulator_service'],
    'backend': ['parent', 'parent_web'],
    'cli': ['cli_osd_notify', 'cli_update_apps', 'cli_flatpak', 'cli_emulator', 'cli_emulator_check'],
    'tools': [], 'services': [],
}
components = {key: {'files': ['src/laurinos/' + name + '.py' for name in names]} for key, names in groups.items()}
components['shared']['files'] += ['run.py', 'assets/webapp.css']
components['backend']['files'] += sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'assets/parent-web').glob('*.html'))
components['emulators']['files'] += ['data/emulator-catalog.json']
components['cli']['files'] += sorted(str(p.relative_to(ROOT)) for folder in ('bin', 'sbin') for p in (ROOT / folder).glob('*') if p.is_file())
components['tools']['files'] += sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tools').glob('*.py') if p.name not in {'check.py', 'build-manifest.py', 'build-release.py'})
components['services']['files'] += sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'systemd').rglob('*') if p.is_file())
manifest = {'schema': 1, 'runtime_api': 1, 'version': (ROOT / 'VERSION').read_text().strip(), 'components': components}
(ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('manifest.json aktualisiert.')
