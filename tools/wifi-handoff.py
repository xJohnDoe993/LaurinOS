"""Eine explizite WLAN-Konfiguration aus ifupdown an NetworkManager übergeben."""
import fnmatch
import glob
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

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
                        result.extend('# PaimenOS / NetworkManager: '+line for line in raw.splitlines(keepends=True))
                    continue
            if in_target:
                result.extend('# PaimenOS / NetworkManager: '+line for line in raw.splitlines(keepends=True))
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
        fd, temporary = tempfile.mkstemp(prefix='.paimenos-ifupdown-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data)
                os.fchmod(stream.fileno(),item['mode'])
                os.fchown(stream.fileno(),item['uid'],item['gid'])
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

def unquote(value):
    """Ordinary ifupdown strings, without evaluating shell expressions."""
    value = value.strip()
    if value.startswith('"'):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError('Nicht unterstützte WLAN-Zeichenfolge; Verbindung bleibt unverändert.') from None
    if not isinstance(value, str) or any(c in value for c in ('\x00', '\n', '\r')):
        raise ValueError('Ungültige WLAN-Zeichenfolge.')
    return value

def keyfile_string(value):
    # GLib key files need escapes for backslashes and leading/trailing spaces.
    return value.replace('\\', '\\\\').replace(' ', '\\s').replace('\t', '\\t')

def wpa_config(path):
    """Import a single ordinary WPA-PSK/open network; never guess a network."""
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('WPA-Konfiguration muss eine reguläre absolute Datei sein.')
    networks, current = [], None
    allowed = {'ssid', 'psk', 'key_mgmt', 'scan_ssid', 'priority', 'disabled'}
    for line in path.read_text().splitlines():
        # Strip comments outside quoted values, preserving # in passwords.
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if re.fullmatch(r'network\s*=\s*\{\s*(?:#.*)?', line):
            if current is not None: raise ValueError('Verschachtelte WPA-Konfiguration.')
            current = {}
        elif re.fullmatch(r'}\s*(?:#.*)?', line):
            if current is None: raise ValueError('Ungültige WPA-Konfiguration.')
            networks.append(current); current = None
        elif current is not None:
            match = re.fullmatch(r'([a-z_]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^#]*?)\s*(?:#.*)?', line)
            if not match or match[1] not in allowed or match[1] in current:
                raise ValueError('Erweiterte WPA-Konfiguration benötigt manuelle Übernahme.')
            current[match[1]] = match[2].strip()
        else:
            match = re.fullmatch(r'(ctrl_interface|ctrl_interface_group|update_config|country|ap_scan)\s*=\s*(.*?)\s*(?:#.*)?', line)
            if not match or (match[1] == 'ap_scan' and match[2] != '1'):
                raise ValueError('Erweiterte globale WPA-Konfiguration benötigt manuelle Übernahme.')
    if current is not None or len(networks) != 1:
        raise ValueError('WPA-Konfiguration mit mehreren/ungültigen Netzen benötigt manuelle Übernahme.')
    network = networks[0]
    if network.get('disabled', '0') != '0':
        raise ValueError('Deaktiviertes WLAN wird nicht automatisch übernommen.')
    ssid = network.get('ssid', '')
    if not ssid.startswith('"'):
        try: ssid = json.dumps(bytes.fromhex(ssid).decode('utf-8'))
        except (ValueError, UnicodeError): raise ValueError('Nicht unterstützte hexadezimale SSID.') from None
    return {'wpa-ssid': ssid, 'wpa-psk': network.get('psk', ''),
            'wpa-key-mgmt': network.get('key_mgmt', 'WPA-PSK'),
            'wpa-scan-ssid': network.get('scan_ssid', '0')}

def profile(device, backup):
    """Prepare a private NM keyfile before any service/interface is stopped."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}', device):
        raise ValueError('Ungültiger Adaptername.')
    manifest = json.loads((backup/'manifest.json').read_text())
    stanzas, current = [], None
    for item in manifest:
        for raw, tokens in logical_lines((backup/f'{item["index"]}.old').read_text()):
            if not tokens or tokens[0].startswith('#'): continue
            word = tokens[0]
            if word in HEADERS or word.startswith('allow-'):
                current = None
                if word == 'iface' and len(tokens) > 1 and tokens[1] == device:
                    if len(tokens) != 4: raise ValueError('Erweiterte iface-Konfiguration benötigt manuelle Übernahme.')
                    current = {'family': tokens[2], 'method': tokens[3], 'options': {}}
                    stanzas.append(current)
            elif current is not None:
                parts = re.sub(r'\\\r?\n', ' ', raw).strip().split(None, 1)
                if len(parts) != 2 or word in current['options']:
                    raise ValueError('Mehrdeutige WLAN-Option benötigt manuelle Übernahme.')
                current['options'][word] = parts[1]
    ipv4 = [s for s in stanzas if s['family'] == 'inet']
    if len(ipv4) != 1 or ipv4[0]['method'] != 'dhcp':
        raise ValueError('Automatische WLAN-Übernahme unterstützt eine inet-DHCP-Konfiguration; Verbindung bleibt unverändert.')
    if any(s is not ipv4[0] and (s['family'] != 'inet6' or s['method'] != 'auto' or s['options']) for s in stanzas):
        raise ValueError('Erweiterte IPv6-Konfiguration benötigt manuelle Übernahme.')
    options = ipv4[0]['options'].copy()
    allowed = {'wpa-ssid', 'wpa-psk', 'wpa-conf', 'wpa-key-mgmt', 'wpa-scan-ssid', 'dns-nameservers', 'dns-search'}
    if set(options) - allowed:
        raise ValueError('Erweiterte ifupdown-WLAN-Optionen benötigen manuelle Übernahme; Verbindung bleibt unverändert.')
    if 'wpa-conf' in options:
        if any(k.startswith('wpa-') and k != 'wpa-conf' for k in options):
            raise ValueError('Mehrdeutige WPA-Konfiguration.')
        options.update(wpa_config(Path(unquote(options.pop('wpa-conf')))))
    ssid = unquote(options.get('wpa-ssid', ''))
    if not 1 <= len(ssid.encode('utf-8')) <= 32:
        raise ValueError('WLAN-Name fehlt oder ist ungültig; Verbindung bleibt unverändert.')
    psk = unquote(options.get('wpa-psk', ''))
    key_mgmt = options.get('wpa-key-mgmt', 'WPA-PSK').strip()
    if key_mgmt not in ('WPA-PSK', 'NONE') or (key_mgmt == 'NONE' and psk):
        raise ValueError('WLAN-Sicherheit benötigt manuelle Übernahme.')
    if key_mgmt == 'WPA-PSK' and not (8 <= len(psk.encode('utf-8')) <= 63 or re.fullmatch(r'[0-9a-fA-F]{64}', psk)):
        raise ValueError('WLAN-Schlüssel fehlt oder ist ungültig; Verbindung bleibt unverändert.')
    hidden = options.get('wpa-scan-ssid', '0').strip()
    if hidden not in ('0', '1'): raise ValueError('Ungültige WLAN-Suchoption.')
    identifier = str(uuid.uuid4())
    content = f'[connection]\nid=PaimenOS Debian WLAN {device}\nuuid={identifier}\ntype=wifi\ninterface-name={device}\nautoconnect=false\n\n[wifi]\nmode=infrastructure\n'
    # Decimal byte lists preserve arbitrary SSID punctuation without ambiguity.
    content += 'ssid=' + ''.join(f'{b};' for b in ssid.encode('utf-8')) + '\n'
    content += f'hidden={"true" if hidden == "1" else "false"}\n'
    if key_mgmt == 'WPA-PSK':
        content += '\n[wifi-security]\nkey-mgmt=wpa-psk\npsk-flags=0\npsk=' + keyfile_string(psk) + '\n'
    content += '\n[ipv4]\nmethod=auto\nmay-fail=false\n'
    if 'dns-nameservers' in options:
        try: servers = [str(ipaddress.ip_address(s)) for s in options['dns-nameservers'].split()]
        except ValueError: raise ValueError('Ungültige DNS-Adresse in ifupdown-Konfiguration.') from None
        if any(':' in s for s in servers): raise ValueError('IPv6-DNS benötigt manuelle Übernahme.')
        content += 'dns=' + ';'.join(servers) + ';\n'
    if 'dns-search' in options:
        domains = options['dns-search'].split()
        if any(not re.fullmatch(r'[a-zA-Z0-9_.~-]+', s) for s in domains):
            raise ValueError('Ungültige DNS-Suchdomain.')
        content += 'dns-search=' + ';'.join(domains) + ';\n'
    content += '\n[ipv6]\nmethod=auto\n'
    for name, data in (('profile.nmconnection', content), ('profile.uuid', identifier)):
        # Permissions apply from creation, including when the helper is run manually.
        fd = os.open(backup/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream: stream.write(data)
    print('WLAN-Profil zur Wiederverbindung vorbereitet (nur root lesbar).')

if __name__ == '__main__':
    try:
        action, device, directory = sys.argv[1:]
        backup = Path(directory)
        if action == 'prepare': prepare(device,backup)
        elif action == 'profile': profile(device,backup)
        elif action in ('apply','restore'): write_files(backup,action=='restore')
        else: raise ValueError('Unbekannte Übergabeaktion.')
    except (ValueError,OSError) as exc:
        # Keine Konfigurationsinhalte / WLAN-Passwörter ausgeben.
        print('FEHLER: '+str(exc),file=sys.stderr)
        sys.exit(1)
