#!/usr/bin/python3
"""Disable installation-media sources and fill missing Debian online components."""
from pathlib import Path as _Path
import sys as _sys
_release = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_release / ('app' if (_release / 'app').is_dir() else 'src')))
from paimenos.i18n import t
import importlib.util
import os
from pathlib import Path
import re
import shutil

spec = importlib.util.spec_from_file_location('components', Path(__file__).resolve().parents[1] / 'tools/configure-debian-components.py')
components = importlib.util.module_from_spec(spec)
spec.loader.exec_module(components)


def configure(root=Path('/')):
    root = Path(root)
    folder = root / 'etc/apt/sources.list.d'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'paimenos-iso.sources'
    files = [root / 'etc/apt/sources.list', *sorted(folder.glob('*.list')), *sorted(folder.glob('*.sources'))]
    for path in files:
        if not path.is_file() or path == target:
            continue
        old = path.read_text()
        if path.suffix == '.sources':
            stanzas = re.split(r'\n[ \t]*\n', old)
            for index, stanza in enumerate(stanzas):
                if re.search(r'^URIs:\s*cdrom:', stanza, re.M | re.I):
                    stanza = re.sub(r'^Enabled:.*\n?', '', stanza, flags=re.M | re.I)
                    stanzas[index] = stanza.rstrip() + '\nEnabled: no\n'
            new = '\n\n'.join(stanzas)
        else:
            new = re.sub(r'^(\s*deb(?:-src)?\s+(?:\[[^\]]*\]\s+)?cdrom:.*)$', r'# PaimenOS: Installationsmedium deaktiviert\n# \1', old, flags=re.M)
        if old != new:
            backup = path.with_name(path.name + '.before-paimenos-iso')
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(new)
    suites = ('trixie', 'trixie-updates', 'trixie-security')
    existing = {suite: set() for suite in suites}
    signing = {}
    for path in files:
        if not path.is_file() or path == target:
            continue
        for suite, areas, uri, key in components.entries(path.read_text(), path.suffix, with_signing=True):
            if suite in existing:
                existing[suite].update(areas)
            if uri in signing and signing[uri] != key:
                raise ValueError(t('Widersprüchliche Signed-By-Angaben: ') + uri)
            signing[uri] = key
    blocks = []
    for suite in suites:
        missing = [area for area in ('main', 'contrib', 'non-free', 'non-free-firmware') if area not in existing[suite]]
        if not missing:
            continue
        uri = 'https://deb.debian.org/' + ('debian-security' if suite.endswith('-security') else 'debian')
        key = signing.get(uri, '/usr/share/keyrings/debian-archive-keyring.gpg')
        block = f'Types: deb\nURIs: {uri}\nSuites: {suite}\nComponents: {" ".join(missing)}\n'
        if key:
            block += 'Signed-By: ' + key + '\n'
        blocks.append(block)
    target.write_text('# PaimenOS ISO: Debian-Onlinequellen\n\n' + '\n'.join(blocks))
    target.chmod(0o644)


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit(t('Bitte mit sudo starten.'))
    configure()
