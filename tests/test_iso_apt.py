import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('iso_apt', ROOT / 'iso/prepare-apt.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AptTests(unittest.TestCase):
    def test_cdrom_only_system_gets_main_and_security_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apt = root / 'etc/apt'
            apt.mkdir(parents=True)
            source = apt / 'sources.list'
            original = 'deb cdrom:[Debian 13 LIVE/INSTALL]/ trixie main\n'
            source.write_text(original)
            module.configure(root)
            self.assertTrue(source.read_text().startswith('#'))
            self.assertEqual(source.with_name('sources.list.before-paimenos-iso').read_text(), original)
            online = apt / 'sources.list.d/paimenos-iso.sources'
            first = online.read_text()
            self.assertIn('Components: main contrib non-free non-free-firmware', first)
            self.assertIn('Suites: trixie-security', first)
            module.configure(root)
            self.assertEqual(online.read_text(), first)

    def test_deb822_media_disabled_online_source_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'etc/apt/sources.list.d'
            folder.mkdir(parents=True)
            source = folder / 'debian.sources'
            online = 'Types: deb\nURIs: https://deb.debian.org/debian\nSuites: trixie\nComponents: main\n'
            source.write_text('Types: deb\nURIs: cdrom:Debian\nSuites: trixie\nComponents: main\n\n' + online)
            module.configure(root)
            self.assertIn('Enabled: no', source.read_text())
            self.assertIn(online, source.read_text())
            entries = list(module.components.entries((folder / 'paimenos-iso.sources').read_text(), '.sources'))
            self.assertNotIn('main', next(areas for suite, areas in entries if suite == 'trixie'))
