import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deploy', ROOT / 'tools/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns('__pycache__', '.git', 'tmp*'))
        self.base = self.root / 'installed'
        self.base.mkdir()
    def tearDown(self):
        self.temp.cleanup()
    def initial(self):
        release, names = deploy.stage_release(self.source, self.base)
        deploy.activate(self.base, release, initial=True, live=False)
        return release
    def test_full_release_installs_package_and_resources(self):
        release = self.initial()
        self.assertEqual((self.base / 'current').resolve(), release)
        self.assertTrue((release / 'app/laurinos/menu.py').is_file())
        self.assertTrue((release / 'assets/parent-web/base.html').is_file())
        self.assertEqual(release.stat().st_mode & 0o777, 0o755)
        self.assertEqual((release / 'app/laurinos/menu.py').stat().st_mode & 0o777, 0o644)
    def test_component_update_preserves_other_code_and_user_data(self):
        old = self.initial()
        data = self.root / 'home/kids/.config/laurinos/settings.json'
        data.parent.mkdir(parents=True)
        data.write_text('{"pin":"6789","bonus_minutes":9}')
        menu = (old / 'app/laurinos/menu.py').read_bytes()
        controller = self.source / 'src/laurinos/controller.py'
        controller.write_text(controller.read_text() + '\n# Controller fix\n')
        # An unrelated change in the source tree is deliberately not installed.
        unrelated = self.source / 'src/laurinos/menu.py'
        unrelated.write_text(unrelated.read_text() + '\n# Do not deploy this file\n')
        release, names = deploy.stage_release(self.source, self.base, ['controller'])
        deploy.activate(self.base, release, live=False)
        self.assertEqual(names, ['controller'])
        self.assertEqual((release / 'app/laurinos/menu.py').read_bytes(), menu)
        self.assertIn('Controller fix', (release / 'app/laurinos/controller.py').read_text())
        self.assertEqual(data.read_text(), '{"pin":"6789","bonus_minutes":9}')
        self.assertEqual((self.base / 'previous').resolve(), old)
    def test_invalid_python_does_not_switch_current(self):
        old = self.initial()
        (self.source / 'src/laurinos/controller.py').write_text('def broken(:\n')
        with self.assertRaises(SyntaxError):
            deploy.stage_release(self.source, self.base, ['controller'])
        self.assertEqual((self.base / 'current').resolve(), old)
        self.assertFalse(list((self.base / 'releases').glob('.stage-*')))
    def test_rollback_restores_previous_release(self):
        old = self.initial()
        path = self.source / 'src/laurinos/controller.py'
        path.write_text(path.read_text() + '\n# second release\n')
        new, _ = deploy.stage_release(self.source, self.base, ['controller'])
        deploy.activate(self.base, new, live=False)
        deploy.activate(self.base, (self.base / 'previous').resolve(), live=False)
        self.assertEqual((self.base / 'current').resolve(), old)
        self.assertEqual((self.base / 'previous').resolve(), new)
    def test_service_failure_restores_code_and_restarts_old_services(self):
        old = self.initial()
        path = self.source / 'src/laurinos/controller.py'
        path.write_text(path.read_text() + '\n# second release\n')
        new, _ = deploy.stage_release(self.source, self.base, ['controller'])
        error = subprocess.CalledProcessError(1, 'systemctl')
        with patch.object(deploy, 'install_launchers'), patch.object(deploy, 'restart_services', side_effect=[error, None]) as restart:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.activate(self.base, new)
        self.assertEqual((self.base / 'current').resolve(), old)
        self.assertEqual(restart.call_count, 2)
    def test_source_symlink_is_rejected(self):
        file = self.source / 'src/laurinos/controller.py'
        file.unlink()
        file.symlink_to(ROOT / 'src/laurinos/controller.py')
        with self.assertRaises(ValueError):
            deploy.validate_source(self.source)
    def test_unknown_component_is_rejected(self):
        self.initial()
        with self.assertRaises(ValueError):
            deploy.stage_release(self.source, self.base, ['does-not-exist'])
    def test_deleted_component_file_is_removed_from_new_release(self):
        extra = self.source / 'src/laurinos/obsolete.py'
        extra.write_text('VALUE = 1\n')
        manifest = json.loads((self.source / 'manifest.json').read_text())
        manifest['components']['controller']['files'].append('src/laurinos/obsolete.py')
        (self.source / 'manifest.json').write_text(json.dumps(manifest))
        old = self.initial()
        extra.unlink()
        manifest['components']['controller']['files'].remove('src/laurinos/obsolete.py')
        (self.source / 'manifest.json').write_text(json.dumps(manifest))
        new, _ = deploy.stage_release(self.source, self.base, ['controller'])
        self.assertTrue((old / 'app/laurinos/obsolete.py').exists())
        self.assertFalse((new / 'app/laurinos/obsolete.py').exists())
    def test_traversal_is_rejected(self):
        for value in ('../etc/shadow', '/etc/shadow', 'src/../bin/foo', 'src/another_package/foo.py'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                deploy.destination(value)
    def test_unit_install_failure_restores_previous_units_and_code(self):
        old = self.initial()
        path = self.source / 'src/laurinos/controller.py'
        path.write_text(path.read_text() + '\n# second release\n')
        new, _ = deploy.stage_release(self.source, self.base, ['controller'])
        error = subprocess.CalledProcessError(1, 'systemctl daemon-reload')
        with patch.object(deploy, 'install_launchers'), patch.object(deploy, 'apply_units', side_effect=[error, None]) as units, patch.object(deploy, 'restart_services') as restart:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.activate(self.base, new, units=True)
        self.assertEqual((self.base / 'current').resolve(), old)
        self.assertEqual(units.call_args_list[1].args, (old,))
        self.assertEqual(units.call_args_list[1].kwargs, {'previous': new})
        self.assertEqual(restart.call_count, 1)
