"""Manuelle Gamepad-Profile und Eingabelernen für das Eltern-Webbackend."""
from contextlib import contextmanager
from paimenos.input_devices import possible_gamepad
from pathlib import Path
import fcntl
import glob
import hashlib
import json
import os
import re
import secrets
import select
import shutil
import tempfile
import threading
import time

try:
    import evdev
except ImportError:
    evdev = None

ROOT = Path.home() / '.local/share/paimenos/controllers'
OFFICIAL = Path('/usr/local/share/paimenos/retroarch-autoconfig')
# Linux input-event-codes.h; Qt ist für den Webdienst nicht erforderlich.
EV_KEY, EV_ABS, EV_SYN, SYN_DROPPED = 1, 3, 0, 3
CONTROLS = [
    ('up', 'Steuerkreuz: oben', True), ('down', 'Steuerkreuz: unten', True),
    ('left', 'Steuerkreuz: links', True), ('right', 'Steuerkreuz: rechts', True),
    ('b', 'Untere Aktionstaste · B / Kreuz · Menü öffnen', True),
    ('a', 'Rechte Aktionstaste · A / Kreis · Zurück', True),
    ('y', 'Linke Aktionstaste · Y / Quadrat', False),
    ('x', 'Obere Aktionstaste · X / Dreieck', False),
    ('start', 'Start / Options · Farbe und Eltern', True),
    ('select', 'Select / Back / Share', False),
    ('l', 'Linke Schultertaste · L / L1 · vorige Kategorie', False),
    ('r', 'Rechte Schultertaste · R / R1 · nächste Kategorie', False),
    ('l2', 'Linker Trigger · L2', False), ('r2', 'Rechter Trigger · R2', False),
    ('l3', 'Linken Stick drücken · L3', False), ('r3', 'Rechten Stick drücken · R3', False),
    ('l_x_minus', 'Linker Analogstick: links', False),
    ('l_x_plus', 'Linker Analogstick: rechts', False),
    ('l_y_minus', 'Linker Analogstick: oben', False),
    ('l_y_plus', 'Linker Analogstick: unten', False),
    ('r_x_minus', 'Rechter Analogstick: links', False),
    ('r_x_plus', 'Rechter Analogstick: rechts', False),
    ('r_y_minus', 'Rechter Analogstick: oben', False),
    ('r_y_plus', 'Rechter Analogstick: unten', False),
]
CONTROL_IDS = {key for key, _, _ in CONTROLS}
REQUIRED = {key for key, _, required in CONTROLS if required}
DIRECTIONS = {'up', 'down', 'left', 'right'}


class ProfileError(ValueError):
    pass


def gamepad_capabilities(caps):
    keys = set(caps.get(EV_KEY, []))
    buttons = keys.intersection(range(256, 272)) | keys.intersection(range(288, 320))
    # Keine Maus, Tastatur, Kamera oder Touchpad für das Eingabelernen anbieten.
    return len(buttons) >= 2


def identity(device):
    return {'name': device.name, 'vendor': int(device.info.vendor),
            'product': int(device.info.product), 'bus': int(device.info.bustype)}


def profile_id(info):
    return hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()[:24]


def describe(device):
    caps = device.capabilities(absinfo=False)
    info = identity(device)
    return dict(info, id=profile_id(info), device=device.path,
                keys=sorted(caps.get(EV_KEY, [])),
                axes={str(code): {'min': value.min, 'max': value.max}
                      for code, value in device.capabilities().get(EV_ABS, [])
                      if 0 <= code < 40 and value.max > value.min})


@contextmanager
def profile_lock():
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'profiles.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_profiles():
    try:
        data = json.loads((ROOT / 'profiles.json').read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise ProfileError('Controller-Profile konnten nicht gelesen werden.') from exc
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('profiles'), dict):
        raise ProfileError('Controller-Profilformat ist ungültig.')
    return data['profiles']


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.controller-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def saved_profile(device):
    return read_profiles().get(profile_id(identity(device)))


def calibration_active():
    try:
        return 0 <= time.time() - (ROOT / 'calibration.json').stat().st_mtime < 35
    except OSError:
        return False


