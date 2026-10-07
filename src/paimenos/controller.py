"""Gamepads im Kinder-Menü lesen, ohne Eingaben von Spielen abzufangen."""
import select
import sys
import time
import glob
import os
import stat
import fcntl
import struct
import threading
from collections import deque
from paimenos.input_devices import possible_gamepad
from paimenos.diagnostics import log_event
import paimenos.controller_profiles as profiles
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

try:
    import evdev
    from evdev import ecodes as E
except ImportError:
    evdev = None
    E = None


def input_clock(device):
    # EVIOCSCLOCKID aus linux/input.h: Ereignisalter ohne Änderungen der Systemzeit.
    try:
        fcntl.ioctl(device.fd, 0x400445a0, struct.pack('i', time.CLOCK_MONOTONIC))
        return time.monotonic
    except OSError:
        return time.time


def readable_devices():
    """Versionsunabhängige Gerätesuche; ältere evdev-Versionen kennen writable nicht."""
    paths = []
    for path in glob.glob('/dev/input/event*'):
        try:
            if stat.S_ISCHR(os.stat(path).st_mode) and os.access(path, os.R_OK) and possible_gamepad(path):
                paths.append(path)
        except OSError:
            continue
    return sorted(paths)


def controller_mapping(caps):
    """Standard-Gamepads und ältere HID-Joysticks, niemals Maus/Touchpad."""
    keys = set(caps.get(E.EV_KEY, []))
    axes = set(caps.get(E.EV_ABS, []))
    navigation = ({E.ABS_X, E.ABS_Y}.issubset(axes)
                  or {E.ABS_HAT0X, E.ABS_HAT0Y}.issubset(axes)
                  or keys.intersection(GamepadState.DPAD))
    if not navigation:
        return None
    face = sorted(keys.intersection((E.BTN_SOUTH, E.BTN_EAST, E.BTN_NORTH, E.BTN_WEST)))
    if face and (E.BTN_SOUTH in keys or len(face) >= 2):
        buttons = {face[0]: 'activate'}
        if len(face) >= 2:
            buttons[face[1]] = 'back'
        if E.BTN_START in keys:
            buttons[E.BTN_START] = 'toolbar'
        if E.BTN_TL in keys:
            buttons[E.BTN_TL] = 'category_prev'
        if E.BTN_TR in keys:
            buttons[E.BTN_TR] = 'category_next'
        return buttons
    # Manche HID-Modi melden BTN_0..BTN_9 oder BTN_TRIGGER.. statt BTN_GAMEPAD.
    legacy = sorted(code for code in keys if E.BTN_0 <= code <= E.BTN_9
                    or E.BTN_JOYSTICK <= code < E.BTN_GAMEPAD)
    if len(legacy) < 2:
        return None
    buttons = {legacy[0]: 'activate', legacy[1]: 'back'}
    if E.BTN_START in keys:
        buttons[E.BTN_START] = 'toolbar'
    if E.BTN_TL in keys:
        buttons[E.BTN_TL] = 'category_prev'
    if E.BTN_TR in keys:
        buttons[E.BTN_TR] = 'category_next'
    if len(legacy) >= 6:
        buttons.setdefault(legacy[4], 'category_prev')
        buttons.setdefault(legacy[5], 'category_next')
    return buttons


def controller_diagnosis():
    """Auch nicht lesbare Event-Geräte sichtbar machen; keine Tastatureingaben lesen."""
    lines = ['PaimenOS Controller-Diagnose',
             'Benutzer-ID: ' + str(os.getuid()) + ' · Gruppen-IDs: ' + str(os.getgroups())]
    if evdev is None:
        return '\n'.join(lines + ['FEHLER: python3-evdev ist nicht installiert.'])
    paths = sorted(glob.glob('/dev/input/event*'))
    readable = set(readable_devices())
    lines.append(f'Event-Geräte: {len(paths)} · lesbar: {len(readable)}')
    found = 0
    for path in paths:
        if path not in readable:
            lines.append(path + ': kein Lesezugriff')
            continue
        if not possible_gamepad(path):
            continue
        device = None
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities(absinfo=False)
            mapping = controller_mapping(caps)
            if mapping is None and not any(name in device.name.lower() for name in ('8bitdo', 'sn30', 'gamepad', 'controller', 'joystick')):
                continue
            found += 1
            lines += ['', path + ': ' + device.name,
                      'Menü-Erkennung: ' + ('Ja' if mapping else 'Nein'),
                      'Tastencodes: ' + str(caps.get(E.EV_KEY, [])),
                      'Menü-Tasten: ' + str(mapping),
                      'Achsen: ' + str(device.capabilities().get(E.EV_ABS, []))]
        except OSError as exc:
            lines.append(path + ': ' + str(exc))
        finally:
            if device is not None:
                device.close()
    if not found:
        lines.append('Kein lesbarer Controller gefunden. Bluetooth-Verbindung, Betriebsmodus und input-Gruppe prüfen.')
    return '\n'.join(lines)


