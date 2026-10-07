"""PIN bootstrap never writes child paths as root or opens endpoints early."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('iso_first_boot', ROOT / 'iso/first-boot.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FirstBootTests(unittest.TestCase):
    def test_invalid_pin_retried_and_settings_written_as_child(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pending = base / 'pending'
            pending.touch()
            (base / 'settings.json').write_text('{"daily_limit": 60}')
            with patch.object(module, 'BASE', base), patch.object(module, 'PENDING', pending), \
                 patch.object(module.os, 'geteuid', return_value=0), \
                 patch.object(module.sys, 'argv', ['first-boot']), \
                 patch('builtins.open', return_value=open(base / 'lock', 'w')), \
                 patch.object(module.getpass, 'getpass', side_effect=['bad', 'bad', '4567', '4567']), \
                 patch.object(module.subprocess, 'run') as run:
                module.main()
                self.assertEqual(run.call_args_list[0].args[0][:4], ['runuser', '-u', 'kids', '--'])
                self.assertEqual(json.loads(run.call_args_list[0].kwargs['input'])['pin'], '4567')
                self.assertFalse(pending.exists())
                self.assertEqual(run.call_args_list[1].args[0][0:2], ['systemctl', 'start'])

    def test_write_failure_keeps_endpoints_gated(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            pending = base / 'pending'
            pending.touch()
            (base / 'settings.json').write_text('{}')
            with patch.object(module, 'BASE', base), patch.object(module, 'PENDING', pending), \
                 patch.object(module.os, 'geteuid', return_value=0), \
                 patch.object(module.sys, 'argv', ['first-boot']), \
                 patch('builtins.open', return_value=open(base / 'lock', 'w')), \
                 patch.object(module.getpass, 'getpass', return_value='4567'), \
                 patch.object(module.subprocess, 'run', side_effect=OSError('write failed')) as run:
                with self.assertRaises(OSError):
                    module.main()
                self.assertTrue(pending.exists())
                self.assertEqual(run.call_count, 1)

    def test_completed_setup_is_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(module, 'PENDING', base / 'pending'), \
                 patch.object(module.os, 'geteuid', return_value=0), \
                 patch.object(module.sys, 'argv', ['first-boot']), \
                 patch('builtins.open', return_value=open(base / 'lock', 'w')), \
                 patch.object(module.subprocess, 'run') as run:
                module.main()
                run.assert_not_called()
