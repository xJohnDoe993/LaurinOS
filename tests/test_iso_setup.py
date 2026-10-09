"""Exercise the post-install loop with a fake installer, without system changes."""
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupLoopTests(unittest.TestCase):
    def run_setup(self, fail_once=False, installed_locale='de_DE.UTF-8', legacy_locale='', apt_fails_once=False):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pending, success = base / 'pending', base / 'success'
            current, calls = base / 'current', base / 'calls'
            webapps = base / 'webapps.json'
            pending.touch()
            (base / 'iso').mkdir()
            shutil.copytree(ROOT / 'installer', base / 'installer')
            modern, legacy = base / 'locale.conf', base / 'default-locale'
            modern.write_text('LANG=' + installed_locale + '\n')
            legacy.write_text('LANG=' + legacy_locale + '\n')
            helper = base / 'installer/language.sh'
            helper.write_text(helper.read_text().replace('/etc/locale.conf', str(modern)).replace('/etc/default/locale', str(legacy)))
            shutil.copytree(ROOT / 'src', base / 'src')
            shutil.copytree(ROOT / 'assets/i18n', base / 'assets/i18n')
            (base / 'tools').mkdir()
            shutil.copy2(ROOT / 'tools/language.py', base / 'tools/language.py')
            shutil.copy2(ROOT / 'tools/default-webapps.py', base / 'tools/default-webapps.py')
            (base / 'data').mkdir()
            for name in ('default-webapps.json', 'default-webapps.en.json'):
                shutil.copy2(ROOT / 'data' / name, base / 'data' / name)
            (base / 'iso/prepare-apt.py').write_text('''# Test double: no real APT or network changes.
import argparse
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--apt-config', type=Path)
parser.add_argument('--diagnose', action='store_true')
args = parser.parse_args()
if args.apt_config:
    args.apt_config.write_text('APT::Update::Error-Mode "any";\\nAcquire::ForceIPv4 "true";\\n')
''')
            (base / 'bin').mkdir()
            apt = base / 'bin/apt-get'
            apt.write_text(f'''#!/bin/bash
printf '%s\\n' "apt:$*" >> '{calls}'
[[ -r "${{APT_CONFIG:-}}" ]] || exit 99
if [[ {'true' if apt_fails_once else 'false'} == true && ! -e '{base}/apt-tried' ]]; then
    touch '{base}/apt-tried'
    echo 'APT mirror unreachable' >&2
    exit 100
fi
''')
            apt.chmod(0o755)
            installer = base / 'install.sh'
            installer.write_text(f'''#!/bin/bash
printf '%s\\n' "args:$* reboot:$PAIMENOS_REBOOT" >> '{calls}'
printf '%s\\n' "language:$PAIMENOS_LANGUAGE" >> '{calls}'
printf '%s\\n' "apt-config:${{APT_CONFIG:-missing}}" >> '{calls}'
if [[ -r "${{APT_CONFIG:-}}" ]]; then cat "$APT_CONFIG" >> '{calls}'; fi
python3 '{base}/tools/default-webapps.py' > '{webapps}' || exit 1
if [[ {'true' if fail_once else 'false'} == true && ! -e '{current}' ]]; then
    touch '{current}'
    exit 1
fi
touch '{success}'
''')
            systemctl = base / 'systemctl'
            systemctl.write_text(f'#!/bin/bash\nprintf "systemctl:%s\\n" "$*" >> "{calls}"\n')
            systemctl.chmod(0o755)
            script = (ROOT / 'iso/setup-after-install.sh').read_text()
            script = script.replace('[[ $EUID == 0 ]]', '[[ 1 == 1 ]]')
            script = script.replace('/opt/paimenos-source', str(base))
            script = script.replace('/var/lib/paimenos/setup-pending', str(pending))
            script = script.replace('/etc/paimenos-laptop.installed', str(success))
            script = script.replace('/usr/local/lib/paimenos/current', str(current))
            script = script.replace('/run/paimenos-apt.XXXXXX', str(base / 'paimenos-apt.XXXXXX'))
            script = script.replace('systemctl ', str(systemctl) + ' ')
            wrapper = base / 'wrapper.sh'
            wrapper.write_text(script)
            environment = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8', PATH=str(base / 'bin') + ':' + os.environ['PATH'])
            environment.pop('PAIMENOS_LANGUAGE', None)
            result = subprocess.run(['bash', str(wrapper)], input='2\n' * (2 if fail_once or apt_fails_once else 1) + 'n\n',
                                    env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(pending.exists())
            self.assertTrue(success.exists())
            log = calls.read_text()
            self.assertIn('systemctl:disable paimenos-setup.service', log)
            self.assertNotIn('systemctl:reboot', log)
            for filename in re.findall(r'^apt-config:(.+)$', log, re.M):
                if filename != 'missing':
                    self.assertFalse(Path(filename).exists(), 'APT session file survives setup exit')
            return log, result.stdout, json.loads('[' + webapps.read_text() + ']')

    def test_success_disables_setup_without_forcing_reboot(self):
        log, _, _ = self.run_setup()
        self.assertIn('args: reboot:0', log)

    def test_failed_install_is_resumed(self):
        log, _, _ = self.run_setup(fail_once=True)
        self.assertIn('args:--resume reboot:0', log)

    def test_apt_session_reaches_installer_and_is_removed(self):
        log, _, _ = self.run_setup()
        self.assertIn('apt:update', log)
        self.assertNotIn('apt-config:missing', log)
        self.assertIn('Acquire::ForceIPv4 "true";', log)
        self.assertIn('APT::Update::Error-Mode "any";', log)

    def test_mirror_failure_returns_to_menu_before_installation(self):
        log, output, _ = self.run_setup(apt_fails_once=True)
        self.assertEqual(log.count('apt:update'), 2)
        self.assertEqual(log.count('args: reboot:0'), 1)
        self.assertLess(log.rindex('apt:update'), log.index('args: reboot:0'))
        self.assertIn('Debian-Paketquellen konnten nicht vollständig geprüft werden.', output)

    def test_english_first_boot_uses_installed_locale_and_english_webapps(self):
        log, output, apps = self.run_setup(installed_locale='en_GB.UTF-8', legacy_locale='de_DE.UTF-8')
        self.assertIn('Welcome to PaimenOS!', output)
        self.assertIn('2) Start PaimenOS setup', output)
        self.assertNotIn('Willkommen bei PaimenOS!', output)
        self.assertIn('language:en', log)
        self.assertEqual({app['id'] for app in apps},
                         {'pbs-kids', 'learnenglish-kids', 'nasa-space-place', 'blockly-games', 'scratch-web'})

    def test_german_first_boot_ignores_stale_english_locale(self):
        log, output, apps = self.run_setup(installed_locale='de_DE.UTF-8', legacy_locale='en_US.UTF-8')
        self.assertIn('Willkommen bei PaimenOS!', output)
        self.assertIn('language:de', log)
        self.assertEqual(apps, json.loads((ROOT / 'data/default-webapps.json').read_text()))

    def test_uninstalled_live_system_does_not_start_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            script = (ROOT / 'iso/setup-after-install.sh').read_text()
            script = script.replace('[[ $EUID == 0 ]]', '[[ 1 == 1 ]]')
            script = script.replace('/var/lib/paimenos/setup-pending', directory + '/absent')
            wrapper = Path(directory) / 'wrapper.sh'
            wrapper.write_text(script)
            result = subprocess.run(['bash', str(wrapper)], text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
