"""Fehlende Komponenten derselben Debian-Version als eigene Quelle ergänzen."""
from pathlib import Path
import os
import re
import shutil
import sys
from urllib.parse import urlsplit

COMPONENTS = ('contrib', 'non-free', 'non-free-firmware')

def official(uri):
    return urlsplit(uri).hostname in ('deb.debian.org', 'security.debian.org', 'ftp.debian.org')

def entries(text, suffix, with_signing=False):
    if suffix == '.sources':
        for stanza in re.split(r'\n\s*\n', text):
            fields = {}; key = None
            for line in stanza.splitlines():
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                if line[:1].isspace() and key:
                    fields[key] += ' ' + line.strip()
                elif ':' in line:
                    key, value = line.split(':', 1); key = key.lower().strip()
                    fields[key] = value.strip()
            if fields.get('enabled', 'yes').lower() == 'no' or 'deb' not in fields.get('types', '').split():
                continue
            for uri in fields.get('uris', '').split():
                if official(uri):
                    for suite in fields.get('suites', '').split():
                        components = set(fields.get('components', '').split())
                        yield (suite, components, uri.rstrip('/'), fields.get('signed-by')) if with_signing else (suite, components)
    else:
        for line in text.splitlines():
            match = re.match(r'^\s*deb\s+(?:\[[^\]]*\]\s+)?(\S+)\s+(\S+)\s+([^#]+)', line)
            if match and official(match[1]):
                components = set(match[3].split())
                key = re.search(r'signed-by=([^\s\]]+)', line)
                signing = key[1] if key else None
                yield (match[2], components, match[1].rstrip('/'), signing) if with_signing else (match[2], components)

def configure(root, codename):
    if codename not in ('bookworm', 'trixie'):
        raise ValueError('Automatische Quellen-Ergänzung unterstützt Debian 12/13 (bookworm/trixie).')
    root = Path(root)
    keyring = root / 'usr/share/keyrings/debian-archive-keyring.gpg'
    if not keyring.is_file():
        raise ValueError('debian-archive-keyring fehlt.')
    folder = root / 'etc/apt/sources.list.d'; folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'paimenos-components.sources'
    suites = [codename, codename + '-updates', codename + '-security']
    existing = {suite: set() for suite in suites}
    # Eigene Quelle beim Berechnen ausschließen, damit Wiederholungen stabil bleiben.
    files = [root / 'etc/apt/sources.list'] + sorted(folder.glob('*.list')) + sorted(folder.glob('*.sources'))
    for file in files:
        if file == target or not file.is_file():
            continue
        for suite, components in entries(file.read_text(), file.suffix):
            aliases = {codename: ('stable' if codename == 'trixie' else 'oldstable')}
            for known in suites:
                alias = aliases[codename] + known[len(codename):]
                if suite in (known, alias):
                    existing[known].update(components)
    # Bei gleicher URI die bereits verwendete Signaturkonfiguration übernehmen.
    signing = {}
    for file in files:
        if file == target or not file.is_file():
            continue
        for suite, components, uri, key in entries(file.read_text(), file.suffix, with_signing=True):
            if uri in signing and signing[uri] != key:
                raise ValueError('Vorhandene Debian-Quellen haben widersprüchliche Signed-By-Angaben: ' + uri)
            signing[uri] = key
    blocks = []
    for suite in suites:
        missing = [c for c in COMPONENTS if c not in existing[suite]]
        if not missing:
            continue
        uri = 'https://deb.debian.org/debian-security' if suite.endswith('-security') else 'https://deb.debian.org/debian'
        key = signing.get(uri, '/usr/share/keyrings/debian-archive-keyring.gpg')
        signature = 'Signed-By: ' + key + '\n' if key else ''
        blocks.append('Types: deb\nURIs: ' + uri + '\nSuites: ' + suite + '\nComponents: ' + ' '.join(missing) + '\n' + signature)
    content = '# PaimenOS: zusätzliche Bereiche derselben Debian-Version.\n\n' + '\n'.join(blocks)
    if not blocks:
        content = '# PaimenOS: alle zusätzlichen Bereiche sind bereits eingerichtet.\n'
    if not target.exists() or target.read_text() != content:
        if target.exists():
            shutil.copy2(target, target.with_suffix('.sources.before-update'))
        temporary = target.with_suffix('.sources.new'); temporary.write_text(content)
        temporary.chmod(0o644); os.replace(temporary, target)
    print('Debian-Quellen geprüft: ' + codename + ', contrib / non-free / non-free-firmware.')

if __name__ == '__main__':
    configure('/', sys.argv[1])
