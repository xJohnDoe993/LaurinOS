"""Energiesparen: Controller trennen, Leerlauf melden und Bereitschaft nur ohne Wartung."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from paimenos import idle, power
from paimenos.bluetooth import BluetoothError


class Clock:
    def __init__(self, now=1000.0):
        self.now = now
    def __call__(self):
        return self.now


def absinfo(value, minimum, maximum):
    return SimpleNamespace(value=value, min=minimum, max=maximum)


class FakeDevice:
    def __init__(self, uniq='aa:bb:cc:dd:ee:ff', bustype=idle.BUS_BLUETOOTH):
        self.uniq, self.info, self.fd, self.closed = uniq, SimpleNamespace(bustype=bustype), 3, False
    def capabilities(self):
        return {idle.EV_ABS: [(0x00, absinfo(128, 0, 255)), (0x02, absinfo(0, 0, 255)), (0x10, absinfo(0, -1, 1))]}
    def close(self):
        self.closed = True


def event(kind, code, value):
    return SimpleNamespace(type=kind, code=code, value=value)


class LockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.lock = Path(self.temp.name) / 'job.lock'
        self.lock.write_text('')
        self.key = '00:24:%d' % os.stat(self.lock).st_ino
        self.locks = Path(self.temp.name) / 'locks'
    def tearDown(self):
        self.temp.cleanup()
    def held(self, text):
        self.locks.write_text(text)
        return power.exclusive_lock_held(str(self.lock), str(self.locks))
    def test_only_held_exclusive_lock_counts(self):
        self.assertTrue(self.held('1: FLOCK  ADVISORY  WRITE 42 %s 0 EOF\n' % self.key))
        self.assertFalse(self.held('1: FLOCK  ADVISORY  READ 42 %s 0 EOF\n' % self.key))
        self.assertFalse(self.held('1: FLOCK  ADVISORY  WRITE 42 00:24:%d1 0 EOF\n' % os.stat(self.lock).st_ino))
        # Wartende Anfrage bedeutet nicht, dass gerade Wartung läuft.
        self.assertFalse(self.held('1: -> FLOCK  ADVISORY  WRITE 42 %s 0 EOF\n' % self.key))
    def test_missing_lock_file_is_not_maintenance(self):
        self.assertFalse(power.exclusive_lock_held(str(self.lock) + '.missing', str(self.locks)))
    def test_real_flock_is_detected(self):
        import fcntl
        with open(self.lock) as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertTrue(power.exclusive_lock_held(str(self.lock)))
        self.assertFalse(power.exclusive_lock_held(str(self.lock)))


class FakeLogind:
    def __init__(self, **session):
        self.props = dict(User=(1001, '/u'), Active=True, Type='x11', IdleHint=True,
                          IdleSinceHintMonotonic=2_000_000_000)
        self.props.update(session)
        self.blockers, self.suspended = [], 0
    def sessions(self):
        return ['/org/freedesktop/login1/session/c1']
    def session_properties(self, path):
        return self.props
    def inhibitors(self):
        return self.blockers
    def suspend(self):
        self.suspended += 1


class PowerManagerTests(unittest.TestCase):
    def manager(self, logind, maintenance=False, now=1000.0):
        return power.PowerManager(logind, 1001, clock=Clock(now), maintenance=lambda: maintenance)
    def test_idle_kids_session_suspends_once(self):
        logind = FakeLogind()
        manager = self.manager(logind)
        self.assertTrue(manager.check())
        # Derselbe, vor der Bereitschaft gesetzte Hinweis löst keine zweite aus.
        self.assertFalse(manager.check())
        self.assertEqual(logind.suspended, 1)
    def test_hint_from_before_service_start_is_ignored(self):
        logind = FakeLogind(IdleSinceHintMonotonic=500_000_000)
        self.assertFalse(self.manager(logind).check())
    def test_no_suspend_without_matching_idle_session(self):
        for changes in (dict(IdleHint=False), dict(Active=False), dict(Type='tty'), dict(User=(1002, '/u'))):
            logind = FakeLogind(**changes)
            self.assertFalse(self.manager(logind).check(), changes)
            self.assertEqual(logind.suspended, 0)
    def test_maintenance_and_blocking_inhibitors_prevent_suspend(self):
        logind = FakeLogind()
        self.assertFalse(self.manager(logind, maintenance=True).check())
        logind.blockers = [('shutdown:sleep', 'apt', 'Paket', 'block', 0, 1)]
        self.assertFalse(self.manager(logind).check())
        logind.blockers = [('sleep', 'nm', 'WLAN', 'delay', 0, 1), ('handle-lid-switch', 'x', 'y', 'block', 0, 1)]
        self.assertTrue(self.manager(logind).check())


class FakeGamepads:
    def __init__(self, last=None, idle=()):
        self.last, self.idle, self.resets = last, set(idle), []
    def refresh(self):
        pass
    def last_activity(self):
        return self.last
    def idle_addresses(self, now, seconds):
        return set(self.idle)
    def reset(self, now):
        self.resets.append(now)


class FakeHint:
    def __init__(self):
        self.values = []
    def set(self, value):
        self.values.append(value)


class GamepadTests(unittest.TestCase):
    def test_noise_does_not_count_as_use(self):
        gamepad = idle.Gamepad(FakeDevice(), 0)
        self.assertEqual(gamepad.address, 'AA:BB:CC:DD:EE:FF')
        self.assertFalse(gamepad.active(event(idle.EV_ABS, 0x00, 140)))
        self.assertFalse(gamepad.active(event(idle.EV_ABS, 0x02, 20)))
        self.assertFalse(gamepad.active(event(idle.EV_ABS, 0x10, 0)))
        self.assertFalse(gamepad.active(event(0x00, 0, 0)))
        self.assertTrue(gamepad.active(event(idle.EV_ABS, 0x00, 250)))
        self.assertTrue(gamepad.active(event(idle.EV_ABS, 0x02, 200)))
        self.assertTrue(gamepad.active(event(idle.EV_ABS, 0x10, -1)))
        self.assertTrue(gamepad.active(event(idle.EV_KEY, 304, 1)))
    def test_usb_gamepad_has_no_bluetooth_address(self):
        self.assertEqual(idle.Gamepad(FakeDevice(bustype=0x03), 0).address, '')
    def test_controller_idle_is_tracked_per_address(self):
        clock = Clock(0)
        paths = ['/dev/input/event5', '/dev/input/event6']
        activity = idle.GamepadActivity(open_device=lambda path: FakeDevice(), paths=lambda: paths, clock=clock)
        activity.refresh()
        activity.gamepads['/dev/input/event6'].last = 200
        self.assertEqual(activity.idle_addresses(400, 300), set())
        self.assertEqual(activity.idle_addresses(500, 300), {'AA:BB:CC:DD:EE:FF'})
        paths.pop()
        activity.refresh()
        self.assertEqual(list(activity.gamepads), ['/dev/input/event5'])


class IdleMonitorTests(unittest.TestCase):
    def monitor(self, gamepads=None, x_idle=0, audio=False, backup=False, bluetooth=None, slept=None):
        self.clock = Clock(10_000)
        self.hint = FakeHint()
        self.requests = []
        def request(action, **values):
            self.requests.append((action, values))
            return {'devices': [dict(address='aa:bb:cc:dd:ee:ff', path='/org/bluez/hci0/dev_AA', connected=True, name='8BitDo'),
                                dict(address='11:22:33:44:55:66', path='/org/bluez/hci0/dev_11', connected=True, name='Kopfhörer')]}
        self.x = [x_idle]
        return idle.IdleMonitor(gamepads or FakeGamepads(), lambda: self.x[0], self.hint,
                                audio=lambda: audio, backup=lambda: backup, bluetooth=bluetooth or request,
                                clock=self.clock, slept=slept or (lambda: 0))
    def test_only_idle_controllers_are_disconnected_and_not_repeatedly(self):
        monitor = self.monitor(FakeGamepads(idle={'AA:BB:CC:DD:EE:FF'}))
        with patch.object(idle, 'log_event'):
            monitor.tick()
            self.assertEqual(self.requests, [('status', {}), ('disconnect', {'device': '/org/bluez/hci0/dev_AA'})])
            self.clock.now += idle.TICK_SECONDS
            monitor.tick()
        self.assertEqual(len(self.requests), 2)
    def test_bluetooth_errors_are_retried_later(self):
        def busy(action, **values):
            raise BluetoothError('läuft')
        monitor = self.monitor(FakeGamepads(idle={'AA:BB:CC:DD:EE:FF'}), bluetooth=busy)
        with patch.object(idle, 'log_event') as log:
            monitor.tick()
        self.assertIn('läuft', log.call_args[0][1])
    def test_session_idle_after_thirty_minutes_without_any_activity(self):
        monitor = self.monitor(x_idle=10_000)
        monitor.last_activity = self.clock.now - idle.SESSION_IDLE_SECONDS + 1
        monitor.tick()
        self.clock.now += 1
        monitor.tick()
        self.assertEqual(self.hint.values, [False, True])
    def test_gamepad_audio_backup_and_missing_x_keep_session_awake(self):
        for options in (dict(gamepads=FakeGamepads(last=10_000)), dict(audio=True), dict(backup=True)):
            monitor = self.monitor(x_idle=10_000, **options)
            monitor.last_activity = 0
            monitor.tick()
            self.assertEqual(self.hint.values, [False], options)
        monitor = self.monitor()
        monitor.last_activity = 0
        def broken():
            raise RuntimeError('kein X')
        monitor.x_idle = broken
        monitor.tick()
        self.assertEqual(self.hint.values, [False])
    def test_resume_restarts_idle_time(self):
        slept = [0]
        gamepads = FakeGamepads()
        monitor = self.monitor(gamepads, x_idle=10_000, slept=lambda: slept[0])
        monitor.last_activity = 0
        monitor.tick()
        self.assertEqual(self.hint.values, [True])
        slept[0] = 3600
        self.clock.now += 1
        monitor.tick()
        # X meldet weiterhin lange Leerlaufzeit; nach dem Aufwachen zählt das nicht.
        monitor.tick()
        self.assertEqual(self.hint.values, [True, False, False])
        self.assertEqual(gamepads.resets, [self.clock.now])


class AudioTests(unittest.TestCase):
    def test_running_playback_stream_counts(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            status = Path(folder) / 'card0/pcm0p/sub0/status'
            status.parent.mkdir(parents=True)
            status.write_text('closed\n')
            self.assertFalse(idle.audio_playing(Path(folder)))
            status.write_text('state: RUNNING\nowner_pid   : 1\n')
            self.assertTrue(idle.audio_playing(Path(folder)))


class WiringTests(unittest.TestCase):
    def test_services_are_installed_and_started(self):
        self.assertIn('paimenos-idle.service', (ROOT / 'systemd/user/paimenos-session.target').read_text())
        self.assertIn('paimenos-idle.service', (ROOT / 'config/openbox/autostart').read_text())
        self.assertIn('systemctl enable paimenos-power.service', (ROOT / 'installer/80-services.sh').read_text())
        self.assertIn('systemd/user/paimenos-idle.service', (ROOT / 'installer/90-desktop.sh').read_text())


if __name__ == '__main__':
    unittest.main()