def devices():
    if evdev is None:
        raise ProfileError('python3-evdev fehlt. PaimenOS-Setup erneut ausführen.')
    profiles = read_profiles()
    result = []
    for path in sorted(glob.glob('/dev/input/event*')):
        if not possible_gamepad(path):
            continue
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        try:
            if gamepad_capabilities(device.capabilities(absinfo=False)):
                item = describe(device)
                item['configured'] = item['id'] in profiles
                result.append(item)
        except OSError:
            pass
        finally:
            device.close()
    return result


def status():
    return {'devices': devices(), 'profiles': [
        {'id': key, 'name': value['name'], 'vendor': value['vendor'],
         'product': value['product'], 'count': len(value['bindings'])}
        for key, value in read_profiles().items()],
        'controls': [{'id': key, 'label': label, 'required': required}
                     for key, label, required in CONTROLS]}


def validate_bindings(info, bindings):
    if not REQUIRED.issubset(bindings):
        raise ProfileError('Bitte Steuerkreuz, untere/rechte Aktionstaste und Start zuordnen.')
    seen = {}
    for control, binding in bindings.items():
        if control not in CONTROL_IDS or not isinstance(binding, dict):
            raise ProfileError('Unbekannte Tastenbelegung.')
        kind, code = binding.get('type'), binding.get('code')
        if type(code) is not int:
            raise ProfileError('Ungültiger Eingabecode.')
        if kind == 'key':
            if code not in info['keys'] or control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')):
                raise ProfileError('Diese Eingabe passt nicht zum Controller.')
            signature = (kind, code)
        elif kind == 'axis':
            if str(code) not in info['axes'] or binding.get('sign') not in (-1, 1):
                raise ProfileError('Ungültige Achsenbelegung.')
            signature = (kind, code, binding['sign'])
        else:
            raise ProfileError('Unbekannter Eingabetyp.')
        # Ein Stick darf zusätzlich zum Steuerkreuz als Analogstick zugeordnet sein.
        if not control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')):
            if signature in seen:
                raise ProfileError('Dieselbe Eingabe ist mehrfach zugeordnet: ' + seen[signature] + ' / ' + control)
            seen[signature] = control


def udev_indices(info):
    # Entspricht RetroArch input/drivers_joypad/udev_joypad.c, udev_add_pad().
    keys = sorted(info['keys'])
    ordered = ([k for k in keys if 103 <= k <= 108] + [k for k in keys if 256 <= k < 767]
               + [k for k in keys if k < 103] + [k for k in keys if 108 < k < 256])[:64]
    axes = sorted(int(code) for code in info['axes'] if not 16 <= int(code) <= 23)[:16]
    return {code: i for i, code in enumerate(ordered)}, {code: i for i, code in enumerate(axes)}


def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ') + '"'


