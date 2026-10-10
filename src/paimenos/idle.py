"""Energiesparen in der Kindersitzung: unbenutzte Bluetooth-Gamepads trennen, Leerlauf melden.

Gamepads werden nur mitgelesen (kein Grab). Getrennte Bluetooth-Controller schalten sich
selbst aus; die Kopplung bleibt erhalten und ein Tastendruck verbindet sie wieder.
Der Leerlauf der ganzen Sitzung geht als logind-IdleHint an paimenos.power.
"""
import fcntl
import glob
import os
from pathlib import Path
import select
import time
from paimenos.bluetooth import BluetoothError, bluetooth_request
from paimenos.diagnostics import log_event
from paimenos.input_devices import possible_gamepad
from paimenos.paths import STATE_DIR
from paimenos.power import LOGIND, MANAGER, SESSION, exclusive_lock_held

GAMEPAD_IDLE_SECONDS = 5 * 60
SESSION_IDLE_SECONDS = 30 * 60
TICK_SECONDS = 15
DISCONNECT_RETRY_SECONDS = 60
BUS_BLUETOOTH = 0x05
EV_KEY, EV_ABS = 0x01, 0x03
HAT_AXES = range(0x10, 0x18)
# Leichtes Stick-Rauschen hält Controller nicht wach.
AXIS_THRESHOLD = 0.3


class Gamepad:
    def __init__(self, device, now):
        self.device = device
        self.last = now
        info = device.info
        uniq = (getattr(device, 'uniq', '') or '').strip().upper()
        self.address = uniq if info.bustype == BUS_BLUETOOTH and uniq else ''
        self.axes = {}
        for code, absinfo in device.capabilities().get(EV_ABS, []):
            span = absinfo.max - absinfo.min
            if span > 0:
                self.axes[code] = (absinfo.value, span)

    def active(self, event):
        if event.type == EV_KEY:
            return True
        if event.type != EV_ABS:
            return False
        if event.code in HAT_AXES:
            return event.value != 0
        rest, span = self.axes.get(event.code, (0, 0))
        return span > 0 and abs(event.value - rest) > span * AXIS_THRESHOLD


class GamepadActivity:
    def __init__(self, open_device=None, paths=None, clock=time.monotonic):
        self.open_device = open_device or self._evdev_device
        self.paths = paths or self._gamepad_paths
        self.clock = clock
        self.gamepads = {}

    @staticmethod
    def _evdev_device(path):
        import evdev
        return evdev.InputDevice(path)

    @staticmethod
    def _gamepad_paths():
        return sorted(path for path in glob.glob('/dev/input/event*')
                      if os.access(path, os.R_OK) and possible_gamepad(path))

    def refresh(self):
        current = set(self.paths())
        for path in set(self.gamepads) - current:
            self.drop(path)
        for path in current - set(self.gamepads):
            try:
                self.gamepads[path] = Gamepad(self.open_device(path), self.clock())
            except OSError:
                continue

    def drop(self, path):
        gamepad = self.gamepads.pop(path, None)
        if gamepad:
            try:
                gamepad.device.close()
            except OSError:
                pass

    def poll(self, timeout):
        if not self.gamepads:
            time.sleep(timeout)
            return
        by_fd = {gamepad.device.fd: path for path, gamepad in self.gamepads.items()}
        try:
            ready, _, _ = select.select(list(by_fd), [], [], timeout)
        except (OSError, ValueError):
            ready = list(by_fd)
        for fd in ready:
            path = by_fd[fd]
            gamepad = self.gamepads[path]
            try:
                events = list(gamepad.device.read())
            except BlockingIOError:
                continue
            except OSError:
                self.drop(path)  # Controller getrennt oder ausgeschaltet.
                continue
            if any(gamepad.active(event) for event in events):
                gamepad.last = self.clock()

    def last_activity(self):
        return max((gamepad.last for gamepad in self.gamepads.values()), default=None)

    def idle_addresses(self, now, seconds):
        latest = {}
        for gamepad in self.gamepads.values():
            if gamepad.address:
                latest[gamepad.address] = max(latest.get(gamepad.address, 0), gamepad.last)
        return {address for address, last in latest.items() if now - last >= seconds}

    def reset(self, now):
        for gamepad in self.gamepads.values():
            gamepad.last = now


def x_idle_reader():
    from Xlib import display
    from Xlib.ext import screensaver  # noqa: F401 - registriert die Erweiterung
    connection = display.Display()
    if not connection.has_extension('MIT-SCREEN-SAVER'):
        raise RuntimeError('X-Erweiterung MIT-SCREEN-SAVER fehlt')
    root = connection.screen().root
    return lambda: root.screensaver_query_info().idle / 1000


def audio_playing(root=Path('/proc/asound')):
    # PipeWire schließt ungenutzte Ausgänge nach wenigen Sekunden; RUNNING heißt echte Wiedergabe.
    for status in root.glob('card*/pcm*p/sub*/status'):
        try:
            if status.read_text(errors='replace').startswith('state: RUNNING'):
                return True
        except OSError:
            continue
    return False


def backup_running(lock=None):
    # Backup/Wiederherstellung halten emulator-data.lock exklusiv (paimenos.backups.data_lock).
    return exclusive_lock_held(str(lock or STATE_DIR / 'emulator-data.lock'))