class GamepadState:
    BUTTONS = {304: 'activate', 305: 'back', 315: 'toolbar'}
    DPAD = {544: 'up', 545: 'down', 546: 'left', 547: 'right'}

    def __init__(self, device, buttons=None, custom=None, event_clock=time.time):
        self.device = device
        self.event_clock = event_clock
        self.last_lag_log = -100
        self.custom = custom
        self.buttons = buttons if buttons is not None else self.BUTTONS
        self.axes = dict(device.capabilities().get(E.EV_ABS, []))
        self.values = {code: info.value for code, info in self.axes.items()}
        self.keys = set(device.active_keys())
        self.sticks = {}
        self.pending = []
        self.blocked = True
        self.held = None
        self.next_repeat = 0
        self.dropped = False
        self.frame_open = False
        self.axis_pressed = set()

    def cancel(self):
        # Nach App/Dialog/Neuverbinden erst loslassen, dann neu bedienen.
        self.blocked = True
        self.held = None
        self.pending.clear()
        self.axis_pressed.clear()

    def resync(self):
        self.values = {code: self.device.absinfo(code).value for code in self.axes}
        self.keys = set(self.device.active_keys())
        self.sticks.clear()
        self.dropped = False
        self.cancel()

    def update(self, event):
        if event.type == E.EV_SYN and event.code == E.SYN_REPORT:
            self.frame_open = False
        elif event.type in (E.EV_ABS, E.EV_KEY):
            self.frame_open = True
        if event.type == E.EV_SYN and event.code == E.SYN_DROPPED:
            self.dropped = True
            self.cancel()
        elif self.dropped:
            if event.type == E.EV_SYN and event.code == E.SYN_REPORT:
                self.resync()
        elif event.type == E.EV_ABS and event.code in self.axes:
            self.values[event.code] = event.value
        elif event.type == E.EV_KEY:
            if event.value == 0:
                self.keys.discard(event.code)
            elif event.value == 1:
                if event.code in self.buttons and event.code not in self.keys:
                    self.pending.append(self.buttons[event.code])
                self.keys.add(event.code)

    def stick(self, code):
        info = self.axes.get(code)
        if info is None or info.max <= info.min:
            return 0, 0.0
        half = (info.max - info.min) / 2
        value = (self.values[code] - (info.min + half)) / half
        previous = self.sticks.get(code, 0)
        threshold = max(0.35 if previous * value > 0 else 0.55, min(0.9, info.flat / half))
        direction = (1 if value > 0 else -1) if abs(value) >= threshold else 0
        self.sticks[code] = direction
        return direction, abs(value)

    def direction(self):
        if self.custom:
            for direction in ('up', 'down', 'left', 'right'):
                binding = self.custom.get(direction)
                if not binding:
                    continue
                if binding['type'] == 'key' and binding['code'] in self.keys:
                    return direction
                if binding['type'] == 'axis':
                    sign, _ = self.stick(binding['code'])
                    if sign == binding['sign']:
                        return direction
            # Ein zusätzlich zugeordneter linker Stick kann ebenfalls navigieren.
            for control, direction in (('l_y_minus', 'up'), ('l_y_plus', 'down'),
                                       ('l_x_minus', 'left'), ('l_x_plus', 'right')):
                binding = self.custom.get(control)
                if binding and binding['type'] == 'axis':
                    sign, _ = self.stick(binding['code'])
                    if sign == binding['sign']:
                        return direction
            return None
        # Steuerkreuz hat Vorrang; diagonale Eingaben wählen genau eine Richtung.
        x, y = self.values.get(E.ABS_HAT0X, 0), self.values.get(E.ABS_HAT0Y, 0)
        if y:
            return 'down' if y > 0 else 'up'
        if x:
            return 'right' if x > 0 else 'left'
        for code, direction in self.DPAD.items():
            if code in self.keys:
                return direction
        x, strength_x = self.stick(E.ABS_X)
        y, strength_y = self.stick(E.ABS_Y)
        # Am diagonalen Rand nicht bei jedem kleinen Zittern die Achse wechseln.
        if x and y:
            if self.held in ('left', 'right') and strength_y < strength_x + 0.2:
                return 'right' if x > 0 else 'left'
            if self.held in ('up', 'down') and strength_x < strength_y + 0.2:
                return 'down' if y > 0 else 'up'
        if y and (not x or strength_y >= strength_x):
            return 'down' if y > 0 else 'up'
        if x:
            return 'right' if x > 0 else 'left'
        return None

    def actions(self, enabled, now):
        if not enabled or self.dropped:
            self.cancel()
            return []
        direction = self.direction()
        axis_actions = set()
        if self.custom:
            for control, action in (('b', 'activate'), ('a', 'back'), ('start', 'toolbar'),
                                    ('l', 'category_prev'), ('r', 'category_next')):
                binding = self.custom.get(control)
                if binding and binding['type'] == 'axis':
                    sign, _ = self.stick(binding['code'])
                    if sign == binding['sign']:
                        axis_actions.add(action)
            if not self.blocked:
                self.pending.extend(sorted(axis_actions - self.axis_pressed))
            self.axis_pressed = axis_actions
        if self.blocked:
            self.pending.clear()
            if direction is None and not self.keys.intersection(self.buttons) and not axis_actions:
                self.blocked = False
            return []
        result, self.pending = self.pending, []
        if direction != self.held:
            self.held = direction
            self.next_repeat = now + 0.38
            if direction:
                result.insert(0, direction)
        elif direction and now >= self.next_repeat:
            result.insert(0, direction)
            self.next_repeat = now + 0.13
        return result


