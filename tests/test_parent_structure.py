import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from unittest.mock import patch

from paimenos.bluetooth import BluetoothController, ADAPTER, DEVICE

HAS_QT = importlib.util.find_spec('PyQt5') is not None


class FakeDriver:
    def __init__(self, objects):
        self._objects = objects

    def objects(self):
        return self._objects


class BluetoothNameTests(unittest.TestCase):
    def test_devices_report_whether_bluez_knows_a_real_name(self):
        objects = {
            '/org/bluez/hci0': {ADAPTER: {'Alias': 'Laptop', 'Powered': True}},
            '/org/bluez/hci0/dev_1': {DEVICE: {'Adapter': '/org/bluez/hci0', 'Address': 'AA:BB:CC:DD:EE:01',
                                               'Alias': 'Xbox Wireless Controller', 'Name': 'Xbox Wireless Controller'}},
            '/org/bluez/hci0/dev_2': {DEVICE: {'Adapter': '/org/bluez/hci0', 'Address': 'AA:BB:CC:DD:EE:02',
                                               'Alias': 'AA-BB-CC-DD-EE-02'}},
        }
        devices = {d['address']: d for d in BluetoothController(FakeDriver(objects)).snapshot()['devices']}
        self.assertTrue(devices['AA:BB:CC:DD:EE:01']['named'])
        self.assertFalse(devices['AA:BB:CC:DD:EE:02']['named'])
        self.assertEqual(devices['AA:BB:CC:DD:EE:02']['name'], 'AA-BB-CC-DD-EE-02')


def device(address, named, paired=False):
    return {'path': '/dev_' + address, 'adapter': '/hci0', 'name': 'Pad' if named else address.replace(':', '-'),
            'named': named, 'address': address, 'icon': '', 'paired': paired, 'connected': False, 'trusted': False}


@unittest.skipUnless(HAS_QT, 'PyQt5 required')
class LocalParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def texts(self, widget):
        from PyQt5.QtWidgets import QLabel
        return [label.text() for label in widget.findChildren(QLabel)]

    def test_local_bluetooth_hides_unnamed_found_devices_but_never_paired_ones(self):
        from paimenos import bluetooth_ui
        with patch.object(bluetooth_ui.ParentBluetooth, 'refresh'):
            dialog = bluetooth_ui.ParentBluetooth()
        self.addCleanup(dialog.deleteLater)
        state = {'available': True, 'adapters': [{'path': '/hci0', 'name': 'Laptop', 'powered': True}],
                 'devices': [device('AA:00:00:00:00:01', True), device('AA:00:00:00:00:02', False),
                             device('AA:00:00:00:00:03', False, paired=True)],
                 'scan': None, 'operation': None, 'prompt': None, 'message': '', 'error': ''}
        dialog.hide_unnamed.setChecked(True)
        dialog.render(state)
        shown = self.texts(dialog.devices.widget())
        self.assertIn('Pad', shown)
        self.assertNotIn('AA-00-00-00-00-02', shown)
        self.assertIn('AA-00-00-00-00-03', shown)
        from paimenos.i18n import t
        self.assertIn(t('{value0} Gerät(e) ohne Namen ausgeblendet.', value0=1), shown)
        dialog.hide_unnamed.setChecked(False)
        self.assertIn('AA-00-00-00-00-02', self.texts(dialog.devices.widget()))
        bluetooth_ui.ParentBluetooth.remember_hide_unnamed = True

    def test_backups_tab_defaults_and_restore_confirmation(self):
        from paimenos import backups, parent_ui_system
        found = [{'id': 'backup-20261010T180000-abcdefabcdef', 'date': 'heute', 'groups': ['saves'], 'size': 1}]
        with patch.object(backups, 'offered', return_value=['roms', 'saves', 'bios', 'app-tuxpaint', 'files']), \
                patch.object(parent_ui_system, 'submit_task'):
            tab = parent_ui_system.BackupsTab()
        self.addCleanup(tab.stop)
        self.assertTrue(tab.group_boxes['app-tuxpaint'].isChecked())
        self.assertFalse(tab.group_boxes['files'].isChecked())
        tab.completed('drives', [{'id': 'usb', 'label': 'Stick', 'free': 0}], '')
        tab.completed(('found', 'usb'), found, '')
        from PyQt5.QtWidgets import QCheckBox, QMessageBox
        with patch.object(backups, 'start') as start, patch.object(QMessageBox, 'warning') as warning:
            tab.restore(found[0], {'saves': QCheckBox()}, QCheckBox())
            warning.assert_called_once()
            start.assert_not_called()
            confirm = QCheckBox(); confirm.setChecked(True)
            saves = QCheckBox(); saves.setChecked(True)
            tab.restore(found[0], {'saves': saves}, confirm)
            start.assert_called_once_with('restore', 'usb', ['saves'], found[0]['id'])

    def test_updates_tab_only_installs_from_the_default_source(self):
        from paimenos import parent_ui_system
        with patch.object(parent_ui_system, 'submit_task'):
            tab = parent_ui_system.UpdatesTab()
        self.addCleanup(tab.stop)
        state = {'current_version': '0.66.1', 'update_available': True, 'last_checked': 1, 'checking': False,
                 'check_error': '', 'job': None, 'release': {'version': '0.67.0', 'tag': 'v0.67.0', 'notes': 'Neu'}}
        tab.render(state)
        self.assertTrue(tab.install_button.isEnabled())
        self.assertEqual(tab.notes.toPlainText(), 'Neu')
        state['release']['source_override'] = True
        tab.render(state)
        self.assertFalse(tab.install_button.isEnabled())
        tab.render(dict(state, job={'status': 'running', 'progress': 40, 'message': 'Lädt'}))
        self.assertFalse(tab.check_button.isEnabled())
        self.assertEqual(tab.job_progress.value(), 40)


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask required')
class WebStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from paimenos import paths
        cls.tmp = tempfile.TemporaryDirectory()
        with patch.object(paths, 'CONFIG_DIR', Path(cls.tmp.name)):
            from paimenos import parent_web
        cls.web = parent_web
        cls.web.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.web.app.test_client()
        p = patch.object(self.web, 'read_settings', return_value={'pin': '123456'})
        p.start(); self.addCleanup(p.stop)
        with self.client.session_transaction() as s:
            s.update(parent_authenticated=True, pin_fingerprint=self.web.pin_fingerprint(), csrf_token='csrf')

    def test_navigation_is_grouped_child_connections_system(self):
        page = self.client.get('/bluetooth').get_data(as_text=True)
        nav = page[page.index('<nav'):page.index('</nav>')]
        order = [nav.index(href) for href in ('href="/"', '/time', '/apps', '/emulators', '/wifi', '/bluetooth',
                                               '/controllers', '/backups', '/updates', '/settings', '/diagnostics')]
        self.assertEqual(order, sorted(order))
        self.assertEqual(nav.count('class="nav-sep"'), 2)
        self.assertIn('id="bt-hide-unnamed" checked', page)


if __name__ == '__main__':
    unittest.main()
