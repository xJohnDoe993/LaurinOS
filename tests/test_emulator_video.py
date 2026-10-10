from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from paimenos import emulators
from paimenos.emulator_catalog import CATALOG


class VideoProfileTests(unittest.TestCase):
    def test_every_launcher_writes_consistent_display_and_preserves_save_policy(self):
        for system in CATALOG:
            with self.subTest(system=system), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                game = root / 'roms/rom-test/game.rom'
                game.parent.mkdir(parents=True)
                game.write_bytes(b'fixture')
                with patch.object(emulators, 'ROOT', root), patch.object(emulators, 'core_path', return_value='/cores/test_libretro.so'), patch.object(emulators, 'ready', return_value=True), patch.object(emulators, 'ps1_preflight', return_value=('eu', [])), patch.object(emulators.controllers, 'effective_autoconfig', return_value=root), patch('paimenos.emulator_session.run_session', return_value=0):
                    emulators.launch(system, str(game))
                lines = (root / ('retroarch-paimenos-' + system + '.cfg')).read_text().splitlines()
                keys = [line.split(' = ', 1)[0] for line in lines]
                self.assertEqual(len(keys), len(set(keys)), 'Conflicting duplicate settings')
                config = dict(line.split(' = ', 1) for line in lines)
                self.assertEqual(config['aspect_ratio_index'], '"22"')
                self.assertEqual(config['video_vsync'], '"true"')
                self.assertEqual(config['savestate_auto_load'], '"false"')
                self.assertEqual(config['sort_savestates_enable'], '"false"')
                for key in ('rewind_enable', 'run_ahead_enabled', 'preemptive_frames_enable', 'video_shader_enable'):
                    self.assertEqual(config[key], '"false"')
                is_3d = system in ('ps1', 'n64', 'psp')
                self.assertEqual(config['video_smooth'], '"true"' if is_3d else '"false"')
                self.assertEqual(config['video_scale_integer'], '"false"' if is_3d else '"true"')
                if is_3d:
                    options = (root / (system + '-paimenos-options.cfg')).read_text()
                    if system == 'psp':
                        self.assertIn('ppsspp_cpu_core = "JIT"', options)
                        self.assertIn('ppsspp_texture_scaling_level = "disabled"', options)
                        self.assertIn('ppsspp_auto_frameskip = "disabled"', options)
                    if system == 'n64':
                        self.assertIn('mupen64plus-EnableFBEmulation = "True"', options)
                        self.assertIn('mupen64plus-EnableNativeResFactor = "1"', options)