class CallbackSignal:
    def __init__(self, callback):
        self.emit = callback


class InputBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = deque(maxlen=32)
        self.allowed = False
        self.generation = 0
        self.paths = ()

    def set_allowed(self, allowed):
        with self.lock:
            if bool(allowed) != self.allowed:
                self.allowed = bool(allowed)
                self.generation += 1
                self.pending.clear()

    def is_enabled(self):
        with self.lock:
            return self.allowed

    def push(self, action):
        with self.lock:
            if self.allowed:
                self.pending.append((time.monotonic(), self.generation, action))

    def set_devices(self, paths):
        with self.lock:
            self.paths = paths

    def take(self):
        with self.lock:
            pending = list(self.pending)
            self.pending.clear()
            return self.paths, pending

    def valid(self, timestamp, generation):
        with self.lock:
            return (self.allowed and self.generation == generation
                    and 0 <= time.monotonic() - timestamp <= .3)


class ControllerInput:
    """Alle evdev-Zugriffe gehören ausschließlich dem Eingabethread."""
    def __init__(self, bridge):
        self.enabled = bridge.is_enabled
        self.action = CallbackSignal(bridge.push)
        self.available_changed = CallbackSignal(lambda count: bridge.set_devices(tuple(self.devices)))
        self.devices = {}
        self.warned = set()
        self.profile_stamp = None
        self.failed = False
        self.rejected = {}
        if evdev is None:
            print('Controller-Menü: python3-evdev fehlt.', file=sys.stderr)

    def safely(self, operation):
        if self.failed:
            return
        try:
            operation()
        except Exception as exc:
            # Ein Controller-Fehler darf weder Menüstart noch Qt-Popup-Schleifen auslösen.
            self.failed = True
            for path in list(self.devices):
                state = self.devices.pop(path)
                try:
                    state.device.close()
                except Exception:
                    pass
            message = 'Controller-Steuerung deaktiviert: ' + type(exc).__name__ + ': ' + str(exc)
            print(message, file=sys.stderr)
            log_event('controller', message)
            self.available_changed.emit(0)

    def safe_scan(self):
        self.safely(self.scan)

    def safe_poll(self):
        self.safely(self.poll)

    def scan(self):
        if evdev is None:
            return
        try:
            # Zum Lesen ist kein Schreibzugriff nötig; sonst fehlen Controller stillschweigend.
            paths = set(readable_devices())
        except OSError:
            return
        try:
            stamp = (profiles.ROOT / 'profiles.json').stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp != self.profile_stamp:
            self.profile_stamp = stamp
            self.rejected.clear()
            for path in list(self.devices):
                self.remove(path)
        self.rejected = {path: sig for path, sig in self.rejected.items() if path in paths}
        for path in set(self.devices) - paths:
            self.remove(path)
        for path in sorted(paths - set(self.devices)):
            try:
                info = os.stat(path)
                signature = (info.st_ino, info.st_rdev)
            except OSError:
                continue
            if self.rejected.get(path) == signature:
                continue
            device = None
            try:
                device = evdev.InputDevice(path)
                caps = device.capabilities(absinfo=False)
                custom = profiles.saved_profile(device)
                if custom:
                    bindings = custom['bindings']
                    buttons = {value['code']: action
                        for control, action in (('b', 'activate'), ('a', 'back'), ('start', 'toolbar'),
                                                ('l', 'category_prev'), ('r', 'category_next'))
                        for value in [bindings.get(control)] if value and value['type'] == 'key'}
                else:
                    bindings = None
                    buttons = controller_mapping(caps)
                if buttons is None:
                    self.rejected[path] = signature
                    device.close()
                    continue
                self.devices[path] = GamepadState(device, buttons, bindings, input_clock(device))
                self.warned.discard(path)
                print('Controller-Menü: erkannt: ' + device.name, file=sys.stderr)
                log_event('controller', 'Erkannt: ' + device.name + ' · ' + path + ' · Tasten: ' + str(buttons))
                self.available_changed.emit(len(self.devices))
            except OSError as exc:
                if device is not None:
                    device.close()
                if path not in self.warned:
                    print('Controller-Menü: Gerät nicht lesbar: ' + str(exc), file=sys.stderr)
                    log_event('controller', 'Gerät nicht lesbar: ' + str(exc))
                    self.warned.add(path)

    def remove(self, path):
        state = self.devices.pop(path, None)
        if state is not None:
            state.device.close()
            self.available_changed.emit(len(self.devices))

    def dispatch(self, state, now):
        if profiles.calibration_active() or not self.enabled():
            state.cancel()
            return
        if state.frame_open:
            return
        # Ein Tick liefert höchstens eine Bewegung und eine Tastenaktion.
        for action in list(dict.fromkeys(state.actions(True, now)))[:2]:
            if profiles.calibration_active() or not self.enabled():
                state.cancel()
                break
            self.action.emit(action)

    def poll(self):
        now = time.monotonic()
        for path, state in list(self.devices.items()):
            try:
                # Alle verfügbaren Pakete abarbeiten, nicht nur 64 Ereignisse je 25 ms.
                # Budget und Obergrenze verhindern, dass ein Dauerfeuer die Qt-Schleife hält.
                deadline = time.monotonic() + 0.003
                batches = 0
                while batches < 64 and time.monotonic() < deadline:
                    if not select.select([state.device.fd], [], [], 0)[0]:
                        break
                    try:
                        events = list(state.device.read())
                    except BlockingIOError:
                        break
                    if not events:
                        break
                    batches += 1
                    for event in events:
                        state.update(event)
                        timestamp = getattr(event, 'timestamp', None)
                        age = state.event_clock() - timestamp() if callable(timestamp) else 0
                        if age > 0.3 or age < -1:
                            # Zustände aktualisieren, alte Tastendrücke aber niemals nachspielen.
                            state.cancel()
                            if event.type == E.EV_SYN and event.code == E.SYN_REPORT:
                                # Eine alte Neutralstellung darf die Loslass-Sperre lösen,
                                # damit die erste aktuelle Eingabe direkt angenommen wird.
                                state.actions(True, now)
                            if now - state.last_lag_log >= 10:
                                state.last_lag_log = now
                                log_event('controller', 'Veraltete Eingaben verworfen: ' +
                                          state.device.name + ' · Alter ' + f'{age:.2f}' + ' s')
                if select.select([state.device.fd], [], [], 0)[0]:
                    # Noch nicht am aktuellen Ende: keine veraltete Aktion anzeigen.
                    state.cancel()
                    continue
                # Zwischenstände zusammenfassen; nur einmal je Controller/Qt-Tick navigieren.
                self.dispatch(state, time.monotonic())
            except BlockingIOError:
                pass
            except (OSError, ValueError):
                self.remove(path)

    def close(self):
        for path in list(self.devices):
            self.remove(path)


