import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stage_wifi', ROOT/'tools/stage-wifi.py')
stage = importlib.util.module_from_spec(spec); spec.loader.exec_module(stage)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.config = self.root/'etc/network/interfaces'
        self.config.parent.mkdir(parents=True)
        self.original = 'auto lo wlan0\niface lo inet loopback\niface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk secret123\n'
        self.config.write_text(self.original)
        self.calls, self.fail = [], None
        self.migration = stage.Migration(self.root, self.simulate)
    def tearDown(self): self.temp.cleanup()
    def simulate(self, args, **kwargs):
        self.calls.append(args)
        output = ''
        code = 0
        if args[0] == 'nmcli':
            if '--offline' in args:
                output = kwargs['input'].replace('autoconnect=false','autoconnect=true')
            else: output = 'wlan0:wifi\neth0:ethernet\n'
        elif args[0] == 'systemctl' and 'is-enabled' in args: output = 'disabled\n'
        if self.fail and self.fail in args: code = 1
        return subprocess.CompletedProcess(args, code, stdout=output, stderr='')
    def prepare(self):
        self.assertTrue(self.migration.prepare())
        self.assertEqual(self.config.read_text(), self.original)
        self.assertFalse(self.migration.connections.exists())
        self.assertFalse(any('up' in c or 'down' in c or 'managed' in c or 'restart' in c or 'stop' in c for c in self.calls))
    def test_prepare_is_offline_private_and_does_not_touch_live_connection(self):
        self.prepare()
        plan = json.loads(self.migration.pending.read_text())[0]
        profile = Path(plan['backup'])/'profile.nmconnection'
        self.assertIn('autoconnect=true', profile.read_text())
        self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.migration.state.stat().st_mode & 0o777, 0o700)
    def test_boot_applies_once_without_nm_activation(self):
        self.prepare(); self.calls.clear(); self.migration.apply()
        self.assertNotIn('\niface wlan0', self.config.read_text())
        profiles = list(self.migration.connections.glob('*.nmconnection'))
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.migration.pending.exists())
        self.assertTrue((self.migration.state/'completed.json').exists())
        self.assertFalse(any(c[0] == 'nmcli' for c in self.calls))
        self.migration.apply()
        self.assertEqual(len(list(self.migration.connections.glob('*.nmconnection'))), 1)
    def test_resume_replaces_pending_plan_without_duplicate_profiles(self):
        self.prepare(); self.prepare(); self.migration.apply()
        self.assertEqual(len(list(self.migration.connections.glob('*.nmconnection'))), 1)
    def test_invalid_profile_leaves_files_and_previous_plan_unchanged(self):
        self.prepare(); old = self.migration.pending.read_bytes()
        self.fail = '--offline'
        with self.assertRaises(ValueError): self.migration.prepare()
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.migration.pending.read_bytes(), old)
    def test_boot_failure_rolls_back_files_and_profile(self):
        self.prepare(); self.fail = 'mask'
        with self.assertRaises(ValueError): self.migration.apply()
        self.assertEqual(self.config.read_text(), self.original)
        self.assertFalse(list(self.migration.connections.glob('*.nmconnection')))
        self.assertFalse(list(self.migration.policies.glob('*.conf')))
        self.assertTrue((self.migration.state/'failed.json').exists())
        self.assertFalse(self.migration.journal.exists())
    def test_admin_edits_before_boot_are_not_overwritten(self):
        self.prepare(); self.config.write_text(self.original+'# later edit\n')
        with self.assertRaises(ValueError): self.migration.apply()
        self.assertEqual(self.config.read_text(), self.original+'# later edit\n')
        self.assertFalse(self.migration.connections.exists())
    def test_multiple_adapters_sharing_one_file_are_preserved(self):
        self.original += 'allow-hotplug wlan1\niface wlan1 inet dhcp\n wpa-ssid Second\n wpa-psk password123\n'
        self.config.write_text(self.original)
        previous = self.simulate
        def run(args, **kwargs):
            result = previous(args, **kwargs)
            if args[0] == 'nmcli' and '--offline' not in args: result.stdout = 'wlan0:wifi\nwlan1:wifi\n'
            return result
        self.migration.run = run
        self.prepare(); self.migration.apply()
        self.assertEqual(len(list(self.migration.connections.glob('*.nmconnection'))), 2)
        self.assertNotIn('\niface wlan0', self.config.read_text())
        self.assertNotIn('\niface wlan1', self.config.read_text())
        self.assertIn('iface lo inet loopback', self.config.read_text())
    def test_process_killed_after_interface_edit_recovers_at_next_boot(self):
        self.prepare()
        code = '''import importlib.util, os, subprocess
from pathlib import Path
spec=importlib.util.spec_from_file_location('stage', %r)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
real=s.handoff.write_files
def crash(backup,restore=False):
 real(backup,restore)
 if not restore: os._exit(77)
s.handoff.write_files=crash
run=lambda args,**kw: subprocess.CompletedProcess(args,0,stdout='disabled',stderr='')
s.Migration(Path(%r),run).apply()
''' % (str(ROOT/'tools/stage-wifi.py'),str(self.root))
        result = subprocess.run([sys.executable,'-c',code], timeout=10)
        self.assertEqual(result.returncode,77)
        self.assertTrue(self.migration.journal.exists())
        self.migration.apply()
        self.assertFalse(self.migration.journal.exists())
        self.assertEqual(len(list(self.migration.connections.glob('*.nmconnection'))),1)


if __name__ == '__main__': unittest.main()