def retroarch_profile(info):
    validate_bindings(info, info['bindings'])
    keys, axes = udev_indices(info)
    lines = ['input_driver = "udev"', 'input_device = ' + quote(info['name']),
             'input_vendor_id = ' + quote(info['vendor']), 'input_product_id = ' + quote(info['product'])]
    for control, binding in info['bindings'].items():
        kind, code = binding['type'], binding['code']
        if kind == 'key':
            if code not in keys:
                raise ProfileError('Dieser Controller hat mehr Tasten als RetroArch unterstützt.')
            suffix, value = 'btn', str(keys[code])
        elif 16 <= code <= 23:
            if control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')):
                raise ProfileError('Für Analogsticks bitte einen Stick verwenden, kein Steuerkreuz.')
            direction = ('left' if binding['sign'] < 0 else 'right') if code % 2 == 0 else ('up' if binding['sign'] < 0 else 'down')
            suffix, value = 'btn', 'h' + str((code - 16) // 2) + direction
        else:
            if code not in axes:
                raise ProfileError('Diese Achse wird von RetroArch nicht unterstützt.')
            suffix, value = 'axis', ('+' if binding['sign'] > 0 else '-') + str(axes[code])
        lines.append('input_' + control + '_' + suffix + ' = ' + quote(value))
    return '\n'.join(lines) + '\n'


def save_profile(info, bindings):
    value = dict(info, bindings=bindings)
    # Bevor eine bestehende Belegung verändert wird, vollständigen Export prüfen.
    retroarch_profile(value)
    with profile_lock():
        profiles = read_profiles()
        # RetroArch unterscheidet Name und VID/PID, aber nicht den Verbindungstyp.
        profiles = {key: item for key, item in profiles.items()
                    if (item['name'], item['vendor'], item['product']) !=
                       (info['name'], info['vendor'], info['product'])}
        profiles[info['id']] = value
        atomic_json(ROOT / 'profiles.json', {'version': 1, 'profiles': profiles})


def reset_profile(key):
    with profile_lock():
        profiles = read_profiles()
        if key not in profiles:
            raise ProfileError('Dieses eigene Profil wurde nicht gefunden.')
        del profiles[key]
        atomic_json(ROOT / 'profiles.json', {'version': 1, 'profiles': profiles})


def effective_autoconfig():
    """Eigene Profile haben Vorrang; andere offizielle Profile bleiben verfügbar."""
    with profile_lock():
        profiles = read_profiles()
        if not profiles:
            return str(OFFICIAL)
        stage = Path(tempfile.mkdtemp(prefix='.autoconfig-', dir=ROOT))
        destination = ROOT / 'retroarch-autoconfig'
        try:
            (stage / 'udev').mkdir()
            for path in (OFFICIAL / 'udev').glob('*.cfg'):
                text = path.read_text(errors='replace')
                fields = dict(re.findall(r'^\s*(input_device|input_vendor_id|input_product_id)\s*=\s*"([^"\n]*)"', text, re.M))
                overridden = any(
                    (fields.get('input_device') == item['name']
                     and fields.get('input_vendor_id', '0') == '0'
                     and fields.get('input_product_id', '0') == '0') or
                    (item['vendor'] and item['product'] and fields.get('input_vendor_id') == str(item['vendor'])
                     and fields.get('input_product_id') == str(item['product'])) for item in profiles.values())
                if not overridden:
                    shutil.copyfile(path, stage / 'udev' / path.name)
            for key, info in profiles.items():
                if not re.fullmatch(r'[0-9a-f]{24}', key):
                    raise ProfileError('Ungültige Controller-Profilkennung.')
                (stage / 'udev' / ('paimenos-' + key + '.cfg')).write_text(retroarch_profile(info))
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return str(destination)


def binding_label(binding):
    if binding['type'] == 'key':
        return 'Taste ' + str(binding['code'])
    return 'Achse ' + str(binding['code']) + (' +' if binding['sign'] > 0 else ' −')


def axis_value(info, value):
    return (2 * value - info.min - info.max) / (info.max - info.min)


class Calibration:
    """Ein Assistent pro Laptop. Keine exklusiven Grabs, keine Eingabe-Injektion."""
    def __init__(self):
        self.lock = threading.RLock()
        self.read_lock = threading.Lock()
        self.current = None

    def touch(self, state):
        state['touched'] = time.monotonic()
        atomic_json(ROOT / 'calibration.json', {'token': state['token']})

    def checked(self, token, owner):
        state = self.current
        if not state or not secrets.compare_digest(state['token'], token) or state['owner'] != owner:
            raise ProfileError('Konfiguration ist abgelaufen. Bitte erneut öffnen.')
        if time.monotonic() - state['touched'] > 120:
            self.finish(state)
            raise ProfileError('Konfiguration ist abgelaufen. Bitte erneut öffnen.')
        self.touch(state)
        return state

    def finish(self, state):
        state['cancel'].set()
        if self.current is state:
            self.current = None
            (ROOT / 'calibration.json').unlink(missing_ok=True)

    def start(self, device_id, owner):
        with self.lock:
            if self.current:
                if time.monotonic() - self.current['touched'] <= 120 and self.current['owner'] != owner:
                    raise ProfileError('Ein anderer Elternbereich richtet gerade einen Controller ein.')
                if self.read_lock.locked():
                    raise ProfileError('Bitte zuerst die laufende Eingabe abbrechen.')
                self.finish(self.current)
            info = next((item for item in devices() if item['device'] == device_id), None)
            if info is None:
                raise ProfileError('Controller ist nicht mehr verbunden. Liste aktualisieren.')
            bindings = read_profiles().get(info['id'], {}).get('bindings', {})
            state = {'token': secrets.token_hex(24), 'owner': owner, 'info': info,
                     'bindings': dict(bindings), 'cancel': threading.Event()}
            self.touch(state)
            self.current = state
            return self.snapshot(state)

    def snapshot(self, state):
        return {'token': state['token'], 'device': state['info'], 'bindings': state['bindings'],
                'labels': {key: binding_label(value) for key, value in state['bindings'].items()}}

    def action(self, action, token, owner, control=''):
        with self.lock:
            state = self.checked(token, owner)
            if action == 'cancel_capture':
                state['cancel'].set()
            elif action == 'cancel':
                self.finish(state)
                return {'cancelled': True}
            elif action in ('save', 'skip', 'clear'):
                if self.read_lock.locked():
                    raise ProfileError('Bitte die laufende Eingabe zuerst beenden.')
                if action != 'save':
                    if control not in CONTROL_IDS or action == 'skip' and control in REQUIRED:
                        raise ProfileError('Diese Pflichtbelegung kann nicht übersprungen werden.')
                    state['bindings'].pop(control, None)
                else:
                    save_profile(state['info'], state['bindings'])
                    self.finish(state)
                    return {'saved': True}
            elif action != 'heartbeat':
                raise ProfileError('Unbekannte Controller-Aktion.')
            return self.snapshot(state)

    def capture(self, token, owner, control, timeout=10):
        if control not in CONTROL_IDS:
            raise ProfileError('Unbekannte Controller-Taste.')
        with self.lock:
            state = self.checked(token, owner)
            if not self.read_lock.acquire(blocking=False):
                raise ProfileError('Es wird bereits eine Controller-Eingabe gelesen.')
            state['cancel'] = threading.Event()
        device = None
        try:
            device = evdev.InputDevice(state['info']['device'])
            if describe(device) != {k: v for k, v in state['info'].items() if k != 'configured'}:
                raise ProfileError('Controller hat sich geändert. Konfiguration erneut öffnen.')
            # Bereits gedrückte Tasten und alte Ereignisse nicht als neue Zuordnung werten.
            list(device.read()) if select.select([device.fd], [], [], 0)[0] else None
            held = set(device.active_keys())
            axes = {code: info for code, info in device.capabilities().get(EV_ABS, [])
                    if str(code) in state['info']['axes']}
            baseline = {code: axis_value(info, device.absinfo(code).value) for code, info in axes.items()}
            blocked_axes = {code for code, value in baseline.items()
                            if abs(value) > .55 and code not in (2, 5, 9, 10)}
            limit = time.monotonic() + timeout
            while time.monotonic() < limit:
                if state['cancel'].is_set():
                    return {'cancelled': True}
                ready = select.select([device.fd], [], [], min(.1, max(0, limit - time.monotonic())))[0]
                if not ready:
                    continue
                try:
                    events = device.read()
                except BlockingIOError:
                    continue
                for event in events:
                    if event.type == EV_SYN and event.code == SYN_DROPPED:
                        raise ProfileError('Eingaben gingen verloren. Alle Tasten loslassen und erneut versuchen.')
                    binding = None
                    if event.type == EV_KEY and event.code in state['info']['keys']:
                        if event.value == 0:
                            held.discard(event.code)
                        elif event.value == 1 and not held and not blocked_axes:
                            if not control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')):
                                binding = {'type': 'key', 'code': event.code}
                        if event.value:
                            held.add(event.code)
                    elif event.type == EV_ABS and event.code in axes:
                        value = axis_value(axes[event.code], event.value)
                        if abs(value) < .3:
                            blocked_axes.discard(event.code)
                            baseline[event.code] = value
                        elif not held and not blocked_axes and abs(value - baseline[event.code]) >= .55:
                            if control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')) and 16 <= event.code <= 23:
                                continue
                            if abs(value) >= .55:
                                binding = {'type': 'axis', 'code': event.code, 'sign': 1 if value > 0 else -1}
                    if binding is not None:
                        with self.lock:
                            self.checked(token, owner)
                            if state['cancel'].is_set():
                                return {'cancelled': True}
                            # Beim Lernen schon doppelte Eingaben erklären; alte Belegung erhalten.
                            candidate = dict(state['bindings'], **{control: binding})
                            for key, value in state['bindings'].items():
                                if key != control and value == binding and not key.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')) and not control.startswith(('l_x_', 'l_y_', 'r_x_', 'r_y_')):
                                    raise ProfileError('Diese Eingabe ist bereits „' + dict((k, label) for k, label, _ in CONTROLS)[key] + '“ zugeordnet.')
                            state['bindings'] = candidate
                            return self.snapshot(state)
            return {'timeout': True}
        except OSError as exc:
            raise ProfileError('Controller getrennt oder nicht lesbar. Wieder verbinden und erneut öffnen.') from exc
        finally:
            if device is not None:
                device.close()
            self.read_lock.release()


calibration = Calibration()