class ControllerReader(QObject):
    action = pyqtSignal(str)
    available_changed = pyqtSignal(int)

    def __init__(self, parent, enabled):
        super().__init__(parent)
        self.enabled = enabled
        self.bridge = InputBridge()
        self.devices = {}
        self.stopping = threading.Event()
        self.read_timer = QTimer(self)
        self.read_timer.timeout.connect(self.pump)
        self.read_timer.start(25)
        self.worker = threading.Thread(target=self.run, name='PaimenOS-Gamepads', daemon=True)
        self.worker.start()

    def run(self):
        reader = ControllerInput(self.bridge)
        next_scan = 0
        try:
            while not self.stopping.is_set() and not reader.failed:
                if time.monotonic() >= next_scan:
                    reader.safe_scan()
                    next_scan = time.monotonic() + 2
                if not self.stopping.is_set() and not reader.failed:
                    reader.safe_poll()
                self.stopping.wait(.025)
        finally:
            reader.close()

    def pump(self):
        # Qt-Abfragen und Aktionen erfolgen nur im Menüthread.
        if self.stopping.is_set():
            return
        self.bridge.set_allowed(self.enabled())
        paths, actions = self.bridge.take()
        if set(paths) != set(self.devices):
            self.devices = dict.fromkeys(paths)
            self.available_changed.emit(len(paths))
        for timestamp, generation, action in actions:
            self.bridge.set_allowed(self.enabled())
            if self.bridge.valid(timestamp, generation):
                self.action.emit(action)

    def close(self):
        self.read_timer.stop()
        self.bridge.set_allowed(False)
        self.stopping.set()
        # Nicht auf Kernel-close()/RCU warten: Das Menü kann sofort schließen.


if __name__ == '__main__':
    print(controller_diagnosis())

