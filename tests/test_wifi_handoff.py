"""Profile conversion and real shell control flow, with all OS commands mocked."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wifi_handoff', ROOT/'tools/wifi-handoff.py')
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.network = self.root/'network'
        self.network.mkdir()
        self.interfaces = self.network/'interfaces'
        self.backup = self.root/'backup'
        self.backup.mkdir(mode=0o700)
        self.config = patch.object(handoff, 'CONFIG_ROOT', self.network)
        self.config.start()
    def tearDown(self):
        self.config.stop()
        self.temp.cleanup()
    def convert(self, stanza):
        original = 'auto lo eth0 wlan0\niface lo inet loopback\niface eth0 inet dhcp\n' + stanza
        self.interfaces.write_text(original)
        handoff.prepare('wlan0', self.backup)
        handoff.profile('wlan0', self.backup)
        self.assertEqual(self.interfaces.read_text(), original)
        profile = self.backup/'profile.nmconnection'
        self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.backup/'profile.uuid').stat().st_mode & 0o777, 0o600)
        return profile.read_text()
    def test_debian_installer_psk_dhcp_hidden_and_dns(self):
        profile = self.convert('iface wlan0 inet dhcp\n wpa-ssid Home WiFi\n wpa-psk secret#12345\n wpa-scan-ssid 1\n dns-nameservers 192.168.1.1\n dns-search lan\n')
        self.assertIn('ssid=72;111;109;101;32;87;105;70;105;', profile)
        self.assertIn('psk=secret#12345', profile)
        self.assertIn('psk-flags=0', profile)
        self.assertIn('hidden=true', profile)
        self.assertIn('dns=192.168.1.1;', profile)
        self.assertIn('dns-search=lan;', profile)
        self.assertIn('autoconnect=false', profile)
        self.assertIn('may-fail=false', profile)
    def test_hex_key_and_quoted_ssid(self):
        key = 'a'*64
        profile = self.convert('iface wlan0 inet dhcp\n wpa-ssid "Home WiFi"\n wpa-psk '+key+'\n')
        self.assertIn('psk='+key, profile)
    def test_password_spaces_and_backslashes_are_keyfile_escaped(self):
        profile = self.convert('iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk '+json.dumps(' pa ss\\word ')+'\n')
        self.assertIn(r'psk=\spa\sss\\word\s', profile)
    def test_open_network(self):
        profile = self.convert('iface wlan0 inet dhcp\n wpa-ssid Guest\n wpa-key-mgmt NONE\n')
        self.assertNotIn('[wifi-security]', profile)
    def test_wpa_conf_preserves_hash_inside_quoted_password(self):
        conf = self.root/'wpa.conf'
        conf.write_text('ctrl_interface=/run/wpa_supplicant\nnetwork={ # saved\n ssid="Home WiFi" # comment\n psk="secret#12345" # comment\n scan_ssid=1\n}\n')
        profile = self.convert('iface wlan0 inet dhcp\n wpa-conf '+str(conf)+'\n')
        self.assertIn('psk=secret#12345', profile)
        self.assertIn('hidden=true', profile)
    def test_unsupported_configs_never_change_running_configuration(self):
        for stanza in [
            'iface wlan0 inet static\n address 192.168.1.10/24\n wpa-ssid Home\n wpa-psk secret123\n',
            'iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-key-mgmt WPA-EAP\n',
            'iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk short\n',
            'iface wlan0 inet dhcp\n wpa-ssid Home\n',
            'iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk secret123\n post-up echo command\n',
            'iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk secret123\niface wlan0 inet6 static\n address ::1\n',
        ]:
            with self.subTest(stanza=stanza):
                self.interfaces.write_text(stanza)
                handoff.prepare('wlan0', self.backup)
                with self.assertRaises(ValueError): handoff.profile('wlan0', self.backup)
                self.assertEqual(self.interfaces.read_text(), stanza)
                self.assertFalse((self.backup/'profile.nmconnection').exists())
    def test_multiple_wpa_networks_require_explicit_selection(self):
        conf = self.root/'wpa.conf'
        conf.write_text('network={\nssid="Home"\npsk="secret123"\n}\nnetwork={\nssid="Guest"\nkey_mgmt=NONE\n}\n')
        with self.assertRaises(ValueError): handoff.wpa_config(conf)
    def test_wpa_global_includes_and_security_extensions_are_not_ignored(self):
        conf = self.root/'wpa.conf'
        for directive in ('include=/another/config', 'pmf=2', 'ap_scan=2'):
            conf.write_text(directive+'\nnetwork={\nssid="Home"\npsk="secret123"\n}\n')
            with self.assertRaises(ValueError): handoff.wpa_config(conf)
    def test_source_directory_apply_restore_preserves_other_adapters(self):
        included = self.network/'interfaces.d'
        included.mkdir()
        self.interfaces.write_text('auto lo eth0\niface lo inet loopback\niface eth0 inet dhcp\nsource-directory interfaces.d\n')
        wifi = included/'wifi'
        original = 'allow-hotplug wlan0 eth1\niface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk secret123\niface eth1 inet dhcp\n'
        wifi.write_text(original)
        handoff.prepare('wlan0', self.backup)
        handoff.profile('wlan0', self.backup)
        handoff.write_files(self.backup)
        self.assertIn('allow-hotplug eth1\n', wifi.read_text())
        self.assertIn('iface eth1 inet dhcp\n', wifi.read_text())
        self.assertNotIn('\niface wlan0', wifi.read_text())
        handoff.write_files(self.backup, restore=True)
        self.assertEqual(wifi.read_text(), original)
    def test_changes_during_preflight_are_not_overwritten(self):
        self.convert('iface wlan0 inet dhcp\n wpa-ssid Home\n wpa-psk secret123\n')
        self.interfaces.write_text('admin edited this file\n')
        with self.assertRaises(ValueError): handoff.write_files(self.backup)
        self.assertEqual(self.interfaces.read_text(), 'admin edited this file\n')


# Executed instead of nmcli/systemctl/ifupdown/getent/ss/ip. No host devices/services.
MOCK_COMMAND = r"""#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['HANDOFF_TEST_ROOT'])
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with (root/'commands').open('a') as log: log.write(json.dumps([name]+args)+'\n')
state_path = root/'mock-state.json'
state = json.loads(state_path.read_text())
mode = os.environ.get('HANDOFF_TEST_MODE', '')
def save(): state_path.write_text(json.dumps(state))
if name == 'nmcli':
    if 'device' in args and 'status' in args: print('wlan0:wifi\neth0:ethernet')
    elif '-g' in args or '--get-values' in args:
        field = args[args.index('-g')+1] if '-g' in args else args[args.index('--get-values')+1]
        if field == 'GENERAL.TYPE': print('wifi')
        elif field == 'GENERAL.STATE': print('30 (disconnected)' if mode == 'disconnected' else '100 (connected)')
        elif field == 'IP4.ADDRESS':
            if mode != 'no-ip': print('192.168.1.10/24')
        elif field == 'connection.uuid': print('loaded')
    elif 'load' in args and mode == 'bad-load': sys.exit(1)
    elif 'up' in args:
        state['attempted'] = True; save()
        if mode == 'activation-failed': sys.exit(10)
    elif 'down' in args: state['down'] = True; save()