def suspend_clock():
    """Wächst nur während einer Bereitschaft (BOOTTIME zählt sie mit, MONOTONIC nicht)."""
    return time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()


class IdleHint:
    def __init__(self):
        import dbus
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object(LOGIND, '/org/freedesktop/login1'), MANAGER)
        uid = os.getuid()
        self.session = None
        for _id, session_uid, _user, seat, path in manager.ListSessions():
            proxy = bus.get_object(LOGIND, path)
            kind = proxy.Get(SESSION, 'Type', dbus_interface='org.freedesktop.DBus.Properties')
            if int(session_uid) == uid and seat and kind in ('x11', 'wayland'):
                self.session = dbus.Interface(proxy, SESSION)
                break
        if self.session is None:
            raise RuntimeError('Keine grafische logind-Sitzung gefunden')
        self.value = None

    def set(self, idle):
        if idle != self.value:
            # logind erlaubt das nur dem Eigentümer der Sitzung; keine Polkit-Regel nötig.
            self.session.SetIdleHint(bool(idle))
            self.value = idle


class IdleMonitor:
    def __init__(self, gamepads, x_idle, hint, audio=audio_playing, backup=backup_running,
                 bluetooth=bluetooth_request, clock=time.monotonic, slept=suspend_clock):
        self.gamepads, self.x_idle, self.hint = gamepads, x_idle, hint
        self.audio, self.backup, self.bluetooth = audio, backup, bluetooth
        self.clock, self.slept = clock, slept
        now = clock()
        self.last_activity = now
        self.sleep_offset = slept()
        self.disconnect_attempts = {}

    def resumed(self, now):
        offset = self.slept()
        if offset - self.sleep_offset > 5:
            # Nach dem Aufwachen neu beginnen; X zählt die Ruhezeit sonst als Leerlauf.
            self.last_activity = now
            self.gamepads.reset(now)
            self.disconnect_attempts.clear()
            self.sleep_offset = offset
            return True
        self.sleep_offset = offset
        return False

    def session_idle_seconds(self, now):
        if self.audio() or self.backup():
            self.last_activity = now
        gamepad = self.gamepads.last_activity()
        if gamepad is not None:
            self.last_activity = max(self.last_activity, gamepad)
        try:
            self.last_activity = max(self.last_activity, now - self.x_idle())
        except Exception:
            # Ohne X-Leerlaufzeit lieber nie automatisch schlafen.
            self.last_activity = now
        return now - self.last_activity

    def disconnect_idle_gamepads(self, now):
        idle = {address for address in self.gamepads.idle_addresses(now, GAMEPAD_IDLE_SECONDS)
                if now - self.disconnect_attempts.get(address, -DISCONNECT_RETRY_SECONDS) >= DISCONNECT_RETRY_SECONDS}
        if not idle:
            return []
        disconnected = []
        try:
            devices = self.bluetooth('status').get('devices', [])
            for device in devices:
                address = str(device.get('address', '')).upper()
                if address in idle and device.get('connected'):
                    self.disconnect_attempts[address] = now
                    self.bluetooth('disconnect', device=device['path'])
                    disconnected.append(device.get('name') or address)
        except BluetoothError as exc:
            # Laufende Kopplung o. Ä.: beim nächsten Durchlauf erneut versuchen.
            log_event('idle', 'Controller nicht getrennt: ' + str(exc))
        for name in disconnected:
            log_event('idle', 'Unbenutzter Bluetooth-Controller getrennt: ' + str(name))
        return disconnected

    def tick(self):
        self.gamepads.refresh()
        now = self.clock()
        if self.resumed(now):
            self.hint.set(False)
            return
        self.disconnect_idle_gamepads(now)
        self.hint.set(self.session_idle_seconds(now) >= SESSION_IDLE_SECONDS)


class NoHint:
    def set(self, idle):
        pass


def unavailable():
    raise RuntimeError('X-Leerlaufzeit nicht verfügbar')


def main():
    # Auch bei doppeltem Start nur eine Instanz.
    with open(STATE_DIR / 'paimenos-idle.lock', 'a') as instance:
        try:
            fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        gamepads = GamepadActivity()
        try:
            x_idle = x_idle_reader()
        except Exception as exc:
            log_event('idle', 'X-Leerlaufzeit nicht verfügbar, keine automatische Bereitschaft: ' + str(exc))
            x_idle = unavailable
        try:
            hint = IdleHint()
        except Exception as exc:
            # Controller trotzdem trennen; Update-Prüfung erwartet einen laufenden Dienst.
            log_event('idle', 'logind-Sitzung nicht verfügbar, keine automatische Bereitschaft: ' + str(exc))
            hint = NoHint()
        monitor = IdleMonitor(gamepads, x_idle, hint)
        while True:
            try:
                monitor.tick()
            except Exception as exc:
                log_event('idle', 'Leerlaufprüfung fehlgeschlagen: ' + str(exc))
            deadline = time.monotonic() + TICK_SECONDS
            while (left := deadline - time.monotonic()) > 0:
                gamepads.poll(min(left, 1))


if __name__ == '__main__':
    main()
