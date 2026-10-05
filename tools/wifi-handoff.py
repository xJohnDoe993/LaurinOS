"""Eine explizite WLAN-Konfiguration aus ifupdown an NetworkManager übergeben."""
import fnmatch
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

CONFIG_ROOT = Path('/etc/network')
HEADERS = {'iface', 'mapping', 'auto', 'rename', 'source', 'source-directory', 'no-auto-down', 'no-scripts'}

def logical_lines(text):
    result = []
    raw, logical = '', ''
    for line in text.splitlines(keepends=True):
        raw += line
        body = line.rstrip('\r\n')
        if body.endswith('\\'):
            logical += body[:-1] + ' '
            continue
        logical += body
        result.append((raw, logical.split()))
        raw, logical = '', ''
    if raw:
        raise ValueError('Unvollständige Zeilenfortsetzung in ifupdown-Konfiguration.')
    return result

def prepare(device, backup):
    root = CONFIG_ROOT.resolve()
    queue, visited, files = [root/'interfaces'], set(), []
    while queue:
        path = queue.pop(0)
        if not path.exists() and not path.is_symlink():
            continue
        # Nur reguläre Konfigurationsdateien unter /etc/network bearbeiten.
        if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
            raise ValueError('Nicht unterstützte ifupdown-Quelldatei: ' + str(path))
        path = path.resolve()
        if path in visited:
            continue
        visited.add(path)
        original = path.read_bytes()
        records = logical_lines(original.decode('utf-8', 'surrogateescape'))
        result, in_target = [], False
        for raw, tokens in records:
            if not tokens or tokens[0].startswith('#'):
                result.append(raw)
                continue
            word = tokens[0]
            header = word in HEADERS or word.startswith('allow-')
            if header:
                in_target = word == 'iface' and len(tokens) > 1 and tokens[1] == device
            if word in ('source', 'source-directory'):
                for spec in tokens[1:]:
                    if any(c in spec for c in ('$','`','"',"'")):
                        raise ValueError('Dynamische ifupdown-Quelle benötigt manuelle Prüfung.')
                    pattern = str(path.parent/spec) if not spec.startswith('/') else spec
                    for match in sorted(glob.glob(pattern)):
                        included = Path(match)
                        if word == 'source':
                            queue.append(included)
                        else:
                            if included.is_symlink() or not included.is_dir() or root not in included.resolve().parents:
                                raise ValueError('Nicht unterstütztes ifupdown-Quellverzeichnis.')
                            queue.extend(p for p in sorted(included.iterdir()) if re.fullmatch(r'[a-zA-Z0-9_-]+', p.name) and (p.is_file() or p.is_symlink()))
            if word in ('mapping', 'iface') and len(tokens) > 1 and tokens[1] != device:
                if word == 'iface' and 'inherits' in tokens and device in tokens[tokens.index('inherits')+1:]:
                    raise ValueError('Eine andere Schnittstelle erbt WLAN-Optionen; manuelle Prüfung erforderlich.')
                if any(fnmatch.fnmatchcase(device, pattern) for pattern in tokens[1:2]):
                    raise ValueError('ifupdown-Muster für diesen Adapter benötigt manuelle Prüfung.')
            if word == 'mapping' and any(fnmatch.fnmatchcase(device, p) for p in tokens[1:]):
                raise ValueError('ifupdown-Mapping für diesen Adapter benötigt manuelle Prüfung.')
            if word == 'rename' and any(device in p.split('=') for p in tokens[1:]):
                raise ValueError('ifupdown-Umbenennung für diesen Adapter benötigt manuelle Prüfung.')
            if word == 'auto' or word.startswith('allow-'):
                names = tokens[1:]
                if any(n.split('=',1)[0] == device and n != device for n in names):
                    raise ValueError('ifupdown-Autostart mit logischem WLAN-Namen benötigt manuelle Prüfung.')
                if any(n.startswith('/') and n.endswith('/') for n in names):
                    raise ValueError('ifupdown-Autostart mit regulärem Ausdruck benötigt manuelle Prüfung.')
                if any(n != device and fnmatch.fnmatchcase(device, n) for n in names):
                    raise ValueError('ifupdown-Autostart-Muster benötigt manuelle Prüfung.')
                if device in names:
                    others = [n for n in names if n != device]
                    # Andere Adapter auf derselben Zeile erhalten.
                    if others:
                        prefix = raw[:len(raw)-len(raw.lstrip())]
                        result.append(prefix + ' '.join([word]+others) + '\n')
                    else:
                        result.extend('# LaurinOS / NetworkManager: '+line for line in raw.splitlines(keepends=True))
                    continue
            if in_target:
                result.extend('# LaurinOS / NetworkManager: '+line for line in raw.splitlines(keepends=True))
            else:
                result.append(raw)
        replacement = ''.join(result).encode('utf-8', 'surrogateescape')
        if replacement != original:
            info = path.stat()
            files.append((path, original, replacement, info))
    # Erst nach vollständiger Prüfung aller Quelldateien einen Plan schreiben.
    manifest = []
    for index, (path, original, replacement, info) in enumerate(files):
        for suffix, content in (('old',original),('new',replacement)):
            saved = backup/f'{index}.{suffix}'
            saved.write_bytes(content); saved.chmod(0o600)
        manifest.append(dict(path=str(path), index=index, old=hashlib.sha256(original).hexdigest(),
                             new=hashlib.sha256(replacement).hexdigest(), mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid))
    (backup/'manifest.json').write_text(json.dumps(manifest))
    (backup/'manifest.json').chmod(0o600)
    print(f'Geprüft: {len(manifest)} ifupdown-Datei(en) mit Einträgen für {device}.')

def write_files(backup, restore=False):
    manifest = json.loads((backup/'manifest.json').read_text())
    for item in manifest:
        path = Path(item['path'])
        if path.is_symlink() or not path.is_file():
            raise ValueError('ifupdown-Zieldatei hat sich geändert.')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        target, expected = ('old','new') if restore else ('new','old')
        if digest == item[target]:
            continue
        if digest != item[expected]:
            raise ValueError('ifupdown-Datei wurde zwischenzeitlich geändert: '+str(path))
        data = (backup/f'{item["index"]}.{target}').read_bytes()
        fd, temporary = tempfile.mkstemp(prefix='.laurinos-ifupdown-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data)
                os.fchmod(stream.fileno(),item['mode'])
                os.fchown(stream.fileno(),item['uid'],item['gid'])
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

if __name__ == '__main__':
    try:
        action, device, directory = sys.argv[1:]
        backup = Path(directory)
        if action == 'prepare': prepare(device,backup)
        elif action in ('apply','restore'): write_files(backup,action=='restore')
        else: raise ValueError('Unbekannte Übergabeaktion.')
    except (ValueError,OSError) as exc:
        # Keine Konfigurationsinhalte / WLAN-Passwörter ausgeben.
        print('FEHLER: '+str(exc),file=sys.stderr)
        sys.exit(1)
