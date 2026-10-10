"""Bereitschaft nach langem Leerlauf. Root-Dienst; entscheidet nur anhand von logind-Daten.

Die Kindersitzung (paimenos.idle) meldet ihren Leerlauf als logind-IdleHint. Dieser Dienst
versetzt den Laptop erst dann in Bereitschaft, wenn keine Wartung läuft und kein Programm
den Ruhezustand blockiert. Ohne Polkit-Regel, damit auch Backend-Updates die Funktion liefern.
"""
import os
from pathlib import Path
import pwd
import subprocess
import time

LOGIND = 'org.freedesktop.login1'
MANAGER = 'org.freedesktop.login1.Manager'
SESSION = 'org.freedesktop.login1.Session'
CHECK_SECONDS = 30
# Gehaltene Sperren laufender Wartung; Download-/Installationsphasen über aktive Units.
MAINTENANCE_LOCKS = ('/run/paimenos-maintenance.lock', '/run/paimenos-emulator-install.lock',
                     '/run/paimenos-app-update.lock', '/run/paimenos-package-install.lock')
MAINTENANCE_UNITS = ('paimenos-update-job.service', 'paimenos-app-update.service',
                     'paimenos-packages.service')


def exclusive_lock_held(path, locks='/proc/locks'):
    """Fremde exklusive Sperre erkennen, ohne selbst zu sperren (kein Wettlauf mit Wartung)."""
    try:
        info = os.stat(path)
        with open(locks, encoding='ascii') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return False
    # Nur die Inode vergleichen: btrfs meldet in /proc/locks eine andere Geräte-ID als stat().
    # Eine zufällig gleiche Inode anderswo verhindert höchstens eine Bereitschaft.
    inode = ':' + str(info.st_ino)
    for line in lines:
        fields = line.split()
        if len(fields) > 1 and fields[1] == '->':
            continue  # Wartende Sperranfrage, keine gehaltene Sperre.
        if len(fields) >= 6 and fields[3] == 'WRITE' and fields[5].endswith(inode):
            return True
    return False


def maintenance_running():
    if any(exclusive_lock_held(path) for path in MAINTENANCE_LOCKS):
        return True
    # Exit 0, sobald mindestens eine der Units aktiv ist.
    result = subprocess.run(['systemctl', 'is-active', '--quiet', *MAINTENANCE_UNITS], check=False)
    return result.returncode == 0


def sleep_blocked(inhibitors):
    return any(mode == 'block' and {'sleep', 'idle'} & set(str(what).split(':'))
               for what, _who, _why, mode, _uid, _pid in inhibitors)


class PowerManager:
    def __init__(self, logind, uid, clock=time.monotonic, maintenance=maintenance_running):
        self.logind, self.uid, self.clock, self.maintenance = logind, uid, clock, maintenance
        # Ein vor dem Dienststart oder vor der letzten Bereitschaft gesetzter Hinweis zählt nicht.
        self.armed_after = int(clock() * 1_000_000)

    def idle_session(self):
        for session in self.logind.sessions():
            props = self.logind.session_properties(session)
            if (int(props.get('User', (None,))[0]) == self.uid and props.get('Active')
                    and props.get('Type') in ('x11', 'wayland') and props.get('IdleHint')
                    and int(props.get('IdleSinceHintMonotonic', 0)) > self.armed_after):
                return props
        return None

    def check(self):
        session = self.idle_session()
        if session is None:
            return False
        if sleep_blocked(self.logind.inhibitors()) or self.maintenance():
            return False
        self.armed_after = max(int(self.clock() * 1_000_000), int(session['IdleSinceHintMonotonic']))
        self.logind.suspend()
        return True


class Logind:
    def __init__(self):
        import dbus
        self.dbus = dbus
        self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object(LOGIND, '/org/freedesktop/login1'), MANAGER)

    def sessions(self):
        return [str(path) for _id, _uid, _user, _seat, path in self.manager.ListSessions()]

    def session_properties(self, path):
        proxy = self.bus.get_object(LOGIND, path)
        return proxy.GetAll(SESSION, dbus_interface='org.freedesktop.DBus.Properties')

    def inhibitors(self):
        return list(self.manager.ListInhibitors())

    def suspend(self):
        self.manager.Suspend(False)


def run_service():
    manager = PowerManager(Logind(), pwd.getpwnam('kids').pw_uid)
    while True:
        try:
            if manager.check():
                print('PaimenOS power: Bereitschaft nach Leerlauf der Kindersitzung', flush=True)
        except Exception as exc:
            # logind kurz nicht erreichbar: beim nächsten Durchlauf erneut prüfen.
            print('PaimenOS power:', exc, flush=True)
        time.sleep(CHECK_SECONDS)


if __name__ == '__main__':
    run_service()
