from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from paimenos import emulator_catalog as catalog


class CoreInfoTests(unittest.TestCase):
    def test_both_snes_cores_have_offline_metadata(self):
        with patch.object(catalog, 'CORE_INFO_DIRS', ()):
            for name in ('snes9x', 'bsnes_mercury_performance'):
                core = '/nonexistent/cores/' + name + '_libretro.so'
                directory = catalog.core_info_path(core)
                self.assertEqual(directory, catalog.DATA_DIR / 'libretro-info')
                text = (directory / (name + '_libretro.info')).read_text()
                self.assertIn('savestate = "true"', text)
                self.assertIn('savestate_features = ', text)

    def test_matching_system_metadata_precedes_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'snes9x_libretro.info').write_text('savestate = "false"\n')
            with patch.object(catalog, 'CORE_INFO_DIRS', (directory,)):
                self.assertEqual(catalog.core_info_path('/cores/snes9x_libretro.so'), directory)
                self.assertEqual(catalog.core_info_path('/cores/bsnes_mercury_performance_libretro.so'), catalog.DATA_DIR / 'libretro-info')

    def test_core_adjacent_metadata_and_unknown_core(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(catalog, 'CORE_INFO_DIRS', ()):
            core = Path(tmp) / 'custom_libretro.so'
            self.assertIsNone(catalog.core_info_path(core))
            core.with_suffix('.info').write_text('savestate = "false"\n')
            self.assertEqual(catalog.core_info_path(core), core.parent)
