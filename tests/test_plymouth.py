"""Offline theme installation and failed activation in a temporary system root."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('paimenos_theme', ROOT / 'tools/install-paimenos-plymouth.py')
theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme)


class PlymouthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        shutil.copytree(ROOT / 'assets/plymouth/paimenos', self.source)
        self.system = self.root / 'system'
        self.destination = self.system / 'usr/share/plymouth/themes/paimenos'

    def rehash(self):
        (self.source / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256((self.source / name).read_bytes()).hexdigest() + '  ' + name + '\n'
            for name in sorted(theme.EXPECTED)))

    def test_install_is_offline_complete_and_repeatable(self):
        with patch.object(theme.subprocess, 'run', side_effect=AssertionError('No external commands')):
            for _ in range(2):
                theme.install(self.system, self.source)
                self.assertEqual({p.name for p in self.destination.iterdir()}, theme.EXPECTED | {'SHA256SUMS'})
                for name in theme.EXPECTED:
                    path = self.destination / name
                    self.assertEqual(path.read_bytes(), (self.source / name).read_bytes())
                    self.assertEqual(path.stat().st_mode & 0o777, 0o644)
                self.assertEqual(self.destination.stat().st_mode & 0o777, 0o755)
                self.assertFalse(list(self.destination.parent.glob('.paimenos-*')))

    def test_corrupt_assets_preserve_installed_theme(self):
        self.destination.mkdir(parents=True)
        (self.destination / 'old.txt').write_text('keep')
        (self.source / 'spin-7.png').write_bytes(b'broken image')
        with self.assertRaisesRegex(ValueError, 'Prüfsumme'):
            theme.install(self.system, self.source)
        self.assertEqual((self.destination / 'old.txt').read_text(), 'keep')

    def test_truncated_png_is_rejected_even_with_matching_file_hash(self):
        logo = self.source / 'logo.png'
        logo.write_bytes(logo.read_bytes()[:-6])
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'PNG'):
            theme.install(self.system, self.source)
        self.assertFalse(self.destination.exists())

    def test_missing_asset_and_symlink_are_rejected(self):
        image = self.source / 'spin-1.png'
        image.unlink()
        with self.assertRaisesRegex(ValueError, 'unvollständig'):
            theme.install(self.system, self.source)
        image.symlink_to(self.source / 'spin-2.png')
        with self.assertRaisesRegex(ValueError, 'Ungültige Theme-Datei'):
            theme.install(self.system, self.source)
        self.assertFalse(self.destination.exists())

    def test_commit_failure_restores_previous_theme_directory(self):
        self.destination.mkdir(parents=True)
        (self.destination / 'old.txt').write_text('keep')
        replace = theme.os.replace
        def failing_replace(source, destination):
            if Path(source).name.startswith('.paimenos-stage-'):
                raise OSError('simulated rename failure')
            return replace(source, destination)
        with patch.object(theme.os, 'replace', side_effect=failing_replace):
            with self.assertRaisesRegex(OSError, 'rename failure'):
                theme.install(self.system, self.source)
        self.assertEqual((self.destination / 'old.txt').read_text(), 'keep')
        self.assertFalse(list(self.destination.parent.glob('.paimenos-*')))

    def test_grub_preserves_existing_options_and_is_idempotent(self):
        grub = self.root / 'grub'
        original = 'GRUB_TIMEOUT=5\nGRUB_CMDLINE_LINUX_DEFAULT="iommu=soft quiet quiet loglevel=4 splash" # own options\n'
        grub.write_text(original)
        theme.configure_grub(grub)
        changed = grub.read_text()
        self.assertIn('iommu=soft', changed)
        self.assertIn('loglevel=4', changed)
        self.assertNotIn('loglevel=3', changed)
        self.assertIn('# own options', changed)
        self.assertEqual(changed.split('"')[1].split().count('quiet'), 1)
        self.assertEqual(changed.split('"')[1].split().count('splash'), 1)
        theme.configure_grub(grub)
        self.assertEqual(grub.read_text(), changed)
        self.assertEqual(grub.with_name('grub.before-laurinos-paimenos').read_text(), original)

    def fake_commands(self, fail_initramfs=False):
        state = {'selected': 'pixels', 'calls': [], 'failed': False}
        def run(command, **kwargs):
            state['calls'].append(command)
            if command == ['plymouth-set-default-theme']:
                return subprocess.CompletedProcess(command, 0, stdout=state['selected'] + '\n')
            if command[0] == 'plymouth-set-default-theme':
                state['selected'] = command[1]
            if command[0] == 'update-initramfs' and fail_initramfs and not state['failed']:
                state['failed'] = True
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout='')
        return state, run

    def test_explicit_activation_rebuilds_all_kernels(self):
        grub = self.system / 'etc/default/grub'
        grub.parent.mkdir(parents=True)
        grub.write_text('GRUB_CMDLINE_LINUX_DEFAULT="custom=1"\n')
        state, run = self.fake_commands()
        theme.activate(self.system, self.source, run)
        self.assertEqual(state['selected'], 'paimenos')
        self.assertEqual(state['calls'][-1], ['update-initramfs', '-u', '-k', 'all'])
        self.assertIn(['update-grub'], state['calls'])
        self.assertIn('custom=1 quiet splash', grub.read_text())

    def test_initramfs_failure_is_reported_and_previous_selection_restored(self):
        grub = self.system / 'etc/default/grub'
        grub.parent.mkdir(parents=True)
        original = b'GRUB_CMDLINE_LINUX_DEFAULT="custom=1"\n'
        grub.write_bytes(original)
        state, run = self.fake_commands(fail_initramfs=True)
        with self.assertRaises(subprocess.CalledProcessError):
            theme.activate(self.system, self.source, run)
        self.assertEqual(state['selected'], 'pixels')
        self.assertEqual(grub.read_bytes(), original)
        self.assertEqual(state['calls'].count(['update-initramfs', '-u', '-k', 'all']), 2)