elif name == 'systemctl':
    if 'is-active' in args:
        unit = args[-1]
        sys.exit(0 if unit in ('paimenos-wifi.service', 'ifup@wlan0.service') and
                 (unit != 'ifup@wlan0.service' or mode == 'ifup-service') else 3)
    elif 'is-enabled' in args:
        print('enabled-runtime' if mode in ('wpa-autostart','disable-failed') and args[-1] == 'wpa_supplicant@wlan0.service' else 'disabled')
    elif 'disable' in args and mode == 'disable-failed': sys.exit(1)
elif name == 'ifquery':
    if '--state' in args:
        if state['legacy']: print('wlan0=wlan0')
        else: sys.exit(1)
    elif '--list' in args: print('lo')
    elif os.environ.get('NO_LEGACY_CONFIG'): sys.exit(1)
elif name == 'ifdown': state['legacy'] = False; save()
elif name == 'ifup':
    if mode == 'rollback-failed': sys.exit(1)
    state['legacy'] = True; state['restored'] = True; save()
elif name == 'getent':
    if mode == 'dns-before-failed' or (mode in ('dns-failed','rollback-failed') and state['attempted'] and not state['restored']): sys.exit(2)
    print('192.0.2.1 STREAM deb.debian.org')
elif name == 'ip':
    if mode != 'no-route': print('default via 192.168.1.1 dev wlan0')
elif name == 'ss':
    if mode == 'busy-socket': print('u_dgr ESTAB 0 0 '+str(root/'run/wpa_supplicant/wlan0')+' users:mock')
