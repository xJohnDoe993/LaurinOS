"""Exercise the post-install loop with a fake installer, without system changes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupLoopTests(unittest.TestCase):
    def run_setup(self, fail_once=False):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pending, success = base / 'pending', base / 'success'
            current, calls = base / 'current', base / 'calls'
            pending.touch()
            (base / 'iso').mkdir()
            (base / 'iso/prepare-apt.py').write_text('# test double: no real APT changes\n')
            installer = base / 'install.sh'
            installer.write_text(f'''#!/bin/bash
printf '%s\\n' "args:$* reboot:$PAIMENOS_REBOOT" >> '{calls}'
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
            script = script.replace('systemctl ', str(systemctl) + ' ')
            wrapper = base / 'wrapper.sh'
            wrapper.write_text(script)
            result = subprocess.run(['bash', str(wrapper)], input='2\n' * (2 if fail_once else 1) + 'n\n',
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(pending.exists())
            self.assertTrue(success.exists())
            log = calls.read_text()
            self.assertIn('systemctl:disable paimenos-setup.service', log)
            self.assertNotIn('systemctl:reboot', log)
            return log

    def test_success_disables_setup_without_forcing_reboot(self):
        log = self.run_setup()
        self.assertIn('args: reboot:0', log)

    def test_failed_install_is_resumed(self):
        log = self.run_setup(fail_once=True)
        self.assertIn('args:--resume reboot:0', log)

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
