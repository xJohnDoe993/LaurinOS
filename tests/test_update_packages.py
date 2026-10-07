import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


packages = module(ROOT / 'tools/install-update-packages.py', 'test_package_installer')
deploy = module(ROOT / 'tools/deploy.py', 'test_package_deployer')
OLD_DEPLOY = ROOT / 'tests/fixtures/deploy-v062.py'


class FakeAPT:
    def __init__(self, installed=(), fail=None):
        self.installed, self.fail, self.calls = set(installed), fail, []
        self.unavailable = set()
        self.leave_missing = False
        self.architectures, self.flags = {}, {}
    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        tool = Path(command[0]).name
        if tool == 'dpkg':
            return subprocess.CompletedProcess(command, 0, stdout='amd64\n')
        if tool == 'dpkg-query':
            return subprocess.CompletedProcess(command, 1,
                stdout=''.join('installed\t' + name + '\t' + self.flags.get(name, 'ok') + '\t'
                              + self.architectures.get(name, 'amd64') + '\n'
                              for name in command[3:] if name in self.installed))
        if tool == 'apt-cache':
            return subprocess.CompletedProcess(command, 0, stdout=''.join(
                name + ':\n  Candidate: ' + ('(none)' if name in self.unavailable else '1:2.0-1') + '\n'
                for name in command[2:]))
        if tool != 'apt-get':
            raise AssertionError('Unexpected command: ' + repr(command))
        action = 'install' if 'install' in command else 'update'
        if self.fail == action:
            raise subprocess.CalledProcessError(100, command, stderr='Simulated APT failure')
        if action == 'install' and not self.leave_missing:
            self.installed.update(value.split('=')[0] for value in command if value.startswith('test-package='))
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')


class PackageInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.root = Path(self.temp.name)
        (self.root / 'installed.json').write_text(json.dumps({
            'components': {'desktop': {}}, 'package_requirements': {'desktop': ['test-package']}}))
        self.apt = FakeAPT()
    def tearDown(self): self.temp.cleanup()
    def ensure(self):
        return packages.ensure_release(self.root, lambda message: None, self.apt, self.root / 'lock')
    def test_missing_install_is_pinned_noninteractive_and_idempotent(self):
        self.assertEqual(self.ensure(), ['test-package'])
        install = next((c, k) for c, k in self.apt.calls if 'install' in c)
        self.assertIn('test-package=1:2.0-1', install[0])
        self.assertIn('--no-remove', install[0])
        self.assertEqual(install[1]['env']['DEBIAN_FRONTEND'], 'noninteractive')
        self.assertEqual(install[1]['env']['NEEDRESTART_MODE'], 'l')
        self.apt.calls.clear(); self.assertEqual(self.ensure(), [])
        self.assertEqual([Path(c[0]).name for c, _ in self.apt.calls], ['dpkg', 'dpkg-query'])
    def test_foreign_architecture_or_reinstallation_required_is_not_ready(self):
        apt = FakeAPT(installed=['test-package'])
        apt.architectures['test-package'] = 'i386'
        self.assertEqual(packages.installed_packages(['test-package'], apt), set())
        apt.architectures['test-package'] = 'amd64'; apt.flags['test-package'] = 'reinstreq'
        self.assertEqual(packages.installed_packages(['test-package'], apt), set())
        apt.architectures['test-package'] = 'all'; apt.flags['test-package'] = 'ok'
        self.assertEqual(packages.installed_packages(['test-package'], apt), {'test-package'})
    def test_failure_of_update_or_install_is_reported_and_retry_works(self):
        for step in ('update', 'install'):
            self.apt = FakeAPT(fail=step)
            with self.subTest(step=step), self.assertRaisesRegex(ValueError, 'Simulated APT failure'):
                self.ensure()
            self.apt.fail = None
            self.assertEqual(self.ensure(), ['test-package'])
    def test_unknown_candidate_and_incomplete_install_fail(self):
        self.apt.unavailable.add('test-package')
        with self.assertRaisesRegex(ValueError, 'Paketquellen'): self.ensure()
        self.assertFalse(any('install' in command for command, _ in self.apt.calls))
        self.apt.unavailable.clear(); self.apt.leave_missing = True
        with self.assertRaisesRegex(ValueError, 'unvollständig'): self.ensure()
    def test_invalid_schema_and_command_like_names_are_rejected(self):
        values = ['--allow-unauthenticated', 'http://example.org/pkg.deb', '../foo', 'foo=1',
                  'foo;touch /tmp/x', 'foo:amd64', 'foo*', '', None]
        for name in values:
            with self.subTest(name=name), self.assertRaises(ValueError):
                packages.validate_requirements({'schema': 1, 'components': {'desktop': [name]}}, {'desktop': {}})
        with self.assertRaises(ValueError):
            packages.validate_requirements({'schema': True, 'components': {}}, {})
        with self.assertRaises(ValueError):
            packages.validate_requirements({'schema': 1, 'components': {'unknown': []}}, {'desktop': {}})
    def test_apt_action_suffix_is_not_passed_without_an_exact_version(self):
        for name in ('test-package-', 'g++'):
            apt = FakeAPT()
            self.assertEqual(packages.candidates([name], apt, {}), [name + '=1:2.0-1'])
    def test_first_upgrade_reads_copied_metadata_without_new_receipt_fields(self):
        (self.root / 'installed.json').write_text(json.dumps({'components': {'desktop': {}}}))
        (self.root / 'data').mkdir()
        (self.root / 'data/update-packages.json').write_text(json.dumps(
            {'schema': 1, 'components': {'desktop': ['test-package']}}))
        self.assertEqual(self.ensure(), ['test-package'])
    def test_metadata_link_is_rejected_even_if_target_does_not_exist(self):
        target = self.root / 'bad.json'; target.symlink_to(self.root / 'missing.json')
        with self.assertRaises(ValueError): packages.read_plan(target, {})


class PackageDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns('.git', 'dist', '__pycache__'))
        self.base = self.root / 'installed'; self.base.mkdir()
    def tearDown(self): self.temp.cleanup()
    def initial(self):
        release, _ = deploy.stage_release(self.source, self.base)
        deploy.activate(self.base, release, live=False)
        return release
    def test_package_failure_keeps_current_and_previous_links_untouched(self):
        old = self.initial()
        (self.source / 'src/paimenos/menu.py').write_text((self.source / 'src/paimenos/menu.py').read_text() + '\n# next\n')
        staged, _ = deploy.stage_release(self.source, self.base)
        with patch.object(deploy, 'ensure_packages', side_effect=ValueError('APT failed')), \
                patch.object(deploy, 'install_launchers') as launcher:
            with self.assertRaisesRegex(ValueError, 'APT failed'): deploy.activate(self.base, staged)
            launcher.assert_not_called()
        self.assertEqual((self.base / 'current').resolve(), old)
        self.assertFalse((self.base / 'previous').exists())
    def test_partial_update_preserves_requirements_of_other_components(self):
        old = self.initial()
        previous = packages.release_requirements(old)
        plan = {'schema': 1, 'components': {'desktop': ['unused-desktop-package'], 'controller': ['test-package']}}
        (self.source / 'data/update-packages.json').write_text(json.dumps(plan))
        staged, _ = deploy.stage_release(self.source, self.base, ['controller'])
        actual = packages.release_requirements(staged)
        self.assertEqual(actual['desktop'], previous['desktop'])
        self.assertEqual(actual['controller'], ['test-package'])
    def test_package_check_precedes_switch_and_offline_activation_has_no_apt(self):
        old = self.initial()
        (self.source / 'src/paimenos/menu.py').write_text((self.source / 'src/paimenos/menu.py').read_text() + '\n# next\n')
        staged, _ = deploy.stage_release(self.source, self.base)
        def prepare(release, progress): self.assertEqual((self.base / 'current').resolve(), old)
        with patch.object(deploy, 'ensure_packages', side_effect=prepare) as check, \
                patch.object(deploy, 'install_launchers'), patch.object(deploy, 'restart_services'):
            deploy.activate(self.base, staged); check.assert_called_once()
        with patch.object(deploy, 'ensure_packages') as check:
            deploy.activate(self.base, old, live=False); check.assert_not_called()

    def test_original_laurinos_deployer_rejects_paimenos_before_activation(self):
        old_deploy = module(OLD_DEPLOY, 'original_062_deployer')
        previous = self.base / 'releases/legacy'
        previous.mkdir(parents=True)
        (self.base / 'current').symlink_to(previous, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Manifest/API'):
            old_deploy.stage_release(self.source, self.base)
        self.assertEqual((self.base / 'current').resolve(), previous)
        self.assertEqual(list((self.base / 'releases').iterdir()), [previous])

    def test_new_deployer_rejects_old_runtime_and_partial_cross_runtime_update(self):
        manifest_path = self.source / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['runtime_api'] = 1
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Manifest/API'):
            deploy.stage_release(self.source, self.base)
        self.assertFalse((self.base / 'current').exists())
        manifest['runtime_api'] = 2
        manifest_path.write_text(json.dumps(manifest))
        previous = self.initial()
        receipt = previous / 'installed.json'
        installed = json.loads(receipt.read_text())
        installed['runtime_api'] = 1
        receipt.write_text(json.dumps(installed))
        with self.assertRaisesRegex(ValueError, 'Paket-API'):
            deploy.stage_release(self.source, self.base, ['desktop'])
        self.assertEqual((self.base / 'current').resolve(), previous)


if __name__ == '__main__': unittest.main()