"""


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.mockbin = self.root/'mockbin'
        self.mockbin.mkdir()
        for name in ('nmcli','systemctl','ifquery','ifup','ifdown','getent','ss','ip','sleep'):
            path = self.mockbin/name
            path.write_text(MOCK_COMMAND); path.chmod(0o755)
        (self.root/'mock-state.json').write_text(json.dumps({'legacy': True, 'attempted': False, 'restored': False}))
        self.env = dict(os.environ, PATH=str(self.mockbin)+':'+os.environ['PATH'], HANDOFF_TEST_ROOT=str(self.root))
        for directory in ('etc/network', 'var/backups', 'run/wpa_supplicant', 'usr/local/lib/paimenos/current/tools'):
            (self.root/directory).mkdir(parents=True)
        helper = (ROOT/'tools/wifi-handoff.py').read_text().replace("Path('/etc/network')", 'Path('+repr(str(self.root/'etc/network'))+')')
        (self.root/'usr/local/lib/paimenos/current/tools/wifi-handoff.py').write_text(helper)
        self.original = 'auto lo wlan0\niface lo inet loopback\niface wlan0 inet dhcp\n wpa-ssid Home WiFi\n wpa-psk secret#12345\n'
        self.interfaces = self.root/'etc/network/interfaces'
        self.interfaces.write_text(self.original)
        self.resolv = self.root/'etc/resolv.conf'
        self.resolv.write_text('nameserver 192.168.1.1\n')
        self.script = self.root/'handoff.sh'
        text = (ROOT/'sbin/paimenos-wlan-handoff').read_text()
        # Only the sandbox copy has paths/ownership checks adapted for test users.
        for prefix in ('/usr/local/', '/etc/', '/var/backups/', '/run/'):
            text = text.replace(prefix, str(self.root)+prefix)
        text = text.replace('[[ "$EUID" -ne 0 ]]', 'false').replace('-o root -g root ', '')
        self.script.write_text(text)
    def tearDown(self): self.temp.cleanup()
    def run_handoff(self, mode=''):
        result = subprocess.run(['bash', str(self.script), 'wlan0'], env=dict(self.env, HANDOFF_TEST_MODE=mode), capture_output=True, text=True, timeout=15)
        self.commands = [json.loads(line) for line in (self.root/'commands').read_text().splitlines()]
        self.assertNotIn('secret#12345', result.stdout+result.stderr)
        self.assertFalse(any(c[0] == 'systemctl' and any(x in c for x in ('stop','restart')) and
                             any(x in c for x in ('NetworkManager.service','wpa_supplicant.service')) for c in self.commands))
        return result
    def test_success_imports_before_ifdown_and_connects_before_masking(self):
        result = self.run_handoff()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        commands = self.commands
        load = next(i for i,c in enumerate(commands) if c[0] == 'nmcli' and 'load' in c)
        down = next(i for i,c in enumerate(commands) if c[0] == 'ifdown')
        up = next(i for i,c in enumerate(commands) if c[0] == 'nmcli' and 'up' in c)
        mask = next(i for i,c in enumerate(commands) if c[0] == 'systemctl' and 'mask' in c)
        self.assertLess(load, down); self.assertLess(down, up); self.assertLess(up, mask)
        profiles = list((self.root/'etc/NetworkManager/system-connections').glob('*.nmconnection'))
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].stat().st_mode & 0o777, 0o600)
        self.assertIn('# PaimenOS / NetworkManager: iface wlan0', self.interfaces.read_text())
        self.assertTrue(any('connection.autoconnect' in c and 'yes' in c for c in commands))
    def test_failures_restore_ifupdown_and_never_accept_disconnected(self):
        for mode in ('activation-failed','disconnected','no-ip','no-route','dns-failed','busy-socket'):
            with self.subTest(mode=mode):
                # Each scenario needs an independent initial filesystem/state.
                self.tearDown(); self.setUp()
                result = self.run_handoff(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.interfaces.read_text(), self.original)
                self.assertEqual(self.resolv.read_text(), 'nameserver 192.168.1.1\n')
                self.assertTrue(any(c[0] == 'ifup' for c in self.commands))
                self.assertFalse(any(c[0] == 'systemctl' and 'mask' in c for c in self.commands))
                self.assertFalse(list((self.root/'etc/NetworkManager/system-connections').glob('*.nmconnection')))
                self.assertFalse(list((self.root/'etc/NetworkManager/conf.d').glob('*.conf')))
    def test_bad_profile_or_prior_dns_do_not_stop_debian_connection(self):
        for mode in ('bad-load','dns-before-failed'):
            with self.subTest(mode=mode):
                self.tearDown(); self.setUp()
                result = self.run_handoff(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.interfaces.read_text(), self.original)
                self.assertFalse(any(c[0] == 'ifdown' or 'managed' in c for c in self.commands))
    def test_unsupported_static_network_is_not_disconnected(self):
        self.original = self.original.replace('inet dhcp', 'inet static')
        self.interfaces.write_text(self.original)
        result = self.run_handoff()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.interfaces.read_text(), self.original)
        self.assertFalse(any(c[0] == 'ifdown' for c in self.commands))
    def test_existing_policy_and_resolver_symlink_are_restored(self):
        policy = self.root/'etc/NetworkManager/conf.d/99-paimenos-handoff-wlan0.conf'
        policy.parent.mkdir(parents=True); policy.write_text('original policy\n')
        self.resolv.unlink(); self.resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
        result = self.run_handoff('activation-failed')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.resolv.readlink(), Path('/run/systemd/resolve/stub-resolv.conf'))
        self.assertEqual(policy.read_text(), 'original policy\n')
    def test_active_ifup_unit_is_stopped_for_handoff(self):
        result = self.run_handoff('ifup-service')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(any(c == ['systemctl', 'stop', 'ifup@wlan0.service'] for c in self.commands))
    def test_inactive_competing_wpa_autostart_is_disabled_after_success(self):
        result = self.run_handoff('wpa-autostart')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn(['systemctl','--runtime','disable','wpa_supplicant@wlan0.service'], self.commands)
        self.assertNotIn(['systemctl','stop','wpa_supplicant@wlan0.service'], self.commands)
    def test_failed_autostart_change_restores_enabled_mode_and_ifupdown(self):
        result = self.run_handoff('disable-failed')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.interfaces.read_text(), self.original)
        self.assertIn(['systemctl','--runtime','enable','wpa_supplicant@wlan0.service'], self.commands)
        self.assertIn(['systemctl','unmask','ifup@wlan0.service'], self.commands)
        self.assertIn(['ifup','wlan0'], self.commands)
    def test_failed_rollback_is_reported_as_unconfirmed(self):
        result = self.run_handoff('rollback-failed')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nicht vollständig bestätigt', result.stderr)
        self.assertNotIn('und DNS wiederhergestellt.', result.stderr)
    def run_installer(self, legacy=True, fail=False):
        self.env['NO_LEGACY_CONFIG'] = '' if legacy else '1'
        launcher = self.root/'usr/local/sbin/paimenos-wlan-handoff'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('printf "handoff\\n" >> "$HANDOFF_TEST_ROOT/events"\nexit '+('1' if fail else '0')+'\n')
        script = (ROOT/'installer/network.sh').read_text()
        # Run exact installer flow, with only root paths and filesystem writes stubbed.
        script = script.replace('/usr/local/sbin/', str(self.root)+'/usr/local/sbin/')
        script = script.replace('config_dir=/etc/NetworkManager/conf.d', 'config_dir='+str(self.root/'etc/NetworkManager/conf.d'))
        script = script.replace('-o root -g root ', '')
        script = 'install_repo_file() { printf "policy\\n" >> "$HANDOFF_TEST_ROOT/events"; cp '+str(ROOT/'config/networkmanager/99-paimenos-wifi-managed.conf')+' "$2"; }\n'+script
        result = subprocess.run(['bash','-c', script], env=self.env, text=True, capture_output=True, timeout=15)
        events = (self.root/'events').read_text().splitlines() if (self.root/'events').exists() else []
        return result, events
    def test_installer_migrates_networking_service_before_general_policy(self):
        result, events = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(events, ['handoff','policy'])
    def test_failed_handoff_stops_setup_before_general_policy(self):
        result, events = self.run_installer(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ['handoff'])
    def test_existing_nm_connection_needs_no_handoff_or_manager_restart(self):
        result, events = self.run_installer(legacy=False)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(events, ['policy'])
        commands = [json.loads(line) for line in (self.root/'commands').read_text().splitlines()]
        self.assertNotIn(['systemctl','restart','NetworkManager.service'], commands)
        policy = self.root/'etc/NetworkManager/conf.d/99-paimenos-wifi-managed.conf'
        self.assertNotIn('[ifupdown]', policy.read_text())


if __name__ == '__main__': unittest.main()
